"""The company-identity error vocabulary (fail-closed).

Resolution never guesses. When an identifier cannot be resolved to exactly one
filer, or the official mapping needed to resolve it is not available offline, we
raise — we never fabricate a CIK, silently pick among ambiguous candidates, or
fall back to a hardcoded table.
"""

from __future__ import annotations

__all__ = [
    "AmbiguousSymbolError",
    "IdentityError",
    "TickerMapUnavailableError",
    "UnknownSymbolError",
]


class IdentityError(Exception):
    """Base class for every company-identity resolution failure."""


class UnknownSymbolError(IdentityError):
    """The identifier matched no filer in the official SEC ticker mapping."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(
            f"no SEC filer found for {identifier!r}; it is not a known ticker, "
            "company title, or CIK in the official company_tickers mapping"
        )


class AmbiguousSymbolError(IdentityError):
    """The identifier matched more than one filer — we never arbitrate."""

    def __init__(self, identifier: str, candidates: list[str]) -> None:
        self.identifier = identifier
        self.candidates = candidates
        joined = ", ".join(candidates)
        super().__init__(
            f"{identifier!r} is ambiguous: it matches multiple filers "
            f"({joined}); resolve by CIK instead"
        )


class TickerMapUnavailableError(IdentityError):
    """The official ticker mapping is not cached and cannot be fetched offline.

    Resolution by ticker or company name needs SEC's ``company_tickers.json``.
    When it is neither present in the content-addressed cache nor fetchable
    (no network client wired), we fail closed rather than guess.
    """

    def __init__(self) -> None:
        super().__init__(
            "the official SEC ticker mapping (company_tickers.json) is not "
            "cached and no network client is available to fetch it; acquire it "
            "once (SecClient.acquire_company_tickers) or resolve by CIK"
        )
