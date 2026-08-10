"""Sealing, byte-identical round-trip, derived ids, and pin_mismatch (§8, §9).

:class:`FactorAttribution` is a sealed value: its ``result_hash`` folds the computed
answer, its ``attribution_id`` / ``research_result_id`` are re-derived from its own
fields on every access (never read from stored state), and ``from_dict(to_dict(r))``
re-emits identical bytes. It is deliberately **not** a ``Pit*`` type and exposes no
as-of accessor (FA-2). These tests build a record directly (no corpus needed) to pin
those guarantees.
"""

from __future__ import annotations

import json

from quantforge.attribution.model import (
    AttributionUndefinedReason,
    StatValue,
)
from quantforge.attribution.result import (
    BOUNDARY_PIT,
    FactorAttribution,
)
from quantforge.attribution.version import AttributionEngineVersion

_SPEC = {
    "spec_version": "attribution/1",
    "name": "phase17",
    "subject_id": "sha256:subject",
    "factor_ids": ["sha256:f1", "sha256:f2"],
    "risk_free_per_period": "0",
    "periods_per_year": "1",
}


def _known(v: str) -> StatValue:
    return StatValue.known(v)


def _seal(**overrides: object) -> FactorAttribution:
    kwargs: dict[str, object] = {
        "attribution_engine_version_id": (
            AttributionEngineVersion().attribution_engine_version_id
        ),
        "attribution_spec": _SPEC,
        "subject_ref": ("sha256:subject", "sha256:rh-subject"),
        "factor_refs": (
            ("factor_1", "sha256:f1", "sha256:rh-f1"),
            ("factor_2", "sha256:f2", "sha256:rh-f2"),
        ),
        "boundary_kind": BOUNDARY_PIT,
        "schedule_id": "sha256:schedule",
        "periods": 5,
        "coefficients": (
            ("alpha", _known("2.6"), _known("0.5"), _known("5.2")),
            ("factor_1", _known("2.2"), _known("0.1"), _known("22")),
            ("factor_2", _known("-1"), _known("0.2"), _known("-5")),
        ),
        "diagnostics": (
            ("adjusted_r_squared", _known("0.98")),
            ("r_squared", _known("0.99")),
            ("residual_std_error", _known("0.36")),
        ),
        "decomposition": (
            ("alpha", _known("2.6")),
            ("factor_1", _known("6.6")),
            ("factor_2", _known("-1.2")),
        ),
        "residual_digest": "sha256:resid",
        "risk_free_per_period": "0",
        "periods_per_year": "1",
        "dataset_version_ids": ("sha256:ds",),
        "market_dataset_version_ids": ("sha256:mkt",),
    }
    kwargs.update(overrides)
    return FactorAttribution.seal(**kwargs)  # type: ignore[arg-type]


class TestSealAndIdentity:
    def test_result_hash_and_id_are_prefixed(self) -> None:
        record = _seal()
        assert record.result_hash.startswith("sha256:")
        assert record.attribution_id.startswith("sha256:")

    def test_research_result_id_aliases_attribution_id(self) -> None:
        record = _seal()
        assert record.research_result_id == record.attribution_id

    def test_answer_change_changes_result_hash_and_id(self) -> None:
        base = _seal()
        changed = _seal(
            coefficients=(
                ("alpha", _known("9.9"), _known("0.5"), _known("5.2")),
                ("factor_1", _known("2.2"), _known("0.1"), _known("22")),
                ("factor_2", _known("-1"), _known("0.2"), _known("-5")),
            ),
        )
        assert changed.result_hash != base.result_hash
        assert changed.attribution_id != base.attribution_id


class TestRoundTrip:
    def test_from_dict_of_to_dict_is_byte_identical(self) -> None:
        record = _seal()
        payload = record.to_dict()
        reloaded = FactorAttribution.from_dict(payload)
        assert reloaded == record
        # Byte-identical canonical serialization both ways.
        assert json.dumps(reloaded.to_dict(), sort_keys=True) == json.dumps(
            payload, sort_keys=True
        )

    def test_derived_id_survives_round_trip(self) -> None:
        record = _seal()
        reloaded = FactorAttribution.from_dict(record.to_dict())
        assert reloaded.attribution_id == record.attribution_id
        assert reloaded.result_hash == record.result_hash

    def test_undefined_cells_round_trip(self) -> None:
        record = _seal(
            coefficients=(
                (
                    "alpha",
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                ),
                (
                    "factor_1",
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                ),
                (
                    "factor_2",
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                    StatValue.undefined(AttributionUndefinedReason.SINGULAR_DESIGN),
                ),
            ),
        )
        reloaded = FactorAttribution.from_dict(record.to_dict())
        assert reloaded == record


class TestPinMismatch:
    def test_single_shared_pin_is_not_a_mismatch(self) -> None:
        assert _seal().pin_mismatch is False

    def test_multiple_dataset_pins_is_a_mismatch(self) -> None:
        record = _seal(dataset_version_ids=("sha256:ds1", "sha256:ds2"))
        assert record.pin_mismatch is True

    def test_multiple_market_pins_is_a_mismatch(self) -> None:
        record = _seal(market_dataset_version_ids=("sha256:m1", "sha256:m2"))
        assert record.pin_mismatch is True


class TestNotPit:
    def test_boundary_documents_input_side_only(self) -> None:
        assert _seal().boundary_kind == "pit"

    def test_is_not_a_pit_type_and_has_no_as_of_accessor(self) -> None:
        record = _seal()
        # FA-2: an ex-post statistic, never a forward-usable PIT value.
        assert type(record).__name__ == "FactorAttribution"
        assert not hasattr(record, "as_of")
        assert not hasattr(record, "as_of_date")
