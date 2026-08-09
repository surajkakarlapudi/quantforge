"""Provider-neutral market-data acquisition seam (§11, §12, D6).

The canonical layer depends on **no** single vendor (not Yahoo, Alpha Vantage,
Polygon, Bloomberg, Nasdaq, or any other). The vendor-facing capability is a narrow
:class:`typing.Protocol` — :class:`MarketDataProvider` — mirroring the SEC layer's
narrow-Protocol client style, and a concrete adapter (added later, **outside** core)
implements it for one vendor and maps that vendor's bytes → canonical
:class:`~quantforge.market.model.PriceObservation` /
:class:`~quantforge.market.model.CorporateAction`. The canonical layer never imports
a provider.

A provider returns a :class:`RawMarketDocument`: the immutable bytes exactly as the
vendor delivered them, plus the :class:`~quantforge.sec.artifacts.AcquisitionMetadata`
provenance needed to store them content-addressed in the raw tier (the Phase 1
:class:`~quantforge.sec.storage.ArtifactStore`, reused verbatim). Identity is the
bytes' SHA-256; timestamps are provenance, never identity (§14).

:class:`FakeMarketDataProvider` is the in-repo **synthetic** provider used by every
test: it returns obviously-non-real bars (round numbers, fictional tickers) from an
injected fixture, so the whole layer is testable offline with no network and no risk
of shipping data mistakable for real (Principle 8, §19). Zero new runtime
dependencies (Principle 10): the stdlib transport already ships; nothing here imports
a vendor SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from quantforge.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)

__all__ = [
    "DateRange",
    "FakeMarketDataProvider",
    "MarketDataProvider",
    "RawMarketDocument",
]


@dataclass(frozen=True, slots=True)
class DateRange:
    """An inclusive ``[start, end]`` range of ``YYYY-MM-DD`` session dates."""

    start: str
    end: str


@dataclass(frozen=True, slots=True)
class RawMarketDocument:
    """Immutable vendor bytes exactly as fetched + retrieval provenance (§13).

    The market analogue of ``RawDocument``: content-addressed (:attr:`sha256`) so a
    vendor's *correction* is a new document (a new hash), never a mutation, and a bad
    download can never masquerade as a valid artifact. ``metadata`` is Phase 1
    :class:`~quantforge.sec.artifacts.AcquisitionMetadata` (a market-data
    :class:`~quantforge.sec.artifacts.ArtifactType` slug, ``security_id`` carried in
    ``cik`` when it is a ``cik:`` form, ``accession=None`` always so it can never
    associate to an SEC filing). Convertible to a Phase 1
    :class:`~quantforge.sec.artifacts.Artifact` for storage.
    """

    data: bytes
    metadata: AcquisitionMetadata

    @property
    def sha256(self) -> str:
        return self.metadata.sha256

    def as_artifact(self) -> Artifact:
        """View these bytes as a Phase 1 :class:`Artifact` for the raw store."""
        return Artifact(data=self.data, metadata=self.metadata)


@runtime_checkable
class MarketDataProvider(Protocol):
    """The minimal vendor-facing contract the market layer depends on (§11).

    A concrete adapter (outside core) builds an
    :class:`~quantforge.sec.transport.HttpRequest`, sends it through the injected
    :class:`~quantforge.sec.client` retry/throttle stack, and wraps the response
    bytes in a :class:`RawMarketDocument`. Both methods return raw bytes; the
    deterministic canonicalizer (:mod:`quantforge.market.canonical`) parses them into
    canonical records, so re-normalization never needs a re-fetch.
    """

    def fetch_daily_bars(
        self, security_id: str, date_range: DateRange
    ) -> RawMarketDocument:
        """Fetch the raw daily-bar payload for one instrument over a date range."""
        ...

    def fetch_corporate_actions(
        self, security_id: str, date_range: DateRange
    ) -> RawMarketDocument:
        """Fetch the raw corporate-action payload for one instrument."""
        ...


class FakeMarketDataProvider:
    """An offline, synthetic :class:`MarketDataProvider` for tests (§19).

    Returns caller-supplied fixture bytes keyed by ``security_id``, wrapped with a
    deterministic :class:`~quantforge.sec.artifacts.AcquisitionMetadata` (injected
    ``retrieved_at``, a synthetic ``source_url``, the market
    :class:`~quantforge.sec.artifacts.ArtifactType` slugs). It touches no network and
    carries no real data — fixtures are obviously synthetic (round numbers, fictional
    tickers like ``ZZZZ``). ``user_agent`` is a non-secret identity string.
    """

    def __init__(
        self,
        *,
        bars_by_security: dict[str, bytes],
        actions_by_security: dict[str, bytes] | None = None,
        retrieved_at: str,
        user_agent: str = "quantforge-test-fake-provider",
        source_name: str = "fake-market-data",
    ) -> None:
        self._bars = dict(bars_by_security)
        self._actions = dict(actions_by_security or {})
        self._retrieved_at = retrieved_at
        self._user_agent = user_agent
        self._source_name = source_name

    def fetch_daily_bars(
        self, security_id: str, date_range: DateRange
    ) -> RawMarketDocument:
        data = self._bars.get(security_id, b"")
        return self._document(
            data, security_id, date_range, ArtifactType.MARKET_DAILY_BARS
        )

    def fetch_corporate_actions(
        self, security_id: str, date_range: DateRange
    ) -> RawMarketDocument:
        data = self._actions.get(security_id, b"")
        return self._document(
            data, security_id, date_range, ArtifactType.MARKET_CORPORATE_ACTIONS
        )

    def _document(
        self,
        data: bytes,
        security_id: str,
        date_range: DateRange,
        artifact_type: ArtifactType,
    ) -> RawMarketDocument:
        # A synthetic but stable source URL, so provenance round-trips the same way.
        url = (
            f"fake://{self._source_name}/{artifact_type.value}"
            f"?security_id={security_id}&start={date_range.start}&end={date_range.end}"
        )
        metadata = AcquisitionMetadata(
            source_url=url,
            artifact_type=artifact_type,
            sha256=sha256_hex(data),
            retrieved_at=self._retrieved_at,
            http_status=200,
            user_agent=self._user_agent,
            content_type="application/json",
            content_length=len(data),
            # security_id rides in the `cik` slot when it is a cik: form (it is the
            # market anchor); accession is ALWAYS None so this can never associate to
            # an SEC filing.
            cik=security_id if security_id.startswith("cik:") else None,
            accession=None,
        )
        return RawMarketDocument(data=data, metadata=metadata)
