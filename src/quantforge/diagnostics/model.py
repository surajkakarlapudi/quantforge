"""The signal-diagnostics result vocabulary: status, reasons, methods, nested records.

A **signal-diagnostics record** is a set of per-date and summarised cross-sectional
statistics measuring whether an as-of-``T`` signal predicts a member's realized
*forward* return over a horizon. This module defines the fail-closed result vocabulary
those statistics live in, plus the nested records that carry them:

* :class:`DiagnosticStatus` / :class:`DiagnosticUndefinedReason` — the fail-closed cell
  vocabulary. ``UNDEFINED`` is a first-class value carrying *why* a statistic could not
  be computed, never an exception, never ``0`` / ``NaN`` / ``Inf`` (§7, D11). Mirrors
  Phase 15's :class:`~quantforge.analytics.model.AnalyticsStatus` /
  :class:`~quantforge.analytics.model.AnalyticsUndefinedReason` exactly.
* :class:`StatValue` — the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. Never a bare float, never silently omitted.
* :class:`ICMethod` — the closed set of Information-Coefficient methods.
* :class:`PerDateIC`, :class:`QuantileProfile`, :class:`ICSummary`,
  :class:`ICMethodSummary`, :class:`CoverageSummary`, :class:`DateCoverage` — the
  nested, deterministically serializable records the sealed :class:`SignalDiagnostics`
  holds.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CoverageSummary",
    "DateCoverage",
    "DiagnosticStatus",
    "DiagnosticUndefinedReason",
    "ICMethod",
    "ICMethodSummary",
    "ICSummary",
    "PerDateIC",
    "QuantileProfile",
    "StatValue",
]


class DiagnosticStatus(StrEnum):
    """Whether a statistic resolved to a value (``KNOWN``) or not (``UNDEFINED``)."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class DiagnosticUndefinedReason(StrEnum):
    """Why a statistic is ``UNDEFINED`` — fail-closed, never fabricated (§7, D11).

    Every reason preserves information: it records the *absence* of a computable value
    (too few pairs, a zero denominator, an empty bucket, no valid dates) rather than
    inventing one. A zero denominator is never a divide-by-zero — it is one of these
    reasons.
    """

    #: A date with fewer than two eligible (signal, forward-return) pairs — an IC needs
    #: at least two points, so it is undefined for that date.
    INSUFFICIENT_PAIRS = "insufficient_pairs"
    #: Pearson IC (or an IC summary's dispersion) with a constant series on the signal
    #: side — population variance is zero, so the correlation ratio is ``0/0`` and
    #: genuinely undefined. Never divided.
    ZERO_SIGNAL_VARIANCE = "zero_signal_variance"
    #: Pearson IC (or an IC summary's dispersion) with a constant series on the
    #: forward-return side — population variance is zero, so the ratio is undefined.
    ZERO_RETURN_VARIANCE = "zero_return_variance"
    #: A quantile bucket with no members (possible when ``n < q``) — there is no forward
    #: return to average, so the bucket mean (and any spread touching it) is undefined.
    EMPTY_BUCKET = "empty_bucket"
    #: An IC-summary cell for a method that was KNOWN on no evaluation date — there is
    #: no IC series to summarise.
    NO_VALID_DATES = "no_valid_dates"


class ICMethod(StrEnum):
    """The closed set of Information-Coefficient methods (D6)."""

    #: Pearson product-moment correlation of the raw signal and forward-return vectors.
    PEARSON = "pearson"
    #: Spearman rank correlation (Pearson of the average-rank vectors).
    SPEARMAN = "spearman"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (D11).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.1234")`` — a computed decimal string (canonicalized by the
      compute layer via ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(DiagnosticUndefinedReason.INSUFFICIENT_PAIRS)`` — a
      statistic genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    diagnostics analogue of Phase 15's ``StatValue``.
    """

    status: DiagnosticStatus
    value: str | None = None
    reason: DiagnosticUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is DiagnosticStatus.KNOWN:
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
        return cls(status=DiagnosticStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: DiagnosticUndefinedReason) -> StatValue:
        """An UNDEFINED cell recording why the statistic could not be computed."""
        return cls(status=DiagnosticStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only — so
        the two are impossible to confuse and the serialized bytes are minimal.
        """
        if self.status is DiagnosticStatus.KNOWN:
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
            status = DiagnosticStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StatValue status {status_raw!r}") from exc
        if status is DiagnosticStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StatValue must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StatValue must carry a reason string")
        try:
            reason = DiagnosticUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown DiagnosticUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)


def _stat_list(cells: tuple[StatValue, ...]) -> list[dict[str, object]]:
    """Serialize an ordered tuple of cells (helper, deterministic)."""
    return [c.to_dict() for c in cells]


def _stat_tuple(raw: object) -> tuple[StatValue, ...]:
    """Reconstruct an ordered tuple of cells, fail-closed on a malformed list."""
    if not isinstance(raw, list):
        raise ValueError("expected a list of StatValue cells")
    out: list[StatValue] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each StatValue cell must be an object")
        out.append(StatValue.from_dict(item))
    return tuple(out)


def _method_pairs(pairs: tuple[tuple[str, StatValue], ...]) -> list[dict[str, object]]:
    """Serialize ``(method, StatValue)`` pairs as an ordered list (deterministic)."""
    return [{"method": m, "ic": v.to_dict()} for m, v in pairs]


def _method_pairs_from(raw: object) -> tuple[tuple[str, StatValue], ...]:
    if not isinstance(raw, list):
        raise ValueError("expected a list of (method, ic) pairs")
    out: list[tuple[str, StatValue]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each (method, ic) pair must be an object")
        method = item.get("method")
        ic_raw = item.get("ic")
        if not isinstance(method, str) or not isinstance(ic_raw, dict):
            raise ValueError("a (method, ic) pair needs a string method and an ic cell")
        out.append((method, StatValue.from_dict(ic_raw)))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class PerDateIC:
    """One evaluation date's cross-sectional diagnostics (§3.2).

    ``ic`` holds the per-method Information Coefficient (sorted by method), each a
    :class:`StatValue`. ``bucket_means`` holds the ``q`` quantile-bucket mean forward
    returns (bucket ``0`` .. ``q-1``); ``top_minus_bottom_spread`` is bucket ``q-1``
    minus bucket ``0``. ``n_pairs`` is the count of eligible (signal, forward-return)
    pairs at this date.
    """

    as_of: str
    n_pairs: int
    ic: tuple[tuple[str, StatValue], ...]
    bucket_means: tuple[StatValue, ...]
    top_minus_bottom_spread: StatValue

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "n_pairs": self.n_pairs,
            "ic": _method_pairs(self.ic),
            "bucket_means": _stat_list(self.bucket_means),
            "top_minus_bottom_spread": self.top_minus_bottom_spread.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PerDateIC:
        as_of = raw.get("as_of")
        n_pairs = raw.get("n_pairs")
        spread = raw.get("top_minus_bottom_spread")
        if not isinstance(as_of, str):
            raise ValueError("PerDateIC.as_of must be a string")
        if not isinstance(n_pairs, int):
            raise ValueError("PerDateIC.n_pairs must be an int")
        if not isinstance(spread, dict):
            raise ValueError("PerDateIC.top_minus_bottom_spread must be an object")
        return cls(
            as_of=as_of,
            n_pairs=n_pairs,
            ic=_method_pairs_from(raw.get("ic")),
            bucket_means=_stat_tuple(raw.get("bucket_means")),
            top_minus_bottom_spread=StatValue.from_dict(spread),
        )


@dataclass(frozen=True, slots=True)
class QuantileProfile:
    """The across-date mean forward return per bucket, plus mean spread (§3.2)."""

    bucket_means: tuple[StatValue, ...]
    mean_spread: StatValue

    def to_dict(self) -> dict[str, object]:
        return {
            "bucket_means": _stat_list(self.bucket_means),
            "mean_spread": self.mean_spread.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> QuantileProfile:
        spread = raw.get("mean_spread")
        if not isinstance(spread, dict):
            raise ValueError("QuantileProfile.mean_spread must be an object")
        return cls(
            bucket_means=_stat_tuple(raw.get("bucket_means")),
            mean_spread=StatValue.from_dict(spread),
        )


@dataclass(frozen=True, slots=True)
class ICMethodSummary:
    """The summarised IC series for one method over the valid evaluation dates
    (§3.2)."""

    mean_ic: StatValue
    ic_std: StatValue
    ic_information_ratio: StatValue
    ic_t_stat: StatValue
    hit_rate: StatValue
    n_valid_dates: int

    def to_dict(self) -> dict[str, object]:
        return {
            "mean_ic": self.mean_ic.to_dict(),
            "ic_std": self.ic_std.to_dict(),
            "ic_information_ratio": self.ic_information_ratio.to_dict(),
            "ic_t_stat": self.ic_t_stat.to_dict(),
            "hit_rate": self.hit_rate.to_dict(),
            "n_valid_dates": self.n_valid_dates,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ICMethodSummary:
        n_valid = raw.get("n_valid_dates")
        if not isinstance(n_valid, int):
            raise ValueError("ICMethodSummary.n_valid_dates must be an int")

        def cell(key: str) -> StatValue:
            v = raw.get(key)
            if not isinstance(v, dict):
                raise ValueError(f"ICMethodSummary.{key} must be an object")
            return StatValue.from_dict(v)

        return cls(
            mean_ic=cell("mean_ic"),
            ic_std=cell("ic_std"),
            ic_information_ratio=cell("ic_information_ratio"),
            ic_t_stat=cell("ic_t_stat"),
            hit_rate=cell("hit_rate"),
            n_valid_dates=n_valid,
        )


@dataclass(frozen=True, slots=True)
class ICSummary:
    """The per-method IC summaries (sorted by method) (§3.2)."""

    per_method: tuple[tuple[str, ICMethodSummary], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "per_method": [
                {"method": m, "summary": s.to_dict()} for m, s in self.per_method
            ]
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ICSummary:
        per_method_raw = raw.get("per_method")
        if not isinstance(per_method_raw, list):
            raise ValueError("ICSummary.per_method must be a list")
        out: list[tuple[str, ICMethodSummary]] = []
        for item in per_method_raw:
            if not isinstance(item, dict):
                raise ValueError("each ICSummary entry must be an object")
            method = item.get("method")
            summary = item.get("summary")
            if not isinstance(method, str) or not isinstance(summary, dict):
                raise ValueError("an ICSummary entry needs a method and a summary")
            out.append((method, ICMethodSummary.from_dict(summary)))
        return cls(per_method=tuple(out))


@dataclass(frozen=True, slots=True)
class DateCoverage:
    """One evaluation date's coverage breakdown — exclusions are auditable (§6,
    SD-4)."""

    as_of: str
    resolved_members: int
    eligible: int
    dropped_for_signal: int
    dropped_for_return: int

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "resolved_members": self.resolved_members,
            "eligible": self.eligible,
            "dropped_for_signal": self.dropped_for_signal,
            "dropped_for_return": self.dropped_for_return,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> DateCoverage:
        def req_int(key: str) -> int:
            v = raw.get(key)
            if not isinstance(v, int):
                raise ValueError(f"DateCoverage.{key} must be an int")
            return v

        as_of = raw.get("as_of")
        if not isinstance(as_of, str):
            raise ValueError("DateCoverage.as_of must be a string")
        return cls(
            as_of=as_of,
            resolved_members=req_int("resolved_members"),
            eligible=req_int("eligible"),
            dropped_for_signal=req_int("dropped_for_signal"),
            dropped_for_return=req_int("dropped_for_return"),
        )


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """Per-date and total coverage counts — never a silent exclusion (§6, SD-4)."""

    per_date: tuple[DateCoverage, ...]
    total_eligible: int
    total_dropped_for_signal: int
    total_dropped_for_return: int

    def to_dict(self) -> dict[str, object]:
        return {
            "per_date": [d.to_dict() for d in self.per_date],
            "total_eligible": self.total_eligible,
            "total_dropped_for_signal": self.total_dropped_for_signal,
            "total_dropped_for_return": self.total_dropped_for_return,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CoverageSummary:
        per_date_raw = raw.get("per_date")
        if not isinstance(per_date_raw, list):
            raise ValueError("CoverageSummary.per_date must be a list")

        def req_int(key: str) -> int:
            v = raw.get(key)
            if not isinstance(v, int):
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
        )
