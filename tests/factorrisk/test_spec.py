"""Fail-closed shape validation of the factor-risk request (§11).

The spec reads no store and no wall clock; it validates only its own internal shape.
These tests pin every construction guard and the canonical serialization, mirroring the
Phase 17/19 spec suites.
"""

from __future__ import annotations

import pytest

from quantforge.factorrisk.errors import FactorRiskConfigurationError
from quantforge.factorrisk.spec import (
    N_MAX,
    FactorRiskSpecification,
)
from quantforge.factorrisk.version import FACTORRISK_SPEC_VERSION


def _ids(n: int) -> tuple[str, ...]:
    return tuple(f"sha256:factor-{i}" for i in range(n))


class TestValid:
    def test_minimal_two_factor_request(self) -> None:
        spec = FactorRiskSpecification(name="m", factor_portfolio_ids=_ids(2))
        assert spec.factor_portfolio_ids == _ids(2)
        assert spec.periods_per_year == "1"
        assert spec.spec_version == FACTORRISK_SPEC_VERSION

    def test_to_dict_preserves_factor_order(self) -> None:
        ordered = ("sha256:b", "sha256:a", "sha256:c")
        spec = FactorRiskSpecification(name="m", factor_portfolio_ids=ordered)
        assert spec.to_dict()["factor_portfolio_ids"] == list(ordered)

    def test_periods_per_year_is_canonicalized(self) -> None:
        # Canonicalized via str(+Decimal(...)) (the sibling convention): leading zeros
        # and scientific notation collapse to one spelling, so equivalent inputs fold to
        # one identity.
        spec = FactorRiskSpecification(
            name="m", factor_portfolio_ids=_ids(2), periods_per_year="012"
        )
        assert spec.periods_per_year == "12"
        # Equivalent spellings fold to one identity.
        exponent = FactorRiskSpecification(
            name="m", factor_portfolio_ids=_ids(2), periods_per_year="1.2E1"
        )
        assert exponent.periods_per_year == spec.periods_per_year

    def test_n_max_factors_allowed(self) -> None:
        spec = FactorRiskSpecification(name="m", factor_portfolio_ids=_ids(N_MAX))
        assert len(spec.factor_portfolio_ids) == N_MAX


class TestFailClosed:
    def test_empty_name_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(name="", factor_portfolio_ids=_ids(2))

    def test_fewer_than_two_factors_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(name="m", factor_portfolio_ids=_ids(1))

    def test_more_than_n_max_factors_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(name="m", factor_portfolio_ids=_ids(N_MAX + 1))

    def test_duplicate_factor_id_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(
                name="m", factor_portfolio_ids=("sha256:a", "sha256:a")
            )

    def test_empty_factor_id_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(name="m", factor_portfolio_ids=("sha256:a", ""))

    def test_non_tuple_factor_ids_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(
                name="m",
                factor_portfolio_ids=["sha256:a", "sha256:b"],  # type: ignore[arg-type]
            )

    def test_non_decimal_periods_per_year_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(
                name="m", factor_portfolio_ids=_ids(2), periods_per_year="soon"
            )

    def test_zero_periods_per_year_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(
                name="m", factor_portfolio_ids=_ids(2), periods_per_year="0"
            )

    def test_negative_periods_per_year_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(
                name="m", factor_portfolio_ids=_ids(2), periods_per_year="-1"
            )

    def test_empty_spec_version_refused(self) -> None:
        with pytest.raises(FactorRiskConfigurationError):
            FactorRiskSpecification(
                name="m", factor_portfolio_ids=_ids(2), spec_version=""
            )
