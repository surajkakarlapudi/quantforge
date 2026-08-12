"""Content-addressed identity for the campaign layer (§10, §11)."""

from __future__ import annotations

from quantforge.campaign.identity import campaign_id, campaign_result_hash


def _id(**overrides: object) -> str:
    base: dict[str, object] = {
        "campaign_engine_version_id": "sha256:engine",
        "name": "campaign",
        "spec_version": "campaign/1",
        "trial_ids": ["sha256:a", "sha256:b"],
        "benchmark_sharpe": "0",
        "trial_result_hashes": ["sha256:ha", "sha256:hb"],
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return campaign_id(**base)  # type: ignore[arg-type]


def test_ids_are_sha256_prefixed() -> None:
    assert _id().startswith("sha256:")
    assert campaign_result_hash([{"block": "x"}]).startswith("sha256:")


def test_identity_is_deterministic() -> None:
    assert _id() == _id()


def test_trial_order_is_semantic() -> None:
    forward = _id(trial_ids=["sha256:a", "sha256:b"])
    reversed_ = _id(trial_ids=["sha256:b", "sha256:a"])
    assert forward != reversed_


def test_each_fold_changes_the_id() -> None:
    baseline = _id()
    assert _id(campaign_engine_version_id="sha256:other") != baseline
    assert _id(name="other") != baseline
    assert _id(spec_version="campaign/2") != baseline
    assert _id(benchmark_sharpe="0.1") != baseline
    assert _id(trial_result_hashes=["sha256:hx", "sha256:hb"]) != baseline
    assert _id(result_hash="sha256:other") != baseline


def test_result_hash_sensitive_to_every_cell() -> None:
    a = campaign_result_hash([{"block": "trial", "sharpe": "1"}])
    b = campaign_result_hash([{"block": "trial", "sharpe": "2"}])
    assert a != b


def test_result_hash_is_order_sensitive() -> None:
    cells = [{"block": "trial", "i": 1}, {"block": "trial", "i": 2}]
    assert campaign_result_hash(cells) != campaign_result_hash(list(reversed(cells)))
