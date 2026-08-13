"""The calibration-significance vocabulary: statuses, reasons, direction, stat cell.

A **calibration significance** reads, from one sealed
:class:`~quantforge.calibration.result.RiskForecastCalibration`, the aggregate
``mean_variance_ratio`` and population ``variance_ratio_dispersion`` over its
calibratable windows and their count ``n_calibratable``, and asks the question the
calibration never answers directly - *is the mean variance ratio significantly
different from ``1`` (perfect calibration on average)?* This module defines the
fail-closed vocabulary those numbers live in:

* :class:`SignificanceStatus` - whether the test was run (``TESTED``, a KNOWN
  ``t_statistic`` / ``p_value``) or is genuinely undefined for the data (``UNDEFINED``,
  CS-2/CS-3).
* :class:`SignificanceUndefinedReason` - why the test (or a cell) is UNDEFINED: the
  source calibration is not defensible so there is no mean / dispersion to test
  (``SOURCE_NOT_CALIBRATED``); or the per-window variance ratios have zero dispersion so
  the standard error is zero and ``t`` / ``p`` do not exist (``ZERO_RATIO_DISPERSION``).
* :class:`BiasDirection` - the descriptive sign of the mis-calibration:
  ``UNDER_FORECAST`` (mean ``> 1``, realized variance exceeds predicted),
  ``OVER_FORECAST`` (mean ``< 1``), ``UNBIASED`` (mean ``== 1``). No significance; a
  pure descriptive read of the sealed mean.
* :class:`StatStatus` / :class:`SignificanceStat` - the UNDEFINED-preserving cell: a
  KNOWN decimal string **or** an UNDEFINED reason. Never a bare float, never silently
  omitted.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "BiasDirection",
    "SignificanceStat",
    "SignificanceStatus",
    "SignificanceUndefinedReason",
    "StatStatus",
]


class SignificanceStatus(StrEnum):
    """Whether the significance test was run or is genuinely undefined (CS-2/CS-3).

    ``TESTED`` when the source was CALIBRATED and the family had non-zero dispersion, so
    a KNOWN ``t_statistic`` / ``p_value`` exist; ``UNDEFINED`` (with a
    :class:`SignificanceUndefinedReason`) otherwise. A sealed significance always
    records its status honestly - the record seals either way, never raising for a data
    condition.
    """

    TESTED = "tested"
    UNDEFINED = "undefined"


class SignificanceUndefinedReason(StrEnum):
    """Why a significance cell / the roll-up status is UNDEFINED (CS-2/CS-3).

    A closed vocabulary, kept distinct so a reader can never confuse an undefined source
    with a degenerate (zero-dispersion) family.
    """

    #: The source :class:`~quantforge.calibration.result.RiskForecastCalibration` is not
    #: defensible - its ``calibration_status`` is UNDEFINED (fewer calibratable windows
    #: than the Phase-26 floor, or none at all), or its sealed ``mean_variance_ratio`` /
    #: ``variance_ratio_dispersion`` cell is not KNOWN. There is no mean / dispersion to
    #: test, so every significance cell is undefined. Recorded, never fabricated (CS-2).
    SOURCE_NOT_CALIBRATED = "source_not_calibrated"

    #: The per-window variance ratios have zero dispersion (all identical), so the
    #: standard error ``dispersion / sqrt(K)`` is zero and the ``t`` statistic /
    #: ``p`` value do not exist. The ``mean_variance_ratio`` and ``bias_direction`` stay
    #: KNOWN; ``t`` / ``p`` are UNDEFINED, never a divide-by-zero (CS-3).
    ZERO_RATIO_DISPERSION = "zero_ratio_dispersion"


class BiasDirection(StrEnum):
    """The descriptive sign of the risk model's mis-calibration (no significance).

    A pure descriptive read of the sealed mean variance ratio ``m`` against the null
    mean ``1``: ``UNDER_FORECAST`` when ``m > 1`` (realized variance exceeds predicted -
    the risk model *under*-forecasts risk), ``OVER_FORECAST`` when ``m < 1``,
    ``UNBIASED`` when ``m == 1``. Known whenever ``m`` is known (a CALIBRATED source);
    carries no p-value and asserts no significance.
    """

    UNDER_FORECAST = "under_forecast"
    OVER_FORECAST = "over_forecast"
    UNBIASED = "unbiased"


class StatStatus(StrEnum):
    """Whether a single :class:`SignificanceStat` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


@dataclass(frozen=True, slots=True)
class SignificanceStat:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (CS-3).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``SignificanceStat.known("2.13")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``SignificanceStat.undefined(SignificanceUndefinedReason.ZERO_RATIO_DISPERSION)``
      - a value genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    calibration-significance analogue of the calibration / MinTRL ``StatValue``.
    """

    status: StatStatus
    value: str | None = None
    reason: SignificanceUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is StatStatus.KNOWN:
            if not isinstance(self.value, str) or self.reason is not None:
                raise ValueError(
                    "a KNOWN SignificanceStat must carry a decimal-string value and no "
                    "reason"
                )
        else:  # UNDEFINED
            if self.reason is None or self.value is not None:
                raise ValueError(
                    "an UNDEFINED SignificanceStat must carry a reason and no value"
                )

    @classmethod
    def known(cls, value: str) -> SignificanceStat:
        """A KNOWN cell holding a canonical decimal string."""
        return cls(status=StatStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: SignificanceUndefinedReason) -> SignificanceStat:
        """An UNDEFINED cell recording why the value could not be computed."""
        return cls(status=StatStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only - so
        the two are impossible to confuse and the serialized bytes are minimal.
        """
        if self.status is StatStatus.KNOWN:
            return {"status": self.status.value, "value": self.value}
        assert self.reason is not None  # guaranteed by __post_init__
        return {"status": self.status.value, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> SignificanceStat:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed - the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("SignificanceStat.status must be a string")
        try:
            status = StatStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown SignificanceStat status {status_raw!r}") from exc
        if status is StatStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN SignificanceStat must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED SignificanceStat must carry a reason string")
        try:
            reason = SignificanceUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown SignificanceUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)
