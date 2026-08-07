"""Content-addressed, immutable raw artifact storage.

Artifacts are keyed by the SHA-256 of their bytes. This gives three properties
the acquisition layer depends on:

* **Deduplication** — identical bytes fetched twice occupy one blob.
* **Immutability** — a blob's name *is* its content hash, so it can never be
  overwritten with different bytes; a differing payload has a different name.
* **Integrity** — a blob can be re-verified by re-hashing it.

Writes are atomic: bytes are streamed to a temporary file in the same
directory and hashed, then ``os.replace``'d into place (an atomic rename on a
single filesystem). An interrupted download leaves only a temp file, never a
blob that appears valid, so *"a failed download never appears as a valid
immutable artifact."*

Storage layout (all under ``storage_dir``)::

    blobs/<aa>/<full-sha256>            # immutable content-addressed bytes
    meta/<artifact_type>/<key>.json     # one provenance record per retrieval

The two-character shard prefix (``<aa>``) keeps directory sizes manageable.
Metadata is stored separately from blobs because one blob may be produced by
several retrievals (same bytes, different times/URLs); each retrieval appends
its own metadata record without touching the immutable blob.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator
from pathlib import Path

from quantforge.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    sha256_hex,
)
from quantforge.sec.errors import ArtifactConflictError, StorageError

__all__ = ["ArtifactStore", "StoreResult"]


class StoreResult:
    """Outcome of a store operation."""

    __slots__ = ("blob_path", "deduplicated", "metadata_path", "sha256")

    def __init__(
        self,
        sha256: str,
        blob_path: Path,
        metadata_path: Path,
        *,
        deduplicated: bool,
    ) -> None:
        self.sha256 = sha256
        self.blob_path = blob_path
        self.metadata_path = metadata_path
        #: True if the blob already existed with identical bytes.
        self.deduplicated = deduplicated


class ArtifactStore:
    """A filesystem content-addressed store for raw SEC artifacts."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._blobs = self._root / "blobs"
        self._meta = self._root / "meta"

    @property
    def root(self) -> Path:
        return self._root

    def blob_path(self, sha256: str) -> Path:
        """Return the on-disk path a blob with ``sha256`` occupies."""
        return self._blobs / sha256[:2] / sha256

    def has_blob(self, sha256: str) -> bool:
        return self.blob_path(sha256).exists()

    def iter_metadata(self) -> Iterator[AcquisitionMetadata]:
        """Yield every stored provenance record.

        Read-only enumeration of the acquisition metadata already on disk, for
        consumers (e.g. a derived registry) that reconstruct state from what
        was previously acquired. Records that cannot be read or parsed are
        skipped — enumeration never fails on one bad file, and the immutable
        blobs are never touched. Iteration order is unspecified; callers that
        need determinism must sort.
        """
        if not self._meta.exists():
            return
        for meta_file in sorted(self._meta.rglob("*.json")):
            try:
                raw = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict):
                continue
            try:
                yield AcquisitionMetadata.from_dict(raw)
            except ValueError:
                continue

    def read_blob(self, sha256: str) -> bytes:
        """Read a blob back, verifying it still matches its content address."""
        path = self.blob_path(sha256)
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"no blob for {sha256}") from exc
        actual = sha256_hex(data)
        if actual != sha256:
            raise ArtifactConflictError(sha256, actual)
        return data

    def store(self, artifact: Artifact) -> StoreResult:
        """Persist an artifact's bytes and metadata.

        The bytes are written atomically to their content-addressed blob path
        (deduplicated if already present with identical content), and the
        provenance record is written alongside. The recorded SHA-256 is
        verified against the actual bytes before anything is committed, so a
        metadata/content mismatch fails closed.
        """
        sha256 = artifact.sha256
        actual = sha256_hex(artifact.data)
        if actual != sha256:
            raise StorageError(
                f"metadata sha256 {sha256} does not match bytes ({actual})"
            )

        blob_path = self.blob_path(sha256)
        deduplicated = self._write_blob_atomically(blob_path, artifact.data)
        metadata_path = self._write_metadata(artifact.metadata, sha256)
        return StoreResult(sha256, blob_path, metadata_path, deduplicated=deduplicated)

    def _write_blob_atomically(self, blob_path: Path, data: bytes) -> bool:
        """Write ``data`` to ``blob_path`` atomically. Return True if deduped.

        If the blob already exists we verify its content address rather than
        rewrite it: identical bytes are a no-op dedupe; corrupted bytes raise.
        """
        if blob_path.exists():
            existing = blob_path.read_bytes()
            existing_hash = sha256_hex(existing)
            if existing_hash != blob_path.name:
                # On-disk corruption: the stored bytes no longer match the name.
                raise ArtifactConflictError(blob_path.name, existing_hash)
            # Name matched content and content is addressed by hash, so bytes
            # are provably identical to ``data``. Dedupe.
            return True

        blob_path.parent.mkdir(parents=True, exist_ok=True)
        # Unique temp name per PID avoids collisions between concurrent writers
        # racing to materialize the same blob; the final rename is atomic and
        # last-writer-wins is safe because all writers produce identical bytes.
        tmp_path = blob_path.parent / f".{blob_path.name}.{os.getpid()}.tmp"
        try:
            with open(tmp_path, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, blob_path)
        except OSError as exc:
            raise StorageError(f"failed to write blob {blob_path.name}: {exc}") from exc
        finally:
            # Clean up the temp file if the rename never happened (e.g. another
            # writer won the race, or an error occurred mid-write).
            if tmp_path.exists():
                with contextlib.suppress(OSError):
                    tmp_path.unlink()
        return False

    def _write_metadata(self, metadata: AcquisitionMetadata, sha256: str) -> Path:
        meta_dir = self._meta / metadata.artifact_type.value
        meta_dir.mkdir(parents=True, exist_ok=True)
        # Key metadata by content hash; a second retrieval of identical bytes
        # overwrites with an equivalent record (idempotent).
        metadata_path = meta_dir / f"{sha256}.json"
        payload = json.dumps(metadata.to_dict(), indent=2, sort_keys=True).encode(
            "utf-8"
        )
        tmp_path = meta_dir / f".{sha256}.{os.getpid()}.json.tmp"
        try:
            with open(tmp_path, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, metadata_path)
        except OSError as exc:
            raise StorageError(f"failed to write metadata for {sha256}: {exc}") from exc
        finally:
            if tmp_path.exists():
                with contextlib.suppress(OSError):
                    tmp_path.unlink()
        return metadata_path
