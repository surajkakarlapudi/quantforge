"""Identity + engine-version tests (§5.4, §5.6, §5.7).

Pin the content-addressing discipline: ``sha256:`` prefix, sensitivity to every folded
scalar field, result-hash sensitivity to any output cell and its key-order independence,
and the engine-version's dependence on the pinned decimal context + formula method. No
store, no wall clock, no RNG.
"""

from __future__ import annotations

from quantforge.factorportfolio.identity import (
    factor_portfolio_id,
    factor_portfolio_result_hash,
)
from quantforge.factorportfolio.version import (
    FACTORPORTFOLIO_ENGINE_VERSION,
    FACTORPORTFOLIO_FORMULA_VERSION,
    FactorPortfolioEngineVersion,
)


def _base_kwargs() -> dict[str, object]:
    return {
        "factor_portfolio_engine_version_id": "sha256:eng",
        "name": "x",
        "spec_version": "factorportfolio/1",
        "signal": "current_ratio",
        "period_key": "p1",
        "universe_specification_id": "sha256:u",
        "schedule_id": "sha256:s",
        "horizon_days": 1,
        "quantiles": 2,
        "weighting": "equal",
        "risk_free_per_period": "0",
        "periods_per_year": "1",
        "dataset_version_id": "sha256:fund",
        "market_dataset_version_id": "sha256:mkt",
        "result_hash": "sha256:rh",
    }


def test_ids_have_sha256_prefix() -> None:
    assert factor_portfolio_id(**_base_kwargs()).startswith("sha256:")  # type: ignore[arg-type]
    assert factor_portfolio_result_hash([{"block": "summary"}]).startswith("sha256:")


def test_id_is_deterministic() -> None:
    assert factor_portfolio_id(**_base_kwargs()) == factor_portfolio_id(  # type: ignore[arg-type]
        **_base_kwargs()  # type: ignore[arg-type]
    )


def test_every_scalar_field_is_folded() -> None:
    base = factor_portfolio_id(**_base_kwargs())  # type: ignore[arg-type]
    for key, value in [
        ("factor_portfolio_engine_version_id", "sha256:eng2"),
        ("name", "y"),
        ("spec_version", "factorportfolio/2"),
        ("signal", "quick_ratio"),
        ("period_key", "p2"),
        ("universe_specification_id", "sha256:u2"),
        ("schedule_id", "sha256:s2"),
        ("horizon_days", 2),
        ("quantiles", 5),
        ("weighting", "value"),
        ("risk_free_per_period", "0.01"),
        ("periods_per_year", "12"),
        ("dataset_version_id", "sha256:fund2"),
        ("market_dataset_version_id", "sha256:mkt2"),
        ("result_hash", "sha256:rh2"),
    ]:
        changed = _base_kwargs()
        changed[key] = value
        assert factor_portfolio_id(**changed) != base, key  # type: ignore[arg-type]


def test_result_hash_sensitive_to_any_cell() -> None:
    a = factor_portfolio_result_hash([{"block": "per_period", "factor_return": "1"}])
    b = factor_portfolio_result_hash([{"block": "per_period", "factor_return": "2"}])
    assert a != b


def test_result_hash_order_sensitive() -> None:
    # Two periods in either order are two distinct answers (schedule order is meaning).
    a = factor_portfolio_result_hash([{"as_of": "1"}, {"as_of": "2"}])
    b = factor_portfolio_result_hash([{"as_of": "2"}, {"as_of": "1"}])
    assert a != b


def test_result_hash_key_order_independent() -> None:
    a = factor_portfolio_result_hash([{"block": "summary", "mean": "1", "vol": "2"}])
    b = factor_portfolio_result_hash([{"vol": "2", "mean": "1", "block": "summary"}])
    assert a == b


# -- engine version ----------------------------------------------------------


def test_engine_version_defaults() -> None:
    v = FactorPortfolioEngineVersion()
    assert v.code_version == FACTORPORTFOLIO_ENGINE_VERSION
    assert v.formula_version == FACTORPORTFOLIO_FORMULA_VERSION
    assert v.factor_portfolio_engine_version_id.startswith("sha256:")
    assert v.config_hash.startswith("sha256:")


def test_engine_version_depends_on_precision() -> None:
    a = FactorPortfolioEngineVersion()
    b = FactorPortfolioEngineVersion(decimal_precision=28)
    assert a.factor_portfolio_engine_version_id != b.factor_portfolio_engine_version_id


def test_engine_version_depends_on_formula() -> None:
    a = FactorPortfolioEngineVersion()
    b = FactorPortfolioEngineVersion(formula_version="factorportfolio-stats/2")
    assert a.factor_portfolio_engine_version_id != b.factor_portfolio_engine_version_id


def test_engine_version_decimal_context_matches_pin() -> None:
    v = FactorPortfolioEngineVersion()
    ctx = v.decimal_context()
    assert ctx.prec == v.decimal_precision
