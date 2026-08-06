"""Tests for the availability data model's structural invariants (§PA, inv 12)."""

from __future__ import annotations

import pytest

from openfinance.availability.model import (
    AvailabilityStatus,
    FilingAvailability,
    FilingEvidence,
)


def _evidence() -> FilingEvidence:
    return FilingEvidence(
        filing_id="filing:x",
        form="10-K",
        acceptance_timestamp_utc="2024-01-02T15:00:00Z",
        filing_date="2024-01-02",
        report_date=None,
    )


class TestPitEligibility:
    def test_verified_and_derived_are_eligible(self) -> None:
        assert AvailabilityStatus.VERIFIED.is_pit_eligible
        assert AvailabilityStatus.DERIVED.is_pit_eligible

    def test_unknown_is_not_eligible(self) -> None:
        assert not AvailabilityStatus.UNKNOWN.is_pit_eligible


class TestInvariant12:
    def test_derived_requires_timestamp_and_policy(self) -> None:
        rec = FilingAvailability(
            filing_id="filing:x",
            derived_public_availability_timestamp="2024-01-02T22:30:00Z",
            availability_status=AvailabilityStatus.DERIVED,
            availability_policy_id="sha256:p",
            policy_version="edgar-std/v1",
            policy_confidence="unvalidated",
            policy_status="provisional",
            reason="ok",
            evidence=_evidence(),
        )
        assert rec.is_pit_eligible

    def test_unknown_must_not_carry_timestamp(self) -> None:
        with pytest.raises(ValueError, match="must not carry a timestamp"):
            FilingAvailability(
                filing_id="filing:x",
                derived_public_availability_timestamp="2024-01-02T22:30:00Z",
                availability_status=AvailabilityStatus.UNKNOWN,
                availability_policy_id=None,
                policy_version=None,
                policy_confidence=None,
                policy_status=None,
                reason="bad",
                evidence=_evidence(),
            )

    def test_unknown_must_not_reference_policy(self) -> None:
        with pytest.raises(ValueError, match="must not reference a policy"):
            FilingAvailability(
                filing_id="filing:x",
                derived_public_availability_timestamp=None,
                availability_status=AvailabilityStatus.UNKNOWN,
                availability_policy_id="sha256:p",
                policy_version=None,
                policy_confidence=None,
                policy_status=None,
                reason="bad",
                evidence=_evidence(),
            )

    def test_derived_without_policy_rejected(self) -> None:
        with pytest.raises(ValueError, match="requires a policy id"):
            FilingAvailability(
                filing_id="filing:x",
                derived_public_availability_timestamp="2024-01-02T22:30:00Z",
                availability_status=AvailabilityStatus.DERIVED,
                availability_policy_id=None,
                policy_version=None,
                policy_confidence=None,
                policy_status=None,
                reason="bad",
                evidence=_evidence(),
            )

    def test_derived_without_timestamp_rejected(self) -> None:
        with pytest.raises(ValueError, match="requires a timestamp"):
            FilingAvailability(
                filing_id="filing:x",
                derived_public_availability_timestamp=None,
                availability_status=AvailabilityStatus.DERIVED,
                availability_policy_id="sha256:p",
                policy_version="edgar-std/v1",
                policy_confidence="unvalidated",
                policy_status="provisional",
                reason="bad",
                evidence=_evidence(),
            )

    def test_roundtrip_preserves_fields(self) -> None:
        rec = FilingAvailability(
            filing_id="filing:x",
            derived_public_availability_timestamp="2024-01-02T22:30:00Z",
            availability_status=AvailabilityStatus.DERIVED,
            availability_policy_id="sha256:p",
            policy_version="edgar-std/v1",
            policy_confidence="unvalidated",
            policy_status="provisional",
            reason="ok",
            evidence=_evidence(),
        )
        assert FilingAvailability.from_dict(rec.to_dict()) == rec
