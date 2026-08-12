"""End-to-end multiplicity correction through the engine (§6, MC-1..MC-6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from quantforge.comparison.model import ComparisonUndefinedReason
from quantforge.factors.errors import FactorConsistencyError
from quantforge.multiplicity.errors import (
    MultiplicityConfigurationError,
    MultiplicityConsistencyError,
)
from quantforge.multiplicity.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
)
from quantforge.multiplicity.result import MultipleComparisonCorrection
from tests.multiplicity.builders import (
    make_comparison,
    make_spec,
    multiplicity_engine,
    workspace,
)

INSUFFICIENT = ComparisonUndefinedReason.INSUFFICIENT_OVERLAP
ZERO_VAR = ComparisonUndefinedReason.ZERO_DIFFERENCE_VARIANCE


@dataclass(frozen=True)
class _DummyRecord:
    """A non-``StrategyComparison`` :class:`ResearchRecord` for fail-closed tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-comparison", "id": self.research_result_id}


# -- happy path --------------------------------------------------------------


def test_happy_path_corrects_full_family(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=3, p_values=["0.001", "0.02", "0.6"])
    result = multiplicity_engine(ws).correct(make_spec(cmp.research_result_id))

    assert isinstance(result, MultipleComparisonCorrection)
    assert result.family_size == 3
    assert result.coverage.n_pairs_total == 3
    assert result.coverage.n_excluded == 0
    # Defaults: Holm + Benjamini-Yekutieli, in request order.
    assert tuple(c.method for c in result.corrections) == (
        CorrectionMethod.HOLM,
        CorrectionMethod.BENJAMINI_YEKUTIELI,
    )
    holm = result.correction(CorrectionMethod.HOLM)
    assert len(holm.cells) == 3
    # The strongest signal (p = 0.001) is rejected by Holm at alpha = 0.05.
    strongest = next(c for c in holm.cells if (c.i, c.j) == (0, 1))
    assert strongest.rejected is True


def test_source_reference_is_pinned(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=["0.01"])
    result = multiplicity_engine(ws).correct(make_spec(cmp.research_result_id))
    assert result.source_strategy_comparison_id == cmp.research_result_id
    assert result.source_result_hash == cmp.result_hash


def test_honest_dependence_labels_are_sealed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=["0.01"])
    methods = (
        CorrectionMethod.BENJAMINI_HOCHBERG,
        CorrectionMethod.BENJAMINI_YEKUTIELI,
    )
    result = multiplicity_engine(ws).correct(
        make_spec(cmp.research_result_id, methods=methods)
    )
    bh = result.correction(CorrectionMethod.BENJAMINI_HOCHBERG)
    by = result.correction(CorrectionMethod.BENJAMINI_YEKUTIELI)
    assert bh.error_rate is ErrorRate.FALSE_DISCOVERY
    assert bh.dependence is DependenceAssumption.INDEPENDENCE_OR_PRDS
    assert by.dependence is DependenceAssumption.ARBITRARY


# -- UNDEFINED exclusion (MC-3) ----------------------------------------------


def test_undefined_cells_are_excluded_never_imputed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    # 3 strategies, 3 pairs: one KNOWN, one insufficient-overlap, one zero-variance.
    cmp = make_comparison(ws, n_strategies=3, p_values=["0.01", INSUFFICIENT, ZERO_VAR])
    result = multiplicity_engine(ws).correct(make_spec(cmp.research_result_id))

    assert result.family_size == 1
    assert result.coverage.n_excluded == 2
    reasons = {c.reason for c in result.excluded}
    assert reasons == {INSUFFICIENT, ZERO_VAR}
    # The single KNOWN cell is the only one corrected under each method.
    for method_result in result.corrections:
        assert len(method_result.cells) == 1
        assert (method_result.cells[0].i, method_result.cells[0].j) == (0, 1)


def test_all_undefined_family_is_empty(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=[INSUFFICIENT])
    result = multiplicity_engine(ws).correct(make_spec(cmp.research_result_id))
    assert result.family_size == 0
    assert result.coverage.n_excluded == 1
    for method_result in result.corrections:
        assert method_result.cells == ()
        assert method_result.n_rejected == 0


def test_boundary_is_carried_and_record_is_not_pit(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=["0.01"])
    result = multiplicity_engine(ws).correct(make_spec(cmp.research_result_id))
    assert result.boundary_kind == cmp.boundary_kind == "pit"
    assert not hasattr(result, "as_of")


# -- determinism & persistence -----------------------------------------------


def test_recompute_is_byte_identical_and_idempotent(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=3, p_values=["0.001", "0.02", "0.6"])
    engine = multiplicity_engine(ws)
    first = engine.correct(make_spec(cmp.research_result_id))
    second = engine.correct(make_spec(cmp.research_result_id))
    assert first.multiple_comparison_id == second.multiple_comparison_id
    assert first.to_dict() == second.to_dict()
    # Round-trips through the shared sidecar unchanged.
    stored = ws.research_result_store.read_as(
        first.research_result_id, MultipleComparisonCorrection.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()


def test_write_once_conflict_is_impossible_for_same_id(tmp_path: Path) -> None:
    # Two engines over the same sidecar seal a byte-identical record: no conflict.
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=["0.01"])
    a = multiplicity_engine(ws).correct(make_spec(cmp.research_result_id))
    b = multiplicity_engine(ws).correct(make_spec(cmp.research_result_id))
    assert a.to_dict() == b.to_dict()


# -- identity sensitivity ----------------------------------------------------


def test_different_source_answer_changes_correction_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_comparison(ws, n_strategies=2, p_values=["0.01"], name="a")
    b = make_comparison(ws, n_strategies=2, p_values=["0.02"], name="b")
    engine = multiplicity_engine(ws)
    ra = engine.correct(make_spec(a.research_result_id))
    rb = engine.correct(make_spec(b.research_result_id))
    assert ra.multiple_comparison_id != rb.multiple_comparison_id


def test_alpha_changes_correction_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=["0.01"])
    engine = multiplicity_engine(ws)
    lo = engine.correct(make_spec(cmp.research_result_id, alpha="0.01"))
    hi = engine.correct(make_spec(cmp.research_result_id, alpha="0.10"))
    assert lo.multiple_comparison_id != hi.multiple_comparison_id


def test_method_order_changes_correction_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=["0.01"])
    engine = multiplicity_engine(ws)
    forward = engine.correct(
        make_spec(
            cmp.research_result_id,
            methods=(CorrectionMethod.HOLM, CorrectionMethod.BENJAMINI_YEKUTIELI),
        )
    )
    reverse = engine.correct(
        make_spec(
            cmp.research_result_id,
            methods=(CorrectionMethod.BENJAMINI_YEKUTIELI, CorrectionMethod.HOLM),
        )
    )
    assert forward.multiple_comparison_id != reverse.multiple_comparison_id


# -- fail-closed guards (MC-1) -----------------------------------------------


def test_absent_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(MultiplicityConsistencyError):
        multiplicity_engine(ws).correct(make_spec("sha256:does-not-exist"))


def test_non_comparison_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    dummy = _DummyRecord(research_result_id="sha256:dummy")
    ws.research_result_store.write(dummy)
    with pytest.raises(MultiplicityConsistencyError):
        multiplicity_engine(ws).correct(make_spec(dummy.research_result_id))


def test_id_mismatch_fails_closed(tmp_path: Path) -> None:
    # A record stored at a path whose id disagrees with its content is inconsistent.
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=["0.01"])
    store = ws.research_result_store
    real_bytes = store._result_path(cmp.research_result_id).read_bytes()
    fake_id = "sha256:00000000"
    store._result_path(fake_id).write_bytes(real_bytes)
    with pytest.raises(MultiplicityConsistencyError):
        multiplicity_engine(ws).correct(make_spec(fake_id))


def test_non_spec_argument_is_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(MultiplicityConfigurationError):
        multiplicity_engine(ws).correct(object())  # type: ignore[arg-type]


def test_tampered_stored_payload_conflicts(tmp_path: Path) -> None:
    # A differing payload under an existing correction id fails closed at the store.
    ws = workspace(tmp_path)
    cmp = make_comparison(ws, n_strategies=2, p_values=["0.01"])
    result = multiplicity_engine(ws).correct(make_spec(cmp.research_result_id))
    store = ws.research_result_store
    path = store._result_path(result.research_result_id)
    tampered = path.read_text(encoding="utf-8").replace('"pit"', '"tampered"', 1)
    path.write_text(tampered, encoding="utf-8")

    @dataclass(frozen=True)
    class _Same:
        research_result_id: str
        payload: dict[str, object]

        def to_dict(self) -> dict[str, object]:
            return self.payload

    with pytest.raises(FactorConsistencyError):
        store.write(
            _Same(
                research_result_id=result.research_result_id,
                payload=result.to_dict(),
            )
        )
