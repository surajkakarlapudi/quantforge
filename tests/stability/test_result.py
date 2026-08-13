"""The sealed stability record: byte-identical round-trip, re-emitted ids (§9, §10)."""

from __future__ import annotations

import pytest

from quantforge.stability.model import (
    StabilityExcludedReason,
    StabilityStat,
    StabilityStatus,
    StabilityUndefinedReason,
)
from quantforge.stability.result import (
    ExcludedWindow,
    StabilityCoverage,
    StabilitySummary,
    WalkForwardStability,
    WindowStabilityCell,
)


def _summary() -> StabilitySummary:
    known = StabilityStat.known
    return StabilitySummary(
        mean_turnover=known("0.75"),
        turnover_dispersion=known("0.25"),
        max_turnover=known("1.0"),
        min_turnover=known("0.5"),
        mean_gross_leverage=known("1.0"),
        max_gross_leverage=known("1.0"),
        mean_concentration_hhi=known("0.50"),
        mean_effective_breadth=known("2"),
        stability_status=StabilityStatus.STABLE,
        status_reason=None,
    )


def _record() -> WalkForwardStability:
    windows = (
        WindowStabilityCell(
            index=0,
            gross_leverage="1.0",
            concentration_hhi="0.50",
            effective_breadth=StabilityStat.known("2"),
            max_abs_weight="0.5",
            turnover_from_prev=StabilityStat.undefined(
                StabilityUndefinedReason.NO_PRIOR_REALIZED_WINDOW
            ),
        ),
        WindowStabilityCell(
            index=2,
            gross_leverage="1.0",
            concentration_hhi="0.50",
            effective_breadth=StabilityStat.known("2"),
            max_abs_weight="0.5",
            turnover_from_prev=StabilityStat.known("0.5"),
        ),
    )
    excluded = (
        ExcludedWindow(index=1, reason=StabilityExcludedReason.WINDOW_UNDEFINED),
    )
    coverage = StabilityCoverage(
        n_windows=3, n_realized=2, n_excluded=1, n_transitions=1
    )
    return WalkForwardStability.seal(
        stability_engine_version_id="sha256:engine",
        stability_spec={
            "spec_version": "stability/1",
            "name": "stab",
            "source_walk_forward_id": "sha256:src",
        },
        source_ref=("sha256:src", "sha256:srchash"),
        boundary_kind="pit",
        windows=windows,
        excluded=excluded,
        summary=_summary(),
        coverage=coverage,
    )


def test_round_trip_is_byte_identical() -> None:
    record = _record()
    restored = WalkForwardStability.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.result_hash == record.result_hash


def test_derived_ids_are_re_emitted_not_stored() -> None:
    record = _record()
    payload = record.to_dict()
    # Tamper the stored id: the property re-derives it from the record's own fields.
    payload["walk_forward_stability_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = WalkForwardStability.from_dict(payload)
    assert restored.walk_forward_stability_id != "sha256:tampered"
    assert restored.research_result_id == restored.walk_forward_stability_id


def test_research_result_id_aliases_stability_id() -> None:
    record = _record()
    assert record.research_result_id == record.walk_forward_stability_id


def test_source_ref_accessors() -> None:
    record = _record()
    assert record.source_walk_forward_id == "sha256:src"
    assert record.source_result_hash == "sha256:srchash"


def test_stability_status_alias() -> None:
    record = _record()
    assert record.stability_status is StabilityStatus.STABLE


def test_effective_breadth_is_omitted_from_result_hash_payload() -> None:
    # Two records identical except in the derivable effective_breadth seal to the same
    # result_hash (it is excluded from the hashed cell payload; concentration_hhi folds
    # it). The record content still round-trips it.
    record = _record()
    other_windows = tuple(
        WindowStabilityCell(
            index=w.index,
            gross_leverage=w.gross_leverage,
            concentration_hhi=w.concentration_hhi,
            effective_breadth=StabilityStat.known("99"),
            max_abs_weight=w.max_abs_weight,
            turnover_from_prev=w.turnover_from_prev,
        )
        for w in record.windows
    )
    other = WalkForwardStability.seal(
        stability_engine_version_id="sha256:engine",
        stability_spec=dict(record.stability_spec),
        source_ref=record.source_ref,
        boundary_kind="pit",
        windows=other_windows,
        excluded=record.excluded,
        summary=record.summary,
        coverage=record.coverage,
    )
    assert other.result_hash == record.result_hash


def test_from_dict_rejects_malformed_source_ref() -> None:
    payload = _record().to_dict()
    del payload["source_ref"]
    with pytest.raises((KeyError, ValueError)):
        WalkForwardStability.from_dict(payload)
