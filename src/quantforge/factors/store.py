"""Write-once, content-addressed ResearchResult sidecar (``docs/factors.md`` §3, F4).

Per Decision F4 the computed :class:`~quantforge.factors.model.ResearchResult` is
materialized to a file sidecar — never a database — for audit and reuse. It stores
the **provenance record only**, not a second copy of the metric arithmetic: factor
*values* remain compute-on-demand (Decision F2), so the sidecar can never drift
from what the Phase 7 engine recomputes.

Like every store in this project it is one JSON file per result, keyed by the
content-addressed ``research_result_id``, mirroring the Phase 5
:class:`~quantforge.availability.store.AvailabilityStore` layout::

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
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar, runtime_checkable

from quantforge.factors.errors import FactorConsistencyError
from quantforge.factors.model import ResearchResult

__all__ = [
    "RESEARCH_RESULT_FORMAT_VERSION",
    "ResearchRecord",
    "ResearchResultStore",
]


@runtime_checkable
class ResearchRecord(Protocol):
    """The minimal shape a record must have to live in the sidecar.

    Phase 8's :class:`~quantforge.factors.model.ResearchResult` and Phase 10's
    :class:`~quantforge.panel.model.PanelResearchResult` both satisfy this — a
    content-addressed id plus a deterministic ``to_dict``. Keeping the store typed
    to this protocol (rather than a single concrete class) is what lets Phase 10
    **reuse** the sidecar's write-once, fail-closed, atomic file I/O instead of
    duplicating it (Decision D4), while each layer keeps its own §9 record schema.
    """

    @property
    def research_result_id(self) -> str: ...

    def to_dict(self) -> dict[str, object]: ...


_RecordT = TypeVar("_RecordT")

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

    def write(self, result: ResearchRecord) -> Path:
        """Persist a research record write-once; return its path.

        Accepts any :class:`ResearchRecord` — the Phase 8
        :class:`~quantforge.factors.model.ResearchResult` or the Phase 10
        :class:`~quantforge.panel.model.PanelResearchResult` — so both layers share
        this one sidecar rather than duplicating its I/O (Decision D4). Idempotent
        when the same result is recomputed (byte-identical payload → a no-op). A
        *differing* payload under an existing ``research_result_id`` is a determinism
        violation and fails closed (:class:`FactorConsistencyError`) — never a silent
        overwrite (§7, §15).
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
        """Read back a stored Phase 8 ResearchResult by id (``None`` if not present)."""
        return self.read_as(research_result_id, ResearchResult.from_dict)

    def read_as(
        self,
        research_result_id: str,
        from_dict: Callable[[dict[str, object]], _RecordT],
    ) -> _RecordT | None:
        """Read back a stored record by id, decoding with ``from_dict``.

        Generic over the record type so Phase 10 can round-trip its own
        :class:`~quantforge.panel.model.PanelResearchResult` through this same
        sidecar (Decision D4) without the store depending on the panel layer.
        Returns ``None`` when the id is not present.
        """
        path = self._result_path(research_result_id)
        if not path.exists():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        raw = document.get("research_result")
        if not isinstance(raw, dict):
            raise FactorConsistencyError(
                f"stored research record {research_result_id} is malformed"
            )
        return from_dict(raw)

    def has(self, research_result_id: str) -> bool:
        return self._result_path(research_result_id).exists()
