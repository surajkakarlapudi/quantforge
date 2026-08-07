"""Deterministic builders for Phase 7 metric tests.

Construct minimal canonical :class:`Fact` records and a matching
:class:`PointInTimeResolver`, so a test can drive the metric evaluator over a
hand-built world without the full XBRL → canonical → availability pipeline.

The load-bearing detail these builders get right (unlike the Phase 5
``tests/availability/builders.py`` shortcut) is the **consolidated**
``dimensions_hash``: a metric input is resolved only against the undimensioned
observation, so a consolidated fact must carry ``dimensions_hash(())`` — the
sha256 of the empty sentinel — exactly what real canonicalization writes and what
:mod:`openfinance.metrics.resolve_input` matches against. A dimensional fact is
built with a real ``(axis, member)`` hash instead, so it is correctly *ignored*.

Everything is a pure function of its inputs — no wall-clock, no network.
"""

from __future__ import annotations

from datetime import datetime

from openfinance.availability.model import (
    AvailabilityStatus,
    FilingAvailability,
    FilingEvidence,
)
from openfinance.availability.resolve import PointInTimeResolver
from openfinance.availability.timestamps import parse_utc
from openfinance.canonical.concept import Concept
from openfinance.canonical.model import Fact, FactProvenance, fact_id, obs_key
from openfinance.canonical.taxonomy import Taxonomy
from openfinance.registry.identity import company_id as _company_id
from openfinance.registry.identity import filing_id as _filing_id
from openfinance.xbrl.contexts import PeriodType
from openfinance.xbrl.dimensions import RawDimension, dimensions_hash

TV = "sha256:testtransform"
CIK = 320193

#: The hash a consolidated (undimensioned) fact carries — what the resolver
#: matches. Built from the Phase 3 primitive so it can never drift from source.
CONSOLIDATED = dimensions_hash(())


def utc(iso: str) -> datetime:
    """Parse an ISO-8601 UTC instant to an aware ``datetime`` (test convenience)."""
    return parse_utc(iso)


def _us_gaap_clark(local_name: str, *, year: int = 2023) -> str:
    return f"{{http://fasb.org/us-gaap/{year}}}{local_name}"


def _segment_hash(axis: str, member: str) -> str:
    """A real dimensional hash for a single explicit segment (never consolidated)."""
    return dimensions_hash(
        (
            RawDimension(
                axis=axis,
                member=member,
                is_typed=False,
                typed_child=None,
                typed_text=None,
            ),
        )
    )


def fact(
    *,
    accession: str,
    local_name: str,
    value: str | None,
    period_type: PeriodType = PeriodType.INSTANT,
    period_start: str | None = None,
    period_end: str = "2023-09-30",
    unit: str = "USD",
    currency: str | None = "USD",
    unit_ref: str = "usd",
    is_nil: bool = False,
    value_text: str | None = None,
    taxonomy: Taxonomy = Taxonomy.US_GAAP,
    year: int = 2023,
    dimension: tuple[str, str] | None = None,
    cik: int = CIK,
) -> Fact:
    """Build one canonical :class:`Fact`, consolidated unless ``dimension`` is set.

    ``value`` populates ``value_numeric_str`` (``None`` for a nil/non-numeric fact).
    A monetary fact carries ``unit == currency`` (e.g. ``"USD"``); a ``pure`` ratio
    or ``shares`` count sets ``unit`` accordingly with ``currency=None``. Pass
    ``dimension=(axis, member)`` to make a *dimensional* fact the resolver must skip.
    """
    clark = (
        _us_gaap_clark(local_name, year=year)
        if taxonomy is Taxonomy.US_GAAP
        else (f"{{http://example.com/custom}}{local_name}")
    )
    company = _company_id(cik)
    filing = _filing_id(accession)
    dims_hash = _segment_hash(*dimension) if dimension is not None else CONSOLIDATED
    key = obs_key(
        company_id=company,
        security_id=None,
        concept_clark=clark,
        period_type=period_type.value,
        period_start=period_start,
        period_end=period_end,
        unit_ref=unit_ref,
        dimensions_hash=dims_hash,
    )
    fid = fact_id(transformation_version_id=TV, filing_id=filing, obs_key_value=key)
    provenance = FactProvenance(
        raw_fact_id=f"raw-{accession}-{local_name}",
        raw_fact_ids=(f"raw-{accession}-{local_name}",),
        raw_document_id="sha256:doc",
        filing_id=filing,
        accession=accession,
        company_id=company,
        source_artifact_sha256="a" * 64,
        source_url="https://example/doc.xml",
        source_document_name="doc.xml",
        transformation_version_id=TV,
    )
    return Fact(
        fact_id=fid,
        obs_key=key,
        company_id=company,
        security_id=None,
        concept=Concept(
            clark=clark,
            namespace_uri=clark[1 : clark.index("}")],
            local_name=local_name,
            taxonomy=taxonomy,
        ),
        taxonomy=taxonomy,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        value_numeric_str=value,
        value_text=value_text,
        is_nil=is_nil,
        unit=unit,
        currency=currency,
        unit_ref=unit_ref,
        unit_numerator=((f"iso4217:{currency}",) if currency is not None else ()),
        unit_denominator=(),
        unit_is_divide=False,
        scale=0,
        decimals=-6,
        raw_value=value,
        raw_scale=None,
        raw_sign=None,
        raw_decimals="-6",
        dimensions=(),
        dimensions_hash=dims_hash,
        filing_id=filing,
        transformation_version_id=TV,
        provenance=provenance,
    )


def instant(
    accession: str, local_name: str, value: str | None, **kwargs: object
) -> Fact:
    """A consolidated INSTANT balance-sheet fact at ``2023-09-30`` (unless set)."""
    return fact(
        accession=accession,
        local_name=local_name,
        value=value,
        period_type=PeriodType.INSTANT,
        **kwargs,  # type: ignore[arg-type]
    )


def duration(
    accession: str,
    local_name: str,
    value: str | None,
    *,
    period_start: str = "2022-10-01",
    period_end: str = "2023-09-30",
    **kwargs: object,
) -> Fact:
    """A consolidated DURATION income/flow fact over FY2023 (unless overridden)."""
    return fact(
        accession=accession,
        local_name=local_name,
        value=value,
        period_type=PeriodType.DURATION,
        period_start=period_start,
        period_end=period_end,
        **kwargs,  # type: ignore[arg-type]
    )


def avail(
    *,
    accession: str,
    timestamp: str,
    status: AvailabilityStatus = AvailabilityStatus.DERIVED,
    policy_id: str | None = "sha256:policy",
    form: str = "10-K",
) -> FilingAvailability:
    """A derived availability triple for one filing (eligible by default)."""
    return FilingAvailability(
        filing_id=_filing_id(accession),
        derived_public_availability_timestamp=timestamp,
        availability_status=status,
        availability_policy_id=policy_id,
        policy_version="edgar-std/v1" if policy_id else None,
        policy_confidence="unvalidated" if policy_id else None,
        policy_status="provisional" if policy_id else None,
        reason="test",
        evidence=FilingEvidence(
            filing_id=_filing_id(accession),
            form=form,
            acceptance_timestamp_utc=timestamp,
            filing_date=None,
            report_date=None,
        ),
    )


def resolver(
    facts: list[Fact], availabilities: dict[str, FilingAvailability]
) -> PointInTimeResolver:
    """A :class:`PointInTimeResolver` over ``facts`` joined to ``availabilities``.

    ``availabilities`` is keyed by ``filing_id`` (use :func:`avail` values and their
    ``filing_id``). Facts whose filing has no availability record are ``unknown``.
    """
    return PointInTimeResolver(facts, availabilities)


def simple_world(
    facts: list[Fact], *, timestamp: str = "2023-11-05T21:30:00Z"
) -> PointInTimeResolver:
    """A resolver where every distinct filing is DERIVED-eligible at ``timestamp``.

    Convenience for the common case where availability is not the thing under test:
    each fact's filing gets one eligible triple at the same instant.
    """
    availabilities: dict[str, FilingAvailability] = {}
    for f in facts:
        if f.filing_id in availabilities:
            continue
        availabilities[f.filing_id] = avail(
            accession=f.provenance.accession, timestamp=timestamp
        )
    return resolver(facts, availabilities)
