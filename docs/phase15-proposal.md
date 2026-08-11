# Phase 15 — Performance & Benchmark-Relative Analytics (PROPOSAL)

> **Status:** Proposal for review. **No code has been written.** The sole deliverable of
> this step is this document. Nothing in `src/`, `tests/`, or the architecture docs has
> been modified. Every recommendation below is expressed as an explicit decision
> (`D1..Dn`) with Question / Options / Recommendation / Reason / Consequence, so the
> reviewer approves each load-bearing choice before any implementation begins.
>
> **One-line thesis:** Phase 15 adds a deterministic, content-addressed **risk &
> benchmark-relative analytics** layer strictly *above* Phase 12, a **pure consumer** of
> already-sealed, PIT-correct `BacktestResult`s. It computes the family of statistics the
> Phase 12 `stats.py` docstring explicitly deferred — downside/drawdown risk, historical
> VaR/CVaR, return-distribution moments, and (against a **benchmark that is itself a
> sealed backtest**) tracking error, information ratio, and single-factor OLS alpha/beta —
> under the same pinned `Decimal` context, sealing the result as a new `ResearchRecord`
> to the existing sidecar. It introduces **no new data source, no new PIT resolution, no
> benchmark ingestion, no runtime dependency, and no database**, and it computes **no**
> value from anything not already sealed and PIT-eligible.

---

## A. Capability name

**Performance & Benchmark-Relative Analytics** — package `src/quantforge/analytics/`,
producing a sealed `PerformanceAnalytics` record from an `AnalyticsSpecification`, built by
an `AnalyticsEngine` reached through `Workspace.analytics_engine`.

A deliberate naming note: Phase 13 already owns `experiment/analysis.py` and the word
"comparison" (`BacktestComparison` *ranks* sealed results by one already-computed
statistic). Phase 15 is distinct — it *computes new statistics* — so it lives in its own
package `analytics/` with its own vocabulary (`PerformanceAnalytics`, not "analysis"), to
keep the two capabilities impossible to confuse at the import site.

---

## B. Problem statement

QuantForge can, as of Phase 14, run a declarative PIT backtest (Phase 12), sweep it into a
family and rank the family by one absolute statistic (Phase 13), and emit a
reference-only report over the sealed artifacts (Phase 14). What it **cannot** do is
answer the two questions every quantitative researcher asks *after* a backtest runs:

1. **"How risky is this strategy, beyond its Sharpe ratio?"** — The Phase 12 statistic set
   is deliberately thin: cumulative/period return, arithmetic mean, population volatility,
   Sharpe, max drawdown, mean turnover. The `stats.py` docstring names, verbatim, what it
   defers: *"anything needing linear algebra or distributional machinery (attribution,
   regression alpha/beta, information ratio, bootstrapped intervals)."* There is today **no**
   downside deviation, no Sortino, no Calmar, no drawdown *duration* or recovery, no
   historical VaR/CVaR, and no return-distribution shape (skew/kurtosis, best/worst period,
   hit rate). A researcher cannot size a strategy's tail risk from a QuantForge result.

2. **"Did this strategy beat a benchmark?"** — There is **no benchmark anywhere in the
   system.** Every Phase 12/13 statistic is *absolute* and self-referential. `BacktestResult`
   seals `period_returns` (a tuple of decimal strings) but nothing consumes it relative to a
   reference series. A researcher cannot compute active return, tracking error, information
   ratio, or alpha/beta — the core vocabulary of relative performance evaluation.

The raw material for both already exists and is sealed: **`BacktestResult.period_returns`**
(the per-rebalance return vector) plus the equity curve derivable from it and
`initial_capital`. Phase 15 is the layer that turns that already-sealed, already-PIT-correct
vector into the risk and relative-performance statistics the engine deferred — with **zero**
new market resolution and therefore **zero** new look-ahead surface.

---

## C. Target users

- **Quantitative researchers** evaluating a strategy's risk profile and its performance
  *relative to a reference strategy* (a market proxy, an equal-weight universe, a prior
  strategy version) before allocating conviction to it.
- **Reviewers / auditors** who need a reproducible, content-addressed risk statement that
  pins exactly which backtests it was computed from and fails closed if either drifts.
- **The Phase 14 reporting layer and any future phase**, which gain a new sealed
  `ResearchRecord` kind (`analytics`) they can reference by `(id, content_hash)` exactly as
  they reference a backtest or experiment today — a report can now include a risk section
  and a benchmark-relative section without the renderer computing anything.

---

## D. Primary use cases

1. **Absolute risk profile of one strategy.** `AnalyticsSpecification(name=..., subject_id=
   <backtest_id>)` (no benchmark) → a `PerformanceAnalytics` sealing downside deviation,
   Sortino, Calmar, max-drawdown duration & recovery, historical VaR/CVaR at requested
   confidence(s), and distribution moments — all over `subject.period_returns`.
2. **Benchmark-relative evaluation.** `AnalyticsSpecification(name=..., subject_id=<strategy
   backtest_id>, benchmark_id=<benchmark backtest_id>)` → the absolute block **plus** active
   return, tracking error, information ratio, correlation, up/down capture, and single-factor
   OLS alpha & beta of subject vs benchmark. The benchmark is a sealed backtest (e.g. an
   equal-weight buy-and-hold over the same universe on the same schedule).
3. **Reproducible risk statement for a report.** Phase 14 references the sealed
   `PerformanceAnalytics` by `(analytics_id, result_hash)`; the renderer prints the sealed
   decimal strings verbatim — no recomputation, no new number invented at render time.

---

## E. Why this is the correct next phase (and why not earlier / later)

- **It is the smallest layer that closes the single largest research gap.** The system can
  *produce* returns (Phase 12) and *rank* them (Phase 13) but cannot *characterise their risk
  or measure them against anything*. Analytics is the missing verb between "I have results"
  and "I can decide."
- **Its raw material is already sealed and PIT-correct.** `period_returns` shipped in Phase
  12. Phase 15 needs no new ingestion, no new resolver, no new `as_of` — the hardest and most
  dangerous work (making the returns look-ahead-free) is already done and locked. This makes
  Phase 15 both high-value and low-risk: it is a pure, deterministic function of sealed bytes.
- **Not earlier:** it is meaningless before backtests and their `period_returns` exist
  (Phase 12) and before a comparison/report consumer pattern was proven (Phases 13–14). It
  reuses the exact "pure consumer of sealed artifacts → seal a new `ResearchRecord`" spine
  those phases established.
- **Not later:** every downstream capability the roadmap hints at — richer reporting, a
  research UI/API, multi-factor attribution — *wants a risk/relative-performance number to
  display or extend*. Building attribution (Phase 16+) on top of a layer that cannot even
  compute beta would invert the dependency order. Analytics is the correct floor beneath all
  of them.
- **It respects the deferral ledger.** Phase 12 deferred exactly this family of statistics
  *by name*; Phase 15 is the phase that ledger was written for.

---

## F. Alternatives considered (and why rejected as the *primary* Phase 15 capability)

Each was evaluated against the repository, not the old roadmap.

1. **A query / retrieval layer over sealed research records.** *Rejected as primary.* The
   sidecar already exposes `has`, `read_as`, and typed `from_dict` round-trips; a query layer
   is convenience, not capability, and adds no research power. Better as a small future
   utility once there are more record kinds to query (Phase 16+).
2. **Richer execution / cost models (market impact, partial fills, borrow, `next_open`).**
   *Rejected as primary.* This is genuinely valuable but it is a **modification of the Phase
   12 engine's identity surface** — every such addition is a new enum value that bumps
   `backtest_engine_version_id` and re-forks every backtest. It is a Phase 12 *evolution*, not
   a new layer, and it touches the most load-bearing invariant surface in the system. Lower
   value-per-risk than a pure-consumer layer, and the README already flags it as a candidate
   *next* — but building analytics first gives us the tools to *measure* whether a richer cost
   model actually improved anything.
3. **Multi-factor attribution / factor-risk models (Fama-French-style regression).**
   *Rejected as primary; explicitly deferred to Phase 16+.* This genuinely needs linear
   algebra (matrix inversion for multi-regressor OLS), which cannot be done in stdlib `Decimal`
   without either a dependency (violating the zero-dependency invariant) or a hand-rolled
   linear-algebra module of real numerical risk. Single-factor OLS (one benchmark) is
   closed-form scalar arithmetic and *is* in scope; multi-factor is not.
4. **Factor / panel research reports (Phase 10 as report subjects).** *Rejected as primary.*
   Phase 14's scope is `{backtest, experiment}`; extending it to panels/factors is a Phase 14
   *vocabulary* extension, incremental and lower-value than closing the risk/benchmark gap.
5. **Data-quality / audit layer (coverage, gap, revision-frequency reports).** *Rejected as
   primary.* Valuable for operators, but it characterises the *inputs*, not the *research
   output*, and the research-output gap (no risk, no benchmark) is the more acute one. A strong
   Phase 16+ candidate.
6. **Visualization / UI / HTTP API.** *Rejected as primary.* The instruction is explicit that
   UI is not automatically next. A UI over a system that cannot compute a risk-adjusted or
   benchmark-relative number would render a thin story; analytics is the content a UI would
   need first. Presentation belongs strictly above a complete content layer.
7. **Bootstrapped / Monte-Carlo confidence intervals.** *Rejected; deferred.* Requires either
   RNG (forbidden — no randomness invariant) or a deterministic resampling scheme that is its
   own design decision. **Historical** (empirical-quantile) VaR/CVaR delivers most of the tail
   value deterministically with zero randomness, so v1 ships that and defers resampling.

---

## G. Contradiction analysis against every existing invariant

The design was checked against the numbered data-model registry (invariants 1–30, plus 22a)
and the per-phase identity/PIT conventions. Phase 15 **weakens none** of them; several it
actively reinforces.

| Invariant / principle | Phase 15 relationship |
|---|---|
| **PIT / no look-ahead (inv. 6–17)** | **Reinforced.** Phase 15 performs *no* PIT resolution. It reads only `period_returns` from sealed `BacktestResult`s, each of which was already PIT-eligible-at-`T` by BT-2. No new `as_of`, no new market/fundamental read. There is no path by which future data can enter. |
| **PIT vs REVISED separation (inv. 27–30)** | **Preserved.** Backtests are PIT-only (no `RevisedBacktest` exists), so their `period_returns` are PIT-only; the analytics record carries an explicit, un-defaulted `boundary_kind = "pit"` (inv. 27) and fails closed on anything else. A REVISED analytics scope is reserved for a future explicitly-labelled phase (mirrors Phase 14 D10). |
| **Immutable source data (inv. 1–4)** | **Untouched.** No `Fact`, `PriceObservation`, `CorporateAction`, or any raw/canonical record is read or written. Only the research sidecar is touched. |
| **Content-addressed identity (per-phase)** | **Extended, not weakened.** A fresh domain tag `analytics/1`, NUL-separated composite ids, canonical JSON, no collision with any prior layer's tags. |
| **Deterministic reproducibility (inv. 13, 18–21, principle 5/6)** | **Reinforced.** All arithmetic under the *same* pinned `Decimal` context (prec 34, `ROUND_HALF_EVEN`) already used by metrics/market/backtest; no float, no wall-clock, no RNG, no iteration-order dependence. Same inputs → same `analytics_id` and bytes on any machine. |
| **Fail-closed (principle 1; §17 discipline)** | **Followed exactly.** A missing/drifted referenced record, a schedule/length mismatch between subject and benchmark, an incommensurable engine version, or an out-of-range parameter **raises**. A statistic that is genuinely undefined for the data (e.g. Sortino with zero downside, beta with zero benchmark variance) is recorded as a first-class UNDEFINED value with a reason — **never fabricated, never a divide-by-zero**. |
| **Provenance (principle 3; inv. 5)** | **Preserved by reference.** The record pins each input backtest by `(backtest_id, result_hash)`; each already carries complete lineage to raw SEC/market bytes. Provenance is exactly as strong as the source's, with no duplication or divergence. |
| **ResearchResult / `ResearchRecord` identity (Phase 8/§9)** | **Reused verbatim.** `PerformanceAnalytics` implements the `ResearchRecord` Protocol (`research_result_id` + `to_dict`) and persists through the existing `ResearchResultStore`. No new store. |
| **Dataset pinning (inv. 21)** | **Honoured.** Each referenced backtest already pins its `dataset_version_id` / `market_dataset_version_id`; the analytics record carries them through for audit. Subject vs benchmark corpus **pin mismatch is surfaced** (like Phase 13), never silently ignored. |
| **Security identity (per-phase)** | **N/A / untouched.** Phase 15 operates on scalar return vectors, never on securities. |
| **Corporate actions / PeriodAxis / PriceAxis / Universe survivorship** | **Untouched.** All were consumed by Phase 12 to *produce* the sealed returns; Phase 15 reads only the returns. |
| **BacktestResult / ExperimentResult / ResearchReport identity** | **Untouched.** No existing record's identity, schema, or bytes change. `stats.py`, `result.py`, `analysis.py` are not modified. |
| **Write-once persistence (Phase 8; Phase 14 D8)** | **Reused.** Re-running identical analytics is a byte-identical no-op write; a differing payload under an existing id fails closed via the store's `FactorConsistencyError` guard. |
| **No database / zero runtime deps / no hidden state (principle 10; ARCHITECTURE)** | **Preserved.** Only `<root>/research/` is written. Only stdlib `hashlib`/`json`/`dataclasses`/`Decimal`. Single-factor OLS is closed-form scalar `Decimal`; **no** linear-algebra dependency. |
| **Phase boundaries** | **Respected.** Multi-factor attribution, bootstrapped intervals, external benchmark ingestion, and rolling-window *series* artifacts are explicitly deferred (§V). |
| **`strategy_version` reservation** | **Untouched** — Phase 15 has no strategy; it consumes results. |
| **Existing public API contracts** | **Additive only.** New top-level exports (`AnalyticsSpecification`, `PerformanceAnalytics`) and one new `Workspace` property; no existing signature changes. |

**The one genuine tension, resolved openly:** Phase 12's `stats.py` docstring says regression
alpha/beta "needs linear algebra." That is true of *multi-factor* regression (matrix
inversion). *Single-factor* OLS against one benchmark is the closed-form scalar identity
`beta = cov(r_p, r_b) / var(r_b)`, `alpha = mean(r_p) − [rf + beta·(mean(r_b) − rf)]`, which is
pure `Decimal` arithmetic with no matrix. Phase 15 delivers **only** the single-factor case and
explicitly leaves multi-factor deferred (§V, D-table). This does not contradict the deferral —
it honours its *reason* (no linear-algebra machinery) while delivering the tractable subset.

---

## H. Relationship to Phases 1–14

```
Phase 1–5    immutable raw + canonical facts + PIT availability
Phase 7      metrics (PIT/REVISED)          ─┐
Phase 8      factors + ResearchResultStore   │  the shared sidecar + ResearchRecord
Phase 9      universe                        │  protocol Phase 15 reuses unchanged
Phase 10     fundamental panel               │
Phase 11     market data (PitPrice)          │
Phase 12     BACKTEST → seals period_returns ─┘  ← Phase 15's sole input
Phase 13     experiment sweep + comparison (ranks sealed stats; computes none)
Phase 14     report (references sealed records; computes none)
────────────────────────────────────────────────────────────────────────────
Phase 15     ANALYTICS: computes NEW risk & relative stats over sealed
             period_returns; seals a PerformanceAnalytics ResearchRecord.
```

Phase 15 sits beside Phases 13/14 as a third pure consumer of sealed Phase 12 output, and
differs from them in exactly one way: **it computes new numbers.** Phase 13 *ranks*
already-computed statistics; Phase 14 *references* them; Phase 15 *derives* new ones. It reuses
the extension spine every prior phase used: versioned immutable request → fail-closed engine
reached lazily from `Workspace` → distinct sealed result type → content-addressed identity with
a fresh domain tag → data conditions recorded as first-class values, defects raised →
compute-on-demand, write-once to the shared sidecar.

The new record kind slots directly into Phase 14: `ReportSpecification` can (in a future Phase
14 vocabulary bump — **out of Phase 15 scope**, noted in §U) reference an `analytics` record the
same way it references a backtest.

---

## I. Architecture overview

```
                 AnalyticsSpecification            (declarative request, content-addressed)
                          |
                          v
   Workspace.analytics_engine  --->  AnalyticsEngine.compute(spec)
                          |                 |
                          |   resolve subject (+ optional benchmark) from the shared sidecar
                          |   verify each result_hash (fail closed on absent / drift)
                          |   verify commensurability (same schedule_id & length; compatible
                          |   engine version; surface corpus pin_mismatch)
                          v                 v
        compute absolute (+ relative) statistics under the pinned Decimal context
        (UNDEFINED-preserving; no float; no RNG; no wall-clock)
                          |
                          v
             PerformanceAnalytics (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
             store.read_as(id, PerformanceAnalytics.from_dict)   (typed, byte-identical round-trip)
```

**New package `src/quantforge/analytics/`** (mirrors `experiment/`):

- `errors.py` — `AnalyticsError` → `AnalyticsConfigurationError`, `AnalyticsConsistencyError`.
- `identity.py` — `analytics_engine_version_id`, `analytics_result_hash`, `analytics_id`. Fresh
  domain tags `analytics/1`, `analytics-engine/1`.
- `version.py` — `AnalyticsEngineVersion` (folds the pinned decimal context **and** the
  formula-method version `analytics-stats/1` into `config_hash`); `ANALYTICS_ENGINE_VERSION`.
  Mirrors `backtest/version.py`.
- `model.py` — `AnalyticsStatus`/`AnalyticsUndefinedReason` vocabulary; the closed v1 statistic
  key sets; `StatValue` (a KNOWN decimal string **or** UNDEFINED+reason) discipline.
- `compute.py` — the pure statistic functions (return moments, downside/drawdown risk,
  historical VaR/CVaR, tracking error, information ratio, correlation, capture, single-factor
  OLS alpha/beta). Pure; reads no store; takes decimal-string vectors, returns decimal strings.
- `spec.py` — `AnalyticsSpecification`, full construction-time validation.
- `result.py` — `ANALYTICS_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, `PerformanceAnalytics`
  (a `ResearchRecord` with `.seal`/`to_dict`/`from_dict`).
- `engine.py` — `AnalyticsEngine` (constructed from `Workspace`; composes
  `research_result_store` + `AnalyticsEngineVersion`): resolve → verify → compute → seal →
  write-once.
- `__init__.py` — package exports.

**The only edits to existing source** (both additive; neither alters any existing identity):

1. `workspace.py` — one lazy `analytics_engine` `@property` (+ its `self._analytics_engine =
   None` cache line), following the `experiment_engine` template verbatim.
2. `src/quantforge/__init__.py` — top-level re-exports of `AnalyticsSpecification` and
   `PerformanceAnalytics` (spec + result only; the engine is reached via `Workspace`).

**No edit to** `backtest/*` (including `stats.py`, `result.py`, `version.py`), `experiment/*`
(including `analysis.py`), `report/*`, `factors/store.py`, or any identity/version module.

---

## J. Data model

All types `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
wall-clock, no RNG.

### J.1 `AnalyticsSpecification` (declarative request)

```
AnalyticsSpecification(
    name: str,                                   # non-empty
    subject_id: str,                             # non-empty sealed backtest_id
    benchmark_id: str | None = None,             # a sealed backtest_id; None => absolute-only
    var_confidences: tuple[str, ...] = ("0.95",),# decimal strings, each strictly in (0,1)
    risk_free_per_period: str = "0",             # MAR / rf convention (decimal string)
    periods_per_year: str = "1",                 # annualization convention (decimal string, > 0)
    spec_version: str = "analytics/1",
)
```

Construction-time validation (fail closed, `AnalyticsConfigurationError`): empty `name`; empty
`subject_id`; `benchmark_id == subject_id` (a strategy is not its own benchmark — ambiguous);
empty/duplicate/`≤0`/`≥1` `var_confidences`; non-decimal or negative `risk_free_per_period`;
non-decimal or non-positive `periods_per_year`. `var_confidences` is canonicalised and treated
as a **set** for identity (order never changes the id). Reads no store, no wall clock.

### J.2 `PerformanceAnalytics` (implements `ResearchRecord`)

```
PerformanceAnalytics(
    analytics_engine_version_id: str,
    analytics_spec: dict[str, object],           # the full AnalyticsSpecification.to_dict()
    subject_ref: tuple[str, str],                # (backtest_id, result_hash)
    benchmark_ref: tuple[str, str] | None,       # (backtest_id, result_hash) or None
    boundary_kind: str,                          # "pit" (v1 PIT-only)
    schedule_id: str,                            # the shared schedule the returns align on
    periods: int,                                # length of the return vector analysed
    absolute: tuple[tuple[str, "StatValue"], ...],   # sorted by key: risk/return/distribution
    relative: tuple[tuple[str, "StatValue"], ...],   # sorted by key; empty when no benchmark
    var: tuple[tuple[str, "StatValue", "StatValue"], ...],  # (confidence, VaR, CVaR), sorted
    risk_free_per_period: str,
    periods_per_year: str,
    dataset_version_ids: tuple[str, ...],        # distinct pins across subject(+benchmark)
    market_dataset_version_ids: tuple[str, ...],
    formula_version: str,                        # "analytics-stats/1"
    result_hash: str,                            # canonical JSON over the computed outputs
)

# derived, never stored as state:
analytics_id        property -> sha256 folding engine version + spec identity
                                + referenced content hashes + result_hash
research_result_id  property -> alias of analytics_id  (the ResearchRecord key)
pin_mismatch        property -> True iff subject and benchmark differ on any dataset pin
best / summary      -> n/a (analytics is a value record, not a ranking)
```

- `StatValue` is the UNDEFINED-preserving cell: either `("known", "<decimal string>")` or
  `("undefined", "<AnalyticsUndefinedReason>")`. It is **never** a bare float and **never**
  silently omitted — a statistic that cannot be computed for the data is present with a reason.
- `to_dict()` keys (deterministic, `sort_keys=True`): all fields above plus the
  `research_result_id` alias so the generic sidecar reader keys correctly.
- `from_dict` is the fail-closed inverse; `analytics_id`/`research_result_id` are re-derived by
  their properties, **never read from state**, so `from_dict(to_dict(r))` re-emits identical
  bytes and a tampered stored id is ignored (mirrors Phase 14 D4/D8).
- `.seal(...)` is the identity-computing constructor (mirrors `ExperimentResult.seal` /
  `BacktestResult` sealing): it folds the computed outputs into `result_hash`, so identity is a
  pure function of the request + referenced content + computed answer, never caller-supplied.

**What the model deliberately does NOT hold:** section titles, prose, display order, any
presentation; the referenced backtests' bodies/ledgers (pointer-only, like `ExperimentResult`);
any float; any wall-clock or RNG value.

### J.3 Closed v1 statistic vocabulary

Extending any set is an explicit future edit that hashes distinctly — never an implicit
fallback (mirrors the Phase 13 D7 / Phase 14 D7 discipline).

**Absolute** (over subject `period_returns` + derived equity curve; benchmark not required):
`downside_deviation`, `sortino`, `calmar`, `max_drawdown_duration_periods`,
`max_drawdown_recovery_periods`, `skewness`, `excess_kurtosis`, `best_period_return`,
`worst_period_return`, `positive_period_fraction`. (Return/volatility/Sharpe/max-drawdown are
**not** recomputed — they are already sealed in the subject's `PerformanceStatistics`; Phase 15
adds only what is missing, exactly as Phase 13 computes no already-sealed statistic.)

**Historical VaR/CVaR** (per requested confidence): `var`, `cvar` — empirical lower-quantile of
the return distribution by the **nearest-rank** method (pinned; no interpolation, no
distribution assumption, no RNG).

**Relative** (subject vs benchmark; both required, aligned): `active_return`,
`cumulative_active_return`, `tracking_error`, `information_ratio`, `beta`, `alpha`,
`correlation`, `up_capture`, `down_capture`.

`AnalyticsUndefinedReason` (closed): `INSUFFICIENT_PERIODS`, `ZERO_DOWNSIDE` (Sortino with no
downside observations), `ZERO_BENCHMARK_VARIANCE` (beta/capture undefined), `ZERO_TRACKING_ERROR`
(information ratio undefined), `NO_DRAWDOWN` (Calmar/duration when equity never falls),
`UNRECOVERED_DRAWDOWN` (recovery when the trough is never regained by series end).

---

## K. Public API

```python
from quantforge import AnalyticsSpecification, PerformanceAnalytics
from quantforge import Workspace

ws = Workspace.open(root)

# absolute risk profile of one sealed backtest
spec = AnalyticsSpecification(name="risk-profile", subject_id=strategy_backtest_id)
analytics = ws.analytics_engine.compute(
    spec
)  # a sealed, write-once PerformanceAnalytics

# benchmark-relative evaluation vs a sealed equal-weight buy-and-hold backtest
rel = AnalyticsSpecification(
    name="vs-equal-weight",
    subject_id=strategy_backtest_id,
    benchmark_id=equal_weight_backtest_id,
    var_confidences=("0.95", "0.99"),
    periods_per_year="12",
)
result = ws.analytics_engine.compute(rel)

# typed read-back (byte-identical round-trip)
again = ws.research_result_store.read_as(
    result.research_result_id, PerformanceAnalytics.from_dict
)
```

`AnalyticsEngine` is reached only through `Workspace.analytics_engine` (engines are not
re-exported at top level — matches every prior phase). `compute(spec) -> PerformanceAnalytics`
is the single entry point. No `Company` method is added (analytics spans results, not one filer
— mirrors the Phase 13 D6 decision to keep `Company` per-filer).

---

## L. Identity / content-addressing

Domain tags via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
(`sort_keys=True, ensure_ascii=False, separators=(",",":")`). Fresh tags: `analytics/1`,
`analytics-engine/1`.

- `analytics_engine_version_id = sha256(code_version "analytics-engine/1", config_hash)` where
  `config_hash` folds the pinned decimal context (`prec=34\x00round=ROUND_HALF_EVEN`) **and** the
  formula-method version `analytics-stats/1` (which encodes the VaR quantile method and the
  skew/kurtosis definitions). Any change to a formula method bumps the version — exactly the
  `backtest/version.py` pattern, extended with the formula knob.
- `analytics_result_hash = sha256(canonical JSON over the ordered computed outputs:
  absolute + relative + var, each as (key, status, value))`. Sensitive to the computed answer,
  like `BacktestResult.result_hash`.
- `analytics_id = sha256` folding, NUL-joined: `analytics_engine_version_id`, the spec identity
  (name, spec_version, subject_id, benchmark_id or "", sorted `var_confidences`,
  `risk_free_per_period`, `periods_per_year`), the **referenced content hashes** (subject
  `result_hash`, benchmark `result_hash` or ""), and `analytics_result_hash`. So the id is
  sensitive to *any* change in *either* referenced backtest, the convention, the requested
  parameters, or the computed answer — honestly self-verifying.
- `research_result_id` aliases `analytics_id` (single id, mirrors `BacktestResult.backtest_id`;
  simpler than Phase 14's two-id split because analytics, like a backtest, is a value record
  whose id already folds its output).

**Folds (changes identity):** engine-logic + formula version ✔, decimal context ✔, the full
declared request ✔, both referenced backtests' `result_hash` ✔, the computed statistics ✔.
**Does NOT fold:** record schema/format version (a container concern — Phase 14 D9 discipline),
any presentation, wall-clock, RNG, `id()`, iteration order (all set-valued inputs are sorted).

---

## M. PIT semantics

- **Pure PIT consumer.** Phase 15 performs no PIT resolution and takes no `as_of`. Its inputs
  are `BacktestResult.period_returns`, each element of which was produced by the Phase 12 engine
  under BT-2 (every decision at `T` saw only PIT-eligible-at-`T` data). Reading a sealed return
  vector cannot introduce look-ahead.
- **PIT-only v1.** Backtests are PIT-only by construction (no `RevisedBacktest`; the engine
  consumes the PIT-only `PitPriceSeries` hand-off). The record carries an explicit, un-defaulted
  `boundary_kind = "pit"` (inv. 27) and **fails closed** on any other value. A REVISED analytics
  scope is reserved for a future distinct, explicitly-labelled phase (mirrors Phase 14 D10).
- **Benchmark PIT integrity.** Because the benchmark is itself a sealed `BacktestResult`, its
  returns are PIT-correct by the same construction — there is no unprovenanced external index
  series that could smuggle in look-ahead. This is the central reason the benchmark is
  in-system (D3 below).

---

## N. Provenance

- **By reference, never by copy.** The record pins subject and benchmark by
  `(backtest_id, result_hash)`. Each referenced backtest already carries complete lineage down
  to raw SEC/market bytes; the analytics record's provenance is exactly as strong, with no
  duplication or divergence.
- **Convention recorded.** `risk_free_per_period` and `periods_per_year` are stored and folded
  into identity — two analytics identical except for annualization convention get distinct ids
  (they report distinctly-annualized numbers — mirrors Phase 13 D5).
- **Pins carried through.** `dataset_version_ids` / `market_dataset_version_ids` record the
  distinct corpus pins across the referenced backtests; `pin_mismatch` surfaces when subject and
  benchmark differ (analogue of `UniverseComparison.mode_mismatch` / Phase 13 `pin_mismatch`) —
  surfaced, never silently compared away.

---

## O. Reproducibility

Same spec + same sealed inputs → same `analytics_id`, same bytes, on any machine. All arithmetic
under an explicit `localcontext` (prec 34, `ROUND_HALF_EVEN`), never the ambient process context.
No float touches any value; `Decimal.sqrt` (already used by `stats.py`) covers all roots. No
wall-clock, no RNG, no iteration-order dependence (every set-valued input is sorted before
hashing). A `TestDeterminism` double-build asserts byte-identical `to_dict()` and equal ids, id
sensitivity to each input, and input-order invariance — the established convention.

---

## P. Persistence / storage

- **Zero new store types.** `PerformanceAnalytics` is a `ResearchRecord` written through the
  existing `ResearchResultStore` to `<root>/research/sha256-<hex>.json`, in the existing
  container (`{"research_result_format_version": 1, "research_result": ...}`), atomic
  (tmp+fsync+os.replace), `indent=2, sort_keys=True, ensure_ascii=False`.
- **Write-once, idempotent.** Re-computing identical analytics is a byte-identical no-op write; a
  differing payload under an existing id fails closed via the store's `FactorConsistencyError`
  guard (Phase 14 D8 discipline).
- **No database, no in-repo data.** Only `<root>/research/` is written; the store is safe to
  delete and rebuild byte-identically from its inputs.

---

## Q. Failure / fail-closed behavior

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`AnalyticsConfigurationError` / `AnalyticsConsistencyError`):
- Empty `name`; empty `subject_id`; `benchmark_id == subject_id`; a `var_confidence` outside
  `(0,1)` or duplicated; non-decimal/negative `risk_free_per_period`; non-decimal/non-positive
  `periods_per_year`. *(configuration)*
- `subject_id` or `benchmark_id` absent from the sidecar; a referenced record whose recomputed
  `result_hash` does not match the pin (drift); subject and benchmark with different
  `schedule_id` or unequal `period_returns` length (returns not alignable); subject and benchmark
  with incommensurable `backtest_engine_version_id` (mixed engine versions — mirrors Phase 13);
  `boundary_kind != "pit"`. *(consistency)*
- Fewer periods than a statistic requires that would otherwise force a fabricated value where the
  *whole record* is meaningless (e.g. `periods < 2` for any variance-based statistic) — raised as
  configuration rather than silently emitting an all-UNDEFINED record.

**Recorded as first-class UNDEFINED (never raised, never fabricated):** per-statistic
undefinability with an `AnalyticsUndefinedReason` — Sortino with `ZERO_DOWNSIDE`, beta/capture
with `ZERO_BENCHMARK_VARIANCE`, information ratio with `ZERO_TRACKING_ERROR`, Calmar/duration with
`NO_DRAWDOWN`, recovery with `UNRECOVERED_DRAWDOWN`, any statistic with `INSUFFICIENT_PERIODS`
(when the record as a whole is still meaningful). There is no divide-by-zero anywhere: a zero
denominator becomes a recorded UNDEFINED, exactly as Phase 7 metrics and Phase 10 derivations do.

---

## R. Security / integrity

- **Drift detection.** Because `analytics_id` folds each referenced backtest's `result_hash`, and
  the engine re-verifies those hashes at compute time, a tampered or replaced upstream record is
  caught and fails closed — the analytics record can never silently describe a backtest it was
  not computed from.
- **No untrusted input path.** No network, no external file, no benchmark ingestion. The only
  inputs are sidecar records already produced by the trusted engine and the caller's declarative
  spec (fully validated).
- **No secrets, no bundled data.** No credentials; tests use synthetic sealed backtests over the
  fictional CIKs (`9999999991`/`9999999992`), fully offline.

---

## S. Testing strategy

New package `tests/analytics/` following the established pattern:

- `__init__.py` + `builders.py` — re-exports the Phase 12 backtest builders (to seal synthetic
  subject/benchmark `BacktestResult`s with known `period_returns`), adds a typed
  `analytics_engine(...)` accessor and seal helpers, sorted `__all__`.
- `test_spec.py` — construction validation (all the §Q configuration raises; `var_confidences`
  set-canonicalisation).
- `test_compute.py` — each statistic against **hand-computed** expected decimal strings on tiny
  synthetic vectors (e.g. beta of a series vs itself is exactly `1`; alpha of identical series is
  `0`; Sortino with no downside is `ZERO_DOWNSIDE`; historical VaR at 0.95 on a fixed 20-element
  vector is the pinned nearest-rank element). Property checks: absolute block independent of
  benchmark; relative block empty without a benchmark.
- `test_identity.py` — `analytics_id` folds engine version, spec, referenced content hashes, and
  outputs; is invariant under `var_confidences` order; changes when any input changes.
- `test_result.py` — byte-identical `to_dict`/`from_dict` round-trip; id re-derivation not read
  from state; tampered stored id ignored; reference-only (no embedded backtest body).
- `test_engine.py` — resolve/verify/seal/write-once; fail-closed on absent id, drift, schedule
  mismatch, unequal length, mixed engine versions, non-PIT boundary; `pin_mismatch` surfaced on
  differing corpus pins; write-once idempotence and `FactorConsistencyError` on conflicting
  payload.
- `class TestDeterminism` — double-build byte-identical (`first.to_dict()==second.to_dict()` +
  `research_result_id` equality), id sensitivity, input-order invariance.

All under `uv run pytest` (green across all phases), `ruff check`/`ruff format --check`, `mypy
src tests` strict; `tmp_path` params annotated `# type: ignore[no-untyped-def]`; no conftest.

---

## T. Documentation changes

- **New:** `docs/phase15-analytics.md` (narrative) and, on approval + green implementation, a
  `docs/phase15-analytics-locked.md` normative spec mirroring the Phase 13/14 locked-doc
  discipline.
- **Edited (only when green):** `docs/index.md` (new entry), `ARCHITECTURE.md` (a new
  "Performance & risk analytics" row flipped to ✅), `README.md` (capability line + Project
  Status row `v0.11.0`; "Next" line updated). These are **not** touched during implementation
  until the quality gates pass.

---

## U. Future extension points (enabled by, but out of scope for, Phase 15)

- **Phase 14 vocabulary bump** to let a `ReportSpecification` reference an `analytics` record
  (one new kind in Phase 14's closed reference vocabulary — a Phase 14 edit, not Phase 15).
- **Multi-factor attribution** (Fama-French-style) once a deliberate linear-algebra decision is
  made (dependency vs hand-rolled) — a distinct future phase.
- **Rolling-window analytics as a first-class series artifact** (a `RollingAnalytics` record) —
  v1 computes scalar full-sample statistics only.
- **Deterministic resampling / block-bootstrap confidence intervals** — requires a pinned
  resampling scheme (no RNG), its own design decision.
- **External / index benchmarks** — would require a market-index ingestion source beneath Phase
  11 with its own availability policy; deferred, and unnecessary for v1 because a sealed backtest
  is a fully provenanced benchmark.
- **REVISED-scope analytics** — reserved, explicitly labelled, distinct from PIT (Phase 14 D10
  discipline).

---

## V. Explicit non-goals (deferred to Phase 16+)

- No multi-factor / matrix-based regression or risk decomposition (single-factor OLS only).
- No bootstrapped / Monte-Carlo / parametric intervals; historical (empirical-quantile) VaR/CVaR
  only.
- No external benchmark data, no index ingestion, no caller-supplied return series (would be
  unprovenanced/fabricated — forbidden).
- No rolling-window *series* output; no new charts/UI/HTTP; no recomputation of statistics
  Phase 12 already seals (return, volatility, Sharpe, max drawdown, turnover).
- No modification of Phase 12 statistics, the backtest engine, or any existing record's identity.
- No `Company` method; no new store; no database; no runtime dependency.

---

## W. Decision table (load-bearing decisions requiring explicit approval)

Decisions marked **★** are load-bearing (identity, versioning, persistence, public API, PIT,
provenance, data model, or compatibility) and must be explicitly approved before implementation.

| # | Question | Options | Recommendation | Reason | Consequence |
|---|---|---|---|---|---|
| **D1 ★** | Where does the computed analytics live? | (a) A new `ResearchRecord` persisted write-once to the existing sidecar; (b) recompute-only, never persisted (Phase 13 style). | **(a) Persist as a `ResearchRecord`.** | These are *new, expensive, provenance-bearing numbers* (unlike Phase 13, which re-ranks already-sealed numbers). Sealing them matches the "derived value → sealed record" spine (BacktestResult, ResearchResult) and lets Phase 14 reference them by `(id, content_hash)`. | Adds one new record kind to the sidecar. No new store; reuses `ResearchResultStore` unchanged. |
| **D2 ★** | Does Phase 15 recompute the statistics Phase 12 already seals? | (a) Recompute return/vol/Sharpe/max-dd; (b) consume the sealed ones, add only the missing statistics. | **(b) Add only what is missing.** | Mirrors Phase 13, which "computes no new statistic it can read." Recomputing risks a second, drifting source of truth for the same number. | The record's absolute block excludes already-sealed statistics; a reader joins to the subject's `PerformanceStatistics` for those. |
| **D3 ★** | What is a "benchmark"? | (a) Another sealed `BacktestResult`; (b) a `PitPriceSeries` of an index `security_id` (Phase 11); (c) a caller-supplied return series. | **(a) A sealed `BacktestResult`.** | Only (a) keeps the benchmark PIT-correct, content-addressed, and fully provenanced with **no** new ingestion or fabrication. (b) needs index data that does not exist and a new source; (c) is unprovenanced fabricated data (forbidden). A market proxy is expressed as an equal-weight buy-and-hold backtest. | Relative statistics require subject and benchmark to share `schedule_id` and return length; enforced fail-closed. External benchmarks deferred to a future ingestion phase. |
| **D4 ★** | Is single-factor OLS alpha/beta in scope given `stats.py` deferred "regression alpha/beta … needs linear algebra"? | (a) In scope (single-factor, closed-form scalar `Decimal`); (b) deferred with everything else. | **(a) In scope; multi-factor deferred.** | Single-factor OLS is `beta = cov/var`, `alpha = mean_p − [rf + beta·(mean_b − rf)]` — pure scalar `Decimal`, no matrix, honouring the *reason* for the deferral (no linear-algebra machinery). | Multi-factor regression explicitly deferred to Phase 16+ (would need matrix inversion → dependency or hand-rolled linear algebra). |
| **D5 ★** | How are undefinable statistics represented? | (a) First-class UNDEFINED value + reason (metric-style); (b) raise; (c) omit / emit 0. | **(a) First-class UNDEFINED + reason.** | Matches the QuantForge spine (Phase 7 metrics, Phase 10 derivations, `stats.py` zero-vol→Sharpe 0 was a *value*, not a raise). Never fabricates, never divides by zero, never silently drops. | Introduces a small closed `AnalyticsUndefinedReason` vocabulary; every statistic is present as KNOWN-or-UNDEFINED. |
| **D6 ★** | Is the record one id or a two-id (definition/result) split? | (a) One `analytics_id` folding outputs (BacktestResult style); (b) two ids (report_id/report_result_id, Phase 14 style). | **(a) One id.** | Analytics, like a backtest, is a *value* record whose identity should fold its computed output; there is no separate "definition without result" to address. Simpler and matches BacktestResult. | `research_result_id` aliases `analytics_id`; no separate definition id. |
| **D7 ★** | Historical vs parametric/bootstrapped VaR/CVaR? | (a) Historical (empirical nearest-rank quantile); (b) parametric (distribution assumption); (c) bootstrapped. | **(a) Historical, nearest-rank (pinned).** | Deterministic, no RNG, no distribution assumption, pure `Decimal`. (b) assumes normality (false for returns); (c) needs RNG/resampling (forbidden / separate decision). | Quantile method (`nearest-rank`) is folded into the formula version; changing it bumps `analytics_engine_version_id`. Resampling deferred. |
| **D8 ★** | Is the annualization convention (rf, periods/year) part of identity? | (a) Folded into `analytics_id`; (b) not folded. | **(a) Folded.** | Two analytics identical except for convention report distinctly-annualized numbers — they are materially different (mirrors Phase 13 D5). | Convention is stored and folded; distinct conventions → distinct ids. |
| **D9 ★** | Does Phase 15 add a new numbered data-model invariant (#31)? | (a) Add inv. 31 ("derived analytics are pure consumers of sealed, PIT-eligible results and introduce no new PIT resolution"); (b) rely on existing invariants. | **(a) Add inv. 31** (subject to reviewer approval, since data-model.md is the canonical registry). | Makes the "pure consumer, no new resolution" property a first-class, enforceable invariant future phases inherit, rather than a per-phase convention. | One additive entry to §12 (design-only doc). If the reviewer prefers not to touch the registry, the property still holds via §M/§G and existing invariants 6–17. |
| D10 | Scope of one analytics record: one subject (+optional benchmark), or batch/experiment-wide? | (a) Single subject + optional benchmark; (b) experiment-wide batch. | **(a) Single subject + optional benchmark.** | Minimal, composable, defensible; batch is a loop over (a) and can be a thin future helper. Keeps identity and validation simple. | Experiment-wide analytics deferred; expressible by iterating today. |
| D11 | Skewness/kurtosis definition? | (a) Population moments, excess kurtosis; (b) sample (bias-corrected). | **(a) Population, excess kurtosis.** | Matches `stats.py`'s population volatility choice; deterministic and simplest. Definition folded into the formula version. | Changing to sample moments would bump the formula version. |

---

## X. Open questions requiring approval

1. **D9 — data-model invariant #31.** Approve adding the new invariant to the design-only
   `data-model.md` §12 registry, or keep the property as a per-phase convention? (No code impact
   either way; documentation-registry policy call.)
2. **Benchmark commensurability strictness (D3).** Confirm that requiring subject and benchmark
   to share `schedule_id` *and* equal `period_returns` length (fail-closed otherwise) is the
   desired contract, versus a looser "align by common periods" rule. Recommendation: strict
   equality — looser alignment invites silent mismatch.
3. **Version string reservation.** Confirm `analytics-engine/1` and `analytics-stats/1` as the
   fresh domain/formula tags (no collision with any existing tag was found in the survey).
4. **README Project Status label.** Confirm this ships as **`v0.11.0`** and the "Next" line moves
   to "Multi-factor attribution / richer execution & cost models."

---

## Implementation gate (to be executed only after approval)

**Files to be ADDED** (all under the new `src/quantforge/analytics/` package):
`errors.py`, `identity.py`, `version.py`, `model.py`, `compute.py`, `spec.py`, `result.py`,
`engine.py`, `__init__.py`; and test package `tests/analytics/` (`__init__.py`, `builders.py`,
`test_spec.py`, `test_compute.py`, `test_identity.py`, `test_result.py`, `test_engine.py`).
Docs: `docs/phase15-analytics.md` (and later `docs/phase15-analytics-locked.md`).

**Existing files to be CHANGED** (additive only; no existing identity altered):
1. `src/quantforge/workspace.py` — one `self._analytics_engine = None` cache line + one lazy
   `analytics_engine` `@property` mirroring `experiment_engine`.
2. `src/quantforge/__init__.py` — add `AnalyticsSpecification`, `PerformanceAnalytics` to
   `__all__` (alphabetically) and import them.
3. **On green only:** `docs/index.md`, `ARCHITECTURE.md`, `README.md`.

**Explicitly NOT changed:** `backtest/*` (incl. `stats.py`, `result.py`, `version.py`),
`experiment/*` (incl. `analysis.py`), `report/*`, `factors/store.py`, any identity/version
module of a prior phase.

**Expected tests:** the seven `tests/analytics/` files above, including hand-computed statistic
expectations, fail-closed coverage for every §Q raise, `pin_mismatch` surfacing, write-once
idempotence, and a `TestDeterminism` double-build. Full suite remains green across all phases.

**Expected docs:** narrative + (post-implementation) locked spec; index/architecture/README rows
flipped to ✅ only when all gates pass.

**Expected quality gates:** `uv run pytest` green and deterministic across runs; `uv run ruff
check .` and `uv run ruff format --check .` clean; `uv run mypy src tests` clean (strict); zero
runtime dependencies (stdlib `hashlib`/`json`/`dataclasses`/`Decimal` only); no float in any
path; no wall-clock/RNG in any identity or value; only `<root>/research/` written.

**Invariants that must remain true:** all of §12 (1–30, 22a) unchanged; PIT-only with explicit
`boundary_kind`; no new PIT resolution; no existing record identity changes; write-once
fail-closed persistence; content-addressed determinism; provenance by reference.

**Decisions requiring explicit approval before implementation:** D1–D9 (load-bearing, ★) and the
four open questions in §X.
