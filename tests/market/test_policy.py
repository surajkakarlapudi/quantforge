"""Market availability derivation: floors, caps, fail-closed (section 9, D3)."""

from __future__ import annotations

import pytest

from quantforge.availability.model import AvailabilityStatus
from quantforge.market.errors import MarketPolicyConfigurationError
from quantforge.market.model import MarketObservationEvidence
from quantforge.market.policy import (
    MarketAvailabilityPolicy,
    MarketAvailabilityRule,
    derive_market_availability,
    market_eod_std_v1,
    select_market_policy,
)

POLICIES = (market_eod_std_v1(),)


def _ev(
    event_date: str,
    *,
    retrieved_at: str | None = "2024-01-01T00:00:00Z",
    obs_ts: str | None = None,
) -> MarketObservationEvidence:
    return MarketObservationEvidence(
        security_id="cik:9999999999#class:common-stock",
        event_date=event_date,
        observation_timestamp_utc=obs_ts,
        retrieved_at=retrieved_at,
    )


def test_derived_availability_is_close_plus_lag() -> None:
    av = derive_market_availability(_ev("2020-01-02"), POLICIES)
    assert av.availability_status is AvailabilityStatus.DERIVED
    # 16:00 EST + 240 min = 20:00 EST = 01:00 UTC next day.
    assert av.derived_public_availability_timestamp == "2020-01-03T01:00:00Z"
    assert av.is_pit_eligible


def test_availability_is_floored_at_session_close_never_earlier() -> None:
    # A rule with a negative-ish (zero) lag still floors at the session close.
    rule = MarketAvailabilityRule(publication_lag_minutes=0)
    policy = MarketAvailabilityPolicy(
        policy_id="p",
        policy_version="v1",
        effective_from="2007-01-01T00:00:00Z",
        effective_to=None,
        rule_definition=rule,
        status=market_eod_std_v1().status,
        confidence=market_eod_std_v1().confidence,
    )
    av = derive_market_availability(_ev("2020-01-02"), (policy,))
    # 16:00 EST = 21:00 UTC. Never before its own session close.
    assert av.derived_public_availability_timestamp == "2020-01-02T21:00:00Z"


def test_retrieval_before_session_close_fails_closed() -> None:
    # Retrieved at 2020-01-02T00:00Z, before the 21:00Z session close: inconsistent.
    av = derive_market_availability(
        _ev("2020-01-02", retrieved_at="2020-01-02T00:00:00Z"), POLICIES
    )
    assert av.availability_status is AvailabilityStatus.UNKNOWN
    assert av.derived_public_availability_timestamp is None
    assert av.availability_policy_id is None
    assert not av.is_pit_eligible


def test_availability_capped_at_retrieval() -> None:
    # Retrieval between close and close+lag caps the derived instant at retrieval.
    av = derive_market_availability(
        _ev("2020-01-02", retrieved_at="2020-01-02T23:00:00Z"), POLICIES
    )
    assert av.availability_status is AvailabilityStatus.DERIVED
    assert av.derived_public_availability_timestamp == "2020-01-02T23:00:00Z"


def test_session_before_policy_era_is_unknown() -> None:
    av = derive_market_availability(_ev("2005-01-03"), POLICIES)
    assert av.availability_status is AvailabilityStatus.UNKNOWN
    assert not av.is_pit_eligible


def test_missing_session_date_is_unknown() -> None:
    av = derive_market_availability(_ev(""), POLICIES)
    assert av.availability_status is AvailabilityStatus.UNKNOWN


def test_default_policy_never_verified() -> None:
    # dissemination_evidence_trusted is False, so even with an obs timestamp it stays
    # DERIVED, never VERIFIED.
    av = derive_market_availability(
        _ev("2020-01-02", obs_ts="2020-01-02T21:05:00Z"), POLICIES
    )
    assert av.availability_status is AvailabilityStatus.DERIVED


def test_overlapping_policies_fail_closed() -> None:
    p1 = market_eod_std_v1()
    p2 = MarketAvailabilityPolicy(
        policy_id="market-eod-alt",
        policy_version="v1",
        effective_from="2007-01-01T00:00:00Z",
        effective_to=None,
        rule_definition=MarketAvailabilityRule(),
        status=p1.status,
        confidence=p1.confidence,
    )
    with pytest.raises(MarketPolicyConfigurationError):
        select_market_policy(_ev("2020-01-02"), (p1, p2))


def test_unsupported_rule_kind_raises() -> None:
    rule = MarketAvailabilityRule(rule_kind="something-else")
    policy = MarketAvailabilityPolicy(
        policy_id="p",
        policy_version="v1",
        effective_from="2007-01-01T00:00:00Z",
        effective_to=None,
        rule_definition=rule,
        status=market_eod_std_v1().status,
        confidence=market_eod_std_v1().confidence,
    )
    with pytest.raises(MarketPolicyConfigurationError):
        derive_market_availability(_ev("2020-01-02"), (policy,))


def test_derivation_is_deterministic() -> None:
    a = derive_market_availability(_ev("2020-03-16"), POLICIES)
    b = derive_market_availability(_ev("2020-03-16"), POLICIES)
    assert a.to_dict() == b.to_dict()
