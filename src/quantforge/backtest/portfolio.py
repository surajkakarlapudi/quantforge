"""Portfolio & position state — deterministic ``Decimal`` accounting (proposal §D, §31).

The simulation's mutable core: a :class:`Portfolio` is cash plus a set of
:class:`Position`\\ s, each keyed by ``security_id`` (never a ticker — invariant 11,
analysis row 7) and held in **unadjusted shares** (decision D5). Every arithmetic
operation runs under a single, explicit :class:`decimal.Context` (precision 34,
``ROUND_HALF_EVEN`` — the engine's pinned context, proposal §G rule 4); no float ever
touches money or shares, and iteration is always ``security_id``-sorted so a valuation
or a serialized snapshot is byte-identical on any machine (proposal §G rule 3).

This module is a **pure accounting primitive**. It exposes the mechanical effects a
trade or a corporate action has on shares and cash — ``buy`` / ``sell`` /
``multiply_shares`` (a split) / ``credit_cash`` (a dividend) / ``liquidate`` (a
delisting or merger cash leg) / ``rekey`` (a merger successor mapping) — and nothing
more. *Which* action is eligible at a given ``as_of``, *how* its payload is parsed, and
*what* execution price fills an order are the engine's decisions (proposal §D rules
1-3); the portfolio only applies the resulting deterministic Decimal deltas. Keeping
the policy out of here is what lets the corporate-action accounting be unit-tested in
isolation against synthetic actions (proposal §L test categories).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge.backtest.errors import BacktestConfigurationError

__all__ = ["Portfolio", "Position"]

_ZERO = Decimal(0)


def _req_str(raw: dict[str, object], key: str) -> str:
    """Read a required string from a decoded payload; fail closed otherwise.

    The fail-closed decode idiom shared with :mod:`quantforge.factors.model` — a
    ``from_dict`` reconstruction refuses a malformed or wrong-typed field rather than
    guessing, so a corrupt sidecar payload can never silently produce a wrong result.
    """
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


@dataclass(frozen=True, slots=True)
class Position:
    """An immutable snapshot of one holding: ``security_id`` + unadjusted shares.

    A pure value used in ledger records and results; the live, mutating state is the
    :class:`Portfolio`. ``shares`` is the canonical decimal string of the unadjusted
    share count (D5); a position is never keyed by ticker (invariant 11).
    """

    security_id: str
    shares: str

    def shares_decimal(self) -> Decimal:
        return Decimal(self.shares)

    def to_dict(self) -> dict[str, object]:
        return {"security_id": self.security_id, "shares": self.shares}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Position:
        """Reconstruct a :class:`Position` from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict` (Phase 13 D3): a sealed
        :class:`~quantforge.backtest.result.BacktestResult` read back from the sidecar
        must reconstruct byte-identically, so every nested value type round-trips. Both
        fields are required strings; a malformed payload fails closed with a
        :class:`ValueError` (the same discipline the factor/panel decoders use).
        """
        return cls(
            security_id=_req_str(raw, "security_id"),
            shares=_req_str(raw, "shares"),
        )


class Portfolio:
    """Mutable cash + unadjusted-share state under one pinned decimal context (§31).

    Not a frozen dataclass: the simulation walks the schedule mutating one portfolio in
    place, which is both natural and deterministic (all mutation is Decimal arithmetic
    under the fixed context, and every read/serialization iterates ``security_id``-
    sorted). Construct via :meth:`initial`. A zero-share holding is dropped rather than
    retained, so ``security_ids`` and snapshots never carry economically-empty rows.
    """

    __slots__ = ("_cash", "_context", "_shares")

    def __init__(self, *, cash: Decimal, context: Context) -> None:
        self._context = context
        self._cash = cash
        self._shares: dict[str, Decimal] = {}

    @classmethod
    def initial(cls, initial_capital: str, context: Context) -> Portfolio:
        """A portfolio holding ``initial_capital`` in cash and no positions.

        ``initial_capital`` is a decimal string (validated upstream by the
        specification); it is parsed under the pinned context so the opening cash
        rounds exactly as every later balance does.
        """
        with localcontext(context):
            cash = +Decimal(initial_capital)
        return cls(cash=cash, context=context)

    # -- reads ---------------------------------------------------------------

    @property
    def cash(self) -> Decimal:
        return self._cash

    def shares_of(self, security_id: str) -> Decimal:
        """The unadjusted share count held in ``security_id`` (``0`` if none)."""
        return self._shares.get(security_id, _ZERO)

    def security_ids(self) -> tuple[str, ...]:
        """Held ``security_id``\\ s in a single total order (ascending)."""
        return tuple(sorted(self._shares))

    def positions(self) -> tuple[Position, ...]:
        """An immutable, ``security_id``-sorted snapshot of the current holdings."""
        return tuple(
            Position(security_id=sid, shares=str(self._shares[sid]))
            for sid in sorted(self._shares)
        )

    def is_empty(self) -> bool:
        return not self._shares

    def market_value(self, marks: dict[str, Decimal]) -> Decimal:
        """Total equity = cash + sum ``shares x mark`` over held securities (§31).

        ``marks`` maps ``security_id`` → unadjusted mark price. A held security absent
        from ``marks`` is a configuration/consistency defect — the engine must supply a
        mark (or a ``delisted_no_price`` carry value) for every holding before valuing —
        so it is raised, never silently valued at zero (which would fabricate a loss).
        """
        with localcontext(self._context):
            total = +self._cash
            for sid in sorted(self._shares):
                if sid not in marks:
                    raise BacktestConfigurationError(
                        f"cannot value portfolio: no mark supplied for held security "
                        f"{sid!r}; every holding must be marked before valuation"
                    )
                total += self._shares[sid] * marks[sid]
            return +total

    # -- trades --------------------------------------------------------------

    def buy(
        self, security_id: str, shares: Decimal, cost: Decimal, notional: Decimal
    ) -> None:
        """Add ``shares`` of ``security_id``, paying ``notional`` + ``cost`` from cash.

        ``notional`` is ``shares x fill_price`` (the traded value) and ``cost`` the
        transaction cost; both are computed by the engine under this context. Cash may
        legitimately go negative only if the engine over-allocates — a v1 long-only
        engine sizes to available equity, so this stays non-negative in practice.
        """
        with localcontext(self._context):
            self._shares[security_id] = self.shares_of(security_id) + shares
            self._cash = self._cash - notional - cost
            self._prune(security_id)

    def sell(
        self, security_id: str, shares: Decimal, cost: Decimal, notional: Decimal
    ) -> None:
        """Remove ``shares`` of ``security_id``, crediting ``notional`` - ``cost`` to
        cash."""
        with localcontext(self._context):
            self._shares[security_id] = self.shares_of(security_id) - shares
            self._cash = self._cash + notional - cost
            self._prune(security_id)

    def set_shares(self, security_id: str, shares: Decimal) -> None:
        """Set the raw share count for ``security_id`` (share-only, no cash effect)."""
        with localcontext(self._context):
            self._shares[security_id] = +shares
            self._prune(security_id)

    # -- corporate-action effects (proposal §D) ------------------------------

    def multiply_shares(self, security_id: str, ratio: Decimal) -> None:
        """A **split**: ``shares *= ratio`` on the ex-date; no cash effect (§D).

        Applied only if the security is held; a split of an unheld security is a no-op.
        Positions stay in unadjusted shares and economically constant (the price series
        is handled by Phase 11's adjusted view if the strategy opts in — proposal §D).
        """
        if security_id not in self._shares:
            return
        with localcontext(self._context):
            self._shares[security_id] = self._shares[security_id] * ratio
            self._prune(security_id)

    def credit_cash(self, amount: Decimal) -> None:
        """A **dividend** (or other cash leg): ``cash += amount`` (§D).

        ``amount`` is ``shares x per_share`` computed by the engine in the action's
        currency (single-currency portfolio, v1 constraint §B). No DRIP.
        """
        with localcontext(self._context):
            self._cash = self._cash + amount

    def liquidate(self, security_id: str, proceeds: Decimal) -> None:
        """A **delisting/merger cash leg**: close ``security_id``, credit ``proceeds``
        (§D).

        Removes the position entirely (identity is retired) and credits the recovery
        value the engine computed (last PIT price x shares, or a ``delisted_no_price``
        carry mark). A no-op if the security is not held.
        """
        if security_id not in self._shares:
            return
        with localcontext(self._context):
            self._cash = self._cash + proceeds
        del self._shares[security_id]

    def rekey(self, old_security_id: str, new_security_id: str, ratio: Decimal) -> None:
        """A **merger** successor mapping: move ``old``'s shares to ``new`` x ``ratio``
        (§D).

        The old position is retired and its shares are mapped to the successor
        ``security_id`` per the exchange ratio (share-for-share is ``ratio = 1``). A
        no-op if the old security is not held. Any cash leg is applied separately by the
        engine via :meth:`credit_cash`.
        """
        if old_security_id not in self._shares:
            return
        with localcontext(self._context):
            moved = self._shares[old_security_id] * ratio
            self._shares[new_security_id] = self.shares_of(new_security_id) + moved
        del self._shares[old_security_id]
        self._prune(new_security_id)

    # -- internals -----------------------------------------------------------

    def _prune(self, security_id: str) -> None:
        """Drop a holding that has rounded to exactly zero shares (keep state
        minimal)."""
        value = self._shares.get(security_id)
        if value is not None and value == _ZERO:
            del self._shares[security_id]

    def snapshot(self) -> dict[str, object]:
        """A deterministic, ``security_id``-sorted dict of the current state.

        Used both in the per-rebalance ledger and (digested) in ``result_hash``. Cash
        and every share count are canonical decimal strings; ordering is total, so the
        serialized bytes are identical for identical state.
        """
        return {
            "cash": str(self._cash),
            "positions": [p.to_dict() for p in self.positions()],
        }
