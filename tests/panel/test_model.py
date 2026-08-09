"""Deterministic tests for the panel result model (locked §2, §5, §6).

Pins the :class:`PanelCell` effective-status/reason logic (the derivation's outcome
shadows the raw metric's when one applied), :class:`PanelStatus.from_cells` counting
over the *effective* outcome, and the :class:`PanelResearchResult` §9 aliasing +
round-trip through ``to_dict``/``from_dict``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from quantforge.metrics.model import (
    MetricPeriod,
    MetricProvenance,
    MetricStatus,
    PitMetricValue,
    UndefinedReason,
)
from quantforge.panel.model import (
    PanelCell,
    PanelResearchResult,
    PanelStatus,
    PitPanel,
    RevisedPanel,
)

PERIOD = MetricPeriod.instant("2023-12-31")
AS_OF = datetime(2024, 6, 1, tzinfo=UTC)


def _prov(status: MetricStatus, reason: UndefinedReason | None) -> MetricProvenance:
    return MetricProvenance(
        formula_id="sha256:formula",
        metric_engine_version_id="sha256:mev",
        boundary_kind="pit",
        boundary_value="2024-06-01T00:00:00Z",
        inputs=(),
        result_status=status,
        result_reason=reason,
    )


def _metric(
    status: MetricStatus,
    value: str | None,
    reason: UndefinedReason | None = None,
) -> PitMetricValue:
    return PitMetricValue(
        metric_id="sha256:m",
        metric_key="current_ratio",
        formula_id="sha256:formula",
        metric_engine_version_id="sha256:mev",
        company_id="cik:0000320193",
        period=PERIOD,
        status=status,
        value_numeric_str=value,
        unit=None,
        reason=reason,
        provenance=_prov(status, reason),
        as_of=AS_OF,
    )


def _cell(**kw: object) -> PanelCell:
    base = dict(
        company_id="cik:0000320193",
        period=PERIOD,
        as_of=AS_OF,
        metric=_metric(MetricStatus.KNOWN, "2"),
    )
    base.update(kw)
    return PanelCell(**base)  # type: ignore[arg-type]


class TestPanelCellEffective:
    def test_raw_metric_when_no_derivation(self) -> None:
        cell = _cell()
        assert not cell.has_derivation
        assert cell.effective_status is MetricStatus.KNOWN
        assert cell.effective_reason is None

    def test_derivation_status_shadows_metric(self) -> None:
        # A KNOWN metric but an UNDEFINED derivation → effective is UNDEFINED.
        cell = _cell(
            derived_status=MetricStatus.UNDEFINED,
            derived_reason=UndefinedReason.MISSING_INPUT,
        )
        assert cell.has_derivation
        assert cell.effective_status is MetricStatus.UNDEFINED
        assert cell.effective_reason is UndefinedReason.MISSING_INPUT

    def test_known_derivation(self) -> None:
        cell = _cell(
            derived_status=MetricStatus.KNOWN,
            derived_value_numeric_str="0.5",
        )
        assert cell.effective_status is MetricStatus.KNOWN
        assert cell.effective_reason is None

    def test_outcome_digest_is_output_only(self) -> None:
        digest = _cell().outcome_digest()
        assert digest["metric_value_numeric"] == "2"
        assert "provenance" not in digest


class TestPanelStatus:
    def test_counts_over_effective_outcome(self) -> None:
        cells = (
            _cell(metric=_metric(MetricStatus.KNOWN, "2")),
            _cell(
                metric=_metric(
                    MetricStatus.UNDEFINED, None, UndefinedReason.MISSING_INPUT
                )
            ),
            # KNOWN metric shadowed by an UNDEFINED derivation → counts as undefined.
            _cell(
                derived_status=MetricStatus.UNDEFINED,
                derived_reason=UndefinedReason.DIVIDE_BY_ZERO,
            ),
        )
        summary = PanelStatus.from_cells(cells)
        assert summary.total == 3
        assert summary.known == 1
        assert summary.undefined_by_reason == {
            "divide_by_zero": 1,
            "missing_input": 1,
        }

    def test_round_trip(self) -> None:
        summary = PanelStatus(
            total=3, known=1, undefined_by_reason={"missing_input": 2}
        )
        assert PanelStatus.from_dict(summary.to_dict()) == summary


class TestPanelResearchResult:
    def _rr(self) -> PanelResearchResult:
        return PanelResearchResult(
            panel_id="sha256:panel",
            panel_definition_id="sha256:def",
            metric_engine_version_id="sha256:mev",
            metric_key="current_ratio",
            formula_id="sha256:formula",
            derivation_id="growth",
            axis_id="sha256:axis",
            shape="period_series",
            member_key="cik:0000320193",
            boundary_kind="pit",
            boundary_value="2024-06-01T00:00:00Z",
            dataset_version_id="sha256:dv",
            as_of_timestamp="2024-06-01T00:00:00Z",
            summary=PanelStatus(total=1, known=1, undefined_by_reason={}),
            result_hash="sha256:rh",
        )

    def test_research_result_id_is_panel_id(self) -> None:
        rr = self._rr()
        assert rr.research_result_id == rr.panel_id

    def test_datamodel_aliases_and_no_strategy_version(self) -> None:
        data = self._rr().to_dict()
        assert data["factor_definition_id"] == data["panel_definition_id"]
        assert data["factor_version"] == data["metric_engine_version_id"]
        assert "strategy_version" not in data

    def test_query_params_records_axis_derivation_shape(self) -> None:
        params = self._rr().query_params
        assert params["axis_id"] == "sha256:axis"
        assert params["derivation"] == "growth"
        assert params["shape"] == "period_series"

    def test_round_trip(self) -> None:
        rr = self._rr()
        assert PanelResearchResult.from_dict(rr.to_dict()).to_dict() == rr.to_dict()


class TestPanelTypesDistinct:
    def _base(self) -> dict[str, object]:
        rr = TestPanelResearchResult()._rr()
        from quantforge.panel.axis import PeriodAxis
        from quantforge.panel.derive import Derivation

        axis = PeriodAxis.of([PERIOD])
        return dict(
            panel_id=rr.panel_id,
            panel_definition_id=rr.panel_definition_id,
            metric_engine_version_id=rr.metric_engine_version_id,
            metric_key=rr.metric_key,
            formula_id=rr.formula_id,
            derivation_id=rr.derivation_id,
            axis_id=rr.axis_id,
            shape=rr.shape,
            axis=axis,
            derivation=Derivation.growth(),
            cells=(_cell(),),
            summary=rr.summary,
            research_result=rr,
        )

    def test_pit_and_revised_are_not_the_same_type(self) -> None:
        pit = PitPanel(**self._base(), as_of=AS_OF)  # type: ignore[arg-type]
        rev = RevisedPanel(**self._base(), dataset_version_id="sha256:dv")  # type: ignore[arg-type]
        assert isinstance(pit, PitPanel)
        assert isinstance(rev, RevisedPanel)
        assert not isinstance(rev, PitPanel)
        assert pit.to_dict()["mode"] == "pit"
        assert rev.to_dict()["mode"] == "revised"
