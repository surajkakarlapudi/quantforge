"""The :class:`PanelEngine` façade — evaluate one metric over a time axis (locked §9).

The panel layer's I/O boundary. It:

1. resolves the formula by ``metric_key`` (fail-closed on unknown, via the Phase 7
   registry) and pins the shared ``formula_id`` / ``metric_engine_version_id`` /
   decimal context before any work;
2. validates the requested derivation against the axis (a period-kind mismatch —
   e.g. ``ttm`` over an ``INSTANT`` axis — is a configuration defect, raised, §8);
3. evaluates the Phase 7 :class:`~quantforge.metrics.engine.MetricEngine` **once per
   coordinate** at the *one* shared boundary (PIT ``as_of``, a PIT ``as_of`` axis,
   or a REVISED :class:`DatasetVersion`), collecting one :class:`PanelCell` per
   coordinate (never dropped, §8);
4. applies the optional pure multi-period :class:`Derivation` over each filer's
   period-series (§3), which is ``UNDEFINED``-preserving and cannot add look-ahead
   because every input cell was already boundary-eligible (§7);
5. assembles the distinct :class:`PitPanel` / :class:`RevisedPanel`, packages the
   reproducible :class:`PanelResearchResult`, and persists it write-once to the
   shared Phase 8 :class:`ResearchResultStore` sidecar (Decision D4).

It **composes, never re-resolves** (§2): Phase 5 already decided eligibility and
restatement order, Phase 7 already did the arithmetic, Phase 8 already fans a metric
across a universe at one boundary. The engine adds only the *time axis*, the
multi-period derivations, the cross-sectional stacking (matrix shape), and the
``PanelResearchResult`` packaging — introducing no new resolution logic and mutating
no prior store. It keeps PIT/REVISED impossible to confuse: distinct methods, no
default mode (invariant 27), returning the two distinct panel types (invariant 28,
Decision D5).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from quantforge.availability.timestamps import ensure_aware_utc, format_utc_z
from quantforge.availability.version import DatasetVersion
from quantforge.factors.engine import FactorEngine
from quantforge.factors.store import ResearchResultStore
from quantforge.factors.universe import Universe
from quantforge.metrics.engine import MetricEngine
from quantforge.metrics.model import (
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
)
from quantforge.panel.axis import PeriodAxis
from quantforge.panel.derive import Derivation, DerivationKind, SeriesPoint
from quantforge.panel.errors import PanelConfigurationError, PanelConsistencyError
from quantforge.panel.identity import (
    boundary_key as _boundary_key,
)
from quantforge.panel.identity import (
    panel_definition_id as _panel_definition_id,
)
from quantforge.panel.identity import (
    panel_id as _panel_id,
)
from quantforge.panel.identity import (
    result_hash as _result_hash,
)
from quantforge.panel.model import (
    PanelCell,
    PanelResearchResult,
    PanelShape,
    PanelStatus,
    PitPanel,
    RevisedPanel,
    _PanelBaseFields,
)
from quantforge.registry.identity import cik_from_company_id
from quantforge.registry.identity import company_id as _company_id
from quantforge.workspace import Workspace

__all__ = ["PanelEngine"]


class PanelEngine:
    """Evaluate one metric over a period axis for a filer or universe (§9, §2).

    Constructed from a :class:`Workspace` (the composition root); it reuses the
    workspace's cached Phase 7 :class:`MetricEngine`, its Phase 8
    :class:`FactorEngine` (for the matrix shape), and its
    :class:`ResearchResultStore` sidecar. All may be overridden (e.g. for tests).
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        metric_engine: MetricEngine | None = None,
        factor_engine: FactorEngine | None = None,
        research_store: ResearchResultStore | None = None,
    ) -> None:
        self._workspace = workspace
        engine = metric_engine if metric_engine is not None else workspace.metric_engine
        assert isinstance(engine, MetricEngine)  # the workspace builds exactly this
        self._metric_engine = engine
        factors = (
            factor_engine if factor_engine is not None else workspace.factor_engine
        )
        assert isinstance(factors, FactorEngine)
        self._factor_engine = factors
        self._research_store = (
            research_store
            if research_store is not None
            else workspace.research_result_store
        )

    @property
    def metric_engine(self) -> MetricEngine:
        return self._metric_engine

    @property
    def factor_engine(self) -> FactorEngine:
        return self._factor_engine

    @property
    def research_store(self) -> ResearchResultStore:
        return self._research_store

    # -- PIT period-series (4.1) --------------------------------------------

    def panel_as_of(
        self,
        metric_key: str,
        cik: str | int,
        axis: PeriodAxis,
        as_of: datetime,
        *,
        derivation: Derivation | None = None,
    ) -> PitPanel:
        """The point-in-time period-series for one filer at ``as_of`` (§2 4.1, §7).

        Evaluates ``metric_key`` for the filer over every period of ``axis`` at the
        **same** ``as_of`` (timezone-aware; a naive instant is rejected by the Phase
        5 choke point). Every period yields exactly one :class:`PanelCell` — ``KNOWN``
        with provenance or a first-class ``UNDEFINED`` (never dropped, never imputed).
        An optional multi-period :class:`Derivation` (growth / ttm / average_balance
        / level_vs_history) is applied over the resulting series; because every input
        cell shares one ``as_of`` it cannot introduce look-ahead (§7). Returns a
        :class:`PitPanel`.
        """
        deriv = derivation if derivation is not None else Derivation.none()
        self._check_derivation_axis(deriv, axis)
        company = _company_id(cik)
        cells = self._pit_series_cells(metric_key, company, axis, as_of)
        cells = self._apply_derivation(cells, deriv)
        research = self._research(
            metric_key=metric_key,
            axis=axis,
            derivation=deriv,
            shape=PanelShape.PERIOD_SERIES,
            member_key=company,
            cells=cells,
            boundary_kind="pit",
            boundary_value=format_utc_z(ensure_aware_utc(as_of)),
            dataset_version_id=self._filer_dataset_version(cik).dataset_version_id,
            as_of_timestamp=format_utc_z(ensure_aware_utc(as_of)),
        )
        self._research_store.write(research)
        return PitPanel(
            **self._base_fields(
                metric_key, axis, deriv, PanelShape.PERIOD_SERIES, cells, research
            ),
            as_of=ensure_aware_utc(as_of),
        )

    # -- PIT vintage (4.2) --------------------------------------------------

    def vintage_as_of(
        self,
        metric_key: str,
        cik: str | int,
        period: MetricPeriod,
        as_of_axis: list[datetime] | tuple[datetime, ...],
    ) -> PitPanel:
        """The vintage / knowledge-evolution panel for one filer+period (§2 4.2, §7).

        Evaluates ``metric_key`` for the filer at **one** fiscal ``period`` across
        many ``as_of`` instants — making restatement / knowledge-evolution effects
        first-class, auditable data. Each column is an independent ``PIT(as_of_i)``
        evaluation closed under ``≤ as_of_i``; no column reads another (§7). This
        shape is **PIT-only** — REVISED has no ``as_of`` axis (§3.1). No multi-period
        derivation applies (the axis is time-of-knowledge, not fiscal periods).
        Returns a :class:`PitPanel` with :attr:`PitPanel.as_of_axis` set.
        """
        if not as_of_axis:
            raise PanelConfigurationError(
                "a vintage as_of axis must contain at least one instant; an empty "
                "axis is a configuration bug, not an empty result"
            )
        company = _company_id(cik)
        # Normalize + sort the as_of axis ascending (§2 ordering); a naive instant is
        # rejected here, at the choke point, before any evaluation.
        aware = sorted(ensure_aware_utc(a) for a in as_of_axis)
        if len({a.isoformat() for a in aware}) != len(aware):
            raise PanelConfigurationError(
                "a vintage as_of axis must not contain duplicate instants"
            )
        # A single-period, single-filer axis reuses the period axis identity machinery.
        axis = PeriodAxis.of([period])
        deriv = Derivation.none()
        cells: list[PanelCell] = []
        for instant in aware:
            metric = self._metric_engine.metric_as_of(metric_key, cik, period, instant)
            self._check_shared_version(metric)
            cells.append(
                PanelCell(
                    company_id=company,
                    period=period,
                    as_of=instant,
                    metric=metric,
                )
            )
        cell_tuple = tuple(cells)
        boundary_value = ",".join(format_utc_z(a) for a in aware)
        research = self._research(
            metric_key=metric_key,
            axis=axis,
            derivation=deriv,
            shape=PanelShape.VINTAGE,
            member_key=company,
            cells=cell_tuple,
            boundary_kind="pit-vintage",
            boundary_value=boundary_value,
            dataset_version_id=self._filer_dataset_version(cik).dataset_version_id,
            as_of_timestamp=None,
        )
        self._research_store.write(research)
        return PitPanel(
            **self._base_fields(
                metric_key, axis, deriv, PanelShape.VINTAGE, cell_tuple, research
            ),
            as_of_axis=tuple(aware),
        )

    # -- PIT cross-sectional matrix (4.3) -----------------------------------

    def panel_across(
        self,
        metric_key: str,
        universe: Universe,
        axis: PeriodAxis,
        as_of: datetime,
        *,
        derivation: Derivation | None = None,
    ) -> PitPanel:
        """The point-in-time cross-sectional matrix (§2 4.3, §7) — **engine-only** (D6).

        Many filers x many periods at one shared ``as_of``: reuses the Phase 8
        :class:`Universe` and evaluates one metric per ``(member, period)`` coordinate
        at the same boundary, stacking the columns. Cells are ordered by the §2 total
        order (``(period_end, period_type, period_start)`` then ``company_id``). An
        optional :class:`Derivation` applies **within each filer's own period-series**
        (never across filers), so it cannot add look-ahead (§7). Returns a
        :class:`PitPanel`; the universe-wide :class:`DatasetVersion` is cited for
        reproducibility.
        """
        deriv = derivation if derivation is not None else Derivation.none()
        self._check_derivation_axis(deriv, axis)
        aware = ensure_aware_utc(as_of)
        cells = self._matrix_cells(metric_key, universe, axis, aware, deriv)
        dataset_version = self._factor_engine._universe_dataset_version(universe)
        research = self._research(
            metric_key=metric_key,
            axis=axis,
            derivation=deriv,
            shape=PanelShape.CROSS_SECTION,
            member_key=universe.universe_id,
            cells=cells,
            boundary_kind="pit",
            boundary_value=format_utc_z(aware),
            dataset_version_id=dataset_version.dataset_version_id,
            as_of_timestamp=format_utc_z(aware),
        )
        self._research_store.write(research)
        return PitPanel(
            **self._base_fields(
                metric_key, axis, deriv, PanelShape.CROSS_SECTION, cells, research
            ),
            as_of=aware,
        )

    # -- REVISED period-series ----------------------------------------------

    def revised_panel(
        self,
        metric_key: str,
        cik: str | int,
        axis: PeriodAxis,
        dataset_version: DatasetVersion | None = None,
        *,
        derivation: Derivation | None = None,
    ) -> RevisedPanel:
        """The revised period-series for one filer over a pinned snapshot (§2, §3).

        Every period is resolved at the filer's ingestion frontier (Phase 5 REVISED
        semantics) over the **same** ``DatasetVersion`` — built here from the filer's
        snapshot unless one is supplied — so the whole series is pinned to one
        reproducible state. A multi-period :class:`Derivation` may apply. Returns a
        :class:`RevisedPanel`, not interchangeable with a :class:`PitPanel` (invariant
        28). REVISED has no vintage shape (§3.1).
        """
        deriv = derivation if derivation is not None else Derivation.none()
        self._check_derivation_axis(deriv, axis)
        company = _company_id(cik)
        dv = (
            dataset_version
            if dataset_version is not None
            else self._filer_dataset_version(cik)
        )
        cells = self._revised_series_cells(metric_key, company, axis, dv)
        cells = self._apply_derivation(cells, deriv)
        research = self._research(
            metric_key=metric_key,
            axis=axis,
            derivation=deriv,
            shape=PanelShape.PERIOD_SERIES,
            member_key=company,
            cells=cells,
            boundary_kind="rev",
            boundary_value=dv.dataset_version_id,
            dataset_version_id=dv.dataset_version_id,
            as_of_timestamp=None,
        )
        self._research_store.write(research)
        return RevisedPanel(
            **self._base_fields(
                metric_key, axis, deriv, PanelShape.PERIOD_SERIES, cells, research
            ),
            dataset_version_id=dv.dataset_version_id,
        )

    # -- cell production -----------------------------------------------------

    def _pit_series_cells(
        self,
        metric_key: str,
        company: str,
        axis: PeriodAxis,
        as_of: datetime,
    ) -> tuple[PanelCell, ...]:
        """One PIT cell per axis period, all at the shared ``as_of`` (never dropped)."""
        aware = ensure_aware_utc(as_of)
        cik = cik_from_company_id(company)
        cells: list[PanelCell] = []
        for period in axis:
            metric = self._metric_engine.metric_as_of(metric_key, cik, period, aware)
            self._check_shared_version(metric)
            cells.append(
                PanelCell(company_id=company, period=period, as_of=aware, metric=metric)
            )
        return tuple(cells)

    def _revised_series_cells(
        self,
        metric_key: str,
        company: str,
        axis: PeriodAxis,
        dataset_version: DatasetVersion,
    ) -> tuple[PanelCell, ...]:
        """One REVISED cell per axis period over the shared snapshot (never dropped)."""
        cik = cik_from_company_id(company)
        cells: list[PanelCell] = []
        for period in axis:
            metric = self._metric_engine.revised_metric(
                metric_key, cik, period, dataset_version
            )
            self._check_shared_version(metric)
            cells.append(
                PanelCell(company_id=company, period=period, as_of=None, metric=metric)
            )
        return tuple(cells)

    def _matrix_cells(
        self,
        metric_key: str,
        universe: Universe,
        axis: PeriodAxis,
        as_of: datetime,
        derivation: Derivation,
    ) -> tuple[PanelCell, ...]:
        """One PIT cell per ``(member, period)``, ordered by the §2 total order.

        A derivation applies per filer over that filer's own period-series (never
        across filers). The result is re-ordered so cell emission is by
        ``(period_end, period_type, period_start)`` then ``company_id`` — a total
        order independent of universe/axis iteration nuances.
        """
        by_member: list[tuple[str, tuple[PanelCell, ...]]] = []
        for company in universe:
            member = company  # already a canonical company_id (Phase 8 Universe)
            series = self._pit_series_cells(metric_key, member, axis, as_of)
            series = self._apply_derivation(series, derivation)
            by_member.append((member, series))
        flat: list[PanelCell] = [cell for _, series in by_member for cell in series]
        return tuple(
            sorted(
                flat,
                key=lambda c: (
                    c.period.period_end or "",
                    c.period.period_type.value,
                    c.period.period_start or "",
                    c.company_id,
                ),
            )
        )

    # -- derivation ----------------------------------------------------------

    def _apply_derivation(
        self, cells: tuple[PanelCell, ...], derivation: Derivation
    ) -> tuple[PanelCell, ...]:
        """Apply a multi-period derivation over one filer's ordered series (§3, §7).

        ``cells`` is one filer's period-series in axis order. For the identity
        derivation the cells pass through unchanged. Otherwise each cell gains its
        derivation outcome (value or ``UNDEFINED`` + which input made it so),
        computed purely from cells that were already boundary-eligible — so no
        look-ahead is introduced (§7).
        """
        if derivation.kind is DerivationKind.NONE:
            return cells
        series = [
            SeriesPoint(
                period_key=cell.period.period_key,
                is_known=cell.metric.status is MetricStatus.KNOWN,
                value=(
                    Decimal(cell.metric.value_numeric_str)
                    if cell.metric.status is MetricStatus.KNOWN
                    and cell.metric.value_numeric_str is not None
                    else None
                ),
            )
            for cell in cells
        ]
        derived = derivation.apply(
            series, self._metric_engine.engine_version.decimal_context()
        )
        return tuple(
            PanelCell(
                company_id=cell.company_id,
                period=cell.period,
                as_of=cell.as_of,
                metric=cell.metric,
                derived_value_numeric_str=d.value_numeric_str,
                derived_status=d.status,
                derived_reason=d.reason,
                consumed_period_keys=d.consumed_period_keys,
                undefined_input_period_key=d.undefined_input_period_key,
            )
            for cell, d in zip(cells, derived, strict=True)
        )

    def _check_derivation_axis(self, derivation: Derivation, axis: PeriodAxis) -> None:
        """A period-kind mismatch for a derivation is a config defect, raised (§8)."""
        required = derivation.required_period_type()
        if required is None:
            return
        mismatched = [p for p in axis if p.period_type is not required]
        if mismatched:
            raise PanelConfigurationError(
                f"derivation {derivation.derivation_id!r} requires a "
                f"{required.value} axis, but the axis contains "
                f"{mismatched[0].period_type.value} periods"
            )

    def _check_shared_version(
        self, metric: PitMetricValue | RevisedMetricValue
    ) -> None:
        """Every cell must share this engine's metric version (§5) — surfaced if not."""
        expected = self._metric_engine.engine_version.metric_engine_version_id
        if metric.metric_engine_version_id != expected:
            raise PanelConsistencyError(
                "panel cells must share one metric_engine_version_id; "
                f"expected {expected}, got {metric.metric_engine_version_id}"
            )

    # -- assembly ------------------------------------------------------------

    def _research(
        self,
        *,
        metric_key: str,
        axis: PeriodAxis,
        derivation: Derivation,
        shape: PanelShape,
        member_key: str,
        cells: tuple[PanelCell, ...],
        boundary_kind: str,
        boundary_value: str,
        dataset_version_id: str,
        as_of_timestamp: str | None,
    ) -> PanelResearchResult:
        """Build the reproducible :class:`PanelResearchResult` (§5, data-model §9)."""
        formula = self._metric_engine.registry.get(metric_key)
        engine_version_id = self._metric_engine.engine_version.metric_engine_version_id
        definition_id = _panel_definition_id(
            metric_key=metric_key,
            formula_id=formula.formula_id,
            derivation_id=derivation.derivation_id,
            axis_id=axis.axis_id,
            shape=shape.value,
        )
        rhash = _result_hash([cell.outcome_digest() for cell in cells])
        pid = _panel_id(
            panel_definition_id=definition_id,
            metric_engine_version_id=engine_version_id,
            member_key=member_key,
            boundary_key=_boundary_key(kind=boundary_kind, value=boundary_value),
            result_hash=rhash,
        )
        return PanelResearchResult(
            panel_id=pid,
            panel_definition_id=definition_id,
            metric_engine_version_id=engine_version_id,
            metric_key=metric_key,
            formula_id=formula.formula_id,
            derivation_id=derivation.derivation_id,
            axis_id=axis.axis_id,
            shape=shape.value,
            member_key=member_key,
            boundary_kind=boundary_kind,
            boundary_value=boundary_value,
            dataset_version_id=dataset_version_id,
            as_of_timestamp=as_of_timestamp,
            summary=PanelStatus.from_cells(cells),
            result_hash=rhash,
        )

    def _base_fields(
        self,
        metric_key: str,
        axis: PeriodAxis,
        derivation: Derivation,
        shape: PanelShape,
        cells: tuple[PanelCell, ...],
        research: PanelResearchResult,
    ) -> _PanelBaseFields:
        """The shared :class:`_PanelBase` fields for either panel type.

        Returned as ``_PanelBaseFields`` so ``**`` unpacking into
        :class:`PitPanel` / :class:`RevisedPanel` stays statically checkable.
        """
        return _PanelBaseFields(
            panel_id=research.panel_id,
            panel_definition_id=research.panel_definition_id,
            metric_engine_version_id=research.metric_engine_version_id,
            metric_key=metric_key,
            formula_id=research.formula_id,
            derivation_id=derivation.derivation_id,
            axis_id=axis.axis_id,
            shape=shape.value,
            axis=axis,
            derivation=derivation,
            cells=cells,
            summary=research.summary,
            research_result=research,
        )

    # -- snapshot ------------------------------------------------------------

    def _filer_dataset_version(self, cik: str | int) -> DatasetVersion:
        """The reproducible per-filer snapshot pin (reuses Phase 7, §8)."""
        return self._metric_engine.dataset_version_for(cik)
