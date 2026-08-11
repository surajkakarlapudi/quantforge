"""Sealing + serialization tests for the sealed factor-risk record (§9, §10).

The sealed record re-derives its id from its own fields (never stored state),
round-trips byte-identically through ``from_dict``, and folds every computed cell (but
not coverage) into ``result_hash``. These tests pin that discipline without touching a
store.
"""

from __future__ import annotations

import pytest

from quantforge.factorrisk.model import (
    CorrelationCell,
    CovarianceCell,
    CoverageSummary,
    FactorCoverage,
    FactorMoment,
    FactorRiskUndefinedReason,
    StatValue,
)
from quantforge.factorrisk.result import BOUNDARY_PIT, FactorRiskModel


def _factors() -> tuple[FactorMoment, ...]:
    return (
        FactorMoment(
            label="factor_1",
            mean=StatValue.known("0.10"),
            volatility=StatValue.known("0.02"),
            annualized_volatility=StatValue.known("0.04"),
        ),
        FactorMoment(
            label="factor_2",
            mean=StatValue.known("0.05"),
            volatility=StatValue.known("0.03"),
            annualized_volatility=StatValue.known("0.06"),
        ),
    )


def _covariance() -> tuple[CovarianceCell, ...]:
    return (
        CovarianceCell(
            i=0,
            j=0,
            value=StatValue.known("0.0004"),
            annualized=StatValue.known("0.0016"),
        ),
        CovarianceCell(
            i=0,
            j=1,
            value=StatValue.known("0.0002"),
            annualized=StatValue.known("0.0008"),
        ),
        CovarianceCell(
            i=1,
            j=1,
            value=StatValue.known("0.0009"),
            annualized=StatValue.known("0.0036"),
        ),
    )


def _correlation() -> tuple[CorrelationCell, ...]:
    return (
        CorrelationCell(i=0, j=0, value=StatValue.known("1")),
        CorrelationCell(i=0, j=1, value=StatValue.known("0.333")),
        CorrelationCell(i=1, j=1, value=StatValue.known("1")),
    )


def _coverage() -> CoverageSummary:
    return CoverageSummary(
        per_factor=(
            FactorCoverage(
                label="factor_1", factor_portfolio_id="sha256:a", available=2, used=2
            ),
            FactorCoverage(
                label="factor_2", factor_portfolio_id="sha256:b", available=2, used=2
            ),
        ),
        aligned_periods=2,
        dropped_for_alignment=0,
    )


def _seal(**overrides: object) -> FactorRiskModel:
    kwargs: dict[str, object] = {
        "factor_risk_engine_version_id": "sha256:eng",
        "factor_risk_spec": {"name": "x", "spec_version": "factorrisk/1"},
        "factor_refs": (
            ("factor_1", "sha256:a", "sha256:rh-a"),
            ("factor_2", "sha256:b", "sha256:rh-b"),
        ),
        "boundary_kind": BOUNDARY_PIT,
        "schedule_id": "sha256:s",
        "factor_portfolio_engine_version_id": "sha256:fpe",
        "periods": 2,
        "periods_per_year": "1",
        "factors": _factors(),
        "covariance": _covariance(),
        "correlation": _correlation(),
        "coverage": _coverage(),
        "dataset_version_ids": ("sha256:fund",),
        "market_dataset_version_ids": ("sha256:mkt",),
    }
    kwargs.update(overrides)
    return FactorRiskModel.seal(**kwargs)  # type: ignore[arg-type]


# -- sealing + identity ------------------------------------------------------


def test_seal_produces_stable_hashes() -> None:
    a = _seal()
    b = _seal()
    assert a.result_hash == b.result_hash
    assert a.factor_risk_id == b.factor_risk_id


def test_research_result_id_aliases_factor_risk_id() -> None:
    r = _seal()
    assert r.research_result_id == r.factor_risk_id


def test_boundary_kind_is_pit() -> None:
    assert _seal().boundary_kind == "pit"


def test_factor_portfolio_ids_follow_ref_order() -> None:
    assert _seal().factor_portfolio_ids == ("sha256:a", "sha256:b")


def test_result_hash_changes_with_a_covariance_cell() -> None:
    base = _seal()
    changed = list(_covariance())
    changed[1] = CovarianceCell(
        i=0, j=1, value=StatValue.known("0.9999"), annualized=StatValue.known("0.0008")
    )
    other = _seal(covariance=tuple(changed))
    assert other.result_hash != base.result_hash


def test_coverage_not_folded_into_result_hash() -> None:
    base = _seal()
    other = _seal(
        coverage=CoverageSummary(
            per_factor=(),
            aligned_periods=999,
            dropped_for_alignment=7,
        )
    )
    assert other.result_hash == base.result_hash
    assert other.factor_risk_id == base.factor_risk_id


def test_pin_mismatch_flags_multiple_pins() -> None:
    assert _seal().pin_mismatch is False
    assert _seal(dataset_version_ids=("sha256:f1", "sha256:f2")).pin_mismatch is True
    assert (
        _seal(market_dataset_version_ids=("sha256:m1", "sha256:m2")).pin_mismatch
        is True
    )


# -- round-trip --------------------------------------------------------------


def test_round_trip_is_byte_identical() -> None:
    r = _seal()
    restored = FactorRiskModel.from_dict(r.to_dict())
    assert restored.to_dict() == r.to_dict()
    assert restored.factor_risk_id == r.factor_risk_id


def test_round_trip_preserves_undefined_correlation() -> None:
    correlation = (
        CorrelationCell(i=0, j=0, value=StatValue.known("1")),
        CorrelationCell(
            i=0,
            j=1,
            value=StatValue.undefined(FactorRiskUndefinedReason.ZERO_VARIANCE),
        ),
        CorrelationCell(
            i=1,
            j=1,
            value=StatValue.undefined(FactorRiskUndefinedReason.ZERO_VARIANCE),
        ),
    )
    r = _seal(correlation=correlation)
    restored = FactorRiskModel.from_dict(r.to_dict())
    assert restored.to_dict() == r.to_dict()


def test_tampered_stored_id_is_ignored() -> None:
    r = _seal()
    payload = r.to_dict()
    payload["factor_risk_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = FactorRiskModel.from_dict(payload)
    assert restored.factor_risk_id == r.factor_risk_id


def test_from_dict_rejects_malformed_cell() -> None:
    r = _seal()
    payload = r.to_dict()
    covariance = payload["covariance"]
    assert isinstance(covariance, list)
    first = covariance[0]
    assert isinstance(first, dict)
    first["value"] = {"status": "bogus"}
    with pytest.raises(ValueError):
        FactorRiskModel.from_dict(payload)
