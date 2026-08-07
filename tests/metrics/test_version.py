"""Tests for the metric-engine version identity (metrics.md §8, §16, Decision D5).

The engine version is content-addressed over ``code_version`` + the decimal
context (precision + rounding). Two properties are load-bearing: the id is
deterministic for a fixed config, and it is *sensitive* to the decimal context —
so a metric computed under precision 34 can never be confused with one computed
under a different context (invariant-20 analogue).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Context

from quantforge.metrics.version import (
    METRIC_ENGINE_VERSION,
    MetricEngineVersion,
    default_decimal_context,
)


def test_default_context_is_prec34_half_even() -> None:
    ctx = default_decimal_context()
    assert ctx.prec == 34
    from decimal import ROUND_HALF_EVEN

    assert ctx.rounding == ROUND_HALF_EVEN


def test_default_context_is_a_fresh_copy() -> None:
    # Mutating one copy must never perturb another (determinism, §16).
    a = default_decimal_context()
    b = default_decimal_context()
    a.prec = 7
    assert b.prec == 34


def test_version_id_is_deterministic() -> None:
    assert (
        MetricEngineVersion().metric_engine_version_id
        == MetricEngineVersion().metric_engine_version_id
    )


def test_version_id_is_sha256_prefixed() -> None:
    v = MetricEngineVersion()
    assert v.metric_engine_version_id.startswith("sha256:")
    assert v.config_hash.startswith("sha256:")


def test_version_id_changes_with_precision() -> None:
    a = MetricEngineVersion()
    b = MetricEngineVersion(decimal_precision=28)
    assert a.metric_engine_version_id != b.metric_engine_version_id


def test_version_id_changes_with_rounding() -> None:
    a = MetricEngineVersion()
    b = MetricEngineVersion(decimal_rounding=ROUND_HALF_UP)
    assert a.metric_engine_version_id != b.metric_engine_version_id


def test_version_id_changes_with_code_version() -> None:
    a = MetricEngineVersion()
    b = MetricEngineVersion(code_version="metric-engine/2")
    assert a.metric_engine_version_id != b.metric_engine_version_id


def test_default_code_version_is_pinned() -> None:
    assert MetricEngineVersion().code_version == METRIC_ENGINE_VERSION


def test_decimal_context_matches_declared_fields() -> None:
    v = MetricEngineVersion(decimal_precision=20, decimal_rounding=ROUND_HALF_UP)
    ctx = v.decimal_context()
    assert isinstance(ctx, Context)
    assert ctx.prec == 20
    assert ctx.rounding == ROUND_HALF_UP
