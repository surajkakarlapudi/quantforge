"""Shape validation + canonical serialization of the diagnostics request (locked §3.1).

The spec is a frozen, self-validating value: it reads no store and no wall clock,
refuses a misconfigured request at construction (fail closed), and canonicalizes
``ic_methods`` to a sorted, de-duplicated set so caller order/spelling never reaches
identity or the serialized payload. These tests pin every one of those guarantees; they
build the spec directly (no
corpus needed) with placeholder corpus pins.
"""

from __future__ import annotations

import pytest

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.diagnostics.errors import SignalDiagnosticsConfigurationError
from quantforge.diagnostics.spec import (
    DIAGNOSTICS_SPEC_VERSION,
    SignalDiagnosticsSpecification,
)
from quantforge.metrics.model import MetricPeriod
from tests.diagnostics.builders import EVAL_1, EVAL_2, PERIOD, universe_spec

_UNIVERSE = universe_spec(include_b=True)
_SCHED = RebalanceSchedule.of([EVAL_1, EVAL_2])


def _spec(**overrides: object) -> SignalDiagnosticsSpecification:
    kwargs: dict[str, object] = {
        "name": "phase16",
        "signal": "current_ratio",
        "period": PERIOD,
        "universe": _UNIVERSE,
        "schedule": _SCHED,
        "forward_horizon": "1d",
        "quantiles": 2,
        "dataset_version_id": "sha256:fund",
        "market_dataset_version_id": "sha256:mkt",
        "ic_methods": ("spearman", "pearson"),
    }
    kwargs.update(overrides)
    return SignalDiagnosticsSpecification(**kwargs)  # type: ignore[arg-type]


class TestValidShape:
    def test_derives_horizon_days_and_sorted_methods(self) -> None:
        spec = _spec(forward_horizon="21d", ic_methods=("spearman", "pearson"))
        assert spec.horizon_days == 21
        assert spec.sorted_ic_methods == ("pearson", "spearman")
        assert spec.spec_version == DIAGNOSTICS_SPEC_VERSION

    def test_deduplicates_and_sorts_methods_for_identity(self) -> None:
        # Same set, two spellings/orders → identical canonical form.
        a = _spec(ic_methods=("pearson", "spearman"))
        b = _spec(ic_methods=("spearman", "pearson"))
        assert a.sorted_ic_methods == b.sorted_ic_methods == ("pearson", "spearman")


class TestRejects:
    def test_empty_name(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="name"):
            _spec(name="")

    def test_empty_signal(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="signal"):
            _spec(signal="")

    def test_non_period(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="MetricPeriod"):
            _spec(period="2023-09-30")

    def test_non_universe(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="UniverseSpec"):
            _spec(universe=object())

    def test_schedule_without_surface(self) -> None:
        with pytest.raises(
            SignalDiagnosticsConfigurationError, match="RebalanceSchedule"
        ):
            _spec(schedule=object())

    def test_quantiles_below_two(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="at least 2"):
            _spec(quantiles=1)

    def test_quantiles_boolean_rejected(self) -> None:
        # ``bool`` is an ``int`` subclass; a boolean quantile count is a defect.
        with pytest.raises(
            SignalDiagnosticsConfigurationError, match="quantiles must be an int"
        ):
            _spec(quantiles=True)

    def test_bad_horizon_form(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="<n>d"):
            _spec(forward_horizon="1m")

    def test_zero_horizon(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="at least 1"):
            _spec(forward_horizon="0d")

    def test_empty_ic_methods(self) -> None:
        with pytest.raises(
            SignalDiagnosticsConfigurationError, match="at least one ic_method"
        ):
            _spec(ic_methods=())

    def test_out_of_vocab_ic_method(self) -> None:
        with pytest.raises(
            SignalDiagnosticsConfigurationError, match="closed v1 vocabulary"
        ):
            _spec(ic_methods=("kendall",))

    def test_duplicate_ic_method(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="duplicate"):
            _spec(ic_methods=("pearson", "pearson"))

    def test_empty_fundamentals_pin(self) -> None:
        with pytest.raises(
            SignalDiagnosticsConfigurationError, match="dataset_version_id"
        ):
            _spec(dataset_version_id="")

    def test_empty_market_pin(self) -> None:
        with pytest.raises(
            SignalDiagnosticsConfigurationError, match="market_dataset_version_id"
        ):
            _spec(market_dataset_version_id="")


class TestToDict:
    def test_emits_sorted_methods_and_derived_fields(self) -> None:
        payload = _spec(
            forward_horizon="5d", ic_methods=("spearman", "pearson")
        ).to_dict()
        assert payload["ic_methods"] == ["pearson", "spearman"]
        assert payload["horizon_days"] == 5
        assert payload["forward_horizon"] == "5d"
        assert payload["spec_version"] == DIAGNOSTICS_SPEC_VERSION
        # Nested identities are emitted in their own canonical serialized forms.
        assert isinstance(payload["period"], dict)
        assert isinstance(payload["universe"], dict)
        assert isinstance(payload["schedule"], dict)

    def test_to_dict_is_method_order_invariant(self) -> None:
        a = _spec(ic_methods=("pearson", "spearman")).to_dict()
        b = _spec(ic_methods=("spearman", "pearson")).to_dict()
        assert a == b

    def test_period_round_trips_through_metric_period(self) -> None:
        # The emitted period is exactly the MetricPeriod's canonical dict.
        payload = _spec().to_dict()
        assert payload["period"] == PERIOD.to_dict()
        assert isinstance(MetricPeriod, type)  # sanity: PERIOD is a MetricPeriod
