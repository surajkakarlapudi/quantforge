"""Multiple-comparison correction over a strategy comparison's p-value family (Phase
25).

The first **multiplicity** capability strictly above Phase 24: a pure consumer that
treats the KNOWN pairwise ``p`` values of one sealed
:class:`~quantforge.comparison.result.StrategyComparison` as a single hypothesis family
and asks the question the raw comparison matrix cannot - *once we have looked at every
pair, which apparent differences survive a correction for having run the whole family of
tests?* It resolves the one comparison from the shared Phase 8 sidecar, collects its
KNOWN ``p`` values as the family (recording each UNDEFINED pair as a first-class
exclusion, never imputed), and for each requested method seals the adjusted ``p`` value
+ rejection flag of every family member at a declared ``alpha``. It re-resolves no data,
introduces no new PIT surface, adds no runtime dependency, and creates no new store.

* :class:`~quantforge.multiplicity.spec.MultipleComparisonSpecification` - the
  declarative, content-addressed request: a name, exactly one sealed
  ``source_strategy_comparison_id``, a declared ``alpha`` in ``(0, 1)``, and an ordered,
  duplicate-free tuple of :class:`~quantforge.multiplicity.model.CorrectionMethod`\\ s
  (default: Holm + Benjamini-Yekutieli, both valid under arbitrary dependence).
* :class:`~quantforge.multiplicity.engine.MultipleComparisonEngine` - resolves +
  verifies the source comparison (present, a ``StrategyComparison``, id matches),
  collects the KNOWN-``p`` family + the UNDEFINED exclusions (MC-3), corrects the family
  by each method (:func:`~quantforge.multiplicity.compute.correct_family`), and seals a
  :class:`~quantforge.multiplicity.result.MultipleComparisonCorrection`, persisting it
  write-once to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.multiplicity_engine`).
* :class:`~quantforge.multiplicity.result.MultipleComparisonCorrection` - the sealed,
  content-addressed record: the ``(id, result_hash)`` pin to the source comparison, the
  declared ``alpha``, the KNOWN ``p`` value family, the UNDEFINED exclusions, and per
  method the honest error-rate / dependence labels plus each family cell's adjusted
  ``p`` value + rejection flag. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT** (MC-6): not a ``Pit*`` type and no as-of
  accessor.
* :class:`~quantforge.multiplicity.model.CorrectionMethod` /
  :class:`~quantforge.multiplicity.model.ErrorRate` /
  :class:`~quantforge.multiplicity.model.DependenceAssumption` - the closed method
  vocabulary and each method's honest labels: Bonferroni / Holm control the family-wise
  error rate, Benjamini-Hochberg / Benjamini-Yekutieli the false-discovery rate; all but
  Benjamini-Hochberg are valid under arbitrary dependence, and Benjamini-Hochberg's
  independence / PRDS assumption is sealed alongside its results so it can never be
  mistaken for a dependence-robust guarantee (MC-6).

Every identity is content-addressed (:mod:`quantforge.multiplicity.identity`) and
transitively pins the source comparison's ``result_hash``, every value is
deterministically serializable and computed in exact ``Decimal`` arithmetic under a
pinned context (no RNG, no float, no iterative solver), and every failure follows the
raise-vs-record split (:mod:`quantforge.multiplicity.errors`): a request / consistency
defect raises; a pairwise cell genuinely UNDEFINED in the source is excluded and
recorded with its reason.
"""

from __future__ import annotations

from quantforge.multiplicity.compute import MethodComputation, correct_family
from quantforge.multiplicity.engine import MultipleComparisonEngine
from quantforge.multiplicity.errors import (
    MultiplicityConfigurationError,
    MultiplicityConsistencyError,
    MultiplicityError,
)
from quantforge.multiplicity.identity import (
    multiple_comparison_id,
    multiple_comparison_result_hash,
)
from quantforge.multiplicity.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
    method_dependence,
    method_error_rate,
)
from quantforge.multiplicity.result import (
    BOUNDARY_PIT,
    MULTIPLICITY_RESULT_FORMAT_VERSION,
    ExcludedCell,
    FamilyCell,
    MethodCell,
    MethodResult,
    MultipleComparisonCorrection,
    MultiplicityCoverage,
)
from quantforge.multiplicity.spec import (
    DEFAULT_METHODS,
    MultipleComparisonSpecification,
)
from quantforge.multiplicity.version import (
    MULTIPLICITY_ENGINE_VERSION,
    MULTIPLICITY_METHOD_VERSION,
    MULTIPLICITY_SPEC_VERSION,
    MultipleComparisonEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "DEFAULT_METHODS",
    "MULTIPLICITY_ENGINE_VERSION",
    "MULTIPLICITY_METHOD_VERSION",
    "MULTIPLICITY_RESULT_FORMAT_VERSION",
    "MULTIPLICITY_SPEC_VERSION",
    "CorrectionMethod",
    "DependenceAssumption",
    "ErrorRate",
    "ExcludedCell",
    "FamilyCell",
    "MethodCell",
    "MethodComputation",
    "MethodResult",
    "MultipleComparisonCorrection",
    "MultipleComparisonEngine",
    "MultipleComparisonEngineVersion",
    "MultipleComparisonSpecification",
    "MultiplicityConfigurationError",
    "MultiplicityConsistencyError",
    "MultiplicityCoverage",
    "MultiplicityError",
    "correct_family",
    "default_decimal_context",
    "method_dependence",
    "method_error_rate",
    "multiple_comparison_id",
    "multiple_comparison_result_hash",
]
