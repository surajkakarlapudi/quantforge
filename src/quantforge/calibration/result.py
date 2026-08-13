"""The sealed, content-addressed risk-forecast-calibration record (§9, §10).

A completed calibration is a :class:`RiskForecastCalibration`: the engine version, the
full declarative request, the ``(source_walk_forward_id, source_result_hash)`` reference
to the one sealed walk-forward it consumed, per **calibratable** window the
forecast-vs-outcome ratios (in the source's window order), the **excluded** windows
(each a window the source sealed non-calibratable, with its reason), the aggregate
calibration :class:`CalibrationSummary` (mean ratio, pooled bias, dispersion,
under-forecast frequency, min / max, and the roll-up status), a non-hashed coverage
block, and the sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``risk_forecast_calibration_id`` (a single id, mirroring
``multiple_comparison_id``) and ``to_dict`` is deterministic - so it persists write-once
to the shared Phase 8 sidecar with **no new store**. It stores only a *pointer* to the
source walk-forward, never a copy of its windows (the pointer-only discipline of
:class:`~quantforge.multiplicity.result.MultipleComparisonCorrection`): the source
already lives in the same sidecar, so this record stays a thin, reproducible view over
it.

**Ex-post, not PIT (RC-6).** A calibration over an already-ex-post walk-forward is
itself an ex-post research statistic, not a forward-usable PIT value.
:class:`RiskForecastCalibration` is deliberately **not** a ``Pit*`` type and exposes
**no** as-of accessor. ``boundary_kind = "pit"`` documents only that the *underlying
factor portfolios* were PIT walks - the convention where the label describes the
input side, not the ex-post output. It is not a ``BacktestResult`` and performs no
execution.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~RiskForecastCalibration.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.calibration.identity import (
    risk_forecast_calibration_id as _calibration_id,
)
from quantforge.calibration.identity import (
    risk_forecast_calibration_result_hash as _result_hash,
)
from quantforge.calibration.model import (
    CalibrationExcludedReason,
    CalibrationStat,
    CalibrationStatus,
    CalibrationUndefinedReason,
)
from quantforge.calibration.version import CALIBRATION_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "CALIBRATION_RESULT_FORMAT_VERSION",
    "MIN_CALIBRATABLE_WINDOWS",
    "CalibrationCoverage",
    "CalibrationSummary",
    "ExcludedWindow",
    "RiskForecastCalibration",
    "WindowCalibrationCell",
]

#: The §9 record-schema version for the calibration record - distinct from the
#: engine-logic version, the method version, and the sidecar's container format
#: version. Bump it when the serialized meaning of a calibration record changes (a
#: container concern; it is **not** folded into ``risk_forecast_calibration_id`` -
#: §10, prior-phase discipline).
CALIBRATION_RESULT_FORMAT_VERSION = "calibration-result/1"

#: The only boundary a v1 calibration record accepts. It documents that the *underlying
#: factor portfolios* (beneath the source walk-forward) were PIT walks; the calibration
#: *output* is ex-post and is not a PIT value (RC-6). The engine carries the source
#: walk-forward's ``boundary_kind`` through unchanged.
BOUNDARY_PIT = "pit"

#: The minimum number of calibratable windows an aggregate calibration must have to
#: be defensible (§12.9, RC-3). Below this floor the record still seals, but its
#: ``calibration_status`` is ``UNDEFINED`` (``INSUFFICIENT_CALIBRATABLE_WINDOWS``):
#: a single forecast-vs-outcome ratio carries no cross-window structure. Folded into
#: ``risk_forecast_calibration_id`` (§10), so a change to it is a distinguishable
#: record.
MIN_CALIBRATABLE_WINDOWS = 2


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


def _excluded_reason(raw: dict[str, object]) -> CalibrationExcludedReason:
    """Decode a required exclusion ``reason`` string (fail closed)."""
    reason_raw = raw.get("reason")
    if not isinstance(reason_raw, str):
        raise ValueError("ExcludedWindow.reason must be a string")
    try:
        return CalibrationExcludedReason(reason_raw)
    except ValueError as exc:
        raise ValueError(f"unknown CalibrationExcludedReason {reason_raw!r}") from exc


@dataclass(frozen=True, slots=True)
class WindowCalibrationCell:
    """One calibratable window's forecast-vs-outcome ratios (§9, RC-2/RC-4).

    ``index`` is the source window's index; ``predicted_variance`` /
    ``realized_variance`` the source's KNOWN in-sample ``wᵀΣw`` and out-of-sample
    variance, carried verbatim (never recomputed, RC-4). ``predicted_volatility`` /
    ``realized_volatility`` are their ``√`` (carried for readability, derivable, and so
    excluded from the record hash's cell payload); ``variance_ratio =
    realized/predicted`` and ``volatility_ratio = realized_volatility /
    predicted_volatility`` are the risk-model bias on the two scales. All are canonical
    decimal strings.
    """

    index: int
    predicted_variance: str
    realized_variance: str
    predicted_volatility: str
    realized_volatility: str
    variance_ratio: str
    volatility_ratio: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "predicted_variance": self.predicted_variance,
            "realized_variance": self.realized_variance,
            "predicted_volatility": self.predicted_volatility,
            "realized_volatility": self.realized_volatility,
            "variance_ratio": self.variance_ratio,
            "volatility_ratio": self.volatility_ratio,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> WindowCalibrationCell:
        return cls(
            index=_req_int(raw, "index"),
            predicted_variance=_req_str(raw, "predicted_variance"),
            realized_variance=_req_str(raw, "realized_variance"),
            predicted_volatility=_req_str(raw, "predicted_volatility"),
            realized_volatility=_req_str(raw, "realized_volatility"),
            variance_ratio=_req_str(raw, "variance_ratio"),
            volatility_ratio=_req_str(raw, "volatility_ratio"),
        )


@dataclass(frozen=True, slots=True)
class ExcludedWindow:
    """One window excluded from the calibratable family, with its reason (§9, RC-3).

    A window the source sealed non-calibratable: the whole window UNDEFINED
    (``WINDOW_UNDEFINED``); a REALIZED window whose ``realized_variance`` is
    UNDEFINED because its test span had a single period (``SINGLE_VALID_PERIOD``);
    or - defensive, structurally unreachable - a non-positive or UNDEFINED
    ``predicted_variance`` (``ZERO_PREDICTED_VARIANCE`` /
    ``PREDICTED_VARIANCE_UNDEFINED``). It carries no ratio: it is recorded here,
    never imputed and never coerced to a number (RC-3).
    """

    index: int
    reason: CalibrationExcludedReason

    def to_dict(self) -> dict[str, object]:
        return {"index": self.index, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ExcludedWindow:
        return cls(index=_req_int(raw, "index"), reason=_excluded_reason(raw))


@dataclass(frozen=True, slots=True)
class CalibrationSummary:
    """The aggregate calibration statistics + the roll-up status (§9, RC-3/RC-5).

    Six UNDEFINED-preserving :class:`~quantforge.calibration.model.CalibrationStat`
    cells over the calibratable family - ``mean_variance_ratio``, the pooled
    ``aggregate_bias = Σrealized / Σpredicted`` (``> 1`` ⇒ the risk model systematically
    **under-forecasts** risk, ``< 1`` ⇒ over-forecasts), ``variance_ratio_dispersion``
    (population std of the per-window ratios), ``underforecast_frequency``,
    ``max_variance_ratio`` / ``min_variance_ratio`` - plus ``calibration_status``
    (``CALIBRATED`` when the family meets :data:`MIN_CALIBRATABLE_WINDOWS`, else
    ``UNDEFINED`` with ``status_reason``). With no calibratable windows every cell is
    UNDEFINED (``NO_CALIBRATABLE_WINDOWS``); the record still seals (RC-3).
    """

    mean_variance_ratio: CalibrationStat
    aggregate_bias: CalibrationStat
    variance_ratio_dispersion: CalibrationStat
    underforecast_frequency: CalibrationStat
    max_variance_ratio: CalibrationStat
    min_variance_ratio: CalibrationStat
    calibration_status: CalibrationStatus
    status_reason: CalibrationUndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mean_variance_ratio": self.mean_variance_ratio.to_dict(),
            "aggregate_bias": self.aggregate_bias.to_dict(),
            "variance_ratio_dispersion": self.variance_ratio_dispersion.to_dict(),
            "underforecast_frequency": self.underforecast_frequency.to_dict(),
            "max_variance_ratio": self.max_variance_ratio.to_dict(),
            "min_variance_ratio": self.min_variance_ratio.to_dict(),
            "calibration_status": self.calibration_status.value,
        }
        if self.status_reason is not None:
            payload["status_reason"] = self.status_reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CalibrationSummary:
        def _cell(key: str) -> CalibrationStat:
            value = raw.get(key)
            if not isinstance(value, dict):
                raise ValueError(f"CalibrationSummary.{key} must be an object")
            return CalibrationStat.from_dict(value)

        status_raw = _req_str(raw, "calibration_status")
        try:
            status = CalibrationStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown calibration_status {status_raw!r}") from exc
        reason_raw = raw.get("status_reason")
        reason: CalibrationUndefinedReason | None
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            try:
                reason = CalibrationUndefinedReason(reason_raw)
            except ValueError as exc:
                raise ValueError(
                    f"unknown CalibrationUndefinedReason {reason_raw!r}"
                ) from exc
        else:
            raise ValueError(
                "CalibrationSummary.status_reason must be a string or absent"
            )
        return cls(
            mean_variance_ratio=_cell("mean_variance_ratio"),
            aggregate_bias=_cell("aggregate_bias"),
            variance_ratio_dispersion=_cell("variance_ratio_dispersion"),
            underforecast_frequency=_cell("underforecast_frequency"),
            max_variance_ratio=_cell("max_variance_ratio"),
            min_variance_ratio=_cell("min_variance_ratio"),
            calibration_status=status,
            status_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class CalibrationCoverage:
    """The audit coverage block - counts of windows, calibratable, and excluded (§9).

    Excluded from ``result_hash`` beyond the descriptor (a pure function of the sealed
    window / excluded lists - a reader's convenience, not an independent input): the
    source walk held ``n_windows`` windows, of which ``n_calibratable`` yielded a
    forecast-vs-outcome ratio (the family) and ``n_excluded`` were excluded, with
    ``n_calibratable + n_excluded == n_windows`` (RC-2).
    """

    n_windows: int
    n_calibratable: int
    n_excluded: int

    def to_dict(self) -> dict[str, object]:
        return {
            "n_windows": self.n_windows,
            "n_calibratable": self.n_calibratable,
            "n_excluded": self.n_excluded,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CalibrationCoverage:
        return cls(
            n_windows=_req_int(raw, "n_windows"),
            n_calibratable=_req_int(raw, "n_calibratable"),
            n_excluded=_req_int(raw, "n_excluded"),
        )


@dataclass(frozen=True, slots=True)
class RiskForecastCalibration:
    """A sealed, content-addressed risk-forecast-calibration record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`risk_forecast_calibration_id`;
    deterministic :meth:`to_dict`), so it persists write-once to the shared research
    sidecar with no new store. It pins the source walk-forward by ``(id, result_hash)``,
    holds the per-calibratable-window ratios, the excluded windows, the aggregate
    summary, and the coverage block, and seals the computed answer into ``result_hash``.
    It is **not** a ``Pit*`` type and exposes no as-of accessor (RC-6).
    """

    calibration_engine_version_id: str
    calibration_spec: dict[str, object]
    source_ref: tuple[str, str]
    boundary_kind: str
    windows: tuple[WindowCalibrationCell, ...]
    excluded: tuple[ExcludedWindow, ...]
    summary: CalibrationSummary
    coverage: CalibrationCoverage
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def risk_forecast_calibration_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the source walk id + ``result_hash``, the
        ``MIN_CALIBRATABLE_WINDOWS`` floor, and the sealed ``result_hash`` over the
        answer.
        """
        spec = self.calibration_spec
        return _calibration_id(
            calibration_engine_version_id=self.calibration_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_walk_forward_id=_spec_str(spec, "source_walk_forward_id"),
            source_result_hash=self.source_ref[1],
            min_calibratable_windows=MIN_CALIBRATABLE_WINDOWS,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`risk_forecast_calibration_id` - the :class:`ResearchRecord`
        id."""
        return self.risk_forecast_calibration_id

    @property
    def source_walk_forward_id(self) -> str:
        """The referenced source walk-forward's ``research_result_id``."""
        return self.source_ref[0]

    @property
    def source_result_hash(self) -> str:
        """The referenced source walk-forward's ``result_hash`` (the transitive pin)."""
        return self.source_ref[1]

    @property
    def calibration_status(self) -> CalibrationStatus:
        """The roll-up calibration status (a convenience alias of the summary's)."""
        return self.summary.calibration_status

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        calibration_engine_version_id: str,
        calibration_spec: dict[str, object],
        source_ref: tuple[str, str],
        boundary_kind: str,
        windows: tuple[WindowCalibrationCell, ...],
        excluded: tuple[ExcludedWindow, ...],
        summary: CalibrationSummary,
        coverage: CalibrationCoverage,
        method_version: str = CALIBRATION_METHOD_VERSION,
    ) -> RiskForecastCalibration:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the coverage descriptor, the calibratable-window cells, the excluded
        cells, then the aggregate summary) into ``result_hash`` via
        :func:`~quantforge.calibration.identity.risk_forecast_calibration_result_hash`,
        so identity is a pure function of the computed answer and never has to be
        supplied by the caller. The coverage block is a function of those cells and only
        its counts are folded, in the descriptor.
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
            calibration_engine_version_id=calibration_engine_version_id,
            calibration_spec=dict(calibration_spec),
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
            "risk_forecast_calibration_id": self.risk_forecast_calibration_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "calibration_engine_version_id": self.calibration_engine_version_id,
            "calibration_spec": dict(self.calibration_spec),
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
    def from_dict(cls, raw: dict[str, object]) -> RiskForecastCalibration:
        """Reconstruct a sealed calibration record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, RiskForecastCalibration.from_dict)`` is a
        first-class typed object. ``risk_forecast_calibration_id`` /
        ``research_result_id`` are derived aliases re-emitted by their properties (never
        read from state), every nested cell round-trips through its own fail-closed
        ``from_dict``, and the block order is preserved - so ``from_dict(to_dict(r))``
        re-emits identical bytes and the same ``result_hash``, introducing no drift.
        """
        source = _req_dict(raw, "source_ref")
        return cls(
            calibration_engine_version_id=_req_str(
                raw, "calibration_engine_version_id"
            ),
            calibration_spec=dict(_req_dict(raw, "calibration_spec")),
            source_ref=(
                _req_str(source, "source_walk_forward_id"),
                _req_str(source, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            windows=tuple(
                WindowCalibrationCell.from_dict(_as_dict(item, "windows"))
                for item in _req_list(raw, "windows")
            ),
            excluded=tuple(
                ExcludedWindow.from_dict(_as_dict(item, "excluded"))
                for item in _req_list(raw, "excluded")
            ),
            summary=CalibrationSummary.from_dict(_req_dict(raw, "summary")),
            coverage=CalibrationCoverage.from_dict(_req_dict(raw, "coverage")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    windows: tuple[WindowCalibrationCell, ...],
    excluded: tuple[ExcludedWindow, ...],
    summary: CalibrationSummary,
    coverage: CalibrationCoverage,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the coverage descriptor (window / calibratable /
    excluded counts), then the calibratable-window cells (``index`` + the two
    variances + the two ratios) in source window order, then the excluded cells
    (``index`` + reason), then the aggregate summary block - each tagged by its
    block so two structurally different records can never collide. The derivable
    per-window volatilities are omitted (the variances fold them); the ids, request,
    and floor are folded into ``risk_forecast_calibration_id`` through the request +
    reference instead. Sensitive to every computed ratio and aggregate.
    """
    cells: list[dict[str, object]] = [
        {
            "block": "coverage_descriptor",
            "n_windows": coverage.n_windows,
            "n_calibratable": coverage.n_calibratable,
            "n_excluded": coverage.n_excluded,
        }
    ]
    for cell in windows:
        cells.append(
            {
                "block": "window",
                "index": cell.index,
                "predicted_variance": cell.predicted_variance,
                "realized_variance": cell.realized_variance,
                "variance_ratio": cell.variance_ratio,
                "volatility_ratio": cell.volatility_ratio,
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
        raise ValueError(f"calibration_spec.{key} must be a string")
    return value
