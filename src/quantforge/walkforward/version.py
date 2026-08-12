"""The walk-forward-evaluation transformation version (Phase 22, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    walk_forward_engine_version_id = hash(code_version, config_hash)

For Phase 22 the "transformation" is the **walk-forward-evaluation engine** that turns a
declarative :class:`~quantforge.walkforward.spec.WalkForwardEvaluationSpecification`
(naming one sealed :class:`~quantforge.optimization.result.PortfolioOptimization` recipe
plus a :class:`~quantforge.walkforward.spec.TrainingPolicy`) into a sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` - the ordered train->test
windows, the chained out-of-sample (OOS) return series, its performance summary, and the
per-window predicted-vs-realized variance. This module pins that engine logic with a
stable version id, following the exact pattern of
:class:`~quantforge.optimization.version.PortfolioOptimizationEngineVersion` (the id is
a ``sha256:`` of the content; nothing depends on the wall clock).

Three properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All walk-forward arithmetic -
  the per-window covariance re-estimation, the GMV re-solve, the realization of weights
  against the strictly-subsequent test returns, and the OOS summary - runs under an
  explicit :class:`decimal.Context` (precision + rounding). It is folded into
  ``config_hash``, so a change to it necessarily produces a new, distinguishable
  ``walk_forward_engine_version_id``. The default is **precision 34,
  ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The composed method versions are part of the version.** Phase 22 computes no new
  numerical formula: it *composes* three pinned pure methods from the layers below - the
  Phase 20 covariance estimator (``factorrisk-stats/1``), the Phase 21 GMV solve
  (``optimization-solve/1``), and the Phase 19 series summary
  (``factorportfolio-stats/1``)
- plus its own window-partition + realization method (``walkforward-method/1``). All
  four are folded into ``config_hash``, so a change to *any* composed method (a bump in
  a lower layer, or in the partition/realization rule) yields a new, distinguishable
  engine id - a walk computed under one method set can never be confused with one under
  another.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the walk-forward logic in a way that can alter a computed value must bump
:data:`WALKFORWARD_ENGINE_VERSION` (the code version) or
:data:`WALKFORWARD_METHOD_VERSION` (the partition/realization method version); a bump in
a composed lower-layer method version propagates automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.factorportfolio.version import FACTORPORTFOLIO_FORMULA_VERSION
from quantforge.factorrisk.version import FACTORRISK_FORMULA_VERSION
from quantforge.optimization.version import OPTIMIZATION_SOLVE_VERSION
from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "WALKFORWARD_ENGINE_VERSION",
    "WALKFORWARD_METHOD_VERSION",
    "WALKFORWARD_SPEC_VERSION",
    "WalkForwardEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``walk_forward_id`` (§13). Bump it when
# the serialized meaning of a request changes - never when engine logic changes (that is
# ``WALKFORWARD_ENGINE_VERSION``). Shares the ``walkforward/1`` string with the identity
# domain tag by construction (the Phase 16/18/19/20/21 precedent).
WALKFORWARD_SPEC_VERSION = "walkforward/1"

# Bump whenever the walk-forward engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
WALKFORWARD_ENGINE_VERSION = "walkforward-engine/1"

# Bump whenever Phase 22's *own* method changes - the window-partition rule (how the
# complete-case-aligned axis + TrainingPolicy map to ordered train->test windows) or the
# realization rule (applying the training-window GMV weights to the strictly-subsequent
# test returns and chaining the OOS series). Folded into ``config_hash`` alongside the
# three composed lower-layer method versions, so a method change is a new,
# distinguishable engine version (§13).
WALKFORWARD_METHOD_VERSION = "walkforward-method/1"

# The pinned decimal context for all walk-forward arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned walk-forward decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class WalkForwardEngineVersion:
    """Immutable identity of the walk-forward-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 22's own window-partition + realization method;
        folded into ``config_hash`` so a method change is a new version.
    covariance_version / solve_version / summary_version:
        The three composed lower-layer method versions (Phase 20 covariance, Phase 21
        GMV solve, Phase 19 series summary), folded into ``config_hash`` so a bump
        in any composed method yields a new, distinguishable engine version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = WALKFORWARD_ENGINE_VERSION
    method_version: str = WALKFORWARD_METHOD_VERSION
    covariance_version: str = FACTORRISK_FORMULA_VERSION
    solve_version: str = OPTIMIZATION_SOLVE_VERSION
    summary_version: str = FACTORPORTFOLIO_FORMULA_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the decimal-context + method config."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
            f"\x00cov={self.covariance_version}"
            f"\x00solve={self.solve_version}"
            f"\x00summary={self.summary_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def walk_forward_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for walk-forward math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
