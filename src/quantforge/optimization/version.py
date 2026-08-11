"""The portfolio-optimization-engine transformation version (Phase 21, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    optimization_engine_version_id = hash(code_version, config_hash)

For Phase 21 the "transformation" is the **portfolio-optimization engine** that turns a
declarative :class:`~quantforge.optimization.spec.PortfolioOptimizationSpecification`
plus the sealed covariance matrix of the referenced
:class:`~quantforge.factorrisk.result.FactorRiskModel` (an ``N x N`` factor covariance)
into a :class:`~quantforge.optimization.result.PortfolioOptimization` - the global
minimum-variance (GMV) factor-weight vector, the achieved per-period portfolio variance,
and its volatility. This module pins that engine logic with a stable version id,
following the exact pattern of
:class:`~quantforge.factorrisk.version.FactorRiskEngineVersion` (the id is a ``sha256:``
of the content; nothing depends on the wall clock).

Two properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All optimization arithmetic -
  the exact-``Decimal`` LDLᵀ solve of ``Σx = 1``, the weight normalization ``w = x/Σx``,
  and the quadratic form ``wᵀΣw`` (via ``Decimal.sqrt`` for the volatility) - runs under
  an explicit :class:`decimal.Context` (precision + rounding). It is folded into
  ``config_hash``, so a change to it necessarily produces a new, distinguishable
  ``optimization_engine_version_id`` - a weight vector computed under one context can
  never be confused with one computed under another. The default is **precision 34,
  ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The solve-method version is part of the version.** Phase 21 pins a *solution method*
  (the fully-invested GMV closed form ``w = Σ⁻¹1 / (1ᵀΣ⁻¹1)`` solved via the shared
  exact-``Decimal`` LDLᵀ factorization, the ``Σ`` reconstruction from the sealed
  upper-triangle covariance, the exact zero-pivot singularity test, and the ``wᵀΣw``
  variance). That method version (``optimization-solve/1``) is folded into
  ``config_hash``, so changing a formula's definition bumps the engine id and can never
  silently reinterpret a stored optimization.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the optimization logic in a way that can alter a computed value must bump
:data:`OPTIMIZATION_ENGINE_VERSION` (the code version) or
:data:`OPTIMIZATION_SOLVE_VERSION` (the method version).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "OPTIMIZATION_ENGINE_VERSION",
    "OPTIMIZATION_SOLVE_VERSION",
    "OPTIMIZATION_SPEC_VERSION",
    "PortfolioOptimizationEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``optimization_id`` (§13). Bump it when
# the serialized meaning of a request changes - never when engine logic changes (that is
# ``OPTIMIZATION_ENGINE_VERSION``). Shares the ``optimization/1`` string with the
# identity domain tag by construction (the Phase 16/18/19/20 precedent).
OPTIMIZATION_SPEC_VERSION = "optimization/1"

# Bump whenever the optimization engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
OPTIMIZATION_ENGINE_VERSION = "optimization-engine/1"

# Bump whenever the *solution method* changes (the GMV closed form, the ``Σ``
# reconstruction, the LDLᵀ solve, the exact zero-pivot singularity test, or the ``wᵀΣw``
# variance). Folded into ``config_hash`` so a method change is a new, distinguishable
# engine version - a value computed under one method can never be confused with one
# under another (§13).
OPTIMIZATION_SOLVE_VERSION = "optimization-solve/1"

# The pinned decimal context for all optimization arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext`` in the solve function, never the ambient process context, so results
# are deterministic regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned optimization decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class PortfolioOptimizationEngineVersion:
    """Immutable identity of the optimization-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    solve_version:
        Revision string for the solution *method* (the GMV closed form, the ``Σ``
        reconstruction, the LDLᵀ solve, the zero-pivot test, the ``wᵀΣw`` variance);
        folded into ``config_hash`` so a method change is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every weight and
        variance can round), so any change to it is a new version.
    """

    code_version: str = OPTIMIZATION_ENGINE_VERSION
    solve_version: str = OPTIMIZATION_SOLVE_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the decimal-context + solve config."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00solve={self.solve_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def optimization_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for optimization math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
