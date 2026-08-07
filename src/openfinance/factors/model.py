"""The cross-sectional factor result model (``docs/factors.md`` §5, §7, §9).

A **factor** is *one metric, evaluated across one ordered universe, for one fiscal
period, at one knowledge-state boundary*. This module defines:

* :class:`FactorCell` — one universe member's contribution: the full Phase 7
  metric result (``KNOWN`` with provenance, or ``UNDEFINED`` with a reason — never
  ``None``, never dropped) plus the optional transform output for that cell (§5).
* :class:`FactorStatus` — per-reason cell counts, so "how many filers resolved,
  and why not the rest?" is answerable without walking every cell (§9).
* :class:`ResearchResult` — the reproducible provenance record data-model §9
  reserved: ``factor_definition_id`` + ``factor_version`` (≡
  ``metric_engine_version_id``), ``query_params`` (universe/metric/period/transform),
  the boundary, the ``DatasetVersion``, and the ``result_hash`` (§7).
* :class:`PitFactor` / :class:`RevisedFactor` — **distinct** frozen result types
  (Decision F5), extending invariant 28 to the cross-section: a consumer typed to
  ``PitFactor`` structurally cannot be handed a revised factor.

Every field is deterministically serializable (``to_dict``); no wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

from openfinance.availability.timestamps import format_utc_z, parse_utc
from openfinance.factors.transform import Transform, TransformKind
from openfinance.metrics.model import (
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)

__all__ = [
    "FactorCell",
    "FactorStatus",
    "PitFactor",
    "ResearchResult",
    "RevisedFactor",
]


@dataclass(frozen=True, slots=True)
class FactorCell:
    """One universe member's contribution to a factor (§5).

    ``metric`` is the full Phase 7 metric result for the filer — ``KNOWN`` (value +
    provenance) or ``UNDEFINED`` (reason + provenance) — never ``None`` and never
    dropped. ``transformed_value_numeric_str`` is the cross-sectional transform
    output for this cell (Decision F3), exact ``Decimal`` serialized; ``None`` when
    the cell is ``UNDEFINED``, no transform was applied, or the transform left this
    cell undefined (a degenerate population, §6.2).
    """

    company_id: str
    metric: PitMetricValue | RevisedMetricValue
    transformed_value_numeric_str: str | None = None

    @property
    def status(self) -> MetricStatus:
        return self.metric.status

    @property
    def is_known(self) -> bool:
        return self.metric.status is MetricStatus.KNOWN

    def to_dict(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "metric": self.metric.to_dict(),
            "transformed_value_numeric": self.transformed_value_numeric_str,
        }

    def outcome_digest(self) -> dict[str, object]:
        """The minimal per-cell fingerprint hashed into ``result_hash`` (§7).

        Names the member, its resolved status/value/reason, and the transformed
        value — the load-bearing *output* of the cell. It deliberately omits the
        full provenance (which is reproducible from the same request), keeping the
        hash a stable function of the answer, not of the audit chain's layout.
        """
        return {
            "company_id": self.company_id,
            "status": self.metric.status.value,
            "value_numeric": self.metric.value_numeric_str,
            "unit": self.metric.unit,
            "reason": self.metric.reason.value if self.metric.reason else None,
            "transformed_value_numeric": self.transformed_value_numeric_str,
        }


@dataclass(frozen=True, slots=True)
class FactorStatus:
    """Per-reason cell counts across the universe — an audit summary (§9).

    ``known`` counts the ``KNOWN`` cells; ``undefined_by_reason`` maps each
    :class:`UndefinedReason` value that occurred to its count. ``total`` is the
    universe size (every member is a cell). Deterministic: reasons are emitted
    sorted.
    """

    total: int
    known: int
    undefined_by_reason: dict[str, int]

    @classmethod
    def from_cells(cls, cells: tuple[FactorCell, ...]) -> FactorStatus:
        """Summarize a cell tuple into per-reason counts (deterministic)."""
        known = 0
        by_reason: dict[str, int] = {}
        for cell in cells:
            if cell.metric.status is MetricStatus.KNOWN:
                known += 1
                continue
            reason = cell.metric.reason
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
    def from_dict(cls, raw: dict[str, object]) -> FactorStatus:
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
class ResearchResult:
    """The reproducible provenance record for a cross-sectional factor (§7, §9).

    Realizes data-model §9's reserved ``ResearchResult``. ``factor_definition_id``
    ≡ §9 ``factor_definition_id``; ``metric_engine_version_id`` ≡ §9
    ``factor_version``. ``strategy_version`` is deliberately absent — reserved for
    the deferred backtester (§1.2). ``query_params`` records the universe / metric /
    period / transform. ``result_hash`` fingerprints the ordered cell outcomes, so
    ``research_result_id`` pins both the request and the output.
    """

    research_result_id: str
    factor_definition_id: str
    metric_engine_version_id: str
    metric_key: str
    formula_id: str
    transform_id: str
    universe_id: str
    period: MetricPeriod
    boundary_kind: str
    boundary_value: str
    dataset_version_id: str
    as_of_timestamp: str | None
    summary: FactorStatus
    result_hash: str

    @property
    def query_params(self) -> dict[str, object]:
        """The §9 ``query_params`` — universe / metric / period / transform."""
        return {
            "metric_key": self.metric_key,
            "universe_id": self.universe_id,
            "period": self.period.to_dict(),
            "transform": self.transform_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "research_result_id": self.research_result_id,
            "factor_definition_id": self.factor_definition_id,
            # §9 alias: metric_engine_version_id IS the factor_version.
            "factor_version": self.metric_engine_version_id,
            "metric_engine_version_id": self.metric_engine_version_id,
            "metric_key": self.metric_key,
            "formula_id": self.formula_id,
            "transform_id": self.transform_id,
            "universe_id": self.universe_id,
            "period": self.period.to_dict(),
            "boundary_kind": self.boundary_kind,
            "boundary_value": self.boundary_value,
            "dataset_version_id": self.dataset_version_id,
            "as_of_timestamp": self.as_of_timestamp,
            "query_params": self.query_params,
            "summary": self.summary.to_dict(),
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ResearchResult:
        period_raw = raw["period"]
        if not isinstance(period_raw, dict):
            raise ValueError("period must be an object")
        summary_raw = raw["summary"]
        if not isinstance(summary_raw, dict):
            raise ValueError("summary must be an object")
        return cls(
            research_result_id=_req_str(raw, "research_result_id"),
            factor_definition_id=_req_str(raw, "factor_definition_id"),
            metric_engine_version_id=_req_str(raw, "metric_engine_version_id"),
            metric_key=_req_str(raw, "metric_key"),
            formula_id=_req_str(raw, "formula_id"),
            transform_id=_req_str(raw, "transform_id"),
            universe_id=_req_str(raw, "universe_id"),
            period=_period_from_dict(period_raw),
            boundary_kind=_req_str(raw, "boundary_kind"),
            boundary_value=_req_str(raw, "boundary_value"),
            dataset_version_id=_req_str(raw, "dataset_version_id"),
            as_of_timestamp=_opt_str(raw, "as_of_timestamp"),
            summary=FactorStatus.from_dict(summary_raw),
            result_hash=_req_str(raw, "result_hash"),
        )


@dataclass(frozen=True, slots=True)
class _FactorBase:
    """Fields shared by the PIT and REVISED factor result types (§5)."""

    research_result_id: str
    factor_definition_id: str
    metric_engine_version_id: str
    metric_key: str
    formula_id: str
    transform_id: str
    universe_id: str
    period: MetricPeriod
    cells: tuple[FactorCell, ...]
    summary: FactorStatus
    research_result: ResearchResult

    def _base_dict(self) -> dict[str, object]:
        return {
            "research_result_id": self.research_result_id,
            "factor_definition_id": self.factor_definition_id,
            "metric_engine_version_id": self.metric_engine_version_id,
            "metric_key": self.metric_key,
            "formula_id": self.formula_id,
            "transform_id": self.transform_id,
            "universe_id": self.universe_id,
            "period": self.period.to_dict(),
            "cells": [c.to_dict() for c in self.cells],
            "summary": self.summary.to_dict(),
            "research_result": self.research_result.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PitFactor(_FactorBase):
    """A cross-sectional factor knowable as of a historical instant — **PIT** (§5).

    A distinct type from :class:`RevisedFactor` (Decision F5, invariant 28): a
    backtester typed to ``PitFactor`` structurally cannot consume revised history.
    Every cell is a :class:`PitMetricValue` resolved at the same ``as_of`` (§5.1).
    """

    as_of: datetime = field(kw_only=True)

    def to_dict(self) -> dict[str, object]:
        data = self._base_dict()
        data["mode"] = "pit"
        data["as_of"] = format_utc_z(self.as_of)
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PitFactor:
        base = _factor_base_from_dict(raw, PitMetricValue.from_dict)
        as_of_raw = raw["as_of"]
        if not isinstance(as_of_raw, str):
            raise ValueError("as_of must be a string")
        return cls(as_of=parse_utc(as_of_raw), **base)


@dataclass(frozen=True, slots=True)
class RevisedFactor(_FactorBase):
    """The latest cross-section over a pinned universe-wide snapshot — **REVISED** (§5).

    Deliberately *not* interchangeable with :class:`PitFactor`. Every cell is a
    :class:`RevisedMetricValue` resolved over the **same** universe-wide
    ``DatasetVersion`` (§8.1). To use a revised factor in a PIT context the caller
    must call :meth:`reinterpret_as_pit` with an explicit ``as_of`` — an auditable,
    re-evaluating conversion, never an implicit cast (§5.2, invariant 28).
    """

    dataset_version_id: str = field(kw_only=True)

    def to_dict(self) -> dict[str, object]:
        data = self._base_dict()
        data["mode"] = "revised"
        data["dataset_version_id"] = self.dataset_version_id
        return data

    def reinterpret_as_pit(self, engine: object, as_of: datetime) -> PitFactor:
        """Explicit, auditable conversion to a PIT factor at ``as_of`` (§5.2).

        This does **not** reuse the revised cells; it re-runs the whole
        cross-sectional evaluation at ``as_of`` over the same universe (§5.2), so
        the result genuinely reflects what was knowable then. ``engine`` is a
        :class:`~openfinance.factors.engine.FactorEngine`; typed as ``object`` here
        only to avoid a module import cycle.
        """
        from openfinance.factors.engine import FactorEngine
        from openfinance.factors.universe import Universe

        if not isinstance(engine, FactorEngine):
            raise TypeError("reinterpret_as_pit requires a FactorEngine")
        universe = Universe(members=tuple(c.company_id for c in self.cells))
        transform = _transform_from_id(self.transform_id)
        return engine.factor_as_of(
            self.metric_key, universe, self.period, as_of, transform=transform
        )

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RevisedFactor:
        base = _factor_base_from_dict(raw, RevisedMetricValue.from_dict)
        dv_raw = raw["dataset_version_id"]
        if not isinstance(dv_raw, str):
            raise ValueError("dataset_version_id must be a string")
        return cls(dataset_version_id=dv_raw, **base)


class _FactorBaseFields(TypedDict):
    """The shared factor fields, typed so ``**base`` unpacking is checkable."""

    research_result_id: str
    factor_definition_id: str
    metric_engine_version_id: str
    metric_key: str
    formula_id: str
    transform_id: str
    universe_id: str
    period: MetricPeriod
    cells: tuple[FactorCell, ...]
    summary: FactorStatus
    research_result: ResearchResult


def _transform_from_id(transform_id: str) -> Transform:
    """Reconstruct a :class:`Transform` from its canonical id (for reinterpret)."""
    if transform_id == TransformKind.WINSORIZE.value or transform_id.startswith(
        f"{TransformKind.WINSORIZE.value}:"
    ):
        _, lower, upper = transform_id.split(":")
        return Transform.winsorize(lower, upper)
    return Transform(TransformKind(transform_id))


def _factor_base_from_dict(
    raw: dict[str, object],
    metric_from_dict: Callable[
        [dict[str, object]], PitMetricValue | RevisedMetricValue
    ],
) -> _FactorBaseFields:
    """Reconstruct the shared factor fields from a serialized dict."""
    period_raw = raw["period"]
    if not isinstance(period_raw, dict):
        raise ValueError("period must be an object")
    summary_raw = raw["summary"]
    if not isinstance(summary_raw, dict):
        raise ValueError("summary must be an object")
    rr_raw = raw["research_result"]
    if not isinstance(rr_raw, dict):
        raise ValueError("research_result must be an object")
    cells_raw = raw.get("cells", [])
    cells: list[FactorCell] = []
    if isinstance(cells_raw, list):
        for item in cells_raw:
            if not isinstance(item, dict):
                continue
            metric_raw = item["metric"]
            if not isinstance(metric_raw, dict):
                raise ValueError("cell metric must be an object")
            cells.append(
                FactorCell(
                    company_id=_req_str(item, "company_id"),
                    metric=metric_from_dict(metric_raw),
                    transformed_value_numeric_str=_opt_str(
                        item, "transformed_value_numeric"
                    ),
                )
            )
    return _FactorBaseFields(
        research_result_id=_req_str(raw, "research_result_id"),
        factor_definition_id=_req_str(raw, "factor_definition_id"),
        metric_engine_version_id=_req_str(raw, "metric_engine_version_id"),
        metric_key=_req_str(raw, "metric_key"),
        formula_id=_req_str(raw, "formula_id"),
        transform_id=_req_str(raw, "transform_id"),
        universe_id=_req_str(raw, "universe_id"),
        period=_period_from_dict(period_raw),
        cells=tuple(cells),
        summary=FactorStatus.from_dict(summary_raw),
        research_result=ResearchResult.from_dict(rr_raw),
    )


def _period_from_dict(raw: dict[str, object]) -> MetricPeriod:
    from openfinance.xbrl.contexts import PeriodType

    return MetricPeriod(
        period_type=PeriodType(_req_str(raw, "period_type")),
        period_start=_opt_str(raw, "period_start"),
        period_end=_opt_str(raw, "period_end"),
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


# `UndefinedReason` is re-exported implicitly via FactorStatus keys; import kept so
# the reason vocabulary is a documented dependency of this module.
_ = UndefinedReason
