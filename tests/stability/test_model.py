"""The stability vocabulary: fail-closed StabilityStat cell round-trips (§9, WS-3)."""

from __future__ import annotations

import pytest

from quantforge.stability.model import (
    StabilityStat,
    StabilityUndefinedReason,
    StatStatus,
)


def test_known_cell_round_trips() -> None:
    cell = StabilityStat.known("0.75")
    assert cell.status is StatStatus.KNOWN
    assert cell.to_dict() == {"status": "known", "value": "0.75"}
    assert StabilityStat.from_dict(cell.to_dict()) == cell


def test_undefined_cell_round_trips() -> None:
    cell = StabilityStat.undefined(StabilityUndefinedReason.NO_TRANSITIONS)
    assert cell.status is StatStatus.UNDEFINED
    assert cell.to_dict() == {"status": "undefined", "reason": "no_transitions"}
    assert StabilityStat.from_dict(cell.to_dict()) == cell


def test_known_cell_rejects_reason() -> None:
    with pytest.raises(ValueError):
        StabilityStat(
            status=StatStatus.KNOWN,
            value="1",
            reason=StabilityUndefinedReason.NO_TRANSITIONS,
        )


def test_undefined_cell_rejects_value() -> None:
    with pytest.raises(ValueError):
        StabilityStat(status=StatStatus.UNDEFINED, value="1")


def test_from_dict_rejects_unknown_status() -> None:
    with pytest.raises(ValueError):
        StabilityStat.from_dict({"status": "maybe", "value": "1"})


def test_from_dict_rejects_unknown_reason() -> None:
    with pytest.raises(ValueError):
        StabilityStat.from_dict({"status": "undefined", "reason": "not-a-reason"})


def test_from_dict_rejects_non_string_value() -> None:
    with pytest.raises(ValueError):
        StabilityStat.from_dict({"status": "known", "value": 1})
