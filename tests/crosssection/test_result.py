"""Sealing + serialization tests for the result records (§3.2, §5).

The sealed record re-derives its id from its own fields (never stored state),
round-trips byte-identically through ``from_dict``, and folds every computed cell (but
not coverage) into ``result_hash``. These tests pin that discipline without touching a
store.
"""

from __future__ import annotations

import pytest

from quantforge.crosssection.model import (
    CoverageSummary,
    CrossSectionUndefinedReason,
    DateCoverage,
    PerDateCoefficients,
    PremiumEstimate,
    StatValue,
)
from quantforge.crosssection.result import (
    BOUNDARY_PIT,
    CrossSectionalRegression,
)


def _per_date() -> tuple[PerDateCoefficients, ...]:
    return (
        PerDateCoefficients(
            as_of="2024-01-15T00:00:00Z",
            n_members=5,
            coefficients=(
                ("alpha", StatValue.known("0.1")),
                ("factor_1", StatValue.known("0.02")),
            ),
            r_squared=StatValue.known("0.9"),
        ),
        PerDateCoefficients(
            as_of="2024-02-15T00:00:00Z",
            n_members=5,
            coefficients=(
                ("alpha", StatValue.known("0.11")),
                ("factor_1", StatValue.known("0.04")),
            ),
            r_squared=StatValue.known("0.95"),
        ),
    )


def _premia() -> tuple[PremiumEstimate, ...]:
    return (
        PremiumEstimate(
            label="alpha",
            mean=StatValue.known("0.105"),
            std_error=StatValue.known("0.005"),
            t_stat=StatValue.known("21"),
            n_valid_dates=2,
        ),
        PremiumEstimate(
            label="factor_1",
            mean=StatValue.known("0.03"),
            std_error=StatValue.known("0.01"),
            t_stat=StatValue.known("3"),
            n_valid_dates=2,
        ),
    )


def _coverage() -> CoverageSummary:
    return CoverageSummary(
        per_date=(
            DateCoverage(
                as_of="2024-01-15T00:00:00Z",
                resolved_members=5,
                eligible=5,
                dropped_for_signal=0,
                dropped_for_return=0,
                regression_status="known",
            ),
        ),
        total_eligible=10,
        total_dropped_for_signal=0,
        total_dropped_for_return=0,
        total_dropped_for_singular_date=0,
    )


def _seal(**overrides: object) -> CrossSectionalRegression:
    kwargs: dict[str, object] = {
        "crosssection_engine_version_id": "sha256:eng",
        "crosssection_spec": {"name": "x"},
        "name": "x",
        "spec_version": "crosssection/1",
        "factor_descriptors": (("current_ratio", "p1"),),
        "universe_specification_id": "sha256:u",
        "schedule_id": "sha256:s",
        "horizon_days": 1,
        "include_intercept": True,
        "boundary_kind": BOUNDARY_PIT,
        "dataset_version_id": "sha256:fund",
        "market_dataset_version_id": "sha256:mkt",
        "per_date": _per_date(),
        "premia": _premia(),
        "coverage": _coverage(),
    }
    kwargs.update(overrides)
    return CrossSectionalRegression.seal(**kwargs)  # type: ignore[arg-type]


# -- sealing + identity ------------------------------------------------------


def test_seal_produces_stable_hashes() -> None:
    a = _seal()
    b = _seal()
    assert a.result_hash == b.result_hash
    assert a.crosssection_id == b.crosssection_id


def test_research_result_id_aliases_crosssection_id() -> None:
    reg = _seal()
    assert reg.research_result_id == reg.crosssection_id


def test_boundary_kind_is_pit() -> None:
    assert _seal().boundary_kind == "pit"


def test_result_hash_changes_with_a_coefficient() -> None:
    base = _seal()
    changed_pd = list(_per_date())
    changed_pd[0] = PerDateCoefficients(
        as_of="2024-01-15T00:00:00Z",
        n_members=5,
        coefficients=(
            ("alpha", StatValue.known("0.999")),
            ("factor_1", StatValue.known("0.02")),
        ),
        r_squared=StatValue.known("0.9"),
    )
    other = _seal(per_date=tuple(changed_pd))
    assert other.result_hash != base.result_hash


def test_coverage_not_folded_into_result_hash() -> None:
    base = _seal()
    other_coverage = CoverageSummary(
        per_date=(),
        total_eligible=999,
        total_dropped_for_signal=7,
        total_dropped_for_return=3,
        total_dropped_for_singular_date=1,
    )
    other = _seal(coverage=other_coverage)
    assert other.result_hash == base.result_hash
    assert other.crosssection_id == base.crosssection_id


# -- round-trip --------------------------------------------------------------


def test_round_trip_is_byte_identical() -> None:
    reg = _seal()
    restored = CrossSectionalRegression.from_dict(reg.to_dict())
    assert restored.to_dict() == reg.to_dict()
    assert restored.crosssection_id == reg.crosssection_id


def test_round_trip_preserves_undefined_cells() -> None:
    undefined_block = PerDateCoefficients(
        as_of="2024-01-15T00:00:00Z",
        n_members=1,
        coefficients=(
            (
                "alpha",
                StatValue.undefined(CrossSectionUndefinedReason.INSUFFICIENT_MEMBERS),
            ),
            (
                "factor_1",
                StatValue.undefined(CrossSectionUndefinedReason.INSUFFICIENT_MEMBERS),
            ),
        ),
        r_squared=StatValue.undefined(CrossSectionUndefinedReason.INSUFFICIENT_MEMBERS),
    )
    per_date = (undefined_block, *_per_date())
    reg = _seal(per_date=per_date)
    restored = CrossSectionalRegression.from_dict(reg.to_dict())
    assert restored.to_dict() == reg.to_dict()


def test_tampered_stored_id_is_ignored() -> None:
    reg = _seal()
    payload = reg.to_dict()
    payload["crosssection_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = CrossSectionalRegression.from_dict(payload)
    # The id is re-derived from the real fields, not the tampered stored value.
    assert restored.crosssection_id == reg.crosssection_id


def test_from_dict_rejects_malformed_cell() -> None:
    reg = _seal()
    payload = reg.to_dict()
    per_date = payload["per_date"]
    assert isinstance(per_date, list)
    first = per_date[0]
    assert isinstance(first, dict)
    first["r_squared"] = {"status": "bogus"}
    with pytest.raises(ValueError):
        CrossSectionalRegression.from_dict(payload)
