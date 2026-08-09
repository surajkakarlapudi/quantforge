"""The declarative, content-addressed backtest request (proposal §D2, §F, D2 APPROVED).

A backtest is fully described by a **declarative specification** — never a callback, a
subclass, or arbitrary Python. This is the Phase 12 analogue of a
:class:`~quantforge.universe.specification.UniverseSpecification`: a frozen tree of
typed, ordered steps whose identity is a pure content hash of *what was declared*, not
of the source text that declared it (proposal §F). The engine interprets the tree; the
tree never executes code. That is what makes ``strategy_version`` — and therefore
``backtest_id`` — an honest, reproducible identity (D6): equal logic always yields
equal bytes, regardless of formatting or attribute naming.

The pieces, all frozen (``@dataclass(frozen=True, slots=True)``) and all carrying a
content-addressed id:

* :class:`StrategySpecification` — an ordered tuple of typed steps
  (signal → optional filters → rank → select → weight). ``rank_select_weight`` is the
  v1 primary builder. ``strategy_version`` hashes the ordered step dicts via
  :func:`quantforge.backtest.identity.strategy_version` (the order is load-bearing and
  preserved verbatim; only the JSON keys *within* each step are sorted).
* :class:`CostModel` — proportional (bps) + fixed-per-order transaction costs, decimal
  strings only (no float ever touches money). ``cost_model_id`` folds every parameter.
* :class:`AccountingPolicy` — the execution convention (``close`` in v1) and dividend
  timing (``ex_date`` in v1). ``accounting_version_id`` folds the policy.
* :class:`BacktestSpecification` — the whole request: strategy, schedule, universe,
  cost model, accounting policy, initial capital, and the **two pinned corpus
  snapshots** (fundamentals ``dataset_version_id`` + market
  ``market_dataset_version_id``
  — BT-1, D4 APPROVED). Nothing here reads a store or the wall clock; it is a pure,
  reproducible value object the engine consumes.

The v1 conservative resolutions (proposal §L open questions, resolved
most-conservatively
against every Phase 1-11 invariant): declarative-only strategy; ``close`` execution;
``ex_date`` dividend timing; long-only weighting. A future execution convention or
weighting scheme is a *new step / new enum value* that hashes distinctly — never an edit
that changes an existing ``backtest_id`` (the extensibility discipline shared with
``PriceAxis`` / ``UniverseSpecification``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.backtest.errors import BacktestConfigurationError
from quantforge.backtest.identity import (
    accounting_version_id as _accounting_version_id,
)
from quantforge.backtest.identity import (
    cost_model_id as _cost_model_id,
)
from quantforge.backtest.identity import (
    strategy_version as _strategy_version,
)
from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.metrics.model import MetricPeriod
from quantforge.universe.specification import UniverseSpecification
from quantforge.xbrl.contexts import PeriodType

__all__ = [
    "AccountingPolicy",
    "BacktestSpecification",
    "CostModel",
    "StrategySpecification",
]

# -- step kinds (the declarative vocabulary, proposal §D2) -------------------
#
# Each is a stable string tag folded verbatim into ``strategy_version``. A new step
# kind (or a new option value below) hashes distinctly, so it can never change an
# already-computed strategy identity.
_STEP_SIGNAL = "signal"
_STEP_RANK = "rank"
_STEP_SELECT = "select"
_STEP_WEIGHT = "weight"

# The v1 vocabulary for each step's options. Anything outside these is a configuration
# defect (a strategy we refuse to guess the intent of), raised — not silently coerced.
_RANK_DESCENDING = "descending"
_RANK_ASCENDING = "ascending"
_RANK_DIRECTIONS = frozenset({_RANK_DESCENDING, _RANK_ASCENDING})

_SELECT_TOP_N = "top_n"  # ``top_n:<k>`` — the k highest-ranked members
_WEIGHT_EQUAL = "equal"  # equal weight across the selected members (long-only, v1)

# The one execution convention and dividend timing v1 supports (proposal §L; the other
# options are deferred, and are a new enum value when added — not an edit).
_EXECUTION_CLOSE = "close"
_DIVIDEND_EX_DATE = "ex_date"


def _req_str(value: object, field: str) -> str:
    """Coerce a required field to a non-empty ``str``; fail closed otherwise."""
    if not isinstance(value, str) or not value:
        raise BacktestConfigurationError(
            f"{field} must be a non-empty string, got {value!r}"
        )
    return value


def _decimal_str(value: str, field: str, *, allow_zero: bool = True) -> str:
    """Validate ``value`` as a finite, non-negative decimal string; return canonical
    form.

    Money and cost parameters are decimal strings end-to-end (no float ever touches a
    monetary quantity — invariant 20). A non-decimal, non-finite, or negative value is
    a configuration defect, raised. The returned string is the canonical form of the
    parsed :class:`~decimal.Decimal`, so ``"5"`` and ``"5.0"`` fold into distinct ids
    only if they parse distinctly (they do not: both canonicalize identically here).
    """
    if not isinstance(value, str) or not value:
        raise BacktestConfigurationError(
            f"{field} must be a non-empty decimal string, got {value!r}"
        )
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise BacktestConfigurationError(
            f"{field} {value!r} is not a valid decimal string"
        ) from exc
    if not parsed.is_finite():
        raise BacktestConfigurationError(f"{field} {value!r} must be finite")
    if parsed < 0:
        raise BacktestConfigurationError(f"{field} {value!r} must not be negative")
    if not allow_zero and parsed == 0:
        raise BacktestConfigurationError(f"{field} {value!r} must be strictly positive")
    return str(parsed)


# -- strategy ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategySpecification:
    """A declarative, ordered strategy: signal → filters → rank → select → weight (§D2).

    ``steps`` is a tuple of typed step dicts, each with a ``"step"`` tag and its typed
    options. The order is load-bearing and preserved verbatim into ``strategy_version``.
    The strategy is *interpreted* by the engine, never executed as code — so its
    identity is an honest content hash of the declared logic (§F).

    Build via :meth:`rank_select_weight`, the v1 primary factory. Direct construction
    from a hand-built step list is possible but validated the same way.
    """

    steps: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise BacktestConfigurationError(
                "a strategy must declare at least one step; an empty strategy is a "
                "configuration bug, not a no-op backtest"
            )
        for step in self.steps:
            if not isinstance(step, dict) or "step" not in step:
                raise BacktestConfigurationError(
                    f"each strategy step must be a dict with a 'step' tag, got {step!r}"
                )

    @classmethod
    def rank_select_weight(
        cls,
        *,
        signal: str,
        period: MetricPeriod,
        select: str,
        weight: str = _WEIGHT_EQUAL,
        rank: str = _RANK_DESCENDING,
    ) -> StrategySpecification:
        """The v1 primary strategy: rank a signal, select the top members, weight them.

        Parameters
        ----------
        signal:
            The Phase 7 ``metric_key`` to evaluate cross-sectionally at each rebalance
            (e.g. ``"current_ratio"``). Resolved PIT at the rebalance ``as_of`` via the
            factor layer — a member whose signal is ``UNDEFINED`` at ``T`` is excluded
            from selection (BT-4), never guessed.
        period:
            The **explicit** fiscal :class:`~quantforge.metrics.model.MetricPeriod` the
            signal is evaluated at — declared, never inferred from ingestion state
            (inferring a period from what happens to be loaded is
            look-ahead-by-ingestion;
            this mirrors :class:`~quantforge.universe.filters.CompanyMetricFilter`, the
            existing cross-sectional metric-selection primitive, which also takes an
            explicit period). It is folded into ``strategy_version``, so two strategies
            that rank the same metric at different periods get distinct identities. A
            period not yet knowable at ``T`` simply yields ``UNDEFINED`` cells (fail
            closed), never a value.
        select:
            The selection rule, ``"top_n:<k>"`` — the ``k`` highest-ranked members
            (``k`` a positive integer). ``k`` larger than the eligible set simply
            selects the whole eligible set (recorded), never an error.
        weight:
            The weighting scheme; v1 supports ``"equal"`` (long-only equal weight).
        rank:
            Rank direction, ``"descending"`` (default — highest signal first) or
            ``"ascending"``. A descending rank of ``current_ratio`` selects the most
            liquid filers; ascending selects the least.

        The steps are emitted in canonical order (signal → rank → select → weight) so
        the same declared logic always yields the same ``strategy_version`` (§F).
        """
        metric_key = _req_str(signal, "signal")
        if not isinstance(period, MetricPeriod):
            raise BacktestConfigurationError(
                "signal 'period' must be a MetricPeriod; the fiscal period a signal is "
                "ranked at is declared explicitly, never inferred (look-ahead risk)"
            )
        direction = _req_str(rank, "rank")
        if direction not in _RANK_DIRECTIONS:
            raise BacktestConfigurationError(
                f"rank direction {direction!r} is not supported; use one of "
                f"{sorted(_RANK_DIRECTIONS)}"
            )
        select_n = _parse_top_n(select)
        weight_scheme = _req_str(weight, "weight")
        if weight_scheme != _WEIGHT_EQUAL:
            raise BacktestConfigurationError(
                f"weight scheme {weight_scheme!r} is not supported in v1; only "
                f"{_WEIGHT_EQUAL!r} (long-only) is available"
            )
        steps: tuple[dict[str, object], ...] = (
            {
                "step": _STEP_SIGNAL,
                "metric_key": metric_key,
                "period": period.to_dict(),
            },
            {"step": _STEP_RANK, "direction": direction},
            {"step": _STEP_SELECT, "rule": _SELECT_TOP_N, "n": select_n},
            {"step": _STEP_WEIGHT, "scheme": weight_scheme},
        )
        return cls(steps=steps)

    @property
    def strategy_version(self) -> str:
        """The content-addressed strategy id (``sha256:``) over the ordered steps
        (§F)."""
        return _strategy_version([dict(step) for step in self.steps])

    @property
    def signal_metric_key(self) -> str:
        """The Phase 7 ``metric_key`` this strategy ranks on (the ``signal`` step)."""
        for step in self.steps:
            if step.get("step") == _STEP_SIGNAL:
                return _req_str(step.get("metric_key"), "signal.metric_key")
        raise BacktestConfigurationError("strategy declares no signal step")

    @property
    def signal_period(self) -> MetricPeriod:
        """The explicit fiscal period the signal is ranked at (the ``signal`` step).

        Reconstructs the declared :class:`~quantforge.metrics.model.MetricPeriod` from
        the serialized step — the same fail-closed reconstruction
        :func:`~quantforge.universe.filters.filter_from_dict` performs for a
        :class:`~quantforge.universe.filters.CompanyMetricFilter`. A signal step
        without a well-formed period is a specification defect, raised (never
        defaulted — a guessed period is exactly the look-ahead this design forbids).
        """
        for step in self.steps:
            if step.get("step") == _STEP_SIGNAL:
                raw = step.get("period")
                if not isinstance(raw, dict):
                    raise BacktestConfigurationError(
                        "signal step is missing a well-formed 'period'; the fiscal "
                        "period a signal is ranked at must be declared explicitly"
                    )
                period_type = _req_str(
                    raw.get("period_type"), "signal.period.period_type"
                )
                start = raw.get("period_start")
                end = raw.get("period_end")
                if start is not None and not isinstance(start, str):
                    raise BacktestConfigurationError(
                        "signal.period.period_start must be a string or null"
                    )
                if end is not None and not isinstance(end, str):
                    raise BacktestConfigurationError(
                        "signal.period.period_end must be a string or null"
                    )
                try:
                    resolved_type = PeriodType(period_type)
                except ValueError as exc:
                    raise BacktestConfigurationError(
                        f"signal.period.period_type {period_type!r} is not a valid "
                        "PeriodType"
                    ) from exc
                return MetricPeriod(
                    period_type=resolved_type,
                    period_start=start,
                    period_end=end,
                )
        raise BacktestConfigurationError("strategy declares no signal step")

    @property
    def rank_direction(self) -> str:
        """The rank direction (``descending`` / ``ascending``) — highest signal
        first?"""
        for step in self.steps:
            if step.get("step") == _STEP_RANK:
                return _req_str(step.get("direction"), "rank.direction")
        return _RANK_DESCENDING

    @property
    def select_n(self) -> int:
        """The ``k`` of the ``top_n:k`` selection rule."""
        for step in self.steps:
            if step.get("step") == _STEP_SELECT:
                n = step.get("n")
                if not isinstance(n, int) or n <= 0:
                    raise BacktestConfigurationError(
                        f"select.n must be a positive integer, got {n!r}"
                    )
                return n
        raise BacktestConfigurationError("strategy declares no select step")

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_version": self.strategy_version,
            "steps": [dict(step) for step in self.steps],
        }


def _parse_top_n(select: str) -> int:
    """Parse a ``top_n:<k>`` selection rule into ``k``; fail closed on anything else."""
    rule = _req_str(select, "select")
    prefix = f"{_SELECT_TOP_N}:"
    if not rule.startswith(prefix):
        raise BacktestConfigurationError(
            f"selection rule {rule!r} is not supported; use 'top_n:<k>'"
        )
    raw = rule[len(prefix) :]
    try:
        k = int(raw)
    except ValueError as exc:
        raise BacktestConfigurationError(
            f"selection rule {rule!r} has a non-integer count {raw!r}"
        ) from exc
    if k <= 0:
        raise BacktestConfigurationError(
            f"selection rule {rule!r} must select a positive number of members"
        )
    return k


# -- cost model --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostModel:
    """Deterministic transaction costs: proportional (bps) + fixed-per-order (§D5).

    Both parameters are non-negative decimal strings (no float touches money). A trade
    of notional ``N`` (the absolute traded value) incurs
    ``N * proportional_bps / 10000 + fixed_per_order`` under the engine's pinned decimal
    context. ``cost_model_id`` folds both parameters into identity (D6): two backtests
    that differ only in costs get different ``backtest_id``s.
    """

    proportional_bps: str = "0"
    fixed_per_order: str = "0"

    def __post_init__(self) -> None:
        # Re-store the canonical decimal form so ``"5"`` / ``"5.0"`` fold identically
        # and identity never depends on cosmetic formatting (frozen →
        # object.__setattr__).
        object.__setattr__(
            self,
            "proportional_bps",
            _decimal_str(self.proportional_bps, "proportional_bps"),
        )
        object.__setattr__(
            self,
            "fixed_per_order",
            _decimal_str(self.fixed_per_order, "fixed_per_order"),
        )

    @property
    def cost_model_id(self) -> str:
        """The content-addressed cost-model id (``sha256:``) over both parameters."""
        return _cost_model_id(self._payload())

    def _payload(self) -> dict[str, object]:
        return {
            "proportional_bps": self.proportional_bps,
            "fixed_per_order": self.fixed_per_order,
        }

    def to_dict(self) -> dict[str, object]:
        return {"cost_model_id": self.cost_model_id, **self._payload()}


# -- accounting policy -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountingPolicy:
    """The execution + corporate-action accounting convention (§D, §L; D8).

    ``execution`` is the price a rebalance order fills at — v1 supports ``"close"`` (the
    rebalance session's PIT-eligible close). ``dividend_timing`` is when a cash dividend
    is booked — v1 supports ``"ex_date"`` (book ``shares * amount`` on the ex-date; no
    DRIP). Both are folded into ``accounting_version_id`` (D6): a different convention
    is a different result, hence a different ``backtest_id``. A deferred convention
    (``next_open`` execution, ``pay_date`` dividend timing) is a new enum value that
    hashes distinctly — never an edit to an existing id.
    """

    execution: str = _EXECUTION_CLOSE
    dividend_timing: str = _DIVIDEND_EX_DATE

    def __post_init__(self) -> None:
        execution = _req_str(self.execution, "execution")
        if execution != _EXECUTION_CLOSE:
            raise BacktestConfigurationError(
                f"execution convention {execution!r} is not supported in v1; only "
                f"{_EXECUTION_CLOSE!r} is available"
            )
        timing = _req_str(self.dividend_timing, "dividend_timing")
        if timing != _DIVIDEND_EX_DATE:
            raise BacktestConfigurationError(
                f"dividend timing {timing!r} is not supported in v1; only "
                f"{_DIVIDEND_EX_DATE!r} is available"
            )

    @property
    def accounting_version_id(self) -> str:
        """The content-addressed accounting-policy id (``sha256:``) over the policy."""
        return _accounting_version_id(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"execution": self.execution, "dividend_timing": self.dividend_timing}

    def to_dict(self) -> dict[str, object]:
        return {"accounting_version_id": self.accounting_version_id, **self._payload()}


# -- the whole request -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BacktestSpecification:
    """A complete, declarative, reproducible backtest request (§D, §F, BT-1, D4, D6).

    Everything the engine needs to produce a
    :class:`~quantforge.backtest.result.BacktestResult`
    and nothing it does not: the strategy logic, the rebalance schedule, the universe
    specification, the cost model, the accounting policy, the initial capital, and the
    **two pinned corpus snapshots** — the fundamentals ``dataset_version_id`` and the
    market ``market_dataset_version_id`` (BT-1: the engine re-derives and verifies both
    against the live corpus before simulating; a mismatch fails closed).

    This is a pure value object: constructing it reads no store and no wall clock. It
    validates its own shape (a non-positive initial capital, a malformed field) at
    construction, exactly as the metrics/universe layers refuse a misconfigured request.
    """

    strategy: StrategySpecification
    schedule: RebalanceSchedule
    universe: UniverseSpecification
    dataset_version_id: str
    market_dataset_version_id: str
    cost_model: CostModel = CostModel()
    accounting: AccountingPolicy = AccountingPolicy()
    initial_capital: str = "1000000"
    base_currency: str = "USD"

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, StrategySpecification):
            raise BacktestConfigurationError(
                "spec.strategy must be a StrategySpecification"
            )
        if not isinstance(self.schedule, RebalanceSchedule):
            raise BacktestConfigurationError(
                "spec.schedule must be a RebalanceSchedule"
            )
        if not isinstance(self.universe, UniverseSpecification):
            raise BacktestConfigurationError(
                "spec.universe must be a UniverseSpecification"
            )
        if not isinstance(self.cost_model, CostModel):
            raise BacktestConfigurationError("spec.cost_model must be a CostModel")
        if not isinstance(self.accounting, AccountingPolicy):
            raise BacktestConfigurationError(
                "spec.accounting must be an AccountingPolicy"
            )
        object.__setattr__(
            self,
            "initial_capital",
            _decimal_str(self.initial_capital, "initial_capital", allow_zero=False),
        )
        object.__setattr__(
            self, "base_currency", _req_str(self.base_currency, "base_currency")
        )
        _req_str(self.dataset_version_id, "dataset_version_id")
        _req_str(self.market_dataset_version_id, "market_dataset_version_id")

    @property
    def universe_id(self) -> str:
        """The specification id of the universe this backtest ranges over."""
        return self.universe.specification_id

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.to_dict(),
            "schedule": self.schedule.to_dict(),
            "universe": self.universe.to_dict(),
            "cost_model": self.cost_model.to_dict(),
            "accounting": self.accounting.to_dict(),
            "initial_capital": self.initial_capital,
            "base_currency": self.base_currency,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
        }
