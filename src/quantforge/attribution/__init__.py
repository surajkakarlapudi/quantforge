"""Multi-factor performance attribution: deterministic, content-addressed OLS (Phase
17).

The layer strictly above Phase 12 (proposal D1): it consumes an already-sealed,
PIT-correct subject :class:`~quantforge.backtest.result.BacktestResult` and *K* factor
backtests (each itself a sealed ``BacktestResult`` — the Phase 15 D3 convention
generalized from one benchmark to *K* factors), regresses the subject's excess return on
the factors' excess returns via an exact-``Decimal`` OLS, and seals the answer as a new
:class:`~quantforge.factors.store.ResearchRecord`. It re-resolves no data, introduces no
new PIT surface, adds no runtime dependency, and creates no new store.

* :class:`~quantforge.attribution.spec.AttributionSpecification` — the declarative,
  content-addressed request: a name, the ``subject_id`` of a sealed backtest, an ordered
  tuple of factor ``backtest_id``s, and the annualization convention (proposal §12).
* :class:`~quantforge.attribution.engine.AttributionEngine` — resolves the subject and
  each factor from the shared sidecar, verifies them (fail closed on missing / drifted /
  incommensurable — proposal §11), regresses under the pinned decimal context, and seals
  a :class:`~quantforge.attribution.result.FactorAttribution`, persisting it write-once
  to the same Phase 8 sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.attribution_engine`).
* :class:`~quantforge.attribution.result.FactorAttribution` — the sealed,
  content-addressed record: the referenced ``(backtest_id, result_hash)`` pointers, the
  three computed blocks (coefficients / diagnostics / decomposition), the residual
  digest, the recorded convention, and the carried corpus pins. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically (proposal §9, D2). It is **ex-post, not PIT** (FA-2): not a ``Pit*``
  type, no as-of accessor.
* :class:`~quantforge.attribution.model.StatValue` — the UNDEFINED-preserving statistic
  cell: a KNOWN decimal string **or** an UNDEFINED
  :class:`~quantforge.attribution.model.AttributionUndefinedReason`, never a fabricated
  ``0`` / ``NaN`` / divide-by-zero, never a silently dropped factor (proposal §11,
  FA-4).

Every identity is content-addressed (:mod:`quantforge.attribution.identity`), every
value deterministically serializable, and every failure follows the raise-vs-record
split (:mod:`quantforge.attribution.errors`): a defect raises; a statistic genuinely
undefined for the data is recorded with its reason.
"""

from __future__ import annotations

from quantforge.attribution.engine import AttributionEngine
from quantforge.attribution.errors import (
    AttributionConfigurationError,
    AttributionConsistencyError,
    AttributionError,
)
from quantforge.attribution.model import (
    DIAGNOSTIC_KEYS,
    INTERCEPT_LABEL,
    AttributionStatus,
    AttributionUndefinedReason,
    StatValue,
    factor_label,
)
from quantforge.attribution.result import (
    ATTRIBUTION_RESULT_FORMAT_VERSION,
    BOUNDARY_PIT,
    FactorAttribution,
)
from quantforge.attribution.spec import (
    ATTRIBUTION_SPEC_VERSION,
    K_MAX,
    AttributionSpecification,
)
from quantforge.attribution.version import (
    ATTRIBUTION_ENGINE_VERSION,
    ATTRIBUTION_FORMULA_VERSION,
    AttributionEngineVersion,
    default_decimal_context,
)

__all__ = [
    "ATTRIBUTION_ENGINE_VERSION",
    "ATTRIBUTION_FORMULA_VERSION",
    "ATTRIBUTION_RESULT_FORMAT_VERSION",
    "ATTRIBUTION_SPEC_VERSION",
    "BOUNDARY_PIT",
    "DIAGNOSTIC_KEYS",
    "INTERCEPT_LABEL",
    "K_MAX",
    "AttributionConfigurationError",
    "AttributionConsistencyError",
    "AttributionEngine",
    "AttributionEngineVersion",
    "AttributionError",
    "AttributionSpecification",
    "AttributionStatus",
    "AttributionUndefinedReason",
    "FactorAttribution",
    "StatValue",
    "default_decimal_context",
    "factor_label",
]
