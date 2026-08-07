"""Tests for the factor result model round-trips (``docs/factors.md`` §5, §7).

Covers: :class:`FactorStatus.from_cells` counting; :class:`ResearchResult` dict
round-trip and its §9 field aliasing; the distinct :class:`PitFactor` /
:class:`RevisedFactor` to_dict/from_dict round-trips.
"""

from __future__ import annotations

from openfinance.factors.model import (
    FactorCell,
    FactorStatus,
    PitFactor,
    ResearchResult,
    RevisedFactor,
)
from openfinance.metrics.model import (
    MetricPeriod,
    MetricProvenance,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)
from tests.factors.builders import research_result

PERIOD = MetricPeriod.instant("2023-09-30")


def _provenance(kind: str, value: str) -> MetricProvenance:
    return MetricProvenance(
        formula_id="sha256:formula",
        metric_engine_version_id="sha256:engine",
        boundary_kind=kind,
        boundary_value=value,
        inputs=(),
        result_status=MetricStatus.KNOWN,
    )


def _pit_metric(
    company: str, value: str | None, status: MetricStatus
) -> PitMetricValue:
    from openfinance.availability.timestamps import parse_utc

    return PitMetricValue(
        metric_id="sha256:m",
        metric_key="current_ratio",
        formula_id="sha256:formula",
        metric_engine_version_id="sha256:engine",
        company_id=company,
        period=PERIOD,
        status=status,
        value_numeric_str=value,
        unit="pure" if value is not None else None,
        reason=None if status is MetricStatus.KNOWN else UndefinedReason.MISSING_INPUT,
        provenance=_provenance("pit", "2023-11-05T21:30:00Z"),
        as_of=parse_utc("2023-11-05T21:30:00Z"),
    )


def _rev_metric(company: str, value: str) -> RevisedMetricValue:
    return RevisedMetricValue(
        metric_id="sha256:m",
        metric_key="current_ratio",
        formula_id="sha256:formula",
        metric_engine_version_id="sha256:engine",
        company_id=company,
        period=PERIOD,
        status=MetricStatus.KNOWN,
        value_numeric_str=value,
        unit="pure",
        reason=None,
        provenance=_provenance("rev", "sha256:dv"),
        dataset_version_id="sha256:dv",
    )


class TestFactorStatus:
    def test_counts_known_and_reasons(self) -> None:
        cells = (
            FactorCell(
                "cik:0000320193",
                _pit_metric("cik:0000320193", "2", MetricStatus.KNOWN),
            ),
            FactorCell(
                "cik:0000789019",
                _pit_metric("cik:0000789019", None, MetricStatus.UNDEFINED),
            ),
        )
        status = FactorStatus.from_cells(cells)
        assert status.total == 2
        assert status.known == 1
        assert status.undefined_by_reason == {"missing_input": 1}


class TestResearchResultRoundTrip:
    def test_to_from_dict_identical(self) -> None:
        original = research_result()
        round_tripped = ResearchResult.from_dict(original.to_dict())
        assert round_tripped.to_dict() == original.to_dict()

    def test_factor_version_aliases_engine_version(self) -> None:
        data = research_result().to_dict()
        assert data["factor_version"] == data["metric_engine_version_id"]


class TestPitFactorRoundTrip:
    def test_to_from_dict_identical(self) -> None:
        from openfinance.availability.timestamps import parse_utc

        cells = (
            FactorCell(
                "cik:0000320193",
                _pit_metric("cik:0000320193", "2", MetricStatus.KNOWN),
                transformed_value_numeric_str="1",
            ),
        )
        factor = PitFactor(
            research_result_id="sha256:rr",
            factor_definition_id="sha256:def",
            metric_engine_version_id="sha256:engine",
            metric_key="current_ratio",
            formula_id="sha256:formula",
            transform_id="rank",
            universe_id="sha256:universe",
            period=PERIOD,
            cells=cells,
            summary=FactorStatus.from_cells(cells),
            research_result=research_result(),
            as_of=parse_utc("2023-11-05T21:30:00Z"),
        )
        assert PitFactor.from_dict(factor.to_dict()).to_dict() == factor.to_dict()
        assert factor.to_dict()["mode"] == "pit"


class TestRevisedFactorRoundTrip:
    def test_to_from_dict_identical(self) -> None:
        cells = (FactorCell("cik:0000320193", _rev_metric("cik:0000320193", "2")),)
        factor = RevisedFactor(
            research_result_id="sha256:rr",
            factor_definition_id="sha256:def",
            metric_engine_version_id="sha256:engine",
            metric_key="current_ratio",
            formula_id="sha256:formula",
            transform_id="none",
            universe_id="sha256:universe",
            period=PERIOD,
            cells=cells,
            summary=FactorStatus.from_cells(cells),
            research_result=research_result(
                boundary_kind="rev",
                boundary_value="sha256:dv",
                as_of_timestamp=None,
            ),
            dataset_version_id="sha256:dv",
        )
        assert RevisedFactor.from_dict(factor.to_dict()).to_dict() == factor.to_dict()
        assert factor.to_dict()["mode"] == "revised"
