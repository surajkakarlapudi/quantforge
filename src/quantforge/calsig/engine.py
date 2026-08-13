"""The calibration-significance orchestration engine (§6, §11, §12, CS-1..CS-6).

:class:`CalibrationSignificanceEngine` sits strictly **above** Phase 26: it is a pure
consumer that turns a declarative
:class:`~quantforge.calsig.spec.CalibrationSignificanceSpecification` into a sealed
:class:`~quantforge.calsig.result.CalibrationSignificance` by *resolving* the one
already-sealed :class:`~quantforge.calibration.result.RiskForecastCalibration` the
request names, *verifying* it, *gating* on its defensibility, *reading its sealed
aggregate statistics verbatim* (the mean variance ratio, the population dispersion, and
the calibratable-window count - never recomputed, CS-4), *computing* the one-sample
large-sample two-sided significance test over them
(:func:`~quantforge.calsig.compute.test_calibration_significance`), and sealing the
answer. It introduces no new data resolution, no new PIT surface, and no new store; it
composes the pinned pure test under the version's decimal context and persists
write-once to the shared research sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** the ``source_calibration_id`` from the shared sidecar via
   ``store.read_as(id, RiskForecastCalibration.from_dict)``. A missing id (or a payload
   that does not decode as a ``RiskForecastCalibration``) is a consistency defect and
   raises :class:`~quantforge.calsig.errors.CalSigConsistencyError` (fail closed, CS-1).
2. **Verify** the resolved record's ``research_result_id`` equals the requested id (the
   sidecar is otherwise inconsistent); raise on disagreement (CS-1).
3. **Gate on defensibility** (CS-2): build the :class:`CalibratableFamily` only when the
   source's ``calibration_status`` is ``CALIBRATED`` **and** its sealed
   ``mean_variance_ratio`` / ``variance_ratio_dispersion`` cells are both KNOWN -
   reading those decimal strings verbatim (CS-4). Otherwise the family is ``None`` and
   the test is UNDEFINED ``SOURCE_NOT_CALIBRATED`` - recorded, never fabricated.
4. **Compute** the test
   (:func:`~quantforge.calsig.compute.test_calibration_significance`) under the
   version's decimal context: ``standard_error = dispersion / sqrt(K)``,
   ``t = (mean - 1) / standard_error``, the two-sided ``p = 2·(1 - Φ(|t|))`` clamped to
   ``[0, 1]``, and the descriptive bias direction - with the zero-dispersion guard
   sealing ``t`` / ``p`` UNDEFINED ``ZERO_RATIO_DISPERSION`` while ``mean`` and
   direction stay KNOWN (CS-3), never a divide-by-zero.
5. **Seal + persist**: seal a
   :class:`~quantforge.calsig.result.CalibrationSignificance` (its ``result_hash`` folds
   the answer, its id transitively pins the source calibration's ``result_hash``) and
   persist it write-once to the same sidecar. Rebuilding an identical request is a
   byte-identical no-op; a differing payload under the same id fails closed via the
   store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.calibration.model import CalibrationStatus, StatStatus
from quantforge.calibration.result import RiskForecastCalibration
from quantforge.calsig.compute import (
    CalibratableFamily,
    test_calibration_significance,
)
from quantforge.calsig.errors import (
    CalSigConfigurationError,
    CalSigConsistencyError,
)
from quantforge.calsig.result import (
    NULL_MEAN_RATIO,
    CalibrationSignificance,
    SignificanceSummary,
)
from quantforge.calsig.spec import CalibrationSignificanceSpecification
from quantforge.calsig.version import CalibrationSignificanceEngineVersion
from quantforge.factors.store import ResearchResultStore
from quantforge.workspace import Workspace

__all__ = ["CalibrationSignificanceEngine"]


class CalibrationSignificanceEngine:
    """Resolve, verify, gate, compute, and seal a significance request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    calibration engine sealed its calibrations to - so a request evaluates exactly the
    calibration already present. The sidecar may be overridden (for tests). The engine
    pins its orchestration logic + statistical method + normal primitive + decimal
    context via
    :class:`~quantforge.calsig.version.CalibrationSignificanceEngineVersion`, and
    computes every value under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: CalibrationSignificanceEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else CalibrationSignificanceEngineVersion()
        )

    @property
    def calibration_significance_engine_version_id(self) -> str:
        """The orchestration + method + normal + decimal-context version, folded into
        every id."""
        return self._version.calibration_significance_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the significance resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def evaluate(
        self, spec: CalibrationSignificanceSpecification
    ) -> CalibrationSignificance:
        """Resolve, verify, gate, compute, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same source calibration, recomputes byte-identical statistics
        under the pinned decimal context, and seals a byte-identical
        :class:`~quantforge.calsig.result.CalibrationSignificance` on any machine (whose
        sidecar write is an idempotent no-op). Fails closed on a missing / drifted
        reference or a non-``RiskForecastCalibration`` record (CS-1); a source that is
        not defensibly CALIBRATED yields a sealed record whose test is UNDEFINED
        ``SOURCE_NOT_CALIBRATED`` (CS-2), never raised; a degenerate zero-dispersion
        family seals ``t`` / ``p`` UNDEFINED ``ZERO_RATIO_DISPERSION`` (CS-3).
        """
        if not isinstance(spec, CalibrationSignificanceSpecification):
            raise CalSigConfigurationError(
                "evaluate() requires a CalibrationSignificanceSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the one source calibration (CS-1) ---------------
        source = self._resolve_calibration(spec.source_calibration_id, store)

        # -- gate on defensibility + read sealed statistics verbatim (CS-2/CS-4)
        family = self._family(source)

        # -- compute the one-sample test (CS-3/CS-4/CS-5) ---------------------
        computation = test_calibration_significance(
            family,
            null_mean=Decimal(NULL_MEAN_RATIO),
            context=context,
        )
        summary = SignificanceSummary(
            mean_variance_ratio=computation.mean_variance_ratio,
            null_mean_ratio=NULL_MEAN_RATIO,
            n_calibratable=computation.n_calibratable,
            standard_error=computation.standard_error,
            t_statistic=computation.t_statistic,
            p_value=computation.p_value,
            significance_status=computation.significance_status,
            bias_direction=computation.bias_direction,
            status_reason=computation.status_reason,
        )

        # -- seal + persist ---------------------------------------------------
        significance = CalibrationSignificance.seal(
            calibration_significance_engine_version_id=(
                self._version.calibration_significance_engine_version_id
            ),
            calibration_significance_spec=spec.to_dict(),
            source_ref=(source.research_result_id, source.result_hash),
            # Carry the source calibration's boundary through unchanged: it documents
            # that the underlying factor portfolios were PIT walks. The significance
            # output is ex-post and is not a PIT value (CS-6).
            boundary_kind=source.boundary_kind,
            summary=summary,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(significance)
        return significance

    # -- resolution & verification -------------------------------------------

    def _resolve_calibration(
        self, source_id: str, store: ResearchResultStore
    ) -> RiskForecastCalibration:
        """Read + verify the one referenced source calibration (fail closed, CS-1)."""
        try:
            result = store.read_as(source_id, RiskForecastCalibration.from_dict)
        except (KeyError, ValueError) as exc:
            raise CalSigConsistencyError(
                f"source calibration {source_id!r} could not be decoded as a "
                "RiskForecastCalibration; the referenced artifact is absent "
                "or not a risk-forecast calibration (fail closed)"
            ) from exc
        if result is None:
            raise CalSigConsistencyError(
                f"source calibration {source_id!r} is not present in the research "
                "sidecar; cannot test a calibration that was never sealed "
                "(fail closed)"
            )
        if result.research_result_id != source_id:
            raise CalSigConsistencyError(
                f"source calibration {source_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    # -- defensibility gate ---------------------------------------------------

    def _family(self, source: RiskForecastCalibration) -> CalibratableFamily | None:
        """The sealed ``(mean, dispersion, K)`` bundle, or ``None`` if not defensible.

        Builds a :class:`~quantforge.calsig.compute.CalibratableFamily` only when the
        source is defensibly CALIBRATED **and** its sealed ``mean_variance_ratio`` /
        ``variance_ratio_dispersion`` cells are both KNOWN, reading those canonical
        decimal strings verbatim into ``Decimal`` (CS-4 - never recomputed from the
        per-window ratios). Otherwise returns ``None``, so the test is UNDEFINED
        ``SOURCE_NOT_CALIBRATED`` (CS-2). The defensive KNOWN check guards the
        structurally-unreachable case of a CALIBRATED source whose aggregate cell is not
        KNOWN - never coerced into a number.
        """
        if source.calibration_status is not CalibrationStatus.CALIBRATED:
            return None
        summary = source.summary
        mean = summary.mean_variance_ratio
        dispersion = summary.variance_ratio_dispersion
        if mean.status is not StatStatus.KNOWN or mean.value is None:
            return None
        if dispersion.status is not StatStatus.KNOWN or dispersion.value is None:
            return None
        return CalibratableFamily(
            mean_variance_ratio=Decimal(mean.value),
            variance_ratio_dispersion=Decimal(dispersion.value),
            n_calibratable=source.coverage.n_calibratable,
        )
