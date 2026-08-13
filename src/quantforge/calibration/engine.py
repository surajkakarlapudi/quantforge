"""The risk-forecast-calibration orchestration engine (§6, §11, §12, RC-1..RC-6).

:class:`RiskForecastCalibrationEngine` sits strictly **above** Phase 22: it is a
pure consumer that turns a declarative
:class:`~quantforge.calibration.spec.RiskForecastCalibrationSpecification` into a
sealed :class:`~quantforge.calibration.result.RiskForecastCalibration` by
*resolving* the one already-sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` the request names,
*verifying* it, *classifying* each of its windows into the calibratable family (or a
first-class exclusion, never imputed), *calibrating* that family
(:mod:`quantforge.calibration.compute`), and sealing the answer. It introduces no
new data-resolution logic, no new PIT surface, and no new store; it composes the
pinned pure :func:`~quantforge.calibration.compute.calibrate` under the version's
decimal context and persists write-once to the shared research sidecar (§6, §13,
§16).

The build (§6):

1. **Resolve** the ``source_walk_forward_id`` from the shared sidecar via
   ``store.read_as(id, WalkForwardEvaluation.from_dict)``. A missing id (or a
   payload that does not decode as a ``WalkForwardEvaluation``) is a consistency
   defect and raises
   :class:`~quantforge.calibration.errors.CalibrationConsistencyError` (fail closed,
   RC-1).
2. **Verify** the resolved record's ``research_result_id`` equals the requested id (the
   sidecar is otherwise inconsistent); raise on disagreement (RC-1).
3. **Classify the windows** (RC-3): walk the source's windows in their sealed order. A
   REALIZED window whose ``predicted_variance`` is KNOWN and strictly positive and whose
   ``realized_variance`` is KNOWN joins the calibratable family; every other window
   becomes a first-class :class:`~quantforge.calibration.result.ExcludedWindow` carrying
   its reason - never imputed, never coerced to a ratio.
4. **Calibrate** the family (:func:`~quantforge.calibration.compute.calibrate`)
   under the version's decimal context: the per-window variance / volatility ratios
   and the aggregate bias / dispersion / frequency statistics, with
   ``calibration_status`` defensible only when the family meets
   :data:`~quantforge.calibration.result.MIN_CALIBRATABLE_WINDOWS` (RC-3/RC-5). An
   empty family yields empty per-window cells and every aggregate UNDEFINED, never a
   divide-by-zero.
5. **Seal + persist**: seal a
   :class:`~quantforge.calibration.result.RiskForecastCalibration` (its ``result_hash``
   folds the answer, its id transitively pins the source walk's ``result_hash``) and
   persist it write-once to the same sidecar. Rebuilding an identical request is a
   byte-identical no-op; a differing payload under the same id fails closed via the
   store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.calibration.compute import CalibratableWindow, calibrate
from quantforge.calibration.errors import (
    CalibrationConfigurationError,
    CalibrationConsistencyError,
)
from quantforge.calibration.model import CalibrationExcludedReason
from quantforge.calibration.result import (
    MIN_CALIBRATABLE_WINDOWS,
    CalibrationCoverage,
    CalibrationSummary,
    ExcludedWindow,
    RiskForecastCalibration,
    WindowCalibrationCell,
)
from quantforge.calibration.spec import RiskForecastCalibrationSpecification
from quantforge.calibration.version import RiskForecastCalibrationEngineVersion
from quantforge.factors.store import ResearchResultStore
from quantforge.walkforward.model import StatStatus, WindowStatus
from quantforge.walkforward.result import WalkForwardEvaluation, WindowResult
from quantforge.workspace import Workspace

__all__ = ["RiskForecastCalibrationEngine"]

_ZERO = Decimal(0)


class RiskForecastCalibrationEngine:
    """Resolve, verify, classify, calibrate, and seal a calibration request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    walk-forward engine sealed its evaluations to - so a request calibrates exactly the
    walk-forward already present. The sidecar may be overridden (for tests). The engine
    pins its orchestration logic + statistical method + decimal context via
    :class:`~quantforge.calibration.version.RiskForecastCalibrationEngineVersion`, and
    computes every value under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: RiskForecastCalibrationEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else RiskForecastCalibrationEngineVersion()
        )

    @property
    def calibration_engine_version_id(self) -> str:
        """The orchestration + method + decimal-context version, folded into every
        id."""
        return self._version.risk_forecast_calibration_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the calibration resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def calibrate(
        self, spec: RiskForecastCalibrationSpecification
    ) -> RiskForecastCalibration:
        """Resolve, verify, classify, calibrate, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable
        sidecar re-resolves the same source walk-forward, recomputes byte-identical
        ratios and aggregates under the pinned decimal context, and seals a
        byte-identical
        :class:`~quantforge.calibration.result.RiskForecastCalibration` on any
        machine (whose sidecar write is an idempotent no-op). Fails closed on a
        missing / drifted reference or a non-``WalkForwardEvaluation`` record
        (RC-1); a window that is not calibratable is excluded from the family and
        recorded as a first-class
        :class:`~quantforge.calibration.result.ExcludedWindow` (RC-3), never raised.
        """
        if not isinstance(spec, RiskForecastCalibrationSpecification):
            raise CalibrationConfigurationError(
                "calibrate() requires a RiskForecastCalibrationSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the one source walk-forward (RC-1) --------------
        source = self._resolve_walk_forward(spec.source_walk_forward_id, store)

        # -- classify windows: calibratable family + exclusions (RC-3/RC-4) ---
        calibratable, excluded = self._classify_windows(source.windows)

        # -- calibrate the family (RC-4/RC-5) ---------------------------------
        computation = calibrate(
            calibratable,
            min_calibratable=MIN_CALIBRATABLE_WINDOWS,
            context=context,
        )
        windows = tuple(
            WindowCalibrationCell(
                index=ratio.index,
                predicted_variance=ratio.predicted_variance,
                realized_variance=ratio.realized_variance,
                predicted_volatility=ratio.predicted_volatility,
                realized_volatility=ratio.realized_volatility,
                variance_ratio=ratio.variance_ratio,
                volatility_ratio=ratio.volatility_ratio,
            )
            for ratio in computation.windows
        )
        summary = CalibrationSummary(
            mean_variance_ratio=computation.summary.mean_variance_ratio,
            aggregate_bias=computation.summary.aggregate_bias,
            variance_ratio_dispersion=computation.summary.variance_ratio_dispersion,
            underforecast_frequency=computation.summary.underforecast_frequency,
            max_variance_ratio=computation.summary.max_variance_ratio,
            min_variance_ratio=computation.summary.min_variance_ratio,
            calibration_status=computation.summary.calibration_status,
            status_reason=computation.summary.status_reason,
        )
        coverage = CalibrationCoverage(
            n_windows=len(source.windows),
            n_calibratable=len(calibratable),
            n_excluded=len(excluded),
        )

        # -- seal + persist ---------------------------------------------------
        calibration = RiskForecastCalibration.seal(
            calibration_engine_version_id=(
                self._version.risk_forecast_calibration_engine_version_id
            ),
            calibration_spec=spec.to_dict(),
            source_ref=(source.research_result_id, source.result_hash),
            # Carry the source walk-forward's boundary through unchanged: it documents
            # that the underlying factor portfolios were PIT walks. The calibration
            # output is ex-post and is not a PIT value (RC-6).
            boundary_kind=source.boundary_kind,
            windows=windows,
            excluded=excluded,
            summary=summary,
            coverage=coverage,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(calibration)
        return calibration

    # -- resolution & verification -------------------------------------------

    def _resolve_walk_forward(
        self, source_id: str, store: ResearchResultStore
    ) -> WalkForwardEvaluation:
        """Read + verify the one referenced source walk-forward (fail closed, RC-1)."""
        try:
            result = store.read_as(source_id, WalkForwardEvaluation.from_dict)
        except (KeyError, ValueError) as exc:
            raise CalibrationConsistencyError(
                f"source walk-forward {source_id!r} could not be decoded as a "
                "WalkForwardEvaluation; the referenced artifact is absent or not a "
                "walk-forward evaluation (fail closed)"
            ) from exc
        if result is None:
            raise CalibrationConsistencyError(
                f"source walk-forward {source_id!r} is not present in the research "
                "sidecar; cannot calibrate a walk-forward that was never sealed (fail "
                "closed)"
            )
        if result.research_result_id != source_id:
            raise CalibrationConsistencyError(
                f"source walk-forward {source_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    # -- window classification ------------------------------------------------

    def _classify_windows(
        self, windows: tuple[WindowResult, ...]
    ) -> tuple[tuple[CalibratableWindow, ...], tuple[ExcludedWindow, ...]]:
        """Split the source's windows into calibratable + exclusions (RC-3/RC-4).

        Walks the source walk-forward's windows in their sealed order. A REALIZED
        window whose ``predicted_variance`` is KNOWN and strictly positive and whose
        ``realized_variance`` is KNOWN joins the calibratable family (its two
        variances parsed once to ``Decimal`` for the ratio math, RC-4); every other
        window becomes a first-class
        :class:`~quantforge.calibration.result.ExcludedWindow` carrying its reason -
        never imputed, never coerced to a number, never silently dropped. Family
        order is the source order, so every downstream ratio maps straight back to
        its window ``index``. The classification order is deliberate: a non-REALIZED
        window is ``WINDOW_UNDEFINED``; then a KNOWN, strictly-positive predicted
        variance is required (``PREDICTED_VARIANCE_UNDEFINED`` /
        ``ZERO_PREDICTED_VARIANCE`` guard the defensive, structurally-unreachable
        cases); finally a KNOWN realized variance is required
        (``SINGLE_VALID_PERIOD`` is the only reason reachable here under the
        source's own semantics).
        """
        calibratable: list[CalibratableWindow] = []
        excluded: list[ExcludedWindow] = []
        for window in windows:
            reason = self._exclusion_reason(window)
            if reason is not None:
                excluded.append(ExcludedWindow(index=window.index, reason=reason))
                continue
            # Calibratable: predicted KNOWN & > 0, realized KNOWN (guaranteed by the
            # reason check returning None). Parse the sealed strings verbatim (RC-4).
            assert window.predicted_variance.value is not None
            assert window.realized_variance.value is not None
            calibratable.append(
                CalibratableWindow(
                    index=window.index,
                    predicted=Decimal(window.predicted_variance.value),
                    realized=Decimal(window.realized_variance.value),
                )
            )
        return tuple(calibratable), tuple(excluded)

    def _exclusion_reason(
        self, window: WindowResult
    ) -> CalibrationExcludedReason | None:
        """The reason ``window`` is not calibratable, or ``None`` if it is (RC-3)."""
        if window.status is not WindowStatus.REALIZED:
            return CalibrationExcludedReason.WINDOW_UNDEFINED
        predicted = window.predicted_variance
        if predicted.status is not StatStatus.KNOWN or predicted.value is None:
            # Defensive / structurally unreachable: a REALIZED GMV window always
            # sealed a KNOWN in-sample wᵀΣw.
            return CalibrationExcludedReason.PREDICTED_VARIANCE_UNDEFINED
        if Decimal(predicted.value) <= _ZERO:
            # Defensive / structurally unreachable: wᵀΣw over a positive-definite
            # covariance is strictly positive.
            return CalibrationExcludedReason.ZERO_PREDICTED_VARIANCE
        realized = window.realized_variance
        if realized.status is not StatStatus.KNOWN or realized.value is None:
            # A REALIZED window whose realized variance is UNDEFINED had a single
            # out-of-sample period (the source's SINGLE_VALID_PERIOD, carried forward) -
            # the only exclusion reachable for a REALIZED window.
            return CalibrationExcludedReason.SINGLE_VALID_PERIOD
        return None
