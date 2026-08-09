"""The comparative-research orchestration engine (locked §3, §5, D1).

:class:`ExperimentEngine` sits strictly **above** Phase 12: it is a pure consumer that
turns a declarative :class:`~quantforge.experiment.spec.ExperimentSpecification` into a
sealed :class:`~quantforge.experiment.result.ExperimentResult` by *orchestrating* the
Phase 12 :class:`~quantforge.backtest.engine.BacktestEngine` over the expanded sweep. It
introduces no new data-resolution logic, no new arithmetic, and no new store: every
child backtest is run by the existing engine, sealed PIT-correctly to the shared
research sidecar, and the experiment record is a thin, content-addressed index over
those children (locked §1, D4).

The run (locked §3.3):

1. **Expand** the spec into its deterministic family of ``(coordinate, child_spec)``
   pairs (:meth:`~quantforge.experiment.spec.ExperimentSpecification.expand`). Corpus
   pins are inherited verbatim by construction (locked D2).
2. **Run each child** through :meth:`BacktestEngine.run`, threading the experiment's
   annualization convention unchanged to every child (locked D5). The backtest engine
   seals each :class:`~quantforge.backtest.result.BacktestResult` write-once to the
   shared sidecar; re-running an identical experiment re-derives byte-identical
   children, so the write is an idempotent no-op (reuse is by determinism + write-once,
   never a
   pre-run ``store.has`` guess — a child ``backtest_id`` folds its own ``result_hash``
   and so is only knowable *after* the run).
3. **Seal** the ordered ``(coordinate, backtest_id)`` ledger into an
   :class:`ExperimentResult` and persist it write-once to the same sidecar.

The engine holds no mutable per-run state — a run's state lives entirely in local
variables, so one engine can run many specifications and two runs of the same spec are
byte-identical.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from quantforge.backtest.engine import BacktestEngine
from quantforge.experiment.errors import ExperimentConfigurationError
from quantforge.experiment.identity import (
    experiment_engine_version_id as _engine_version_id,
)
from quantforge.experiment.result import ExperimentResult, ExperimentRun
from quantforge.experiment.spec import ExperimentSpecification
from quantforge.factors.store import ResearchResultStore
from quantforge.workspace import Workspace

__all__ = ["ExperimentEngine"]


class ExperimentEngine:
    """Orchestrate a declarative sweep into a sealed experiment result (§3, D1).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's cached Phase 12
    :class:`~quantforge.backtest.engine.BacktestEngine` and the shared Phase 8 research
    sidecar. The backtest engine may be overridden (for tests). The engine performs no
    numeric derivation of its own — its version folds only its domain tag (§4).
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        backtest_engine: BacktestEngine | None = None,
    ) -> None:
        self._workspace = workspace
        be = (
            backtest_engine
            if backtest_engine is not None
            else workspace.backtest_engine
        )
        assert isinstance(be, BacktestEngine)  # the workspace builds exactly this
        self._backtest_engine = be
        self._version_id = _engine_version_id()

    @property
    def experiment_engine_version_id(self) -> str:
        """The engine-logic version folded into every experiment id (§4)."""
        return self._version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The shared write-once sidecar the sealed experiment persists to (D4)."""
        return self._backtest_engine._factor_engine.research_store

    def run(
        self,
        spec: ExperimentSpecification,
        *,
        risk_free_per_period: str = "0",
        periods_per_year: str = "1",
    ) -> ExperimentResult:
        """Expand, run every child, and seal the experiment result (§3.3, D5).

        ``risk_free_per_period`` and ``periods_per_year`` are the annualization
        convention threaded **unchanged** to every child backtest (locked D5): they are
        a run argument, never a sweep axis, so every member of one experiment reports
        commensurable statistics. They are also folded into ``experiment_id`` (they
        change each child's reported Sharpe and ``backtest_id``), so two experiments
        identical except for their convention get distinct ids and never collide.

        Deterministic and reproducible: the same spec + same convention re-derives
        byte-identical children (whose sidecar writes are idempotent no-ops) and an
        identical :class:`ExperimentResult` on any machine.
        """
        if not isinstance(spec, ExperimentSpecification):
            raise ExperimentConfigurationError(
                "run() requires an ExperimentSpecification"
            )

        # Canonicalize the recorded convention once, so the experiment id, the stored
        # record, and every child backtest fold in byte-identical strings ("0" and "0.0"
        # can never disagree) — exactly as the backtest engine canonicalizes its own.
        canonical_rf = _canonical_decimal(risk_free_per_period, "risk_free_per_period")
        canonical_ppy = _canonical_decimal(periods_per_year, "periods_per_year")

        family = spec.expand()
        runs: list[ExperimentRun] = []
        for coordinate, child_spec in family:
            result = self._backtest_engine.run(
                child_spec,
                risk_free_per_period=canonical_rf,
                periods_per_year=canonical_ppy,
            )
            runs.append(
                ExperimentRun(coordinate=coordinate, backtest_id=result.backtest_id)
            )

        experiment_id = spec.experiment_id(
            risk_free_per_period=canonical_rf,
            periods_per_year=canonical_ppy,
        )
        experiment = ExperimentResult.seal(
            experiment_id=experiment_id,
            experiment_engine_version_id=self._version_id,
            base_backtest_request=spec.base.to_dict(),
            axis_ids=spec.sorted_axis_ids(),
            runs=tuple(runs),
            risk_free_per_period=canonical_rf,
            periods_per_year=canonical_ppy,
            dataset_version_id=spec.base.dataset_version_id,
            market_dataset_version_id=spec.base.market_dataset_version_id,
        )
        # Persist write-once to the shared research sidecar (D4). Idempotent for a
        # byte-identical re-run; a differing payload under the same id raises there.
        self.research_store.write(experiment)
        return experiment


def _canonical_decimal(value: str, field: str) -> str:
    """Canonicalize a decimal-string run argument; fail closed on a non-decimal.

    Mirrors the backtest engine's ``str(+Decimal(...))`` canonicalization so the
    experiment threads the child backtests the exact strings they fold into their own
    ``backtest_id``. A malformed convention is a configuration defect, raised.
    """
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ExperimentConfigurationError(
            f"{field} {value!r} is not a valid decimal string"
        ) from exc
    if not parsed.is_finite():
        raise ExperimentConfigurationError(f"{field} {value!r} must be finite")
    return str(+parsed)
