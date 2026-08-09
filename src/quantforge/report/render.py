"""The single reference renderer for a research report (locked §10, §19, D6).

Phase 14 ships **exactly one** reference renderer: :func:`render_markdown`, a **pure,
deterministic function** that resolves a sealed
:class:`~quantforge.report.result.ResearchReport`'s references from the shared sidecar
and formats them as human-readable Markdown. Its purpose is to *prove* the
content/presentation boundary (locked §10): it consumes the canonical artifact and
produces text without any feedback into identity or storage. The output is **not** a
:class:`~quantforge.factors.store.ResearchRecord`, is **not** content-addressed, and is
**not** written to the sidecar. Re-rendering the same report over the same immutable
sidecar yields the same string; editing this renderer changes only its output — never
``report_id`` or the stored record (locked R1).

The renderer computes **no** new financial number. Every figure it prints is read
verbatim (as a decimal string) from a sealed record, or is a deterministically
recomputed :class:`~quantforge.experiment.analysis.BacktestComparison` (which itself
computes no new statistic — it ranks already-sealed ones). Undefined counts, unfilled
orders, unrecognized corporate actions, excluded comparison members, and corpus
``pin_mismatch`` are surfaced by *reading the sealed summaries*, never fabricated and
never hidden (locked §17, G8).

The ten §10 sections are a stable, documented renderer contract — presentation, not
model state — so their titles/ordering can change here without ever touching
``report_id``.

HTML, PDF, charts, and any web UI are deferred to a future presentation phase (locked
§19, §26); Markdown is the v1 choice because it is stdlib-only, diffable, and
deterministic.
"""

from __future__ import annotations

from quantforge.backtest.result import BacktestResult
from quantforge.experiment.analysis import BacktestComparison
from quantforge.experiment.result import ExperimentResult
from quantforge.factors.store import ResearchResultStore
from quantforge.report.errors import ReportConsistencyError
from quantforge.report.result import ReportReference, ResearchReport

__all__ = ["render_markdown"]

_SCOPE_BACKTEST = "backtest"
_SCOPE_EXPERIMENT = "experiment"
_KIND_COMPARISON = "comparison"

# The v1 statistic set, in a stable display order for the Backtest Results section. This
# is presentation ordering only (never folded into identity).
_STATISTIC_ORDER: tuple[str, ...] = (
    "initial_equity",
    "final_equity",
    "peak_equity",
    "cumulative_return",
    "mean_period_return",
    "volatility",
    "sharpe",
    "max_drawdown",
    "mean_turnover",
    "periods",
)


def render_markdown(report: ResearchReport, store: ResearchResultStore) -> str:
    """Render a sealed report to deterministic Markdown (locked §10, §19, D6).

    Pure and side-effect-free: resolves the report's references from ``store`` and
    formats them; it never mutates the report, never writes to the store, and never
    affects ``report_id``. Fails closed
    (:class:`~quantforge.report.errors.ReportConsistencyError`) if a referenced artifact
    cannot be resolved from the sidecar — a report can never be rendered against a
    missing artifact (locked G7).
    """
    lines: list[str] = []
    subject_id = _spec_str(report, "subject_id")
    if report.scope == _SCOPE_BACKTEST:
        subject = _resolve_backtest(subject_id, store)
        _render_backtest_report(report, subject, lines)
    elif report.scope == _SCOPE_EXPERIMENT:
        experiment = _resolve_experiment(subject_id, store)
        _render_experiment_report(report, experiment, store, lines)
    else:  # pragma: no cover - a sealed report always carries a v1 scope.
        raise ReportConsistencyError(f"report scope {report.scope!r} is not supported")
    return "\n".join(lines) + "\n"


# -- backtest-scope rendering ------------------------------------------------


def _render_backtest_report(
    report: ResearchReport, subject: BacktestResult, lines: list[str]
) -> None:
    name = _spec_str(report, "name")
    stats = subject.performance.statistics

    lines.append(f"# Research Report: {name}")
    lines.append("")
    _section(lines, "Executive Summary")
    lines.append(f"- Scope: `{report.scope}` (point-in-time)")
    lines.append(f"- Subject backtest: `{subject.backtest_id}`")
    lines.append(f"- Cumulative return: `{stats.cumulative_return}`")
    lines.append(f"- Sharpe: `{stats.sharpe}`")
    lines.append("")

    _section(lines, "Research Definition")
    lines.append(f"- Report name: {name}")
    lines.append(f"- Scope: `{report.scope}`")
    lines.append(f"- Strategy version: `{subject.strategy_version}`")
    lines.append("")

    _section(lines, "Dataset & PIT Configuration")
    lines.append(f"- Boundary: `{report.boundary_kind}`")
    lines.append(f"- Fundamentals dataset: `{subject.dataset_version_id}`")
    lines.append(f"- Market dataset: `{subject.market_dataset_version_id}`")
    lines.append("")

    _section(lines, "Universe")
    lines.append(f"- Universe: `{subject.universe_id}`")
    lines.append("")

    _section(lines, "Strategy")
    lines.append(f"- Strategy version: `{subject.strategy_version}`")
    lines.append(f"- Schedule: `{subject.schedule_id}`")
    lines.append(f"- Cost model: `{subject.cost_model_id}`")
    lines.append(f"- Accounting: `{subject.accounting_version_id}`")
    lines.append("")

    _section(lines, "Backtest Results")
    _render_statistics_table(subject, lines)
    lines.append("")

    _section(lines, "Experiment Comparison")
    lines.append("- Not applicable to a single-backtest report.")
    lines.append("")

    _section(lines, "Provenance")
    _render_backtest_provenance(subject, lines)
    lines.append("")

    _section(lines, "Warnings / Undefined Data")
    conditions = _backtest_conditions(subject)
    _render_conditions(conditions, lines)
    lines.append("")

    _section(lines, "Reproduction Information")
    lines.append(f"- Report id: `{report.report_id}`")
    lines.append(f"- Report result id: `{report.report_result_id}`")
    lines.append(f"- Report engine version: `{report.report_engine_version_id}`")
    lines.append(f"- Backtest engine version: `{subject.backtest_engine_version_id}`")
    lines.append(f"- Subject id: `{subject.backtest_id}`")


# -- experiment-scope rendering ----------------------------------------------


def _render_experiment_report(
    report: ResearchReport,
    experiment: ExperimentResult,
    store: ResearchResultStore,
    lines: list[str],
) -> None:
    name = _spec_str(report, "name")
    children = _resolve_children(experiment, store)
    comparisons = _recompute_comparisons(report, experiment, store)

    lines.append(f"# Research Report: {name}")
    lines.append("")
    _section(lines, "Executive Summary")
    lines.append(f"- Scope: `{report.scope}` (point-in-time)")
    lines.append(f"- Subject experiment: `{experiment.experiment_result_id}`")
    lines.append(f"- Child backtests: {len(children)}")
    for directive, comparison in comparisons:
        best = comparison.best
        if best is None:
            lines.append(
                f"- Best by `{directive[0]}` ({directive[1]}): none "
                "(every member excluded)"
            )
        else:
            lines.append(
                f"- Best by `{directive[0]}` ({directive[1]}): "
                f"`{best.backtest_id}` = `{best.value}`"
            )
    lines.append("")

    _section(lines, "Research Definition")
    lines.append(f"- Report name: {name}")
    lines.append(f"- Scope: `{report.scope}`")
    lines.append(f"- Experiment id: `{experiment.experiment_id}`")
    for axis_id in experiment.axis_ids:
        lines.append(f"- Sweep axis: `{axis_id}`")
    lines.append("")

    _section(lines, "Dataset & PIT Configuration")
    lines.append(f"- Boundary: `{report.boundary_kind}`")
    lines.append(f"- Fundamentals dataset: `{experiment.dataset_version_id}`")
    lines.append(f"- Market dataset: `{experiment.market_dataset_version_id}`")
    lines.append("")

    _section(lines, "Universe")
    universe_ids = sorted({child.universe_id for child in children})
    for universe_id in universe_ids:
        lines.append(f"- Universe: `{universe_id}`")
    if not universe_ids:
        lines.append("- No child backtests to describe a universe.")
    lines.append("")

    _section(lines, "Strategy")
    strategy_versions = sorted({child.strategy_version for child in children})
    for strategy_version in strategy_versions:
        lines.append(f"- Strategy version: `{strategy_version}`")
    if not strategy_versions:
        lines.append("- No child backtests to describe a strategy.")
    lines.append("")

    _section(lines, "Backtest Results")
    for child in children:
        lines.append(f"### Child `{child.backtest_id}`")
        _render_statistics_table(child, lines)
        lines.append("")
    if not children:
        lines.append("- No child backtests.")
        lines.append("")

    _section(lines, "Experiment Comparison")
    if not comparisons:
        lines.append("- No comparison directive was requested.")
    for directive, comparison in comparisons:
        _render_comparison(directive, comparison, lines)
    lines.append("")

    _section(lines, "Provenance")
    lines.append(f"- Experiment id: `{experiment.experiment_id}`")
    lines.append(
        f"- Experiment engine version: `{experiment.experiment_engine_version_id}`"
    )
    for child in children:
        lines.append(f"- Child `{child.backtest_id}`:")
        _render_backtest_provenance(child, lines, indent="  ")
    lines.append("")

    _section(lines, "Warnings / Undefined Data")
    conditions: list[str] = []
    for child in children:
        for condition in _backtest_conditions(child):
            conditions.append(f"backtest `{child.backtest_id}`: {condition}")
    for directive, comparison in comparisons:
        for backtest_id, reason in comparison.excluded:
            conditions.append(
                f"comparison by `{directive[0]}` ({directive[1]}): excluded "
                f"`{backtest_id}` ({reason})"
            )
        if comparison.pin_mismatch:
            conditions.append(
                f"comparison by `{directive[0]}` ({directive[1]}): corpus pin_mismatch"
            )
    _render_conditions(conditions, lines)
    lines.append("")

    _section(lines, "Reproduction Information")
    lines.append(f"- Report id: `{report.report_id}`")
    lines.append(f"- Report result id: `{report.report_result_id}`")
    lines.append(f"- Report engine version: `{report.report_engine_version_id}`")
    lines.append(f"- Subject id: `{experiment.experiment_result_id}`")
    for child in children:
        lines.append(f"- Child backtest id: `{child.backtest_id}`")


# -- shared section helpers --------------------------------------------------


def _section(lines: list[str], title: str) -> None:
    lines.append(f"## {title}")
    lines.append("")


def _render_statistics_table(result: BacktestResult, lines: list[str]) -> None:
    stats = result.performance.statistics
    values = stats.to_dict()
    lines.append("| Statistic | Value |")
    lines.append("| --- | --- |")
    for key in _STATISTIC_ORDER:
        value = values.get(key)
        lines.append(f"| {key} | `{value}` |")


def _render_comparison(
    directive: tuple[str, str], comparison: BacktestComparison, lines: list[str]
) -> None:
    lines.append(f"### Ranked by `{directive[0]}` ({directive[1]})")
    lines.append(f"- Comparison id: `{comparison.comparison_id}`")
    lines.append(f"- Corpus pin_mismatch: `{comparison.pin_mismatch}`")
    lines.append("")
    lines.append("| Rank | Backtest | Value |")
    lines.append("| --- | --- | --- |")
    for entry in comparison.entries:
        lines.append(f"| {entry.rank} | `{entry.backtest_id}` | `{entry.value}` |")
    if not comparison.entries:
        lines.append("| — | (every member excluded) | — |")


def _render_backtest_provenance(
    result: BacktestResult, lines: list[str], *, indent: str = ""
) -> None:
    lines.append(f"{indent}- Backtest id: `{result.backtest_id}`")
    lines.append(f"{indent}- Result hash: `{result.result_hash}`")
    lines.append(f"{indent}- Strategy version: `{result.strategy_version}`")
    lines.append(f"{indent}- Fundamentals dataset: `{result.dataset_version_id}`")
    lines.append(f"{indent}- Market dataset: `{result.market_dataset_version_id}`")
    lines.append(f"{indent}- Cost model: `{result.cost_model_id}`")
    lines.append(f"{indent}- Accounting: `{result.accounting_version_id}`")
    lines.append(
        f"{indent}- Backtest engine version: `{result.backtest_engine_version_id}`"
    )


def _backtest_conditions(result: BacktestResult) -> list[str]:
    """Surface every recorded data condition in a backtest ledger (locked §17, G8).

    Reads the sealed ledger only — unfilled orders (with their reason) and unrecognized
    corporate actions. It fabricates nothing and hides nothing; an empty list means the
    ledger recorded no such condition.
    """
    conditions: list[str] = []
    for record in result.ledger:
        for fill in record.fills:
            if fill.status != "filled":
                reason = fill.reason if fill.reason is not None else "unspecified"
                conditions.append(
                    f"unfilled order for `{fill.security_id}` at {record.as_of} "
                    f"(status={fill.status}, reason={reason})"
                )
        for action in record.actions_applied:
            if action.unrecognized:
                conditions.append(
                    f"unrecognized corporate action `{action.corporate_action_id}` "
                    f"for `{action.security_id}` at {record.as_of}"
                )
    return conditions


def _render_conditions(conditions: list[str], lines: list[str]) -> None:
    if not conditions:
        lines.append("- None recorded.")
        return
    for condition in conditions:
        lines.append(f"- {condition}")


# -- resolution --------------------------------------------------------------


def _resolve_backtest(subject_id: str, store: ResearchResultStore) -> BacktestResult:
    result = store.read_as(subject_id, BacktestResult.from_dict)
    if result is None:
        raise ReportConsistencyError(
            f"cannot render: backtest {subject_id!r} is absent from the research "
            "sidecar"
        )
    return result


def _resolve_experiment(
    subject_id: str, store: ResearchResultStore
) -> ExperimentResult:
    result = store.read_as(subject_id, ExperimentResult.from_dict)
    if result is None:
        raise ReportConsistencyError(
            f"cannot render: experiment {subject_id!r} is absent from the research "
            "sidecar"
        )
    return result


def _resolve_children(
    experiment: ExperimentResult, store: ResearchResultStore
) -> list[BacktestResult]:
    children: list[BacktestResult] = []
    for backtest_id in experiment.backtest_ids:
        child = store.read_as(backtest_id, BacktestResult.from_dict)
        if child is None:
            raise ReportConsistencyError(
                f"cannot render: child backtest {backtest_id!r} is absent from the "
                "research sidecar"
            )
        children.append(child)
    return children


def _recompute_comparisons(
    report: ResearchReport,
    experiment: ExperimentResult,
    store: ResearchResultStore,
) -> list[tuple[tuple[str, str], BacktestComparison]]:
    """Recompute every comparison reference deterministically for display (§13, D5).

    Reads the ``statistic`` / ``order`` intent from each ``comparison`` reference's
    ``detail`` and recomputes the
    :class:`~quantforge.experiment.analysis.BacktestComparison`
    from the sidecar — identical to what the engine sealed by ``comparison_id``. The
    renderer verifies the recomputed ``comparison_id`` still matches the reference's
    pinned ``content_hash`` and fails closed on drift (locked R4).
    """
    comparisons: list[tuple[tuple[str, str], BacktestComparison]] = []
    for reference in report.references:
        if reference.kind != _KIND_COMPARISON:
            continue
        statistic, order = _comparison_intent(reference)
        comparison = BacktestComparison.of_experiment(
            experiment, store, statistic=statistic, order=order
        )
        if comparison.comparison_id != reference.content_hash:
            raise ReportConsistencyError(
                f"recomputed comparison {comparison.comparison_id!r} does not "
                "match the "
                f"reference content hash {reference.content_hash!r}; the referenced "
                "artifacts have drifted (fail closed)"
            )
        comparisons.append(((statistic, order), comparison))
    return comparisons


def _comparison_intent(reference: ReportReference) -> tuple[str, str]:
    statistic = reference.detail.get("statistic")
    order = reference.detail.get("order")
    if not isinstance(statistic, str) or not isinstance(order, str):
        raise ReportConsistencyError(
            "comparison reference detail is missing a well-formed statistic/order "
            "intent"
        )
    return statistic, order


def _spec_str(report: ResearchReport, key: str) -> str:
    value = report.report_spec.get(key)
    if not isinstance(value, str):
        raise ReportConsistencyError(f"report_spec.{key} must be a string")
    return value
