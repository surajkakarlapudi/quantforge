"""Deterministic ranking & comparison of sealed backtests (locked §3.4, §5, §6, D1).

The comparison half of comparative research (locked D1): a
:class:`BacktestComparison` ranks a set of already-sealed
:class:`~quantforge.backtest.result.BacktestResult`s by a chosen performance statistic
and surfaces the ordering, exactly as
:class:`~quantforge.universe.analysis.UniverseComparison` diffs two universes. It is the
natural read-side of an experiment: hand it an
experiment's children (or any set of backtest ids) and it tells you which won, by which
statistic, in what order — deterministically, with full provenance.

It computes **no** new statistic. It reads the v1
:class:`~quantforge.backtest.stats.PerformanceStatistics` the Phase 12 engine already
sealed, selects one field, and ranks by its :class:`~decimal.Decimal` value. Everything
is a frozen value with a deterministic ``to_dict``: no wall-clock, RNG, or set-iteration
dependence; ties break by ``backtest_id`` for a total order.

Fail-closed and fail-surfaced follow Phase 12's split exactly (locked §6):

* A **data/research condition** is surfaced, never raised. A member whose chosen
  statistic is not a finite decimal is recorded in :attr:`excluded` (with a reason) and
  left out of the ranking, never guessed. Members built under different **corpus pins**
  are still ranked (the statistics are numbers), but :attr:`pin_mismatch` flags it so a
  researcher is never misled into comparing unlike corpora silently — the mirror of
  ``UniverseComparison.mode_mismatch``.
* A **configuration/consistency defect** is raised. An unknown ``statistic``, an
  ``order`` that is neither ``descending``/``ascending``, a member id absent from the
  sidecar, or members computed under **mixed engine versions** (incommensurable
  statistics) is a
  :class:`~quantforge.experiment.errors.ExperimentConfigurationError` /
  :class:`~quantforge.experiment.errors.ExperimentConsistencyError` — a raised error
  always beats a wrong comparison.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.backtest.result import BacktestResult
from quantforge.experiment.errors import (
    ExperimentConfigurationError,
    ExperimentConsistencyError,
)
from quantforge.experiment.identity import comparison_id as _comparison_id
from quantforge.experiment.identity import (
    comparison_version_id as _comparison_version_id,
)
from quantforge.experiment.result import ExperimentResult
from quantforge.factors.store import ResearchResultStore

__all__ = ["RANKABLE_STATISTICS", "BacktestComparison", "ComparisonEntry"]

_ORDER_DESCENDING = "descending"
_ORDER_ASCENDING = "ascending"
_ORDERS = frozenset({_ORDER_DESCENDING, _ORDER_ASCENDING})

#: The v1 rankable statistics — the numeric fields of the sealed
#: :class:`~quantforge.backtest.stats.PerformanceStatistics` (locked §3.4). ``periods``
#: and ``period_returns`` are excluded: a count and a vector are not a scalar ranking
#: key. A statistic outside this closed set fails closed, never silently ignored.
RANKABLE_STATISTICS: frozenset[str] = frozenset(
    {
        "initial_equity",
        "final_equity",
        "peak_equity",
        "cumulative_return",
        "mean_period_return",
        "volatility",
        "sharpe",
        "max_drawdown",
        "mean_turnover",
    }
)

_REASON_UNDEFINED_STATISTIC = "statistic_not_finite_decimal"


@dataclass(frozen=True, slots=True)
class ComparisonEntry:
    """One ranked member of a comparison — a backtest and its statistic value (§3.4).

    ``rank`` is 1-based over the *included* members (best first under the chosen order);
    ties on the statistic value share the ranking key but are ordered by ``backtest_id``
    for a total order, and each still gets a distinct successive ``rank``. ``value`` is
    the canonical decimal string of the ranked statistic, carried verbatim from the
    sealed result. ``dataset_version_id`` / ``market_dataset_version_id`` are the
    member's two corpus pins, surfaced so a :attr:`~BacktestComparison.pin_mismatch` is
    auditable per member.
    """

    rank: int
    backtest_id: str
    value: str
    dataset_version_id: str
    market_dataset_version_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "backtest_id": self.backtest_id,
            "value": self.value,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
        }


@dataclass(frozen=True, slots=True)
class BacktestComparison:
    """A deterministic ranking of sealed backtests by one performance statistic (§3.4).

    Reduces a set of :class:`~quantforge.backtest.result.BacktestResult`s to their
    chosen-statistic values and ranks them under ``order``. :attr:`entries` is the
    ranked, included members (best first, ties broken by ``backtest_id``);
    :attr:`excluded` names any member whose statistic was not a finite decimal, with a
    reason (surfaced, never guessed). :attr:`pin_mismatch` flags members built under
    differing corpus pins (the ranking still stands — statistics are numbers — but the
    difference is surfaced, mirroring ``UniverseComparison.mode_mismatch``).

    Build via :meth:`of_results` (from in-hand results), :meth:`of_result_ids` (read
    from the shared sidecar), or :meth:`of_experiment` (rank an experiment's children).
    """

    comparison_id: str
    comparison_version_id: str
    statistic_key: str
    order: str
    entries: tuple[ComparisonEntry, ...]
    excluded: tuple[tuple[str, str], ...]
    dataset_version_ids: tuple[str, ...]
    market_dataset_version_ids: tuple[str, ...]

    # -- constructors --------------------------------------------------------

    @classmethod
    def of_results(
        cls,
        results: Iterable[BacktestResult],
        *,
        statistic: str,
        order: str = _ORDER_DESCENDING,
    ) -> BacktestComparison:
        """Rank in-hand sealed results by ``statistic`` under ``order`` (§3.4).

        The core constructor. Validates the ranking rule (``statistic`` in the closed
        v1 set, ``order`` a known direction), fails closed on members built under mixed
        engine versions (their statistics are incommensurable), and surfaces a corpus
        ``pin_mismatch`` without refusing to rank.
        """
        if statistic not in RANKABLE_STATISTICS:
            raise ExperimentConfigurationError(
                f"statistic {statistic!r} is not a rankable v1 performance statistic; "
                f"use one of {sorted(RANKABLE_STATISTICS)}"
            )
        if order not in _ORDERS:
            raise ExperimentConfigurationError(
                f"order {order!r} must be one of {sorted(_ORDERS)}"
            )

        members = list(results)
        # Consistency: statistics from different engine versions are not commensurable.
        engine_versions = {r.backtest_engine_version_id for r in members}
        if len(engine_versions) > 1:
            raise ExperimentConsistencyError(
                "cannot compare backtests computed under differing "
                f"backtest_engine_version_ids {sorted(engine_versions)}; their "
                "statistics are not commensurable (fail closed, never a wrong ranking)"
            )

        dataset_ids = tuple(sorted({r.dataset_version_id for r in members}))
        market_ids = tuple(sorted({r.market_dataset_version_id for r in members}))

        included: list[tuple[Decimal, str, BacktestResult]] = []
        excluded: list[tuple[str, str]] = []
        for result in members:
            value_str = _statistic_value(result, statistic)
            parsed = _finite_decimal(value_str)
            if parsed is None:
                excluded.append((result.backtest_id, _REASON_UNDEFINED_STATISTIC))
                continue
            included.append((parsed, result.backtest_id, result))

        descending = order == _ORDER_DESCENDING
        # Total order: primary by statistic value (direction-sensitive), tie-broken by
        # backtest_id ascending. Two-pass stable sort keeps the tie-break independent of
        # the value direction (mirrors the backtest engine's selection ranking).
        included.sort(key=lambda item: item[1])
        included.sort(key=lambda item: item[0], reverse=descending)

        entries = tuple(
            ComparisonEntry(
                rank=index + 1,
                backtest_id=result.backtest_id,
                value=_statistic_value(result, statistic),
                dataset_version_id=result.dataset_version_id,
                market_dataset_version_id=result.market_dataset_version_id,
            )
            for index, (_, _, result) in enumerate(included)
        )
        excluded_sorted = tuple(sorted(excluded))

        member_ids = sorted(r.backtest_id for r in members)
        version_id = _comparison_version_id()
        cid = _comparison_id(
            comparison_version_id=version_id,
            statistic_key=statistic,
            order=order,
            sorted_member_backtest_ids=member_ids,
        )
        return cls(
            comparison_id=cid,
            comparison_version_id=version_id,
            statistic_key=statistic,
            order=order,
            entries=entries,
            excluded=excluded_sorted,
            dataset_version_ids=dataset_ids,
            market_dataset_version_ids=market_ids,
        )

    @classmethod
    def of_result_ids(
        cls,
        backtest_ids: Iterable[str],
        store: ResearchResultStore,
        *,
        statistic: str,
        order: str = _ORDER_DESCENDING,
    ) -> BacktestComparison:
        """Read sealed results by id from the shared sidecar, then rank them (§3.4, D4).

        A member id absent from the sidecar is a consistency defect — we refuse to
        compare a set we cannot fully materialize — and raises
        :class:`~quantforge.experiment.errors.ExperimentConsistencyError` (fail closed).
        """
        results: list[BacktestResult] = []
        for backtest_id in backtest_ids:
            result = store.read_as(backtest_id, BacktestResult.from_dict)
            if result is None:
                raise ExperimentConsistencyError(
                    f"backtest {backtest_id!r} is not present in the research sidecar; "
                    "cannot compare a member that was never sealed (fail closed)"
                )
            results.append(result)
        return cls.of_results(results, statistic=statistic, order=order)

    @classmethod
    def of_experiment(
        cls,
        experiment: ExperimentResult,
        store: ResearchResultStore,
        *,
        statistic: str,
        order: str = _ORDER_DESCENDING,
    ) -> BacktestComparison:
        """Rank an experiment's children by ``statistic`` (the read-side of a sweep).

        Resolves every child ``backtest_id`` the experiment recorded from the shared
        sidecar and ranks them — the direct bridge from an
        :class:`~quantforge.experiment.result.ExperimentResult` to its comparison.
        """
        return cls.of_result_ids(
            experiment.backtest_ids, store, statistic=statistic, order=order
        )

    # -- surfaced conditions -------------------------------------------------

    @property
    def pin_mismatch(self) -> bool | None:
        """Whether the compared members span differing corpus pins (surfaced, §6).

        ``None`` when there are no included/excluded members at all (no claim to make);
        otherwise ``True`` iff more than one distinct fundamentals *or* market
        ``dataset_version_id`` appears across the members. The ranking is still valid
        (statistics are numbers), but a researcher can assert this is ``False`` before
        treating the members as like-for-like — the analogue of
        ``UniverseComparison.mode_mismatch``.
        """
        if not self.dataset_version_ids and not self.market_dataset_version_ids:
            return None
        return (
            len(self.dataset_version_ids) > 1
            or len(self.market_dataset_version_ids) > 1
        )

    @property
    def best(self) -> ComparisonEntry | None:
        """The top-ranked included member (``None`` when every member was excluded)."""
        return self.entries[0] if self.entries else None

    def to_dict(self) -> dict[str, object]:
        """A deterministic, serializable ranking."""
        return {
            "comparison_id": self.comparison_id,
            "comparison_version_id": self.comparison_version_id,
            "statistic_key": self.statistic_key,
            "order": self.order,
            "entries": [e.to_dict() for e in self.entries],
            "excluded": [list(pair) for pair in self.excluded],
            "dataset_version_ids": list(self.dataset_version_ids),
            "market_dataset_version_ids": list(self.market_dataset_version_ids),
            "pin_mismatch": self.pin_mismatch,
        }


def _statistic_value(result: BacktestResult, statistic: str) -> str:
    """Read one v1 statistic's canonical string from a sealed result (total order).

    ``statistic`` is guaranteed to be in :data:`RANKABLE_STATISTICS` by the caller, so
    the attribute always exists on the sealed
    :class:`~quantforge.backtest.stats.PerformanceStatistics`.
    """
    value = getattr(result.performance.statistics, statistic)
    assert isinstance(value, str)
    return value


def _finite_decimal(value: str) -> Decimal | None:
    """Parse a statistic string to a finite :class:`Decimal`, or ``None`` if it is not.

    A non-finite or unparseable statistic is surfaced as an excluded member (§6), never
    ranked as if it were a number.
    """
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed
