"""End-to-end integration for the Phase 10 panel engine over the real backend.

Drives panels through :class:`PanelEngine`, :class:`Workspace`, and the thin
:class:`Company` façade over a genuine multi-year Phase 1/2/4 backend — proving the
engine composes Phase 7 per coordinate at one shared boundary, records one cell per
coordinate (mixed KNOWN/UNDEFINED, never dropped), applies UNDEFINED-preserving
derivations without look-ahead, keeps PIT and REVISED distinct types, produces the
three shapes (period-series / vintage / matrix), reproduces the ``panel_id`` +
values, and persists + round-trips the research sidecar (Decision D4).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from quantforge.availability.timestamps import parse_utc
from quantforge.company import Company
from quantforge.factors.universe import Universe
from quantforge.metrics.model import MetricPeriod, MetricStatus
from quantforge.panel.axis import PeriodAxis
from quantforge.panel.derive import Derivation
from quantforge.panel.engine import PanelEngine
from quantforge.panel.errors import PanelConfigurationError
from quantforge.panel.model import PanelShape, PitPanel, RevisedPanel
from quantforge.registry.identity import company_id as _company_id
from quantforge.workspace import Workspace
from quantforge.xbrl.contexts import PeriodType
from tests.panel.builders import APPLE, MSFT, Year, populate

APPLE_YEARS = [
    Year(2018, assets="100", liabilities="50"),  # ratio 2
    Year(2019, assets="120", liabilities="50"),  # ratio 2.4
    Year(2020, assets="200", liabilities="50"),  # ratio 4
]
MSFT_YEARS = [
    Year(2018, assets="300", liabilities="100"),  # ratio 3
    Year(2019, assets=None, liabilities="100"),  # UNDEFINED (missing assets)
    Year(2020, assets="500", liabilities="100"),  # ratio 5
]

LATE = "2024-06-01T00:00:00Z"  # after every filing is public


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return populate(tmp_path, apple_years=APPLE_YEARS, msft_years=MSFT_YEARS)


@pytest.fixture
def engine(workspace: Workspace) -> PanelEngine:
    return PanelEngine(workspace)


def _annual_instant() -> PeriodAxis:
    return PeriodAxis.annual("2018-12-31", "2020-12-31", period_type=PeriodType.INSTANT)


class TestPitPeriodSeries:
    def test_returns_pit_type_one_cell_per_period(self, engine: PanelEngine) -> None:
        p = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc(LATE)
        )
        assert isinstance(p, PitPanel)
        assert p.shape == PanelShape.PERIOD_SERIES.value
        assert [c.period.period_end for c in p.cells] == [
            "2018-12-31",
            "2019-12-31",
            "2020-12-31",
        ]

    def test_values_match_standalone_phase7(
        self, engine: PanelEngine, workspace: Workspace
    ) -> None:
        p = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc(LATE)
        )
        metric_engine = workspace.metric_engine
        for cell in p.cells:
            standalone = metric_engine.metric_as_of(  # type: ignore[attr-defined]
                "current_ratio", APPLE, cell.period, parse_utc(LATE)
            )
            assert cell.metric.value_numeric_str == standalone.value_numeric_str
            assert cell.metric.status is standalone.status

    def test_all_periods_known(self, engine: PanelEngine) -> None:
        p = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc(LATE)
        )
        assert [c.metric.value_numeric_str for c in p.cells] == ["2", "2.4", "4"]


class TestLookAhead:
    def test_as_of_hides_periods_not_yet_public(self, engine: PanelEngine) -> None:
        # At 2019-06 only FY2018 (filed 2019-02) is public; later years are UNDEFINED
        # cells, never dropped and never look-ahead-resolved.
        p = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc("2019-06-01T00:00:00Z")
        )
        by_end = {c.period.period_end: c.metric.status for c in p.cells}
        assert by_end["2018-12-31"] is MetricStatus.KNOWN
        assert by_end["2019-12-31"] is MetricStatus.UNDEFINED
        assert by_end["2020-12-31"] is MetricStatus.UNDEFINED

    def test_before_any_filing_all_undefined(self, engine: PanelEngine) -> None:
        p = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc("2017-01-01T00:00:00Z")
        )
        assert all(c.metric.status is MetricStatus.UNDEFINED for c in p.cells)


class TestDerivations:
    def test_growth_over_series(self, engine: PanelEngine) -> None:
        # working_capital: 50, 70, 150 → growth 2019: (70-50)/50=0.4; 2020: (150-70)/70.
        p = engine.panel_as_of(
            "working_capital",
            APPLE,
            _annual_instant(),
            parse_utc(LATE),
            derivation=Derivation.growth(),
        )
        cells = {c.period.period_end: c for c in p.cells}
        assert (
            cells["2018-12-31"].effective_status is MetricStatus.UNDEFINED
        )  # no prior
        assert cells["2019-12-31"].derived_value_numeric_str == "0.4"
        assert cells["2019-12-31"].consumed_period_keys == (
            MetricPeriod.instant("2018-12-31").period_key,
            MetricPeriod.instant("2019-12-31").period_key,
        )

    def test_derivation_undefined_input_poisons_and_names_it(
        self, engine: PanelEngine
    ) -> None:
        # MSFT FY2019 current_ratio is UNDEFINED (missing assets); growth 2019 & 2020
        # both consume it and must be UNDEFINED, naming the bad period.
        p = engine.panel_as_of(
            "current_ratio",
            MSFT,
            _annual_instant(),
            parse_utc(LATE),
            derivation=Derivation.growth(),
        )
        cells = {c.period.period_end: c for c in p.cells}
        bad_key = MetricPeriod.instant("2019-12-31").period_key
        assert cells["2019-12-31"].effective_status is MetricStatus.UNDEFINED
        assert cells["2019-12-31"].undefined_input_period_key == bad_key
        assert cells["2020-12-31"].effective_status is MetricStatus.UNDEFINED
        assert cells["2020-12-31"].undefined_input_period_key == bad_key

    def test_ttm_over_instant_axis_is_config_error(self, engine: PanelEngine) -> None:
        with pytest.raises(PanelConfigurationError):
            engine.panel_as_of(
                "current_ratio",
                APPLE,
                _annual_instant(),
                parse_utc(LATE),
                derivation=Derivation.ttm(),
            )


class TestVintage:
    def test_vintage_walks_as_of_axis(self, engine: PanelEngine) -> None:
        # FY2020 seen at two instants: before its filing (UNDEFINED) and after (KNOWN).
        period = MetricPeriod.instant("2020-12-31")
        p = engine.vintage_as_of(
            "current_ratio",
            APPLE,
            period,
            [parse_utc("2020-06-01T00:00:00Z"), parse_utc(LATE)],
        )
        assert isinstance(p, PitPanel)
        assert p.shape == PanelShape.VINTAGE.value
        assert p.as_of is None
        assert len(p.as_of_axis) == 2
        assert p.cells[0].metric.status is MetricStatus.UNDEFINED  # pre-filing
        assert p.cells[1].metric.status is MetricStatus.KNOWN
        assert p.cells[1].metric.value_numeric_str == "4"

    def test_empty_as_of_axis_rejected(self, engine: PanelEngine) -> None:
        with pytest.raises(PanelConfigurationError):
            engine.vintage_as_of(
                "current_ratio", APPLE, MetricPeriod.instant("2020-12-31"), []
            )

    def test_duplicate_as_of_rejected(self, engine: PanelEngine) -> None:
        with pytest.raises(PanelConfigurationError):
            engine.vintage_as_of(
                "current_ratio",
                APPLE,
                MetricPeriod.instant("2020-12-31"),
                [parse_utc(LATE), parse_utc(LATE)],
            )


class TestMatrix:
    def test_matrix_stacks_filers_in_total_order(self, engine: PanelEngine) -> None:
        universe = Universe.of(APPLE, MSFT)
        m = engine.panel_across(
            "current_ratio", universe, _annual_instant(), parse_utc(LATE)
        )
        assert isinstance(m, PitPanel)
        assert m.shape == PanelShape.CROSS_SECTION.value
        # 2 filers x 3 periods = 6 cells; ordered by (period_end, ..., company_id).
        assert len(m.cells) == 6
        coords = [(c.period.period_end, c.company_id) for c in m.cells]
        assert coords == [
            ("2018-12-31", _company_id(APPLE)),
            ("2018-12-31", _company_id(MSFT)),
            ("2019-12-31", _company_id(APPLE)),
            ("2019-12-31", _company_id(MSFT)),
            ("2020-12-31", _company_id(APPLE)),
            ("2020-12-31", _company_id(MSFT)),
        ]

    def test_matrix_derivation_is_per_filer_never_across(
        self, engine: PanelEngine
    ) -> None:
        # Growth must be computed within each filer's own series. APPLE 2019 growth
        # uses APPLE 2018 (not MSFT), so it stays KNOWN even though MSFT 2019 is bad.
        universe = Universe.of(APPLE, MSFT)
        m = engine.panel_across(
            "current_ratio",
            universe,
            _annual_instant(),
            parse_utc(LATE),
            derivation=Derivation.growth(),
        )
        by = {(c.period.period_end, c.company_id): c for c in m.cells}
        apple_2019 = by[("2019-12-31", _company_id(APPLE))]
        assert apple_2019.effective_status is MetricStatus.KNOWN
        msft_2019 = by[("2019-12-31", _company_id(MSFT))]
        assert msft_2019.effective_status is MetricStatus.UNDEFINED

    def test_missing_filer_is_undefined_cells_never_dropped(
        self, engine: PanelEngine
    ) -> None:
        universe = Universe.of(APPLE, 1067983)  # Berkshire — not populated
        m = engine.panel_across(
            "current_ratio", universe, _annual_instant(), parse_utc(LATE)
        )
        missing = [c for c in m.cells if c.company_id == _company_id(1067983)]
        assert len(missing) == 3
        assert all(c.metric.status is MetricStatus.UNDEFINED for c in missing)


class TestRevised:
    def test_revised_type_and_shared_snapshot(self, engine: PanelEngine) -> None:
        r = engine.revised_panel("current_ratio", APPLE, _annual_instant())
        assert isinstance(r, RevisedPanel)
        assert not hasattr(r, "as_of")  # REVISED has no as_of; a vintage is PIT-only
        # Every cell resolved against the one shared dataset snapshot.
        assert r.dataset_version_id.startswith("sha256:")
        for cell in r.cells:
            assert cell.as_of is None

    def test_revised_has_no_vintage(self, engine: PanelEngine) -> None:
        # "REVISED vintage" is a contradiction — restatement history is PIT-only.
        assert not hasattr(engine, "revised_vintage")

    def test_reinterpret_as_pit_reevaluates(self, engine: PanelEngine) -> None:
        r = engine.revised_panel("current_ratio", APPLE, _annual_instant())
        p = r.reinterpret_as_pit(engine, parse_utc(LATE))
        assert isinstance(p, PitPanel)
        assert not isinstance(p, RevisedPanel)
        assert [c.metric.value_numeric_str for c in p.cells] == ["2", "2.4", "4"]


class TestReproducibility:
    def test_same_request_same_panel_id_and_hash(self, engine: PanelEngine) -> None:
        one = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc(LATE)
        )
        two = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc(LATE)
        )
        assert one.panel_id == two.panel_id
        assert one.research_result.result_hash == two.research_result.result_hash

    def test_derivation_changes_panel_id(self, engine: PanelEngine) -> None:
        plain = engine.panel_as_of(
            "working_capital", APPLE, _annual_instant(), parse_utc(LATE)
        )
        grown = engine.panel_as_of(
            "working_capital",
            APPLE,
            _annual_instant(),
            parse_utc(LATE),
            derivation=Derivation.growth(),
        )
        assert plain.panel_id != grown.panel_id

    def test_pit_and_revised_have_distinct_ids(self, engine: PanelEngine) -> None:
        pit = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc(LATE)
        )
        rev = engine.revised_panel("current_ratio", APPLE, _annual_instant())
        assert pit.panel_id != rev.panel_id

    def test_research_result_persisted_and_round_trips(
        self, engine: PanelEngine, workspace: Workspace
    ) -> None:
        from quantforge.panel.model import PanelResearchResult

        p = engine.panel_as_of(
            "current_ratio", APPLE, _annual_instant(), parse_utc(LATE)
        )
        stored = workspace.research_result_store.read_as(
            p.research_result.research_result_id, PanelResearchResult.from_dict
        )
        assert stored is not None
        assert stored.to_dict() == p.research_result.to_dict()


class TestCompanyDelegation:
    def test_company_panel_as_of(self, workspace: Workspace) -> None:
        apple = Company.resolve("AAPL", workspace=workspace)
        p = apple.panel_as_of("current_ratio", _annual_instant(), parse_utc(LATE))
        assert isinstance(p, PitPanel)
        assert [c.metric.value_numeric_str for c in p.cells] == ["2", "2.4", "4"]

    def test_company_vintage_and_revised(self, workspace: Workspace) -> None:
        apple = Company.resolve("AAPL", workspace=workspace)
        v = apple.vintage_as_of(
            "current_ratio", MetricPeriod.instant("2020-12-31"), [parse_utc(LATE)]
        )
        assert v.shape == PanelShape.VINTAGE.value
        r = apple.revised_panel("current_ratio", _annual_instant())
        assert isinstance(r, RevisedPanel)


class TestAdditiveWiring:
    def test_panel_engine_cached_on_workspace(self, workspace: Workspace) -> None:
        assert workspace.panel_engine is workspace.panel_engine

    def test_naive_as_of_rejected(self, engine: PanelEngine) -> None:
        # A naive as_of is a look-ahead hazard; the availability boundary rejects it.
        with pytest.raises(ValueError, match="timezone-aware"):
            engine.panel_as_of(
                "current_ratio", APPLE, _annual_instant(), datetime(2024, 6, 1)
            )

    def test_unknown_metric_fails_closed(self, engine: PanelEngine) -> None:
        from quantforge.metrics.errors import FormulaConfigurationError

        with pytest.raises(FormulaConfigurationError):
            engine.panel_as_of("ebitda", APPLE, _annual_instant(), parse_utc(LATE))
