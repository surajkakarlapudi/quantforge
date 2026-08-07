"""Deterministic builders for Phase 8 factor tests.

Construct a minimal :class:`ResearchResult` (and its parts) without the full
pipeline, so the store and model round-trip tests have a hand-built, byte-stable
fixture. Everything is a pure function of its inputs — no wall-clock, no network.
"""

from __future__ import annotations

from quantforge.factors.model import FactorStatus, ResearchResult
from quantforge.metrics.model import MetricPeriod


def research_result(
    *,
    research_result_id: str = "sha256:rr",
    boundary_kind: str = "pit",
    boundary_value: str = "2023-11-05T21:30:00Z",
    as_of_timestamp: str | None = "2023-11-05T21:30:00Z",
    dataset_version_id: str = "sha256:dv",
) -> ResearchResult:
    """A minimal, fully-populated :class:`ResearchResult` for store/model tests."""
    return ResearchResult(
        research_result_id=research_result_id,
        factor_definition_id="sha256:def",
        metric_engine_version_id="sha256:engine",
        metric_key="current_ratio",
        formula_id="sha256:formula",
        transform_id="none",
        universe_id="sha256:universe",
        period=MetricPeriod.instant("2023-09-30"),
        boundary_kind=boundary_kind,
        boundary_value=boundary_value,
        dataset_version_id=dataset_version_id,
        as_of_timestamp=as_of_timestamp,
        summary=FactorStatus(
            total=2, known=1, undefined_by_reason={"missing_input": 1}
        ),
        result_hash="sha256:result",
    )
