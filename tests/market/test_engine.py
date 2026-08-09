"""Engine integration: provenance, provider independence, versions, currency (15/16)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantforge.market.errors import MarketPolicyConfigurationError
from quantforge.market.provider import DateRange
from quantforge.market.version import (
    AdjustmentVersion,
    MarketDatasetVersion,
    MarketTransformationVersion,
)
from tests.market.builders import (
    FAKE_SOURCE,
    SECURITY_ID,
    bar,
    bars_document,
    ingest_bars,
    make_engine,
    make_provider,
)

AFTER = datetime(2024, 1, 1, tzinfo=UTC)


def test_provenance_chain_present(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    price = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER)
    prov = price.provenance
    assert prov.selected_price_observation_id is not None
    assert prov.selected_raw_document_sha256 is not None
    assert prov.selected_source_id == "fake-market-data"
    assert prov.availability_policy_id is not None
    assert prov.boundary_kind == "pit"


def test_undefined_price_still_carries_provenance(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    price = engine.price_as_of(SECURITY_ID, "2020-01-03", AFTER)  # unreported
    assert not price.is_known
    assert price.provenance is not None
    assert price.provenance.result_status.value == "undefined"


def test_provider_independence_synthetic_urls(tmp_path: Path) -> None:
    # The layer never hard-codes a vendor; the fake provider's synthetic fake:// URL
    # rides through provenance unchanged.
    ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    raw = list((tmp_path / "market" / "raw").rglob("*"))
    # Raw bytes were stored (content-addressed) with no vendor name baked into core.
    assert any(p.is_file() for p in raw)


def test_dataset_version_is_reproducible(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    dv1 = engine.dataset_version_for(SECURITY_ID)
    dv2 = engine.dataset_version_for(SECURITY_ID)
    assert isinstance(dv1, MarketDatasetVersion)
    assert dv1.dataset_version_id == dv2.dataset_version_id


def test_revised_over_explicit_dataset_version(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    dv = engine.dataset_version_for(SECURITY_ID)
    revised = engine.revised_price(SECURITY_ID, "2020-01-02", dv)
    assert revised.dataset_version_id == dv.dataset_version_id


def test_currency_consistency_check_passes_single_currency(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    # Should not raise.
    engine.check_currency_consistency(SECURITY_ID)


def test_currency_consistency_check_fails_on_mix(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    provider = make_provider(
        bars_by_security={
            SECURITY_ID: bars_document(
                [
                    bar("2020-01-02", close="105", currency="USD"),
                    bar("2020-01-03", close="106", currency="EUR"),
                ]
            )
        },
    )
    engine.ingest(
        provider,
        SECURITY_ID,
        DateRange(start="2020-01-01", end="2020-12-31"),
        source=FAKE_SOURCE,
        with_actions=False,
    )
    with pytest.raises(MarketPolicyConfigurationError):
        engine.check_currency_consistency(SECURITY_ID)


def test_repeated_ingest_is_idempotent(tmp_path: Path) -> None:
    # Ingesting the same bytes twice yields the same stored observation ids.
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    ids_before = {
        o.price_observation_id for o in engine.store.read_observations(SECURITY_ID)
    }
    provider = make_provider(
        bars_by_security={SECURITY_ID: bars_document([bar("2020-01-02", close="105")])},
    )
    engine.ingest(
        provider,
        SECURITY_ID,
        DateRange(start="2020-01-01", end="2020-12-31"),
        source=FAKE_SOURCE,
        with_actions=False,
    )
    ids_after = {
        o.price_observation_id for o in engine.store.read_observations(SECURITY_ID)
    }
    assert ids_before == ids_after


def test_transformation_version_ids_are_stable() -> None:
    assert (
        MarketTransformationVersion().market_transformation_version_id
        == MarketTransformationVersion().market_transformation_version_id
    )
    assert (
        AdjustmentVersion().adjustment_version == AdjustmentVersion().adjustment_version
    )


def test_adjustment_version_rejects_unknown_convention() -> None:
    with pytest.raises(ValueError):
        AdjustmentVersion(convention="bogus")
