"""The analytics-engine transformation version (proposal §L, D7; data-model §9).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    analytics_engine_version_id = hash(code_version, config_hash)

For Phase 15 the "transformation" is the **statistics engine** that turns a declarative
:class:`~quantforge.analytics.spec.AnalyticsSpecification` plus the sealed
``period_returns`` of the referenced backtest(s) into a
:class:`~quantforge.analytics.result.PerformanceAnalytics`. This module pins that engine
logic with a stable version id, following the exact pattern of
:class:`~quantforge.backtest.version.BacktestEngineVersion` (the id is a ``sha256:`` of
the content; nothing depends on the wall clock).

Two properties are load-bearing (proposal §L; data-model invariants 13, 21):

* **The pinned decimal context is part of the version.** All statistic arithmetic runs
  under an explicit :class:`decimal.Context` (precision + rounding). It is folded into
  ``config_hash``, so a change to it necessarily produces a new, distinguishable
  ``analytics_engine_version_id`` — a result computed under one context can never be
  confused with one computed under another. The default is **precision 34,
  ``ROUND_HALF_EVEN``** — identical to the metrics, market, and backtest layers, so each
  layer's arithmetic rounds the same way.
* **The formula-method version is part of the version.** Unlike the backtest engine,
  Phase 15 pins a *statistical method* (the nearest-rank VaR/CVaR quantile rule, the
  population skewness / excess-kurtosis definitions — proposal D7/D11). That method
  version (``analytics-stats/1``) is folded into ``config_hash`` too, so changing a
  formula's definition bumps the engine id and can never silently reinterpret a stored
  analytics record.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the statistics logic in a way that can alter a computed value must bump
:data:`ANALYTICS_ENGINE_VERSION` (the code version) or :data:`ANALYTICS_FORMULA_VERSION`
(the method version).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "ANALYTICS_ENGINE_VERSION",
    "ANALYTICS_FORMULA_VERSION",
    "AnalyticsEngineVersion",
    "default_decimal_context",
]

# Bump whenever the statistics engine's orchestration logic changes in a way that can
# alter a computed value. The analytics analogue of a code git SHA for the (as-yet
# uncommitted) engine; explicit and stable so derived identity never depends on the wall
# clock or a random value.
ANALYTICS_ENGINE_VERSION = "analytics-engine/1"

# Bump whenever a *statistical method* changes (the VaR/CVaR quantile rule, the
# skew/kurtosis moment definitions). Folded into ``config_hash`` so a method change is a
# new, distinguishable engine version — a value computed under one method can never be
# confused with one under another (proposal §L, D7, D11).
ANALYTICS_FORMULA_VERSION = "analytics-stats/1"

# The pinned decimal context for all analytics arithmetic. Precision 34 with banker's
# rounding — identical to the metrics/market/backtest layers, so a risk statistic rounds
# the same way the return it derives from did. Applied only via an explicit
# ``localcontext`` in the compute functions, never the ambient process context, so
# results are deterministic regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned analytics decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class AnalyticsEngineVersion:
    """Immutable identity of the statistics-engine logic + config (§L, D7).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    formula_version:
        Revision string for the statistical *method* set (quantile rule, moment
        definitions); folded into ``config_hash`` so a method change is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every statistic can
        round), so any change to it is a new version.
    """

    code_version: str = ANALYTICS_ENGINE_VERSION
    formula_version: str = ANALYTICS_FORMULA_VERSION
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
    def analytics_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for analytics arithmetic."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
