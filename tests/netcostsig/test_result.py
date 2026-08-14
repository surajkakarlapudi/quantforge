"""The sealed significance record round-trips byte-identically (§9, §10)."""

from __future__ import annotations

from quantforge.netcostsig.model import (
    EdgeDirection,
    NetCostSigUndefinedReason,
    SignificanceStat,
    SignificanceStatus,
)
from quantforge.netcostsig.result import (
    NULL_MEAN_RETURN,
    NetOfCostSignificance,
    SignificanceSummary,
)


def _tested_summary() -> SignificanceSummary:
    return SignificanceSummary(
        net_mean=SignificanceStat.known("0.01"),
        null_mean_return=NULL_MEAN_RETURN,
        n_periods=100,
        standard_error=SignificanceStat.known("0.005"),
        t_statistic=SignificanceStat.known("2"),
        p_value=SignificanceStat.known("0.02275"),
        significance_status=SignificanceStatus.TESTED,
        edge_direction=EdgeDirection.PROFITABLE,
    )


def _undefined_summary() -> SignificanceSummary:
    reason = NetCostSigUndefinedReason.SOURCE_NOT_MEASURED
    undefined = SignificanceStat.undefined(reason)
    return SignificanceSummary(
        net_mean=undefined,
        null_mean_return=NULL_MEAN_RETURN,
        n_periods=0,
        standard_error=undefined,
        t_statistic=undefined,
        p_value=undefined,
        significance_status=SignificanceStatus.UNDEFINED,
        status_reason=reason,
    )


def _seal(summary: SignificanceSummary) -> NetOfCostSignificance:
    return NetOfCostSignificance.seal(
        net_of_cost_significance_engine_version_id="sha256:engine",
        net_of_cost_significance_spec={
            "spec_version": "netcostsig/1",
            "name": "phase32",
            "source_net_of_cost_id": "sha256:nc",
        },
        source_ref=("sha256:nc", "sha256:nc-hash"),
        boundary_kind="pit",
        summary=summary,
    )


def test_tested_record_round_trips() -> None:
    record = _seal(_tested_summary())
    restored = NetOfCostSignificance.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.net_of_cost_significance_id == record.net_of_cost_significance_id
    assert restored.result_hash == record.result_hash


def test_undefined_record_round_trips() -> None:
    record = _seal(_undefined_summary())
    restored = NetOfCostSignificance.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.significance_status is SignificanceStatus.UNDEFINED


def test_research_result_id_aliases_the_significance_id() -> None:
    record = _seal(_tested_summary())
    assert record.research_result_id == record.net_of_cost_significance_id


def test_source_ref_accessors() -> None:
    record = _seal(_tested_summary())
    assert record.source_net_of_cost_id == "sha256:nc"
    assert record.source_result_hash == "sha256:nc-hash"


def test_id_is_derived_not_stored() -> None:
    # A tampered stored id is ignored; the property re-derives from content.
    record = _seal(_tested_summary())
    payload = record.to_dict()
    payload["net_of_cost_significance_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = NetOfCostSignificance.from_dict(payload)
    assert restored.net_of_cost_significance_id == record.net_of_cost_significance_id


def test_result_hash_folds_the_answer() -> None:
    a = _seal(_tested_summary())
    changed = _tested_summary()
    changed = SignificanceSummary(
        net_mean=changed.net_mean,
        null_mean_return=changed.null_mean_return,
        n_periods=changed.n_periods,
        standard_error=changed.standard_error,
        t_statistic=SignificanceStat.known("3"),
        p_value=changed.p_value,
        significance_status=changed.significance_status,
        edge_direction=changed.edge_direction,
    )
    b = _seal(changed)
    assert a.result_hash != b.result_hash
    assert a.net_of_cost_significance_id != b.net_of_cost_significance_id


def test_record_is_not_pit() -> None:
    record = _seal(_tested_summary())
    assert record.boundary_kind == "pit"
    assert not hasattr(record, "as_of")
