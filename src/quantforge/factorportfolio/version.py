"""The factor-portfolio-engine transformation version (Phase 19, §5.7).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    factor_portfolio_engine_version_id = hash(code_version, config_hash)

For Phase 19 the "transformation" is the **characteristic-sorted long/short
factor-portfolio construction engine** that turns a declarative
:class:`~quantforge.factorportfolio.spec.FactorPortfolioSpecification` plus the PIT
signal cross-sections and the realized forward returns of the referenced corpora into a
:class:`~quantforge.factorportfolio.result.FactorPortfolio`. This module pins that
engine logic with a stable version id, following the exact pattern of
:class:`~quantforge.crosssection.version.CrossSectionEngineVersion` and
:class:`~quantforge.diagnostics.version.SignalDiagnosticsEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Two properties are load-bearing (data-model invariants 13, 21):

* **The pinned decimal context is part of the version.** All statistic arithmetic (the
  per-leg mean forward returns, the per-period long-minus-short spread, and the return
  series summary - cumulative / mean / population volatility / annualized Sharpe /
  t-statistic / hit rate) runs under an explicit :class:`decimal.Context` (precision +
  rounding). It is folded into ``config_hash``, so a change to it necessarily produces a
  new, distinguishable ``factor_portfolio_engine_version_id``. The default is
  **precision 34, ``ROUND_HALF_EVEN``** - identical to the metrics, market, backtest,
  analytics, diagnostics, attribution, and cross-sectional-regression layers.
* **The formula-method version is part of the version.** Phase 19 pins a *construction +
  statistics method* (the quantile-bucket leg formation, the equal-weight per-leg mean,
  the long-minus-short spread, the compounded cumulative return, the
  population-volatility / annualized-Sharpe / t-statistic aggregation). That method
  version (``factorportfolio-stats/1``) is folded into ``config_hash``, so changing a
  formula's definition bumps the engine id and can never silently reinterpret a stored
  record.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the construction/estimation logic in a way that can alter a computed value must
bump :data:`FACTORPORTFOLIO_ENGINE_VERSION` (the code version) or
:data:`FACTORPORTFOLIO_FORMULA_VERSION` (the method version).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "FACTORPORTFOLIO_ENGINE_VERSION",
    "FACTORPORTFOLIO_FORMULA_VERSION",
    "FACTORPORTFOLIO_SPEC_VERSION",
    "FactorPortfolioEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``factor_portfolio_id`` (§5.4). Bump it
# when the serialized meaning of a request changes - never when engine logic changes
# (that is ``FACTORPORTFOLIO_ENGINE_VERSION``). Shares the ``factorportfolio/1`` string
# with the identity domain tag by construction (the Phase 16/18 precedent).
FACTORPORTFOLIO_SPEC_VERSION = "factorportfolio/1"

# Bump whenever the factor-portfolio engine's orchestration logic changes in a way that
# can alter a computed value. The analogue of a code git SHA for the (as-yet
# uncommitted) engine; explicit and stable so derived identity never depends on the wall
# clock or a random value.
FACTORPORTFOLIO_ENGINE_VERSION = "factorportfolio-engine/1"

# Bump whenever a *construction / statistical method* changes (the quantile
# leg-formation rule, the per-leg weighting, the spread definition, the
# cumulative-return compounding, or the summary aggregation - the population-volatility
# / annualized-Sharpe / t-statistic conventions). Folded into ``config_hash`` so a
# method change is a new, distinguishable engine version - a value computed under one
# method can never be confused with one under another (§5.7).
FACTORPORTFOLIO_FORMULA_VERSION = "factorportfolio-stats/1"

# The pinned decimal context for all factor-portfolio arithmetic. Precision 34 with
# banker's rounding - identical to every prior derived layer. Applied only via an
# explicit ``localcontext`` in the compute functions, never the ambient process context,
# so results are deterministic regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned factor-portfolio decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class FactorPortfolioEngineVersion:
    """Immutable identity of the construction-engine logic + config (§5.7).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    formula_version:
        Revision string for the construction/statistics *method* set (the quantile leg
        formation, the per-leg mean, the spread, and the summary aggregation); folded
        into ``config_hash`` so a method change is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every statistic can
        round), so any change to it is a new version.
    """

    code_version: str = FACTORPORTFOLIO_ENGINE_VERSION
    formula_version: str = FACTORPORTFOLIO_FORMULA_VERSION
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
    def factor_portfolio_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for construction
        arithmetic."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
