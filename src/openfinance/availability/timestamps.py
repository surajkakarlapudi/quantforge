"""Aware-UTC timestamp parsing/formatting for the availability layer.

Data-model §6.4 / invariant 15: **every** stored timestamp is timezone-aware UTC,
and a naive ``as_of`` is rejected (an ambiguous boundary is a look-ahead risk).
These helpers are the single choke point that enforces that — no other module
parses timestamps ad hoc, so the aware-UTC guarantee cannot be bypassed.

Parsing accepts the two forms SEC and this codebase actually emit — a trailing
``Z`` (EDGAR ``acceptanceDateTime``) and an explicit ``+00:00`` offset — and
canonical serialization always emits the ``Z`` form. A parsed value with a
non-UTC offset is normalized to UTC; a naive string (no offset) is an error.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = [
    "ensure_aware_utc",
    "format_utc_z",
    "parse_utc",
]


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware UTC :class:`datetime`.

    Accepts a trailing ``Z`` or an explicit numeric offset. A naive string (no
    timezone designator) raises :class:`ValueError` — we never assume a zone
    (invariant 15). Any non-UTC offset is converted to UTC.
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp is not timezone-aware: {value!r}")
    return parsed.astimezone(UTC)


def ensure_aware_utc(dt: datetime) -> datetime:
    """Return ``dt`` as aware UTC; raise if it is naive (invariant 15)."""
    if dt.tzinfo is None:
        raise ValueError("datetime is not timezone-aware")
    return dt.astimezone(UTC)


def format_utc_z(dt: datetime) -> str:
    """Serialize an aware UTC instant to canonical ISO-8601 with a ``Z`` suffix."""
    dt = ensure_aware_utc(dt)
    # isoformat() yields "+00:00"; normalize to the compact "Z" form we store.
    return dt.isoformat().replace("+00:00", "Z")
