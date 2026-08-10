"""Shape-validation and serialization tests for the declarative request (§3.1).

The specification validates its own internal shape at construction (fail closed) and
never reads a store or the wall clock; these tests pin exactly which shapes it accepts
and refuses, and that its canonical payload / identity descriptors are order-preserving.
"""

from __future__ import annotations

import pytest

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.crosssection.errors import CrossSectionConfigurationError
from quantforge.crosssection.spec import (
    CROSSSECTION_SPEC_VERSION,
    K_MAX,
    CrossSectionalRegressionSpecification,
    FactorSpec,
)
from quantforge.metrics.model import MetricPeriod
from quantforge.universe.filters import ExplicitCompanyFilter
from quantforge.universe.specification import UniverseSpecification

PERIOD = MetricPeriod.instant("2023-09-30")
PERIOD_OTHER = MetricPeriod.instant("2022-09-30")


def _universe() -> UniverseSpecification:
    return UniverseSpecification(
        name="u", filters=(ExplicitCompanyFilter(identifiers=("123", "456")),)
    )


def _schedule() -> RebalanceSchedule:
    return RebalanceSchedule.of(["2024-01-15T00:00:00Z", "2024-02-15T00:00:00Z"])


def _spec(**overrides: object) -> CrossSectionalRegressionSpecification:
    kwargs: dict[str, object] = {
        "name": "x",
        "factors": (
            FactorSpec("current_ratio", PERIOD),
            FactorSpec("quick_ratio", PERIOD),
        ),
        "universe": _universe(),
        "schedule": _schedule(),
        "forward_horizon": "1d",
        "dataset_version_id": "fund",
        "market_dataset_version_id": "mkt",
    }
    kwargs.update(overrides)
    return CrossSectionalRegressionSpecification(**kwargs)  # type: ignore[arg-type]


# -- valid construction ------------------------------------------------------


def test_valid_spec_derives_horizon_and_defaults() -> None:
    spec = _spec()
    assert spec.horizon_days == 1
    assert spec.include_intercept is True
    assert spec.spec_version == CROSSSECTION_SPEC_VERSION


def test_factor_descriptors_preserve_declared_order() -> None:
    spec = _spec(
        factors=(
            FactorSpec("quick_ratio", PERIOD),
            FactorSpec("current_ratio", PERIOD),
        )
    )
    assert spec.factor_descriptors == [
        ["quick_ratio", PERIOD.period_key],
        ["current_ratio", PERIOD.period_key],
    ]


def test_factor_label_is_display_only_not_in_descriptor() -> None:
    labelled = FactorSpec("current_ratio", PERIOD, label="Liquidity")
    plain = FactorSpec("current_ratio", PERIOD)
    assert labelled.descriptor == plain.descriptor


def test_to_dict_is_order_preserving_and_round_numbered() -> None:
    spec = _spec()
    payload = spec.to_dict()
    factors = payload["factors"]
    assert isinstance(factors, list)
    assert [f["metric_key"] for f in factors] == [
        "current_ratio",
        "quick_ratio",
    ]
    assert payload["include_intercept"] is True
    assert payload["horizon_days"] == 1


# -- rejected shapes ---------------------------------------------------------


def test_empty_name_rejected() -> None:
    with pytest.raises(CrossSectionConfigurationError):
        _spec(name="")


def test_no_factors_rejected() -> None:
    with pytest.raises(CrossSectionConfigurationError):
        _spec(factors=())


def test_too_many_factors_rejected() -> None:
    factors = tuple(
        FactorSpec("current_ratio", MetricPeriod.instant(f"20{10 + i:02d}-09-30"))
        for i in range(K_MAX + 1)
    )
    with pytest.raises(CrossSectionConfigurationError):
        _spec(factors=factors)


def test_duplicate_factor_same_period_rejected() -> None:
    with pytest.raises(CrossSectionConfigurationError):
        _spec(
            factors=(
                FactorSpec("current_ratio", PERIOD),
                FactorSpec("current_ratio", PERIOD),
            )
        )


def test_same_metric_different_period_is_allowed() -> None:
    spec = _spec(
        factors=(
            FactorSpec("current_ratio", PERIOD),
            FactorSpec("current_ratio", PERIOD_OTHER),
        )
    )
    assert len(spec.factors) == 2


def test_empty_metric_key_rejected() -> None:
    with pytest.raises(CrossSectionConfigurationError):
        _spec(factors=(FactorSpec("", PERIOD),))


def test_non_bool_intercept_rejected() -> None:
    with pytest.raises(CrossSectionConfigurationError):
        _spec(include_intercept=1)


def test_bad_horizon_rejected() -> None:
    with pytest.raises(CrossSectionConfigurationError):
        _spec(forward_horizon="1w")


def test_zero_horizon_rejected() -> None:
    with pytest.raises(CrossSectionConfigurationError):
        _spec(forward_horizon="0d")


def test_empty_corpus_pin_rejected() -> None:
    with pytest.raises(CrossSectionConfigurationError):
        _spec(dataset_version_id="")
    with pytest.raises(CrossSectionConfigurationError):
        _spec(market_dataset_version_id="")


def test_intercept_flag_is_folded_into_two_distinct_shapes() -> None:
    on = _spec(include_intercept=True)
    off = _spec(include_intercept=False)
    assert on.to_dict()["include_intercept"] != off.to_dict()["include_intercept"]
