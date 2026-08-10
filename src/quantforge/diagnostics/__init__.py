"""Phase 16 — Cross-Sectional Signal Diagnostics (locked ``docs/phase16-…-locked.md``).

The *diagnostic sibling* of the Phase 12 backtester: a pure-consumer research layer
that measures whether an as-of-``T`` signal cross-section predicts each member's
realized **forward** return over a horizon — the Information Coefficient (Spearman rank
+ Pearson), quantile-bucket mean forward returns, and the top-minus-bottom spread —
summarised across a schedule of evaluation dates and sealed as a content-addressed,
write-once research record.

It sits **above** and composes **only** Phases 9 (survivorship-free universe), 10
(``panel_across`` signal cross-section), and 11 (the PIT-gated adjusted price view); it
consumes **no** ``BacktestResult``, introduces no new store (reusing the Phase 8
sidecar), and adds no new PIT resolver. Its four hard invariants — SD-1 (both corpus
pins verified, fail closed; a changed corpus yields a different ``diagnostics_id``),
SD-2 (a distinct forward-looking type: no ``Pit*`` type, no as-of accessor), SD-3 (the
signal is read PIT-eligible at ``T``), and SD-4 (fail-closed pairing: a member without a
PIT signal or a
computable forward return is excluded and recorded in coverage, never imputed) — are the
public contract of this package.

The public surface: the declarative :class:`SignalDiagnosticsSpecification`, the sealed
:class:`SignalDiagnostics` record, and the :class:`SignalDiagnosticsEngine` (its
``evaluate(spec)`` method the single entry point; normally reached via
``workspace.signal_diagnostics_engine``).
"""

from __future__ import annotations

from quantforge.diagnostics.engine import SignalDiagnosticsEngine
from quantforge.diagnostics.errors import (
    SignalDiagnosticsConfigurationError,
    SignalDiagnosticsConsistencyError,
    SignalDiagnosticsError,
)
from quantforge.diagnostics.model import (
    CoverageSummary,
    DateCoverage,
    DiagnosticStatus,
    DiagnosticUndefinedReason,
    ICMethod,
    ICMethodSummary,
    ICSummary,
    PerDateIC,
    QuantileProfile,
    StatValue,
)
from quantforge.diagnostics.result import SignalDiagnostics
from quantforge.diagnostics.spec import SignalDiagnosticsSpecification
from quantforge.diagnostics.version import SignalDiagnosticsEngineVersion

__all__ = [
    "CoverageSummary",
    "DateCoverage",
    "DiagnosticStatus",
    "DiagnosticUndefinedReason",
    "ICMethod",
    "ICMethodSummary",
    "ICSummary",
    "PerDateIC",
    "QuantileProfile",
    "SignalDiagnostics",
    "SignalDiagnosticsConfigurationError",
    "SignalDiagnosticsConsistencyError",
    "SignalDiagnosticsEngine",
    "SignalDiagnosticsEngineVersion",
    "SignalDiagnosticsError",
    "SignalDiagnosticsSpecification",
    "StatValue",
]
