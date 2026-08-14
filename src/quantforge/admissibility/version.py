"""The strategy-admissibility transformation version (Phase 33, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    admissibility_engine_version_id = hash(code_version, config_hash)

For Phase 33 the "transformation" is the **strategy-admissibility engine** that turns a
declarative :class:`~quantforge.admissibility.spec.AdmissibilitySpecification` (naming
exactly three sealed ex-post verdicts of one strategy - a
:class:`~quantforge.stability.result.WalkForwardStability`, a
:class:`~quantforge.calsig.result.CalibrationSignificance`, and a
:class:`~quantforge.netcostsig.result.NetOfCostSignificance`) into a single sealed
:class:`~quantforge.admissibility.result.StrategyAdmissibility` verdict - ADMISSIBLE
only when the book is stable, the risk model is not significantly mis-calibrated, and
the after-cost edge is significantly profitable at a declared level ``alpha``. This
module pins that engine logic with a stable version id, following the exact pattern of
:class:`~quantforge.netcostsig.version.NetOfCostSignificanceEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Two properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** The admissibility decision is a
  set of exact-``Decimal`` comparisons of the consumed p-values against the declared
  ``alpha`` (no transcendental is evaluated here - the ``Φ`` CDF was already applied and
  sealed by the significance layers, AD-4). It runs under an explicit
  :class:`decimal.Context` (precision + rounding), folded into ``config_hash`` so a
  change to it necessarily produces a new, distinguishable
  ``admissibility_engine_version_id``. The default is **precision 34,
  ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The method version is part of the version.** Phase 33 defines its own
  self-contained joint-decision rule (:data:`ADMISSIBILITY_METHOD_VERSION`) - the three
  per-criterion pass tests and the fail-closed roll-up. It is folded into
  ``config_hash`` so a change to the decision rule yields a new, distinguishable engine
  id. Unlike the significance layers Phase 33 evaluates **no** standard-normal primitive
  of its own, so there is no normal-version fold: it consumes already-sealed p-values
  verbatim.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the decision logic in a way that can alter a verdict must bump
:data:`ADMISSIBILITY_ENGINE_VERSION` (the code version) or
:data:`ADMISSIBILITY_METHOD_VERSION` (the joint-decision rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "ADMISSIBILITY_ENGINE_VERSION",
    "ADMISSIBILITY_METHOD_VERSION",
    "ADMISSIBILITY_SPEC_VERSION",
    "AdmissibilityEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``admissibility_id`` (§13). Bump it when
# the serialized meaning of a request changes - never when engine logic changes (that is
# ``ADMISSIBILITY_ENGINE_VERSION``). Shares the ``admissibility/1`` string with the
# identity domain tag by construction (the prior-phase precedent).
ADMISSIBILITY_SPEC_VERSION = "admissibility/1"

# Bump whenever the admissibility engine's orchestration logic changes in a way that can
# alter a verdict. The analogue of a code git SHA for the engine; explicit and stable so
# derived identity never depends on the wall clock or a random value.
ADMISSIBILITY_ENGINE_VERSION = "admissibility-engine/1"

# Bump whenever Phase 33's *decision rule* changes - the three per-criterion pass tests
# (stability STABLE; calibration p-value ``> alpha`` two-sided; net-of-cost edge p-value
# ``<= alpha`` upper-tailed and PROFITABLE) or the fail-closed roll-up (ADMISSIBLE iff
# all pass, UNDEFINED iff any criterion is undefined). Folded into ``config_hash`` so a
# method change is a new, distinguishable engine version (§13).
ADMISSIBILITY_METHOD_VERSION = "admissibility-method/1"

# The pinned decimal context for the admissibility comparisons. Precision 34 with
# banker's rounding - identical to every prior derived layer. Applied only via an
# explicit ``localcontext``, never the ambient process context, so results are
# deterministic regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned admissibility decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class AdmissibilityEngineVersion:
    """Immutable identity of the admissibility-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 33's own joint-decision rule (the per-criterion pass
        tests + the fail-closed roll-up); folded into ``config_hash`` so a method change
        is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (a comparison can depend
        on the parsed precision), so any change to it is a new version.
    """

    code_version: str = ADMISSIBILITY_ENGINE_VERSION
    method_version: str = ADMISSIBILITY_METHOD_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` of the decimal-context + method version."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def admissibility_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for the comparisons."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
