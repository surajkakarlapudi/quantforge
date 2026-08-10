"""Sealing + serialization tests for the sealed record (§5.5, §5.6).

The sealed record re-derives its id from its own fields (never stored state),
round-trips byte-identically through ``from_dict``, and folds every computed cell (but
not leg membership or coverage) into ``result_hash``. These tests pin that discipline
without touching a store.
"""

from __future__ import annotations

import pytest

from quantforge.factorportfolio.model import (
    CoverageSummary,
    DateCoverage,
    FactorPortfolioUndefinedReason,
    FactorReturnSummary,
    LegKind,
    LegMembership,
    PerPeriodReturn,
    StatValue,
)
from quantforge.factorportfolio.result import (
    BOUNDARY_PIT,
    FactorPortfolio,
)


def _per_period() -> tuple[PerPeriodReturn, ...]:
    return (
        PerPeriodReturn(
            as_of="2024-01-15T00:00:00Z",
            n_members=4,
            long_membership=LegMembership(kind=LegKind.LONG, company_ids=("c", "d")),
            short_membership=LegMembership(kind=LegKind.SHORT, company_ids=("a", "b")),
            long_return=StatValue.known("0.35"),
            short_return=StatValue.known("0.15"),
            factor_return=StatValue.known("0.20"),
        ),
        PerPeriodReturn(
            as_of="2024-02-15T00:00:00Z",
            n_members=4,
            long_membership=LegMembership(kind=LegKind.LONG, company_ids=("c", "d")),
            short_membership=LegMembership(kind=LegKind.SHORT, company_ids=("a", "b")),
            long_return=StatValue.known("0.34"),
            short_return=StatValue.known("0.10"),
            factor_return=StatValue.known("0.24"),
        ),
    )


def _summary() -> FactorReturnSummary:
    return FactorReturnSummary(
        cumulative_return=StatValue.known("0.4688"),
        mean_period_return=StatValue.known("0.22"),
        volatility=StatValue.known("0.02"),
        annualized_sharpe=StatValue.known("11"),
        mean_t_stat=StatValue.known("15.5"),
        hit_rate=StatValue.known("1"),
        n_valid_periods=2,
    )


def _coverage() -> CoverageSummary:
    return CoverageSummary(
        per_date=(
            DateCoverage(
                as_of="2024-01-15T00:00:00Z",
                resolved_members=4,
                eligible=4,
                dropped_for_signal=0,
                dropped_for_return=0,
                period_status="known",
            ),
        ),
        total_resolved=8,
        total_dropped_for_signal=0,
        total_dropped_for_return=0,
        total_undefined_periods=0,
    )


def _seal(**overrides: object) -> FactorPortfolio:
    kwargs: dict[str, object] = {
        "factor_portfolio_engine_version_id": "sha256:eng",
        "factor_portfolio_spec": {"name": "x"},
        "name": "x",
        "spec_version": "factorportfolio/1",
        "signal": "current_ratio",
        "period_key": "p1",
        "universe_specification_id": "sha256:u",
        "schedule_id": "sha256:s",
        "horizon_days": 1,
        "quantiles": 2,
        "weighting": "equal",
        "boundary_kind": BOUNDARY_PIT,
        "risk_free_per_period": "0",
        "periods_per_year": "1",
        "dataset_version_id": "sha256:fund",
        "market_dataset_version_id": "sha256:mkt",
        "per_period": _per_period(),
        "summary": _summary(),
        "coverage": _coverage(),
    }
    kwargs.update(overrides)
    return FactorPortfolio.seal(**kwargs)  # type: ignore[arg-type]


# -- sealing + identity ------------------------------------------------------


def test_seal_produces_stable_hashes() -> None:
    a = _seal()
    b = _seal()
    assert a.result_hash == b.result_hash
    assert a.factor_portfolio_id == b.factor_portfolio_id


def test_research_result_id_aliases_factor_portfolio_id() -> None:
    r = _seal()
    assert r.research_result_id == r.factor_portfolio_id


def test_boundary_kind_is_pit() -> None:
    assert _seal().boundary_kind == "pit"


def test_result_hash_changes_with_a_factor_return() -> None:
    base = _seal()
    changed = list(_per_period())
    changed[0] = PerPeriodReturn(
        as_of="2024-01-15T00:00:00Z",
        n_members=4,
        long_membership=LegMembership(kind=LegKind.LONG, company_ids=("c", "d")),
        short_membership=LegMembership(kind=LegKind.SHORT, company_ids=("a", "b")),
        long_return=StatValue.known("0.35"),
        short_return=StatValue.known("0.15"),
        factor_return=StatValue.known("0.999"),
    )
    other = _seal(per_period=tuple(changed))
    assert other.result_hash != base.result_hash


def test_leg_membership_not_folded_into_result_hash() -> None:
    # Membership is audit metadata (§5.6): changing only it leaves the hash and id
    # stable.
    base = _seal()
    changed = list(_per_period())
    first = changed[0]
    changed[0] = PerPeriodReturn(
        as_of=first.as_of,
        n_members=first.n_members,
        long_membership=LegMembership(kind=LegKind.LONG, company_ids=("x", "y")),
        short_membership=LegMembership(kind=LegKind.SHORT, company_ids=("p", "q")),
        long_return=first.long_return,
        short_return=first.short_return,
        factor_return=first.factor_return,
    )
    other = _seal(per_period=tuple(changed))
    assert other.result_hash == base.result_hash
    assert other.factor_portfolio_id == base.factor_portfolio_id


def test_coverage_not_folded_into_result_hash() -> None:
    base = _seal()
    other = _seal(
        coverage=CoverageSummary(
            per_date=(),
            total_resolved=999,
            total_dropped_for_signal=7,
            total_dropped_for_return=3,
            total_undefined_periods=2,
        )
    )
    assert other.result_hash == base.result_hash
    assert other.factor_portfolio_id == base.factor_portfolio_id


# -- round-trip --------------------------------------------------------------


def test_round_trip_is_byte_identical() -> None:
    r = _seal()
    restored = FactorPortfolio.from_dict(r.to_dict())
    assert restored.to_dict() == r.to_dict()
    assert restored.factor_portfolio_id == r.factor_portfolio_id


def test_round_trip_preserves_undefined_cells() -> None:
    undefined_period = PerPeriodReturn(
        as_of="2024-03-15T00:00:00Z",
        n_members=3,
        long_membership=LegMembership(kind=LegKind.LONG, company_ids=()),
        short_membership=LegMembership(kind=LegKind.SHORT, company_ids=()),
        long_return=StatValue.undefined(
            FactorPortfolioUndefinedReason.INSUFFICIENT_MEMBERS
        ),
        short_return=StatValue.undefined(
            FactorPortfolioUndefinedReason.INSUFFICIENT_MEMBERS
        ),
        factor_return=StatValue.undefined(
            FactorPortfolioUndefinedReason.INSUFFICIENT_MEMBERS
        ),
    )
    r = _seal(per_period=(*_per_period(), undefined_period))
    restored = FactorPortfolio.from_dict(r.to_dict())
    assert restored.to_dict() == r.to_dict()


def test_tampered_stored_id_is_ignored() -> None:
    r = _seal()
    payload = r.to_dict()
    payload["factor_portfolio_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = FactorPortfolio.from_dict(payload)
    # The id is re-derived from the real fields, not the tampered stored value.
    assert restored.factor_portfolio_id == r.factor_portfolio_id


def test_from_dict_rejects_malformed_cell() -> None:
    r = _seal()
    payload = r.to_dict()
    per_period = payload["per_period"]
    assert isinstance(per_period, list)
    first = per_period[0]
    assert isinstance(first, dict)
    first["factor_return"] = {"status": "bogus"}
    with pytest.raises(ValueError):
        FactorPortfolio.from_dict(payload)
