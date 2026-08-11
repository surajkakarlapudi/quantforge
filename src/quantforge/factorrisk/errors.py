"""Exception hierarchy for the factor-risk layer (Phase 20, §12).

Rooted at :class:`FactorRiskError` so a caller can catch every failure of this layer
with one type. Phase 20 is a *pure consumer* of Phase 19: it resolves already-sealed
:class:`~quantforge.factorportfolio.result.FactorPortfolio` records (an ordered set of
*N* factor return series) from the shared research sidecar and estimates their
second-moment structure (covariance, correlation, per-factor volatility, and the mean
vector). It resolves no data at any ``T`` and re-derives nothing from source, so its
only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§12), and the attribution /
factor-portfolio layers in particular:

* A **data / estimation condition** - a statistic that is genuinely undefined for the
  data (a correlation cell whose factor has zero volatility over the common window) - is
  **never** an exception. It is recorded as a first-class UNDEFINED
  :class:`~quantforge.factorrisk.model.StatValue` carrying *why* (FR-4), and surfaced -
  never fabricated, never a divide-by-zero.
* A **configuration / consistency defect** - an empty name, fewer than two or more than
  ``N_MAX`` factor ids, a duplicate or empty id, a non-decimal / non-positive
  ``periods_per_year``, a referenced id absent from the sidecar, a referenced record
  whose ``research_result_id`` disagrees with the request or that is not a
  ``FactorPortfolio``, factors that are not commensurable (a different ``schedule_id``
  or producing-engine version), or fewer than two complete-case common estimation dates
  - *is* raised. These are our bugs, surfaced rather than silently resolved. A raised
  error
  is always preferable to a wrong risk model.
"""

from __future__ import annotations

__all__ = [
    "FactorRiskConfigurationError",
    "FactorRiskConsistencyError",
    "FactorRiskError",
]


class FactorRiskError(Exception):
    """Base class for all factor-risk-layer errors."""


class FactorRiskConfigurationError(FactorRiskError):
    """A factor-risk request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.factorrisk.spec.FactorRiskSpecification` (an empty ``name`` or
    ``spec_version``; fewer than two or more than ``N_MAX`` factor ids; an empty or
    duplicate id; a non-decimal or non-positive ``periods_per_year``), for a
    non-:class:`~quantforge.factorrisk.spec.FactorRiskSpecification` argument, or for a
    referenced factor set that yields fewer than two complete-case common estimation
    dates (so the second moment has no dispersion to estimate). We refuse to guess a
    request's intent, exactly as Phase 19 refuses a misconfigured construction.
    """


class FactorRiskConsistencyError(FactorRiskError):
    """A model cannot be honestly estimated from the referenced artifacts - surfaced.

    Fail-closed guard for the reference + commensurability contract (§12, FR-1/FR-3): a
    ``factor_portfolio_id`` absent from the research sidecar, a referenced record whose
    ``research_result_id`` disagrees with the requested id or that is not a
    :class:`~quantforge.factorportfolio.result.FactorPortfolio`, a corrupt / non-finite
    factor-return cell, or a factor set that does not all share one ``schedule_id`` and
    one ``factor_portfolio_engine_version_id`` (their return series are not
    commensurable). Each is a consistency violation and is raised - never silently
    computed around. (A corpus-pin difference is *not* raised: it is surfaced as
    :attr:`~quantforge.factorrisk.result.FactorRiskModel.pin_mismatch` and the model is
    still estimated, exactly as ``FactorAttribution.pin_mismatch`` does.)
    """
