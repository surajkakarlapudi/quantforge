"""Market-data availability policy + deriver (proposal §9, D3).

The market analogue of :mod:`quantforge.availability.policy`, mirroring it exactly:
a versioned, era-bounded, **declarative** rule (:class:`MarketAvailabilityRule`) and
a pure, deterministic :func:`derive_market_availability` that turns one bar/action's
:class:`~quantforge.market.model.MarketObservationEvidence` into a
:class:`~quantforge.market.model.MarketAvailability` triple.

The v1 rule (D3): **an EOD bar for session ``D`` becomes knowable no earlier than the
exchange close of ``D`` plus a policy-defined publication lag.** The derived instant
is

* **floored at the session close** - a bar can never be knowable before its own
  session ends (the market analogue of Phase 5 invariant 10, "never before
  acceptance"), and
* **capped at ``retrieved_at``** - the retrieval instant is a hard upper bound
  (invariant 11 analogue); a bar whose retrieval precedes its own session close is
  inconsistent evidence and fails **closed** to ``UNKNOWN``,

and anything that cannot be defended → ``UNKNOWN`` → excluded (fail-closed invariants
8-9). "Round LATER on uncertainty, never earlier" (§9).

Guarantees (invariants 13, 21): no wall-clock, no RNG, no input-order dependence;
same evidence + same policy version ⇒ identical triple. All ET / DST reasoning is
delegated to the self-contained :mod:`quantforge.availability.calendar` (no host tz
database), reused verbatim - the market layer re-implements no time handling.

:class:`~quantforge.availability.version.PolicyStatus` /
:class:`~quantforge.availability.version.PolicyConfidence` are **reused**, not
re-declared: a market policy's lifecycle/validation vocabulary is identical to a
filing policy's (§2.3).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from quantforge.availability.calendar import utc_from_eastern_naive
from quantforge.availability.model import AvailabilityStatus
from quantforge.availability.timestamps import format_utc_z, parse_utc
from quantforge.availability.version import PolicyConfidence, PolicyStatus
from quantforge.market.errors import MarketPolicyConfigurationError
from quantforge.market.identity import market_availability_policy_id
from quantforge.market.model import (
    MarketAvailability,
    MarketObservationEvidence,
)

__all__ = [
    "MarketAvailabilityPolicy",
    "MarketAvailabilityRule",
    "derive_market_availability",
    "market_eod_std_v1",
    "select_market_policy",
]

# A separator that cannot occur in any id component (same convention as §11).
_SEP = "\x00"

_SELECTABLE = (PolicyStatus.ACTIVE, PolicyStatus.PROVISIONAL)
_SUPPORTED_RULE = "session-close-plus-publication-lag"
_SUPPORTED_CALENDAR = "us-eastern-business"


@dataclass(frozen=True, slots=True)
class MarketAvailabilityRule:
    """Declarative definition of how a bar's availability is derived (§9, D3).

    **Data, not code**: :func:`derive_market_availability` reads these fields to
    decide the availability instant and status. Because the whole rule is hashed
    into :attr:`MarketAvailabilityPolicy.market_availability_policy_id`, any change
    to it necessarily yields a new policy version (invariant 14) - the publication
    lag, the assumed session close, and the calendar are all part of identity.

    Attributes
    ----------
    rule_kind:
        The derivation algorithm the deriver must apply. The only kind implemented
        is ``"session-close-plus-publication-lag"``; any other value fails closed
        (:class:`~quantforge.market.errors.MarketPolicyConfigurationError`) - we
        never guess a rule's intent.
    session_close_local_time:
        ``"HH:MM"`` exchange-close wall-clock in the rule's ``calendar`` timezone
        (ET). The availability floor: a bar is never knowable before this instant on
        its own ``trading_date``.
    publication_lag_minutes:
        Minutes added to the session close to model EOD dissemination delay. Added
        in ET wall-clock then converted to UTC, so it is DST-correct. Non-negative;
        larger is more conservative (rounds *later*, never earlier - §9).
    calendar:
        Business-calendar identifier. Only ``"us-eastern-business"`` is implemented
        (see :mod:`quantforge.availability.calendar`).
    dissemination_evidence_trusted:
        Whether a source's direct dissemination timestamp may upgrade status to
        ``VERIFIED``. **False** in v1 (§9: derived or unknown only); a future
        validated policy version may set it True - the branch is already provided.
    fail_closed_on_missing_session:
        When the session date is absent/unparseable, produce ``UNKNOWN`` rather than
        guess. Always True here.
    """

    rule_kind: str = "session-close-plus-publication-lag"
    session_close_local_time: str = "16:00"
    publication_lag_minutes: int = 240
    calendar: str = "us-eastern-business"
    dissemination_evidence_trusted: bool = False
    fail_closed_on_missing_session: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_kind": self.rule_kind,
            "session_close_local_time": self.session_close_local_time,
            "publication_lag_minutes": self.publication_lag_minutes,
            "calendar": self.calendar,
            "dissemination_evidence_trusted": self.dissemination_evidence_trusted,
            "fail_closed_on_missing_session": self.fail_closed_on_missing_session,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MarketAvailabilityRule:
        lag = raw.get("publication_lag_minutes", 240)
        return cls(
            rule_kind=_req_str(raw, "rule_kind"),
            session_close_local_time=_req_str(raw, "session_close_local_time"),
            publication_lag_minutes=int(lag) if isinstance(lag, int) else 240,
            calendar=_req_str(raw, "calendar"),
            dissemination_evidence_trusted=bool(
                raw.get("dissemination_evidence_trusted", False)
            ),
            fail_closed_on_missing_session=bool(
                raw.get("fail_closed_on_missing_session", True)
            ),
        )

    @property
    def rule_definition_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the declarative rule content."""
        from quantforge.sec.artifacts import sha256_hex

        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )
        return f"sha256:{sha256_hex(payload)}"

    @property
    def session_close_hour_minute(self) -> tuple[int, int]:
        """Parse ``session_close_local_time`` into ``(hour, minute)``; fail if bad."""
        parts = self.session_close_local_time.split(":")
        if len(parts) != 2:
            raise ValueError(
                f"invalid session_close_local_time {self.session_close_local_time!r}"
            )
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(
                f"session close out of range {self.session_close_local_time!r}"
            )
        return hour, minute


@dataclass(frozen=True, slots=True)
class MarketAvailabilityPolicy:
    """One immutable, era-bounded market-availability policy version (§9, D3).

    Selection (§9): a policy governs a session when the session's date falls in
    ``[effective_from, effective_to)`` and its status is active/provisional. Exactly
    one such version must match a given session date; overlap is a configuration
    error surfaced by :func:`select_market_policy` (never arbitrated). Identity is
    ``market_availability_policy_id = sha256(policy_id, policy_version,
    rule_definition_hash)`` (§14) - the Phase 5 shape - so a change to the rule is a
    new id, and re-declaring the identical policy reproduces the same id
    (invariant 20).
    """

    policy_id: str
    policy_version: str
    effective_from: str
    effective_to: str | None
    rule_definition: MarketAvailabilityRule
    status: PolicyStatus
    confidence: PolicyConfidence
    notes: str = ""

    @property
    def market_availability_policy_id(self) -> str:
        """``sha256(policy_id, policy_version, rule_definition_hash)`` (§14)."""
        return market_availability_policy_id(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            rule_definition_hash=self.rule_definition.rule_definition_hash,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "market_availability_policy_id": self.market_availability_policy_id,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "rule_definition": self.rule_definition.to_dict(),
            "status": self.status.value,
            "confidence": self.confidence.value,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MarketAvailabilityPolicy:
        rule_raw = raw["rule_definition"]
        if not isinstance(rule_raw, dict):
            raise ValueError("rule_definition must be an object")
        return cls(
            policy_id=_req_str(raw, "policy_id"),
            policy_version=_req_str(raw, "policy_version"),
            effective_from=_req_str(raw, "effective_from"),
            effective_to=_opt_str(raw, "effective_to"),
            rule_definition=MarketAvailabilityRule.from_dict(rule_raw),
            status=PolicyStatus(_req_str(raw, "status")),
            confidence=PolicyConfidence(_req_str(raw, "confidence")),
            notes=_str_default(raw, "notes"),
        )


def market_eod_std_v1() -> MarketAvailabilityPolicy:
    """The initial market-availability policy - ``market-eod-std/v1`` (§9, D3).

    Provisional and unvalidated: it encodes the conservative EOD convention (session
    close 16:00 ET + a publication lag) as a *derived* estimate, and it **never**
    produces ``VERIFIED`` (``dissemination_evidence_trusted=False``). Its era is
    bounded to the post-2007 DST regime onward, so the self-contained ET calendar is
    exactly correct; sessions dated before it get ``UNKNOWN``. A future validated or
    exchange-specific policy is introduced as a *new version*, never an edit.
    """
    return MarketAvailabilityPolicy(
        policy_id="market-eod-std",
        policy_version="v1",
        # Safely after the 2007 DST regime so the ET calendar holds (invariant 14).
        effective_from="2007-01-01T00:00:00Z",
        effective_to=None,
        rule_definition=MarketAvailabilityRule(),
        status=PolicyStatus.PROVISIONAL,
        confidence=PolicyConfidence.UNVALIDATED,
        notes=(
            "Initial provisional market policy. Conservative session-close (16:00 "
            "ET) + publication-lag derivation, floored at the session close and "
            "capped at retrieved_at; produces DERIVED or UNKNOWN only, never "
            "VERIFIED, until a source supplies trustworthy dissemination evidence "
            "and a validated successor version exists."
        ),
    )


def select_market_policy(
    evidence: MarketObservationEvidence,
    policies: Sequence[MarketAvailabilityPolicy],
) -> MarketAvailabilityPolicy | None:
    """Select the single policy governing ``evidence`` (§9), or ``None``.

    A policy is a candidate when its status is active/provisional and the session's
    date falls in ``[effective_from, effective_to)``. Returns the sole match, or
    ``None`` if none match (the session is out of scope → the caller yields
    ``UNKNOWN``). Raises
    :class:`~quantforge.market.errors.MarketPolicyConfigurationError` if more than
    one active/provisional policy matches - overlapping active eras are a
    configuration error, never arbitrated (fail closed).
    """
    session_instant = _session_midnight_utc(evidence.event_date)
    if session_instant is None:
        return None

    matches: list[MarketAvailabilityPolicy] = []
    for policy in policies:
        if policy.status not in _SELECTABLE:
            continue
        if not _in_era(session_instant, policy):
            continue
        matches.append(policy)

    if not matches:
        return None
    if len(matches) > 1:
        ids = sorted(p.market_availability_policy_id for p in matches)
        raise MarketPolicyConfigurationError(
            "overlapping active market availability policies match session "
            f"{evidence.session_key!r}: {ids}; exactly one must match - refusing "
            "to arbitrate (§9)"
        )
    return matches[0]


def derive_market_availability(
    evidence: MarketObservationEvidence,
    policies: Sequence[MarketAvailabilityPolicy],
) -> MarketAvailability:
    """Derive one session's availability triple deterministically (§9, D3).

    Selects the governing policy (:func:`select_market_policy`) then applies its
    declarative rule. Any inability to defend a reliable instant yields ``UNKNOWN``
    (fail closed); an unimplemented rule/calendar is a configuration error. The
    result is a pure function of ``(evidence, policy version)``.
    """
    policy = select_market_policy(evidence, policies)
    if policy is None:
        return _unknown(
            evidence,
            "no active market availability policy governs this session's date/era "
            "(or the session date is missing/unparseable)",
        )

    rule = policy.rule_definition
    if rule.rule_kind != _SUPPORTED_RULE or rule.calendar != _SUPPORTED_CALENDAR:
        raise MarketPolicyConfigurationError(
            f"policy {policy.market_availability_policy_id} names unsupported "
            f"rule_kind={rule.rule_kind!r} / calendar={rule.calendar!r}"
        )

    session_day = _parse_session_date(evidence.event_date)
    if session_day is None:
        return _unknown(evidence, "session date is missing or unparseable")

    close_h, close_m = rule.session_close_hour_minute
    et_close = datetime(
        session_day.year, session_day.month, session_day.day, close_h, close_m
    )
    session_close_utc = utc_from_eastern_naive(et_close)
    retrieved_upper = _retrieved_upper_bound(evidence)

    # Optional direct dissemination evidence → VERIFIED, but only if the policy
    # trusts it (§9: the initial policy does not, so this branch is dormant until a
    # validated successor policy enables it).
    if rule.dissemination_evidence_trusted and evidence.observation_timestamp_utc:
        try:
            disseminated = parse_utc(evidence.observation_timestamp_utc)
        except ValueError:
            disseminated = None
        if disseminated is not None:
            # Never before the session close (floor); cap at retrieval.
            instant = max(disseminated, session_close_utc)
            capped = _cap_at_retrieval(instant, session_close_utc, retrieved_upper)
            if capped is None:
                return _unknown(
                    evidence,
                    "dissemination evidence / retrieval precedes the session close; "
                    "cannot defend a consistent availability (invariant 11)",
                )
            return _resolved(
                evidence,
                policy,
                capped,
                AvailabilityStatus.VERIFIED,
                "direct dissemination evidence, trusted by policy",
            )

    # DERIVED path: session close + publication lag (in ET wall-clock, DST-correct).
    et_avail = et_close + timedelta(minutes=rule.publication_lag_minutes)
    instant = utc_from_eastern_naive(et_avail)
    # Floor at session close (a bar is never knowable before its session ends).
    if instant < session_close_utc:
        instant = session_close_utc
    capped = _cap_at_retrieval(instant, session_close_utc, retrieved_upper)
    if capped is None:
        return _unknown(
            evidence,
            "retrieval precedes the session close - a bar cannot have been retrieved "
            "before its own session ended (inconsistent evidence, invariant 11)",
        )
    return _resolved(
        evidence,
        policy,
        capped,
        AvailabilityStatus.DERIVED,
        "derived from session close + publication-lag policy rule",
    )


def _in_era(session_instant: datetime, policy: MarketAvailabilityPolicy) -> bool:
    """Whether ``session_instant`` falls in the policy's ``[from, to)`` era."""
    start = parse_utc(policy.effective_from)
    if session_instant < start:
        return False
    if policy.effective_to is not None:
        end = parse_utc(policy.effective_to)
        if session_instant >= end:
            return False
    return True


def _parse_session_date(value: str) -> date | None:
    """Parse an ``YYYY-MM-DD`` session date; ``None`` if missing/unparseable."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _session_midnight_utc(value: str) -> datetime | None:
    """The session date at ``T00:00:00Z`` for coarse era matching, or ``None``."""
    day = _parse_session_date(value)
    if day is None:
        return None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _retrieved_upper_bound(evidence: MarketObservationEvidence) -> datetime | None:
    if evidence.retrieved_at is None:
        return None
    try:
        return parse_utc(evidence.retrieved_at)
    except ValueError:
        return None


def _cap_at_retrieval(
    instant: datetime, floor: datetime, retrieved_upper: datetime | None
) -> datetime | None:
    """Cap ``instant`` at the retrieval upper bound (invariant 11 analogue).

    Returns the capped instant, or ``None`` when capping would push availability
    *before* the session-close ``floor`` (i.e. the bytes were retrieved before the
    session even closed) - inconsistent evidence the caller turns into ``UNKNOWN``.
    Normal case: ``instant`` unchanged when already ``<= retrieved_upper``.
    """
    if retrieved_upper is None:
        return instant
    if instant <= retrieved_upper:
        return instant
    # Our estimate overshoots the moment we fetched the bytes. Hard evidence wins →
    # cap at retrieval, but never below the session-close floor.
    if retrieved_upper < floor:
        return None
    return retrieved_upper


def _resolved(
    evidence: MarketObservationEvidence,
    policy: MarketAvailabilityPolicy,
    instant: datetime,
    status: AvailabilityStatus,
    reason: str,
) -> MarketAvailability:
    return MarketAvailability(
        security_id=evidence.security_id,
        event_date=evidence.event_date,
        derived_public_availability_timestamp=format_utc_z(instant.astimezone(UTC)),
        availability_status=status,
        availability_policy_id=policy.market_availability_policy_id,
        policy_version=f"{policy.policy_id}/{policy.policy_version}",
        policy_confidence=policy.confidence.value,
        policy_status=policy.status.value,
        reason=reason,
        evidence=evidence,
    )


def _unknown(evidence: MarketObservationEvidence, reason: str) -> MarketAvailability:
    return MarketAvailability(
        security_id=evidence.security_id,
        event_date=evidence.event_date,
        derived_public_availability_timestamp=None,
        availability_status=AvailabilityStatus.UNKNOWN,
        availability_policy_id=None,
        policy_version=None,
        policy_confidence=None,
        policy_status=None,
        reason=reason,
        evidence=evidence,
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
