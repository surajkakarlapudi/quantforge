"""Content-addressed identity for the minimum-track-record-length layer (§10, §11)."""

from __future__ import annotations

from quantforge.mintrl.identity import (
    minimum_track_record_length_id,
    minimum_track_record_length_result_hash,
)


def _id(**overrides: object) -> str:
    base: dict[str, object] = {
        "minimum_track_record_length_engine_version_id": "sha256:engine",
        "name": "mintrl",
        "spec_version": "mintrl/1",
        "source_campaign_id": "sha256:src",
        "source_result_hash": "sha256:srchash",
        "confidence": "0.95",
        "benchmark_sharpe": "0",
        "min_determined_trials": 2,
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return minimum_track_record_length_id(**base)  # type: ignore[arg-type]


def test_ids_are_sha256_prefixed() -> None:
    assert _id().startswith("sha256:")
    assert minimum_track_record_length_result_hash([{"block": "x"}]).startswith(
        "sha256:"
    )


def test_identity_is_deterministic() -> None:
    assert _id() == _id()


def test_each_fold_changes_the_id() -> None:
    base = _id()
    assert _id(minimum_track_record_length_engine_version_id="sha256:other") != base
    assert _id(name="other") != base
    assert _id(spec_version="mintrl/2") != base
    assert _id(source_campaign_id="sha256:other") != base
    assert _id(source_result_hash="sha256:other") != base
    assert _id(confidence="0.99") != base
    assert _id(benchmark_sharpe="0.1") != base
    assert _id(min_determined_trials=3) != base
    assert _id(result_hash="sha256:other") != base


def test_result_hash_is_sensitive_to_a_single_cell() -> None:
    a = minimum_track_record_length_result_hash(
        [{"block": "trial", "min_track_record_length": "12"}]
    )
    b = minimum_track_record_length_result_hash(
        [{"block": "trial", "min_track_record_length": "13"}]
    )
    assert a != b


def test_result_hash_is_order_sensitive() -> None:
    a = minimum_track_record_length_result_hash(
        [{"block": "trial", "label": "trial_1"}, {"block": "trial", "label": "trial_2"}]
    )
    b = minimum_track_record_length_result_hash(
        [{"block": "trial", "label": "trial_2"}, {"block": "trial", "label": "trial_1"}]
    )
    assert a != b
