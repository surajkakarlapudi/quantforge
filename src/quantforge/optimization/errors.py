"""Exception hierarchy for the portfolio-optimization layer (Phase 21, §15).

Rooted at :class:`PortfolioOptimizationError` so a caller can catch every failure of
this layer with one type. Phase 21 is a *pure consumer* of Phase 20: it resolves exactly
one already-sealed :class:`~quantforge.factorrisk.result.FactorRiskModel` from the
shared research sidecar and computes the global minimum-variance (GMV) factor-weight
vector over that model's covariance matrix. It resolves no data at any ``T`` and
re-derives nothing from source, so its only failures are of the request or of a
consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the factor-risk layer
in particular:

* A **data / estimation condition** - a problem that is genuinely undefined for the data
  (a non-positive-definite covariance matrix, so ``Σ⁻¹1`` does not exist and the GMV is
  undefined) - is **never** an exception. It is recorded as a first-class UNDEFINED
  :class:`~quantforge.optimization.model.StatValue` carrying *why*
  (``SINGULAR_COVARIANCE``, PO-4), never fabricated, never a divide-by-zero, never a
  repaired / regularized / pseudo-inverted matrix.
* A **configuration / consistency defect** - an empty name / spec version / risk-model
  id, an objective outside the closed vocabulary, ``fully_invested`` not ``True``, a
  referenced id absent from the sidecar, a referenced record whose
  ``research_result_id`` disagrees with the request or that is not a
  ``FactorRiskModel``, a factor count outside ``2..N_MAX``, or a corrupt / non-finite /
  UNDEFINED / missing covariance cell - *is* raised. These are our bugs, surfaced rather
  than silently resolved. A raised error is always preferable to a wrong portfolio.
"""

from __future__ import annotations

__all__ = [
    "PortfolioOptimizationConfigurationError",
    "PortfolioOptimizationConsistencyError",
    "PortfolioOptimizationError",
]


class PortfolioOptimizationError(Exception):
    """Base class for all portfolio-optimization-layer errors."""


class PortfolioOptimizationConfigurationError(PortfolioOptimizationError):
    """A portfolio-optimization request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.optimization.spec.PortfolioOptimizationSpecification` (an empty
    ``name`` / ``spec_version`` / ``factor_risk_id``; an ``objective`` outside the
    closed vocabulary; ``fully_invested`` not ``True`` in v1) or for a
    non-:class:`~quantforge.optimization.spec.PortfolioOptimizationSpecification`
    argument to the engine. We refuse to guess a request's intent, exactly as the
    factor-risk layer refuses a misconfigured construction.
    """


class PortfolioOptimizationConsistencyError(PortfolioOptimizationError):
    """A portfolio cannot be honestly optimized from the referenced artifact - surfaced.

    Fail-closed guard for the reference contract (§15, PO-1/PO-3): a ``factor_risk_id``
    absent from the research sidecar, a referenced record whose ``research_result_id``
    disagrees with the requested id or that is not a
    :class:`~quantforge.factorrisk.result.FactorRiskModel`, a factor count outside
    ``2..N_MAX``, or a corrupt covariance matrix (a non-finite / UNDEFINED / missing /
    out-of-range covariance cell in a record whose covariance cells must all be KNOWN by
    construction). Each is a consistency violation and is raised - never silently
    computed around. (A non-positive-definite covariance is *not* raised: the GMV is
    genuinely undefined for it, so it is recorded as a first-class UNDEFINED
    ``SINGULAR_COVARIANCE`` result, PO-4.)
    """
