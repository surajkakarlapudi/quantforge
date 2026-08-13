"""The MinTRL vocabulary + the UNDEFINED-preserving stat cell (MT-3)."""

from __future__ import annotations

import pytest

from quantforge.mintrl.model import (
    MinTrlExcludedReason,
    MinTrlStat,
    MinTrlStatus,
    MinTrlUndefinedReason,
    StatStatus,
)


def test_known_cell_carries_value_only() -> None:
    cell = MinTrlStat.known("12.5")
    assert cell.status is StatStatus.KNOWN
    assert cell.value == "12.5"
    assert cell.reason is None
    assert cell.to_dict() == {"status": "known", "value": "12.5"}


def test_undefined_cell_carries_reason_only() -> None:
    cell = MinTrlStat.undefined(MinTrlUndefinedReason.SHARPE_NOT_ABOVE_BENCHMARK)
    assert cell.status is StatStatus.UNDEFINED
    assert cell.value is None
    assert cell.to_dict() == {
        "status": "undefined",
        "reason": "sharpe_not_above_benchmark",
    }


def test_known_cell_rejects_missing_value() -> None:
    with pytest.raises(ValueError):
        MinTrlStat(status=StatStatus.KNOWN, value=None)


def test_undefined_cell_rejects_a_value() -> None:
    with pytest.raises(ValueError):
        MinTrlStat(
            status=StatStatus.UNDEFINED,
            value="1.0",
            reason=MinTrlUndefinedReason.NO_DETERMINED_TRIALS,
        )


def test_stat_round_trips_through_from_dict() -> None:
    for cell in (
        MinTrlStat.known("0.5"),
        MinTrlStat.undefined(MinTrlUndefinedReason.DEGENERATE_SHARPE_ESTIMATOR),
    ):
        assert MinTrlStat.from_dict(cell.to_dict()) == cell


def test_from_dict_rejects_corrupt_cells() -> None:
    with pytest.raises(ValueError):
        MinTrlStat.from_dict({"status": "bogus"})
    with pytest.raises(ValueError):
        MinTrlStat.from_dict({"status": "known"})  # no value
    with pytest.raises(ValueError):
        MinTrlStat.from_dict({"status": "undefined", "reason": "not_a_reason"})


def test_status_and_reason_vocabularies_are_closed() -> None:
    assert {s.value for s in MinTrlStatus} == {"evaluated", "undefined"}
    assert {r.value for r in MinTrlExcludedReason} == {
        "trial_undefined",
        "moments_undefined",
    }
    assert {r.value for r in MinTrlUndefinedReason} == {
        "sharpe_not_above_benchmark",
        "degenerate_sharpe_estimator",
        "no_determined_trials",
        "insufficient_determined_trials",
    }
