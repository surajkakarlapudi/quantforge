"""Shape-validation and serialization tests for the declarative request (§5.2).

The specification validates its own internal shape at construction (fail closed) and
never reads a store or the wall clock; these tests pin exactly which shapes it accepts
and refuses, that it derives its horizon-day count and canonicalizes its annualization
decimals, and that its canonical payload is order- and value-preserving.
"""

from __future__ import annotations

import pytest

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.factorportfolio.errors import FactorPortfolioConfigurationError
from quantforge.factorportfolio.spec import (
    WEIGHTING_EQUAL,
    FactorPortfolioSpecification,
)
from quantforge.factorportfolio.version import FACTORPORTFOLIO_SPEC_VERSION
from quantforge.metrics.model import MetricPeriod
from quantforge.universe.filters import ExplicitCompanyFilter
from quantforge.universe.specification import UniverseSpecification

PERIOD = MetricPeriod.instant("2023-09-30")


def _universe() -> UniverseSpecification:
    return UniverseSpecification(
        name="u", filters=(ExplicitCompanyFilter(identifiers=("123", "456")),)
    )


def _schedule() -> RebalanceSchedule:
    return RebalanceSchedule.of(["2024-01-15T00:00:00Z", "2024-02-15T00:00:00Z"])


def _spec(**overrides: object) -> FactorPortfolioSpecification:
    kwargs: dict[str, object] = {
        "name": "x",
        "signal": "current_ratio",
        "period": PERIOD,
        "universe": _universe(),
        "schedule": _schedule(),
        "forward_horizon": "1d",
        "quantiles": 2,
        "dataset_version_id": "fund",
        "market_dataset_version_id": "mkt",
    }
    kwargs.update(overrides)
    return FactorPortfolioSpecification(**kwargs)  # type: ignore[arg-type]


# -- valid construction ------------------------------------------------------


def test_valid_spec_derives_horizon_and_defaults() -> None:
    spec = _spec()
    assert spec.horizon_days == 1
    assert spec.weighting == WEIGHTING_EQUAL
    assert spec.risk_free_per_period == "0"
    assert spec.periods_per_year == "1"
    assert spec.spec_version == FACTORPORTFOLIO_SPEC_VERSION


def test_multi_day_horizon_parses() -> None:
    assert _spec(forward_horizon="21d").horizon_days == 21


def test_annualization_decimals_canonicalized() -> None:
    # A leading ``+`` and an exponent spelling collapse to their canonical decimal form
    # via ``str(+Decimal(raw))``, so two spellings of the same number yield one id.
    spec = _spec(risk_free_per_period="+0.01", periods_per_year="2.52E2")
    assert spec.risk_free_per_period == "0.01"
    assert spec.periods_per_year == "252"


def test_to_dict_is_order_preserving_and_round_numbered() -> None:
    spec = _spec(quantiles=5, periods_per_year="252")
    payload = spec.to_dict()
    assert payload["signal"] == "current_ratio"
    assert payload["horizon_days"] == 1
    assert payload["quantiles"] == 5
    assert payload["weighting"] == "equal"
    assert payload["periods_per_year"] == "252"
    assert payload["period"] == PERIOD.to_dict()


# -- rejected shapes ---------------------------------------------------------


def test_empty_name_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(name="")


def test_empty_signal_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(signal="")


def test_non_metric_period_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(period="2023-09-30")


def test_non_universe_specification_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(universe=object())


def test_quantiles_below_two_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(quantiles=1)


def test_non_int_quantiles_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(quantiles=2.0)


def test_bool_quantiles_rejected() -> None:
    # ``bool`` is a subclass of ``int``; ``True`` must never masquerade as Q.
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(quantiles=True)


def test_unknown_weighting_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(weighting="value")


def test_bad_horizon_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(forward_horizon="1w")


def test_zero_horizon_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(forward_horizon="0d")


def test_non_decimal_risk_free_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(risk_free_per_period="oops")


def test_non_finite_periods_per_year_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(periods_per_year="Infinity")


def test_empty_corpus_pin_rejected() -> None:
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(dataset_version_id="")
    with pytest.raises(FactorPortfolioConfigurationError):
        _spec(market_dataset_version_id="")
