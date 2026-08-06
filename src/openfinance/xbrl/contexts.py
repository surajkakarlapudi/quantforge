"""Raw XBRL context modeling.

A context binds a fact to *who*, *when*, and *in what dimensional slice*. Data
model §3.1/§6.2 and requirement 8 require the context identity to preserve:
entity, period (instant vs duration, with start/end), and the full dimensional
segment (explicit members, typed members) — nothing discarded.

A :class:`RawContext` is the context **exactly as parsed**:

* ``entity_identifier`` / ``entity_scheme`` — the ``<entity><identifier>`` value
  and its ``scheme`` (typically the SEC CIK under the EDGAR scheme). Preserved
  verbatim; never reinterpreted as our ``company_id`` here.
* ``period_type`` — ``instant`` or ``duration`` (or ``forever``, tolerated).
* ``instant`` / ``start`` / ``end`` — the raw period dates as written.
* ``dimensions`` — the tuple of :class:`RawDimension`, from which the
  deterministic ``dimensions_hash`` is derived.

The context's own ``id`` attribute (``context_ref``) is document-local — facts
reference it via ``contextRef`` — and is preserved for provenance and used as the
``xbrl_context_ref`` component of ``raw_fact_id`` (§11), exactly as SEC wrote it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from openfinance.xbrl.dimensions import RawDimension, dimensions_hash

__all__ = ["PeriodType", "RawContext"]


class PeriodType(StrEnum):
    """The kind of period a context carries (XBRL ``<period>`` shape)."""

    #: A point in time — ``<instant>`` (balance-sheet items).
    INSTANT = "instant"
    #: A span — ``<startDate>``/``<endDate>`` (flow items).
    DURATION = "duration"
    #: ``<forever>`` — rare, tolerated and preserved rather than rejected.
    FOREVER = "forever"


@dataclass(frozen=True, slots=True)
class RawContext:
    """One XBRL context, exactly as parsed (entity, period, dimensions).

    Immutable and self-describing: given a context, the deterministic
    ``dimensions_hash`` is a pure function of its dimensions, so segmented facts
    never collide with the consolidated fact (requirement 4, data-model §6.2).
    """

    context_ref: str
    entity_identifier: str
    entity_scheme: str
    period_type: PeriodType
    instant: str | None = None
    start: str | None = None
    end: str | None = None
    dimensions: tuple[RawDimension, ...] = ()

    @property
    def dimensions_hash(self) -> str:
        """Deterministic hash of the dimensional segment (§3.1, §15.5)."""
        return dimensions_hash(self.dimensions)

    def to_dict(self) -> dict[str, object]:
        return {
            "context_ref": self.context_ref,
            "entity_identifier": self.entity_identifier,
            "entity_scheme": self.entity_scheme,
            "period_type": self.period_type.value,
            "instant": self.instant,
            "start": self.start,
            "end": self.end,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "dimensions_hash": self.dimensions_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RawContext:
        raw_dims = raw.get("dimensions", [])
        dimensions = tuple(
            RawDimension.from_dict(d)
            for d in (raw_dims if isinstance(raw_dims, list) else [])
            if isinstance(d, dict)
        )
        return cls(
            context_ref=_req_str(raw, "context_ref"),
            entity_identifier=_req_str(raw, "entity_identifier"),
            entity_scheme=_req_str(raw, "entity_scheme"),
            period_type=PeriodType(_req_str(raw, "period_type")),
            instant=_opt_str(raw, "instant"),
            start=_opt_str(raw, "start"),
            end=_opt_str(raw, "end"),
            dimensions=dimensions,
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
