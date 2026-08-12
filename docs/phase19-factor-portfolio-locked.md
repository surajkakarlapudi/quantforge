# Phase 19 — Characteristic-Sorted Long/Short Factor-Portfolio Construction (Factor Return Series) (LOCKED)

> **Status:** Locked normative specification. Decisions **D-SCOPE, D-INPUT, D-NAME,
> D-LEG, D-WEIGHT, D-QUANTILE, D-FWD, D-SUMMARY, D-UNDEFINED, D-INVARIANTS, D-VERSION,
> D-DIRECTION-KNOB** were approved as recommended; this document is the source of truth for
> the implementation and supersedes the recommendations in
> [phase19-factor-portfolio-proposal.md](phase19-factor-portfolio-proposal.md). Every
> conditional reference in the proposal ("recommended", "approval needed") is resolved here
> to a committed decision.
>
> **One-line thesis:** Phase 19 adds a deterministic, content-addressed
> **characteristic-sorted long/short factor-portfolio construction** layer — the first
> member of a new **portfolio-construction** capability class, a *constructive* sibling of
> the Phase 16 signal-diagnostics layer. Given a declarative
> `FactorPortfolioSpecification` naming one signal `(metric_key, MetricPeriod)`, a Phase 9
> universe, a Phase 12 schedule of evaluation instants, a `"<n>d"` forward horizon, a
> quantile count `Q`, a leg-weighting scheme, an annualization convention, and both corpus
> pins, `FactorPortfolioEngine.construct(...)` — at each scheduled rebalance date `T` —
> rebuilds membership PIT as-of `T`, reads the signal cross-section via
> `panel_across(as_of=T)`, pairs each member with its realized **forward** return over
> `[T, T+h]` trading days, sorts the survivors into `Q` quantiles, forms a **long** (top
> bucket) and **short** (bottom bucket) leg, equal-weights each, and computes the per-period
> factor return `f_T = mean(long) - mean(short)` (dollar-neutral, gross); it chains the
> valid per-period spreads into a **factor return series** with per-period leg holdings,
> coverage, and a performance summary (compounded cumulative / mean / population volatility
> / annualized Sharpe / t-statistic / hit rate), and seals a `FactorPortfolio`
> `ResearchRecord` write-once to the existing Phase 8 sidecar under the same pinned
> `Decimal` context. It composes Phases 9/10/11 only, consumes **no** `BacktestResult` and
> produces none, introduces **no** new data source, **no** new store, **no** runtime
> dependency, and **no** database.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **Single-signal, long/short, quantile-sorted construction with equal-weight legs**, per-rebalance forward-return spread chained into a return series. Multi-signal composites, portfolio optimization, and net-of-cost returns are out of scope (§9). |
| **D-INPUT** | **A new sibling layer over Phases 9/10/11** (like Phase 16 / Phase 18). It consumes **no** `BacktestResult` and produces none, and it **modifies no** Phase 12 vocabulary, engine, or identity. The sibling path preserves all prior identity; the Phase-12-extension path (Alt B) was rejected as a repo-wide versioning event. |
| **D-NAME** | **Package `factorportfolio`.** Public types `FactorPortfolioSpecification`, `FactorPortfolio`; engine `FactorPortfolioEngine` (reached via `Workspace`, not re-exported); entry `construct`. The domain tag is `factorportfolio/1`; the engine-version string is `factorportfolio-engine/1`; the formula-method string is `factorportfolio-stats/1`. These are baked into every `factor_portfolio_id`; changing them later is a breaking identity change. |
| **D-LEG** | **long = top quantile bucket, short = bottom bucket** (high-minus-low on the **raw** signal, no sign flip); `f_T = mean(long forward returns) - mean(short forward returns)` (dollar-neutral, gross). Each leg's own equal-weight mean return and membership are recorded. This fixes the sign and meaning of every reported number and is pinned in `factorportfolio-stats/1`. |
| **D-WEIGHT** | **Equal-weight within each leg** in v1 (closed vocabulary `{"equal"}`). `weighting` is folded into identity so a future value/rank/proportional scheme hashes distinctly. |
| **D-QUANTILE** | **Reuse the Phase 16 `quantile_buckets` rule verbatim:** members ordered by (signal ascending, then `company_id`), the member at 0-based ordinal `i` assigned `bucket = floor(i·Q/n)` (clamped to `Q-1`); the bottom bucket (`0`) is the short leg, the top bucket (`Q-1`) the long leg. One bucketing definition in the codebase, commensurable with the diagnostic layer. |
| **D-FWD** | **Reuse the Phase 16/18 `"<n>d"` trading-day PIT-gated adjusted forward return verbatim** (import `forward_return` from `quantforge.diagnostics.compute`; replicate the `_forward_return` / `_close_dates` / `_session_available_at` helper shape as Phase 18 does). No new prior-phase edit; no second, divergent return definition enters the codebase. |
| **D-SUMMARY** | **Seal a summary over the factor return series:** compounded cumulative `∏(1+f_T) - 1`, mean period return, **population** volatility, annualized Sharpe `(mean - rf)/vol · √periods_per_year` (via `Decimal.sqrt`, the Phase 12 precedent), the mean's t-statistic `mean/(popStd/√M)`, and hit rate. `risk_free_per_period` + `periods_per_year` are folded into identity. The population-std convention and the compounding are pinned in `factorportfolio-stats/1`. |
| **D-UNDEFINED** | **Two thresholds.** (a) A per-period **member floor** `n_members >= 2·Q` — a period below it, or with an empty long or short leg, is a recorded `UNDEFINED` period (P19-4), **never** a raise; (b) a **minimum valid-periods** guard `_MIN_VALID_PERIODS = 2` for the summary — a run yielding fewer than two *defined* per-period returns raises `FactorPortfolioConfigurationError` (the Phase 18 `_MIN_VALID_DATES` / Phase 16 `_MIN_PAIRS` / Phase 15 `_MIN_PERIODS` precedent), so an all-`UNDEFINED` record is never sealed. A zero-variance series → `UNDEFINED` Sharpe / t-statistic. |
| **D-INVARIANTS** | **P19-1..P19-5 are documented both as phase-local invariants here and as a small additive `data-model.md §12` block** mirroring the SD-1..4 / XS-1..4 blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.16.0`** (Phase 18 = v0.15.0, confirmed by git tags). The package `__version__` string is unchanged (versioning is by content-addressed ids, not a semver string). The pre-existing README version-label drift is **not** fixed here. |
| **D-DIRECTION-KNOB** | v1 fixes high-minus-low on the raw signal — **no `rank_direction` field.** A future `rank_direction ∈ {descending, ascending}` can flip the factor sign, folded into identity when added. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; none changes an identity discipline or weakens an invariant.

1. **The pure per-period compute type is `PeriodLegResult` (in `stats.py`), not
   `PerPeriodReturn`.** The proposal §5.1 named `stats.py`'s outputs loosely; the
   implementation returns an internal `PeriodLegResult` (`long_ids`, `short_ids`,
   `long_return`, `short_return`, `factor_return`) from `period_factor_return(...)` and the
   engine assembles the sealed `PerPeriodReturn` (with `LegMembership`) from it. The sealed
   record shape and the identity fold are exactly as proposed.
2. **The series-summary compute type is `SeriesSummary` (in `stats.py`); the sealed record
   field is `FactorReturnSummary` (in `model.py`).** `series_summary(...)` returns a pure
   `SeriesSummary`; the engine copies its six cells + `n_valid_periods` into the sealed
   `FactorReturnSummary`. Both carry identical fields; the split keeps the pure compute
   layer free of the record vocabulary.
3. **Version constants are split across `version.py`, `spec.py`, and `result.py`.**
   `FACTORPORTFOLIO_SPEC_VERSION` lives in `version.py` and is imported by `spec.py`;
   `FACTORPORTFOLIO_RESULT_FORMAT_VERSION` lives in `result.py` (beside the record it
   versions); `version.py` owns the engine + formula versions and the pinned decimal
   context. No value or fold changes.
4. **`errors.py` defines the two-error hierarchy as proposed**
   (`FactorPortfolioError → FactorPortfolioConfigurationError,
   FactorPortfolioConsistencyError`); `WEIGHTING_EQUAL` is exported from `spec.py`.

---

## 2. Architecture (locked)

Phase 19 is a thin factor-portfolio-construction layer *above* Phases 9/10/11,
structurally the **constructive sibling of Phase 16** (`diagnostics`) — the correct
precedent because Phase 19, like the IC diagnostics, reads the **raw corpora** (universe
membership, PIT signals, PIT-gated adjusted forward returns) rather than sealed
`BacktestResult`s. It follows the extension recipe every prior phase uses: versioned
immutable request object → fail-closed engine reached from `Workspace` via a lazy,
cycle-free `@property` → distinct result type → content-addressed identity with fresh
domain tags → data conditions recorded as first-class values, defects raised →
compute-on-demand with the shared write-once sidecar. Like Phase 16 (and unlike Phase 17),
Phase 19 references the corpora by **corpus pin** (the fundamentals `dataset_version_id`
and market `market_dataset_version_id`), so the id stays sensitive to any corpus change
without folding a sealed artifact hash.

```
                 FactorPortfolioSpecification    (declarative request, content-addressed)
                          |
                          v
   Workspace.factor_portfolio_engine  --->  FactorPortfolioEngine.construct(spec)
                          |                 |
                          |   re-derive + verify BOTH corpus pins (P19-1)         — fail closed
                          |     fundamentals DatasetVersion + market MarketDatasetVersion
                          |     over the universe's explicit source companies/securities
                          |
                          |   per rebalance date T (schedule order):
                          |     build membership PIT as-of T          (Phase 9, survivorship-free)
                          |     read signal cross-section via panel_across(as_of=T)  (Phase 10, P19-3)
                          |     pair each member w/ realized forward return over [T, T+h]
                          |       through the Phase 11 PIT-gated adjusted view          (P19-2, P19-4)
                          |     if n_members >= 2*Q and both legs non-empty:
                          |       quantile-sort -> long (top) / short (bottom) legs
                          |       f_T = mean(long) - mean(short)   (equal-weight, dollar-neutral)
                          |     else: recorded UNDEFINED period (INSUFFICIENT_MEMBERS / EMPTY_*_LEG)
                          |
                          |   require >= 2 valid periods                           — fail closed (D-UNDEFINED)
                          |   aggregate the valid f_T series into a summary:
                          |     cumulative ∏(1+f_T)-1, mean, population vol, annualized Sharpe,
                          |     t = mean/(popStd/√M), hit rate  (UNDEFINED-preserving)
                          v                 v
             FactorPortfolio (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
             store.read_as(id, FactorPortfolio.from_dict)  (typed, byte-identical round-trip)
```

**New package `src/quantforge/factorportfolio/`** (mirrors `diagnostics/` / `crosssection/`):

- `errors.py` — `FactorPortfolioError` → `FactorPortfolioConfigurationError`,
  `FactorPortfolioConsistencyError`.
- `version.py` — `FactorPortfolioEngineVersion` (folds the pinned decimal context **and**
  the formula-method version `factorportfolio-stats/1` into `config_hash`);
  `FACTORPORTFOLIO_ENGINE_VERSION = "factorportfolio-engine/1"`,
  `FACTORPORTFOLIO_FORMULA_VERSION = "factorportfolio-stats/1"`,
  `FACTORPORTFOLIO_SPEC_VERSION = "factorportfolio/1"`; `default_decimal_context()`. The id
  property is `factor_portfolio_engine_version_id`.
- `identity.py` — `factor_portfolio_result_hash`, `factor_portfolio_id`. Fresh record
  domain tag `factorportfolio/1`. (The engine-version id is **not** re-implemented here — it
  is a property of `FactorPortfolioEngineVersion`, one source of truth.)
- `model.py` — `FactorPortfolioStatus` / `FactorPortfolioUndefinedReason` vocabulary;
  `StatValue` (a KNOWN decimal string **or** UNDEFINED+reason); `LegKind` (`long`/`short`);
  the nested records `LegMembership`, `PerPeriodReturn`, `FactorReturnSummary`,
  `DateCoverage`, `CoverageSummary`.
- `spec.py` — `FactorPortfolioSpecification`, full construction-time validation;
  `WEIGHTING_EQUAL`.
- `stats.py` — the pure per-period leg formation + spread (`period_factor_return`,
  `PeriodLegResult`) and the series aggregation (`series_summary`, `SeriesSummary`). Pure;
  read no store; take decimal-string vectors, return KNOWN / UNDEFINED cells.
- `result.py` — `FACTORPORTFOLIO_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, `FactorPortfolio`
  (a `ResearchRecord` with `.seal` / `to_dict` / `from_dict`).
- `engine.py` — `FactorPortfolioEngine` (constructed from `Workspace`; reuses the
  workspace's Phase 8 `FactorEngine` + shared research sidecar, Phase 10 `PanelEngine`,
  Phase 11 `PriceEngine`, and a Phase 9 `UniverseBuilder`): verify pins → per-date resolve
  + pair + sort + spread → aggregate → seal → write-once.
- `__init__.py` — package exports (`FactorPortfolioSpecification`, `FactorPortfolio`).

**Edits to existing source** (all additive; none altering any existing identity):

1. `workspace.py` — one lazy `factor_portfolio_engine` `@property` (+ its
   `self._factor_portfolio_engine: object | None = None` cache line), following the
   `crosssection_engine` / `attribution_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of `FactorPortfolioSpecification`
   and `FactorPortfolio` (spec + result only; the engine is reached via `Workspace`).
3. `tests/test_smoke.py` — one additive public-API export assertion.

**No edit to** `backtest/*`, `analytics/*`, `attribution/*`, `crosssection/*`,
`experiment/*`, `report/*`, `diagnostics/*` (beyond importing its `forward_return`),
`panel/*`, `market/*`, `universe/*`, `factors/store.py`, or any identity/version module of
a prior phase. **No new PIT resolution and no new store.** Unlike Phase 18, Phase 19 does
no OLS and promotes no shared helper: `_linalg` is untouched.

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
wall-clock, no RNG.

### 3.1 `FactorPortfolioSpecification` (declarative request)

```
FactorPortfolioSpecification(
    name: str,                       # non-empty
    signal: str,                     # a Phase 7 metric_key, non-empty
    period: MetricPeriod,            # the explicit fiscal period the signal is read for (never inferred)
    universe: UniverseSpecification,  # Phase 9 declarative request
    schedule: RebalanceSchedule,      # Phase 12 as_of instants (rebalance dates T)
    forward_horizon: str,             # r"^[0-9]+d$" trading-day horizon (Phase 16 grammar)
    quantiles: int,                   # Q >= 2 (long = top bucket, short = bottom bucket)
    dataset_version_id: str,          # fundamentals corpus pin (non-empty)
    market_dataset_version_id: str,   # market corpus pin (non-empty)
    weighting: str = "equal",         # leg weighting; v1 closed vocabulary {"equal"}
    risk_free_per_period: str = "0",  # canonicalized decimal; folded into identity
    periods_per_year: str = "1",      # canonicalized decimal; folded into identity
    spec_version: str = "factorportfolio/1",
    horizon_days: int = <derived>,    # parsed from forward_horizon at construction, never supplied
)
```

Construction-time validation (fail closed, `FactorPortfolioConfigurationError`): empty
`name` / `signal` / `spec_version` / either corpus pin; a `period` that is not a
`MetricPeriod`; a `universe` that is not a `UniverseSpecification`; a `schedule` missing the
`RebalanceSchedule` surface (`schedule_id` + `as_of_instants`) or enumerating zero instants;
a `forward_horizon` not of the form `"<n>d"` with `n ≥ 1`; a non-`int` or `bool` `quantiles`
(a truthy bool can never masquerade as a count) or `quantiles < 2`; a `weighting` outside
the closed `{"equal"}` vocabulary; a non-decimal or non-finite `risk_free_per_period` /
`periods_per_year` (canonicalized in place via `str(+Decimal(...))` so two spellings of the
same number yield one id). It reads no store and no wall clock — it cannot know whether the
referenced corpora exist (that is the engine's P19-1 step) or whether any period clears the
member floor (the engine's fail-closed steps); it validates only the request's internal
shape. `to_dict()` emits the request's canonical payload (the `universe` / `schedule` in
their own canonical forms; the annualization decimals already canonicalized), embedded in
the sealed record.

### 3.2 Per-period + summary compute blocks (`stats.py`, internal)

`period_factor_return(members, quantiles, *, context)` takes the eligible per-member
`(company_id, signal_string, forward_return_string)` triples for one date and returns a
`PeriodLegResult`:

```
PeriodLegResult(
    long_ids: tuple[str, ...],    # top-bucket company_ids, sorted ascending (audit)
    short_ids: tuple[str, ...],   # bottom-bucket company_ids, sorted ascending (audit)
    long_return: StatValue,       # equal-weight mean forward return of the long leg
    short_return: StatValue,      # equal-weight mean forward return of the short leg
    factor_return: StatValue,     # long_return - short_return (the per-period spread)
)
```

`series_summary(factor_returns, *, risk_free_per_period, periods_per_year, context)` takes
the ordered KNOWN per-period factor-return strings over the valid dates and returns a
`SeriesSummary` (`cumulative_return`, `mean_period_return`, `volatility`,
`annualized_sharpe`, `mean_t_stat`, `hit_rate`, `n_valid_periods`).

`StatValue` is the UNDEFINED-preserving cell: `StatValue.known("<decimal string>")` **or**
`StatValue.undefined(<FactorPortfolioUndefinedReason>)`. Exactly one of `value` / `reason`
is populated (enforced at construction). Never a bare float, never silently omitted.

### 3.3 `FactorPortfolio` (implements `ResearchRecord`)

```
FactorPortfolio(
    factor_portfolio_engine_version_id: str,
    factor_portfolio_spec: dict[str, object],       # the full FactorPortfolioSpecification.to_dict()
    name: str,
    spec_version: str,
    signal: str,
    period_key: str,
    universe_specification_id: str,
    schedule_id: str,                               # the shared evaluation-schedule identity
    horizon_days: int,
    quantiles: int,
    weighting: str,
    boundary_kind: str,                             # "pit" (signal side; P19-2 — not a PIT value)
    risk_free_per_period: str,
    periods_per_year: str,
    dataset_version_id: str,                        # fundamentals corpus pin
    market_dataset_version_id: str,                 # market corpus pin
    per_period: tuple[PerPeriodReturn, ...],        # one per VALID or UNDEFINED rebalance date, schedule order
    summary: FactorReturnSummary,
    coverage: CoverageSummary,
    formula_version: str,                           # "factorportfolio-stats/1"
    result_hash: str,                               # canonical JSON over the ordered output cells
)

# derived, never stored as state:
factor_portfolio_id  property -> sha256 folding engine version + request identity
                                 + both corpus pins + result_hash
research_result_id   property -> alias of factor_portfolio_id  (the ResearchRecord key)
```

- `PerPeriodReturn(as_of, n_members, long_membership: LegMembership, short_membership:
  LegMembership, long_return: StatValue, short_return: StatValue, factor_return: StatValue)`
  — the per-rebalance spread; a period below the member floor or with an empty long/short
  leg yields UNDEFINED legs/return, recorded, never dropped.
- `LegMembership(kind: LegKind, company_ids: tuple[str, ...])` — the ordered members
  assigned to that leg (audit; **not** folded into identity — §5).
- `FactorReturnSummary(cumulative_return, mean_period_return, volatility, annualized_sharpe,
  mean_t_stat, hit_rate, n_valid_periods)` — each statistic a `StatValue`;
  `n_valid_periods` the count of periods that contributed a KNOWN factor return.
- `CoverageSummary(per_date: tuple[DateCoverage, …], total_resolved,
  total_dropped_for_signal, total_dropped_for_return, total_undefined_periods)`;
  `DateCoverage(as_of, resolved_members, eligible, dropped_for_signal, dropped_for_return,
  period_status)` — `period_status` is `"known"` when the date admitted a defined factor
  return, else the reason value (`"insufficient_members"` / `"empty_long_leg"` /
  `"empty_short_leg"`) that made the whole per-period block UNDEFINED.
- `to_dict()` keys include `factor_portfolio_id`, `research_result_id` (alias so the generic
  reader keys correctly), and every field above. A KNOWN cell emits `value` only; an
  UNDEFINED cell emits `reason` only.
- `from_dict` is the fail-closed inverse; `factor_portfolio_id` / `research_result_id` are
  re-derived by their properties, **never read from state**, so `from_dict(to_dict(r))`
  re-emits identical bytes and the same `result_hash`, and a tampered stored id is ignored.
  A malformed cell (unknown status, missing value/reason, unrecognized reason) is refused
  with a `ValueError`.
- `.seal(...)` is the identity-computing constructor: it folds the ordered computed-output
  cells (the per-period factor-return panel in schedule order, then the summary block, each
  tagged by its block so two structurally different records can never collide) into
  `result_hash`, so identity is a pure function of the request + referenced corpora +
  computed answer, never caller-supplied. **The per-period leg membership and the coverage
  summary are audit metadata and are NOT folded into `result_hash`** (§5) — they are fully
  determined by the same inputs, so they never desynchronize.

**What the model deliberately does NOT hold:** any copy of a raw fundamentals or price
value (only the derived per-leg means, factor returns, and summary); any float; any
wall-clock or RNG value; any `Pit*` type or as-of accessor (P19-2); any presentation.

### 3.4 Closed v1 vocabulary

`FactorPortfolioUndefinedReason` (closed, 6): `INSUFFICIENT_MEMBERS`, `EMPTY_LONG_LEG`,
`EMPTY_SHORT_LEG`, `NO_VALID_PERIODS`, `SINGLE_VALID_PERIOD`, `ZERO_RETURN_VARIANCE`.
`FactorPortfolioStatus` (2): `KNOWN`, `UNDEFINED`. `LegKind` (2): `LONG`, `SHORT`.
Extending the reason set is an explicit future edit that hashes distinctly (a new reason
changes `result_hash`) — never an implicit fallback.

---

## 4. Formula methods (locked, folded into `factorportfolio-stats/1`)

Changing any of these bumps `FACTORPORTFOLIO_FORMULA_VERSION`, so a value computed under one
method can never be silently reinterpreted under another. All arithmetic runs under an
explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`), never the ambient process
context. `Decimal.sqrt(context)` covers all roots. No float touches any value.

- **Quantile leg formation (D-QUANTILE, reused from Phase 16).** The eligible members are
  ordered by (signal ascending, then `company_id`); the member at 0-based ordinal `i` is
  assigned `bucket = floor(i·Q/n)` (clamped to `Q-1`). The **bottom** bucket (`0`, the
  lowest-signal members) is the **short** leg; the **top** bucket (`Q-1`, the highest-signal
  members) is the **long** leg (high-minus-low on the raw signal, no sign flip — D-LEG).
- **Per-leg return + spread (D-LEG / D-WEIGHT).** Each leg's return is the equal-weight mean
  forward return of its members (`Σ/n`); the per-period factor return is the long-minus-short
  spread `f_T = mean(long) - mean(short)` (dollar-neutral, gross).
- **Member floor (D-UNDEFINED).** A period with `n_members < 2·Q` yields all-UNDEFINED legs
  and factor return with reason `INSUFFICIENT_MEMBERS` and empty membership tuples — never a
  fabricated leg. A defensively-detected empty top / bottom bucket after sorting yields
  `EMPTY_LONG_LEG` / `EMPTY_SHORT_LEG`.
- **Series summary (D-SUMMARY).** Over the `M` valid per-period factor returns: cumulative
  is the compounded product `∏(1+f_T) - 1`; the mean is `(1/M) Σ f_T`; the volatility is the
  **population** standard deviation `√(Σ(f_T − mean)²/M)`; the annualized Sharpe is
  `(mean − rf)/volatility · √periods_per_year`; the mean's t-statistic is
  `mean/(volatility/√M)`; the hit rate is `#(f_T > 0)/M`. Only a period whose factor return
  was KNOWN contributes to the series (an UNDEFINED period contributes nothing).
- **Aggregation degeneracies (never a divide-by-zero).** `M = 0` → every summary cell is
  `NO_VALID_PERIODS`. `M = 1` → the cumulative / mean / hit-rate cells are KNOWN but the
  dispersion cells (volatility, annualized Sharpe, t-statistic) are `SINGLE_VALID_PERIOD`.
  `M ≥ 2` with zero population dispersion (every per-period return identical) → the
  volatility is a KNOWN exact `0` and the annualized Sharpe / t-statistic are
  `ZERO_RETURN_VARIANCE`.

---

## 5. Identity / determinism (locked)

- Domain tags via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): record tag
  `factorportfolio/1`; engine tag `factorportfolio-engine/1`; formula tag
  `factorportfolio-stats/1`.
- `factor_portfolio_engine_version_id = sha256(code_version "factorportfolio-engine/1",
  config_hash)` where `config_hash =
  sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=factorportfolio-stats/1")`. Any change
  to the decimal context **or** a formula method yields a new engine id.
- `factor_portfolio_result_hash = sha256(canonical JSON over the ordered computed-output
  cells: the per-period factor-return panel in schedule order — each `{"block":"per_period",
  as_of, n_members, long_return, short_return, factor_return}` — then the summary block —
  `{"block":"summary", …}`)`. Sensitive to every computed cell: each period's member count,
  long-leg mean, short-leg mean, and factor return, and every summary cell. One differing
  cell changes it.
- `factor_portfolio_id = sha256`, NUL-joined, in this exact order: `factorportfolio/1`,
  `factor_portfolio_engine_version_id`, `name`, `spec_version`, `signal`, `period_key`,
  `universe_specification_id`, `schedule_id`, `str(horizon_days)`, `str(quantiles)`,
  `weighting`, `risk_free_per_period`, `periods_per_year`, `dataset_version_id`,
  `market_dataset_version_id`, and `factor_portfolio_result_hash`.
- `research_result_id` aliases `factor_portfolio_id` (a single id).

**Folds (changes identity):** engine-logic + formula + decimal-context version ✔, the full
declared request (name, spec version, signal + period key, universe/schedule identities,
horizon day count, quantile count, leg weighting, and the annualization convention
`risk_free_per_period` / `periods_per_year`) ✔, **both** corpus pins — a changed corpus
changes a pin (P19-1) ✔, the computed statistics (via `result_hash`) ✔. **Does NOT fold:**
the record schema/format version (`FACTORPORTFOLIO_RESULT_FORMAT_VERSION` — a container
concern), the per-period leg membership (audit metadata), the coverage summary (audit
metadata), any presentation, wall-clock, RNG, `id()`, or iteration order (the per-period
series preserves schedule order; leg membership is sorted by `company_id`; the carried
corpus-pin component sets are sorted).

Same request + same pinned corpora → same `factor_portfolio_id` and same bytes on any
machine.

---

## 6. PIT semantics, provenance, storage (locked)

- **The signal side is read PIT-correctly (P19-3).** At each rebalance date `T`, the signal
  cross-section is read via `panel_across(..., as_of=T)` (invariant 29), so no post-`T`
  fundamentals ever contaminate leg formation. Membership is rebuilt at each `T` through
  Phase 9 `build_as_of`, inheriting Phase 9's survivorship-correct membership. Only KNOWN
  panel cells enter; a member with no KNOWN signal at `T` is dropped for signal.
- **The output is ex-post, not PIT (P19-2).** The **forward** return over `[T, T+h]` is
  realized *after* `T`, so the chained factor return series is an ex-post research artifact.
  `FactorPortfolio` is **not** a `Pit*` type, exposes **no** as-of accessor, and is
  inadmissible where a PIT signal/value is required — the exact analogue of invariant 28 /
  SD-2 / XS-2. `boundary_kind = "pit"` documents only that the *signal side* was read
  PIT-eligibly; it does not claim the series is a PIT value.
- **A factor portfolio is not a `BacktestResult` (P19-5).** `FactorPortfolio` is a distinct
  record type; it does not enter Phase 12's identity and cannot be passed where a
  `BacktestResult` is required (enforced by type).
- **Forward return (D-FWD, reused verbatim from Phase 16/18).** A member's `company_id` maps
  to its single tradable `security_id` (a company with no tradable security — or, for v1,
  more than one — is dropped for return, never guessed); the base trading date is the latest
  stored close on-or-before `T`, the end the close `h` trading days later; both endpoints are
  read through the Phase 11 PIT-gated adjusted view at the **window-end `as_of`** (the
  instant the `T+h` session becomes knowable), so split/dividend adjustment is consistent and
  free of revision leak. A missing/UNKNOWN endpoint, a non-positive base, or a window that
  runs past the stored history → the member is dropped for return (P19-4).
- **Corpus pins re-verified (P19-1).** Before touching any data the engine re-derives both
  the fundamentals `DatasetVersion` (the union of each source filer's per-filer snapshot) and
  the market `MarketDatasetVersion` (the union of each source security's per-instrument
  snapshot) over the universe's explicit source companies, and asserts each equals the spec's
  declared pin; a mismatch — or a corpus that does not admit a single normalizing
  transformation version — is a `FactorPortfolioConsistencyError` (fail closed, never
  silently reconciled). This reuses the Phase 16 / Phase 18 machinery verbatim. A changed
  corpus yields a different pin, hence a different `factor_portfolio_id`.
- **Fail-closed pairing (P19-4).** A member lacking the PIT signal at `T`, or with no
  computable forward return, is excluded from that date's cross-section and counted in
  coverage (`dropped_for_signal` / `dropped_for_return`), never imputed, zero-filled, or
  fabricated. A period below the member floor or with an empty long/short leg is a recorded
  `UNDEFINED` period (counted in `total_undefined_periods`), never raised, and contributes no
  factor return to the series.
- **Provenance.** The record embeds the full declared spec (`factor_portfolio_spec`), both
  corpus pins, the signal + period key, the universe / schedule identities, the horizon day
  count, the quantile count, the leg weighting, the annualization convention, the
  engine/formula versions, the complete per-period factor-return panel + leg membership + the
  summary, and the coverage summary — so the whole construction is reconstructible and
  auditable from the record plus the two pinned corpora. It stores **no copy** of any raw
  financial value beyond the derived statistics.
- **Storage.** Zero new store types; the `ResearchResultStore` writes the record to
  `<root>/research/sha256-<hex>.json` in the existing container. Write-once and idempotent:
  re-constructing an identical portfolio is a byte-identical no-op; a differing payload under
  an existing id fails closed via the store's guard.

---

## 7. Failure / UNDEFINED behavior (locked)

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`FactorPortfolioConfigurationError` / `FactorPortfolioConsistencyError`):
- Malformed spec: empty `name` / `signal` / `spec_version` / either corpus pin; a
  non-`MetricPeriod` period; a non-`UniverseSpecification` universe; a schedule missing its
  surface or enumerating zero instants; a malformed `forward_horizon`; a non-`int` / `bool`
  or `< 2` `quantiles`; an unknown `weighting`; a non-decimal / non-finite annualization
  input. *(configuration, at construction)*
- A non-`FactorPortfolioSpecification` argument to `construct`, or a source filter that is
  not an `ExplicitCompanyFilter` (cannot pin a reproducible corpus). *(configuration)*
- **Insufficient valid periods:** fewer than `_MIN_VALID_PERIODS = 2` scheduled dates yield a
  defined factor return — the return-series summary would have no time-series dispersion, so
  the run raises rather than sealing an all-`UNDEFINED` record (the Phase 18 `_MIN_VALID_DATES`
  / Phase 16 `_MIN_PAIRS` / Phase 15 `_MIN_PERIODS` precedent). *(configuration)*
- A corpus-pin mismatch or a non-unique corpus normalizer (P19-1). *(consistency)*
- A corrupt / non-finite decimal read from a signal or forward-return value. *(consistency,
  never guessed)*

**Recorded as first-class UNDEFINED (never raised, never fabricated — P19-4):** a period
below the member floor (`n_members < 2·Q`) → the whole per-period block is
`INSUFFICIENT_MEMBERS`; an empty top / bottom bucket after sorting → `EMPTY_LONG_LEG` /
`EMPTY_SHORT_LEG` (no leg fabricated, no member silently dropped); a summary over no valid
period → `NO_VALID_PERIODS`; over exactly one valid period → the cumulative / mean / hit-rate
cells stay KNOWN but the dispersion cells are `SINGLE_VALID_PERIOD`; a series (of ≥ 2 valid
periods) with zero population dispersion → the annualized Sharpe / t-statistic are
`ZERO_RETURN_VARIANCE` (the mean, cumulative, and the zero volatility stay KNOWN). There is no
divide-by-zero anywhere: a zero denominator becomes a recorded UNDEFINED, exactly as Phase 7
metrics / Phase 15 analytics / Phase 16 diagnostics / Phase 18 regressions do.

---

## 8. Public API (locked)

```python
from quantforge import (
    Workspace,
    FactorPortfolioSpecification,
    FactorPortfolio,
)

ws = Workspace.open(root)
spec = FactorPortfolioSpecification(
    name="value-long-short",
    signal="current_ratio",  # a Phase 7 metric_key
    period=PERIOD,  # the explicit MetricPeriod it is read for
    universe=universe_spec,  # a Phase 9 UniverseSpecification (explicit source filter)
    schedule=schedule,  # a Phase 12 RebalanceSchedule of rebalance instants T
    forward_horizon="1d",  # "<n>d" trading-day horizon
    quantiles=5,  # Q >= 2 (long = top bucket, short = bottom bucket)
    dataset_version_id=fundamentals_pin,  # re-verified at construct (P19-1)
    market_dataset_version_id=market_pin,
    weighting="equal",  # v1 closed vocabulary
    risk_free_per_period="0",  # annualization convention (folded into identity)
    periods_per_year="252",
)
portfolio = ws.factor_portfolio_engine.construct(
    spec
)  # sealed, write-once FactorPortfolio

portfolio.per_period  # ordered PerPeriodReturn — one per rebalance date (schedule order)
portfolio.summary  # FactorReturnSummary — cumulative / mean / vol / Sharpe / t-stat / hit rate
portfolio.coverage  # per-date + total coverage counts (audit metadata, not folded)
portfolio.research_result_id  # == portfolio.factor_portfolio_id (ResearchRecord)

# typed read-back (byte-identical round-trip)
again = ws.research_result_store.read_as(
    portfolio.research_result_id, FactorPortfolio.from_dict
)
```

`FactorPortfolioEngine` is reached only through `Workspace.factor_portfolio_engine` (a lazy,
cached, cycle-free `@property` annotated `-> object`; engines are not re-exported at top
level). `construct(spec) -> FactorPortfolio` is the single entry point. No `Company` method
is added (a factor portfolio spans a universe + one signal, not one filer).

---

## 9. Out of scope (strict)

Deferred to later, explicitly-labelled phases; Phase 19 does not absorb any:
- **Any modification to Phase 12** (its vocabulary, engine, or identity) — Alt B is its own
  gated phase.
- **Multi-signal composite / orthogonalized factors**, signal neutralization, z-scoring,
  winsorization (a future closed-vocabulary extension).
- **Value / rank / signal-proportional leg weighting** (D-WEIGHT; a future closed
  vocabulary).
- **Transaction-cost-aware / net-of-cost factor returns**, execution modelling, cash,
  share-level fills (that is Phase 12's domain).
- **Factor risk model / covariance-matrix estimation** (needs multiple factor series first;
  the phase after this).
- **Feeding `FactorPortfolio` into Phase 17 attribution** (a future Phase 17 extension; no
  scope reserved now).
- **Rolling/windowed factor performance**, sub-period / regime conditioning.
- **Calendar/step forward-horizon forms** and **multi-share-class** forward returns (the
  Phase 16 deferrals, inherited — a company with ≠ 1 tradable security is dropped and
  recorded).
- **A REVISED scope** for the construction (reserved for a future explicitly-labelled phase).
  v1 is PIT-signal / ex-post only.
- **A `rank_direction` knob** (D-DIRECTION-KNOB; v1 fixes high-minus-low on the raw signal).
- **Batch/multi-signal runs** (one spec = one factor study; batching is a thin future loop).

---

## 10. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 19 suite added), deterministic across runs
  (including `-p no:randomly`).
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src` clean
  (strict).
- Zero runtime dependencies (stdlib `hashlib` / `json` / `dataclasses` / `Decimal` only); no
  float in any path; no wall-clock/RNG in any identity or value; the annualized Sharpe uses
  `Decimal.sqrt` under the pinned context (the Phase 12 precedent, no numpy).
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** — the only source edits are the additive
  `Workspace.factor_portfolio_engine` property/cache line and the `__init__.py` re-exports;
  no edit to any other identity/version module or to `backtest/*`, `analytics/*`,
  `attribution/*`, `crosssection/*`, `diagnostics/*` (beyond importing `forward_return`),
  `panel/*`, `market/*`, or `universe/*`.
- Byte-identical `FactorPortfolio` round-trip test proves `from_dict` introduces no drift and
  a tampered stored id is ignored; a determinism double-build proves `to_dict()`
  byte-equality and id sensitivity to each input.
- P19-1 (both pins folded + re-verified; changed corpus → different id; mismatch raised),
  P19-2 (no `Pit*` type / no as-of accessor; forward return is ex-post; not a
  `BacktestResult`), P19-3 (signal read PIT-eligibly via `panel_across(as_of=T)`), P19-4
  (fail-closed pairing + UNDEFINED-preserving per-period leg formation), P19-5 (distinct
  record type) each covered by a test.
- Docs updated; `ARCHITECTURE.md` "Factor-portfolio construction" row added and `README.md`
  advanced to `v0.16.0` only when green.

---

## 11. Test coverage (locked)

New package `tests/factorportfolio/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_stats.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline over
fictional CIKs `9999999901..` (reusing the Phase 18 cross-section synthetic corpus verbatim,
where filer `i` has `current_ratio = 2 + i`, a strictly increasing signal), covering:

- **Construction validation** — every fail-closed spec path (empty fields, non-`MetricPeriod`
  period, non-`UniverseSpecification` universe, `quantiles < 2`, non-`int`/`bool` quantiles,
  unknown weighting, bad/zero horizon, non-decimal / non-finite annualization, empty corpus
  pins), the derived `horizon_days`, the annualization canonicalization
  (`+0.01` → `0.01`, `2.52E2` → `252`), and the order-preserving canonical payload (SPEC).
- **Exact-`Decimal` per-period leg formation + series aggregation** against hand-computed
  reference values — the two-quantile four-member spread, the tie-break by
  (signal, `company_id`), the uneven five-member `{0,0,0,1,1}` split, below-floor
  `INSUFFICIENT_MEMBERS`, rejection of a non-decimal / non-finite input; the two-period
  summary (cumulative `0.0608`, mean `0.03`, population vol `0.01`, Sharpe `3`, t-stat
  `3√2`, hit rate `1`), annualization scaling (ppy=4 → Sharpe `6`), the risk-free shift,
  the negative-mean t-sign, single-period `SINGLE_VALID_PERIOD`, no-period
  `NO_VALID_PERIODS`, zero-variance `ZERO_RETURN_VARIANCE`, and determinism (STATS).
- `factor_portfolio_id` folding + sensitivity to each input (engine version, name, spec
  version, signal, period, universe/schedule/horizon/quantiles/weighting/either annualization
  field/either pin, result hash); `factor_portfolio_result_hash` determinism + per-cell
  sensitivity + key-order independence; the engine-version's dependence on the pinned
  precision + formula (IDENTITY).
- Byte-identical `to_dict` / `from_dict`, derived-id survival, `research_result_id` alias,
  `boundary_kind = "pit"`, result-hash sensitivity to a factor return, leg membership **not**
  folded, coverage **not** folded, UNDEFINED-cell round-trip, tampered-id ignored,
  malformed-cell rejection (RESULT).
- End-to-end over the builders: all dates resolve with a KNOWN factor return, the legs follow
  the monotone signal (long = the two highest-signal filers, short = the three lowest),
  the summary covers all valid periods, full coverage with no drops; persistence +
  byte-identical round-trip from the sidecar; re-construction idempotent no-op; two
  independent corpora agree; the P19-2 ex-post boundary (no `pit`/`as_of` accessor,
  `boundary_kind = "pit"`, not a `BacktestResult`); P19-1 corpus-pin mismatch fails closed
  (fundamentals + market); P19-4 coverage (a member without a tradable security dropped for
  return; a below-floor `n_filers=3` corpus → every date `INSUFFICIENT_MEMBERS` → refused);
  the fail-closed single-scheduled-date / fewer-than-two-valid-periods raise (ENGINE).
- `tests/test_smoke.py` — an additive public-API export assertion for
  `FactorPortfolioSpecification` / `FactorPortfolio`.

No real financial or network data; the architecture does not require it.
