"""The signal-diagnostics-engine transformation version (Phase 16, §5, D6/D9).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    signal_diagnostics_engine_version_id = hash(code_version, config_hash)

For Phase 16 the "transformation" is the **diagnostics engine** that turns a declarative
:class:`~quantforge.diagnostics.spec.SignalDiagnosticsSpecification` plus the PIT signal
cross-section and the realized forward returns of the referenced corpora into a
:class:`~quantforge.diagnostics.result.SignalDiagnostics`. This module pins that engine
logic with a stable version id, following the exact pattern of
:class:`~quantforge.analytics.version.AnalyticsEngineVersion` (the id is a ``sha256:``
of the content; nothing depends on the wall clock).

Two properties are load-bearing (data-model invariants 13, 21):

* **The pinned decimal context is part of the version.** All statistic arithmetic (rank
  IC, Pearson IC, quantile means, spreads, IC summary) runs under an explicit
  :class:`decimal.Context` (precision + rounding). It is folded into ``config_hash``, so
  a change to it necessarily produces a new, distinguishable
  ``signal_diagnostics_engine_version_id``. The default is **precision 34,
  ``ROUND_HALF_EVEN``** — identical to the metrics, market, backtest, and analytics
  layers.
* **The formula-method version is part of the version.** Phase 16 pins a *statistical
  method* (the average-rank Spearman rule, the population Pearson IC, the floor-based
  bucketing rule, the per-period IC information ratio — D6/D7). That method version
  (``diagnostics-stats/1``) is folded into ``config_hash``, so changing a formula's
  definition bumps the engine id and can never silently reinterpret a stored record.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the diagnostics logic in a way that can alter a computed value must bump
:data:`DIAGNOSTICS_ENGINE_VERSION` (the code version) or
:data:`DIAGNOSTICS_FORMULA_VERSION` (the method version).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "DIAGNOSTICS_ENGINE_VERSION",
    "DIAGNOSTICS_FORMULA_VERSION",
    "SignalDiagnosticsEngineVersion",
    "default_decimal_context",
]

# Bump whenever the diagnostics engine's orchestration logic changes in a way that can
# alter a computed value. The diagnostics analogue of a code git SHA for the (as-yet
# uncommitted) engine; explicit and stable so derived identity never depends on the wall
# clock or a random value.
DIAGNOSTICS_ENGINE_VERSION = "diagnostics-engine/1"

# Bump whenever a *statistical method* changes (the IC definition, the average-rank tie
# rule, the floor-based bucketing rule, the IC-information-ratio convention). Folded
# into ``config_hash`` so a method change is a new, distinguishable engine version — a
# value computed under one method can never be confused with one under another (D6, D7).
DIAGNOSTICS_FORMULA_VERSION = "diagnostics-stats/1"

# The pinned decimal context for all diagnostics arithmetic. Precision 34 with banker's
# rounding — identical to the metrics/market/backtest/analytics layers. Applied only via
# an explicit ``localcontext`` in the compute functions, never the ambient process
# context, so results are deterministic regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned diagnostics decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class SignalDiagnosticsEngineVersion:
    """Immutable identity of the diagnostics-engine logic + config (§5, D6/D9).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    formula_version:
        Revision string for the statistical *method* set (IC definition, tie rule,
        bucketing rule); folded into ``config_hash`` so a method change is a new
        version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every statistic can
        round), so any change to it is a new version.
    """

    code_version: str = DIAGNOSTICS_ENGINE_VERSION
    formula_version: str = DIAGNOSTICS_FORMULA_VERSION
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
    def signal_diagnostics_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for diagnostics arithmetic."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
