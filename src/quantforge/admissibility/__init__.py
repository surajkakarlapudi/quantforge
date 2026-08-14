"""Strategy admissibility over three sealed ex-post verdicts of one strategy (Phase 33).

The first **multi-source** consumer in the research spine, and the capstone over the
ex-post validator battery: a pure consumer that resolves the three sealed verdicts of
one strategy - a :class:`~quantforge.stability.result.WalkForwardStability`, a
:class:`~quantforge.calsig.result.CalibrationSignificance`, and a
:class:`~quantforge.netcostsig.result.NetOfCostSignificance` - reads the answer each
layer already computed verbatim (never recomputed, AD-4), and asks what no single layer
answers: *taken together, is this strategy admissible?* It seals a single joint
verdict - ADMISSIBLE only when the book was STABLE, the risk model was not
significantly mis-calibrated (the two-sided calibration p-value exceeds a declared
``alpha``), and the after-cost edge was significantly profitable (the one-sided
net-of-cost p-value is at most ``alpha`` and the edge is PROFITABLE); INADMISSIBLE when
every criterion was decidable and at least one failed; UNDEFINED (fail closed) when any
criterion could not be decided. It resolves the three records from the shared Phase 8
sidecar, adds no new statistical primitive (it evaluates only exact-``Decimal``
comparisons), introduces no new PIT surface, adds no runtime dependency, uses no
``_linalg`` primitive, and creates no new store.

* :class:`~quantforge.admissibility.spec.AdmissibilitySpecification` - the declarative,
  content-addressed request: a name, exactly one ``source_stability_id`` /
  ``source_calibration_significance_id`` /
  ``source_net_of_cost_significance_id``, and the declared significance level ``alpha``
  (default :data:`~quantforge.admissibility.spec.DEFAULT_ALPHA`), canonicalized and
  folded into the id.
* :class:`~quantforge.admissibility.engine.AdmissibilityEngine` - resolves + verifies
  the three source verdicts (present, correctly typed, id matches), reduces each to its
  primitive fact (AD-4), decides the joint verdict
  (:func:`~quantforge.admissibility.compute.decide_admissibility`), and seals a
  :class:`~quantforge.admissibility.result.StrategyAdmissibility`, persisting it
  write-once to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.admissibility_engine`).
* :class:`~quantforge.admissibility.result.StrategyAdmissibility` - the sealed,
  content-addressed record: three ``(id, result_hash)`` pins to the source verdicts and
  the :class:`~quantforge.admissibility.result.AdmissibilitySummary` (the verdict, the
  declared level, and the three ordered criteria). Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT** (AD-6): not a ``Pit*`` type and no as-of
  accessor.
* :class:`~quantforge.admissibility.model.AdmissibilityVerdict` /
  :class:`~quantforge.admissibility.model.CriterionKind` /
  :class:`~quantforge.admissibility.model.CriterionStatus` /
  :class:`~quantforge.admissibility.model.AdmissibilityUndefinedReason` /
  :class:`~quantforge.admissibility.model.Criterion` - the closed fail-closed
  vocabulary: the roll-up verdict, which criterion a cell describes, whether it
  passed / failed / is undefined, why a criterion is undefined, and the evaluated
  criterion cell.

Every identity is content-addressed (:mod:`quantforge.admissibility.identity`) and
transitively pins all three sources' ``result_hash``, every value is deterministically
serializable and decided in exact ``Decimal`` arithmetic under a pinned context (no
transcendental, no RNG, no float, no unbounded iteration), and every failure follows the
raise-vs-record split (:mod:`quantforge.admissibility.errors`): a request / consistency
defect raises; a consumed verdict that is genuinely UNDEFINED seals an UNDEFINED
criterion and a fail-closed UNDEFINED roll-up, never imputed.
"""

from __future__ import annotations

from quantforge.admissibility.compute import (
    AdmissibilityComputation,
    AdmissibilityInputs,
    decide_admissibility,
)
from quantforge.admissibility.engine import AdmissibilityEngine
from quantforge.admissibility.errors import (
    AdmissibilityConfigurationError,
    AdmissibilityConsistencyError,
    AdmissibilityError,
)
from quantforge.admissibility.identity import (
    admissibility_id,
    admissibility_result_hash,
)
from quantforge.admissibility.model import (
    AdmissibilityUndefinedReason,
    AdmissibilityVerdict,
    Criterion,
    CriterionKind,
    CriterionStatus,
)
from quantforge.admissibility.result import (
    ADMISSIBILITY_RESULT_FORMAT_VERSION,
    BOUNDARY_PIT,
    AdmissibilitySummary,
    StrategyAdmissibility,
)
from quantforge.admissibility.spec import (
    DEFAULT_ALPHA,
    AdmissibilitySpecification,
)
from quantforge.admissibility.version import (
    ADMISSIBILITY_ENGINE_VERSION,
    ADMISSIBILITY_METHOD_VERSION,
    ADMISSIBILITY_SPEC_VERSION,
    AdmissibilityEngineVersion,
    default_decimal_context,
)

__all__ = [
    "ADMISSIBILITY_ENGINE_VERSION",
    "ADMISSIBILITY_METHOD_VERSION",
    "ADMISSIBILITY_RESULT_FORMAT_VERSION",
    "ADMISSIBILITY_SPEC_VERSION",
    "BOUNDARY_PIT",
    "DEFAULT_ALPHA",
    "AdmissibilityComputation",
    "AdmissibilityConfigurationError",
    "AdmissibilityConsistencyError",
    "AdmissibilityEngine",
    "AdmissibilityEngineVersion",
    "AdmissibilityError",
    "AdmissibilityInputs",
    "AdmissibilitySpecification",
    "AdmissibilitySummary",
    "AdmissibilityUndefinedReason",
    "AdmissibilityVerdict",
    "Criterion",
    "CriterionKind",
    "CriterionStatus",
    "StrategyAdmissibility",
    "admissibility_id",
    "admissibility_result_hash",
    "decide_admissibility",
    "default_decimal_context",
]
