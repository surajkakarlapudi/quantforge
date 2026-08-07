"""The pure metric evaluator — bind, unit-check, apply, fail closed (§4, §6.3, §14).

:class:`MetricEvaluator` is the deterministic core: given a
:class:`~quantforge.metrics.formula.FormulaDefinition`, a filer's facts, a Phase 5
resolver, and a boundary, it resolves every input (§7), evaluates the operation tree
under the **pinned decimal context** (Decision D5), and returns a
:class:`~quantforge.metrics.model.PitMetricValue` /
:class:`~quantforge.metrics.model.RevisedMetricValue`.

It is a **pure function** of ``(formula, resolved inputs, engine version)`` — the
engine/façade does the I/O. Two disciplines are absolute:

* **Fail closed to a value, never an exception, on any data condition** (§2, §13,
  §14): a missing/nil/non-numeric/unit-mismatched input, or a zero denominator,
  yields an ``UNDEFINED`` metric carrying the reason — the evaluator never raises for
  data. It raises (:class:`FormulaConfigurationError`) only for our *own* bug — an
  operation referencing an input the formula never declared.
* **Exact arithmetic under one versioned context** (§16): ``Decimal`` only, no
  ``float``; addition/subtraction are exact and only division rounds, under the
  engine's pinned :class:`decimal.Context` applied via an explicit ``localcontext``
  (never the ambient process context) so the result is machine-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from quantforge.availability.resolve import PointInTimeResolver
from quantforge.canonical.model import Fact
from quantforge.canonical.numeric import canonical_decimal_str
from quantforge.metrics.errors import FormulaConfigurationError
from quantforge.metrics.formula import (
    Add,
    Const,
    Div,
    FormulaDefinition,
    Mul,
    Operation,
    Ref,
    Sub,
)
from quantforge.metrics.identity import metric_id
from quantforge.metrics.model import (
    InputResolution,
    MetricPeriod,
    MetricProvenance,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)
from quantforge.metrics.resolve_input import (
    MetricBoundary,
    ResolvedInput,
    resolve_input,
)
from quantforge.metrics.units import (
    ResolvedUnit,
    UnitExpectation,
    add_sub_result_unit,
    div_result_unit,
)
from quantforge.metrics.version import MetricEngineVersion

__all__ = ["EvaluatedMetric", "MetricEvaluator"]


@dataclass(frozen=True, slots=True)
class _OpValue:
    """The exact value + unit of an operation subtree (internal to evaluation)."""

    value: Decimal
    unit: ResolvedUnit


@dataclass(frozen=True, slots=True)
class _OpFailure:
    """A fail-closed operation outcome carrying its reason (internal)."""

    reason: UndefinedReason


# An operation node evaluates to a value+unit or a fail-closed reason.
_OpResult = _OpValue | _OpFailure


@dataclass(frozen=True, slots=True)
class EvaluatedMetric:
    """The mode-agnostic result of evaluation, wrapped into a typed value by callers.

    Holds everything both result types share (status/value/unit/reason + the
    per-input resolutions), so :class:`MetricEvaluator` can build the PIT or REVISED
    type without duplicating the arithmetic.
    """

    status: MetricStatus
    value_numeric_str: str | None
    unit: str | None
    reason: UndefinedReason | None
    input_resolutions: tuple[InputResolution, ...]


class MetricEvaluator:
    """Evaluate a formula to an exact metric value or a fail-closed ``UNDEFINED``.

    Constructed with a pinned :class:`MetricEngineVersion` (carrying the decimal
    context, Decision D5). Stateless per call; deterministic.
    """

    def __init__(self, engine_version: MetricEngineVersion | None = None) -> None:
        self._version = engine_version or MetricEngineVersion()

    @property
    def engine_version(self) -> MetricEngineVersion:
        return self._version

    # -- PIT / REVISED entry points -----------------------------------------

    def evaluate_pit(
        self,
        formula: FormulaDefinition,
        company_id: str,
        facts: list[Fact],
        resolver: PointInTimeResolver,
        period: MetricPeriod,
        boundary: MetricBoundary,
    ) -> PitMetricValue:
        """Evaluate ``formula`` at a PIT ``boundary`` → a :class:`PitMetricValue`."""
        if boundary.as_of is None:
            raise FormulaConfigurationError("evaluate_pit requires a PIT boundary")
        evaluated = self._evaluate(formula, facts, resolver, period, boundary)
        provenance = self._provenance(formula, boundary, evaluated)
        mid = self._metric_id(formula, company_id, period, boundary)
        return PitMetricValue(
            metric_id=mid,
            metric_key=formula.metric_key,
            formula_id=formula.formula_id,
            metric_engine_version_id=self._version.metric_engine_version_id,
            company_id=company_id,
            period=period,
            status=evaluated.status,
            value_numeric_str=evaluated.value_numeric_str,
            unit=evaluated.unit,
            reason=evaluated.reason,
            provenance=provenance,
            as_of=boundary.as_of,
        )

    def evaluate_revised(
        self,
        formula: FormulaDefinition,
        company_id: str,
        facts: list[Fact],
        resolver: PointInTimeResolver,
        period: MetricPeriod,
        boundary: MetricBoundary,
    ) -> RevisedMetricValue:
        """Evaluate ``formula`` over a REVISED ``boundary`` → a metric value."""
        if boundary.dataset_version is None:
            raise FormulaConfigurationError(
                "evaluate_revised requires a REVISED boundary"
            )
        evaluated = self._evaluate(formula, facts, resolver, period, boundary)
        provenance = self._provenance(formula, boundary, evaluated)
        mid = self._metric_id(formula, company_id, period, boundary)
        return RevisedMetricValue(
            metric_id=mid,
            metric_key=formula.metric_key,
            formula_id=formula.formula_id,
            metric_engine_version_id=self._version.metric_engine_version_id,
            company_id=company_id,
            period=period,
            status=evaluated.status,
            value_numeric_str=evaluated.value_numeric_str,
            unit=evaluated.unit,
            reason=evaluated.reason,
            provenance=provenance,
            dataset_version_id=boundary.dataset_version.dataset_version_id,
        )

    # -- core -----------------------------------------------------------------

    def _evaluate(
        self,
        formula: FormulaDefinition,
        facts: list[Fact],
        resolver: PointInTimeResolver,
        period: MetricPeriod,
        boundary: MetricBoundary,
    ) -> EvaluatedMetric:
        """Resolve inputs, then apply the op tree under the pinned context."""
        resolved: dict[str, ResolvedInput] = {}
        resolutions: list[InputResolution] = []
        for binding in formula.inputs:
            r = resolve_input(binding, facts, resolver, boundary, period)
            resolved[binding.name] = r
            resolutions.append(r.resolution)

        # Partial availability: any UNDEFINED input ⇒ the whole metric is UNDEFINED
        # (a ratio needs every operand; never computed from a subset — §13). The
        # metric-level reason mirrors the first failing input in declared order.
        for binding in formula.inputs:
            r = resolved[binding.name]
            if r.status is MetricStatus.UNDEFINED:
                return EvaluatedMetric(
                    status=MetricStatus.UNDEFINED,
                    value_numeric_str=None,
                    unit=None,
                    reason=r.resolution.reason,
                    input_resolutions=tuple(resolutions),
                )

        # All inputs known — evaluate the operation tree under the pinned context.
        with localcontext(self._version.decimal_context()):
            outcome = self._eval_op(formula.operation, resolved)

        if isinstance(outcome, _OpFailure):
            return EvaluatedMetric(
                status=MetricStatus.UNDEFINED,
                value_numeric_str=None,
                unit=None,
                reason=outcome.reason,
                input_resolutions=tuple(resolutions),
            )

        # A KNOWN value must also satisfy the formula's declared output unit family
        # (a self-check: e.g. a ratio must be `pure`). A mismatch is a fail-closed
        # UNIT_MISMATCH rather than a wrong unit label on a KNOWN metric.
        if not _matches_output_family(outcome.unit, formula.output_unit):
            return EvaluatedMetric(
                status=MetricStatus.UNDEFINED,
                value_numeric_str=None,
                unit=None,
                reason=UndefinedReason.UNIT_MISMATCH,
                input_resolutions=tuple(resolutions),
            )

        return EvaluatedMetric(
            status=MetricStatus.KNOWN,
            value_numeric_str=canonical_decimal_str(outcome.value),
            unit=outcome.unit.token,
            reason=None,
            input_resolutions=tuple(resolutions),
        )

    def _eval_op(self, op: Operation, resolved: dict[str, ResolvedInput]) -> _OpResult:
        """Post-order evaluation of one operation node (pinned context is active).

        Every input referenced here is guaranteed ``KNOWN`` (the caller returned
        early otherwise), so a :class:`Ref` to a resolved input always has a value.
        A :class:`Ref` to an *undeclared* input is a formula-configuration bug and
        raises — but :meth:`FormulaDefinition.__post_init__` already forbids that, so
        it is unreachable for a registry formula.
        """
        if isinstance(op, Ref):
            r = resolved.get(op.name)
            if r is None:
                raise FormulaConfigurationError(
                    f"operation references undeclared input {op.name!r}"
                )
            assert r.value is not None and r.unit is not None  # KNOWN ⇒ present
            return _OpValue(r.value, r.unit)

        if isinstance(op, Const):
            # A literal is dimensionless (`pure`) — it scales/shifts without a unit.
            return _OpValue(
                Decimal(op.literal), ResolvedUnit(UnitExpectation.PURE, None, "pure")
            )

        if isinstance(op, Add | Sub):
            left = self._eval_op(op.left, resolved)
            if isinstance(left, _OpFailure):
                return left
            right = self._eval_op(op.right, resolved)
            if isinstance(right, _OpFailure):
                return right
            unit = add_sub_result_unit(left.unit, right.unit)
            if unit is None:
                return _OpFailure(UndefinedReason.UNIT_MISMATCH)
            value = (
                left.value + right.value
                if isinstance(op, Add)
                else left.value - right.value
            )
            return _OpValue(value, unit)

        if isinstance(op, Mul):
            left = self._eval_op(op.left, resolved)
            if isinstance(left, _OpFailure):
                return left
            right = self._eval_op(op.right, resolved)
            if isinstance(right, _OpFailure):
                return right
            # Multiplication is used only to scale by a dimensionless constant in the
            # Phase 7 set; the non-pure operand's unit carries through.
            unit = _mul_result_unit(left.unit, right.unit)
            if unit is None:
                return _OpFailure(UndefinedReason.UNIT_MISMATCH)
            return _OpValue(left.value * right.value, unit)

        if isinstance(op, Div):
            numerator = self._eval_op(op.numerator, resolved)
            if isinstance(numerator, _OpFailure):
                return numerator
            denominator = self._eval_op(op.denominator, resolved)
            if isinstance(denominator, _OpFailure):
                return denominator
            if denominator.value == 0:  # exact Decimal zero → fail closed (§14)
                return _OpFailure(UndefinedReason.DIVIDE_BY_ZERO)
            unit = div_result_unit(numerator.unit, denominator.unit)
            if unit is None:
                return _OpFailure(UndefinedReason.UNIT_MISMATCH)
            return _OpValue(numerator.value / denominator.value, unit)

        # The Operation union is closed; an unknown node is our bug.
        raise FormulaConfigurationError(f"unknown operation node {type(op).__name__}")

    def _provenance(
        self,
        formula: FormulaDefinition,
        boundary: MetricBoundary,
        evaluated: EvaluatedMetric,
    ) -> MetricProvenance:
        return MetricProvenance(
            formula_id=formula.formula_id,
            metric_engine_version_id=self._version.metric_engine_version_id,
            boundary_kind=boundary.kind,
            boundary_value=boundary.value,
            inputs=evaluated.input_resolutions,
            result_status=evaluated.status,
            result_reason=evaluated.reason,
        )

    def _metric_id(
        self,
        formula: FormulaDefinition,
        company_id: str,
        period: MetricPeriod,
        boundary: MetricBoundary,
    ) -> str:
        return metric_id(
            formula_id=formula.formula_id,
            metric_engine_version_id=self._version.metric_engine_version_id,
            company_id=company_id,
            period_key=period.period_key,
            boundary_key=f"{boundary.kind}:{boundary.value}",
        )


def _matches_output_family(unit: ResolvedUnit, expected: UnitExpectation) -> bool:
    """Whether a computed unit satisfies the formula's declared output family (§14)."""
    return unit.family is expected


def _mul_result_unit(left: ResolvedUnit, right: ResolvedUnit) -> ResolvedUnit | None:
    """The unit of ``left * right`` — only constant-scaling is supported (§6.3).

    Exactly one operand must be dimensionless (``pure``); the other's unit carries
    through. Two non-pure operands have no defined product unit in Phase 7 (no
    area/volume metrics) and fail closed.
    """
    if right.family is UnitExpectation.PURE:
        return left
    if left.family is UnitExpectation.PURE:
        return right
    return None
