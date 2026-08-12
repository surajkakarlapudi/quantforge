"""The declarative, content-addressed walk-forward-evaluation request (§14).

A **walk-forward-evaluation request** names exactly one sealed
:class:`~quantforge.optimization.result.PortfolioOptimization` (the optimization
*recipe* to walk out-of-sample) and a :class:`TrainingPolicy` (how to partition the
factors' complete-case-aligned return axis into ordered train->test windows). Like every
request in this project it is a frozen value whose identity is a pure content hash of
*what was declared* - the engine resolves and interprets it; it never executes caller
code (mirrors
:class:`~quantforge.optimization.spec.PortfolioOptimizationSpecification`).

Both types validate their own shape at construction (fail closed,
:class:`~quantforge.walkforward.errors.WalkForwardConfigurationError`): an empty
``name`` / ``spec_version`` / ``optimization_id``; a :class:`TrainingPolicy` whose
``window`` is outside the closed vocabulary, whose ``min_train_periods`` is below the
floor, whose ``test_periods`` is below one, or whose ``rolling_length`` is absent for a
rolling window, present for an expanding one, or below ``min_train_periods``. They read
no store and no wall clock - they cannot know whether the referenced id exists (that is
the engine's fail-closed resolution step) or how long the common axis is (that needs the
resolved records); they validate only the request's internal shape.

**Deviation from the proposal (disclosed in the locked doc §1.1).** The proposal
sketched a separate ``schedule: RebalanceSchedule`` input plus an instant->axis mapping
(its open question #3). Phase 22 instead derives the windows from the factors'
complete-case-aligned ``as_of`` axis itself, governed by the :class:`TrainingPolicy`
cadence: the factor-return series' ``as_of`` axis *already is* a rebalance calendar
(Phase 19 built the factors on a ``RebalanceSchedule``), so a second schedule + mapping
is redundant and fragile. The inherited ``schedule_id`` (from the resolved
:class:`~quantforge.factorrisk.result.FactorRiskModel`) is still folded into identity,
preserving the proposal §13 schedule-pinning intent.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.walkforward.errors import WalkForwardConfigurationError
from quantforge.walkforward.version import WALKFORWARD_SPEC_VERSION

__all__ = [
    "WINDOW_EXPANDING",
    "WINDOW_ROLLING",
    "TrainingPolicy",
    "WalkForwardEvaluationSpecification",
]

#: An **expanding** training window: every window trains on the whole aligned history up
#: to the rebalance cut (``[0, c_k)``). ``rolling_length`` must be absent.
WINDOW_EXPANDING = "expanding"

#: A **rolling** training window: every window trains on the most recent
#: ``rolling_length`` periods up to the rebalance cut (``[max(0, c_k - rolling_length),
#: c_k)``). ``rolling_length`` must be present and at least ``min_train_periods``.
WINDOW_ROLLING = "rolling"

#: The closed window-kind vocabulary. A kind outside this set is a configuration defect,
#: raised - never silently reinterpreted. Extending it later hashes distinctly via
#: ``walk_forward_id`` (the training policy is folded), so no collision can occur.
_WINDOW_KINDS = frozenset({WINDOW_EXPANDING, WINDOW_ROLLING})

#: The minimum training-window length the walk requires. A population second moment
#: needs at least two observations to carry any dispersion (the same floor Phase 20
#: enforces); below this a covariance is degenerate. The floor for
#: ``min_train_periods``.
_MIN_TRAIN_PERIODS = 2


@dataclass(frozen=True, slots=True)
class TrainingPolicy:
    """How to partition the aligned factor-return axis into train->test windows (§14).

    ``window`` is the closed-vocabulary kind (``expanding`` or ``rolling``).
    ``min_train_periods`` is the initial training length (>= 2), which also fixes the
    first rebalance cut. ``test_periods`` is the number of aligned periods per test
    window (the rebalance cadence, >= 1). ``rolling_length`` is the fixed
    training-window length for a rolling policy (>= ``min_train_periods``); it must be
    ``None`` for an expanding policy. Constructing this reads no store and no wall
    clock; it validates its own shape.
    """

    window: str
    min_train_periods: int
    test_periods: int
    rolling_length: int | None = None

    def __post_init__(self) -> None:
        if self.window not in _WINDOW_KINDS:
            raise WalkForwardConfigurationError(
                f"training window kind {self.window!r} is not supported; the v1 walk "
                f"supports exactly {sorted(_WINDOW_KINDS)!r} (fail closed rather than "
                "silently reinterpret)"
            )
        if not isinstance(self.min_train_periods, int) or isinstance(
            self.min_train_periods, bool
        ):
            raise WalkForwardConfigurationError("min_train_periods must be an int")
        if self.min_train_periods < _MIN_TRAIN_PERIODS:
            raise WalkForwardConfigurationError(
                f"min_train_periods must be at least {_MIN_TRAIN_PERIODS} (a "
                f"covariance estimate needs at least that many periods); got "
                f"{self.min_train_periods}"
            )
        if not isinstance(self.test_periods, int) or isinstance(
            self.test_periods, bool
        ):
            raise WalkForwardConfigurationError("test_periods must be an int")
        if self.test_periods < 1:
            raise WalkForwardConfigurationError(
                f"test_periods must be at least 1 (each window must realize at least "
                f"one OOS period); got {self.test_periods}"
            )
        if self.window == WINDOW_ROLLING:
            if not isinstance(self.rolling_length, int) or isinstance(
                self.rolling_length, bool
            ):
                raise WalkForwardConfigurationError(
                    "a rolling training window requires an int rolling_length"
                )
            if self.rolling_length < self.min_train_periods:
                raise WalkForwardConfigurationError(
                    f"rolling_length ({self.rolling_length}) must be at least "
                    f"min_train_periods ({self.min_train_periods}); a shorter rolling "
                    "window would train on fewer periods than the declared minimum"
                )
        elif self.rolling_length is not None:
            raise WalkForwardConfigurationError(
                "an expanding training window must not carry a rolling_length; it "
                "trains on the whole history up to each rebalance cut"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical training-policy payload (deterministic; folded into identity).

        Emits ``rolling_length`` only for a rolling policy (an expanding policy omits
        it), so the two hash distinctly and the serialized bytes are minimal.
        """
        payload: dict[str, object] = {
            "window": self.window,
            "min_train_periods": self.min_train_periods,
            "test_periods": self.test_periods,
        }
        if self.window == WINDOW_ROLLING:
            payload["rolling_length"] = self.rolling_length
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TrainingPolicy:
        """Reconstruct a policy from its :meth:`to_dict` payload (fail closed)."""
        window = raw.get("window")
        if not isinstance(window, str):
            raise ValueError("TrainingPolicy.window must be a string")
        min_train = raw.get("min_train_periods")
        if not isinstance(min_train, int) or isinstance(min_train, bool):
            raise ValueError("TrainingPolicy.min_train_periods must be an int")
        test_periods = raw.get("test_periods")
        if not isinstance(test_periods, int) or isinstance(test_periods, bool):
            raise ValueError("TrainingPolicy.test_periods must be an int")
        rolling_length_raw = raw.get("rolling_length")
        rolling_length: int | None
        if rolling_length_raw is None:
            rolling_length = None
        elif isinstance(rolling_length_raw, int) and not isinstance(
            rolling_length_raw, bool
        ):
            rolling_length = rolling_length_raw
        else:
            raise ValueError("TrainingPolicy.rolling_length must be an int or absent")
        return cls(
            window=window,
            min_train_periods=min_train,
            test_periods=test_periods,
            rolling_length=rolling_length,
        )


@dataclass(frozen=True, slots=True)
class WalkForwardEvaluationSpecification:
    """A declarative, content-addressed walk-forward-evaluation request.

    ``optimization_id`` is the sealed
    :class:`~quantforge.optimization.result.PortfolioOptimization` whose GMV recipe is
    walked out-of-sample (it transitively pins the risk model, factors, and corpus).
    ``training_policy`` governs the train->test partition of the factors' aligned return
    axis. Constructing this reads no store and no wall clock; it validates its own
    shape, exactly as the optimization / factor-risk layers refuse a misconfigured
    request.
    """

    name: str
    optimization_id: str
    training_policy: TrainingPolicy
    spec_version: str = WALKFORWARD_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise WalkForwardConfigurationError(
                "a walk-forward-evaluation request must have a non-empty name"
            )
        if not isinstance(self.optimization_id, str) or not self.optimization_id:
            raise WalkForwardConfigurationError(
                "optimization_id must be a non-empty sealed PortfolioOptimization id"
            )
        if not isinstance(self.training_policy, TrainingPolicy):
            raise WalkForwardConfigurationError(
                "training_policy must be a TrainingPolicy"
            )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise WalkForwardConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the record)."""
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "optimization_id": self.optimization_id,
            "training_policy": self.training_policy.to_dict(),
        }
