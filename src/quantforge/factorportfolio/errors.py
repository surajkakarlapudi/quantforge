"""Exception hierarchy for the factor-portfolio layer (Phase 19, §9).

Rooted at :class:`FactorPortfolioError` so a caller can catch every failure of this
layer with one type. Phase 19 is a *pure consumer* of Phases 9/10/11 (a constructive
sibling of the Phase 16 diagnostic): it resolves the universe PIT as-of each rebalance
date, reads the signal cross-section as a :class:`~quantforge.panel.model.PitPanel`,
sorts the members into ``Q`` quantiles, forms a long (top) and short (bottom) leg, and
pairs each member with a realized forward return from PIT-gated adjusted prices - the
per-period factor return is the long-minus-short spread, chained into a return series.
It consumes no ``BacktestResult`` and reads the raw corpora only through the existing
PIT accessors, so its only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§9):

* A **data / research condition** - a period that is genuinely undefined for the data
  (too few members to fill both legs, an empty long or short leg, a return series with
  no or a single valid period, a zero-variance series for the Sharpe / t-statistic) - is
  **never** an exception. It is recorded as a first-class UNDEFINED
  :class:`~quantforge.factorportfolio.model.StatValue` carrying *why*, and surfaced -
  never fabricated, never a divide-by-zero, never silently dropped. A member lacking the
  PIT signal at ``T`` or a computable forward return is excluded from that period and
  counted in coverage (P19-4).
* A **configuration / consistency defect** - an empty name, an empty signal, ``Q < 2``,
  an unknown weighting scheme, a malformed horizon, a non-``MetricPeriod`` period, a
  corpus pin that does not match the pinned corpus, a non-unique corpus normalizer, or a
  run in which fewer than two rebalance dates yield a defined factor return - *is*
  raised. These are our bugs, surfaced rather than silently resolved. A raised error is
  always preferable to a wrong factor-portfolio record.
"""

from __future__ import annotations

__all__ = [
    "FactorPortfolioConfigurationError",
    "FactorPortfolioConsistencyError",
    "FactorPortfolioError",
]


class FactorPortfolioError(Exception):
    """Base class for all factor-portfolio-layer errors."""


class FactorPortfolioConfigurationError(FactorPortfolioError):
    """A factor-portfolio request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.factorportfolio.spec.FactorPortfolioSpecification` (an empty
    ``name`` / ``signal`` / ``spec_version`` / corpus pin, a ``period`` that is not a
    :class:`~quantforge.metrics.model.MetricPeriod`, ``quantiles < 2``, an unknown
    ``weighting`` scheme, a non-canonical ``risk_free_per_period`` /
    ``periods_per_year``, a ``forward_horizon`` not of the form ``"<n>d"`` with ``n >=
    1``, a ``universe`` or ``schedule`` missing its content-addressed identity), for a
    non-specification argument to ``construct``, or for a study in which fewer than two
    rebalance dates yield a defined factor return (so the return series has no
    time-series dispersion and the summary is meaningless - the Phase 18
    ``_MIN_VALID_DATES`` / Phase 16 ``_MIN_PAIRS`` precedent). We refuse to guess a
    request's intent, exactly as Phase 12 refuses a misconfigured backtest.
    """


class FactorPortfolioConsistencyError(FactorPortfolioError):
    """A record cannot be honestly computed from the pinned corpora - surfaced.

    Fail-closed guard for the corpus-pin contract (P19-1, §9): the fundamentals
    ``dataset_version_id`` or the market ``market_dataset_version_id`` re-derived from
    the universe's source companies and their securities does not match the spec's
    declared pin, or the corpus does not admit a single normalizing dataset version (a
    non-unique normalizer). Because a factor portfolio reads both corpora PIT-as-of over
    an append-only store, an unpinned or drifted corpus would silently change the
    answer; the mismatch is raised - never silently computed around. A corrupt /
    non-finite decimal read from the corpus is likewise raised, never guessed.
    """
