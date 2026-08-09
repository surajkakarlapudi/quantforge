"""The content-addressed identities for the backtesting layer (proposal §F, §G, D6).

Every identity here follows the project's §11 discipline verbatim — ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``,
or iteration order (proposal §F, §G; data-model invariant 13). Re-declaring the
identical request reproduces every id, on any machine.

The ids, and what each pins:

    strategy_version      = sha256( domain "strategy/1", canonical JSON of the
                                    ordered declarative strategy steps )
                                    (§F)
    schedule_id           = sha256( domain "backtest-schedule/1", kind, *components )
    (§D3)
    cost_model_id         = sha256( domain "cost-model/1", canonical JSON of costs )
    accounting_version_id = sha256( domain "accounting/1", canonical JSON of policy )
    result_hash           = sha256( canonical JSON of the ordered rebalance-ledger
                                    outcome digests )
                                    (§G, §H)
    backtest_id           = sha256( strategy_version, schedule_id, universe id,
                                    dataset_version_id, market_dataset_version_id,
                                    cost_model_id, accounting_version_id,
                                    backtest_engine_version_id,
                                    risk_free_per_period, periods_per_year,
                                    result_hash )
                                    (D6)

``strategy_version`` is an **honest** content hash (proposal §F): it changes iff the
declarative logic changes and is invariant to formatting/naming — never a hash of
arbitrary Python source (over-sensitive to whitespace, under-sensitive to imported
helpers). ``backtest_id`` folds in **every** result-changing input (D6): omitting any
one would let two materially different backtests share an id — dishonest
content-addressing, rejected here.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "accounting_version_id",
    "backtest_id",
    "boundary_key",
    "cost_model_id",
    "result_hash",
    "schedule_id",
    "strategy_version",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a date, a currency code, a metric key, or a canonical-JSON
# payload, so a joined payload is unambiguous.
_SEP = "\x00"

# Domain tags. A new tag (or a bump) yields distinct ids without altering any
# already-computed id — the extensibility discipline shared with PriceAxis /
# UniverseSpecification / MetricEngineVersion.
_STRATEGY_DOMAIN = "strategy/1"
_SCHEDULE_DOMAIN = "backtest-schedule/1"
_COST_MODEL_DOMAIN = "cost-model/1"
_ACCOUNTING_DOMAIN = "accounting/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def strategy_version(steps: list[dict[str, object]]) -> str:
    """``sha256(domain, canonical JSON of the ordered steps)`` — the strategy id (§F).

    ``steps`` is the strategy's ordered, typed step declaration (signal / filter /
    rank / select / weight). The order is load-bearing (a filter before vs. after a
    rank is a different strategy) and preserved verbatim — the list is *not* sorted;
    only the JSON *keys within* each step are sorted, so equal logic always yields
    identical bytes regardless of formatting or attribute naming.
    """
    payload = _SEP.join((_STRATEGY_DOMAIN, _canonical_json(steps)))
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def schedule_id(*, kind: str, components: list[str]) -> str:
    """``sha256(domain, kind, *components)`` — the rebalance-schedule id (§D3).

    Mirrors :attr:`~quantforge.market.axis.PriceAxis.axis_id`: an explicit schedule
    hashes its ordered instants; a generator schedule hashes its declared bounds. The
    domain tag and ``kind`` are always included so a future schedule kind hashes
    distinctly and leaves every existing ``schedule_id`` unchanged.
    """
    payload = _SEP.join((_SCHEDULE_DOMAIN, kind, *components))
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def cost_model_id(payload: dict[str, object]) -> str:
    """``sha256(domain, canonical JSON of the cost fields)`` — the cost-model id.

    Folds every cost parameter (proportional bps, fixed-per-order, any short carry)
    into identity, so two backtests that differ only in costs get different
    ``backtest_id``s (D6).
    """
    joined = _SEP.join((_COST_MODEL_DOMAIN, _canonical_json(payload)))
    return f"sha256:{sha256_hex(joined.encode('utf-8'))}"


def accounting_version_id(payload: dict[str, object]) -> str:
    """``sha256(domain, canonical JSON of the accounting policy)`` — the policy id.

    Folds the execution convention (close / next-open) and dividend-timing choice
    into identity: a different accounting convention is a different result, so it must
    be a different ``backtest_id`` (D6, D8).
    """
    joined = _SEP.join((_ACCOUNTING_DOMAIN, _canonical_json(payload)))
    return f"sha256:{sha256_hex(joined.encode('utf-8'))}"


def boundary_key(*, kind: str, value: str) -> str:
    """The serialized boundary discriminator, mirroring the Phase 8/10 helper.

    ``"pit:<as_of>"`` (a point-in-time boundary) or ``"rev:<dataset_version_id>"``,
    so a PIT and a REVISED artifact never collide in a content hash. Reused here for
    per-rebalance provenance keys.
    """
    return f"{kind}:{value}"


def result_hash(rebalance_digests: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered per-rebalance outcome digests — the output seal (§G).

    ``rebalance_digests`` is the ordered list of minimal per-rebalance dicts (the
    as_of, the resolved holdings, the fills, the applied actions, the valuation) in
    schedule order; it is serialized with the canonical-JSON discipline so equal
    ledgers always yield identical bytes. Order is preserved (the list is *not*
    re-sorted): the schedule's order is load-bearing.
    """
    return f"sha256:{sha256_hex(_canonical_json(rebalance_digests).encode('utf-8'))}"


def backtest_id(
    *,
    strategy_version: str,
    schedule_id: str,
    universe_id: str,
    dataset_version_id: str,
    market_dataset_version_id: str,
    cost_model_id: str,
    accounting_version_id: str,
    backtest_engine_version_id: str,
    risk_free_per_period: str,
    periods_per_year: str,
    result_hash: str,
) -> str:
    """The identity of a whole backtest — request **and** output (D6, §G).

    Pins every result-changing input: the strategy logic, the rebalance schedule, the
    universe/specification, **both** corpus snapshots (fundamentals + market — BT-1),
    the cost model, the accounting policy, the engine version (numeric config), the
    recorded Sharpe/annualization convention (``risk_free_per_period`` +
    ``periods_per_year`` — they change the reported statistics, hence the result), and
    the sealed ``result_hash``. Same inputs ⇒ same id and same result, on any machine;
    a change to *any* input (including a corpus pin or the annualization convention)
    yields a different id, never a silently different result under the same id.
    """
    payload = _SEP.join(
        (
            strategy_version,
            schedule_id,
            universe_id,
            dataset_version_id,
            market_dataset_version_id,
            cost_model_id,
            accounting_version_id,
            backtest_engine_version_id,
            risk_free_per_period,
            periods_per_year,
            result_hash,
        )
    )
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"
