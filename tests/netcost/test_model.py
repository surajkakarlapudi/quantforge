"""The UNDEFINED-preserving net-of-cost stat cell and its fail-closed serialization."""

from __future__ import annotations

import pytest

from quantforge.netcost.model import (
    NetCostExcludedReason,
    NetCostStat,
    NetCostStatus,
    NetCostUndefinedReason,
    StatStatus,
)


def test_known_round_trip() -> None:
    cell = NetCostStat.known("0.041")
    assert cell.status is StatStatus.KNOWN
    assert cell.value == "0.041"
    assert cell.reason is None
    assert cell.to_dict() == {"status": "known", "value": "0.041"}
    assert NetCostStat.from_dict(cell.to_dict()) == cell


def test_undefined_round_trip() -> None:
    cell = NetCostStat.undefined(NetCostUndefinedReason.DEGENERATE_NO_TURNOVER)
    assert cell.status is StatStatus.UNDEFINED
    assert cell.value is None
    assert cell.reason is NetCostUndefinedReason.DEGENERATE_NO_TURNOVER
    assert cell.to_dict() == {"status": "undefined", "reason": "degenerate_no_turnover"}
    assert NetCostStat.from_dict(cell.to_dict()) == cell


def test_known_without_value_rejected() -> None:
    with pytest.raises(ValueError):
        NetCostStat(status=StatStatus.KNOWN)


def test_known_with_reason_rejected() -> None:
    with pytest.raises(ValueError):
        NetCostStat(
            status=StatStatus.KNOWN,
            value="1",
            reason=NetCostUndefinedReason.NO_VALID_PERIODS,
        )


def test_undefined_without_reason_rejected() -> None:
    with pytest.raises(ValueError):
        NetCostStat(status=StatStatus.UNDEFINED)


def test_undefined_with_value_rejected() -> None:
    with pytest.raises(ValueError):
        NetCostStat(
            status=StatStatus.UNDEFINED,
            value="1",
            reason=NetCostUndefinedReason.NO_VALID_PERIODS,
        )


@pytest.mark.parametrize(
    "raw",
    [
        {"status": "bogus"},
        {"status": "known"},  # missing value
        {"status": "known", "value": 1},  # non-string value
        {"status": "undefined"},  # missing reason
        {"status": "undefined", "reason": "not_a_reason"},
        {},
    ],
)
def test_from_dict_fails_closed(raw: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        NetCostStat.from_dict(raw)


def test_series_reason_parity_with_factorportfolio() -> None:
    """The three reused-summary reasons share their string values across layers."""
    from quantforge.factorportfolio.model import FactorPortfolioUndefinedReason

    for name in ("NO_VALID_PERIODS", "SINGLE_VALID_PERIOD", "ZERO_RETURN_VARIANCE"):
        assert (
            NetCostUndefinedReason[name].value
            == FactorPortfolioUndefinedReason[name].value
        )


def test_no_prior_reason_parity_with_stability() -> None:
    from quantforge.stability.model import StabilityUndefinedReason

    assert (
        NetCostUndefinedReason.NO_PRIOR_REALIZED_WINDOW.value
        == StabilityUndefinedReason.NO_PRIOR_REALIZED_WINDOW.value
    )


def test_excluded_reason_parity_with_stability() -> None:
    from quantforge.stability.model import StabilityExcludedReason

    assert (
        NetCostExcludedReason.WINDOW_UNDEFINED.value
        == StabilityExcludedReason.WINDOW_UNDEFINED.value
    )


def test_status_values() -> None:
    assert NetCostStatus.MEASURED.value == "measured"
    assert NetCostStatus.UNDEFINED.value == "undefined"
