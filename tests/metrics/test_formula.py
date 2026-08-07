"""Tests for the declarative formula model + content-addressed id (metrics.md §6).

A formula is data: its ``formula_id`` is a content hash over the inputs, operation
tree, period type, and output unit (never the human description/notes). Changing
any of those is a new version; re-declaring the identical formula reproduces the
id. The ``__post_init__`` guard fails closed on a self-inconsistent formula.
"""

from __future__ import annotations

import pytest

from quantforge.canonical.taxonomy import Taxonomy
from quantforge.metrics.errors import FormulaConfigurationError
from quantforge.metrics.formula import (
    Add,
    ConceptCandidate,
    Const,
    Div,
    FormulaDefinition,
    InputBinding,
    Mul,
    Operation,
    Ref,
    Sub,
)
from quantforge.metrics.units import UnitExpectation
from quantforge.xbrl.contexts import PeriodType


def _binding(
    name: str, local: str, kind: PeriodType = PeriodType.INSTANT
) -> InputBinding:
    return InputBinding(
        name=name,
        concept_candidates=(ConceptCandidate(Taxonomy.US_GAAP, local),),
        period_kind=kind,
        unit_expectation=UnitExpectation.MONETARY,
    )


def _current_ratio() -> FormulaDefinition:
    return FormulaDefinition(
        metric_key="current_ratio",
        description="Current assets divided by current liabilities.",
        inputs=(
            _binding("a", "AssetsCurrent"),
            _binding("l", "LiabilitiesCurrent"),
        ),
        operation=Div(Ref("a"), Ref("l")),
        period_type=PeriodType.INSTANT,
        output_unit=UnitExpectation.PURE,
    )


class TestFormulaId:
    def test_is_deterministic(self) -> None:
        assert _current_ratio().formula_id == _current_ratio().formula_id

    def test_is_sha256_prefixed(self) -> None:
        assert _current_ratio().formula_id.startswith("sha256:")

    def test_description_and_notes_do_not_change_id(self) -> None:
        base = _current_ratio()
        reworded = FormulaDefinition(
            metric_key=base.metric_key,
            description="totally different prose",
            inputs=base.inputs,
            operation=base.operation,
            period_type=base.period_type,
            output_unit=base.output_unit,
            notes="extra notes",
        )
        assert reworded.formula_id == base.formula_id

    def test_operation_change_changes_id(self) -> None:
        base = _current_ratio()
        swapped = FormulaDefinition(
            metric_key=base.metric_key,
            description=base.description,
            inputs=base.inputs,
            operation=Div(Ref("l"), Ref("a")),  # inverted
            period_type=base.period_type,
            output_unit=base.output_unit,
        )
        assert swapped.formula_id != base.formula_id

    def test_candidate_change_changes_id(self) -> None:
        base = _current_ratio()
        extended = FormulaDefinition(
            metric_key=base.metric_key,
            description=base.description,
            inputs=(
                InputBinding(
                    name="a",
                    concept_candidates=(
                        ConceptCandidate(Taxonomy.US_GAAP, "AssetsCurrent"),
                        ConceptCandidate(Taxonomy.US_GAAP, "OtherAssetsCurrent"),
                    ),
                    period_kind=PeriodType.INSTANT,
                    unit_expectation=UnitExpectation.MONETARY,
                ),
                _binding("l", "LiabilitiesCurrent"),
            ),
            operation=base.operation,
            period_type=base.period_type,
            output_unit=base.output_unit,
        )
        assert extended.formula_id != base.formula_id

    def test_output_unit_change_changes_id(self) -> None:
        base = _current_ratio()
        as_money = FormulaDefinition(
            metric_key=base.metric_key,
            description=base.description,
            inputs=base.inputs,
            operation=base.operation,
            period_type=base.period_type,
            output_unit=UnitExpectation.MONETARY,
        )
        assert as_money.formula_id != base.formula_id


class TestPostInitGuards:
    def test_duplicate_input_name_rejected(self) -> None:
        with pytest.raises(FormulaConfigurationError, match="duplicate"):
            FormulaDefinition(
                metric_key="dup",
                description="",
                inputs=(_binding("a", "AssetsCurrent"), _binding("a", "Liabilities")),
                operation=Ref("a"),
                period_type=PeriodType.INSTANT,
                output_unit=UnitExpectation.MONETARY,
            )

    def test_undeclared_ref_rejected(self) -> None:
        with pytest.raises(FormulaConfigurationError, match="undeclared"):
            FormulaDefinition(
                metric_key="bad",
                description="",
                inputs=(_binding("a", "AssetsCurrent"),),
                operation=Div(Ref("a"), Ref("missing")),
                period_type=PeriodType.INSTANT,
                output_unit=UnitExpectation.PURE,
            )

    def test_instant_primary_with_duration_input_rejected(self) -> None:
        with pytest.raises(FormulaConfigurationError, match="INSTANT"):
            FormulaDefinition(
                metric_key="mixed",
                description="",
                inputs=(
                    _binding("a", "AssetsCurrent"),
                    _binding("r", "Revenues", kind=PeriodType.DURATION),
                ),
                operation=Div(Ref("a"), Ref("r")),
                period_type=PeriodType.INSTANT,
                output_unit=UnitExpectation.PURE,
            )

    def test_forever_primary_rejected(self) -> None:
        with pytest.raises(FormulaConfigurationError, match="period_type"):
            FormulaDefinition(
                metric_key="forever",
                description="",
                inputs=(_binding("a", "AssetsCurrent"),),
                operation=Ref("a"),
                period_type=PeriodType.FOREVER,
                output_unit=UnitExpectation.MONETARY,
            )


class TestInputAccessor:
    def test_input_returns_binding(self) -> None:
        f = _current_ratio()
        assert f.input("a").name == "a"

    def test_input_missing_fails_closed(self) -> None:
        with pytest.raises(FormulaConfigurationError, match="no input"):
            _current_ratio().input("nope")


class TestOperationTree:
    @pytest.mark.parametrize(
        "op",
        [
            Ref("a"),
            Const("1"),
            Add(Ref("a"), Ref("b")),
            Sub(Ref("a"), Ref("b")),
            Mul(Ref("a"), Const("2")),
            Div(Ref("a"), Ref("b")),
        ],
    )
    def test_to_dict_has_op_tag(self, op: Operation) -> None:
        assert "op" in op.to_dict()

    def test_input_names_collects_all_refs(self) -> None:
        op = Div(Sub(Ref("revenue"), Ref("cost")), Ref("revenue"))
        assert op.input_names() == frozenset({"revenue", "cost"})

    def test_const_has_no_input_names(self) -> None:
        assert Const("3.14").input_names() == frozenset()

    def test_concept_candidate_label(self) -> None:
        c = ConceptCandidate(Taxonomy.US_GAAP, "AssetsCurrent")
        assert c.label == "us-gaap:AssetsCurrent"
