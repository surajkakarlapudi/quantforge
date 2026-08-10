"""The factor-portfolio result vocabulary: status, reasons, nested records.

A **factor-portfolio record** is the realized return series of a characteristic-sorted
long/short portfolio: at each rebalance date ``T`` the eligible members are sorted into
``Q`` quantiles by an as-of-``T`` signal, the top bucket forms the long leg and the
bottom bucket the short leg, each leg is equal-weighted, and the per-period factor
return is the long-leg mean forward return minus the short-leg mean forward return; the
series is then aggregated into a performance summary. This module defines the
fail-closed result vocabulary those statistics live in, plus the nested records that
carry them:

* :class:`FactorPortfolioStatus` / :class:`FactorPortfolioUndefinedReason` - the
  fail-closed cell vocabulary. ``UNDEFINED`` is a first-class value carrying *why* a
  statistic could not be computed for the data (a period with too few members to fill
  both legs, an empty long or short leg, a series with no or a single valid period, a
  series with zero return variance for its Sharpe / t-statistic), never an exception,
  never ``0`` / ``NaN`` / ``Inf`` (§9). Mirrors Phase 16's / Phase 18's reason enums.
* :class:`StatValue` - the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. Never a bare float, never silently omitted.
* :class:`LegKind`, :class:`LegMembership`, :class:`PerPeriodReturn`,
  :class:`FactorReturnSummary`, :class:`CoverageSummary`, :class:`DateCoverage` - the
  nested, deterministically serializable records the sealed
  :class:`~quantforge.factorportfolio.result.FactorPortfolio` holds.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CoverageSummary",
    "DateCoverage",
    "FactorPortfolioStatus",
    "FactorPortfolioUndefinedReason",
    "FactorReturnSummary",
    "LegKind",
    "LegMembership",
    "PerPeriodReturn",
    "StatValue",
]


class FactorPortfolioStatus(StrEnum):
    """Whether a statistic resolved to a value (``KNOWN``) or not (``UNDEFINED``)."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class FactorPortfolioUndefinedReason(StrEnum):
    """Why a statistic is ``UNDEFINED`` - fail-closed, never fabricated (§9).

    Every reason preserves information: it records the *absence* of a computable value
    (a period with an empty leg or too few members, a series with no or a single valid
    period, a series with zero dispersion) rather than inventing one. A zero denominator
    is never a divide-by-zero - it is one of these reasons.
    """

    #: A rebalance period whose eligible-member count is below the leg floor
    #: (``n_members < 2 * quantiles``, so at least one member per bucket and both legs
    #: non-empty cannot be guaranteed) - the whole per-period block (both legs and the
    #: factor return) is undefined for that period. No leg is fabricated and no member
    #: is silently dropped.
    INSUFFICIENT_MEMBERS = "insufficient_members"
    #: A period whose top (long) quantile bucket is empty after sorting - there is no
    #: long leg, so the factor return cannot be formed. Recorded, never fabricated.
    EMPTY_LONG_LEG = "empty_long_leg"
    #: A period whose bottom (short) quantile bucket is empty after sorting - there is
    #: no short leg, so the factor return cannot be formed. Recorded, never fabricated.
    EMPTY_SHORT_LEG = "empty_short_leg"
    #: A summary cell over a return series that was KNOWN on no valid period - there is
    #: no per-period return series to aggregate.
    NO_VALID_PERIODS = "no_valid_periods"
    #: A summary's dispersion cell (volatility / Sharpe / t-statistic) over a series
    #: with exactly one valid period - a single observation carries no dispersion
    #: information, so no volatility can be formed. The mean / cumulative cells are
    #: still KNOWN; only the dispersion-derived cells are undefined.
    SINGLE_VALID_PERIOD = "single_valid_period"
    #: A summary's Sharpe / t-statistic over a series (of two or more valid periods)
    #: with zero population dispersion - every per-period factor return is identical, so
    #: the volatility is exactly ``0`` and the ratio would divide by it. The mean,
    #: cumulative, and (zero) volatility cells are still KNOWN; only the Sharpe /
    #: t-statistic are undefined.
    ZERO_RETURN_VARIANCE = "zero_return_variance"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (§9).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.1234")`` - a computed decimal string (canonicalized by the
      compute layer via ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(FactorPortfolioUndefinedReason.EMPTY_LONG_LEG)`` - a
      statistic genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    factor-portfolio analogue of Phase 16's / Phase 18's ``StatValue``.
    """

    status: FactorPortfolioStatus
    value: str | None = None
    reason: FactorPortfolioUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is FactorPortfolioStatus.KNOWN:
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
        return cls(status=FactorPortfolioStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: FactorPortfolioUndefinedReason) -> StatValue:
        """An UNDEFINED cell recording why the statistic could not be computed."""
        return cls(status=FactorPortfolioStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only - so
        the two are impossible to confuse and the serialized bytes are minimal.
        """
        if self.status is FactorPortfolioStatus.KNOWN:
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
            status = FactorPortfolioStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StatValue status {status_raw!r}") from exc
        if status is FactorPortfolioStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StatValue must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StatValue must carry a reason string")
        try:
            reason = FactorPortfolioUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown FactorPortfolioUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)


class LegKind(StrEnum):
    """Which leg of the long/short factor portfolio a membership records."""

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class LegMembership:
    """The ordered members assigned to one leg on one rebalance date (§5.5).

    ``company_ids`` is the sorted tuple of ``company_id``s the sort placed in this leg's
    quantile bucket (top for LONG, bottom for SHORT). It is audit metadata - recoverable
    from the pinned corpora - and is **not** folded into ``result_hash`` (§5.6); only
    the per-period leg returns and factor return are sealed.
    """

    kind: LegKind
    company_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind.value, "company_ids": list(self.company_ids)}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> LegMembership:
        kind_raw = raw.get("kind")
        if not isinstance(kind_raw, str):
            raise ValueError("LegMembership.kind must be a string")
        try:
            kind = LegKind(kind_raw)
        except ValueError as exc:
            raise ValueError(f"unknown LegKind {kind_raw!r}") from exc
        ids_raw = raw.get("company_ids")
        if not isinstance(ids_raw, list) or not all(
            isinstance(x, str) for x in ids_raw
        ):
            raise ValueError("LegMembership.company_ids must be a list of strings")
        return cls(kind=kind, company_ids=tuple(ids_raw))


@dataclass(frozen=True, slots=True)
class PerPeriodReturn:
    """One rebalance date's long/short factor return + leg detail (§5.5).

    ``long_return`` / ``short_return`` are each leg's equal-weighted mean forward
    return; ``factor_return`` is the long-minus-short spread - each a
    :class:`StatValue`. A period below the leg floor or with an empty long/short leg
    yields UNDEFINED legs and factor return (recorded, never dropped).
    ``long_membership`` / ``short_membership`` record the members assigned to each leg
    (audit metadata, not sealed). ``n_members`` is the count of eligible members (rows)
    in this period's cross-section.
    """

    as_of: str
    n_members: int
    long_membership: LegMembership
    short_membership: LegMembership
    long_return: StatValue
    short_return: StatValue
    factor_return: StatValue

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "n_members": self.n_members,
            "long_membership": self.long_membership.to_dict(),
            "short_membership": self.short_membership.to_dict(),
            "long_return": self.long_return.to_dict(),
            "short_return": self.short_return.to_dict(),
            "factor_return": self.factor_return.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PerPeriodReturn:
        as_of = raw.get("as_of")
        n_members = raw.get("n_members")
        if not isinstance(as_of, str):
            raise ValueError("PerPeriodReturn.as_of must be a string")
        if not isinstance(n_members, int) or isinstance(n_members, bool):
            raise ValueError("PerPeriodReturn.n_members must be an int")

        def cell(key: str) -> StatValue:
            v = raw.get(key)
            if not isinstance(v, dict):
                raise ValueError(f"PerPeriodReturn.{key} must be an object")
            return StatValue.from_dict(v)

        def membership(key: str) -> LegMembership:
            v = raw.get(key)
            if not isinstance(v, dict):
                raise ValueError(f"PerPeriodReturn.{key} must be an object")
            return LegMembership.from_dict(v)

        return cls(
            as_of=as_of,
            n_members=n_members,
            long_membership=membership("long_membership"),
            short_membership=membership("short_membership"),
            long_return=cell("long_return"),
            short_return=cell("short_return"),
            factor_return=cell("factor_return"),
        )


@dataclass(frozen=True, slots=True)
class FactorReturnSummary:
    """The aggregated performance of the factor return series (§5.5).

    ``cumulative_return`` is the compounded ``prod(1 + f_T) - 1`` over the valid
    periods; ``mean_period_return`` the time-series mean; ``volatility`` the population
    standard deviation; ``annualized_sharpe`` the ``(mean - rf)/vol *
    sqrt(periods_per_year)``; ``mean_t_stat`` the mean's t-statistic ``mean /
    (popStd/sqrt(M))``; ``hit_rate`` the fraction of valid periods with a positive
    factor return; each a :class:`StatValue`. ``n_valid_periods`` is the count of
    periods that contributed a KNOWN factor return.
    """

    cumulative_return: StatValue
    mean_period_return: StatValue
    volatility: StatValue
    annualized_sharpe: StatValue
    mean_t_stat: StatValue
    hit_rate: StatValue
    n_valid_periods: int

    def to_dict(self) -> dict[str, object]:
        return {
            "cumulative_return": self.cumulative_return.to_dict(),
            "mean_period_return": self.mean_period_return.to_dict(),
            "volatility": self.volatility.to_dict(),
            "annualized_sharpe": self.annualized_sharpe.to_dict(),
            "mean_t_stat": self.mean_t_stat.to_dict(),
            "hit_rate": self.hit_rate.to_dict(),
            "n_valid_periods": self.n_valid_periods,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FactorReturnSummary:
        n_valid = raw.get("n_valid_periods")
        if not isinstance(n_valid, int) or isinstance(n_valid, bool):
            raise ValueError("FactorReturnSummary.n_valid_periods must be an int")

        def cell(key: str) -> StatValue:
            v = raw.get(key)
            if not isinstance(v, dict):
                raise ValueError(f"FactorReturnSummary.{key} must be an object")
            return StatValue.from_dict(v)

        return cls(
            cumulative_return=cell("cumulative_return"),
            mean_period_return=cell("mean_period_return"),
            volatility=cell("volatility"),
            annualized_sharpe=cell("annualized_sharpe"),
            mean_t_stat=cell("mean_t_stat"),
            hit_rate=cell("hit_rate"),
            n_valid_periods=n_valid,
        )


@dataclass(frozen=True, slots=True)
class DateCoverage:
    """One rebalance date's coverage breakdown - exclusions are auditable (§6, P19-4).

    ``period_status`` is ``"known"`` when the date admitted a defined factor return, or
    the ``FactorPortfolioUndefinedReason`` value (``"insufficient_members"`` /
    ``"empty_long_leg"`` / ``"empty_short_leg"``) that made the whole per-period block
    UNDEFINED - so a reader sees exactly why a scheduled date did not contribute a valid
    factor return.
    """

    as_of: str
    resolved_members: int
    eligible: int
    dropped_for_signal: int
    dropped_for_return: int
    period_status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "resolved_members": self.resolved_members,
            "eligible": self.eligible,
            "dropped_for_signal": self.dropped_for_signal,
            "dropped_for_return": self.dropped_for_return,
            "period_status": self.period_status,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> DateCoverage:
        def req_int(key: str) -> int:
            v = raw.get(key)
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError(f"DateCoverage.{key} must be an int")
            return v

        as_of = raw.get("as_of")
        period_status = raw.get("period_status")
        if not isinstance(as_of, str):
            raise ValueError("DateCoverage.as_of must be a string")
        if not isinstance(period_status, str):
            raise ValueError("DateCoverage.period_status must be a string")
        return cls(
            as_of=as_of,
            resolved_members=req_int("resolved_members"),
            eligible=req_int("eligible"),
            dropped_for_signal=req_int("dropped_for_signal"),
            dropped_for_return=req_int("dropped_for_return"),
            period_status=period_status,
        )


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """Per-date and total coverage counts - never a silent exclusion (§6, P19-4)."""

    per_date: tuple[DateCoverage, ...]
    total_resolved: int
    total_dropped_for_signal: int
    total_dropped_for_return: int
    total_undefined_periods: int

    def to_dict(self) -> dict[str, object]:
        return {
            "per_date": [d.to_dict() for d in self.per_date],
            "total_resolved": self.total_resolved,
            "total_dropped_for_signal": self.total_dropped_for_signal,
            "total_dropped_for_return": self.total_dropped_for_return,
            "total_undefined_periods": self.total_undefined_periods,
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
            total_resolved=req_int("total_resolved"),
            total_dropped_for_signal=req_int("total_dropped_for_signal"),
            total_dropped_for_return=req_int("total_dropped_for_return"),
            total_undefined_periods=req_int("total_undefined_periods"),
        )
