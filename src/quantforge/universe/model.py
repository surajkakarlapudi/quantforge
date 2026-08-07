"""The universe: a deterministic, point-in-time collection of filer identities.

Phase 9.1 is the **universe-management foundation** for cross-sectional research.
A :class:`Universe` is an immutable, ordered, de-duplicated collection of filer
identities assembled from caller-supplied identifiers — the securities a later
ranking, portfolio, or backtest step will operate across. This phase builds *only*
that foundation: no ranking, no portfolios, no backtesting.

The layer **composes, never duplicates** the company identity layer. It owns no
identifier system of its own: every member is a
:class:`~quantforge.identity.model.CompanyIdentity` produced by the existing
:class:`~quantforge.identity.resolve.CompanyResolver`, keyed by the canonical
``company_id`` (data-model §11). A ticker or name is a descriptive label that never
participates in identity — exactly as at the :class:`~quantforge.company.Company`
front door.

The front door is :meth:`Universe.from_companies`::

    from quantforge.universe import Universe

    universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"])
    for company_id in universe:
        ...

Three properties are load-bearing (ARCHITECTURE.md principles 3, 5):

* **Deterministic ordering.** Members are canonicalized and de-duplicated while
  **preserving first-seen order**, so the caller's declared order is the universe's
  order. Identical inputs always yield an identical universe — no reliance on
  wall-clock time, hashing order, or resolution-cache state.
* **Provenance.** Each member carries how it was resolved (the exact identifier the
  caller supplied and which lookup matched), and the universe carries the pinned
  :class:`~quantforge.universe.version.UniverseBuilderVersion` that built it. The
  full record is serializable via :meth:`to_dict` for audit.
* **Content-addressed identity.** :attr:`universe_id` is a SHA-256 over the ordered
  ``company_id`` members, using the *same* domain-tagged scheme as the
  cross-sectional factor universe — so a universe assembled here and a factor
  universe over the same ordered members share one id and reproduce.

An empty universe fails closed (:class:`UniverseConfigurationError`): a universe
over nobody is a configuration bug, not an empty result.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from quantforge.identity.model import CompanyIdentity
from quantforge.sec.artifacts import sha256_hex
from quantforge.universe.errors import UniverseConfigurationError
from quantforge.universe.version import UniverseBuilderVersion

__all__ = ["Universe"]

# A separator that cannot occur in a company_id (they are `cik:`+digits), so a
# joined payload is unambiguous. This is the §11 identity convention shared with
# the Merkle manifest, the metric-id hashing, and — deliberately — the factor
# universe (see :attr:`Universe.universe_id`).
_SEP = "\x00"


@dataclass(frozen=True, slots=True)
class Universe:
    """An immutable, ordered, de-duplicated collection of filer identities.

    Construct via :meth:`from_companies` (resolve tickers/CIKs/names through the
    company identity layer) or :meth:`from_identities` (when identities are already
    in hand). Frozen and hashable; ``identities`` is the canonical, ordered tuple
    used for iteration, identity, and provenance.
    """

    #: The resolved members, in deterministic first-seen order, de-duplicated by
    #: canonical ``company_id``. Each carries its own resolution provenance.
    identities: tuple[CompanyIdentity, ...]
    #: The pinned construction logic that built this universe (provenance).
    builder_version: UniverseBuilderVersion = field(
        default_factory=UniverseBuilderVersion
    )

    # -- construction --------------------------------------------------------

    @classmethod
    def from_companies(
        cls,
        identifiers: Iterable[str],
        *,
        by: str | None = None,
        workspace: object | None = None,
    ) -> Universe:
        """Build a universe by resolving ``identifiers`` through the identity layer.

        Each identifier (a ticker like ``"AAPL"``, a CIK, or an exact company name)
        is resolved by the existing
        :class:`~quantforge.identity.resolve.CompanyResolver` — this layer creates
        no identifier system of its own and never guesses a filer. ``by`` optionally
        forces the interpretation (``"cik"`` / ``"ticker"`` / ``"name"``) for every
        identifier, mirroring :meth:`Company.resolve`.

        ``workspace`` supplies the wired resolver; when omitted a default
        :class:`~quantforge.workspace.Workspace` is opened from the environment.
        Duplicates (distinct spellings of one filer) collapse to a single member,
        keeping first-seen order. An unknown or ambiguous symbol fails closed via
        the identity layer's own error; an empty universe fails closed here.
        """
        # A bare string is iterable character-by-character — a silent, nasty bug
        # (``from_companies("AAPL")`` would try to resolve "A", "A", "P", "L").
        # Refuse it: we never guess whether a string is one identifier or many.
        if isinstance(identifiers, str):
            raise UniverseConfigurationError(
                "from_companies expects an iterable of identifiers "
                f"(e.g. ['AAPL', 'MSFT']); got a bare string {identifiers!r}"
            )

        # Imported lazily to avoid a module-load import cycle: Workspace wires the
        # whole stack, and nothing in the universe layer is needed at its import.
        from quantforge.workspace import Workspace

        ws = workspace if workspace is not None else Workspace.open()
        assert isinstance(ws, Workspace)  # narrow the composition-root type
        resolver = ws.resolver
        return cls.from_identities(
            resolver.resolve(identifier, by=by) for identifier in identifiers
        )

    @classmethod
    def from_identities(cls, identities: Iterable[CompanyIdentity]) -> Universe:
        """Build a universe from already-resolved identities (composition path).

        De-duplicates by canonical ``company_id`` keeping first-seen order, so a
        caller that already holds :class:`CompanyIdentity` values (e.g. from
        :attr:`Company.identity`) assembles a universe without re-resolving. An
        empty result — no identities, or every one collapsing to a duplicate of a
        prior member — fails closed.
        """
        ordered: list[CompanyIdentity] = []
        seen: set[str] = set()
        for identity in identities:
            if identity.company_id in seen:
                continue
            seen.add(identity.company_id)
            ordered.append(identity)
        if not ordered:
            raise UniverseConfigurationError(
                "a universe must contain at least one filer; an empty universe is "
                "a configuration bug, not an empty result"
            )
        return cls(identities=tuple(ordered))

    # -- ordered membership --------------------------------------------------

    @property
    def company_ids(self) -> tuple[str, ...]:
        """The canonical ``company_id``s, in deterministic order (data-model §11)."""
        return tuple(identity.company_id for identity in self.identities)

    @property
    def universe_id(self) -> str:
        """Content hash over the *ordered* ``company_id`` members.

        ``sha256("universe", m0, m1, …)``, order-sensitive and domain-tagged so it
        cannot collide with any other id space. Uses the identical scheme as the
        cross-sectional factor universe, so a universe built here and a factor
        universe over the same ordered members share one id and reproduce (§9).
        """
        payload = _SEP.join(("universe", *self.company_ids))
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    # -- provenance ----------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        """A deterministic, serializable provenance record of this universe.

        Captures the content-addressed :attr:`universe_id`, the pinned builder
        version, and each member's full resolution provenance (via
        :meth:`CompanyIdentity.to_dict`) — sufficient to audit exactly how the
        membership was derived and to reproduce it.
        """
        return {
            "universe_id": self.universe_id,
            "universe_version_id": self.builder_version.universe_version_id,
            "builder_version": self.builder_version.code_version,
            "members": [identity.to_dict() for identity in self.identities],
        }

    # -- iteration / sizing --------------------------------------------------

    def __len__(self) -> int:
        return len(self.identities)

    def __iter__(self) -> Iterator[str]:
        """Iterate the canonical ``company_id``s in deterministic order.

        Matches the cross-sectional factor universe's iteration contract, so the
        two are interchangeable wherever an ordered ``company_id`` stream is
        expected. Iterate :attr:`identities` for the full resolved members.
        """
        return iter(self.company_ids)

    def __repr__(self) -> str:
        labels = [
            identity.ticker or identity.name or identity.cik
            for identity in self.identities
        ]
        return f"Universe({labels!r}, n={len(self.identities)})"
