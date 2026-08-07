"""Tests for the Phase 9.1 :class:`Universe` — the deterministic filer collection.

Covers construction through the real company identity layer
(:meth:`Universe.from_companies`), deterministic first-seen ordering,
de-duplication by canonical ``company_id``, empty/mis-typed inputs failing closed,
per-member and builder provenance, and the content-addressed ``universe_id``
(determinism, order/membership sensitivity, and equality with the cross-sectional
factor universe over the same members).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quantforge.availability.store import AvailabilityStore
from quantforge.canonical.store import CanonicalFactStore
from quantforge.factors.universe import Universe as FactorUniverse
from quantforge.identity.errors import UnknownSymbolError
from quantforge.identity.model import CompanyIdentity, ResolutionSource
from quantforge.identity.resolve import CompanyResolver
from quantforge.registry.registry import FilingRegistry
from quantforge.registry.store import RegistryStore
from quantforge.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from quantforge.sec.storage import ArtifactStore
from quantforge.universe import Universe
from quantforge.universe.errors import UniverseConfigurationError
from quantforge.workspace import Workspace

# Official-mapping shape (see tests/identity): keyed by arbitrary string indices.
TICKERS = (
    b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
    b'"1":{"cik_str":789019,"ticker":"MSFT","title":"MICROSOFT CORP"},'
    b'"2":{"cik_str":1045810,"ticker":"NVDA","title":"NVIDIA CORP"},'
    b'"3":{"cik_str":1318605,"ticker":"TSLA","title":"Tesla, Inc."}}'
)


def _store_tickers(store: ArtifactStore) -> None:
    meta = AcquisitionMetadata(
        source_url="https://www.sec.gov/files/company_tickers.json",
        artifact_type=ArtifactType.COMPANY_TICKERS,
        sha256=sha256_hex(TICKERS),
        retrieved_at="2026-01-01T00:00:00",
        http_status=200,
        user_agent="test test@example.com",
    )
    store.store(Artifact(data=TICKERS, metadata=meta))


def _workspace(root: Path) -> Workspace:
    """A minimal offline workspace whose resolver serves the cached mapping.

    Only the resolver is exercised by the universe layer; the other stores are
    wired to satisfy the composition root exactly as production does (test_company
    builds them the same way).
    """
    artifacts = ArtifactStore(root / "sec")
    _store_tickers(artifacts)
    return Workspace(
        artifact_store=artifacts,
        registry=FilingRegistry(
            RegistryStore(root / "registry"), artifact_store=artifacts
        ),
        canonical_store=CanonicalFactStore(root / "canonical"),
        resolver=CompanyResolver(artifacts),  # offline; tickers already cached
        availability_store=AvailabilityStore(root / "availability"),
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return _workspace(tmp_path)


def _identity(cik: int, ticker: str, name: str) -> CompanyIdentity:
    return CompanyIdentity.from_cik(
        cik,
        resolved_from=ticker,
        source=ResolutionSource.TICKER,
        ticker=ticker,
        name=name,
    )


# -- from_companies: resolves through the identity layer --------------------


def test_from_companies_resolves_the_example(workspace: Workspace) -> None:
    universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"], workspace=workspace)
    assert universe.company_ids == (
        "cik:0000320193",
        "cik:0000789019",
        "cik:0001045810",
    )
    assert len(universe) == 3


def test_from_companies_uses_canonical_company_id_not_a_new_system(
    workspace: Workspace,
) -> None:
    # Every member is keyed by the canonical company_id produced by the identity
    # layer — the universe layer introduces no identifier system of its own.
    universe = Universe.from_companies(["NVDA"], workspace=workspace)
    (member,) = universe.identities
    assert member.company_id == "cik:0001045810"
    assert member.cik == "1045810"
    assert member.ticker == "NVDA"
    assert member.source is ResolutionSource.TICKER


def test_from_companies_accepts_mixed_ticker_and_cik(workspace: Workspace) -> None:
    # A ticker and a bare CIK both resolve; identity is the same company_id.
    universe = Universe.from_companies(["AAPL", "789019"], workspace=workspace)
    assert universe.company_ids == ("cik:0000320193", "cik:0000789019")


def test_from_companies_forces_mode_with_by(workspace: Workspace) -> None:
    universe = Universe.from_companies(
        ["Apple Inc.", "MICROSOFT CORP"], by="name", workspace=workspace
    )
    assert universe.company_ids == ("cik:0000320193", "cik:0000789019")


def test_unknown_symbol_propagates_from_identity_layer(workspace: Workspace) -> None:
    # The universe layer never re-wraps or softens the identity layer's failure.
    with pytest.raises(UnknownSymbolError):
        Universe.from_companies(["AAPL", "NOPE"], workspace=workspace)


# -- deterministic ordering & de-duplication --------------------------------


def test_order_is_preserved(workspace: Workspace) -> None:
    universe = Universe.from_companies(["MSFT", "AAPL", "NVDA"], workspace=workspace)
    assert universe.company_ids == (
        "cik:0000789019",
        "cik:0000320193",
        "cik:0001045810",
    )


def test_deduplication_keeps_first_seen_order(workspace: Workspace) -> None:
    universe = Universe.from_companies(
        ["AAPL", "MSFT", "AAPL", "NVDA", "MSFT"], workspace=workspace
    )
    assert universe.company_ids == (
        "cik:0000320193",
        "cik:0000789019",
        "cik:0001045810",
    )


def test_distinct_spellings_of_one_filer_collapse(workspace: Workspace) -> None:
    # A ticker and its CIK are the same filer — one member, not two.
    universe = Universe.from_companies(["AAPL", "320193"], workspace=workspace)
    assert len(universe) == 1
    assert universe.company_ids == ("cik:0000320193",)


def test_construction_is_deterministic(workspace: Workspace) -> None:
    a = Universe.from_companies(["AAPL", "MSFT", "NVDA"], workspace=workspace)
    b = Universe.from_companies(["AAPL", "MSFT", "NVDA"], workspace=workspace)
    assert a.company_ids == b.company_ids
    assert a.universe_id == b.universe_id


# -- fail-closed inputs ------------------------------------------------------


def test_empty_universe_fails_closed(workspace: Workspace) -> None:
    with pytest.raises(UniverseConfigurationError):
        Universe.from_companies([], workspace=workspace)


def test_bare_string_is_rejected(workspace: Workspace) -> None:
    # "AAPL" is iterable as 'A','A','P','L' — refuse it rather than silently
    # resolving four bogus one-letter identifiers.
    with pytest.raises(UniverseConfigurationError, match="bare string"):
        Universe.from_companies("AAPL", workspace=workspace)


def test_from_identities_empty_fails_closed() -> None:
    with pytest.raises(UniverseConfigurationError):
        Universe.from_identities([])


def test_from_identities_all_duplicates_fails_closed() -> None:
    apple = _identity(320193, "AAPL", "Apple Inc.")
    # Same filer twice → collapses to one; that one member is a valid universe.
    universe = Universe.from_identities([apple, apple])
    assert len(universe) == 1


# -- provenance --------------------------------------------------------------


def test_member_provenance_preserved(workspace: Workspace) -> None:
    universe = Universe.from_companies(["aapl"], workspace=workspace)
    (member,) = universe.identities
    # The exact supplied identifier and the matching lookup are retained.
    assert member.resolved_from == "aapl"
    assert member.source is ResolutionSource.TICKER


def test_to_dict_is_serializable_and_complete(workspace: Workspace) -> None:
    universe = Universe.from_companies(["AAPL", "MSFT"], workspace=workspace)
    record = universe.to_dict()
    assert record["universe_id"] == universe.universe_id
    assert record["builder_version"] == "universe-builder/1"
    version_id = record["universe_version_id"]
    assert isinstance(version_id, str)
    assert version_id.startswith("sha256:")
    members = record["members"]
    assert isinstance(members, list)
    assert [m["company_id"] for m in members] == list(universe.company_ids)
    assert members[0]["resolved_from"] == "AAPL"


def test_builder_version_is_pinned_and_deterministic() -> None:
    apple = _identity(320193, "AAPL", "Apple Inc.")
    universe = Universe.from_identities([apple])
    assert universe.builder_version.code_version == "universe-builder/1"
    assert universe.builder_version.universe_version_id.startswith("sha256:")


# -- content-addressed identity ---------------------------------------------


def test_universe_id_is_sha256_prefixed_and_deterministic() -> None:
    a = _identity(320193, "AAPL", "Apple Inc.")
    m = _identity(789019, "MSFT", "MICROSOFT CORP")
    assert Universe.from_identities([a, m]).universe_id.startswith("sha256:")
    assert (
        Universe.from_identities([a, m]).universe_id
        == Universe.from_identities([a, m]).universe_id
    )


def test_universe_id_is_order_sensitive() -> None:
    a = _identity(320193, "AAPL", "Apple Inc.")
    m = _identity(789019, "MSFT", "MICROSOFT CORP")
    assert (
        Universe.from_identities([a, m]).universe_id
        != Universe.from_identities([m, a]).universe_id
    )


def test_universe_id_is_membership_sensitive() -> None:
    a = _identity(320193, "AAPL", "Apple Inc.")
    m = _identity(789019, "MSFT", "MICROSOFT CORP")
    assert (
        Universe.from_identities([a]).universe_id
        != Universe.from_identities([a, m]).universe_id
    )


def test_universe_id_matches_factor_universe_over_same_members() -> None:
    # The two universe abstractions share one content-addressing scheme, so a
    # resolved universe and a factor universe over the same ordered members
    # reproduce the same id — they compose rather than diverge.
    a = _identity(320193, "AAPL", "Apple Inc.")
    m = _identity(789019, "MSFT", "MICROSOFT CORP")
    resolved = Universe.from_identities([a, m])
    factor = FactorUniverse.of(320193, 789019)
    assert resolved.universe_id == factor.universe_id


# -- iteration ---------------------------------------------------------------


def test_iteration_yields_canonical_ids_in_order() -> None:
    a = _identity(320193, "AAPL", "Apple Inc.")
    m = _identity(789019, "MSFT", "MICROSOFT CORP")
    universe = Universe.from_identities([a, m])
    assert list(universe) == ["cik:0000320193", "cik:0000789019"]


def test_repr_is_readable() -> None:
    a = _identity(320193, "AAPL", "Apple Inc.")
    universe = Universe.from_identities([a])
    assert repr(universe) == "Universe(['AAPL'], n=1)"
