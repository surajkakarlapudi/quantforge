"""The sealed, content-addressed backtest result & ledger (proposal §H, §22, D7).

A completed backtest is a :class:`BacktestResult`: the full request identity, the v1
:class:`PerformanceSummary`, and the ordered per-rebalance :class:`RebalanceRecord`
ledger that answers "what did the strategy know when it decided, and what did the
engine do about it?" (proposal §H). It satisfies the existing
:class:`~quantforge.factors.store.ResearchRecord` Protocol — ``research_result_id``
aliases ``backtest_id``, and ``to_dict`` is deterministic — so it persists write-once to
the same Phase 8 :class:`~quantforge.factors.store.ResearchResultStore` sidecar Phase 10
reused (decision D7), with no new store type.

The ledger records, per rebalance (proposal §H):

* the ``as_of`` ``T`` and the resolved universe identity;
* every **signal** the strategy read, as the identity of the ``Pit*`` result that
  produced it (:class:`SignalRef`: a ``panel_id`` / ``research_result_id`` / price
  provenance) — so a decision traces to specific PIT inputs and their availability;
* the resulting :class:`TargetWeights`;
* each :class:`Fill` (or ``unfilled`` outcome) with its execution price, PIT price
  provenance, and applied cost;
* each :class:`AppliedAction` (corporate action) with its ``corporate_action_id`` and
  availability;
* the post-rebalance portfolio snapshot and its marked equity.

Every record exposes an ``outcome_digest()`` — the minimal, canonically-ordered dict
that seals into ``result_hash`` (proposal §G, §H). The digest is deliberately narrower
than the full record: it captures every *result-changing* fact (weights, fills, actions,
equity) and omits nothing that could differ between two materially different runs, so
``result_hash`` is an honest content seal (analysis row 4). All monetary/share
fields are canonical decimal strings; nothing here holds a float or a wall-clock value.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantforge.backtest.portfolio import Position
from quantforge.backtest.stats import PerformanceStatistics

__all__ = [
    "AppliedAction",
    "BacktestResult",
    "Fill",
    "PerformanceSummary",
    "RebalanceRecord",
    "SignalRef",
    "TargetWeights",
]


# -- target weights ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TargetWeights:
    """A deterministic ``security_id`` → decimal-weight map (proposal §11, §30).

    The strategy's only output (BT-3): the engine diffs it against current holdings to
    generate orders; the strategy never fabricates share counts. ``weights`` is stored
    as a ``security_id``-sorted tuple of ``(security_id, weight_str)`` pairs so its
    identity and iteration are order-independent (proposal §G rule 3). Long-only v1: a
    weight is a non-negative decimal string and the set typically sums to ``1``.
    """

    weights: tuple[tuple[str, str], ...]

    @classmethod
    def of(cls, mapping: dict[str, str]) -> TargetWeights:
        """Build from a ``security_id`` → weight-string map, canonically ordered."""
        return cls(weights=tuple(sorted(mapping.items())))

    def is_empty(self) -> bool:
        return not self.weights

    def security_ids(self) -> tuple[str, ...]:
        return tuple(sid for sid, _ in self.weights)

    def to_dict(self) -> dict[str, object]:
        return {"weights": [list(pair) for pair in self.weights]}


# -- provenance leaves -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignalRef:
    """A pointer from a decision to the ``Pit*`` result that fed it (proposal §H).

    ``kind`` names the source layer (``"panel"`` → ``panel_id``, ``"factor"`` →
    ``research_result_id``, ``"price"`` → a price provenance id); ``result_id`` is the
    content-addressed id itself. This is how "every signal the strategy read" is made
    auditable without copying the values — the id recomputes the same ``Pit*`` result.
    """

    kind: str
    result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "result_id": self.result_id}


@dataclass(frozen=True, slots=True)
class Fill:
    """One executed (or unfilled) order at a rebalance (proposal §12, §H).

    ``side`` is ``"buy"`` / ``"sell"``; ``shares`` the traded unadjusted share count;
    ``price`` the PIT execution price (unadjusted close, v1); ``notional`` the traded
    value; ``cost`` the applied transaction cost. When the required execution price is
    not PIT-available, ``status`` is ``"unfilled"`` with a ``reason`` and zero
    shares/notional/cost (BT-4: recorded, never fabricated). ``price_provenance_id`` is
    the selected price-observation id (proposal §H) or ``None`` when unfilled.
    """

    security_id: str
    side: str
    status: str
    shares: str
    price: str | None
    notional: str
    cost: str
    reason: str | None = None
    price_provenance_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "side": self.side,
            "status": self.status,
            "shares": self.shares,
            "price": self.price,
            "notional": self.notional,
            "cost": self.cost,
            "reason": self.reason,
            "price_provenance_id": self.price_provenance_id,
        }

    def outcome_digest(self) -> dict[str, object]:
        """The result-changing facts of this fill (omits nothing economically
        material)."""
        return {
            "security_id": self.security_id,
            "side": self.side,
            "status": self.status,
            "shares": self.shares,
            "price": self.price,
            "notional": self.notional,
            "cost": self.cost,
        }


@dataclass(frozen=True, slots=True)
class AppliedAction:
    """A corporate action applied to the portfolio at a rebalance (proposal §D, §H).

    Records the ``corporate_action_id``, its ``action_kind``, the ``ex_date``, its
    ``availability_timestamp`` (so "acted only once availability <= T" is auditable),
    and the concrete ``effect`` the engine applied (a canonical dict, e.g. the split
    ratio or the dividend cash credited). An ``unrecognized`` flag marks a payload that
    could not be applied deterministically (recorded, position untouched — proposal §D
    rule 3); the engine raises for a genuinely malformed spec but flags an unknown
    payload shape here.
    """

    corporate_action_id: str
    action_kind: str
    security_id: str
    ex_date: str
    availability_timestamp: str | None
    effect: dict[str, object] = field(default_factory=dict)
    unrecognized: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "corporate_action_id": self.corporate_action_id,
            "action_kind": self.action_kind,
            "security_id": self.security_id,
            "ex_date": self.ex_date,
            "availability_timestamp": self.availability_timestamp,
            "effect": dict(self.effect),
            "unrecognized": self.unrecognized,
        }

    def outcome_digest(self) -> dict[str, object]:
        return {
            "corporate_action_id": self.corporate_action_id,
            "action_kind": self.action_kind,
            "security_id": self.security_id,
            "effect": dict(self.effect),
            "unrecognized": self.unrecognized,
        }


# -- per-rebalance ledger record ---------------------------------------------


@dataclass(frozen=True, slots=True)
class RebalanceRecord:
    """The full, auditable record of one rebalance (proposal §H, §22).

    Ordered in schedule order within :class:`BacktestResult`. Holds the decision inputs
    (``as_of``, universe identity, the signals read), the decision output
    (``target_weights``), and the mechanical results (``actions_applied`` first —
    actions apply to positions before the rebalance trades — then ``fills``, then the
    post-rebalance ``positions`` and marked ``equity``). ``outcome_digest`` seals only
    the result-changing facts into ``result_hash``.
    """

    as_of: str
    universe_id: str
    signals: tuple[SignalRef, ...]
    target_weights: TargetWeights
    actions_applied: tuple[AppliedAction, ...]
    fills: tuple[Fill, ...]
    positions: tuple[Position, ...]
    cash: str
    equity: str
    turnover: str

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "universe_id": self.universe_id,
            "signals": [s.to_dict() for s in self.signals],
            "target_weights": self.target_weights.to_dict(),
            "actions_applied": [a.to_dict() for a in self.actions_applied],
            "fills": [f.to_dict() for f in self.fills],
            "positions": [p.to_dict() for p in self.positions],
            "cash": self.cash,
            "equity": self.equity,
            "turnover": self.turnover,
        }

    def outcome_digest(self) -> dict[str, object]:
        """The minimal, canonically-ordered dict this rebalance contributes to the seal.

        Every result-changing fact: the ``as_of`` and universe it decided over, the
        target weights, the applied actions and fills (in the order applied), and the
        resulting cash/equity/positions. Deterministically ordered so equal ledgers
        yield identical bytes (proposal §G, §H).
        """
        return {
            "as_of": self.as_of,
            "universe_id": self.universe_id,
            "target_weights": self.target_weights.to_dict(),
            "actions_applied": [a.outcome_digest() for a in self.actions_applied],
            "fills": [f.outcome_digest() for f in self.fills],
            "positions": [p.to_dict() for p in self.positions],
            "cash": self.cash,
            "equity": self.equity,
        }


# -- performance summary -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    """The v1 performance statistics + their annualization convention (proposal §34).

    Wraps the computed :class:`~quantforge.backtest.stats.PerformanceStatistics` with
    the **recorded** convention that produced the Sharpe ratio — the risk-free
    per-period constant and the ``periods_per_year`` annualization factor (§L Q3):
    the convention is provenance, never implicit. ``formula_version`` pins the statistic
    definitions so a future change to a formula is distinguishable.
    """

    statistics: PerformanceStatistics
    risk_free_per_period: str
    periods_per_year: str
    formula_version: str = "backtest-stats/1"

    def to_dict(self) -> dict[str, object]:
        return {
            "formula_version": self.formula_version,
            "risk_free_per_period": self.risk_free_per_period,
            "periods_per_year": self.periods_per_year,
            "statistics": self.statistics.to_dict(),
        }


# -- the sealed result -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """A complete, sealed, content-addressed backtest (proposal §H, §22, §24, D6, D7).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`backtest_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It records every §9 lineage field the backtest ran over — both corpus
    pins (fundamentals + market, BT-1), the strategy/schedule/cost/accounting/engine
    identities (D6) — plus the sealed ``result_hash`` over the ordered ledger, the v1
    :class:`PerformanceSummary`, and the full :class:`RebalanceRecord` ledger (proposal
    §L question 5, resolved: persist the full ledger).
    """

    backtest_id: str
    result_hash: str
    strategy_version: str
    schedule_id: str
    universe_id: str
    dataset_version_id: str
    market_dataset_version_id: str
    cost_model_id: str
    accounting_version_id: str
    backtest_engine_version_id: str
    base_currency: str
    initial_capital: str
    performance: PerformanceSummary
    ledger: tuple[RebalanceRecord, ...]

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`backtest_id` — the :class:`ResearchRecord` identity (§24)."""
        return self.backtest_id

    def to_dict(self) -> dict[str, object]:
        return {
            "backtest_id": self.backtest_id,
            "research_result_id": self.research_result_id,
            "result_hash": self.result_hash,
            "strategy_version": self.strategy_version,
            "schedule_id": self.schedule_id,
            "universe_id": self.universe_id,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
            "cost_model_id": self.cost_model_id,
            "accounting_version_id": self.accounting_version_id,
            "backtest_engine_version_id": self.backtest_engine_version_id,
            "base_currency": self.base_currency,
            "initial_capital": self.initial_capital,
            "performance": self.performance.to_dict(),
            "ledger": [record.to_dict() for record in self.ledger],
        }
