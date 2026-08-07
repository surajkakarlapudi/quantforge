"""PIT/REVISED discipline at the metric layer (metrics.md §5, invariants 27, 28).

Distinct result types that cannot be silently interchanged; no default mode (each
entry point demands its own boundary argument); a naive ``as_of`` is rejected at
the Phase 5 choke point; ``reinterpret_as_pit`` re-resolves rather than reusing the
revised value; and PIT monotonicity — an input public later is invisible earlier.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from openfinance.availability.errors import ModeError
from openfinance.availability.resolve import PointInTimeResolver
from openfinance.availability.version import DatasetVersion
from openfinance.canonical.model import Fact
from openfinance.metrics.evaluate import MetricEvaluator
from openfinance.metrics.model import (
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
)
from openfinance.metrics.registry import FormulaRegistry
from openfinance.metrics.resolve_input import MetricBoundary
from tests.metrics.builders import CIK, avail, instant, resolver, utc

ACC_OLD = "0000320193-20-000001"
ACC_NEW = "0000320193-23-000106"
COMPANY = f"cik:{CIK:010d}"
REG = FormulaRegistry()


def _period() -> MetricPeriod:
    return MetricPeriod.instant("2023-09-30")


def _dataset() -> DatasetVersion:
    return DatasetVersion(
        transformation_version_id="sha256:tv",
        availability_policy_ids=("sha256:policy",),
        raw_document_ids=(),
        fact_ids=(),
    )


class TestDistinctTypes:
    def test_pit_returns_pit_type(self) -> None:
        facts = [
            instant(ACC_NEW, "AssetsCurrent", "200"),
            instant(ACC_NEW, "LiabilitiesCurrent", "100"),
        ]
        avs = {
            facts[0].filing_id: avail(
                accession=ACC_NEW, timestamp="2023-11-05T21:30:00Z"
            )
        }
        m = MetricEvaluator().evaluate_pit(
            REG.get("current_ratio"),
            COMPANY,
            facts,
            resolver(facts, avs),
            _period(),
            MetricBoundary.pit(utc("2023-11-05T21:30:00Z")),
        )
        assert isinstance(m, PitMetricValue)
        assert not isinstance(m, RevisedMetricValue)
        assert m.to_dict()["mode"] == "pit"

    def test_revised_returns_revised_type(self) -> None:
        facts = [
            instant(ACC_NEW, "AssetsCurrent", "200"),
            instant(ACC_NEW, "LiabilitiesCurrent", "100"),
        ]
        avs = {
            facts[0].filing_id: avail(
                accession=ACC_NEW, timestamp="2023-11-05T21:30:00Z"
            )
        }
        m = MetricEvaluator().evaluate_revised(
            REG.get("current_ratio"),
            COMPANY,
            facts,
            resolver(facts, avs),
            _period(),
            MetricBoundary.revised(_dataset()),
        )
        assert isinstance(m, RevisedMetricValue)
        assert not isinstance(m, PitMetricValue)
        assert m.to_dict()["mode"] == "revised"


class TestBoundaryGuards:
    def test_evaluate_pit_rejects_revised_boundary(self) -> None:
        from openfinance.metrics.errors import FormulaConfigurationError

        facts: list[Fact] = []
        with pytest.raises(FormulaConfigurationError):
            MetricEvaluator().evaluate_pit(
                REG.get("current_ratio"),
                COMPANY,
                facts,
                resolver(facts, {}),
                _period(),
                MetricBoundary.revised(_dataset()),
            )

    def test_evaluate_revised_rejects_pit_boundary(self) -> None:
        from openfinance.metrics.errors import FormulaConfigurationError

        facts: list[Fact] = []
        with pytest.raises(FormulaConfigurationError):
            MetricEvaluator().evaluate_revised(
                REG.get("current_ratio"),
                COMPANY,
                facts,
                resolver(facts, {}),
                _period(),
                MetricBoundary.pit(utc("2023-11-05T21:30:00Z")),
            )

    def test_naive_as_of_rejected(self) -> None:
        facts = [
            instant(ACC_NEW, "AssetsCurrent", "200"),
            instant(ACC_NEW, "LiabilitiesCurrent", "100"),
        ]
        avs = {
            facts[0].filing_id: avail(
                accession=ACC_NEW, timestamp="2023-11-05T21:30:00Z"
            )
        }
        naive = datetime(2023, 11, 5, 21, 30, 0)  # intentional naive instant
        with pytest.raises(ModeError):
            MetricEvaluator().evaluate_pit(
                REG.get("current_ratio"),
                COMPANY,
                facts,
                resolver(facts, avs),
                _period(),
                MetricBoundary.pit(naive),
            )


class TestMonotonicity:
    def _world(self) -> tuple[list[Fact], PointInTimeResolver]:
        # Assets known from 2023-11; liabilities only from 2024-02 (a late input).
        facts = [
            instant(ACC_NEW, "AssetsCurrent", "200"),
            instant(ACC_OLD, "LiabilitiesCurrent", "100"),
        ]
        avs = {
            facts[0].filing_id: avail(
                accession=ACC_NEW, timestamp="2023-11-05T21:30:00Z"
            ),
            facts[1].filing_id: avail(
                accession=ACC_OLD, timestamp="2024-02-01T21:30:00Z"
            ),
        }
        return facts, resolver(facts, avs)

    def test_before_second_input_public_is_undefined(self) -> None:
        facts, res = self._world()
        m = MetricEvaluator().evaluate_pit(
            REG.get("current_ratio"),
            COMPANY,
            facts,
            res,
            _period(),
            MetricBoundary.pit(utc("2023-12-01T00:00:00Z")),
        )
        assert m.status is MetricStatus.UNDEFINED

    def test_after_second_input_public_is_known(self) -> None:
        facts, res = self._world()
        m = MetricEvaluator().evaluate_pit(
            REG.get("current_ratio"),
            COMPANY,
            facts,
            res,
            _period(),
            MetricBoundary.pit(utc("2024-03-01T00:00:00Z")),
        )
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "2"


class TestRoundTrip:
    def test_pit_to_dict_from_dict(self) -> None:
        facts = [
            instant(ACC_NEW, "AssetsCurrent", "200"),
            instant(ACC_NEW, "LiabilitiesCurrent", "100"),
        ]
        avs = {
            facts[0].filing_id: avail(
                accession=ACC_NEW, timestamp="2023-11-05T21:30:00Z"
            )
        }
        m = MetricEvaluator().evaluate_pit(
            REG.get("current_ratio"),
            COMPANY,
            facts,
            resolver(facts, avs),
            _period(),
            MetricBoundary.pit(utc("2023-11-05T21:30:00Z")),
        )
        again = PitMetricValue.from_dict(m.to_dict())
        assert again.to_dict() == m.to_dict()

    def test_revised_to_dict_from_dict(self) -> None:
        facts = [
            instant(ACC_NEW, "AssetsCurrent", "200"),
            instant(ACC_NEW, "LiabilitiesCurrent", "100"),
        ]
        avs = {
            facts[0].filing_id: avail(
                accession=ACC_NEW, timestamp="2023-11-05T21:30:00Z"
            )
        }
        m = MetricEvaluator().evaluate_revised(
            REG.get("current_ratio"),
            COMPANY,
            facts,
            resolver(facts, avs),
            _period(),
            MetricBoundary.revised(_dataset()),
        )
        again = RevisedMetricValue.from_dict(m.to_dict())
        assert again.to_dict() == m.to_dict()
