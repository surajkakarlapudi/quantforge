"""The sealed MinTRL record (§9, §10): seal, round-trip, derived ids, accessors."""

from __future__ import annotations

import json

import pytest

from quantforge.mintrl.model import (
    MinTrlExcludedReason,
    MinTrlStat,
    MinTrlStatus,
    MinTrlUndefinedReason,
)
from quantforge.mintrl.result import (
    ExcludedTrial,
    MinimumTrackRecordLength,
    MinTrlCoverage,
    MinTrlSummary,
    TrialMinTrlCell,
)


def _cell(
    label: str,
    *,
    observed_length: int,
    min_trl: str,
    excess: str,
    sharpe: str = "0.5",
    skew: str = "0",
    kurtosis: str = "3",
) -> TrialMinTrlCell:
    return TrialMinTrlCell(
        label=label,
        observed_length=observed_length,
        sharpe=sharpe,
        skew=skew,
        kurtosis=kurtosis,
        min_track_record_length=MinTrlStat.known(min_trl),
        excess_length=MinTrlStat.known(excess),
    )


def _record() -> MinimumTrackRecordLength:
    trials = (
        _cell("trial_1", observed_length=100, min_trl="12", excess="88"),
        _cell("trial_2", observed_length=100, min_trl="30", excess="70"),
    )
    excluded = (
        ExcludedTrial(label="trial_3", reason=MinTrlExcludedReason.TRIAL_UNDEFINED),
    )
    summary = MinTrlSummary(
        mean_min_trl=MinTrlStat.known("21"),
        min_trl_dispersion=MinTrlStat.known("9"),
        max_min_trl=MinTrlStat.known("30"),
        min_min_trl=MinTrlStat.known("12"),
        sufficient_frequency=MinTrlStat.known("1"),
        n_determined=2,
        mintrl_status=MinTrlStatus.EVALUATED,
        status_reason=None,
    )
    coverage = MinTrlCoverage(n_trials=3, n_evaluable=2, n_excluded=1)
    return MinimumTrackRecordLength.seal(
        minimum_track_record_length_engine_version_id="sha256:engine",
        mintrl_spec={
            "spec_version": "mintrl/1",
            "name": "mintrl",
            "source_campaign_id": "sha256:src",
            "confidence": "0.95",
            "benchmark_sharpe": "0",
        },
        source_ref=("sha256:src", "sha256:srchash"),
        boundary_kind="pit",
        trials=trials,
        excluded=excluded,
        summary=summary,
        coverage=coverage,
    )


def test_seal_folds_answer_into_result_hash() -> None:
    assert _record().result_hash.startswith("sha256:")


def test_derived_id_aliases_research_result_id() -> None:
    r = _record()
    assert r.minimum_track_record_length_id == r.research_result_id
    assert r.minimum_track_record_length_id.startswith("sha256:")


def test_round_trip_is_byte_identical() -> None:
    r = _record()
    again = MinimumTrackRecordLength.from_dict(r.to_dict())
    assert json.dumps(r.to_dict(), sort_keys=True) == json.dumps(
        again.to_dict(), sort_keys=True
    )
    assert again.minimum_track_record_length_id == r.minimum_track_record_length_id
    assert again.result_hash == r.result_hash


def test_id_is_rederived_not_read_from_state() -> None:
    # A tampered stored id is ignored: the property recomputes from content.
    r = _record()
    raw = r.to_dict()
    raw["minimum_track_record_length_id"] = "sha256:tampered"
    raw["research_result_id"] = "sha256:tampered"
    again = MinimumTrackRecordLength.from_dict(raw)
    assert again.minimum_track_record_length_id == r.minimum_track_record_length_id


def test_accessors() -> None:
    r = _record()
    assert r.source_campaign_id == "sha256:src"
    assert r.source_result_hash == "sha256:srchash"
    assert r.mintrl_status is MinTrlStatus.EVALUATED


def test_not_a_pit_type_and_no_as_of_accessor() -> None:
    # Ex-post record: boundary documents the input side, but there is no as-of surface.
    r = _record()
    assert r.boundary_kind == "pit"
    assert not hasattr(r, "as_of")
    assert type(r).__name__ == "MinimumTrackRecordLength"
    assert not type(r).__name__.startswith("Pit")


def _resealed(**cell0: str) -> MinimumTrackRecordLength:
    """Re-seal ``_record`` with the first trial cell's fields overridden.

    Used to probe how ``seal`` folds each per-trial field into the hash.
    """
    r = _record()
    base = r.trials[0]
    first = TrialMinTrlCell(
        label=base.label,
        observed_length=base.observed_length,
        sharpe=cell0.get("sharpe", base.sharpe),
        skew=cell0.get("skew", base.skew),
        kurtosis=cell0.get("kurtosis", base.kurtosis),
        min_track_record_length=(
            MinTrlStat.known(cell0["min_trl"])
            if "min_trl" in cell0
            else base.min_track_record_length
        ),
        excess_length=base.excess_length,
    )
    return MinimumTrackRecordLength.seal(
        minimum_track_record_length_engine_version_id=(
            r.minimum_track_record_length_engine_version_id
        ),
        mintrl_spec=r.mintrl_spec,
        source_ref=r.source_ref,
        boundary_kind=r.boundary_kind,
        trials=(first, r.trials[1]),
        excluded=r.excluded,
        summary=r.summary,
        coverage=r.coverage,
    )


def test_min_trl_change_changes_the_hash() -> None:
    r = _record()
    assert _resealed(min_trl="13").result_hash != r.result_hash


def test_carried_moment_change_changes_the_hash() -> None:
    # The carried moments are part of the sealed per-trial cell (MT-4).
    r = _record()
    assert _resealed(sharpe="0.6").result_hash != r.result_hash


def test_from_dict_rejects_unknown_excluded_reason() -> None:
    r = _record()
    raw = r.to_dict()
    excluded = raw["excluded"]
    assert isinstance(excluded, list)
    first = excluded[0]
    assert isinstance(first, dict)
    first["reason"] = "not_a_reason"
    with pytest.raises(ValueError):
        MinimumTrackRecordLength.from_dict(raw)


def test_undefined_summary_round_trips_with_status_reason() -> None:
    # An all-undefined summary carries a status_reason that must survive the round trip.
    undef = MinTrlStat.undefined(MinTrlUndefinedReason.NO_DETERMINED_TRIALS)
    summary = MinTrlSummary(
        mean_min_trl=undef,
        min_trl_dispersion=undef,
        max_min_trl=undef,
        min_min_trl=undef,
        sufficient_frequency=undef,
        n_determined=0,
        mintrl_status=MinTrlStatus.UNDEFINED,
        status_reason=MinTrlUndefinedReason.INSUFFICIENT_DETERMINED_TRIALS,
    )
    r = MinimumTrackRecordLength.seal(
        minimum_track_record_length_engine_version_id="sha256:engine",
        mintrl_spec={
            "spec_version": "mintrl/1",
            "name": "mintrl",
            "source_campaign_id": "sha256:src",
            "confidence": "0.95",
            "benchmark_sharpe": "0",
        },
        source_ref=("sha256:src", "sha256:srchash"),
        boundary_kind="pit",
        trials=(),
        excluded=(),
        summary=summary,
        coverage=MinTrlCoverage(n_trials=0, n_evaluable=0, n_excluded=0),
    )
    again = MinimumTrackRecordLength.from_dict(r.to_dict())
    assert (
        again.summary.status_reason
        is MinTrlUndefinedReason.INSUFFICIENT_DETERMINED_TRIALS
    )
    assert again.result_hash == r.result_hash
