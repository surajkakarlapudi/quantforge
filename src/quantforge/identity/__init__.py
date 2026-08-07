"""Company identity layer — resolve tickers / CIKs / names to a filer identity.

This layer sits *beside* Phases 1-5, not inside them. It answers a single
question — *"which filer does this user-facing symbol mean?"* — and returns the
canonical ``company_id`` the rest of the project already uses (data-model §11).

It reuses the official SEC ``company_tickers.json`` mapping (retrieved and cached
through the Phase 1 content-addressed store) and never hardcodes any company. It
introduces no new data model and no second storage system.
"""

from __future__ import annotations

from quantforge.identity.errors import (
    AmbiguousSymbolError,
    IdentityError,
    TickerMapUnavailableError,
    UnknownSymbolError,
)
from quantforge.identity.model import CompanyIdentity, ResolutionSource
from quantforge.identity.resolve import CompanyResolver, looks_like_cik
from quantforge.identity.tickers import TickerEntry, TickerMap

__all__ = [
    "AmbiguousSymbolError",
    "CompanyIdentity",
    "CompanyResolver",
    "IdentityError",
    "ResolutionSource",
    "TickerEntry",
    "TickerMap",
    "TickerMapUnavailableError",
    "UnknownSymbolError",
    "looks_like_cik",
]
