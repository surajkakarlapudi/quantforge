"""The resolved company identity value object.

:class:`CompanyIdentity` is the deterministic result of resolving a user-facing
identifier (ticker, CIK, or company title) to the project's canonical filer
identity. It carries the canonical ``company_id`` used throughout Phases 2-5,
the bare-integer ``cik``, and — when the official mapping supplies them — the
ticker and title, plus how the resolution was made (for provenance).

Identity here follows the same rule as everywhere else (data-model §11): the
stable payload is the CIK. The ticker and name are descriptive metadata that can
change over time; they never participate in identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from openfinance.registry.identity import company_id as _company_id
from openfinance.sec.endpoints import canonical_cik

__all__ = ["CompanyIdentity", "ResolutionSource"]


class ResolutionSource(StrEnum):
    """How an identifier was resolved to a filer (provenance, not identity)."""

    #: Matched a ticker in the official SEC company_tickers mapping.
    TICKER = "ticker"
    #: Matched an exact company title in the official mapping.
    NAME = "name"
    #: Supplied directly as a CIK (integer, CIK-prefixed, or explicit by="cik").
    CIK = "cik"


@dataclass(frozen=True, slots=True)
class CompanyIdentity:
    """A resolved filer identity: canonical ``company_id`` + descriptive labels."""

    company_id: str
    cik: str
    ticker: str | None
    name: str | None
    #: The exact identifier string the user supplied, preserved for provenance.
    resolved_from: str
    #: Which lookup produced the match.
    source: ResolutionSource

    @classmethod
    def from_cik(
        cls,
        cik: str | int,
        *,
        resolved_from: str,
        source: ResolutionSource,
        ticker: str | None = None,
        name: str | None = None,
    ) -> CompanyIdentity:
        """Build an identity from a CIK, canonicalizing ``company_id``/``cik``."""
        canonical = canonical_cik(cik)
        return cls(
            company_id=_company_id(canonical),
            cik=canonical,
            ticker=ticker,
            name=name,
            resolved_from=resolved_from,
            source=source,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "cik": self.cik,
            "ticker": self.ticker,
            "name": self.name,
            "resolved_from": self.resolved_from,
            "source": self.source.value,
        }
