"""The explicit, ordered, content-addressed factor universe (``docs/factors.md`` §7.1).

A cross-sectional factor needs a set of filers to evaluate across. Per Decision F1
that set is **caller-supplied and explicit** — never an enumeration of whatever
happens to be locally ingested, which would couple a factor's identity and value
to a machine's ingestion state (a reproducibility break and a silent
look-ahead-by-ingestion risk, §1.3).

:class:`Universe` is therefore an **explicit, ordered, de-duplicated, frozen**
tuple of canonical ``company_id``s (``cik:`` + 10-digit form; a bare CIK or
``CIK``-prefixed value is canonicalized via the Phase 2 identity helpers). Its
``universe_id`` is a content hash over the *ordered* members, so two requests with
the same members in the same order share identity and reproduce, and a change in
membership *or order* yields a new id. An empty universe fails closed
(:class:`FactorConfigurationError`) — a factor over nobody is a configuration bug.

There is deliberately **no** "all filers" constructor (F1): a caller assembles a
universe from resolved ``Company`` / CIK values it already holds.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from quantforge.factors.errors import FactorConfigurationError
from quantforge.registry.identity import company_id as _company_id
from quantforge.sec.artifacts import sha256_hex

__all__ = ["Universe"]

# A separator that cannot occur in a company_id (they are `cik:`+digits), so a
# joined payload is unambiguous — the §11 identity convention, shared with the
# Merkle-manifest and metric-id hashing.
_SEP = "\x00"


@dataclass(frozen=True, slots=True)
class Universe:
    """An explicit, ordered, de-duplicated set of filer identities (§7.1).

    Construct via :meth:`of` (from tickers-resolved ``company_id``s or CIKs a
    caller already holds); the constructor canonicalizes and de-duplicates while
    **preserving first-seen order**, so the caller's declared order is the
    cross-section's cell order (§6.1). Frozen and hashable; ``members`` is the
    canonical, ordered tuple used for both iteration and identity.
    """

    members: tuple[str, ...]

    @classmethod
    def of(cls, *identifiers: str | int) -> Universe:
        """Build a universe from explicit CIKs / ``company_id``s (F1, §7.1).

        Each identifier is canonicalized to a ``cik:``+10-digit ``company_id`` via
        the Phase 2 identity rule (so a bare int ``320193``, the string
        ``"320193"``, and ``"cik:0000320193"`` all map to one member). Duplicates
        are dropped keeping first-seen order. An empty universe — no identifiers,
        or all duplicates collapsing to nothing — fails closed.
        """
        return cls.from_iterable(identifiers)

    @classmethod
    def from_iterable(cls, identifiers: Iterable[str | int]) -> Universe:
        """Build a universe from an iterable of CIKs / ``company_id``s (§7.1)."""
        ordered: list[str] = []
        seen: set[str] = set()
        for identifier in identifiers:
            member = cls._canonical_member(identifier)
            if member in seen:
                continue
            seen.add(member)
            ordered.append(member)
        if not ordered:
            raise FactorConfigurationError(
                "a factor universe must contain at least one filer; "
                "an empty universe is a configuration bug, not an empty result"
            )
        return cls(members=tuple(ordered))

    @staticmethod
    def _canonical_member(identifier: str | int) -> str:
        """Canonicalize one identifier to a ``company_id``; fail closed if unusable.

        Reuses the Phase 2 :func:`company_id` rule so identity is the same across
        phases (§11). A value that cannot be read as a CIK is a configuration bug
        (we never guess a filer), surfaced as :class:`FactorConfigurationError`.
        """
        try:
            if isinstance(identifier, str) and identifier.startswith("cik:"):
                # Already a company_id; re-canonicalize the numeric part so an
                # unpadded `cik:320193` normalizes identically to `cik:0000320193`.
                return _company_id(identifier[len("cik:") :])
            return _company_id(identifier)
        except (ValueError, TypeError) as exc:
            raise FactorConfigurationError(
                f"universe member {identifier!r} is not a usable CIK / company_id"
            ) from exc

    @property
    def universe_id(self) -> str:
        """Content hash over the *ordered* members: ``sha256(universe, m0, m1, …)``.

        Order-sensitive (a rank/percentile tie is broken by member order, §6.2) and
        prefixed with a domain tag so it cannot collide with any other id space.
        Re-declaring the identical ordered universe reproduces the same id
        (invariant 20 analogue).
        """
        payload = _SEP.join(("universe", *self.members))
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    def __len__(self) -> int:
        return len(self.members)

    def __iter__(self) -> Iterator[str]:
        return iter(self.members)
