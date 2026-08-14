"""The net-of-cost engine-version id is deterministic and config-sensitive."""

from __future__ import annotations

from decimal import ROUND_HALF_DOWN, ROUND_HALF_EVEN

from quantforge.netcost.version import (
    NETCOST_METHOD_VERSION,
    NETCOST_SUMMARY_VERSION,
    NetOfCostEngineVersion,
    default_decimal_context,
)


def test_default_context() -> None:
    ctx = default_decimal_context()
    assert ctx.prec == 34
    assert ctx.rounding == ROUND_HALF_EVEN


def test_version_id_deterministic() -> None:
    a = NetOfCostEngineVersion().net_of_cost_engine_version_id
    b = NetOfCostEngineVersion().net_of_cost_engine_version_id
    assert a == b
    assert a.startswith("sha256:")


def test_summary_version_pins_phase19() -> None:
    from quantforge.factorportfolio.version import FACTORPORTFOLIO_FORMULA_VERSION

    assert NETCOST_SUMMARY_VERSION == FACTORPORTFOLIO_FORMULA_VERSION


def test_version_id_sensitive_to_each_config_axis() -> None:
    base = NetOfCostEngineVersion()
    base_id = base.net_of_cost_engine_version_id
    variants = [
        NetOfCostEngineVersion(code_version="other-code"),
        NetOfCostEngineVersion(method_version="other-method"),
        NetOfCostEngineVersion(summary_version="other-summary"),
        NetOfCostEngineVersion(decimal_precision=28),
        NetOfCostEngineVersion(decimal_rounding=ROUND_HALF_DOWN),
    ]
    ids = {v.net_of_cost_engine_version_id for v in variants}
    assert base_id not in ids
    assert len(ids) == len(variants)


def test_decimal_context_matches_version() -> None:
    v = NetOfCostEngineVersion(decimal_precision=20, decimal_rounding=ROUND_HALF_DOWN)
    ctx = v.decimal_context()
    assert ctx.prec == 20
    assert ctx.rounding == ROUND_HALF_DOWN


def test_method_version_constant() -> None:
    assert NetOfCostEngineVersion().method_version == NETCOST_METHOD_VERSION
