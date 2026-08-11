"""The factor-risk result vocabulary: status, reasons, nested records, labels.

A **factor-risk record** is the second-moment structure of an ordered set of *N* sealed
:class:`~quantforge.factorportfolio.result.FactorPortfolio` factor return series: the
per-factor mean and (population) volatility, the ``N x N`` population covariance matrix,
and the companion correlation matrix, all estimated over the complete-case common window
where every factor has a KNOWN return. This module defines the fail-closed result
vocabulary those statistics live in, plus the nested records that carry them:

* :class:`FactorRiskStatus` / :class:`FactorRiskUndefinedReason` - the fail-closed cell
  vocabulary. ``UNDEFINED`` is a first-class value carrying *why* a statistic could not
  be computed for the data (a correlation cell whose factor has zero volatility over the
  common window), never an exception, never ``0`` / ``NaN`` / ``Inf`` / a divide-by-zero
  (§12, FR-4). Mirrors Phase 17's / Phase 19's reason enums.
* :class:`StatValue` - the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. Never a bare float, never silently omitted.
* :class:`FactorMoment`, :class:`CovarianceCell`, :class:`CorrelationCell`,
  :class:`FactorCoverage`, :class:`CoverageSummary` - the nested, deterministically
  serializable records the sealed
  :class:`~quantforge.factorrisk.result.FactorRiskModel` holds. The matrices are stored
  as their **upper triangle** (``i <= j``); the lower triangle is implied by symmetry
  and
  never stored (D-TRIANGLE).
* :func:`factor_label` - the deterministic, name-free factor label keyed to a factor's
  position in the request (which fixes the matrix row/column order).

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CorrelationCell",
    "CovarianceCell",
    "CoverageSummary",
    "FactorCoverage",
    "FactorMoment",
    "FactorRiskStatus",
    "FactorRiskUndefinedReason",
    "StatValue",
    "factor_label",
]


class FactorRiskStatus(StrEnum):
    """Whether a statistic resolved to a value (``KNOWN``) or not (``UNDEFINED``)."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class FactorRiskUndefinedReason(StrEnum):
    """Why a statistic is ``UNDEFINED`` - fail-closed, never fabricated (§12, FR-4).

    Every reason preserves information: it records the *absence* of a computable value
    (a zero denominator in the correlation) rather than inventing one. A zero
    denominator is never a divide-by-zero - it is one of these reasons.
    """

    #: A correlation cell ``corr(i,j) = cov(i,j)/(vol_i·vol_j)`` where the volatility of
    #: factor ``i`` or factor ``j`` over the common window is exactly ``0`` - the
    #: denominator is zero, so the correlation is genuinely undefined. The factor's
    #: mean, its (zero) volatility, and every covariance cell involving it stay KNOWN;
    #: only the correlation cells that would divide by the zero volatility are
    #: UNDEFINED. Recorded,
    #: never divided.
    ZERO_VARIANCE = "zero_variance"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (FR-4).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.1234")`` - a computed decimal string (canonicalized by the
      compute layer via ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(FactorRiskUndefinedReason.ZERO_VARIANCE)`` - a statistic
      genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    factor-risk analogue of Phase 17's / Phase 19's ``StatValue``.
    """

    status: FactorRiskStatus
    value: str | None = None
    reason: FactorRiskUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is FactorRiskStatus.KNOWN:
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
        return cls(status=FactorRiskStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: FactorRiskUndefinedReason) -> StatValue:
        """An UNDEFINED cell recording why the statistic could not be computed."""
        return cls(status=FactorRiskStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only - so
        the two are impossible to confuse and the serialized bytes are minimal.
        """
        if self.status is FactorRiskStatus.KNOWN:
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
            status = FactorRiskStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StatValue status {status_raw!r}") from exc
        if status is FactorRiskStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StatValue must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StatValue must carry a reason string")
        try:
            reason = FactorRiskUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown FactorRiskUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)


def factor_label(index: int) -> str:
    """The deterministic label of the ``index``-th factor (0-based).

    ``factor_1``, ``factor_2``, ... in request order - a stable, name-free label keyed
    to the factor's position in the request (which fixes the matrix row/column order).
    The
    record's coverage summary maps each position back to its ``factor_portfolio_id`` for
    provenance, so the numeric label never loses information.
    """
    if index < 0:
        raise ValueError("factor index must be non-negative")
    return f"factor_{index + 1}"


@dataclass(frozen=True, slots=True)
class FactorMoment:
    """One factor's first- and second-moment scalars (§9).

    ``label`` is the name-free :func:`factor_label` for the factor's position;
    ``mean`` the time-series mean of its factor returns over the common window;
    ``volatility`` the per-period population standard deviation;
    ``annualized_volatility``
    the ``volatility·√periods_per_year`` scaling. Each moment is a :class:`StatValue`
    (KNOWN over a valid common window; the volatilities are KNOWN even at exactly
    ``0``).
    """

    label: str
    mean: StatValue
    volatility: StatValue
    annualized_volatility: StatValue

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "mean": self.mean.to_dict(),
            "volatility": self.volatility.to_dict(),
            "annualized_volatility": self.annualized_volatility.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FactorMoment:
        label = raw.get("label")
        if not isinstance(label, str):
            raise ValueError("FactorMoment.label must be a string")

        def cell(key: str) -> StatValue:
            v = raw.get(key)
            if not isinstance(v, dict):
                raise ValueError(f"FactorMoment.{key} must be an object")
            return StatValue.from_dict(v)

        return cls(
            label=label,
            mean=cell("mean"),
            volatility=cell("volatility"),
            annualized_volatility=cell("annualized_volatility"),
        )


@dataclass(frozen=True, slots=True)
class CovarianceCell:
    """One upper-triangle covariance entry ``(i, j, per_period, annualized)`` (§9).

    ``i`` / ``j`` are 0-based factor indices with ``i <= j`` (the matrix is symmetric,
    so only the upper triangle is stored - D-TRIANGLE). ``value`` is the per-period
    population covariance ``(1/M)·Σ(f_i-mean_i)(f_j-mean_j)``; ``annualized`` the
    ``value·periods_per_year`` scaling. A covariance is always defined over a common
    window of ``M >= 2`` observations, so both cells are KNOWN.
    """

    i: int
    j: int
    value: StatValue
    annualized: StatValue

    def to_dict(self) -> dict[str, object]:
        return {
            "i": self.i,
            "j": self.j,
            "value": self.value.to_dict(),
            "annualized": self.annualized.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CovarianceCell:
        return cls(
            i=_req_index(raw, "i"),
            j=_req_index(raw, "j"),
            value=_req_cell(raw, "value", "CovarianceCell"),
            annualized=_req_cell(raw, "annualized", "CovarianceCell"),
        )


@dataclass(frozen=True, slots=True)
class CorrelationCell:
    """One upper-triangle correlation entry ``(i, j, value)`` (§9).

    ``i`` / ``j`` are 0-based factor indices with ``i <= j`` (upper triangle only).
    ``value`` is ``cov(i,j)/(vol_i·vol_j)`` - a :class:`StatValue` that is UNDEFINED
    ``ZERO_VARIANCE`` when either factor's volatility over the common window is exactly
    ``0`` (never a divide-by-zero); the diagonal ``corr(i,i)`` of a positive-variance
    factor is a KNOWN ``1``.
    """

    i: int
    j: int
    value: StatValue

    def to_dict(self) -> dict[str, object]:
        return {"i": self.i, "j": self.j, "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CorrelationCell:
        return cls(
            i=_req_index(raw, "i"),
            j=_req_index(raw, "j"),
            value=_req_cell(raw, "value", "CorrelationCell"),
        )


@dataclass(frozen=True, slots=True)
class FactorCoverage:
    """One factor's coverage breakdown - audit metadata, not folded (§9, FR-4).

    ``label`` the name-free position label; ``factor_portfolio_id`` the sealed input's
    id (provenance); ``available`` the number of KNOWN per-period factor returns the
    input carried; ``used`` the number that survived complete-case alignment onto the
    common estimation window (equal for every factor - it is the common ``M`` - but
    stored per factor so a reader sees how much each contributed vs how much aligned).
    """

    label: str
    factor_portfolio_id: str
    available: int
    used: int

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "factor_portfolio_id": self.factor_portfolio_id,
            "available": self.available,
            "used": self.used,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FactorCoverage:
        label = raw.get("label")
        factor_portfolio_id = raw.get("factor_portfolio_id")
        if not isinstance(label, str):
            raise ValueError("FactorCoverage.label must be a string")
        if not isinstance(factor_portfolio_id, str):
            raise ValueError("FactorCoverage.factor_portfolio_id must be a string")
        return cls(
            label=label,
            factor_portfolio_id=factor_portfolio_id,
            available=_req_count(raw, "available"),
            used=_req_count(raw, "used"),
        )


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """Per-factor coverage + the aligned window - never a silent exclusion (§9, FR-4).

    ``per_factor`` the ordered per-factor coverage; ``aligned_periods`` the common
    complete-case window size ``M`` the moments were estimated over;
    ``dropped_for_alignment`` the total number of per-factor KNOWN returns that fell
    outside the common window (``Σ available - N·M``). Audit metadata; **not** folded
    into ``result_hash`` (it is fully determined by the inputs).
    """

    per_factor: tuple[FactorCoverage, ...]
    aligned_periods: int
    dropped_for_alignment: int

    def to_dict(self) -> dict[str, object]:
        return {
            "per_factor": [f.to_dict() for f in self.per_factor],
            "aligned_periods": self.aligned_periods,
            "dropped_for_alignment": self.dropped_for_alignment,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CoverageSummary:
        per_factor_raw = raw.get("per_factor")
        if not isinstance(per_factor_raw, list):
            raise ValueError("CoverageSummary.per_factor must be a list")
        per_factor = tuple(
            FactorCoverage.from_dict(f) for f in per_factor_raw if isinstance(f, dict)
        )
        if len(per_factor) != len(per_factor_raw):
            raise ValueError("each CoverageSummary.per_factor entry must be an object")
        return cls(
            per_factor=per_factor,
            aligned_periods=_req_count(raw, "aligned_periods"),
            dropped_for_alignment=_req_count(raw, "dropped_for_alignment"),
        )


# -- shared fail-closed decode helpers ---------------------------------------


def _req_index(raw: dict[str, object], key: str) -> int:
    v = raw.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise ValueError(f"{key} must be a non-negative int")
    return v


def _req_count(raw: dict[str, object], key: str) -> int:
    v = raw.get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        raise ValueError(f"{key} must be an int")
    return v


def _req_cell(raw: dict[str, object], key: str, what: str) -> StatValue:
    v = raw.get(key)
    if not isinstance(v, dict):
        raise ValueError(f"{what}.{key} must be an object")
    return StatValue.from_dict(v)
