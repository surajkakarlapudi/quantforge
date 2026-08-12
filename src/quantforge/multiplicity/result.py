"""The sealed, content-addressed multiplicity-correction record (§9, §10).

A completed correction is a :class:`MultipleComparisonCorrection`: the engine version,
the full declarative request, the
``(source_strategy_comparison_id, source_result_hash)`` reference to the one sealed
comparison it consumed, the declared ``alpha``, the KNOWN ``p`` value **family** (in the
source comparison's upper-triangle order), the **excluded** cells (pairs the source
sealed with an UNDEFINED ``p`` value, each with its reason), the per-method
**corrections** (each method's honest labels plus its adjusted ``p`` value + rejection
flag per family cell), a non-hashed coverage block, and the sealed ``result_hash`` over
the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``multiple_comparison_id`` (a single id, mirroring ``strategy_comparison_id``)
and ``to_dict`` is deterministic - so it persists write-once to the shared Phase 8
sidecar with **no new store**. It stores only a *pointer* to the source comparison,
never a copy of its matrix (the pointer-only discipline of
:class:`~quantforge.comparison.result.StrategyComparison`): the source already lives in
the same sidecar, so this record stays a thin, reproducible view over it.

**Ex-post, not PIT (MC-6).** A multiplicity correction over already-ex-post pairwise
``p`` values is itself an ex-post research statistic, not a forward-usable PIT value.
:class:`MultipleComparisonCorrection` is deliberately **not** a ``Pit*`` type and
exposes **no** as-of accessor. ``boundary_kind = "pit"`` documents only that the
*underlying strategies* were PIT walks - the convention where the label describes the
input side, not the ex-post output.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~MultipleComparisonCorrection.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.comparison.model import ComparisonUndefinedReason
from quantforge.multiplicity.identity import (
    multiple_comparison_id as _multiple_comparison_id,
)
from quantforge.multiplicity.identity import (
    multiple_comparison_result_hash as _result_hash,
)
from quantforge.multiplicity.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
)
from quantforge.multiplicity.version import MULTIPLICITY_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "MULTIPLICITY_RESULT_FORMAT_VERSION",
    "ExcludedCell",
    "FamilyCell",
    "MethodCell",
    "MethodResult",
    "MultipleComparisonCorrection",
    "MultiplicityCoverage",
]

#: The §9 record-schema version for the correction record - distinct from the
#: engine-logic version, the method version, and the sidecar's container format version.
#: Bump it when the serialized meaning of a correction record changes (a container
#: concern; it is **not** folded into ``multiple_comparison_id`` - §10, prior-phase
#: discipline).
MULTIPLICITY_RESULT_FORMAT_VERSION = "multiplicity-result/1"

#: The only boundary a v1 correction record accepts. It documents that the *underlying
#: strategies* (beneath the source comparison) were PIT walks; the correction *output*
#: is ex-post and is not a PIT value (MC-6). The engine carries the source comparison's
#: ``boundary_kind`` through unchanged.
BOUNDARY_PIT = "pit"


# -- fail-closed decode helpers ----------------------------------------------


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _req_int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an int")
    return value


def _req_bool(raw: dict[str, object], key: str) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a bool")
    return value


def _req_dict(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _req_list(raw: dict[str, object], key: str) -> list[object]:
    value = raw[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _as_dict(value: object, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"each {key} entry must be an object")
    return value


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"each {key} entry must be a string")
    return value


def _reason(raw: dict[str, object]) -> ComparisonUndefinedReason:
    """Decode a required exclusion ``reason`` string (fail closed).

    The reason is the source comparison's ``p`` value UNDEFINED reason
    (``INSUFFICIENT_OVERLAP`` for an undefined pair, ``ZERO_DIFFERENCE_VARIANCE`` for a
    zero-variance paired difference), so the closed
    :class:`~quantforge.comparison.model.ComparisonUndefinedReason` vocabulary validates
    it.
    """
    reason_raw = raw.get("reason")
    if not isinstance(reason_raw, str):
        raise ValueError("ExcludedCell.reason must be a string")
    try:
        return ComparisonUndefinedReason(reason_raw)
    except ValueError as exc:
        raise ValueError(f"unknown ComparisonUndefinedReason {reason_raw!r}") from exc


def _method(value: str) -> CorrectionMethod:
    try:
        return CorrectionMethod(value)
    except ValueError as exc:
        raise ValueError(f"unknown correction method {value!r}") from exc


@dataclass(frozen=True, slots=True)
class FamilyCell:
    """One KNOWN pairwise ``p`` value entering the corrected family (§9, MC-3).

    ``i`` / ``j`` are the source comparison's upper-triangle strategy indices;
    ``label_i`` / ``label_j`` the ``strategy_k`` labels (carried for readability,
    derivable from ``i`` / ``j``, excluded from the hash's cell payload beyond ``i`` /
    ``j``); ``p_value`` the source's KNOWN two-sided ``p`` value as a canonical decimal
    string.
    """

    i: int
    j: int
    label_i: str
    label_j: str
    p_value: str

    def to_dict(self) -> dict[str, object]:
        return {
            "i": self.i,
            "j": self.j,
            "label_i": self.label_i,
            "label_j": self.label_j,
            "p_value": self.p_value,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FamilyCell:
        return cls(
            i=_req_int(raw, "i"),
            j=_req_int(raw, "j"),
            label_i=_req_str(raw, "label_i"),
            label_j=_req_str(raw, "label_j"),
            p_value=_req_str(raw, "p_value"),
        )


@dataclass(frozen=True, slots=True)
class ExcludedCell:
    """One pairwise cell excluded from the family - its ``p`` value was UNDEFINED
    (MC-3).

    A pair the source comparison sealed with an UNDEFINED ``p`` value (``reason``:
    ``INSUFFICIENT_OVERLAP`` - too few shared dates; or ``ZERO_DIFFERENCE_VARIANCE`` - a
    zero-variance paired difference). It carries no adjusted value: it is recorded here,
    never imputed and never coerced to a number (MC-4).
    """

    i: int
    j: int
    label_i: str
    label_j: str
    reason: ComparisonUndefinedReason

    def to_dict(self) -> dict[str, object]:
        return {
            "i": self.i,
            "j": self.j,
            "label_i": self.label_i,
            "label_j": self.label_j,
            "reason": self.reason.value,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ExcludedCell:
        return cls(
            i=_req_int(raw, "i"),
            j=_req_int(raw, "j"),
            label_i=_req_str(raw, "label_i"),
            label_j=_req_str(raw, "label_j"),
            reason=_reason(raw),
        )


@dataclass(frozen=True, slots=True)
class MethodCell:
    """One family member's adjusted ``p`` value + rejection flag under one method (§9).

    ``i`` / ``j`` key the cell back to its :class:`FamilyCell`; ``p_adjusted`` is the
    method's adjusted ``p`` value as a canonical decimal string (capped at ``1``);
    ``rejected`` is ``p_adjusted ≤ alpha`` (the single, self-consistent rejection rule,
    MC-5).
    """

    i: int
    j: int
    p_adjusted: str
    rejected: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "i": self.i,
            "j": self.j,
            "p_adjusted": self.p_adjusted,
            "rejected": self.rejected,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MethodCell:
        return cls(
            i=_req_int(raw, "i"),
            j=_req_int(raw, "j"),
            p_adjusted=_req_str(raw, "p_adjusted"),
            rejected=_req_bool(raw, "rejected"),
        )


@dataclass(frozen=True, slots=True)
class MethodResult:
    """One correction method's honest labels + per-family-cell results (§9, MC-5/MC-6).

    ``error_rate`` (family-wise vs false-discovery) and ``dependence`` (arbitrary vs
    independence/PRDS) are the method's sealed labels, so Benjamini-Hochberg's
    independence assumption can never be mistaken for a dependence-robust guarantee
    (MC-6). ``cells`` hold the adjusted ``p`` value + rejection per family cell (in
    family order); ``n_rejected`` is the count of rejections (a reader's convenience; a
    pure function of ``cells``, excluded from ``result_hash``).
    """

    method: CorrectionMethod
    error_rate: ErrorRate
    dependence: DependenceAssumption
    cells: tuple[MethodCell, ...]
    n_rejected: int

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method.value,
            "error_rate": self.error_rate.value,
            "dependence": self.dependence.value,
            "cells": [cell.to_dict() for cell in self.cells],
            "n_rejected": self.n_rejected,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MethodResult:
        try:
            error_rate = ErrorRate(_req_str(raw, "error_rate"))
        except ValueError as exc:
            raise ValueError("unknown error_rate") from exc
        try:
            dependence = DependenceAssumption(_req_str(raw, "dependence"))
        except ValueError as exc:
            raise ValueError("unknown dependence assumption") from exc
        return cls(
            method=_method(_req_str(raw, "method")),
            error_rate=error_rate,
            dependence=dependence,
            cells=tuple(
                MethodCell.from_dict(_as_dict(item, "cells"))
                for item in _req_list(raw, "cells")
            ),
            n_rejected=_req_int(raw, "n_rejected"),
        )


@dataclass(frozen=True, slots=True)
class MultiplicityCoverage:
    """The audit coverage block - counts of pairs, family, and exclusions (§9).

    Excluded from ``result_hash`` (a pure function of the sealed family / excluded lists
    - a reader's convenience, not an independent input): the source comparison held
    ``n_pairs_total`` upper-triangle pairs, of which ``family_size`` had a KNOWN ``p``
    value (the corrected family) and ``n_excluded`` were excluded (UNDEFINED ``p``).
    """

    n_pairs_total: int
    family_size: int
    n_excluded: int

    def to_dict(self) -> dict[str, object]:
        return {
            "n_pairs_total": self.n_pairs_total,
            "family_size": self.family_size,
            "n_excluded": self.n_excluded,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MultiplicityCoverage:
        return cls(
            n_pairs_total=_req_int(raw, "n_pairs_total"),
            family_size=_req_int(raw, "family_size"),
            n_excluded=_req_int(raw, "n_excluded"),
        )


@dataclass(frozen=True, slots=True)
class MultipleComparisonCorrection:
    """A sealed, content-addressed multiplicity-correction record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`multiple_comparison_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins the source comparison by ``(id, result_hash)``, records the
    declared ``alpha``, holds the KNOWN ``p`` value family, the excluded cells, and the
    per-method corrections, and seals the computed answer into ``result_hash``. It is
    **not** a ``Pit*`` type and exposes no as-of accessor (MC-6).
    """

    multiplicity_engine_version_id: str
    correction_spec: dict[str, object]
    source_ref: tuple[str, str]
    boundary_kind: str
    family: tuple[FamilyCell, ...]
    excluded: tuple[ExcludedCell, ...]
    corrections: tuple[MethodResult, ...]
    coverage: MultiplicityCoverage
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def multiple_comparison_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the source comparison id + ``result_hash``, the
        declared ``alpha``, the ordered method list, and the sealed ``result_hash`` over
        the answer.
        """
        spec = self.correction_spec
        return _multiple_comparison_id(
            multiplicity_engine_version_id=self.multiplicity_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_strategy_comparison_id=_spec_str(
                spec, "source_strategy_comparison_id"
            ),
            source_result_hash=self.source_ref[1],
            alpha=_spec_str(spec, "alpha"),
            methods=_spec_methods(spec),
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`multiple_comparison_id` - the :class:`ResearchRecord` id."""
        return self.multiple_comparison_id

    @property
    def source_strategy_comparison_id(self) -> str:
        """The referenced source comparison's ``research_result_id``."""
        return self.source_ref[0]

    @property
    def source_result_hash(self) -> str:
        """The referenced source comparison's ``result_hash`` (the transitive pin)."""
        return self.source_ref[1]

    @property
    def alpha(self) -> str:
        """The declared significance level (canonical decimal string), from the
        request."""
        return _spec_str(self.correction_spec, "alpha")

    @property
    def family_size(self) -> int:
        """The corrected family size ``m`` (count of KNOWN pairwise ``p`` values)."""
        return len(self.family)

    def correction(self, method: CorrectionMethod) -> MethodResult:
        """The :class:`MethodResult` for ``method``; raises if it was not requested."""
        for result in self.corrections:
            if result.method is method:
                return result
        raise KeyError(f"method {method.value!r} was not part of this correction")

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        multiplicity_engine_version_id: str,
        correction_spec: dict[str, object],
        source_ref: tuple[str, str],
        boundary_kind: str,
        family: tuple[FamilyCell, ...],
        excluded: tuple[ExcludedCell, ...],
        corrections: tuple[MethodResult, ...],
        coverage: MultiplicityCoverage,
        method_version: str = MULTIPLICITY_METHOD_VERSION,
    ) -> MultipleComparisonCorrection:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the family descriptor, the KNOWN family cells, the excluded cells, then
        per method the labels and adjusted cells) into ``result_hash`` via
        :func:`~quantforge.multiplicity.identity.multiple_comparison_result_hash`, so
        identity is a pure function of the computed answer and never has to be supplied
        by the caller. The coverage block is a function of those cells and is excluded.
        """
        rhash = _result_hash(
            _output_cells(
                family=family,
                excluded=excluded,
                corrections=corrections,
                coverage=coverage,
            )
        )
        return cls(
            multiplicity_engine_version_id=multiplicity_engine_version_id,
            correction_spec=dict(correction_spec),
            source_ref=source_ref,
            boundary_kind=boundary_kind,
            family=family,
            excluded=excluded,
            corrections=corrections,
            coverage=coverage,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "multiple_comparison_id": self.multiple_comparison_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "multiplicity_engine_version_id": self.multiplicity_engine_version_id,
            "correction_spec": dict(self.correction_spec),
            "source_ref": {
                "source_strategy_comparison_id": self.source_ref[0],
                "source_result_hash": self.source_ref[1],
            },
            "boundary_kind": self.boundary_kind,
            "family": [cell.to_dict() for cell in self.family],
            "excluded": [cell.to_dict() for cell in self.excluded],
            "corrections": [result.to_dict() for result in self.corrections],
            "coverage": self.coverage.to_dict(),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MultipleComparisonCorrection:
        """Reconstruct a sealed correction record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, MultipleComparisonCorrection.from_dict)`` is a
        first-class typed object. ``multiple_comparison_id`` / ``research_result_id``
        are derived aliases re-emitted by their properties (never read from state),
        every nested cell round-trips through its own fail-closed ``from_dict``, and the
        block order is preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes
        and the same ``result_hash``, introducing no drift.
        """
        source = _req_dict(raw, "source_ref")
        return cls(
            multiplicity_engine_version_id=_req_str(
                raw, "multiplicity_engine_version_id"
            ),
            correction_spec=dict(_req_dict(raw, "correction_spec")),
            source_ref=(
                _req_str(source, "source_strategy_comparison_id"),
                _req_str(source, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            family=tuple(
                FamilyCell.from_dict(_as_dict(item, "family"))
                for item in _req_list(raw, "family")
            ),
            excluded=tuple(
                ExcludedCell.from_dict(_as_dict(item, "excluded"))
                for item in _req_list(raw, "excluded")
            ),
            corrections=tuple(
                MethodResult.from_dict(_as_dict(item, "corrections"))
                for item in _req_list(raw, "corrections")
            ),
            coverage=MultiplicityCoverage.from_dict(_req_dict(raw, "coverage")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    family: tuple[FamilyCell, ...],
    excluded: tuple[ExcludedCell, ...],
    corrections: tuple[MethodResult, ...],
    coverage: MultiplicityCoverage,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the family descriptor (family size ``m`` + excluded
    count), then the KNOWN family cells (``i`` / ``j`` / ``p_value``) in source
    upper-triangle order, then the excluded cells (``i`` / ``j`` / reason), then per
    method the honest labels (error-rate, dependence) and each family cell's adjusted
    value + rejection - each tagged by its block so two structurally different records
    can never collide. The derivable ``label_i`` / ``label_j`` are omitted (the ``i`` /
    ``j`` indices fold them); the ids, ``alpha``, and method order are folded into
    ``multiple_comparison_id`` through the request + reference instead. Sensitive to
    every computed adjusted value and rejection flag. The coverage block is a pure
    function of these cells (only its two structural counts are folded, in the
    descriptor).
    """
    cells: list[dict[str, object]] = [
        {
            "block": "family_descriptor",
            "family_size": coverage.family_size,
            "n_excluded": coverage.n_excluded,
        }
    ]
    for member in family:
        cells.append(
            {
                "block": "family",
                "i": member.i,
                "j": member.j,
                "p_value": member.p_value,
            }
        )
    for gap in excluded:
        cells.append(
            {
                "block": "excluded",
                "i": gap.i,
                "j": gap.j,
                "reason": gap.reason.value,
            }
        )
    for result in corrections:
        cells.append(
            {
                "block": "method",
                "method": result.method.value,
                "error_rate": result.error_rate.value,
                "dependence": result.dependence.value,
                "cells": [
                    {
                        "i": cell.i,
                        "j": cell.j,
                        "p_adjusted": cell.p_adjusted,
                        "rejected": cell.rejected,
                    }
                    for cell in result.cells
                ],
            }
        )
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"correction_spec.{key} must be a string")
    return value


def _spec_methods(spec: dict[str, object]) -> list[str]:
    """Read the ordered method value strings from the embedded request (fail closed)."""
    value = spec.get("methods")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("correction_spec.methods must be a list of strings")
    return [str(item) for item in value]
