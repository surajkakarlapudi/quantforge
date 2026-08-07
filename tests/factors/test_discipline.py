"""PIT discipline for the cross-sectional factor layer (``docs/factors.md`` §11, §15).

Two guarantees, lifted from Phase 5/7 to the vector:

* **Cell-wise monotonicity.** As the shared ``as_of`` advances across a filer's
  last input's availability, that filer's cell goes ``UNDEFINED → KNOWN`` and stays
  known — the factor is the cross-section of per-cell PIT results, so it inherits
  monotonicity cell by cell (invariant 29).
* **Type separation.** ``PitFactor`` and ``RevisedFactor`` are distinct types
  (invariant 28, F5); the PIT boundary and the REVISED boundary produce different
  ``research_result_id``s, so a factor's PIT-ness is structural, not hoped-for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openfinance.availability.timestamps import parse_utc
from openfinance.factors.engine import FactorEngine
from openfinance.factors.model import PitFactor, RevisedFactor
from openfinance.factors.universe import Universe
from openfinance.metrics.model import MetricStatus
from tests.factors.test_engine_integration import (
    APPLE,
    FY_END,
    MSFT,
    PERIOD,
    _populate,
)


@pytest.fixture
def engine(tmp_path: Path) -> FactorEngine:
    return FactorEngine(_populate(tmp_path))


@pytest.fixture
def universe() -> Universe:
    return Universe.of(APPLE, MSFT)


def test_cells_go_undefined_to_known_as_as_of_advances(
    engine: FactorEngine, universe: Universe
) -> None:
    # Before the filings are public: every cell UNDEFINED.
    before = engine.factor_as_of(
        "current_ratio", universe, PERIOD, parse_utc("2023-01-01T00:00:00Z")
    )
    assert all(c.metric.status is MetricStatus.UNDEFINED for c in before.cells)

    # Well after acceptance (2023-11-02): every cell KNOWN.
    after = engine.factor_as_of(
        "current_ratio", universe, PERIOD, parse_utc("2024-06-01T00:00:00Z")
    )
    assert all(c.metric.status is MetricStatus.KNOWN for c in after.cells)


def test_pit_and_revised_are_distinct_types(
    engine: FactorEngine, universe: Universe
) -> None:
    pit = engine.factor_as_of(
        "current_ratio", universe, PERIOD, parse_utc("2024-06-01T00:00:00Z")
    )
    rev = engine.revised_factor("current_ratio", universe, PERIOD)
    assert isinstance(pit, PitFactor)
    assert isinstance(rev, RevisedFactor)
    assert not isinstance(pit, RevisedFactor)
    assert not isinstance(rev, PitFactor)


def test_advancing_as_of_never_regresses_a_known_cell(
    engine: FactorEngine, universe: Universe
) -> None:
    # Once known, a later as_of keeps the cell known with the same value.
    early = engine.factor_as_of(
        "current_ratio", universe, PERIOD, parse_utc("2023-11-10T00:00:00Z")
    )
    late = engine.factor_as_of(
        "current_ratio", universe, PERIOD, parse_utc("2025-01-01T00:00:00Z")
    )
    early_by_id = {c.company_id: c for c in early.cells}
    for cell in late.cells:
        prior = early_by_id[cell.company_id]
        if prior.metric.status is MetricStatus.KNOWN:
            assert cell.metric.status is MetricStatus.KNOWN
            assert cell.metric.value_numeric_str == prior.metric.value_numeric_str


def test_period_end_is_fiscal_year_end(engine: FactorEngine) -> None:
    # Guard the shared fixture constant so the monotonicity dates stay meaningful.
    assert PERIOD.period_end == FY_END
