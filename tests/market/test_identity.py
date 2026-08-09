"""Instrument identity and content-addressed id determinism (section 14, D2/D8)."""

from __future__ import annotations

import pytest

from quantforge.market.identity import (
    adjusted_series_id,
    company_id_of_security_id,
    corporate_action_id,
    normalize_security_class,
    price_obs_key,
    price_observation_id,
    security_id,
)


def test_security_id_cik_form_is_stable_and_ticker_free() -> None:
    sid = security_id(cik="9999999999", security_class="Common Stock")
    assert sid == "cik:9999999999#class:common-stock"
    # A ticker is never a component of identity.
    assert "ZZZZ" not in sid


def test_security_id_pads_cik() -> None:
    assert security_id(cik=1, security_class="common") == "cik:0000000001#class:common"


def test_security_id_figi_form() -> None:
    assert security_id(figi="BBG000B9XRY4") == "figi:BBG000B9XRY4"


def test_security_id_requires_exactly_one_form() -> None:
    with pytest.raises(ValueError):
        security_id(figi="X", cik="1", security_class="common")
    with pytest.raises(ValueError):
        security_id(cik="1")  # missing class
    with pytest.raises(ValueError):
        security_id()  # nothing


def test_normalize_security_class_folds_whitespace_and_case() -> None:
    assert normalize_security_class(" common  STOCK ") == "common-stock"


def test_normalize_security_class_rejects_empty() -> None:
    with pytest.raises(ValueError):
        normalize_security_class("   ")


def test_normalize_security_class_rejects_reserved_char() -> None:
    with pytest.raises(ValueError):
        normalize_security_class("class#a")


def test_company_id_recovered_from_cik_form() -> None:
    sid = "cik:9999999999#class:common-stock"
    assert company_id_of_security_id(sid) == "cik:9999999999"


def test_company_id_none_for_figi_form() -> None:
    assert company_id_of_security_id("figi:BBG000B9XRY4") is None


def test_price_observation_id_is_deterministic() -> None:
    kwargs = dict(
        market_transformation_version_id="tv1",
        security_id="cik:9999999999#class:common-stock",
        trading_date="2020-01-02",
        currency="USD",
        field="close",
        value="105",
    )
    first = price_observation_id(**kwargs)
    assert first == price_observation_id(**kwargs)
    assert first.startswith("sha256:")


def test_price_observation_id_changes_with_value() -> None:
    base = dict(
        market_transformation_version_id="tv1",
        security_id="s",
        trading_date="2020-01-02",
        currency="USD",
        field="close",
    )
    assert price_observation_id(value="105", **base) != price_observation_id(
        value="106", **base
    )


def test_price_obs_key_is_per_field() -> None:
    close = price_obs_key(security_id="s", trading_date="2020-01-02", field="close")
    open_ = price_obs_key(security_id="s", trading_date="2020-01-02", field="open")
    assert close != open_


def test_corporate_action_id_deterministic_over_payload() -> None:
    def _make() -> str:
        return corporate_action_id(
            market_transformation_version_id="tv1",
            security_id="s",
            action_kind="split",
            ex_date="2020-06-01",
            payload={"ratio": "2"},
        )

    assert _make() == _make()


def test_adjusted_series_id_order_sensitive_and_deterministic() -> None:
    base = dict(
        adjustment_version="adj1",
        security_id="s",
        boundary_key="pit:2024-01-01T00:00:00Z",
    )
    a = adjusted_series_id(unadjusted_obs_ids=["o1", "o2"], action_ids=["x1"], **base)
    b = adjusted_series_id(unadjusted_obs_ids=["o2", "o1"], action_ids=["x1"], **base)
    # Series date order is load-bearing: reordering obs ids yields a different id.
    assert a != b
    # But identical inputs reproduce the id.
    assert a == adjusted_series_id(
        unadjusted_obs_ids=["o1", "o2"], action_ids=["x1"], **base
    )
