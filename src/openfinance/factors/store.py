"""Write-once, content-addressed ResearchResult sidecar (``docs/factors.md`` §3, F4).

Per Decision F4 the computed :class:`~openfinance.factors.model.ResearchResult` is
materialized to a file sidecar — never a database — for audit and reuse. It stores
the **provenance record only**, not a second copy of the metric arithmetic: factor
*values* remain compute-on-demand (Decision F2), so the sidecar can never drift
from what the Phase 7 engine recomputes.

Like every store in this project it is one JSON file per result, keyed by the
content-addressed ``research_result_id``, mirroring the Phase 5
:class:`~openfinance.availability.store.AvailabilityStore` layout::

    research/sha256-<hex>.json    # one computed ResearchResult

(The ``sha256:`` id's colon is illegal in a Windows filename, so it is slugified
to ``sha256-<hex>`` exactly as ``AvailabilityStore`` slugifies ``cik:`` — the id
itself is stored verbatim *inside* the file.)

**Write-once, fail-closed (§7, §15).** Writing a result whose id already exists is
a no-op *iff* the stored payload is byte-identical (idempotent recompute); a
*differing* payload under the same id is a determinism violation and raises
:class:`FactorConsistencyError` — the store never silently overwrites. Writes are
atomic (temp + ``fsync`` + ``os.replace``) and deterministic
(``indent=2, sort_keys=True``); it is derived state, safe to delete and rebuild
byte-identically.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from openfinance.factors.errors import FactorConsistencyError
from openfinance.factors.model import ResearchResult

__all__ = ["RESEARCH_RESULT_FORMAT_VERSION", "ResearchResultStore"]

#: On-disk container format version — distinct from any factor/engine logic version.
RESEARCH_RESULT_FORMAT_VERSION = 1


class ResearchResultStore:
    """A filesystem store for computed ResearchResults, one file per result."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._dir = self._root / "research"

    @property
    def root(self) -> Path:
        return self._root

    def _result_path(self, research_result_id: str) -> Path:
        # `sha256:abc…` -> `sha256-abc….json`; the colon is illegal on Windows, so
        # slugify it exactly as AvailabilityStore slugifies `cik:` (the id is kept
        # verbatim inside the file, so identity is never lost).
        slug = research_result_id.replace(":", "-")
        return self._dir / f"{slug}.json"

    def write(self, result: ResearchResult) -> Path:
        """Persist a ResearchResult write-once; return its path.

        Idempotent when the same result is recomputed (byte-identical payload → a
        no-op). A *differing* payload under an existing ``research_result_id`` is a
        determinism violation and fails closed (:class:`FactorConsistencyError`) —
        never a silent overwrite (§7, §15).
        """
        document = {
            "research_result_format_version": RESEARCH_RESULT_FORMAT_VERSION,
            "research_result": result.to_dict(),
        }
        payload = json.dumps(
            document, indent=2, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        path = self._result_path(result.research_result_id)
        if path.exists():
            existing = path.read_bytes()
            if existing == payload:
                return path  # idempotent recompute — nothing to do
            raise FactorConsistencyError(
                f"ResearchResult {result.research_result_id} already stored with a "
                "different payload; a content-addressed id must be reproducible — "
                "refusing to overwrite"
            )

        self._dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self._dir / f".{path.name}.{os.getpid()}.tmp"
        with open(tmp_path, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        return path

    def read(self, research_result_id: str) -> ResearchResult | None:
        """Read back a stored ResearchResult by id (``None`` if not present)."""
        path = self._result_path(research_result_id)
        if not path.exists():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        raw = document.get("research_result")
        if not isinstance(raw, dict):
            raise FactorConsistencyError(
                f"stored ResearchResult {research_result_id} is malformed"
            )
        return ResearchResult.from_dict(raw)

    def has(self, research_result_id: str) -> bool:
        return self._result_path(research_result_id).exists()
