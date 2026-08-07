"""QuantForge Phase 9 — the Universe Research Layer.

A :class:`Universe` is a deterministic, immutable, point-in-time collection of filer
identities — the securities a later cross-sectional step operates across. Phase 9 is
one coherent capability, delivered in three cooperating parts on a single universe
abstraction:

    Universe management  →  construction  →  inspection / analysis / comparison / export

* **Management (9.1).** A :class:`Universe` resolves and holds membership through the
  existing company identity layer (no new identifier system), preserving first-seen
  order and per-member provenance, and content-addressing the ordered membership::

      universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"])

* **Construction (9.2).** A deterministic ``UniverseSpecification → UniverseBuilder →
  Universe (+ UniverseConstruction)`` framework:

  * :class:`UniverseSpecification` — the immutable, serializable, content-addressed
    *request*: a name, a version, and an **ordered** list of selection
    :mod:`~quantforge.universe.filters` (``ExplicitCompanyFilter``,
    ``CompanyMetricFilter``, ``SectorFilter``). It holds no data and no boundary.
  * :class:`UniverseBuilder` — the fail-closed *engine* that evaluates a
    specification at one PIT/REVISED boundary, composing the existing
    ``CompanyResolver`` and ``MetricEngine``, and emits a :class:`ConstructionResult`
    (the :class:`Universe` plus a reproducible :class:`UniverseConstruction`
    provenance record: specification identity, builder version, boundary, applied
    filters, and every excluded company with its reason).

* **Research surface (this completion).** Inspection, deterministic description,
  membership comparison, and dependency-free export on the *same* universe object —
  no second abstraction, no financial statistics, no market data:

  * inspection — :meth:`Universe.members`, :attr:`Universe.company_ids`,
    ``len(universe)``, :meth:`Universe.contains`, and
    :meth:`ConstructionResult.provenance` / :meth:`UniverseConstruction.excluded_for`;
  * description — :meth:`Universe.describe` / :meth:`ConstructionResult.describe`
    return a serializable :class:`UniverseSummary`;
  * comparison — :meth:`Universe.compare` / :meth:`ConstructionResult.compare` return
    a serializable :class:`UniverseComparison` that diffs by canonical ``company_id``
    and surfaces any PIT/REVISED mode mismatch;
  * export — :meth:`Universe.to_dict` / :meth:`Universe.to_records`.

Ranking, portfolios, optimization, backtesting, price feeds, and market-data
ingestion remain deliberately **not** implemented here — those belong to later
phases. Phase 9 is research-*universe* infrastructure.
"""

from __future__ import annotations

from quantforge.universe.analysis import UniverseComparison, UniverseSummary
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
    "UniverseComparison",
    "UniverseConfigurationError",
    "UniverseConstruction",
    "UniverseConstructionVersion",
    "UniverseError",
    "UniverseFilter",
    "UniverseSpecification",
    "UniverseSpecificationError",
    "UniverseSummary",
    "filter_from_dict",
]
