"""The attribution-engine transformation version (proposal §14; data-model §9).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    attribution_engine_version_id = hash(code_version, config_hash)

For Phase 17 the "transformation" is the **multi-factor OLS engine** that turns a
declarative :class:`~quantforge.attribution.spec.AttributionSpecification` plus the
sealed ``period_returns`` of the referenced backtests (a subject and *K* factors) into a
:class:`~quantforge.attribution.result.FactorAttribution`. This module pins that engine
logic with a stable version id, following the exact pattern of
:class:`~quantforge.analytics.version.AnalyticsEngineVersion` (the id is a ``sha256:``
of the content; nothing depends on the wall clock).

Two properties are load-bearing (proposal §8, §14; data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All regression arithmetic — the
  design-matrix assembly, the exact-``Decimal`` Cholesky/LDLᵀ solve, the residual and
  diagnostic computations — runs under an explicit :class:`decimal.Context` (precision +
  rounding). It is folded into ``config_hash``, so a change to it necessarily produces a
  new, distinguishable ``attribution_engine_version_id`` — a result computed under one
  context can never be confused with one computed under another. The default is
  **precision 34, ``ROUND_HALF_EVEN``** — identical to the metrics, market, backtest,
  and
  analytics layers, so each layer's arithmetic rounds the same way.
* **The formula-method version is part of the version.** Phase 17 pins a *statistical
  method* (the OLS normal-equation solve via symmetric factorization with an exact
  zero-pivot test, the population-moment definitions of R²/adjusted R², the classical
  ``sigma_sq(XᵀX)⁻¹`` coefficient covariance). That method version
  (``attribution-stats/1``)
  is folded into ``config_hash`` too, so changing a formula's definition bumps the
  engine
  id and can never silently reinterpret a stored attribution record.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the estimation logic in a way that can alter a computed value must bump
:data:`ATTRIBUTION_ENGINE_VERSION` (the code version) or
:data:`ATTRIBUTION_FORMULA_VERSION` (the method version).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "ATTRIBUTION_ENGINE_VERSION",
    "ATTRIBUTION_FORMULA_VERSION",
    "AttributionEngineVersion",
    "default_decimal_context",
]

# Bump whenever the attribution engine's orchestration logic changes in a way that can
# alter a computed value. The attribution analogue of a code git SHA for the (as-yet
# uncommitted) engine; explicit and stable so derived identity never depends on the wall
# clock or a random value.
ATTRIBUTION_ENGINE_VERSION = "attribution-engine/1"

# Bump whenever a *statistical method* changes (the OLS solve algorithm, the R²/adjusted
# R² definitions, the coefficient-covariance basis). Folded into ``config_hash`` so a
# method change is a new, distinguishable engine version — a value computed under one
# method can never be confused with one under another (proposal §8, §14).
ATTRIBUTION_FORMULA_VERSION = "attribution-stats/1"

# The pinned decimal context for all attribution arithmetic. Precision 34 with banker's
# rounding — identical to the metrics/market/backtest/analytics layers, so a regression
# statistic rounds the same way the return it derives from did. Applied only via an
# explicit ``localcontext`` in the compute functions, never the ambient process context,
# so results are deterministic regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned attribution decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class AttributionEngineVersion:
    """Immutable identity of the OLS-engine logic + config (§8, §14).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    formula_version:
        Revision string for the statistical *method* set (the OLS solve, the moment /
        covariance definitions); folded into ``config_hash`` so a method change is a new
        version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every statistic can
        round), so any change to it is a new version.
    """

    code_version: str = ATTRIBUTION_ENGINE_VERSION
    formula_version: str = ATTRIBUTION_FORMULA_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the decimal-context + formula config."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00formula={self.formula_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def attribution_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for attribution arithmetic."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
