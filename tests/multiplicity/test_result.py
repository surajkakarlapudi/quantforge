"""The sealed correction record (§9, §10): seal, round-trip, derived ids, accessors."""

from __future__ import annotations

import json

import pytest

from quantforge.comparison.model import ComparisonUndefinedReason
from quantforge.multiplicity.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
)
from quantforge.multiplicity.result import (
    ExcludedCell,
    FamilyCell,
    MethodCell,
    MethodResult,
    MultipleComparisonCorrection,
    MultiplicityCoverage,
)


def _record() -> MultipleComparisonCorrection:
    family = (
        FamilyCell(
            i=0, j=1, label_i="strategy_1", label_j="strategy_2", p_value="0.01"
        ),
        FamilyCell(
            i=0, j=2, label_i="strategy_1", label_j="strategy_3", p_value="0.04"
        ),
    )
    excluded = (
        ExcludedCell(
            i=1,
            j=2,
            label_i="strategy_2",
            label_j="strategy_3",
            reason=ComparisonUndefinedReason.INSUFFICIENT_OVERLAP,
        ),
    )
    holm = MethodResult(
        method=CorrectionMethod.HOLM,
        error_rate=ErrorRate.FAMILY_WISE,
        dependence=DependenceAssumption.ARBITRARY,
        cells=(
            MethodCell(i=0, j=1, p_adjusted="0.02", rejected=True),
            MethodCell(i=0, j=2, p_adjusted="0.04", rejected=True),
        ),
        n_rejected=2,
    )
    coverage = MultiplicityCoverage(n_pairs_total=3, family_size=2, n_excluded=1)
    return MultipleComparisonCorrection.seal(
        multiplicity_engine_version_id="sha256:engine",
        correction_spec={
            "spec_version": "multiplicity/1",
            "name": "corr",
            "source_strategy_comparison_id": "sha256:src",
            "alpha": "0.05",
            "methods": ["holm"],
        },
        source_ref=("sha256:src", "sha256:srchash"),
        boundary_kind="pit",
        family=family,
        excluded=excluded,
        corrections=(holm,),
        coverage=coverage,
    )


def test_seal_folds_answer_into_result_hash() -> None:
    assert _record().result_hash.startswith("sha256:")


def test_derived_id_aliases_research_result_id() -> None:
    r = _record()
    assert r.multiple_comparison_id == r.research_result_id
    assert r.multiple_comparison_id.startswith("sha256:")


def test_round_trip_is_byte_identical() -> None:
    r = _record()
    again = MultipleComparisonCorrection.from_dict(r.to_dict())
    assert json.dumps(r.to_dict(), sort_keys=True) == json.dumps(
        again.to_dict(), sort_keys=True
    )
    assert again.multiple_comparison_id == r.multiple_comparison_id
    assert again.result_hash == r.result_hash


def test_id_is_rederived_not_read_from_state() -> None:
    # A tampered stored id is ignored: the property recomputes from content.
    r = _record()
    raw = r.to_dict()
    raw["multiple_comparison_id"] = "sha256:tampered"
    raw["research_result_id"] = "sha256:tampered"
    again = MultipleComparisonCorrection.from_dict(raw)
    assert again.multiple_comparison_id == r.multiple_comparison_id


def test_accessors() -> None:
    r = _record()
    assert r.alpha == "0.05"
    assert r.family_size == 2
    assert r.source_strategy_comparison_id == "sha256:src"
    assert r.source_result_hash == "sha256:srchash"
    assert r.correction(CorrectionMethod.HOLM).n_rejected == 2


def test_correction_accessor_raises_for_absent_method() -> None:
    with pytest.raises(KeyError):
        _record().correction(CorrectionMethod.BONFERRONI)


def test_not_a_pit_type_and_no_as_of_accessor() -> None:
    # Ex-post record: boundary documents the input side, but there is no as-of surface.
    r = _record()
    assert r.boundary_kind == "pit"
    assert not hasattr(r, "as_of")
    assert type(r).__name__ == "MultipleComparisonCorrection"
    assert not type(r).__name__.startswith("Pit")


def test_from_dict_rejects_unknown_reason() -> None:
    r = _record()
    raw = r.to_dict()
    excluded = raw["excluded"]
    assert isinstance(excluded, list)
    first = excluded[0]
    assert isinstance(first, dict)
    first["reason"] = "not_a_reason"
    with pytest.raises(ValueError):
        MultipleComparisonCorrection.from_dict(raw)
