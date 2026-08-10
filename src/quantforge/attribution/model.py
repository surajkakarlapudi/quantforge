"""The attribution result vocabulary: status, undefined reasons, keys, cells, labels.

A **factor-attribution record** is a multi-factor OLS regression of one sealed subject
backtest's ``period_returns`` (as excess returns) on *K* sealed factor backtests' excess
returns. This module defines the fail-closed result vocabulary those statistics live in:

* :class:`AttributionStatus` / :class:`AttributionUndefinedReason` — the fail-closed
cell
  vocabulary. ``UNDEFINED`` is a first-class value carrying *why* a statistic could not
  be computed for the data (a singular design, too few residual degrees of freedom, a
  zero-variance regressand, a perfect fit), never an exception, never ``0`` / ``NaN`` /
  ``Inf`` (§11, FA-4). This mirrors Phase 15's
  :class:`~quantforge.analytics.model.AnalyticsUndefinedReason` exactly.
* :class:`StatValue` — the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. It is never a bare float and never silently omitted — a statistic
  that cannot be computed for the data is present in the record with its reason.
* the **closed v1 diagnostic key set** (:data:`DIAGNOSTIC_KEYS`) and the coefficient /
  decomposition **labels** (:data:`INTERCEPT_LABEL`, :func:`factor_label`). Extending
  the
  diagnostic set is an explicit future edit that hashes distinctly — never an implicit
  fallback (mirrors the Phase 15 D-discipline).

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "DIAGNOSTIC_KEYS",
    "INTERCEPT_LABEL",
    "AttributionStatus",
    "AttributionUndefinedReason",
    "StatValue",
    "factor_label",
]


class AttributionStatus(StrEnum):
    """Whether a statistic resolved to a value (``KNOWN``) or not (``UNDEFINED``)."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class AttributionUndefinedReason(StrEnum):
    """Why a statistic is ``UNDEFINED`` — fail-closed, never fabricated (§11, FA-4).

    Every reason preserves information: it records the *absence* of a computable value
    (a singular design, an unmet precondition, a zero denominator) rather than inventing
    one. A zero denominator is never a divide-by-zero — it is one of these reasons.
    """

    #: The design matrix ``XᵀX`` is not positive-definite — the factors are collinear or
    #: degenerate (a factor is constant, or a factor is a linear combination of the
    #: others / the intercept). The whole coefficient / diagnostic / decomposition block
    #: is UNDEFINED; no coefficient is fabricated and no factor is silently dropped.
    SINGULAR_DESIGN = "singular_design"
    #: Too few return observations for the requested model to have residual degrees of
    #: freedom (``n - K - 1 <= 0``) — the diagnostics that divide by the residual df
    #: (residual standard error, coefficient standard errors, t-statistics) are
    #: undefined. (The engine fails *closed* below ``n >= K + 2`` before computing; this
    #: reason guards any per-cell degenerate case.)
    INSUFFICIENT_PERIODS = "insufficient_periods"
    #: The regressand (the subject's excess return) has zero sample variance, so the
    #: total sum of squares is zero and R² (explained / total) is ``0/0`` — genuinely
    #: undefined, recorded never divided.
    ZERO_VARIANCE = "zero_variance"
    #: A perfect in-sample fit: the residual sum of squares is zero, so the residual
    #: variance is zero and every standard error / t-statistic is undefined (a
    #: zero-over-zero or division by a zero standard error), recorded never divided.
    ZERO_RESIDUAL_VARIANCE = "zero_residual_variance"


# -- the closed v1 diagnostic vocabulary (§6, §11) ---------------------------
#
# A sorted tuple: the record stores the diagnostics block sorted by key, so iteration
# and
# identity are order-independent. Extending the set is an explicit future edit that
# hashes distinctly (a new key changes the result_hash) — never an edit that
# reinterprets an existing record. Per-coefficient standard errors and t-statistics are
# *not* here: they live on each coefficient cell (a ``(label, estimate, std_error,
# t_stat)`` quadruple), because they are indexed by coefficient, not global.
DIAGNOSTIC_KEYS: tuple[str, ...] = (
    "adjusted_r_squared",
    "r_squared",
    "residual_std_error",
)

#: The label of the intercept coefficient (the regression alpha) in the coefficient and
#: decomposition blocks. The factor coefficients follow, labelled by
#: :func:`factor_label`
#: in request order.
INTERCEPT_LABEL = "alpha"


def factor_label(index: int) -> str:
    """The deterministic label of the ``index``-th factor coefficient (0-based).

    ``factor_1``, ``factor_2``, … in request order — a stable, name-free label keyed to
    the factor's position in the request (which fixes the design-matrix column order).
    The record's ``factor_refs`` maps each position back to its ``(backtest_id,
    result_hash)`` for provenance, so the numeric label never loses information.
    """
    if index < 0:
        raise ValueError("factor index must be non-negative")
    return f"factor_{index + 1}"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (FA-4).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.1234")`` — a computed decimal string (canonicalized by the
      compute layer via ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN)`` — a statistic
      that is genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    attribution analogue of Phase 15's KNOWN/UNDEFINED statistic value.
    """

    status: AttributionStatus
    value: str | None = None
    reason: AttributionUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is AttributionStatus.KNOWN:
            if not isinstance(self.value, str) or self.reason is not None:
                raise ValueError(
                    "a KNOWN StatValue must carry a decimal-string value and no reason"
                )
        else:  # UNDEFINED
            if self.reason is None or self.value is not None:
                raise ValueError(
                    "an UNDEFINED StatValue must carry a reason and no value"
                )

    @classmethod
    def known(cls, value: str) -> StatValue:
        """A KNOWN cell holding a canonical decimal string."""
        return cls(status=AttributionStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: AttributionUndefinedReason) -> StatValue:
        """An UNDEFINED cell recording why the statistic could not be computed."""
        return cls(status=AttributionStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only — so
        the two are impossible to confuse and the serialized bytes are minimal.
        """
        if self.status is AttributionStatus.KNOWN:
            return {"status": self.status.value, "value": self.value}
        assert self.reason is not None  # guaranteed by __post_init__
        return {"status": self.status.value, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StatValue:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed — the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("StatValue.status must be a string")
        try:
            status = AttributionStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StatValue status {status_raw!r}") from exc
        if status is AttributionStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StatValue must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StatValue must carry a reason string")
        try:
            reason = AttributionUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown AttributionUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)
