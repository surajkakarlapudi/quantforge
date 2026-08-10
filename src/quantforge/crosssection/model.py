"""The cross-sectional-regression result vocabulary: status, reasons, nested records.

A **cross-sectional-regression record** is the Fama-MacBeth estimate of whether ``K``
as-of-``T`` signals price a member's realized *forward* return: one exact-``Decimal``
OLS cross-section per evaluation date, then the time-series aggregation of the per-date
coefficients into factor **premia**. This module defines the fail-closed result
vocabulary those statistics live in, plus the nested records that carry them:

* :class:`CrossSectionStatus` / :class:`CrossSectionUndefinedReason` - the fail-closed
  cell vocabulary. ``UNDEFINED`` is a first-class value carrying *why* a statistic could
  not be computed for the data (a singular per-date design, too few members, a
  zero-variance regressand, a premium whose per-date coefficient was never KNOWN, or a
  premium with zero cross-date variance for its standard error), never an exception,
  never ``0`` / ``NaN`` / ``Inf`` (§9). Mirrors Phase 16's / Phase 17's reason enums
  exactly.
* :class:`StatValue` - the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. Never a bare float, never silently omitted.
* :class:`PerDateCoefficients`, :class:`PremiumEstimate`, :class:`CoverageSummary`,
  :class:`DateCoverage` - the nested, deterministically serializable records the sealed
  :class:`~quantforge.crosssection.result.CrossSectionalRegression` holds.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CoverageSummary",
    "CrossSectionStatus",
    "CrossSectionUndefinedReason",
    "DateCoverage",
    "PerDateCoefficients",
    "PremiumEstimate",
    "StatValue",
]

#: The label of the intercept coefficient (the per-date cross-sectional alpha) in the
#: coefficient / premia blocks when ``include_intercept`` is set. The factor
#: coefficients follow, labelled by :func:`factor_label` in request order.
INTERCEPT_LABEL = "alpha"


def factor_label(index: int) -> str:
    """The deterministic label of the ``index``-th factor coefficient (0-based).

    ``factor_1``, ``factor_2``, ... in request order - a stable, name-free label keyed
    to the factor's position in the request (which fixes the design-matrix column
    order). Mirrors :func:`quantforge.attribution.model.factor_label` so the two
    regression layers label coefficients identically.
    """
    if index < 0:
        raise ValueError("factor index must be non-negative")
    return f"factor_{index + 1}"


class CrossSectionStatus(StrEnum):
    """Whether a statistic resolved to a value (``KNOWN``) or not (``UNDEFINED``)."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class CrossSectionUndefinedReason(StrEnum):
    """Why a statistic is ``UNDEFINED`` - fail-closed, never fabricated (§9).

    Every reason preserves information: it records the *absence* of a computable value
    (a singular cross-section, too few members, a zero-variance regressand, no valid
    dates, a single valid date) rather than inventing one. A zero denominator is never a
    divide-by-zero - it is one of these reasons.
    """

    #: A per-date design matrix ``XᵀX`` is not positive-definite - the signals are
    #: collinear or degenerate across that date's members (a signal is constant, or a
    #: signal is a linear combination of the others / the intercept). The whole per-date
    #: coefficient block (and its R²) is UNDEFINED; no coefficient is fabricated and no
    #: member is silently dropped.
    SINGULAR_DESIGN = "singular_design"
    #: A date whose eligible-member count is below the degrees-of-freedom floor
    #: (``n_members < K + include_intercept + 1``) - the regression has no residual
    #: degree of freedom, so the whole per-date block is undefined for that date.
    INSUFFICIENT_MEMBERS = "insufficient_members"
    #: A per-date regressand (the members' forward returns) with zero cross-sectional
    #: variance, so the total sum of squares is zero and R² (explained / total) is
    #: ``0/0`` - genuinely undefined, recorded never divided.
    ZERO_VARIANCE = "zero_variance"
    #: A premium cell for a coefficient that was KNOWN on no valid evaluation date -
    #: there is no per-date coefficient series to aggregate.
    NO_VALID_DATES = "no_valid_dates"
    #: A premium's time-series standard error / t-statistic when the coefficient was
    #: KNOWN on exactly one valid date - a single observation carries no dispersion
    #: information, so no standard error can be formed. The mean is still KNOWN; only
    #: the dispersion-derived cells (standard error, t-statistic) are undefined.
    SINGLE_VALID_DATE = "single_valid_date"
    #: A premium's t-statistic when the per-date coefficient series (over two or more
    #: valid dates) has zero population dispersion - every per-date coefficient is
    #: identical, so the standard error is exactly ``0`` and the t-statistic would
    #: divide by it. The mean and the (zero) standard error are still KNOWN; only the
    #: t-statistic is undefined.
    ZERO_COEFFICIENT_VARIANCE = "zero_coefficient_variance"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (§9).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.1234")`` - a computed decimal string (canonicalized by the
      compute layer via ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(CrossSectionUndefinedReason.SINGULAR_DESIGN)`` - a statistic
      genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    cross-sectional-regression analogue of Phase 16's / Phase 17's ``StatValue``.
    """

    status: CrossSectionStatus
    value: str | None = None
    reason: CrossSectionUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is CrossSectionStatus.KNOWN:
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
        return cls(status=CrossSectionStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: CrossSectionUndefinedReason) -> StatValue:
        """An UNDEFINED cell recording why the statistic could not be computed."""
        return cls(status=CrossSectionStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only - so
        the two are impossible to confuse and the serialized bytes are minimal.
        """
        if self.status is CrossSectionStatus.KNOWN:
            return {"status": self.status.value, "value": self.value}
        assert self.reason is not None  # guaranteed by __post_init__
        return {"status": self.status.value, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StatValue:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed - the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("StatValue.status must be a string")
        try:
            status = CrossSectionStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StatValue status {status_raw!r}") from exc
        if status is CrossSectionStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StatValue must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StatValue must carry a reason string")
        try:
            reason = CrossSectionUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown CrossSectionUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)


def _coefficient_pairs(
    pairs: tuple[tuple[str, StatValue], ...],
) -> list[dict[str, object]]:
    """Serialize ``(label, StatValue)`` coefficient pairs as an ordered list."""
    return [{"label": label, **cell.to_dict()} for label, cell in pairs]


def _coefficient_pairs_from(raw: object) -> tuple[tuple[str, StatValue], ...]:
    """Reconstruct ordered ``(label, StatValue)`` coefficient pairs, fail-closed."""
    if not isinstance(raw, list):
        raise ValueError("expected a list of (label, coefficient) pairs")
    out: list[tuple[str, StatValue]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each coefficient entry must be an object")
        label = item.get("label")
        if not isinstance(label, str):
            raise ValueError("each coefficient entry must carry a string label")
        out.append((label, StatValue.from_dict(item)))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class PerDateCoefficients:
    """One evaluation date's cross-sectional regression coefficients (§3.2).

    ``coefficients`` holds the ordered ``(label, StatValue)`` per-date factor returns -
    the intercept (``alpha``) first when the model includes one, then one cell per
    factor in request order; each a :class:`StatValue`. A singular / degenerate
    per-date design yields an all-``UNDEFINED`` block (recorded, never dropped).
    ``r_squared`` is the per-date coefficient of determination (a :class:`StatValue`).
    ``n_members`` is the count of eligible members (rows) in this date's cross-section.
    """

    as_of: str
    n_members: int
    coefficients: tuple[tuple[str, StatValue], ...]
    r_squared: StatValue

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "n_members": self.n_members,
            "coefficients": _coefficient_pairs(self.coefficients),
            "r_squared": self.r_squared.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PerDateCoefficients:
        as_of = raw.get("as_of")
        n_members = raw.get("n_members")
        r_squared = raw.get("r_squared")
        if not isinstance(as_of, str):
            raise ValueError("PerDateCoefficients.as_of must be a string")
        if not isinstance(n_members, int) or isinstance(n_members, bool):
            raise ValueError("PerDateCoefficients.n_members must be an int")
        if not isinstance(r_squared, dict):
            raise ValueError("PerDateCoefficients.r_squared must be an object")
        return cls(
            as_of=as_of,
            n_members=n_members,
            coefficients=_coefficient_pairs_from(raw.get("coefficients")),
            r_squared=StatValue.from_dict(r_squared),
        )


@dataclass(frozen=True, slots=True)
class PremiumEstimate:
    """The aggregated Fama-MacBeth premium for one coefficient (§3.2).

    ``mean`` is the time-series mean of the per-date coefficient over the valid dates;
    ``std_error`` is the plain Fama-MacBeth standard error (population standard
    deviation over the valid dates divided by ``√M``); ``t_stat`` is
    ``mean / std_error``; each a :class:`StatValue`. ``n_valid_dates`` is the count of
    dates on which this coefficient was KNOWN (the ``M`` that aggregated). A coefficient
    KNOWN on no date is all-UNDEFINED (``NO_VALID_DATES``); on exactly one date the mean
    is KNOWN but the dispersion cells are ``SINGLE_VALID_DATE``.
    """

    label: str
    mean: StatValue
    std_error: StatValue
    t_stat: StatValue
    n_valid_dates: int

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "mean": self.mean.to_dict(),
            "std_error": self.std_error.to_dict(),
            "t_stat": self.t_stat.to_dict(),
            "n_valid_dates": self.n_valid_dates,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PremiumEstimate:
        label = raw.get("label")
        n_valid = raw.get("n_valid_dates")
        if not isinstance(label, str):
            raise ValueError("PremiumEstimate.label must be a string")
        if not isinstance(n_valid, int) or isinstance(n_valid, bool):
            raise ValueError("PremiumEstimate.n_valid_dates must be an int")

        def cell(key: str) -> StatValue:
            v = raw.get(key)
            if not isinstance(v, dict):
                raise ValueError(f"PremiumEstimate.{key} must be an object")
            return StatValue.from_dict(v)

        return cls(
            label=label,
            mean=cell("mean"),
            std_error=cell("std_error"),
            t_stat=cell("t_stat"),
            n_valid_dates=n_valid,
        )


@dataclass(frozen=True, slots=True)
class DateCoverage:
    """One evaluation date's coverage breakdown - exclusions are auditable (§6, XS-4).

    ``regression_status`` is ``"known"`` when the date admitted a defined regression, or
    the ``CrossSectionUndefinedReason`` value (``"insufficient_members"`` /
    ``"singular_design"`` / ``"zero_variance"``) that made the whole per-date block
    UNDEFINED - so a reader sees exactly why a scheduled date did not contribute a valid
    cross-section.
    """

    as_of: str
    resolved_members: int
    eligible: int
    dropped_for_signal: int
    dropped_for_return: int
    regression_status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "resolved_members": self.resolved_members,
            "eligible": self.eligible,
            "dropped_for_signal": self.dropped_for_signal,
            "dropped_for_return": self.dropped_for_return,
            "regression_status": self.regression_status,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> DateCoverage:
        def req_int(key: str) -> int:
            v = raw.get(key)
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError(f"DateCoverage.{key} must be an int")
            return v

        as_of = raw.get("as_of")
        regression_status = raw.get("regression_status")
        if not isinstance(as_of, str):
            raise ValueError("DateCoverage.as_of must be a string")
        if not isinstance(regression_status, str):
            raise ValueError("DateCoverage.regression_status must be a string")
        return cls(
            as_of=as_of,
            resolved_members=req_int("resolved_members"),
            eligible=req_int("eligible"),
            dropped_for_signal=req_int("dropped_for_signal"),
            dropped_for_return=req_int("dropped_for_return"),
            regression_status=regression_status,
        )


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """Per-date and total coverage counts - never a silent exclusion (§6, XS-4)."""

    per_date: tuple[DateCoverage, ...]
    total_eligible: int
    total_dropped_for_signal: int
    total_dropped_for_return: int
    total_dropped_for_singular_date: int

    def to_dict(self) -> dict[str, object]:
        return {
            "per_date": [d.to_dict() for d in self.per_date],
            "total_eligible": self.total_eligible,
            "total_dropped_for_signal": self.total_dropped_for_signal,
            "total_dropped_for_return": self.total_dropped_for_return,
            "total_dropped_for_singular_date": self.total_dropped_for_singular_date,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CoverageSummary:
        per_date_raw = raw.get("per_date")
        if not isinstance(per_date_raw, list):
            raise ValueError("CoverageSummary.per_date must be a list")

        def req_int(key: str) -> int:
            v = raw.get(key)
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError(f"CoverageSummary.{key} must be an int")
            return v

        per_date = tuple(
            DateCoverage.from_dict(d) for d in per_date_raw if isinstance(d, dict)
        )
        if len(per_date) != len(per_date_raw):
            raise ValueError("each CoverageSummary.per_date entry must be an object")
        return cls(
            per_date=per_date,
            total_eligible=req_int("total_eligible"),
            total_dropped_for_signal=req_int("total_dropped_for_signal"),
            total_dropped_for_return=req_int("total_dropped_for_return"),
            total_dropped_for_singular_date=req_int("total_dropped_for_singular_date"),
        )
