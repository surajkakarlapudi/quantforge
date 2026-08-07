"""The availability deriver — ``derive(evidence, policy)`` (data-model §PA.2).

This is the pure, deterministic core of Phase 5. Given a filing's
:class:`~quantforge.availability.model.FilingEvidence` and one selected
:class:`~quantforge.availability.version.AvailabilityPolicy`, it produces a
:class:`~quantforge.availability.model.FilingAvailability` triple
``(derived_public_availability_timestamp, availability_status,
availability_policy_id)``.

Guarantees (invariants 6-17, §PA.3):

* **Deterministic (invariant 13).** No wall-clock, no RNG, no input-order
  dependence. Same evidence + same policy version ⇒ identical triple. All ET /
  business-calendar reasoning is delegated to the self-contained
  :mod:`quantforge.availability.calendar` (no host tz database).
* **Fail closed (§PA.3).** Missing/unusable acceptance, an out-of-era filing, or
  a rule the deriver does not implement ⇒ ``unknown`` (never a fall back to
  filing date or retrieval time). ``unknown`` is never PIT-eligible.
* **Never precedes acceptance (invariant 10).** The derived timestamp is
  ``max(cutoff-instant, acceptance)`` — a same-day cutoff earlier than the
  acceptance instant can never pull availability *before* the filing was even
  accepted.
* **Retrieval is an upper bound only (invariant 11).** If the derived instant
  would exceed ``retrieved_at``, it is **capped** at ``retrieved_at`` (hard
  evidence beats estimate). ``retrieved_at`` is *never* used as the availability
  itself.
* **Derived-or-unknown only (Decision 4).** The initial policy sets
  ``dissemination_evidence_trusted=False``, so this deriver returns ``verified``
  only when a (future) policy explicitly trusts direct dissemination evidence and
  such evidence is present; otherwise the best attainable status is ``derived``.

Policy selection (:func:`select_policy`) enforces §PA.2: among candidate policies
matching the filing's ``(form, acceptance date)``, **exactly one** active/
provisional version must match; zero → ``unknown`` (out of scope), more than one
→ :class:`~quantforge.availability.errors.PolicyConfigurationError` (we never
arbitrate overlapping scopes).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from quantforge.availability.calendar import (
    is_us_business_day,
    next_us_business_day,
    to_eastern_naive,
    utc_from_eastern_naive,
)
from quantforge.availability.errors import PolicyConfigurationError
from quantforge.availability.model import (
    AvailabilityStatus,
    FilingAvailability,
    FilingEvidence,
)
from quantforge.availability.timestamps import format_utc_z, parse_utc
from quantforge.availability.version import (
    AvailabilityPolicy,
    PolicyStatus,
)

__all__ = ["derive", "select_policy"]

_SELECTABLE = (PolicyStatus.ACTIVE, PolicyStatus.PROVISIONAL)
_SUPPORTED_RULE = "acceptance-cutoff-next-business-day"
_SUPPORTED_CALENDAR = "us-eastern-business"


def select_policy(
    evidence: FilingEvidence, policies: Sequence[AvailabilityPolicy]
) -> AvailabilityPolicy | None:
    """Select the single policy governing ``evidence`` (§PA.2), or ``None``.

    A policy is a candidate when its :meth:`~AvailabilityPolicy.covers_form`
    matches the filing's form, its status is active/provisional, and the filing's
    acceptance instant falls in ``[effective_from, effective_to)``. Returns the
    sole matching policy, or ``None`` if none match (the filing is out of scope →
    the caller yields ``unknown``). Raises
    :class:`PolicyConfigurationError` if more than one active/provisional policy
    matches — overlapping active scopes are a configuration error, never
    arbitrated (fail closed).

    A filing with no acceptance timestamp cannot be era-matched, so it has no
    governing policy here (``None``) and the caller fails it closed to ``unknown``.
    """
    if evidence.acceptance_timestamp_utc is None:
        return None
    try:
        acceptance = parse_utc(evidence.acceptance_timestamp_utc)
    except ValueError:
        return None

    matches: list[AvailabilityPolicy] = []
    for policy in policies:
        if policy.status not in _SELECTABLE:
            continue
        if not policy.covers_form(evidence.form):
            continue
        if not _in_era(acceptance, policy):
            continue
        matches.append(policy)

    if not matches:
        return None
    if len(matches) > 1:
        ids = sorted(p.availability_policy_id for p in matches)
        raise PolicyConfigurationError(
            "overlapping active availability policies match filing "
            f"{evidence.filing_id!r} (form {evidence.form!r}): {ids}; "
            "exactly one must match — refusing to arbitrate (§PA.2)"
        )
    return matches[0]


def _in_era(acceptance: datetime, policy: AvailabilityPolicy) -> bool:
    """Whether ``acceptance`` falls in the policy's ``[from, to)`` era."""
    start = parse_utc(policy.effective_from)
    if acceptance < start:
        return False
    if policy.effective_to is not None:
        end = parse_utc(policy.effective_to)
        if acceptance >= end:
            return False
    return True


def derive(
    evidence: FilingEvidence, policies: Sequence[AvailabilityPolicy]
) -> FilingAvailability:
    """Derive one filing's availability triple deterministically (§PA.2).

    Selects the governing policy (:func:`select_policy`) then applies its
    declarative rule. Any inability to defend a reliable timestamp yields
    ``unknown`` (fail closed); an unimplemented rule/calendar is a configuration
    error. The result is a pure function of ``(evidence, policy version)``.
    """
    policy = select_policy(evidence, policies)
    if policy is None:
        return _unknown(
            evidence,
            "no active availability policy governs this filing's form/era "
            "(or acceptance timestamp is missing/unparseable)",
        )

    rule = policy.rule_definition
    if rule.rule_kind != _SUPPORTED_RULE or rule.calendar != _SUPPORTED_CALENDAR:
        # We never guess a rule's intent; an unknown rule is a config error.
        raise PolicyConfigurationError(
            f"policy {policy.availability_policy_id} names unsupported "
            f"rule_kind={rule.rule_kind!r} / calendar={rule.calendar!r}"
        )

    # Acceptance is guaranteed present & parseable (select_policy required it).
    assert evidence.acceptance_timestamp_utc is not None
    acceptance = parse_utc(evidence.acceptance_timestamp_utc)

    retrieved_upper = _retrieved_upper_bound(evidence)

    # Optional direct dissemination evidence → `verified`, but only if the policy
    # trusts it (Decision 4: the initial policy does not, so this branch is dormant
    # until a validated successor policy enables it).
    if rule.dissemination_evidence_trusted and evidence.dissemination_evidence_utc:
        try:
            disseminated = parse_utc(evidence.dissemination_evidence_utc)
        except ValueError:
            disseminated = None
        if disseminated is not None:
            # Never earlier than acceptance (invariant 10); cap at retrieval
            # (invariant 11).
            capped = _cap_at_retrieval(max(disseminated, acceptance), retrieved_upper)
            if capped is None:
                return _unknown(
                    evidence,
                    "dissemination evidence precedes the retrieval upper bound; "
                    "cannot defend a consistent availability (invariant 11)",
                )
            return _resolved(
                evidence,
                policy,
                capped,
                AvailabilityStatus.VERIFIED,
                "direct dissemination evidence, trusted by policy",
            )

    # Otherwise derive conservatively from acceptance + cutoff/calendar.
    instant = _derive_from_acceptance(acceptance, rule.cutoff_hour_minute)
    # Never before acceptance (invariant 10).
    if instant < acceptance:
        instant = acceptance
    capped = _cap_at_retrieval(instant, retrieved_upper)
    if capped is None:
        # Our estimate is later than when we actually fetched it — impossible.
        # Hard evidence wins: cap at retrieval. (Only None when even acceptance
        # exceeds retrieval, which means the retrieval evidence is inconsistent.)
        return _unknown(
            evidence,
            "derived availability exceeds retrieval upper bound and even "
            "acceptance follows retrieval — inconsistent evidence (invariant 11)",
        )
    return _resolved(
        evidence,
        policy,
        capped,
        AvailabilityStatus.DERIVED,
        "derived from acceptance via cutoff/next-business-day policy rule",
    )


def _derive_from_acceptance(
    acceptance: datetime, cutoff_hm: tuple[int, int]
) -> datetime:
    """Conservative availability instant from acceptance + ET cutoff/calendar.

    Convert acceptance UTC → ET wall-clock. If it is a business day at/before the
    cutoff, availability is that day's cutoff instant (ET). Otherwise (after the
    cutoff, or a weekend/holiday) it rolls to the *next US business day's* cutoff
    instant. The cutoff instant is then converted back to UTC. Rounding to the
    cutoff (never earlier) implements §PA.3's "round later on uncertainty."
    """
    cutoff_h, cutoff_m = cutoff_hm
    et = to_eastern_naive(acceptance)
    et_day = et.date()
    on_business_day = is_us_business_day(et_day)
    before_cutoff = (et.hour, et.minute, et.second, et.microsecond) <= (
        cutoff_h,
        cutoff_m,
        0,
        0,
    )
    if on_business_day and before_cutoff:
        avail_day = et_day
    else:
        avail_day = next_us_business_day(et_day)
    et_cutoff = datetime(
        avail_day.year, avail_day.month, avail_day.day, cutoff_h, cutoff_m
    )
    return utc_from_eastern_naive(et_cutoff)


def _retrieved_upper_bound(evidence: FilingEvidence) -> datetime | None:
    if evidence.retrieved_at is None:
        return None
    try:
        return parse_utc(evidence.retrieved_at)
    except ValueError:
        return None


def _cap_at_retrieval(
    instant: datetime, retrieved_upper: datetime | None
) -> datetime | None:
    """Cap ``instant`` at the retrieval upper bound (invariant 11).

    Returns the capped instant, or ``None`` if capping is impossible because the
    retrieval bound is itself before the (already floored-at-acceptance) instant
    only when acceptance itself exceeds retrieval — an inconsistent-evidence
    signal the caller turns into ``unknown``. Normal case: ``instant`` unchanged
    when it is already ``<= retrieved_upper``.
    """
    if retrieved_upper is None:
        return instant
    if instant <= retrieved_upper:
        return instant
    # Our estimate overshoots the moment we actually fetched the bytes. Hard
    # evidence wins → cap at retrieval, provided that does not fall before
    # acceptance handling already guaranteed a sane floor.
    return retrieved_upper


def _resolved(
    evidence: FilingEvidence,
    policy: AvailabilityPolicy,
    instant: datetime,
    status: AvailabilityStatus,
    reason: str,
) -> FilingAvailability:
    return FilingAvailability(
        filing_id=evidence.filing_id,
        derived_public_availability_timestamp=format_utc_z(instant.astimezone(UTC)),
        availability_status=status,
        availability_policy_id=policy.availability_policy_id,
        policy_version=f"{policy.policy_id}/{policy.policy_version}",
        policy_confidence=policy.confidence.value,
        policy_status=policy.status.value,
        reason=reason,
        evidence=evidence,
    )


def _unknown(evidence: FilingEvidence, reason: str) -> FilingAvailability:
    return FilingAvailability(
        filing_id=evidence.filing_id,
        derived_public_availability_timestamp=None,
        availability_status=AvailabilityStatus.UNKNOWN,
        availability_policy_id=None,
        policy_version=None,
        policy_confidence=None,
        policy_status=None,
        reason=reason,
        evidence=evidence,
    )
