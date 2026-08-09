"""PerformanceAnalytics: sealing, round-trip, derived-id re-emission, pin surfacing.

Covers proposal §J.2 / §L / §N / D1 / D6: the record seals the computed answer into
``result_hash``; ``to_dict`` / ``from_dict`` round-trips byte-identically; the derived
``analytics_id`` / ``research_result_id`` are re-emitted from fields (never read from
stored state), so a tampered stored id is ignored; and ``pin_mismatch`` surfaces a
corpus-pin disagreement without raising.
"""

from __future__ import annotations

from quantforge.analytics.model import AnalyticsUndefinedReason, StatValue
from quantforge.analytics.result import (
    ANALYTICS_RESULT_FORMAT_VERSION,
    BOUNDARY_PIT,
    PerformanceAnalytics,
)
from quantforge.analytics.spec import AnalyticsSpecification


def _spec_dict(**kw: object) -> dict[str, object]:
    base = AnalyticsSpecification(
        name="r",
        subject_id="sha256:subject",
        benchmark_id=kw.get("benchmark_id"),  # type: ignore[arg-type]
    )
    return base.to_dict()


def _seal(
    *,
    benchmark_ref: tuple[str, str] | None = None,
    dataset_version_ids: tuple[str, ...] = ("sha256:ds",),
    market_dataset_version_ids: tuple[str, ...] = ("sha256:mkt",),
) -> PerformanceAnalytics:
    return PerformanceAnalytics.seal(
        analytics_engine_version_id="sha256:engine",
        analytics_spec=_spec_dict(
            benchmark_id=None if benchmark_ref is None else benchmark_ref[0]
        ),
        subject_ref=("sha256:subject", "sha256:subjecthash"),
        benchmark_ref=benchmark_ref,
        boundary_kind=BOUNDARY_PIT,
        schedule_id="sha256:sched",
        periods=3,
        absolute=(
            ("calmar", StatValue.known("0.4")),
            ("sortino", StatValue.undefined(AnalyticsUndefinedReason.ZERO_DOWNSIDE)),
        ),
        relative=(("beta", StatValue.known("1")),) if benchmark_ref else (),
        var=(("0.95", StatValue.known("-0.1"), StatValue.known("-0.1")),),
        risk_free_per_period="0",
        periods_per_year="1",
        dataset_version_ids=dataset_version_ids,
        market_dataset_version_ids=market_dataset_version_ids,
    )


class TestSealing:
    def test_format_version_is_pinned(self) -> None:
        assert ANALYTICS_RESULT_FORMAT_VERSION == "analytics-result/1"

    def test_result_hash_folds_the_answer(self) -> None:
        base = _seal()
        different = PerformanceAnalytics.seal(
            analytics_engine_version_id="sha256:engine",
            analytics_spec=_spec_dict(),
            subject_ref=("sha256:subject", "sha256:subjecthash"),
            benchmark_ref=None,
            boundary_kind=BOUNDARY_PIT,
            schedule_id="sha256:sched",
            periods=3,
            absolute=(("calmar", StatValue.known("0.5")),),  # changed value
            relative=(),
            var=(("0.95", StatValue.known("-0.1"), StatValue.known("-0.1")),),
            risk_free_per_period="0",
            periods_per_year="1",
            dataset_version_ids=("sha256:ds",),
            market_dataset_version_ids=("sha256:mkt",),
        )
        assert base.result_hash != different.result_hash


class TestRoundTrip:
    def test_to_dict_from_dict_is_byte_identical(self) -> None:
        record = _seal(benchmark_ref=("sha256:bench", "sha256:benchhash"))
        loaded = PerformanceAnalytics.from_dict(record.to_dict())
        assert loaded.to_dict() == record.to_dict()
        assert loaded.result_hash == record.result_hash
        assert loaded.analytics_id == record.analytics_id

    def test_research_result_id_aliases_analytics_id(self) -> None:
        record = _seal()
        assert record.research_result_id == record.analytics_id


class TestDerivedIds:
    def test_tampered_stored_id_is_ignored(self) -> None:
        record = _seal()
        payload = record.to_dict()
        payload["analytics_id"] = "sha256:tampered"
        payload["research_result_id"] = "sha256:tampered"
        loaded = PerformanceAnalytics.from_dict(payload)
        # The id is re-derived from fields, so the tampered value is ignored.
        assert loaded.analytics_id == record.analytics_id
        assert loaded.analytics_id != "sha256:tampered"

    def test_benchmark_reference_changes_identity(self) -> None:
        without = _seal()
        with_bench = _seal(benchmark_ref=("sha256:bench", "sha256:benchhash"))
        assert without.analytics_id != with_bench.analytics_id


class TestPinMismatch:
    def test_absolute_only_record_never_flags(self) -> None:
        record = _seal(dataset_version_ids=("sha256:ds1", "sha256:ds2"))
        assert record.pin_mismatch is False

    def test_single_shared_pin_does_not_flag(self) -> None:
        record = _seal(benchmark_ref=("sha256:bench", "sha256:benchhash"))
        assert record.pin_mismatch is False

    def test_distinct_fundamentals_pin_flags(self) -> None:
        record = _seal(
            benchmark_ref=("sha256:bench", "sha256:benchhash"),
            dataset_version_ids=("sha256:ds1", "sha256:ds2"),
        )
        assert record.pin_mismatch is True

    def test_distinct_market_pin_flags(self) -> None:
        record = _seal(
            benchmark_ref=("sha256:bench", "sha256:benchhash"),
            market_dataset_version_ids=("sha256:m1", "sha256:m2"),
        )
        assert record.pin_mismatch is True
