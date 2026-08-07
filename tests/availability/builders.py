"""Deterministic builders for Phase 5 availability / point-in-time tests.

Construct :class:`FilingEvidence`, derived :class:`FilingAvailability`, and
minimal canonical :class:`Fact` records that share an ``obs_key`` across filings —
so a test can model the §KS.3 restatement (two filings asserting the same
``obs_key`` at different availability) without going through the full XBRL
pipeline. Everything is a pure function of its inputs (no wall-clock, no network).
"""

from __future__ import annotations

from quantforge.availability.model import (
    AvailabilityStatus,
    FilingAvailability,
    FilingEvidence,
)
from quantforge.canonical.concept import Concept
from quantforge.canonical.model import Fact, FactProvenance, fact_id, obs_key
from quantforge.canonical.taxonomy import Taxonomy
from quantforge.registry.identity import company_id as _company_id
from quantforge.registry.identity import filing_id as _filing_id
from quantforge.xbrl.contexts import PeriodType

TV = "sha256:testtransform"


def evidence(
    *,
    accession: str,
    form: str = "10-K",
    acceptance: str | None,
    filing_date: str | None = None,
    report_date: str | None = None,
    dissemination: str | None = None,
    retrieved_at: str | None = "2026-08-01T00:00:00Z",
) -> FilingEvidence:
    """Build one filing's derivation evidence."""
    return FilingEvidence(
        filing_id=_filing_id(accession),
        form=form,
        acceptance_timestamp_utc=acceptance,
        filing_date=filing_date,
        report_date=report_date,
        dissemination_evidence_utc=dissemination,
        retrieved_at=retrieved_at,
    )


def availability(
    *,
    accession: str,
    timestamp: str | None,
    status: AvailabilityStatus,
    policy_id: str | None,
    form: str = "10-K",
    acceptance: str | None = None,
) -> FilingAvailability:
    """Build a derived availability triple directly (bypassing derive)."""
    return FilingAvailability(
        filing_id=_filing_id(accession),
        derived_public_availability_timestamp=timestamp,
        availability_status=status,
        availability_policy_id=policy_id,
        policy_version="edgar-std/v1" if policy_id else None,
        policy_confidence="unvalidated" if policy_id else None,
        policy_status="provisional" if policy_id else None,
        reason="test",
        evidence=evidence(
            accession=accession, form=form, acceptance=acceptance or timestamp
        ),
    )


def revenue_fact(
    *,
    accession: str,
    value: str,
    cik: int = 320193,
    concept_local: str = "Revenues",
    period_start: str = "2019-01-01",
    period_end: str = "2019-12-31",
    unit_ref: str = "usd",
) -> Fact:
    """A minimal canonical revenue Fact for FY2019, tied to one filing.

    All facts built with the same period/concept/unit share an ``obs_key`` (they
    describe the same economic observation), differing only by ``filing_id`` /
    value — exactly the §KS.3 restatement setup.
    """
    clark = f"{{http://fasb.org/us-gaap/2023}}{concept_local}"
    company = _company_id(cik)
    filing = _filing_id(accession)
    key = obs_key(
        company_id=company,
        security_id=None,
        concept_clark=clark,
        period_type=PeriodType.DURATION.value,
        period_start=period_start,
        period_end=period_end,
        unit_ref=unit_ref,
        dimensions_hash="",
    )
    fid = fact_id(transformation_version_id=TV, filing_id=filing, obs_key_value=key)
    provenance = FactProvenance(
        raw_fact_id="raw-1",
        raw_fact_ids=("raw-1",),
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
            namespace_uri="http://fasb.org/us-gaap/2023",
            local_name=concept_local,
            taxonomy=Taxonomy.US_GAAP,
        ),
        taxonomy=Taxonomy.US_GAAP,
        period_type=PeriodType.DURATION,
        period_start=period_start,
        period_end=period_end,
        value_numeric_str=value,
        value_text=None,
        is_nil=False,
        unit="USD",
        currency="USD",
        unit_ref=unit_ref,
        unit_numerator=("iso4217:USD",),
        unit_denominator=(),
        unit_is_divide=False,
        scale=0,
        decimals=-6,
        raw_value=value,
        raw_scale=None,
        raw_sign=None,
        raw_decimals="-6",
        dimensions=(),
        dimensions_hash="",
        filing_id=filing,
        transformation_version_id=TV,
        provenance=provenance,
    )
