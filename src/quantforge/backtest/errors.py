"""Exception hierarchy for the backtesting layer (Phase 12, proposal §L).

Rooted at :class:`BacktestError` so a caller can catch every failure of this layer
with one type. Phase 12 *composes* the Phase 7/8/9/10/11 engines through their
existing public ``*_as_of`` accessors; it computes no data of its own beyond
deterministic portfolio accounting and statistics (proposal §J).

The governing posture matches the rest of the project (data-model §12; factors
§1.5) — a sharp split between two failure kinds, extended by the Phase 12 BT-4
"fail-closed simulation" invariant:

* A **data / simulation condition** — an UNDEFINED signal for a member, an
  unavailable execution price, a member with no PIT-eligible price at a rebalance — is
  **never** an exception. It excludes the member from selection, or leaves an order
  ``unfilled``, and is recorded explicitly in the ledger (BT-4). A backtest over many
  rebalances must record "excluded filer X at T because Y" without aborting.
* A **configuration / consistency defect** — a malformed specification, a corpus
  pin that fails to verify on re-run (BT-1), an unrecognized corporate-action payload
  shape, a mixed-currency portfolio, or stored derived state that violates an
  invariant on read — *is* raised. These are our bugs, surfaced rather than silently
  resolved. A raised error is always preferable to a wrong backtest.
"""

from __future__ import annotations

__all__ = [
    "BacktestConfigurationError",
    "BacktestConsistencyError",
    "BacktestError",
]


class BacktestError(Exception):
    """Base class for all backtesting-layer errors."""


class BacktestConfigurationError(BacktestError):
    """A backtest request is internally inconsistent — our bug, surfaced.

    Raised for a malformed :class:`~quantforge.backtest.spec.BacktestSpecification`
    (an empty schedule, an unparseable selection rule, a non-positive initial
    capital), a mixed-currency portfolio (a v1 constraint, proposal §B), or an
    unrecognized corporate-action payload shape that cannot be applied deterministically
    (proposal §D rule 3). We refuse to guess a backtest's intent, exactly as Phase 7
    refuses a misconfigured formula and Phase 9 a misconfigured specification.
    """


class BacktestConsistencyError(BacktestError):
    """A computed or pinned backtest artifact violates an invariant on read.

    Fail-closed guard for the reproducibility contract (BT-1, data-model §12): a
    pinned ``dataset_version_id`` / ``market_dataset_version_id`` that does not match
    the corpus on re-run, or a re-computed
    :class:`~quantforge.backtest.result.BacktestResult`
    whose payload differs from a stored one under the same ``backtest_id``, is a
    determinism violation and is raised — never silently resolved or overwritten.
    """
