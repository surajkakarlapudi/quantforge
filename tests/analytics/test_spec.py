"""AnalyticsSpecification: fail-closed validation and set-valued confidence identity.

Covers proposal §J.1 / §L: a request validates its own shape at construction (empty
name / subject, self-benchmark, out-of-range or duplicate confidences, bad convention
decimals) and canonicalizes ``var_confidences`` to a sorted, de-duplicated set so order
and spelling never change identity.
"""

from __future__ import annotations

import pytest

from quantforge.analytics.errors import AnalyticsConfigurationError
from quantforge.analytics.spec import ANALYTICS_SPEC_VERSION, AnalyticsSpecification


class TestValidation:
    def test_empty_name_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="non-empty name"):
            AnalyticsSpecification(name="", subject_id="sha256:s")

    def test_empty_subject_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="subject_id"):
            AnalyticsSpecification(name="n", subject_id="")

    def test_self_benchmark_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="own benchmark"):
            AnalyticsSpecification(
                name="n", subject_id="sha256:s", benchmark_id="sha256:s"
            )

    def test_empty_benchmark_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="benchmark_id"):
            AnalyticsSpecification(name="n", subject_id="sha256:s", benchmark_id="")

    @pytest.mark.parametrize("bad", ["0", "1", "-0.1", "1.5", "abc", ""])
    def test_confidence_out_of_range_fails_closed(self, bad: str) -> None:
        with pytest.raises(AnalyticsConfigurationError):
            AnalyticsSpecification(
                name="n", subject_id="sha256:s", var_confidences=(bad,)
            )

    def test_duplicate_confidence_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="duplicate"):
            AnalyticsSpecification(
                name="n", subject_id="sha256:s", var_confidences=("0.95", "0.9500")
            )

    def test_empty_confidences_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="at least one"):
            AnalyticsSpecification(name="n", subject_id="sha256:s", var_confidences=())

    def test_negative_risk_free_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="risk_free_per_period"):
            AnalyticsSpecification(
                name="n", subject_id="sha256:s", risk_free_per_period="-0.01"
            )

    @pytest.mark.parametrize("bad", ["0", "-1", "abc"])
    def test_non_positive_periods_per_year_fails_closed(self, bad: str) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="periods_per_year"):
            AnalyticsSpecification(
                name="n", subject_id="sha256:s", periods_per_year=bad
            )


class TestCanonicalization:
    def test_confidences_are_sorted_and_deduplicated_by_canonical_form(self) -> None:
        spec = AnalyticsSpecification(
            name="n",
            subject_id="sha256:s",
            var_confidences=("0.99", "0.9500"),
        )
        assert spec.sorted_var_confidences == ("0.95", "0.99")

    def test_convention_decimals_are_canonicalized(self) -> None:
        spec = AnalyticsSpecification(
            name="n",
            subject_id="sha256:s",
            risk_free_per_period="0.0100",
            periods_per_year="12.0",
        )
        assert spec.risk_free_per_period == "0.01"
        assert spec.periods_per_year == "12"

    def test_zero_risk_free_is_allowed(self) -> None:
        spec = AnalyticsSpecification(
            name="n", subject_id="sha256:s", risk_free_per_period="0"
        )
        assert spec.risk_free_per_period == "0"

    def test_to_dict_emits_sorted_confidences_and_spec_version(self) -> None:
        spec = AnalyticsSpecification(
            name="n", subject_id="sha256:s", var_confidences=("0.99", "0.95")
        )
        payload = spec.to_dict()
        assert payload["var_confidences"] == ["0.95", "0.99"]
        assert payload["spec_version"] == ANALYTICS_SPEC_VERSION
        assert payload["benchmark_id"] is None


class TestIdentityInvariance:
    def test_order_and_spelling_do_not_change_the_request_payload(self) -> None:
        a = AnalyticsSpecification(
            name="n", subject_id="sha256:s", var_confidences=("0.95", "0.99")
        )
        b = AnalyticsSpecification(
            name="n", subject_id="sha256:s", var_confidences=("0.9900", "0.9500")
        )
        assert a.to_dict() == b.to_dict()
