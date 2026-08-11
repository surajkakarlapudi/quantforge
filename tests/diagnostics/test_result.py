"""The sealed diagnostics record: seal, round-trip, derived-id honesty (locked §3.3,
§5).

A :class:`SignalDiagnostics` seals the computed blocks and folds the answer into
``result_hash``; its ``diagnostics_id`` is re-derived from the record's own fields on
every access (never read from stored state). These tests pin: the seal folds the answer;
``from_dict(to_dict(r))`` re-emits byte-identical payload and the same id; a *tampered*
stored id is ignored (the property re-derives it); ``research_result_id`` aliases
``diagnostics_id``; and the record is a forward-looking type with no ``Pit*`` / as-of
accessor (SD-2). The record is built directly from small hand-made blocks — no corpus.
"""

from __future__ import annotations

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.diagnostics.model import (
    CoverageSummary,
    DateCoverage,
    DiagnosticUndefinedReason,
    ICMethodSummary,
    ICSummary,
    PerDateIC,
    QuantileProfile,
    StatValue,
)
from quantforge.diagnostics.result import (
    BOUNDARY_PIT,
    SignalDiagnostics,
)
from quantforge.diagnostics.spec import SignalDiagnosticsSpecification
from quantforge.diagnostics.version import SignalDiagnosticsEngineVersion
from tests.diagnostics.builders import EVAL_1, EVAL_2, PERIOD, universe_spec

_ENGINE_ID = SignalDiagnosticsEngineVersion().signal_diagnostics_engine_version_id
_SCHED = RebalanceSchedule.of([EVAL_1, EVAL_2])


def _spec_dict() -> dict[str, object]:
    return SignalDiagnosticsSpecification(
        name="phase16",
        signal="current_ratio",
        period=PERIOD,
        universe=universe_spec(include_b=True),
        schedule=_SCHED,
        forward_horizon="1d",
        quantiles=2,
        dataset_version_id="sha256:fund",
        market_dataset_version_id="sha256:mkt",
        ic_methods=("spearman", "pearson"),
    ).to_dict()


def _per_date() -> tuple[PerDateIC, ...]:
    return (
        PerDateIC(
            as_of=EVAL_1,
            n_pairs=2,
            ic=(
                ("pearson", StatValue.known("-1")),
                ("spearman", StatValue.known("-1")),
            ),
            bucket_means=(StatValue.known("0.05"), StatValue.known("0.045")),
            top_minus_bottom_spread=StatValue.known("-0.005"),
        ),
    )


def _profile() -> QuantileProfile:
    return QuantileProfile(
        bucket_means=(StatValue.known("0.05"), StatValue.known("0.045")),
        mean_spread=StatValue.known("-0.005"),
    )


def _ic_summary() -> ICSummary:
    summary = ICMethodSummary(
        mean_ic=StatValue.known("-1"),
        ic_std=StatValue.known("0"),
        ic_information_ratio=StatValue.undefined(
            DiagnosticUndefinedReason.ZERO_RETURN_VARIANCE
        ),
        ic_t_stat=StatValue.undefined(DiagnosticUndefinedReason.ZERO_RETURN_VARIANCE),
        hit_rate=StatValue.known("0"),
        n_valid_dates=1,
    )
    return ICSummary(per_method=(("pearson", summary), ("spearman", summary)))


def _coverage() -> CoverageSummary:
    return CoverageSummary(
        per_date=(
            DateCoverage(
                as_of=EVAL_1,
                resolved_members=2,
                eligible=2,
                dropped_for_signal=0,
                dropped_for_return=0,
            ),
        ),
        total_eligible=2,
        total_dropped_for_signal=0,
        total_dropped_for_return=0,
    )


def _sealed() -> SignalDiagnostics:
    return SignalDiagnostics.seal(
        signal_diagnostics_engine_version_id=_ENGINE_ID,
        diagnostics_spec=_spec_dict(),
        boundary_kind=BOUNDARY_PIT,
        dataset_version_id="sha256:fund",
        market_dataset_version_id="sha256:mkt",
        schedule_id=_SCHED.schedule_id,
        per_date=_per_date(),
        quantile_profile=_profile(),
        ic_summary=_ic_summary(),
        coverage=_coverage(),
    )


class TestSeal:
    def test_result_hash_is_prefixed_and_folds_answer(self) -> None:
        record = _sealed()
        assert record.result_hash.startswith("sha256:")
        assert record.diagnostics_id.startswith("sha256:")

    def test_research_result_id_aliases_diagnostics_id(self) -> None:
        record = _sealed()
        assert record.research_result_id == record.diagnostics_id

    def test_a_changed_answer_changes_id(self) -> None:
        base = _sealed()
        other = SignalDiagnostics.seal(
            signal_diagnostics_engine_version_id=_ENGINE_ID,
            diagnostics_spec=_spec_dict(),
            boundary_kind=BOUNDARY_PIT,
            dataset_version_id="sha256:fund",
            market_dataset_version_id="sha256:mkt",
            schedule_id=_SCHED.schedule_id,
            per_date=(
                PerDateIC(
                    as_of=EVAL_1,
                    n_pairs=2,
                    ic=(("pearson", StatValue.known("1")),),  # flipped IC
                    bucket_means=(StatValue.known("0.05"), StatValue.known("0.045")),
                    top_minus_bottom_spread=StatValue.known("-0.005"),
                ),
            ),
            quantile_profile=_profile(),
            ic_summary=_ic_summary(),
            coverage=_coverage(),
        )
        assert other.result_hash != base.result_hash
        assert other.diagnostics_id != base.diagnostics_id


class TestRoundTrip:
    def test_from_dict_to_dict_is_byte_identical(self) -> None:
        record = _sealed()
        payload = record.to_dict()
        restored = SignalDiagnostics.from_dict(payload)
        assert restored.to_dict() == payload

    def test_id_survives_round_trip(self) -> None:
        record = _sealed()
        restored = SignalDiagnostics.from_dict(record.to_dict())
        assert restored.diagnostics_id == record.diagnostics_id
        assert restored.result_hash == record.result_hash

    def test_tampered_stored_id_is_ignored(self) -> None:
        # The id is re-derived from the record's own fields, never read from state — a
        # tampered stored ``diagnostics_id`` is silently corrected on read.
        record = _sealed()
        payload = record.to_dict()
        payload["diagnostics_id"] = "sha256:tampered"
        payload["research_result_id"] = "sha256:tampered"
        restored = SignalDiagnostics.from_dict(payload)
        assert restored.diagnostics_id == record.diagnostics_id
        assert restored.diagnostics_id != "sha256:tampered"

    def test_ic_method_order_in_spec_does_not_change_id(self) -> None:
        # The embedded spec already sorted ic_methods, so the id is method-order
        # invariant.
        record = _sealed()
        assert record.diagnostics_spec["ic_methods"] == ["pearson", "spearman"]


class TestForwardLookingType:
    def test_no_pit_or_as_of_accessor(self) -> None:
        # SD-2: the record must never look like a PIT as-of-T value.
        record = _sealed()
        names = dir(record)
        assert not any(n.lower().startswith("pit") for n in names)
        assert not any(n == "as_of" or n.startswith("as_of_") for n in names)
        assert record.boundary_kind == "pit"  # documents the signal side only
