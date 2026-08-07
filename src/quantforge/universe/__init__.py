"""QuantForge universe-management layer (Phase 9.1).

A :class:`Universe` is a deterministic, immutable, point-in-time collection of
filer identities — the securities a later cross-sectional step operates across.
This is the *foundation only*: it resolves and holds membership. Ranking,
portfolios, and backtesting are deliberately **not** implemented here.

The front door is :meth:`Universe.from_companies`::

    from quantforge.universe import Universe

    universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"])
    for company_id in universe:
        ...

Membership is resolved through the existing company identity layer
(:class:`~quantforge.identity.resolve.CompanyResolver`), so the universe layer
introduces **no** new company-identifier system: every member is keyed by the
canonical ``company_id`` used across all phases (data-model §11). Ordering is
deterministic (first-seen, de-duplicated), provenance is preserved per member and
for the builder, and :attr:`Universe.universe_id` is a content hash over the
ordered membership.
"""

from __future__ import annotations

from quantforge.universe.errors import (
    UniverseConfigurationError,
    UniverseError,
)
from quantforge.universe.model import Universe
from quantforge.universe.version import (
    UNIVERSE_BUILDER_VERSION,
    UniverseBuilderVersion,
)

__all__ = [
    "UNIVERSE_BUILDER_VERSION",
    "Universe",
    "UniverseBuilderVersion",
    "UniverseConfigurationError",
    "UniverseError",
]
