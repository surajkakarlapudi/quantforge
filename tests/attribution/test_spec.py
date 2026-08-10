"""Shape validation and canonical serialization of :class:`AttributionSpecification`.

The spec validates its own internal shape at construction (fail closed) and reads no
store — it cannot know whether the referenced ids exist or whether the subject has
enough periods (those are the engine's fail-closed steps). These tests pin the
§12 / §21-D3 validation surface: empty fields, the ``K_MAX`` ceiling, duplicate / self /
empty factor ids, decimal-convention validation, and the order-preserving canonical
payload.
"""

from __future__ import annotations

import pytest

from quantforge.attribution.errors import AttributionConfigurationError
from quantforge.attribution.spec import (
    ATTRIBUTION_SPEC_VERSION,
    K_MAX,
    AttributionSpecification,
)


def _spec(**overrides: object) -> AttributionSpecification:
    kwargs: dict[str, object] = {
        "name": "phase17",
        "subject_id": "sha256:subject",
        "factor_ids": ("sha256:f1", "sha256:f2"),
    }
    kwargs.update(overrides)
    return AttributionSpecification(**kwargs)  # type: ignore[arg-type]


class TestValidShape:
    def test_minimal_valid_spec_constructs(self) -> None:
        spec = _spec()
        assert spec.subject_id == "sha256:subject"
        assert spec.factor_ids == ("sha256:f1", "sha256:f2")
        assert spec.spec_version == ATTRIBUTION_SPEC_VERSION

    def test_frozen_and_slotted(self) -> None:
        spec = _spec()
        with pytest.raises((AttributeError, TypeError)):
            spec.name = "other"  # type: ignore[misc]
        # slots=True → no per-instance __dict__.
        assert not hasattr(spec, "__dict__")

    def test_exactly_k_max_factors_is_allowed(self) -> None:
        factors = tuple(f"sha256:f{i}" for i in range(K_MAX))
        spec = _spec(factor_ids=factors)
        assert len(spec.factor_ids) == K_MAX


class TestRejectsBadShape:
    def test_empty_name(self) -> None:
        with pytest.raises(AttributionConfigurationError, match="non-empty name"):
            _spec(name="")

    def test_empty_subject_id(self) -> None:
        with pytest.raises(AttributionConfigurationError, match="subject_id"):
            _spec(subject_id="")

    def test_empty_factor_tuple(self) -> None:
        with pytest.raises(AttributionConfigurationError, match="at least one factor"):
            _spec(factor_ids=())

    def test_too_many_factors_fails_closed(self) -> None:
        factors = tuple(f"sha256:f{i}" for i in range(K_MAX + 1))
        with pytest.raises(AttributionConfigurationError, match="at most K_MAX"):
            _spec(factor_ids=factors)

    def test_factor_equal_to_subject_rejected(self) -> None:
        with pytest.raises(AttributionConfigurationError, match="explaining itself"):
            _spec(factor_ids=("sha256:subject",))

    def test_duplicate_factor_rejected(self) -> None:
        with pytest.raises(AttributionConfigurationError, match="duplicate factor"):
            _spec(factor_ids=("sha256:f1", "sha256:f1"))

    def test_empty_factor_id_rejected(self) -> None:
        with pytest.raises(
            AttributionConfigurationError, match="non-empty backtest id"
        ):
            _spec(factor_ids=("sha256:f1", ""))


class TestConventionValidation:
    def test_negative_risk_free_rejected(self) -> None:
        with pytest.raises(AttributionConfigurationError, match="must not be negative"):
            _spec(risk_free_per_period="-0.01")

    def test_non_decimal_risk_free_rejected(self) -> None:
        with pytest.raises(AttributionConfigurationError, match="not a valid decimal"):
            _spec(risk_free_per_period="oops")

    def test_zero_periods_per_year_rejected(self) -> None:
        with pytest.raises(AttributionConfigurationError, match="strictly positive"):
            _spec(periods_per_year="0")

    def test_conventions_are_canonicalized(self) -> None:
        # Spelling-independent: trailing zeros / exponent forms collapse to one form.
        spec = _spec(risk_free_per_period="0.0100", periods_per_year="12.0")
        assert spec.risk_free_per_period == "0.01"
        assert spec.periods_per_year == "12"


class TestCanonicalPayload:
    def test_factor_order_is_preserved_not_sorted(self) -> None:
        # (f2, f1) must serialize in declared order — order is semantic.
        spec = _spec(factor_ids=("sha256:f2", "sha256:f1"))
        assert spec.to_dict()["factor_ids"] == ["sha256:f2", "sha256:f1"]

    def test_payload_shape(self) -> None:
        payload = _spec().to_dict()
        assert payload == {
            "spec_version": ATTRIBUTION_SPEC_VERSION,
            "name": "phase17",
            "subject_id": "sha256:subject",
            "factor_ids": ["sha256:f1", "sha256:f2"],
            "risk_free_per_period": "0",
            "periods_per_year": "1",
        }
