"""The declarative walk-forward request + policy and their fail-closed validation."""

from __future__ import annotations

import pytest

from quantforge.walkforward.errors import WalkForwardConfigurationError
from quantforge.walkforward.spec import (
    WINDOW_EXPANDING,
    WINDOW_ROLLING,
    TrainingPolicy,
    WalkForwardEvaluationSpecification,
)
from quantforge.walkforward.version import WALKFORWARD_SPEC_VERSION


class TestTrainingPolicyValid:
    def test_expanding_defaults(self) -> None:
        policy = TrainingPolicy(
            window=WINDOW_EXPANDING, min_train_periods=3, test_periods=1
        )
        assert policy.rolling_length is None
        assert policy.to_dict() == {
            "window": "expanding",
            "min_train_periods": 3,
            "test_periods": 1,
        }

    def test_rolling_emits_rolling_length(self) -> None:
        policy = TrainingPolicy(
            window=WINDOW_ROLLING,
            min_train_periods=3,
            test_periods=2,
            rolling_length=4,
        )
        assert policy.to_dict() == {
            "window": "rolling",
            "min_train_periods": 3,
            "test_periods": 2,
            "rolling_length": 4,
        }

    def test_round_trip(self) -> None:
        for policy in (
            TrainingPolicy(
                window=WINDOW_EXPANDING, min_train_periods=2, test_periods=1
            ),
            TrainingPolicy(
                window=WINDOW_ROLLING,
                min_train_periods=2,
                test_periods=3,
                rolling_length=5,
            ),
        ):
            assert TrainingPolicy.from_dict(policy.to_dict()) == policy


class TestTrainingPolicyFailClosed:
    def test_unknown_window_kind_raises(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            TrainingPolicy(window="sliding", min_train_periods=3, test_periods=1)

    def test_min_train_below_floor_raises(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            TrainingPolicy(window=WINDOW_EXPANDING, min_train_periods=1, test_periods=1)

    def test_min_train_bool_rejected(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            TrainingPolicy(
                window=WINDOW_EXPANDING,
                min_train_periods=True,
                test_periods=1,
            )

    def test_test_periods_below_one_raises(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            TrainingPolicy(window=WINDOW_EXPANDING, min_train_periods=3, test_periods=0)

    def test_test_periods_bool_rejected(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            TrainingPolicy(
                window=WINDOW_EXPANDING,
                min_train_periods=3,
                test_periods=True,
            )

    def test_rolling_requires_rolling_length(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            TrainingPolicy(window=WINDOW_ROLLING, min_train_periods=3, test_periods=1)

    def test_rolling_length_below_min_train_raises(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            TrainingPolicy(
                window=WINDOW_ROLLING,
                min_train_periods=4,
                test_periods=1,
                rolling_length=3,
            )

    def test_expanding_must_not_carry_rolling_length(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            TrainingPolicy(
                window=WINDOW_EXPANDING,
                min_train_periods=3,
                test_periods=1,
                rolling_length=5,
            )


class TestSpecValid:
    def test_defaults(self) -> None:
        spec = WalkForwardEvaluationSpecification(
            name="w",
            optimization_id="sha256:abc",
            training_policy=TrainingPolicy(
                window=WINDOW_EXPANDING, min_train_periods=3, test_periods=1
            ),
        )
        assert spec.spec_version == WALKFORWARD_SPEC_VERSION

    def test_to_dict_is_canonical_request(self) -> None:
        policy = TrainingPolicy(
            window=WINDOW_EXPANDING, min_train_periods=3, test_periods=1
        )
        spec = WalkForwardEvaluationSpecification(
            name="w", optimization_id="sha256:abc", training_policy=policy
        )
        assert spec.to_dict() == {
            "spec_version": WALKFORWARD_SPEC_VERSION,
            "name": "w",
            "optimization_id": "sha256:abc",
            "training_policy": policy.to_dict(),
        }


class TestSpecFailClosed:
    _POLICY = TrainingPolicy(
        window=WINDOW_EXPANDING, min_train_periods=3, test_periods=1
    )

    def test_empty_name_raises(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            WalkForwardEvaluationSpecification(
                name="", optimization_id="sha256:abc", training_policy=self._POLICY
            )

    def test_empty_optimization_id_raises(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            WalkForwardEvaluationSpecification(
                name="w", optimization_id="", training_policy=self._POLICY
            )

    def test_non_policy_raises(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            WalkForwardEvaluationSpecification(
                name="w",
                optimization_id="sha256:abc",
                training_policy="expanding",  # type: ignore[arg-type]
            )

    def test_empty_spec_version_raises(self) -> None:
        with pytest.raises(WalkForwardConfigurationError):
            WalkForwardEvaluationSpecification(
                name="w",
                optimization_id="sha256:abc",
                training_policy=self._POLICY,
                spec_version="",
            )
