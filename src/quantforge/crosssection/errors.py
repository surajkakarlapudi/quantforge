"""Exception hierarchy for the cross-sectional-regression layer (Phase 18, §9).

Rooted at :class:`CrossSectionError` so a caller can catch every failure of this layer
with one type. Phase 18 is a *pure consumer* of Phases 9/10/11 (the multivariate
cross-sectional sibling of the Phase 16 univariate IC): it resolves the universe PIT
as-of each evaluation date, reads the ``K``-signal cross-section as
:class:`~quantforge.panel.model.PitPanel`\\ s, and pairs each member with a realized
forward return from PIT-gated adjusted prices, then runs one exact-``Decimal`` OLS per
date and aggregates the per-date coefficients into Fama-MacBeth premia. It consumes no
``BacktestResult`` and reads the raw corpora only through the existing PIT accessors, so
its only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§9):

* A **data / research condition** - a per-date design that is genuinely undefined for
  the data (too few members for the requested model, a singular/collinear cross-section,
  a zero-variance regressand, a premium whose per-date coefficient was never KNOWN) - is
  **never** an exception. It is recorded as a first-class UNDEFINED
  :class:`~quantforge.crosssection.model.StatValue` carrying *why*, and surfaced - never
  fabricated, never a divide-by-zero, never silently dropped. A member lacking any of
  the ``K`` PIT signals at ``T`` or a computable forward return is excluded from that
  date's cross-section and counted in coverage (XS-4).
* A **configuration / consistency defect** - an empty name, no factors or more than
  ``K_MAX``, a duplicated factor, a malformed horizon, a non-``MetricPeriod`` period, a
  corpus pin that does not match the pinned corpus, a non-unique corpus normalizer, or a
  run in which fewer than two evaluation dates yield a defined regression - *is* raised.
  These are our bugs, surfaced rather than silently resolved. A raised error is always
  preferable to a wrong regression record.
"""

from __future__ import annotations

__all__ = [
    "CrossSectionConfigurationError",
    "CrossSectionConsistencyError",
    "CrossSectionError",
]


class CrossSectionError(Exception):
    """Base class for all cross-sectional-regression-layer errors."""


class CrossSectionConfigurationError(CrossSectionError):
    """A cross-sectional-regression request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.crosssection.spec.CrossSectionalRegressionSpecification` (an
    empty ``name`` / ``spec_version`` / corpus pin, an empty or over-``K_MAX`` factor
    tuple, a duplicated factor, a factor whose ``period`` is not a
    :class:`~quantforge.metrics.model.MetricPeriod`, a ``forward_horizon`` not of the
    form ``"<n>d"`` with ``n >= 1``, a ``universe`` or ``schedule`` missing its
    content-addressed identity), for a non-specification argument to ``estimate``, or
    for a study in which fewer than two scheduled dates yield a defined cross-sectional
    regression (so the Fama-MacBeth aggregation would have no time-series dispersion and
    the whole record is meaningless - the Phase 16 ``_MIN_PAIRS`` / Phase 15
    ``_MIN_PERIODS`` precedent). We refuse to guess a request's intent, exactly as Phase
    12 refuses a misconfigured backtest.
    """


class CrossSectionConsistencyError(CrossSectionError):
    """A record cannot be honestly computed from the pinned corpora - surfaced.

    Fail-closed guard for the corpus-pin contract (XS-1, §9): the fundamentals
    ``dataset_version_id`` or the market ``market_dataset_version_id`` re-derived from
    the universe's source companies and their securities does not match the spec's
    declared pin, or the corpus does not admit a single normalizing dataset version (a
    non-unique normalizer). Because a regression reads both corpora PIT-as-of over an
    append-only store, an unpinned or drifted corpus would silently change the answer;
    the mismatch is raised - never silently computed around. A corrupt / non-finite
    decimal read from the corpus is likewise raised, never guessed.
    """
