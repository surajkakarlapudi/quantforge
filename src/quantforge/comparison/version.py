"""The strategy-comparison transformation version (Phase 24, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    strategy_comparison_engine_version_id = hash(code_version, config_hash)

For Phase 24 the "transformation" is the **strategy-comparison engine** that turns a
declarative :class:`~quantforge.comparison.spec.StrategyComparisonSpecification` (naming
an ordered set of ``N`` sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` strategies) into a sealed
:class:`~quantforge.comparison.result.StrategyComparison` - the upper-triangle matrix of
pairwise paired-difference statistics (mean OOS return difference, standard error, ``t``
statistic, two-sided ``p`` value, descriptive Sharpe difference, overlap). This module
pins that engine logic with a stable version id, following the exact pattern of
:class:`~quantforge.campaign.version.CampaignEngineVersion` (the id is a ``sha256:`` of
the content; nothing depends on the wall clock).

Three properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All comparison arithmetic - the
  per-pair paired-difference mean and population variance, the ``t`` statistic, the
  normal-CDF evaluation for the two-sided ``p`` value, and the descriptive Sharpe
  difference - runs under an explicit :class:`decimal.Context` (precision + rounding).
  It is folded into ``config_hash``, so a change to it necessarily produces a new,
  distinguishable ``strategy_comparison_engine_version_id``. The default is **precision
  34, ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The method versions are part of the version.** Phase 24 computes its own
  self-contained paired-difference method (:data:`COMPARISON_METHOD_VERSION`: the
  date-reconstruction alignment, the paired-difference statistics, and the descriptive
  Sharpe difference) on top of the shared deterministic exact-``Decimal``
  standard-normal primitive (:data:`COMPARISON_NORMAL_VERSION`: the Φ series it reuses
  from
  :mod:`quantforge._stats.normal` for the two-sided ``p`` value). Both are folded into
  ``config_hash``, so a change to *either* yields a new, distinguishable engine id.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the comparison logic in a way that can alter a computed value must bump
:data:`COMPARISON_ENGINE_VERSION` (the code version), :data:`COMPARISON_METHOD_VERSION`
(the statistical method), or :data:`COMPARISON_NORMAL_VERSION` (the normal primitive).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "COMPARISON_ENGINE_VERSION",
    "COMPARISON_METHOD_VERSION",
    "COMPARISON_NORMAL_VERSION",
    "COMPARISON_SPEC_VERSION",
    "StrategyComparisonEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``strategy_comparison_id`` (§13). Bump
# it when the serialized meaning of a request changes - never when engine logic changes
# (that is ``COMPARISON_ENGINE_VERSION``). Shares the ``comparison/1`` string with the
# identity domain tag by construction (the prior-phase precedent).
COMPARISON_SPEC_VERSION = "comparison/1"

# Bump whenever the comparison engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
COMPARISON_ENGINE_VERSION = "comparison-engine/1"

# Bump whenever Phase 24's *statistical method* changes - the date-reconstruction
# alignment (transitive-chain resolution + complete-case axis + calendar-date pair
# intersection), the paired-difference statistics (population-variance standard error,
# the ``t`` statistic, the two-sided ``p`` value), or the descriptive Sharpe difference.
# Folded into ``config_hash`` alongside the normal-primitive version, so a method change
# is a new, distinguishable engine version (§13).
COMPARISON_METHOD_VERSION = "comparison-method/1"

# Bump whenever the deterministic exact-``Decimal`` standard-normal primitive Phase 24
# reuses changes - the shared Φ series in :mod:`quantforge._stats.normal`. Folded into
# ``config_hash`` so a change to how the two-sided ``p`` value's normal CDF is computed
# is a new, distinguishable engine version.
COMPARISON_NORMAL_VERSION = "comparison-normal/1"

# The pinned decimal context for all comparison arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned comparison decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class StrategyComparisonEngineVersion:
    """Immutable identity of the comparison-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 24's own statistical method (date-reconstruction
        alignment, paired-difference statistics, Sharpe difference); folded into
        ``config_hash`` so a method change is a new version.
    normal_version:
        Revision string for the shared deterministic exact-``Decimal`` standard-normal
        primitive (Φ) the two-sided ``p`` value reuses; folded into ``config_hash`` so a
        change to the normal computation is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = COMPARISON_ENGINE_VERSION
    method_version: str = COMPARISON_METHOD_VERSION
    normal_version: str = COMPARISON_NORMAL_VERSION
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
    def strategy_comparison_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for comparison math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
