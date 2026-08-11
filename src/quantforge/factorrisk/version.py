"""The factor-risk-engine transformation version (Phase 20, §10).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    factor_risk_engine_version_id = hash(code_version, config_hash)

For Phase 20 the "transformation" is the **factor-risk estimation engine** that turns a
declarative :class:`~quantforge.factorrisk.spec.FactorRiskSpecification` plus the sealed
factor return series of the referenced :class:`~quantforge.factorportfolio.result.\
FactorPortfolio` records (an ordered set of *N* factors) into a
:class:`~quantforge.factorrisk.result.FactorRiskModel` - a factor covariance matrix, the
companion correlation matrix, the per-factor volatilities, and the mean-return vector.
This module pins that engine logic with a stable version id, following the exact pattern
of :class:`~quantforge.attribution.version.AttributionEngineVersion` and
:class:`~quantforge.factorportfolio.version.FactorPortfolioEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Two properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All second-moment arithmetic -
  the per-factor means, the population covariance sums of products, the population
  volatilities (via ``Decimal.sqrt``), the correlation ratios, and the annualized
  scalings - runs under an explicit :class:`decimal.Context` (precision + rounding). It
  is folded into ``config_hash``, so a change to it necessarily produces a new,
  distinguishable ``factor_risk_engine_version_id`` - a matrix computed under one
  context can never be confused with one computed under another. The default is
  **precision 34,
  ``ROUND_HALF_EVEN``** - identical to the metrics, market, backtest, analytics,
  diagnostics, attribution, cross-section, and factor-portfolio layers.
* **The formula-method version is part of the version.** Phase 20 pins a *statistical
  method* (the complete-case alignment, the population moment definitions, the
  ``cov(i,j)/(vol_i·vol_j)`` correlation, and the ``·ppy`` / ``·√ppy`` annualization).
  That method version (``factorrisk-stats/1``) is folded into ``config_hash``, so
  changing a formula's definition bumps the engine id and can never silently reinterpret
  a stored risk model.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the estimation logic in a way that can alter a computed value must bump
:data:`FACTORRISK_ENGINE_VERSION` (the code version) or
:data:`FACTORRISK_FORMULA_VERSION` (the method version).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "FACTORRISK_ENGINE_VERSION",
    "FACTORRISK_FORMULA_VERSION",
    "FACTORRISK_SPEC_VERSION",
    "FactorRiskEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``factor_risk_id`` (§10). Bump it when
# the serialized meaning of a request changes - never when engine logic changes (that is
# ``FACTORRISK_ENGINE_VERSION``). Shares the ``factorrisk/1`` string with the identity
# domain tag by construction (the Phase 16/18/19 precedent).
FACTORRISK_SPEC_VERSION = "factorrisk/1"

# Bump whenever the factor-risk engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
FACTORRISK_ENGINE_VERSION = "factorrisk-engine/1"

# Bump whenever a *statistical method* changes (the complete-case alignment rule, the
# population mean / covariance / volatility definitions, the correlation ratio, or the
# annualization scaling). Folded into ``config_hash`` so a method change is a new,
# distinguishable engine version - a value computed under one method can never be
# confused with one under another (§10).
FACTORRISK_FORMULA_VERSION = "factorrisk-stats/1"

# The pinned decimal context for all factor-risk arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext`` in the compute functions, never the ambient process context, so
# results are deterministic regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned factor-risk decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class FactorRiskEngineVersion:
    """Immutable identity of the estimation-engine logic + config (§10).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    formula_version:
        Revision string for the statistical *method* set (the alignment rule, the moment
        / covariance / correlation definitions, the annualization scaling); folded into
        ``config_hash`` so a method change is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every statistic can
        round), so any change to it is a new version.
    """

    code_version: str = FACTORRISK_ENGINE_VERSION
    formula_version: str = FACTORRISK_FORMULA_VERSION
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
    def factor_risk_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for factor-risk arithmetic."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
