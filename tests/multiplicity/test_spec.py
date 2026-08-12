"""The declarative multiplicity-correction request (§14): validation +
canonicalization."""

from __future__ import annotations

import pytest

from quantforge.multiplicity.errors import MultiplicityConfigurationError
from quantforge.multiplicity.model import CorrectionMethod
from quantforge.multiplicity.spec import (
    DEFAULT_METHODS,
    MultipleComparisonSpecification,
)


def _spec(**overrides: object) -> MultipleComparisonSpecification:
    base: dict[str, object] = {
        "name": "corr",
        "source_strategy_comparison_id": "sha256:src",
        "alpha": "0.05",
    }
    base.update(overrides)
    return MultipleComparisonSpecification(**base)  # type: ignore[arg-type]


def test_defaults_are_holm_and_yekutieli() -> None:
    assert DEFAULT_METHODS == (
        CorrectionMethod.HOLM,
        CorrectionMethod.BENJAMINI_YEKUTIELI,
    )
    assert _spec().methods == DEFAULT_METHODS


def test_alpha_is_canonicalized() -> None:
    # Trailing-zero variants collapse to one canonical string (so one id).
    assert _spec(alpha="0.05").alpha == _spec(alpha="0.050").alpha == "0.05"


def test_to_dict_preserves_method_order() -> None:
    spec = _spec(
        methods=(
            CorrectionMethod.BENJAMINI_YEKUTIELI,
            CorrectionMethod.HOLM,
        )
    )
    assert spec.to_dict()["methods"] == ["benjamini_yekutieli", "holm"]


@pytest.mark.parametrize("bad", ["", "abc", "nan", "0", "1", "-0.1", "1.5"])
def test_alpha_must_be_a_decimal_strictly_in_open_unit_interval(bad: str) -> None:
    with pytest.raises(MultiplicityConfigurationError):
        _spec(alpha=bad)


def test_empty_name_is_rejected() -> None:
    with pytest.raises(MultiplicityConfigurationError):
        _spec(name="")


def test_empty_source_id_is_rejected() -> None:
    with pytest.raises(MultiplicityConfigurationError):
        _spec(source_strategy_comparison_id="")


def test_empty_method_tuple_is_rejected() -> None:
    with pytest.raises(MultiplicityConfigurationError):
        _spec(methods=())


def test_duplicate_method_is_rejected() -> None:
    with pytest.raises(MultiplicityConfigurationError):
        _spec(methods=(CorrectionMethod.HOLM, CorrectionMethod.HOLM))


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(MultiplicityConfigurationError):
        _spec(spec_version="")


def test_round_trip_re_validation_is_stable() -> None:
    # Re-constructing from an already-canonical alpha is idempotent (no drift).
    spec = _spec(alpha="0.050")
    again = MultipleComparisonSpecification(
        name=spec.name,
        source_strategy_comparison_id=spec.source_strategy_comparison_id,
        alpha=spec.alpha,
        methods=spec.methods,
    )
    assert again.alpha == spec.alpha == "0.05"
