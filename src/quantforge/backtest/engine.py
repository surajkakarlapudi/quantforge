"""The deterministic simulation engine — declarative spec → sealed result (§A-§H).

:class:`BacktestEngine` is the Phase 12 composition root. It turns a declarative
:class:`~quantforge.backtest.spec.BacktestSpecification` plus the pinned PIT corpus
into a sealed, content-addressed
:class:`~quantforge.backtest.result.BacktestResult`, composing — never re-resolving —
the Phase 7/8/9/10/11 engines through their public ``*_as_of`` accessors (proposal
§J). It introduces no new data-resolution logic: Phase 5 already decided eligibility,
Phase 7 the metric arithmetic, Phase 9 the membership, Phase 11 the prices. The engine
adds only the walk over the rebalance schedule, deterministic portfolio accounting,
and the identity seal.

The invariants it enforces, verbatim (proposal §A, BT-1..BT-4; the nine correctness
requirements):

* **No look-ahead (BT-2).** The strategy signal at each instant ``T`` is resolved
  through an :class:`~quantforge.backtest.context.AsOfContext` bound to ``T`` — every
  accessor is availability-gated at ``T`` and returns only ``Pit*`` results. Execution
  and marking use the **latest PIT-eligible close as of** ``T`` (a bar not knowable at
  ``T`` is never used), so no future or revised value can enter a decision or a mark.
* **Corpus pinning (BT-1).** Before simulating, the engine re-derives both corpus
  snapshots — the fundamentals :class:`~quantforge.availability.version.DatasetVersion`
  and the :class:`~quantforge.market.version.MarketDatasetVersion` — from the
  specification's declared source and verifies each against the pinned id; a mismatch
  is a :class:`~quantforge.backtest.errors.BacktestConsistencyError` (fail closed).
* **Survivorship-free (Phase 9).** Membership is rebuilt at every ``T`` via
  :meth:`~quantforge.universe.builder.UniverseBuilder.build_as_of`, so a filer later
  delisted is present at the instants it was public and a filer not yet public is
  absent — never today's membership applied to the past.
* **Fail-closed simulation (BT-4).** A data/simulation condition — an ``UNDEFINED``
  signal, a member with no tradable security, a price not knowable at ``T`` — is
  recorded in the ledger (an excluded member, an ``unfilled`` fill, a flagged action),
  never raised. Only a configuration/consistency defect (a malformed spec, a mixed
  currency, a corpus-pin mismatch) is raised.
* **Determinism + identity (§G, D6).** All arithmetic runs under one pinned decimal
  :class:`~decimal.Context` (precision 34, ``ROUND_HALF_EVEN``); every iteration is
  sorted. ``result_hash`` seals the ordered per-rebalance outcome digests, and
  ``backtest_id`` folds in every result-changing input, so identical inputs reproduce
  an identical id and result on any machine.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Context, Decimal, InvalidOperation, localcontext

from quantforge.availability.timestamps import format_utc_z, parse_utc
from quantforge.availability.version import DatasetVersion
from quantforge.backtest.context import AsOfContext
from quantforge.backtest.errors import (
    BacktestConfigurationError,
    BacktestConsistencyError,
)
from quantforge.backtest.identity import backtest_id as _backtest_id
from quantforge.backtest.identity import result_hash as _result_hash
from quantforge.backtest.portfolio import Portfolio
from quantforge.backtest.result import (
    AppliedAction,
    BacktestResult,
    Fill,
    PerformanceSummary,
    RebalanceRecord,
    SignalRef,
    TargetWeights,
)
from quantforge.backtest.spec import BacktestSpecification
from quantforge.backtest.stats import compute_statistics
from quantforge.backtest.version import BacktestEngineVersion
from quantforge.factors.engine import FactorEngine
from quantforge.factors.model import FactorCell
from quantforge.factors.universe import Universe as FactorUniverse
from quantforge.market.engine import PriceEngine
from quantforge.market.identity import company_id_of_security_id
from quantforge.market.model import CorporateAction, CorporateActionKind, PriceField
from quantforge.market.result import PitPrice
from quantforge.market.version import MarketDatasetVersion
from quantforge.metrics.model import MetricStatus
from quantforge.panel.engine import PanelEngine
from quantforge.registry.identity import cik_from_company_id
from quantforge.universe.builder import UniverseBuilder
from quantforge.universe.filters import ExplicitCompanyFilter
from quantforge.workspace import Workspace

__all__ = ["BacktestEngine"]

_ZERO = Decimal(0)
_ONE = Decimal(1)

# Fill/side vocabulary — stable strings folded into the ledger's outcome digests.
_SIDE_BUY = "buy"
_SIDE_SELL = "sell"
_STATUS_FILLED = "filled"
_STATUS_UNFILLED = "unfilled"

# The reasons a data/simulation condition is recorded rather than raised (BT-4).
_REASON_NO_MARK = "no_pit_price"
_REASON_NO_SECURITY = "no_tradable_security"
_REASON_DELISTED_NO_PRICE = "delisted_no_price"


class BacktestEngine:
    """Run a declarative :class:`BacktestSpecification` to a sealed result (§A-§H).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's cached Phase 8 :class:`FactorEngine`, Phase 10
    :class:`PanelEngine`, and Phase 11 :class:`PriceEngine`, and builds a Phase 9
    :class:`UniverseBuilder` over the same metric engine. Every dependency may be
    overridden (for tests). The engine holds no mutable per-run state — a run's state
    lives entirely in local variables, so one engine can run many specifications and
    two runs of the same spec are byte-identical.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        factor_engine: FactorEngine | None = None,
        price_engine: PriceEngine | None = None,
        panel_engine: PanelEngine | None = None,
        universe_builder: UniverseBuilder | None = None,
        engine_version: BacktestEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        fe = factor_engine if factor_engine is not None else workspace.factor_engine
        assert isinstance(fe, FactorEngine)  # the workspace builds exactly this
        self._factor_engine = fe
        pe = price_engine if price_engine is not None else workspace.price_engine
        assert isinstance(pe, PriceEngine)
        self._price_engine = pe
        pne = panel_engine if panel_engine is not None else workspace.panel_engine
        assert isinstance(pne, PanelEngine)
        self._panel_engine = pne
        self._universe_builder = (
            universe_builder
            if universe_builder is not None
            else UniverseBuilder(workspace)
        )
        self._version = engine_version or BacktestEngineVersion()

    @property
    def engine_version(self) -> BacktestEngineVersion:
        return self._version

    def _context(self) -> Context:
        """A fresh copy of the pinned decimal context for a single arithmetic scope."""
        return self._version.decimal_context()

    # -- corpus pins (BT-1, D4) ---------------------------------------------

    def fundamentals_dataset_version(
        self, spec: BacktestSpecification
    ) -> DatasetVersion:
        """The universe-wide fundamentals snapshot over the spec's declared source.

        The union of each source filer's per-filer
        :meth:`~quantforge.metrics.engine.MetricEngine.dataset_version_for` snapshot —
        mirroring :meth:`FactorEngine._universe_dataset_version` — so the pin is a
        deterministic function of the *specification* (its explicit source members),
        independent of the rebalance schedule. A caller pins
        ``spec.dataset_version_id`` to ``.dataset_version_id`` of this.
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
            raise BacktestConsistencyError(
                "source filers were normalized under differing transformation "
                f"versions {sorted(tvs)}; one fundamentals corpus requires one "
                "normalizer"
            )
        transformation_version_id = tvs.pop() if tvs else (fallback_tv or "")
        return DatasetVersion(
            transformation_version_id=transformation_version_id,
            availability_policy_ids=tuple(sorted(policy_ids)),
            raw_document_ids=tuple(sorted(raw_docs)),
            fact_ids=tuple(sorted(fact_ids)),
        )

    def market_dataset_version(
        self, spec: BacktestSpecification
    ) -> MarketDatasetVersion:
        """The universe-wide market snapshot over the spec's declared source (§14).

        The union of each source security's per-instrument
        :meth:`~quantforge.market.engine.PriceEngine.dataset_version_for` snapshot: the
        normalizer version, and the union of availability-policy / raw-document /
        observation / corporate-action ids across every security owned by a source
        filer. A caller pins ``spec.market_dataset_version_id`` to
        ``.dataset_version_id`` of this. Deterministic and schedule-independent.
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
            raise BacktestConsistencyError(
                "source securities were normalized under differing market "
                f"transformation versions {sorted(tvs)}; one market corpus requires "
                "one normalizer"
            )
        transformation_version_id = tvs.pop() if tvs else fallback_tv
        return MarketDatasetVersion(
            market_transformation_version_id=transformation_version_id,
            market_availability_policy_ids=tuple(sorted(policy_ids)),
            raw_document_ids=tuple(sorted(raw_docs)),
            price_observation_ids=tuple(sorted(obs_ids)),
            corporate_action_ids=tuple(sorted(action_ids)),
        )

    def _verify_corpus_pins(self, spec: BacktestSpecification) -> None:
        """Re-derive both corpus snapshots and fail closed on any mismatch (BT-1)."""
        derived_fundamentals = self.fundamentals_dataset_version(
            spec
        ).dataset_version_id
        if derived_fundamentals != spec.dataset_version_id:
            raise BacktestConsistencyError(
                "pinned fundamentals dataset_version_id does not match the corpus on "
                f"re-derivation (pinned {spec.dataset_version_id!r}, re-derived "
                f"{derived_fundamentals!r}); the corpus changed under the pin (BT-1)"
            )
        derived_market = self.market_dataset_version(spec).dataset_version_id
        if derived_market != spec.market_dataset_version_id:
            raise BacktestConsistencyError(
                "pinned market_dataset_version_id does not match the corpus on "
                f"re-derivation (pinned {spec.market_dataset_version_id!r}, re-derived "
                f"{derived_market!r}); the market corpus changed under the pin (BT-1)"
            )

    def _source_company_ids(self, spec: BacktestSpecification) -> list[str]:
        """The specification's explicit source ``company_id``s, first-seen order.

        Resolves the first (source) filter's identifiers through the same resolver the
        universe builder uses (§9.2). The specification guarantees the first filter is
        an :class:`ExplicitCompanyFilter`; a differently-shaped source is a defect.
        """
        source = spec.universe.filters[0]
        if not isinstance(source, ExplicitCompanyFilter):
            raise BacktestConfigurationError(
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
        """A ``company_id`` → sorted ``security_id``s map over the whole market corpus.

        Built once per run from the pinned market store. A ``figi:`` security (no
        offline issuer) maps to no company and is skipped (its fundamentals join needs
        the external mapping — Phase 11 §7).
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

    # -- the run (§A) --------------------------------------------------------

    def run(
        self,
        spec: BacktestSpecification,
        *,
        risk_free_per_period: str = "0",
        periods_per_year: str = "1",
    ) -> BacktestResult:
        """Simulate ``spec`` and return the sealed, content-addressed result (§A-§H).

        ``risk_free_per_period`` and ``periods_per_year`` are the **recorded**
        Sharpe/annualization convention (proposal §L question 3): they parameterize the
        performance summary but not the simulation, so they never enter the
        ``result_hash`` (which seals only the rebalance ledger). They *are* folded into
        the ``backtest_id`` (D6): they change the reported statistics, so two runs that
        differ only in the annualization convention are materially different results and
        must not collide on one id — they share a ``result_hash`` and ledger but get
        distinct ``backtest_id``s and a differently-annualized Sharpe.
        """
        if not isinstance(spec, BacktestSpecification):
            raise BacktestConfigurationError("run() requires a BacktestSpecification")

        # BT-1: re-derive and verify both corpus pins before touching the simulation.
        self._verify_corpus_pins(spec)

        context = self._context()
        company_security_map = self._company_security_map()
        portfolio = Portfolio.initial(spec.initial_capital, context)

        # Actions are applied at most once, at the first rebalance they are PIT-eligible
        # and the security is held (§D rule 1). This is the only cross-rebalance state.
        applied_action_ids: set[str] = set()

        ledger: list[RebalanceRecord] = []
        equity_curve: list[Decimal] = []
        turnovers: list[Decimal] = []

        for as_of in spec.schedule.as_of_instants():
            record = self._rebalance(
                spec=spec,
                as_of=as_of,
                portfolio=portfolio,
                company_security_map=company_security_map,
                applied_action_ids=applied_action_ids,
                context=context,
            )
            ledger.append(record)
            equity_curve.append(Decimal(record.equity))
            turnovers.append(Decimal(record.turnover))

        statistics = compute_statistics(
            equity_curve,
            turnovers,
            context=context,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
        )
        # Canonicalize the recorded convention once, so the summary and the identity
        # fold in byte-identical strings ("0" and "0.0" can never disagree).
        canonical_rf = str(+Decimal(risk_free_per_period))
        canonical_ppy = str(+Decimal(periods_per_year))
        performance = PerformanceSummary(
            statistics=statistics,
            risk_free_per_period=canonical_rf,
            periods_per_year=canonical_ppy,
        )

        rhash = _result_hash([r.outcome_digest() for r in ledger])
        bt_id = _backtest_id(
            strategy_version=spec.strategy.strategy_version,
            schedule_id=spec.schedule.schedule_id,
            universe_id=spec.universe_id,
            dataset_version_id=spec.dataset_version_id,
            market_dataset_version_id=spec.market_dataset_version_id,
            cost_model_id=spec.cost_model.cost_model_id,
            accounting_version_id=spec.accounting.accounting_version_id,
            backtest_engine_version_id=self._version.backtest_engine_version_id,
            risk_free_per_period=canonical_rf,
            periods_per_year=canonical_ppy,
            result_hash=rhash,
        )
        result = BacktestResult(
            backtest_id=bt_id,
            result_hash=rhash,
            strategy_version=spec.strategy.strategy_version,
            schedule_id=spec.schedule.schedule_id,
            universe_id=spec.universe_id,
            dataset_version_id=spec.dataset_version_id,
            market_dataset_version_id=spec.market_dataset_version_id,
            cost_model_id=spec.cost_model.cost_model_id,
            accounting_version_id=spec.accounting.accounting_version_id,
            backtest_engine_version_id=self._version.backtest_engine_version_id,
            base_currency=spec.base_currency,
            initial_capital=spec.initial_capital,
            performance=performance,
            ledger=tuple(ledger),
        )
        # Persist write-once to the shared research sidecar (D7). Idempotent for a
        # byte-identical re-run; a differing payload under the same id raises there.
        self._factor_engine.research_store.write(result)
        return result

    # -- one rebalance -------------------------------------------------------

    def _rebalance(
        self,
        *,
        spec: BacktestSpecification,
        as_of: datetime,
        portfolio: Portfolio,
        company_security_map: dict[str, list[str]],
        applied_action_ids: set[str],
        context: Context,
    ) -> RebalanceRecord:
        """Apply eligible actions, resolve the signal, trade, mark, and record (§H)."""
        ctx = AsOfContext(
            as_of=as_of,
            panel_engine=self._panel_engine,
            factor_engine=self._factor_engine,
            price_engine=self._price_engine,
            universe_builder=self._universe_builder,
        )

        # 1. Corporate actions first — applied to holdings *before* the rebalance trades
        #    (§H ordering), only when PIT-eligible at T and not already applied.
        actions_applied = self._apply_corporate_actions(
            as_of=as_of,
            portfolio=portfolio,
            base_currency=spec.base_currency,
            applied_action_ids=applied_action_ids,
            context=context,
        )

        # 2. Membership at T (survivorship-free) and the cross-sectional signal.
        construction = ctx.universe(spec.universe)
        member_company_ids = construction.universe.company_ids
        signals: list[SignalRef] = []
        selected_company_ids: list[str] = []
        if member_company_ids:
            factor_universe = FactorUniverse.from_iterable(member_company_ids)
            factor = ctx.factor(
                spec.strategy.signal_metric_key,
                factor_universe,
                spec.strategy.signal_period,
            )
            signals.append(
                SignalRef(kind="factor", result_id=factor.research_result_id)
            )
            selected_company_ids = self._select(spec, factor.cells)

        # 3. Selection → target weights keyed by security_id (BT-3: the strategy's only
        #    output). Untradable selected names hold their weight mass in cash (honest,
        #    never silently renormalized).
        target_weights, target_sids = self._target_weights(
            selected_company_ids, company_security_map, context
        )

        # 4. Mark, size, and execute the rebalance at the PIT close as of T.
        fills, equity, turnover = self._execute(
            as_of=as_of,
            portfolio=portfolio,
            target_weights=target_weights,
            target_sids=target_sids,
            cost_model=spec.cost_model,
            context=context,
        )

        return RebalanceRecord(
            as_of=format_utc_z(as_of),
            universe_id=construction.universe.universe_id,
            signals=tuple(signals),
            target_weights=target_weights,
            actions_applied=tuple(actions_applied),
            fills=tuple(fills),
            positions=portfolio.positions(),
            cash=str(portfolio.cash),
            equity=str(equity),
            turnover=str(turnover),
        )

    # -- selection & weighting -----------------------------------------------

    def _select(
        self, spec: BacktestSpecification, cells: tuple[FactorCell, ...]
    ) -> list[str]:
        """Rank the KNOWN cells and select the top ``n`` (fail-closed on UNDEFINED).

        A member whose signal is ``UNDEFINED`` at ``T`` is excluded from selection
        (BT-4), never guessed. Ranking is by numeric value, tie-broken by ``company_id``
        for total-order determinism (proposal §G rule 3); ``k`` larger than the eligible
        set selects the whole eligible set (recorded, never an error).
        """
        known: list[tuple[Decimal, str]] = []
        for cell in cells:
            if cell.metric.status is not MetricStatus.KNOWN:
                continue
            value_str = cell.metric.value_numeric_str
            if value_str is None:
                continue
            known.append((Decimal(value_str), cell.company_id))
        descending = spec.strategy.rank_direction == "descending"
        # Sort by (value, company_id); a descending rank negates the value comparison
        # while keeping the company_id tie-break ascending (stable, deterministic).
        known.sort(key=lambda pair: pair[1])
        known.sort(key=lambda pair: pair[0], reverse=descending)
        return [company_id for _, company_id in known[: spec.strategy.select_n]]

    def _target_weights(
        self,
        selected_company_ids: list[str],
        company_security_map: dict[str, list[str]],
        context: Context,
    ) -> tuple[TargetWeights, tuple[str, ...]]:
        """Equal-weight the selected names, keyed by ``security_id`` (long-only, v1).

        Each of the ``N`` selected companies gets ``1/N`` of equity. A selected company
        with exactly one tradable security is included at that weight; one with **no**
        tradable security is dropped (its ``1/N`` stays in cash — honest, never
        renormalized); one with **multiple** securities is a configuration defect for v1
        (multi-share-class weighting is deferred), surfaced. Returns the weights and the
        ordered target ``security_id``s.
        """
        if not selected_company_ids:
            return TargetWeights.of({}), ()
        with localcontext(context):
            weight = +(_ONE / Decimal(len(selected_company_ids)))
        weights: dict[str, str] = {}
        for company_id in selected_company_ids:
            securities = company_security_map.get(company_id, [])
            if not securities:
                # No tradable security — the weight mass stays uninvested (cash). BT-4.
                continue
            if len(securities) > 1:
                raise BacktestConfigurationError(
                    f"selected company {company_id!r} maps to multiple securities "
                    f"{securities}; multi-share-class weighting is deferred (v1 "
                    "requires one tradable security per selected company)"
                )
            weights[securities[0]] = str(weight)
        target_weights = TargetWeights.of(weights)
        return target_weights, target_weights.security_ids()

    # -- execution & valuation (§12, §31) ------------------------------------

    def _execute(
        self,
        *,
        as_of: datetime,
        portfolio: Portfolio,
        target_weights: TargetWeights,
        target_sids: tuple[str, ...],
        cost_model: object,
        context: Context,
    ) -> tuple[list[Fill], Decimal, Decimal]:
        """Rebalance to ``target_weights`` at the PIT close as of ``T`` (§12).

        Marks every held-or-targeted security at its latest PIT-eligible close as of
        ``T``; a security with no knowable price is carried at zero and cannot be traded
        (BT-4). Equity is measured, target shares are sized against it, and the diff
        against current holdings is executed — sells first (to free cash), then buys —
        each at the mark, with the deterministic :class:`CostModel` applied. Returns the
        fills, the marked post-trade equity, and the turnover fraction.
        """
        held_before = set(portfolio.security_ids())
        needed = sorted(held_before | set(target_sids))
        marks, mark_provenance = self._marks(needed, as_of)

        # Pre-trade equity: cash + sum shares x mark over held securities (§31).
        equity_before = portfolio.market_value(
            {sid: marks[sid] for sid in portfolio.security_ids()}
        )

        weight_of = dict(target_weights.weights)
        fills: list[Fill] = []
        traded_notional = _ZERO

        # Desired shares per target security, sized against pre-trade equity.
        desired: dict[str, Decimal] = {}
        with localcontext(context):
            for sid in target_sids:
                price = marks[sid]
                if price <= _ZERO:
                    # Not knowable at T → cannot size or fill this leg (BT-4).
                    fills.append(_unfilled(sid, _SIDE_BUY, _REASON_NO_MARK))
                    continue
                target_notional = equity_before * Decimal(weight_of[sid])
                desired[sid] = +(target_notional / price)

        # Deterministic diff over the union of held and desired securities.
        order_sids = sorted(set(portfolio.security_ids()) | set(desired))
        sells: list[str] = []
        buys: list[str] = []
        for sid in order_sids:
            delta = desired.get(sid, _ZERO) - portfolio.shares_of(sid)
            if delta < _ZERO:
                sells.append(sid)
            elif delta > _ZERO:
                buys.append(sid)

        # Sells first (free cash), then buys — both in security_id order.
        for sid in sells + buys:
            price = marks[sid]
            if price <= _ZERO:
                fills.append(_unfilled(sid, _SIDE_SELL, _REASON_NO_MARK))
                continue
            with localcontext(context):
                delta = desired.get(sid, _ZERO) - portfolio.shares_of(sid)
                shares = abs(delta)
                notional = +(shares * price)
                cost = self._cost(cost_model, notional, context)
            side = _SIDE_BUY if delta > _ZERO else _SIDE_SELL
            if side == _SIDE_BUY:
                portfolio.buy(sid, shares, cost, notional)
            else:
                portfolio.sell(sid, shares, cost, notional)
            with localcontext(context):
                traded_notional = +(traded_notional + notional)
            prov = mark_provenance.get(sid)
            fills.append(
                Fill(
                    security_id=sid,
                    side=side,
                    status=_STATUS_FILLED,
                    shares=str(shares),
                    price=str(price),
                    notional=str(notional),
                    cost=str(cost),
                    price_provenance_id=(
                        prov.provenance.selected_price_observation_id if prov else None
                    ),
                )
            )

        # Post-trade equity, marked at the same PIT closes.
        equity_after = portfolio.market_value(
            {sid: marks[sid] for sid in portfolio.security_ids()}
        )
        with localcontext(context):
            if equity_before > _ZERO:
                turnover = +(traded_notional / equity_before)
            else:
                turnover = _ZERO
        return fills, equity_after, turnover

    def _cost(self, cost_model: object, notional: Decimal, context: Context) -> Decimal:
        """The transaction cost for a trade of ``notional`` (proportional bps +
        fixed)."""
        from quantforge.backtest.spec import CostModel

        assert isinstance(cost_model, CostModel)
        with localcontext(context):
            proportional = Decimal(cost_model.proportional_bps) / Decimal(10000)
            return +(notional * proportional + Decimal(cost_model.fixed_per_order))

    # -- PIT marks -----------------------------------------------------------

    def _marks(
        self, security_ids: list[str], as_of: datetime
    ) -> tuple[dict[str, Decimal], dict[str, PitPrice]]:
        """The latest PIT-eligible close as of ``T`` for each security (BT-2).

        Walks each security's stored close trading-dates latest-first and returns the
        first that is ``KNOWN`` at ``as_of`` (a bar not knowable at ``T`` is skipped —
        no look-ahead). A security with no knowable close is marked ``0`` (it cannot be
        traded or valued positively — BT-4); its provenance is omitted.
        """
        marks: dict[str, Decimal] = {}
        provenance: dict[str, PitPrice] = {}
        for security_id in security_ids:
            price = self._latest_pit_close(security_id, as_of, on_or_before=None)
            if price is not None and price.value_numeric_str is not None:
                marks[security_id] = Decimal(price.value_numeric_str)
                provenance[security_id] = price
            else:
                marks[security_id] = _ZERO
        return marks, provenance

    def _latest_pit_close(
        self, security_id: str, as_of: datetime, *, on_or_before: str | None
    ) -> PitPrice | None:
        """The latest KNOWN PIT close for ``security_id`` at ``as_of`` (optionally
        capped).

        Draws candidate trading-dates from the stored close observations, walks them
        latest-first (optionally only those ``<= on_or_before``), and returns the first
        :class:`PitPrice` that resolves ``KNOWN`` at ``as_of`` via the Phase 11 engine —
        the same latest-eligible-close discipline Phase 11 uses for dividend references.
        ``None`` when none is knowable.
        """
        close_dates = sorted(
            {
                obs.trading_date
                for obs in self._price_engine.store.read_observations(security_id)
                if obs.field is PriceField.CLOSE
            }
        )
        for trading_date in reversed(close_dates):
            if on_or_before is not None and trading_date > on_or_before:
                continue
            price = self._price_engine.price_as_of(
                security_id, trading_date, as_of, field=PriceField.CLOSE
            )
            if price.is_known and price.value_numeric_str is not None:
                return price
        return None

    # -- corporate actions (§D) ---------------------------------------------

    def _apply_corporate_actions(
        self,
        *,
        as_of: datetime,
        portfolio: Portfolio,
        base_currency: str,
        applied_action_ids: set[str],
        context: Context,
    ) -> list[AppliedAction]:
        """Apply every newly PIT-eligible action on a held security, once (§D).

        Gathers, for each currently-held security, the corporate actions whose session
        is PIT-eligible at ``as_of`` (replicating the Phase 11 availability gate exactly
        — there is no public accessor), skips any already applied, and applies the rest
        in ``(security_id, ex_date, corporate_action_id)`` order. Each application is
        recorded as an :class:`AppliedAction`; an unrecognized payload is flagged and
        the position left untouched (§D rule 3), never raised — only a mixed-currency
        cash leg is a raised configuration defect (§B).
        """
        applied: list[AppliedAction] = []
        # Snapshot the held set now — actions apply to what is held *before* trading.
        pending: list[tuple[str, CorporateAction, str | None]] = []
        for security_id in portfolio.security_ids():
            for action, availability_ts in self._pit_eligible_actions(
                security_id, as_of
            ):
                if action.corporate_action_id in applied_action_ids:
                    continue
                pending.append((security_id, action, availability_ts))
        pending.sort(
            key=lambda item: (item[0], item[1].ex_date, item[1].corporate_action_id)
        )

        for security_id, action, availability_ts in pending:
            applied_action_ids.add(action.corporate_action_id)
            applied.append(
                self._apply_one_action(
                    security_id=security_id,
                    action=action,
                    availability_ts=availability_ts,
                    portfolio=portfolio,
                    base_currency=base_currency,
                    as_of=as_of,
                    context=context,
                )
            )
        return applied

    def _pit_eligible_actions(
        self, security_id: str, as_of: datetime
    ) -> list[tuple[CorporateAction, str | None]]:
        """Actions whose session is PIT-eligible by ``as_of`` (replicates §10 gate).

        The Phase 11 :meth:`PriceEngine._pit_eligible_actions` is private, so the engine
        replicates its exact rule over the same store reads: an action is admitted only
        if its session's availability is PIT-eligible and its availability timestamp is
        ``<= as_of``. A future action not yet knowable is excluded (no look-ahead).
        """
        store = self._price_engine.store
        availability = store.read_availability_map(security_id)
        eligible: list[tuple[CorporateAction, str | None]] = []
        for action in store.read_actions(security_id):
            av = availability.get(action.session_key)
            if av is None or not av.is_pit_eligible:
                continue
            ts = av.derived_public_availability_timestamp
            if ts is None:
                continue
            if parse_utc(ts) <= as_of:
                eligible.append((action, ts))
        return eligible

    def _apply_one_action(
        self,
        *,
        security_id: str,
        action: CorporateAction,
        availability_ts: str | None,
        portfolio: Portfolio,
        base_currency: str,
        as_of: datetime,
        context: Context,
    ) -> AppliedAction:
        """Apply one action's deterministic Decimal effect (§D) and record it."""
        kind = action.action_kind
        effect: dict[str, object] = {}
        unrecognized = False

        if kind is CorporateActionKind.SPLIT:
            ratio = _decimal_or_none(action.payload.get("ratio"))
            if ratio is None:
                unrecognized = True
            else:
                portfolio.multiply_shares(security_id, ratio)
                effect = {"kind": "split", "ratio": str(ratio)}

        elif kind is CorporateActionKind.DIVIDEND:
            amount = _decimal_or_none(action.payload.get("amount"))
            currency = action.payload.get("currency")
            if amount is None:
                unrecognized = True
            elif currency != base_currency:
                raise BacktestConfigurationError(
                    f"dividend on {security_id!r} is in currency {currency!r}, not the "
                    f"portfolio base currency {base_currency!r}; a mixed-currency "
                    "portfolio is a v1 configuration defect (§B)"
                )
            else:
                shares = portfolio.shares_of(security_id)
                with localcontext(context):
                    credited = +(shares * amount)
                portfolio.credit_cash(credited)
                effect = {
                    "kind": "dividend",
                    "amount": str(amount),
                    "currency": currency,
                    "cash": str(credited),
                }

        elif kind is CorporateActionKind.SYMBOL_CHANGE:
            # Ticker is never identity (§7) — the security_id is unchanged; no-op.
            effect = {"kind": "symbol_change"}

        elif kind is CorporateActionKind.DELISTING:
            effect = self._apply_delisting(
                security_id=security_id,
                action=action,
                portfolio=portfolio,
                as_of=as_of,
                context=context,
            )

        elif kind is CorporateActionKind.MERGER:
            effect, unrecognized = self._apply_merger(
                security_id=security_id,
                action=action,
                portfolio=portfolio,
                context=context,
            )

        else:  # pragma: no cover - CorporateActionKind is exhaustively handled above.
            unrecognized = True

        return AppliedAction(
            corporate_action_id=action.corporate_action_id,
            action_kind=kind.value,
            security_id=security_id,
            ex_date=action.ex_date,
            availability_timestamp=availability_ts,
            effect=effect,
            unrecognized=unrecognized,
        )

    def _apply_delisting(
        self,
        *,
        security_id: str,
        action: CorporateAction,
        portfolio: Portfolio,
        as_of: datetime,
        context: Context,
    ) -> dict[str, object]:
        """Force-liquidate a delisted holding at its last PIT close ≤ effective date
        (§D).

        Proceeds are ``shares x`` the latest PIT-eligible close on or before the
        effective (ex) date, resolved at ``as_of``. When no such price is knowable the
        position is removed with zero proceeds and flagged ``delisted_no_price`` — a
        recorded data condition, never a guess (BT-4).
        """
        shares = portfolio.shares_of(security_id)
        price = self._latest_pit_close(security_id, as_of, on_or_before=action.ex_date)
        if price is not None and price.value_numeric_str is not None:
            with localcontext(context):
                proceeds = +(shares * Decimal(price.value_numeric_str))
            portfolio.liquidate(security_id, proceeds)
            return {
                "kind": "delisting",
                "price": price.value_numeric_str,
                "proceeds": str(proceeds),
            }
        portfolio.liquidate(security_id, _ZERO)
        return {"kind": "delisting", "flag": _REASON_DELISTED_NO_PRICE, "proceeds": "0"}

    def _apply_merger(
        self,
        *,
        security_id: str,
        action: CorporateAction,
        portfolio: Portfolio,
        context: Context,
    ) -> tuple[dict[str, object], bool]:
        """Map a merged holding's shares to its successor per the exchange ratio (§D).

        v1 interprets the merger ``payload``'s ``terms`` as a decimal exchange ratio
        (successor shares per old share) and requires a ``successor_security_id``. When
        either is absent or unparseable the action is flagged unrecognized and the
        position is left untouched (§D rule 3) — a future terms grammar is a new
        convention, never a guess here.
        """
        successor = action.payload.get("successor_security_id")
        ratio = _decimal_or_none(action.payload.get("terms"))
        if not isinstance(successor, str) or not successor or ratio is None:
            return {"kind": "merger"}, True
        portfolio.rekey(security_id, successor, ratio)
        return (
            {
                "kind": "merger",
                "successor_security_id": successor,
                "ratio": str(ratio),
            },
            False,
        )


def _unfilled(security_id: str, side: str, reason: str) -> Fill:
    """A recorded, zero-quantity unfilled order (BT-4: recorded, not fabricated)."""
    return Fill(
        security_id=security_id,
        side=side,
        status=_STATUS_UNFILLED,
        shares="0",
        price=None,
        notional="0",
        cost="0",
        reason=reason,
    )


def _decimal_or_none(value: object) -> Decimal | None:
    """Parse ``value`` as a finite :class:`Decimal`, or ``None`` if it is not one.

    Used for corporate-action payload fields: a missing or non-decimal value marks an
    unrecognized payload (§D rule 3), applied as a recorded flag rather than a guess.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed
