"""Tests for content-addressed artifact storage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openfinance.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from openfinance.sec.errors import ArtifactConflictError, StorageError
from openfinance.sec.storage import ArtifactStore


def _artifact(data: bytes, url: str = "https://data.sec.gov/x") -> Artifact:
    return Artifact(
        data=data,
        metadata=AcquisitionMetadata(
            source_url=url,
            artifact_type=ArtifactType.SUBMISSIONS,
            sha256=sha256_hex(data),
            retrieved_at="2026-08-05T00:00:00+00:00",
            http_status=200,
            user_agent="OpenFinance test@example.com",
        ),
    )


def test_store_writes_blob_and_metadata(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    data = b'{"a": 1}'
    result = store.store(_artifact(data))
    assert result.blob_path.exists()
    assert result.metadata_path.exists()
    assert not result.deduplicated
    assert store.read_blob(result.sha256) == data


def test_blob_is_content_addressed(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    data = b"hello sec"
    result = store.store(_artifact(data))
    assert result.sha256 == sha256_hex(data)
    # Sharded path: blobs/<aa>/<full-hash>
    assert result.blob_path.name == result.sha256
    assert result.blob_path.parent.name == result.sha256[:2]


def test_identical_bytes_deduplicate(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    data = b"same bytes"
    first = store.store(_artifact(data, url="https://a"))
    second = store.store(_artifact(data, url="https://b"))
    assert first.sha256 == second.sha256
    assert first.blob_path == second.blob_path
    assert not first.deduplicated
    assert second.deduplicated  # second write recognized existing blob


def test_different_bytes_get_different_blobs(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    r1 = store.store(_artifact(b"one"))
    r2 = store.store(_artifact(b"two"))
    assert r1.blob_path != r2.blob_path
    assert store.read_blob(r1.sha256) == b"one"
    assert store.read_blob(r2.sha256) == b"two"


def test_metadata_mismatch_fails_closed(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    bad = Artifact(
        data=b"actual bytes",
        metadata=AcquisitionMetadata(
            source_url="https://x",
            artifact_type=ArtifactType.SUBMISSIONS,
            sha256=sha256_hex(b"different bytes"),  # wrong hash
            retrieved_at="2026-08-05T00:00:00+00:00",
            http_status=200,
            user_agent="a@b.com",
        ),
    )
    with pytest.raises(StorageError, match="does not match"):
        store.store(bad)


def test_corrupted_blob_detected_on_read(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    result = store.store(_artifact(b"good"))
    # Corrupt the stored blob in place.
    result.blob_path.write_bytes(b"tampered")
    with pytest.raises(ArtifactConflictError):
        store.read_blob(result.sha256)


def test_corrupted_blob_detected_on_dedupe_write(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    data = b"payload"
    result = store.store(_artifact(data))
    result.blob_path.write_bytes(b"corrupted different length")
    # A second store of the same logical content must refuse to treat the
    # corrupted on-disk blob as a valid dedupe target.
    with pytest.raises(ArtifactConflictError):
        store.store(_artifact(data))


def test_metadata_content_is_json_and_complete(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    result = store.store(_artifact(b"x"))
    meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert meta["sha256"] == result.sha256
    assert meta["artifact_type"] == "submissions"
    assert meta["http_status"] == 200
    assert meta["content_length"] is None  # not set on this synthetic artifact


def test_no_temp_files_left_behind(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.store(_artifact(b"clean"))
    leftover = list(tmp_path.rglob("*.tmp"))
    assert leftover == []
