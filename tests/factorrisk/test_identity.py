"""Identity + engine-version tests (§10).

Pin the content-addressing discipline: ``sha256:`` prefix, sensitivity to every folded
field (including the ordered factor id / result-hash lists), result-hash sensitivity to
any output cell and its key-order independence, and the engine-version's dependence on
the pinned decimal context + formula method. No store, no wall clock, no RNG.
"""

from __future__ import annotations

from quantforge.factorrisk.identity import (
    factor_risk_id,
    factor_risk_result_hash,
)
from quantforge.factorrisk.version import (
    FACTORRISK_ENGINE_VERSION,
    FACTORRISK_FORMULA_VERSION,
    FactorRiskEngineVersion,
)


def _base_kwargs() -> dict[str, object]:
    return {
        "factor_risk_engine_version_id": "sha256:eng",
        "name": "x",
        "spec_version": "factorrisk/1",
        "factor_portfolio_ids": ["sha256:a", "sha256:b"],
        "periods_per_year": "1",
        "factor_result_hashes": ["sha256:rh-a", "sha256:rh-b"],
        "result_hash": "sha256:rh",
    }


def test_ids_have_sha256_prefix() -> None:
    assert factor_risk_id(**_base_kwargs()).startswith("sha256:")  # type: ignore[arg-type]
    assert factor_risk_result_hash([{"block": "factor"}]).startswith("sha256:")


def test_id_is_deterministic() -> None:
    assert factor_risk_id(**_base_kwargs()) == factor_risk_id(  # type: ignore[arg-type]
        **_base_kwargs()  # type: ignore[arg-type]
    )


def test_every_field_is_folded() -> None:
    base = factor_risk_id(**_base_kwargs())  # type: ignore[arg-type]
    for key, value in [
        ("factor_risk_engine_version_id", "sha256:eng2"),
        ("name", "y"),
        ("spec_version", "factorrisk/2"),
        ("factor_portfolio_ids", ["sha256:a", "sha256:c"]),
        ("periods_per_year", "12"),
        ("factor_result_hashes", ["sha256:rh-a", "sha256:rh-c"]),
        ("result_hash", "sha256:rh2"),
    ]:
        changed = _base_kwargs()
        changed[key] = value
        assert factor_risk_id(**changed) != base, key  # type: ignore[arg-type]


def test_factor_order_is_semantic() -> None:
    # Reversing the factor order (and the matching result-hash order) is a distinct
    # request - order fixes the matrix row/column order.
    a = factor_risk_id(**_base_kwargs())  # type: ignore[arg-type]
    reversed_kwargs = _base_kwargs()
    reversed_kwargs["factor_portfolio_ids"] = ["sha256:b", "sha256:a"]
    reversed_kwargs["factor_result_hashes"] = ["sha256:rh-b", "sha256:rh-a"]
    assert factor_risk_id(**reversed_kwargs) != a  # type: ignore[arg-type]


def test_result_hash_sensitive_to_any_cell() -> None:
    a = factor_risk_result_hash([{"block": "cov", "value": "1"}])
    b = factor_risk_result_hash([{"block": "cov", "value": "2"}])
    assert a != b


def test_result_hash_order_sensitive() -> None:
    a = factor_risk_result_hash([{"i": 0}, {"i": 1}])
    b = factor_risk_result_hash([{"i": 1}, {"i": 0}])
    assert a != b


def test_result_hash_key_order_independent() -> None:
    a = factor_risk_result_hash([{"block": "factor", "mean": "1", "vol": "2"}])
    b = factor_risk_result_hash([{"vol": "2", "mean": "1", "block": "factor"}])
    assert a == b


# -- engine version ----------------------------------------------------------


def test_engine_version_defaults() -> None:
    v = FactorRiskEngineVersion()
    assert v.code_version == FACTORRISK_ENGINE_VERSION
    assert v.formula_version == FACTORRISK_FORMULA_VERSION
    assert v.factor_risk_engine_version_id.startswith("sha256:")
    assert v.config_hash.startswith("sha256:")


def test_engine_version_depends_on_precision() -> None:
    a = FactorRiskEngineVersion()
    b = FactorRiskEngineVersion(decimal_precision=28)
    assert a.factor_risk_engine_version_id != b.factor_risk_engine_version_id


def test_engine_version_depends_on_formula() -> None:
    a = FactorRiskEngineVersion()
    b = FactorRiskEngineVersion(formula_version="factorrisk-stats/2")
    assert a.factor_risk_engine_version_id != b.factor_risk_engine_version_id


def test_engine_version_decimal_context_matches_pin() -> None:
    v = FactorRiskEngineVersion()
    ctx = v.decimal_context()
    assert ctx.prec == v.decimal_precision
