"""End-to-end: resolve a sealed pair, charge cost, seal, persist, fail closed."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from quantforge.factors.errors import FactorConsistencyError
from quantforge.netcost.errors import (
    NetOfCostConfigurationError,
    NetOfCostConsistencyError,
)
from quantforge.netcost.model import NetCostStat, NetCostStatus, NetCostUndefinedReason
from quantforge.netcost.result import NetOfCostPerformance
from tests.netcost.builders import (
    excluded,
    make_sources,
    make_spec,
    net_of_cost_engine,
    realized,
    workspace,
)

# The golden schedule: window 0 has no prior (turnover None), window 1 trades 0.6.
_GOLDEN = [
    realized(0, ["0.02"], turnover=None),
    realized(1, ["0.04"], turnover="0.6"),
]


def _known(cell: NetCostStat) -> Decimal:
    """The numeric value of a KNOWN cell (canonical trailing zeros ignored)."""
    assert cell.value is not None
    return Decimal(cell.value)


def test_golden_end_to_end(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    _walk, stability = make_sources(ws, windows=_GOLDEN)
    engine = net_of_cost_engine(ws)

    perf = engine.evaluate(make_spec(stability.research_result_id, cost_rate="0.1"))

    assert Decimal(perf.summary.total_gross_return) == Decimal("0.06")
    assert Decimal(perf.summary.total_turnover) == Decimal("0.6")
    assert Decimal(perf.summary.total_cost) == Decimal("0.06")
    assert _known(perf.summary.gross_mean) == Decimal("0.03")
    assert _known(perf.summary.net_mean) == Decimal("0")
    assert _known(perf.summary.net_sharpe) == Decimal("0")
    assert _known(perf.summary.break_even_cost_rate) == Decimal("0.1")
    assert _known(perf.summary.cost_drag_mean) == Decimal("0.03")
    assert perf.net_status is NetCostStatus.MEASURED
    assert perf.coverage.n_windows == 2
    assert perf.coverage.n_realized == 2
    assert perf.coverage.n_charged == 1
    assert perf.coverage.n_periods == 2
    assert perf.source_ref == (stability.research_result_id, stability.result_hash)
    assert perf.boundary_kind == "pit"


def test_persisted_and_readable(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    _walk, stability = make_sources(ws, windows=_GOLDEN)
    engine = net_of_cost_engine(ws)
    perf = engine.evaluate(make_spec(stability.research_result_id))

    read = ws.research_result_store.read_as(
        perf.research_result_id, NetOfCostPerformance.from_dict
    )
    assert read == perf


def test_rebuild_is_idempotent_no_op(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    _walk, stability = make_sources(ws, windows=_GOLDEN)
    engine = net_of_cost_engine(ws)
    spec = make_spec(stability.research_result_id)
    first = engine.evaluate(spec)
    second = engine.evaluate(spec)
    assert first == second
    assert first.to_dict() == second.to_dict()


def test_zero_cost_identity_end_to_end(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    _walk, stability = make_sources(ws, windows=_GOLDEN)
    engine = net_of_cost_engine(ws)
    perf = engine.evaluate(make_spec(stability.research_result_id, cost_rate="0"))
    assert Decimal(perf.summary.total_cost) == Decimal("0")
    assert perf.summary.net_mean == perf.summary.gross_mean
    assert perf.summary.net_volatility == perf.summary.gross_volatility
    assert perf.summary.net_sharpe == perf.summary.gross_sharpe


def test_cost_rate_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    _walk, stability = make_sources(ws, windows=_GOLDEN)
    engine = net_of_cost_engine(ws)
    a = engine.evaluate(make_spec(stability.research_result_id, cost_rate="0.1"))
    b = engine.evaluate(make_spec(stability.research_result_id, cost_rate="0.2"))
    assert a.net_of_cost_id != b.net_of_cost_id


def test_excluded_window_carried(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    schedule = [
        realized(0, ["0.02"], turnover=None),
        excluded(1),
        realized(2, ["0.04"], turnover="0.6"),
    ]
    _walk, stability = make_sources(ws, windows=schedule)
    engine = net_of_cost_engine(ws)
    perf = engine.evaluate(make_spec(stability.research_result_id))
    assert perf.coverage.n_windows == 3
    assert perf.coverage.n_excluded == 1
    assert [w.index for w in perf.excluded] == [1]
    # The two realized windows are still adjacent for turnover purposes.
    assert [w.index for w in perf.windows] == [0, 2]


def test_degenerate_no_turnover_seals_undefined_break_even(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    schedule = [
        realized(0, ["0.05"], turnover=None),
        realized(1, ["0.08"], turnover=None),
    ]
    _walk, stability = make_sources(ws, windows=schedule)
    engine = net_of_cost_engine(ws)
    perf = engine.evaluate(make_spec(stability.research_result_id, cost_rate="0.1"))
    assert perf.summary.total_turnover == "0"
    assert perf.summary.break_even_cost_rate.status.value == "undefined"
    assert (
        perf.summary.break_even_cost_rate.reason
        is NetCostUndefinedReason.DEGENERATE_NO_TURNOVER
    )


def test_zero_net_variance_seals_undefined_sharpe(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    schedule = [
        realized(0, ["0.05"], turnover=None),
        realized(1, ["0.08"], turnover="0.6"),
    ]
    _walk, stability = make_sources(ws, windows=schedule)
    engine = net_of_cost_engine(ws)
    # cost = 0.05*0.6 = 0.03 -> net = ["0.05", "0.05"] (constant).
    perf = engine.evaluate(make_spec(stability.research_result_id, cost_rate="0.05"))
    assert perf.net_status is NetCostStatus.UNDEFINED
    assert perf.summary.net_sharpe.status.value == "undefined"
    assert perf.summary.status_reason is NetCostUndefinedReason.ZERO_RETURN_VARIANCE


def test_workspace_property_is_engine(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    first = ws.net_of_cost_engine
    second = ws.net_of_cost_engine
    assert first is second  # cached


# -- fail-closed paths -------------------------------------------------------


def test_non_spec_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = net_of_cost_engine(ws)
    with pytest.raises(NetOfCostConfigurationError):
        engine.evaluate(object())  # type: ignore[arg-type]


def test_missing_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = net_of_cost_engine(ws)
    with pytest.raises(NetOfCostConsistencyError):
        engine.evaluate(make_spec("sha256:does-not-exist"))


def test_wrong_type_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    _walk, _stability = make_sources(ws, windows=_GOLDEN)
    engine = net_of_cost_engine(ws)
    # Point the spec at the WALK id (a WalkForwardEvaluation), not a stability record.
    with pytest.raises(NetOfCostConsistencyError):
        engine.evaluate(make_spec(_walk.research_result_id))


def test_differing_payload_same_id_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    _walk, stability = make_sources(ws, windows=_GOLDEN)
    engine = net_of_cost_engine(ws)
    spec = make_spec(stability.research_result_id)
    perf = engine.evaluate(spec)

    # Forge a differing payload and re-key it under perf's already-stored id: the
    # store's write-once guard must refuse the silent overwrite.
    forged_raw = perf.to_dict()
    summary = forged_raw["summary"]
    assert isinstance(summary, dict)
    summary["total_cost"] = "9.99"
    forged_raw["summary"] = summary
    forged = NetOfCostPerformance.from_dict(forged_raw)
    with pytest.raises(FactorConsistencyError):
        ws.research_result_store.write(_Aliased(perf.research_result_id, forged))


class _Aliased:
    """A ResearchRecord that reports a chosen id but a different (forged) payload."""

    def __init__(self, research_result_id: str, inner: NetOfCostPerformance) -> None:
        self._id = research_result_id
        self._inner = inner

    @property
    def research_result_id(self) -> str:
        return self._id

    def to_dict(self) -> dict[str, object]:
        return self._inner.to_dict()
