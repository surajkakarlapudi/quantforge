"""The point-in-time fundamental panel layer (Phase 10) — one metric over a time axis.

Phase 7 answers *one metric, one filer, one period, one boundary*; Phase 8 fans that
across a universe at one period. Phase 10 adds the **time axis**: *one metric,
evaluated over a declared period axis, for one filer or one universe, at one shared
knowledge-state boundary* — in three shapes (``docs/phase10-panel-locked.md``):

* **period-series** — one filer, many periods, one ``as_of`` (the basis for every
  multi-period derivation);
* **vintage** — one filer, one period, many ``as_of`` instants (PIT-only — REVISED
  has no ``as_of`` axis);
* **cross-sectional matrix** — many filers x many periods at one ``as_of``
  (engine-only, reuses the Phase 8 :class:`Universe`).

The front door is :class:`PanelEngine` (constructed from a
:class:`~quantforge.workspace.Workspace`)::

    from quantforge.panel import PanelEngine, PeriodAxis, Derivation
    from quantforge.xbrl.contexts import PeriodType

    engine = workspace.panel_engine
    axis = PeriodAxis.annual("2018-12-31", "2023-12-31", period_type=PeriodType.INSTANT)
    panel = engine.panel_as_of("current_ratio", 320193, axis, as_of)
    growth = engine.panel_as_of(
        "working_capital", 320193, axis, as_of, derivation=Derivation.growth()
    )

It **composes, never re-resolves** the lower layers: Phase 5 decided eligibility and
restatement order, Phase 7 did the arithmetic, Phase 8 fans across a universe. This
layer adds only the time axis, the pure ``UNDEFINED``-preserving multi-period
derivations, the cross-sectional stacking, and the reproducible
:class:`PanelResearchResult` (persisted to the shared Phase 8 sidecar). The
PIT/REVISED distinction is preserved as two distinct result types
(:class:`PitPanel` / :class:`RevisedPanel`, Decision D5), so a consumer typed to one
can never be handed the other, and a revised → PIT conversion must re-resolve
explicitly at an ``as_of``.
"""

from __future__ import annotations

from quantforge.panel.axis import PeriodAxis
from quantforge.panel.derive import Derivation, DerivationKind, HistoryStat
from quantforge.panel.engine import PanelEngine
from quantforge.panel.errors import (
    PanelConfigurationError,
    PanelConsistencyError,
    PanelError,
)
from quantforge.panel.model import (
    PanelCell,
    PanelResearchResult,
    PanelShape,
    PanelStatus,
    PitPanel,
    RevisedPanel,
)

__all__ = [
    "Derivation",
    "DerivationKind",
    "HistoryStat",
    "PanelCell",
    "PanelConfigurationError",
    "PanelConsistencyError",
    "PanelEngine",
    "PanelError",
    "PanelResearchResult",
    "PanelShape",
    "PanelStatus",
    "PeriodAxis",
    "PitPanel",
    "RevisedPanel",
]
