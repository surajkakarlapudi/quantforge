"""The :class:`UniverseBuilder` — evaluate a specification into a universe (§9.2).

The construction layer's I/O boundary and the analogue of the Phase 8
:class:`~quantforge.factors.engine.FactorEngine`: it turns a declarative
:class:`~quantforge.universe.specification.UniverseSpecification` into a resolved
:class:`~quantforge.universe.model.Universe` plus a reproducible
:class:`~quantforge.universe.construction.UniverseConstruction` record. It:

1. validates the specification (fail-closed: an unknown metric, a sector rule with
   no classification, a narrowing filter before a source — all raised, never guessed
   around);
2. builds a :class:`FilterContext` at *one* explicit boundary — a PIT ``as_of`` or a
   universe-wide REVISED :class:`DatasetVersion` — so metric filters resolve against
   one reproducible snapshot;
3. applies the specification's filters **in declared order**, threading the ordered
   candidate set through each and accumulating every exclusion with its reason;
4. assembles the surviving identities into a :class:`Universe` (fail-closed on an
   empty result, exactly as Phase 9.1) and packages the construction provenance.

It **composes, never duplicates** (ARCHITECTURE.md principles 3, 5): resolution is
the existing :class:`~quantforge.identity.resolve.CompanyResolver`, metric evaluation
is the existing :class:`~quantforge.metrics.engine.MetricEngine`, and PIT/REVISED
eligibility is Phase 5's — the builder adds only the rule evaluation, the ordered
narrowing, and the provenance packaging. It owns no identifier system, no arithmetic,
and no storage. Two methods, no default mode (invariant 27): PIT and REVISED are
impossible to confuse.
"""

from __future__ import annotations

from datetime import datetime

from quantforge.availability.version import DatasetVersion
from quantforge.identity.model import CompanyIdentity
from quantforge.metrics.engine import MetricEngine
from quantforge.registry.identity import cik_from_company_id
from quantforge.universe.construction import (
    AppliedFilter,
    ConstructionResult,
    UniverseConstruction,
)
from quantforge.universe.filters import (
    ExcludedCompany,
    ExplicitCompanyFilter,
    FilterContext,
    SectorClassification,
)
from quantforge.universe.identity import boundary_key as _boundary_key
from quantforge.universe.identity import construction_id as _construction_id
from quantforge.universe.model import Universe
from quantforge.universe.specification import UniverseSpecification
from quantforge.universe.version import UniverseConstructionVersion
from quantforge.workspace import Workspace

__all__ = ["UniverseBuilder"]


class UniverseBuilder:
    """Evaluate a :class:`UniverseSpecification` at one boundary (§9.2).

    Constructed from a :class:`Workspace` (the composition root); it reuses the
    workspace's cached Phase 7 :class:`MetricEngine` and the same
    :class:`~quantforge.identity.resolve.CompanyResolver` as :class:`Company` and the
    Phase 9.1 :class:`Universe`. Both the engine and the construction version may be
    overridden (e.g. for tests).
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        metric_engine: MetricEngine | None = None,
        construction_version: UniverseConstructionVersion | None = None,
    ) -> None:
        self._workspace = workspace
        engine = metric_engine if metric_engine is not None else workspace.metric_engine
        assert isinstance(engine, MetricEngine)  # the workspace builds exactly this
        self._metric_engine = engine
        self._version = construction_version or UniverseConstructionVersion()

    @property
    def metric_engine(self) -> MetricEngine:
        return self._metric_engine

    @property
    def construction_version(self) -> UniverseConstructionVersion:
        return self._version

    # -- PIT / REVISED construction API -------------------------------------

    def build_as_of(
        self,
        specification: UniverseSpecification,
        as_of: datetime,
        *,
        classifications: tuple[SectorClassification, ...] = (),
    ) -> ConstructionResult:
        """Construct the point-in-time universe for ``specification`` at ``as_of``.

        Metric filters are evaluated at the same point-in-time ``as_of``
        (timezone-aware; a naive instant is rejected by the Phase 5 choke point via
        Phase 7). A company excluded because a metric is not yet public at ``as_of``
        is recorded, never raised. Returns a :class:`ConstructionResult` (the
        resolved universe + its provenance).
        """
        context = FilterContext.pit(
            resolver=self._workspace.resolver,
            metric_engine=self._metric_engine,
            as_of=as_of,
            classifications=classifications,
        )
        return self._build(specification, context, classifications)

    def build_revised(
        self,
        specification: UniverseSpecification,
        dataset_version: DatasetVersion | None = None,
        *,
        classifications: tuple[SectorClassification, ...] = (),
    ) -> ConstructionResult:
        """Construct the revised universe over a pinned universe-wide snapshot (§8.1).

        Metric filters are evaluated over one universe-wide
        :class:`DatasetVersion` — built here (from the specification's explicit
        source members) as the union of the members' per-filer snapshots unless one
        is supplied — so the whole construction is pinned to one reproducible state.
        Returns a :class:`ConstructionResult`, not interchangeable with a PIT build
        (invariant 27).
        """
        dv = (
            dataset_version
            if dataset_version is not None
            else self._revised_snapshot(specification)
        )
        context = FilterContext.revised(
            resolver=self._workspace.resolver,
            metric_engine=self._metric_engine,
            dataset_version=dv,
            classifications=classifications,
        )
        return self._build(specification, context, classifications)

    # -- rule evaluation -----------------------------------------------------

    def _build(
        self,
        specification: UniverseSpecification,
        context: FilterContext,
        classifications: tuple[SectorClassification, ...],
    ) -> ConstructionResult:
        """Apply the ordered filters, then assemble the universe + provenance."""
        # `None` marks "no membership established yet"; the first (source) filter
        # seeds it. Later filters narrow the ordered candidate set.
        candidates: tuple[CompanyIdentity, ...] | None = None
        applied: list[AppliedFilter] = []
        all_excluded: list[ExcludedCompany] = []
        for filt in specification.filters:
            received = 0 if candidates is None else len(candidates)
            outcome = filt.apply(candidates, context)
            applied.append(
                AppliedFilter(
                    filter_id=filt.filter_id,
                    filter_kind=filt.kind,
                    received=received,
                    kept=len(outcome.kept),
                    excluded=len(outcome.excluded),
                )
            )
            all_excluded.extend(outcome.excluded)
            candidates = outcome.kept

        # An empty final membership fails closed — exactly as Phase 9.1. Every drop
        # is preserved in `all_excluded` so the failure is fully explained.
        universe = Universe.from_identities(candidates or ())

        construction = self._package(
            specification=specification,
            context=context,
            universe=universe,
            applied=tuple(applied),
            excluded=tuple(all_excluded),
            classifications=classifications,
        )
        return ConstructionResult(universe=universe, construction=construction)

    def _package(
        self,
        *,
        specification: UniverseSpecification,
        context: FilterContext,
        universe: Universe,
        applied: tuple[AppliedFilter, ...],
        excluded: tuple[ExcludedCompany, ...],
        classifications: tuple[SectorClassification, ...],
    ) -> UniverseConstruction:
        """Build the reproducible :class:`UniverseConstruction` record (§9.2)."""
        boundary_key = _boundary_key(
            kind=context.boundary_kind, value=context.boundary_value
        )
        cid = _construction_id(
            specification_id=specification.specification_id,
            construction_version_id=self._version.construction_version_id,
            boundary_key=boundary_key,
            universe_id=universe.universe_id,
        )
        return UniverseConstruction(
            construction_id=cid,
            specification_id=specification.specification_id,
            specification_name=specification.name,
            spec_version=specification.spec_version,
            construction_version_id=self._version.construction_version_id,
            construction_code_version=self._version.code_version,
            boundary_kind=context.boundary_kind,
            boundary_value=context.boundary_value,
            universe_id=universe.universe_id,
            filter_ids=specification.filter_ids,
            classification_ids=tuple(c.classification_id for c in classifications),
            applied_filters=applied,
            excluded=excluded,
        )

    # -- universe-wide snapshot (REVISED) ------------------------------------

    def _revised_snapshot(self, specification: UniverseSpecification) -> DatasetVersion:
        """A universe-wide :class:`DatasetVersion` over the specification's source.

        Pins the REVISED boundary from the *explicit source* members the
        specification declares (its first filter). Mirrors the factor engine's
        union-of-per-filer-snapshots (§8.1): the same normalizer across members
        (surfaced if mixed via the per-filer builder), the union of raw-document /
        fact / policy ids. Narrowing filters only remove members, so pinning to the
        source is a superset — reproducible and complete.
        """
        source = specification.filters[0]
        # The source is an ExplicitCompanyFilter (validated by the specification);
        # resolve its members to seed the snapshot. Resolution reuses the workspace
        # resolver, never a new one.
        assert isinstance(source, ExplicitCompanyFilter)
        resolver = self._workspace.resolver
        company_ids: list[str] = []
        seen: set[str] = set()
        for identifier in source.identifiers:
            identity = resolver.resolve(identifier, by=source.by)
            if identity.company_id in seen:
                continue
            seen.add(identity.company_id)
            company_ids.append(identity.company_id)

        raw_docs: set[str] = set()
        fact_ids: set[str] = set()
        policy_ids: set[str] = set()
        tvs: set[str] = set()
        fallback_tv: str | None = None
        for company_id in company_ids:
            cik = cik_from_company_id(company_id)
            per_filer = self._metric_engine.dataset_version_for(cik)
            fallback_tv = per_filer.transformation_version_id
            raw_docs.update(per_filer.raw_document_ids)
            fact_ids.update(per_filer.fact_ids)
            policy_ids.update(per_filer.availability_policy_ids)
            if per_filer.fact_ids:
                tvs.add(per_filer.transformation_version_id)
        if len(tvs) > 1:
            from quantforge.universe.errors import UniverseSpecificationError

            raise UniverseSpecificationError(
                "universe members were normalized under differing transformation "
                f"versions {sorted(tvs)}; a single universe-wide snapshot requires "
                "one normalizer"
            )
        transformation_version_id = tvs.pop() if tvs else (fallback_tv or "")
        return DatasetVersion(
            transformation_version_id=transformation_version_id,
            availability_policy_ids=tuple(sorted(policy_ids)),
            raw_document_ids=tuple(sorted(raw_docs)),
            fact_ids=tuple(sorted(fact_ids)),
        )
