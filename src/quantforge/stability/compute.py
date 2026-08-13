"""The pure walk-forward turnover & stability procedures over one walk (§11, §12).

Given the ordered windows of one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` - each either REALIZED
(carrying its KNOWN GMV weight vector, parsed once to ``Decimal``) or not - and the
transitions floor, :func:`analyze_stability` computes, per REALIZED window, the
stability of that window's weight vector plus its one-way turnover against the
immediately-preceding REALIZED window, and over the walk the aggregate turnover /
concentration profile. All arithmetic runs under an explicit :class:`decimal.Context`,
in exact ``Decimal``, with no RNG, no floating point, and no data-dependent iteration
(``Decimal.sqrt`` is the only transcendental, the exact method Phases 19/20/22/26 use).

Per REALIZED window (weight vector ``w`` of length ``N``, in factor order - WS-4, the
sealed weights are consumed verbatim, never re-solved):

* ``gross_leverage = Σ_i |w_i|``
* ``concentration_hhi = Σ_i w_i²``
* ``effective_breadth = 1 / concentration_hhi`` (UNDEFINED ``ZERO_CONCENTRATION`` when
  ``HHI = 0`` - defensive; a fully-invested vector has ``Σw = 1`` so ``HHI ≥ 1/N > 0``)
* ``max_abs_weight = max_i |w_i|``
* ``turnover_from_prev = ½ Σ_i |w_i - w'_i|`` where ``w'`` is the immediately-preceding
  window's weights - KNOWN iff that adjacent window is also REALIZED, else UNDEFINED
  (``NO_PRIOR_REALIZED_WINDOW``). A window straddling an UNDEFINED gap has no book to
  trade from, so its turnover is never fabricated.

Over the walk - the ``T`` windows whose ``turnover_from_prev`` is KNOWN and the ``W``
REALIZED windows:

* ``mean_turnover`` / ``turnover_dispersion`` (population) / ``max_turnover`` /
  ``min_turnover`` - every cell UNDEFINED (``NO_TRANSITIONS``) when ``T = 0``.
* ``mean_gross_leverage`` / ``max_gross_leverage`` / ``mean_concentration_hhi`` /
  ``mean_effective_breadth`` - every cell UNDEFINED (``NO_REALIZED_WINDOWS``) when
  ``W = 0`` (defensive); ``mean_effective_breadth`` UNDEFINED (``ZERO_CONCENTRATION``)
  if any window's ``HHI = 0``.

``stability_status`` is ``STABLE`` iff ``T >= min_transitions``, else ``UNDEFINED``
(``INSUFFICIENT_TRANSITIONS``) - the record seals either way (WS-3).

Pure: a function of the ordered windows, the floor, and the context - no wall clock, no
RNG, no iteration-order dependence. The per-window values are computed once and reused
for every aggregate, so a cell and the aggregates over it can never disagree.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge.stability.model import (
    StabilityStat,
    StabilityStatus,
    StabilityUndefinedReason,
)

__all__ = [
    "SourceWindow",
    "StabilityComputation",
    "StabilitySummaryComputation",
    "WindowStabilityMetrics",
    "analyze_stability",
]

_ZERO = Decimal(0)
_TWO = Decimal(2)


@dataclass(frozen=True, slots=True)
class SourceWindow:
    """One source window's REALIZED-status + parsed weight vector (WS-2/WS-4).

    ``index`` is the source window's index; ``realized`` whether the source sealed it
    REALIZED; ``weights`` its per-factor GMV weights parsed once from the source's
    canonical decimal strings (a non-empty vector in factor order when ``realized``, an
    empty tuple otherwise). The engine builds these in source order, so adjacency
    here is schedule adjacency.
    """

    index: int
    realized: bool
    weights: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class WindowStabilityMetrics:
    """The computed per-window stability metrics (§11).

    ``gross_leverage`` / ``concentration_hhi`` / ``max_abs_weight`` are canonical
    decimal strings (always defined for a non-empty weight vector);
    ``effective_breadth`` and ``turnover_from_prev`` are UNDEFINED-preserving cells.
    Aligned index-for-index to the REALIZED windows passed to
    :func:`analyze_stability`.
    """

    index: int
    gross_leverage: str
    concentration_hhi: str
    effective_breadth: StabilityStat
    max_abs_weight: str
    turnover_from_prev: StabilityStat


@dataclass(frozen=True, slots=True)
class StabilitySummaryComputation:
    """The aggregate turnover / concentration statistics, as UNDEFINED cells (§11)."""

    mean_turnover: StabilityStat
    turnover_dispersion: StabilityStat
    max_turnover: StabilityStat
    min_turnover: StabilityStat
    mean_gross_leverage: StabilityStat
    max_gross_leverage: StabilityStat
    mean_concentration_hhi: StabilityStat
    mean_effective_breadth: StabilityStat
    stability_status: StabilityStatus
    status_reason: StabilityUndefinedReason | None


@dataclass(frozen=True, slots=True)
class StabilityComputation:
    """The full pure result: per-window metrics + the aggregate summary (§11)."""

    windows: tuple[WindowStabilityMetrics, ...]
    summary: StabilitySummaryComputation


def analyze_stability(
    windows: Sequence[SourceWindow],
    *,
    min_transitions: int,
    context: Context,
) -> StabilityComputation:
    """Compute per-window stability + aggregate turnover/concentration (§11, WS-3/4/5).

    ``windows`` are the source's windows in source (schedule) order, each REALIZED (with
    a non-empty weight vector) or not; ``min_transitions`` is the floor below which
    ``stability_status`` is UNDEFINED; ``context`` is the pinned decimal context.
    Deterministic: identical inputs yield identical ``Decimal`` values on any machine.
    A window with no adjacent REALIZED predecessor yields an UNDEFINED
    ``turnover_from_prev`` (never a fabricated trade); a walk with no realized-adjacent
    transitions yields every turnover aggregate UNDEFINED - never divide-by-zero (WS-3).
    """
    with localcontext(context):
        metrics: list[WindowStabilityMetrics] = []
        turnovers: list[Decimal] = []
        gross_leverages: list[Decimal] = []
        hhis: list[Decimal] = []
        breadths: list[Decimal] = []
        any_breadth_undefined = False
        prev_weights: tuple[Decimal, ...] | None = None
        for window in windows:
            if not window.realized:
                # An UNDEFINED window breaks the weight path: the next REALIZED window
                # has no adjacent book to trade from (WS-3).
                prev_weights = None
                continue
            weights = window.weights
            gross_leverage = sum((abs(w) for w in weights), _ZERO)
            concentration_hhi = sum((w * w for w in weights), _ZERO)
            max_abs_weight = max(abs(w) for w in weights)

            if concentration_hhi == _ZERO:
                # Defensive / structurally unreachable: a fully-invested GMV vector has
                # Σw = 1 so HHI >= 1/N > 0. Never a divide-by-zero.
                effective_breadth = StabilityStat.undefined(
                    StabilityUndefinedReason.ZERO_CONCENTRATION
                )
                any_breadth_undefined = True
            else:
                breadth = Decimal(1) / concentration_hhi
                effective_breadth = StabilityStat.known(str(+breadth))
                breadths.append(breadth)

            if prev_weights is not None:
                turnover = (
                    sum(
                        (
                            abs(a - b)
                            for a, b in zip(weights, prev_weights, strict=True)
                        ),
                        _ZERO,
                    )
                    / _TWO
                )
                turnover_from_prev = StabilityStat.known(str(+turnover))
                turnovers.append(turnover)
            else:
                turnover_from_prev = StabilityStat.undefined(
                    StabilityUndefinedReason.NO_PRIOR_REALIZED_WINDOW
                )

            metrics.append(
                WindowStabilityMetrics(
                    index=window.index,
                    gross_leverage=str(+gross_leverage),
                    concentration_hhi=str(+concentration_hhi),
                    effective_breadth=effective_breadth,
                    max_abs_weight=str(+max_abs_weight),
                    turnover_from_prev=turnover_from_prev,
                )
            )
            gross_leverages.append(gross_leverage)
            hhis.append(concentration_hhi)
            prev_weights = weights

        summary = _summarize(
            turnovers=turnovers,
            gross_leverages=gross_leverages,
            hhis=hhis,
            breadths=breadths,
            any_breadth_undefined=any_breadth_undefined,
            min_transitions=min_transitions,
        )
    return StabilityComputation(windows=tuple(metrics), summary=summary)


def _summarize(
    *,
    turnovers: list[Decimal],
    gross_leverages: list[Decimal],
    hhis: list[Decimal],
    breadths: list[Decimal],
    any_breadth_undefined: bool,
    min_transitions: int,
) -> StabilitySummaryComputation:
    """Aggregate the per-window metrics (called inside the pinned context)."""
    turnover_cells = _turnover_aggregates(turnovers)
    concentration_cells = _concentration_aggregates(
        gross_leverages=gross_leverages,
        hhis=hhis,
        breadths=breadths,
        any_breadth_undefined=any_breadth_undefined,
    )

    t = len(turnovers)
    stable = t >= min_transitions
    status = StabilityStatus.STABLE if stable else StabilityStatus.UNDEFINED
    status_reason = (
        None if stable else StabilityUndefinedReason.INSUFFICIENT_TRANSITIONS
    )
    return StabilitySummaryComputation(
        mean_turnover=turnover_cells[0],
        turnover_dispersion=turnover_cells[1],
        max_turnover=turnover_cells[2],
        min_turnover=turnover_cells[3],
        mean_gross_leverage=concentration_cells[0],
        max_gross_leverage=concentration_cells[1],
        mean_concentration_hhi=concentration_cells[2],
        mean_effective_breadth=concentration_cells[3],
        stability_status=status,
        status_reason=status_reason,
    )


def _turnover_aggregates(
    turnovers: list[Decimal],
) -> tuple[StabilityStat, StabilityStat, StabilityStat, StabilityStat]:
    """``(mean, dispersion, max, min)`` over the KNOWN turnovers, UNDEFINED if none."""
    t = len(turnovers)
    if t == 0:
        undefined = StabilityStat.undefined(StabilityUndefinedReason.NO_TRANSITIONS)
        return undefined, undefined, undefined, undefined
    t_dec = Decimal(t)
    mean = sum(turnovers, _ZERO) / t_dec
    dispersion_sq = sum(((x - mean) ** 2 for x in turnovers), _ZERO) / t_dec
    dispersion = dispersion_sq.sqrt()
    return (
        StabilityStat.known(str(+mean)),
        StabilityStat.known(str(+dispersion)),
        StabilityStat.known(str(+max(turnovers))),
        StabilityStat.known(str(+min(turnovers))),
    )


def _concentration_aggregates(
    *,
    gross_leverages: list[Decimal],
    hhis: list[Decimal],
    breadths: list[Decimal],
    any_breadth_undefined: bool,
) -> tuple[StabilityStat, StabilityStat, StabilityStat, StabilityStat]:
    """``(mean_gl, max_gl, mean_hhi, mean_breadth)`` over REALIZED windows.

    Every cell UNDEFINED (``NO_REALIZED_WINDOWS``) when there are no realized windows -
    defensive, never a divide-by-zero; ``mean_effective_breadth`` UNDEFINED
    (``ZERO_CONCENTRATION``) if any window's ``HHI`` was zero, so a defined mean
    is never contaminated by a silently dropped window.
    """
    w = len(gross_leverages)
    if w == 0:
        undefined = StabilityStat.undefined(
            StabilityUndefinedReason.NO_REALIZED_WINDOWS
        )
        return undefined, undefined, undefined, undefined
    w_dec = Decimal(w)
    mean_gl = sum(gross_leverages, _ZERO) / w_dec
    max_gl = max(gross_leverages)
    mean_hhi = sum(hhis, _ZERO) / w_dec
    if any_breadth_undefined:
        mean_breadth = StabilityStat.undefined(
            StabilityUndefinedReason.ZERO_CONCENTRATION
        )
    else:
        mean_breadth = StabilityStat.known(str(+(sum(breadths, _ZERO) / w_dec)))
    return (
        StabilityStat.known(str(+mean_gl)),
        StabilityStat.known(str(+max_gl)),
        StabilityStat.known(str(+mean_hhi)),
        mean_breadth,
    )
