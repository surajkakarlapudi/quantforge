"""Stable, filing-independent QName resolution.

XBRL identifies concepts, axes, and members by **qualified name** (QName): a
namespace URI plus a local name. In the source document a QName is written with
a *prefix* (``us-gaap:Revenue``), but the prefix is only a local alias — the same
namespace URI may be bound to different prefixes in different filings (recon
§II.7). Identity must therefore be keyed on the **namespace URI**, never the
prefix, or two byte-identical facts from different filings would hash
differently (data-model §11, §12 invariant 18).

This module canonicalizes every QName to **Clark notation** — ``{uri}local`` —
which ``xml.etree.ElementTree`` already uses for element tags. Two responsibilities:

* Element/attribute *tags* arrive from ElementTree already in Clark notation;
  :func:`split_clark` / :func:`local_name` decompose them.
* QNames that appear as attribute **values** or element **text** (an
  ``xbrldi:explicitMember`` ``dimension`` axis and its member value) carry a raw
  prefix that must be resolved against the document's in-scope namespace
  declarations. :class:`NamespaceContext` performs that resolution.

Determinism/fail-closed: prefix→URI bindings are collected from the document's
namespace declarations. If a prefix is rebound to a *different* URI anywhere in
the document, global resolution would be ambiguous, so we fail closed
(:class:`UnsupportedXbrlError`) rather than silently pick one binding.
"""

from __future__ import annotations

from openfinance.xbrl.errors import MalformedXbrlError, UnsupportedXbrlError

__all__ = [
    "NamespaceContext",
    "QName",
    "local_name",
    "namespace_uri",
    "split_clark",
]


def split_clark(tag: str) -> tuple[str | None, str]:
    """Split a Clark-notation tag ``{uri}local`` into ``(uri, local)``.

    A tag with no namespace (``local``) yields ``(None, "local")``. This is the
    inverse of ElementTree's tag encoding and never guesses a namespace.
    """
    if tag.startswith("{"):
        end = tag.find("}")
        if end == -1:  # pragma: no cover - ElementTree never emits this
            raise MalformedXbrlError(f"malformed Clark-notation tag: {tag!r}")
        return tag[1:end], tag[end + 1 :]
    return None, tag


def local_name(tag: str) -> str:
    """Return just the local part of a Clark-notation tag."""
    return split_clark(tag)[1]


def namespace_uri(tag: str) -> str | None:
    """Return just the namespace URI of a Clark-notation tag, or ``None``."""
    return split_clark(tag)[0]


class QName:
    """A resolved qualified name: a namespace URI plus a local name.

    The canonical string form is Clark notation (``{uri}local``), which is
    stable across filings because it never depends on the source prefix. A
    QName with no namespace renders as its bare local name.
    """

    __slots__ = ("local", "uri")

    def __init__(self, uri: str | None, local: str) -> None:
        self.uri = uri or None
        self.local = local

    @classmethod
    def from_clark(cls, tag: str) -> QName:
        uri, local = split_clark(tag)
        return cls(uri, local)

    @property
    def clark(self) -> str:
        """The canonical ``{uri}local`` (or bare ``local``) string."""
        return f"{{{self.uri}}}{self.local}" if self.uri else self.local

    def __str__(self) -> str:
        return self.clark

    def __repr__(self) -> str:
        return f"QName({self.clark!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QName):
            return NotImplemented
        return self.uri == other.uri and self.local == other.local

    def __hash__(self) -> int:
        return hash((self.uri, self.local))


class NamespaceContext:
    """Resolves prefixed QName *values* to stable Clark notation.

    Built from the prefix→URI bindings declared in the source document (captured
    from ``xmlns`` declarations). Resolving keys identity on the namespace URI,
    so the same logical axis/member resolves identically regardless of the
    prefix a given filing chose.
    """

    __slots__ = ("_by_prefix",)

    def __init__(self, bindings: dict[str, str]) -> None:
        # Maps prefix ("" == default namespace) -> namespace URI.
        self._by_prefix = dict(bindings)

    def add(self, prefix: str, uri: str) -> None:
        """Record a prefix→URI binding, failing closed on rebinding conflicts.

        Re-declaring the same prefix with the **same** URI is a no-op (XBRL
        instances routinely repeat root declarations). Re-declaring it with a
        **different** URI makes global resolution ambiguous — we refuse to guess.
        """
        existing = self._by_prefix.get(prefix)
        if existing is not None and existing != uri:
            raise UnsupportedXbrlError(
                f"namespace prefix {prefix!r} is rebound from {existing!r} to "
                f"{uri!r}; ambiguous QName resolution is not supported"
            )
        self._by_prefix[prefix] = uri

    def resolve(self, value: str) -> QName:
        """Resolve a raw ``prefix:local`` (or ``local``) QName value.

        An unprefixed value resolves against the default namespace when one is
        declared, else it has no namespace. An unknown prefix is a malformed
        document (the value references a namespace the document never declared),
        so we fail closed rather than fabricate a namespace.
        """
        raw = value.strip()
        if not raw:
            raise MalformedXbrlError("empty QName value")
        if ":" in raw:
            prefix, _, local = raw.partition(":")
            uri = self._by_prefix.get(prefix)
            if uri is None:
                raise MalformedXbrlError(
                    f"QName {raw!r} uses undeclared namespace prefix {prefix!r}"
                )
            return QName(uri, local)
        # Unprefixed: bind to the default namespace if the document declared one.
        return QName(self._by_prefix.get(""), raw)
