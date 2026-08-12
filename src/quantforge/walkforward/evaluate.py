"""Pure, deterministic per-window re-estimate, re-solve, and OOS realization (§12).

Everything Phase 22 computes for a single train->test window, in stdlib
:class:`~decimal.Decimal` under the engine's pinned context - no numpy, no float, no
wall-clock, no RNG. Phase 22 introduces **no new numerical formula**: it *composes* two
pinned pure methods from the layers below over each window's training span -

* :func:`quantforge.factorrisk.stats.estimate_moments` (Phase 20) re-estimates the ``N x
  N`` per-period covariance over the training returns, and
* :func:`quantforge.optimization.solve.solve_min_variance` (Phase 21) re-solves the
  fully-invested GMV weights over that covariance -

then applies those weights to the window's **strictly-subsequent** test returns (WF-2,
no look-ahead) to realize the out-of-sample (OOS) return of each test period, and
computes the window's predicted (in-sample, from the training covariance) and realized
(population variance of the OOS test returns) variance.

This module reads no store and holds no state; the engine resolves, verifies, aligns,
and partitions the inputs and hands each window's aligned matrix here. A window that is
genuinely undefined for the data - a training covariance that is not positive-definite,
so its GMV does not exist - is returned as a first-class UNDEFINED
:class:`~quantforge.walkforward.model.WindowStatus` window carrying
``SINGULAR_TRAINING_COVARIANCE``, **never** a divide-by-zero, a fabricated ``0``, a
repaired / regularized matrix, or a silently dropped window (§15, WF-4). The
``INSUFFICIENT_TRAINING`` / ``EMPTY_TEST_WINDOW`` guards are defensive: the axis-derived
window generator (:func:`quantforge.walkforward.windows.build_windows`) cannot produce a
window that trips them, so they are retained as fail-closed backstops - the direct
analogue of the solve layer's non-positive-``s`` guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge.factorrisk.model import FactorRiskStatus
from quantforge.factorrisk.stats import MomentEstimate, estimate_moments
from quantforge.optimization.model import OptimizationStatus
from quantforge.optimization.solve import solve_min_variance
from quantforge.walkforward.errors import WalkForwardConsistencyError
from quantforge.walkforward.model import (
    StatValue,
    WalkForwardUndefinedReason,
    WindowStatus,
)
from quantforge.walkforward.windows import WindowSpec

__all__ = [
    "WindowEvaluation",
    "evaluate_window",
]

_ZERO = Decimal(0)

#: The defensive minimum training-window length (mirrors the spec floor). Structurally
#: guaranteed by the window generator; re-checked here fail-closed (WF-4).
_MIN_TRAIN_PERIODS = 2


@dataclass(frozen=True, slots=True)
class WindowEvaluation:
    """The computed result of one train->test window (§12, WF-4).

    ``status`` is ``REALIZED`` when the training GMV existed and OOS returns were
    realized, else ``UNDEFINED`` with ``reason``. ``weights`` are the per-factor
    training GMV weights in factor order (KNOWN when REALIZED, empty when UNDEFINED -
    never a partial vector). ``predicted_variance`` is the in-sample ``wᵀΣw`` over the
    training covariance; ``realized_variance`` the population variance of the OOS test
    returns (KNOWN when at least two test periods, ``SINGLE_VALID_PERIOD`` when exactly
    one). ``oos_returns`` are the realized OOS return decimal strings in test-date order
    (empty when UNDEFINED).
    """

    window: WindowSpec
    status: WindowStatus
    reason: WalkForwardUndefinedReason | None
    weights: tuple[StatValue, ...]
    predicted_variance: StatValue
    realized_variance: StatValue
    oos_returns: tuple[str, ...]


def _undefined(
    window: WindowSpec, reason: WalkForwardUndefinedReason
) -> WindowEvaluation:
    """An UNDEFINED window carrying why - no weights, no returns (WF-4)."""
    undef = StatValue.undefined(reason)
    return WindowEvaluation(
        window=window,
        status=WindowStatus.UNDEFINED,
        reason=reason,
        weights=(),
        predicted_variance=undef,
        realized_variance=undef,
        oos_returns=(),
    )


def _reconstruct(moment: MomentEstimate, n: int) -> list[list[str]]:
    """Rebuild the full symmetric ``N x N`` per-period covariance from the estimate.

    :func:`~quantforge.factorrisk.stats.estimate_moments` returns only the **upper
    triangle** (``i <= j``) of the per-period covariance, each cell KNOWN by
    construction. This fills a dense ``N x N`` matrix of decimal strings, mirroring
    ``Σ[i][j]`` into ``Σ[j][i]``. It re-verifies fail-closed (never trusting the
    estimate blindly): every index is in range with ``i <= j``, no position is missing
    or set twice, and every used cell is KNOWN with a string value. The matrix is
    **never** repaired or regularized - a non-positive-definite ``Σ`` is the solve
    layer's UNDEFINED concern (WF-4).
    """
    matrix: list[list[str | None]] = [[None] * n for _ in range(n)]
    for cell in moment.covariance:
        i, j = cell.i, cell.j
        if not (0 <= i < n and 0 <= j < n) or i > j:
            raise WalkForwardConsistencyError(
                f"re-estimated covariance cell ({i}, {j}) is not a valid "
                f"upper-triangle index for a {n}-factor window (fail closed)"
            )
        if cell.value.status is not FactorRiskStatus.KNOWN:
            raise WalkForwardConsistencyError(
                f"re-estimated covariance cell ({i}, {j}) is UNDEFINED; the per-period "
                "covariance cells must all be KNOWN by construction (fail closed)"
            )
        value = cell.value.value
        if not isinstance(value, str):
            raise WalkForwardConsistencyError(
                f"re-estimated covariance cell ({i}, {j}) carries a non-string value "
                "(fail closed)"
            )
        if matrix[i][j] is not None:
            raise WalkForwardConsistencyError(
                f"re-estimated covariance cell ({i}, {j}) appears more than once "
                "(fail closed)"
            )
        matrix[i][j] = value
        matrix[j][i] = value

    for i in range(n):
        for j in range(n):
            if matrix[i][j] is None:
                raise WalkForwardConsistencyError(
                    f"re-estimated covariance cell ({min(i, j)}, {max(i, j)}) is "
                    f"missing; the estimate does not fully cover the {n}x{n} matrix "
                    "(fail closed)"
                )
    return [[_require(matrix[i][j]) for j in range(n)] for i in range(n)]


def _require(value: str | None) -> str:
    """Assert a covariance cell was filled - a programming-bug backstop, never data."""
    assert value is not None  # guaranteed by the full-coverage check above
    return value


def evaluate_window(
    series: list[list[str]],
    window: WindowSpec,
    *,
    n: int,
    periods_per_year: str,
    context: Context,
) -> WindowEvaluation:
    """Re-estimate, re-solve, and realize the OOS returns for one window (§12, WF-2).

    ``series`` is the complete-case-aligned matrix (``series[i]`` is factor ``i``'s
    KNOWN per-period returns over the whole common axis, in shared date order);
    ``window`` the train->test index ranges; ``n`` the factor count;
    ``periods_per_year`` the inherited annualization convention. Every arithmetic step
    runs under the pinned ``context``.

    Returns a :class:`WindowEvaluation`: ``REALIZED`` with the training GMV weights, the
    predicted / realized variance, and the OOS test returns when the training covariance
    is positive-definite; otherwise ``UNDEFINED`` ``SINGULAR_TRAINING_COVARIANCE``
    (never a divide-by-zero). The defensive ``INSUFFICIENT_TRAINING`` /
    ``EMPTY_TEST_WINDOW`` branches cannot be reached from a generator-produced window.
    """
    if window.train_length < _MIN_TRAIN_PERIODS:  # defensive; generator guarantees min
        return _undefined(window, WalkForwardUndefinedReason.INSUFFICIENT_TRAINING)
    if window.test_length < 1:  # defensive; generator guarantees a non-empty test span
        return _undefined(window, WalkForwardUndefinedReason.EMPTY_TEST_WINDOW)

    train_series = [row[window.train_start : window.train_end] for row in series]
    moment = estimate_moments(
        train_series, periods_per_year=periods_per_year, context=context
    )
    sigma = _reconstruct(moment, n)
    solution = solve_min_variance(sigma, context=context)
    if solution.status is not OptimizationStatus.OPTIMAL:
        # A non-positive-definite training covariance: the window's GMV does not exist.
        return _undefined(
            window, WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE
        )

    with localcontext(context):
        weights_dec = [_known_decimal(w.value) for w in solution.weights]
        oos_values: list[Decimal] = []
        for t in range(window.test_start, window.test_end):
            realized = _ZERO
            for i in range(n):
                realized += weights_dec[i] * Decimal(series[i][t])
            oos_values.append(+realized)
        oos_returns = tuple(str(v) for v in oos_values)

        realized_variance = _realized_variance(oos_values, context)

    predicted_value = solution.variance.value
    assert predicted_value is not None  # OPTIMAL solution has a KNOWN variance
    weights = tuple(_known_decimal_cell(w.value) for w in solution.weights)
    return WindowEvaluation(
        window=window,
        status=WindowStatus.REALIZED,
        reason=None,
        weights=weights,
        predicted_variance=StatValue.known(predicted_value),
        realized_variance=realized_variance,
        oos_returns=oos_returns,
    )


def _realized_variance(values: list[Decimal], context: Context) -> StatValue:
    """The population variance of a window's OOS returns as a :class:`StatValue`.

    KNOWN when at least two test periods (``(1/M) Σ (r_t - mean)²``); a single test
    period has no dispersion, so ``SINGLE_VALID_PERIOD`` (never a divide-by-zero). The
    generator guarantees at least one test period, so the empty case cannot arise.
    """
    m = len(values)
    if m < 2:
        return StatValue.undefined(WalkForwardUndefinedReason.SINGLE_VALID_PERIOD)
    mean = sum(values, _ZERO) / Decimal(m)
    variance = sum(((v - mean) * (v - mean) for v in values), _ZERO) / Decimal(m)
    return StatValue.known(str(+variance))


def _known_decimal(value: str | None) -> Decimal:
    """Parse a KNOWN GMV weight's decimal string (solve-layer invariant, never data)."""
    assert value is not None  # an OPTIMAL solution's weights are all KNOWN
    return Decimal(value)


def _known_decimal_cell(value: str | None) -> StatValue:
    """Wrap a KNOWN GMV weight string into a walk-forward :class:`StatValue`."""
    assert value is not None  # an OPTIMAL solution's weights are all KNOWN
    return StatValue.known(value)
