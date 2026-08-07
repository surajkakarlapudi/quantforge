"""The reproducible provenance record of a universe construction (Phase 9.2).

A :class:`UniverseConstruction` is the audit artifact the
:class:`~quantforge.universe.builder.UniverseBuilder` emits alongside the resolved
:class:`~quantforge.universe.model.Universe`. It answers, deterministically and for
all time, *how this exact membership was derived*:

* **specification identity** — the ``specification_id`` and the name/version, so the
  request is pinned;
* **builder version** — the ``construction_version_id`` of the rule engine that
  evaluated it;
* **boundary** — the PIT ``as_of`` or the REVISED ``dataset_version_id`` the metric
  filters were evaluated at, so the answer is reproducible against one snapshot;
* **source identities** — the ordered ``filter_id``s applied and any
  ``classification_id``s consulted;
* **applied filters** — a per-filter tally of how many candidates each kept and
  dropped;
* **excluded companies + reasons** — every drop, with the filter and a
  machine-readable reason (zero information loss);
* **result** — the resulting ``universe_id`` and the ``construction_id`` that binds
  the whole thing (specification + builder + boundary + output).

Like the factor :class:`~quantforge.factors.model.ResearchResult`, it is a pure,
frozen, serializable value; re-running the same specification under the same builder
over the same data reproduces an identical record (§12).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from quantforge.universe.filters import ExcludedCompany, FilterKind
from quantforge.universe.model import Universe

if TYPE_CHECKING:
    from quantforge.universe.analysis import UniverseComparison, UniverseSummary

__all__ = ["AppliedFilter", "ConstructionResult", "UniverseConstruction"]


@dataclass(frozen=True, slots=True)
class AppliedFilter:
    """A per-filter tally within a construction — an audit summary line.

    Records the filter's content id and kind, and how many candidates it received,
    kept, and excluded. Deterministic and order-preserving (filters are recorded in
    application order).
    """

    filter_id: str
    filter_kind: FilterKind
    received: int
    kept: int
    excluded: int

    def to_dict(self) -> dict[str, object]:
        return {
            "filter_id": self.filter_id,
            "filter_kind": self.filter_kind.value,
            "received": self.received,
            "kept": self.kept,
            "excluded": self.excluded,
        }


@dataclass(frozen=True, slots=True)
class UniverseConstruction:
    """The reproducible provenance record for one constructed universe (§9.2).

    Pins the specification, the builder version, the boundary, the ordered applied
    filters, every excluded company with its reason, and the resulting universe —
    everything needed to audit *and reproduce* the construction. ``construction_id``
    binds the specification + builder + boundary + resulting membership, so the same
    request over the same data reproduces the same id.
    """

    construction_id: str
    specification_id: str
    specification_name: str
    spec_version: str
    construction_version_id: str
    construction_code_version: str
    boundary_kind: str
    boundary_value: str
    universe_id: str
    filter_ids: tuple[str, ...]
    classification_ids: tuple[str, ...]
    applied_filters: tuple[AppliedFilter, ...]
    excluded: tuple[ExcludedCompany, ...]

    @property
    def mode(self) -> str:
        """The PIT/REVISED boundary discriminator (``"pit"`` / ``"rev"``).

        An alias of :attr:`boundary_kind`, named for the researcher-facing analysis
        layer, where preserving the construction mode is a correctness property
        (a PIT membership and a REVISED membership are never conflated, invariant 27).
        """
        return self.boundary_kind

    def exclusions_by_reason(self) -> dict[str, int]:
        """Excluded-company counts per reason, emitted sorted (deterministic)."""
        counts: dict[str, int] = {}
        for excluded in self.excluded:
            key = excluded.reason.value
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    def excluded_for(self, company_id: str) -> tuple[ExcludedCompany, ...]:
        """Every recorded exclusion of ``company_id``, in application order.

        A company can be dropped by at most one filter in a single construction (once
        excluded it is no longer a candidate), but the return is a tuple so the
        "why was this company not a member?" query has one uniform shape.
        """
        return tuple(e for e in self.excluded if e.company_id == company_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "construction_id": self.construction_id,
            "specification_id": self.specification_id,
            "specification_name": self.specification_name,
            "spec_version": self.spec_version,
            "construction_version_id": self.construction_version_id,
            "construction_code_version": self.construction_code_version,
            "boundary_kind": self.boundary_kind,
            "boundary_value": self.boundary_value,
            "universe_id": self.universe_id,
            "filter_ids": list(self.filter_ids),
            "classification_ids": list(self.classification_ids),
            "applied_filters": [a.to_dict() for a in self.applied_filters],
            "excluded": [e.to_dict() for e in self.excluded],
        }


@dataclass(frozen=True, slots=True)
class ConstructionResult:
    """The pair a build returns: the resolved universe and its provenance record.

    Keeping the two together (rather than mutating the universe with build metadata)
    preserves the Phase 9.1 :class:`Universe` as a pure membership value while making
    the full construction provenance available for audit and persistence. This is the
    researcher-facing handle for a *constructed* universe: it exposes the same
    inspection/export surface as a bare :class:`Universe`, plus a
    provenance-carrying :meth:`describe` and a mode-aware :meth:`compare`.
    """

    universe: Universe
    construction: UniverseConstruction

    # -- inspection ----------------------------------------------------------

    def provenance(self) -> UniverseConstruction:
        """The full construction provenance record (specification → exclusions).

        The single traceable artifact: specification identity and version, builder
        version, PIT/REVISED boundary, ordered applied filters, and every excluded
        company with its reason. From here a researcher walks up to the specification
        and its filters, and down to the identity resolution of each member (via
        :meth:`Universe.members`) and the metric/PIT inputs each filter consulted.
        """
        return self.construction

    def to_records(self) -> list[dict[str, object]]:
        """Tabular member records, tagged with this construction's identity + mode.

        Extends :meth:`Universe.to_records` with the ``construction_id`` and PIT/
        REVISED ``mode`` on every row, so exported membership from different
        constructions never loses which construction — or which knowledge boundary —
        it came from when concatenated into one table.
        """
        mode = self.construction.mode
        cid = self.construction.construction_id
        rows = self.universe.to_records()
        for row in rows:
            row["construction_id"] = cid
            row["mode"] = mode
        return rows

    # -- analysis (Phase 9 research layer) -----------------------------------

    def describe(self) -> UniverseSummary:
        """A deterministic summary carrying full construction provenance.

        Unlike :meth:`Universe.describe`, the summary includes the specification
        identity, the PIT/REVISED mode and boundary, the applied filters, and the
        exclusion counts by reason.
        """
        from quantforge.universe.analysis import UniverseSummary

        return UniverseSummary.of_construction(self)

    def compare(self, other: ConstructionResult) -> UniverseComparison:
        """Diff against another construction by membership, surfacing mode mismatch.

        Returns a deterministic
        :class:`~quantforge.universe.analysis.UniverseComparison` whose
        :attr:`~quantforge.universe.analysis.UniverseComparison.mode_mismatch`
        flags whether the two constructions used different PIT/REVISED boundaries — so
        a PIT membership and a REVISED membership are never *silently* compared as if
        they were the same knowledge state (invariant 27).
        """
        from quantforge.universe.analysis import UniverseComparison

        return UniverseComparison.of_constructions(self, other)
