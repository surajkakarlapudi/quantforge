"""The :class:`FactorEngine` façade — fan out Phase 7 across a universe (§4, §6).

The factor layer's I/O boundary. It:

1. resolves the formula by ``metric_key`` (fail-closed on unknown, via the Phase 7
   registry) and pins the shared ``formula_id`` / ``metric_engine_version_id`` /
   decimal context before any work;
2. builds a **universe-wide** :class:`DatasetVersion` — the union of each member's
   per-filer snapshot — so both PIT and REVISED factors cite one reproducible pin
   spanning the whole universe (§8.1);
3. evaluates the Phase 7 :class:`~openfinance.metrics.engine.MetricEngine` **once
   per universe member, in declared order**, at the *one* shared boundary — PIT
   ``as_of`` or the universe-wide REVISED ``DatasetVersion`` — collecting one
   :class:`FactorCell` per member (never dropped, §6.1);
4. applies the optional pure cross-sectional :class:`Transform` over the KNOWN
   cells only (§6.2);
5. assembles the distinct :class:`PitFactor` / :class:`RevisedFactor`, packages the
   reproducible :class:`ResearchResult`, and persists it write-once to the
   :class:`ResearchResultStore` sidecar (Decision F4).

It **composes, never re-resolves** (§2): Phase 5 already decided eligibility and
restatement order, Phase 7 already did the arithmetic. The engine adds only the
fan-out, the cross-sectional assembly, the transforms, and the ``ResearchResult``
packaging — introducing no new resolution logic and mutating no prior store. It
keeps PIT/REVISED impossible to confuse: two methods, no default mode (invariant
27), returning the two distinct factor types (invariant 28, Decision F5).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from openfinance.availability.timestamps import format_utc_z
from openfinance.availability.version import DatasetVersion
from openfinance.factors.errors import FactorConsistencyError
from openfinance.factors.identity import (
    boundary_key as _boundary_key,
)
from openfinance.factors.identity import (
    factor_definition_id as _factor_definition_id,
)
from openfinance.factors.identity import (
    research_result_id as _research_result_id,
)
from openfinance.factors.identity import (
    result_hash as _result_hash,
)
from openfinance.factors.model import (
    FactorCell,
    FactorStatus,
    PitFactor,
    ResearchResult,
    RevisedFactor,
    _FactorBaseFields,
)
from openfinance.factors.store import ResearchResultStore
from openfinance.factors.transform import Transform
from openfinance.factors.universe import Universe
from openfinance.metrics.engine import MetricEngine
from openfinance.metrics.model import (
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
)
from openfinance.registry.identity import cik_from_company_id
from openfinance.workspace import Workspace

__all__ = ["FactorEngine"]


class FactorEngine:
    """Evaluate one metric across an explicit universe at one boundary (§4, §11).

    Constructed from a :class:`Workspace` (the composition root); it reuses the
    workspace's cached Phase 7 :class:`MetricEngine` and its
    :class:`ResearchResultStore` sidecar. Both may be overridden (e.g. for tests).
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        metric_engine: MetricEngine | None = None,
        research_store: ResearchResultStore | None = None,
    ) -> None:
        self._workspace = workspace
        engine = metric_engine if metric_engine is not None else workspace.metric_engine
        assert isinstance(engine, MetricEngine)  # the workspace builds exactly this
        self._metric_engine = engine
        self._research_store = (
            research_store
            if research_store is not None
            else workspace.research_result_store
        )

    @property
    def metric_engine(self) -> MetricEngine:
        return self._metric_engine

    @property
    def research_store(self) -> ResearchResultStore:
        return self._research_store

    # -- PIT / REVISED factor API -------------------------------------------

    def factor_as_of(
        self,
        metric_key: str,
        universe: Universe,
        period: MetricPeriod,
        as_of: datetime,
        *,
        transform: Transform | None = None,
    ) -> PitFactor:
        """The point-in-time cross-sectional factor at ``as_of`` (§6, §11, §12).

        Evaluates ``metric_key`` for every universe member at the same ``as_of``
        (timezone-aware; a naive instant is rejected by the Phase 5 choke point via
        Phase 7). Every member yields exactly one :class:`FactorCell` — ``KNOWN``
        with provenance or a first-class ``UNDEFINED`` (never dropped, never
        imputed). Returns a :class:`PitFactor`; the universe-wide
        :class:`DatasetVersion` is cited for reproducibility (§7).
        """
        tf = transform if transform is not None else Transform.none()
        dataset_version = self._universe_dataset_version(universe)
        # PIT boundary is the shared as_of; the universe-wide snapshot is cited.
        cells = self._evaluate_pit_cells(metric_key, universe, period, as_of)
        cells = self._apply_transform(cells, tf)
        research = self._research_result(
            metric_key=metric_key,
            universe=universe,
            period=period,
            transform=tf,
            cells=cells,
            boundary_kind="pit",
            boundary_value=format_utc_z(as_of),
            dataset_version_id=dataset_version.dataset_version_id,
            as_of_timestamp=format_utc_z(as_of),
        )
        self._research_store.write(research)
        return PitFactor(
            **self._base_fields(metric_key, universe, period, tf, cells, research),
            as_of=as_of,
        )

    def revised_factor(
        self,
        metric_key: str,
        universe: Universe,
        period: MetricPeriod,
        dataset_version: DatasetVersion | None = None,
        *,
        transform: Transform | None = None,
    ) -> RevisedFactor:
        """The revised cross-sectional factor over one universe-wide snapshot (§8.1).

        Every member is resolved at its own ingestion frontier (Phase 5 REVISED
        semantics), and every cell records the **same** universe-wide
        :class:`DatasetVersion` — built here as the union of the members' snapshots
        unless one is supplied — so the whole vector is pinned to one reproducible
        state (§8.1). Returns a :class:`RevisedFactor`, not interchangeable with a
        PIT factor (invariant 28).
        """
        tf = transform if transform is not None else Transform.none()
        dv = (
            dataset_version
            if dataset_version is not None
            else self._universe_dataset_version(universe)
        )
        cells = self._evaluate_revised_cells(metric_key, universe, period, dv)
        cells = self._apply_transform(cells, tf)
        research = self._research_result(
            metric_key=metric_key,
            universe=universe,
            period=period,
            transform=tf,
            cells=cells,
            boundary_kind="rev",
            boundary_value=dv.dataset_version_id,
            dataset_version_id=dv.dataset_version_id,
            as_of_timestamp=None,
        )
        self._research_store.write(research)
        return RevisedFactor(
            **self._base_fields(metric_key, universe, period, tf, cells, research),
            dataset_version_id=dv.dataset_version_id,
        )

    # -- fan-out -------------------------------------------------------------

    def _evaluate_pit_cells(
        self,
        metric_key: str,
        universe: Universe,
        period: MetricPeriod,
        as_of: datetime,
    ) -> tuple[FactorCell, ...]:
        """One PIT cell per member, in universe order (never dropped, §6.1)."""
        cells: list[FactorCell] = []
        for company in universe:
            cik = cik_from_company_id(company)
            metric = self._metric_engine.metric_as_of(metric_key, cik, period, as_of)
            self._check_shared_version(metric)
            cells.append(FactorCell(company_id=company, metric=metric))
        return tuple(cells)

    def _evaluate_revised_cells(
        self,
        metric_key: str,
        universe: Universe,
        period: MetricPeriod,
        dataset_version: DatasetVersion,
    ) -> tuple[FactorCell, ...]:
        """One REVISED cell per member over the shared snapshot (§6.1, §8.1)."""
        cells: list[FactorCell] = []
        for company in universe:
            cik = cik_from_company_id(company)
            metric = self._metric_engine.revised_metric(
                metric_key, cik, period, dataset_version
            )
            self._check_shared_version(metric)
            cells.append(FactorCell(company_id=company, metric=metric))
        return tuple(cells)

    def _check_shared_version(
        self, metric: PitMetricValue | RevisedMetricValue
    ) -> None:
        """Every cell must share this engine's version (§8) — surfaced if not."""
        expected = self._metric_engine.engine_version.metric_engine_version_id
        if metric.metric_engine_version_id != expected:
            raise FactorConsistencyError(
                "cross-sectional cells must share one metric_engine_version_id; "
                f"expected {expected}, got {metric.metric_engine_version_id}"
            )

    # -- transforms ----------------------------------------------------------

    def _apply_transform(
        self, cells: tuple[FactorCell, ...], transform: Transform
    ) -> tuple[FactorCell, ...]:
        """Apply a transform over the KNOWN cells only (§6.2); UNDEFINED stay so.

        The population is the KNOWN cells in universe order (insertion order
        preserved). ``UNDEFINED`` cells are excluded from the statistic and keep a
        ``None`` transformed value — never imputed (Principle 8).
        """
        population: dict[str, Decimal] = {
            cell.company_id: Decimal(cell.metric.value_numeric_str)
            for cell in cells
            if cell.metric.status is MetricStatus.KNOWN
            and cell.metric.value_numeric_str is not None
        }
        transformed = transform.apply(
            population, self._metric_engine.engine_version.decimal_context()
        )
        return tuple(
            FactorCell(
                company_id=cell.company_id,
                metric=cell.metric,
                transformed_value_numeric_str=transformed.get(cell.company_id),
            )
            for cell in cells
        )

    # -- assembly ------------------------------------------------------------

    def _research_result(
        self,
        *,
        metric_key: str,
        universe: Universe,
        period: MetricPeriod,
        transform: Transform,
        cells: tuple[FactorCell, ...],
        boundary_kind: str,
        boundary_value: str,
        dataset_version_id: str,
        as_of_timestamp: str | None,
    ) -> ResearchResult:
        """Build the reproducible :class:`ResearchResult` (§7, data-model §9)."""
        formula = self._metric_engine.registry.get(metric_key)
        engine_version_id = self._metric_engine.engine_version.metric_engine_version_id
        definition_id = _factor_definition_id(
            metric_key=metric_key,
            formula_id=formula.formula_id,
            transform_id=transform.transform_id,
        )
        rhash = _result_hash([cell.outcome_digest() for cell in cells])
        rr_id = _research_result_id(
            factor_definition_id=definition_id,
            metric_engine_version_id=engine_version_id,
            universe_id=universe.universe_id,
            period_key=period.period_key,
            boundary_key=_boundary_key(kind=boundary_kind, value=boundary_value),
            result_hash=rhash,
        )
        return ResearchResult(
            research_result_id=rr_id,
            factor_definition_id=definition_id,
            metric_engine_version_id=engine_version_id,
            metric_key=metric_key,
            formula_id=formula.formula_id,
            transform_id=transform.transform_id,
            universe_id=universe.universe_id,
            period=period,
            boundary_kind=boundary_kind,
            boundary_value=boundary_value,
            dataset_version_id=dataset_version_id,
            as_of_timestamp=as_of_timestamp,
            summary=FactorStatus.from_cells(cells),
            result_hash=rhash,
        )

    def _base_fields(
        self,
        metric_key: str,
        universe: Universe,
        period: MetricPeriod,
        transform: Transform,
        cells: tuple[FactorCell, ...],
        research: ResearchResult,
    ) -> _FactorBaseFields:
        """The shared :class:`_FactorBase` fields for either factor type.

        Returned as the model's ``_FactorBaseFields`` TypedDict so ``**`` unpacking
        into :class:`PitFactor` / :class:`RevisedFactor` stays statically checkable.
        """
        return _FactorBaseFields(
            research_result_id=research.research_result_id,
            factor_definition_id=research.factor_definition_id,
            metric_engine_version_id=research.metric_engine_version_id,
            metric_key=metric_key,
            formula_id=research.formula_id,
            transform_id=transform.transform_id,
            universe_id=universe.universe_id,
            period=period,
            cells=cells,
            summary=research.summary,
            research_result=research,
        )

    # -- universe-wide snapshot ----------------------------------------------

    def _universe_dataset_version(self, universe: Universe) -> DatasetVersion:
        """The union of the members' per-filer snapshots — one universe pin (§8.1).

        Reuses the Phase 7 per-filer :meth:`MetricEngine.dataset_version_for` and
        unions the raw-document / fact / policy id sets. The transformation version
        must be consistent across every member that has facts (a mixed normalizer
        cannot form one snapshot — surfaced, not guessed); an all-empty universe
        falls back to the default via the per-filer builder.
        """
        raw_docs: set[str] = set()
        fact_ids: set[str] = set()
        policy_ids: set[str] = set()
        tvs: set[str] = set()
        fallback_tv: str | None = None
        for company in universe:
            cik = cik_from_company_id(company)
            per_filer = self._metric_engine.dataset_version_for(cik)
            fallback_tv = per_filer.transformation_version_id
            raw_docs.update(per_filer.raw_document_ids)
            fact_ids.update(per_filer.fact_ids)
            policy_ids.update(per_filer.availability_policy_ids)
            if per_filer.fact_ids:  # only members with facts pin a normalizer
                tvs.add(per_filer.transformation_version_id)
        if len(tvs) > 1:
            raise FactorConsistencyError(
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
