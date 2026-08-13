"""The sealed, content-addressed minimum-track-record-length record (§9, §10).

A completed evaluation is a :class:`MinimumTrackRecordLength`: the engine version, the
full declarative request, the ``(source_campaign_id, source_result_hash)`` reference to
the one sealed :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` it
consumed, per **evaluable** trial its minimum track-record length and excess length (in
the source's trial order), the **excluded** trials (each a trial the source sealed
UNDEFINED - or, defensively, a VALID trial whose moments were not KNOWN - with its
reason), the aggregate MinTRL :class:`MinTrlSummary` (mean / dispersion / max / min /
sufficient-frequency and the roll-up status), a non-hashed coverage block, and the
sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``minimum_track_record_length_id`` (a single id, mirroring
``risk_forecast_calibration_id``) and ``to_dict`` is deterministic - so it persists
write-once to the shared Phase 8 sidecar with **no new store** (§13). It stores only a
*pointer* to the source campaign, never a copy of its trials (the pointer-only
discipline of :class:`~quantforge.calibration.result.RiskForecastCalibration`): the
source already lives in the same sidecar, so this record stays a thin, reproducible view
over it.

**Ex-post, not PIT (MT-6).** A minimum track-record length computed over an
already-ex-post campaign is itself an ex-post research statistic, not a forward-usable
PIT value. :class:`MinimumTrackRecordLength` is deliberately **not** a ``Pit*`` type and
exposes **no** as-of accessor. ``boundary_kind = "pit"`` documents only that the
*underlying trials* were PIT walks - the convention where the label describes the input
side, not the ex-post output. It is not a ``BacktestResult`` and performs no execution.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~MinimumTrackRecordLength.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.mintrl.identity import (
    minimum_track_record_length_id as _mintrl_id,
)
from quantforge.mintrl.identity import (
    minimum_track_record_length_result_hash as _result_hash,
)
from quantforge.mintrl.model import (
    MinTrlExcludedReason,
    MinTrlStat,
    MinTrlStatus,
    MinTrlUndefinedReason,
)
from quantforge.mintrl.version import MINTRL_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "MINTRL_RESULT_FORMAT_VERSION",
    "MIN_DETERMINED_TRIALS",
    "ExcludedTrial",
    "MinTrlCoverage",
    "MinTrlSummary",
    "MinimumTrackRecordLength",
    "TrialMinTrlCell",
]

#: The §9 record-schema version for the MinTRL record - distinct from the engine-logic
#: version, the method version, the normal-primitive version, and the sidecar's
#: container format version. Bump it when the serialized meaning of a MinTRL record
#: changes (a container concern; it is **not** folded into
#: ``minimum_track_record_length_id`` - §10, prior-phase discipline).
MINTRL_RESULT_FORMAT_VERSION = "mintrl-result/1"

#: The only boundary a v1 MinTRL record accepts. It documents that the *underlying
#: trials* (beneath the source campaign) were PIT walks; the MinTRL *output* is ex-post
#: and is not a PIT value (MT-6). The engine carries the source campaign's
#: ``boundary_kind`` through unchanged.
BOUNDARY_PIT = "pit"

#: The minimum number of determined trials (evaluable trials with a KNOWN MinTRL) an
#: aggregate MinTRL profile must have to be defensible (§12, MT-3). Below this floor the
#: record still seals, but its ``mintrl_status`` is ``UNDEFINED``
#: (``INSUFFICIENT_DETERMINED_TRIALS``): a single MinTRL carries no cross-trial
#: dispersion. Folded into ``minimum_track_record_length_id`` (§10), so a change to it
#: is a distinguishable record.
MIN_DETERMINED_TRIALS = 2


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


def _excluded_reason(raw: dict[str, object]) -> MinTrlExcludedReason:
    """Decode a required exclusion ``reason`` string (fail closed)."""
    reason_raw = raw.get("reason")
    if not isinstance(reason_raw, str):
        raise ValueError("ExcludedTrial.reason must be a string")
    try:
        return MinTrlExcludedReason(reason_raw)
    except ValueError as exc:
        raise ValueError(f"unknown MinTrlExcludedReason {reason_raw!r}") from exc


@dataclass(frozen=True, slots=True)
class TrialMinTrlCell:
    """One evaluable trial's computed MinTRL cell (§9, MT-2/MT-4).

    ``label`` is the source trial's label; ``observed_length`` its OOS period count
    ``n``; ``sharpe`` / ``skew`` / ``kurtosis`` its KNOWN per-period Sharpe, skew, and
    non-excess kurtosis, carried verbatim from the source (never recomputed, MT-4).
    ``min_track_record_length`` is the minimum track-record length ``1 +
    V·(Z_alpha/(SR-SR*))²`` (UNDEFINED-preserving); ``excess_length = observed_length -
    min_track_record_length`` (UNDEFINED, inheriting the MinTRL's reason, when the
    MinTRL is undefined). All KNOWN values are canonical decimal strings.
    """

    label: str
    observed_length: int
    sharpe: str
    skew: str
    kurtosis: str
    min_track_record_length: MinTrlStat
    excess_length: MinTrlStat

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "observed_length": self.observed_length,
            "sharpe": self.sharpe,
            "skew": self.skew,
            "kurtosis": self.kurtosis,
            "min_track_record_length": self.min_track_record_length.to_dict(),
            "excess_length": self.excess_length.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TrialMinTrlCell:
        return cls(
            label=_req_str(raw, "label"),
            observed_length=_req_int(raw, "observed_length"),
            sharpe=_req_str(raw, "sharpe"),
            skew=_req_str(raw, "skew"),
            kurtosis=_req_str(raw, "kurtosis"),
            min_track_record_length=MinTrlStat.from_dict(
                _req_dict(raw, "min_track_record_length")
            ),
            excess_length=MinTrlStat.from_dict(_req_dict(raw, "excess_length")),
        )


@dataclass(frozen=True, slots=True)
class ExcludedTrial:
    """One trial excluded from the evaluable family, with its reason (§9, MT-3).

    A trial the source sealed non-evaluable: the whole trial UNDEFINED
    (``TRIAL_UNDEFINED``); or - defensive, structurally unreachable - a VALID trial
    whose ``sharpe`` / ``skew`` / ``kurtosis`` cell is not KNOWN
    (``MOMENTS_UNDEFINED``). It carries no MinTRL: it is recorded here, never imputed
    and never coerced to a length (MT-3).
    """

    label: str
    reason: MinTrlExcludedReason

    def to_dict(self) -> dict[str, object]:
        return {"label": self.label, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ExcludedTrial:
        return cls(label=_req_str(raw, "label"), reason=_excluded_reason(raw))


@dataclass(frozen=True, slots=True)
class MinTrlSummary:
    """The aggregate MinTRL statistics + the roll-up status (§9, MT-3/MT-5).

    Five UNDEFINED-preserving :class:`~quantforge.mintrl.model.MinTrlStat` cells over
    the determined family - ``mean_min_trl``, ``min_trl_dispersion`` (population std of
    the per-trial MinTRLs), ``max_min_trl`` / ``min_min_trl``, and
    ``sufficient_frequency`` (the fraction of determined trials whose observed length
    already meets its MinTRL) - plus ``n_determined`` (the count of determined trials,
    folded into the coverage descriptor's audit but retained here for readability) and
    ``mintrl_status`` (``EVALUATED`` when the family meets
    :data:`MIN_DETERMINED_TRIALS`, else ``UNDEFINED`` with ``status_reason``). With no
    determined trials every cell is UNDEFINED (``NO_DETERMINED_TRIALS``); the record
    still seals (MT-3).
    """

    mean_min_trl: MinTrlStat
    min_trl_dispersion: MinTrlStat
    max_min_trl: MinTrlStat
    min_min_trl: MinTrlStat
    sufficient_frequency: MinTrlStat
    n_determined: int
    mintrl_status: MinTrlStatus
    status_reason: MinTrlUndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mean_min_trl": self.mean_min_trl.to_dict(),
            "min_trl_dispersion": self.min_trl_dispersion.to_dict(),
            "max_min_trl": self.max_min_trl.to_dict(),
            "min_min_trl": self.min_min_trl.to_dict(),
            "sufficient_frequency": self.sufficient_frequency.to_dict(),
            "n_determined": self.n_determined,
            "mintrl_status": self.mintrl_status.value,
        }
        if self.status_reason is not None:
            payload["status_reason"] = self.status_reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MinTrlSummary:
        def _cell(key: str) -> MinTrlStat:
            value = raw.get(key)
            if not isinstance(value, dict):
                raise ValueError(f"MinTrlSummary.{key} must be an object")
            return MinTrlStat.from_dict(value)

        status_raw = _req_str(raw, "mintrl_status")
        try:
            status = MinTrlStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown mintrl_status {status_raw!r}") from exc
        reason_raw = raw.get("status_reason")
        reason: MinTrlUndefinedReason | None
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            try:
                reason = MinTrlUndefinedReason(reason_raw)
            except ValueError as exc:
                raise ValueError(
                    f"unknown MinTrlUndefinedReason {reason_raw!r}"
                ) from exc
        else:
            raise ValueError("MinTrlSummary.status_reason must be a string or absent")
        return cls(
            mean_min_trl=_cell("mean_min_trl"),
            min_trl_dispersion=_cell("min_trl_dispersion"),
            max_min_trl=_cell("max_min_trl"),
            min_min_trl=_cell("min_min_trl"),
            sufficient_frequency=_cell("sufficient_frequency"),
            n_determined=_req_int(raw, "n_determined"),
            mintrl_status=status,
            status_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class MinTrlCoverage:
    """The audit coverage block - counts of trials, evaluable, and excluded (§9).

    Beyond the descriptor a pure function of the sealed evaluable / excluded lists (a
    reader's convenience, not an independent input): the source campaign held
    ``n_trials`` trials, of which ``n_evaluable`` had KNOWN moments (the family fed to
    the MinTRL computation) and ``n_excluded`` were excluded, with ``n_evaluable +
    n_excluded == n_trials`` (MT-2).
    """

    n_trials: int
    n_evaluable: int
    n_excluded: int

    def to_dict(self) -> dict[str, object]:
        return {
            "n_trials": self.n_trials,
            "n_evaluable": self.n_evaluable,
            "n_excluded": self.n_excluded,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MinTrlCoverage:
        return cls(
            n_trials=_req_int(raw, "n_trials"),
            n_evaluable=_req_int(raw, "n_evaluable"),
            n_excluded=_req_int(raw, "n_excluded"),
        )


@dataclass(frozen=True, slots=True)
class MinimumTrackRecordLength:
    """A sealed, content-addressed minimum-track-record-length record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`minimum_track_record_length_id`;
    deterministic :meth:`to_dict`), so it persists write-once to the shared research
    sidecar with no new store. It pins the source campaign by ``(id, result_hash)``,
    holds the per-evaluable-trial MinTRL cells, the excluded trials, the aggregate
    summary, and the coverage block, and seals the computed answer into ``result_hash``.
    It is **not** a ``Pit*`` type and exposes no as-of accessor (MT-6).
    """

    minimum_track_record_length_engine_version_id: str
    mintrl_spec: dict[str, object]
    source_ref: tuple[str, str]
    boundary_kind: str
    trials: tuple[TrialMinTrlCell, ...]
    excluded: tuple[ExcludedTrial, ...]
    summary: MinTrlSummary
    coverage: MinTrlCoverage
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def minimum_track_record_length_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request, including the canonical confidence and benchmark),
        the source campaign id + ``result_hash``, the :data:`MIN_DETERMINED_TRIALS`
        floor, and the sealed ``result_hash`` over the answer.
        """
        spec = self.mintrl_spec
        return _mintrl_id(
            minimum_track_record_length_engine_version_id=(
                self.minimum_track_record_length_engine_version_id
            ),
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_campaign_id=_spec_str(spec, "source_campaign_id"),
            source_result_hash=self.source_ref[1],
            confidence=_spec_str(spec, "confidence"),
            benchmark_sharpe=_spec_str(spec, "benchmark_sharpe"),
            min_determined_trials=MIN_DETERMINED_TRIALS,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`minimum_track_record_length_id` - the :class:`ResearchRecord`
        id."""
        return self.minimum_track_record_length_id

    @property
    def source_campaign_id(self) -> str:
        """The referenced source campaign's ``research_result_id``."""
        return self.source_ref[0]

    @property
    def source_result_hash(self) -> str:
        """The referenced source campaign's ``result_hash`` (the transitive pin)."""
        return self.source_ref[1]

    @property
    def mintrl_status(self) -> MinTrlStatus:
        """The roll-up MinTRL status (a convenience alias of the summary's)."""
        return self.summary.mintrl_status

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        minimum_track_record_length_engine_version_id: str,
        mintrl_spec: dict[str, object],
        source_ref: tuple[str, str],
        boundary_kind: str,
        trials: tuple[TrialMinTrlCell, ...],
        excluded: tuple[ExcludedTrial, ...],
        summary: MinTrlSummary,
        coverage: MinTrlCoverage,
        method_version: str = MINTRL_METHOD_VERSION,
    ) -> MinimumTrackRecordLength:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the coverage descriptor, the evaluable-trial MinTRL cells, the excluded
        cells, then the aggregate summary) into ``result_hash`` via
        :func:`~quantforge.mintrl.identity.minimum_track_record_length_result_hash`, so
        identity is a pure function of the computed answer and never has to be supplied
        by the caller. The coverage block is a function of those cells and only its
        counts are folded, in the descriptor.
        """
        rhash = _result_hash(
            _output_cells(
                trials=trials,
                excluded=excluded,
                summary=summary,
                coverage=coverage,
            )
        )
        return cls(
            minimum_track_record_length_engine_version_id=(
                minimum_track_record_length_engine_version_id
            ),
            mintrl_spec=dict(mintrl_spec),
            source_ref=source_ref,
            boundary_kind=boundary_kind,
            trials=trials,
            excluded=excluded,
            summary=summary,
            coverage=coverage,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "minimum_track_record_length_id": (self.minimum_track_record_length_id),
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "minimum_track_record_length_engine_version_id": (
                self.minimum_track_record_length_engine_version_id
            ),
            "mintrl_spec": dict(self.mintrl_spec),
            "source_ref": {
                "source_campaign_id": self.source_ref[0],
                "source_result_hash": self.source_ref[1],
            },
            "boundary_kind": self.boundary_kind,
            "trials": [cell.to_dict() for cell in self.trials],
            "excluded": [cell.to_dict() for cell in self.excluded],
            "summary": self.summary.to_dict(),
            "coverage": self.coverage.to_dict(),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MinimumTrackRecordLength:
        """Reconstruct a sealed MinTRL record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, MinimumTrackRecordLength.from_dict)`` is a
        first-class typed object. ``minimum_track_record_length_id`` /
        ``research_result_id`` are derived aliases re-emitted by their properties (never
        read from state), every nested cell round-trips through its own fail-closed
        ``from_dict``, and the block order is preserved - so ``from_dict(to_dict(r))``
        re-emits identical bytes and the same ``result_hash``, introducing no drift.
        """
        source = _req_dict(raw, "source_ref")
        return cls(
            minimum_track_record_length_engine_version_id=_req_str(
                raw, "minimum_track_record_length_engine_version_id"
            ),
            mintrl_spec=dict(_req_dict(raw, "mintrl_spec")),
            source_ref=(
                _req_str(source, "source_campaign_id"),
                _req_str(source, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            trials=tuple(
                TrialMinTrlCell.from_dict(_as_dict(item, "trials"))
                for item in _req_list(raw, "trials")
            ),
            excluded=tuple(
                ExcludedTrial.from_dict(_as_dict(item, "excluded"))
                for item in _req_list(raw, "excluded")
            ),
            summary=MinTrlSummary.from_dict(_req_dict(raw, "summary")),
            coverage=MinTrlCoverage.from_dict(_req_dict(raw, "coverage")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    trials: tuple[TrialMinTrlCell, ...],
    excluded: tuple[ExcludedTrial, ...],
    summary: MinTrlSummary,
    coverage: MinTrlCoverage,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the coverage descriptor (trial / evaluable / excluded
    counts), then the evaluable-trial MinTRL cells (``label`` + the three carried
    moments + the MinTRL + the excess length) in source trial order, then the excluded
    cells (``label`` + reason), then the aggregate summary block - each tagged by its
    block so two structurally different records can never collide. The ids, request,
    confidence, benchmark, and floor are folded into ``minimum_track_record_length_id``
    through the request + reference instead. Sensitive to every computed length and
    aggregate.
    """
    cells: list[dict[str, object]] = [
        {
            "block": "coverage_descriptor",
            "n_trials": coverage.n_trials,
            "n_evaluable": coverage.n_evaluable,
            "n_excluded": coverage.n_excluded,
        }
    ]
    for cell in trials:
        cells.append(
            {
                "block": "trial",
                "label": cell.label,
                "observed_length": cell.observed_length,
                "sharpe": cell.sharpe,
                "skew": cell.skew,
                "kurtosis": cell.kurtosis,
                "min_track_record_length": cell.min_track_record_length.to_dict(),
                "excess_length": cell.excess_length.to_dict(),
            }
        )
    for gap in excluded:
        cells.append(
            {
                "block": "excluded",
                "label": gap.label,
                "reason": gap.reason.value,
            }
        )
    cells.append({"block": "summary", **summary.to_dict()})
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"mintrl_spec.{key} must be a string")
    return value
