"""The sealed, content-addressed walk-forward-stability record (§9, §10).

A completed analysis is a :class:`WalkForwardStability`: the engine version, the full
declarative request, the ``(source_walk_forward_id, source_result_hash)`` reference to
the one sealed walk-forward it consumed, per **REALIZED** window the weight-vector
stability metrics and one-way turnover (in the source's window order), the **excluded**
windows (each a window the source sealed UNDEFINED, with its reason), the aggregate
turnover / concentration :class:`StabilitySummary`, a non-hashed coverage block, and the
sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``walk_forward_stability_id`` (a single id, mirroring
``risk_forecast_calibration_id``) and ``to_dict`` is deterministic - so it persists
write-once to the shared Phase 8 sidecar with **no new store**. It stores only a
*pointer* to the source walk-forward, never a copy of its windows (the pointer-only
discipline of :class:`~quantforge.calibration.result.RiskForecastCalibration`): the
source already lives in the same sidecar, so this record stays a thin, reproducible view
over it.

**Ex-post, not PIT (WS-6).** A stability analysis over an already-ex-post
walk-forward is itself an ex-post research statistic, not a forward-usable PIT value.
:class:`WalkForwardStability` is deliberately **not** a ``Pit*`` type and exposes
**no** as-of accessor. ``boundary_kind = "pit"`` documents only that the *underlying
factor portfolios* were PIT walks - the convention where the label describes the input
side, not the ex-post output. It is not a ``BacktestResult`` and performs no execution.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~WalkForwardStability.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.stability.identity import (
    walk_forward_stability_id as _stability_id,
)
from quantforge.stability.identity import (
    walk_forward_stability_result_hash as _result_hash,
)
from quantforge.stability.model import (
    StabilityExcludedReason,
    StabilityStat,
    StabilityStatus,
    StabilityUndefinedReason,
)
from quantforge.stability.version import STABILITY_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "MIN_STABILITY_TRANSITIONS",
    "STABILITY_RESULT_FORMAT_VERSION",
    "ExcludedWindow",
    "StabilityCoverage",
    "StabilitySummary",
    "WalkForwardStability",
    "WindowStabilityCell",
]

#: The §9 record-schema version for the stability record - distinct from the
#: engine-logic version, the method version, and the sidecar's container format version.
#: Bump it when the serialized meaning of a stability record changes (a container
#: concern; it is **not** folded into ``walk_forward_stability_id`` - §10, prior-phase
#: discipline).
STABILITY_RESULT_FORMAT_VERSION = "stability-result/1"

#: The only boundary a v1 stability record accepts. It documents that the *underlying
#: factor portfolios* (beneath the source walk-forward) were PIT walks; the stability
#: *output* is ex-post and is not a PIT value (WS-6). The engine carries the source
#: walk-forward's ``boundary_kind`` through unchanged.
BOUNDARY_PIT = "pit"

#: The minimum number of realized-adjacent transitions an aggregate turnover profile
#: must have to be defensible (§12, WS-3). Below this floor the record still seals, but
#: its ``stability_status`` is ``UNDEFINED`` (``INSUFFICIENT_TRANSITIONS``): a single
#: turnover value carries no cross-transition structure. Folded into
#: ``walk_forward_stability_id`` (§10), so a change to it is a distinguishable record.
MIN_STABILITY_TRANSITIONS = 2


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


def _cell(raw: dict[str, object], key: str) -> StabilityStat:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return StabilityStat.from_dict(value)


def _excluded_reason(raw: dict[str, object]) -> StabilityExcludedReason:
    """Decode a required exclusion ``reason`` string (fail closed)."""
    reason_raw = raw.get("reason")
    if not isinstance(reason_raw, str):
        raise ValueError("ExcludedWindow.reason must be a string")
    try:
        return StabilityExcludedReason(reason_raw)
    except ValueError as exc:
        raise ValueError(f"unknown StabilityExcludedReason {reason_raw!r}") from exc


@dataclass(frozen=True, slots=True)
class WindowStabilityCell:
    """One REALIZED window's weight-vector stability metrics (§9, WS-2/WS-4).

    ``index`` is the source window's index; ``gross_leverage = Σ|w|``,
    ``concentration_hhi = Σw²``, and ``max_abs_weight = max|w|`` are canonical decimal
    strings computed once from the source's KNOWN weight vector (consumed verbatim,
    never re-solved, WS-4); ``effective_breadth = 1/HHI`` is an UNDEFINED-preserving
    cell (derivable, so excluded from the record hash's cell payload);
    ``turnover_from_prev = ½Σ|Δw|`` against the immediately-preceding REALIZED window
    is an UNDEFINED-preserving cell (UNDEFINED ``NO_PRIOR_REALIZED_WINDOW`` when there
    is no adjacent predecessor).
    """

    index: int
    gross_leverage: str
    concentration_hhi: str
    effective_breadth: StabilityStat
    max_abs_weight: str
    turnover_from_prev: StabilityStat

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "gross_leverage": self.gross_leverage,
            "concentration_hhi": self.concentration_hhi,
            "effective_breadth": self.effective_breadth.to_dict(),
            "max_abs_weight": self.max_abs_weight,
            "turnover_from_prev": self.turnover_from_prev.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> WindowStabilityCell:
        return cls(
            index=_req_int(raw, "index"),
            gross_leverage=_req_str(raw, "gross_leverage"),
            concentration_hhi=_req_str(raw, "concentration_hhi"),
            effective_breadth=_cell(raw, "effective_breadth"),
            max_abs_weight=_req_str(raw, "max_abs_weight"),
            turnover_from_prev=_cell(raw, "turnover_from_prev"),
        )


@dataclass(frozen=True, slots=True)
class ExcludedWindow:
    """One window excluded from the stability family, with its reason (§9, WS-3).

    A window the source sealed UNDEFINED (``WINDOW_UNDEFINED``): it carries no KNOWN
    weight vector, so it yields no stability cell. It is recorded here, never imputed
    and never coerced to a number (WS-3).
    """

    index: int
    reason: StabilityExcludedReason

    def to_dict(self) -> dict[str, object]:
        return {"index": self.index, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ExcludedWindow:
        return cls(index=_req_int(raw, "index"), reason=_excluded_reason(raw))


@dataclass(frozen=True, slots=True)
class StabilitySummary:
    """The aggregate turnover / concentration statistics + roll-up status (§9, WS-3).

    Eight UNDEFINED-preserving :class:`~quantforge.stability.model.StabilityStat` cells:
    the turnover family over the realized-adjacent transitions (``mean_turnover``,
    population ``turnover_dispersion``, ``max_turnover``, ``min_turnover`` - all
    UNDEFINED ``NO_TRANSITIONS`` when there are none) and the concentration family over
    the REALIZED windows (``mean_gross_leverage``, ``max_gross_leverage``,
    ``mean_concentration_hhi``, ``mean_effective_breadth``) - plus ``stability_status``
    (``STABLE`` when the transitions meet :data:`MIN_STABILITY_TRANSITIONS`, else
    ``UNDEFINED`` with ``status_reason``). The status reflects the *turnover* evidence;
    the per-window cells and the aggregates still seal below the floor (WS-3).
    """

    mean_turnover: StabilityStat
    turnover_dispersion: StabilityStat
    max_turnover: StabilityStat
    min_turnover: StabilityStat
    mean_gross_leverage: StabilityStat
    max_gross_leverage: StabilityStat
    mean_concentration_hhi: StabilityStat
    mean_effective_breadth: StabilityStat
    stability_status: StabilityStatus
    status_reason: StabilityUndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mean_turnover": self.mean_turnover.to_dict(),
            "turnover_dispersion": self.turnover_dispersion.to_dict(),
            "max_turnover": self.max_turnover.to_dict(),
            "min_turnover": self.min_turnover.to_dict(),
            "mean_gross_leverage": self.mean_gross_leverage.to_dict(),
            "max_gross_leverage": self.max_gross_leverage.to_dict(),
            "mean_concentration_hhi": self.mean_concentration_hhi.to_dict(),
            "mean_effective_breadth": self.mean_effective_breadth.to_dict(),
            "stability_status": self.stability_status.value,
        }
        if self.status_reason is not None:
            payload["status_reason"] = self.status_reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StabilitySummary:
        status_raw = _req_str(raw, "stability_status")
        try:
            status = StabilityStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown stability_status {status_raw!r}") from exc
        reason_raw = raw.get("status_reason")
        reason: StabilityUndefinedReason | None
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            try:
                reason = StabilityUndefinedReason(reason_raw)
            except ValueError as exc:
                raise ValueError(
                    f"unknown StabilityUndefinedReason {reason_raw!r}"
                ) from exc
        else:
            raise ValueError(
                "StabilitySummary.status_reason must be a string or absent"
            )
        return cls(
            mean_turnover=_cell(raw, "mean_turnover"),
            turnover_dispersion=_cell(raw, "turnover_dispersion"),
            max_turnover=_cell(raw, "max_turnover"),
            min_turnover=_cell(raw, "min_turnover"),
            mean_gross_leverage=_cell(raw, "mean_gross_leverage"),
            max_gross_leverage=_cell(raw, "max_gross_leverage"),
            mean_concentration_hhi=_cell(raw, "mean_concentration_hhi"),
            mean_effective_breadth=_cell(raw, "mean_effective_breadth"),
            stability_status=status,
            status_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class StabilityCoverage:
    """The audit coverage block - counts of windows, realized, excluded, transitions
    (§9).

    Beyond the descriptor folded into ``result_hash`` it is a pure function of the
    sealed window / excluded lists (a reader's convenience, not an independent input):
    the source walk held ``n_windows`` windows, of which ``n_realized`` yielded a
    stability cell (the family) and ``n_excluded`` were excluded, with ``n_realized +
    n_excluded == n_windows`` (WS-2); ``n_transitions`` is the count of those realized
    windows with a KNOWN ``turnover_from_prev`` (a realized-adjacent predecessor).
    """

    n_windows: int
    n_realized: int
    n_excluded: int
    n_transitions: int

    def to_dict(self) -> dict[str, object]:
        return {
            "n_windows": self.n_windows,
            "n_realized": self.n_realized,
            "n_excluded": self.n_excluded,
            "n_transitions": self.n_transitions,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StabilityCoverage:
        return cls(
            n_windows=_req_int(raw, "n_windows"),
            n_realized=_req_int(raw, "n_realized"),
            n_excluded=_req_int(raw, "n_excluded"),
            n_transitions=_req_int(raw, "n_transitions"),
        )


@dataclass(frozen=True, slots=True)
class WalkForwardStability:
    """A sealed, content-addressed walk-forward-stability record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`walk_forward_stability_id`;
    deterministic :meth:`to_dict`), so it persists write-once to the shared research
    sidecar with no new store. It pins the source walk-forward by ``(id, result_hash)``,
    holds the per-REALIZED-window stability cells, the excluded windows, the aggregate
    summary, and the coverage block, and seals the computed answer into ``result_hash``.
    It is **not** a ``Pit*`` type and exposes no as-of accessor (WS-6).
    """

    stability_engine_version_id: str
    stability_spec: dict[str, object]
    source_ref: tuple[str, str]
    boundary_kind: str
    windows: tuple[WindowStabilityCell, ...]
    excluded: tuple[ExcludedWindow, ...]
    summary: StabilitySummary
    coverage: StabilityCoverage
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def walk_forward_stability_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from
        stored state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the
        embedded request), the source walk id + ``result_hash``, the
        ``MIN_STABILITY_TRANSITIONS`` floor, and the sealed ``result_hash`` over the
        answer.
        """
        spec = self.stability_spec
        return _stability_id(
            stability_engine_version_id=self.stability_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_walk_forward_id=_spec_str(spec, "source_walk_forward_id"),
            source_result_hash=self.source_ref[1],
            min_stability_transitions=MIN_STABILITY_TRANSITIONS,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`walk_forward_stability_id` - the :class:`ResearchRecord`
        id."""
        return self.walk_forward_stability_id

    @property
    def source_walk_forward_id(self) -> str:
        """The referenced source walk-forward's ``research_result_id``."""
        return self.source_ref[0]

    @property
    def source_result_hash(self) -> str:
        """The referenced source walk-forward's ``result_hash`` (the transitive pin)."""
        return self.source_ref[1]

    @property
    def stability_status(self) -> StabilityStatus:
        """The roll-up stability status (a convenience alias of the summary's)."""
        return self.summary.stability_status

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        stability_engine_version_id: str,
        stability_spec: dict[str, object],
        source_ref: tuple[str, str],
        boundary_kind: str,
        windows: tuple[WindowStabilityCell, ...],
        excluded: tuple[ExcludedWindow, ...],
        summary: StabilitySummary,
        coverage: StabilityCoverage,
        method_version: str = STABILITY_METHOD_VERSION,
    ) -> WalkForwardStability:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the coverage descriptor, the per-window stability cells, the excluded
        cells, then the aggregate summary) into ``result_hash`` via
        :func:`~quantforge.stability.identity.walk_forward_stability_result_hash`, so
        identity is a pure function of the computed answer and never has to be
        supplied by the caller. The coverage block is a function of those cells and
        only its counts are folded, in the descriptor.
        """
        rhash = _result_hash(
            _output_cells(
                windows=windows,
                excluded=excluded,
                summary=summary,
                coverage=coverage,
            )
        )
        return cls(
            stability_engine_version_id=stability_engine_version_id,
            stability_spec=dict(stability_spec),
            source_ref=source_ref,
            boundary_kind=boundary_kind,
            windows=windows,
            excluded=excluded,
            summary=summary,
            coverage=coverage,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "walk_forward_stability_id": self.walk_forward_stability_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "stability_engine_version_id": self.stability_engine_version_id,
            "stability_spec": dict(self.stability_spec),
            "source_ref": {
                "source_walk_forward_id": self.source_ref[0],
                "source_result_hash": self.source_ref[1],
            },
            "boundary_kind": self.boundary_kind,
            "windows": [cell.to_dict() for cell in self.windows],
            "excluded": [cell.to_dict() for cell in self.excluded],
            "summary": self.summary.to_dict(),
            "coverage": self.coverage.to_dict(),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> WalkForwardStability:
        """Reconstruct a sealed stability record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, WalkForwardStability.from_dict)`` is a
        first-class typed object. ``walk_forward_stability_id`` / ``research_result_id``
        are derived aliases re-emitted by their properties (never read from state),
        every nested cell round-trips through its own fail-closed ``from_dict``, and the
        block order is preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes
        and the same ``result_hash``, introducing no drift.
        """
        source = _req_dict(raw, "source_ref")
        return cls(
            stability_engine_version_id=_req_str(raw, "stability_engine_version_id"),
            stability_spec=dict(_req_dict(raw, "stability_spec")),
            source_ref=(
                _req_str(source, "source_walk_forward_id"),
                _req_str(source, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            windows=tuple(
                WindowStabilityCell.from_dict(_as_dict(item, "windows"))
                for item in _req_list(raw, "windows")
            ),
            excluded=tuple(
                ExcludedWindow.from_dict(_as_dict(item, "excluded"))
                for item in _req_list(raw, "excluded")
            ),
            summary=StabilitySummary.from_dict(_req_dict(raw, "summary")),
            coverage=StabilityCoverage.from_dict(_req_dict(raw, "coverage")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    windows: tuple[WindowStabilityCell, ...],
    excluded: tuple[ExcludedWindow, ...],
    summary: StabilitySummary,
    coverage: StabilityCoverage,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the coverage descriptor (window / realized /
    excluded / transition counts), then the per-window stability cells (``index`` +
    gross leverage + concentration + max-abs weight + turnover) in source window order,
    then the excluded
    cells (``index`` + reason), then the aggregate summary block - each tagged by its
    block so two structurally different records can never collide. The derivable
    per-window ``effective_breadth`` is omitted (``concentration_hhi`` folds it); the
    ids, request, and floor are folded into ``walk_forward_stability_id`` through the
    request + reference instead. Sensitive to every computed metric and aggregate.
    """
    cells: list[dict[str, object]] = [
        {
            "block": "coverage_descriptor",
            "n_windows": coverage.n_windows,
            "n_realized": coverage.n_realized,
            "n_excluded": coverage.n_excluded,
            "n_transitions": coverage.n_transitions,
        }
    ]
    for cell in windows:
        cells.append(
            {
                "block": "window",
                "index": cell.index,
                "gross_leverage": cell.gross_leverage,
                "concentration_hhi": cell.concentration_hhi,
                "max_abs_weight": cell.max_abs_weight,
                "turnover_from_prev": cell.turnover_from_prev.to_dict(),
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
    cells.append({"block": "summary", **summary.to_dict()})
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"stability_spec.{key} must be a string")
    return value
