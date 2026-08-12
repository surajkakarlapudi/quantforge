"""Offline, obviously-synthetic fixtures for Phase 25 multiplicity tests.

Phase 25 is a pure consumer of exactly **one** already-sealed
:class:`~quantforge.comparison.result.StrategyComparison`: the engine reads only that
record's KNOWN pairwise ``p`` values (and its UNDEFINED exclusions), never the
strategies beneath it. So - unlike the comparison layer, which must reconstruct a real
walk-forward chain - these builders synthesize a ``StrategyComparison`` **directly**
with hand-chosen per-pair ``p`` values, seal it, and persist it to the shared sidecar.
Every id / hash the synthetic record pins is an obviously-fictional placeholder
(Principle 8): Phase 25 pins the comparison by ``(id, result_hash)`` and never resolves
anything beneath it, so the placeholders are load-bearing for identity only, never
dereferenced.

``make_comparison`` builds the ``n·(n-1)/2`` upper-triangle cells in ``(i < j)`` order,
assigning each the next entry of ``p_values``: a ``str`` is a KNOWN ``p`` value; a
:class:`~quantforge.comparison.model.ComparisonUndefinedReason` is an UNDEFINED cell
(whole pair UNDEFINED for ``INSUFFICIENT_OVERLAP``, an otherwise-KNOWN pair with an
UNDEFINED ``p`` for ``ZERO_DIFFERENCE_VARIANCE``) - so the family-collection and
exclusion paths are both exercised.
"""

from __future__ import annotations

from pathlib import Path

from quantforge.comparison.model import (
    ComparisonStatus,
    ComparisonUndefinedReason,
    StatValue,
    strategy_label,
)
from quantforge.comparison.result import (
    BOUNDARY_PIT,
    ComparisonCell,
    Coverage,
    StrategyComparison,
    TrialSummary,
)
from quantforge.multiplicity.engine import MultipleComparisonEngine
from quantforge.multiplicity.spec import MultipleComparisonSpecification
from quantforge.workspace import Workspace

__all__ = [
    "make_comparison",
    "make_spec",
    "multiplicity_engine",
    "workspace",
]


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def multiplicity_engine(ws: Workspace) -> MultipleComparisonEngine:
    """The workspace's Phase 25 engine, narrowed from the ``object`` property."""
    engine = ws.multiplicity_engine
    assert isinstance(engine, MultipleComparisonEngine)
    return engine


def _pair_cell(
    i: int, j: int, entry: str | ComparisonUndefinedReason
) -> ComparisonCell:
    """One upper-triangle cell: a KNOWN ``p`` value, or an UNDEFINED exclusion."""
    label_i, label_j = strategy_label(i), strategy_label(j)
    # ComparisonUndefinedReason is a StrEnum (hence also a str), so test it first.
    if not isinstance(entry, ComparisonUndefinedReason):
        known = StatValue.known(entry)
        return ComparisonCell(
            i=i,
            j=j,
            label_i=label_i,
            label_j=label_j,
            status=ComparisonStatus.KNOWN,
            overlap_periods=12,
            mean_diff=StatValue.known("0.001"),
            stderr_diff=StatValue.known("0.0005"),
            t_stat=StatValue.known("2.0"),
            p_value=known,
            sharpe_diff=StatValue.known("0.1"),
            reason=None,
        )
    # An UNDEFINED p value: excluded from the family, recorded with its reason.
    undefined = StatValue.undefined(entry)
    if entry is ComparisonUndefinedReason.ZERO_DIFFERENCE_VARIANCE:
        # A KNOWN pair (defined mean) whose t / p are UNDEFINED (zero variance).
        return ComparisonCell(
            i=i,
            j=j,
            label_i=label_i,
            label_j=label_j,
            status=ComparisonStatus.KNOWN,
            overlap_periods=12,
            mean_diff=StatValue.known("0.0"),
            stderr_diff=StatValue.known("0.0"),
            t_stat=undefined,
            p_value=undefined,
            sharpe_diff=StatValue.known("0.0"),
            reason=None,
        )
    # A wholly UNDEFINED pair (too little overlap): every cell UNDEFINED.
    return ComparisonCell(
        i=i,
        j=j,
        label_i=label_i,
        label_j=label_j,
        status=ComparisonStatus.UNDEFINED,
        overlap_periods=0,
        mean_diff=undefined,
        stderr_diff=undefined,
        t_stat=undefined,
        p_value=undefined,
        sharpe_diff=undefined,
        reason=entry,
    )


def make_comparison(
    ws: Workspace,
    *,
    n_strategies: int,
    p_values: list[str | ComparisonUndefinedReason],
    name: str = "synthetic-comparison",
    engine_version_id: str = "sha256:synthetic-comparison-engine",
) -> StrategyComparison:
    """Seal a synthetic :class:`StrategyComparison` and persist it to the sidecar.

    ``p_values`` supplies one entry per upper-triangle ``(i < j)`` pair, in order; its
    length must equal ``n_strategies·(n_strategies-1)/2``. Returns the sealed record
    (its ``research_result_id`` is what a Phase 25 request points at).
    """
    expected = n_strategies * (n_strategies - 1) // 2
    if len(p_values) != expected:
        raise ValueError(
            f"expected {expected} pair p-values for {n_strategies} strategies, "
            f"got {len(p_values)}"
        )
    cells: list[ComparisonCell] = []
    cursor = 0
    for i in range(n_strategies):
        for j in range(i + 1, n_strategies):
            cells.append(_pair_cell(i, j, p_values[cursor]))
            cursor += 1
    trials = tuple(
        TrialSummary(
            label=strategy_label(index),
            sharpe=StatValue.known("1.0"),
            n_valid_periods=12,
            axis_periods=12,
        )
        for index in range(n_strategies)
    )
    defined = sum(1 for cell in cells if cell.p_value.value is not None)
    coverage = Coverage(
        n_strategies=n_strategies,
        n_pairs=len(cells),
        n_defined_pairs=defined,
        n_undefined_pairs=len(cells) - defined,
    )
    refs = tuple(
        (
            strategy_label(index),
            f"sha256:strategy-{index}",
            f"sha256:strategy-hash-{index}",
        )
        for index in range(n_strategies)
    )
    comparison = StrategyComparison.seal(
        strategy_comparison_engine_version_id=engine_version_id,
        comparison_spec={"spec_version": "comparison/1", "name": name},
        strategy_refs=refs,
        boundary_kind=BOUNDARY_PIT,
        schedule_id="schedule-synthetic",
        factor_portfolio_engine_version_id="sha256:fpe",
        periods_per_year="1",
        risk_free_per_period="0",
        trials=trials,
        comparisons=tuple(cells),
        coverage=coverage,
        dataset_version_ids=("sha256:ds",),
        market_dataset_version_ids=("sha256:mkt",),
    )
    ws.research_result_store.write(comparison)
    return comparison


def make_spec(
    source_id: str,
    *,
    name: str = "phase25-correction",
    alpha: str = "0.05",
    methods: object = None,
) -> MultipleComparisonSpecification:
    """A correction request over one sealed comparison id (defaults: Holm + BY)."""
    if methods is None:
        return MultipleComparisonSpecification(
            name=name, source_strategy_comparison_id=source_id, alpha=alpha
        )
    return MultipleComparisonSpecification(
        name=name,
        source_strategy_comparison_id=source_id,
        alpha=alpha,
        methods=methods,  # type: ignore[arg-type]
    )
