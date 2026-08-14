# Phase 31 Proposal — Net-of-Cost Walk-Forward Performance (Transaction-Cost & Break-Even Implementability)

**Status: DESIGN ONLY — PROPOSAL. Nothing described here is implemented.**
No source, test, README, ARCHITECTURE, `docs/index.md`, or `docs/data-model.md` file has been
created or modified by this document. This is a capability-frontier investigation and a design
proposal awaiting approval. Implementation is explicitly out of scope and is flagged as such in
every section (see **§18 DESIGN ONLY vs IMPLEMENTATION**).

- **Proposed version:** `v0.28.0`
- **Proposed capability class:** *economic implementability* — the first monetary consumer of the
  Phase 27 turnover leaf; completes the implementability lens that Phase 27 opened as its
  "honest cost-free precursor."
- **Repository state at time of writing:** `HEAD = dab6cbf` (Phase 30, `v0.27.0`). Phases 1–30
  are committed and locked. The next honest phase is **Phase 31** (not Phase 28 — Phase 28
  "Minimum Track-Record Length" shipped at `v0.25.0`, commit `975386e`).

---

## 0. Scope of the investigation

Per the mandate, this proposal is preceded by a repository-wide read: all source packages, the
sealed-artifact/consumer graph, the shared numerical primitives, `README.md`, `ARCHITECTURE.md`,
`docs/index.md`, `docs/data-model.md`, `docs/canonicalization.md`, every Phase 19–30
proposal/locked document, git history, and current tags. Sections §1–§8 record the findings that
constrain the design; §9 onward is the proposal proper.

The existing architecture and invariants are treated as **binding**. A candidate is rejected the
moment it would violate exact-`Decimal` determinism, introduce RNG / floating point / wall-clock
dependence, cross a PIT boundary, break content-addressed identity or write-once persistence,
require a second store, fabricate an expected return / price / benchmark, add unnecessary
ingestion, or add an unnecessary numerical primitive.

---

## 1. Current architecture map (as of v0.27.0 / Phase 30)

Main package: `src/quantforge/` (src layout, zero runtime dependencies). Two strata:

**Data & PIT foundation (Phases 1–11).** `sec/` (content-addressed EDGAR acquisition;
`sha256_hex` lives in `sec/artifacts.py`) → `registry/` (filing identity/provenance) → `xbrl/`
(immutable `RawFact`) → `canonical/` (deterministic `Fact`) → `availability/` (Phase 5 public
availability, PIT/REVISED resolution) → `identity/`, `company.py`, `metrics/` (Phase 7 PIT
metrics) → `factors/` (Phase 8 `ResearchResult` **plus the single shared `ResearchResultStore`**
and the `ResearchRecord` protocol in `factors/store.py`) → `universe/` (Phase 9) → `panel/`
(Phase 10) → `market/` (Phase 11 PIT market data, added *beneath* the stack).

**Research / analytics layers (Phases 12–30).** Each is a sibling package with the same shape —
`spec.py` + `engine.py` + `result.py` + `compute.py`/`model.py` + `identity.py` + `version.py`:
`backtest/` (12), `experiment/` (13), `report/` (14), `analytics/` (15), `diagnostics/` (16),
`attribution/` (17), `crosssection/` (18), `factorportfolio/` (19), `factorrisk/` (20),
`optimization/` (21), `walkforward/` (22), `campaign/` (23), `comparison/` (24), `multiplicity/`
(25), `calibration/` (26), `stability/` (27), `mintrl/` (28), `calsig/` (29), `campaignmult/`
(30). A `Workspace` facade (`workspace.py`) exposes every engine as a property.

**Shared internal primitives (deliberately minimal):**
- `_linalg/decimal_ols.py` — exact-`Decimal` `ldl`, `ldl_solve`, `inverse_diagonal` (positive-
  definite only; returns `None` on a non-PD pivot). Used by GMV (21), attribution (17), OLS (18).
- `_stats/normal.py` — exact-`Decimal` `standard_normal_cdf` (Φ via an all-positive-term `erf`
  series) and `standard_normal_ppf` (Z⁻¹ via fixed-iteration monotone bisection). Introduced
  phase-local in Phase 23, extracted verbatim to `_stats` in Phase 24.

Mean/variance/std are **not** shared — each phase defines its own exact-`Decimal`,
population-convention moment helper (`analytics/compute.py`, `factorportfolio/stats.py`,
`campaign/moments.py`, …). `Decimal.sqrt` is the only transcendental in most phases.

**The store.** `factors/store.py :: ResearchResultStore` — one JSON file per result at
`<root>/research/sha256-<hex>.json`; envelope
`{"research_result_format_version": 1, "research_result": <record.to_dict()>}`;
`json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)`. Write-once is enforced by
byte-comparison: an identical payload under an existing id is an idempotent no-op; any *differing*
payload under the same id raises `FactorConsistencyError`. Writes are atomic (temp +
`flush`/`fsync` + `os.replace`). The record id is a re-derived `@property`, never read from stored
state, so a tampered stored id is ignored. There is exactly one store; no database anywhere.

---

## 2. Terminal artifacts and reserved-but-unconsumed payloads

The design idiom since Phase 20 is: a sibling package consumes *exactly one* (occasionally N
ordered) already-sealed artifact by id, seals a new `ResearchRecord`, and edits no prior phase.
The narration is "first consumer of a terminal leaf / reserved payload."

**Producer → consumer edges (verified by `store.read_as(...)` in each `engine.py`):**

```
FactorPortfolio(19) → FactorRiskModel(20) → PortfolioOptimization(21) → WalkForwardEvaluation(22)
WalkForwardEvaluation(22) ─┬→ ResearchCampaignEvaluation(23) ─┬→ MinimumTrackRecordLength(28)   [trial moments]
                           │                                  └→ CampaignMultiplicityCorrection(30) [trial psr]
                           ├→ StrategyComparison(24) → MultipleComparisonCorrection(25)          [pairwise p]
                           ├→ RiskForecastCalibration(26) → CalibrationSignificance(29)          [calib summary]
                           └→ WalkForwardStability(27)                                            [per-window weights]
BacktestResult(12) ─┬→ PerformanceAnalytics(15)  ├→ FactorAttribution(17)  └→ ResearchReport(14) ← ExperimentResult(13)
```

**TERMINAL sealed artifacts (no downstream consumer today):**
`MultipleComparisonCorrection` (25), `WalkForwardStability` (27), `MinimumTrackRecordLength` (28),
`CalibrationSignificance` (29), `CampaignMultiplicityCorrection` (30); plus the older parallel
leaves `ResearchReport` (14), `PerformanceAnalytics` (15), `SignalDiagnostics` (16),
`FactorAttribution` (17), `CrossSectionalRegression` (18).

**Reserved-but-consumed payloads (for reference — the pattern this phase follows):**
Phase 22 reserved per-window `predicted/realized variance` (consumed by 26) and per-window GMV
`weights` (consumed by 27). Phase 23 reserved the per-trial moment block (consumed by 28) and the
per-trial `psr` block (consumed by 30).

**Reserved-but-still-unconsumed data-model fields (out of scope here, noted for completeness):**
`security_id`, `fiscal_year`/`fiscal_quarter` (canonicalization §9), and
`amendment_link_confidence = SOURCE_ASSERTED` are reserved positional/identity slots — they are
ingestion-layer concerns, not research-layer capabilities, and do not bear on Phase 31.

**Structural observation.** No phase today consumes *two different sealed artifact types
together*; every consumer reads one source (occasionally re-resolving that source's own
`source_ref` transitively). The strongest unclaimed economic signal is that **Phase 27's turnover
leaf is terminal and was explicitly designed to be consumed by a cost model** (§3).

---

## 3. Capabilities explicitly deferred by Phases 19–30 (consolidated)

De-duplicated across all twelve proposal/locked documents, grouped and annotated with
architecture-honesty:

**A. Selection-bias / multiplicity.** Campaign multiplicity → *shipped (30)*. Pairwise FWER/FDR →
*shipped (25)*. Šidák (`1−(1−p)^m`) → open, needs exact `Decimal` power (a new primitive).
**Cross-source families** (spanning >1 sealed source) → open, recurring (25,26,28,29,30). Multiple
`alpha` at once → open, "trivial." PBO via CSCV → blocked (new combinatorial primitive + a
config-grid producer that does not exist). Surviving-strategy dominance → open.

**B. Statistical testing.** MinTRL → *shipped (28)*. Calibration significance → *shipped (29)*.
**Finite-sample Student-t** (the standing ★ deferral, 24 & 29) → open, needs a new distribution
primitive. Sharpe-difference significance (Jobson-Korkie/Memmel) → open (needs series correlation
+ higher moments). Confidence intervals / effect sizes → open. Bootstrap / White RC / Hansen SPA /
MC-PBO → **permanently rejected (RNG, invariant 21)**. Annualization conventions → open (thin).

**C. Portfolio construction / optimization.** Mean-variance / max-Sharpe / any μ objective →
**permanently blocked (no PIT-safe expected return; ex-post μ is look-ahead fabrication)**.
**Equality-constrained GMV `Aw=b`** (factor-neutral / target-exposure) → open, "the most-cited
next optimizer step," but flagged as needing an additive `_linalg` matmul helper ⇒ "a different
(larger) phase." Inequality-constrained QP / long-only / box / risk-parity / ERC → **rejected
(iterative float-tolerance solver breaks exact-`Decimal` finite-termination determinism)**.
Black-Litterman / robust / Bayesian → blocked (no priors/views/μ). Tracking-error optimization →
open (needs a benchmark-in-factor-space artifact). Asset-level construction → blocked (no PIT-safe
asset covariance). **Transaction-cost-aware optimization** → deferred (needs a cost model +
holdings; execution-adjacent). Walk-forward/rolling optimization → open (large PIT-decision
surface). A PIT-eligible tradable decision artifact → reserved for "a future explicitly-labelled
phase."

**D. Risk modeling.** Covariance shrinkage / Ledoit-Wolf / EWMA / rolling / regime → open
(expands the Phase 20 estimator vocabulary). Matrix inversion / precision matrix → partly resolved
(21 used `ldl_solve`; a full inverse remains out). Factor covariance-stability / collinearity /
condition-number diagnostics → blocked (needs an eigensolver that does not exist). Idiosyncratic /
asset-on-factor risk → open (larger). Risk attribution MCTR/CCTR → **rejected as tautological for
GMV (`%CCTRᵢ = wᵢ`)**; meaningful only after constrained portfolios exist (itself blocked).

**E. Transaction cost / turnover / implementability.** Walk-forward turnover & stability →
*shipped (27)*. **Transaction-cost / net-of-cost return series** → deferred by 19, 21, 24, and
**explicitly named by 27 as a sanctioned future consumer** ("a cost model, if ever added, consumes
it"; turnover is "the honest cost-free precursor"). Two-way turnover / netting → open (a "trivial
×2 a reader can derive").

**F. Factor construction / attribution.** Multi-signal composite / neutralization / z-scoring /
winsorization, leg-weighting schemes, `rank_direction`, batch runs → open (Phase 19 extensions,
thin). Holdings-based exposure attribution → rejected as near-tautological. Pooled/panel regression
with HAC SEs → open (thin). Cross-sectional exposure analytics on walk-forward → **rejected
("warned against," Phase 22 §7 H; Phase 27 chose temporal instead)**.

**G. Reporting / orchestration.** Report-scope extension → open but "not a research capability."
Cross-artifact meta-report → rejected (Phase 19 Alt G, convenience). Batch/multi-model runs →
open (thin loop). UI / API → out of model.

---

## 4. Binding invariants (the rejection filter)

Quoted/paraphrased from the canon; every candidate in §5 is tested against these:

1. **Exact `Decimal`, no float.** All value/id arithmetic under a pinned context
   (`prec=34, ROUND_HALF_EVEN`); scale/sign folded once; canonical string serialization.
2. **No RNG.** "no float, wall-clock, or RNG enters any value or id" (invariant 21). Permanently
   blocks bootstrap/resampling families.
3. **No wall-clock.** Determinism cannot depend on `datetime.now`/`time.time`; ids never fold time.
4. **PIT boundaries.** A PIT query "must never use information that was not publicly available at
   the requested research timestamp." Research artifacts above Phase 12 are **ex-post** — not a
   `Pit*` type, not a `BacktestResult`, no as-of accessor; `boundary_kind = "pit"` documents only
   that the *underlying* walks were PIT.
5. **Content-addressed identity.** Ids are `sha256:`-prefixed hashes folding engine/method/
   decimal-context version + full declared spec + referenced id(s) **and** their `result_hash`
   (transitive pin) + a `result_hash` over the ordered computed answer.
6. **Write-once persistence.** One shared `ResearchResultStore`; byte-identical round-trip or
   `FactorConsistencyError`; append-only, never edited/deleted; **no new store**.
7. **No fabricated financial data.** "never invents financial data … never fabricates an
   expected-return, risk-free, or benchmark input." UNDEFINED is preferable to an invented input.
8. **No unnecessary ingestion.** "Adds no runtime dependency, no database, no new data source, and
   no new PIT resolution." Layers above Phase 12 are pure consumers of already-sealed artifacts.
9. **No unnecessary numerical primitive.** Exactly one new primitive has ever been admitted
   (Phase 23's normal Φ/Z⁻¹, later shared). "No new numerical primitive and no `_linalg` change …
   If review prefers a design that would require either, that is a different (larger) phase."
10. **Fail-closed degeneracy.** Every singular/degenerate case is a first-class recorded
    `UNDEFINED` (`SINGULAR_COVARIANCE`, `DEGENERATE_SHARPE_ESTIMATOR`, …), never a divide-by-zero
    or a fabricated fallback. **Honest labels** (e.g. BH's independence assumption is never
    relabelled dependence-robust).

---

## 5. Candidate capabilities (≥10), classified

Legend: **architecture-honest** (implementable now within all invariants), **questionable**
(defensible but bumps a load-bearing constraint or the "convenience" line — needs approval),
**rejected** (violates a binding invariant or is tautological/thin).

| # | Candidate | Class | Rationale |
|---|-----------|-------|-----------|
| 1 | **Net-of-cost walk-forward performance + break-even cost** (consume Phase 27 turnover + transitive Phase 22 gross OOS returns; apply a *declared* linear cost rate; also seal an assumption-free break-even cost) | **architecture-honest** | Consumes a terminal leaf that Phase 27 *explicitly reserved for a cost model*; pure `Decimal` arithmetic (turnover × rate, subtract, re-Sharpe via existing moments); no new primitive/RNG/float/wall-clock/ingestion; no fabricated market data (a declared cost rate is a spec parameter like `alpha`/`SR*`, and the break-even rate needs no parameter at all). **RECOMMENDED — see §9.** |
| 2 | **Equality-constrained GMV `Aw=b`** (factor-neutral / target-exposure minimum-variance) | **questionable** | Highest "quant" value and on the README "Next" row; no fabricated μ (min-variance uses Σ only). But solving `w = Σ⁻¹Aᵀ(AΣ⁻¹Aᵀ)⁻¹b` needs a matmul helper + a second `ldl` on the small Gram system — the canon repeatedly flags the additive `_linalg` step as "a different (larger) phase." Bumps invariant 9. Strong Phase 32 candidate. |
| 3 | **Multi-criteria research admissibility record** (first multi-terminal consumer: join CalibrationSignificance, CampaignMultiplicity, MinTRL, WalkForwardStability under a *declared* decision policy → a sealed go/no-go verdict) | **questionable** | Invariant-safe (boolean/threshold comparisons over sealed `Decimal`s, no new primitive); directly resolves the "5 orphaned terminal leaves" boundary. But flirts with the rejected "meta-report / convenience" precedent (Phase 19 Alt G) and risks thinness unless the sealed *decision* (with fail-closed disagreement semantics) is treated as more than a report. Viable but needs an explicit convenience-line ruling. |
| 4 | **Cross-source multiplicity family** (one correction spanning several StrategyComparisons or campaigns) | **questionable** | Reuses `multiplicity.compute.correct_family` verbatim (like Phase 30); invariant-safe. But incremental ("more correction"), and the join semantics across heterogeneous families are contrived; low marginal value over 25/30. |
| 5 | **Finite-sample Student-t distribution** (replace normal-approx p-values in 24/29) | **rejected** | Requires a new exact-`Decimal` t-CDF primitive (regularized incomplete beta) — violates invariant 9 — and produces *no new artifact* (an accuracy upgrade to existing tests). The canon marks this the standing ★ deferral precisely because it is a primitive addition. |
| 6 | **Bootstrap / White's Reality Check / Hansen SPA / MC-PBO** | **rejected** | Requires RNG — violates invariant 2 (21). Permanently blocked by design. |
| 7 | **Mean-variance / max-Sharpe optimization** | **rejected** | Requires an expected-return input; ex-post μ is look-ahead fabrication — violates invariants 4 & 7. Blocked until a PIT-safe μ artifact exists. |
| 8 | **Inequality-constrained QP (long-only / box / gross) · risk-parity · ERC** | **rejected** | Requires an iterative float-tolerance solver with no exact finite-termination guarantee — violates invariants 1 & 9. |
| 9 | **Covariance shrinkage / Ledoit-Wolf / EWMA risk-model variant** | **questionable** | EWMA/linear shrinkage *can* be exact-`Decimal` deterministic (Ledoit-Wolf's optimal intensity is a closed-form ratio). But it extends the Phase 20 estimator vocabulary rather than consuming a leaf, and the shrinkage-target choice invites a convenience creep. A legitimate but lower-priority risk-model sibling. |
| 10 | **GMV risk attribution (MCTR / CCTR)** | **rejected** | Mathematically tautological for the only optimizer that exists (`%CCTRᵢ = wᵢ`); vacuous until constrained portfolios exist (blocked). Explicitly rejected by 22/23/24/25/26. |
| 11 | **Transaction-cost-*aware* optimization** (cost inside the objective) | **rejected** | Needs a cost model *and* holdings inside an iterative optimizer — execution-adjacent, breaks determinism, and duplicates candidate #1's honest ex-post treatment. |
| 12 | **Sharpe-difference significance (Jobson-Korkie / Memmel)** over StrategyComparison | **questionable** | Reuses Φ; a legitimate consumer of Phase 24. But Phase 25 ruled this "belongs inside Phase 24," and it needs per-series correlation + higher co-moments the comparison artifact does not currently seal. Moderate value. |
| 13 | **Report-scope extension** (make Phases 15–30 renderable) | **rejected** | "Not a research capability" (convenience) per 22/23/24. |
| 14 | **PBO via CSCV / combinatorial CV** | **rejected** | Needs a new combinatorial primitive *and* a config-grid performance-matrix producer that does not exist. |
| 15 | **Šidák correction · multiple-`alpha` levels** | **rejected (thin)** | Šidák needs exact `Decimal` power (a primitive) for marginal gain over Holm; multiple-alpha is a "trivial later addition," not a phase. |
| 16 | **Multi-signal composite / neutralized factor construction** | **questionable** | A real Phase 19-class extension, but large, infrastructure-heavy, and off the current statistical/implementability frontier. |

---

## 6. Is the platform at a natural architectural boundary?

**Yes — and the boundary is diagnostic, not terminal.** Three signals:

1. **The linear spine reached a "natural terminus" at Phase 24** (its own words). Phases 25–30 did
   not extend the spine; they *mined reserved payloads* (26/27 read Phase 22's reserved
   variance/weights; 28/30 read Phase 23's reserved moment/psr blocks) and produced **correction /
   significance leaves**.
2. **Five terminal statistical-verdict leaves now exist** (25, 27, 28, 29, 30) with **no
   consumer**, and no artifact joins any two of them. The validation superstructure is broad but
   unintegrated, and — critically — **entirely dimensionless**: every recent leaf is a
   *statistical* verdict (a p-value, a probability, a track-record length, a variance ratio).
   **Nothing in the platform yet expresses an economic cost.**
3. **Phase 27 left an explicit hook.** It sealed turnover as "the honest cost-free precursor" and
   named a cost model as its sanctioned future consumer. This is the same "the architecture
   reserved a consumer for this payload" signal that justified Phases 26/27/28/30 — the strongest
   evidence the canon recognizes for the next phase.

The boundary therefore argues **against** another statistical correction leaf (diminishing returns;
candidates #4, #15) and **against** premature optimizer expansion that requires new machinery
(candidates #2, #8). It argues **for** either (a) the first *economic* consumer of a terminal leaf,
or (b) the first *multi-terminal integrator*. Between these, (a) is the more rigorous, higher-value,
lower-risk move — it adds a genuinely new *dimension* (money) rather than re-packaging existing
verdicts.

---

## 7. The four-way determination (mandate item 8)

- **Consume an existing terminal artifact** — ✅ **CHOSEN.** Phase 31 consumes the terminal
  `WalkForwardStability` (27) turnover leaf plus, transitively, the `WalkForwardEvaluation` (22)
  gross OOS return series. This turns a terminal leaf non-terminal and honors the reservation
  Phase 27 made explicitly.
- **Introduce a genuinely new capability class** — ✅ **also true.** Net-of-cost performance is the
  platform's first *economic / monetary* layer: every prior artifact is dimensionless. This is a
  new capability class ("economic implementability"), not a fifth correction leaf.
- **Consolidate / refactor** — ❌ not now. The recent phases are clean siblings; there is no
  refactor debt that blocks progress (the only noted smell — per-phase `default_decimal_context()`
  duplication — is harmless and out of scope).
- **Stop feature expansion** — ❌ not warranted. A clearly honest, high-value, invariant-safe
  capability exists; the boundary is a redirection (statistical → economic), not exhaustion.

---

## 8. Recommendation

**Phase 31 = Net-of-Cost Walk-Forward Performance.** Apply a *declared, explicit* linear
transaction-cost model to the sealed per-window turnover (Phase 27) and gross out-of-sample
returns (Phase 22), sealing a net-of-cost return series, net performance summary, cost drag, and —
the honest, assumption-free core — the **break-even cost rate** at which the strategy's edge is
exactly consumed. This is chosen for architectural fit (consumes the reserved terminal leaf),
material research value (cost is the single factor that most separates paper strategies from
tradable ones), and airtight invariant compliance — **not** for ease of implementation.

---

## 9. Recommended capability — full specification (DESIGN ONLY)

### 9.1 Exact purpose
Given one sealed `WalkForwardStability` record (Phase 27), which pins one `WalkForwardEvaluation`
(Phase 22) via its `source_ref`, seal an **ex-post** record answering: *how much of this
walk-forward strategy's realized out-of-sample performance survives a declared, hypothetical linear
transaction cost — and at what cost rate does the performance edge vanish entirely?*

Two honest deliverables:
1. **Net-of-cost performance under a declared cost rate `c`** (a required spec parameter, no
   default): per-window net returns, net mean/volatility/Sharpe, and **cost drag** relative to the
   gross figures Phase 22 sealed.
2. **Break-even cost rate `c*`** (parameter-free): the linear cost rate at which mean net return is
   exactly zero — a property of the strategy alone, independent of any assumed rate.

### 9.2 Why it belongs after Phase 27 (and after Phase 30)
Phase 27 opened the *implementability* lens and sealed turnover as "the honest cost-free
precursor," explicitly naming a cost model as its future consumer. Every phase since (28–30) added
*statistical* verdicts; none touched economics. Phase 31 is the sanctioned, reserved next step: it
converts a dimensionless turnover leaf into a monetary conclusion, closing the loop from
"how much does this strategy trade?" (27) to "does it still make money once it pays to trade?" It
is the natural first *economic* layer at exactly the boundary §6 diagnoses.

### 9.3 Precise input artifact(s)
- **Primary:** exactly one sealed `WalkForwardStability` (Phase 27), by id, via
  `store.read_as(...)`. Provides per-realized-window `turnover` (one-way), `gross_leverage`, the
  `excluded` set, and `coverage`.
- **Transitive:** the `WalkForwardEvaluation` (Phase 22) that Phase 27's `source_ref` pins,
  re-resolved read-only by id. Provides per-window gross `oos_returns` aligned to the same window
  axis, and the window calendar.
- **No third source. No new PIT resolution. No new ingestion.**

Alignment is by the shared window index the two artifacts already agree on (Phase 27 derives its
windows from the same Phase 22 record). Any window UNDEFINED/excluded in *either* source is
excluded here (fail-closed) and recorded.

### 9.4 Precise output artifact
A new sealed `ResearchRecord`: **`NetOfCostPerformance`** (proposed domain tag `netcost/1`),
persisted write-once to the existing `ResearchResultStore`. Payload (all Decimals as canonical
strings):

- `source_ref`: `(stability_id, stability_result_hash)` — transitively pins Phase 22 and below.
- `spec`: the full declared specification (see §9.9), including the declared cost rate `c`, the
  entry-cost convention, `periods_per_year` (only if annualizing), and a `break_even: bool` flag.
- `windows`: ordered per-window cells `{index, gross_return, turnover, cost, net_return, status}`.
- `excluded`: windows dropped, each with a reason label.
- `summary`: `{gross_mean, gross_vol, gross_sharpe, net_mean, net_vol, net_sharpe, cost_drag_mean,
  sharpe_drag, break_even_cost_rate, break_even_status, total_cost, total_turnover}`.
- `coverage`: counts (windows total / used / excluded), mirroring Phase 26/27.
- `result_hash`: sha256 over the ordered computed answer cells.

### 9.5 Mathematical methodology
Let realized OOS windows be indexed `t = 1..T`. For each window Phase 22 seals a gross arithmetic
return `r_t` and Phase 27 seals one-way turnover `τ_t` (fraction of portfolio traded at the
rebalance initiating window `t`), with `τ_1` undefined (no predecessor — Phase 27 excludes it).

- **Per-window cost:** `k_t = c · τ_t` for a declared linear rate `c` (cost per unit one-way
  turnover, e.g. in the same Decimal units as returns).
- **Entry cost (window 1):** approved-decision-gated (§17). Recommended: `k_1 = c · L_1` where
  `L_1 = gross_leverage_1 = Σ|w_i|` (turnover from all-cash is the establishment trade). Alternative:
  exclude window 1 from the net series (strict fail-closed).
- **Per-window net return:** `n_t = r_t − k_t`.
- **Net moments:** `net_mean = mean(n_t)`, `net_vol = popstd(n_t)`,
  `net_sharpe = net_mean / net_vol` (UNDEFINED if `net_vol = 0`), using the same population
  convention and the phase-local moment helper the rest of the platform uses. Annualization (if
  requested) reuses each series' own `periods_per_year` exactly as Phase 22 does.
- **Cost drag:** `cost_drag_mean = gross_mean − net_mean`; `sharpe_drag = gross_sharpe − net_sharpe`.
- **Break-even cost rate (parameter-free):** the rate `c*` making mean net return zero. With linear
  costs, `mean(r_t − c*·τ_t) = 0 ⇒ c* = Σ r_t / Σ τ_t` over the used windows (equivalently
  `mean(r)/mean(τ)`). If `Σ τ_t = 0` → `break_even_status = DEGENERATE_NO_TURNOVER`, `c*` UNDEFINED.
  `c*` uses no assumed cost and no new primitive — it is a pure ratio of sealed sums.

All operations are `+ − × ÷` and `Decimal.sqrt` (already the platform's only transcendental). **No
new numerical primitive; no `_linalg` change; no `_stats` call.**

### 9.6 Exact `Decimal` requirements
- All arithmetic under a phase-local pinned context (`prec=34, ROUND_HALF_EVEN`), defined in
  `netcost/version.py :: default_decimal_context()` and folded into engine identity as a version
  string (mirroring `calsig/version.py`).
- Inputs are parsed from the sealed canonical strings back into `Decimal` under this context;
  outputs re-serialized to canonical strings (plain notation, trailing zeros stripped, negative
  zero → `"0"`).
- Division (`c*`, Sharpe) is the only rounding-sensitive step; it inherits the pinned context. No
  intermediate float ever exists.

### 9.7 Determinism strategy
- Pure function of the two sealed inputs and the declared spec — no wall-clock, no RNG, no
  input-order dependence (windows are processed in sealed index order; the used-window set is a
  deterministic filter).
- Identity re-derived on every property access from the record's own fields; the pinned context
  version is folded into the id so a context change is a new id, never a silent redefinition.
- Byte-identical round-trip through the store or `FactorConsistencyError`.

### 9.8 PIT / ex-post boundary
`NetOfCostPerformance` is **ex-post**: not a `Pit*` type, not a `BacktestResult`, exposes **no
as-of accessor**. `boundary_kind = "pit"` (if carried) documents only that the *underlying* walks
were PIT — never that this artifact is a PIT value. The net returns are **counterfactual** ("what
this strategy would have realized net of a declared hypothetical cost") and must never be
substituted where a realized market return is required. Invariant **NC-2** (proposed, §16) states
this in the SD-2/WS-6 family. The declared cost rate is a *modeling assumption*, labeled as such;
it is not fabricated market data (see §17).

### 9.9 Identity inputs (folded into `research_result_id`)
1. Engine + method version + pinned-`Decimal`-context version string.
2. Full declared spec: `cost_rate c` (canonical string), `entry_cost_convention`
   (`gross_leverage` | `exclude`), `annualize` + `periods_per_year` (if any), `break_even` flag.
3. `source_ref = (stability_id, stability_result_hash)` — the transitive pin (Phase 27 → 22 → …).
4. `result_hash` over the ordered computed answer cells.

### 9.10 Persistence behavior
Write-once to the single shared `ResearchResultStore` at
`<root>/research/sha256-<hex>.json`, same envelope and atomic write as every phase. Idempotent
re-write is a no-op; any differing payload under the same id raises `FactorConsistencyError`. **No
new store, no database, no new file format.**

### 9.11 Failure semantics (fail-closed)
- **Missing `cost_rate`** → error at spec construction. No default cost is ever assumed.
- **Source not found** (`read_as` → `None`) → explicit error, never a fabricated substitute.
- **Window UNDEFINED/excluded in either source** → excluded here, recorded in `excluded` with a
  reason; net moments computed over the used windows only, with `coverage` disclosed.
- **`Σ τ = 0`** (a never-trading strategy) → `break_even_status = DEGENERATE_NO_TURNOVER`, `c*`
  UNDEFINED; net series equals gross (cost is exactly zero, honestly reported).
- **`net_vol = 0`** → `net_sharpe = DEGENERATE_SHARPE_ESTIMATOR` (reuse the platform's label
  vocabulary), never a divide-by-zero.
- **Non-commensurable window axes** (Phase 27 and Phase 22 disagree on the index/calendar) →
  first-class error; never silently intersected.
- **Negative net volatility / imaginary sqrt** cannot arise (population variance ≥ 0 exactly).

### 9.12 Proposed package structure
```
src/quantforge/netcost/
  __init__.py
  spec.py        # NetOfCostSpecification (declared cost rate, entry-cost convention, annualize, break_even)
  compute.py     # exact-Decimal per-window net return, moments, cost drag, break-even ratio
  engine.py      # reads WalkForwardStability + transitive WalkForwardEvaluation; assembles the record
  result.py      # NetOfCostPerformance frozen dataclass (ResearchRecord); to_dict/from_dict
  identity.py    # sha256 id + result_hash (reuses sec/artifacts.sha256_hex)
  version.py     # engine/method version + default_decimal_context()
```
Plus a `net_of_cost_engine` property on the `Workspace` facade. No edits to any prior package
(Phase 27/22 records are read-only inputs).

### 9.13 Proposed tests
- **Determinism / round-trip:** identical inputs → byte-identical record and id; store re-write is
  a no-op; a mutated payload under the same id raises `FactorConsistencyError`.
- **Golden values:** hand-computed net returns, net Sharpe, cost drag, and `c* = Σr/Στ` on a small
  fixed fixture (Decimal literals), asserted exactly.
- **Break-even correctness:** at `c = c*`, `net_mean == 0` exactly (to context precision).
- **Monotonicity property:** `net_mean` is non-increasing in `c` when `Στ > 0` (exact Decimal check
  across two declared rates).
- **Zero-cost identity:** `c = 0` ⇒ net series ≡ gross series ⇒ `net_sharpe == gross_sharpe`.
- **Fail-closed:** missing `cost_rate`; missing source; `Στ = 0` → `DEGENERATE_NO_TURNOVER`;
  `net_vol = 0` → `DEGENERATE_SHARPE_ESTIMATOR`; non-commensurable axes → error; excluded windows
  flow into `excluded`/`coverage`.
- **Entry-cost convention:** both `gross_leverage` and `exclude` conventions produce the documented,
  distinct, exact results.
- **No-float / no-RNG / no-wall-clock static checks** consistent with the repo's existing guards.
- **Identity sensitivity:** changing `cost_rate`, `entry_cost_convention`, or the source
  `result_hash` changes the id; re-serialization is stable.

### 9.14 Proposed invariants
- **NC-1** Pure ex-post consumer of exactly one sealed `WalkForwardStability` (transitively its
  `WalkForwardEvaluation`); edits no prior phase's vocabulary, engine, or identity.
- **NC-2** `NetOfCostPerformance` is ex-post: not a `Pit*` type, not a `BacktestResult`, no as-of
  accessor; net returns are counterfactual and never substitutable for realized market returns.
- **NC-3** The cost rate is a *declared spec parameter*, never a default and never inferred from
  data; the break-even rate uses no assumed cost.
- **NC-4** No float, RNG, wall-clock, iterative solver, `_linalg` change, `_stats` call, or new
  numerical primitive enters any value or id; `+ − × ÷` and `Decimal.sqrt` only.
- **NC-5** Every degenerate case is a recorded first-class UNDEFINED label; no divide-by-zero, no
  fabricated fallback; `coverage` always discloses used/excluded counts.
- **NC-6** Adds no runtime dependency, no database, no new store, no new data source, and no new
  PIT resolution.

### 9.15 Version number
**`v0.28.0`** (Phase 31), consistent with the one-phase-per-minor cadence since Phase 17.

### 9.16 Alternatives rejected (and why) — see the full matrix in §5
- **Equality-constrained GMV (#2)** — highest quant value but requires an additive `_linalg`
  matmul + second `ldl`; the canon rules that "a different (larger) phase." Best Phase 32 candidate.
- **Multi-criteria admissibility record (#3)** — invariant-safe and resolves the orphaned-leaf
  boundary, but risks the rejected "meta-report/convenience" precedent and adds no new dimension.
  A strong alternative if the reviewer prefers integration over economics.
- **Mean-variance / max-Sharpe (#7), inequality-constrained QP (#8), bootstrap (#6),
  GMV risk attribution (#10), Student-t primitive (#5)** — each violates a binding invariant
  (fabricated μ / iterative float solver / RNG / tautology / new primitive), per §5.
- **Cross-source multiplicity (#4), Šidák/multi-alpha (#15), report-scope (#13)** — thin /
  convenience; low marginal value.

### 9.17 Architectural risks
1. **The "fabricated forward-looking input" objection (primary risk).** Phase 27 rejected sealing a
   transaction-cost return series *inside its own scope*, phrasing it as "fabricates a
   forward-looking input." Mitigation: (a) the cost rate is a **required declared spec parameter**
   (like `alpha`, `SR*`, `TrainingPolicy`), not owned market data; (b) the output is explicitly
   labeled counterfactual and ex-post (NC-2); (c) the **break-even rate is parameter-free** and is
   the honest core even if a reviewer disallows the declared-rate layer. This must be ratified
   (§17).
2. **Entry-cost convention** (window 1) is a genuine modeling choice; surfaced as an approval-gated
   decision, defaulting to `gross_leverage` (establishment trade from cash) with `exclude` as the
   strict alternative.
3. **Turnover-return alignment convention** — cost for the rebalance initiating window `t` is
   charged to `r_t`. This is the standard convention but should be confirmed against Phase 27's
   exact turnover timing (turnover `τ_t` is measured against the *preceding* window's weights).
4. **Units of the cost rate** — returns and turnover must be in compatible fractional units; the
   spec must state that `c` is "cost per unit one-way turnover, in return units," and validate it.
5. **Scope creep toward cost-aware optimization** — explicitly excluded (candidate #11 is rejected);
   Phase 31 is strictly ex-post measurement, never an optimizer input.

### 9.18 Open approval-gated decisions
1. **Ratify the declared-cost-rate framing** (risk #1): is a declared linear cost rate an
   acceptable spec parameter, or should Phase 31 ship **break-even-only** (fully parameter-free)?
   Recommendation: ship both, with break-even as the default deliverable.
2. **Entry-cost convention default** (`gross_leverage` vs `exclude`). Recommendation: `gross_leverage`.
3. **Annualization** — carry it (reusing each series' `periods_per_year`) or seal per-period only?
   Recommendation: per-period core + optional annualized summary behind an explicit spec flag.
4. **Cost-rate cardinality** — a single `c`, or a small declared *set* of rates sealed together
   (a cost-sensitivity curve)? Recommendation: single `c` for v0.28.0; a declared set is a "trivial
   later addition" not worth the identity surface now.
5. **Domain tag** `netcost/1` and the artifact name `NetOfCostPerformance` — confirm naming.

---

## 18. DESIGN ONLY vs IMPLEMENTATION

**DESIGN ONLY (this document):** the capability selection, the §9 specification, the proposed
package/test/invariant structure, the version number, and the open decisions in §17. Nothing here
has been built; no `src/quantforge/netcost/` package, spec, engine, result type, test, or workspace
property exists.

**IMPLEMENTATION (explicitly NOT performed, and not authorized by this proposal):** writing the
`netcost/` package; adding the `Workspace` property; adding tests; updating `README.md`,
`ARCHITECTURE.md`, `docs/index.md`, or `docs/data-model.md`; producing a `phase31-…-locked.md`;
any commit, tag, or release. These await explicit approval of the §9 design and resolution of §17.

---

## 19. Summary

The repository is at a real but non-terminal architectural boundary: the Phase 19→24 spine reached
its natural terminus, and Phases 25–30 have accumulated five orphaned, purely *statistical*
terminal verdict-leaves. The single most honest, highest-value, invariant-safe next move is the
platform's first *economic* layer — **Net-of-Cost Walk-Forward Performance** — which consumes the
terminal turnover leaf Phase 27 explicitly reserved for a cost model, adds a new dimension (money)
rather than another correction, needs no new numerical primitive / RNG / float / wall-clock /
ingestion / store, and rests its honesty on a declared cost parameter plus a parameter-free
break-even rate. Proposed as **Phase 31, `v0.28.0`**, DESIGN ONLY, pending approval.
