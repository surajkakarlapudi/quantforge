"""The metric result model: status, provenance, and distinct PIT/REVISED types.

A **metric** is one value of one named formula, for one fiscal period, for one
filer, at one knowledge-state boundary (``docs/metrics.md`` §5). This module defines:

* :class:`MetricStatus` / :class:`UndefinedReason` — the fail-closed result
  vocabulary. ``UNDEFINED`` is a first-class value carrying *why*, never an
  exception, never ``0``/``NaN``/``Inf`` (§13, §14).
* :class:`MetricPeriod` — the requested fiscal period (an ``instant`` point or a
  ``duration`` span), defined solely by its dates (mirrors Phase 4's period rule).
* :class:`InputResolution` / :class:`MetricProvenance` — the audit chain from a
  metric back to the winning canonical facts, the discarded candidates, and the
  boundary (§9). Zero information loss (§15).
* :class:`PitMetricValue` / :class:`RevisedMetricValue` — **distinct** frozen result
  types (Decision D4), extending invariant 28 to the metric layer: a PIT-typed
  consumer can never be silently handed a revised metric.

Every field is deterministically serializable (``to_dict``); no wall-clock, RNG, or
iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TypedDict

from openfinance.availability.timestamps import format_utc_z, parse_utc
from openfinance.xbrl.contexts import PeriodType


class _BaseFields(TypedDict):
    """The shared metric fields, typed so ``**base`` unpacking is checkable."""

    metric_id: str
    metric_key: str
    formula_id: str
    metric_engine_version_id: str
    company_id: str
    period: MetricPeriod
    status: MetricStatus
    value_numeric_str: str | None
    unit: str | None
    reason: UndefinedReason | None
    provenance: MetricProvenance


__all__ = [
    "InputResolution",
    "MetricPeriod",
    "MetricProvenance",
    "MetricStatus",
    "PitMetricValue",
    "RevisedMetricValue",
    "UndefinedReason",
]


class MetricStatus(StrEnum):
    """Whether a metric resolved to a value (``KNOWN``) or not (``UNDEFINED``)."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class UndefinedReason(StrEnum):
    """Why a metric (or one of its inputs) is ``UNDEFINED`` — fail-closed (§13, §14).

    Every reason preserves information: it records the *absence* of a computable
    value rather than fabricating one. ``AMBIGUOUS_INPUT`` is retained for future
    strict selection policies; the Decision-D3 default selector does not raise it
    (it selects the first valid candidate and records the rest in provenance).
    """

    MISSING_INPUT = "missing_input"
    NIL_INPUT = "nil_input"
    NON_NUMERIC_INPUT = "non_numeric_input"
    UNIT_MISMATCH = "unit_mismatch"
    DIVIDE_BY_ZERO = "divide_by_zero"
    AMBIGUOUS_INPUT = "ambiguous_input"
    PERIOD_UNALIGNED = "period_unaligned"


@dataclass(frozen=True, slots=True)
class MetricPeriod:
    """The fiscal period a metric is requested for — defined solely by its dates.

    An ``INSTANT`` period carries ``period_end`` (the point) with ``period_start``
    ``None``; a ``DURATION`` period carries both dates. No fiscal-year/quarter
    meaning is attached (mirrors Phase 4's :class:`~openfinance.canonical.period`
    rule). ``period_key`` is the deterministic identity component used in
    ``metric_id`` (§6.2).
    """

    period_type: PeriodType
    period_start: str | None
    period_end: str | None

    @classmethod
    def instant(cls, period_end: str) -> MetricPeriod:
        """A balance-sheet point in time (e.g. ``"2023-09-30"``)."""
        return cls(PeriodType.INSTANT, None, period_end)

    @classmethod
    def duration(cls, period_start: str, period_end: str) -> MetricPeriod:
        """A flow span (e.g. FY2023 ``"2022-10-01"`` → ``"2023-09-30"``)."""
        return cls(PeriodType.DURATION, period_start, period_end)

    @property
    def period_key(self) -> str:
        """Deterministic identity string ``type|start|end`` (NUL-free components)."""
        return "\x00".join(
            (
                self.period_type.value,
                self.period_start or "",
                self.period_end or "",
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "period_type": self.period_type.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
        }


@dataclass(frozen=True, slots=True)
class InputResolution:
    """How one formula input resolved — the per-operand audit record (§9).

    Records the selected concept and its winning ``fact_id`` (→ Phase 4 Fact → full
    provenance → SEC bytes), the availability policy id that made it eligible, and
    **every** other candidate that was also present (Decision D3 — discarded
    candidates recorded), plus the resolution status/reason. For an ``UNDEFINED``
    input the selected fields are ``None`` and ``reason`` explains which input
    failed and why.
    """

    name: str
    status: MetricStatus
    selected_taxonomy: str | None = None
    selected_local_name: str | None = None
    selected_fact_id: str | None = None
    selected_availability_policy_id: str | None = None
    present_candidates: tuple[str, ...] = ()
    reason: UndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "selected_taxonomy": self.selected_taxonomy,
            "selected_local_name": self.selected_local_name,
            "selected_fact_id": self.selected_fact_id,
            "selected_availability_policy_id": self.selected_availability_policy_id,
            "present_candidates": list(self.present_candidates),
            "reason": self.reason.value if self.reason is not None else None,
        }


@dataclass(frozen=True, slots=True)
class MetricProvenance:
    """The unbroken chain from a metric back to canonical facts + boundary (§9).

    ``boundary_kind`` is ``"pit"`` or ``"rev"``; ``boundary_value`` is the aware-UTC
    ``as_of`` (PIT) or the ``dataset_version_id`` (REVISED). ``inputs`` records how
    each operand resolved (selected + discarded candidates). Present for both
    ``KNOWN`` and ``UNDEFINED`` metrics — an undefined metric records exactly which
    input failed and why (zero information loss, §15).
    """

    formula_id: str
    metric_engine_version_id: str
    boundary_kind: str
    boundary_value: str
    inputs: tuple[InputResolution, ...]
    result_status: MetricStatus
    result_reason: UndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "formula_id": self.formula_id,
            "metric_engine_version_id": self.metric_engine_version_id,
            "boundary_kind": self.boundary_kind,
            "boundary_value": self.boundary_value,
            "inputs": [i.to_dict() for i in self.inputs],
            "result_status": self.result_status.value,
            "result_reason": (
                self.result_reason.value if self.result_reason is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class _MetricValueBase:
    """Fields shared by the PIT and REVISED metric result types (§5)."""

    metric_id: str
    metric_key: str
    formula_id: str
    metric_engine_version_id: str
    company_id: str
    period: MetricPeriod
    status: MetricStatus
    value_numeric_str: str | None
    unit: str | None
    reason: UndefinedReason | None
    provenance: MetricProvenance

    @property
    def is_known(self) -> bool:
        return self.status is MetricStatus.KNOWN

    def _base_dict(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "metric_key": self.metric_key,
            "formula_id": self.formula_id,
            "metric_engine_version_id": self.metric_engine_version_id,
            "company_id": self.company_id,
            "period": self.period.to_dict(),
            "status": self.status.value,
            "value_numeric": self.value_numeric_str,
            "unit": self.unit,
            "reason": self.reason.value if self.reason is not None else None,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PitMetricValue(_MetricValueBase):
    """A metric knowable as of a historical instant — a **PIT** result (§5, §12).

    A distinct type from :class:`RevisedMetricValue` (Decision D4, invariant 28): a
    factor/backtest typed to ``PitMetricValue`` structurally cannot consume revised
    history. Computed *only* from :class:`~openfinance.availability.resolve.PitValue`
    inputs resolved at the same ``as_of`` (§5.1).
    """

    as_of: datetime = field(kw_only=True)

    def to_dict(self) -> dict[str, object]:
        data = self._base_dict()
        data["mode"] = "pit"
        data["as_of"] = format_utc_z(self.as_of)
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PitMetricValue:
        base = _base_from_dict(raw)
        as_of_raw = raw["as_of"]
        if not isinstance(as_of_raw, str):
            raise ValueError("as_of must be a string")
        return cls(as_of=parse_utc(as_of_raw), **base)


@dataclass(frozen=True, slots=True)
class RevisedMetricValue(_MetricValueBase):
    """The latest known metric over a pinned snapshot — a **REVISED** result (§5).

    Deliberately *not* interchangeable with :class:`PitMetricValue`. To use a
    revised metric in a PIT context the caller must call :meth:`reinterpret_as_pit`
    with an explicit ``as_of`` — an auditable, re-evaluating conversion, never an
    implicit cast (§5.2, invariant 28). ``dataset_version_id`` pins the ingestion
    frontier so the answer is reproducible.
    """

    dataset_version_id: str = field(kw_only=True)

    def to_dict(self) -> dict[str, object]:
        data = self._base_dict()
        data["mode"] = "revised"
        data["dataset_version_id"] = self.dataset_version_id
        return data

    def reinterpret_as_pit(self, engine: object, as_of: datetime) -> PitMetricValue:
        """Explicit, auditable conversion to a PIT metric at ``as_of``.

        This does **not** reuse the revised value; it re-runs the whole metric
        evaluation at ``as_of`` over the same history (§5.2), so the result
        genuinely reflects what was knowable then. ``engine`` is a
        :class:`~openfinance.metrics.engine.MetricEngine`; typed as ``object`` here
        only to avoid a module import cycle.
        """
        from openfinance.metrics.engine import MetricEngine
        from openfinance.registry.identity import cik_from_company_id

        if not isinstance(engine, MetricEngine):
            raise TypeError("reinterpret_as_pit requires a MetricEngine")
        # metric_as_of expects a bare CIK; recover it from the canonical company_id.
        cik = cik_from_company_id(self.company_id)
        return engine.metric_as_of(self.metric_key, cik, self.period, as_of)

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RevisedMetricValue:
        base = _base_from_dict(raw)
        dv_raw = raw["dataset_version_id"]
        if not isinstance(dv_raw, str):
            raise ValueError("dataset_version_id must be a string")
        return cls(dataset_version_id=dv_raw, **base)


def _base_from_dict(raw: dict[str, object]) -> _BaseFields:
    """Reconstruct the shared metric fields from a serialized dict."""
    period_raw = raw["period"]
    if not isinstance(period_raw, dict):
        raise ValueError("period must be an object")
    prov_raw = raw["provenance"]
    if not isinstance(prov_raw, dict):
        raise ValueError("provenance must be an object")
    reason = raw.get("reason")
    return _BaseFields(
        metric_id=_req_str(raw, "metric_id"),
        metric_key=_req_str(raw, "metric_key"),
        formula_id=_req_str(raw, "formula_id"),
        metric_engine_version_id=_req_str(raw, "metric_engine_version_id"),
        company_id=_req_str(raw, "company_id"),
        period=MetricPeriod(
            period_type=PeriodType(_req_str(period_raw, "period_type")),
            period_start=_opt_str(period_raw, "period_start"),
            period_end=_opt_str(period_raw, "period_end"),
        ),
        status=MetricStatus(_req_str(raw, "status")),
        value_numeric_str=_opt_str(raw, "value_numeric"),
        unit=_opt_str(raw, "unit"),
        reason=UndefinedReason(reason) if isinstance(reason, str) else None,
        provenance=_provenance_from_dict(prov_raw),
    )


def _provenance_from_dict(raw: dict[str, object]) -> MetricProvenance:
    inputs_raw = raw.get("inputs", [])
    inputs: list[InputResolution] = []
    if isinstance(inputs_raw, list):
        for item in inputs_raw:
            if not isinstance(item, dict):
                continue
            reason = item.get("reason")
            candidates = item.get("present_candidates", [])
            inputs.append(
                InputResolution(
                    name=_req_str(item, "name"),
                    status=MetricStatus(_req_str(item, "status")),
                    selected_taxonomy=_opt_str(item, "selected_taxonomy"),
                    selected_local_name=_opt_str(item, "selected_local_name"),
                    selected_fact_id=_opt_str(item, "selected_fact_id"),
                    selected_availability_policy_id=_opt_str(
                        item, "selected_availability_policy_id"
                    ),
                    present_candidates=tuple(
                        c for c in candidates if isinstance(c, str)
                    )
                    if isinstance(candidates, list)
                    else (),
                    reason=UndefinedReason(reason) if isinstance(reason, str) else None,
                )
            )
    result_reason = raw.get("result_reason")
    return MetricProvenance(
        formula_id=_req_str(raw, "formula_id"),
        metric_engine_version_id=_req_str(raw, "metric_engine_version_id"),
        boundary_kind=_req_str(raw, "boundary_kind"),
        boundary_value=_req_str(raw, "boundary_value"),
        inputs=tuple(inputs),
        result_status=MetricStatus(_req_str(raw, "result_status")),
        result_reason=(
            UndefinedReason(result_reason) if isinstance(result_reason, str) else None
        ),
    )


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value
