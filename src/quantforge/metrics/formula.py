"""Declarative formula model + content-addressed identity (``metrics.md`` §6, §7).

A :class:`FormulaDefinition` is **data, not code**: the evaluator reads it to decide
what to fetch and how to combine (mirroring the Phase 5
:class:`~quantforge.availability.version.AvailabilityRule`). It comprises:

* ordered :class:`InputBinding`s — each an operand naming an *ordered* candidate
  list of ``(taxonomy, local_name)`` concepts (Decision D2, §7.0), a period kind,
  a dimension selector, and a unit expectation;
* an :class:`Operation` tree — a tiny closed algebra (``Ref``/``Const``/``Add``/
  ``Sub``/``Mul``/``Div``) over the input names (§6.3);
* the formula's primary period type and output unit expectation (§6.4, §14).

Because the entire definition is serialized deterministically and hashed into
``formula_id`` (§6.2), any change — a candidate list, an operation, a unit rule —
necessarily yields a new formula version; a definition is never mutated in place
(invariant 14 analogue).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from quantforge.canonical.taxonomy import Taxonomy
from quantforge.metrics.errors import FormulaConfigurationError
from quantforge.metrics.units import UnitExpectation
from quantforge.sec.artifacts import sha256_hex
from quantforge.xbrl.contexts import PeriodType

__all__ = [
    "Add",
    "ConceptCandidate",
    "Const",
    "Div",
    "FormulaDefinition",
    "InputBinding",
    "Mul",
    "Operation",
    "PeriodKind",
    "Ref",
    "Sub",
]

# The period kinds an input may carry. A subset of Phase 4 PeriodType (FOREVER is
# never a metric input) — kept as PeriodType so alignment compares directly.
PeriodKind = PeriodType


@dataclass(frozen=True, slots=True)
class ConceptCandidate:
    """One ordered candidate concept, matched by ``(taxonomy, local_name)`` (§7.0).

    A formula cannot know a filer's year-versioned concept URI or raw ``unit_ref``,
    so a candidate is a prefix-/version-independent ``(taxonomy, local_name)`` pair
    matched against the Phase 4 ``taxonomy`` + ``concept.local_name`` fields. This
    is *selection*, never mapping: it only ever picks a concept the filer actually
    reported (§1.2).
    """

    taxonomy: Taxonomy
    local_name: str

    @property
    def label(self) -> str:
        """A stable ``taxonomy:local_name`` label for provenance/audit."""
        return f"{self.taxonomy.value}:{self.local_name}"

    def to_dict(self) -> dict[str, object]:
        return {"taxonomy": self.taxonomy.value, "local_name": self.local_name}


@dataclass(frozen=True, slots=True)
class InputBinding:
    """A named formula operand: an ordered candidate list + alignment + unit (§7).

    ``concept_candidates`` is walked in order; the first candidate the filer
    reported (as a ``KNOWN`` numeric fact) wins (Decision D3). ``period_kind`` says
    how the input aligns to the requested period (§6.4). ``consolidated`` selects
    the undimensioned context (the default and only supported selector in Phase 7,
    §7.2). ``unit_expectation`` narrows/validates the fact's unit family (§14).
    """

    name: str
    concept_candidates: tuple[ConceptCandidate, ...]
    period_kind: PeriodKind
    unit_expectation: UnitExpectation
    consolidated: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "concept_candidates": [c.to_dict() for c in self.concept_candidates],
            "period_kind": self.period_kind.value,
            "unit_expectation": self.unit_expectation.value,
            "consolidated": self.consolidated,
        }


# -- the operation algebra (§6.3) -------------------------------------------------
#
# A tiny closed set of frozen node types over input names + decimal literals. No
# user code, no arbitrary functions — fully serializable, hashable, deterministic.


@dataclass(frozen=True, slots=True)
class Ref:
    """Reference the resolved value of an :class:`InputBinding` by name."""

    name: str

    def to_dict(self) -> dict[str, object]:
        return {"op": "ref", "name": self.name}

    def input_names(self) -> frozenset[str]:
        return frozenset((self.name,))


@dataclass(frozen=True, slots=True)
class Const:
    """A decimal literal (stored as its exact string form; e.g. ``"1"``)."""

    literal: str

    def to_dict(self) -> dict[str, object]:
        return {"op": "const", "literal": self.literal}

    def input_names(self) -> frozenset[str]:
        return frozenset()


@dataclass(frozen=True, slots=True)
class Add:
    """``left + right``."""

    left: Operation
    right: Operation

    def to_dict(self) -> dict[str, object]:
        return {"op": "add", "left": self.left.to_dict(), "right": self.right.to_dict()}

    def input_names(self) -> frozenset[str]:
        return self.left.input_names() | self.right.input_names()


@dataclass(frozen=True, slots=True)
class Sub:
    """``left - right``."""

    left: Operation
    right: Operation

    def to_dict(self) -> dict[str, object]:
        return {"op": "sub", "left": self.left.to_dict(), "right": self.right.to_dict()}

    def input_names(self) -> frozenset[str]:
        return self.left.input_names() | self.right.input_names()


@dataclass(frozen=True, slots=True)
class Mul:
    """``left * right``."""

    left: Operation
    right: Operation

    def to_dict(self) -> dict[str, object]:
        return {"op": "mul", "left": self.left.to_dict(), "right": self.right.to_dict()}

    def input_names(self) -> frozenset[str]:
        return self.left.input_names() | self.right.input_names()


@dataclass(frozen=True, slots=True)
class Div:
    """``numerator / denominator`` — divide-by-zero fails closed (§14)."""

    numerator: Operation
    denominator: Operation

    def to_dict(self) -> dict[str, object]:
        return {
            "op": "div",
            "numerator": self.numerator.to_dict(),
            "denominator": self.denominator.to_dict(),
        }

    def input_names(self) -> frozenset[str]:
        return self.numerator.input_names() | self.denominator.input_names()


# The closed operation union. Any new node type is a deliberate, versioned change.
Operation = Ref | Const | Add | Sub | Mul | Div


@dataclass(frozen=True, slots=True)
class FormulaDefinition:
    """One immutable, content-addressed metric formula (§6).

    Selection (§6.5): a formula is looked up by ``metric_key``. Identity is
    ``formula_id = sha256(metric_key, definition_hash)`` where ``definition_hash``
    covers the inputs, operation tree, primary period type, and output unit — so
    two formulas with the same key but a different definition have different ids
    (they cannot be confused), and re-declaring the identical formula reproduces the
    same id (invariant 20 analogue).

    The ``__post_init__`` guard fails closed on a self-inconsistent formula (an
    operation referencing an undeclared input, a duplicate input name, or an input
    whose ``period_kind`` contradicts an ``INSTANT`` primary) — our bug, surfaced.
    """

    metric_key: str
    description: str
    inputs: tuple[InputBinding, ...]
    operation: Operation
    period_type: PeriodType
    output_unit: UnitExpectation
    confidence: str = "unvalidated"
    notes: str = ""

    def __post_init__(self) -> None:
        names = [b.name for b in self.inputs]
        if len(names) != len(set(names)):
            raise FormulaConfigurationError(
                f"formula {self.metric_key!r} has duplicate input names"
            )
        declared = set(names)
        referenced = self.operation.input_names()
        missing = referenced - declared
        if missing:
            raise FormulaConfigurationError(
                f"formula {self.metric_key!r} operation references undeclared "
                f"input(s): {sorted(missing)}"
            )
        if self.period_type not in (PeriodType.INSTANT, PeriodType.DURATION):
            raise FormulaConfigurationError(
                f"formula {self.metric_key!r} primary period_type must be INSTANT "
                f"or DURATION, not {self.period_type.value!r}"
            )
        # Under an INSTANT primary, every input must also be INSTANT — a duration
        # input has no ending point to align to an instant request (§6.4).
        if self.period_type is PeriodType.INSTANT:
            for binding in self.inputs:
                if binding.period_kind is not PeriodType.INSTANT:
                    raise FormulaConfigurationError(
                        f"formula {self.metric_key!r} is INSTANT but input "
                        f"{binding.name!r} is {binding.period_kind.value!r}"
                    )

    def input(self, name: str) -> InputBinding:
        """Return the binding named ``name`` (fail closed if absent)."""
        for binding in self.inputs:
            if binding.name == name:
                return binding
        raise FormulaConfigurationError(
            f"formula {self.metric_key!r} has no input {name!r}"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metric_key": self.metric_key,
            "description": self.description,
            "inputs": [b.to_dict() for b in self.inputs],
            "operation": self.operation.to_dict(),
            "period_type": self.period_type.value,
            "output_unit": self.output_unit.value,
            "confidence": self.confidence,
            "notes": self.notes,
        }

    @property
    def definition_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the declarative definition content.

        Excludes ``description``/``notes`` (human documentation that does not change
        the computed value); covers inputs, operation, period type, and output unit.
        """
        core = {
            "inputs": [b.to_dict() for b in self.inputs],
            "operation": self.operation.to_dict(),
            "period_type": self.period_type.value,
            "output_unit": self.output_unit.value,
        }
        payload = json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return f"sha256:{sha256_hex(payload)}"

    @property
    def formula_id(self) -> str:
        """``sha256(metric_key, definition_hash)`` (§6.2)."""
        payload = f"{self.metric_key}\x00{self.definition_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"
