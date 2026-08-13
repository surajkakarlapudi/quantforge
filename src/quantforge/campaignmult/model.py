"""The campaign-multiplicity vocabulary - reused verbatim from Phase 25 (§15, CM-5).

A **campaign-multiplicity correction** treats the per-trial one-sided
Probabilistic-Sharpe-Ratio p-values ``p_i = 1 - PSR_i`` of one sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation` as a single hypothesis
family and adjusts them so that a family-wise error rate (FWE) or a false-discovery rate
(FDR) is controlled at a declared ``alpha``. The method vocabulary and each method's
honest error-rate / dependence labels are **identical** to Phase 25's - the correction
core (:func:`~quantforge.multiplicity.compute.correct_family`) is reused verbatim, so
its vocabulary must be too. Rather than redefine a parallel (and drift-prone) enum, this
module **re-exports** the single source of truth from
:mod:`quantforge.multiplicity.model`:

* :class:`~quantforge.multiplicity.model.CorrectionMethod` - the closed set of
  procedures: ``BONFERRONI`` / ``HOLM`` (FWE), ``BENJAMINI_HOCHBERG`` /
  ``BENJAMINI_YEKUTIELI`` (FDR).
* :class:`~quantforge.multiplicity.model.ErrorRate` - which error quantity a method
  controls.
* :class:`~quantforge.multiplicity.model.DependenceAssumption` - the dependence
  structure under which a method's guarantee holds. Load-bearing for honesty (CM-6): the
  per-trial ``PSR`` values of one campaign are dependent (the trials may overlap in time
  and share a corpus), so Benjamini-Hochberg's independence / PRDS assumption is sealed
  alongside its results and can never be mistaken for a dependence-robust guarantee.
* :func:`~quantforge.multiplicity.model.method_error_rate` /
  :func:`~quantforge.multiplicity.model.method_dependence` - the single source of truth
  for a method's labels.

Re-exporting (rather than re-declaring) guarantees the label mapping can never diverge
from the correction core that produces the adjusted values.
"""

from __future__ import annotations

from quantforge.multiplicity.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
    method_dependence,
    method_error_rate,
)

__all__ = [
    "CorrectionMethod",
    "DependenceAssumption",
    "ErrorRate",
    "method_dependence",
    "method_error_rate",
]
