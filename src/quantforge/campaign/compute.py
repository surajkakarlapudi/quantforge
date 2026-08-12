"""Pure, deterministic PSR/DSR selection-bias arithmetic (§12, López de Prado).

Given each trial's out-of-sample moments (from
:mod:`quantforge.campaign.moments`) and a benchmark Sharpe ``SR*``, this module
computes - in stdlib :class:`~decimal.Decimal` under the engine's pinned
context, atop the deterministic normal primitive of
:mod:`quantforge.campaign.normal` - everything the sealed record reports:

* **Per-trial Probabilistic Sharpe Ratio** against ``SR*``
  (:func:`probabilistic_sharpe`).
* **The selection**: the valid trial with the greatest per-period Sharpe (ties broken by
  the lowest request index, so the choice is order-deterministic).
* **The expected-maximum Sharpe under the null** ``SR₀`` (:func:`expected_max_sharpe`) -
  the Sharpe you would expect the *best* of ``N`` independent zero-skill trials
  to post by luck alone, from the population dispersion of the trials' Sharpe
  ratios.
* **The Deflated Sharpe Ratio**: the PSR of the selected trial *against* ``SR₀`` - the
  selection-bias-corrected significance of the best strategy.

The **pinned formulas** (folded into ``campaign-method/1``; changing one bumps
:class:`~quantforge.campaign.version.CampaignEngineVersion`):

* ``PSR(SR*) = Φ( (SR - SR*)·√(n-1) / √(1 - gamma₃·SR + ((gamma₄-1)/4)·SR²) )``
  where ``n`` is the trial's OOS period count, ``gamma₃`` its skew, ``gamma₄``
  its non-excess kurtosis. The denominator argument is ``≥ 0`` for any valid
  moment set (the skew-kurtosis inequality ``gamma₄ ≥ 1 + gamma₃²``); a
  non-positive value is recorded ``DEGENERATE_SHARPE_ESTIMATOR``, never a
  divide-by-zero or a square root of a negative.
* ``SR₀ = √V · [ (1-gamma)·Z⁻¹(1 - 1/N) + gamma·Z⁻¹(1 - 1/(N·e)) ]`` where ``V``
  is the **population** variance of the valid trials' Sharpe ratios, ``N`` the
  size of the search (the count of **all** submitted trials, valid or not -
  CE-2), ``gamma`` the Euler-Mascheroni constant, and ``e = exp(1)``.
* ``DSR = PSR(SR₀)`` of the selected trial.

A campaign with fewer than :data:`MIN_VALID_TRIALS` valid trials cannot estimate the
Sharpe dispersion, so its selection / ``SR₀`` / DSR are undefined
``INSUFFICIENT_VALID_TRIALS`` (recorded, never fabricated). Every function here
is a pure function of its arguments and the passed context - no store, no state,
no wall clock, no RNG, no float.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge.campaign.model import CampaignUndefinedReason, TrialStatus
from quantforge.campaign.moments import TrialMoments
from quantforge.campaign.normal import (
    EULER_MASCHERONI,
    standard_normal_cdf,
    standard_normal_ppf,
)

__all__ = [
    "MIN_VALID_TRIALS",
    "CampaignComputation",
    "TrialComputation",
    "campaign_statistics",
    "expected_max_sharpe",
    "probabilistic_sharpe",
    "sharpe_dispersion",
    "trial_statistics",
]

#: The minimum number of valid trials a campaign needs before a selection-bias
#: correction is meaningful: at least two, so the cross-trial Sharpe dispersion
#: ``V`` is estimable from a genuine spread rather than a single point. Fewer
#: valid trials records the campaign selection / ``SR₀`` / DSR as UNDEFINED
#: ``INSUFFICIENT_VALID_TRIALS`` (CE-4) - never fabricated from one trial.
#: Mirrors the spec's ``_MIN_TRIALS`` floor on *submitted* trials, but here
#: counts the *valid* ones.
MIN_VALID_TRIALS = 2

_ZERO = Decimal(0)
_ONE = Decimal(1)
_FOUR = Decimal(4)


@dataclass(frozen=True, slots=True)
class TrialComputation:
    """One trial's computed statistics under the pinned context (§12).

    ``status`` is ``VALID`` exactly when the OOS Sharpe is defined; then
    ``sharpe`` / ``skew`` / ``kurtosis`` are KNOWN decimals and ``reason`` is
    ``None``. When ``status`` is ``UNDEFINED`` those are ``None`` and ``reason``
    records why (a moment-level reason). ``psr`` is the per-trial Probabilistic
    Sharpe Ratio against the benchmark; it is ``None`` with ``psr_reason`` set
    when the trial is undefined (inheriting ``reason``) or when its
    Sharpe-estimator variance is degenerate (``DEGENERATE_SHARPE_ESTIMATOR``).
    """

    index: int
    n: int
    status: TrialStatus
    sharpe: Decimal | None
    skew: Decimal | None
    kurtosis: Decimal | None
    reason: CampaignUndefinedReason | None
    psr: Decimal | None
    psr_reason: CampaignUndefinedReason | None


@dataclass(frozen=True, slots=True)
class CampaignComputation:
    """The cross-trial selection-bias result under the pinned context (§12).

    When defined (``reason is None``): ``selected_index`` is the request index of the
    greatest-Sharpe valid trial (ties → lowest index), ``selected_sharpe`` its Sharpe,
    ``dispersion`` the population variance ``V`` of the valid Sharpe ratios,
    ``expected_max_sharpe`` the null threshold ``SR₀``, and ``deflated_sharpe`` the DSR
    (``None`` with ``deflated_reason`` set only if the selected trial's PSR estimator is
    degenerate). When undefined (fewer than :data:`MIN_VALID_TRIALS` valid trials),
    ``reason`` is ``INSUFFICIENT_VALID_TRIALS`` and every campaign-level statistic is
    ``None``.
    """

    n_trials: int
    valid_count: int
    reason: CampaignUndefinedReason | None
    selected_index: int | None
    selected_sharpe: Decimal | None
    dispersion: Decimal | None
    expected_max_sharpe: Decimal | None
    deflated_sharpe: Decimal | None
    deflated_reason: CampaignUndefinedReason | None


def probabilistic_sharpe(
    *,
    sharpe: Decimal,
    benchmark: Decimal,
    skew: Decimal,
    kurtosis: Decimal,
    n: int,
    context: Context,
) -> Decimal | None:
    """``PSR(SR*) = Φ((SR - SR*)·√(n-1)/√(1 - gamma₃·SR + ((gamma₄-1)/4)·SR²))``
    (deterministic).

    Returns the probability under the pinned context, or ``None`` when the
    estimator variance ``1 - gamma₃·SR + ((gamma₄-1)/4)·SR²`` is non-positive (a
    degenerate moment set) - the caller records that as
    ``DEGENERATE_SHARPE_ESTIMATOR`` rather than taking a square root of a
    non-positive number. Requires ``n ≥ 2`` (guaranteed by the moment layer).
    """
    with localcontext(context):
        estimator_variance = (
            _ONE - skew * sharpe + ((kurtosis - _ONE) / _FOUR) * sharpe * sharpe
        )
        if estimator_variance <= _ZERO:
            return None
        numerator = (sharpe - benchmark) * Decimal(n - 1).sqrt(context)
        argument = numerator / estimator_variance.sqrt(context)
    return standard_normal_cdf(argument, context=context)


def sharpe_dispersion(sharpes: list[Decimal], *, context: Context) -> Decimal:
    """The **population** variance ``V`` of the valid trials' Sharpe ratios
    (deterministic).

    Population divisor (count, not count - 1), the same convention the moment layer and
    every prior derived layer use. A pure function of the Sharpe list and the context.
    """
    with localcontext(context):
        m = Decimal(len(sharpes))
        mean = sum(sharpes, _ZERO) / m
        variance = sum(((s - mean) * (s - mean) for s in sharpes), _ZERO) / m
        return +variance


def expected_max_sharpe(
    *,
    dispersion: Decimal,
    n_trials: int,
    context: Context,
) -> Decimal:
    """``SR₀ = √V·[(1-gamma)·Z⁻¹(1-1/N) + gamma·Z⁻¹(1-1/(N·e))]`` (deterministic).

    The Sharpe the best of ``N`` independent zero-skill trials is expected to
    post by luck, from the population dispersion ``V`` and the search size
    ``N = n_trials`` (all submitted trials, CE-2). ``gamma`` is the
    Euler-Mascheroni constant and ``e = exp(1)``, both under the pinned context.
    Requires ``n_trials ≥ 2`` (so both quantile arguments lie in ``(0, 1)``).
    """
    with localcontext(context):
        n = Decimal(n_trials)
        e = _ONE.exp(context)
        p_first = _ONE - _ONE / n
        p_second = _ONE - _ONE / (n * e)
        z_first = standard_normal_ppf(p_first, context=context)
        z_second = standard_normal_ppf(p_second, context=context)
        sr0 = dispersion.sqrt(context) * (
            (_ONE - EULER_MASCHERONI) * z_first + EULER_MASCHERONI * z_second
        )
        return +sr0


def trial_statistics(
    moments: list[TrialMoments],
    *,
    benchmark: Decimal,
    context: Context,
) -> tuple[TrialComputation, ...]:
    """Per-trial statistics (Sharpe, skew, kurtosis, PSR against ``benchmark``).

    Each moment set becomes a :class:`TrialComputation`: ``VALID`` with KNOWN
    statistics and a PSR when its Sharpe is defined (PSR itself may be
    ``DEGENERATE_SHARPE_ESTIMATOR`` for a razor-edge moment set), else
    ``UNDEFINED`` carrying the moment-level reason. The trial order is the
    request order (index fixes the ``trial_1..trial_N`` label and the selection
    tie-break).
    """
    computations: list[TrialComputation] = []
    for index, moment in enumerate(moments):
        if moment.reason is not None:
            computations.append(
                TrialComputation(
                    index=index,
                    n=moment.n,
                    status=TrialStatus.UNDEFINED,
                    sharpe=None,
                    skew=None,
                    kurtosis=None,
                    reason=moment.reason,
                    psr=None,
                    psr_reason=moment.reason,
                )
            )
            continue
        assert moment.sharpe is not None  # reason is None ⇒ statistics defined
        assert moment.skew is not None
        assert moment.kurtosis is not None
        psr = probabilistic_sharpe(
            sharpe=moment.sharpe,
            benchmark=benchmark,
            skew=moment.skew,
            kurtosis=moment.kurtosis,
            n=moment.n,
            context=context,
        )
        computations.append(
            TrialComputation(
                index=index,
                n=moment.n,
                status=TrialStatus.VALID,
                sharpe=moment.sharpe,
                skew=moment.skew,
                kurtosis=moment.kurtosis,
                reason=None,
                psr=psr,
                psr_reason=(
                    None
                    if psr is not None
                    else CampaignUndefinedReason.DEGENERATE_SHARPE_ESTIMATOR
                ),
            )
        )
    return tuple(computations)


def campaign_statistics(
    trials: tuple[TrialComputation, ...],
    *,
    n_trials: int,
    context: Context,
) -> CampaignComputation:
    """Select the best trial and deflate its Sharpe for the size of the search (§12).

    ``n_trials`` is the count of **all** submitted trials (the search size
    ``N``, CE-2), independent of how many are valid. When fewer than
    :data:`MIN_VALID_TRIALS` trials are valid the campaign selection / ``SR₀`` /
    DSR are undefined ``INSUFFICIENT_VALID_TRIALS`` (never fabricated). Otherwise
    the greatest-Sharpe valid trial is selected (ties → lowest index), ``SR₀`` is
    computed from the valid trials' Sharpe dispersion, and the Deflated Sharpe
    Ratio is the selected trial's PSR against ``SR₀``.
    """
    valid = [t for t in trials if t.status is TrialStatus.VALID]
    if len(valid) < MIN_VALID_TRIALS:
        return CampaignComputation(
            n_trials=n_trials,
            valid_count=len(valid),
            reason=CampaignUndefinedReason.INSUFFICIENT_VALID_TRIALS,
            selected_index=None,
            selected_sharpe=None,
            dispersion=None,
            expected_max_sharpe=None,
            deflated_sharpe=None,
            deflated_reason=None,
        )
    # Greatest Sharpe, ties broken by the lowest request index (deterministic order).
    selected = valid[0]
    for candidate in valid[1:]:
        assert candidate.sharpe is not None and selected.sharpe is not None
        if candidate.sharpe > selected.sharpe:
            selected = candidate
    assert selected.sharpe is not None
    assert selected.skew is not None
    assert selected.kurtosis is not None
    sharpes = [t.sharpe for t in valid if t.sharpe is not None]
    dispersion = sharpe_dispersion(sharpes, context=context)
    sr0 = expected_max_sharpe(dispersion=dispersion, n_trials=n_trials, context=context)
    dsr = probabilistic_sharpe(
        sharpe=selected.sharpe,
        benchmark=sr0,
        skew=selected.skew,
        kurtosis=selected.kurtosis,
        n=selected.n,
        context=context,
    )
    return CampaignComputation(
        n_trials=n_trials,
        valid_count=len(valid),
        reason=None,
        selected_index=selected.index,
        selected_sharpe=selected.sharpe,
        dispersion=dispersion,
        expected_max_sharpe=sr0,
        deflated_sharpe=dsr,
        deflated_reason=(
            None
            if dsr is not None
            else CampaignUndefinedReason.DEGENERATE_SHARPE_ESTIMATOR
        ),
    )
