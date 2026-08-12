"""The multiple-comparison-correction transformation version (Phase 25, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    multiplicity_engine_version_id = hash(code_version, config_hash)

For Phase 25 the "transformation" is the **multiple-comparison-correction engine** that
turns a declarative
:class:`~quantforge.multiplicity.spec.MultipleComparisonSpecification` (naming exactly
one sealed :class:`~quantforge.comparison.result.StrategyComparison` and a declared
``alpha`` + method set) into a sealed
:class:`~quantforge.multiplicity.result.MultipleComparisonCorrection` - the family-wise
(Holm, Bonferroni) and false-discovery-rate (Benjamini-Yekutieli, Benjamini-Hochberg)
adjusted ``p`` values plus a rejection set over the source comparison's KNOWN pairwise
``p`` value family. This module pins that engine logic with a stable version id,
following the exact pattern of
:class:`~quantforge.comparison.version.StrategyComparisonEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Two properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All correction arithmetic - the
  per-rank adjusted-``p`` multipliers, the Benjamini-Yekutieli harmonic constant
  ``c(m) = Σ_{k=1}^{m} 1/k``, the running min / running max monotonicity enforcement,
  the ``min(1, ·)`` capping, and the ``p_adj ≤ alpha`` rejection comparison - runs under
  an explicit :class:`decimal.Context` (precision + rounding). It is folded into
  ``config_hash``, so a change to it necessarily produces a new, distinguishable
  ``multiplicity_engine_version_id``. The default is **precision 34,
  ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The method version is part of the version.** Phase 25 computes its own
  self-contained step-up / step-down adjusted-``p`` procedures
  (:data:`MULTIPLICITY_METHOD_VERSION`). Unlike Phase 23 / Phase 24 it reuses **no**
  standard-normal primitive (it consumes already-sealed ``p`` values), so there is no
  normal-primitive version to fold. The method version is folded into ``config_hash``,
  so a change to it yields a new, distinguishable engine id.

Changing the correction logic in a way that can alter a computed value must bump
:data:`MULTIPLICITY_ENGINE_VERSION` (the code version) or
:data:`MULTIPLICITY_METHOD_VERSION` (the statistical method).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "MULTIPLICITY_ENGINE_VERSION",
    "MULTIPLICITY_METHOD_VERSION",
    "MULTIPLICITY_SPEC_VERSION",
    "MultipleComparisonEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``multiple_comparison_id`` (§13). Bump
# it when the serialized meaning of a request changes - never when engine logic changes
# (that is ``MULTIPLICITY_ENGINE_VERSION``). Shares the ``multiplicity/1`` string with
# the identity domain tag by construction (the prior-phase precedent).
MULTIPLICITY_SPEC_VERSION = "multiplicity/1"

# Bump whenever the correction engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
MULTIPLICITY_ENGINE_VERSION = "multiplicity-engine/1"

# Bump whenever Phase 25's *statistical method* changes - the family collection
# (KNOWN-``p`` selection + UNDEFINED exclusion), the total-order sort, the Bonferroni /
# Holm / Benjamini-Hochberg / Benjamini-Yekutieli adjusted-``p`` procedures, the
# harmonic constant, the monotonicity enforcement, the ``min(1, ·)`` capping, or the
# ``p_adj ≤ alpha`` rejection rule. Folded into ``config_hash`` so a method change is a
# new, distinguishable engine version (§13).
MULTIPLICITY_METHOD_VERSION = "multiplicity-method/1"

# The pinned decimal context for all correction arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned correction decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class MultipleComparisonEngineVersion:
    """Immutable identity of the correction-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 25's own statistical method (family collection, sort,
        adjusted-``p`` procedures, harmonic constant, monotonicity, capping, rejection
        rule); folded into ``config_hash`` so a method change is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = MULTIPLICITY_ENGINE_VERSION
    method_version: str = MULTIPLICITY_METHOD_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the decimal-context + method config."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def multiplicity_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for correction math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
