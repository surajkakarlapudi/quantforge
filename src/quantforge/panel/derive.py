"""Pure multi-period derivations over one filer's period-series (locked §3, §7, §8).

A derivation is a **pure, deterministic function of the cells of one filer's
period-series** — all resolved at the panel's single ``as_of`` (or single snapshot)
— so it introduces no new data and no new boundary and **cannot add look-ahead**
(every input cell was already boundary-eligible; §7, the same argument as the Phase
8 cross-sectional transforms). Included per Decision D3.

Four disciplines are absolute (locked §8; data-model Principle 8):

* **UNDEFINED-preserving.** Any ``UNDEFINED`` input period makes the derivation
  ``UNDEFINED`` — a growth rate needs both endpoints; a TTM needs four consecutive
  quarters. Never imputed, never carried-forward, never ``0``.
* **Exact arithmetic under the Phase 7 pinned context.** ``Decimal`` only, no
  ``float``; all arithmetic runs inside the caller-supplied
  :class:`decimal.Context` (precision 34, ``ROUND_HALF_EVEN``), already folded into
  ``metric_engine_version_id`` — so a derivation result is byte-reproducible.
* **Divide-by-zero fails to a value, never a blow-up.** ``growth`` with a zero prior
  value → ``UNDEFINED(DIVIDE_BY_ZERO)`` (exact ``Decimal == 0``), never ``Inf`` /
  ``NaN``.
* **Population = KNOWN cells only.** ``level_vs_history`` computes its statistic over
  the KNOWN cells of its window; ``UNDEFINED`` cells are excluded from the
  population and never fabricated to a mean/median.

A derivation is identified by a canonical ``derivation_id`` string (``"none"``,
``"growth"``, ``"ttm"``, ``"average_balance"``, or
``"level_vs_history:<stat>:<window>"``) that is hashed into ``panel_definition_id``
(§5). Each per-cell outcome records **which input periods it consumed** and, for an
``UNDEFINED`` derivation, **which input period made it undefined and why** (§6 zero
information loss). A period-kind mismatch (e.g. ``ttm`` over an ``INSTANT`` axis) is
a configuration defect and is raised by the engine, never a silent cell (§8).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from enum import StrEnum

from quantforge.canonical.numeric import canonical_decimal_str
from quantforge.metrics.model import MetricStatus, UndefinedReason
from quantforge.panel.errors import PanelConfigurationError
from quantforge.xbrl.contexts import PeriodType

__all__ = [
    "Derivation",
    "DerivationKind",
    "DerivedCell",
    "HistoryStat",
    "SeriesPoint",
]

#: The number of consecutive quarters a trailing-twelve-months sum consumes.
_TTM_WINDOW = 4


class DerivationKind(StrEnum):
    """The closed set of supported multi-period derivations (D3, §3)."""

    NONE = "none"
    GROWTH = "growth"
    TTM = "ttm"
    AVERAGE_BALANCE = "average_balance"
    LEVEL_VS_HISTORY = "level_vs_history"


class HistoryStat(StrEnum):
    """The statistic ``level_vs_history`` compares the current level against (§3)."""

    MEDIAN = "median"
    MIN = "min"
    MAX = "max"


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    """One period's resolved metric, the raw input to a derivation.

    ``value`` is the exact :class:`~decimal.Decimal` for a ``KNOWN`` cell, ``None``
    for an ``UNDEFINED`` one — so an ``UNDEFINED`` input is visible to (and preserved
    by) every derivation, never silently treated as zero.
    """

    period_key: str
    is_known: bool
    value: Decimal | None


@dataclass(frozen=True, slots=True)
class DerivedCell:
    """The per-coordinate derivation outcome + its input provenance (§6).

    ``status`` is ``KNOWN`` with a serialized ``value_numeric_str`` when the
    derivation computed a value, else ``UNDEFINED`` with the ``reason`` and the
    ``undefined_input_period_key`` that made it so (``None`` when the failure is
    "not enough history" rather than one bad period). ``consumed_period_keys`` names
    every input period the derivation read, in order.
    """

    status: MetricStatus
    value_numeric_str: str | None
    consumed_period_keys: tuple[str, ...]
    reason: UndefinedReason | None
    undefined_input_period_key: str | None

    @classmethod
    def known(cls, value: Decimal, consumed: tuple[str, ...]) -> DerivedCell:
        return cls(
            status=MetricStatus.KNOWN,
            value_numeric_str=canonical_decimal_str(value),
            consumed_period_keys=consumed,
            reason=None,
            undefined_input_period_key=None,
        )

    @classmethod
    def undefined(
        cls,
        reason: UndefinedReason,
        consumed: tuple[str, ...],
        *,
        input_period_key: str | None = None,
    ) -> DerivedCell:
        return cls(
            status=MetricStatus.UNDEFINED,
            value_numeric_str=None,
            consumed_period_keys=consumed,
            reason=reason,
            undefined_input_period_key=input_period_key,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "value_numeric": self.value_numeric_str,
            "consumed_period_keys": list(self.consumed_period_keys),
            "reason": self.reason.value if self.reason is not None else None,
            "undefined_input_period_key": self.undefined_input_period_key,
        }


@dataclass(frozen=True, slots=True)
class Derivation:
    """A pure multi-period derivation, identified by a canonical ``derivation_id``.

    Construct via the factory classmethods (:meth:`none`, :meth:`growth`,
    :meth:`ttm`, :meth:`average_balance`, :meth:`level_vs_history`) so the params and
    the ``derivation_id`` can never drift apart. :meth:`apply` maps one filer's
    ordered :class:`SeriesPoint` list (in axis order) to an aligned list of
    :class:`DerivedCell`, one per period.
    """

    kind: DerivationKind
    window: int | None = None
    stat: HistoryStat | None = None

    # -- factories -----------------------------------------------------------

    @classmethod
    def none(cls) -> Derivation:
        """The identity: no derivation — the panel is the raw metric series (§3)."""
        return cls(DerivationKind.NONE)

    @classmethod
    def growth(cls) -> Derivation:
        """Period-over-period growth ``(x_T - x_{T-1}) / x_{T-1}`` (§3)."""
        return cls(DerivationKind.GROWTH)

    @classmethod
    def ttm(cls) -> Derivation:
        """Trailing-twelve-months: the sum of 4 consecutive DURATION quarters (§3)."""
        return cls(DerivationKind.TTM)

    @classmethod
    def average_balance(cls) -> Derivation:
        """Two-point average balance ``(x_T + x_{T-1}) / 2`` (§3)."""
        return cls(DerivationKind.AVERAGE_BALANCE)

    @classmethod
    def level_vs_history(
        cls, *, window: int, stat: HistoryStat = HistoryStat.MEDIAN
    ) -> Derivation:
        """Current level minus the ``stat`` of the prior ``window`` KNOWN cells (§3).

        ``x_T - stat(prior window)`` where ``stat`` is the median / min / max over
        the KNOWN cells of the ``window`` periods immediately preceding ``T``. A
        difference (never a ratio), so it introduces no second divide-by-zero path;
        the population excludes ``UNDEFINED`` cells (never imputed). ``window`` must
        be a positive integer -- a non-positive window is a configuration bug.
        """
        if window <= 0:
            raise PanelConfigurationError(
                f"level_vs_history window must be a positive integer; got {window}"
            )
        return cls(DerivationKind.LEVEL_VS_HISTORY, window=window, stat=stat)

    # -- identity ------------------------------------------------------------

    @property
    def derivation_id(self) -> str:
        """The canonical id hashed into ``panel_definition_id`` (§5)."""
        if self.kind is DerivationKind.LEVEL_VS_HISTORY:
            assert self.stat is not None and self.window is not None
            return f"{self.kind.value}:{self.stat.value}:{self.window}"
        return self.kind.value

    def required_period_type(self) -> PeriodType | None:
        """The axis ``period_type`` this derivation requires, or ``None`` for any.

        ``ttm`` sums flow quarters, so it requires a ``DURATION`` axis; the engine
        raises :class:`PanelConfigurationError` on a mismatch before evaluating (§8).
        """
        if self.kind is DerivationKind.TTM:
            return PeriodType.DURATION
        return None

    # -- application ---------------------------------------------------------

    def apply(self, series: list[SeriesPoint], context: Context) -> list[DerivedCell]:
        """Apply this derivation to one filer's ordered period-series (§3, §7).

        ``series`` is in axis order (the §2 total order). Returns one
        :class:`DerivedCell` per point, aligned by index. All arithmetic runs inside
        the pinned ``context`` so results are byte-reproducible. ``NONE`` is not a
        valid argument here — the engine skips derivation entirely for ``none``.
        """
        if self.kind is DerivationKind.NONE:
            # The engine never calls apply() for the identity derivation.
            raise PanelConfigurationError(
                "the 'none' derivation has no per-cell output; the engine must skip it"
            )
        with localcontext(context):
            if self.kind is DerivationKind.GROWTH:
                return [self._growth(series, i) for i in range(len(series))]
            if self.kind is DerivationKind.AVERAGE_BALANCE:
                return [self._average_balance(series, i) for i in range(len(series))]
            if self.kind is DerivationKind.TTM:
                return [self._ttm(series, i) for i in range(len(series))]
            if self.kind is DerivationKind.LEVEL_VS_HISTORY:
                return [self._level_vs_history(series, i) for i in range(len(series))]
        # DerivationKind is closed; an unknown kind is our bug.
        raise PanelConfigurationError(f"unknown derivation kind {self.kind!r}")

    # -- per-kind ------------------------------------------------------------

    def _growth(self, series: list[SeriesPoint], i: int) -> DerivedCell:
        curr = series[i]
        if i == 0:
            # No prior period exists — insufficient history, not a bad input period.
            return DerivedCell.undefined(
                UndefinedReason.MISSING_INPUT, (curr.period_key,)
            )
        prev = series[i - 1]
        consumed = (prev.period_key, curr.period_key)
        if not curr.is_known or curr.value is None:
            return DerivedCell.undefined(
                UndefinedReason.MISSING_INPUT,
                consumed,
                input_period_key=curr.period_key,
            )
        if not prev.is_known or prev.value is None:
            return DerivedCell.undefined(
                UndefinedReason.MISSING_INPUT,
                consumed,
                input_period_key=prev.period_key,
            )
        if prev.value == 0:
            # Exact Decimal zero prior value — a growth rate is undefined, never Inf.
            return DerivedCell.undefined(
                UndefinedReason.DIVIDE_BY_ZERO,
                consumed,
                input_period_key=prev.period_key,
            )
        value = (curr.value - prev.value) / prev.value
        return DerivedCell.known(value, consumed)

    def _average_balance(self, series: list[SeriesPoint], i: int) -> DerivedCell:
        curr = series[i]
        if i == 0:
            return DerivedCell.undefined(
                UndefinedReason.MISSING_INPUT, (curr.period_key,)
            )
        prev = series[i - 1]
        consumed = (prev.period_key, curr.period_key)
        if not curr.is_known or curr.value is None:
            return DerivedCell.undefined(
                UndefinedReason.MISSING_INPUT,
                consumed,
                input_period_key=curr.period_key,
            )
        if not prev.is_known or prev.value is None:
            return DerivedCell.undefined(
                UndefinedReason.MISSING_INPUT,
                consumed,
                input_period_key=prev.period_key,
            )
        value = (curr.value + prev.value) / Decimal(2)
        return DerivedCell.known(value, consumed)

    def _ttm(self, series: list[SeriesPoint], i: int) -> DerivedCell:
        if i < _TTM_WINDOW - 1:
            # Fewer than four periods precede-or-include T — insufficient history.
            consumed = tuple(p.period_key for p in series[: i + 1])
            return DerivedCell.undefined(UndefinedReason.MISSING_INPUT, consumed)
        window = series[i - _TTM_WINDOW + 1 : i + 1]
        consumed = tuple(p.period_key for p in window)
        total = Decimal(0)
        for point in window:
            if not point.is_known or point.value is None:
                return DerivedCell.undefined(
                    UndefinedReason.MISSING_INPUT,
                    consumed,
                    input_period_key=point.period_key,
                )
            total += point.value
        return DerivedCell.known(total, consumed)

    def _level_vs_history(self, series: list[SeriesPoint], i: int) -> DerivedCell:
        assert self.window is not None and self.stat is not None
        curr = series[i]
        if i < self.window:
            # Fewer than `window` prior periods exist — insufficient history.
            consumed = tuple(p.period_key for p in series[: i + 1])
            return DerivedCell.undefined(UndefinedReason.MISSING_INPUT, consumed)
        prior = series[i - self.window : i]
        consumed = (*(p.period_key for p in prior), curr.period_key)
        if not curr.is_known or curr.value is None:
            return DerivedCell.undefined(
                UndefinedReason.MISSING_INPUT,
                consumed,
                input_period_key=curr.period_key,
            )
        population = [p.value for p in prior if p.is_known and p.value is not None]
        if not population:
            # Every prior period in the window was UNDEFINED — no population.
            return DerivedCell.undefined(UndefinedReason.MISSING_INPUT, consumed)
        reference = _statistic(population, self.stat)
        return DerivedCell.known(curr.value - reference, consumed)


def _statistic(population: list[Decimal], stat: HistoryStat) -> Decimal:
    """The ``stat`` over a non-empty KNOWN population, exact under the live context.

    Assumes ``localcontext`` is already active (set by :meth:`Derivation.apply`), so
    the median's division rounds under the pinned context, not the ambient one.
    """
    if stat is HistoryStat.MIN:
        return min(population)
    if stat is HistoryStat.MAX:
        return max(population)
    # MEDIAN: middle value (odd) or the mean of the two middle values (even).
    ordered = sorted(population)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal(2)
