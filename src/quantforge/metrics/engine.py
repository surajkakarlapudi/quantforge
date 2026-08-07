"""The :class:`MetricEngine` façade — compose Phase 4 + Phase 5, evaluate (§4, §11).

The engine is the metric layer's I/O boundary. It:

1. looks a formula up by ``metric_key`` in the :class:`FormulaRegistry` (fail-closed
   on unknown, §6);
2. obtains a Phase 5 :class:`~quantforge.availability.resolve.PointInTimeResolver`
   for the filer from the existing :class:`AvailabilityIngestor` — deriving the
   sidecar availability first (idempotent, deterministic, offline) — never
   re-implementing eligibility or restatement ordering;
3. hands the filer's facts + resolver + boundary to the **pure**
   :class:`~quantforge.metrics.evaluate.MetricEvaluator`.

It mirrors the Phase 4 ``Canonicalizer``-vs-``Ingestor`` and Phase 5
``derive``-vs-``AvailabilityIngestor`` split: arithmetic is pure and lives in the
evaluator; the engine only reads/derives. It introduces **no** new store — metrics
are computed on demand (Decision D1) — and keeps PIT/REVISED impossible to confuse:
two methods, no default mode (invariant 27), returning the two distinct types.
"""

from __future__ import annotations

from datetime import datetime

from quantforge.availability.ingest import AvailabilityIngestor
from quantforge.availability.version import DatasetVersion
from quantforge.canonical.model import Fact
from quantforge.canonical.version import CanonicalFactVersion
from quantforge.metrics.evaluate import MetricEvaluator
from quantforge.metrics.model import (
    MetricPeriod,
    PitMetricValue,
    RevisedMetricValue,
)
from quantforge.metrics.registry import FormulaRegistry
from quantforge.metrics.resolve_input import MetricBoundary
from quantforge.metrics.version import MetricEngineVersion
from quantforge.registry.identity import company_id as _company_id
from quantforge.workspace import Workspace

__all__ = ["MetricEngine"]


class MetricEngine:
    """Evaluate versioned formulas for one filer, composing Phases 4 & 5 (§11).

    Constructed from a :class:`Workspace` (the composition root). The registry and
    engine version may be overridden (e.g. for tests or a pinned decimal context);
    both default to the locked Phase 7 configuration.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        registry: FormulaRegistry | None = None,
        engine_version: MetricEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._registry = registry or FormulaRegistry()
        self._version = engine_version or MetricEngineVersion()
        self._evaluator = MetricEvaluator(self._version)

    @property
    def registry(self) -> FormulaRegistry:
        return self._registry

    @property
    def engine_version(self) -> MetricEngineVersion:
        return self._version

    # -- PIT / REVISED metric API -------------------------------------------

    def metric_as_of(
        self,
        metric_key: str,
        cik: str | int,
        period: MetricPeriod,
        as_of: datetime,
    ) -> PitMetricValue:
        """Compute the point-in-time metric for one filer at ``as_of`` (§10, §12).

        ``as_of`` must be timezone-aware — a naive instant is rejected by the
        Phase 5 timestamp choke point (a
        :class:`~quantforge.availability.errors.ModeError`, invariant 15). Returns a
        :class:`PitMetricValue`; an input not yet public at ``as_of`` yields
        ``UNDEFINED(MISSING_INPUT)`` (never an error, §13).
        """
        formula = self._registry.get(metric_key)
        company = _company_id(cik)
        ingestor, facts = self._prepare(cik)
        resolver = ingestor.resolver_for_company(cik)
        boundary = MetricBoundary.pit(as_of)
        return self._evaluator.evaluate_pit(
            formula, company, facts, resolver, period, boundary
        )

    def revised_metric(
        self,
        metric_key: str,
        cik: str | int,
        period: MetricPeriod,
        dataset_version: DatasetVersion,
    ) -> RevisedMetricValue:
        """Compute the revised metric over a pinned ``dataset_version`` (§10, §12).

        Resolves at the Phase 5 ingestion frontier (reproducible, not a wall-clock
        read) over the pinned snapshot. Returns a :class:`RevisedMetricValue`, which
        is *not* interchangeable with a PIT metric (invariant 28).
        """
        formula = self._registry.get(metric_key)
        company = _company_id(cik)
        ingestor, facts = self._prepare(cik)
        resolver = ingestor.resolver_for_company(cik)
        boundary = MetricBoundary.revised(dataset_version)
        return self._evaluator.evaluate_revised(
            formula, company, facts, resolver, period, boundary
        )

    def dataset_version_for(self, cik: str | int) -> DatasetVersion:
        """Build the reproducible :class:`DatasetVersion` for one filer's REVISED view.

        Convenience over the Phase 5 façade: pins this filer's facts + normalizer +
        availability-policy set, so a caller can obtain the snapshot to pass to
        :meth:`revised_metric` without reaching into Phase 5 internals (§8).
        """
        ingestor, facts = self._prepare(cik)
        transformation_version_id = _transformation_version_of(facts)
        return ingestor.dataset_version_for_company(
            cik, transformation_version_id=transformation_version_id
        )

    # -- composition ---------------------------------------------------------

    def _prepare(self, cik: str | int) -> tuple[AvailabilityIngestor, list[Fact]]:
        """Derive availability (idempotent) and read the filer's facts.

        Building a resolver requires the sidecar availability to exist; deriving it
        is deterministic and offline, so we derive on demand rather than requiring a
        separate pipeline step. Returns the ingestor (for resolver construction) and
        the filer's canonical facts (read once, reused by the evaluator).
        """
        ingestor = self._ingestor()
        ingestor.derive_company(cik)
        company = _company_id(cik)
        facts = self._workspace.canonical_store.read_company(company)
        return ingestor, facts

    def _ingestor(self) -> AvailabilityIngestor:
        """The Phase 5 façade over the workspace's wired stores (§11).

        Reuses the workspace's own cached availability ingestor — wired to
        ``<root>/availability/`` — never a new store. Deriving availability through
        it is deterministic and offline.
        """
        return self._workspace.availability_ingestor


def _transformation_version_of(facts: list[Fact]) -> str:
    """The normalizer version the facts were built under (for the DatasetVersion).

    Every fact of one build shares one ``transformation_version_id``; we read it
    from the facts so a REVISED snapshot pins the *actual* normalizer that produced
    them. Falls back to the current default when the filer has no stored facts (an
    empty snapshot is still reproducible).
    """
    for fact in facts:
        return fact.transformation_version_id
    return CanonicalFactVersion().transformation_version_id
