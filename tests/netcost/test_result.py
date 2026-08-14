"""The sealed net-of-cost record round-trips byte-identically and re-derives its id."""

from __future__ import annotations

from dataclasses import replace

import pytest

from quantforge.netcost.model import (
    NetCostExcludedReason,
    NetCostStat,
    NetCostStatus,
    NetCostUndefinedReason,
)
from quantforge.netcost.result import (
    ExcludedWindow,
    NetOfCostCoverage,
    NetOfCostPerformance,
    NetOfCostSummary,
    WindowNetCostCell,
)
from quantforge.netcost.version import NetOfCostEngineVersion

_ENGINE_ID = NetOfCostEngineVersion().net_of_cost_engine_version_id

_SPEC: dict[str, object] = {
    "name": "phase31-netcost",
    "spec_version": "netcost/1",
    "source_stability_id": "sha256:stability",
    "cost_rate": "0.1",
}


def _summary() -> NetOfCostSummary:
    return NetOfCostSummary(
        gross_mean=NetCostStat.known("0.03"),
        gross_volatility=NetCostStat.known("0.01"),
        gross_sharpe=NetCostStat.known("3"),
        net_mean=NetCostStat.known("0"),
        net_volatility=NetCostStat.known("0.02"),
        net_sharpe=NetCostStat.known("0"),
        cost_drag_mean=NetCostStat.known("0.03"),
        sharpe_drag=NetCostStat.known("3"),
        break_even_cost_rate=NetCostStat.known("0.1"),
        total_gross_return="0.06",
        total_turnover="0.6",
        total_cost="0.06",
        net_status=NetCostStatus.MEASURED,
    )


def _windows() -> tuple[WindowNetCostCell, ...]:
    return (
        WindowNetCostCell(
            index=0,
            n_periods=1,
            gross_return="0.02",
            turnover=NetCostStat.undefined(
                NetCostUndefinedReason.NO_PRIOR_REALIZED_WINDOW
            ),
            cost=NetCostStat.undefined(NetCostUndefinedReason.NO_PRIOR_REALIZED_WINDOW),
            net_return="0.02",
        ),
        WindowNetCostCell(
            index=1,
            n_periods=1,
            gross_return="0.04",
            turnover=NetCostStat.known("0.6"),
            cost=NetCostStat.known("0.06"),
            net_return="-0.02",
        ),
    )


def _seal(**over: object) -> NetOfCostPerformance:
    kwargs: dict[str, object] = {
        "net_of_cost_engine_version_id": _ENGINE_ID,
        "net_of_cost_spec": _SPEC,
        "source_ref": ("sha256:stability", "sha256:rh"),
        "boundary_kind": "pit",
        "periods_per_year": "1",
        "risk_free_per_period": "0",
        "windows": _windows(),
        "excluded": (
            ExcludedWindow(index=2, reason=NetCostExcludedReason.WINDOW_UNDEFINED),
        ),
        "summary": _summary(),
        "coverage": NetOfCostCoverage(
            n_windows=3, n_realized=2, n_excluded=1, n_charged=1, n_periods=2
        ),
    }
    kwargs.update(over)
    return NetOfCostPerformance.seal(**kwargs)  # type: ignore[arg-type]


def test_seal_computes_result_hash() -> None:
    perf = _seal()
    assert perf.result_hash.startswith("sha256:")
    assert perf.net_of_cost_id.startswith("sha256:")
    assert perf.research_result_id == perf.net_of_cost_id


def test_round_trip_byte_identical() -> None:
    perf = _seal()
    restored = NetOfCostPerformance.from_dict(perf.to_dict())
    assert restored == perf
    assert restored.to_dict() == perf.to_dict()
    assert restored.net_of_cost_id == perf.net_of_cost_id
    assert restored.result_hash == perf.result_hash


def test_id_rederived_not_stored() -> None:
    perf = _seal()
    tampered = perf.to_dict()
    tampered["net_of_cost_id"] = "sha256:TAMPERED"
    tampered["research_result_id"] = "sha256:TAMPERED"
    restored = NetOfCostPerformance.from_dict(tampered)
    assert restored.net_of_cost_id == perf.net_of_cost_id


def test_source_ref_accessors() -> None:
    perf = _seal()
    assert perf.source_stability_id == "sha256:stability"
    assert perf.source_result_hash == "sha256:rh"
    assert perf.net_status is NetCostStatus.MEASURED


def test_result_hash_sensitive_to_a_window_cell() -> None:
    base = _seal()
    win = list(_windows())
    win[1] = WindowNetCostCell(
        index=1,
        n_periods=1,
        gross_return="0.04",
        turnover=NetCostStat.known("0.6"),
        cost=NetCostStat.known("0.06"),
        net_return="-0.03",  # changed
    )
    other = _seal(windows=tuple(win))
    assert other.result_hash != base.result_hash


def test_result_hash_sensitive_to_summary() -> None:
    base = _seal()
    other = _seal(summary=replace(_summary(), net_sharpe=NetCostStat.known("0.5")))
    assert other.result_hash != base.result_hash


def test_cost_rate_changes_id_but_not_result_hash() -> None:
    base = _seal()
    other = _seal(net_of_cost_spec={**_SPEC, "cost_rate": "0.2"})
    # result_hash is over the computed answer cells only (spec not folded there).
    assert other.result_hash == base.result_hash
    # ...but the declared cost rate is folded into the id.
    assert other.net_of_cost_id != base.net_of_cost_id


def test_undefined_summary_round_trip() -> None:
    summ = replace(
        _summary(),
        net_sharpe=NetCostStat.undefined(NetCostUndefinedReason.ZERO_RETURN_VARIANCE),
        net_status=NetCostStatus.UNDEFINED,
        status_reason=NetCostUndefinedReason.ZERO_RETURN_VARIANCE,
    )
    perf = _seal(summary=summ)
    restored = NetOfCostPerformance.from_dict(perf.to_dict())
    assert restored == perf
    assert restored.summary.status_reason is NetCostUndefinedReason.ZERO_RETURN_VARIANCE


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("summary"),
        lambda d: d.__setitem__("windows", "not-a-list"),
        lambda d: d.__setitem__("source_ref", "not-a-dict"),
        lambda d: d.pop("result_hash"),
    ],
)
def test_from_dict_fails_closed(mutate: object) -> None:
    payload = _seal().to_dict()
    mutate(payload)  # type: ignore[operator]
    with pytest.raises((ValueError, KeyError)):
        NetOfCostPerformance.from_dict(payload)
