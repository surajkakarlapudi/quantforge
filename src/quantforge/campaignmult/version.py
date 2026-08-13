"""The campaign-multiplicity transformation version (Phase 30, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    campaign_multiplicity_engine_version_id = hash(code_version, config_hash)

For Phase 30 the "transformation" is the **campaign-multiplicity-correction engine**
that turns a declarative
:class:`~quantforge.campaignmult.spec.CampaignMultiplicitySpecification` (naming exactly
one sealed :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` and a
declared ``alpha`` + method set) into a sealed
:class:`~quantforge.campaignmult.result.CampaignMultiplicityCorrection` - the
family-wise (Holm, Bonferroni) and false-discovery-rate (Benjamini-Yekutieli,
Benjamini-Hochberg) adjusted ``p`` values plus a rejection set over the campaign's
per-trial one-sided ``p_i = 1 - PSR_i`` family. This module pins that engine logic with
a stable version id, following the exact pattern of
:class:`~quantforge.multiplicity.version.MultipleComparisonEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Three properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** The one added arithmetic - the
  exact ``p = 1 - PSR`` transform - and every reused correction step (the per-rank
  adjusted-``p`` multipliers, the Benjamini-Yekutieli harmonic constant, the running
  min / running max monotonicity, the ``min(1, ·)`` capping, and the ``p_adj ≤ alpha``
  rejection comparison) run under an explicit :class:`decimal.Context` (precision +
  rounding). It is folded into ``config_hash``, so a change to it necessarily produces a
  new, distinguishable ``campaign_multiplicity_engine_version_id``. The default is
  **precision 34, ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **Both the own method version and the reused correction-core version are part of the
  version.** Phase 30 owns the family construction (KNOWN-``psr`` selection, the
  ``p = 1 - PSR`` transform, UNDEFINED exclusion) as
  :data:`CAMPAIGNMULT_METHOD_VERSION`, and it *reuses* Phase 25's step-up / step-down
  adjusted-``p`` procedures verbatim - pinned here as
  :data:`CAMPAIGNMULT_CORRECTION_VERSION` (a copy of
  :data:`~quantforge.multiplicity.version.MULTIPLICITY_METHOD_VERSION`). Both are folded
  into ``config_hash``, so a change to *either* Phase 30's own method **or** the reused
  correction core yields a new, distinguishable engine id - an honest transitive pin of
  the reused algorithm. Phase 30 reuses **no** standard-normal primitive (it consumes an
  already-sealed ``PSR`` and subtracts it from one), so there is no normal-primitive
  version to fold.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the correction logic in a way that can alter a computed value must bump
:data:`CAMPAIGNMULT_ENGINE_VERSION` (the code version) or
:data:`CAMPAIGNMULT_METHOD_VERSION` (the statistical method); a change to the reused
correction core is picked up automatically through
:data:`CAMPAIGNMULT_CORRECTION_VERSION`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.multiplicity.version import MULTIPLICITY_METHOD_VERSION
from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "CAMPAIGNMULT_CORRECTION_VERSION",
    "CAMPAIGNMULT_ENGINE_VERSION",
    "CAMPAIGNMULT_METHOD_VERSION",
    "CAMPAIGNMULT_SPEC_VERSION",
    "CampaignMultiplicityEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``campaign_multiplicity_id`` (§13). Bump
# it when the serialized meaning of a request changes - never when engine logic changes
# (that is ``CAMPAIGNMULT_ENGINE_VERSION``). Shares the ``campaignmult/1`` string with
# the identity domain tag by construction (the prior-phase precedent).
CAMPAIGNMULT_SPEC_VERSION = "campaignmult/1"

# Bump whenever the correction engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
CAMPAIGNMULT_ENGINE_VERSION = "campaignmult-engine/1"

# Bump whenever Phase 30's *own* statistical method changes - the family construction
# (KNOWN-``psr`` selection + UNDEFINED exclusion) and the ``p = 1 - PSR`` one-sided
# p-value transform. Folded into ``config_hash`` so a method change is a new,
# distinguishable engine version (§13). The reused adjusted-``p`` procedures are pinned
# separately by ``CAMPAIGNMULT_CORRECTION_VERSION``.
CAMPAIGNMULT_METHOD_VERSION = "campaignmult-method/1"

# The version of the *reused* multiplicity correction core
# (:func:`~quantforge.multiplicity.compute.correct_family`): the Bonferroni / Holm /
# Benjamini-Hochberg / Benjamini-Yekutieli adjusted-``p`` procedures, the harmonic
# constant, the monotonicity enforcement, the ``min(1, ·)`` capping, and the ``p_adj ≤
# alpha`` rejection rule. Bound to
# :data:`~quantforge.multiplicity.version.MULTIPLICITY_METHOD_VERSION` so that a change
# to the shared correction algorithm is picked up automatically and changes this
# record's identity - an honest transitive pin of the reused code.
CAMPAIGNMULT_CORRECTION_VERSION = MULTIPLICITY_METHOD_VERSION

# The pinned decimal context for all correction arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned campaign-multiplicity decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class CampaignMultiplicityEngineVersion:
    """Immutable identity of the correction-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 30's own statistical method (family construction and
        the ``p = 1 - PSR`` transform); folded into ``config_hash`` so a method change
        is a new version.
    correction_version:
        Revision string for the *reused* multiplicity correction core (the
        adjusted-``p`` procedures, harmonic constant, monotonicity, capping, rejection
        rule); bound to
        :data:`~quantforge.multiplicity.version.MULTIPLICITY_METHOD_VERSION` and folded
        into ``config_hash`` so a change to the reused core is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = CAMPAIGNMULT_ENGINE_VERSION
    method_version: str = CAMPAIGNMULT_METHOD_VERSION
    correction_version: str = CAMPAIGNMULT_CORRECTION_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` of the decimal-context + method + correction."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
            f"\x00correction={self.correction_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def campaign_multiplicity_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for correction math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
