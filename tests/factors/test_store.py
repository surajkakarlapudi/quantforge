"""Tests for :class:`ResearchResultStore` — the write-once sidecar (§3, F4, §15).

Covers: round-trip (write → read → identical); content-addressed layout keyed by
``research_result_id`` (colon slugified for Windows); idempotent re-write; a
differing payload under an existing id fails closed; the store lives under the given
root, never in the repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quantforge.factors.errors import FactorConsistencyError
from quantforge.factors.store import ResearchResultStore
from tests.factors.builders import research_result


def test_round_trips_identically(tmp_path: Path) -> None:
    store = ResearchResultStore(tmp_path)
    original = research_result()
    store.write(original)
    read_back = store.read(original.research_result_id)
    assert read_back is not None
    assert read_back.to_dict() == original.to_dict()


def test_file_is_keyed_by_id_with_colon_slugified(tmp_path: Path) -> None:
    store = ResearchResultStore(tmp_path)
    store.write(research_result(research_result_id="sha256:abc123"))
    expected = tmp_path / "research" / "sha256-abc123.json"
    assert expected.exists()


def test_read_missing_returns_none(tmp_path: Path) -> None:
    store = ResearchResultStore(tmp_path)
    assert store.read("sha256:absent") is None
    assert store.has("sha256:absent") is False


def test_rewrite_of_identical_payload_is_idempotent(tmp_path: Path) -> None:
    store = ResearchResultStore(tmp_path)
    result = research_result()
    first = store.write(result)
    first_bytes = first.read_bytes()
    store.write(result)  # no error, no change
    assert first.read_bytes() == first_bytes


def test_differing_payload_under_same_id_fails_closed(tmp_path: Path) -> None:
    store = ResearchResultStore(tmp_path)
    store.write(research_result(research_result_id="sha256:collide"))
    # Same id, different content: a determinism violation, never a silent overwrite.
    conflicting = research_result(
        research_result_id="sha256:collide", boundary_value="different"
    )
    with pytest.raises(FactorConsistencyError):
        store.write(conflicting)


def test_store_lives_under_given_root(tmp_path: Path) -> None:
    store = ResearchResultStore(tmp_path)
    store.write(research_result())
    assert (tmp_path / "research").is_dir()
    assert store.root == tmp_path
