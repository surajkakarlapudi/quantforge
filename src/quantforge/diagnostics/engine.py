"""The signal-diagnostics orchestration engine (§2, §6, D1-D11).

:class:`SignalDiagnosticsEngine` is the Phase 16 composition root — the *diagnostic
sibling* of the Phase 12 backtester, sitting **above** Phases 9/10/11 and a **pure
consumer** of them. It turns a declarative
:class:`~quantforge.diagnostics.spec.SignalDiagnosticsSpecification` into a sealed,
content-addressed :class:`~quantforge.diagnostics.result.SignalDiagnostics`, composing —
never re-resolving — the Phase 9 universe builder, the Phase 10 panel engine
(``panel_across``), and the Phase 11 price engine (the PIT-gated adjusted view) through
their public accessors. It introduces no new data-resolution logic, no new PIT surface,
and no new store; it consumes **no** ``BacktestResult``.

The build (locked §2):

1. **Verify both corpus pins** (SD-1, D8). Re-derive the fundamentals
   :class:`~quantforge.availability.version.DatasetVersion` (union over the universe's
   explicit source companies via the Phase 7 metric engine) and the market
   :class:`~quantforge.market.version.MarketDatasetVersion` (union over the mapped
   securities via the Phase 11 price engine), and assert each equals the spec's declared
   pin — a mismatch or a non-unique normalizer is a
   :class:`~quantforge.diagnostics.errors.SignalDiagnosticsConsistencyError`
   (fail closed).
2. **Per evaluation date ``T``** (in schedule order): resolve membership PIT as-of ``T``
   (Phase 9, survivorship-free), read the as-of-``T`` signal cross-section via
   ``panel_across(..., as_of=T)`` (Phase 10, SD-3), and pair each member with its
   realized
   **forward** return over ``[T, T+h]`` trading days through the Phase 11 PIT-gated
   adjusted view read at the window-end ``as_of`` (D4). A member with an UNDEFINED
   signal
   at ``T`` or no computable forward return is **excluded and counted in coverage**
   (SD-4),
   never imputed.
3. **Compute** per date the Spearman rank IC + Pearson IC, the quantile-bucket mean
   forward
   returns, and the top-minus-bottom spread; then **summarise** the IC series (mean,
   std,
   information ratio, t-stat, hit rate per method) and the mean quantile profile — all
   under
   the pinned decimal context, UNDEFINED-preserving (no float, no RNG, no wall-clock).
4. **Seal** the computed blocks into a :class:`SignalDiagnostics` (its ``result_hash``
   folds
   the answer) and persist it write-once to the shared Phase 8 research sidecar.
   Rebuilding
   an identical request over the same immutable corpora is a byte-identical no-op.

The engine holds no mutable per-run state — a run's state lives entirely in local
variables, so one engine can evaluate many specifications and two runs of the same spec
over the same corpora are byte-identical.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Context

from quantforge.availability.timestamps import format_utc_z, parse_utc
from quantforge.availability.version import DatasetVersion
from quantforge.diagnostics.compute import (
    forward_return,
    ic_summary,
    pearson_ic,
    quantile_buckets,
    quantile_profile,
    rank_ic,
    top_minus_bottom,
)
from quantforge.diagnostics.errors import (
    SignalDiagnosticsConfigurationError,
    SignalDiagnosticsConsistencyError,
)
from quantforge.diagnostics.model import (
    CoverageSummary,
    DateCoverage,
    ICMethod,
    ICMethodSummary,
    ICSummary,
    PerDateIC,
    QuantileProfile,
    StatValue,
)
from quantforge.diagnostics.result import BOUNDARY_PIT, SignalDiagnostics
from quantforge.diagnostics.spec import SignalDiagnosticsSpecification
from quantforge.diagnostics.version import SignalDiagnosticsEngineVersion
from quantforge.factors.engine import FactorEngine
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

__all__ = ["SignalDiagnosticsEngine"]

# The minimum eligible (signal, forward-return) pairs for an evaluation date to admit
# any
# IC — an IC needs at least two points. A study in which *no* scheduled date clears
# this is
# meaningless (every IC on every method would be UNDEFINED), so it is raised as a
# configuration defect rather than sealed (the Phase 15 ``_MIN_PERIODS`` precedent, §7).
_MIN_PAIRS = 2


class SignalDiagnosticsEngine:
    """Evaluate a declarative diagnostics request to a sealed record (§2, D1-D11).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's cached Phase 8 :class:`FactorEngine` (for the Phase 7
    metric
    engine + the shared research sidecar), Phase 10 :class:`PanelEngine`, and Phase 11
    :class:`PriceEngine`, and builds a Phase 9 :class:`UniverseBuilder` over the same
    metric engine — creating no new store and duplicating no resolution logic. Every
    dependency may be overridden (for tests). It pins its statistics logic + formula +
    decimal context via :class:`SignalDiagnosticsEngineVersion` and computes every
    statistic
    under that version's decimal
    context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        factor_engine: FactorEngine | None = None,
        panel_engine: PanelEngine | None = None,
        price_engine: PriceEngine | None = None,
        universe_builder: UniverseBuilder | None = None,
        engine_version: SignalDiagnosticsEngineVersion | None = None,
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
        self._version = engine_version or SignalDiagnosticsEngineVersion()

    @property
    def engine_version(self) -> SignalDiagnosticsEngineVersion:
        return self._version

    @property
    def signal_diagnostics_engine_version_id(self) -> str:
        """The engine-logic + formula + decimal-context version folded into every id."""
        return self._version.signal_diagnostics_engine_version_id

    # -- corpus pins (SD-1, D8) ---------------------------------------------

    def fundamentals_dataset_version(
        self, spec: SignalDiagnosticsSpecification
    ) -> DatasetVersion:
        """The universe-wide fundamentals snapshot over the spec's declared source (§6).

        The union of each source filer's per-filer
        :meth:`~quantforge.metrics.engine.MetricEngine.dataset_version_for` snapshot —
        the
        exact derivation :class:`~quantforge.backtest.engine.BacktestEngine` uses — so
        the
        pin is a deterministic function of the *specification* (its explicit source
        members), independent of the schedule. A caller pins ``spec.dataset_version_id``
        to
        ``.dataset_version_id`` of this.
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
            raise SignalDiagnosticsConsistencyError(
                "source filers were normalized under differing transformation "
                f"versions {sorted(tvs)}; one fundamentals corpus requires one "
                "normalizer (SD-1)"
            )
        transformation_version_id = tvs.pop() if tvs else (fallback_tv or "")
        return DatasetVersion(
            transformation_version_id=transformation_version_id,
            availability_policy_ids=tuple(sorted(policy_ids)),
            raw_document_ids=tuple(sorted(raw_docs)),
            fact_ids=tuple(sorted(fact_ids)),
        )

    def market_dataset_version(
        self, spec: SignalDiagnosticsSpecification
    ) -> MarketDatasetVersion:
        """The universe-wide market snapshot over the spec's declared source (§6).

        The union of each source security's per-instrument
        :meth:`~quantforge.market.engine.PriceEngine.dataset_version_for` snapshot —
        the
        exact derivation the backtester uses. A caller pins
        ``spec.market_dataset_version_id`` to ``.dataset_version_id`` of this.
        Deterministic
        and schedule-independent.
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
            raise SignalDiagnosticsConsistencyError(
                "source securities were normalized under differing market "
                f"transformation versions {sorted(tvs)}; one market corpus requires "
                "one normalizer (SD-1)"
            )
        transformation_version_id = tvs.pop() if tvs else fallback_tv
        return MarketDatasetVersion(
            market_transformation_version_id=transformation_version_id,
            market_availability_policy_ids=tuple(sorted(policy_ids)),
            raw_document_ids=tuple(sorted(raw_docs)),
            price_observation_ids=tuple(sorted(obs_ids)),
            corporate_action_ids=tuple(sorted(action_ids)),
        )

    def _verify_corpus_pins(self, spec: SignalDiagnosticsSpecification) -> None:
        """Re-derive both corpus snapshots and fail closed on any mismatch (SD-1)."""
        derived_fundamentals = self.fundamentals_dataset_version(
            spec
        ).dataset_version_id
        if derived_fundamentals != spec.dataset_version_id:
            raise SignalDiagnosticsConsistencyError(
                "pinned fundamentals dataset_version_id does not match the corpus on "
                f"re-derivation (pinned {spec.dataset_version_id!r}, re-derived "
                f"{derived_fundamentals!r}); the corpus changed under the pin (SD-1)"
            )
        derived_market = self.market_dataset_version(spec).dataset_version_id
        if derived_market != spec.market_dataset_version_id:
            raise SignalDiagnosticsConsistencyError(
                "pinned market_dataset_version_id does not match the corpus on "
                f"re-derivation (pinned {spec.market_dataset_version_id!r}, re-derived "
                f"{derived_market!r}); the market corpus changed under the pin (SD-1)"
            )

    def _source_company_ids(self, spec: SignalDiagnosticsSpecification) -> list[str]:
        """The specification's explicit source ``company_id``s, first-seen order.

        Resolves the first (source) filter's identifiers through the same resolver the
        universe builder uses (§9.2). The specification guarantees the first filter is
        an
        :class:`ExplicitCompanyFilter`; a differently-shaped source cannot pin a
        reproducible corpus and is a configuration defect.
        """
        source = spec.universe.filters[0]
        if not isinstance(source, ExplicitCompanyFilter):
            raise SignalDiagnosticsConfigurationError(
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
        offline
        issuer) maps to no company and is skipped (its fundamentals join needs the
        external
        mapping — Phase 11 §7).
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
        """Every ``security_id`` owned by one of ``company_ids``, sorted
        (corpus pin)."""
        mapping = self._company_security_map()
        found: list[str] = []
        for company_id in sorted(company_ids):
            found.extend(mapping.get(company_id, ()))
        return sorted(found)

    # -- the evaluation (§2) -------------------------------------------------

    def evaluate(self, spec: SignalDiagnosticsSpecification) -> SignalDiagnostics:
        """Evaluate ``spec`` and return the sealed, content-addressed record (§2, §6).

        Deterministic and reproducible: the same spec over the same immutable corpora
        re-resolves the same PIT signal cross-sections, recomputes byte-identical
        statistics
        under the pinned decimal context, and seals a byte-identical
        :class:`SignalDiagnostics` on any machine (whose sidecar write is an idempotent
        no-op). Fails closed on a corpus-pin mismatch or a non-unique normalizer (SD-1)
        and
        on a study in which no scheduled date has at least two eligible pairs (§7);
        every
        data condition (an UNDEFINED signal, no computable forward return, a zero
        denominator, an empty bucket) is recorded as a first-class UNDEFINED value,
        never
        raised (SD-4).
        """
        if not isinstance(spec, SignalDiagnosticsSpecification):
            raise SignalDiagnosticsConfigurationError(
                "evaluate() requires a SignalDiagnosticsSpecification"
            )

        # SD-1: re-derive and verify both corpus pins before touching any data.
        self._verify_corpus_pins(spec)

        context = self._version.decimal_context()
        company_security_map = self._company_security_map()
        signal_axis = PeriodAxis.of([spec.period])
        methods = spec.sorted_ic_methods
        close_cache: dict[str, list[str]] = {}

        per_date: list[PerDateIC] = []
        coverage_dates: list[DateCoverage] = []
        # Per-method IC series, in schedule order, for the across-date summary.
        ic_series: dict[str, list[StatValue]] = {m: [] for m in methods}
        per_date_bucket_means: list[tuple[StatValue, ...]] = []
        per_date_spreads: list[StatValue] = []
        total_eligible = 0
        total_dropped_signal = 0
        total_dropped_return = 0
        max_pairs = 0

        for as_of in spec.schedule.as_of_instants():
            as_of_z = format_utc_z(as_of)

            # 2a. Membership at T (survivorship-free, Phase 9).
            construction = self._universe_builder.build_as_of(spec.universe, as_of)
            member_company_ids = construction.universe.company_ids
            resolved_members = len(member_company_ids)

            # 2b. The as-of-T signal cross-section (Phase 10, SD-3). An empty universe
            #     reads no panel (the factor universe fails closed on empty).
            signal_by_company: dict[str, str] = {}
            if member_company_ids:
                factor_universe = FactorUniverse.from_iterable(member_company_ids)
                panel = self._panel_engine.panel_across(
                    spec.signal, factor_universe, signal_axis, as_of
                )
                for cell in panel.cells:
                    if (
                        cell.metric.status is MetricStatus.KNOWN
                        and cell.metric.value_numeric_str is not None
                    ):
                        signal_by_company[cell.company_id] = (
                            cell.metric.value_numeric_str
                        )

            # 2c. Pair each member's signal with its realized forward return (SD-4).
            eligible: list[tuple[str, str, str]] = []
            dropped_signal = 0
            dropped_return = 0
            for company_id in member_company_ids:
                signal_value = signal_by_company.get(company_id)
                if signal_value is None:
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

            n_pairs = len(eligible)
            max_pairs = max(max_pairs, n_pairs)
            total_eligible += n_pairs
            total_dropped_signal += dropped_signal
            total_dropped_return += dropped_return
            coverage_dates.append(
                DateCoverage(
                    as_of=as_of_z,
                    resolved_members=resolved_members,
                    eligible=n_pairs,
                    dropped_for_signal=dropped_signal,
                    dropped_for_return=dropped_return,
                )
            )

            # 2d. Per-date statistics (UNDEFINED-preserving; §4).
            signals = [sig for _cid, sig, _ret in eligible]
            returns = [ret for _cid, _sig, ret in eligible]
            ic_pairs: list[tuple[str, StatValue]] = []
            for method in methods:
                ic = self._compute_ic(method, signals, returns, context=context)
                ic_series[method].append(ic)
                ic_pairs.append((method, ic))
            bucket_means = quantile_buckets(eligible, spec.quantiles, context=context)
            spread = top_minus_bottom(bucket_means, context=context)
            per_date_bucket_means.append(bucket_means)
            per_date_spreads.append(spread)
            per_date.append(
                PerDateIC(
                    as_of=as_of_z,
                    n_pairs=n_pairs,
                    ic=tuple(ic_pairs),
                    bucket_means=bucket_means,
                    top_minus_bottom_spread=spread,
                )
            )

        # No valid evaluation dates → a meaningless all-UNDEFINED record; raised (§7).
        if max_pairs < _MIN_PAIRS:
            raise SignalDiagnosticsConfigurationError(
                "no scheduled evaluation date has at least "
                f"{_MIN_PAIRS} eligible (signal, forward-return) pairs; every IC on "
                "every method would be UNDEFINED (fail closed rather than seal an "
                "all-UNDEFINED record)"
            )

        # 3. Summaries across dates (§4).
        summaries: list[tuple[str, ICMethodSummary]] = []
        for method in methods:
            mean, std, ratio, t_stat, hit_rate, n_valid = ic_summary(
                ic_series[method], context=context
            )
            summaries.append(
                (
                    method,
                    ICMethodSummary(
                        mean_ic=mean,
                        ic_std=std,
                        ic_information_ratio=ratio,
                        ic_t_stat=t_stat,
                        hit_rate=hit_rate,
                        n_valid_dates=n_valid,
                    ),
                )
            )
        profile_buckets, mean_spread = quantile_profile(
            per_date_bucket_means, per_date_spreads, spec.quantiles, context=context
        )

        # 4. Seal and persist write-once to the shared research sidecar (D10).
        diagnostics = SignalDiagnostics.seal(
            signal_diagnostics_engine_version_id=(
                self._version.signal_diagnostics_engine_version_id
            ),
            diagnostics_spec=spec.to_dict(),
            boundary_kind=BOUNDARY_PIT,
            dataset_version_id=spec.dataset_version_id,
            market_dataset_version_id=spec.market_dataset_version_id,
            schedule_id=spec.schedule.schedule_id,
            per_date=tuple(per_date),
            quantile_profile=QuantileProfile(
                bucket_means=profile_buckets, mean_spread=mean_spread
            ),
            ic_summary=ICSummary(per_method=tuple(summaries)),
            coverage=CoverageSummary(
                per_date=tuple(coverage_dates),
                total_eligible=total_eligible,
                total_dropped_for_signal=total_dropped_signal,
                total_dropped_for_return=total_dropped_return,
            ),
            formula_version=self._version.formula_version,
        )
        self._factor_engine.research_store.write(diagnostics)
        return diagnostics

    # -- forward return (§4, D4, SD-4) --------------------------------------

    def _compute_ic(
        self,
        method: str,
        signals: list[str],
        returns: list[str],
        *,
        context: Context,
    ) -> StatValue:
        """Dispatch one IC method over the eligible vectors (fail-closed vocabulary)."""
        if method == ICMethod.SPEARMAN.value:
            return rank_ic(signals, returns, context=context)
        if method == ICMethod.PEARSON.value:
            return pearson_ic(signals, returns, context=context)
        # Unreachable: the spec validates ``ic_methods`` against the closed vocabulary.
        raise SignalDiagnosticsConfigurationError(  # pragma: no cover
            f"unknown ic_method {method!r}"
        )

    def _forward_return(
        self,
        company_id: str,
        as_of: datetime,
        horizon_days: int,
        company_security_map: dict[str, list[str]],
        close_cache: dict[str, list[str]],
        context: Context,
    ) -> str | None:
        """The realized forward return over ``[T, T+h]`` trading days, or ``None`` (§4).

        The member's ``company_id`` is mapped to its single tradable ``security_id``; a
        company with no tradable security — or, for v1, more than one (multi-share-class
        forward returns are deferred) — is **dropped for return** (SD-4), never guessed.
        The base trading date is the latest stored close on-or-before ``T``; the end is
        the
        close ``h`` trading days later. Both endpoints are read through the Phase 11
        PIT-gated adjusted view at the **window-end ``as_of``** (the instant the
        ``T+h``
        session becomes knowable), so split/dividend adjustment is consistent and free
        of
        revision leak (D4). A missing/UNKNOWN endpoint, a non-positive base, or a window
        that runs past the stored history (a delisting with no recovery) → ``None``.
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
            # The window runs past the stored history — a delisting inside the window
            # with
            # no recovery price, or simply not enough forward data. Dropped for return.
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

        Drawn from the pinned market store's observations — the same candidate set the
        Phase 11 engine walks for its own PIT marks — so the forward-return window rides
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
        """The instant a session's close becomes PIT-eligible, or ``None`` (§6, D4).

        Replicates the Phase 11 availability gate over the same store reads: a session
        is
        knowable only when its availability is PIT-eligible and carries a derived public
        availability timestamp. The returned instant is the window-end ``as_of`` at
        which
        the forward endpoints are read, so both endpoints are honestly eligible and only
        corporate actions available by then are applied (no revision leak).
        """
        availability = self._price_engine.store.read_availability_map(security_id)
        av = availability.get(session_key(security_id, trading_date))
        if av is None or not av.is_pit_eligible:
            return None
        ts = av.derived_public_availability_timestamp
        if ts is None:
            return None
        return parse_utc(ts)
