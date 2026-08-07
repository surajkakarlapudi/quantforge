"""The official SEC ticker → CIK mapping, parsed into a queryable index.

SEC publishes ``company_tickers.json`` at ``www.sec.gov/files/company_tickers.json``
as the authoritative ticker/name → CIK directory. Its shape is a JSON object
keyed by arbitrary string indices::

    {
      "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
      "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
      ...
    }

:class:`TickerMap` parses those bytes once into deterministic lookup indices by
ticker, by CIK, and by company title. It performs **no** network I/O and holds
no hardcoded companies — the data is entirely SEC's. Every CIK it emits is
canonicalized through the Phase 1 :func:`~quantforge.sec.endpoints.canonical_cik`
so identity never diverges from the rest of the project.

Lookups fail closed: an unknown symbol raises, and a symbol that maps to more
than one CIK is ambiguous and raises rather than picking one (a ticker can be
reassigned across issuers over time, and titles are not unique).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from quantforge.identity.errors import (
    AmbiguousSymbolError,
    UnknownSymbolError,
)
from quantforge.sec.endpoints import canonical_cik

__all__ = ["TickerEntry", "TickerMap"]


@dataclass(frozen=True, slots=True)
class TickerEntry:
    """One filer row from the official mapping (ticker, title, canonical CIK).

    ``cik`` is the canonical bare-integer CIK string (Phase 1 form); ``ticker``
    and ``title`` are preserved exactly as SEC supplies them for provenance,
    while the normalized forms used for lookup are derived on demand.
    """

    ticker: str
    title: str
    cik: str


def _normalize_ticker(value: str) -> str:
    # SEC tickers are upper-case; normalize case and surrounding whitespace so a
    # user's "aapl" resolves. We do not alter internal punctuation (e.g. "BRK-B"
    # vs "BRK.B") — that is an exact SEC-supplied token.
    return value.strip().upper()


def _normalize_title(value: str) -> str:
    # Titles vary in case ("Apple Inc." vs "MICROSOFT CORP"); fold case and
    # collapse surrounding whitespace for a forgiving exact-title match.
    return " ".join(value.strip().upper().split())


class TickerMap:
    """A parsed, in-memory index over SEC's official ticker → CIK mapping."""

    def __init__(self, entries: list[TickerEntry]) -> None:
        # Deterministic ordering, independent of source iteration order.
        self._entries = sorted(entries, key=lambda e: (e.cik, e.ticker, e.title))
        self._by_ticker: dict[str, set[str]] = {}
        self._by_title: dict[str, set[str]] = {}
        self._by_cik: dict[str, TickerEntry] = {}
        for entry in self._entries:
            self._by_ticker.setdefault(_normalize_ticker(entry.ticker), set()).add(
                entry.cik
            )
            self._by_title.setdefault(_normalize_title(entry.title), set()).add(
                entry.cik
            )
            # A CIK may carry several tickers (share classes); keep the first
            # deterministically as its representative entry.
            self._by_cik.setdefault(entry.cik, entry)

    @classmethod
    def from_bytes(cls, data: bytes) -> TickerMap:
        """Parse SEC ``company_tickers.json`` bytes into a :class:`TickerMap`.

        Rows missing a CIK or ticker, or with an unparseable CIK, are skipped
        (the directory occasionally carries incomplete rows); a well-formed row
        is never dropped. Raises ``ValueError`` if the document is not the
        expected JSON object shape — we never guess at a malformed mapping.
        """
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            raise ValueError("company_tickers.json must be a JSON object")
        entries: list[TickerEntry] = []
        for row in parsed.values():
            if not isinstance(row, dict):
                continue
            raw_cik = row.get("cik_str")
            ticker = row.get("ticker")
            title = row.get("title", "")
            if raw_cik is None or not isinstance(ticker, str) or not ticker.strip():
                continue
            try:
                cik = canonical_cik(raw_cik)
            except (ValueError, TypeError):
                continue
            entries.append(
                TickerEntry(
                    ticker=ticker,
                    title=title if isinstance(title, str) else "",
                    cik=cik,
                )
            )
        return cls(entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[TickerEntry]:
        return iter(self._entries)

    def entry_for_cik(self, cik: str | int) -> TickerEntry | None:
        """Return the representative entry for a CIK, or ``None`` if not listed.

        Not every EDGAR filer has an assigned ticker, so a CIK absent from this
        mapping is not an error — it simply has no ticker/title metadata here.
        """
        return self._by_cik.get(canonical_cik(cik))

    def cik_for_ticker(self, ticker: str) -> str:
        """Resolve a ticker to its canonical CIK (fail-closed).

        Raises :class:`UnknownSymbolError` if the ticker is not listed and
        :class:`AmbiguousSymbolError` if it maps to more than one CIK.
        """
        return self._resolve_unique(ticker, self._by_ticker, _normalize_ticker)

    def cik_for_title(self, title: str) -> str:
        """Resolve an exact company title to its canonical CIK (fail-closed)."""
        return self._resolve_unique(title, self._by_title, _normalize_title)

    def _resolve_unique(
        self,
        identifier: str,
        index: dict[str, set[str]],
        normalize: Callable[[str], str],
    ) -> str:
        key = normalize(identifier)
        candidates = index.get(key)
        if not candidates:
            raise UnknownSymbolError(identifier)
        if len(candidates) > 1:
            raise AmbiguousSymbolError(identifier, sorted(candidates))
        return next(iter(candidates))
