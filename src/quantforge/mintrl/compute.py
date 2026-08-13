"""Pure, deterministic minimum-track-record-length arithmetic (§11, §12, Bailey-LdP).

Given each evaluable trial's out-of-sample moments (per-period Sharpe ``SR``, skew
``gamma₃``, non-excess kurtosis ``gamma₄``) and OOS period count ``n`` - the engine has
already parsed the KNOWN moments and excluded every source-UNDEFINED trial (MT-3) - plus
a confidence ``alpha`` and a benchmark Sharpe ``SR*``, :func:`evaluate_mintrl` computes,
per trial, the minimum track-record length and, over the family, the aggregate MinTRL
profile. All arithmetic runs under an explicit :class:`decimal.Context`, in exact
``Decimal``, with no RNG, no floating point, and no data-dependent iteration; the only
elementary transcendental is ``Decimal.sqrt`` (dispersion) and the only quantile is the
*reused* deterministic :func:`~quantforge._stats.normal.standard_normal_ppf` (the fixed
240-step bisection - bounded and terminating, **not** a convergence-tolerance loop),
evaluated once for ``Z_alpha``.

Per evaluable trial (MT-4 - the sealed moments are consumed verbatim, never recomputed):

* ``V = 1 - gamma₃·SR + ((gamma₄-1)/4)·SR²``
  (the Phase-23 PSR estimator variance).
* If ``V ≤ 0`` the MinTRL is UNDEFINED ``DEGENERATE_SHARPE_ESTIMATOR`` (never a
  ``√`` of a non-positive); else if ``SR ≤ SR*`` it is UNDEFINED
  ``SHARPE_NOT_ABOVE_BENCHMARK`` (never a divide-by-zero); else

      ``MinTRL = 1 + V·(Z_alpha/(SR - SR*))²``   and
      ``excess_length = n - MinTRL``.

  ``n ≥ MinTRL`` marks the observed record as already sufficient.

Over the family of ``K`` **determined** trials (those with a KNOWN MinTRL; KNOWN iff
``K ≥ 1``, every cell UNDEFINED ``NO_DETERMINED_TRIALS`` when ``K = 0`` - never a
divide-by-zero):

* ``mean_min_trl = (Σ MinTRLₖ) / K``
* ``min_trl_dispersion = √( Σ (MinTRLₖ - mean)² / K )`` (population)
* ``max_min_trl`` / ``min_min_trl``
* ``sufficient_frequency = |{k : nₖ ≥ MinTRLₖ}| / K``

``mintrl_status`` is ``EVALUATED`` iff ``K ≥ min_determined``, else ``UNDEFINED``
(``INSUFFICIENT_DETERMINED_TRIALS``) - the record seals either way (MT-3).

Pure: a function of the evaluable trials, the confidence, the benchmark, the floor, and
the context - no wall clock, no RNG, no iteration-order dependence. The per-trial MinTRL
values are computed once and reused for every aggregate, so a cell's length and the
aggregates over it can never disagree.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge._stats.normal import standard_normal_ppf
from quantforge.mintrl.model import (
    MinTrlStat,
    MinTrlStatus,
    MinTrlUndefinedReason,
)

__all__ = [
    "EvaluableTrial",
    "MinTrlComputation",
    "MinTrlSummaryComputation",
    "TrialMinTrlComputation",
    "evaluate_mintrl",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)
_FOUR = Decimal(4)


@dataclass(frozen=True, slots=True)
class EvaluableTrial:
    """One source trial whose KNOWN moments admit a MinTRL evaluation (MT-2).

    ``label`` is the source trial's label; ``n`` its OOS period count; ``sharpe`` /
    ``skew`` / ``kurtosis`` its KNOWN per-period Sharpe, skew, and non-excess kurtosis,
    each a ``Decimal`` parsed once from the source's canonical decimal strings - never
    recomputed (MT-4).
    """

    label: str
    n: int
    sharpe: Decimal
    skew: Decimal
    kurtosis: Decimal


@dataclass(frozen=True, slots=True)
class TrialMinTrlComputation:
    """One trial's computed MinTRL cell (§11).

    ``sharpe`` / ``skew`` / ``kurtosis`` are the source's KNOWN moments as canonical
    decimal strings (carried verbatim); ``min_trl`` is the minimum track-record length
    (UNDEFINED-preserving); ``excess_length = observed_length - min_trl`` (UNDEFINED,
    inheriting ``min_trl``'s reason, when the MinTRL is undefined).
    """

    label: str
    observed_length: int
    sharpe: str
    skew: str
    kurtosis: str
    min_trl: MinTrlStat
    excess_length: MinTrlStat


@dataclass(frozen=True, slots=True)
class MinTrlSummaryComputation:
    """The aggregate MinTRL statistics, as UNDEFINED-preserving cells (§11)."""

    n_determined: int
    mean_min_trl: MinTrlStat
    min_trl_dispersion: MinTrlStat
    max_min_trl: MinTrlStat
    min_min_trl: MinTrlStat
    sufficient_frequency: MinTrlStat
    mintrl_status: MinTrlStatus
    status_reason: MinTrlUndefinedReason | None


@dataclass(frozen=True, slots=True)
class MinTrlComputation:
    """The full pure result: per-trial MinTRL cells + the aggregate summary (§11)."""

    trials: tuple[TrialMinTrlComputation, ...]
    summary: MinTrlSummaryComputation


def evaluate_mintrl(
    evaluable: Sequence[EvaluableTrial],
    *,
    confidence: Decimal,
    benchmark: Decimal,
    min_determined: int,
    context: Context,
) -> MinTrlComputation:
    """Compute per-trial MinTRL + aggregate statistics (§11, MT-3/MT-4/MT-5).

    ``evaluable`` are the source's evaluable trials in source order (each with KNOWN
    moments); ``confidence`` is ``alpha`` (``Z_alpha = Φ⁻¹(alpha)``, evaluated
    once); ``benchmark`` is ``SR*``; ``min_determined`` is the floor below which
    ``mintrl_status`` is UNDEFINED; ``context`` is the pinned decimal context. An
    **empty** family (``len(evaluable) == 0``) yields empty per-trial cells and every
    aggregate cell UNDEFINED (``NO_DETERMINED_TRIALS``) - never a divide-by-zero
    (MT-3). Deterministic: identical inputs yield identical ``Decimal`` values on any
    machine.
    """
    with localcontext(context):
        z_alpha = standard_normal_ppf(confidence, context=context)
        trials: list[TrialMinTrlComputation] = []
        determined: list[Decimal] = []
        n_sufficient = 0
        for trial in evaluable:
            min_trl_value, reason = _trial_min_trl(
                sharpe=trial.sharpe,
                skew=trial.skew,
                kurtosis=trial.kurtosis,
                benchmark=benchmark,
                z_alpha=z_alpha,
            )
            if min_trl_value is None:
                assert reason is not None
                undefined = MinTrlStat.undefined(reason)
                trials.append(
                    TrialMinTrlComputation(
                        label=trial.label,
                        observed_length=trial.n,
                        sharpe=str(+trial.sharpe),
                        skew=str(+trial.skew),
                        kurtosis=str(+trial.kurtosis),
                        min_trl=undefined,
                        excess_length=undefined,
                    )
                )
                continue
            excess = Decimal(trial.n) - min_trl_value
            sufficient = Decimal(trial.n) >= min_trl_value
            if sufficient:
                n_sufficient += 1
            determined.append(min_trl_value)
            trials.append(
                TrialMinTrlComputation(
                    label=trial.label,
                    observed_length=trial.n,
                    sharpe=str(+trial.sharpe),
                    skew=str(+trial.skew),
                    kurtosis=str(+trial.kurtosis),
                    min_trl=MinTrlStat.known(str(+min_trl_value)),
                    excess_length=MinTrlStat.known(str(+excess)),
                )
            )

        summary = _summarize(
            determined=determined,
            n_sufficient=n_sufficient,
            min_determined=min_determined,
        )
    return MinTrlComputation(trials=tuple(trials), summary=summary)


def _trial_min_trl(
    *,
    sharpe: Decimal,
    skew: Decimal,
    kurtosis: Decimal,
    benchmark: Decimal,
    z_alpha: Decimal,
) -> tuple[Decimal | None, MinTrlUndefinedReason | None]:
    """``(MinTRL, None)`` or ``(None, reason)`` (called inside the pinned context).

    ``V = 1 - gamma₃·SR + ((gamma₄-1)/4)·SR²`` is checked first: a non-positive
    estimator variance is ``DEGENERATE_SHARPE_ESTIMATOR`` (matching the Phase-23 PSR
    guard, never a ``√`` of a non-positive). Then ``SR ≤ SR*`` is
    ``SHARPE_NOT_ABOVE_BENCHMARK`` (never a divide-by-zero). Otherwise
    ``MinTRL = 1 + V·(Z_alpha/(SR - SR*))²``.
    """
    estimator_variance = (
        _ONE - skew * sharpe + ((kurtosis - _ONE) / _FOUR) * sharpe * sharpe
    )
    if estimator_variance <= _ZERO:
        return None, MinTrlUndefinedReason.DEGENERATE_SHARPE_ESTIMATOR
    if sharpe <= benchmark:
        return None, MinTrlUndefinedReason.SHARPE_NOT_ABOVE_BENCHMARK
    ratio = z_alpha / (sharpe - benchmark)
    min_trl = _ONE + estimator_variance * ratio * ratio
    return +min_trl, None


def _summarize(
    *,
    determined: list[Decimal],
    n_sufficient: int,
    min_determined: int,
) -> MinTrlSummaryComputation:
    """Aggregate the per-trial MinTRLs (called inside the pinned context)."""
    k = len(determined)
    if k == 0:
        # No determined trials: every aggregate is undefined, never a divide-by-zero.
        undefined = MinTrlStat.undefined(MinTrlUndefinedReason.NO_DETERMINED_TRIALS)
        return MinTrlSummaryComputation(
            n_determined=0,
            mean_min_trl=undefined,
            min_trl_dispersion=undefined,
            max_min_trl=undefined,
            min_min_trl=undefined,
            sufficient_frequency=undefined,
            mintrl_status=MinTrlStatus.UNDEFINED,
            status_reason=MinTrlUndefinedReason.INSUFFICIENT_DETERMINED_TRIALS,
        )

    k_dec = Decimal(k)
    mean = sum(determined, _ZERO) / k_dec
    dispersion_sq = sum(((x - mean) ** 2 for x in determined), _ZERO) / k_dec
    dispersion = dispersion_sq.sqrt()
    sufficient_frequency = Decimal(n_sufficient) / k_dec
    max_min_trl = max(determined)
    min_min_trl = min(determined)

    evaluated = k >= min_determined
    return MinTrlSummaryComputation(
        n_determined=k,
        mean_min_trl=MinTrlStat.known(str(+mean)),
        min_trl_dispersion=MinTrlStat.known(str(+dispersion)),
        max_min_trl=MinTrlStat.known(str(+max_min_trl)),
        min_min_trl=MinTrlStat.known(str(+min_min_trl)),
        sufficient_frequency=MinTrlStat.known(str(+sufficient_frequency)),
        mintrl_status=(MinTrlStatus.EVALUATED if evaluated else MinTrlStatus.UNDEFINED),
        status_reason=(
            None if evaluated else MinTrlUndefinedReason.INSUFFICIENT_DETERMINED_TRIALS
        ),
    )
