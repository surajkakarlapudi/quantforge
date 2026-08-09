"""The research-reporting orchestration engine (locked §7, §13, §15, D1).

:class:`ReportEngine` sits strictly **above** Phase 13: it is a pure consumer that turns
a declarative :class:`~quantforge.report.spec.ReportSpecification` into a sealed
:class:`~quantforge.report.result.ResearchReport` by *resolving* the already-sealed
artifacts a report is about, *verifying* them, and sealing a thin, content-addressed
manifest of references. It introduces no new data-resolution logic, no new arithmetic,
and no new store: every referenced artifact was sealed by a lower phase, and the report
record persists write-once to the shared research sidecar (locked §1, §15, D1).

The build (locked §13):

1. **Resolve** the ``subject_id`` from the shared sidecar via
   ``store.read_as(subject_id, <Type>.from_dict)`` — a
   :class:`~quantforge.backtest.result.BacktestResult` for a ``backtest`` scope, an
   :class:`~quantforge.experiment.result.ExperimentResult` for an ``experiment`` scope.
   A missing id is a consistency defect (we refuse to report on an artifact we cannot
   materialize) and raises :class:`~quantforge.report.errors.ReportConsistencyError`
   (fail closed, locked G7).
2. **Verify** the resolved record's own ``research_result_id`` equals the requested
   ``subject_id`` (a corrupt sidecar whose key disagrees with its content fails closed)
   and that its implied boundary agrees with the report's declared ``boundary_kind``
   (v1 records are PIT-only, so the boundary is ``pit``; a disagreement raises — D10).
3. **Recompute** each requested comparison deterministically via
   :meth:`BacktestComparison.of_experiment`, taking its ``comparison_id`` as the
   reference ``content_hash`` (locked D5) — the comparison is never persisted and
   ``experiment/analysis.py`` is never edited.
4. **Seal** the ordered reference manifest into a
   :class:`~quantforge.report.result.ResearchReport` and persist it write-once to the
   same sidecar. Rebuilding an identical report is a byte-identical no-op; a differing
   payload under the same id fails closed via the store's guard (locked §15, D8).

The engine holds no mutable per-run state — a build's state lives entirely in local
variables, so one engine can build many reports and two builds of the same spec over the
same immutable sidecar are byte-identical (locked §16).
"""

from __future__ import annotations

from quantforge.backtest.result import BacktestResult
from quantforge.experiment.analysis import BacktestComparison
from quantforge.experiment.result import ExperimentResult
from quantforge.factors.store import ResearchResultStore
from quantforge.report.errors import ReportConsistencyError
from quantforge.report.identity import (
    report_engine_version_id as _engine_version_id,
)
from quantforge.report.result import (
    BOUNDARY_PIT,
    ReportReference,
    ResearchReport,
)
from quantforge.report.spec import ComparisonDirective, ReportSpecification
from quantforge.workspace import Workspace

__all__ = ["ReportEngine"]

_SCOPE_BACKTEST = "backtest"
_SCOPE_EXPERIMENT = "experiment"

_KIND_BACKTEST = "backtest"
_KIND_EXPERIMENT = "experiment"
_KIND_COMPARISON = "comparison"

_MEMBER_SCOPE_EXPERIMENT_CHILDREN = "experiment_children"


class ReportEngine:
    """Resolve, verify, and seal a declarative report request (§7, §13, D1).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar — the same store the
    backtest and experiment engines sealed their artifacts to — so a report references
    exactly the artifacts already present. The sidecar may be overridden
    (for tests). The
    engine performs no numeric derivation of its own — its version folds only its domain
    tag (§9).
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version_id = _engine_version_id()

    @property
    def report_engine_version_id(self) -> str:
        """The engine-logic version folded into every report id (§9)."""
        return self._version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The shared write-once sidecar the report resolves from and persists to
        (D1)."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def build(self, spec: ReportSpecification) -> ResearchReport:
        """Resolve, verify, seal, and persist a report from ``spec`` (§13, §15).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same artifacts, recomputes the same comparison ids, and seals a
        byte-identical :class:`~quantforge.report.result.ResearchReport` on any machine
        (whose sidecar write is an idempotent no-op). Fails closed on any missing or
        drifted reference (locked G7).
        """
        if not isinstance(spec, ReportSpecification):
            raise ReportConsistencyError("build() requires a ReportSpecification")

        store = self.research_store
        references: list[ReportReference] = []

        if spec.scope == _SCOPE_BACKTEST:
            subject = self._resolve_backtest(spec.subject_id, store)
            references.append(
                ReportReference(
                    kind=_KIND_BACKTEST,
                    reference_id=subject.backtest_id,
                    content_hash=subject.result_hash,
                    detail={},
                )
            )
        elif spec.scope == _SCOPE_EXPERIMENT:
            experiment = self._resolve_experiment(spec.subject_id, store)
            references.append(
                ReportReference(
                    kind=_KIND_EXPERIMENT,
                    reference_id=experiment.experiment_result_id,
                    content_hash=experiment.result_hash,
                    detail={},
                )
            )
            # Comparison directives are recomputed by intent, sorted deterministically
            # so
            # the manifest order never depends on the caller's directive order (§9, D5).
            for directive in _sorted_directives(spec.comparisons):
                references.append(
                    self._comparison_reference(experiment, directive, store)
                )
        else:  # pragma: no cover - ReportSpecification validates the scope first.
            raise ReportConsistencyError(
                f"report scope {spec.scope!r} is not supported"
            )

        report = ResearchReport.seal(
            report_engine_version_id=self._version_id,
            report_spec=spec.to_dict(),
            scope=spec.scope,
            references=tuple(references),
            boundary_kind=BOUNDARY_PIT,
        )
        # Persist write-once to the shared research sidecar (D1). Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(report)
        return report

    # -- resolution & verification -------------------------------------------

    def _resolve_backtest(
        self, subject_id: str, store: ResearchResultStore
    ) -> BacktestResult:
        """Read + verify the subject backtest from the sidecar (fail closed, §13)."""
        result = store.read_as(subject_id, BacktestResult.from_dict)
        if result is None:
            raise ReportConsistencyError(
                f"backtest {subject_id!r} is not present in the research sidecar; "
                "cannot report on an artifact that was never sealed (fail closed)"
            )
        if result.research_result_id != subject_id:
            raise ReportConsistencyError(
                f"backtest {subject_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar "
                "is inconsistent (fail closed)"
            )
        return result

    def _resolve_experiment(
        self, subject_id: str, store: ResearchResultStore
    ) -> ExperimentResult:
        """Read + verify the subject experiment from the sidecar (fail closed, §13)."""
        result = store.read_as(subject_id, ExperimentResult.from_dict)
        if result is None:
            raise ReportConsistencyError(
                f"experiment {subject_id!r} is not present in the research sidecar; "
                "cannot report on an artifact that was never sealed (fail closed)"
            )
        if result.research_result_id != subject_id:
            raise ReportConsistencyError(
                f"experiment {subject_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar "
                "is inconsistent (fail closed)"
            )
        return result

    def _comparison_reference(
        self,
        experiment: ExperimentResult,
        directive: ComparisonDirective,
        store: ResearchResultStore,
    ) -> ReportReference:
        """Recompute a comparison by intent and pin it by ``comparison_id`` (§13, D5).

        The comparison is a pure deterministic function of the experiment's
        already-sealed
        children + ``(statistic, order)``; its ``comparison_id`` already
        content-addresses
        exactly those inputs, so the reference pins it as ``content_hash`` without
        persisting the comparison or editing ``experiment/analysis.py``. A member absent
        from the sidecar fails closed inside
        :meth:`~quantforge.experiment.analysis.BacktestComparison.of_experiment` (locked
        G7); a corpus ``pin_mismatch`` is surfaced by the renderer, never raised here.
        """
        comparison = BacktestComparison.of_experiment(
            experiment,
            store,
            statistic=directive.statistic,
            order=directive.order,
        )
        return ReportReference(
            kind=_KIND_COMPARISON,
            reference_id=comparison.comparison_id,
            content_hash=comparison.comparison_id,
            detail={
                "statistic": directive.statistic,
                "order": directive.order,
                "member_scope": _MEMBER_SCOPE_EXPERIMENT_CHILDREN,
                "comparison_version_id": comparison.comparison_version_id,
            },
        )


def _sorted_directives(
    directives: tuple[ComparisonDirective, ...],
) -> list[ComparisonDirective]:
    """Order the directives deterministically by ``(statistic, order)`` (§9)."""
    return sorted(directives, key=lambda d: (d.statistic, d.order))
