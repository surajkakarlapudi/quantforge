"""Deterministic derived-registry storage (no database).

Phase 2 deliberately introduces **no database**. The derived registry is a
simple, deterministic, file-based representation that can be materialized into
DuckDB/Parquet later (data-model §10) without reshaping. It is *derived state*:
it may be deleted and rebuilt from the immutable acquisition artifacts at any
time, reproducing byte-identical logical records (determinism, §12).

Layout under the registry root::

    registry/filings/<company_id-slug>.json   # one filer's filing records

Each file is a JSON document::

    {
      "registry_format_version": 1,
      "transformation_version_id": "sha256:...",
      "company_id": "cik:0000320193",
      "filings": [ <FilingRecord.to_dict()>, ... ]   # sorted by accession
    }

Why this shape:

* **Deterministic bytes.** Records are sorted by accession number and written
  with ``sort_keys=True``; no wall-clock, ordering, or random value appears, so
  re-serializing the same logical records yields identical bytes.
* **Rebuildable.** Nothing here is authoritative — the content-addressed raw
  store is. Deleting a registry file and rebuilding regenerates it exactly.
* **Never touches raw artifacts.** This store writes only under its own root;
  it reads raw bytes via the Phase 1 ``ArtifactStore`` but never writes there.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from openfinance.registry.identity import cik_from_company_id
from openfinance.registry.model import FilingRecord

__all__ = ["REGISTRY_FORMAT_VERSION", "RegistryStore"]

#: On-disk container format version. Distinct from the *logic* version
#: (:data:`~openfinance.registry.version.REGISTRY_LOGIC_VERSION`): this governs
#: the file envelope, that governs the derived record content.
REGISTRY_FORMAT_VERSION = 1


class RegistryStore:
    """A filesystem store for derived filing records, one file per filer."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._filings = self._root / "filings"

    @property
    def root(self) -> Path:
        return self._root

    def _filing_path(self, company_id: str) -> Path:
        # `cik:0000320193` -> `cik-0000320193.json`. Derived purely from the
        # (stable) CIK; never from a mutable name/ticker.
        cik = cik_from_company_id(company_id)
        return self._filings / f"cik-{cik.zfill(10)}.json"

    def write_company(
        self,
        company_id: str,
        transformation_version_id: str,
        records: list[FilingRecord],
    ) -> Path:
        """Write one filer's records deterministically; return the file path.

        Records are emitted sorted by canonical accession number so the bytes
        are a pure function of the logical record set (order-independent).
        """
        ordered = sorted(records, key=lambda r: r.accession_number)
        document = {
            "registry_format_version": REGISTRY_FORMAT_VERSION,
            "transformation_version_id": transformation_version_id,
            "company_id": company_id,
            "filings": [r.to_dict() for r in ordered],
        }
        payload = json.dumps(
            document, indent=2, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        path = self._filing_path(company_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
        with open(tmp_path, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        return path

    def read_company(self, company_id: str) -> list[FilingRecord]:
        """Read back one filer's records, or an empty list if none stored."""
        path = self._filing_path(company_id)
        if not path.exists():
            return []
        document = json.loads(path.read_text(encoding="utf-8"))
        filings = document.get("filings", [])
        return [FilingRecord.from_dict(row) for row in filings if isinstance(row, dict)]

    def has_company(self, company_id: str) -> bool:
        return self._filing_path(company_id).exists()

    def list_company_ids(self) -> list[str]:
        """Return the ``company_id`` of every filer stored, sorted."""
        if not self._filings.exists():
            return []
        ids: list[str] = []
        for path in sorted(self._filings.glob("cik-*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            cid = document.get("company_id")
            if isinstance(cid, str):
                ids.append(cid)
        return sorted(ids)
