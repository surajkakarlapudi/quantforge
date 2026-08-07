"""QuantForge universe layer: management (Phase 9.1) + construction rules (Phase 9.2).

A :class:`Universe` is a deterministic, immutable, point-in-time collection of filer
identities — the securities a later cross-sectional step operates across. **Phase
9.1** builds that membership foundation; it resolves and holds membership through the
existing company identity layer (no new identifier system). **Phase 9.2** adds a
deterministic *construction framework* on top:

    UniverseSpecification  →  UniverseBuilder  →  Universe (+ UniverseConstruction)

* :class:`UniverseSpecification` — the immutable, serializable, content-addressed
  *request*: a name, a version, and an **ordered** list of selection
  :mod:`~quantforge.universe.filters` (``ExplicitCompanyFilter``,
  ``CompanyMetricFilter``, ``SectorFilter``). It holds no data and no boundary.
* :class:`UniverseBuilder` — the fail-closed *engine* that evaluates a specification
  at one PIT/REVISED boundary, composing the existing ``CompanyResolver`` and
  ``MetricEngine``, and emits a :class:`Universe` plus a reproducible
  :class:`UniverseConstruction` provenance record (specification identity, builder
  version, boundary, applied filters, and every excluded company with its reason).
* :class:`Universe` — the resolved, ordered, de-duplicated membership (Phase 9.1),
  unchanged.

Direct membership is still available via the Phase 9.1 front door::

    from quantforge.universe import Universe

    universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"])

Ranking, portfolios, optimization, and backtesting remain deliberately **not**
implemented here.
"""

from __future__ import annotations

from quantforge.universe.builder import UniverseBuilder
from quantforge.universe.construction import (
    AppliedFilter,
    ConstructionResult,
    UniverseConstruction,
)
from quantforge.universe.errors import (
    UniverseConfigurationError,
    UniverseError,
    UniverseSpecificationError,
)
from quantforge.universe.filters import (
    CompanyMetricFilter,
    ComparisonOperator,
    ExcludedCompany,
    ExclusionReason,
    ExplicitCompanyFilter,
    FilterContext,
    FilterKind,
    FilterOutcome,
    SectorClassification,
    SectorFilter,
    UniverseFilter,
    filter_from_dict,
)
from quantforge.universe.model import Universe
from quantforge.universe.specification import (
    SPECIFICATION_VERSION,
    UniverseSpecification,
)
from quantforge.universe.version import (
    UNIVERSE_BUILDER_VERSION,
    UNIVERSE_CONSTRUCTION_VERSION,
    UniverseBuilderVersion,
    UniverseConstructionVersion,
)

__all__ = [
    "SPECIFICATION_VERSION",
    "UNIVERSE_BUILDER_VERSION",
    "UNIVERSE_CONSTRUCTION_VERSION",
    "AppliedFilter",
    "CompanyMetricFilter",
    "ComparisonOperator",
    "ConstructionResult",
    "ExcludedCompany",
    "ExclusionReason",
    "ExplicitCompanyFilter",
    "FilterContext",
    "FilterKind",
    "FilterOutcome",
    "SectorClassification",
    "SectorFilter",
    "Universe",
    "UniverseBuilder",
    "UniverseBuilderVersion",
    "UniverseConfigurationError",
    "UniverseConstruction",
    "UniverseConstructionVersion",
    "UniverseError",
    "UniverseFilter",
    "UniverseSpecification",
    "UniverseSpecificationError",
    "filter_from_dict",
]
