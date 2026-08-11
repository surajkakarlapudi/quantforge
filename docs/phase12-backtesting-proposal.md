# Phase 12 - Backtesting / Research Simulation Engine (Design Proposal)

> **Status: PROPOSAL - DESIGN ONLY. Not approved. No code exists.**
> This document is the sole deliverable of the Phase 12 design step. It proposes
> *whether and how* QuantForge should build its first point-in-time backtesting
> layer on the foundations of Phases 1-11. It modifies no production source, adds
> no dependency, and writes no code. The implementation gate (§L) enumerates
> exactly what would change **if and only if** this design is approved.
>
> Date: 2026-08-09. Author: Phase 12 design pass.
> Governing prior specs (source of truth): [data-model.md](data-model.md)
> (invariants 1-30), [phase10-panel-locked.md](phase10-panel-locked.md),
> [phase11-market-data-locked.md](phase11-market-data-locked.md),
> [metrics.md](metrics.md), [factors.md](factors.md),
> [universe.md](universe.md) / [universe-construction.md](universe-construction.md),
> [ARCHITECTURE.md](../ARCHITECTURE.md) (10 Engineering Principles).

---

## 0. How to read this document

The user's directive required, in order: (1) a **contradiction analysis** against
every relevant existing invariant, stopping if a hard contradiction were found;
(2) if none, a proposal answering 40 enumerated questions and satisfying 12
critical design requirements (A-L), including a decision table and an
implementation gate.

**Headline finding: no hard contradiction exists.** Phase 12 is realizable as an
*additive layer that composes* the existing PIT data architecture. It does not
require weakening any Phase 1-11 invariant. The three areas of genuine tension
(PIT reproducibility needs corpus pinning; `strategy_version` cannot be honestly
content-addressed for arbitrary Python; survivorship needs both fundamentals and
market listing status) are all resolvable by composition and explicit design
decisions - documented as such in §1 and §K, not designed around silently.

Sections: §1 contradiction analysis · §2 the 40 questions · §A-J the critical
design requirements · §K decision table · §L implementation gate.

---

## 1. Contradiction analysis (mandated first step)

Each row states an existing invariant (with its source), the Phase 12 concept
that touches it, the **verdict**, and the resolution. Verdicts: **COMPOSES** (no
change to the invariant; Phase 12 consumes it), **CONSTRAINS** (the invariant
forces a Phase 12 design choice), **TENSION** (a non-obvious interaction that is
resolvable but must be handled explicitly). No row is **HARD CONTRADICTION**.

| # | Existing invariant (source) | Phase 12 touch-point | Verdict | Resolution |
|---|---|---|---|---|
| 1 | **No look-ahead; PIT integrity** (Principle 4; inv. 9,15; `resolve.py:knowledge_state_as_of`) | Strategy at rebalance T must see only data known at T | **COMPOSES / CONSTRAINS** | Strategy receives a *frozen* `AsOfContext` bound to T that exposes **only** `as_of`-bound PIT accessors; the strategy never sees a settable `as_of`. Look-ahead becomes hard to express, not merely discouraged (§A). |
| 2 | **PIT vs REVISED are distinct result types; no default mode; REVISED never feeds historical-T** (inv. 27-30; §KS) | A backtest is a walk over historical T | **COMPOSES / CONSTRAINS** | `AsOfContext` returns **only** `PitPrice`/`PitPriceSeries`/`PitPanel`/`PitMetricValue`/`PitFactor`. `Revised*` types are not constructible inside the strategy boundary. A v1 backtest is intrinsically PIT; there is no "revised backtest" and no default mode (§A, §2 Q18). |
| 3 | **Immutable raw/source data; append-only** (Principle 2; inv. 2,4) | Backtest reads facts, prices, actions | **COMPOSES** | The engine is strictly read-only over all Phase 1-11 stores; it writes only its own content-addressed result sidecar. Never rewrites a `Fact`, `PriceObservation`, or `CorporateAction`. |
| 4 | **Deterministic, content-addressed identity** (Principle 5; `_SEP="\x00"`, `sha256:` scheme) | Backtest identity + reproducibility | **COMPOSES / CONSTRAINS** | Backtest id = `sha256:` over the canonical join of (`strategy_version`, `schedule_id`, `universe/spec id`, corpus `dataset_version_id`, `cost_model_id`, `accounting_version_id`, engine version). Same scheme as every existing id builder (§G, §K-D6). |
| 5 | **Fail-closed availability; UNKNOWN never eligible** (§PA; inv. 12; `AvailabilityStatus.is_pit_eligible`) | Price/metric UNDEFINED or UNKNOWN at T | **COMPOSES / CONSTRAINS** | UNDEFINED/UNKNOWN inputs are first-class: a member with an undefined signal is excluded from the tradeable set; an order needing an unavailable execution price cannot fill and is recorded as an explicit `unfilled` outcome. No fabrication, no zero-fill (§2 Q16). |
| 6 | **DatasetVersion pins the corpus (Merkle over sorted member ids)** (`availability/version.py:DatasetVersion`; `market/version.py:MarketDatasetVersion`) | Reproducibility of a PIT walk over a *growing* append-only store | **TENSION (resolvable)** | PIT `knowledge_state_as_of` gates by *availability timestamp* (evidence-derived), not by ingestion time - so a late-ingested filing that was public before T **changes a historical answer** unless the corpus is pinned. Resolution: a backtest **must** record the fundamentals `DatasetVersion` and `MarketDatasetVersion` it ran over, and re-runs assert the corpus matches. This is composition, not a new resolver mode: PIT gating (availability <= T) and corpus identity (which observations exist) are orthogonal. It does introduce one **new hard invariant** (§L). |
| 7 | **Security identity; ticker is never identity** (inv. 11; `market/identity.py:security_id`) | Positions, fills, action linkage | **COMPOSES / CONSTRAINS** | Positions are keyed by `security_id` (`cik:<CIK>#class:<...>` or `figi:`), never ticker. A `symbol_change` action does not change position identity. |
| 8 | **Corporate actions are first-class, availability-gated** (Phase 11 D4/D5; `CorporateAction`) | Splits/dividends/symbol-changes/mergers/delistings affect shares, cash, identity | **COMPOSES / CONSTRAINS** | Positions held in **unadjusted shares**; the engine applies a PIT action ledger during simulation (split -> share multiply on ex_date; dividend -> cash on pay/ex date; delisting -> forced liquidation; merger -> successor mapping). Adjusted prices are used **only** via Phase 11's already-PIT-gated `adjusted_series_as_of` when a strategy explicitly wants adjusted signals - never as the accounting book value (§D). |
| 9 | **PIT eligibility = status in {verified,derived} AND ts NOT NULL AND ts <= as_of** (§6.1) | Every data read at T | **COMPOSES** | Inherited unchanged through the existing `*_as_of` accessors; the engine adds no new eligibility logic. |
| 10 | **Total-order selection determinism** (§6.3; resolver `_rank_key`) | Which vintage the strategy sees at T | **COMPOSES** | Inherited unchanged. The engine never re-ranks observations. |
| 11 | **PeriodAxis = accounting periods; PriceAxis = trading dates** (`panel/axis.py`, `market/axis.py`) | Rebalance dates are neither | **CONSTRAINS** | Rebalance dates are a **calendar/as_of axis** (a `RebalanceSchedule` of tz-aware `as_of` instants), a new content-addressed axis following the exact `"<domain>/1"`+kind+NUL+`sha256:` pattern. Precedent already exists: `PanelEngine.vintage_as_of` takes an `as_of_axis: tuple[datetime,...]` (§2 Q8, §K-D3). |
| 12 | **Phase 9 universe = deterministic, PIT, content-addressed membership** (`universe/builder.py:build_as_of`) | Survivorship-free universe at each T | **TENSION (resolvable)** | Rebuilding the universe `build_as_of(spec, T)` at each rebalance yields historical membership (includes later-delisted filers, excludes not-yet-public filers) - defeating survivorship bias **for fundamentals**. But SEC-filing membership does not itself encode market delisting; true tradeability status is a Phase 11 signal. Resolution: v1 membership is fundamentals-driven (Phase 9 as-of) and Phase 11 `delisting` actions are applied in-sim to force liquidation. Documented limitation (§E, §2 Q29). |
| 13 | **Phase 10 panel: `panel_across` = cross-sectional matrix over a universe as-of T** (`panel/engine.py:panel_across`) | The natural cross-sectional signal input | **COMPOSES** | A cross-sectional strategy consumes `panel_across(metric, universe, axis, as_of=T)` or `factor_as_of(...)` directly. No new fundamental-data path (§C). |
| 14 | **Phase 11 price availability = session-close + publication lag, fail-closed** (`market/policy.py:market_eod_std_v1`) | Execution timing | **COMPOSES / CONSTRAINS** | Execution at "close of day D" uses prices whose availability <= the decision `as_of`. The engine's execution model is defined in availability terms so a fill can never use a not-yet-knowable price (§B, §D). |
| 15 | **Factor transforms; UNDEFINED propagation** (`factors/model.py`; §metrics) | Ranking / weighting on a factor | **COMPOSES / CONSTRAINS** | Strategy must declare how UNDEFINED members are handled; fail-closed default = excluded from the tradeable set. No imputation. |
| 16 | **No default PIT/REVISED mode** (inv. 27) | Backtest API surface | **COMPOSES** | The engine exposes `run(...)` which is PIT-by-construction (a historical walk); it has no mode flag and cannot be handed `Revised*` inputs. |
| 17 | **`strategy_version` is a reserved `ResearchResult` slot** (§9; `factors/model.py:158`) | Phase 12 must finally define it | **COMPOSES / CONSTRAINS** | Defining `strategy_version` now is the *intended* use of the reserved slot - not a change to the invariant. It must be content-derived from strategy **logic**, not object id/timestamp. This forces the v1 strategy model toward a declarative spec (§F, §K-D2). |
| 18 | **`ResearchResult` identity & the research sidecar Protocol** (§9; `factors/store.py:ResearchRecord`) | Where a backtest result lives | **COMPOSES** | `ResearchResultStore` is already typed to a `ResearchRecord` Protocol (`research_result_id` + `to_dict`) - Phase 10 reused it for `PanelResearchResult`. A `BacktestResult` satisfying the same Protocol reuses the same write-once, fail-closed sidecar. This is exactly the extension point §9 reserved (§H, §K-D7). |
| 19 | **Reproducibility end to end** (Principle 6) | Re-run -> byte-identical | **COMPOSES / CONSTRAINS** | Guaranteed by: pinned corpus (row 6), ordered axes (row 11), `security_id`-ordered iteration (row 7), fixed-context `Decimal` arithmetic (reuse `MetricEngineVersion.decimal_context()`), no wall-clock, no unseeded randomness (§G). |
| 20 | **No database; content-addressed file stores only** (ARCHITECTURE tech notes; Principle 10) | Result persistence | **COMPOSES** | Results persist as content-addressed JSON via the existing sidecar store. No DuckDB, no new store type (§2 Q36). |
| 21 | **Zero runtime dependencies** (Principle 10) | Portfolio math, statistics | **COMPOSES / CONSTRAINS** | All arithmetic in stdlib `Decimal` (with `.sqrt()` for volatility). No numpy/pandas. v1 statistics limited to what is deterministically computable in `Decimal` (§2 Q34-35). |
| 22 | **No fabricated financial data; synthetic-only tests** (Principle 8) | Test corpus | **COMPOSES** | Tests use the Phase 11 `FakeMarketDataProvider` and synthetic fictional tickers (TEST/ZZZZ). No bundled real market data (§2 Q37-38). |
| 23 | **Phase boundaries / minimal scope** (project discipline) | Scope creep risk | **CONSTRAINS** | v1 explicitly excludes live trading, brokers, optimization, ML, options/futures, intraday, order books, tax lots, margin/leverage, distributed execution, UI (§I, §2 Q5). |
| 24 | **`Company` is a per-filer facade** (`company.py`) | Where the engine lives | **COMPOSES / CONSTRAINS** | Backtesting is cross-sectional/portfolio-level, so `BacktestEngine` is a workspace-level engine (`workspace.backtest_engine`), like `PanelEngine`/`FactorEngine` - **not** a method on `Company` (§2 Q26). |

**Conclusion of the analysis.** Phase 12 is a clean additive composition. It
introduces exactly **one** new hard invariant (a reproducible backtest must pin
and record its corpus `DatasetVersion`/`MarketDatasetVersion`; re-runs verify the
match) and it *populates* the long-reserved `strategy_version` slot. Neither is a
contradiction; both are the architecture being used as designed. Proceeding to
the proposal.

---

## 2. The 40 required questions

### Purpose & scope (Q1-5)

**Q1. What is a QuantForge backtest?** A deterministic, point-in-time simulation
of a **declarative portfolio strategy** over an ordered `RebalanceSchedule` of
`as_of` instants. At each instant it composes existing PIT layers (universe as-of
T, factor/panel signals as-of T, PIT prices as-of T) to produce target weights,
translates weight changes into orders, executes them against PIT prices under an
explicit cost model, applies the PIT corporate-action ledger to positions and
cash, and records a fully provenanced ledger plus a content-addressed
`BacktestResult`.

**Q2. What problem does it solve?** It answers "how would this strategy have
performed using *only* information available at each decision date, over a pinned
data corpus, reproducibly?" - free of look-ahead and survivorship bias, with
every decision traceable to its PIT inputs. It is the capstone that turns the PIT
data stack into research conclusions.

**Q3. Intended user?** The same quantitative researcher/developer the rest of
QuantForge targets: someone who needs an auditable, reproducible research result,
not a production trading system.

**Q4. Smallest useful v1 scope?** Daily-frequency, long-only *or* dollar-neutral
long/short, weight-based portfolios; rebalance on an explicit schedule;
close-to-close (or close-to-next-open) execution; proportional + fixed
transaction costs; splits/dividends/delistings applied from the Phase 11 action
ledger; a compact set of `Decimal`-computable performance statistics; results
persisted to the existing content-addressed sidecar. The strategy is a
**declarative specification** composed from existing primitives (rank by
factor/metric -> select -> weight), so `strategy_version` is honestly
content-addressable.

**Q5. Explicitly out of scope (v1)?** Live/paper trading, broker/exchange
connectivity, intraday or tick data, order-book/market-impact microstructure,
portfolio optimization (mean-variance, risk parity), machine learning,
options/futures/derivatives, tax lots and tax-aware accounting, leverage/margin
and borrow costs beyond a flat short cost, multi-currency portfolios, distributed
execution, and any UI. Arbitrary-Python strategy callbacks are *deferred* (see §F
and Q7).

### Inputs & strategy model (Q6-11)

**Q6. Input model?** A `BacktestSpecification` (immutable, content-addressed)
bundling: a `StrategySpecification`, a `RebalanceSchedule`, a universe source
(either a fixed `Universe` or a `UniverseSpecification` rebuilt as-of each T), a
`CostModel`, an `AccountingPolicy`, an initial capital amount (decimal string),
and the corpus pins (`dataset_version_id`, `market_dataset_version_id`).

**Q7. How is a strategy defined?** As a **declarative `StrategySpecification`** -
an ordered composition of typed steps drawn from a small vocabulary
(`signal` = a metric/factor/panel reference; `filter` = threshold/rank cut;
`rank`; `select` = top-N / bottom-N / quantile; `weight` = equal / signal-
proportional / inverse-vol-lite). This mirrors `UniverseSpecification` and
`FormulaDefinition`: content-addressable, serializable, no arbitrary code. An
optional escape hatch (a Python callback strategy) is **explicitly deferred to a
future phase** because its logic cannot be honestly content-addressed (§F).

**Q8. How are rebalance dates represented?** As a `RebalanceSchedule`: an ordered
tuple of tz-aware UTC `as_of` instants with a content-addressed `schedule_id`
(domain `backtest-schedule/1`, same NUL+`sha256:` construction as `PeriodAxis`/
`PriceAxis`). Constructors: `RebalanceSchedule.of([...instants])` and a calendar
generator (e.g. `month_end_closes(start, end)`) that emits session-close-derived
instants. Precedent: `PanelEngine.vintage_as_of(as_of_axis=...)` already treats an
ordered `as_of` tuple as a first-class axis.

**Q9. How does a strategy access PIT fundamentals?** Only through the frozen
`AsOfContext`, which delegates to Phase 7/8/10: `context.factor(metric, ...)`,
`context.panel(metric, axis)`, `context.metric(company, metric, period)` - each
internally calling the corresponding `*_as_of(as_of=T)` over the pinned corpus and
returning the `Pit*` type. The strategy cannot pass its own `as_of`.

**Q10. How does a strategy access PIT market prices?** Through the same context:
`context.price(security_id, field)` -> `PitPrice`, `context.price_series(...)` ->
`PitPriceSeries`, `context.adjusted_series(...)` -> PIT-gated adjusted
`PitPriceSeries`. All resolve at T via Phase 11's `price_as_of` /
`price_series_as_of` / `adjusted_series_as_of`. No second market-data path.

**Q11. How are orders / signals represented?** A rebalance produces `TargetWeights`
(a `security_id -> decimal weight` map, deterministically ordered). The engine
diffs target vs current holdings to produce `Order` records (side, `security_id`,
target-delta in shares or notional). Signals are retained in provenance as the
`Pit*` result ids the strategy read (§H). Orders are engine-generated from
weights; the strategy never fabricates share counts.

### Execution, costs, corporate actions (Q12-16)

**Q12. How are executions modeled?** Deterministically and simply: an order is
filled at the PIT execution price for the configured execution point
(`close` of the decision session, or `next_open`), if that price is PIT-available
at the decision `as_of`; otherwise the order is `unfilled` (recorded, not
silently dropped, not fabricated). No partial fills, no market impact, no latency
model in v1.

**Q13. Transaction costs?** A `CostModel` with (a) proportional cost in basis
points of traded notional and (b) an optional fixed per-order cost, both decimal
strings, applied deterministically at fill. Optionally a flat annualized short-
carry cost accrued per period on short notional. `cost_model_id` is content-
addressed and part of the backtest identity.

**Q14. How are corporate actions handled?** Via a PIT action ledger built from
Phase 11 `CorporateAction`s whose availability <= the relevant `as_of`
(see §D for per-kind accounting). Splits, dividends, symbol-changes, mergers, and
delistings are applied to positions/cash between and at rebalances; nothing is
inferred beyond the recorded actions.

**Q15. How are delistings handled?** A `delisting` action forces liquidation of
the position at the last PIT-available price on/before the effective date (or a
policy-defined recovery value); if no price is available the position is closed at
its last marked value with an explicit `delisted_no_price` provenance flag. The
security is removed from the tradeable set thereafter. This is the primary
survivorship-bias guard on the market side (§E).

**Q16. Missing / UNKNOWN / UNDEFINED handling?** Fail-closed throughout:
UNDEFINED signal -> member excluded from selection; UNKNOWN/UNDEFINED price at a
required decision -> that name is untradeable this rebalance; UNKNOWN/UNDEFINED
execution price -> order `unfilled`. Every such event is recorded in the ledger.
No zero-fill, no forward/backfill, no imputation.

### PIT integrity, identity, determinism (Q17-24)

**Q17. Is look-ahead prevented structurally?** Yes - see §A. The strategy is
handed a frozen `AsOfContext` whose accessors are already bound to T and take no
`as_of` argument; the raw engines, the corpus, and future dates are not reachable
from inside the strategy boundary. Look-ahead requires deliberately breaking the
type/capability boundary, not merely forgetting a guard.

**Q18. PIT / REVISED separation?** A v1 backtest is PIT-only by construction. The
context yields only `Pit*` types; `Revised*` types are not constructible within
the strategy boundary; there is no mode flag and no default. A "revised backtest"
is not a v1 concept.

**Q19. How is `strategy_version` defined?** As the content hash of the
`StrategySpecification` (domain `strategy/1`; canonical-JSON of its ordered typed
steps, same scheme as `specification_id`). Changing any step (signal, threshold,
selection, weighting) changes `strategy_version`; reformatting/renaming does not,
because it hashes the *structured spec*, not source text. For the deferred Python-
callback path, `strategy_version` would require a caller-declared version plus a
source fingerprint, with a documented honesty caveat - which is precisely why v1
prefers the declarative spec (§F, §K-D2).

**Q20. How is backtest identity generated?** `backtest_id = sha256:` over the NUL-
join of (`strategy_version`, `schedule_id`, universe identity [`universe_id` or
`specification_id`], `dataset_version_id`, `market_dataset_version_id`,
`cost_model_id`, `accounting_version_id`, `backtest_engine_version_id`,
`result_hash`), where `result_hash` is `sha256:` over the canonical-JSON ledger
digest. Same construction family as `research_result_id` / `panel_id`.

**Q21. Is determinism guaranteed?** Yes, by construction (§G): pinned corpus,
ordered schedule/axes, `security_id`-ordered member iteration, fixed-context
`Decimal` arithmetic, no wall-clock (all time flows from the schedule), no
randomness (or an explicit seed recorded in identity if ever needed), no reliance
on dict/set iteration order.

**Q22. What provenance must a result retain?** Enough to answer "what did the
strategy know when it decided?" (§H): for each rebalance, the `as_of`; the
resolved universe identity; every signal read as its `Pit*` result id
(`research_result_id` / `panel_id` / price `provenance` ids); the target weights;
the orders and their fills (price, cost, PIT price provenance); actions applied;
and the corpus pins. Rolled up into a `BacktestResult` whose `result_hash` seals
the ledger.

**Q23. Persist vs compute on demand?** Both, layered: the full per-rebalance
ledger is recomputable from the pinned inputs (determinism), and the compact
`BacktestResult` record (identity + summary stats + provenance digest, and
optionally the serialized ledger) is persisted content-addressed for audit and
fast retrieval. Write-once, fail-closed - identical id must map to identical bytes.

**Q24. Relation to `ResearchResult`?** `BacktestResult` is the sibling that
finally uses the reserved `strategy_version`. It satisfies the existing
`ResearchRecord` Protocol (`research_result_id` -> aliases `backtest_id`;
`to_dict()`), so it reuses `ResearchResultStore` unchanged. It records the same
§9 lineage fields (`dataset_version_id`, transformation/engine versions,
availability-policy ids) plus `strategy_version`, `schedule_id`,
`market_dataset_version_id`, `cost_model_id`, `accounting_version_id`.

### API, boundaries, portfolio mechanics (Q25-33)

**Q25. Public API?** New engine reached via the workspace:
`workspace.backtest_engine.run(spec: BacktestSpecification) -> BacktestResult`.
Supporting public types: `BacktestSpecification`, `StrategySpecification` (+ step
builders), `RebalanceSchedule`, `CostModel`, `AccountingPolicy`, `TargetWeights`,
`BacktestResult`, `PerformanceSummary`, and the read-only `AsOfContext` handed to
strategies. Top-level re-exports mirror the existing pattern (engines reached via
`Workspace`; result/spec types exported from `quantforge`).

**Q26. `Company` vs `BacktestEngine` boundary?** `Company` stays a per-filer
facade and gains nothing. `BacktestEngine` is workspace-level and cross-sectional,
constructed lazily like `PanelEngine`/`FactorEngine`/`PriceEngine`
(`workspace.backtest_engine`, annotated `-> object` to avoid the import cycle,
concrete type imported in the property body).

**Q27. Consume Phase 10 `PeriodAxis`?** Yes - when a strategy's signal is a
fundamental panel/derivation, it uses `PeriodAxis` for the *accounting* dimension,
resolved as-of T. `PeriodAxis` is not the rebalance axis (that is
`RebalanceSchedule`).

**Q28. Consume Phase 11 `PriceAxis`?** Yes - for price series inputs and for
marking positions between rebalances the engine uses `PriceAxis` (e.g.
`business_daily`) to pull PIT price series, all availability-gated at the relevant
`as_of`.

**Q29. Survivorship bias & delisted securities?** Addressed on two axes (§E):
fundamentals membership via `UniverseBuilder.build_as_of(spec, T)` at each
rebalance (historical, includes later-delisted filers, excludes not-yet-public);
market exit via Phase 11 `delisting` actions applied in-sim (Q15). Known v1
limitation: SEC-filing membership does not fully model exchange listing status.

**Q30. Portfolio weights?** Target weights are decimal strings that sum to a
policy-defined gross/net (e.g. long-only sums to 1; dollar-neutral sums to 0 with
gross 2). Deterministic normalization (fixed `Decimal` context, `security_id`
order). UNDEFINED-signal names are excluded before weighting.

**Q31. Cash & positions?** A `Portfolio` state = cash (decimal) + positions
(`security_id -> unadjusted share count`, decimal). Between rebalances positions
are marked at PIT prices; cash accrues dividends and pays costs. All decimal, all
deterministic.

**Q32. Commissions / slippage?** Commissions via the `CostModel` (Q13). Slippage
in v1 is either zero or a flat proportional bps add-on in the `CostModel`; no
volume/impact model. Recorded per fill.

**Q33. Splits / dividends in portfolio accounting?** Split: multiply share count
by the split ratio on ex_date (positions in unadjusted shares stay economically
constant; price series handled by Phase 11's PIT adjusted view if the strategy
opts in). Dividend: credit cash = shares x per-share amount on the pay date (or
ex date per `AccountingPolicy`), in the action's currency; no DRIP in v1. All
sourced from Phase 11 actions gated by availability.

### Statistics, storage, testing, hand-off (Q34-40)

**Q34. v1 performance statistics?** Deterministically `Decimal`-computable:
cumulative and per-period return, arithmetic mean return, volatility (via
`Decimal.sqrt`), a simple Sharpe (with an explicit annualization convention and
risk-free input), max drawdown, turnover, hit rate, and final/peak equity. Each
formula documented and versioned in `PerformanceSummary`.

**Q35. Deferred statistics?** Anything needing heavy linear algebra or
distributional machinery: factor attribution, regression betas/alpha,
information ratio decomposition, bootstrapped confidence intervals, drawdown
duration distributions, tail statistics. Deferred with the numeric-dependency
question (would a vetted `Decimal`-only implementation or an optional extra be
justified?).

**Q36. Storage model?** Content-addressed JSON via the existing
`ResearchResultStore` sidecar (`research/sha256-<hex>.json`), reused through its
`ResearchRecord` Protocol. Optionally a separate `backtests/` subdirectory under
the same store root for discoverability. No database, no new store class if the
Protocol suffices.

**Q37. Test architecture?** Pure offline/synthetic: `FakeMarketDataProvider` with
fictional tickers; hand-built canonical facts/availability for fundamentals;
golden `backtest_id` and `result_hash` determinism tests (same spec -> byte-
identical); look-ahead red-team tests (a strategy that *attempts* to read future
data cannot, by type/capability); corporate-action accounting unit tests (split,
dividend, delisting); fail-closed tests (UNDEFINED signal, unavailable execution
price). `uv run` pytest/ruff/mypy-strict gates as in every prior phase.

**Q38. Real-data validation required?** Not for v1 correctness (Principle 8
forbids bundling real market data; determinism/accounting are provable on
synthetic corpora). Optional, non-committed, out-of-tree validation against a real
provider could be a future confidence exercise, but is not a gate.

**Q39. Known limitations (v1)?** Declarative-only strategies (no Python
callbacks); daily frequency only; simplistic execution (no impact/partial fills);
survivorship handled via fundamentals membership + delisting actions but not full
exchange-listing status; single currency; no leverage/margin/borrow modeling
beyond a flat short cost; statistics limited to `Decimal`-computable set;
`RebalanceSchedule` calendar generators approximate market calendars (holidays
depend on Phase 11 session data).

**Q40. Exact Phase 13 hand-off?** Phase 12 exposes a stable, content-addressed
`BacktestResult` + `PerformanceSummary` and a frozen `strategy_version`. Phase 13
(candidate: research/reporting & comparison, or a strategy-optimization/parameter-
sweep layer, or the Python-callback strategy escape hatch) consumes
`BacktestResult`s by id, compares them (like `Universe.compare`), and/or sweeps
`StrategySpecification` parameters - **never** re-deriving prices/fundamentals and
**never** relaxing the PIT/corpus-pin invariants. The reserved seams for that hand-
off are enumerated in §L.

---

## A. NO LOOK-AHEAD (structural, not documentary)

The requirement is that the API/type architecture make accidental look-ahead
*difficult or impossible*, not merely warned against. Design:

- **Capability boundary.** A strategy never receives the `Workspace`, an engine,
  the corpus, or the schedule. It receives, per rebalance, a frozen
  `AsOfContext` constructed by the engine and bound to a single `as_of = T`.
- **No settable time.** Every `AsOfContext` accessor
  (`factor`, `panel`, `metric`, `price`, `price_series`, `adjusted_series`,
  `universe`) is pre-bound to T and takes **no** `as_of` parameter. There is no
  method on the context that accepts a future date, so a strategy cannot ask "what
  will the price be tomorrow." The only temporal freedom - choosing an accounting
  `PeriodAxis` or a historical `PriceAxis` - is upper-bounded by T inside the
  context (a series axis extending past T returns UNDEFINED/`not_knowable_yet`
  cells via the existing availability gate, never a value).
- **Type-level PIT lock.** The context returns only `Pit*` types. `Revised*`
  types require a `DatasetVersion` argument that the context does not expose, so
  the strategy cannot obtain revised data. This reuses invariant 30's existing
  type separation - Phase 12 adds no new enforcement mechanism, it just declines
  to hand the strategy the revised door.
- **Engine-owned execution.** The strategy returns only `TargetWeights`. It does
  not compute fills or read execution prices; the engine translates weights to
  orders and fills them at T-available prices. A strategy therefore cannot peek at
  a future fill price even accidentally.
- **Red-team tests** (Q37) assert that a deliberately adversarial strategy
  (attempting to reach a future date, the raw store, or revised data) fails to
  compile/type-check or raises, rather than silently returning future data.

This is the same philosophy Phases 5/10/11 used (distinct result types, no default
mode); Phase 12 extends it from "you can't confuse PIT and REVISED" to "you can't
even name a time other than T."

---

## B. PRICE SEMANTICS

- Uses Phase 11 exclusively: `PriceEngine.price_as_of` /
  `price_series_as_of` / `adjusted_series_as_of`, returning
  `PitPrice`/`PitPriceSeries`. **No second market-data implementation.**
- Historical marks and fills use **unadjusted** PIT prices for accounting
  (positions are in unadjusted shares; §D). When a strategy wants an
  adjustment-consistent *signal* (e.g. momentum on a split-adjusted series), it
  requests `context.adjusted_series(...)`, which is Phase 11's already-PIT-gated
  view (only actions with availability <= T are applied) - so no revised or
  future adjustment can leak in.
- **No revised prices in a historical backtest** (invariant 30): the context
  cannot construct a `RevisedPrice`.
- Currency: the engine calls `check_currency_consistency(security_id)` at ingest/
  setup and treats a single-currency portfolio as a v1 constraint; mixed-currency
  handling is deferred (Q39).

---

## C. FUNDAMENTALS

- Uses Phase 10 `PanelEngine` (`panel_across`, `panel_as_of`) and Phase 7/8
  (`MetricEngine.metric_as_of`, `FactorEngine.factor_as_of`) exclusively, via the
  context. **No second fundamental-data implementation.**
- Cross-sectional signals come from `panel_across(metric, universe, axis, T)` or
  `factor_as_of(metric, universe, period, T)` - both already returning
  UNDEFINED-preserving `Pit*` results.
- UNDEFINED fundamentals propagate (invariant 15): an UNDEFINED signal excludes
  the member from selection; it is never imputed.

---

## D. CORPORATE ACTIONS (exact effect on positions & accounting)

Positions are held in **unadjusted shares**, keyed by `security_id`. The engine
builds a PIT action ledger from Phase 11 `CorporateAction`s (availability-gated).
Per kind:

| Kind | Trigger date | Effect on positions | Effect on cash | Identity |
|---|---|---|---|---|
| **split** (`payload.ratio`) | `ex_date` | `shares *= ratio` (deterministic `Decimal`) | none | unchanged |
| **dividend** (`payload.amount`,`currency`) | pay date (default) or `ex_date` per `AccountingPolicy` | none | `cash += shares * amount` in action currency; no DRIP v1 | unchanged |
| **symbol_change** (`old`->`new` ticker) | effective | none (identity is `security_id`, not ticker) | none | unchanged - reinforces invariant 11 |
| **delisting** (`payload.reason`) | effective | force-liquidate at last PIT price on/before effective date; else close at last mark with `delisted_no_price` flag | `cash += proceeds` | position removed |
| **merger** (`payload.successor_security_id`,`terms`) | effective | map shares to successor per `terms` (share-for-share and/or cash) | cash leg per terms | position re-keyed to successor `security_id` |

Rules: (1) an action affects the portfolio only once its availability <= the
current simulation `as_of` (no acting on unannounced actions); (2) all action
math is `Decimal` in the fixed context; (3) unrecognized action payload shapes
fail closed (recorded, position untouched, flagged) rather than guessed; (4)
adjusted *prices* are never the accounting book value - they are a signal-only
view (§B).

---

## E. SURVIVORSHIP BIAS

- **Must not operate only on today's survivors.** The engine never uses a fixed
  "current" universe unless the caller explicitly pins one; the default and
  recommended mode is a `UniverseSpecification` rebuilt via
  `UniverseBuilder.build_as_of(spec, T)` at **each** rebalance, yielding the
  historical membership known at T (Phase 9's PIT, content-addressed membership).
- **Delisted securities** that were members at some T remain in the simulation
  and are exited via Phase 11 `delisting` actions (§D), so their pre-delisting
  returns and their exit are both counted - the classic survivorship trap is
  avoided.
- **Known limitation** (Q29, Q39): Phase 9 membership derives from SEC filings,
  which do not fully encode exchange listing status; a filer that stops trading
  but keeps filing, or vice versa, is a documented edge. v1 handles the common
  case (delisting action present); the gap is flagged, not hidden.

---

## F. STRATEGY IDENTITY

- `strategy_version` **must** derive from strategy logic, not object id or
  timestamp (requirement F). A Python object's `id()` and any wall-clock are
  forbidden inputs.
- **v1 decision:** the strategy is a **declarative `StrategySpecification`** -
  an immutable, ordered composition of typed steps (signal/filter/rank/select/
  weight). `strategy_version = sha256:` over its canonical JSON (domain
  `strategy/1`), exactly like `specification_id`/`formula_id`. This makes
  `strategy_version` an **honest** content hash: it changes iff the logic changes,
  and is invariant to formatting/naming.
- **Why not hash arbitrary Python source?** Source hashing is simultaneously
  over-sensitive (whitespace/comments change the hash) and *under-sensitive* (a
  change in an imported helper does not) - the latter is a silent correctness gap
  that would let two materially different strategies share a `strategy_version`.
  That is dishonest content-addressing and is rejected for v1.
- **Escape hatch, deferred:** a Python-callback strategy would require a caller-
  *declared* `strategy_version` plus a best-effort source fingerprint, with an
  explicit, documented caveat that the system cannot verify the declaration
  matches the logic. Because that weakens the honesty guarantee, it is deferred to
  a later phase (Q39, §L open question).

---

## G. DETERMINISM

Byte-identical results for identical inputs, guaranteed by:

1. **Pinned corpus** - the backtest records and re-verifies `dataset_version_id`
   and `market_dataset_version_id`; a changed corpus yields a *different*
   `backtest_id` (never a silently different result under the same id).
2. **Ordered axes** - `RebalanceSchedule`, `PeriodAxis`, `PriceAxis` are all
   explicit ordered, content-addressed tuples.
3. **Deterministic iteration** - members and positions iterate in `security_id`
   (and `company_id`) sorted order; weights map is canonicalized before hashing;
   no reliance on dict/set insertion order.
4. **Fixed-context Decimal arithmetic** - reuse `MetricEngineVersion.decimal_context()`
   (precision 34, `ROUND_HALF_EVEN`); no float. `backtest_engine_version_id`
   captures the numeric config, like `metric_engine_version_id`.
5. **No wall-clock** - all time flows from the schedule; the forbidden
   `Date.now()`-equivalents are never called.
6. **No unseeded randomness** - v1 has no randomness; if ever introduced, the seed
   is an explicit spec field folded into `backtest_id`.

---

## H. RESEARCH PROVENANCE

A completed backtest answers "what information did the strategy have when it made
this decision?" For every rebalance the ledger records:

- the `as_of` T and the resolved universe identity (`universe_id`/`construction_id`);
- **every signal the strategy read**, as the identity of the `Pit*` result that
  produced it: `research_result_id` (factor), `panel_id` (panel), or the
  `PriceProvenance` (`selected_price_observation_id`,
  `selected_raw_document_sha256`, `availability_policy_id`,
  `availability_timestamp`) for prices;
- the resulting `TargetWeights`;
- each `Order` and its fill: execution price, its PIT price provenance, and the
  applied cost;
- corporate actions applied (with their `corporate_action_id` and availability);
- the corpus pins.

Thus every order/signal traces back to specific PIT inputs and their availability
evidence. The `BacktestResult` seals this with `result_hash`, and satisfies the
`ResearchRecord` Protocol so it lives in the existing provenance sidecar (§H reuses
Phase 8/10 machinery; no new store).

---

## I. V1 SCOPE DISCIPLINE

Built in v1: declarative daily strategies; long-only or dollar-neutral long/short;
weight-based portfolios; explicit rebalance schedule; close/next-open execution;
proportional + fixed costs (+ optional flat short carry); split/dividend/
delisting/merger/symbol-change accounting from Phase 11; `Decimal`-computable
statistics; content-addressed persistence.

**Not** auto-built (each excluded until a contradiction analysis proves it
required): live/paper trading, broker integration, portfolio optimization, ML,
options/futures, intraday execution, complex order books/market impact, tax lots,
leverage/margin/borrow modeling, distributed execution, UI, multi-currency
portfolios, arbitrary-Python strategies. None of these is needed to make v1
correct, reproducible, and useful; each would expand the trust surface without
serving the core "reproducible PIT research result" goal.

---

## J. ARCHITECTURE

- **Additive layer above the existing PIT data architecture.** Phase 12 composes
  Phases 7/8/9/10/11 through their existing public `*_as_of` accessors; it adds no
  parallel data path and edits no prior store.
- **Read-only over lower layers** (the "read-only composition" principle): the
  engine reads facts/prices/actions and writes only its own result sidecar.
- **Workspace-hosted engine** (Q26): `workspace.backtest_engine`, lazily
  constructed like the other engines (property annotated `-> object`, concrete
  import inside the body, to preserve the no-import-cycle discipline).
- **Reuses identity/versioning conventions** verbatim: `_SEP="\x00"`, `sha256:`
  prefix, canonical JSON (`sort_keys=True, ensure_ascii=False,
  separators=(",",":")`), Merkle-style ids for the corpus pins, `"<domain>/1"`
  axis-id construction.
- **Zero new runtime dependencies** (Principle 10): stdlib `Decimal` only.

---

## K. DESIGN DECISIONS

| ID | Question | Options considered | Recommendation | Reasoning | Consequences | Reversible? |
|---|---|---|---|---|---|---|
| **D1** | Where does the engine live? | (a) method on `Company`; (b) workspace-level engine; (c) standalone module taking a `Workspace` | **(b)** `workspace.backtest_engine` | Backtesting is cross-sectional/portfolio-level, not per-filer; matches `Panel`/`Factor`/`Price` engine placement | New lazy property; no `Company` change | Reversible |
| **D2** | Strategy model | (a) declarative spec; (b) arbitrary Python callback; (c) both now | **(a)** declarative spec; (b) deferred | Only a structured spec can be *honestly* content-addressed for `strategy_version` (§F) | Limits v1 expressiveness; escape hatch later | **Architectural** (defines `strategy_version`) |
| **D3** | Rebalance-date representation | (a) reuse `PeriodAxis`; (b) reuse `PriceAxis`; (c) new `RebalanceSchedule` (as_of axis) | **(c)** new `RebalanceSchedule` | Rebalances are calendar `as_of` instants, neither accounting periods nor trading-date price axes; precedent = `vintage_as_of(as_of_axis)` | New small content-addressed type | Reversible (additive) |
| **D4** | PIT reproducibility vs growing store | (a) accept drift; (b) pin corpus via `DatasetVersion`+`MarketDatasetVersion` in identity | **(b)** pin + verify | PIT-as-of over an append-only store is not stable unless the corpus is fixed (analysis row 6) | Introduces one new hard invariant (§L); backtest id includes corpus pins | **Architectural** |
| **D5** | Accounting book value | (a) adjusted prices; (b) unadjusted shares + PIT action ledger | **(b)** unadjusted + ledger | Adjusted series changes as future actions arrive; unadjusted+ledger is look-ahead-safe and auditable; adjusted stays signal-only | Engine must maintain an action ledger (§D) | Reversible (internal) |
| **D6** | Backtest identity inputs | minimal (strategy+schedule) vs full (strategy+schedule+universe+corpus+costs+accounting+engine) | **full** | Any of these changes the result; omitting one would let different results share an id | Larger id payload; airtight reproducibility | **Architectural** |
| **D7** | Result persistence | (a) new store/db; (b) reuse `ResearchResultStore` via `ResearchRecord` Protocol | **(b)** reuse | The Protocol was designed for exactly this extension (Phase 10 precedent); no db (Principle 10/row 20) | `BacktestResult` implements `research_result_id`+`to_dict` | Reversible |
| **D8** | Execution model | (a) close; (b) next-open; (c) both, configurable | **(c)** configurable, default close | Simple, deterministic, availability-safe; researchers differ on convention | `AccountingPolicy`/`CostModel` carry the choice into identity | Reversible |
| **D9** | Statistics scope | (a) rich (needs numpy); (b) `Decimal`-only core set | **(b)** | Principle 10 (zero deps); everything in v1 is `Decimal`-computable | Defer attribution/regression stats (Q35) | Reversible |
| **D10** | Long/short scope | (a) long-only; (b) long-only + dollar-neutral L/S | **(b)** | Dollar-neutral is a small deterministic extension of weight normalization and a core research use | Weight normalization handles net/gross targets | Reversible |

---

## L. IMPLEMENTATION GATE

Nothing below is built until this proposal is approved.

### Decisions requiring explicit approval
- **D2** (declarative-only strategy; defer Python callbacks) - defines
  `strategy_version` and bounds v1 expressiveness.
- **D4** (pin + verify corpus) - introduces a new hard invariant.
- **D6** (full identity inputs) - fixes the reproducibility contract.

### Unresolved questions for the approver
1. Is the declarative-only strategy acceptable for v1, or is a (caveated) Python-
   callback escape hatch required now? (Affects D2, §F.)
2. Default execution convention: close vs next-open? (D8.)
3. Sharpe annualization convention and risk-free input source (constant vs a
   fundamentals-derived rate)? (Q34.)
4. Dividend accounting timing: ex-date vs pay-date default? (§D.)
5. Should the full per-rebalance ledger be persisted, or only recomputed on
   demand from the compact `BacktestResult`? (Q23.)
6. Is a dollar-neutral long/short in v1 scope, or long-only first? (D10.)

### Hard invariants Phase 12 would introduce
- **BT-1 (corpus pin):** a reproducible backtest records and, on re-run, verifies
  its fundamentals `dataset_version_id` and `market_dataset_version_id`; a corpus
  mismatch yields a different `backtest_id` and is never silently resolved.
- **BT-2 (PIT-only strategy boundary):** the `AsOfContext` exposes only `Pit*`
  accessors bound to a single T; `Revised*` and future dates are unreachable from
  a strategy.
- **BT-3 (engine-owned execution):** strategies emit only `TargetWeights`; the
  engine owns order generation, fills, costs, and action accounting.
- **BT-4 (fail-closed simulation):** UNDEFINED/UNKNOWN signals/prices exclude or
  leave orders unfilled, recorded explicitly; never fabricated.

### Exact files to add (proposed `src/quantforge/backtest/`)
- `__init__.py` - package exports.
- `spec.py` - `BacktestSpecification`, `StrategySpecification` (+ step builders),
  `CostModel`, `AccountingPolicy`; content-addressed ids.
- `schedule.py` - `RebalanceSchedule` (`of`, calendar generators; `schedule_id`).
- `context.py` - the frozen, PIT-only `AsOfContext` capability object.
- `engine.py` - `BacktestEngine.run(...)`; the per-rebalance simulation loop,
  order generation, execution, cost and corporate-action accounting.
- `portfolio.py` - `Portfolio`/`Position` state, `Decimal` accounting, action
  application.
- `result.py` - `BacktestResult` (implements `ResearchRecord`),
  `PerformanceSummary`, ledger types.
- `identity.py` - `strategy_version`, `schedule_id`, `cost_model_id`,
  `accounting_version_id`, `backtest_id`, `result_hash` builders.
- `version.py` - `BacktestEngineVersion` (code + `Decimal` config -> id).
- `stats.py` - `Decimal`-only performance statistics.

### Exact existing files to change (additive only)
- `src/quantforge/workspace.py` - add a lazy `backtest_engine` property
  (annotated `-> object`, concrete import in body), mirroring `panel_engine`/
  `price_engine`.
- `src/quantforge/__init__.py` - re-export the new public spec/result types (not
  the engine, consistent with existing pattern).
- `docs/index.md`, `ARCHITECTURE.md`, `README.md` - register Phase 12 (component
  status Planned -> Exists; version bump) **on completion**, not before.
- No change to any Phase 1-11 *store* or *engine* internals. No `Fact`,
  `PriceObservation`, or `CorporateAction` is ever rewritten.

### Expected public API (shape)
```python
from quantforge import Workspace
from quantforge.backtest import (
    BacktestSpecification,
    StrategySpecification,
    RebalanceSchedule,
    CostModel,
    AccountingPolicy,
)

ws = Workspace.open()
spec = BacktestSpecification(
    strategy=StrategySpecification.rank_select_weight(
        signal="current_ratio",
        select="top_n:20",
        weight="equal",
    ),
    schedule=RebalanceSchedule.month_end_closes("2018-01-31", "2023-12-31"),
    universe=universe_spec_or_fixed_universe,
    cost_model=CostModel(proportional_bps="5", fixed_per_order="0"),
    accounting=AccountingPolicy(execution="close", dividend_timing="pay_date"),
    initial_capital="1000000",
    dataset_version_id=...,
    market_dataset_version_id=...,
)
result = ws.backtest_engine.run(spec)  # -> BacktestResult (PIT-only, deterministic)
result.performance  # -> PerformanceSummary
result.research_result_id  # == result.backtest_id (ResearchRecord)
```

### Expected test categories
- **Determinism/golden:** same spec -> byte-identical `backtest_id`/`result_hash`.
- **Look-ahead red-team:** adversarial strategy cannot read future/revised data
  (type/capability failure).
- **Corporate-action accounting:** split, dividend, delisting, merger,
  symbol-change - each unit-tested against synthetic actions.
- **Fail-closed:** UNDEFINED signal excluded; unavailable execution price ->
  `unfilled`.
- **Survivorship:** universe rebuilt as-of includes a later-delisted synthetic
  filer whose exit is accounted.
- **Provenance:** every order traces to a `Pit*` result id / price provenance.
- **Identity:** `strategy_version` changes iff spec logic changes; corpus mismatch
  changes `backtest_id`.
- **Statistics:** each `Decimal` stat verified against hand-computed values.

### Expected quality gates (unchanged from prior phases)
`uv run pytest` (all green) · `uv run ruff check` · `uv run ruff format --check`
· `uv run mypy` (strict, src + tests). No commit/push/release as part of this
step.

---

## Appendix: composition map (existing APIs Phase 12 would call)

| Phase 12 need | Existing API (verbatim) | Returns |
|---|---|---|
| Universe as-of T | `UniverseBuilder.build_as_of(spec, as_of)` | `ConstructionResult` (`.universe`) |
| Cross-sectional signal | `PanelEngine.panel_across(metric_key, universe, axis, as_of, *, derivation=None)` | `PitPanel` |
| Per-filer signal | `PanelEngine.panel_as_of(metric_key, cik, axis, as_of, *, derivation=None)` | `PitPanel` |
| Factor signal | `FactorEngine.factor_as_of(metric_key, universe, period, as_of, *, transform=None)` | `PitFactor` |
| Scalar metric | `MetricEngine.metric_as_of(metric_key, cik, period, as_of)` | `PitMetricValue` |
| Spot price | `PriceEngine.price_as_of(security_id, trading_date, as_of, *, field=CLOSE)` | `PitPrice` |
| Price series | `PriceEngine.price_series_as_of(security_id, axis, as_of, *, field=CLOSE)` | `PitPriceSeries` |
| Adjusted signal | `PriceEngine.adjusted_series_as_of(security_id, axis, as_of, *, field=CLOSE, adjustment=None)` | `PitPriceSeries` (PIT-gated) |
| Corpus pins | `MetricEngine.dataset_version_for(cik)`, `PriceEngine.dataset_version_for(security_id)` | `DatasetVersion` / `MarketDatasetVersion` |
| Result persistence | `ResearchResultStore.write(record)` / `.read_as(id, from_dict)` | content-addressed sidecar |
| Decimal context | `MetricEngineVersion.decimal_context()` | `decimal.Context` (prec 34, HALF_EVEN) |
| Security identity | `market.identity.security_id(cik=..., security_class=...)` | `cik:<CIK>#class:<...>` |
```
