"""Researcher-facing inspection and analysis for universes (Phase 9, research layer).

Phase 9.1 builds a :class:`~quantforge.universe.model.Universe` (a deterministic,
ordered membership) and Phase 9.2 constructs one from a specification, recording a
:class:`~quantforge.universe.construction.UniverseConstruction` provenance record.
This module completes Phase 9 with the *analysis* surface a researcher reaches for
once a universe exists — **without** introducing a second universe abstraction,
duplicating the company identity model, or computing any financial statistic:

* :class:`UniverseSummary` — a deterministic, serializable *description* of a
  universe: its size, ordered canonical ``company_id``s, content-addressed
  ``universe_id``, and — when the universe came from a Phase 9.2 construction — the
  specification identity, the PIT/REVISED boundary, the applied filters, and the
  exclusion counts by reason. The `Universe.describe()` / `ConstructionResult.
  describe()` accessors return one.
* :class:`UniverseComparison` — a deterministic, serializable diff of two universes
  by **canonical ``company_id`` membership** (never object identity): the members
  added, removed, and retained, with counts. When both sides carry construction
  provenance it also surfaces whether they were built under *different* PIT/REVISED
  modes, so a researcher is never misled into treating a PIT membership and a
  REVISED membership as the same thing (invariant 27 extended to analysis).

Everything here is a frozen value with a deterministic ``to_dict``: no wall-clock,
no RNG, no dependence on dict/set iteration order. Members are compared and ordered
by canonical ``company_id`` (the only identity, data-model §11); a ticker or name is
descriptive metadata and never authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quantforge.universe.construction import ConstructionResult
    from quantforge.universe.model import Universe

__all__ = ["UniverseComparison", "UniverseSummary"]


def _exclusions_by_reason(construction: object) -> dict[str, int]:
    """Count a construction's excluded companies per reason, deterministically.

    Mirrors :meth:`FactorStatus.from_cells`: reasons are emitted sorted so the map
    never depends on iteration order. ``construction`` is a
    :class:`~quantforge.universe.construction.UniverseConstruction`; typed loosely to
    avoid a runtime import cycle (this module is imported lazily by the construction
    layer).
    """
    counts: dict[str, int] = {}
    for excluded in construction.excluded:  # type: ignore[attr-defined]
        key = excluded.reason.value
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class UniverseSummary:
    """A deterministic, serializable description of a universe (research layer).

    Always carries the membership essentials (size, ordered ``company_id``s, the
    content-addressed ``universe_id``, and the pinned builder version). When the
    universe came from a Phase 9.2 construction, the optional fields additionally pin
    the specification identity, the PIT/REVISED boundary, the ordered applied
    filters, and the exclusion counts by reason — everything a researcher needs to
    understand *what this universe is and how it was built*, with no financial
    statistic computed.

    Build one via :meth:`Universe.describe` (membership only) or
    :meth:`ConstructionResult.describe` (membership + construction provenance);
    the direct classmethods :meth:`of_universe` / :meth:`of_construction` are the
    same paths.
    """

    universe_id: str
    member_count: int
    company_ids: tuple[str, ...]
    builder_version_id: str
    #: Construction-only provenance (``None`` for a bare Phase 9.1 universe).
    name: str | None = None
    construction_id: str | None = None
    specification_id: str | None = None
    spec_version: str | None = None
    construction_version_id: str | None = None
    construction_code_version: str | None = None
    #: The construction boundary discriminator: ``"pit"`` or ``"rev"`` (``None`` for
    #: a bare universe). Deliberately never defaulted — a universe built as-of a date
    #: and one built over a revised snapshot are distinguishable here (invariant 27).
    mode: str | None = None
    boundary_value: str | None = None
    filter_ids: tuple[str, ...] = ()
    classification_ids: tuple[str, ...] = ()
    applied_filters: tuple[dict[str, object], ...] = ()
    excluded_count: int = 0
    exclusions_by_reason: dict[str, int] = field(default_factory=dict)

    @classmethod
    def of_universe(cls, universe: Universe) -> UniverseSummary:
        """Summarize a bare Phase 9.1 universe — membership essentials only."""
        return cls(
            universe_id=universe.universe_id,
            member_count=len(universe),
            company_ids=universe.company_ids,
            builder_version_id=universe.builder_version.universe_version_id,
        )

    @classmethod
    def of_construction(cls, result: ConstructionResult) -> UniverseSummary:
        """Summarize a Phase 9.2 construction — membership + full provenance."""
        universe = result.universe
        construction = result.construction
        return cls(
            universe_id=universe.universe_id,
            member_count=len(universe),
            company_ids=universe.company_ids,
            builder_version_id=universe.builder_version.universe_version_id,
            name=construction.specification_name,
            construction_id=construction.construction_id,
            specification_id=construction.specification_id,
            spec_version=construction.spec_version,
            construction_version_id=construction.construction_version_id,
            construction_code_version=construction.construction_code_version,
            mode=construction.boundary_kind,
            boundary_value=construction.boundary_value,
            filter_ids=construction.filter_ids,
            classification_ids=construction.classification_ids,
            applied_filters=tuple(a.to_dict() for a in construction.applied_filters),
            excluded_count=len(construction.excluded),
            exclusions_by_reason=_exclusions_by_reason(construction),
        )

    @property
    def is_constructed(self) -> bool:
        """Whether this summary carries Phase 9.2 construction provenance."""
        return self.construction_id is not None

    def to_dict(self) -> dict[str, object]:
        """A deterministic, serializable description.

        Construction-only keys are present but ``null`` for a bare universe, so the
        serialized shape is stable regardless of provenance depth.
        """
        return {
            "universe_id": self.universe_id,
            "member_count": self.member_count,
            "company_ids": list(self.company_ids),
            "builder_version_id": self.builder_version_id,
            "name": self.name,
            "construction_id": self.construction_id,
            "specification_id": self.specification_id,
            "spec_version": self.spec_version,
            "construction_version_id": self.construction_version_id,
            "construction_code_version": self.construction_code_version,
            "mode": self.mode,
            "boundary_value": self.boundary_value,
            "filter_ids": list(self.filter_ids),
            "classification_ids": list(self.classification_ids),
            "applied_filters": [dict(a) for a in self.applied_filters],
            "excluded_count": self.excluded_count,
            "exclusions_by_reason": dict(sorted(self.exclusions_by_reason.items())),
        }


@dataclass(frozen=True, slots=True)
class UniverseComparison:
    """A deterministic diff of two universes by canonical ``company_id``.

    Compares **membership**, never object identity: the ``left`` (before) and
    ``right`` (after) universes are reduced to their canonical ``company_id`` sets,
    and the members are partitioned into :attr:`added` (in right, not left),
    :attr:`removed` (in left, not right), and :attr:`retained` (in both). Ordering is
    deterministic — ``removed`` / ``retained`` follow the left universe's order,
    ``added`` follows the right universe's order — so equivalent inputs always yield
    an identical comparison.

    When both universes carry Phase 9.2 construction provenance, :attr:`left_mode` /
    :attr:`right_mode` record each side's PIT/REVISED boundary and
    :attr:`mode_mismatch` flags a difference. The comparison itself is always
    legitimate (membership is a set of ``company_id``s, independent of the knowledge
    boundary), but the flag ensures a PIT membership and a REVISED membership are
    never *silently* treated as equivalent (invariant 27).
    """

    left_universe_id: str
    right_universe_id: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    retained: tuple[str, ...]
    left_mode: str | None = None
    right_mode: str | None = None
    left_boundary_value: str | None = None
    right_boundary_value: str | None = None

    @classmethod
    def of_universes(cls, left: Universe, right: Universe) -> UniverseComparison:
        """Diff two bare universes by membership (no boundary metadata)."""
        return cls._compare(
            left_universe_id=left.universe_id,
            right_universe_id=right.universe_id,
            left_ids=left.company_ids,
            right_ids=right.company_ids,
        )

    @classmethod
    def of_constructions(
        cls, left: ConstructionResult, right: ConstructionResult
    ) -> UniverseComparison:
        """Diff two constructions by membership, surfacing any PIT/REVISED mismatch."""
        return cls._compare(
            left_universe_id=left.universe.universe_id,
            right_universe_id=right.universe.universe_id,
            left_ids=left.universe.company_ids,
            right_ids=right.universe.company_ids,
            left_mode=left.construction.boundary_kind,
            right_mode=right.construction.boundary_kind,
            left_boundary_value=left.construction.boundary_value,
            right_boundary_value=right.construction.boundary_value,
        )

    @classmethod
    def _compare(
        cls,
        *,
        left_universe_id: str,
        right_universe_id: str,
        left_ids: tuple[str, ...],
        right_ids: tuple[str, ...],
        left_mode: str | None = None,
        right_mode: str | None = None,
        left_boundary_value: str | None = None,
        right_boundary_value: str | None = None,
    ) -> UniverseComparison:
        left_set = set(left_ids)
        right_set = set(right_ids)
        # Order deterministically off the source universes, never off set iteration.
        retained = tuple(cid for cid in left_ids if cid in right_set)
        removed = tuple(cid for cid in left_ids if cid not in right_set)
        added = tuple(cid for cid in right_ids if cid not in left_set)
        return cls(
            left_universe_id=left_universe_id,
            right_universe_id=right_universe_id,
            added=added,
            removed=removed,
            retained=retained,
            left_mode=left_mode,
            right_mode=right_mode,
            left_boundary_value=left_boundary_value,
            right_boundary_value=right_boundary_value,
        )

    @property
    def added_count(self) -> int:
        return len(self.added)

    @property
    def removed_count(self) -> int:
        return len(self.removed)

    @property
    def retained_count(self) -> int:
        return len(self.retained)

    @property
    def is_identical(self) -> bool:
        """Whether the two universes have identical membership (order aside)."""
        return not self.added and not self.removed

    @property
    def mode_mismatch(self) -> bool | None:
        """Whether the two constructions used different PIT/REVISED modes.

        ``None`` when either side lacks construction provenance (the modes are
        unknown, so no claim is made); otherwise ``True`` iff the boundary kinds
        differ. A researcher can assert this is ``False`` before treating two
        constructed universes as comparable snapshots of the same knowledge state.
        """
        if self.left_mode is None or self.right_mode is None:
            return None
        return self.left_mode != self.right_mode

    def to_dict(self) -> dict[str, object]:
        """A deterministic, serializable diff."""
        return {
            "left_universe_id": self.left_universe_id,
            "right_universe_id": self.right_universe_id,
            "added": list(self.added),
            "removed": list(self.removed),
            "retained": list(self.retained),
            "added_count": self.added_count,
            "removed_count": self.removed_count,
            "retained_count": self.retained_count,
            "is_identical": self.is_identical,
            "left_mode": self.left_mode,
            "right_mode": self.right_mode,
            "left_boundary_value": self.left_boundary_value,
            "right_boundary_value": self.right_boundary_value,
            "mode_mismatch": self.mode_mismatch,
        }
