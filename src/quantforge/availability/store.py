"""Deterministic sidecar availability storage, keyed by ``filing_id`` (Decision 3).

The availability triple is a *sidecar* over the immutable canonical facts: it is
stored **once per filing** and joined to that filing's facts at query time, never
copied onto or drifting from the Fact rows (invariant 7, 17). This preserves the
Phase 4 invariant that Canonical Facts are content-addressed and never rewritten
when an availability policy changes (Decision 3): a policy change re-derives into
a *new* availability record under a new ``availability_policy_id`` / a new
``DatasetVersion``; the fact store is untouched.

Like every store in this project it introduces **no database** — one JSON file per
filer, mirroring the Phase 2 :class:`~quantforge.registry.store.RegistryStore`
layout so the two align 1:1 by ``company_id``:

    availability/<company_id-slug>.json    # one filer's filing-availability records

Each file::

    {
      "availability_format_version": 1,
      "availability_policy_ids": [ "sha256:...", ... ],   # sorted; policies applied
      "company_id": "cik:0000320193",
      "filings": [ <FilingAvailability.to_dict()>, ... ]  # sorted by filing_id
    }

Determinism: records are emitted sorted by ``filing_id`` with ``sort_keys=True``;
no wall-clock/ordering/random value appears; writes are atomic (temp + ``fsync`` +
``os.replace``). It is derived state — safe to delete and rebuild byte-identically.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from quantforge.availability.model import FilingAvailability
from quantforge.registry.identity import cik_from_company_id

__all__ = ["AVAILABILITY_FORMAT_VERSION", "AvailabilityStore"]

#: On-disk container format version — distinct from any policy/logic version.
AVAILABILITY_FORMAT_VERSION = 1


class AvailabilityStore:
    """A filesystem store for derived filing availability, one file per filer."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._avail = self._root / "availability"

    @property
    def root(self) -> Path:
        return self._root

    def _company_path(self, company_id: str) -> Path:
        # `cik:0000320193` -> `cik-0000320193.json`; mirrors RegistryStore exactly
        # so a filer's registry and availability files line up by name.
        cik = cik_from_company_id(company_id)
        return self._avail / f"cik-{cik.zfill(10)}.json"

    def write_company(
        self,
        company_id: str,
        records: list[FilingAvailability],
        availability_policy_ids: list[str],
    ) -> Path:
        """Write one filer's availability records deterministically; return path.

        Records are emitted sorted by ``filing_id`` and the applied policy id set
        is stored (sorted) so the file self-describes which policy versions
        produced it (feeding the :class:`DatasetVersion` manifest).
        """
        ordered = sorted(records, key=lambda r: r.filing_id)
        document = {
            "availability_format_version": AVAILABILITY_FORMAT_VERSION,
            "availability_policy_ids": sorted(set(availability_policy_ids)),
            "company_id": company_id,
            "filings": [r.to_dict() for r in ordered],
        }
        payload = json.dumps(
            document, indent=2, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        path = self._company_path(company_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
        with open(tmp_path, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        return path

    def read_company(self, company_id: str) -> list[FilingAvailability]:
        """Read back one filer's availability records (empty list if none)."""
        path = self._company_path(company_id)
        if not path.exists():
            return []
        document = json.loads(path.read_text(encoding="utf-8"))
        filings = document.get("filings", [])
        return [
            FilingAvailability.from_dict(row)
            for row in filings
            if isinstance(row, dict)
        ]

    def read_company_map(self, company_id: str) -> dict[str, FilingAvailability]:
        """Read one filer's availability as a ``filing_id`` → record mapping."""
        return {rec.filing_id: rec for rec in self.read_company(company_id)}

    def has_company(self, company_id: str) -> bool:
        return self._company_path(company_id).exists()

    def list_company_ids(self) -> list[str]:
        """Return the ``company_id`` of every filer stored, sorted."""
        if not self._avail.exists():
            return []
        ids: list[str] = []
        for path in sorted(self._avail.glob("cik-*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            cid = document.get("company_id")
            if isinstance(cid, str):
                ids.append(cid)
        return sorted(ids)
