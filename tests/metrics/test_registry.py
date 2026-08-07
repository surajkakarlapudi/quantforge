"""Tests for the built-in formula registry (metrics.md §6.5, Decision D6).

The registry ships the eight approved starter formulas, is fail-closed on an
unknown ``metric_key`` (never a guessed formula), rejects a duplicate-key
construction, and enumerates deterministically. Formula ids are stable across
calls (content-addressed, no shared mutable state).
"""

from __future__ import annotations

import pytest

from openfinance.metrics.errors import FormulaConfigurationError
from openfinance.metrics.formula import FormulaDefinition
from openfinance.metrics.registry import FormulaRegistry, builtin_formulas

_EXPECTED_KEYS = (
    "asset_turnover",
    "current_ratio",
    "debt_to_equity",
    "gross_margin",
    "net_margin",
    "operating_margin",
    "quick_ratio",
    "working_capital",
)


def test_ships_exactly_the_eight_approved_metrics() -> None:
    assert FormulaRegistry().metric_keys() == _EXPECTED_KEYS


def test_get_returns_matching_formula() -> None:
    f = FormulaRegistry().get("current_ratio")
    assert isinstance(f, FormulaDefinition)
    assert f.metric_key == "current_ratio"


def test_unknown_key_fails_closed() -> None:
    with pytest.raises(FormulaConfigurationError, match="unknown metric_key"):
        FormulaRegistry().get("ebitda_margin")


def test_has_reports_membership() -> None:
    reg = FormulaRegistry()
    assert reg.has("net_margin")
    assert not reg.has("nope")


def test_metric_keys_are_sorted() -> None:
    keys = FormulaRegistry().metric_keys()
    assert list(keys) == sorted(keys)


def test_formulas_ordered_by_key() -> None:
    reg = FormulaRegistry()
    assert tuple(f.metric_key for f in reg.formulas()) == reg.metric_keys()


def test_builtin_formula_ids_stable_across_calls() -> None:
    a = {f.metric_key: f.formula_id for f in builtin_formulas()}
    b = {f.metric_key: f.formula_id for f in builtin_formulas()}
    assert a == b


def test_duplicate_key_construction_rejected() -> None:
    dup = builtin_formulas()[0]
    with pytest.raises(FormulaConfigurationError, match="duplicate metric_key"):
        FormulaRegistry((dup, dup))


def test_custom_formula_set_is_accepted() -> None:
    one = builtin_formulas()[0]
    reg = FormulaRegistry((one,))
    assert reg.metric_keys() == (one.metric_key,)


def test_all_builtins_construct_without_guard_error() -> None:
    # Construction runs every __post_init__ consistency check (§6).
    assert len(builtin_formulas()) == 8
