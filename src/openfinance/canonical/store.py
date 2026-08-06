"""Deterministic canonical-fact storage (no database) — requirement 18.

Phase 4, like Phases 2 and 3, deliberately introduces **no database** (the
approved architecture lists DuckDB/Parquet only as a *future* materialization of
this same shape, data-model §10). The canonical representation is a simple,
deterministic, file-based document — one file per canonicalized instance — that
can be deleted and rebuilt from the immutable Phase 1 artifacts (via Phase 3) at
any time, reproducing byte-identical output (requirement 14, invariant 18).

This store holds only *derived* state. The authoritative raw bytes remain in the
Phase 1 content-addressed store; the raw facts remain in the Phase 3
:class:`~openfinance.xbrl.store.RawXbrlStore`. This store references the instance
by its ``raw_document_id`` and **never writes to any other store** (requirement
18: do not create an unrelated second storage system — this reuses the exact
file-store precedent of Phases 2/3). It is safe to delete and regenerate.

Layout under the store root::

    canonical_facts/<raw_document_id-slug>.json    # one canonicalized instance

Each file is a JSON document::

    {
      "canonical_facts_format_version": 1,
      "transformation_version_id": "sha256:...",
      "raw_document_id": "sha256:...",
      "facts": [ <Fact.to_dict()>, ... ]   # sorted by fact_id
    }

Determinism: facts are emitted sorted by ``fact_id`` and written with
``sort_keys=True``; no wall-clock, iteration order, or random value appears, and
the file is named by ``raw_document_id`` (content-addressed), so re-canonicalizing
the same instance overwrites it idempotently with identical bytes. Writes are
atomic (temp file + ``fsync`` + ``os.replace``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from openfinance.canonical.canonicalize import CanonicalizeResult
from openfinance.canonical.model import Fact

__all__ = ["CANONICAL_FACTS_FORMAT_VERSION", "CanonicalFactStore"]

#: On-disk container format version. Distinct from the *normalizer* version
#: (:data:`~openfinance.canonical.version.CANONICAL_FACT_VERSION`): this governs
#: the file envelope, that governs the derived record content.
CANONICAL_FACTS_FORMAT_VERSION = 1


class CanonicalFactStore:
    """A filesystem store for canonical facts, one file per instance."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._facts = self._root / "canonical_facts"

    @property
    def root(self) -> Path:
        return self._root

    def _instance_path(self, raw_document_id: str) -> Path:
        # `sha256:<hex>` -> `sha256-<hex>.json`. Derived purely from the content
        # hash of the source bytes; never from a mutable name/path.
        slug = raw_document_id.replace(":", "-")
        return self._facts / f"{slug}.json"

    def write_instance(
        self, result: CanonicalizeResult, transformation_version_id: str
    ) -> Path:
        """Write one canonicalized instance deterministically; return its path.

        Facts are emitted sorted by ``fact_id`` so the bytes are a pure function
        of the canonical content (order-independent).
        """
        document = {
            "canonical_facts_format_version": CANONICAL_FACTS_FORMAT_VERSION,
            "transformation_version_id": transformation_version_id,
            "raw_document_id": result.raw_document_id,
            "facts": [
                fact.to_dict() for fact in sorted(result.facts, key=lambda f: f.fact_id)
            ],
        }
        payload = json.dumps(
            document, indent=2, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        path = self._instance_path(result.raw_document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
        with open(tmp_path, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        return path

    def read_instance(self, raw_document_id: str) -> list[Fact] | None:
        """Read one canonicalized instance's facts back, or ``None`` if absent."""
        path = self._instance_path(raw_document_id)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Fact.from_dict(f) for f in raw.get("facts", []) if isinstance(f, dict)]

    def has_instance(self, raw_document_id: str) -> bool:
        return self._instance_path(raw_document_id).exists()

    def list_document_ids(self) -> list[str]:
        """Return the ``raw_document_id`` of every stored instance, sorted."""
        if not self._facts.exists():
            return []
        ids: list[str] = []
        for path in sorted(self._facts.glob("sha256-*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            doc_id = raw.get("raw_document_id")
            if isinstance(doc_id, str):
                ids.append(doc_id)
        return sorted(ids)
