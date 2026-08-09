"""The point-in-time fundamental panel result model (locked §2, §5, §6, §9).

A **panel** is *one metric, evaluated over a declared period axis, for one filer or
one universe, at one knowledge-state boundary*, in one of three shapes (§2). This
module defines:

* :class:`PanelShape` — the closed set of shapes (period-series / vintage /
  cross-section).
* :class:`PanelCell` — one ``(period, as_of, member)`` coordinate's contribution:
  the full Phase 7 metric result (``KNOWN`` with provenance, or ``UNDEFINED`` with a
  reason — never ``None``, never dropped) plus the optional multi-period derivation
  output and the input periods it consumed (§6).
* :class:`PanelStatus` — per-reason cell counts over the *effective* cell outcome
  (the derived value when a derivation applied, else the raw metric), so "how many
  coordinates resolved, and why not the rest?" is answerable without walking every
  cell (§6).
* :class:`PanelResearchResult` — the reproducible §9 provenance record, one axis
  wider than the Phase 8 :class:`~quantforge.factors.model.ResearchResult`: its
  ``query_params`` records the *axis*, the *derivation*, and the *shape* (not a
  single period), and ``strategy_version`` is deliberately absent (reserved for the
  deferred backtester, §5).
* :class:`PitPanel` / :class:`RevisedPanel` — **distinct** frozen result types
  (Decision D5, invariant 28): a consumer typed to ``PitPanel`` structurally cannot
  be handed a revised panel, and a revised → PIT conversion must re-resolve
  explicitly at an ``as_of`` (:meth:`RevisedPanel.reinterpret_as_pit`).

Every value is deterministically serializable (``to_dict``); no wall-clock, RNG, or
iteration-order dependence enters any value or id. Panels are **compute-on-demand**
(D2) and their values are never persisted (§10); only the
:class:`PanelResearchResult` is materialized to the write-once sidecar (D4), so
these result types carry ``to_dict`` for inspection/export but are never
deserialized from disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TypedDict

from quantforge.availability.timestamps import format_utc_z
from quantforge.metrics.model import (
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)
from quantforge.panel.axis import PeriodAxis
from quantforge.panel.derive import Derivation

__all__ = [
    "PanelCell",
    "PanelResearchResult",
    "PanelShape",
    "PanelStatus",
    "PitPanel",
    "RevisedPanel",
]


class _PanelBaseFields(TypedDict):
    """The shared panel fields, typed so ``**base`` unpacking is checkable."""

    panel_id: str
    panel_definition_id: str
    metric_engine_version_id: str
    metric_key: str
    formula_id: str
    derivation_id: str
    axis_id: str
    shape: str
    axis: PeriodAxis
    derivation: Derivation
    cells: tuple[PanelCell, ...]
    summary: PanelStatus
    research_result: PanelResearchResult


class PanelShape(StrEnum):
    """The closed set of panel shapes (§2)."""

    PERIOD_SERIES = "period_series"
    VINTAGE = "vintage"
    CROSS_SECTION = "cross_section"


@dataclass(frozen=True, slots=True)
class PanelCell:
    """One ``(period, as_of, member)`` coordinate's contribution to a panel (§2, §6).

    ``metric`` is the full Phase 7 metric result for this coordinate — ``KNOWN``
    (value + provenance) or ``UNDEFINED`` (reason + provenance) — never ``None`` and
    never dropped. When a multi-period derivation applied, ``derived_value_numeric_str``
    is its output (exact ``Decimal`` serialized, ``None`` when the derivation is
    ``UNDEFINED``); ``derived_status`` / ``derived_reason`` record the derivation's
    own outcome and ``consumed_period_keys`` / ``undefined_input_period_key`` name
    which input periods it read and which (if any) made it undefined (§6 zero
    information loss). For the identity derivation ``derived_status`` is ``None``.
    """

    company_id: str
    period: MetricPeriod
    as_of: datetime | None
    metric: PitMetricValue | RevisedMetricValue
    derived_value_numeric_str: str | None = None
    derived_status: MetricStatus | None = None
    derived_reason: UndefinedReason | None = None
    consumed_period_keys: tuple[str, ...] = ()
    undefined_input_period_key: str | None = None

    @property
    def has_derivation(self) -> bool:
        """Whether a multi-period derivation was applied to this cell."""
        return self.derived_status is not None

    @property
    def effective_status(self) -> MetricStatus:
        """The status a researcher reads: the derivation's when one applied, else the
        raw metric's."""
        if self.derived_status is not None:
            return self.derived_status
        return self.metric.status

    @property
    def effective_reason(self) -> UndefinedReason | None:
        """The reason behind the effective status (``None`` when ``KNOWN``)."""
        if self.derived_status is not None:
            return self.derived_reason
        return self.metric.reason

    def to_dict(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "period": self.period.to_dict(),
            "as_of": format_utc_z(self.as_of) if self.as_of is not None else None,
            "metric": self.metric.to_dict(),
            "derived_value_numeric": self.derived_value_numeric_str,
            "derived_status": (
                self.derived_status.value if self.derived_status is not None else None
            ),
            "derived_reason": (
                self.derived_reason.value if self.derived_reason is not None else None
            ),
            "consumed_period_keys": list(self.consumed_period_keys),
            "undefined_input_period_key": self.undefined_input_period_key,
        }

    def outcome_digest(self) -> dict[str, object]:
        """The minimal per-cell fingerprint hashed into ``result_hash`` (§5).

        Names the coordinate, the resolved metric status/value/reason, and the
        derivation output — the load-bearing *output* of the cell. It omits the full
        provenance chain (reproducible from the same request), keeping the hash a
        stable function of the answer, not of the audit chain's layout.
        """
        return {
            "company_id": self.company_id,
            "period_key": self.period.period_key,
            "as_of": format_utc_z(self.as_of) if self.as_of is not None else None,
            "metric_status": self.metric.status.value,
            "metric_value_numeric": self.metric.value_numeric_str,
            "metric_unit": self.metric.unit,
            "metric_reason": (self.metric.reason.value if self.metric.reason else None),
            "derived_value_numeric": self.derived_value_numeric_str,
            "derived_status": (
                self.derived_status.value if self.derived_status is not None else None
            ),
            "derived_reason": (
                self.derived_reason.value if self.derived_reason is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class PanelStatus:
    """Per-reason cell counts across the panel — an audit summary (§6).

    Counts are over the *effective* cell outcome (the derivation's when one applied,
    else the raw metric's), so a panel with a ``growth`` derivation reports how many
    growth cells resolved, not how many raw levels did. ``known`` counts the
    effective-``KNOWN`` cells; ``undefined_by_reason`` maps each occurring
    :class:`UndefinedReason` value to its count. ``total`` is the coordinate count
    (every coordinate is a cell). Deterministic: reasons are emitted sorted.
    """

    total: int
    known: int
    undefined_by_reason: dict[str, int]

    @classmethod
    def from_cells(cls, cells: tuple[PanelCell, ...]) -> PanelStatus:
        """Summarize a cell tuple into per-reason counts (deterministic)."""
        known = 0
        by_reason: dict[str, int] = {}
        for cell in cells:
            if cell.effective_status is MetricStatus.KNOWN:
                known += 1
                continue
            reason = cell.effective_reason
            key = reason.value if reason is not None else "unspecified"
            by_reason[key] = by_reason.get(key, 0) + 1
        return cls(
            total=len(cells),
            known=known,
            undefined_by_reason=dict(sorted(by_reason.items())),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "known": self.known,
            "undefined_by_reason": dict(sorted(self.undefined_by_reason.items())),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PanelStatus:
        by_reason_raw = raw.get("undefined_by_reason", {})
        by_reason: dict[str, int] = {}
        if isinstance(by_reason_raw, dict):
            for key, value in by_reason_raw.items():
                if isinstance(key, str) and isinstance(value, int):
                    by_reason[key] = value
        return cls(
            total=_req_int(raw, "total"),
            known=_req_int(raw, "known"),
            undefined_by_reason=dict(sorted(by_reason.items())),
        )


@dataclass(frozen=True, slots=True)
class PanelResearchResult:
    """The reproducible provenance record for a panel (§5, §6, data-model §9).

    Realizes data-model §9's reserved ``ResearchResult`` one axis wider than the
    Phase 8 :class:`~quantforge.factors.model.ResearchResult`. ``panel_definition_id``
    ≡ §9 ``factor_definition_id``; ``metric_engine_version_id`` ≡ §9
    ``factor_version``. ``strategy_version`` is deliberately absent — reserved for
    the deferred backtester (§5, §11). ``query_params`` records the *axis*, the
    *derivation*, the *shape*, and the member(s) — not a single period.
    ``result_hash`` fingerprints the ordered cell outcomes, so ``panel_id`` pins both
    the request and the output.

    ``member_key`` is a ``company_id`` (per-filer shapes) or a ``universe_id`` (the
    matrix). Round-trips through the shared write-once sidecar (Decision D4).
    """

    panel_id: str
    panel_definition_id: str
    metric_engine_version_id: str
    metric_key: str
    formula_id: str
    derivation_id: str
    axis_id: str
    shape: str
    member_key: str
    boundary_kind: str
    boundary_value: str
    dataset_version_id: str
    as_of_timestamp: str | None
    summary: PanelStatus
    result_hash: str

    @property
    def research_result_id(self) -> str:
        """Alias so this record satisfies the sidecar's ``ResearchRecord`` protocol.

        The panel's content-addressed identity *is* its ``panel_id``; the sidecar
        keys files by ``research_result_id``, so we expose the id under that name
        without introducing a second identity.
        """
        return self.panel_id

    @property
    def query_params(self) -> dict[str, object]:
        """The §9 ``query_params`` — metric / axis / derivation / shape / member."""
        return {
            "metric_key": self.metric_key,
            "member_key": self.member_key,
            "axis_id": self.axis_id,
            "derivation": self.derivation_id,
            "shape": self.shape,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "panel_id": self.panel_id,
            # §9 aliases so a generic reader keyed on the reserved names still works.
            "research_result_id": self.panel_id,
            "factor_definition_id": self.panel_definition_id,
            "factor_version": self.metric_engine_version_id,
            "panel_definition_id": self.panel_definition_id,
            "metric_engine_version_id": self.metric_engine_version_id,
            "metric_key": self.metric_key,
            "formula_id": self.formula_id,
            "derivation_id": self.derivation_id,
            "axis_id": self.axis_id,
            "shape": self.shape,
            "member_key": self.member_key,
            "boundary_kind": self.boundary_kind,
            "boundary_value": self.boundary_value,
            "dataset_version_id": self.dataset_version_id,
            "as_of_timestamp": self.as_of_timestamp,
            "query_params": self.query_params,
            "summary": self.summary.to_dict(),
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PanelResearchResult:
        summary_raw = raw["summary"]
        if not isinstance(summary_raw, dict):
            raise ValueError("summary must be an object")
        return cls(
            panel_id=_req_str(raw, "panel_id"),
            panel_definition_id=_req_str(raw, "panel_definition_id"),
            metric_engine_version_id=_req_str(raw, "metric_engine_version_id"),
            metric_key=_req_str(raw, "metric_key"),
            formula_id=_req_str(raw, "formula_id"),
            derivation_id=_req_str(raw, "derivation_id"),
            axis_id=_req_str(raw, "axis_id"),
            shape=_req_str(raw, "shape"),
            member_key=_req_str(raw, "member_key"),
            boundary_kind=_req_str(raw, "boundary_kind"),
            boundary_value=_req_str(raw, "boundary_value"),
            dataset_version_id=_req_str(raw, "dataset_version_id"),
            as_of_timestamp=_opt_str(raw, "as_of_timestamp"),
            summary=PanelStatus.from_dict(summary_raw),
            result_hash=_req_str(raw, "result_hash"),
        )


@dataclass(frozen=True, slots=True)
class _PanelBase:
    """Fields shared by the PIT and REVISED panel result types (§2)."""

    panel_id: str
    panel_definition_id: str
    metric_engine_version_id: str
    metric_key: str
    formula_id: str
    derivation_id: str
    axis_id: str
    shape: str
    axis: PeriodAxis
    derivation: Derivation
    cells: tuple[PanelCell, ...]
    summary: PanelStatus
    research_result: PanelResearchResult

    def _base_dict(self) -> dict[str, object]:
        return {
            "panel_id": self.panel_id,
            "panel_definition_id": self.panel_definition_id,
            "metric_engine_version_id": self.metric_engine_version_id,
            "metric_key": self.metric_key,
            "formula_id": self.formula_id,
            "derivation_id": self.derivation_id,
            "axis_id": self.axis_id,
            "shape": self.shape,
            "axis": self.axis.to_dict(),
            "cells": [c.to_dict() for c in self.cells],
            "summary": self.summary.to_dict(),
            "research_result": self.research_result.to_dict(),
        }

    def _member_ids(self) -> tuple[str, ...]:
        """The distinct member ``company_id``s, in first-seen cell order."""
        ordered: list[str] = []
        seen: set[str] = set()
        for cell in self.cells:
            if cell.company_id not in seen:
                seen.add(cell.company_id)
                ordered.append(cell.company_id)
        return tuple(ordered)


@dataclass(frozen=True, slots=True)
class PitPanel(_PanelBase):
    """A panel knowable as of a historical instant (or an as_of axis) — **PIT** (§2).

    A distinct type from :class:`RevisedPanel` (Decision D5, invariant 28): a future
    backtester typed to ``PitPanel`` structurally cannot consume revised history.
    For the period-series and cross-section shapes every cell shares one ``as_of``
    (:attr:`as_of`); for the vintage shape the coordinates walk an ``as_of`` axis
    (:attr:`as_of_axis`) and :attr:`as_of` is ``None``.
    """

    as_of: datetime | None = field(default=None, kw_only=True)
    as_of_axis: tuple[datetime, ...] = field(default=(), kw_only=True)

    def to_dict(self) -> dict[str, object]:
        data = self._base_dict()
        data["mode"] = "pit"
        data["as_of"] = format_utc_z(self.as_of) if self.as_of is not None else None
        data["as_of_axis"] = [format_utc_z(a) for a in self.as_of_axis]
        return data


@dataclass(frozen=True, slots=True)
class RevisedPanel(_PanelBase):
    """The latest panel over a pinned universe/filer-wide snapshot — **REVISED** (§2).

    Deliberately *not* interchangeable with :class:`PitPanel`. Supports only the
    period-series and cross-section shapes — REVISED has no ``as_of`` axis, so a
    "revised vintage" is a category error rejected at the engine (§3.1). To use a
    revised panel in a PIT context the caller must call :meth:`reinterpret_as_pit`
    with an explicit ``as_of`` — an auditable, re-evaluating conversion that re-runs
    the whole panel and never reuses a revised cell (§1.1, invariant 28).
    """

    dataset_version_id: str = field(kw_only=True)

    def to_dict(self) -> dict[str, object]:
        data = self._base_dict()
        data["mode"] = "revised"
        data["dataset_version_id"] = self.dataset_version_id
        return data

    def reinterpret_as_pit(self, engine: object, as_of: datetime) -> PitPanel:
        """Explicit, auditable conversion to a PIT panel at ``as_of`` (§1.1, §3).

        Does **not** reuse the revised cells; it re-runs the whole panel evaluation
        at ``as_of`` over the same member(s), axis, and derivation, so the result
        genuinely reflects what was knowable then. ``engine`` is a
        :class:`~quantforge.panel.engine.PanelEngine`; typed as ``object`` here only
        to avoid a module import cycle.
        """
        from quantforge.panel.engine import PanelEngine

        if not isinstance(engine, PanelEngine):
            raise TypeError("reinterpret_as_pit requires a PanelEngine")
        members = self._member_ids()
        if self.shape == PanelShape.CROSS_SECTION.value:
            from quantforge.factors.universe import Universe

            universe = Universe(members=members)
            return engine.panel_across(
                self.metric_key,
                universe,
                self.axis,
                as_of,
                derivation=self.derivation,
            )
        # Per-filer period-series: exactly one member.
        from quantforge.registry.identity import cik_from_company_id

        cik = cik_from_company_id(members[0])
        return engine.panel_as_of(
            self.metric_key, cik, self.axis, as_of, derivation=self.derivation
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


def _req_int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an int")
    return value
