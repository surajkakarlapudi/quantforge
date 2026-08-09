"""Research reporting & explainability: deterministic, content-addressed reports
(Phase 14).

The layer strictly above Phase 13 (locked D1): it consumes already-sealed, PIT-correct
research artifacts — a :class:`~quantforge.backtest.result.BacktestResult` or an
:class:`~quantforge.experiment.result.ExperimentResult` — and never re-resolves data,
introduces new arithmetic, or creates a new store. A **report** is a declarative,
content-addressed request turned into an immutable, auditable artifact:

* :class:`~quantforge.report.spec.ReportSpecification` — the declarative,
  content-addressed request (a name, a closed-vocabulary ``scope`` of
  ``{backtest, experiment}``, the ``subject_id`` of the sealed artifact being reported,
  and optional :class:`~quantforge.report.spec.ComparisonDirective`s ranking an
  experiment's children by a Phase 13 statistic — locked D7).
* :class:`~quantforge.report.engine.ReportEngine` — resolves the subject and each
  requested comparison from the shared sidecar, verifies them (fail closed on any
  missing/drifted reference — locked G7), and seals a
  :class:`~quantforge.report.result.ResearchReport`, persisting it write-once to the
  same Phase 8 sidecar with no new store (locked D1, D8).
* :class:`~quantforge.report.result.ResearchReport` — the sealed, content-addressed
  record: a thin, reproducible manifest of
  :class:`~quantforge.report.result.ReportReference` pointers (never a copy of any
  financial value — locked D3), satisfying the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-tripping
  byte-identically (locked D4).
* :func:`~quantforge.report.render.render_markdown` — the single v1 reference renderer
  (locked D6): a pure, deterministic function that resolves references and formats
  Markdown with zero effect on identity or storage. Presentation, never model state
  (locked §10).

Every identity is content-addressed (:mod:`quantforge.report.identity`) and every value
deterministically serializable; failures follow the raise-vs-record split
(:mod:`quantforge.report.errors`).
"""

from __future__ import annotations

from quantforge.report.engine import ReportEngine
from quantforge.report.errors import (
    ReportConfigurationError,
    ReportConsistencyError,
    ReportError,
)
from quantforge.report.render import render_markdown
from quantforge.report.result import (
    BOUNDARY_PIT,
    REPORT_RESULT_FORMAT_VERSION,
    ReportReference,
    ResearchReport,
)
from quantforge.report.spec import (
    REPORT_SCOPES,
    REPORT_SPEC_VERSION,
    ComparisonDirective,
    ReportSpecification,
)

__all__ = [
    "BOUNDARY_PIT",
    "REPORT_RESULT_FORMAT_VERSION",
    "REPORT_SCOPES",
    "REPORT_SPEC_VERSION",
    "ComparisonDirective",
    "ReportConfigurationError",
    "ReportConsistencyError",
    "ReportEngine",
    "ReportError",
    "ReportReference",
    "ReportSpecification",
    "ResearchReport",
    "render_markdown",
]
