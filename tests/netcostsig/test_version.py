"""The engine version pins code + method + normal + decimal context (§13)."""

from __future__ import annotations

from quantforge.netcostsig.version import (
    NETCOSTSIG_ENGINE_VERSION,
    NETCOSTSIG_METHOD_VERSION,
    NETCOSTSIG_NORMAL_VERSION,
    NetOfCostSignificanceEngineVersion,
    default_decimal_context,
)


def test_default_context_is_prec_34_half_even() -> None:
    ctx = default_decimal_context()
    assert ctx.prec == 34
    # A fresh instance each call, never a shared mutable context.
    assert default_decimal_context() is not ctx


def test_version_id_is_deterministic_and_sha256() -> None:
    base = NetOfCostSignificanceEngineVersion()
    other = NetOfCostSignificanceEngineVersion()
    assert (
        base.net_of_cost_significance_engine_version_id
        == other.net_of_cost_significance_engine_version_id
    )
    assert base.net_of_cost_significance_engine_version_id.startswith("sha256:")
    assert base.config_hash.startswith("sha256:")


def test_defaults_match_module_constants() -> None:
    base = NetOfCostSignificanceEngineVersion()
    assert base.code_version == NETCOSTSIG_ENGINE_VERSION
    assert base.method_version == NETCOSTSIG_METHOD_VERSION
    assert base.normal_version == NETCOSTSIG_NORMAL_VERSION


def test_version_id_folds_every_component() -> None:
    base = NetOfCostSignificanceEngineVersion()
    base_id = base.net_of_cost_significance_engine_version_id
    assert (
        NetOfCostSignificanceEngineVersion(
            code_version="netcostsig-engine/2"
        ).net_of_cost_significance_engine_version_id
        != base_id
    )
    assert (
        NetOfCostSignificanceEngineVersion(
            method_version="netcostsig-method/2"
        ).net_of_cost_significance_engine_version_id
        != base_id
    )
    assert (
        NetOfCostSignificanceEngineVersion(
            normal_version="netcostsig-normal/2"
        ).net_of_cost_significance_engine_version_id
        != base_id
    )
    assert (
        NetOfCostSignificanceEngineVersion(
            decimal_precision=28
        ).net_of_cost_significance_engine_version_id
        != base_id
    )
