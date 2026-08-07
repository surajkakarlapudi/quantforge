"""Tests for the pure cross-sectional transforms (``docs/factors.md`` §6.2).

Rank/zscore/minmax/winsorize are pure, deterministic functions of the KNOWN-cell
population under the Phase 7 pinned decimal context. Covers: exactness; tie-order
by ``company_id``; degenerate populations fail closed to all-``None`` (never a
division blow-up); an empty (all-``UNDEFINED``) population yields all-``None``;
``winsorize`` bound validation; ``transform_id`` stability.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from openfinance.factors.errors import FactorConfigurationError
from openfinance.factors.transform import Transform, TransformKind
from openfinance.metrics.version import MetricEngineVersion

CTX = MetricEngineVersion().decimal_context()


def _pop(**kwargs: str) -> dict[str, Decimal]:
    return {member: Decimal(value) for member, value in kwargs.items()}


class TestNone:
    def test_identity_yields_all_none(self) -> None:
        out = Transform.none().apply(_pop(a="1", b="2"), CTX)
        assert out == {"a": None, "b": None}

    def test_transform_id(self) -> None:
        assert Transform.none().transform_id == "none"


class TestRank:
    def test_ordinal_ascending_by_value(self) -> None:
        out = Transform.rank().apply(_pop(a="10", b="20", c="5"), CTX)
        assert out == {"a": "2", "b": "3", "c": "1"}

    def test_ties_break_by_company_id(self) -> None:
        # Equal values: the lexicographically smaller company_id ranks first.
        out = Transform.rank().apply(_pop(b="5", a="5"), CTX)
        assert out == {"a": "1", "b": "2"}

    def test_is_a_total_order(self) -> None:
        out = Transform.rank().apply(_pop(a="5", b="5", c="5"), CTX)
        assert sorted(v for v in out.values() if v is not None) == ["1", "2", "3"]


class TestZscore:
    def test_symmetric_population(self) -> None:
        out = Transform.zscore().apply(_pop(a="1", b="2", c="3"), CTX)
        # The mean cell is exactly 0; the tails straddle it (below/above).
        assert out["b"] == "0"
        low, high = out["a"], out["c"]
        assert low is not None and high is not None
        assert Decimal(low) < 0 < Decimal(high)

    def test_zero_stdev_fails_closed(self) -> None:
        out = Transform.zscore().apply(_pop(a="7", b="7"), CTX)
        assert out == {"a": None, "b": None}

    def test_single_cell_fails_closed(self) -> None:
        # A single cell has zero stdev → undefined, never a division blow-up.
        out = Transform.zscore().apply(_pop(a="7"), CTX)
        assert out == {"a": None}

    def test_single_high_precision_cell_fails_closed(self) -> None:
        # Regression: a single value with more digits than the ambient thread
        # context (precision 28) must still fail closed. The transform must run
        # under the PINNED context (precision 34) — otherwise the bare mean rounds
        # to 28 digits, leaves a nonzero residual, and slips past the zero-stdev
        # guard to emit a spurious z-score (§6.2).
        out = Transform.zscore().apply(
            _pop(a="2.024912390270982963811109954547032"), CTX
        )
        assert out == {"a": None}


class TestMinMax:
    def test_scales_to_unit_interval(self) -> None:
        out = Transform.minmax().apply(_pop(a="0", b="5", c="10"), CTX)
        assert out == {"a": "0", "b": "0.5", "c": "1"}

    def test_zero_range_fails_closed(self) -> None:
        out = Transform.minmax().apply(_pop(a="4", b="4"), CTX)
        assert out == {"a": None, "b": None}

    def test_single_high_precision_cell_fails_closed(self) -> None:
        # Regression companion to the z-score case: one 34-digit value has zero
        # range and must fail closed under the pinned context, not slip through.
        out = Transform.minmax().apply(
            _pop(a="2.024912390270982963811109954547032"), CTX
        )
        assert out == {"a": None}


class TestWinsorize:
    def test_clips_to_percentile_bounds(self) -> None:
        # Values 1..5; winsorize at the 25th/75th percentile bounds (2..4).
        out = Transform.winsorize("0.25", "0.75").apply(
            _pop(a="1", b="2", c="3", d="4", e="5"), CTX
        )
        assert out["a"] == "2"  # clipped up to the lower bound
        assert out["c"] == "3"  # inside, unchanged
        assert out["e"] == "4"  # clipped down to the upper bound

    def test_bounds_validation(self) -> None:
        with pytest.raises(FactorConfigurationError):
            Transform.winsorize("0.75", "0.25")  # lower > upper
        with pytest.raises(FactorConfigurationError):
            Transform.winsorize("-0.1", "0.9")  # out of [0, 1]

    def test_transform_id_serializes_bounds(self) -> None:
        assert Transform.winsorize("0.05", "0.95").transform_id == "winsorize:0.05:0.95"


class TestEmptyPopulation:
    @pytest.mark.parametrize(
        "transform",
        [
            Transform.rank(),
            Transform.zscore(),
            Transform.minmax(),
            Transform.winsorize("0.1", "0.9"),
        ],
    )
    def test_all_undefined_population_yields_empty_map(
        self, transform: Transform
    ) -> None:
        # No KNOWN cells → nothing to transform, never an exception.
        assert transform.apply({}, CTX) == {}


class TestDeterminism:
    def test_same_population_same_output(self) -> None:
        pop = _pop(a="1", b="2", c="3")
        assert Transform.zscore().apply(pop, CTX) == Transform.zscore().apply(pop, CTX)

    def test_transform_kind_round_trips_via_id(self) -> None:
        for kind in (TransformKind.RANK, TransformKind.ZSCORE, TransformKind.MINMAX):
            assert Transform(kind).transform_id == kind.value
