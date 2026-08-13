"""Content-addressed identity of the campaign-multiplicity record (§10, §11, CM-1)."""

from __future__ import annotations

from quantforge.campaignmult.identity import (
    campaign_multiplicity_id,
    campaign_multiplicity_result_hash,
)


def _id(**over: object) -> str:
    base: dict[str, object] = {
        "campaign_multiplicity_engine_version_id": "sha256:engine",
        "name": "c",
        "spec_version": "campaignmult/1",
        "source_campaign_id": "sha256:campaign",
        "source_result_hash": "sha256:rh",
        "alpha": "0.05",
        "methods": ["holm", "benjamini_yekutieli"],
        "result_hash": "sha256:answer",
    }
    base.update(over)
    return campaign_multiplicity_id(**base)  # type: ignore[arg-type]


def test_stable_and_prefixed() -> None:
    assert _id() == _id()
    assert _id().startswith("sha256:")


def test_transitive_pin_on_source_result_hash() -> None:
    # A change in the source campaign's result_hash changes the correction id (CM-1).
    assert _id() != _id(source_result_hash="sha256:other")


def test_sensitive_to_answer() -> None:
    assert _id() != _id(result_hash="sha256:other-answer")


def test_method_order_is_load_bearing() -> None:
    assert _id(methods=["holm", "benjamini_yekutieli"]) != _id(
        methods=["benjamini_yekutieli", "holm"]
    )


def test_sensitive_to_alpha_and_source_and_engine() -> None:
    assert _id() != _id(alpha="0.01")
    assert _id() != _id(source_campaign_id="sha256:other")
    assert _id() != _id(campaign_multiplicity_engine_version_id="sha256:other")


def test_result_hash_sensitive_to_cells() -> None:
    a = campaign_multiplicity_result_hash(
        [{"block": "family", "index": 0, "psr": "0.9", "p_value": "0.1"}]
    )
    b = campaign_multiplicity_result_hash(
        [{"block": "family", "index": 0, "psr": "0.8", "p_value": "0.2"}]
    )
    assert a != b
    assert a.startswith("sha256:")
