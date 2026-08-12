"""End-to-end walk-forward orchestration over a real sealed chain (§6, WF-1..WF-6).

Each test seals a real factor -> risk-model -> optimization chain into a workspace's
shared research sidecar via :mod:`tests.walkforward.builders`, then runs the true
resolve -> verify -> align -> partition -> evaluate -> summarize -> seal -> persist.
The fixture chain uses two independent return series so a training span of >= 3 periods
is positive-definite (a REALIZED window) and a 2-period span is singular - which lets
the mixed-window and fail-closed scenarios be constructed by choosing the training
policy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quantforge.walkforward.errors import (
    WalkForwardConfigurationError,
    WalkForwardConsistencyError,
)
from quantforge.walkforward.model import WindowStatus
from quantforge.walkforward.result import MIN_VALID_WINDOWS, WalkForwardEvaluation
from tests.walkforward.builders import (
    SERIES_A,
    SERIES_B,
    DummyRecord,
    build_chain,
    expanding_policy,
    make_factor,
    make_risk_model,
    make_wf_spec,
    seal_optimization,
    wf_engine,
    workspace,
)


class TestHappyPath:
    def test_all_windows_realized(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        opt = build_chain(ws)
        evaluation = wf_engine(ws).evaluate(make_wf_spec(opt.research_result_id))
        assert evaluation.status is WindowStatus.REALIZED
        # min_train=3 over 6 complete-case periods -> cuts 3,4,5 -> 3 windows.
        assert len(evaluation.windows) == 3
        assert all(w.status is WindowStatus.REALIZED for w in evaluation.windows)
        assert len(evaluation.oos_returns) == 3
        assert evaluation.common_periods == 6

    def test_references_and_conventions_carried_through(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        opt = build_chain(ws)
        evaluation = wf_engine(ws).evaluate(make_wf_spec(opt.research_result_id))
        assert evaluation.optimization_id == opt.research_result_id
        assert evaluation.optimization_ref == (opt.research_result_id, opt.result_hash)
        assert evaluation.n_factors == 2
        assert evaluation.factor_labels == ("factor_1", "factor_2")

    def test_persisted_write_once_and_readable(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        opt = build_chain(ws)
        evaluation = wf_engine(ws).evaluate(make_wf_spec(opt.research_result_id))
        restored = ws.research_result_store.read_as(
            evaluation.research_result_id, WalkForwardEvaluation.from_dict
        )
        assert restored is not None
        assert restored.to_dict() == evaluation.to_dict()

    def test_rebuild_is_idempotent(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        opt = build_chain(ws)
        spec = make_wf_spec(opt.research_result_id)
        first = wf_engine(ws).evaluate(spec)
        second = wf_engine(ws).evaluate(spec)
        assert first.to_dict() == second.to_dict()

    def test_predicted_vs_realized_is_available(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        opt = build_chain(ws)
        evaluation = wf_engine(ws).evaluate(make_wf_spec(opt.research_result_id))
        assert len(evaluation.predicted_vs_realized) == 3


class TestMixedWindows:
    def test_singular_first_window_still_seals(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        opt = build_chain(ws)
        # min_train=2 -> first window trains on 2 obs (rank-1, singular); the rest
        # train on >= 3 obs and realize. Still >= MIN_VALID_WINDOWS realized.
        evaluation = wf_engine(ws).evaluate(
            make_wf_spec(
                opt.research_result_id,
                policy=expanding_policy(min_train_periods=2),
            )
        )
        statuses = [w.status for w in evaluation.windows]
        assert statuses[0] is WindowStatus.UNDEFINED
        realized = sum(1 for s in statuses if s is WindowStatus.REALIZED)
        assert realized >= MIN_VALID_WINDOWS
        assert evaluation.status is WindowStatus.REALIZED


class TestCompleteCaseAlignment:
    def test_undefined_cell_excluded_from_common_axis(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        # Factor 0 is UNDEFINED at index 2 -> that date drops from the common axis.
        holed = (SERIES_A[0], SERIES_A[1], None, SERIES_A[3], SERIES_A[4], SERIES_A[5])
        opt = build_chain(ws, series=(holed, SERIES_B))
        evaluation = wf_engine(ws).evaluate(make_wf_spec(opt.research_result_id))
        assert evaluation.common_periods == 5


class TestDeterminism:
    def test_identical_across_two_workspaces(self, tmp_path: Path) -> None:
        ws_a = workspace(tmp_path / "a")
        ws_b = workspace(tmp_path / "b")
        opt_a = build_chain(ws_a)
        opt_b = build_chain(ws_b)
        eval_a = wf_engine(ws_a).evaluate(make_wf_spec(opt_a.research_result_id))
        eval_b = wf_engine(ws_b).evaluate(make_wf_spec(opt_b.research_result_id))
        assert eval_a.research_result_id == eval_b.research_result_id
        assert eval_a.to_dict() == eval_b.to_dict()


class TestFailClosed:
    def test_non_specification_input_raises(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        with pytest.raises(WalkForwardConfigurationError):
            wf_engine(ws).evaluate("not-a-spec")  # type: ignore[arg-type]

    def test_missing_optimization_raises(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        with pytest.raises(WalkForwardConsistencyError):
            wf_engine(ws).evaluate(make_wf_spec("sha256:never-sealed"))

    def test_non_optimization_record_raises(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        ws.research_result_store.write(DummyRecord("sha256:dummy"))
        with pytest.raises(WalkForwardConsistencyError):
            wf_engine(ws).evaluate(make_wf_spec("sha256:dummy"))

    def test_non_optimal_recipe_raises(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        # A collinear in-sample covariance makes the optimizer SINGULAR (not OPTIMAL);
        # there is no GMV recipe to walk.
        opt = build_chain(ws, matrix=[["1", "1"], ["1", "1"]])
        assert opt.status.value != "optimal"
        with pytest.raises(WalkForwardConsistencyError):
            wf_engine(ws).evaluate(make_wf_spec(opt.research_result_id))

    def test_too_few_windows_raises(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        opt = build_chain(ws)
        # min_train=5 over 6 periods -> a single window, below MIN_VALID_WINDOWS.
        with pytest.raises(WalkForwardConsistencyError):
            wf_engine(ws).evaluate(
                make_wf_spec(
                    opt.research_result_id,
                    policy=expanding_policy(min_train_periods=5),
                )
            )

    def test_all_singular_windows_raise(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        # Two identical factor series -> every window's covariance is singular.
        opt = build_chain(ws, series=(SERIES_A, SERIES_A))
        with pytest.raises(WalkForwardConsistencyError):
            wf_engine(ws).evaluate(make_wf_spec(opt.research_result_id))

    def test_risk_free_disagreement_raises(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        f0 = make_factor(name="f0", values=SERIES_A, risk_free_per_period="0")
        f1 = make_factor(name="f1", values=SERIES_B, risk_free_per_period="0.001")
        ws.research_result_store.write(f0)
        ws.research_result_store.write(f1)
        opt = seal_optimization(ws, make_risk_model([f0, f1]))
        with pytest.raises(WalkForwardConsistencyError):
            wf_engine(ws).evaluate(make_wf_spec(opt.research_result_id))
