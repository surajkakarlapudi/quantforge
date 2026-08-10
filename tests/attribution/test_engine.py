"""AttributionEngine: resolve, verify, regress, seal, persist — end to end (§6, §11).

Covers the engine orchestration the pure-``Decimal`` numerics in ``test_stats.py`` skip:
the engine analyses only already-sealed PIT-correct backtests from the shared sidecar
(a subject plus *K* factors), verifies each (present, id-consistent, un-drifted),
enforces commensurability (FA-3) and the residual-df floor (§11), regresses, seals a
content-addressed record write-once (D1/D2), and fails closed on any missing / drifted
reference, incommensurable factor, or too-short subject. The same spec over the same
immutable sidecar rebuilds a byte-identical record, and the sealed record is ex-post,
not a PIT value (FA-2).

The corpus has only two tradable securities, so distinct commensurable return series
come from varying the *strategy* over one shared schedule: a top-1 descending subject
(holds filer B), a top-1 ascending factor (holds filer A), and a top-2 blend (holds
both) as a second, non-collinear factor for the genuine two-factor case.
"""

from __future__ import annotations

import json

import pytest

from quantforge.attribution.engine import AttributionEngine
from quantforge.attribution.errors import (
    AttributionConfigurationError,
    AttributionConsistencyError,
)
from quantforge.attribution.result import BOUNDARY_PIT, FactorAttribution
from tests.attribution.builders import (
    attribution_engine,
    attribution_spec,
    multi_period_corpus,
    seal_backtest,
    seal_factor,
    seal_subject,
)
from tests.backtest.builders import default_schedule


class TestSingleFactorEndToEnd:
    def test_seals_a_well_formed_record(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor = seal_factor(corpus)
        engine = attribution_engine(corpus)
        record = engine.attribute(
            attribution_spec(subject.backtest_id, (factor.backtest_id,))
        )
        assert record.boundary_kind == BOUNDARY_PIT
        assert record.periods == 5
        assert record.subject_ref == (subject.backtest_id, subject.result_hash)
        # Intercept + one factor, labelled in request order.
        assert [label for label, *_ in record.coefficients] == ["alpha", "factor_1"]
        assert record.factor_refs == (
            ("factor_1", factor.backtest_id, factor.result_hash),
        )

    def test_carries_the_corpus_pins(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor = seal_factor(corpus)
        engine = attribution_engine(corpus)
        record = engine.attribute(
            attribution_spec(subject.backtest_id, (factor.backtest_id,))
        )
        # Subject and factor ran over the same corpus snapshot → one distinct pin each.
        assert record.dataset_version_ids == (subject.dataset_version_id,)
        assert record.market_dataset_version_ids == (subject.market_dataset_version_id,)
        assert record.pin_mismatch is False


class TestMultiFactorEndToEnd:
    def test_two_non_collinear_factors_regress(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor_a = seal_factor(corpus)  # holds A
        factor_blend = seal_backtest(corpus, select_n=2)  # holds A + B → third series
        engine = attribution_engine(corpus)
        record = engine.attribute(
            attribution_spec(
                subject.backtest_id,
                (factor_a.backtest_id, factor_blend.backtest_id),
            )
        )
        assert [label for label, *_ in record.coefficients] == [
            "alpha",
            "factor_1",
            "factor_2",
        ]
        # Factor references preserve request order with positional labels.
        assert [ref[0] for ref in record.factor_refs] == ["factor_1", "factor_2"]
        assert [ref[1] for ref in record.factor_refs] == [
            factor_a.backtest_id,
            factor_blend.backtest_id,
        ]

    def test_factor_order_yields_a_distinct_record(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor_a = seal_factor(corpus)
        factor_blend = seal_backtest(corpus, select_n=2)
        engine = attribution_engine(corpus)
        forward = engine.attribute(
            attribution_spec(
                subject.backtest_id,
                (factor_a.backtest_id, factor_blend.backtest_id),
            )
        )
        reverse = engine.attribute(
            attribution_spec(
                subject.backtest_id,
                (factor_blend.backtest_id, factor_a.backtest_id),
            )
        )
        # Order is semantic → a genuinely distinct request, id, and column labelling.
        assert forward.attribution_id != reverse.attribution_id


class TestFailClosed:
    def test_absent_subject_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        factor = seal_factor(corpus)
        engine = attribution_engine(corpus)
        with pytest.raises(AttributionConsistencyError, match="not present"):
            engine.attribute(attribution_spec("sha256:deadbeef", (factor.backtest_id,)))

    def test_absent_factor_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = attribution_engine(corpus)
        with pytest.raises(AttributionConsistencyError, match="not present"):
            engine.attribute(
                attribution_spec(subject.backtest_id, ("sha256:deadbeef",))
            )

    def test_too_short_subject_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # The default two-instant schedule yields a single return; a one-factor
        # regression needs n >= K + 2 = 3, so this fails the residual-df floor.
        corpus = multi_period_corpus(tmp_path)
        sched = default_schedule()
        subject = seal_subject(corpus, schedule=sched)
        factor = seal_factor(corpus, schedule=sched)
        engine = attribution_engine(corpus)
        with pytest.raises(AttributionConfigurationError, match="residual degree"):
            engine.attribute(
                attribution_spec(subject.backtest_id, (factor.backtest_id,))
            )

    def test_incommensurable_schedule_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from quantforge.backtest.schedule import RebalanceSchedule
        from tests.attribution.builders import SIX_INSTANTS

        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        # A factor on a different (shorter) schedule → distinct schedule_id.
        alt = RebalanceSchedule.of(list(SIX_INSTANTS.instants[:5]))
        factor = seal_factor(corpus, schedule=alt)
        engine = attribution_engine(corpus)
        with pytest.raises(AttributionConsistencyError, match="schedule"):
            engine.attribute(
                attribution_spec(subject.backtest_id, (factor.backtest_id,))
            )

    def test_non_spec_argument_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        engine = attribution_engine(corpus)
        with pytest.raises(
            AttributionConfigurationError, match="AttributionSpecification"
        ):
            engine.attribute("not-a-spec")  # type: ignore[arg-type]

    def test_drifted_factor_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor = seal_factor(corpus)
        engine = attribution_engine(corpus)
        # Rewrite the factor's sealed result_hash so its ledger no longer recomputes to
        # it — the engine must refuse to attribute against a drifted reference.
        store = engine.research_store
        slug = factor.backtest_id.replace(":", "-")
        path = store.root / "research" / f"{slug}.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["research_result"]["result_hash"] = "sha256:tampered"
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(AttributionConsistencyError, match="drift"):
            engine.attribute(
                attribution_spec(subject.backtest_id, (factor.backtest_id,))
            )


class TestPersistence:
    def test_record_is_persisted_write_once(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor = seal_factor(corpus)
        engine = attribution_engine(corpus)
        record = engine.attribute(
            attribution_spec(subject.backtest_id, (factor.backtest_id,))
        )
        assert engine.research_store.has(record.research_result_id)

    def test_record_round_trips_from_sidecar(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor = seal_factor(corpus)
        engine = attribution_engine(corpus)
        record = engine.attribute(
            attribution_spec(subject.backtest_id, (factor.backtest_id,))
        )
        loaded = engine.research_store.read_as(
            record.research_result_id, FactorAttribution.from_dict
        )
        assert loaded is not None
        assert loaded.to_dict() == record.to_dict()

    def test_rebuild_is_idempotent(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor = seal_factor(corpus)
        engine = attribution_engine(corpus)
        spec = attribution_spec(subject.backtest_id, (factor.backtest_id,))
        first = engine.attribute(spec)
        second = engine.attribute(spec)  # write-once no-op, not an error
        assert first.to_dict() == second.to_dict()


class TestReproducibility:
    def test_independent_workspaces_agree(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Two independently populated corpora produce byte-identical attribution for the
        # same declared request — no machine / order / wall-clock dependence.
        left = multi_period_corpus(tmp_path / "left")
        right = multi_period_corpus(tmp_path / "right")
        subj_l = seal_subject(left)
        subj_r = seal_subject(right)
        fac_l = seal_factor(left)
        fac_r = seal_factor(right)
        assert subj_l.backtest_id == subj_r.backtest_id
        assert fac_l.backtest_id == fac_r.backtest_id
        rec_l = attribution_engine(left).attribute(
            attribution_spec(subj_l.backtest_id, (fac_l.backtest_id,))
        )
        rec_r = attribution_engine(right).attribute(
            attribution_spec(subj_r.backtest_id, (fac_r.backtest_id,))
        )
        assert rec_l.to_dict() == rec_r.to_dict()


class TestWorkspaceWiring:
    def test_attribution_engine_is_cached(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        assert (
            corpus.workspace.attribution_engine is corpus.workspace.attribution_engine
        )

    def test_engine_shares_the_research_sidecar(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = attribution_engine(corpus)
        assert engine.research_store is corpus.workspace.research_result_store
        assert engine.research_store.has(subject.backtest_id)

    def test_engine_type_from_workspace(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        assert isinstance(corpus.workspace.attribution_engine, AttributionEngine)


class TestNotPit:
    def test_record_is_ex_post_not_a_pit_value(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        factor = seal_factor(corpus)
        engine = attribution_engine(corpus)
        record = engine.attribute(
            attribution_spec(subject.backtest_id, (factor.backtest_id,))
        )
        # FA-2: never a Pit* type, never an as-of accessor, even though its inputs were
        # PIT walks (boundary_kind documents only the input side).
        assert not hasattr(record, "as_of")
        assert not type(record).__name__.startswith("Pit")
