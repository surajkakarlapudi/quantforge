"""The cross-sectional factor layer (Phase 8) — one metric across a universe.

Phase 7 answers *one metric, one filer, one boundary*. Phase 8 is the
cross-sectional research primitive built on top: **one metric, evaluated across a
caller-supplied explicit universe of filers, for one fiscal period, at one shared
knowledge-state boundary** — a PIT ``as_of`` or a REVISED universe-wide
``DatasetVersion`` — yielding a fail-closed, fully-provenanced factor vector plus a
reproducible, content-addressed :class:`ResearchResult` (``docs/factors.md``).

The front door is :class:`FactorEngine` (constructed from a
:class:`~openfinance.workspace.Workspace`)::

    from openfinance.factors import FactorEngine, Universe, Transform

    engine = workspace.factor_engine
    universe = Universe.of(320193, 789019, 1652044)  # explicit, ordered (F1)
    factor = engine.factor_as_of(
        "gross_margin", universe, period, as_of, transform=Transform.zscore()
    )

It **composes, never re-resolves** the lower layers: Phase 5 decided eligibility
and restatement order, Phase 7 did the arithmetic. This layer only fans out over
the universe, assembles the cross-section, applies the pure transforms, and
packages the ``ResearchResult``. The PIT/REVISED distinction is preserved as two
distinct result types (:class:`PitFactor` / :class:`RevisedFactor`, Decision F5),
so a consumer typed to one can never be handed the other.
"""

from __future__ import annotations

from openfinance.factors.engine import FactorEngine
from openfinance.factors.errors import (
    FactorConfigurationError,
    FactorConsistencyError,
    FactorError,
)
from openfinance.factors.model import (
    FactorCell,
    FactorStatus,
    PitFactor,
    ResearchResult,
    RevisedFactor,
)
from openfinance.factors.store import ResearchResultStore
from openfinance.factors.transform import Transform, TransformKind
from openfinance.factors.universe import Universe

__all__ = [
    "FactorCell",
    "FactorConfigurationError",
    "FactorConsistencyError",
    "FactorEngine",
    "FactorError",
    "FactorStatus",
    "PitFactor",
    "ResearchResult",
    "ResearchResultStore",
    "RevisedFactor",
    "Transform",
    "TransformKind",
    "Universe",
]
