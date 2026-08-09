"""PIT / REVISED market result types and the price series (§8, §9, D9, §17).

The market analogue of :mod:`quantforge.availability.resolve`'s ``PitValue`` /
``RevisedValue`` and :mod:`quantforge.metrics.model`'s PIT/REVISED metric types,
carrying the invariant-27/28 discipline one domain over:

* :class:`PitPrice` / :class:`RevisedPrice` — **distinct** frozen result types for a
  single ``(security_id, trading_date, field)`` price. A consumer typed to
  ``PitPrice`` (a future backtester) structurally cannot be handed a
  :class:`RevisedPrice`; the only bridge is the explicit, re-resolving
  :meth:`RevisedPrice.reinterpret_as_pit` (never a cast).
* :class:`PriceProvenance` — the audit chain from a resolved price back to the
  winning observation, the discarded correction candidates, the availability policy,
  and the boundary (§15). Present for both ``KNOWN`` and ``UNDEFINED`` prices — an
  undefined price records exactly *why* (zero information loss).
* :class:`PitPriceSeries` — one :class:`PitPrice` cell per date on a declared
  :class:`~quantforge.market.axis.PriceAxis`, UNDEFINED-preserving; the Phase 12
  hand-off surface (§17). There is deliberately **no** ``RevisedPriceSeries``: the
  hand-off is PIT-only.

Every field is deterministically serializable; no wall-clock, RNG, or iteration
order enters any value (invariant 13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

from quantforge.availability.timestamps import format_utc_z, parse_utc
from quantforge.market.model import PriceField, PriceStatus, PriceUndefinedReason

__all__ = [
    "PitPrice",
    "PitPriceSeries",
    "PriceProvenance",
    "RevisedPrice",
]


@dataclass(frozen=True, slots=True)
class PriceProvenance:
    """The unbroken chain from a resolved price back to raw bytes + boundary (§15).

    ``boundary_kind`` is ``"pit"`` or ``"rev"``; ``boundary_value`` is the aware-UTC
    ``as_of`` (PIT) or the ``dataset_version_id`` (REVISED). ``present_candidates``
    lists every ``price_observation_id`` that was also present for the key (vendor
    corrections that lost or won the total-order selection), so a corrected price is
    as auditable as a fundamental fact. Present for both ``KNOWN`` and ``UNDEFINED``
    results.
    """

    market_transformation_version_id: str
    boundary_kind: str
    boundary_value: str
    selected_price_observation_id: str | None
    selected_raw_document_sha256: str | None
    selected_source_id: str | None
    availability_policy_id: str | None
    availability_timestamp: str | None
    present_candidates: tuple[str, ...]
    eligible_count: int
    result_status: PriceStatus
    result_reason: PriceUndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "market_transformation_version_id": self.market_transformation_version_id,
            "boundary_kind": self.boundary_kind,
            "boundary_value": self.boundary_value,
            "selected_price_observation_id": self.selected_price_observation_id,
            "selected_raw_document_sha256": self.selected_raw_document_sha256,
            "selected_source_id": self.selected_source_id,
            "availability_policy_id": self.availability_policy_id,
            "availability_timestamp": self.availability_timestamp,
            "present_candidates": list(self.present_candidates),
            "eligible_count": self.eligible_count,
            "result_status": self.result_status.value,
            "result_reason": (
                self.result_reason.value if self.result_reason is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PriceProvenance:
        candidates = raw.get("present_candidates", [])
        reason = raw.get("result_reason")
        count = raw.get("eligible_count", 0)
        return cls(
            market_transformation_version_id=_req_str(
                raw, "market_transformation_version_id"
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            boundary_value=_req_str(raw, "boundary_value"),
            selected_price_observation_id=_opt_str(
                raw, "selected_price_observation_id"
            ),
            selected_raw_document_sha256=_opt_str(raw, "selected_raw_document_sha256"),
            selected_source_id=_opt_str(raw, "selected_source_id"),
            availability_policy_id=_opt_str(raw, "availability_policy_id"),
            availability_timestamp=_opt_str(raw, "availability_timestamp"),
            present_candidates=tuple(c for c in candidates if isinstance(c, str))
            if isinstance(candidates, list)
            else (),
            eligible_count=count if isinstance(count, int) else 0,
            result_status=PriceStatus(_req_str(raw, "result_status")),
            result_reason=(
                PriceUndefinedReason(reason) if isinstance(reason, str) else None
            ),
        )


class _PriceBaseFields(TypedDict):
    """The shared price fields, typed so ``**base`` unpacking is checkable."""

    security_id: str
    trading_date: str
    field: PriceField
    status: PriceStatus
    value_numeric_str: str | None
    currency: str | None
    reason: PriceUndefinedReason | None
    provenance: PriceProvenance


@dataclass(frozen=True, slots=True)
class _PriceBase:
    """Fields shared by the PIT and REVISED price result types (§8)."""

    security_id: str
    trading_date: str
    field: PriceField
    status: PriceStatus
    value_numeric_str: str | None
    currency: str | None
    reason: PriceUndefinedReason | None
    provenance: PriceProvenance

    @property
    def is_known(self) -> bool:
        return self.status is PriceStatus.KNOWN

    def _base_dict(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "trading_date": self.trading_date,
            "field": self.field.value,
            "status": self.status.value,
            "value_numeric": self.value_numeric_str,
            "currency": self.currency,
            "reason": self.reason.value if self.reason is not None else None,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PitPrice(_PriceBase):
    """A price knowable as of a historical instant — a **PIT** result (§8, D9).

    A distinct type from :class:`RevisedPrice` (invariant 28): a factor/backtester
    typed to ``PitPrice`` structurally cannot consume revised history. ``status ==
    UNDEFINED`` with ``reason`` set means no eligible observation existed by
    ``as_of`` (a legitimate "not yet knowable" answer, not an error). This is the
    typed Phase 12 hand-off (§17).
    """

    as_of: datetime = field(kw_only=True)

    def to_dict(self) -> dict[str, object]:
        data = self._base_dict()
        data["mode"] = "pit"
        data["as_of"] = format_utc_z(self.as_of)
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PitPrice:
        base = _base_from_dict(raw)
        as_of_raw = raw["as_of"]
        if not isinstance(as_of_raw, str):
            raise ValueError("as_of must be a string")
        return cls(as_of=parse_utc(as_of_raw), **base)


@dataclass(frozen=True, slots=True)
class RevisedPrice(_PriceBase):
    """The latest known price over a pinned snapshot — a **REVISED** result (§9, D9).

    Deliberately *not* interchangeable with :class:`PitPrice`. To use a revised
    price in a PIT context the caller must call :meth:`reinterpret_as_pit` with an
    explicit ``as_of`` — an auditable, re-resolving conversion, never an implicit
    cast (invariant 28). ``dataset_version_id`` pins the ingestion frontier so the
    answer is reproducible (invariants 21, 30).
    """

    dataset_version_id: str = field(kw_only=True)

    def to_dict(self) -> dict[str, object]:
        data = self._base_dict()
        data["mode"] = "revised"
        data["dataset_version_id"] = self.dataset_version_id
        return data

    def reinterpret_as_pit(self, resolver: object, as_of: datetime) -> PitPrice:
        """Explicit, auditable conversion to a PIT price at ``as_of``.

        This does **not** reuse the revised winner; it re-runs the PIT resolution at
        ``as_of`` over the same history (§9), so the result genuinely reflects what
        was knowable then. ``resolver`` is a
        :class:`~quantforge.market.resolve.MarketPointInTimeResolver`; typed as
        ``object`` here only to avoid a module import cycle.
        """
        from quantforge.market.resolve import MarketPointInTimeResolver

        if not isinstance(resolver, MarketPointInTimeResolver):
            raise TypeError("reinterpret_as_pit requires a MarketPointInTimeResolver")
        return resolver.price_as_of(
            self.security_id, self.trading_date, as_of, field=self.field
        )

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RevisedPrice:
        base = _base_from_dict(raw)
        dv_raw = raw["dataset_version_id"]
        if not isinstance(dv_raw, str):
            raise ValueError("dataset_version_id must be a string")
        return cls(dataset_version_id=dv_raw, **base)


@dataclass(frozen=True, slots=True)
class PitPriceSeries:
    """A PIT price cell per date on a declared axis — the Phase 12 hand-off (§17).

    One :class:`PitPrice` per axis date, at a single ``as_of`` and ``field`` (or the
    adjusted view). UNDEFINED-preserving: a date the source never reported, or one
    not knowable by ``as_of``, is a first-class ``UNDEFINED`` cell — never dropped,
    never forward-filled (§8). There is intentionally **no** ``RevisedPriceSeries``:
    the hand-off is PIT-only, so a backtester can only ever consume look-ahead-free
    prices. ``adjusted`` records whether these are unadjusted canonical prices or a
    derived split/dividend view (with ``adjustment_version`` / ``adjusted_series_id``
    then populated).
    """

    security_id: str
    field: PriceField
    as_of: datetime
    axis_id: str
    cells: tuple[PitPrice, ...]
    adjusted: bool = False
    adjustment_version: str | None = None
    adjusted_series_id: str | None = None

    @property
    def known_count(self) -> int:
        return sum(1 for c in self.cells if c.is_known)

    def __len__(self) -> int:
        return len(self.cells)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.cells)

    def to_dict(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "field": self.field.value,
            "as_of": format_utc_z(self.as_of),
            "axis_id": self.axis_id,
            "adjusted": self.adjusted,
            "adjustment_version": self.adjustment_version,
            "adjusted_series_id": self.adjusted_series_id,
            "cells": [c.to_dict() for c in self.cells],
        }


def _base_from_dict(raw: dict[str, object]) -> _PriceBaseFields:
    """Reconstruct the shared price fields from a serialized dict."""
    prov_raw = raw["provenance"]
    if not isinstance(prov_raw, dict):
        raise ValueError("provenance must be an object")
    reason = raw.get("reason")
    return _PriceBaseFields(
        security_id=_req_str(raw, "security_id"),
        trading_date=_req_str(raw, "trading_date"),
        field=PriceField(_req_str(raw, "field")),
        status=PriceStatus(_req_str(raw, "status")),
        value_numeric_str=_opt_str(raw, "value_numeric"),
        currency=_opt_str(raw, "currency"),
        reason=PriceUndefinedReason(reason) if isinstance(reason, str) else None,
        provenance=PriceProvenance.from_dict(prov_raw),
    )


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value
