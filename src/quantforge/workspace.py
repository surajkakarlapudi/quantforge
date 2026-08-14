"""The composition root that wires Phases 1-5 into one reusable context.

:class:`Workspace` holds the existing stores and façades — the Phase 1
:class:`~quantforge.sec.storage.ArtifactStore`, the Phase 2
:class:`~quantforge.registry.registry.FilingRegistry`, the Phase 4
:class:`~quantforge.canonical.store.CanonicalFactStore`, and the company
:class:`~quantforge.identity.resolve.CompanyResolver` — assembled from a single
data root. It creates **no** new storage and duplicates **no** logic; it only
constructs the components each phase already defines and hands them to the
:class:`~quantforge.company.Company` façade.

Directory layout under the data root (matches the phase-validation layout)::

    <root>/sec/          # Phase 1 content-addressed artifacts (authoritative)
    <root>/registry/     # Phase 2 derived filing registry
    <root>/canonical/    # Phase 4 derived canonical facts
    <root>/availability/ # Phase 5 derived availability (wired here, not new code)

Wall-clock, network, and secrets never enter identity here — the workspace is a
plain wiring object. A network client is attached only when a User-Agent is
configured, and it is used solely to fetch the official ticker mapping once (and
only if it is not already cached).

Phase 7 extends the workspace **additively**: it wires the already-existing Phase 5
:class:`~quantforge.availability.store.AvailabilityStore` /
:class:`~quantforge.availability.ingest.AvailabilityIngestor` under
``<root>/availability/`` and lazily builds a
:class:`~quantforge.metrics.engine.MetricEngine`. No prior store is edited and no
fact is rewritten — the derived-metrics path composes on top of the existing chain.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from quantforge.availability.ingest import AvailabilityIngestor
from quantforge.availability.store import AvailabilityStore
from quantforge.canonical.store import CanonicalFactStore
from quantforge.identity.resolve import CompanyResolver
from quantforge.registry.registry import FilingRegistry
from quantforge.registry.store import RegistryStore
from quantforge.sec.client import SecClient
from quantforge.sec.config import ENV_STORAGE_DIR, SecConfig
from quantforge.sec.storage import ArtifactStore

if TYPE_CHECKING:
    from quantforge.factors.store import ResearchResultStore

__all__ = ["ENV_DATA_ROOT", "Workspace"]

#: Environment variable naming the QuantForge data root. When unset, the
#: workspace falls back to the parent of the Phase 1 storage dir (so an existing
#: ``<x>/sec`` acquisition tree yields ``<x>`` as the root).
ENV_DATA_ROOT = "QUANTFORGE_DATA_ROOT"


class Workspace:
    """Wire the existing per-phase stores and façades from one data root."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        registry: FilingRegistry,
        canonical_store: CanonicalFactStore,
        resolver: CompanyResolver,
        availability_store: AvailabilityStore,
        research_result_store: ResearchResultStore | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._registry = registry
        self._canonical = canonical_store
        self._resolver = resolver
        self._availability_store = availability_store
        self._research_result_store = research_result_store
        # The Phase 5 façade and the Phase 7/8 engines are built lazily and cached,
        # so a workspace that never touches metrics or factors pays nothing for them
        # (and there is no import cycle at module load — the engines import
        # :class:`Workspace`, so they are imported on first use, not here).
        self._availability_ingestor: AvailabilityIngestor | None = None
        self._metric_engine: object | None = None
        self._factor_engine: object | None = None
        self._panel_engine: object | None = None
        self._price_engine: object | None = None
        self._backtest_engine: object | None = None
        self._experiment_engine: object | None = None
        self._report_engine: object | None = None
        self._analytics_engine: object | None = None
        self._signal_diagnostics_engine: object | None = None
        self._attribution_engine: object | None = None
        self._crosssection_engine: object | None = None
        self._factor_portfolio_engine: object | None = None
        self._factor_risk_engine: object | None = None
        self._optimization_engine: object | None = None
        self._walk_forward_engine: object | None = None
        self._campaign_engine: object | None = None
        self._comparison_engine: object | None = None
        self._multiplicity_engine: object | None = None
        self._risk_calibration_engine: object | None = None
        self._stability_engine: object | None = None
        self._mintrl_engine: object | None = None
        self._calibration_significance_engine: object | None = None
        self._campaign_multiplicity_engine: object | None = None
        self._net_of_cost_engine: object | None = None
        self._net_of_cost_significance_engine: object | None = None

    @property
    def artifact_store(self) -> ArtifactStore:
        return self._artifacts

    @property
    def registry(self) -> FilingRegistry:
        return self._registry

    @property
    def canonical_store(self) -> CanonicalFactStore:
        return self._canonical

    @property
    def resolver(self) -> CompanyResolver:
        return self._resolver

    @property
    def availability_store(self) -> AvailabilityStore:
        return self._availability_store

    @property
    def availability_ingestor(self) -> AvailabilityIngestor:
        """The Phase 5 availability façade over this workspace's wired stores.

        Built once and cached. It derives availability offline and constructs the
        point-in-time resolver the metric engine needs — reusing the existing Phase
        5 component, never a new store.
        """
        if self._availability_ingestor is None:
            self._availability_ingestor = AvailabilityIngestor(
                self._registry,
                self._availability_store,
                artifact_store=self._artifacts,
                canonical_store=self._canonical,
            )
        return self._availability_ingestor

    @property
    def metric_engine(self) -> object:
        """The Phase 7 :class:`~quantforge.metrics.engine.MetricEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine
        imports :class:`Workspace`). Cached for reuse.
        """
        if self._metric_engine is None:
            from quantforge.metrics.engine import MetricEngine

            self._metric_engine = MetricEngine(self)
        return self._metric_engine

    @property
    def research_result_store(self) -> ResearchResultStore:
        """The Phase 8 :class:`ResearchResultStore` sidecar under ``<root>/research/``.

        Built once and cached, mirroring the other derived stores. It sits beside
        the Phase 5 availability tree (``availability_store.root`` is
        ``<root>/availability``, so its parent is the data root), so no new root has
        to be threaded through construction. A caller may inject one explicitly.
        """
        if self._research_result_store is None:
            from quantforge.factors.store import ResearchResultStore

            self._research_result_store = ResearchResultStore(
                self._availability_store.root.parent
            )
        return self._research_result_store

    @property
    def factor_engine(self) -> object:
        """The Phase 8 :class:`~quantforge.factors.engine.FactorEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine
        imports :class:`Workspace`). Cached for reuse.
        """
        if self._factor_engine is None:
            from quantforge.factors.engine import FactorEngine

            self._factor_engine = FactorEngine(self)
        return self._factor_engine

    @property
    def panel_engine(self) -> object:
        """The Phase 10 :class:`~quantforge.panel.engine.PanelEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine
        imports :class:`Workspace`). Cached for reuse; it reuses this workspace's
        Phase 7 metric engine, Phase 8 factor engine, and research sidecar rather
        than building any new store.
        """
        if self._panel_engine is None:
            from quantforge.panel.engine import PanelEngine

            self._panel_engine = PanelEngine(self)
        return self._panel_engine

    @property
    def price_engine(self) -> object:
        """The Phase 11 :class:`~quantforge.market.engine.PriceEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace` transitively). Cached for reuse. It owns a derived
        :class:`~quantforge.market.store.MarketDataStore` under ``<root>/market/``
        (canonical + availability sidecars) and reuses a Phase 1
        :class:`~quantforge.sec.storage.ArtifactStore` under ``<root>/market/raw/``
        for immutable vendor bytes — a sibling of the SEC acquisition tree, never
        mixed with it. Building any new fundamentals store is avoided: the market
        layer is additive and touches no prior phase's data.
        """
        if self._price_engine is None:
            from quantforge.market.engine import PriceEngine
            from quantforge.market.store import MarketDataStore

            # The data root is the parent of the availability tree (same derivation
            # the research sidecar uses), so no new root is threaded through open().
            market_root = self._availability_store.root.parent / "market"
            self._price_engine = PriceEngine(MarketDataStore(market_root))
        return self._price_engine

    @property
    def backtest_engine(self) -> object:
        """The Phase 12 :class:`~quantforge.backtest.engine.BacktestEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. It composes this workspace's Phase 8
        factor engine, Phase 10 panel engine, and Phase 11 price engine through their
        public ``*_as_of`` accessors and builds a Phase 9 universe builder over the
        same metric engine — it creates no new store and duplicates no resolution
        logic, exactly as :attr:`price_engine` and the other derived engines do.
        """
        if self._backtest_engine is None:
            from quantforge.backtest.engine import BacktestEngine

            self._backtest_engine = BacktestEngine(self)
        return self._backtest_engine

    @property
    def experiment_engine(self) -> object:
        """The Phase 13 :class:`~quantforge.experiment.engine.ExperimentEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. It sits strictly above Phase 12: it
        orchestrates this workspace's :attr:`backtest_engine` over a declarative sweep
        and persists the sealed experiment to the same shared research sidecar — it
        creates no new store and duplicates no resolution logic, exactly as the other
        derived engines do.
        """
        if self._experiment_engine is None:
            from quantforge.experiment.engine import ExperimentEngine

            self._experiment_engine = ExperimentEngine(self)
        return self._experiment_engine

    @property
    def report_engine(self) -> object:
        """The Phase 14 :class:`~quantforge.report.engine.ReportEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. It sits strictly above Phase 13: it
        resolves already-sealed backtest/experiment artifacts (and recomputes their
        comparisons deterministically) from this workspace's shared research sidecar
        and seals a content-addressed
        :class:`~quantforge.report.result.ResearchReport` back to the same sidecar — it
        creates no new store and duplicates no resolution logic, exactly as the other
        derived engines do.
        """
        if self._report_engine is None:
            from quantforge.report.engine import ReportEngine

            self._report_engine = ReportEngine(self)
        return self._report_engine

    @property
    def analytics_engine(self) -> object:
        """The Phase 15 :class:`~quantforge.analytics.engine.AnalyticsEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. It sits strictly above Phase 12: it
        resolves already-sealed backtest artifacts from this workspace's shared research
        sidecar, computes the risk / benchmark-relative statistics Phase 12 deferred,
        and seals a content-addressed
        :class:`~quantforge.analytics.result.PerformanceAnalytics` back to the same
        sidecar — it creates no new store and duplicates no resolution logic, exactly as
        the other derived engines do.
        """
        if self._analytics_engine is None:
            from quantforge.analytics.engine import AnalyticsEngine

            self._analytics_engine = AnalyticsEngine(self)
        return self._analytics_engine

    @property
    def signal_diagnostics_engine(self) -> object:
        """The Phase 16 :class:`~quantforge.diagnostics.engine.SignalDiagnosticsEngine`.

        Imported on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The diagnostic sibling of the Phase 12
        backtester: a pure consumer that composes this workspace's Phase 9 universe
        builder, Phase 10 panel engine, and Phase 11 price engine to measure whether an
        as-of-``T`` signal cross-section predicts realized forward returns, and seals a
        content-addressed
        :class:`~quantforge.diagnostics.result.SignalDiagnostics` back to the shared
        research sidecar — it creates no new store and duplicates no resolution logic,
        exactly as the other derived engines do.
        """
        if self._signal_diagnostics_engine is None:
            from quantforge.diagnostics.engine import SignalDiagnosticsEngine

            self._signal_diagnostics_engine = SignalDiagnosticsEngine(self)
        return self._signal_diagnostics_engine

    @property
    def attribution_engine(self) -> object:
        """The Phase 17 attribution engine (lazy).

        :class:`~quantforge.attribution.engine.AttributionEngine` is imported on first
        use to avoid a module-load import cycle (the engine imports :class:`Workspace`).
        Cached for reuse. It sits strictly above Phase 12: it resolves an already-sealed
        subject backtest and *K* factor backtests from this workspace's shared research
        sidecar, regresses the subject's excess return on the factors' excess returns
        (multi-factor OLS — the multi-factor generalization Phase 15 deferred), and
        seals a content-addressed
        :class:`~quantforge.attribution.result.FactorAttribution` back to the same
        sidecar — it creates no new store and duplicates no resolution logic, exactly as
        the other derived engines do.
        """
        if self._attribution_engine is None:
            from quantforge.attribution.engine import AttributionEngine

            self._attribution_engine = AttributionEngine(self)
        return self._attribution_engine

    @property
    def crosssection_engine(self) -> object:
        """The Phase 18 cross-sectional-regression engine (lazy).

        :class:`~quantforge.crosssection.engine.CrossSectionalRegressionEngine` is
        imported on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The multivariate cross-sectional sibling
        of the Phase 16 diagnostics engine: a pure consumer that composes this
        workspace's Phase 9 universe builder, Phase 10 panel engine, and Phase 11 price
        engine to run one exact-``Decimal`` OLS of realized forward returns on an
        as-of-``T`` ``K``-signal cross-section per scheduled date, aggregates the
        per-date coefficients into Fama-MacBeth premia, and seals a content-addressed
        :class:`~quantforge.crosssection.result.CrossSectionalRegression` back to the
        shared research sidecar - it creates no new store and duplicates no resolution
        logic, exactly as the other derived engines do.
        """
        if self._crosssection_engine is None:
            from quantforge.crosssection.engine import (
                CrossSectionalRegressionEngine,
            )

            self._crosssection_engine = CrossSectionalRegressionEngine(self)
        return self._crosssection_engine

    @property
    def factor_portfolio_engine(self) -> object:
        """The Phase 19 characteristic-sorted factor-portfolio engine (lazy).

        :class:`~quantforge.factorportfolio.engine.FactorPortfolioEngine` is imported on
        first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first member of a new
        portfolio-construction capability class - a constructive sibling that composes
        this workspace's Phase 9 universe builder, Phase 10 panel engine, and Phase 11
        price engine to sort each scheduled date's members into ``Q`` quantiles by an
        as-of-``T`` signal, form equal-weight long (top) / short (bottom) legs, take the
        long-minus-short forward-return spread as that period's factor return, chain the
        valid periods into a return series + summary, and seal a content-addressed
        :class:`~quantforge.factorportfolio.result.FactorPortfolio` back to the shared
        research sidecar - it creates no new store, duplicates no resolution logic, and
        consumes no ``BacktestResult``, exactly as the other derived engines do.
        """
        if self._factor_portfolio_engine is None:
            from quantforge.factorportfolio.engine import FactorPortfolioEngine

            self._factor_portfolio_engine = FactorPortfolioEngine(self)
        return self._factor_portfolio_engine

    @property
    def factor_risk_engine(self) -> object:
        """The Phase 20 factor covariance/correlation risk-model engine (lazy).

        :class:`~quantforge.factorrisk.engine.FactorRiskEngine` is imported on first use
        to avoid a module-load import cycle (the engine imports :class:`Workspace`).
        Cached for reuse. The first member of a new risk-modelling capability class - a
        pure consumer that resolves an ordered set of *N* sealed
        :class:`~quantforge.factorportfolio.result.FactorPortfolio` records from this
        workspace's shared research sidecar, re-verifies each, complete-case aligns
        their KNOWN factor return series on a common time axis, and estimates the
        second-moment structure (per-factor means and population volatilities, the
        ``N x N`` population covariance matrix, and the companion correlation matrix)
        under the pinned decimal context, sealing a content-addressed
        :class:`~quantforge.factorrisk.result.FactorRiskModel` back to the same sidecar
        - it creates no new store, duplicates no resolution logic, and consumes no
        ``BacktestResult``, exactly as the other derived engines do.
        """
        if self._factor_risk_engine is None:
            from quantforge.factorrisk.engine import FactorRiskEngine

            self._factor_risk_engine = FactorRiskEngine(self)
        return self._factor_risk_engine

    @property
    def optimization_engine(self) -> object:
        """The Phase 21 global minimum-variance portfolio-optimization engine (lazy).

        :class:`~quantforge.optimization.engine.PortfolioOptimizationEngine` is imported
        on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first member of a new
        portfolio-construction-over-a-risk-model capability class - a pure consumer
        strictly above Phase 20 that resolves exactly one sealed
        :class:`~quantforge.factorrisk.result.FactorRiskModel` from this workspace's
        shared research sidecar, re-verifies it, reconstructs the full symmetric
        ``N x N`` factor covariance matrix from its sealed upper-triangle cells, solves
        the fully-invested global minimum-variance factor-weight problem
        ``w = Σ⁻¹1 / (1ᵀΣ⁻¹1)`` under the pinned decimal context via the shared
        exact-``Decimal`` LDLᵀ factorization, and seals a content-addressed
        :class:`~quantforge.optimization.result.PortfolioOptimization` back to the same
        sidecar - it creates no new store, duplicates no resolution logic, and consumes
        no ``BacktestResult``, exactly as the other derived engines do.
        """
        if self._optimization_engine is None:
            from quantforge.optimization.engine import PortfolioOptimizationEngine

            self._optimization_engine = PortfolioOptimizationEngine(self)
        return self._optimization_engine

    @property
    def walk_forward_engine(self) -> object:
        """The Phase 22 walk-forward out-of-sample evaluation engine (lazy).

        :class:`~quantforge.walkforward.engine.WalkForwardEvaluationEngine` is imported
        on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first member of a new
        out-of-sample-evaluation capability class - a pure consumer strictly above Phase
        21 that resolves exactly one sealed
        :class:`~quantforge.optimization.result.PortfolioOptimization` GMV recipe from
        this workspace's shared research sidecar, transitively resolves the referenced
        :class:`~quantforge.factorrisk.result.FactorRiskModel` and its factor
        portfolios, aligns their return series on a common complete-case axis,
        partitions it into ordered train->test windows, re-estimates the covariance
        (Phase 20 method) and re-solves the GMV weights (Phase 21 method) on each
        training span, realizes those weights against the strictly-subsequent test
        returns, summarizes the chained out-of-sample series (Phase 19 method), and
        seals a content-addressed
        :class:`~quantforge.walkforward.result.WalkForwardEvaluation` back to the same
        sidecar - it creates no new store, duplicates no resolution logic, and consumes
        no ``BacktestResult``, exactly as the other derived engines do.
        """
        if self._walk_forward_engine is None:
            from quantforge.walkforward.engine import WalkForwardEvaluationEngine

            self._walk_forward_engine = WalkForwardEvaluationEngine(self)
        return self._walk_forward_engine

    @property
    def campaign_engine(self) -> object:
        """The Phase 23 out-of-sample research-campaign evaluation engine (lazy).

        :class:`~quantforge.campaign.engine.ResearchCampaignEngine` is imported on
        first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first member of a new
        research-campaign capability class - a pure consumer strictly above Phase 22
        that resolves an ordered set of ``N`` sealed
        :class:`~quantforge.walkforward.result.WalkForwardEvaluation` records (the
        trials of one research campaign) from this workspace's shared research
        sidecar, verifies they are commensurable, estimates each trial's
        out-of-sample Sharpe / skew / kurtosis and Probabilistic Sharpe Ratio (Phase
        23 method), selects the best out-of-sample Sharpe, estimates the
        expected-maximum Sharpe under the null, and deflates the best trial's
        significance for the size of the search (the Deflated Sharpe Ratio), sealing
        a content-addressed
        :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` back to the
        same sidecar - it creates no new store and duplicates no resolution logic,
        exactly as the other derived engines do.
        """
        if self._campaign_engine is None:
            from quantforge.campaign.engine import ResearchCampaignEngine

            self._campaign_engine = ResearchCampaignEngine(self)
        return self._campaign_engine

    @property
    def comparison_engine(self) -> object:
        """The Phase 24 pairwise out-of-sample strategy-comparison engine (lazy).

        :class:`~quantforge.comparison.engine.StrategyComparisonEngine` is imported on
        first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first member of a new
        strategy-comparison capability class - a pure consumer strictly above Phase 22
        that resolves an ordered set of ``N`` sealed
        :class:`~quantforge.walkforward.result.WalkForwardEvaluation` records (the
        competing strategies) from this workspace's shared research sidecar, verifies
        they are commensurable, reconstructs each strategy's realized out-of-sample
        return series by calendar date, and for every upper-triangle ``(i < j)`` pair
        computes the paired-difference statistics (mean out-of-sample return difference,
        standard error, ``t`` statistic, two-sided ``p`` value, descriptive Sharpe
        difference), sealing a content-addressed
        :class:`~quantforge.comparison.result.StrategyComparison` back to the same
        sidecar - it creates no new store and duplicates no resolution logic, exactly as
        the other derived engines do.
        """
        if self._comparison_engine is None:
            from quantforge.comparison.engine import StrategyComparisonEngine

            self._comparison_engine = StrategyComparisonEngine(self)
        return self._comparison_engine

    @property
    def multiplicity_engine(self) -> object:
        """The Phase 25 multiple-comparison-correction engine (lazy).

        :class:`~quantforge.multiplicity.engine.MultipleComparisonEngine` is imported on
        first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first member of a new multiplicity
        capability class - a pure consumer strictly above Phase 24 that resolves exactly
        one sealed :class:`~quantforge.comparison.result.StrategyComparison` from this
        workspace's shared research sidecar, treats its KNOWN pairwise ``p`` values as a
        single hypothesis family (recording each UNDEFINED pair as a first-class
        exclusion, never imputed), and for each requested
        :class:`~quantforge.multiplicity.model.CorrectionMethod` seals the family-wise /
        false-discovery adjusted ``p`` value plus a rejection flag at a declared
        ``alpha``, sealing a content-addressed
        :class:`~quantforge.multiplicity.result.MultipleComparisonCorrection` back to
        the same sidecar - it creates no new store and duplicates no resolution logic,
        exactly as the other derived engines do.
        """
        if self._multiplicity_engine is None:
            from quantforge.multiplicity.engine import MultipleComparisonEngine

            self._multiplicity_engine = MultipleComparisonEngine(self)
        return self._multiplicity_engine

    @property
    def risk_calibration_engine(self) -> object:
        """The Phase 26 walk-forward risk-forecast-calibration engine (lazy).

        :class:`~quantforge.calibration.engine.RiskForecastCalibrationEngine` is
        imported on first use to avoid a module-load import cycle (the engine
        imports :class:`Workspace`). Cached for reuse. The first member of a new
        risk-model out-of-sample-validation capability class - a pure consumer
        strictly above Phase 22 that resolves exactly one sealed
        :class:`~quantforge.walkforward.result.WalkForwardEvaluation` from this
        workspace's shared research sidecar, reads its reserved-but-unconsumed
        per-window ``predicted_variance`` (in-sample ``wᵀΣw``) and
        ``realized_variance`` (out-of-sample variance), classifies each window into
        the calibratable family (recording every non-calibratable window as a
        first-class exclusion, never imputed), and seals the per-window
        forecast-vs-outcome ratios plus the aggregate bias / dispersion statistics
        into a content-addressed
        :class:`~quantforge.calibration.result.RiskForecastCalibration` back to the
        same sidecar - it creates no new store and duplicates no resolution logic,
        exactly as the other derived engines do.
        """
        if self._risk_calibration_engine is None:
            from quantforge.calibration.engine import RiskForecastCalibrationEngine

            self._risk_calibration_engine = RiskForecastCalibrationEngine(self)
        return self._risk_calibration_engine

    @property
    def stability_engine(self) -> object:
        """The Phase 27 walk-forward turnover & stability engine (lazy).

        :class:`~quantforge.stability.engine.WalkForwardStabilityEngine` is imported on
        first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first consumer of Phase 22's
        reserved-but-unconsumed per-window ``weights`` payload - a pure consumer
        strictly above Phase 22 that resolves exactly one sealed
        :class:`~quantforge.walkforward.result.WalkForwardEvaluation` from this
        workspace's shared research sidecar, reads each REALIZED window's GMV weight
        vector, and seals the per-window weight-vector stability metrics and one-way
        turnover plus the aggregate turnover / concentration profile into a
        content-addressed :class:`~quantforge.stability.result.WalkForwardStability`
        back to the same sidecar - it creates no new store and duplicates no resolution
        logic, exactly as the other derived engines do.
        """
        if self._stability_engine is None:
            from quantforge.stability.engine import WalkForwardStabilityEngine

            self._stability_engine = WalkForwardStabilityEngine(self)
        return self._stability_engine

    @property
    def mintrl_engine(self) -> object:
        """The Phase 28 minimum-track-record-length engine (lazy).

        :class:`~quantforge.mintrl.engine.MinimumTrackRecordLengthEngine` is imported on
        first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first consumer of Phase 23's sealed
        per-trial OOS Sharpe / skew / kurtosis - a pure consumer strictly above Phase 23
        that resolves exactly one sealed
        :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` from this
        workspace's shared research sidecar, reads each VALID trial's moments, and seals
        the per-trial Bailey-López de Prado minimum track-record length and the
        aggregate MinTRL profile into a content-addressed
        :class:`~quantforge.mintrl.result.MinimumTrackRecordLength` back to the same
        sidecar - it creates no new store and duplicates no resolution logic, exactly as
        the other derived engines do.
        """
        if self._mintrl_engine is None:
            from quantforge.mintrl.engine import MinimumTrackRecordLengthEngine

            self._mintrl_engine = MinimumTrackRecordLengthEngine(self)
        return self._mintrl_engine

    @property
    def calibration_significance_engine(self) -> object:
        """The Phase 29 calibration-significance engine (lazy).

        :class:`~quantforge.calsig.engine.CalibrationSignificanceEngine` is imported on
        first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first consumer of Phase 26's sealed
        aggregate calibration statistics - a pure consumer strictly above Phase 26 that
        resolves exactly one sealed
        :class:`~quantforge.calibration.result.RiskForecastCalibration` from this
        workspace's shared research sidecar, reads its sealed mean variance ratio,
        population dispersion and calibratable-window count verbatim, and seals the
        one-sample large-sample two-sided significance test of the mean variance ratio
        against the null mean ``1`` into a content-addressed
        :class:`~quantforge.calsig.result.CalibrationSignificance` back to the same
        sidecar - it creates no new store and duplicates no resolution logic, exactly as
        the other derived engines do.
        """
        if self._calibration_significance_engine is None:
            from quantforge.calsig.engine import CalibrationSignificanceEngine

            self._calibration_significance_engine = CalibrationSignificanceEngine(self)
        return self._calibration_significance_engine

    @property
    def campaign_multiplicity_engine(self) -> object:
        """The Phase 30 campaign-multiplicity-correction engine (lazy).

        :class:`~quantforge.campaignmult.engine.CampaignMultiplicityEngine` is imported
        on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first consumer of Phase 23's sealed
        per-trial Probabilistic Sharpe Ratio - a pure consumer strictly above Phase 23
        that resolves exactly one sealed
        :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` from this
        workspace's shared research sidecar, treats its KNOWN per-trial ``psr`` values
        as a single hypothesis family (deriving each trial's one-sided p-value
        ``p = 1 - PSR`` and recording each UNDEFINED-``psr`` trial as a first-class
        exclusion, never imputed), and for each requested
        :class:`~quantforge.campaignmult.model.CorrectionMethod` seals the family-wise /
        false-discovery adjusted ``p`` value plus a rejection flag at a declared
        ``alpha`` (reusing :func:`quantforge.multiplicity.compute.correct_family`
        verbatim), sealing a content-addressed
        :class:`~quantforge.campaignmult.result.CampaignMultiplicityCorrection` back to
        the same sidecar - it creates no new store and duplicates no resolution logic,
        exactly as the other derived engines do.
        """
        if self._campaign_multiplicity_engine is None:
            from quantforge.campaignmult.engine import CampaignMultiplicityEngine

            self._campaign_multiplicity_engine = CampaignMultiplicityEngine(self)
        return self._campaign_multiplicity_engine

    @property
    def net_of_cost_engine(self) -> object:
        """The Phase 31 net-of-cost walk-forward-performance engine (lazy).

        :class:`~quantforge.netcost.engine.NetOfCostEngine` is imported on first use to
        avoid a module-load import cycle (the engine imports :class:`Workspace`). Cached
        for reuse. The first consumer of Phase 27's sealed per-window one-way turnover -
        a pure consumer strictly above Phase 27 that resolves exactly one sealed
        :class:`~quantforge.stability.result.WalkForwardStability` from this workspace's
        shared research sidecar and, transitively, the one
        :class:`~quantforge.walkforward.result.WalkForwardEvaluation` it pins (verifying
        the pinned ``result_hash``), aligns the per-window turnover to the per-period
        gross out-of-sample returns, charges a *declared* linear transaction cost
        ``cost_rate · turnover`` at each realized window's first out-of-sample period,
        summarizes the net series with the reused Phase 19 series summary (consuming the
        gross summary verbatim so the zero-cost identity holds), and reports the
        parameter-free break-even ``Σ gross / Σ turnover`` - sealing a content-addressed
        :class:`~quantforge.netcost.result.NetOfCostPerformance` back to the same
        sidecar. It creates no new store and duplicates no resolution logic, exactly as
        the other derived engines do.
        """
        if self._net_of_cost_engine is None:
            from quantforge.netcost.engine import NetOfCostEngine

            self._net_of_cost_engine = NetOfCostEngine(self)
        return self._net_of_cost_engine

    @property
    def net_of_cost_significance_engine(self) -> object:
        """The Phase 32 net-of-cost-significance engine (lazy).

        :class:`~quantforge.netcostsig.engine.NetOfCostSignificanceEngine` is imported
        on first use to avoid a module-load import cycle (the engine imports
        :class:`Workspace`). Cached for reuse. The first consumer of Phase 31's sealed
        after-cost performance - and the first significance test applied to an economic
        (after-cost) quantity: a pure consumer strictly above Phase 31 that resolves
        exactly one sealed :class:`~quantforge.netcost.result.NetOfCostPerformance` from
        this workspace's shared research sidecar, reads its sealed after-cost mean
        return, population net volatility and net-series period count verbatim, and
        seals the one-sample large-sample upper-tailed significance test of the
        after-cost mean return against the null mean ``0`` into a content-addressed
        :class:`~quantforge.netcostsig.result.NetOfCostSignificance` back to the same
        sidecar - it creates no new store and duplicates no resolution logic, exactly as
        the other derived engines do.
        """
        if self._net_of_cost_significance_engine is None:
            from quantforge.netcostsig.engine import NetOfCostSignificanceEngine

            self._net_of_cost_significance_engine = NetOfCostSignificanceEngine(self)
        return self._net_of_cost_significance_engine

    # -- construction --------------------------------------------------------

    @classmethod
    def open(
        cls,
        root: str | os.PathLike[str] | None = None,
        *,
        config: SecConfig | None = None,
        client: SecClient | None = None,
    ) -> Workspace:
        """Assemble a workspace from a data ``root`` (or the environment).

        When ``root`` is omitted it is read from ``QUANTFORGE_DATA_ROOT``, or
        else derived as the parent of the configured Phase 1 storage dir. A
        network :class:`SecClient` is attached automatically when a User-Agent is
        configured (used only to fetch the ticker mapping once, cache-first); if
        none is available the workspace is fully offline and ticker/name
        resolution requires an already-cached mapping.
        """
        data_root = cls._resolve_root(root, config)
        sec_root = data_root / "sec"
        registry_root = data_root / "registry"
        canonical_root = data_root / "canonical"
        availability_root = data_root / "availability"

        artifacts = ArtifactStore(sec_root)
        registry = FilingRegistry(
            RegistryStore(registry_root), artifact_store=artifacts
        )
        canonical = CanonicalFactStore(canonical_root)
        availability = AvailabilityStore(availability_root)
        sec_client = client if client is not None else cls._maybe_client(config)
        resolver = CompanyResolver(artifacts, client=sec_client)
        return cls(
            artifact_store=artifacts,
            registry=registry,
            canonical_store=canonical,
            resolver=resolver,
            availability_store=availability,
        )

    @staticmethod
    def _resolve_root(
        root: str | os.PathLike[str] | None, config: SecConfig | None
    ) -> Path:
        if root is not None:
            return Path(root)
        env_root = os.environ.get(ENV_DATA_ROOT)
        if env_root:
            return Path(env_root)
        # Fall back to the parent of the Phase 1 storage dir, so a workspace
        # lines up with an already-populated acquisition tree.
        storage_dir = (
            config.storage_dir
            if config is not None
            else os.environ.get(ENV_STORAGE_DIR, "./data/sec")
        )
        return Path(storage_dir).parent

    @staticmethod
    def _maybe_client(config: SecConfig | None) -> SecClient | None:
        """Build a network client only if a valid config is available.

        A missing/invalid User-Agent means we cannot lawfully call SEC, so we
        stay offline rather than fail construction — ticker/name resolution then
        needs an already-cached mapping, and CIK resolution still works.
        """
        from quantforge.sec import build_client
        from quantforge.sec.errors import ConfigError

        try:
            cfg = config if config is not None else SecConfig.from_env()
        except ConfigError:
            return None
        try:
            return build_client(cfg)
        except ConfigError:
            return None
