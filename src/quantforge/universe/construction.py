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

from quantforge.universe.filters import ExcludedCompany, FilterKind
from quantforge.universe.model import Universe

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
    the full construction provenance available for audit and persistence.
    """

    universe: Universe
    construction: UniverseConstruction
