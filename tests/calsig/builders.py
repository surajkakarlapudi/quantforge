"""Offline, obviously-synthetic fixtures for Phase 29 calibration-significance tests.

Phase 29 is a pure consumer of exactly **one** already-sealed
:class:`~quantforge.calibration.result.RiskForecastCalibration`: the engine reads only
its ``calibration_status``, its sealed aggregate ``mean_variance_ratio`` /
``variance_ratio_dispersion`` cells, its ``coverage.n_calibratable`` and its
``boundary_kind`` - never the walk-forward / optimization / risk-model / factor chain
beneath it, and never the per-window ratios (CS-4). So - like the MinTRL and calibration
builders - these builders synthesize a ``RiskForecastCalibration`` **directly** with a
hand-chosen aggregate summary, seal it, and persist it to the shared sidecar. Every id /
hash the synthetic record pins is an obviously-fictional placeholder (Principle 8):
Phase 29 pins the calibration by ``(id, result_hash)`` and never resolves anything
beneath it, so the placeholders are load-bearing for identity only, never dereferenced.

The helpers cover the defensibility branches (CS-2/CS-3): a CALIBRATED source with a
chosen mean + dispersion (:func:`calibrated`), a CALIBRATED source with zero dispersion
(:func:`zero_dispersion`), an UNDEFINED (below-floor) source (:func:`undefined_source`),
and - the defensive guard - a CALIBRATED source whose aggregate mean cell is UNDEFINED
(:func:`calibrated_mean_undefined`).
"""

from __future__ import annotations

from pathlib import Path

from quantforge.calibration.model import (
    CalibrationStat,
    CalibrationStatus,
    CalibrationUndefinedReason,
)
from quantforge.calibration.result import (
    CalibrationCoverage,
    CalibrationSummary,
    RiskForecastCalibration,
)
from quantforge.calsig.engine import CalibrationSignificanceEngine
from quantforge.calsig.spec import CalibrationSignificanceSpecification
from quantforge.workspace import Workspace

__all__ = [
    "calibrated",
    "calibrated_mean_undefined",
    "calsig_engine",
    "make_calibration",
    "make_spec",
    "undefined_source",
    "workspace",
    "zero_dispersion",
]


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def calsig_engine(ws: Workspace) -> CalibrationSignificanceEngine:
    """The workspace's Phase 29 engine, narrowed from the ``object`` property."""
    engine = ws.calibration_significance_engine
    assert isinstance(engine, CalibrationSignificanceEngine)
    return engine


def _inert_known() -> CalibrationStat:
    """A KNOWN aggregate cell Phase 29 never reads (bias / frequency / min / max)."""
    return CalibrationStat.known("0")


def calibrated(*, mean: str, dispersion: str) -> CalibrationSummary:
    """A CALIBRATED summary with a chosen KNOWN mean + dispersion (the tested pair)."""
    return CalibrationSummary(
        mean_variance_ratio=CalibrationStat.known(mean),
        aggregate_bias=_inert_known(),
        variance_ratio_dispersion=CalibrationStat.known(dispersion),
        underforecast_frequency=_inert_known(),
        max_variance_ratio=_inert_known(),
        min_variance_ratio=_inert_known(),
        calibration_status=CalibrationStatus.CALIBRATED,
    )


def zero_dispersion(*, mean: str) -> CalibrationSummary:
    """A CALIBRATED summary whose per-window ratios have zero dispersion."""
    return calibrated(mean=mean, dispersion="0")


def undefined_source() -> CalibrationSummary:
    """An UNDEFINED summary (below the Phase-26 floor): every aggregate UNDEFINED."""
    reason = CalibrationUndefinedReason.INSUFFICIENT_CALIBRATABLE_WINDOWS
    undefined = CalibrationStat.undefined(reason)
    return CalibrationSummary(
        mean_variance_ratio=undefined,
        aggregate_bias=undefined,
        variance_ratio_dispersion=undefined,
        underforecast_frequency=undefined,
        max_variance_ratio=undefined,
        min_variance_ratio=undefined,
        calibration_status=CalibrationStatus.UNDEFINED,
        status_reason=reason,
    )


def calibrated_mean_undefined() -> CalibrationSummary:
    """Defensive: a CALIBRATED summary whose mean cell is UNDEFINED (unreachable)."""
    reason = CalibrationUndefinedReason.NO_CALIBRATABLE_WINDOWS
    return CalibrationSummary(
        mean_variance_ratio=CalibrationStat.undefined(reason),
        aggregate_bias=_inert_known(),
        variance_ratio_dispersion=CalibrationStat.known("0.1"),
        underforecast_frequency=_inert_known(),
        max_variance_ratio=_inert_known(),
        min_variance_ratio=_inert_known(),
        calibration_status=CalibrationStatus.CALIBRATED,
    )


def make_calibration(
    ws: Workspace,
    *,
    summary: CalibrationSummary,
    n_calibratable: int = 4,
    name: str = "synthetic-calibration",
    engine_version_id: str = "sha256:synthetic-calibration-engine",
) -> RiskForecastCalibration:
    """Seal a synthetic :class:`RiskForecastCalibration` and persist it to the sidecar.

    ``summary`` is the sealed aggregate block Phase 29 reads; ``n_calibratable`` the
    window count ``K`` it reads from coverage. Returns the sealed record (its
    ``research_result_id`` is what a Phase 29 request points at). Every reference the
    record pins is a fictional placeholder that Phase 29 never dereferences.
    """
    coverage = CalibrationCoverage(
        n_windows=n_calibratable,
        n_calibratable=n_calibratable,
        n_excluded=0,
    )
    calibration = RiskForecastCalibration.seal(
        calibration_engine_version_id=engine_version_id,
        calibration_spec={
            "spec_version": "calibration/1",
            "name": name,
            "source_walk_forward_id": "sha256:walk",
        },
        source_ref=("sha256:walk", "sha256:walk-hash"),
        boundary_kind="pit",
        windows=(),
        excluded=(),
        summary=summary,
        coverage=coverage,
    )
    ws.research_result_store.write(calibration)
    return calibration


def make_spec(
    source_id: str,
    *,
    name: str = "phase29-calsig",
) -> CalibrationSignificanceSpecification:
    """A significance request over one sealed calibration id."""
    return CalibrationSignificanceSpecification(
        name=name, source_calibration_id=source_id
    )
