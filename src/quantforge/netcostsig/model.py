"""The net-of-cost-significance vocabulary: statuses, reasons, direction, stat cell.

A **net-of-cost significance** reads, from one sealed
:class:`~quantforge.netcost.result.NetOfCostPerformance`, the aggregate after-cost mean
return ``net_mean`` and its population ``net_volatility`` over the realized net series,
and its period count ``n_periods``, and asks the question the net-of-cost record never
answers directly - *is the after-cost mean return significantly greater than ``0`` (a
real edge, not noise, given the realized sample length)?* This module defines the
fail-closed vocabulary those numbers live in:

* :class:`SignificanceStatus` - whether the test was run (``TESTED``, a KNOWN
  ``t_statistic`` / ``p_value``) or is genuinely undefined for the data (``UNDEFINED``,
  NS-2/NS-3).
* :class:`NetCostSigUndefinedReason` - why the test (or a cell) is UNDEFINED: the source
  net-of-cost record is not defensible so there is no net mean / volatility to test
  (``SOURCE_NOT_MEASURED``); or the net return series has zero population volatility so
  the standard error is zero and ``t`` / ``p`` do not exist (``ZERO_NET_VOLATILITY``).
* :class:`EdgeDirection` - the descriptive sign of the after-cost edge:
  ``PROFITABLE`` (mean ``> 0``, the strategy earns after costs), ``UNPROFITABLE``
  (mean ``< 0``), ``FLAT`` (mean ``== 0``). No significance; a pure descriptive read of
  the sealed net mean.
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
    "EdgeDirection",
    "NetCostSigUndefinedReason",
    "SignificanceStat",
    "SignificanceStatus",
    "StatStatus",
]


class SignificanceStatus(StrEnum):
    """Whether the significance test was run or is genuinely undefined (NS-2/NS-3).

    ``TESTED`` when the source was MEASURED and the net series had non-zero volatility,
    so a KNOWN ``t_statistic`` / ``p_value`` exist; ``UNDEFINED`` (with a
    :class:`NetCostSigUndefinedReason`) otherwise. A sealed significance always records
    its status honestly - the record seals either way, never raising for a data
    condition.
    """

    TESTED = "tested"
    UNDEFINED = "undefined"


class NetCostSigUndefinedReason(StrEnum):
    """Why a significance cell / the roll-up status is UNDEFINED (NS-2/NS-3).

    A closed vocabulary, kept distinct so a reader can never confuse an undefined source
    with a degenerate (zero-volatility) net series.
    """

    #: The source :class:`~quantforge.netcost.result.NetOfCostPerformance` is not
    #: defensible - its ``net_status`` is UNDEFINED (its net Sharpe was never formed),
    #: or its sealed ``net_mean`` / ``net_volatility`` cell is not KNOWN. There is no
    #: net mean / volatility to test, so every significance cell is undefined. Recorded,
    #: never fabricated (NS-2).
    SOURCE_NOT_MEASURED = "source_not_measured"

    #: The net return series has zero population volatility (every net period
    #: identical), so the standard error ``net_volatility / sqrt(n)`` is zero and the
    #: ``t`` statistic / ``p`` value do not exist. The ``net_mean`` and
    #: ``edge_direction`` stay KNOWN; ``t`` / ``p`` are UNDEFINED, never a
    #: divide-by-zero (NS-3). **Defensive / structurally unreachable** for a MEASURED
    #: source, whose KNOWN net Sharpe implies a positive net volatility.
    ZERO_NET_VOLATILITY = "zero_net_volatility"


class EdgeDirection(StrEnum):
    """The descriptive sign of the after-cost edge (no significance).

    A pure descriptive read of the sealed net mean return ``m`` against the null mean
    ``0``: ``PROFITABLE`` when ``m > 0`` (the strategy earns a positive return after
    paying to trade), ``UNPROFITABLE`` when ``m < 0``, ``FLAT`` when ``m == 0``. Known
    whenever ``m`` is known (a MEASURED source); carries no p-value and asserts no
    significance.
    """

    PROFITABLE = "profitable"
    UNPROFITABLE = "unprofitable"
    FLAT = "flat"


class StatStatus(StrEnum):
    """Whether a single :class:`SignificanceStat` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


@dataclass(frozen=True, slots=True)
class SignificanceStat:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (NS-3).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``SignificanceStat.known("2.13")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``SignificanceStat.undefined(NetCostSigUndefinedReason.ZERO_NET_VOLATILITY)``
      - a value genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    net-of-cost-significance analogue of the calibration-significance
    ``SignificanceStat``.
    """

    status: StatStatus
    value: str | None = None
    reason: NetCostSigUndefinedReason | None = None

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
    def undefined(cls, reason: NetCostSigUndefinedReason) -> SignificanceStat:
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
            reason = NetCostSigUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown NetCostSigUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)
