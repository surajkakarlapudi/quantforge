"""Offline, obviously-synthetic fixtures for Phase 16 signal-diagnostics tests.

A signal-diagnostics integration test needs the *same* combined corpus a backtest does —
SEC fundamentals (filings → canonical facts → metrics) fused with market bars, each
synthetic filer's fundamentals ``company_id`` matching its market ``security_id`` — so
we reuse :func:`tests.backtest.builders.populate` verbatim and only add a richer
default price history (so several evaluation dates each have a valid forward-return
window) plus a :class:`~quantforge.diagnostics.spec.SignalDiagnosticsSpecification`
assembler that pins both corpora exactly as a real caller does.

The default corpus (from ``tests/backtest/builders``): two fictional filers, filer A
with ``current_ratio`` = ``2`` and filer B with ``current_ratio`` = ``4`` (both
PIT-known from late 2023). Here we give them monthly closes that rise at *different*
rates, so the
signal (``current_ratio``) and the realized forward return are genuinely, hand-checkably
(anti-)correlated — the higher-ratio filer B posts the *smaller* forward return, so the
per-date IC is a clean ``-1`` and every statistic is verifiable by hand.
"""

from __future__ import annotations

from pathlib import Path

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.diagnostics.engine import SignalDiagnosticsEngine
from quantforge.diagnostics.spec import SignalDiagnosticsSpecification
from quantforge.metrics.model import MetricPeriod
from tests.backtest.builders import (
    CIK_A,
    CIK_B,
    Corpus,
    populate,
)
from tests.backtest.builders import (
    PERIOD as SIGNAL_PERIOD,
)
from tests.backtest.builders import (
    universe_spec as _universe_spec,
)
from tests.market.builders import bar

# The signal period (the instant fiscal period ``current_ratio`` is ranked at) and the
# universe assembler come straight from the backtest builders — one shared corpus shape.
PERIOD: MetricPeriod = SIGNAL_PERIOD
universe_spec = _universe_spec


# Four monthly closes per security. A rises 10 → 11 → 12 → 13 (bigger relative steps);
# B rises 20 → 21 → 22 → 23 (smaller relative steps). So on every
# one-trading-day-forward window the lower-ratio filer A out-returns the higher-ratio
# filer B — a clean, constant, perfectly (anti-)ranked cross-section.
def default_bars_a() -> list[dict[str, object]]:
    return [
        bar("2024-01-10", close="10"),
        bar("2024-02-10", close="11"),
        bar("2024-03-10", close="12"),
        bar("2024-04-10", close="13"),
    ]


def default_bars_b() -> list[dict[str, object]]:
    return [
        bar("2024-01-10", close="20"),
        bar("2024-02-10", close="21"),
        bar("2024-03-10", close="22"),
        bar("2024-04-10", close="23"),
    ]


# Two evaluation instants; each picks a base close and (with a 1-trading-day horizon
# over the stored axis) a distinct valid forward window:
#   T1 = 2024-01-15 → base 2024-01-10, end 2024-02-10;
#   T2 = 2024-02-15 → base 2024-02-10, end 2024-03-10.
EVAL_1 = "2024-01-15T00:00:00Z"
EVAL_2 = "2024-02-15T00:00:00Z"


def default_schedule() -> RebalanceSchedule:
    return RebalanceSchedule.of([EVAL_1, EVAL_2])


def populate_diagnostics(
    root: Path,
    *,
    bars_a: list[dict[str, object]] | None = None,
    bars_b: list[dict[str, object]] | None = None,
    include_b: bool = True,
    market_a: bool = True,
    market_b: bool = True,
) -> Corpus:
    """Populate the combined corpus with the richer diagnostics price history.

    Thin wrapper over :func:`tests.backtest.builders.populate` that swaps in the
    four-bar default histories (so multiple evaluation dates each resolve a forward
    window) while
    leaving every fundamentals default untouched.
    """
    return populate(
        root,
        bars_a=default_bars_a() if bars_a is None else bars_a,
        bars_b=default_bars_b() if bars_b is None else bars_b,
        include_b=include_b,
        market_a=market_a,
        market_b=market_b,
    )


def diagnostics_engine(corpus: Corpus) -> SignalDiagnosticsEngine:
    """The workspace's Phase 16 engine, narrowed from the ``object`` property."""
    engine = corpus.workspace.signal_diagnostics_engine
    assert isinstance(engine, SignalDiagnosticsEngine)
    return engine


def make_spec(
    engine: SignalDiagnosticsEngine,
    *,
    signal: str = "current_ratio",
    forward_horizon: str = "1d",
    quantiles: int = 2,
    schedule: RebalanceSchedule | None = None,
    ic_methods: tuple[str, ...] = ("spearman", "pearson"),
    include_b: bool = True,
    name: str = "phase16-synthetic",
) -> SignalDiagnosticsSpecification:
    """Assemble a fully pinned :class:`SignalDiagnosticsSpecification` for the corpus.

    Pins are re-derived from the engine exactly as a real caller does: a throwaway spec
    with placeholder pins gives the source company ids, from which the true fundamentals
    + market dataset-version ids are computed and folded into the final spec (so
    ``evaluate`` re-derives them and SD-1 verification passes).
    """
    universe = universe_spec(include_b=include_b)
    sched = schedule or default_schedule()

    def _spec(fundamentals_id: str, market_id: str) -> SignalDiagnosticsSpecification:
        return SignalDiagnosticsSpecification(
            name=name,
            signal=signal,
            period=PERIOD,
            universe=universe,
            schedule=sched,
            forward_horizon=forward_horizon,
            quantiles=quantiles,
            dataset_version_id=fundamentals_id,
            market_dataset_version_id=market_id,
            ic_methods=ic_methods,
        )

    placeholder = _spec("pending", "pending")
    fundamentals_id = engine.fundamentals_dataset_version(
        placeholder
    ).dataset_version_id
    market_id = engine.market_dataset_version(placeholder).dataset_version_id
    return _spec(fundamentals_id, market_id)


__all__ = [
    "CIK_A",
    "CIK_B",
    "EVAL_1",
    "EVAL_2",
    "PERIOD",
    "Corpus",
    "default_bars_a",
    "default_bars_b",
    "default_schedule",
    "diagnostics_engine",
    "make_spec",
    "populate_diagnostics",
    "universe_spec",
]
