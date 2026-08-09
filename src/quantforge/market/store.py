"""Derived market-data storage — file sidecars, one per instrument (§13, D7).

No database (D7): a thin derived store mirroring
:class:`~quantforge.availability.store.AvailabilityStore`, one JSON file per
instrument holding that instrument's canonical
:class:`~quantforge.market.model.PriceObservation` / canonical
:class:`~quantforge.market.model.CorporateAction` records, the
:class:`~quantforge.market.model.Instrument` metadata, and the derived
:class:`~quantforge.market.model.MarketAvailability` sidecars. It is **derived
state — safe to delete and rebuild byte-identically** from the immutable raw tier
(the Phase 1 :class:`~quantforge.sec.storage.ArtifactStore`, reused verbatim under
``<root>/market/raw/``).

Layout under the market root::

    <root>/market/raw/                       # immutable content-addressed vendor bytes
    <root>/market/canonical/security-<slug>.json   # per-instrument canonical records
    <root>/market/availability/security-<slug>.json # per-instrument availability

The ``security_id``'s reserved characters (``:``/``#``) are illegal or awkward in a
filename, so they are slugified to ``-`` exactly as
:class:`~quantforge.availability.store.AvailabilityStore` slugifies ``cik:`` (the id
is kept verbatim *inside* the file, so identity is never lost).

Determinism: records are emitted sorted by their content-addressed id with
``sort_keys=True``; writes are atomic (temp + ``flush`` + ``os.fsync`` +
``os.replace``); no wall-clock/RNG/iteration-order appears. On read, a stored
observation whose recomputed ``price_observation_id`` disagrees with its stored id
fails closed (:class:`~quantforge.market.errors.MarketConsistencyError`).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from quantforge.market.errors import MarketConsistencyError
from quantforge.market.model import (
    CorporateAction,
    Instrument,
    MarketAvailability,
    PriceObservation,
)

__all__ = ["MARKET_FORMAT_VERSION", "MarketDataStore"]

#: On-disk container format version — distinct from any transformation/policy version.
MARKET_FORMAT_VERSION = 1

# Characters legal in a slug; everything else in a security_id collapses to '-'.
_SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(security_id: str) -> str:
    """Slugify a ``security_id`` into a safe filename stem (id kept inside file)."""
    return _SLUG_UNSAFE.sub("-", security_id)


class MarketDataStore:
    """A filesystem store for derived market data, one file per instrument."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._canonical = self._root / "canonical"
        self._availability = self._root / "availability"

    @property
    def root(self) -> Path:
        return self._root

    @property
    def raw_root(self) -> Path:
        """The raw-tier directory (a reused Phase 1 ArtifactStore lives here)."""
        return self._root / "raw"

    # -- canonical tier ------------------------------------------------------

    def _canonical_path(self, security_id: str) -> Path:
        return self._canonical / f"security-{_slug(security_id)}.json"

    def write_instrument(
        self,
        instrument: Instrument,
        observations: list[PriceObservation],
        actions: list[CorporateAction],
        *,
        market_transformation_version_id: str,
    ) -> Path:
        """Write one instrument's canonical records deterministically; return path.

        Observations are emitted sorted by ``price_observation_id`` and actions by
        ``corporate_action_id`` (stable content hashes), so the file is
        byte-identical on every rebuild from the same inputs.
        """
        ordered_obs = sorted(observations, key=lambda o: o.price_observation_id)
        ordered_actions = sorted(actions, key=lambda a: a.corporate_action_id)
        document = {
            "market_format_version": MARKET_FORMAT_VERSION,
            "market_transformation_version_id": market_transformation_version_id,
            "security_id": instrument.security_id,
            "instrument": instrument.to_dict(),
            "observations": [o.to_dict() for o in ordered_obs],
            "corporate_actions": [a.to_dict() for a in ordered_actions],
        }
        return _atomic_write_json(
            self._canonical_path(instrument.security_id), document
        )

    def read_instrument(self, security_id: str) -> Instrument | None:
        """Read back one instrument's metadata (``None`` if not stored)."""
        document = self._read(self._canonical_path(security_id))
        if document is None:
            return None
        raw = document.get("instrument")
        if not isinstance(raw, dict):
            return None
        return Instrument.from_dict(raw)

    def read_observations(self, security_id: str) -> list[PriceObservation]:
        """Read one instrument's canonical observations, verifying integrity.

        A stored observation whose recomputed ``price_observation_id`` disagrees
        with its stored id fails closed
        (:class:`~quantforge.market.errors.MarketConsistencyError`).
        """
        document = self._read(self._canonical_path(security_id))
        if document is None:
            return []
        rows = document.get("observations", [])
        out: list[PriceObservation] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                obs = PriceObservation.from_dict(row)
                stored_id = row.get("price_observation_id")
                if isinstance(stored_id, str) and stored_id != obs.price_observation_id:
                    raise MarketConsistencyError(
                        f"stored price_observation_id {stored_id!r} does not match "
                        f"recomputed {obs.price_observation_id!r} for "
                        f"{security_id!r} — refusing to trust corrupted derived state"
                    )
                out.append(obs)
        return out

    def read_actions(self, security_id: str) -> list[CorporateAction]:
        """Read one instrument's canonical corporate actions, verifying integrity."""
        document = self._read(self._canonical_path(security_id))
        if document is None:
            return []
        rows = document.get("corporate_actions", [])
        out: list[CorporateAction] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                action = CorporateAction.from_dict(row)
                stored_id = row.get("corporate_action_id")
                if (
                    isinstance(stored_id, str)
                    and stored_id != action.corporate_action_id
                ):
                    raise MarketConsistencyError(
                        f"stored corporate_action_id {stored_id!r} does not match "
                        f"recomputed {action.corporate_action_id!r} for "
                        f"{security_id!r} — refusing to trust corrupted derived state"
                    )
                out.append(action)
        return out

    def has_instrument(self, security_id: str) -> bool:
        return self._canonical_path(security_id).exists()

    # -- availability tier ---------------------------------------------------

    def _availability_path(self, security_id: str) -> Path:
        return self._availability / f"security-{_slug(security_id)}.json"

    def write_availability(
        self,
        security_id: str,
        records: list[MarketAvailability],
        market_availability_policy_ids: list[str],
    ) -> Path:
        """Write one instrument's availability sidecars deterministically."""
        ordered = sorted(records, key=lambda r: r.event_date)
        document = {
            "market_format_version": MARKET_FORMAT_VERSION,
            "market_availability_policy_ids": sorted(
                set(market_availability_policy_ids)
            ),
            "security_id": security_id,
            "sessions": [r.to_dict() for r in ordered],
        }
        return _atomic_write_json(self._availability_path(security_id), document)

    def read_availability(self, security_id: str) -> list[MarketAvailability]:
        """Read back one instrument's availability sidecars (empty if none)."""
        document = self._read(self._availability_path(security_id))
        if document is None:
            return []
        rows = document.get("sessions", [])
        if not isinstance(rows, list):
            return []
        return [
            MarketAvailability.from_dict(row) for row in rows if isinstance(row, dict)
        ]

    def read_availability_map(self, security_id: str) -> dict[str, MarketAvailability]:
        """Read one instrument's availability as a ``session_key`` → record mapping."""
        return {rec.session_key: rec for rec in self.read_availability(security_id)}

    def has_availability(self, security_id: str) -> bool:
        return self._availability_path(security_id).exists()

    def list_security_ids(self) -> list[str]:
        """Return the ``security_id`` of every instrument stored, sorted."""
        if not self._canonical.exists():
            return []
        ids: list[str] = []
        for path in sorted(self._canonical.glob("security-*.json")):
            document = self._read(path)
            if document is None:
                continue
            sid = document.get("security_id")
            if isinstance(sid, str):
                ids.append(sid)
        return sorted(ids)

    @staticmethod
    def _read(path: Path) -> dict[str, object] | None:
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MarketConsistencyError(
                f"stored market document {path} could not be decoded: {exc}"
            ) from exc
        if not isinstance(document, dict):
            raise MarketConsistencyError(
                f"stored market document {path} is not an object"
            )
        return document


def _atomic_write_json(path: Path, document: dict[str, object]) -> Path:
    """Write ``document`` as deterministic JSON atomically; return the path."""
    payload = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    return path
