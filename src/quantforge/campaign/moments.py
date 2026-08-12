"""Pure, deterministic per-trial out-of-sample moment estimation (§12).

Everything a single campaign trial contributes, in stdlib :class:`~decimal.Decimal`
under the engine's pinned context - no numpy, no float, no wall-clock, no RNG (Principle
10). The input is one trial's chained out-of-sample (OOS) return series (the
already-canonical decimal strings a :class:`~quantforge.walkforward.result.\
WalkForwardEvaluation` sealed) plus the per-period risk-free rate the walk inherited.
Every moment is a pure function of that series, so identical inputs reproduce identical
strings on any machine.

This module reads no store and holds no state; the engine resolves the trials and hands
each trial's OOS series here. A trial genuinely undefined for its data (fewer than two
OOS periods, or a zero-variance OOS series) is returned as a :class:`TrialMoments` whose
``reason`` is set and whose statistics are ``None`` - **never** a divide-by-zero, a
fabricated ``0``, a ``NaN``/``Inf``, or a silent omission (§12, CE-4).

**Pinned moment method** (folded into ``campaign-method/1``; changing one bumps
:class:`~quantforge.campaign.version.CampaignEngineVersion`). Over the ``n`` per-period
excess returns ``e_t = r_t - rf``:

* **Mean** ``μ = (1/n) Σ_t e_t``.
* **Population variance** ``sigma² = (1/n) Σ_t (e_t - μ)²`` (population divisor ``n``,
  the same convention Phase 19/20 use), and ``sigma = √sigma²`` via ``Decimal.sqrt``.
* **Per-period Sharpe** ``SR = μ / sigma`` (the *non-annualized* per-period ratio the
  PSR/DSR formulas take; the ``√(n-1)`` term supplies the sample-size scaling).
* **Skew** ``gamma₃ = m₃ / sigma³`` and **non-excess kurtosis**
  ``gamma₄ = m₄ / sigma⁴`` where ``m₃ = (1/n) Σ_t (e_t - μ)³`` and
  ``m₄ = (1/n) Σ_t (e_t - μ)⁴``.

When ``n < 2`` the moments are undefined ``INSUFFICIENT_OOS_PERIODS``; when
``sigma = 0`` they are undefined ``ZERO_OOS_VARIANCE`` (never a divide-by-zero).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext

from quantforge.campaign.errors import CampaignConsistencyError
from quantforge.campaign.model import CampaignUndefinedReason

__all__ = [
    "TrialMoments",
    "trial_moments",
]

_ZERO = Decimal(0)


def _parse_decimal(raw: str, *, what: str) -> Decimal:
    """Parse one finite :class:`~decimal.Decimal` (fail closed).

    The referenced walk-forward records sealed every OOS return via
    ``str(+Decimal(...))``; a non-decimal or non-finite element is a corrupt sealed
    value and raises :class:`CampaignConsistencyError` rather than being guessed
    (CE-4's fail-closed posture for a corrupt input cell).
    """
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise CampaignConsistencyError(
            f"{what} {raw!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise CampaignConsistencyError(f"{what} {raw!r} must be finite")
    return +value


@dataclass(frozen=True, slots=True)
class TrialMoments:
    """The per-trial OOS excess-return moments (§12).

    ``n`` is the OOS period count. When the trial is defined (``reason is None``) every
    statistic is a KNOWN :class:`~decimal.Decimal` under the pinned context; when it is
    undefined (``reason`` set) every statistic is ``None`` and ``reason`` records why.
    ``sharpe`` is the *per-period* (non-annualized) Sharpe; ``kurtosis`` is non-excess.
    """

    n: int
    sharpe: Decimal | None
    skew: Decimal | None
    kurtosis: Decimal | None
    reason: CampaignUndefinedReason | None


def trial_moments(
    oos_returns: tuple[str, ...] | list[str],
    *,
    risk_free_per_period: str,
    context: Context,
) -> TrialMoments:
    """Estimate one trial's OOS excess-return moments (§12).

    ``oos_returns`` is the trial's chained OOS return series (already-canonical decimal
    strings, in period order); ``risk_free_per_period`` the inherited per-period
    risk-free rate. Returns a :class:`TrialMoments` under the pinned context: KNOWN
    statistics when ``n >= 2`` and the population variance is positive, else an
    UNDEFINED :class:`TrialMoments` carrying the reason (``INSUFFICIENT_OOS_PERIODS`` or
    ``ZERO_OOS_VARIANCE``), never a divide-by-zero.
    """
    n = len(oos_returns)
    if n < 2:
        return TrialMoments(
            n=n,
            sharpe=None,
            skew=None,
            kurtosis=None,
            reason=CampaignUndefinedReason.INSUFFICIENT_OOS_PERIODS,
        )
    with localcontext(context):
        rf = _parse_decimal(risk_free_per_period, what="risk_free_per_period")
        excess = [_parse_decimal(v, what="oos return") - rf for v in oos_returns]
        divisor = Decimal(n)
        mean = sum(excess, _ZERO) / divisor
        deviations = [e - mean for e in excess]
        variance = sum((d * d for d in deviations), _ZERO) / divisor
        if variance == _ZERO:
            return TrialMoments(
                n=n,
                sharpe=None,
                skew=None,
                kurtosis=None,
                reason=CampaignUndefinedReason.ZERO_OOS_VARIANCE,
            )
        sigma = variance.sqrt(context)
        m3 = sum((d * d * d for d in deviations), _ZERO) / divisor
        m4 = sum((d * d * d * d for d in deviations), _ZERO) / divisor
        sigma3 = sigma * sigma * sigma
        sigma4 = sigma3 * sigma
        return TrialMoments(
            n=n,
            sharpe=+(mean / sigma),
            skew=+(m3 / sigma3),
            kurtosis=+(m4 / sigma4),
            reason=None,
        )
