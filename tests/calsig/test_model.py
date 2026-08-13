"""The fail-closed significance vocabulary and stat cell round-trip (§9)."""

from __future__ import annotations

import pytest

from quantforge.calsig.model import (
    SignificanceStat,
    SignificanceUndefinedReason,
    StatStatus,
)


def test_known_cell_round_trips() -> None:
    cell = SignificanceStat.known("2.13")
    assert cell.status is StatStatus.KNOWN
    assert cell.to_dict() == {"status": "known", "value": "2.13"}
    assert SignificanceStat.from_dict(cell.to_dict()) == cell


def test_undefined_cell_round_trips() -> None:
    cell = SignificanceStat.undefined(SignificanceUndefinedReason.ZERO_RATIO_DISPERSION)
    assert cell.status is StatStatus.UNDEFINED
    assert cell.to_dict() == {
        "status": "undefined",
        "reason": "zero_ratio_dispersion",
    }
    assert SignificanceStat.from_dict(cell.to_dict()) == cell


def test_known_cell_rejects_a_reason() -> None:
    with pytest.raises(ValueError):
        SignificanceStat(
            status=StatStatus.KNOWN,
            value="1",
            reason=SignificanceUndefinedReason.SOURCE_NOT_CALIBRATED,
        )


def test_undefined_cell_requires_a_reason() -> None:
    with pytest.raises(ValueError):
        SignificanceStat(status=StatStatus.UNDEFINED)


def test_from_dict_rejects_unknown_status() -> None:
    with pytest.raises(ValueError):
        SignificanceStat.from_dict({"status": "bogus"})


def test_from_dict_rejects_unknown_reason() -> None:
    with pytest.raises(ValueError):
        SignificanceStat.from_dict({"status": "undefined", "reason": "bogus"})
