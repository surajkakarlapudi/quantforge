"""The sealed, content-addressed strategy-admissibility record (§9, §10).

A completed decision is a :class:`StrategyAdmissibility`: the engine version, the full
declarative request, three ``(id, result_hash)`` references to the sealed
:class:`~quantforge.stability.result.WalkForwardStability`,
:class:`~quantforge.calsig.result.CalibrationSignificance`, and
:class:`~quantforge.netcostsig.result.NetOfCostSignificance` it consumed, the
:class:`AdmissibilitySummary` (the joint verdict, the declared level, and the three
ordered criteria), and the sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``admissibility_id`` (a single id) and ``to_dict`` is deterministic - so it
persists write-once to the shared Phase 8 sidecar with **no new store** (§13). It stores
only *pointers* to the three source verdicts, never a copy of their contents (the
pointer-only discipline of
:class:`~quantforge.netcostsig.result.NetOfCostSignificance`): each source already lives
in the same sidecar, so this record stays a thin, reproducible view over them.

**Ex-post, not PIT (AD-6).** An admissibility decision over three already-ex-post
verdicts is itself an ex-post research statistic, not a forward-usable PIT value.
:class:`StrategyAdmissibility` is deliberately **not** a ``Pit*`` type and exposes
**no** as-of accessor. ``boundary_kind = "pit"`` documents only that the *underlying
factor portfolios* (beneath each consumed verdict's walk-forward) were PIT walks - the
convention where the label describes the input side, not the ex-post output. It is not a
``BacktestResult`` and performs no execution.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~StrategyAdmissibility.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.admissibility.identity import (
    admissibility_id as _admissibility_id,
)
from quantforge.admissibility.identity import (
    admissibility_result_hash as _result_hash,
)
from quantforge.admissibility.model import (
    AdmissibilityVerdict,
    Criterion,
    CriterionKind,
    CriterionStatus,
)
from quantforge.admissibility.version import ADMISSIBILITY_METHOD_VERSION

__all__ = [
    "ADMISSIBILITY_RESULT_FORMAT_VERSION",
    "BOUNDARY_PIT",
    "AdmissibilitySummary",
    "StrategyAdmissibility",
]

#: The §9 record-schema version for the admissibility record - distinct from the
#: engine-logic version, the method version, and the sidecar's container format version.
#: Bump it when the serialized meaning of an admissibility record changes (a container
#: concern; it is **not** folded into ``admissibility_id`` - §10, prior-phase
#: discipline).
ADMISSIBILITY_RESULT_FORMAT_VERSION = "admissibility-result/1"

#: The only boundary a v1 admissibility record accepts. It documents that the
#: *underlying factor portfolios* (beneath each consumed verdict's walk-forward) were
#: PIT walks; the admissibility *output* is ex-post and is not a PIT value (AD-6).
BOUNDARY_PIT = "pit"


# -- fail-closed decode helpers ----------------------------------------------


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
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


@dataclass(frozen=True, slots=True)
class AdmissibilitySummary:
    """The joint verdict + the declared level + the three ordered criteria (§9).

    ``verdict`` is the roll-up
    (:class:`~quantforge.admissibility.model.AdmissibilityVerdict`); ``alpha`` the
    declared significance level tested (canonical decimal string); ``criteria`` the
    three evaluated :class:`~quantforge.admissibility.model.Criterion` cells in the
    fixed order STABILITY, CALIBRATION, NET_OF_COST_EDGE. With any consumed verdict
    UNDEFINED the corresponding criterion is UNDEFINED and the roll-up is UNDEFINED; the
    record still seals (AD-2).
    """

    verdict: AdmissibilityVerdict
    alpha: str
    criteria: tuple[Criterion, ...]

    @property
    def failed_criteria(self) -> tuple[CriterionKind, ...]:
        """The kinds of the criteria that FAILed (empty unless INADMISSIBLE)."""
        return tuple(c.kind for c in self.criteria if c.status is CriterionStatus.FAIL)

    @property
    def undefined_criteria(self) -> tuple[CriterionKind, ...]:
        """The kinds of the criteria that are UNDEFINED (empty unless verdict
        UNDEFINED)."""
        return tuple(
            c.kind for c in self.criteria if c.status is CriterionStatus.UNDEFINED
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "alpha": self.alpha,
            "criteria": [c.to_dict() for c in self.criteria],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> AdmissibilitySummary:
        verdict_raw = _req_str(raw, "verdict")
        try:
            verdict = AdmissibilityVerdict(verdict_raw)
        except ValueError as exc:
            raise ValueError(f"unknown verdict {verdict_raw!r}") from exc

        criteria_raw = _req_list(raw, "criteria")
        criteria: list[Criterion] = []
        for cell in criteria_raw:
            if not isinstance(cell, dict):
                raise ValueError(
                    "each AdmissibilitySummary criterion must be an object"
                )
            criteria.append(Criterion.from_dict(cell))

        return cls(
            verdict=verdict,
            alpha=_req_str(raw, "alpha"),
            criteria=tuple(criteria),
        )


@dataclass(frozen=True, slots=True)
class StrategyAdmissibility:
    """A sealed, content-addressed strategy-admissibility record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`admissibility_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins each of the three source verdicts by ``(id, result_hash)``, holds
    the joint :class:`AdmissibilitySummary`, and seals the computed answer into
    ``result_hash``. It is **not** a ``Pit*`` type and exposes no as-of accessor (AD-6).
    """

    admissibility_engine_version_id: str
    admissibility_spec: dict[str, object]
    stability_ref: tuple[str, str]
    calibration_ref: tuple[str, str]
    net_of_cost_ref: tuple[str, str]
    boundary_kind: str
    summary: AdmissibilitySummary
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def admissibility_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), each source verdict's id + ``result_hash`` (so the
        id is transitively sensitive to any change beneath), the declared ``alpha``, and
        the sealed ``result_hash`` over the answer.
        """
        spec = self.admissibility_spec
        return _admissibility_id(
            admissibility_engine_version_id=self.admissibility_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_stability_id=_spec_str(spec, "source_stability_id"),
            source_stability_result_hash=self.stability_ref[1],
            source_calibration_significance_id=_spec_str(
                spec, "source_calibration_significance_id"
            ),
            source_calibration_result_hash=self.calibration_ref[1],
            source_net_of_cost_significance_id=_spec_str(
                spec, "source_net_of_cost_significance_id"
            ),
            source_net_of_cost_result_hash=self.net_of_cost_ref[1],
            alpha=self.summary.alpha,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`admissibility_id` - the :class:`ResearchRecord` id."""
        return self.admissibility_id

    @property
    def source_stability_id(self) -> str:
        """The referenced source stability record's ``research_result_id``."""
        return self.stability_ref[0]

    @property
    def source_stability_result_hash(self) -> str:
        """The referenced source stability record's ``result_hash`` (transitive pin)."""
        return self.stability_ref[1]

    @property
    def source_calibration_significance_id(self) -> str:
        """The referenced source calibration-significance record's
        ``research_result_id``."""
        return self.calibration_ref[0]

    @property
    def source_calibration_result_hash(self) -> str:
        """The referenced source calibration record's ``result_hash`` (transitive
        pin)."""
        return self.calibration_ref[1]

    @property
    def source_net_of_cost_significance_id(self) -> str:
        """The referenced source net-of-cost-significance record's
        ``research_result_id``."""
        return self.net_of_cost_ref[0]

    @property
    def source_net_of_cost_result_hash(self) -> str:
        """The referenced source net-of-cost record's ``result_hash`` (transitive
        pin)."""
        return self.net_of_cost_ref[1]

    @property
    def verdict(self) -> AdmissibilityVerdict:
        """The roll-up admissibility verdict (a convenience alias of the summary's)."""
        return self.summary.verdict

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        admissibility_engine_version_id: str,
        admissibility_spec: dict[str, object],
        stability_ref: tuple[str, str],
        calibration_ref: tuple[str, str],
        net_of_cost_ref: tuple[str, str],
        boundary_kind: str,
        summary: AdmissibilitySummary,
        method_version: str = ADMISSIBILITY_METHOD_VERSION,
    ) -> StrategyAdmissibility:
        """Seal the computed summary, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the single admissibility summary block) into ``result_hash`` via
        :func:`~quantforge.admissibility.identity.admissibility_result_hash`, so
        identity is a pure function of the computed answer and never has to be supplied
        by the caller.
        """
        rhash = _result_hash(_output_cells(summary=summary))
        return cls(
            admissibility_engine_version_id=admissibility_engine_version_id,
            admissibility_spec=dict(admissibility_spec),
            stability_ref=stability_ref,
            calibration_ref=calibration_ref,
            net_of_cost_ref=net_of_cost_ref,
            boundary_kind=boundary_kind,
            summary=summary,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "admissibility_id": self.admissibility_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "admissibility_engine_version_id": self.admissibility_engine_version_id,
            "admissibility_spec": dict(self.admissibility_spec),
            "stability_ref": {
                "source_stability_id": self.stability_ref[0],
                "source_result_hash": self.stability_ref[1],
            },
            "calibration_ref": {
                "source_calibration_significance_id": self.calibration_ref[0],
                "source_result_hash": self.calibration_ref[1],
            },
            "net_of_cost_ref": {
                "source_net_of_cost_significance_id": self.net_of_cost_ref[0],
                "source_result_hash": self.net_of_cost_ref[1],
            },
            "boundary_kind": self.boundary_kind,
            "summary": self.summary.to_dict(),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StrategyAdmissibility:
        """Reconstruct a sealed admissibility record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, StrategyAdmissibility.from_dict)`` is a
        first-class typed object. ``admissibility_id`` / ``research_result_id`` are
        derived aliases re-emitted by their properties (never read from state), the
        nested summary round-trips through its own fail-closed ``from_dict`` - so
        ``from_dict(to_dict(r))`` re-emits identical bytes and the same ``result_hash``,
        introducing no drift.
        """
        stability = _req_dict(raw, "stability_ref")
        calibration = _req_dict(raw, "calibration_ref")
        net_of_cost = _req_dict(raw, "net_of_cost_ref")
        return cls(
            admissibility_engine_version_id=_req_str(
                raw, "admissibility_engine_version_id"
            ),
            admissibility_spec=dict(_req_dict(raw, "admissibility_spec")),
            stability_ref=(
                _req_str(stability, "source_stability_id"),
                _req_str(stability, "source_result_hash"),
            ),
            calibration_ref=(
                _req_str(calibration, "source_calibration_significance_id"),
                _req_str(calibration, "source_result_hash"),
            ),
            net_of_cost_ref=(
                _req_str(net_of_cost, "source_net_of_cost_significance_id"),
                _req_str(net_of_cost, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            summary=AdmissibilitySummary.from_dict(_req_dict(raw, "summary")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(*, summary: AdmissibilitySummary) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the admissibility summary block, tagged by its block
    so two structurally different records can never collide. The ids, request, and level
    are folded into ``admissibility_id`` through the request + references instead.
    Sensitive to the verdict and every per-criterion status.
    """
    return [{"block": "summary", **summary.to_dict()}]


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"admissibility_spec.{key} must be a string")
    return value
