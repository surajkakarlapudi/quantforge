"""Public-availability data model: evidence in, availability triple out.

Three small immutable records anchor Phase 5 (data-model §PA, §3.1, §12):

* :class:`AvailabilityStatus` — the fail-closed safety valve (§PA.3): ``verified``
  / ``derived`` / ``unknown``. Only ``verified`` and ``derived`` are PIT-eligible;
  ``unknown`` is **never** eligible for normal research (invariant 9).
* :class:`FilingEvidence` — the *raw inputs* to derivation for one filing:
  acceptance timestamp, filing date, optional dissemination evidence, and the
  ``retrieved_at`` upper bound (invariant 11). This is assembled by the façade by
  joining Phase 2 :class:`~quantforge.registry.model.FilingRecord` fields with
  Phase 1 ``retrieved_at`` — and ``retrieved_at`` is joined **only here**, at
  derivation time (mandate: never on RawFact/Fact identity).
* :class:`FilingAvailability` — the derived **availability triple**
  ``(derived_public_availability_timestamp, availability_status,
  availability_policy_id)`` for one filing, plus the evidence and the policy that
  produced it (audit). Because a filing is disseminated as a unit, this single
  triple attaches to every Fact of the filing (invariant 17) — it is stored once
  per ``filing_id`` (sidecar store) and joined to facts at query time, never
  copied onto or drifting from the immutable Fact rows (invariant 7).

None of these participate in Fact identity. They are a *sidecar* layer over the
immutable canonical facts (Decision 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "AvailabilityStatus",
    "FilingAvailability",
    "FilingEvidence",
]


class AvailabilityStatus(StrEnum):
    """Whether — and how defensibly — a filing's public availability is known.

    Data-model §PA.3 / invariants 8-9. ``VERIFIED`` requires *direct*
    dissemination/index evidence (not produced by the initial policy — Decision
    4). ``DERIVED`` is computed from acceptance + a validated policy rule,
    conservative. ``UNKNOWN`` is the fail-closed state: the policy cannot defend a
    reliable timestamp, so the filing is excluded from all normal PIT research.
    """

    VERIFIED = "verified"
    DERIVED = "derived"
    UNKNOWN = "unknown"

    @property
    def is_pit_eligible(self) -> bool:
        """PIT-eligible iff status ∈ {verified, derived} (§6.1-A, invariant 9)."""
        return self in (AvailabilityStatus.VERIFIED, AvailabilityStatus.DERIVED)


@dataclass(frozen=True, slots=True)
class FilingEvidence:
    """The immutable raw inputs to availability derivation for one filing (§PA.2).

    Attributes
    ----------
    filing_id:
        The filing these evidence facts belong to (Phase 2 identity).
    form:
        SEC form label, used for policy form-scope selection.
    acceptance_timestamp_utc:
        EDGAR ``acceptanceDateTime`` as-supplied UTC (``…Z``), or ``None`` if the
        source omitted it. Never converted on ingest (§6.4); a policy converts to
        ET *inside* its calendar logic.
    filing_date:
        Legal "deemed filed" date (date-only). **Never** used as a lower bound on
        availability (invariant 10).
    report_date:
        Period-of-report date, carried for completeness/audit only.
    dissemination_evidence_utc:
        Optional direct dissemination/index timestamp (UTC). ``None`` until a
        dissemination index is actually ingested; only a policy that trusts it may
        use it to reach ``verified``.
    retrieved_at:
        The earliest Phase 1 ``retrieved_at`` (ISO-8601 UTC) across the filing's
        source artifacts — an **upper bound** on availability (invariant 11),
        joined here at derivation only. ``None`` if unknown.
    """

    filing_id: str
    form: str
    acceptance_timestamp_utc: str | None
    filing_date: str | None
    report_date: str | None
    dissemination_evidence_utc: str | None = None
    retrieved_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "filing_id": self.filing_id,
            "form": self.form,
            "acceptance_timestamp_utc": self.acceptance_timestamp_utc,
            "filing_date": self.filing_date,
            "report_date": self.report_date,
            "dissemination_evidence_utc": self.dissemination_evidence_utc,
            "retrieved_at": self.retrieved_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FilingEvidence:
        return cls(
            filing_id=_req_str(raw, "filing_id"),
            form=_req_str(raw, "form"),
            acceptance_timestamp_utc=_opt_str(raw, "acceptance_timestamp_utc"),
            filing_date=_opt_str(raw, "filing_date"),
            report_date=_opt_str(raw, "report_date"),
            dissemination_evidence_utc=_opt_str(raw, "dissemination_evidence_utc"),
            retrieved_at=_opt_str(raw, "retrieved_at"),
        )


@dataclass(frozen=True, slots=True)
class FilingAvailability:
    """The derived availability triple for one filing, with its evidence & policy.

    The triple ``(derived_public_availability_timestamp, availability_status,
    availability_policy_id)`` is what the PIT resolver joins onto every Fact of the
    filing (invariant 17). ``availability_policy_id`` is ``None`` exactly when the
    status is ``unknown`` (invariant 12). ``derived_public_availability_timestamp``
    is an aware-UTC ISO-8601 string (``…Z``) when the status is eligible, else
    ``None``.

    ``evidence`` retains the raw derivation inputs and ``policy_version`` /
    ``policy_confidence`` / ``policy_status`` record the deciding policy for audit —
    so a stored availability record is fully self-describing and re-derivable.
    """

    filing_id: str
    derived_public_availability_timestamp: str | None
    availability_status: AvailabilityStatus
    availability_policy_id: str | None
    policy_version: str | None
    policy_confidence: str | None
    policy_status: str | None
    reason: str
    evidence: FilingEvidence

    def __post_init__(self) -> None:
        # Invariant 12: a non-unknown status must reference a policy; unknown must
        # not carry a derived timestamp (it is never PIT-eligible, §6.1-A).
        if self.availability_status is AvailabilityStatus.UNKNOWN:
            if self.derived_public_availability_timestamp is not None:
                raise ValueError("unknown availability must not carry a timestamp")
            if self.availability_policy_id is not None:
                raise ValueError("unknown availability must not reference a policy")
        else:
            status = self.availability_status.value
            if self.availability_policy_id is None:
                raise ValueError(f"{status} availability requires a policy id")
            if self.derived_public_availability_timestamp is None:
                raise ValueError(f"{status} availability requires a timestamp")

    @property
    def is_pit_eligible(self) -> bool:
        """Eligible iff status ∈ {verified, derived} and a timestamp exists."""
        return (
            self.availability_status.is_pit_eligible
            and self.derived_public_availability_timestamp is not None
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "filing_id": self.filing_id,
            "derived_public_availability_timestamp": (
                self.derived_public_availability_timestamp
            ),
            "availability_status": self.availability_status.value,
            "availability_policy_id": self.availability_policy_id,
            "policy_version": self.policy_version,
            "policy_confidence": self.policy_confidence,
            "policy_status": self.policy_status,
            "reason": self.reason,
            "evidence": self.evidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FilingAvailability:
        evidence_raw = raw["evidence"]
        if not isinstance(evidence_raw, dict):
            raise ValueError("evidence must be an object")
        return cls(
            filing_id=_req_str(raw, "filing_id"),
            derived_public_availability_timestamp=_opt_str(
                raw, "derived_public_availability_timestamp"
            ),
            availability_status=AvailabilityStatus(
                _req_str(raw, "availability_status")
            ),
            availability_policy_id=_opt_str(raw, "availability_policy_id"),
            policy_version=_opt_str(raw, "policy_version"),
            policy_confidence=_opt_str(raw, "policy_confidence"),
            policy_status=_opt_str(raw, "policy_status"),
            reason=_str_default(raw, "reason"),
            evidence=FilingEvidence.from_dict(evidence_raw),
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


def _str_default(raw: dict[str, object], key: str) -> str:
    value = raw.get(key, "")
    return value if isinstance(value, str) else ""
