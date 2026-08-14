"""End-to-end net-of-cost-significance through the engine (§6, NS-1..NS-6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from quantforge.factors.errors import FactorConsistencyError
from quantforge.netcostsig.errors import (
    NetCostSigConfigurationError,
    NetCostSigConsistencyError,
)
from quantforge.netcostsig.model import (
    EdgeDirection,
    NetCostSigUndefinedReason,
    SignificanceStatus,
    StatStatus,
)
from quantforge.netcostsig.result import NetOfCostSignificance
from tests.netcostsig.builders import (
    make_net_of_cost,
    make_spec,
    measured,
    measured_mean_undefined,
    netcostsig_engine,
    undefined_source,
    workspace,
    zero_volatility,
)


@dataclass(frozen=True)
class _DummyRecord:
    """A non-``NetOfCostPerformance`` :class:`ResearchRecord` for fail-closed tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-net-of-cost", "id": self.research_result_id}


# -- happy path (NS-4/NS-5) --------------------------------------------------


def test_happy_path_tests_the_series(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(
        ws, summary=measured(net_mean="0.01", net_volatility="0.05"), n_periods=100
    )
    result = netcostsig_engine(ws).evaluate(make_spec(nc.research_result_id))

    assert isinstance(result, NetOfCostSignificance)
    assert result.significance_status is SignificanceStatus.TESTED
    assert result.summary.n_periods == 100
    assert result.summary.null_mean_return == "0"
    assert result.summary.edge_direction is EdgeDirection.PROFITABLE
    assert result.summary.net_mean.value == "0.01"
    assert result.summary.standard_error.value == "0.005"
    assert result.summary.t_statistic.value == "2"
    assert result.summary.p_value.status is StatStatus.KNOWN


def test_source_reference_is_pinned(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=measured(net_mean="0.02", net_volatility="0.1"))
    result = netcostsig_engine(ws).evaluate(make_spec(nc.research_result_id))
    assert result.source_net_of_cost_id == nc.research_result_id
    assert result.source_result_hash == nc.result_hash


def test_boundary_is_carried_and_record_is_not_pit(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=measured(net_mean="0.02", net_volatility="0.1"))
    result = netcostsig_engine(ws).evaluate(make_spec(nc.research_result_id))
    assert result.boundary_kind == nc.boundary_kind == "pit"
    assert not hasattr(result, "as_of")


# -- defensibility gate (NS-2/NS-3) ------------------------------------------


def test_undefined_source_seals_undefined_verdict(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=undefined_source())
    result = netcostsig_engine(ws).evaluate(make_spec(nc.research_result_id))
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert result.summary.status_reason is NetCostSigUndefinedReason.SOURCE_NOT_MEASURED
    assert result.summary.net_mean.status is StatStatus.UNDEFINED
    assert result.summary.edge_direction is None


def test_measured_but_undefined_mean_is_source_not_measured(tmp_path: Path) -> None:
    # Defensive branch: MEASURED status but the aggregate net-mean cell is UNDEFINED.
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=measured_mean_undefined())
    result = netcostsig_engine(ws).evaluate(make_spec(nc.research_result_id))
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert result.summary.status_reason is NetCostSigUndefinedReason.SOURCE_NOT_MEASURED


def test_zero_volatility_seals_partial_undefined(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=zero_volatility(net_mean="0.03"))
    result = netcostsig_engine(ws).evaluate(make_spec(nc.research_result_id))
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert result.summary.status_reason is NetCostSigUndefinedReason.ZERO_NET_VOLATILITY
    # Mean + direction survive; t / p are undefined, never a divide-by-zero.
    assert result.summary.net_mean.value == "0.03"
    assert result.summary.edge_direction is EdgeDirection.PROFITABLE
    assert result.summary.t_statistic.status is StatStatus.UNDEFINED


# -- determinism & persistence -----------------------------------------------


def test_recompute_is_byte_identical_and_idempotent(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=measured(net_mean="0.01", net_volatility="0.05"))
    engine = netcostsig_engine(ws)
    first = engine.evaluate(make_spec(nc.research_result_id))
    second = engine.evaluate(make_spec(nc.research_result_id))
    assert first.net_of_cost_significance_id == second.net_of_cost_significance_id
    assert first.to_dict() == second.to_dict()
    stored = ws.research_result_store.read_as(
        first.research_result_id, NetOfCostSignificance.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()


# -- identity sensitivity (NS-1) ---------------------------------------------


def test_different_source_answer_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_net_of_cost(
        ws, summary=measured(net_mean="0.01", net_volatility="0.05"), name="a"
    )
    b = make_net_of_cost(
        ws, summary=measured(net_mean="0.02", net_volatility="0.05"), name="b"
    )
    engine = netcostsig_engine(ws)
    ra = engine.evaluate(make_spec(a.research_result_id))
    rb = engine.evaluate(make_spec(b.research_result_id))
    assert ra.net_of_cost_significance_id != rb.net_of_cost_significance_id


def test_request_name_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=measured(net_mean="0.01", net_volatility="0.05"))
    engine = netcostsig_engine(ws)
    one = engine.evaluate(make_spec(nc.research_result_id, name="one"))
    two = engine.evaluate(make_spec(nc.research_result_id, name="two"))
    assert one.net_of_cost_significance_id != two.net_of_cost_significance_id


# -- fail-closed guards (NS-1) -----------------------------------------------


def test_absent_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(NetCostSigConsistencyError):
        netcostsig_engine(ws).evaluate(make_spec("sha256:does-not-exist"))


def test_non_net_of_cost_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    dummy = _DummyRecord(research_result_id="sha256:dummy")
    ws.research_result_store.write(dummy)
    with pytest.raises(NetCostSigConsistencyError):
        netcostsig_engine(ws).evaluate(make_spec(dummy.research_result_id))


def test_id_mismatch_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=measured(net_mean="0.01", net_volatility="0.05"))
    store = ws.research_result_store
    real_bytes = store._result_path(nc.research_result_id).read_bytes()
    fake_id = "sha256:00000000"
    store._result_path(fake_id).write_bytes(real_bytes)
    with pytest.raises(NetCostSigConsistencyError):
        netcostsig_engine(ws).evaluate(make_spec(fake_id))


def test_non_spec_argument_is_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(NetCostSigConfigurationError):
        netcostsig_engine(ws).evaluate(object())  # type: ignore[arg-type]


def test_tampered_stored_payload_conflicts(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    nc = make_net_of_cost(ws, summary=measured(net_mean="0.01", net_volatility="0.05"))
    result = netcostsig_engine(ws).evaluate(make_spec(nc.research_result_id))
    store = ws.research_result_store

    @dataclass(frozen=True)
    class _Same:
        research_result_id: str
        payload: dict[str, object]

        def to_dict(self) -> dict[str, object]:
            return self.payload

    tampered = result.to_dict()
    tampered["boundary_kind"] = "tampered"
    with pytest.raises(FactorConsistencyError):
        store.write(
            _Same(
                research_result_id=result.research_result_id,
                payload=tampered,
            )
        )
