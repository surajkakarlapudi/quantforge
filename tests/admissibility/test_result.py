"""The sealed admissibility record round-trips byte-identically (§9, §10)."""

from __future__ import annotations

from quantforge.admissibility.model import (
    AdmissibilityUndefinedReason,
    AdmissibilityVerdict,
    Criterion,
    CriterionKind,
)
from quantforge.admissibility.result import (
    BOUNDARY_PIT,
    AdmissibilitySummary,
    StrategyAdmissibility,
)


def _admissible_summary() -> AdmissibilitySummary:
    return AdmissibilitySummary(
        verdict=AdmissibilityVerdict.ADMISSIBLE,
        alpha="0.05",
        criteria=(
            Criterion.passed(CriterionKind.STABILITY, detail="stable"),
            Criterion.passed(CriterionKind.CALIBRATION, detail="0.5"),
            Criterion.passed(CriterionKind.NET_OF_COST_EDGE, detail="0.01"),
        ),
    )


def _undefined_summary() -> AdmissibilitySummary:
    return AdmissibilitySummary(
        verdict=AdmissibilityVerdict.UNDEFINED,
        alpha="0.05",
        criteria=(
            Criterion.passed(CriterionKind.STABILITY, detail="stable"),
            Criterion.passed(CriterionKind.CALIBRATION, detail="0.5"),
            Criterion.undefined(
                CriterionKind.NET_OF_COST_EDGE,
                AdmissibilityUndefinedReason.NET_OF_COST_UNDEFINED,
            ),
        ),
    )


def _seal(summary: AdmissibilitySummary) -> StrategyAdmissibility:
    return StrategyAdmissibility.seal(
        admissibility_engine_version_id="sha256:engine",
        admissibility_spec={
            "spec_version": "admissibility/1",
            "name": "phase33",
            "source_stability_id": "sha256:stab",
            "source_calibration_significance_id": "sha256:cal",
            "source_net_of_cost_significance_id": "sha256:net",
            "alpha": summary.alpha,
        },
        stability_ref=("sha256:stab", "sha256:stab-hash"),
        calibration_ref=("sha256:cal", "sha256:cal-hash"),
        net_of_cost_ref=("sha256:net", "sha256:net-hash"),
        boundary_kind=BOUNDARY_PIT,
        summary=summary,
    )


def test_admissible_record_round_trips() -> None:
    record = _seal(_admissible_summary())
    restored = StrategyAdmissibility.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.admissibility_id == record.admissibility_id
    assert restored.result_hash == record.result_hash


def test_undefined_record_round_trips() -> None:
    record = _seal(_undefined_summary())
    restored = StrategyAdmissibility.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.verdict is AdmissibilityVerdict.UNDEFINED


def test_research_result_id_aliases_the_admissibility_id() -> None:
    record = _seal(_admissible_summary())
    assert record.research_result_id == record.admissibility_id


def test_source_ref_accessors() -> None:
    record = _seal(_admissible_summary())
    assert record.source_stability_id == "sha256:stab"
    assert record.source_stability_result_hash == "sha256:stab-hash"
    assert record.source_calibration_significance_id == "sha256:cal"
    assert record.source_calibration_result_hash == "sha256:cal-hash"
    assert record.source_net_of_cost_significance_id == "sha256:net"
    assert record.source_net_of_cost_result_hash == "sha256:net-hash"


def test_id_is_derived_not_stored() -> None:
    # A tampered stored id is ignored; the property re-derives from content.
    record = _seal(_admissible_summary())
    payload = record.to_dict()
    payload["admissibility_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = StrategyAdmissibility.from_dict(payload)
    assert restored.admissibility_id == record.admissibility_id


def test_result_hash_folds_the_answer() -> None:
    admissible = _seal(_admissible_summary())
    undefined = _seal(_undefined_summary())
    assert admissible.result_hash != undefined.result_hash
    assert admissible.admissibility_id != undefined.admissibility_id


def test_summary_criterion_views() -> None:
    summary = _undefined_summary()
    assert summary.undefined_criteria == (CriterionKind.NET_OF_COST_EDGE,)
    assert summary.failed_criteria == ()


def test_record_is_not_pit() -> None:
    record = _seal(_admissible_summary())
    assert record.boundary_kind == "pit"
    assert not hasattr(record, "as_of")
