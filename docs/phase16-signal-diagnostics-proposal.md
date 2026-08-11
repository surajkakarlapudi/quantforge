# Phase 16 — Cross-Sectional Signal Diagnostics (Design Proposal)

> **Status: PROPOSAL — DESIGN ONLY. Not approved. No code exists.**
> This document is the **sole deliverable** of the Phase 16 design step. It proposes
> *whether and how* QuantForge should build a signal-evaluation (predictive-power)
> layer on the foundations of Phases 1–15. It modifies no production source, adds no
> dependency, writes no code, and creates no locked document. The implementation gate
> (§25) enumerates exactly what would change **if and only if** this design is approved.
>
> Governing prior specs (source of truth): [data-model.md](data-model.md) (invariants
> 1–30, 22a; §KS knowledge-state/revised semantics; §11 identity discipline),
> [phase10-panel-locked.md](phase10-panel-locked.md),
> [phase11-market-data-locked.md](phase11-market-data-locked.md),
> [phase12-backtesting-proposal.md](phase12-backtesting-proposal.md) (BT-1…BT-4),
> [phase15-analytics-locked.md](phase15-analytics-locked.md),
> [ARCHITECTURE.md](../ARCHITECTURE.md) (10 Engineering Principles).

---

## 1. Executive summary

**Selected capability: a cross-sectional *signal diagnostics* layer** — a deterministic,
content-addressed engine that measures whether a fundamental signal has cross-sectional
predictive power over the pinned corpora, *before* a researcher commits to simulating a
full strategy. Given a declarative `SignalDiagnosticsSpecification` (a signal metric, an
explicit fiscal period, a universe specification, an ordered evaluation schedule of
`as_of` instants, a forward-return horizon, and a quantile count), the
`SignalDiagnosticsEngine.evaluate(...)`:

1. resolves the universe **PIT as-of each evaluation date** (Phase 9),
2. reads the signal cross-section **PIT as-of that date** as a `PitPanel` (Phase 10),
3. computes the **realized forward return** of each member over the horizon from Phase 11
   PIT-gated adjusted prices,
4. computes, per date, the **Information Coefficient** (Spearman rank IC and Pearson IC)
   between the as-of-`T` signal and the forward return, plus **quantile-bucket** mean
   forward returns and the **top-minus-bottom spread**,
5. summarises the IC series (mean, dispersion, IC information ratio, hit rate) and
6. seals a content-addressed `SignalDiagnostics` record write-once to the existing Phase 8
   research sidecar.

It composes existing PIT layers exclusively (Phase 9 universe, Phase 10 panel, Phase 11
prices), adds **no runtime dependency, no database, no new store, and no new PIT
resolver**, and follows the established pure-consumer recipe of Phases 13/14/15 verbatim.

**Headline finding: no hard contradiction exists.** The one genuine tension — a diagnostic
deliberately pairs an as-of-`T` signal with a *forward* (post-`T`) realized return — is
resolved honestly by making the result a **distinct forward-looking type that can never be
substituted where a PIT as-of-`T` value is required** (the direct analog of invariant 28,
"`REVISED` is not a PIT source"). Phase 16 introduces four new hard invariants (SD-1…SD-4,
§5) and populates no reserved slot it is not entitled to.

---

## 2. Current-state analysis (what already exists)

Phases 1–15 are implemented. Reading the repository as the source of truth:

- **Phases 1–5** turn acquired SEC bytes into immutable canonical `Fact`s with a
  derived, versioned, fail-closed public-availability timestamp; PIT and REVISED are
  distinct result types (`PitValue`/`RevisedValue`) that cannot be confused (invariants
  27–30). SEC acquisition is real (`SecClient`); market acquisition is a provider-neutral
  seam with only `FakeMarketDataProvider` (synthetic corpora).
- **Phase 7** computes fail-closed, versioned derived metrics (`PitMetricValue`).
- **Phase 8** evaluates a metric across a universe → `PitFactor`, and defines the
  **`ResearchResultStore` sidecar** and the **`ResearchRecord` Protocol**
  (`research_result_id` + `to_dict`), write-once/atomic/fail-closed, one JSON file per
  record at `research/sha256-<hex>.json`.
- **Phase 9** is the deterministic, PIT, content-addressed universe (management +
  `UniverseSpecification` → `UniverseBuilder.build_as_of` → `Universe`).
- **Phase 10** evaluates one metric over a content-addressed period axis in three shapes,
  including `panel_across(metric, universe, axis, as_of)` → `PitPanel` (the cross-sectional
  matrix). Seals a `PanelResearchResult` reusing the Phase 8 sidecar.
- **Phase 11** is the provider-neutral PIT market layer: unadjusted OHLCV +
  first-class corporate actions, served as `PitPrice`/`PitPriceSeries`, with a
  **PIT-gated adjusted view** (`adjusted_series_as_of`).
- **Phase 12** is the deterministic PIT backtester: a **declarative** strategy
  (`signal → rank → select → weight`; v1 is single-signal, `top_n`, equal-weight,
  long-only), engine-owned execution, both corpora pinned & verified (BT-1), fail-closed
  (BT-4), sealed as a content-addressed `BacktestResult`.
- **Phases 13/14/15** are pure consumers strictly *above* Phase 12: experiment sweeps &
  comparison (13), reference-only reports + renderer (14), risk & benchmark-relative
  analytics over a sealed backtest (15). All reuse the same sidecar and the same
  identity discipline.

**The gap.** The research funnel jumps directly from *panel* (a signal cross-section) to
*full strategy backtest*. There is **no way to ask the most basic quant-research question —
"does this signal predict cross-sectional returns at all?"** — without building and running
a complete portfolio simulation, whose result then conflates signal quality with
selection, weighting, costs, and corporate-action accounting. The standard pre-backtest
diagnostic (Information Coefficient + quantile forward-return profile, the "Alphalens"
workflow) is absent. Everything downstream (Phase 12 strategy choice, Phase 13 sweeps,
Phase 15 attribution) would be better-founded if signals could be *evaluated* first.

---

## 3. Why this, after Phase 15

Phase 15 completed the *ex-post* statistics of a **completed strategy** (risk, VaR,
benchmark-relative). It deliberately deferred **multi-factor attribution**, which is
named as a candidate "Next." Studying the repository shows attribution is **blocked by a
missing prerequisite**: multi-factor attribution regresses a return series on *factor
return series*, and QuantForge has no way to produce a factor's return series except by
running a full backtest — and the backtester cannot even express a long/short quantile
("factor-mimicking") portfolio (it is long-only `top_n` equal-weight). So attribution
would require smuggling in either (a) externally-supplied factor returns (no connector
exists; shipping them would risk fabricated financial data, Principle 8) or (b) a
factor-portfolio construction capability. Signal diagnostics is the honest, minimal
prerequisite: it evaluates a signal's predictive power directly and cleanly, and its
quantile-spread machinery is the seed a future factor-portfolio / attribution phase can
build on. Choosing diagnostics now avoids smuggling a prerequisite into an attribution
phase, and it materially increases usefulness to real researchers today — it is the
front-end of the research process, not a convenience.

It composes naturally after Phase 15 because it reuses the *identical* pure-consumer
recipe the codebase has converged on (declarative spec → workspace lazy engine →
pinned-corpus verification → UNDEFINED-preserving Decimal statistics → sealed
`ResearchRecord` → write-once sidecar), so it adds capability without adding architecture.

---

## 4. Alternatives considered and rejected

Each candidate evaluated on: capability · why it matters · what it composes · new
primitives · invariant risk · complexity · research value · unlocks later phases.

| Candidate | Verdict | Reasoning |
|---|---|---|
| **A. Cross-sectional signal diagnostics (IC + quantile spreads)** — *SELECTED* | **CHOSEN** | Composes Phase 9/10/11 only; new primitives are a thin declarative spec + Decimal statistics; **no invariant blocked** (the forward-return tension is resolved by a distinct type, §5); moderate complexity; high research value (the standard pre-backtest diagnostic, entirely absent today); **unlocks** factor-portfolio construction and multi-factor attribution. |
| **B. Multi-factor performance attribution** (Phase 15's explicit deferral) | Rejected (blocked) | Requires factor **return series**, which need either an ingestion connector that does not exist (fabrication risk, Principle 8) or factor-mimicking portfolios the backtester cannot express. Building it now would smuggle in candidate A or a long/short backtest. Deferred until A + a long/short strategy exist. |
| **C. Richer strategy vocabulary** (multi-signal composite, quantile select, long/short, signal-proportional / inverse-vol weighting) | Rejected (for now) | High leverage but is a **Phase 12 v2 extension**, not a new capability; long/short introduces borrow/short-carry accounting that touches the execution model; better sequenced *after* diagnostics prove which signals are worth the richer machinery. A clean additive follow-on (each new step/enum hashes distinctly, per `spec.py`). |
| **D. Richer execution & cost models** (`next_open`, participation limits, slippage/impact, borrow) | Rejected | Increases *realism*, not research *capability*; the Phase 12 `AccountingPolicy`/`CostModel` already reserve the extension seams (new enum values hash distinctly). Convenience-leaning; lower marginal research value than A. |
| **E. Real market-data ingestion connector** | Rejected (out of phase family) | The single largest infrastructure gap, but it is *ingestion/prerequisite* work, not a research layer; ARCHITECTURE marks it Planned; it composes nothing above and would not compose with a research phase. A dedicated infrastructure track, not Phase 16. |
| **F. Sector-neutral / risk-model factor analysis** | Rejected (premature) | A refinement of A (residualising the signal against sectors before IC). Needs A's IC machinery first and a richer classification source; deferred as an A-follow-on. |

---

## 5. Contradiction / invariant analysis (mandated)

Verdicts: **COMPOSES** (Phase 16 consumes the invariant unchanged), **CONSTRAINS** (the
invariant forces a design choice), **TENSION (resolvable)** (a non-obvious interaction
handled explicitly). No row is **HARD CONTRADICTION**.

| # | Existing invariant / principle (source) | Phase 16 touch-point | Verdict | Resolution |
|---|---|---|---|---|
| 1 | **No look-ahead; PIT integrity** (Principle 4; inv. 6, 9, 29) | Signal read at each eval date `T` | **COMPOSES / CONSTRAINS** | The **signal** is read only via `panel_across(..., as_of=T)` → `PitPanel`, so it depends only on data available `≤ T` (inv. 29). No future data ever contaminates the *signal* side (**SD-3**). |
| 2 | **PIT vs REVISED are distinct types; REVISED is not a PIT source** (inv. 27–30; §KS.5) | A diagnostic pairs an as-of-`T` signal with a **forward** realized return | **TENSION (resolvable)** | A forward return is *post-`T`* by construction — it is the evaluation *target*, never fed into a decision. The `SignalDiagnostics` result is therefore a **distinct forward-looking type** that **can never be substituted where a PIT as-of-`T` value is required** (the exact analog of inv. 28). It carries no as-of-`T` reuse semantics; it is an ex-post research statistic (**SD-2**). |
| 3 | **Immutable raw/source data; append-only** (Principle 2; inv. 2, 5) | Reads facts, prices, actions | **COMPOSES** | Strictly read-only over Phases 1–11; writes only its own content-addressed sidecar record. Rewrites no `Fact`, `PriceObservation`, or `CorporateAction`. |
| 4 | **Deterministic, content-addressed identity** (Principle 5; §11 `sha256:`, `_SEP="\x00"`, canonical JSON) | `diagnostics_id`, `diagnostics_result_hash` | **COMPOSES / CONSTRAINS** | Same id family as every prior layer, fresh domain tag `diagnostics/1` (§9). |
| 5 | **Fail-closed availability; UNKNOWN never eligible** (inv. 9, 12) | Undefined signal / missing forward price | **COMPOSES / CONSTRAINS** | A member lacking a PIT signal at `T` or a computable forward return is **excluded from that date's pair set and recorded in coverage** — never imputed, never zero-filled (**SD-4**). |
| 6 | **Corpus pin for reproducibility over an append-only store** (BT-1; `DatasetVersion`/`MarketDatasetVersion`) | PIT-as-of over a growing corpus is unstable unless pinned | **TENSION (resolvable)** | Diagnostics reads **both** corpora, so it records and **re-verifies** the fundamentals `dataset_version_id` and market `market_dataset_version_id`; a mismatch fails closed and a different corpus yields a different `diagnostics_id` (**SD-1**, the BT-1 analog). |
| 7 | **PIT eligibility predicate** (§6.1; status ∈ {verified,derived} ∧ ts ≤ as_of) | Every read | **COMPOSES** | Inherited unchanged through the existing `*_as_of` accessors; the engine adds no eligibility logic. |
| 8 | **Total-order selection determinism** (§6.3; inv. 16) | Which vintage the signal sees at `T` | **COMPOSES** | Inherited unchanged; the engine never re-ranks observations. |
| 9 | **Adjusted prices are a PIT-gated derived view, never book value** (Phase 11) | Forward return needs split/dividend consistency | **COMPOSES / CONSTRAINS** | Forward return uses `adjusted_series_as_of` (only actions available at the window-end `as_of` are applied). No revised or future adjustment can leak in. |
| 10 | **Security identity; ticker is never identity** (inv. 11) | Pairing signals to price returns | **COMPOSES / CONSTRAINS** | Members keyed by `security_id`; the signal (per-filer `company_id`/CIK) maps to `security_id` exactly as Phase 12 does. |
| 11 | **`PeriodAxis` = accounting; `PriceAxis` = trading dates; `RebalanceSchedule` = as_of instants** | Evaluation dates | **COMPOSES** | Evaluation dates reuse the Phase 12 `RebalanceSchedule` (content-addressed `as_of` axis); the signal's fiscal period is an explicit `MetricPeriod` (as in Phase 12's signal step). No new axis type. |
| 12 | **UNDEFINED is first-class, never NaN/Inf/exception** (Phase 7/10/15) | Undefinable IC / bucket cells | **COMPOSES** | Reuses the Phase 15 `StatValue`(KNOWN/UNDEFINED + reason) discipline verbatim. A date with `< 2` valid pairs → IC `UNDEFINED(INSUFFICIENT_PAIRS)`; an empty bucket → `UNDEFINED`. |
| 13 | **`ResearchResult` sidecar & Protocol** (§9; `factors/store.py`) | Where the result lives | **COMPOSES** | `SignalDiagnostics` satisfies `ResearchRecord`; reuses `ResearchResultStore` write-once, no new store (Phase 10/13/14/15 precedent). |
| 14 | **No database; zero runtime dependencies** (Principle 10) | Statistics, persistence | **COMPOSES / CONSTRAINS** | All arithmetic in stdlib `Decimal` (rank IC, Pearson IC, quantiles, `.sqrt()`); persistence via the existing sidecar. No numpy/pandas, no DuckDB. |
| 15 | **No wall-clock / RNG in values or ids** (Principle 5; inv. 13, 21) | Determinism | **COMPOSES** | All time flows from the declared schedule; no randomness (nearest-rank/average-rank are deterministic). |
| 16 | **No fabricated financial data; synthetic-only tests** (Principle 8) | Test corpus | **COMPOSES** | Reuses the Phase 12/15 synthetic builders (fictional CIKs, `FakeMarketDataProvider`). No bundled real data. |
| 17 | **`strategy_version` reservation** (§9) | Does Phase 16 touch it? | **COMPOSES** | Diagnostics evaluates a *signal*, not a strategy; it does **not** touch `strategy_version`. It defines its own `signal_diagnostics_engine_version_id`. |
| 18 | **Additive composition; thin public API over an explicit engine** (project discipline) | Engine placement | **COMPOSES / CONSTRAINS** | Workspace-level `signal_diagnostics_engine` lazy property (annotated `-> object`), mirroring `panel_engine`/`analytics_engine`. `Company` gains nothing. |
| 19 | **Change-control on temporal/identity/invariant rules** (data-model closing clause) | New invariants SD-1…SD-4 | **CONSTRAINS** | SD-1…SD-4 are *additive* to §12 and do not weaken 1–30; they are documented here and (on approval) folded into `data-model.md` **before** implementation. |

**Conclusion.** Phase 16 is a clean additive composition. The single real tension (row 2)
is the crux and is resolved by the same discipline the whole project already relies on:
a value that "knows the future" is a **distinct type inadmissible as a PIT input**. No
Phase 1–15 invariant is weakened.

---

## 6. Architecture

- **A pure-consumer layer, parallel to Phase 12, above Phases 9/10/11.** It is the
  *diagnostic sibling* of the backtester: where Phase 12 *simulates* a strategy,
  Phase 16 *evaluates* a signal. Both sit above panel/market; neither depends on the
  other. Phase 16 does **not** consume `BacktestResult`s (unlike 13/14/15).
- **Read-only composition.** It calls Phase 9 `UniverseBuilder.build_as_of`, Phase 10
  `PanelEngine.panel_across`, and Phase 11 `PriceEngine.adjusted_series_as_of` /
  `price_as_of` through their existing public `*_as_of` accessors. It adds no parallel
  data path and edits no prior store.
- **Workspace-hosted engine** (`workspace.signal_diagnostics_engine`), lazily constructed
  like every other engine (import-in-body to avoid the load-time cycle).
- **Zero new runtime dependencies**; stdlib `Decimal` under the pinned context only.
- **New package** `src/quantforge/diagnostics/` mirroring the `analytics/` module layout
  (`spec`, `model`, `compute`, `engine`, `result`, `identity`, `version`, `__init__`).

Build flow (`evaluate(spec)`):

1. **Verify corpus pins (SD-1):** re-derive and assert the fundamentals + market
   `DatasetVersion`/`MarketDatasetVersion` match the spec's pins; mismatch fails closed.
2. **For each evaluation `as_of` `T` in the schedule (in order):** resolve the universe
   PIT as-of `T`; read the signal cross-section `panel_across(metric, universe, [period],
   as_of=T)`; for each member compute the forward return over `[T, T+horizon]` from
   PIT-gated adjusted prices; drop members lacking a PIT signal or a computable forward
   return (record in coverage); compute that date's rank IC, Pearson IC, and quantile
   bucket means + top-minus-bottom spread.
3. **Summarise** the per-date IC series (mean, population std, IC information ratio, t-stat,
   hit rate) and the mean quantile profile, UNDEFINED-preserving.
4. **Seal** into `SignalDiagnostics` (its `result_hash` folds the answer) and **persist**
   write-once to the shared sidecar (idempotent no-op on identical rebuild).

---

## 7. Data model

All monetary/statistic fields are canonical decimal strings; no float, no wall-clock.

- **`SignalDiagnosticsSpecification`** (frozen, content-addressed): `name`, `signal`
  (Phase 7 `metric_key`), `period` (`MetricPeriod`, explicit — never inferred),
  `universe` (`UniverseSpecification`), `schedule` (`RebalanceSchedule` of eval `as_of`
  instants), `forward_horizon` (a declared trading-day count or calendar step),
  `quantiles` (int `q ≥ 2`), `ic_methods` (closed set: `{"spearman","pearson"}`),
  `dataset_version_id`, `market_dataset_version_id`.
- **`ICMethod`** — closed enum (`spearman`, `pearson`).
- **`StatValue`** — reused pattern from `analytics/model.py`: `KNOWN(value_str)` or
  `UNDEFINED(reason)`.
- **`DiagnosticUndefinedReason`** — closed enum: `INSUFFICIENT_PAIRS`, `ZERO_SIGNAL_VARIANCE`,
  `ZERO_RETURN_VARIANCE`, `EMPTY_BUCKET`, `NO_VALID_DATES`.
- **`PerDateIC`** — one evaluation date: `as_of`, `n_pairs`, `spearman_ic` (`StatValue`),
  `pearson_ic` (`StatValue`), the `q` bucket mean forward returns, `top_minus_bottom_spread`.
- **`QuantileProfile`** — the across-date mean forward return per bucket (`q` cells) + mean
  spread, each a `StatValue`.
- **`ICSummary`** — `mean_ic`, `ic_std`, `ic_information_ratio` (mean/std·√n or per §J), 
  `ic_t_stat`, `hit_rate` (fraction of dates with positive IC), per method — each `StatValue`.
- **`CoverageSummary`** — per-date and total counts of eligible members, dropped-for-signal,
  dropped-for-return — so exclusions are auditable, never silent.
- **`SignalDiagnostics`** (the sealed `ResearchRecord`): `diagnostics_id`, `result_hash`,
  `signal_diagnostics_engine_version_id`, the declared spec, `boundary_kind = "pit"`
  (signal side), both corpus pins, `per_date` ledger, `quantile_profile`, `ic_summary`,
  `coverage`, `formula_version`. `research_result_id` aliases `diagnostics_id`.

---

## 8. Public API

```python
from quantforge import Workspace, SignalDiagnosticsSpecification
from quantforge.backtest import RebalanceSchedule  # reused as the eval axis
from quantforge.metrics import MetricPeriod
from quantforge.xbrl.contexts import PeriodType

ws = Workspace.open()
spec = SignalDiagnosticsSpecification(
    name="current-ratio-ic",
    signal="current_ratio",
    period=MetricPeriod(period_type=PeriodType.INSTANT, period_end="2022-12-31"),
    universe=universe_spec,
    schedule=RebalanceSchedule.month_end_closes("2018-01-31", "2022-12-31"),
    forward_horizon="21d",  # one trading month forward
    quantiles=5,
    ic_methods=("spearman", "pearson"),
    dataset_version_id=...,
    market_dataset_version_id=...,
)
diag = ws.signal_diagnostics_engine.evaluate(spec)  # -> SignalDiagnostics (sealed)
diag.ic_summary  # mean IC, IR, t-stat, hit rate (per method)
diag.quantile_profile  # mean forward return per bucket + spread
diag.research_result_id  # == diag.diagnostics_id (ResearchRecord)
```

Top-level re-exports mirror the existing pattern: `SignalDiagnosticsSpecification` and
`SignalDiagnostics` from `quantforge`; the engine reached via `Workspace` (not exported).

---

## 9. Identity / content-addressing

Reuses the §11 discipline verbatim (`sha256:` prefix, `_SEP="\x00"` NUL-join, canonical
JSON `sort_keys=True, ensure_ascii=False, separators=(",",":")`), with a fresh domain tag
`diagnostics/1`. No wall-clock, RNG, or `id()`.

- **What is hashed into `diagnostics_result_hash`:** the ordered computed output cells —
  the per-date IC cells, the quantile profile cells, and the IC summary cells, each reduced
  to a canonical `(scope, key, method, status, value)` dict, in stored order. Sensitive to
  every computed statistic (a single differing cell changes it).
- **What is hashed into `diagnostics_id`:** `diagnostics/1`,
  `signal_diagnostics_engine_version_id`, the declared spec identity (name, spec version,
  signal, canonical `period`, universe `specification_id`, `schedule_id`, forward horizon,
  quantiles, sorted `ic_methods`), **both corpus pins** (`dataset_version_id`,
  `market_dataset_version_id`), and `diagnostics_result_hash`.
- **What is NOT hashed:** presentation, any renderer output, schema/format version, and
  time.
- **How referenced artifacts are represented:** Phase 16 reads *raw corpora*, not sealed
  research artifacts, so it references them by **corpus pin** (not by a `result_hash` the
  way Phase 15 references a sealed backtest). The pins are content-addressed
  `DatasetVersion` ids, so the id remains sensitive to any corpus change.
- **Engine/version sensitivity:** `signal_diagnostics_engine_version_id` lives on
  `SignalDiagnosticsEngineVersion` (single source of truth) and folds the pinned decimal
  context + formula-method version; a change to either bumps every id, exactly as
  `AnalyticsEngineVersion`/`BacktestEngineVersion` do.
- **Reproducibility:** same spec + same pinned corpora ⇒ byte-identical
  `diagnostics_id`/`result_hash` on any machine.

No new identity scheme is introduced — an existing one is composed with a fresh tag.

---

## 10. Versioning

- `SignalDiagnosticsEngineVersion` folds `code_version`, the pinned `decimal_context`
  (precision 34, `ROUND_HALF_EVEN`), and `formula_version` (`diagnostics-stats/1`) into
  `signal_diagnostics_engine_version_id`, mirroring `AnalyticsEngineVersion`. Changing a
  formula (IC definition, tie rule, bucketing rule) or the decimal context bumps the id.
- **Extensibility discipline:** a new IC method, a new bucketing rule, or a new horizon
  representation is a **new enum value / new spec field** that hashes distinctly — never an
  edit that changes an already-computed `diagnostics_id`.

---

## 11. PIT semantics (the crux)

- **Signal side is strictly PIT (SD-3).** The signal cross-section at each evaluation date
  `T` is read via `panel_across(..., as_of=T)`, so it uses only data available `≤ T`
  (invariant 29). No future data ever enters the signal.
- **Forward-return side is the evaluation target, not a PIT input.** The realized return
  over `[T, T+horizon]` is, by definition, information from *after* `T`. It is used only to
  *score* the as-of-`T` signal; it is **never** an input to any decision and is **never**
  reusable as an as-of-`T` value.
- **The result is a distinct forward-looking type (SD-2).** `SignalDiagnostics` is an
  ex-post research statistic. Just as invariant 28 forbids a `REVISED` value from feeding a
  PIT-as-of-`T` computation, a `SignalDiagnostics` (which incorporates realized forward
  returns) is **inadmissible where a PIT signal/value is required** — it is not a `Pit*`
  type and exposes no as-of-`T` accessor. Its `boundary_kind = "pit"` documents that the
  *signal* was PIT-eligible; it does **not** claim the diagnostic is a PIT value.
- **Forward-return determinism.** Prices for `T` and `T+horizon` are read via the Phase 11
  PIT-gated adjusted view at the **window-end `as_of`** (`T+horizon`), so both endpoints are
  eligible and only corporate actions available by the window end are applied — pinned via
  `market_dataset_version_id`, reproducible, no revision leak.

---

## 12. Provenance

For every evaluation date the ledger records: the `as_of` `T`; the resolved universe
identity; the number of eligible pairs and the coverage breakdown (dropped-for-signal,
dropped-for-return); the per-date IC cells and bucket means. The `SignalDiagnostics`
records both corpus pins, the engine/formula version, and the full declared spec, and
seals the answer with `result_hash`. Because the signal is a `panel_across` result, the
diagnostic traces back to the same PIT panel machinery (and thence to canonical facts and
availability evidence). No copied financial values beyond the computed statistics; the
diagnostic references corpora by pin.

---

## 13. Error / fail-closed behavior

- **Missing/mismatched corpus pin** → `SignalDiagnosticsConsistencyError` (SD-1).
- **Malformed spec** (unknown IC method, `quantiles < 2`, non-`MetricPeriod` period,
  empty schedule, malformed horizon) → `SignalDiagnosticsConfigurationError` at
  construction, exactly as Phase 12/15 refuse a misconfigured request.
- **No valid evaluation dates** (every date has `< 2` eligible pairs) → a configuration
  defect is raised rather than sealing an all-UNDEFINED record (the Phase 15 `_MIN_PERIODS`
  precedent).
- **Corrupt/non-finite decimal from the corpus** → raised, never guessed.

---

## 14. Undefined / missing-data semantics (SD-4)

- A member with an **UNDEFINED signal** at `T` (Phase 7/10 UNDEFINED) is **excluded** from
  that date's pair set and counted in coverage — never imputed.
- A member with **no computable forward return** (missing/UNKNOWN price at either endpoint,
  or a delisting inside the window with no recovery price) is **excluded** and counted —
  never zero-filled.
- A date with `< 2` valid pairs → that date's IC is `UNDEFINED(INSUFFICIENT_PAIRS)`; it
  contributes no IC to the summary.
- Zero signal variance at a date → `UNDEFINED(ZERO_SIGNAL_VARIANCE)`; zero return variance
  → `UNDEFINED(ZERO_RETURN_VARIANCE)` (Pearson only; Spearman uses ranks). An empty quantile
  bucket → `UNDEFINED(EMPTY_BUCKET)`. Never a divide-by-zero, `NaN`, or `Inf`.

---

## 15. Storage / sidecar

Content-addressed JSON via the existing `ResearchResultStore` (`research/sha256-<hex>.json`),
reused through the `ResearchRecord` Protocol (`research_result_id` + `to_dict`). Write-once,
atomic (temp + `fsync` + `os.replace`), fail-closed: a differing payload under an existing
id raises `FactorConsistencyError`. **No new store, no database.** Byte-identical
round-trip via a `from_dict` inverse (Phase 13 D3 discipline).

---

## 16. Workspace composition

Add one lazy cached property, mirroring `analytics_engine` exactly:

```python
@property
def signal_diagnostics_engine(self) -> object:
    if self._signal_diagnostics_engine is None:
        from quantforge.diagnostics.engine import SignalDiagnosticsEngine

        self._signal_diagnostics_engine = SignalDiagnosticsEngine(self)
    return self._signal_diagnostics_engine
```

The engine reuses the workspace's Phase 9 universe builder / Phase 10 panel engine /
Phase 11 price engine and the shared Phase 8 sidecar — it constructs no new store.

---

## 17. Interaction with existing phases

- **Phase 9/10/11:** consumed read-only through public `*_as_of` accessors (universe,
  panel, adjusted prices). No change to any of them.
- **Phase 12:** *not* consumed. Phase 16 is parallel (the diagnostic sibling). It reuses
  the `RebalanceSchedule` type only. No `BacktestResult` involvement.
- **Phase 13/14/15:** independent. A future report/experiment layer *could* reference a
  `SignalDiagnostics` id (it is a `ResearchRecord`), but Phase 16 requires no change to
  13/14/15. No existing record's identity changes.

---

## 18. Future-phase handoff

Phase 16 seals a stable, content-addressed `SignalDiagnostics`. It opens clean seams for:

- **Long/short quantile ("factor-mimicking") portfolios** — the top-minus-bottom construction
  becomes a strategy the (extended) backtester can simulate, producing a factor return
  series.
- **Multi-factor attribution** (Phase 15's deferral) — once factor return series exist as
  sealed backtests, attribution regresses a strategy on them (the closed-form single-factor
  OLS in `analytics/compute.py` generalises).
- **Sector-neutral / risk-model IC** — residualise the signal before IC (candidate F).
- **Signal-decay curves** — the same machinery over multiple horizons.

None of these is smuggled into Phase 16; each is a distinct additive phase.

---

## 19. Testing strategy (designed before implementation)

Pure offline/synthetic (Principle 8), reusing the `tests/backtest/builders.populate`
corpus + `FakeMarketDataProvider` + fictional CIKs `9999999991/2`; a new
`tests/diagnostics/` subpackage with `builders.py` and the per-phase file convention
(`test_spec.py`, `test_compute.py`, `test_engine.py`, `test_identity.py`, `test_result.py`).

- **Determinism / golden:** same spec over the same corpus → byte-identical
  `diagnostics_id`/`result_hash`.
- **Identity sensitivity:** `diagnostics_id` changes iff the signal, period, universe,
  schedule, horizon, quantiles, IC methods, engine version, either corpus pin, or the
  computed answer changes; confidence/method **order** does not matter (only content).
- **Round-trip serialization:** `from_dict(to_dict(r))` re-emits identical bytes and the
  same `result_hash`.
- **Persistence:** write-once idempotent no-op on identical rebuild; `FactorConsistencyError`
  on a differing payload under the same id.
- **PIT correctness / look-ahead prevention:** a signal made available only *after* `T` is
  excluded at `T` (SD-3); a red-team test asserts the signal side never sees post-`T` data.
- **Forward-return honesty:** the diagnostic incorporates realized forward returns *by
  design*; a test asserts `SignalDiagnostics` exposes **no** `Pit*`/as-of accessor and is
  not accepted anywhere a PIT value is required (SD-2 — type/API boundary).
- **Corpus pin (SD-1):** a mismatched pin fails closed; a different corpus yields a
  different `diagnostics_id`.
- **Fail-closed / undefined (SD-4):** UNDEFINED signal excluded + counted; missing forward
  price excluded + counted; `< 2` pairs → `INSUFFICIENT_PAIRS`; zero variance →
  the right reason; empty bucket → `EMPTY_BUCKET`; no valid dates → config error.
- **Statistics correctness:** rank IC, Pearson IC, quantile means, and top-minus-bottom
  spread verified against hand-computed values on a tiny synthetic cross-section; average-
  rank tie handling verified deterministic.
- **Interaction:** reuses Phase 9/10/11 engines unchanged; no Phase 1–15 test regresses.

No real financial or network data; the architecture does not require it.

---

## 20. Quality gates (unchanged from prior phases)

`uv run pytest` (all green) · `uv run ruff check` · `uv run ruff format --check` ·
`uv run mypy` (strict, src + tests). No commit/push/release as part of the implementation
step.

---

## 21. Files added / changed (if approved)

**Added — `src/quantforge/diagnostics/`:**
- `__init__.py` — package exports.
- `spec.py` — `SignalDiagnosticsSpecification`, `ICMethod`; validation + `spec_id`.
- `model.py` — `StatValue`, `DiagnosticUndefinedReason`, `PerDateIC`, `QuantileProfile`,
  `ICSummary`, `CoverageSummary`, closed key sets.
- `compute.py` — pure Decimal functions: `rank_ic`, `pearson_ic`, `quantile_buckets`,
  `top_minus_bottom`, `ic_summary`, `forward_return`.
- `engine.py` — `SignalDiagnosticsEngine.evaluate(spec)`.
- `result.py` — `SignalDiagnostics` (`ResearchRecord`) + nested records + `from_dict`.
- `identity.py` — `diagnostics_id`, `diagnostics_result_hash`.
- `version.py` — `SignalDiagnosticsEngineVersion`.
- `errors.py` — `SignalDiagnosticsConfigurationError`, `SignalDiagnosticsConsistencyError`.

**Changed (additive only):**
- `src/quantforge/workspace.py` — add `_signal_diagnostics_engine` cache +
  `signal_diagnostics_engine` lazy property.
- `src/quantforge/__init__.py` — re-export `SignalDiagnosticsSpecification`,
  `SignalDiagnostics`.
- `docs/index.md`, `ARCHITECTURE.md`, `README.md` — register Phase 16 (status, version
  bump) **on completion**, not before. **Not touched in the implementation step's first
  pass beyond the locked doc.**

**Added docs (on approval → implementation):** `docs/phase16-signal-diagnostics-locked.md`
(the normative spec). **Not created by this design step.**

---

## 22. Explicitly out of scope (v1)

Multi-factor attribution; factor-mimicking / long-short portfolio *construction*;
sector-neutral or risk-model-residualised IC; signal-decay curves across many horizons
(v1 is a single declared horizon); Fama-MacBeth cross-sectional regression; turnover/decay
of the signal itself; any consumption of `BacktestResult`; any new market-data ingestion;
any UI. Each is a distinct future phase; none is needed to make v1 correct, reproducible,
and useful.

---

## 23. Approval-gated decisions

| ID | Decision | Question | Options | Recommendation | Reason | Consequence |
|---|---|---|---|---|---|---|
| **D1 ★** | Capability | What is the highest-value Phase 16? | A diagnostics · B attribution · C richer strategy · D exec/costs · E ingestion · F sector-neutral | **A — signal diagnostics** | Fills the absent pre-backtest signal-evaluation step; composes 9/10/11 only; unblocks B/C/F | New pure-consumer layer |
| **D2** | Placement | Where does the engine live? | Company method · workspace engine · standalone | **Workspace-level `signal_diagnostics_engine`** | Cross-sectional, matches `panel`/`analytics` placement | New lazy property; no `Company` change |
| **D3** | Signal source | New fundamental path or reuse? | New path · reuse `panel_across` | **Reuse Phase 10 `panel_across`** | No second fundamental-data path; inherits PIT/UNDEFINED | Depends on Phase 10 API |
| **D4** | Forward return | How is it built? | Unadjusted spot · **PIT-gated adjusted view** at window-end `as_of` | **Adjusted view (Phase 11)** | Split/dividend consistency without revision leak | Pins `market_dataset_version_id` |
| **D5 ★** | PIT honesty | How to reconcile as-of-`T` signal with post-`T` return? | Treat as PIT value · **distinct forward-looking type, inadmissible as a PIT input** | **Distinct type (SD-2)** | Analog of invariant 28; prevents look-ahead reuse | Result is not a `Pit*` type; no as-of accessor |
| **D6** | IC definition | Which IC + tie rule? | Spearman only · Pearson only · **both**; average-rank ties; population moments | **Both; average-rank; population moments (match `analytics/stats`)** | Standard practice; matches existing Decimal conventions | Folded into `formula_version` |
| **D7** | Quantiles | How to bucket? | Fixed `q` by rank, deterministic boundary/tie rule; top-minus-bottom spread | **Fixed `q ≥ 2`, deterministic** | Standard portfolio-sort diagnostic; reproducible | `quantiles` folded into id |
| **D8 ★** | Corpus pin | Pin corpora? | Accept drift · **pin + verify both** | **Pin + verify (SD-1, BT-1 analog)** | PIT-as-of over an append-only store is unstable unless pinned | Both pins fold into `diagnostics_id` |
| **D9 ★** | Identity | Reference corpora how? | New scheme · reuse §11 with corpus pins | **Reuse §11 + corpus pins + answer** | Reads raw corpora, not sealed artifacts; pins are content-addressed | `diagnostics_id` sensitive to any corpus/answer change |
| **D10** | Persistence | New store or reuse? | New store · reuse `ResearchResultStore` | **Reuse sidecar via `ResearchRecord`** | Protocol designed for this; no DB | `SignalDiagnostics` implements the Protocol |
| **D11** | Undefined | How handled? | Impute · **first-class UNDEFINED + coverage** | **UNDEFINED-preserving (SD-4)** | Fail-closed; no fabrication | Reuses Phase 15 `StatValue` |

★ = load-bearing / requires explicit approval.

**New hard invariants Phase 16 would introduce** (additive to §12; folded into
`data-model.md` before implementation, per its change-control clause):
- **SD-1 (corpus pin):** a reproducible diagnostic records and, on re-run, verifies both
  the fundamentals `dataset_version_id` and market `market_dataset_version_id`; a mismatch
  fails closed and a changed corpus yields a different `diagnostics_id`.
- **SD-2 (forward-looking diagnostic is not a PIT value):** a `SignalDiagnostics`
  incorporates realized forward returns and can never be substituted where a PIT as-of-`T`
  value/signal is required; it exposes no `Pit*` type and no as-of accessor.
- **SD-3 (signal PIT-eligibility):** the signal at each evaluation date `T` is read
  PIT-eligible-at-`T`; no post-`T` data contaminates the signal side.
- **SD-4 (fail-closed pairing):** a member lacking a PIT signal at `T` or a computable
  forward return is excluded and recorded in coverage; never imputed.

---

## 24. Open questions requiring approval

1. **Horizon representation.** Trading-day count (`"21d"` via a `PriceAxis`) vs a calendar
   step vs a count of schedule steps? (Affects D4; recommend trading-day count over the
   Phase 11 `PriceAxis` so it is corporate-calendar aware.)
2. **IC information-ratio convention.** `mean_ic / ic_std` (per period) vs annualised by
   `√(periods_per_year)`? (Recommend per-period IR + a separate t-stat `mean/std·√n`, no
   annualisation, since evaluation dates need not be uniformly spaced.)
3. **Signal period vs evaluation date.** v1 fixes one explicit `MetricPeriod` for the whole
   study (simple, honest). Should the period instead track each `T` (e.g. "most recent
   annual as-of `T`")? (Recommend fixed explicit period for v1; per-`T` period selection is
   a documented follow-on to avoid smuggling a period-resolution rule in now.)
4. **Bucket boundary/tie rule.** Exact rank-to-bucket assignment on ties and non-divisible
   counts (recommend deterministic average-rank + floor-based bucketing, documented).
5. **Version numbering.** README labels Phase 15 as `v0.11.0`; the Phase 16 kickoff framing
   referenced a different mapping. Phase 16 would be the next bump (`v0.12.0` on the README's
   scheme) — reconcile at completion.

---

## 25. Implementation gate

Nothing above is built until this proposal is approved. On approval, implementation would:
create `src/quantforge/diagnostics/` (§21), add the workspace property and top-level
re-exports (§16, §21), author `docs/phase16-signal-diagnostics-locked.md`, fold SD-1…SD-4
into `data-model.md`, and (on completion only) register Phase 16 in `docs/index.md` /
`ARCHITECTURE.md` / `README.md` with a version bump. All quality gates (§20) must be green.
No commit, push, or release is part of this design step or the subsequent implementation
step unless separately authorised.
