"""Deterministic derived raw-fact storage (no database).

Phase 3, like Phase 2, deliberately introduces **no database** (requirement 17;
the approved architecture lists DuckDB/Parquet only as a *future* materialization
of this same shape, data-model §10). The derived raw-XBRL representation is a
simple, deterministic, file-based document — one file per parsed instance — that
can be deleted and rebuilt from the immutable Phase 1 artifacts at any time,
reproducing byte-identical output (requirement 13, invariant 18).

This store holds only *derived* state. The authoritative raw bytes remain in the
Phase 1 content-addressed :class:`~openfinance.sec.storage.ArtifactStore`; this
store references them by content hash and **never writes there** (requirements
2, 16). It is safe to delete and regenerate.

Layout under the store root::

    raw_xbrl/<raw_document_id-slug>.json    # one parsed XBRL instance

Each file is a JSON document::

    {
      "raw_xbrl_format_version": 1,
      "transformation_version_id": "sha256:...",
      "document":  { <RawDocument.to_dict()> },
      "contexts":  [ <RawContext.to_dict()>, ... ],   # sorted by context_ref
      "units":     [ <RawUnit.to_dict()>, ... ],      # sorted by unit_id
      "facts":     [ <RawFact.to_dict()>, ... ]       # sorted by raw_fact_id
    }

Why this shape:

* **Deterministic bytes.** Contexts/units/facts are emitted in a stable sorted
  order and written with ``sort_keys=True``; no wall-clock, iteration order, or
  random value appears, so re-serializing the same parsed instance yields
  identical bytes.
* **Content-addressed file name.** The file is named by ``raw_document_id`` (the
  content hash of the source bytes), so the same instance always lands in the
  same file and re-parsing overwrites it idempotently.
* **Rebuildable.** Nothing here is authoritative — the Phase 1 store is. Deleting
  a file and re-parsing regenerates it exactly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from openfinance.xbrl.contexts import RawContext
from openfinance.xbrl.model import RawDocument, RawFact
from openfinance.xbrl.parser import ParsedInstance
from openfinance.xbrl.units import RawUnit

__all__ = ["RAW_XBRL_FORMAT_VERSION", "RawXbrlStore"]

#: On-disk container format version. Distinct from the *parser* version
#: (:data:`~openfinance.xbrl.version.XBRL_PARSER_VERSION`): this governs the file
#: envelope, that governs the derived record content.
RAW_XBRL_FORMAT_VERSION = 1

#: A read-back parsed instance: (document, contexts-by-ref, units-by-id, facts).
ReadInstance = tuple[
    RawDocument,
    dict[str, RawContext],
    dict[str, RawUnit],
    list[RawFact],
]


class RawXbrlStore:
    """A filesystem store for derived raw-XBRL records, one file per instance."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._docs = self._root / "raw_xbrl"

    @property
    def root(self) -> Path:
        return self._root

    def _document_path(self, raw_document_id: str) -> Path:
        # `sha256:<hex>` -> `sha256-<hex>.json`. Derived purely from the content
        # hash of the source bytes; never from a mutable name/path.
        slug = raw_document_id.replace(":", "-")
        return self._docs / f"{slug}.json"

    def write_instance(
        self, parsed: ParsedInstance, transformation_version_id: str
    ) -> Path:
        """Write one parsed instance deterministically; return the file path.

        Contexts, units, and facts are emitted in a stable sorted order so the
        bytes are a pure function of the parsed content (order-independent).
        """
        document = {
            "raw_xbrl_format_version": RAW_XBRL_FORMAT_VERSION,
            "transformation_version_id": transformation_version_id,
            "document": parsed.document.to_dict(),
            "contexts": [
                parsed.contexts[cid].to_dict() for cid in sorted(parsed.contexts)
            ],
            "units": [parsed.units[uid].to_dict() for uid in sorted(parsed.units)],
            "facts": [
                fact.to_dict()
                for fact in sorted(parsed.facts, key=lambda f: f.raw_fact_id)
            ],
        }
        payload = json.dumps(
            document, indent=2, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        path = self._document_path(parsed.document.raw_document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
        with open(tmp_path, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        return path

    def read_instance(self, raw_document_id: str) -> ReadInstance | None:
        """Read one parsed instance back, or ``None`` if not stored."""
        path = self._document_path(raw_document_id)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        document = RawDocument.from_dict(raw["document"])
        contexts = {
            ctx.context_ref: ctx
            for ctx in (
                RawContext.from_dict(c)
                for c in raw.get("contexts", [])
                if isinstance(c, dict)
            )
        }
        units = {
            unit.unit_id: unit
            for unit in (
                RawUnit.from_dict(u)
                for u in raw.get("units", [])
                if isinstance(u, dict)
            )
        }
        facts = [
            RawFact.from_dict(f) for f in raw.get("facts", []) if isinstance(f, dict)
        ]
        return document, contexts, units, facts

    def has_instance(self, raw_document_id: str) -> bool:
        return self._document_path(raw_document_id).exists()

    def list_document_ids(self) -> list[str]:
        """Return the ``raw_document_id`` of every stored instance, sorted."""
        if not self._docs.exists():
            return []
        ids: list[str] = []
        for path in sorted(self._docs.glob("sha256-*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            document = raw.get("document")
            if isinstance(document, dict):
                doc_id = document.get("raw_document_id")
                if isinstance(doc_id, str):
                    ids.append(doc_id)
        return sorted(ids)
