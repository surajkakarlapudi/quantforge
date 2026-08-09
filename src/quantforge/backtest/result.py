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


# -- fail-closed decode helpers ----------------------------------------------
#
# The ``from_dict`` inverses below (Phase 13 D3) reconstruct a sealed result from its
# ``to_dict`` payload byte-identically. They reuse the project-wide fail-closed decode
# idiom (`quantforge.factors.model`): a required field of the wrong type is a corrupt
# payload, refused with a ``ValueError`` rather than guessed — a sidecar that cannot be
# read back correctly must never silently produce a wrong result.


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _req_bool(raw: dict[str, object], key: str) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a bool")
    return value


def _req_dict(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _req_list(raw: dict[str, object], key: str) -> list[object]:
    value = raw[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


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

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TargetWeights:
        """Reconstruct from a :meth:`to_dict` payload (Phase 13 D3), order preserved.

        ``weights`` was emitted ``security_id``-sorted by :meth:`of`; the stored order
        is authoritative and preserved verbatim, so a re-emitted :meth:`to_dict` is
        byte-identical. Each entry must be a ``[security_id, weight]`` string pair.
        """
        pairs: list[tuple[str, str]] = []
        for pair in _req_list(raw, "weights"):
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or not all(isinstance(item, str) for item in pair)
            ):
                raise ValueError("each weight must be a [security_id, weight] pair")
            pairs.append((pair[0], pair[1]))
        return cls(weights=tuple(pairs))


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

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> SignalRef:
        """Reconstruct from a :meth:`to_dict` payload (Phase 13 D3)."""
        return cls(kind=_req_str(raw, "kind"), result_id=_req_str(raw, "result_id"))


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

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Fill:
        """Reconstruct from a :meth:`to_dict` payload (Phase 13 D3).

        ``price``, ``reason`` and ``price_provenance_id`` are nullable (an unfilled
        order has no price/provenance); every other field is a required string.
        """
        return cls(
            security_id=_req_str(raw, "security_id"),
            side=_req_str(raw, "side"),
            status=_req_str(raw, "status"),
            shares=_req_str(raw, "shares"),
            price=_opt_str(raw, "price"),
            notional=_req_str(raw, "notional"),
            cost=_req_str(raw, "cost"),
            reason=_opt_str(raw, "reason"),
            price_provenance_id=_opt_str(raw, "price_provenance_id"),
        )


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

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> AppliedAction:
        """Reconstruct from a :meth:`to_dict` payload (Phase 13 D3).

        ``availability_timestamp`` is nullable; ``effect`` is a canonical dict copied
        verbatim; ``unrecognized`` is a required bool.
        """
        return cls(
            corporate_action_id=_req_str(raw, "corporate_action_id"),
            action_kind=_req_str(raw, "action_kind"),
            security_id=_req_str(raw, "security_id"),
            ex_date=_req_str(raw, "ex_date"),
            availability_timestamp=_opt_str(raw, "availability_timestamp"),
            effect=dict(_req_dict(raw, "effect")),
            unrecognized=_req_bool(raw, "unrecognized"),
        )


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

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RebalanceRecord:
        """Reconstruct from a :meth:`to_dict` payload (Phase 13 D3), order preserved.

        Every nested tuple (signals, actions, fills, positions) is decoded in its
        stored order — schedule/security order is load-bearing for both the ledger and
        ``result_hash`` — so a re-emitted :meth:`to_dict` is byte-identical.
        """
        return cls(
            as_of=_req_str(raw, "as_of"),
            universe_id=_req_str(raw, "universe_id"),
            signals=tuple(
                SignalRef.from_dict(_as_dict(s, "signals"))
                for s in _req_list(raw, "signals")
            ),
            target_weights=TargetWeights.from_dict(_req_dict(raw, "target_weights")),
            actions_applied=tuple(
                AppliedAction.from_dict(_as_dict(a, "actions_applied"))
                for a in _req_list(raw, "actions_applied")
            ),
            fills=tuple(
                Fill.from_dict(_as_dict(f, "fills")) for f in _req_list(raw, "fills")
            ),
            positions=tuple(
                Position.from_dict(_as_dict(p, "positions"))
                for p in _req_list(raw, "positions")
            ),
            cash=_req_str(raw, "cash"),
            equity=_req_str(raw, "equity"),
            turnover=_req_str(raw, "turnover"),
        )


def _as_dict(value: object, key: str) -> dict[str, object]:
    """Narrow a decoded list element to a dict; fail closed otherwise."""
    if not isinstance(value, dict):
        raise ValueError(f"each {key} entry must be an object")
    return value


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

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PerformanceSummary:
        """Reconstruct from a :meth:`to_dict` payload (Phase 13 D3).

        The recorded annualization convention (``risk_free_per_period`` /
        ``periods_per_year``) and ``formula_version`` are required strings; the nested
        :class:`~quantforge.backtest.stats.PerformanceStatistics` round-trips through
        its own ``from_dict``.
        """
        return cls(
            statistics=PerformanceStatistics.from_dict(_req_dict(raw, "statistics")),
            risk_free_per_period=_req_str(raw, "risk_free_per_period"),
            periods_per_year=_req_str(raw, "periods_per_year"),
            formula_version=_req_str(raw, "formula_version"),
        )


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

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> BacktestResult:
        """Reconstruct a sealed result from its :meth:`to_dict` payload (Phase 13 D3).

        The additive inverse of :meth:`to_dict`, so a sealed result read back from the
        shared research sidecar via ``store.read_as(id, BacktestResult.from_dict)`` is a
        first-class typed object. The round-trip is byte-identical:
        ``research_result_id`` is a derived alias of ``backtest_id`` (re-emitted by the
        property, not stored as state), and every nested value type round-trips through
        its own ``from_dict`` in stored order — so ``from_dict(to_dict(r))`` re-emits an
        identical ``to_dict`` and the same ``result_hash``, with no identity drift.
        """
        return cls(
            backtest_id=_req_str(raw, "backtest_id"),
            result_hash=_req_str(raw, "result_hash"),
            strategy_version=_req_str(raw, "strategy_version"),
            schedule_id=_req_str(raw, "schedule_id"),
            universe_id=_req_str(raw, "universe_id"),
            dataset_version_id=_req_str(raw, "dataset_version_id"),
            market_dataset_version_id=_req_str(raw, "market_dataset_version_id"),
            cost_model_id=_req_str(raw, "cost_model_id"),
            accounting_version_id=_req_str(raw, "accounting_version_id"),
            backtest_engine_version_id=_req_str(raw, "backtest_engine_version_id"),
            base_currency=_req_str(raw, "base_currency"),
            initial_capital=_req_str(raw, "initial_capital"),
            performance=PerformanceSummary.from_dict(_req_dict(raw, "performance")),
            ledger=tuple(
                RebalanceRecord.from_dict(_as_dict(record, "ledger"))
                for record in _req_list(raw, "ledger")
            ),
        )
