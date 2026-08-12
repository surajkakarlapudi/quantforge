"""The research-campaign-evaluation transformation version (Phase 23, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    campaign_engine_version_id = hash(code_version, config_hash)

For Phase 23 the "transformation" is the **research-campaign-evaluation engine** that
turns a declarative :class:`~quantforge.campaign.spec.ResearchCampaignSpecification`
(naming an ordered set of ``N`` sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` trials plus a benchmark
Sharpe) into a sealed :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` -
the per-trial out-of-sample Sharpe / skew / kurtosis / Probabilistic Sharpe Ratio, the
best-trial selection, the expected-maximum Sharpe under the null, and the Deflated
Sharpe Ratio of the best trial. This module pins that engine logic with a stable version
id, following the exact pattern of
:class:`~quantforge.walkforward.version.WalkForwardEngineVersion` and
:class:`~quantforge.factorrisk.version.FactorRiskEngineVersion` (the id is a ``sha256:``
of the content; nothing depends on the wall clock).

Three properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All campaign arithmetic - the
  per-trial moment estimation, the PSR/DSR normal-CDF evaluations, the population
  variance of the trials' Sharpe ratios, and the expected-maximum-Sharpe inverse-CDF
  weighting - runs under an explicit :class:`decimal.Context` (precision + rounding). It
  is folded into ``config_hash``, so a change to it necessarily produces a new,
  distinguishable ``campaign_engine_version_id``. The default is **precision 34,
  ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The method versions are part of the version.** Phase 23 computes its own
  self-contained selection-bias method (:data:`CAMPAIGN_METHOD_VERSION`: the per-trial
  moment definitions, the PSR/DSR formulas, and the expected-maximum-Sharpe estimator)
  on top of a new deterministic exact-``Decimal`` standard-normal primitive
  (:data:`CAMPAIGN_NORMAL_VERSION`: the Φ series, the Z⁻¹ bisection, and the documented
  ``gamma``/``π`` literals). Both are folded into ``config_hash``, so a change to
  *either* yields a new, distinguishable engine id - a campaign computed under one
  method/normal set can never be confused with one under another.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the campaign logic in a way that can alter a computed value must bump
:data:`CAMPAIGN_ENGINE_VERSION` (the code version), :data:`CAMPAIGN_METHOD_VERSION` (the
statistical method), or :data:`CAMPAIGN_NORMAL_VERSION` (the normal primitive).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "CAMPAIGN_ENGINE_VERSION",
    "CAMPAIGN_METHOD_VERSION",
    "CAMPAIGN_NORMAL_VERSION",
    "CAMPAIGN_SPEC_VERSION",
    "CampaignEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``campaign_id`` (§13). Bump it when the
# serialized meaning of a request changes - never when engine logic changes (that is
# ``CAMPAIGN_ENGINE_VERSION``). Shares the ``campaign/1`` string with the identity
# domain tag by construction (the Phase 18/19/20/22 precedent).
CAMPAIGN_SPEC_VERSION = "campaign/1"

# Bump whenever the campaign engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
CAMPAIGN_ENGINE_VERSION = "campaign-engine/1"

# Bump whenever Phase 23's *statistical method* changes - the per-trial excess-return
# moment definitions (mean, population variance, skew, non-excess kurtosis, per-period
# Sharpe), the Probabilistic Sharpe Ratio and Deflated Sharpe Ratio formulas, or the
# expected-maximum-Sharpe estimator across trials. Folded into ``config_hash`` alongside
# the normal-primitive version, so a method change is a new, distinguishable engine
# version (§13).
CAMPAIGN_METHOD_VERSION = "campaign-method/1"

# Bump whenever the deterministic exact-``Decimal`` standard-normal primitive changes
# - the Φ series, the Z⁻¹ bisection parameters, or the documented ``gamma`` / ``π``
# literals (:mod:`quantforge.campaign.normal`). Folded into ``config_hash`` so a change
# to how the normal quantiles are computed is a new, distinguishable engine version.
CAMPAIGN_NORMAL_VERSION = "campaign-normal/1"

# The pinned decimal context for all campaign arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned campaign decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class CampaignEngineVersion:
    """Immutable identity of the campaign-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 23's own statistical method (moments, PSR/DSR,
        expected-maximum Sharpe); folded into ``config_hash`` so a method change is
        a new version.
    normal_version:
        Revision string for the deterministic exact-``Decimal`` standard-normal
        primitive (Φ / Z⁻¹ / the ``gamma`` / ``π`` literals); folded into
        ``config_hash`` so a change to the normal computation is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = CAMPAIGN_ENGINE_VERSION
    method_version: str = CAMPAIGN_METHOD_VERSION
    normal_version: str = CAMPAIGN_NORMAL_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the decimal-context + method config."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
            f"\x00normal={self.normal_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def campaign_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for campaign math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
