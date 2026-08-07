"""Deterministic helpers for Phase 4 canonicalization tests.

These build on the Phase 3 XBRL instance builders (``tests/xbrl/builders.py``)
so the canonical tests exercise the *real* raw-fact pipeline — instance bytes →
:func:`parse_instance` → :class:`ParsedInstance` → :class:`Canonicalizer` — rather
than hand-constructing :class:`RawFact` records that might drift from what the
parser actually emits. Everything stays offline and deterministic (no network, no
wall-clock, stable element order).
"""

from __future__ import annotations

from quantforge.canonical.canonicalize import Canonicalizer, CanonicalizeResult
from quantforge.canonical.model import Fact
from quantforge.xbrl.parser import ParsedInstance, parse_instance
from tests.xbrl.builders import InstanceBuilder, source_identity


def parse(
    builder: InstanceBuilder,
    *,
    cik: int = 320193,
    accession: str = "0000320193-23-000106",
    filename: str = "aapl-20230930_htm.xml",
) -> ParsedInstance:
    """Parse a built instance into a :class:`ParsedInstance` (offline)."""
    data = builder.to_bytes()
    identity = source_identity(
        cik=cik, accession=accession, filename=filename, data=data
    )
    return parse_instance(data, identity)


def canonicalize(
    builder: InstanceBuilder,
    *,
    cik: int = 320193,
    accession: str = "0000320193-23-000106",
    filename: str = "aapl-20230930_htm.xml",
) -> CanonicalizeResult:
    """Build, parse, and canonicalize an instance in one step."""
    return Canonicalizer().canonicalize(
        parse(builder, cik=cik, accession=accession, filename=filename)
    )


def facts(
    builder: InstanceBuilder,
    *,
    cik: int = 320193,
    accession: str = "0000320193-23-000106",
    filename: str = "aapl-20230930_htm.xml",
) -> tuple[Fact, ...]:
    """Return just the canonical facts for a built instance."""
    return canonicalize(builder, cik=cik, accession=accession, filename=filename).facts


def fact_ids(canonical_facts: tuple[Fact, ...]) -> set[str]:
    """The set of ``fact_id`` values (for distinctness assertions)."""
    return {f.fact_id for f in canonical_facts}
