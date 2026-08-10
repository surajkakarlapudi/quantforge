"""The sealed, content-addressed signal-diagnostics record (§3.3, §5).

A completed diagnostics computation is a :class:`SignalDiagnostics`: the engine version,
the full declarative request, the PIT ``boundary_kind`` (signal side), both re-verified
corpus pins, the evaluation ``schedule_id``, the per-date IC ledger, the across-date
quantile profile, the IC summary, the coverage breakdown, and the sealed ``result_hash``
over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol — ``research_result_id``
aliases ``diagnostics_id`` (a single id) and ``to_dict`` is deterministic — so it
persists write-once to the shared Phase 8 sidecar with **no new store** (D10). It
references the raw corpora only by **pin** (D9), never a copy of a financial value
beyond the computed statistics.

Crucially, the record is a **distinct forward-looking type (SD-2)**: it incorporates
realized *forward* returns and therefore exposes no ``Pit*`` type and no as-of accessor
— it can never be substituted where a PIT as-of-``T`` value/signal is required.
``boundary_kind = "pit"`` documents that the *signal* was PIT-eligible, not that the
diagnostic itself is a PIT value.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~SignalDiagnostics.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict( r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.diagnostics.identity import diagnostics_id as _diagnostics_id
from quantforge.diagnostics.identity import diagnostics_result_hash as _result_hash
from quantforge.diagnostics.model import (
    CoverageSummary,
    ICSummary,
    PerDateIC,
    QuantileProfile,
)
from quantforge.diagnostics.version import DIAGNOSTICS_FORMULA_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "DIAGNOSTICS_RESULT_FORMAT_VERSION",
    "SignalDiagnostics",
]

#: The §9 record-schema version for the diagnostics record — distinct from the
#: engine-logic version, the formula version, and the sidecar's container format
#: version. Bump it when the serialized meaning of a diagnostics record changes (a
#: container concern; it is **not** folded into ``diagnostics_id`` — §5, Phase 14 D9
#: discipline).
DIAGNOSTICS_RESULT_FORMAT_VERSION = "diagnostics-result/1"

#: The only boundary a v1 diagnostics record carries (SD-2, §6). It documents that the
#: *signal* was PIT-eligible; it does **not** claim the diagnostic is a PIT value.
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


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"each {key} entry must be a string")
    return value


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"diagnostics_spec.{key} must be a string")
    return value


def _spec_int(spec: dict[str, object], key: str) -> int:
    value = spec.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"diagnostics_spec.{key} must be an int")
    return value


def _spec_methods(spec: dict[str, object]) -> list[str]:
    """Read the sorted IC methods out of the embedded request (fail closed).

    The embedded ``SignalDiagnosticsSpecification.to_dict()`` already emits
    ``ic_methods`` in its sorted form, so the value folded into ``diagnostics_id`` is
    order-independent by construction.
    """
    value = spec.get("ic_methods")
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError("diagnostics_spec.ic_methods must be a list of strings")
    return list(value)


def _spec_period_key(spec: dict[str, object]) -> str:
    """Reconstruct the canonical ``period_key`` from the embedded request (fail closed).

    Mirrors :attr:`~quantforge.metrics.model.MetricPeriod.period_key` — the NUL-joined
    ``type|start|end`` — so identity does not depend on re-instantiating a
    ``MetricPeriod`` and matches what the spec would have produced.
    """
    period = spec.get("period")
    if not isinstance(period, dict):
        raise ValueError("diagnostics_spec.period must be an object")
    period_type = period.get("period_type")
    if not isinstance(period_type, str):
        raise ValueError("diagnostics_spec.period.period_type must be a string")
    start = period.get("period_start")
    end = period.get("period_end")
    return "\x00".join(
        (
            period_type,
            start if isinstance(start, str) else "",
            end if isinstance(end, str) else "",
        )
    )


def _spec_universe_id(spec: dict[str, object]) -> str:
    universe = spec.get("universe")
    if not isinstance(universe, dict):
        raise ValueError("diagnostics_spec.universe must be an object")
    return _spec_str(universe, "specification_id")


def _spec_schedule_id(spec: dict[str, object]) -> str:
    schedule = spec.get("schedule")
    if not isinstance(schedule, dict):
        raise ValueError("diagnostics_spec.schedule must be an object")
    return _spec_str(schedule, "schedule_id")


@dataclass(frozen=True, slots=True)
class SignalDiagnostics:
    """A sealed, content-addressed signal-diagnostics record (§3.3, D9, D10).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`diagnostics_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It references both corpora by pin, records the evaluation schedule
    identity and the per-date / summary / coverage blocks, and seals the computed answer
    into ``result_hash`` — so its identity is a pure function of the request, both
    corpus pins, and the computed statistics. It is a forward-looking type: it exposes
    **no** ``Pit*`` type and **no** as-of accessor (SD-2).
    """

    signal_diagnostics_engine_version_id: str
    diagnostics_spec: dict[str, object]
    boundary_kind: str
    dataset_version_id: str
    market_dataset_version_id: str
    schedule_id: str
    per_date: tuple[PerDateIC, ...]
    quantile_profile: QuantileProfile
    ic_summary: ICSummary
    coverage: CoverageSummary
    formula_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def diagnostics_id(self) -> str:
        """The content-addressed id — request, corpora, **and** answer (§5).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), both corpus pins, and the sealed ``result_hash``
        over the computed answer.
        """
        spec = self.diagnostics_spec
        return _diagnostics_id(
            signal_diagnostics_engine_version_id=(
                self.signal_diagnostics_engine_version_id
            ),
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            signal=_spec_str(spec, "signal"),
            period_key=_spec_period_key(spec),
            universe_specification_id=_spec_universe_id(spec),
            schedule_id=self.schedule_id,
            horizon_days=_spec_int(spec, "horizon_days"),
            quantiles=_spec_int(spec, "quantiles"),
            sorted_ic_methods=_spec_methods(spec),
            dataset_version_id=self.dataset_version_id,
            market_dataset_version_id=self.market_dataset_version_id,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`diagnostics_id` — the :class:`ResearchRecord` identity."""
        return self.diagnostics_id

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        signal_diagnostics_engine_version_id: str,
        diagnostics_spec: dict[str, object],
        boundary_kind: str,
        dataset_version_id: str,
        market_dataset_version_id: str,
        schedule_id: str,
        per_date: tuple[PerDateIC, ...],
        quantile_profile: QuantileProfile,
        ic_summary: ICSummary,
        coverage: CoverageSummary,
        formula_version: str = DIAGNOSTICS_FORMULA_VERSION,
    ) -> SignalDiagnostics:
        """Seal the computed blocks, folding the answer into ``result_hash`` (§5).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the per-date IC block, then the quantile-profile block, then the
        IC-summary block) into ``result_hash`` via
        :func:`~quantforge.diagnostics.identity.diagnostics_result_hash`, so identity is
        a pure function of the computed answer and never has to be supplied by the
        caller.
        """
        rhash = _result_hash(
            _output_cells(
                per_date=per_date,
                quantile_profile=quantile_profile,
                ic_summary=ic_summary,
            )
        )
        return cls(
            signal_diagnostics_engine_version_id=(signal_diagnostics_engine_version_id),
            diagnostics_spec=dict(diagnostics_spec),
            boundary_kind=boundary_kind,
            dataset_version_id=dataset_version_id,
            market_dataset_version_id=market_dataset_version_id,
            schedule_id=schedule_id,
            per_date=per_date,
            quantile_profile=quantile_profile,
            ic_summary=ic_summary,
            coverage=coverage,
            formula_version=formula_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "diagnostics_id": self.diagnostics_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "signal_diagnostics_engine_version_id": (
                self.signal_diagnostics_engine_version_id
            ),
            "diagnostics_spec": dict(self.diagnostics_spec),
            "boundary_kind": self.boundary_kind,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
            "schedule_id": self.schedule_id,
            "per_date": [d.to_dict() for d in self.per_date],
            "quantile_profile": self.quantile_profile.to_dict(),
            "ic_summary": self.ic_summary.to_dict(),
            "coverage": self.coverage.to_dict(),
            "formula_version": self.formula_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> SignalDiagnostics:
        """Reconstruct a sealed diagnostics record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, SignalDiagnostics.from_dict)`` is a first-class
        typed object. ``diagnostics_id`` / ``research_result_id`` are derived aliases
        re-emitted by their properties (never read from state), every nested record
        round-trips through its own fail-closed ``from_dict``, and the per-date order is
        preserved — so ``from_dict(to_dict(r))`` re-emits identical bytes and the same
        ``result_hash``, introducing no drift.
        """
        per_date = tuple(
            PerDateIC.from_dict(d)
            for d in _req_list(raw, "per_date")
            if isinstance(d, dict)
        )
        if len(per_date) != len(_req_list(raw, "per_date")):
            raise ValueError("each per_date entry must be an object")
        return cls(
            signal_diagnostics_engine_version_id=_req_str(
                raw, "signal_diagnostics_engine_version_id"
            ),
            diagnostics_spec=dict(_req_dict(raw, "diagnostics_spec")),
            boundary_kind=_req_str(raw, "boundary_kind"),
            dataset_version_id=_req_str(raw, "dataset_version_id"),
            market_dataset_version_id=_req_str(raw, "market_dataset_version_id"),
            schedule_id=_req_str(raw, "schedule_id"),
            per_date=per_date,
            quantile_profile=QuantileProfile.from_dict(
                _req_dict(raw, "quantile_profile")
            ),
            ic_summary=ICSummary.from_dict(_req_dict(raw, "ic_summary")),
            coverage=CoverageSummary.from_dict(_req_dict(raw, "coverage")),
            formula_version=_req_str(raw, "formula_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    per_date: tuple[PerDateIC, ...],
    quantile_profile: QuantileProfile,
    ic_summary: ICSummary,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§5).

    A single deterministic list — the per-date IC block (each date's per-method IC,
    bucket means, and spread), then the quantile-profile block, then the IC-summary
    block — each cell tagged by its block so two structurally different records can
    never collide. Sensitive to every computed statistic: one differing cell changes
    ``result_hash`` and therefore ``diagnostics_id``.
    """
    cells: list[dict[str, object]] = []
    for date in per_date:
        cells.append({"block": "per_date", **date.to_dict()})
    cells.append({"block": "quantile_profile", **quantile_profile.to_dict()})
    cells.append({"block": "ic_summary", **ic_summary.to_dict()})
    return cells
