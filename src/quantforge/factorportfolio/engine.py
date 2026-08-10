"""The factor-portfolio construction orchestration engine (§5, P19-1..5).

:class:`FactorPortfolioEngine` is the Phase 19 composition root - the first member of a
new **portfolio-construction** capability class, a *constructive sibling* of the Phase
16 diagnostic and the Phase 18 regression engines. It sits **above** Phases 9/10/11 and
is a **pure consumer** of them: it turns a declarative
:class:`~quantforge.factorportfolio.spec.FactorPortfolioSpecification` into a sealed,
content-addressed :class:`~quantforge.factorportfolio.result.FactorPortfolio` by
composing - never re-resolving - the Phase 9 universe builder, the Phase 10 panel engine
(``panel_across``), and the Phase 11 price engine (the PIT-gated adjusted view) through
their public accessors. It introduces no new data-resolution logic, no new PIT surface,
and no new store; it consumes **no** ``BacktestResult`` and produces none (P19-5).

The build (§5):

1. **Verify both corpus pins** (P19-1). Re-derive the fundamentals
   :class:`~quantforge.availability.version.DatasetVersion` and the market
   :class:`~quantforge.market.version.MarketDatasetVersion` over the universe's explicit
   source companies (and their securities) and assert each equals the spec's declared
   pin - a mismatch or a non-unique normalizer is a
   :class:`~quantforge.factorportfolio.errors.FactorPortfolioConsistencyError` (fail
   closed, never silently reconciled). This reuses the Phase 16 / Phase 18 machinery
   verbatim.
2. **Per rebalance date ``T``** (in schedule order): resolve membership PIT as-of ``T``
   (Phase 9, survivorship-free), read the signal as-of-``T`` cross-section via
   ``panel_across(..., as_of=T)`` (Phase 10, P19-3), and pair each member with its
   realized **forward** return over ``[T, T+h]`` trading days through the Phase 11
   PIT-gated adjusted view (P19-2). A member missing the signal at ``T``, or with no
   computable forward return, is **excluded and counted in coverage** (P19-4), never
   imputed.
3. **Per date**, sort the surviving members into ``Q`` quantile buckets by the PIT
   signal (the Phase 16 ``quantile_buckets`` rule, reused verbatim), form the long (top
   bucket) / short (bottom bucket) legs, equal-weight within each leg, and compute the
   per-period factor return ``f_T = mean(long) - mean(short)``; a date below the
   member floor (``n_members < 2·Q``) or with an empty long / short leg is a recorded
   UNDEFINED period (never raised, never dropped), contributing no factor return to the
   series.
4. **Aggregate** the ``M`` valid per-period factor returns into a performance summary
   (cumulative / mean / population volatility / annualized Sharpe / t-statistic / hit
   rate) - all under the pinned decimal context, UNDEFINED-preserving (no float, no RNG,
   no wall-clock).
5. **Seal** the computed blocks into a :class:`FactorPortfolio` (its ``result_hash``
   folds the answer) and persist it write-once to the shared Phase 8 research sidecar.
   Rebuilding an identical request over the same immutable corpora is a byte-identical
   no-op.

The engine holds no mutable per-run state - a run's state lives entirely in local
variables, so one engine can construct many specifications and two runs of the same spec
over the same corpora are byte-identical.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Context

from quantforge.availability.timestamps import format_utc_z, parse_utc
from quantforge.availability.version import DatasetVersion
from quantforge.diagnostics.compute import forward_return
from quantforge.factorportfolio.errors import (
    FactorPortfolioConfigurationError,
    FactorPortfolioConsistencyError,
)
from quantforge.factorportfolio.model import (
    CoverageSummary,
    DateCoverage,
    FactorPortfolioStatus,
    FactorReturnSummary,
    LegKind,
    LegMembership,
    PerPeriodReturn,
)
from quantforge.factorportfolio.result import BOUNDARY_PIT, FactorPortfolio
from quantforge.factorportfolio.spec import FactorPortfolioSpecification
from quantforge.factorportfolio.stats import period_factor_return, series_summary
from quantforge.factorportfolio.version import FactorPortfolioEngineVersion
from quantforge.factors.engine import FactorEngine
from quantforge.factors.store import ResearchResultStore
from quantforge.factors.universe import Universe as FactorUniverse
from quantforge.market.axis import PriceAxis
from quantforge.market.engine import PriceEngine
from quantforge.market.identity import company_id_of_security_id
from quantforge.market.model import PriceField, session_key
from quantforge.market.version import MarketDatasetVersion
from quantforge.metrics.model import MetricStatus
from quantforge.panel.axis import PeriodAxis
from quantforge.panel.engine import PanelEngine
from quantforge.registry.identity import cik_from_company_id
from quantforge.universe.builder import UniverseBuilder
from quantforge.universe.filters import ExplicitCompanyFilter
from quantforge.workspace import Workspace

__all__ = ["FactorPortfolioEngine"]

#: The minimum number of scheduled rebalance dates that must yield a *defined* factor
#: return for the return-series summary to carry any time-series information
#: (D-UNDEFINED, §7). With fewer than two valid periods the series has no dispersion
#: (the volatility / Sharpe / t-statistic would all be UNDEFINED), so a run that clears
#: no two periods is a configuration defect - raised, not sealed (the Phase 18
#: ``_MIN_VALID_DATES`` / Phase 16 ``_MIN_PAIRS`` / Phase 15 ``_MIN_PERIODS``
#: precedent).
_MIN_VALID_PERIODS = 2


class FactorPortfolioEngine:
    """Construct a declarative factor-portfolio request to a sealed record (§5,
    P19-1..5).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's cached Phase 8 :class:`FactorEngine` (for the Phase 7
    metric engine + the shared research sidecar), Phase 10 :class:`PanelEngine`, and
    Phase 11 :class:`PriceEngine`, and builds a Phase 9 :class:`UniverseBuilder` over
    the same metric engine - creating no new store and duplicating no resolution logic.
    Every dependency may be overridden (for tests). It pins its construction +
    statistics logic + formula + decimal context via
    :class:`FactorPortfolioEngineVersion` and computes every statistic under that
    version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        factor_engine: FactorEngine | None = None,
        panel_engine: PanelEngine | None = None,
        price_engine: PriceEngine | None = None,
        universe_builder: UniverseBuilder | None = None,
        engine_version: FactorPortfolioEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        fe = factor_engine if factor_engine is not None else workspace.factor_engine
        assert isinstance(fe, FactorEngine)  # the workspace builds exactly this
        self._factor_engine = fe
        pne = panel_engine if panel_engine is not None else workspace.panel_engine
        assert isinstance(pne, PanelEngine)
        self._panel_engine = pne
        pe = price_engine if price_engine is not None else workspace.price_engine
        assert isinstance(pe, PriceEngine)
        self._price_engine = pe
        self._universe_builder = (
            universe_builder
            if universe_builder is not None
            else UniverseBuilder(workspace)
        )
        self._version = engine_version or FactorPortfolioEngineVersion()

    @property
    def engine_version(self) -> FactorPortfolioEngineVersion:
        return self._version

    @property
    def factor_portfolio_engine_version_id(self) -> str:
        """The engine-logic + formula + decimal-context version folded into every id."""
        return self._version.factor_portfolio_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The shared Phase 8 research sidecar this engine seals records to.

        Exposed (and overridable in tests) exactly as the Phase 16 / Phase 18 siblings
        expose their store, so ``engine.research_store.write(...)`` is the single seam.
        """
        return self._factor_engine.research_store

    # -- corpus pins (P19-1) -------------------------------------------------

    def fundamentals_dataset_version(
        self, spec: FactorPortfolioSpecification
    ) -> DatasetVersion:
        """The universe-wide fundamentals snapshot over the spec's declared source (§5).

        The union of each source filer's per-filer
        :meth:`~quantforge.metrics.engine.MetricEngine.dataset_version_for` snapshot -
        the exact derivation the Phase 16 diagnostics engine, the Phase 18 regression
        engine, and the Phase 12 backtester use - so the pin is a deterministic function
        of the *specification* (its explicit source members), independent of the
        schedule. A caller pins ``spec.dataset_version_id`` to ``.dataset_version_id``
        of this.
        """
        raw_docs: set[str] = set()
        fact_ids: set[str] = set()
        policy_ids: set[str] = set()
        tvs: set[str] = set()
        fallback_tv: str | None = None
        metric_engine = self._factor_engine.metric_engine
        for company_id in self._source_company_ids(spec):
            cik = cik_from_company_id(company_id)
            per_filer = metric_engine.dataset_version_for(cik)
            fallback_tv = per_filer.transformation_version_id
            raw_docs.update(per_filer.raw_document_ids)
            fact_ids.update(per_filer.fact_ids)
            policy_ids.update(per_filer.availability_policy_ids)
            if per_filer.fact_ids:
                tvs.add(per_filer.transformation_version_id)
        if len(tvs) > 1:
            raise FactorPortfolioConsistencyError(
                "source filers were normalized under differing transformation "
                f"versions {sorted(tvs)}; one fundamentals corpus requires one "
                "normalizer (P19-1)"
            )
        transformation_version_id = tvs.pop() if tvs else (fallback_tv or "")
        return DatasetVersion(
            transformation_version_id=transformation_version_id,
            availability_policy_ids=tuple(sorted(policy_ids)),
            raw_document_ids=tuple(sorted(raw_docs)),
            fact_ids=tuple(sorted(fact_ids)),
        )

    def market_dataset_version(
        self, spec: FactorPortfolioSpecification
    ) -> MarketDatasetVersion:
        """The universe-wide market snapshot over the spec's declared source (§5).

        The union of each source security's per-instrument
        :meth:`~quantforge.market.engine.PriceEngine.dataset_version_for` snapshot - the
        exact derivation the backtester and the Phase 16 / Phase 18 engines use. A
        caller pins ``spec.market_dataset_version_id`` to ``.dataset_version_id`` of
        this.
        Deterministic and schedule-independent.
        """
        policy_ids: set[str] = set()
        raw_docs: set[str] = set()
        obs_ids: set[str] = set()
        action_ids: set[str] = set()
        tvs: set[str] = set()
        fallback_tv = (
            self._price_engine.transformation_version.market_transformation_version_id
        )
        source_ids = frozenset(self._source_company_ids(spec))
        for security_id in self._securities_for_companies(source_ids):
            dv = self._price_engine.dataset_version_for(security_id)
            tvs.add(dv.market_transformation_version_id)
            policy_ids.update(dv.market_availability_policy_ids)
            raw_docs.update(dv.raw_document_ids)
            obs_ids.update(dv.price_observation_ids)
            action_ids.update(dv.corporate_action_ids)
        if len(tvs) > 1:
            raise FactorPortfolioConsistencyError(
                "source securities were normalized under differing market "
                f"transformation versions {sorted(tvs)}; one market corpus requires "
                "one normalizer (P19-1)"
            )
        transformation_version_id = tvs.pop() if tvs else fallback_tv
        return MarketDatasetVersion(
            market_transformation_version_id=transformation_version_id,
            market_availability_policy_ids=tuple(sorted(policy_ids)),
            raw_document_ids=tuple(sorted(raw_docs)),
            price_observation_ids=tuple(sorted(obs_ids)),
            corporate_action_ids=tuple(sorted(action_ids)),
        )

    def _verify_corpus_pins(self, spec: FactorPortfolioSpecification) -> None:
        """Re-derive both corpus snapshots and fail closed on any mismatch (P19-1)."""
        derived_fundamentals = self.fundamentals_dataset_version(
            spec
        ).dataset_version_id
        if derived_fundamentals != spec.dataset_version_id:
            raise FactorPortfolioConsistencyError(
                "pinned fundamentals dataset_version_id does not match the corpus on "
                f"re-derivation (pinned {spec.dataset_version_id!r}, re-derived "
                f"{derived_fundamentals!r}); the corpus changed under the pin (P19-1)"
            )
        derived_market = self.market_dataset_version(spec).dataset_version_id
        if derived_market != spec.market_dataset_version_id:
            raise FactorPortfolioConsistencyError(
                "pinned market_dataset_version_id does not match the corpus on "
                f"re-derivation (pinned {spec.market_dataset_version_id!r}, re-derived "
                f"{derived_market!r}); the market corpus changed under the pin (P19-1)"
            )

    def _source_company_ids(self, spec: FactorPortfolioSpecification) -> list[str]:
        """The specification's explicit source ``company_id``s, first-seen order.

        Resolves the first (source) filter's identifiers through the same resolver the
        universe builder uses. The specification's source filter must be an
        :class:`ExplicitCompanyFilter`; a differently-shaped source cannot pin a
        reproducible corpus and is a configuration defect.
        """
        source = spec.universe.filters[0]
        if not isinstance(source, ExplicitCompanyFilter):
            raise FactorPortfolioConfigurationError(
                "the universe specification's source filter must be an "
                "ExplicitCompanyFilter to pin a reproducible corpus"
            )
        resolver = self._workspace.resolver
        company_ids: list[str] = []
        seen: set[str] = set()
        for identifier in source.identifiers:
            identity = resolver.resolve(identifier, by=source.by)
            if identity.company_id in seen:
                continue
            seen.add(identity.company_id)
            company_ids.append(identity.company_id)
        return company_ids

    def _company_security_map(self) -> dict[str, list[str]]:
        """A ``company_id`` -> sorted ``security_id``s map over the whole market corpus.

        Built once per run from the pinned market store. A ``figi:`` security (no
        offline issuer) maps to no company and is skipped (its fundamentals join needs
        the external mapping - Phase 11 §7).
        """
        mapping: dict[str, list[str]] = {}
        for security_id in self._price_engine.store.list_security_ids():
            company_id = company_id_of_security_id(security_id)
            if company_id is None:
                continue
            mapping.setdefault(company_id, []).append(security_id)
        for security_ids in mapping.values():
            security_ids.sort()
        return mapping

    def _securities_for_companies(self, company_ids: frozenset[str]) -> list[str]:
        """Every ``security_id`` owned by one of ``company_ids``, sorted (corpus
        pin)."""
        mapping = self._company_security_map()
        found: list[str] = []
        for company_id in sorted(company_ids):
            found.extend(mapping.get(company_id, ()))
        return sorted(found)

    # -- the construction (§5) -----------------------------------------------

    def construct(self, spec: FactorPortfolioSpecification) -> FactorPortfolio:
        """Construct ``spec`` and return the sealed, content-addressed record (§5).

        Deterministic and reproducible: the same spec over the same immutable corpora
        re-resolves the same PIT signal cross-sections, re-forms byte-identical legs,
        recomputes byte-identical statistics under the pinned decimal context, and seals
        a byte-identical :class:`FactorPortfolio` on any machine (whose sidecar write is
        an idempotent no-op). Fails closed on a corpus-pin mismatch or a non-unique
        normalizer (P19-1) and on a run in which fewer than two rebalance dates yield a
        defined factor return (§7, D-UNDEFINED); every data condition (a member missing
        the signal or a forward return, a period below the member floor or with an empty
        long / short leg, a series with no or a single valid period, a zero-variance
        series) is recorded as a first-class UNDEFINED value, never raised (P19-4).
        """
        if not isinstance(spec, FactorPortfolioSpecification):
            raise FactorPortfolioConfigurationError(
                "construct() requires a FactorPortfolioSpecification"
            )

        # P19-1: re-derive and verify both corpus pins before touching any data.
        self._verify_corpus_pins(spec)

        context = self._version.decimal_context()
        company_security_map = self._company_security_map()
        close_cache: dict[str, list[str]] = {}

        per_period: list[PerPeriodReturn] = []
        coverage_dates: list[DateCoverage] = []
        # The KNOWN per-period factor returns, in schedule order, for the series
        # summary.
        factor_return_series: list[str] = []
        valid_periods = 0
        total_resolved = 0
        total_dropped_signal = 0
        total_dropped_return = 0
        total_undefined_periods = 0

        for as_of in spec.schedule.as_of_instants():
            as_of_z = format_utc_z(as_of)

            # 2a. Membership at T (survivorship-free, Phase 9).
            construction = self._universe_builder.build_as_of(spec.universe, as_of)
            member_company_ids = construction.universe.company_ids
            resolved_members = len(member_company_ids)
            total_resolved += resolved_members

            # 2b. The as-of-T signal cross-section (Phase 10, P19-3). An empty universe
            #     reads no panel (the factor universe fails closed on empty). Signals
            #     are keyed by company_id, KNOWN cells only.
            signal_by_company: dict[str, str] = {}
            if member_company_ids:
                factor_universe = FactorUniverse.from_iterable(member_company_ids)
                panel = self._panel_engine.panel_across(
                    spec.signal,
                    factor_universe,
                    PeriodAxis.of([spec.period]),
                    as_of,
                )
                for cell in panel.cells:
                    if (
                        cell.metric.status is MetricStatus.KNOWN
                        and cell.metric.value_numeric_str is not None
                    ):
                        signal_by_company[cell.company_id] = (
                            cell.metric.value_numeric_str
                        )

            # 2c. Pair each member's signal with its realized forward return (P19-4).
            eligible: list[tuple[str, str, str]] = []
            dropped_signal = 0
            dropped_return = 0
            for company_id in member_company_ids:
                signal_value = signal_by_company.get(company_id)
                if signal_value is None:
                    # A member lacking the PIT signal at T is excluded (never imputed)
                    # and counted as dropped-for-signal (P19-4).
                    dropped_signal += 1
                    continue
                fwd = self._forward_return(
                    company_id,
                    as_of,
                    spec.horizon_days,
                    company_security_map,
                    close_cache,
                    context,
                )
                if fwd is None:
                    dropped_return += 1
                    continue
                eligible.append((company_id, signal_value, fwd))

            n_members = len(eligible)
            total_dropped_signal += dropped_signal
            total_dropped_return += dropped_return

            # 2d/3. Quantile leg formation + the long-minus-short factor return
            #       (UNDEFINED-preserving; §12). A period below the member floor or with
            #       an empty long / short leg is a recorded UNDEFINED period; it neither
            #       raises nor contributes to the series.
            leg = period_factor_return(eligible, spec.quantiles, context=context)
            factor_cell = leg.factor_return
            if factor_cell.status is FactorPortfolioStatus.KNOWN:
                assert factor_cell.value is not None
                valid_periods += 1
                factor_return_series.append(factor_cell.value)
                period_status = FactorPortfolioStatus.KNOWN.value
            else:
                total_undefined_periods += 1
                assert factor_cell.reason is not None
                period_status = factor_cell.reason.value

            per_period.append(
                PerPeriodReturn(
                    as_of=as_of_z,
                    n_members=n_members,
                    long_membership=LegMembership(
                        kind=LegKind.LONG, company_ids=leg.long_ids
                    ),
                    short_membership=LegMembership(
                        kind=LegKind.SHORT, company_ids=leg.short_ids
                    ),
                    long_return=leg.long_return,
                    short_return=leg.short_return,
                    factor_return=factor_cell,
                )
            )
            coverage_dates.append(
                DateCoverage(
                    as_of=as_of_z,
                    resolved_members=resolved_members,
                    eligible=n_members,
                    dropped_for_signal=dropped_signal,
                    dropped_for_return=dropped_return,
                    period_status=period_status,
                )
            )

        # Fewer than two valid periods -> a meaningless series with no dispersion;
        # raised (§7, D-UNDEFINED).
        if valid_periods < _MIN_VALID_PERIODS:
            raise FactorPortfolioConfigurationError(
                f"only {valid_periods} scheduled rebalance date(s) yielded a defined "
                f"factor return, but at least {_MIN_VALID_PERIODS} are required for a "
                "return-series summary with time-series dispersion (fail closed rather "
                "than seal a record with no valid periods)"
            )

        # 4. Aggregate the valid per-period factor returns into a summary (§12).
        summary = series_summary(
            factor_return_series,
            risk_free_per_period=spec.risk_free_per_period,
            periods_per_year=spec.periods_per_year,
            context=context,
        )

        # 5. Seal and persist write-once to the shared research sidecar.
        portfolio = FactorPortfolio.seal(
            factor_portfolio_engine_version_id=(
                self._version.factor_portfolio_engine_version_id
            ),
            factor_portfolio_spec=spec.to_dict(),
            name=spec.name,
            spec_version=spec.spec_version,
            signal=spec.signal,
            period_key=spec.period.period_key,
            universe_specification_id=spec.universe.specification_id,
            schedule_id=spec.schedule.schedule_id,
            horizon_days=spec.horizon_days,
            quantiles=spec.quantiles,
            weighting=spec.weighting,
            boundary_kind=BOUNDARY_PIT,
            risk_free_per_period=spec.risk_free_per_period,
            periods_per_year=spec.periods_per_year,
            dataset_version_id=spec.dataset_version_id,
            market_dataset_version_id=spec.market_dataset_version_id,
            per_period=tuple(per_period),
            summary=FactorReturnSummary(
                cumulative_return=summary.cumulative_return,
                mean_period_return=summary.mean_period_return,
                volatility=summary.volatility,
                annualized_sharpe=summary.annualized_sharpe,
                mean_t_stat=summary.mean_t_stat,
                hit_rate=summary.hit_rate,
                n_valid_periods=summary.n_valid_periods,
            ),
            coverage=CoverageSummary(
                per_date=tuple(coverage_dates),
                total_resolved=total_resolved,
                total_dropped_for_signal=total_dropped_signal,
                total_dropped_for_return=total_dropped_return,
                total_undefined_periods=total_undefined_periods,
            ),
            formula_version=self._version.formula_version,
        )
        self.research_store.write(portfolio)
        return portfolio

    # -- forward return (§5, P19-2, P19-4) ----------------------------------

    def _forward_return(
        self,
        company_id: str,
        as_of: datetime,
        horizon_days: int,
        company_security_map: dict[str, list[str]],
        close_cache: dict[str, list[str]],
        context: Context,
    ) -> str | None:
        """The realized forward return over ``[T, T+h]`` trading days, or ``None`` (§5).

        Reused verbatim from the Phase 16 / Phase 18 engines (D-FWD): the member's
        ``company_id`` is mapped to its single tradable ``security_id`` (a company with
        no tradable security - or, for v1, more than one - is dropped for return, never
        guessed); the base trading date is the latest stored close on-or-before ``T``,
        the end the close ``h`` trading days later; both endpoints are read through the
        Phase 11 PIT-gated adjusted view at the **window-end ``as_of``** (the instant
        the ``T+h`` session becomes knowable), so split/dividend adjustment is
        consistent and free of revision leak. A missing/UNKNOWN endpoint, a non-positive
        base, or a window that runs past the stored history -> ``None`` (dropped for
        return, P19-4). This is an ex-post read (P19-2): the window end is strictly
        after ``T``.
        """
        securities = company_security_map.get(company_id, [])
        if len(securities) != 1:
            return None
        security_id = securities[0]

        close_dates = self._close_dates(security_id, close_cache)
        if not close_dates:
            return None
        as_of_date = as_of.date().isoformat()
        # The base is the latest stored close trading date on-or-before T.
        base_index = -1
        for index, trading_date in enumerate(close_dates):
            if trading_date <= as_of_date:
                base_index = index
            else:
                break
        if base_index < 0:
            return None
        end_index = base_index + horizon_days
        if end_index >= len(close_dates):
            # The window runs past the stored history - a delisting inside the window
            # with no recovery price, or simply not enough forward data. Dropped for
            # return.
            return None
        base_date = close_dates[base_index]
        end_date = close_dates[end_index]

        # The window-end as_of is the instant the T+h close becomes knowable; a session
        # that never becomes PIT-eligible yields no forward return (dropped for return).
        window_end = self._session_available_at(security_id, end_date)
        if window_end is None:
            return None

        series = self._price_engine.adjusted_series_as_of(
            security_id, PriceAxis.of([base_date, end_date]), window_end
        )
        by_date = {cell.trading_date: cell for cell in series.cells}
        base_cell = by_date.get(base_date)
        end_cell = by_date.get(end_date)
        if base_cell is None or end_cell is None:
            return None
        if not base_cell.is_known or base_cell.value_numeric_str is None:
            return None
        if not end_cell.is_known or end_cell.value_numeric_str is None:
            return None
        return forward_return(
            base_cell.value_numeric_str, end_cell.value_numeric_str, context=context
        )

    def _close_dates(
        self, security_id: str, close_cache: dict[str, list[str]]
    ) -> list[str]:
        """The security's stored CLOSE trading dates, ascending (cached per run).

        Drawn from the pinned market store's observations - the same candidate set the
        Phase 11 engine walks for its own PIT marks - so the forward-return window rides
        the corporate calendar without introducing a new resolver.
        """
        cached = close_cache.get(security_id)
        if cached is not None:
            return cached
        dates = sorted(
            {
                obs.trading_date
                for obs in self._price_engine.store.read_observations(security_id)
                if obs.field is PriceField.CLOSE
            }
        )
        close_cache[security_id] = dates
        return dates

    def _session_available_at(
        self, security_id: str, trading_date: str
    ) -> datetime | None:
        """The instant a session's close becomes PIT-eligible, or ``None`` (§5, P19-2).

        Replicates the Phase 11 availability gate over the same store reads: a session
        is knowable only when its availability is PIT-eligible and carries a derived
        public availability timestamp. The returned instant is the window-end ``as_of``
        at which the forward endpoints are read, so both endpoints are honestly eligible
        and only corporate actions available by then are applied (no revision leak).
        """
        availability = self._price_engine.store.read_availability_map(security_id)
        av = availability.get(session_key(security_id, trading_date))
        if av is None or not av.is_pit_eligible:
            return None
        ts = av.derived_public_availability_timestamp
        if ts is None:
            return None
        return parse_utc(ts)
