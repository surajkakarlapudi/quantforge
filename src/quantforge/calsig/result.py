"""The sealed, content-addressed calibration-significance record (§9, §10).

A completed test is a :class:`CalibrationSignificance`: the engine version, the full
declarative request, the ``(source_calibration_id, source_result_hash)`` reference to
the one sealed :class:`~quantforge.calibration.result.RiskForecastCalibration` it
consumed, the aggregate :class:`SignificanceSummary` (the mean variance ratio carried
verbatim, the null mean tested, the window count, the standard error, the ``t``
statistic, the two-sided ``p`` value, the descriptive bias direction, and the roll-up
status), and the sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``calibration_significance_id`` (a single id, mirroring
``minimum_track_record_length_id``) and ``to_dict`` is deterministic - so it persists
write-once to the shared Phase 8 sidecar with **no new store** (§13). It stores only a
*pointer* to the source calibration, never a copy of its windows (the pointer-only
discipline of :class:`~quantforge.mintrl.result.MinimumTrackRecordLength`): the source
already lives in the same sidecar, so this record stays a thin, reproducible view over
it.

**Ex-post, not PIT (CS-6).** A significance test over an already-ex-post calibration is
itself an ex-post research statistic, not a forward-usable PIT value.
:class:`CalibrationSignificance` is deliberately **not** a ``Pit*`` type and exposes
**no** as-of accessor. ``boundary_kind = "pit"`` documents only that the *underlying
factor portfolios* were PIT walks - the convention where the label describes the input
side, not the ex-post output. It is not a ``BacktestResult`` and performs no execution.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~CalibrationSignificance.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.calsig.identity import (
    calibration_significance_id as _calsig_id,
)
from quantforge.calsig.identity import (
    calibration_significance_result_hash as _result_hash,
)
from quantforge.calsig.model import (
    BiasDirection,
    SignificanceStat,
    SignificanceStatus,
    SignificanceUndefinedReason,
)
from quantforge.calsig.version import CALSIG_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "CALSIG_RESULT_FORMAT_VERSION",
    "NULL_MEAN_RATIO",
    "CalibrationSignificance",
    "SignificanceSummary",
]

#: The §9 record-schema version for the significance record - distinct from the
#: engine-logic version, the method version, the normal-primitive version, and the
#: sidecar's container format version. Bump it when the serialized meaning of a
#: significance record changes (a container concern; it is **not** folded into
#: ``calibration_significance_id`` - §10, prior-phase discipline).
CALSIG_RESULT_FORMAT_VERSION = "calsig-result/1"

#: The only boundary a v1 significance record accepts. It documents that the
#: *underlying factor portfolios* (beneath the source calibration's walk-forward) were
#: PIT walks; the significance *output* is ex-post and is not a PIT value (CS-6). The
#: engine carries the source calibration's ``boundary_kind`` through unchanged.
BOUNDARY_PIT = "pit"

#: The null mean tested: perfect calibration on average is a mean variance ratio of
#: ``1``. A fixed platform constant (the single approved methodology has no per-request
#: numerical parameter), folded into ``calibration_significance_id`` (§10) - as Phase 26
#: folds ``MIN_CALIBRATABLE_WINDOWS`` - so a change to it is a distinguishable record.
NULL_MEAN_RATIO = "1"


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


@dataclass(frozen=True, slots=True)
class SignificanceSummary:
    """The aggregate one-sample significance statistics + the roll-up status (§9).

    ``mean_variance_ratio`` is the source's KNOWN mean carried verbatim (CS-4);
    ``null_mean_ratio`` the hypothesized mean tested (``1``); ``n_calibratable`` the
    source's calibratable-window count ``K``. ``standard_error`` / ``t_statistic`` /
    ``p_value`` are UNDEFINED-preserving
    :class:`~quantforge.calsig.model.SignificanceStat`
    cells; ``bias_direction`` the descriptive sign of the mis-calibration (``None`` when
    the source is not CALIBRATED); and ``significance_status`` (``TESTED`` when ``t`` /
    ``p`` are KNOWN, else ``UNDEFINED`` with ``status_reason``). With a non-CALIBRATED
    source every statistic is UNDEFINED (``SOURCE_NOT_CALIBRATED``); the record still
    seals (CS-2).
    """

    mean_variance_ratio: SignificanceStat
    null_mean_ratio: str
    n_calibratable: int
    standard_error: SignificanceStat
    t_statistic: SignificanceStat
    p_value: SignificanceStat
    significance_status: SignificanceStatus
    bias_direction: BiasDirection | None = None
    status_reason: SignificanceUndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mean_variance_ratio": self.mean_variance_ratio.to_dict(),
            "null_mean_ratio": self.null_mean_ratio,
            "n_calibratable": self.n_calibratable,
            "standard_error": self.standard_error.to_dict(),
            "t_statistic": self.t_statistic.to_dict(),
            "p_value": self.p_value.to_dict(),
            "significance_status": self.significance_status.value,
        }
        if self.bias_direction is not None:
            payload["bias_direction"] = self.bias_direction.value
        if self.status_reason is not None:
            payload["status_reason"] = self.status_reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> SignificanceSummary:
        def _cell(key: str) -> SignificanceStat:
            value = raw.get(key)
            if not isinstance(value, dict):
                raise ValueError(f"SignificanceSummary.{key} must be an object")
            return SignificanceStat.from_dict(value)

        status_raw = _req_str(raw, "significance_status")
        try:
            status = SignificanceStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown significance_status {status_raw!r}") from exc

        direction_raw = raw.get("bias_direction")
        direction: BiasDirection | None
        if direction_raw is None:
            direction = None
        elif isinstance(direction_raw, str):
            try:
                direction = BiasDirection(direction_raw)
            except ValueError as exc:
                raise ValueError(f"unknown bias_direction {direction_raw!r}") from exc
        else:
            raise ValueError(
                "SignificanceSummary.bias_direction must be a string or absent"
            )

        reason_raw = raw.get("status_reason")
        reason: SignificanceUndefinedReason | None
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            try:
                reason = SignificanceUndefinedReason(reason_raw)
            except ValueError as exc:
                raise ValueError(
                    f"unknown SignificanceUndefinedReason {reason_raw!r}"
                ) from exc
        else:
            raise ValueError(
                "SignificanceSummary.status_reason must be a string or absent"
            )

        return cls(
            mean_variance_ratio=_cell("mean_variance_ratio"),
            null_mean_ratio=_req_str(raw, "null_mean_ratio"),
            n_calibratable=_req_int(raw, "n_calibratable"),
            standard_error=_cell("standard_error"),
            t_statistic=_cell("t_statistic"),
            p_value=_cell("p_value"),
            significance_status=status,
            bias_direction=direction,
            status_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class CalibrationSignificance:
    """A sealed, content-addressed calibration-significance record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`calibration_significance_id`;
    deterministic :meth:`to_dict`), so it persists write-once to the shared research
    sidecar with no new store. It pins the source calibration by ``(id, result_hash)``,
    holds the aggregate significance summary, and seals the computed answer into
    ``result_hash``. It is **not** a ``Pit*`` type and exposes no as-of accessor (CS-6).
    """

    calibration_significance_engine_version_id: str
    calibration_significance_spec: dict[str, object]
    source_ref: tuple[str, str]
    boundary_kind: str
    summary: SignificanceSummary
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def calibration_significance_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the source calibration id + ``result_hash``, the
        :data:`NULL_MEAN_RATIO` tested, and the sealed ``result_hash`` over the answer.
        """
        spec = self.calibration_significance_spec
        return _calsig_id(
            calibration_significance_engine_version_id=(
                self.calibration_significance_engine_version_id
            ),
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_calibration_id=_spec_str(spec, "source_calibration_id"),
            source_result_hash=self.source_ref[1],
            null_mean_ratio=self.summary.null_mean_ratio,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`calibration_significance_id` - the :class:`ResearchRecord`
        id."""
        return self.calibration_significance_id

    @property
    def source_calibration_id(self) -> str:
        """The referenced source calibration's ``research_result_id``."""
        return self.source_ref[0]

    @property
    def source_result_hash(self) -> str:
        """The referenced source calibration's ``result_hash`` (the transitive pin)."""
        return self.source_ref[1]

    @property
    def significance_status(self) -> SignificanceStatus:
        """The roll-up significance status (a convenience alias of the summary's)."""
        return self.summary.significance_status

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        calibration_significance_engine_version_id: str,
        calibration_significance_spec: dict[str, object],
        source_ref: tuple[str, str],
        boundary_kind: str,
        summary: SignificanceSummary,
        method_version: str = CALSIG_METHOD_VERSION,
    ) -> CalibrationSignificance:
        """Seal the computed summary, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the single aggregate summary block) into ``result_hash`` via
        :func:`~quantforge.calsig.identity.calibration_significance_result_hash`, so
        identity is a pure function of the computed answer and never has to be supplied
        by the caller.
        """
        rhash = _result_hash(_output_cells(summary=summary))
        return cls(
            calibration_significance_engine_version_id=(
                calibration_significance_engine_version_id
            ),
            calibration_significance_spec=dict(calibration_significance_spec),
            source_ref=source_ref,
            boundary_kind=boundary_kind,
            summary=summary,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "calibration_significance_id": self.calibration_significance_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "calibration_significance_engine_version_id": (
                self.calibration_significance_engine_version_id
            ),
            "calibration_significance_spec": dict(self.calibration_significance_spec),
            "source_ref": {
                "source_calibration_id": self.source_ref[0],
                "source_result_hash": self.source_ref[1],
            },
            "boundary_kind": self.boundary_kind,
            "summary": self.summary.to_dict(),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CalibrationSignificance:
        """Reconstruct a sealed significance record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, CalibrationSignificance.from_dict)`` is a
        first-class typed object. ``calibration_significance_id`` /
        ``research_result_id`` are derived aliases re-emitted by their properties (never
        read from state), the nested summary round-trips through its own fail-closed
        ``from_dict`` - so ``from_dict(to_dict(r))`` re-emits identical bytes and the
        same ``result_hash``, introducing no drift.
        """
        source = _req_dict(raw, "source_ref")
        return cls(
            calibration_significance_engine_version_id=_req_str(
                raw, "calibration_significance_engine_version_id"
            ),
            calibration_significance_spec=dict(
                _req_dict(raw, "calibration_significance_spec")
            ),
            source_ref=(
                _req_str(source, "source_calibration_id"),
                _req_str(source, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            summary=SignificanceSummary.from_dict(_req_dict(raw, "summary")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(*, summary: SignificanceSummary) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the aggregate significance summary block, tagged by
    its block so two structurally different records can never collide. The ids, request,
    and null mean are folded into ``calibration_significance_id`` through the request +
    reference instead. Sensitive to every computed statistic.
    """
    return [{"block": "summary", **summary.to_dict()}]


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"calibration_significance_spec.{key} must be a string")
    return value
