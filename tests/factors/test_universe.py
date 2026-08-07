"""Tests for :class:`Universe` — the explicit, ordered, content-addressed set (§7.1).

Covers: ordering preserved; de-duplication (first-seen order kept); bare-CIK /
``cik:``-prefixed canonicalization to one member; empty universe fails closed;
``universe_id`` determinism and sensitivity to both membership and order.
"""

from __future__ import annotations

import pytest

from quantforge.factors.errors import FactorConfigurationError
from quantforge.factors.universe import Universe


def test_of_canonicalizes_bare_and_prefixed_to_one_member() -> None:
    # A bare int, its string form, an unpadded and a padded cik: all collapse.
    uni = Universe.of(320193, "320193", "cik:320193", "cik:0000320193")
    assert uni.members == ("cik:0000320193",)


def test_order_is_preserved() -> None:
    uni = Universe.of(789019, 320193, 1652044)
    assert uni.members == (
        "cik:0000789019",
        "cik:0000320193",
        "cik:0001652044",
    )


def test_deduplication_keeps_first_seen_order() -> None:
    uni = Universe.of(320193, 789019, 320193, 1652044, 789019)
    assert uni.members == (
        "cik:0000320193",
        "cik:0000789019",
        "cik:0001652044",
    )


def test_empty_universe_fails_closed() -> None:
    with pytest.raises(FactorConfigurationError):
        Universe.of()


def test_all_duplicates_collapsing_is_not_empty() -> None:
    # Distinct spellings of one filer are still one filer — a valid universe.
    uni = Universe.of(320193, "cik:0000320193")
    assert len(uni) == 1


def test_unusable_member_fails_closed() -> None:
    with pytest.raises(FactorConfigurationError):
        Universe.of("not-a-cik")


def test_universe_id_is_sha256_prefixed_and_deterministic() -> None:
    uni = Universe.of(320193, 789019)
    assert uni.universe_id.startswith("sha256:")
    assert uni.universe_id == Universe.of(320193, 789019).universe_id


def test_universe_id_is_order_sensitive() -> None:
    assert (
        Universe.of(320193, 789019).universe_id
        != Universe.of(789019, 320193).universe_id
    )


def test_universe_id_is_membership_sensitive() -> None:
    assert Universe.of(320193).universe_id != Universe.of(320193, 789019).universe_id


def test_from_iterable_matches_of() -> None:
    assert (
        Universe.from_iterable([320193, 789019]).universe_id
        == Universe.of(320193, 789019).universe_id
    )


def test_iteration_yields_canonical_members_in_order() -> None:
    uni = Universe.of(789019, 320193)
    assert list(uni) == ["cik:0000789019", "cik:0000320193"]
