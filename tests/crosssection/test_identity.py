"""Identity + engine-version tests (§5).

Pin the content-addressing discipline: ``sha256:`` prefix, order-sensitive factor
descriptors, sensitivity to every folded field, and the engine-version's dependence on
the pinned decimal context + formula method. No store, no wall clock, no RNG.
"""

from __future__ import annotations

from quantforge.crosssection.identity import (
    crosssection_id,
    crosssection_result_hash,
)
from quantforge.crosssection.version import (
    CROSSSECTION_ENGINE_VERSION,
    CROSSSECTION_FORMULA_VERSION,
    CrossSectionEngineVersion,
)


def _base_kwargs() -> dict[str, object]:
    return {
        "crosssection_engine_version_id": "sha256:eng",
        "name": "x",
        "spec_version": "crosssection/1",
        "factor_descriptors": [["current_ratio", "p1"], ["quick_ratio", "p1"]],
        "universe_specification_id": "sha256:u",
        "schedule_id": "sha256:s",
        "horizon_days": 1,
        "include_intercept": True,
        "dataset_version_id": "sha256:fund",
        "market_dataset_version_id": "sha256:mkt",
        "result_hash": "sha256:rh",
    }


def test_ids_have_sha256_prefix() -> None:
    assert crosssection_id(**_base_kwargs()).startswith("sha256:")  # type: ignore[arg-type]
    assert crosssection_result_hash([{"block": "premium"}]).startswith("sha256:")


def test_id_is_deterministic() -> None:
    assert crosssection_id(**_base_kwargs()) == crosssection_id(**_base_kwargs())  # type: ignore[arg-type]


def test_factor_order_changes_id() -> None:
    base = crosssection_id(**_base_kwargs())  # type: ignore[arg-type]
    swapped = _base_kwargs()
    swapped["factor_descriptors"] = [["quick_ratio", "p1"], ["current_ratio", "p1"]]
    assert crosssection_id(**swapped) != base  # type: ignore[arg-type]


def test_intercept_flag_changes_id() -> None:
    base = crosssection_id(**_base_kwargs())  # type: ignore[arg-type]
    off = _base_kwargs()
    off["include_intercept"] = False
    assert crosssection_id(**off) != base  # type: ignore[arg-type]


def test_every_scalar_field_is_folded() -> None:
    base = crosssection_id(**_base_kwargs())  # type: ignore[arg-type]
    for key, value in [
        ("name", "y"),
        ("spec_version", "crosssection/2"),
        ("universe_specification_id", "sha256:u2"),
        ("schedule_id", "sha256:s2"),
        ("horizon_days", 2),
        ("dataset_version_id", "sha256:fund2"),
        ("market_dataset_version_id", "sha256:mkt2"),
        ("result_hash", "sha256:rh2"),
        ("crosssection_engine_version_id", "sha256:eng2"),
    ]:
        changed = _base_kwargs()
        changed[key] = value
        assert crosssection_id(**changed) != base, key  # type: ignore[arg-type]


def test_result_hash_sensitive_to_any_cell() -> None:
    a = crosssection_result_hash([{"block": "premium", "mean": {"value": "1"}}])
    b = crosssection_result_hash([{"block": "premium", "mean": {"value": "2"}}])
    assert a != b


def test_result_hash_key_order_independent() -> None:
    a = crosssection_result_hash([{"block": "premium", "mean": "1", "t": "2"}])
    b = crosssection_result_hash([{"t": "2", "mean": "1", "block": "premium"}])
    assert a == b


# -- engine version ----------------------------------------------------------


def test_engine_version_defaults() -> None:
    v = CrossSectionEngineVersion()
    assert v.code_version == CROSSSECTION_ENGINE_VERSION
    assert v.formula_version == CROSSSECTION_FORMULA_VERSION
    assert v.crosssection_engine_version_id.startswith("sha256:")


def test_engine_version_depends_on_precision() -> None:
    a = CrossSectionEngineVersion()
    b = CrossSectionEngineVersion(decimal_precision=28)
    assert a.crosssection_engine_version_id != b.crosssection_engine_version_id


def test_engine_version_depends_on_formula() -> None:
    a = CrossSectionEngineVersion()
    b = CrossSectionEngineVersion(formula_version="crosssection-stats/2")
    assert a.crosssection_engine_version_id != b.crosssection_engine_version_id


def test_engine_version_decimal_context_matches_pin() -> None:
    v = CrossSectionEngineVersion()
    ctx = v.decimal_context()
    assert ctx.prec == v.decimal_precision
