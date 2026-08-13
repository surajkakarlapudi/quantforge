"""The sealed, content-addressed campaign-multiplicity-correction record (§9, §10).

A completed correction is a :class:`CampaignMultiplicityCorrection`: the engine version,
the full declarative request, the ``(source_campaign_id, source_result_hash)`` reference
to the one sealed campaign it consumed, the declared ``alpha``, the per-trial one-sided
p-value **family** (in the source campaign's trial order, each carrying the consumed
``psr`` and the derived ``p = 1 - PSR``), the **excluded** trials (trials the source
sealed with an UNDEFINED ``psr``, each with its reason), the per-method **corrections**
(each method's honest labels plus its adjusted ``p`` value + rejection flag per family
trial), a non-hashed coverage block, and the sealed ``result_hash`` over the computed
answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``campaign_multiplicity_id`` (a single id, mirroring ``campaign_id``) and
``to_dict`` is deterministic - so it persists write-once to the shared Phase 8 sidecar
with **no new store**. It stores only a *pointer* to the source campaign, never a copy
of its trial table (the pointer-only discipline of
:class:`~quantforge.multiplicity.result.MultipleComparisonCorrection`): the source
already lives in the same sidecar, so this record stays a thin, reproducible view over
it.

**Ex-post, not PIT (CM-6).** A multiplicity correction over already-ex-post per-trial
``PSR`` values is itself an ex-post research statistic, not a forward-usable PIT value.
:class:`CampaignMultiplicityCorrection` is deliberately **not** a ``Pit*`` type and
exposes **no** as-of accessor. ``boundary_kind = "pit"`` documents only that the
*underlying trials* were PIT walks - the convention where the label describes the input
side, not the ex-post output.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~CampaignMultiplicityCorrection.from_dict`; the derived ids are re-emitted by
their properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.campaign.model import CampaignUndefinedReason
from quantforge.campaignmult.identity import (
    campaign_multiplicity_id as _campaign_multiplicity_id,
)
from quantforge.campaignmult.identity import (
    campaign_multiplicity_result_hash as _result_hash,
)
from quantforge.campaignmult.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
)
from quantforge.campaignmult.version import CAMPAIGNMULT_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "CAMPAIGNMULT_RESULT_FORMAT_VERSION",
    "CampaignMultiplicityCorrection",
    "CampaignMultiplicityCoverage",
    "ExcludedTrialCell",
    "MethodResult",
    "TrialFamilyCell",
    "TrialMethodCell",
]

#: The §9 record-schema version for the correction record - distinct from the
#: engine-logic version, the method version, and the sidecar's container format version.
#: Bump it when the serialized meaning of a correction record changes (a container
#: concern; it is **not** folded into ``campaign_multiplicity_id`` - §10, prior-phase
#: discipline).
CAMPAIGNMULT_RESULT_FORMAT_VERSION = "campaignmult-result/1"

#: The only boundary a v1 correction record accepts. It documents that the *underlying
#: trials* (beneath the source campaign) were PIT walks; the correction *output* is
#: ex-post and is not a PIT value (CM-6). The engine carries the source campaign's
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


def _reason(raw: dict[str, object]) -> CampaignUndefinedReason:
    """Decode a required exclusion ``reason`` string (fail closed).

    The reason is the source campaign's ``psr`` UNDEFINED reason (``ZERO_OOS_VARIANCE``
    for a zero-variance OOS series, ``DEGENERATE_SHARPE_ESTIMATOR`` for a degenerate PSR
    estimator, ``INSUFFICIENT_OOS_PERIODS`` for a too-short trial), so the closed
    :class:`~quantforge.campaign.model.CampaignUndefinedReason` vocabulary validates it.
    """
    reason_raw = raw.get("reason")
    if not isinstance(reason_raw, str):
        raise ValueError("ExcludedTrialCell.reason must be a string")
    try:
        return CampaignUndefinedReason(reason_raw)
    except ValueError as exc:
        raise ValueError(f"unknown CampaignUndefinedReason {reason_raw!r}") from exc


def _method(value: str) -> CorrectionMethod:
    try:
        return CorrectionMethod(value)
    except ValueError as exc:
        raise ValueError(f"unknown correction method {value!r}") from exc


@dataclass(frozen=True, slots=True)
class TrialFamilyCell:
    """One KNOWN per-trial ``p`` value entering the corrected family (§9, CM-3/CM-4).

    ``index`` is the trial's 0-based position in the source campaign's request order;
    ``label`` the ``trial_k`` label (carried for readability, derivable from ``index``,
    excluded from the hash's cell payload beyond ``index``); ``psr`` the source's KNOWN
    Probabilistic Sharpe Ratio as a canonical decimal string (consumed verbatim);
    ``p_value`` the derived one-sided p-value ``1 - PSR`` as a canonical decimal string
    (the only added arithmetic, CM-4).
    """

    index: int
    label: str
    psr: str
    p_value: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "label": self.label,
            "psr": self.psr,
            "p_value": self.p_value,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TrialFamilyCell:
        return cls(
            index=_req_int(raw, "index"),
            label=_req_str(raw, "label"),
            psr=_req_str(raw, "psr"),
            p_value=_req_str(raw, "p_value"),
        )


@dataclass(frozen=True, slots=True)
class ExcludedTrialCell:
    """One trial excluded from the family - its ``psr`` was UNDEFINED (CM-3).

    A trial the source campaign sealed with an UNDEFINED ``psr`` (``reason``:
    ``ZERO_OOS_VARIANCE`` - a zero-variance OOS series; ``DEGENERATE_SHARPE_ESTIMATOR``
    - a non-positive PSR-estimator variance; ``INSUFFICIENT_OOS_PERIODS`` - too few OOS
    periods). It carries no adjusted value: it is recorded here, never imputed and never
    coerced to a number (CM-4).
    """

    index: int
    label: str
    reason: CampaignUndefinedReason

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "label": self.label,
            "reason": self.reason.value,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ExcludedTrialCell:
        return cls(
            index=_req_int(raw, "index"),
            label=_req_str(raw, "label"),
            reason=_reason(raw),
        )


@dataclass(frozen=True, slots=True)
class TrialMethodCell:
    """One family trial's adjusted ``p`` value + rejection flag under one method (§9).

    ``index`` keys the cell back to its :class:`TrialFamilyCell`; ``p_adjusted`` is the
    method's adjusted ``p`` value as a canonical decimal string (capped at ``1``);
    ``rejected`` is ``p_adjusted ≤ alpha`` (the single, self-consistent rejection rule,
    CM-5).
    """

    index: int
    p_adjusted: str
    rejected: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "p_adjusted": self.p_adjusted,
            "rejected": self.rejected,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TrialMethodCell:
        return cls(
            index=_req_int(raw, "index"),
            p_adjusted=_req_str(raw, "p_adjusted"),
            rejected=_req_bool(raw, "rejected"),
        )


@dataclass(frozen=True, slots=True)
class MethodResult:
    """One correction method's honest labels + per-family-trial results (§9, CM-5/CM-6).

    ``error_rate`` (family-wise vs false-discovery) and ``dependence`` (arbitrary vs
    independence/PRDS) are the method's sealed labels, so Benjamini-Hochberg's
    independence assumption can never be mistaken for a dependence-robust guarantee
    (CM-6). ``cells`` hold the adjusted ``p`` value + rejection per family trial (in
    family order); ``n_rejected`` is the count of rejections (a reader's convenience; a
    pure function of ``cells``, excluded from ``result_hash``).
    """

    method: CorrectionMethod
    error_rate: ErrorRate
    dependence: DependenceAssumption
    cells: tuple[TrialMethodCell, ...]
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
                TrialMethodCell.from_dict(_as_dict(item, "cells"))
                for item in _req_list(raw, "cells")
            ),
            n_rejected=_req_int(raw, "n_rejected"),
        )


@dataclass(frozen=True, slots=True)
class CampaignMultiplicityCoverage:
    """The audit coverage block - counts of trials, family, and exclusions (§9).

    Excluded from ``result_hash`` (a pure function of the sealed family / excluded lists
    - a reader's convenience, not an independent input): the source campaign held
    ``n_trials_total`` trials, of which ``family_size`` had a KNOWN ``psr`` (the
    corrected family) and ``n_excluded`` were excluded (UNDEFINED ``psr``).
    """

    n_trials_total: int
    family_size: int
    n_excluded: int

    def to_dict(self) -> dict[str, object]:
        return {
            "n_trials_total": self.n_trials_total,
            "family_size": self.family_size,
            "n_excluded": self.n_excluded,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CampaignMultiplicityCoverage:
        return cls(
            n_trials_total=_req_int(raw, "n_trials_total"),
            family_size=_req_int(raw, "family_size"),
            n_excluded=_req_int(raw, "n_excluded"),
        )


@dataclass(frozen=True, slots=True)
class CampaignMultiplicityCorrection:
    """A sealed, content-addressed campaign-multiplicity-correction record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`campaign_multiplicity_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins the source campaign by ``(id, result_hash)``, records the
    declared ``alpha``, holds the per-trial ``p`` value family, the excluded trials, and
    the per-method corrections, and seals the computed answer into ``result_hash``. It
    is **not** a ``Pit*`` type and exposes no as-of accessor (CM-6).
    """

    campaign_multiplicity_engine_version_id: str
    correction_spec: dict[str, object]
    source_ref: tuple[str, str]
    boundary_kind: str
    family: tuple[TrialFamilyCell, ...]
    excluded: tuple[ExcludedTrialCell, ...]
    corrections: tuple[MethodResult, ...]
    coverage: CampaignMultiplicityCoverage
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def campaign_multiplicity_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the source campaign id + ``result_hash``, the
        declared ``alpha``, the ordered method list, and the sealed ``result_hash`` over
        the answer.
        """
        spec = self.correction_spec
        return _campaign_multiplicity_id(
            campaign_multiplicity_engine_version_id=(
                self.campaign_multiplicity_engine_version_id
            ),
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_campaign_id=_spec_str(spec, "source_campaign_id"),
            source_result_hash=self.source_ref[1],
            alpha=_spec_str(spec, "alpha"),
            methods=_spec_methods(spec),
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`campaign_multiplicity_id` - the :class:`ResearchRecord`
        id."""
        return self.campaign_multiplicity_id

    @property
    def source_campaign_id(self) -> str:
        """The referenced source campaign's ``research_result_id``."""
        return self.source_ref[0]

    @property
    def source_result_hash(self) -> str:
        """The referenced source campaign's ``result_hash`` (the transitive pin)."""
        return self.source_ref[1]

    @property
    def alpha(self) -> str:
        """The declared significance level (canonical decimal string), from the
        request."""
        return _spec_str(self.correction_spec, "alpha")

    @property
    def family_size(self) -> int:
        """The corrected family size ``m`` (count of KNOWN per-trial ``p`` values)."""
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
        campaign_multiplicity_engine_version_id: str,
        correction_spec: dict[str, object],
        source_ref: tuple[str, str],
        boundary_kind: str,
        family: tuple[TrialFamilyCell, ...],
        excluded: tuple[ExcludedTrialCell, ...],
        corrections: tuple[MethodResult, ...],
        coverage: CampaignMultiplicityCoverage,
        method_version: str = CAMPAIGNMULT_METHOD_VERSION,
    ) -> CampaignMultiplicityCorrection:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the family descriptor, the KNOWN family cells, the excluded cells, then
        per method the labels and adjusted cells) into ``result_hash`` via
        :func:`~quantforge.campaignmult.identity.campaign_multiplicity_result_hash`, so
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
            campaign_multiplicity_engine_version_id=(
                campaign_multiplicity_engine_version_id
            ),
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
            "campaign_multiplicity_id": self.campaign_multiplicity_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "campaign_multiplicity_engine_version_id": (
                self.campaign_multiplicity_engine_version_id
            ),
            "correction_spec": dict(self.correction_spec),
            "source_ref": {
                "source_campaign_id": self.source_ref[0],
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
    def from_dict(cls, raw: dict[str, object]) -> CampaignMultiplicityCorrection:
        """Reconstruct a sealed correction record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, CampaignMultiplicityCorrection.from_dict)`` is a
        first-class typed object. ``campaign_multiplicity_id`` / ``research_result_id``
        are derived aliases re-emitted by their properties (never read from state),
        every nested cell round-trips through its own fail-closed ``from_dict``, and the
        block order is preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes
        and the same ``result_hash``, introducing no drift.
        """
        source = _req_dict(raw, "source_ref")
        return cls(
            campaign_multiplicity_engine_version_id=_req_str(
                raw, "campaign_multiplicity_engine_version_id"
            ),
            correction_spec=dict(_req_dict(raw, "correction_spec")),
            source_ref=(
                _req_str(source, "source_campaign_id"),
                _req_str(source, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            family=tuple(
                TrialFamilyCell.from_dict(_as_dict(item, "family"))
                for item in _req_list(raw, "family")
            ),
            excluded=tuple(
                ExcludedTrialCell.from_dict(_as_dict(item, "excluded"))
                for item in _req_list(raw, "excluded")
            ),
            corrections=tuple(
                MethodResult.from_dict(_as_dict(item, "corrections"))
                for item in _req_list(raw, "corrections")
            ),
            coverage=CampaignMultiplicityCoverage.from_dict(_req_dict(raw, "coverage")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    family: tuple[TrialFamilyCell, ...],
    excluded: tuple[ExcludedTrialCell, ...],
    corrections: tuple[MethodResult, ...],
    coverage: CampaignMultiplicityCoverage,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the family descriptor (family size ``m`` + excluded
    count), then the KNOWN family cells (``index`` / ``psr`` / ``p_value``) in source
    trial order, then the excluded cells (``index`` / reason), then per method the
    honest labels (error-rate, dependence) and each family trial's adjusted value +
    rejection - each tagged by its block so two structurally different records can never
    collide. The derivable ``label`` is omitted (the ``index`` folds it); the ids,
    ``alpha``, and method order are folded into ``campaign_multiplicity_id`` through the
    request + reference instead. Sensitive to every consumed ``psr``, derived ``p``
    value, computed adjusted value, and rejection flag. The coverage block is a pure
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
                "index": member.index,
                "psr": member.psr,
                "p_value": member.p_value,
            }
        )
    for gap in excluded:
        cells.append(
            {
                "block": "excluded",
                "index": gap.index,
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
                        "index": cell.index,
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
