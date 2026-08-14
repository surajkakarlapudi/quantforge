"""The fail-closed significance vocabulary and stat cell round-trip (§9)."""

from __future__ import annotations

import pytest

from quantforge.netcostsig.model import (
    EdgeDirection,
    NetCostSigUndefinedReason,
    SignificanceStat,
    SignificanceStatus,
    StatStatus,
)


def test_known_cell_round_trips() -> None:
    cell = SignificanceStat.known("2.13")
    assert cell.status is StatStatus.KNOWN
    assert cell.to_dict() == {"status": "known", "value": "2.13"}
    assert SignificanceStat.from_dict(cell.to_dict()) == cell


def test_undefined_cell_round_trips() -> None:
    cell = SignificanceStat.undefined(NetCostSigUndefinedReason.ZERO_NET_VOLATILITY)
    assert cell.status is StatStatus.UNDEFINED
    assert cell.to_dict() == {
        "status": "undefined",
        "reason": "zero_net_volatility",
    }
    assert SignificanceStat.from_dict(cell.to_dict()) == cell


def test_known_cell_rejects_a_reason() -> None:
    with pytest.raises(ValueError):
        SignificanceStat(
            status=StatStatus.KNOWN,
            value="1",
            reason=NetCostSigUndefinedReason.SOURCE_NOT_MEASURED,
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


def test_closed_vocabularies() -> None:
    # The closed status / reason / direction vocabularies are exactly as declared.
    assert {s.value for s in SignificanceStatus} == {"tested", "undefined"}
    assert {r.value for r in NetCostSigUndefinedReason} == {
        "source_not_measured",
        "zero_net_volatility",
    }
    assert {d.value for d in EdgeDirection} == {
        "profitable",
        "unprofitable",
        "flat",
    }
