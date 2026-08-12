"""Offline, obviously-synthetic fixtures for Phase 22 walk-forward tests.

The walk-forward engine is a pure consumer of one sealed
:class:`~quantforge.optimization.result.PortfolioOptimization` recipe and, transitively,
the :class:`~quantforge.factorrisk.result.FactorRiskModel` it optimized and that model's
:class:`~quantforge.factorportfolio.result.FactorPortfolio` factors - from which it
reads only each factor's per-period ``(as_of, factor_return)`` series. Rather than seed
a full multi-filer fundamentals + market corpus (that path is proven end-to-end in
``tests/factorportfolio`` / ``tests/factorrisk``), these builders **synthesize** the
sealed chain directly from hand-chosen return series and a hand-chosen covariance, and
persist each record to a real :class:`~quantforge.factors.store.ResearchResultStore`
sidecar via the workspace. That gives exact control over the aligned axis, the
train->test windows, and which windows are positive-definite - while still exercising
the true resolve -> verify -> align -> partition -> evaluate -> seal -> persist path
through the engine and the shared store.

Every synthesized record is a *valid* sealed record (its ``result_hash`` / id are the
real content hashes and it round-trips through its own ``from_dict``), so the engine's
fail-closed reference checks pass exactly as they would for engine-produced records. The
factor cells the walk never reads (leg returns / membership, the summary, coverage) are
honest KNOWN placeholders; the risk-model covariance is a real matrix the *optimizer*
solves (the walk re-estimates its own per-window covariance from the factor returns).
Everything is fictional and offline (Principle 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantforge.factorportfolio.model import (
    CoverageSummary,
    FactorReturnSummary,
    LegKind,
    LegMembership,
    PerPeriodReturn,
)
from quantforge.factorportfolio.model import (
    StatValue as FPStatValue,
)
from quantforge.factorportfolio.result import (
    BOUNDARY_PIT as FP_BOUNDARY_PIT,
)
from quantforge.factorportfolio.result import (
    FactorPortfolio,
)
from quantforge.factorrisk.model import (
    CorrelationCell,
    CovarianceCell,
    FactorCoverage,
    FactorMoment,
)
from quantforge.factorrisk.model import (
    CoverageSummary as RiskCoverageSummary,
)
from quantforge.factorrisk.model import (
    StatValue as RiskStatValue,
)
from quantforge.factorrisk.model import (
    factor_label as risk_factor_label,
)
from quantforge.factorrisk.result import BOUNDARY_PIT as RISK_BOUNDARY_PIT
from quantforge.factorrisk.result import FactorRiskModel
from quantforge.optimization.engine import PortfolioOptimizationEngine
from quantforge.optimization.result import PortfolioOptimization
from quantforge.optimization.spec import PortfolioOptimizationSpecification
from quantforge.walkforward.engine import WalkForwardEvaluationEngine
from quantforge.walkforward.spec import (
    TrainingPolicy,
    WalkForwardEvaluationSpecification,
)
from quantforge.workspace import Workspace

__all__ = [
    "DummyRecord",
    "build_chain",
    "expanding_policy",
    "make_factor",
    "make_risk_model",
    "make_wf_spec",
    "seal_optimization",
    "wf_engine",
    "workspace",
]

# A synthetic producing-engine version + schedule the factors/model share. The walk
# carries the risk model's values through to its sealed record; their exact strings are
# arbitrary but must be stable so re-builds reproduce identical ids.
_FPE_VERSION = "fpe-synthetic/1"
_SCHEDULE = "schedule-synthetic"

# Six ISO-like rebalance instants (the factor as_of axis). Lexicographic order == time
# order, matching the schedule the real Phase 19 engine emits.
DATES = (
    "2020-01-31",
    "2020-02-29",
    "2020-03-31",
    "2020-04-30",
    "2020-05-31",
    "2020-06-30",
)

# Two independent factor return series over DATES: no window of >= 3 observations is
# collinear, so every training span of at least three periods yields a positive-definite
# 2x2 covariance (a REALIZED window). A 2-observation training span is rank-1 and
# therefore SINGULAR - exploited by the mixed-window fixtures below.
SERIES_A: tuple[str, ...] = ("0.01", "-0.02", "0.03", "-0.01", "0.02", "-0.03")
SERIES_B: tuple[str, ...] = ("0.02", "0.01", "-0.03", "0.015", "-0.01", "0.025")


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def wf_engine(ws: Workspace) -> WalkForwardEvaluationEngine:
    """The workspace's Phase 22 engine, narrowed from the ``object`` property."""
    engine = ws.walk_forward_engine
    assert isinstance(engine, WalkForwardEvaluationEngine)
    return engine


def _canonical(value: str) -> str:
    """The canonical decimal string of ``value`` (matches the sealing layers)."""
    from decimal import Decimal

    return str(+Decimal(value))


def make_factor(
    *,
    name: str,
    values: tuple[str | None, ...],
    dates: tuple[str, ...] = DATES,
    risk_free_per_period: str = "0",
    periods_per_year: str = "1",
    schedule_id: str = _SCHEDULE,
    signal: str = "current_ratio",
) -> FactorPortfolio:
    """Synthesize a sealed :class:`FactorPortfolio` from a per-period return series.

    ``values`` is one entry per ``dates`` instant: a decimal string for a KNOWN factor
    return, or ``None`` for an UNDEFINED period (which the walk's complete-case
    alignment excludes). Only ``as_of`` + ``factor_return`` are read by the walk; the
    leg returns, membership, summary, and coverage are honest KNOWN placeholders. Not
    written to any store - see :func:`build_chain`.
    """
    from quantforge.factorportfolio.model import FactorPortfolioUndefinedReason

    assert len(values) == len(dates), "one value per date"
    zero = FPStatValue.known("0")
    empty_long = LegMembership(kind=LegKind.LONG, company_ids=())
    empty_short = LegMembership(kind=LegKind.SHORT, company_ids=())
    per_period = tuple(
        PerPeriodReturn(
            as_of=as_of,
            n_members=0,
            long_membership=empty_long,
            short_membership=empty_short,
            long_return=zero,
            short_return=zero,
            factor_return=(
                FPStatValue.known(_canonical(value))
                if value is not None
                else FPStatValue.undefined(
                    FactorPortfolioUndefinedReason.INSUFFICIENT_MEMBERS
                )
            ),
        )
        for as_of, value in zip(dates, values, strict=True)
    )
    n_known = sum(1 for v in values if v is not None)
    summary = FactorReturnSummary(
        cumulative_return=zero,
        mean_period_return=zero,
        volatility=zero,
        annualized_sharpe=zero,
        mean_t_stat=zero,
        hit_rate=zero,
        n_valid_periods=n_known,
    )
    coverage = CoverageSummary(
        per_date=(),
        total_resolved=0,
        total_dropped_for_signal=0,
        total_dropped_for_return=0,
        total_undefined_periods=len(values) - n_known,
    )
    spec_payload: dict[str, object] = {
        "spec_version": "factorportfolio/1",
        "name": name,
    }
    return FactorPortfolio.seal(
        factor_portfolio_engine_version_id=_FPE_VERSION,
        factor_portfolio_spec=spec_payload,
        name=name,
        spec_version="factorportfolio/1",
        signal=signal,
        period_key="FY:2019",
        universe_specification_id="sha256:synthetic-universe",
        schedule_id=schedule_id,
        horizon_days=1,
        quantiles=2,
        weighting="equal",
        boundary_kind=FP_BOUNDARY_PIT,
        risk_free_per_period=risk_free_per_period,
        periods_per_year=periods_per_year,
        dataset_version_id="ds-synthetic",
        market_dataset_version_id="mkt-synthetic",
        per_period=per_period,
        summary=summary,
        coverage=coverage,
    )


def make_risk_model(
    factors: list[FactorPortfolio],
    *,
    matrix: list[list[str]] | None = None,
    name: str = "phase22-synthetic-risk",
    periods_per_year: str = "1",
    schedule_id: str = _SCHEDULE,
    dataset_version_ids: tuple[str, ...] = ("ds-synthetic",),
    market_dataset_version_ids: tuple[str, ...] = ("mkt-synthetic",),
) -> FactorRiskModel:
    """Synthesize a sealed :class:`FactorRiskModel` referencing real sealed ``factors``.

    Each factor is pinned by its real ``(label, factor_portfolio_id, result_hash)`` so
    the walk resolves and verifies them exactly as it would engine-produced factors.
    ``matrix`` is the full symmetric ``N x N`` covariance the *optimizer* solves
    (default identity, giving a clean OPTIMAL GMV recipe); the walk ignores it and
    re-estimates its own per-window covariance from the factor returns. Not written to
    any store.
    """
    n = len(factors)
    cov = matrix or [["1" if i == j else "0" for j in range(n)] for i in range(n)]
    assert len(cov) == n and all(len(row) == n for row in cov), "matrix must be N x N"

    factor_refs = tuple(
        (
            risk_factor_label(i),
            factors[i].research_result_id,
            factors[i].result_hash,
        )
        for i in range(n)
    )
    moments = tuple(
        FactorMoment(
            label=risk_factor_label(i),
            mean=RiskStatValue.known("0"),
            volatility=RiskStatValue.known(_canonical(cov[i][i])),
            annualized_volatility=RiskStatValue.known(_canonical(cov[i][i])),
        )
        for i in range(n)
    )
    covariance = tuple(
        CovarianceCell(
            i=i,
            j=j,
            value=RiskStatValue.known(_canonical(cov[i][j])),
            annualized=RiskStatValue.known(_canonical(cov[i][j])),
        )
        for i in range(n)
        for j in range(i, n)
    )
    correlation = tuple(
        CorrelationCell(i=i, j=j, value=RiskStatValue.known("0"))
        for i in range(n)
        for j in range(i, n)
    )
    coverage = RiskCoverageSummary(
        per_factor=tuple(
            FactorCoverage(
                label=risk_factor_label(i),
                factor_portfolio_id=factors[i].research_result_id,
                available=len(DATES),
                used=len(DATES),
            )
            for i in range(n)
        ),
        aligned_periods=len(DATES),
        dropped_for_alignment=0,
    )
    spec_payload: dict[str, object] = {
        "spec_version": "factorrisk/1",
        "name": name,
        "factor_portfolio_ids": [ref[1] for ref in factor_refs],
        "periods_per_year": periods_per_year,
    }
    return FactorRiskModel.seal(
        factor_risk_engine_version_id="fre-synthetic/1",
        factor_risk_spec=spec_payload,
        factor_refs=factor_refs,
        boundary_kind=RISK_BOUNDARY_PIT,
        schedule_id=schedule_id,
        factor_portfolio_engine_version_id=_FPE_VERSION,
        periods=len(DATES),
        periods_per_year=periods_per_year,
        factors=moments,
        covariance=covariance,
        correlation=correlation,
        coverage=coverage,
        dataset_version_ids=dataset_version_ids,
        market_dataset_version_ids=market_dataset_version_ids,
    )


def seal_optimization(
    ws: Workspace, model: FactorRiskModel, *, name: str = "phase22-recipe"
) -> PortfolioOptimization:
    """Run the real Phase 21 optimizer over ``model`` and return the sealed recipe.

    Both the model and the resulting :class:`PortfolioOptimization` are persisted to the
    workspace sidecar, so the walk can resolve the whole chain.
    """
    ws.research_result_store.write(model)
    engine = ws.optimization_engine
    assert isinstance(engine, PortfolioOptimizationEngine)
    spec = PortfolioOptimizationSpecification(
        name=name, factor_risk_id=model.research_result_id
    )
    return engine.optimize(spec)


def build_chain(
    ws: Workspace,
    *,
    series: tuple[tuple[str | None, ...], ...] = (SERIES_A, SERIES_B),
    dates: tuple[str, ...] = DATES,
    matrix: list[list[str]] | None = None,
    risk_free_per_period: str = "0",
    periods_per_year: str = "1",
    schedule_id: str = _SCHEDULE,
    name: str = "phase22-recipe",
) -> PortfolioOptimization:
    """Seal N factors + a risk model + an optimization recipe into the sidecar.

    Returns the sealed :class:`PortfolioOptimization` a walk-forward request references.
    ``series`` is one return series per factor (each aligned to ``dates``).
    """
    factors = [
        make_factor(
            name=f"{name}-factor-{i}",
            values=values,
            dates=dates,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
            schedule_id=schedule_id,
        )
        for i, values in enumerate(series)
    ]
    for factor in factors:
        ws.research_result_store.write(factor)
    model = make_risk_model(
        factors,
        matrix=matrix,
        periods_per_year=periods_per_year,
        schedule_id=schedule_id,
    )
    return seal_optimization(ws, model, name=name)


def expanding_policy(
    *, min_train_periods: int = 3, test_periods: int = 1
) -> TrainingPolicy:
    """A conventional expanding-window training policy for the fixtures."""
    return TrainingPolicy(
        window="expanding",
        min_train_periods=min_train_periods,
        test_periods=test_periods,
    )


def make_wf_spec(
    optimization_id: str,
    *,
    policy: TrainingPolicy | None = None,
    name: str = "phase22-walk",
) -> WalkForwardEvaluationSpecification:
    """A walk-forward-evaluation request over the given sealed optimization recipe."""
    return WalkForwardEvaluationSpecification(
        name=name,
        optimization_id=optimization_id,
        training_policy=policy or expanding_policy(),
    )


@dataclass(frozen=True)
class DummyRecord:
    """A non-``PortfolioOptimization`` :class:`ResearchRecord` for fail-closed tests.

    Satisfies the store's write Protocol (a content-addressed id + a deterministic
    ``to_dict``) but its payload cannot decode as a
    :class:`~quantforge.optimization.result.PortfolioOptimization`, so referencing it
    exercises the engine's "resolved record is not an optimization" fail-closed guard.
    """

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-an-optimization", "id": self.research_result_id}
