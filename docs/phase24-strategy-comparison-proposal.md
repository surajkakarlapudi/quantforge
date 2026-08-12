# Phase 24 Proposal — Pairwise Out-of-Sample Strategy Comparison

> **Status: PROPOSAL / DESIGN-ONLY.** Nothing in this document is implemented. No
> source files, tests, locked specification, or version bumps have been created. The
> only repository artifact produced for Phase 24 is this file. All decisions marked ★
> require explicit approval before any implementation begins.

---

## 1. Executive thesis

The Phase 19 → 23 capability spine has reached a natural terminus:

```
FactorPortfolio (19) → FactorRiskModel (20) → PortfolioOptimization (21)
  → WalkForwardEvaluation (22) → ResearchCampaignEvaluation (23, terminal)
```

Every link consumes the artifact below it and seals a new write-once, content-addressed
`ResearchRecord` to the shared Phase 8 sidecar. The platform can now build factor
portfolios, model their covariance, optimize (fully-invested GMV), evaluate a strategy
out-of-sample (walk-forward), and correct selection bias over *many* strategies (DSR/PSR).

What it **cannot** do is answer the single most common comparative question in quant
research: **"Is strategy A significantly better, out-of-sample, than strategy B?"** Phase
23 measures the *absolute* significance of the *best* of N strategies; it has no notion of
a *relative*, head-to-head comparison between two strategies evaluated under identical
out-of-sample conditions. Phase 23 explicitly foreshadowed this as **"a separate future
capability … needs cross-trial return alignment."**

I recommend **Phase 24 = Pairwise Out-of-Sample Strategy Comparison** (working artifact
name ★ `StrategyComparison`): consume an ordered set of `2..N` sealed
`WalkForwardEvaluation` records that share a schedule and producing-engine version, align
their realized OOS per-period return series on the shared common date axis, and seal an
upper-triangle matrix of **paired-difference** comparison cells (mean per-period return
difference, its standard error and t-statistic, a deterministic two-sided p-value, the
Sharpe-ratio point difference, and the overlap count), plus a per-trial summary and a
coverage block.

This is a **category-A** (genuinely new capability class): *relative/comparative
statistical testing*, structurally distinct from Phase 23's *absolute selection-bias
correction*. It consumes the one payload in the entire artifact set that is currently
reduced to a scalar and never read as a series (`WalkForwardEvaluation.oos_returns`); it
introduces **no new numerical primitive** (it reuses the Phase 23 exact-Decimal normal Φ),
**no `_linalg` change**, **no RNG**, **no iteration**, **no new store**, **no runtime
dependency**; it is purely ex-post (no PIT surface, no forward-return fabrication); and it
reuses the proven `FactorRiskModel` upper-triangle matrix-cell result skeleton almost
verbatim.

Two candidates that a roadmap-continuation instinct would reach for first are **rejected on
inspection**: risk decomposition (MCTR/CCTR) of `PortfolioOptimization` is *tautological*
for the only sealed objective (GMV), and mean-variance/max-Sharpe optimization is a
look-ahead-fabrication trap already rejected by Phase 21. See §6–§7.

Proposed version: **v0.21.0** (package `__version__` stays `"0.0.0"` per repo convention;
versioning is by content-addressed ids + the README table).

---

## 2. Current architecture state

### 2.1 The consumer spine and its identities

| Phase | Artifact | Package | Identity | Version | Consumes | Consumed by |
|------:|----------|---------|----------|---------|----------|-------------|
| 19 | `FactorPortfolio` | `factorportfolio` | `factor_portfolio_id` | v0.16.0 | (PIT panels/prices) | 20 (+transitive 21/22/23) |
| 20 | `FactorRiskModel` | `factorrisk` | `factor_risk_id` | v0.17.0 | N × `FactorPortfolio` | 21 |
| 21 | `PortfolioOptimization` | `optimization` | `optimization_id` | v0.18.0 | 1 × `FactorRiskModel` | 22 |
| 22 | `WalkForwardEvaluation` | `walkforward` | `walk_forward_id` | v0.19.0 | 1 × `PortfolioOptimization` | 23 |
| 23 | `ResearchCampaignEvaluation` | `campaign` | `campaign_id` | v0.20.0 | N × `WalkForwardEvaluation` | — (terminal) |

Parallel terminal leaves off the earlier spine (not on the 19→23 chain):
`PerformanceAnalytics` (15), `SignalDiagnostics` (16), `FactorAttribution` (17),
`CrossSectionalRegression` (18), `ResearchReport` (14).

### 2.2 Shared infrastructure (authoritative, not to be modified)

- **Content-addressed identity** — `quantforge.sec.artifacts.sha256_hex`; `_SEP="\x00"`
  NUL-join; canonical JSON `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))`; `sha256:`-prefixed ids; derived ids re-emitted by properties,
  never stored/trusted-on-read.
- **Exact-Decimal determinism** — precision 34, `ROUND_HALF_EVEN`, explicit
  `localcontext`; no float, no RNG, no wall-clock, no `id()`, no iteration-order
  dependence.
- **`ResearchResultStore`** (`factors/store.py`) — one shared sidecar under
  `<root>/research/sha256-<hex>.json`; write-once, fail-closed (byte-identical recompute =
  no-op; a differing payload under the same id raises `FactorConsistencyError`); atomic
  (temp + fsync + `os.replace`); generic `read_as(id, from_dict)` decoder;
  `RESEARCH_RESULT_FORMAT_VERSION = 1`.
- **`ResearchRecord` protocol** — `research_result_id` property + `to_dict()`.
- **`_linalg`** (shared, private) — exactly `ldl`, `ldl_solve`, `inverse_diagonal`
  (PD-only exact-Decimal LDLᵀ). No general inverse, eigen, SVD, QR, or iterative solver.
- **`campaign/normal.py`** (Phase 23) — the platform's only exact-Decimal standard-normal
  Φ (cancellation-free erf series) and inverse Z⁻¹ (fixed-depth monotone bisection).
  Explicitly *not* an `_linalg` member.
- **`Workspace`** — lazy `@property` engines (`Engine(self)`, deferred import, `object`
  return type, private `_<name>_engine` cache); `research_result_store` built lazily at the
  data root.

### 2.3 Confirmed payload facts (read directly this investigation)

- `PortfolioOptimization` seals a per-factor **`weights`** vector (`optimization/result.py`)
  that **no downstream reader consumes** — Phase 22 re-solves GMV per window rather than
  reading these weights.
- `FactorRiskModel` seals per-factor **means μ** *and* the covariance/correlation matrices
  (`FactorMoment.mean/volatility/annualized_volatility`); the **means μ have no consumer**
  (GMV uses only Σ).
- `WalkForwardEvaluation` seals `oos_returns: tuple[str, ...]` — the realized OOS
  per-period return **series** — plus per-window `WindowResult(test_start, test_end,
  status, …)` **half-open index ranges into the shared common date axis**. The top-level
  `oos_returns` is **explicitly audit metadata: not folded into the result hash** (it is a
  deterministic function of the pinned config, whose identity *is* folded via
  `result_hash`). Phase 23 reduces this series to a single Sharpe scalar per trial; **the
  series itself is never read by any consumer.**

---

## 3. Capability-gap analysis

The directive's ten investigation questions, answered against the repository:

1. **Current terminal leaves** — `ResearchCampaignEvaluation` (23),
   `PerformanceAnalytics` (15), `SignalDiagnostics` (16), `FactorAttribution` (17),
   `CrossSectionalRegression` (18), `ResearchReport` (14).
2. **Artifacts / payloads with no consumer** — (a) `PortfolioOptimization.weights`;
   (b) `FactorRiskModel` means μ; (c) `WalkForwardEvaluation.oos_returns` *as a series*
   (its Sharpe scalar is consumed by 23, the series is not).
3. **Capabilities deferred by Phases 19–23** — leg-weighting/neutralization (19);
   shrinkage/EWMA/factor-model covariance (20); mean-variance/max-Sharpe, inequality
   constraints, risk-parity, equality-constrained GMV (21); multiple-testing correction,
   risk attribution, regime conditioning (22); bootstrap/PBO-Monte-Carlo, White/Hansen
   resampling, Bonferroni/Holm/BH-FDR, minimum-track-record-length, **pairwise
   horse-race / paired-difference OOS t-stats**, combinatorial-CV PBO, heterogeneous-input
   campaigns (23).
4. **Which deferrals are now unblocked** — pairwise OOS comparison (22 now seals the
   per-period series + axis ranges that alignment needs, and ≥2 comparable evaluations can
   exist); MinTRL and FDR/Bonferroni (23's Φ/Z⁻¹ primitive now exists).
5. **Which create a genuinely new capability CLASS (A)** — pairwise OOS comparison
   (relative/comparative testing). Everything else deferred is either an extension of an
   existing class (B) or blocked (D/E) — see §6–§7.
6. **Which are mere refinements** — MinTRL (inverts 23's per-trial PSR); FDR/Bonferroni
   (multiple-testing over the same campaign family); shrinkage/EWMA (extend 20);
   equality-constrained GMV (extends 21).
7. **Which would violate invariants** — bootstrap / White / Hansen / Monte-Carlo PBO
   (RNG → invariant 21); inequality-constrained QP and risk-parity/ERC (iterative,
   float-tolerance convergence → invariant 21); mean-variance with ex-post μ as forward
   expected return (look-ahead fabrication → invariant 8, PO-3).
8. **Which require float/RNG/wall-clock/runtime-deps/iterative numerics** — bootstrap/PBO
   (RNG); constrained QP / ERC (iteration + float tolerance); everything on the parametric
   side (pairwise comparison, MinTRL, FDR) needs none beyond the existing Φ.
9. **Which compose cleanly with the write-once / content-addressed / `ResearchRecord`
   architecture** — pairwise OOS comparison composes cleanly (reuses the matrix-cell
   skeleton, the read_as/verify/commensurability/seal/write flow, and the Φ primitive).
10. **Strongest missing capability for a more complete research platform** — the ability
    to *compare* strategies head-to-head out-of-sample. The platform can rank and
    selection-bias-correct, but cannot say "A beats B, and the difference is/ isn't
    statistically distinguishable." That is the recommended Phase 24.

**Key structural observation.** The two *clean, identity-bearing* dead payloads
(`weights`, μ) have their natural consumers **blocked** — risk decomposition of GMV is
tautological (§7.1), and mean-variance needs a forward μ that would be a fabrication
(§7.2). The one payload that admits a genuinely new, invariant-safe consumer is the
`oos_returns` **series**, and its consumer is the explicitly-foreshadowed pairwise
comparison. The gap analysis therefore converges on a single category-A answer.

---

## 4. Recommended capability

**Pairwise Out-of-Sample Strategy Comparison.**

Given a `StrategyComparisonSpecification` naming an ordered set of `2..N_MAX`
`WalkForwardEvaluation` ids (all sharing one `schedule_id` and one
`factor_portfolio_engine_version_id`), the engine:

1. Resolves and verifies each referenced `WalkForwardEvaluation` (present, id-match, status
   `REALIZED`), and checks commensurability (shared schedule, producing-engine version,
   `periods_per_year`, `risk_free_per_period`).
2. Reconstructs, for each strategy, the map `axis_index → OOS return` from its `REALIZED`
   `WindowResult` test ranges and its ordered `oos_returns` (the deterministic,
   axis-anchored inverse of how the chained series was built).
3. For each ordered pair `(i, j)`, `i < j`: intersects the two axis-index sets
   (complete-case), forms the paired difference series `d_t = r_t^{(i)} − r_t^{(j)}` over
   the `T_{ij}` overlapping periods, and computes:
   - `mean_diff` `d̄`,
   - `stderr_diff` `= sqrt(s²_d / T_{ij})` where `s²_d` is the **population** variance of
     `d` (divisor `T_{ij}`, matching Phase 20/22 population convention),
   - `t_stat` `= d̄ / stderr_diff`,
   - `p_value` `= 2·(1 − Φ(|t_stat|))` via the reused Phase 23 Φ,
   - `sharpe_diff` `= Sharpe_i − Sharpe_j` (point difference of the sealed per-trial
     Sharpes; **no** significance claim — see §11.4),
   - `overlap_periods` `= T_{ij}`.
4. Seals an **upper-triangle** comparison matrix (`cmp(i,j)`, `i<j`), a per-trial summary
   (label, `walk_forward_id`, Sharpe, `n_valid_periods`), and a coverage block, into a
   write-once `StrategyComparison` record.

**UNDEFINED-preserving throughout.** A pair whose overlap `T_{ij} < MIN_OVERLAP_PERIODS`
(★ propose `2`) yields an UNDEFINED cell (`reason=INSUFFICIENT_OVERLAP`); a pair whose
paired-difference variance is exactly zero yields an UNDEFINED `t_stat`/`p_value`
(`reason=ZERO_DIFFERENCE_VARIANCE`) while `mean_diff`/`sharpe_diff` stay KNOWN. No branch
divides by zero.

Measurement-only: the artifact seals per-pair statistics and makes **no family-wise or FDR
multiple-comparison claim** — that correction is a clean future consumer of this artifact
(mirroring how Phase 22 seals Sharpes and Phase 23 corrects for selection).

---

## 5. Why now

- **Its input just became consumable.** Before Phase 22 there was no per-period OOS return
  series to align; before ≥2 comparable evaluations existed there was nothing to compare.
  Both now hold.
- **Its numerical primitive just became available.** The two-sided p-value needs a normal
  Φ. Phase 23 introduced the platform's first exact-Decimal Φ. Phase 24 reuses it — no new
  primitive, no `_linalg` change.
- **It is explicitly foreshadowed as a separate capability.** Phase 23 deferred "pairwise
  horse-race / paired-difference OOS t-stats between trials — needs cross-trial return
  alignment; a separate future capability," and did not fold it into its own scope. That is
  the signature of a legitimate own-phase, category-A capability whose prerequisites now
  exist.
- **It closes the platform's one glaring analytical gap** — head-to-head strategy
  comparison — without touching any prior-phase identity, store, or invariant.
- **The alternatives are blocked or refinements.** The competing "next links" are either
  tautological (risk decomposition of GMV), fabrications (mean-variance), invariant
  violations (bootstrap/constrained-QP), or same-class extensions (MinTRL, FDR). See §6–§7.

---

## 6. Alternatives considered

Each analyzed on: what it does · artifact consumed · unblocked? · new artifact class? ·
new math? · determinism threat? · look-ahead/PIT threat? · own phase or defer? · what
follows it. Classification A/B/C/D/E.

### 6.1 (★ RECOMMENDED, A) Pairwise OOS strategy comparison
- **Does:** paired-difference performance comparison over aligned OOS return series.
- **Consumes:** `2..N` `WalkForwardEvaluation` (a terminal-leaf's underused series payload).
- **Unblocked:** yes (see §5). **New class:** yes (relative testing). **New math:** none —
  reuses Φ, complete-case alignment (from `factorrisk`), `Decimal.sqrt`.
- **Determinism:** exact-Decimal, no RNG/iteration. **PIT:** ex-post, no forward info.
- **Own phase:** yes. **Follows it:** FDR/family-wise correction over the pairwise matrix; a
  report layer.

### 6.2 (B) Minimum-track-record-length (MinTRL)
- **Does:** required track length for a single strategy's Sharpe to be significant at α.
- **Consumes:** 1 `WalkForwardEvaluation` (or 1 campaign trial). **Unblocked:** yes (Φ/Z⁻¹
  exist). **New class:** no — inverts Phase 23's per-trial PSR (same single-track-record
  significance family). **New math:** none beyond existing Φ/Z⁻¹.
- **Determinism/PIT:** clean. **Own phase:** defer — a refinement of 23's PSR, cheap to add
  later as a campaign-family extension. **Follows:** nothing new.

### 6.3 (B) Family-wise / FDR multiple-testing over a campaign
- **Does:** Bonferroni/Holm/BH-FDR adjusted p-values / rejection set across N trials.
- **Consumes:** 1 `ResearchCampaignEvaluation` or N walk-forwards. **Unblocked:** yes.
  **New class:** borderline — Phase 23 itself calls it "a separate future meta-analysis on
  the same campaign artifact," i.e. same selection-bias family. **New math:** ordering + Φ
  tail; none new.
- **Determinism/PIT:** clean. **Own phase:** defer — cleaner inputs than 6.1 but same class
  as 23; best sequenced after (or alongside) the pairwise matrix it could also correct.
  **Follows:** a report layer.

### 6.4 (B) Equality-constrained GMV (e.g. factor-group-neutral)
- **Does:** `min wᵀΣw s.t. 1ᵀw=1, Aw=b`, closed form. **Consumes:** 1 `FactorRiskModel`.
  **Unblocked:** partially. **New class:** no — extends the Phase 21 optimization class.
  **New math:** requires **one additive `_linalg` matrix-multiply helper** (Phase 21 §11.2
  flagged this); still PD-only, no KKT/indefinite solver.
- **Determinism/PIT:** clean. **Own phase:** defer — an optimization extension, and it
  touches `_linalg`. **Follows:** its own walk-forward/comparison.

### 6.5 (B) Covariance shrinkage / EWMA estimators
- **Does:** Ledoit-Wolf / EWMA / structured covariance in `FactorRiskModel`. **Consumes:**
  N `FactorPortfolio`. **Unblocked:** yes. **New class:** no — extends Phase 20. **New
  math:** matrix scaling/addition (matrix-multiply-class) for structured/shrinkage targets;
  Frobenius norms feasible in Decimal.
- **Determinism/PIT:** clean. **Own phase:** defer — a Phase 20 estimator extension.
  **Follows:** re-runs of the whole spine on the new estimator.

### 6.6 (borderline A/B, defer) Probability of Backtest Overfitting via CSCV
- **Does:** Bailey/López de Prado combinatorially-symmetric cross-validation PBO.
  **Consumes:** the aligned OOS return matrix of N trials. **Unblocked:** partially. **New
  class:** borderline (overfitting-probability vs parametric DSR). **New math:**
  deterministic combinatorial enumeration (`C(S, S/2)`, tractable at S≤16 but explosive
  beyond) + a logit (`Decimal.ln`).
- **Determinism/PIT:** deterministic (no RNG) but combinatorially heavy. **Own phase:**
  defer — needs the *same* cross-trial alignment that 6.1 establishes, and overlaps 23's
  overfitting family; best sequenced **after** the pairwise-alignment layer exists.

### 6.7 (B/C, defer) OOS performance analytics on a walk-forward series
- **Does:** run Phase 15-style analytics (drawdowns, moments, tail) on
  `WalkForwardEvaluation.oos_returns`. **Consumes:** 1 walk-forward. **New class:** no —
  reuse of the existing analytics class on a new input. **Own phase:** defer — a
  reuse/reporting convenience.

---

## 7. Alternatives rejected

### 7.1 (D/C) Risk decomposition (MCTR/CCTR) of `PortfolioOptimization`
- **Rejected — tautological for the only sealed objective.** The sole optimization objective
  in the platform is fully-invested GMV. Its first-order condition is `Σw = λ·1`, so every
  factor's marginal contribution to risk `MCTRᵢ ∝ (Σw)ᵢ = λ` is **equal**, and each
  factor's percent component contribution is `%CCTRᵢ = wᵢ(Σw)ᵢ / (wᵀΣw) = wᵢ` **exactly**.
  Percent risk contribution collapses to the weight; the risk-concentration Herfindahl
  collapses to the weight Herfindahl. Phase 22's own proposal records this: *"Risk
  attribution / budgeting (MCTR/CCTR) — tautological for GMV."* Only the diversification
  ratio is non-trivial — insufficient for a phase. This becomes category A **only** once a
  non-GMV portfolio (e.g. mean-variance or constrained) is sealed, which is itself blocked
  (§7.2, §6.4). Consuming the dead `weights` payload is therefore **premature**, not a gap.

### 7.2 (D/E) Mean-variance / maximum-Sharpe optimization
- **Rejected — look-ahead fabrication.** It needs an expected-return vector μ. The only μ in
  the platform is `FactorRiskModel`'s **ex-post** factor means. Treating an ex-post mean as
  a forward expected return and emitting portfolio weights fabricates forward information —
  precisely what Phase 21 rejected (D-OBJ) and what PO-3 / global invariant 8 forbid.
  Numerically it is a fine closed form (two `ldl_solve`s), so the blocker is *semantic*, not
  numerical. Rejected until a genuinely PIT-safe expected-return artifact exists (a
  separate, hard, out-of-scope problem).

### 7.3 (E) Bootstrap / White's Reality Check / Hansen's SPA / Monte-Carlo PBO
- **Rejected — requires an RNG**, forbidden by global invariant 21. Phase 23 rejected this
  for the same reason and chose the parametric DSR. No deterministic resampling scheme is
  proposed here.

### 7.4 (E) Inequality-constrained (long-only/box/gross) QP; risk-parity / ERC
- **Rejected — iterative solvers with float convergence tolerances** (active-set / interior
  point; nonlinear root-finding). Incompatible with the exact-Decimal, no-iteration
  determinism rule (invariant 21). Phase 21 rejected these (D-SOLVE). Note risk-parity's
  prerequisite is exactly the risk-decomposition of §7.1, which is itself tautological for
  GMV.

---

## 8. Architecture

New package `src/quantforge/comparison/` (★ name), following the Phase 20/23 consumer
skeleton exactly:

```
comparison/
  __init__.py     # docstring (capability class + ex-post posture) + flat __all__
  errors.py       # ComparisonError → {ComparisonConfigurationError, ComparisonConsistencyError}
  version.py      # StrategyComparisonEngineVersion + version tags + default_decimal_context()
  model.py        # ComparisonStatus/UndefinedReason enums, StatValue reuse, ComparisonCell,
                  #   TrialSummary, coverage record, comparison_label helper
  spec.py         # StrategyComparisonSpecification (frozen, self-validating, canonical to_dict)
  align.py        # pure axis-index reconstruction + complete-case pair intersection
  compute.py      # pure exact-Decimal paired-difference stats (reuses normal Φ)
  result.py       # StrategyComparison ResearchRecord (seal/to_dict/from_dict, derived ids)
  identity.py     # strategy_comparison_result_hash(cells) + strategy_comparison_id(...)
  engine.py       # StrategyComparisonEngine: resolve → verify → commensurable → align → compute → seal → write
```

- **Workspace wiring:** add a lazy `comparison_engine` `@property` (deferred import,
  `object` return type, `_comparison_engine` cache slot) mirroring `campaign_engine`. This
  is an *additive* wiring change to `workspace.py` (allowed at implementation time; not part
  of this proposal).
- **Φ reuse (★ open, see §11.5 / §19):** `compute.py` needs the normal CDF Φ. Recommended:
  extract the existing `campaign/normal.py` into a shared private module (e.g.
  `quantforge/_stats/normal.py`) as a **byte-identical pure refactor** (campaign re-imports;
  its `campaign-normal/1` tag and all ids unchanged), then both packages import it —
  mirroring the `_linalg` shared-primitive precedent. Fallback: `comparison.compute` imports
  `campaign.normal` directly (a one-directional package dependency, no modification to
  campaign). The refactor must not alter any Phase 23 byte or id.

---

## 9. Data flow

```
StrategyComparisonSpecification(name, walk_forward_ids=[wf₀, …, wf_{k-1}], ...)
        │
        ▼  Workspace.comparison_engine.compare(spec)
┌───────────────────────────────────────────────────────────────────────┐
│ 1. resolve: store.read_as(wfᵢ, WalkForwardEvaluation.from_dict)          │
│    verify: present ∧ research_result_id==wfᵢ ∧ status==REALIZED          │
│ 2. commensurable: single schedule_id ∧ single                           │
│    factor_portfolio_engine_version_id ∧ single periods_per_year         │
│    ∧ single risk_free_per_period  (else ComparisonConsistencyError)     │
│ 3. align (per strategy): reconstruct {axis_index → return} from          │
│    REALIZED WindowResult (test_start,test_end) ranges + ordered          │
│    oos_returns  (all under the engine's localcontext)                    │
│ 4. compute (per ordered pair i<j): complete-case axis intersection →     │
│    d_t = rᵢ − rⱼ → mean_diff, stderr, t_stat, p_value=2(1−Φ(|t|)),        │
│    sharpe_diff, overlap  (UNDEFINED-preserving)                          │
│ 5. seal: StrategyComparison.seal(engine_version_id, spec.to_dict(),      │
│    trial_refs=(label, wfᵢ, result_hashᵢ), boundary_kind=BOUNDARY_PIT,    │
│    schedule_id, factor_portfolio_engine_version_id, comparisons,         │
│    trials, coverage, dataset/market pins, method_version)                │
│ 6. write: store.write(record)  (write-once, fail-closed, idempotent)     │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼  sealed StrategyComparison → <root>/research/sha256-<hex>.json
```

Corpus pins (`dataset_version_ids`, `market_dataset_version_ids`) are the sorted-distinct
union of the referenced records' pins; more than one distinct value surfaces
`pin_mismatch` (never raised) — identical to Phase 20/23.

---

## 10. Data model

- `ComparisonStatus` — `KNOWN` / `UNDEFINED`.
- `ComparisonUndefinedReason` — `INSUFFICIENT_OVERLAP`, `ZERO_DIFFERENCE_VARIANCE`
  (★ closed set; a `DEGENERATE_INPUT` fallback may be added if implementation surfaces a
  case, disclosed like Phase 23's 4th reason).
- `StatValue` — reuse the UNDEFINED-preserving cell shape used across Phases 15–23.
- `ComparisonCell` — `{ i, j, label_i, label_j, mean_diff: StatValue, stderr_diff:
  StatValue, t_stat: StatValue, p_value: StatValue, sharpe_diff: StatValue,
  overlap_periods: int, status, reason? }`, upper-triangle (`i<j`) only.
- `TrialSummary` — `{ label, walk_forward_id, sharpe: StatValue, n_valid_periods: int }`.
- `Coverage` — `{ n_trials, n_pairs, axis_periods, n_defined_pairs, n_undefined_pairs }`
  (audit metadata; excluded from the hash fold).
- `comparison_label(i)` / pair labels — deterministic index-derived strings.

Antisymmetry convention: only `i<j` cells are stored; a reader derives `cmp(j,i)` by
negating `mean_diff`, `t_stat`, `sharpe_diff` and preserving `p_value`/`overlap`.

---

## 11. Numerical method

### 11.1 Alignment (pure, exact)
For each strategy, iterate its `WindowResult`s in order; for each `REALIZED` window consume
`(test_end − test_start)` values from that strategy's `oos_returns` in sequence, assigning
them to axis indices `test_start … test_end−1`. This reconstructs `{axis_index → Decimal
return}` exactly and deterministically (the inverse of how the chained series was built).
For a pair, intersect the two index sets and iterate in ascending index order — a
complete-case intersection identical in spirit to `factorrisk`'s common-date alignment,
but over the shared axis indices (well-defined because commensurability pins one
`schedule_id`).

### 11.2 Paired-difference statistics
Under the engine's `localcontext` (prec 34, ROUND_HALF_EVEN), for overlap `T = T_{ij} ≥ 2`:
```
d_t     = r_t^{(i)} − r_t^{(j)}
d̄       = (Σ d_t) / T
s²_d    = (Σ (d_t − d̄)²) / T          # population variance (Phase 20/22 convention)
stderr  = sqrt(s²_d / T)               # one Decimal.sqrt
t_stat  = d̄ / stderr                   # UNDEFINED if s²_d == 0 exactly
```

### 11.3 P-value
`p = 2·(1 − Φ(|t_stat|))`, clamped to `[0, 1]`, using the reused exact-Decimal Φ. Two-sided
by construction; Φ's cancellation-free erf series is correctly-rounded and cross-platform
bit-identical.

### 11.4 Sharpe difference (point estimate only)
`sharpe_diff = Sharpe_i − Sharpe_j`, differencing the sealed per-trial `annualized_sharpe`
(or per-period Sharpe — ★ decide which the summary should carry). **No significance test**
is attached: a correct SE for a Sharpe difference (Jobson–Korkie / Memmel) needs the two
series' correlation *and* higher moments, materially enlarging the numerical surface. The
mean-return-difference t-test already gives a rigorous paired significance statistic;
sealing `sharpe_diff` as a KNOWN descriptive difference and deferring its significance
keeps Phase 24 minimal. (★ Approve deferral, or approve the Memmel variance as in-scope.)

### 11.5 No new primitive, no `_linalg` change
Only `Decimal` arithmetic, one `Decimal.sqrt` per pair, and the reused Φ. No matrix ops, no
factorization, no iteration, no transcendental beyond Φ's existing machinery, no RNG.

---

## 12. Determinism analysis

- **Exact-Decimal only** — all arithmetic in stdlib `Decimal` under a fresh pinned context
  (prec 34, ROUND_HALF_EVEN) from `default_decimal_context()`. No float anywhere.
- **No RNG, no wall-clock, no `id()`** — inputs are fully determined by the spec and the
  referenced records.
- **No iteration with data-dependent termination** — the only "iteration" is bounded
  enumeration over a fixed set of windows/periods/pairs in a canonical order (ascending
  axis index; `i<j` pair order); reused Φ's internal bisection is fixed-depth (Phase 23).
- **Order-independence** — pairs and cells are emitted in a canonical `(i,j)` order derived
  from spec position; alignment iterates ascending axis index. Reordering the store or the
  spec's non-semantic content cannot change output bytes (the spec's `walk_forward_ids`
  order *is* semantic and fixes trial labels).
- **Recompute-stability despite the audit-only input** — `oos_returns` is not folded into
  the *walk-forward* hash, but it is a deterministic function of that record's pinned
  config, whose identity *is* folded via `walk_forward_id` + `result_hash`. Phase 24 folds
  the referenced `result_hash` (identity-bearing) into its own id, so a change in any
  upstream config changes this record's id; a byte-identical recompute reproduces identical
  `oos_returns` and thus identical comparison bytes. Fail-closed store semantics then make
  re-runs idempotent. This matches the same standard used by Phase 22, which itself folds
  the chained OOS series once and treats per-window copies as audit metadata.

Same numerical-rigor standard as Phase 23's deterministic Φ/Z⁻¹ decision: a transcendental
is admissible only if correctly-rounded and cross-platform bit-identical (Φ qualifies).

---

## 13. PIT / ex-post analysis

- **Ex-post, not PIT.** The record compares *realized* out-of-sample return series. Per the
  ex-post-is-not-PIT rule (SD-2 / XS-2 / P19-2 / FR-2 / PO-2 / WF-3 / CE-6), it is **not** a
  `Pit*` type, exposes **no** as-of accessor, and cannot be a `BacktestResult`.
- **`boundary_kind = "pit"`** documents only the *input* side: every referenced
  `WalkForwardEvaluation` was itself built from PIT walks with a strict train/test boundary
  (WF-2). The output side is ex-post.
- **No forward-information fabrication.** The comparison is a pure function of already
  realized OOS returns; it introduces no expected-return, no forecast, no future leakage.
  This is the sharp line that rejects mean-variance (§7.2): comparing realized histories is
  ex-post description, whereas using ex-post means as forward μ is fabrication.
- **Train/test boundary** — inherited and untouched; Phase 24 reads only the OOS (test-side)
  series.
- **Corpus pinning / reference-hash verification / transitive pinning** — each referenced id
  is resolved via `read_as`, verified (`research_result_id == requested`, status
  `REALIZED`), and its `result_hash` folded into the Phase 24 id, making identity
  transitively sensitive to any upstream change.

---

## 14. Identity design

- **Artifact type:** `StrategyComparison` (★). **Identity property:**
  `strategy_comparison_id` (★), with `research_result_id` aliasing it.
- **`result_hash`** — folds an ordered `_output_cells` list, each tagged by a `"block"`
  key: `"trial"` summary cells (spec order) → `"cmp"` comparison cells (upper-triangle,
  `(i,j)` ascending). Coverage/audit metadata is **excluded** from the fold (Phase 20/23
  convention).
- **`strategy_comparison_id`** — canonical-JSON + `_SEP` NUL-join of:
  `strategy_comparison_engine_version_id`, spec `name`, spec `spec_version`, ordered
  referenced `walk_forward_ids`, ordered referenced `result_hash`es (transitive pin),
  `periods_per_year`, and the `result_hash`. Derived by a property, re-emitted, never
  trusted on read (`from_dict` re-derives).
- **`strategy_comparison_engine_version_id`** — `sha256(code_version \x00 config_hash)`
  where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=comparison-method/1")`
  (folds decimal context + method version; not the code version, per the `version.py`
  pattern). If Φ is shared, the normal-version tag is folded in as well (as Phase 23 folds
  `campaign-normal/1`).
- **`pin_mismatch`** — property, `True` when `len(dataset_version_ids) > 1 or
  len(market_dataset_version_ids) > 1`; surfaced, never raised.

---

## 15. Persistence design

- **Store:** the existing shared `ResearchResultStore` sidecar (`<root>/research/`). **No
  new store, no database, no new root.**
- **Record shape:** frozen `@dataclass(frozen=True, slots=True)` implementing the
  `ResearchRecord` protocol. Fields (proposed order): `strategy_comparison_engine_version_id`,
  `strategy_comparison_spec: dict`, `trial_refs: tuple[tuple[str,str,str],...]`
  (`(label, walk_forward_id, result_hash)`), `boundary_kind`, `schedule_id`,
  `factor_portfolio_engine_version_id`, `periods_per_year`, `risk_free_per_period`,
  `trials`, `comparisons`, `coverage`, `dataset_version_ids: tuple`,
  `market_dataset_version_ids: tuple`, `method_version`, `result_hash`.
- **`seal()`** — the single constructor the engine calls; computes `result_hash` internally
  from `_output_cells(...)` (caller never supplies it).
- **`to_dict()` / `from_dict()`** — deterministic; `to_dict` emits both
  `strategy_comparison_id` and `research_result_id` keys (for the generic reader);
  `from_dict` re-derives them; `from_dict(to_dict(r))` is byte-identical.
- **Format version:** `COMPARISON_RESULT_FORMAT_VERSION = "comparison-result/1"` (★).
- **Write-once / fail-closed / atomic** — inherited from the store unchanged.

---

## 16. Invariant interaction matrix

Legend: **COMPOSES** (fits with no tension) · **CONSTRAINS** (shapes the design) ·
**TENSION** (needs a concrete resolution) · **CONTRADICTION** (would eliminate the
candidate).

| Invariant(s) | Interaction | Verdict | Resolution / note |
|---|---|---|---|
| 1–6 content-addressed identity, canonical JSON, `_SEP` | reuse `sha256_hex`, canonical dumps, NUL-join | COMPOSES | §14 |
| 7 derived ids re-emitted, never stored | ids are properties; `from_dict` re-derives | COMPOSES | §14–§15 |
| 8 no forward-information fabrication | pure ex-post comparison of realized returns | COMPOSES | §13; this is the line that kills §7.2 |
| 9–14 write-once / fail-closed / atomic store | reuse `ResearchResultStore` unchanged | COMPOSES | §15 |
| 15–20 exact-Decimal, prec 34, HALF_EVEN, explicit context | one context, `Decimal.sqrt`, reused Φ | COMPOSES | §11–§12 |
| 21 no float / RNG / wall-clock / iteration-order | no RNG; bounded canonical enumeration; fixed-depth Φ | COMPOSES / CONSTRAINS | §12; forbids the §7.3/§7.4 alternatives |
| 22 + 22a transitive pinning | fold referenced `walk_forward` `result_hash`es into id | COMPOSES | §14 |
| 23–30 (packaging, `__version__="0.0.0"`, README-table versioning, no new runtime deps, no UI, no new data source) | additive package + workspace property; zero deps | COMPOSES | §8, §23 |
| SD-2 / XS-2 / P19-2 / FR-2 / PO-2 / WF-3 / CE-6 ex-post-is-not-PIT | not a `Pit*` type; no as-of; `boundary_kind` = input-side | COMPOSES / CONSTRAINS | §13 |
| WF-1..WF-6 walk-forward invariants (train/test boundary, chained OOS) | read-only consumption of OOS series + axis ranges | COMPOSES | §11.1 |
| WF audit-only `oos_returns` (not hashed) | Phase 24's primary per-period input is not identity-bearing on the producer | **TENSION** | Fold the producer's identity-bearing `result_hash` (not the returns) into Phase 24's id; determinism holds because `oos_returns` is a pure function of the pinned config; fail-closed store makes re-runs idempotent (§12). |
| Window-drop asymmetry (strategies may drop different UNDEFINED windows) | positional alignment would be invalid | **TENSION** | Align by **axis index** reconstructed from per-window `(test_start,test_end)` ranges (sealed), not by position; complete-case intersect; `INSUFFICIENT_OVERLAP` UNDEFINED cell when overlap `< MIN_OVERLAP_PERIODS` (§11.1). |
| CE-3 commensurability (shared schedule_id + producing-engine version) | Phase 24 must define its own commensurability contract | CONSTRAINS | Require single `schedule_id`, `factor_portfolio_engine_version_id`, `periods_per_year`, `risk_free_per_period`; else `ComparisonConsistencyError` (§9). |
| PO-3 / 21 no forward μ (mean-variance) | applies to an *alternative*, not the recommendation | CONTRADICTION (alt only) | Eliminates §7.2, not Phase 24. |
| 21 no-iteration (constrained QP / ERC / bootstrap) | applies to *alternatives* | CONTRADICTION (alt only) | Eliminates §7.3/§7.4, not Phase 24. |
| `_linalg` is exactly ldl/ldl_solve/inverse_diagonal | Phase 24 needs no matrix op | COMPOSES | No `_linalg` change (contrast §6.4/§6.5). |

No interaction weakens any invariant. Both TENSIONs have concrete, fail-closed resolutions.

---

## 17. New phase-local invariants (proposed SC-*)

- **SC-1 (reference + transitive pin).** Every referenced `WalkForwardEvaluation` is
  resolved via `read_as`, verified (`research_result_id == requested`, status `REALIZED`),
  and its `result_hash` folded into `strategy_comparison_id`.
- **SC-2 (commensurability).** All trials share one `schedule_id`, one
  `factor_portfolio_engine_version_id`, one `periods_per_year`, and one
  `risk_free_per_period`; any disagreement raises `ComparisonConsistencyError`.
- **SC-3 (axis-index alignment).** OOS returns are aligned by common date axis index
  reconstructed from sealed per-window `(test_start, test_end)` ranges and status — never by
  raw position. Alignment is complete-case per pair.
- **SC-4 (fail-closed degeneracy).** Overlap `< MIN_OVERLAP_PERIODS` → UNDEFINED cell
  (`INSUFFICIENT_OVERLAP`); exact zero paired-difference variance → UNDEFINED
  `t_stat`/`p_value` (`ZERO_DIFFERENCE_VARIANCE`) with `mean_diff`/`sharpe_diff` KNOWN. No
  divide-by-zero branch.
- **SC-5 (single deterministic methodology).** One exact-Decimal method; Φ reused unchanged;
  no RNG, no data-dependent iteration; two-sided p-values only.
- **SC-6 (ex-post / not-PIT / not-BacktestResult).** The record is ex-post, not a `Pit*`
  type, exposes no as-of accessor, cannot be a `BacktestResult`; `boundary_kind="pit"`
  documents only the input side.
- **SC-7 (measurement-only).** The artifact seals per-pair statistics with no family-wise /
  FDR multiple-comparison adjustment; correction is left to a future consumer.
- **SC-8 (antisymmetry).** Only `i<j` cells are stored; `cmp(j,i)` is the sign-flip of
  `mean_diff`/`t_stat`/`sharpe_diff` with `p_value`/`overlap` preserved.

(Final SC-numbering to be reconciled at lock time, as Phase 23 reorganized CE-numbering
between proposal and locked spec.)

---

## 18. Approval-gated decisions (★)

1. ★ **Capability scope** — pairwise paired-difference OOS comparison, measurement-only (no
   multiple-comparison correction, no Sharpe-difference significance).
2. ★ **Artifact name** — `StrategyComparison` (alternatives: `PairwiseStrategyComparison`,
   `OutOfSampleComparison`).
3. ★ **Package name** — `comparison` (alternative: `strategycompare`).
4. ★ **Input artifacts & count** — `2..N_MAX` `WalkForwardEvaluation`; `N_MAX` value
   (propose `32`).
5. ★ **Objective / method** — mean-return paired-difference t-test + descriptive
   `sharpe_diff`; **defer** Sharpe-difference significance (or approve Memmel variance as
   in-scope — §11.4).
6. ★ **Numerical method / Φ sourcing** — reuse Phase 23 Φ; **how**: (a) extract
   `campaign/normal.py` → shared `_stats/normal.py` as a byte-identical refactor
   (recommended), or (b) import `campaign.normal` directly (§8, §19).
7. ★ **Alignment rule** — axis-index complete-case intersection (recommended) vs any
   stricter "fully-valid equal-length axis" requirement.
8. ★ **Undefined behavior** — `MIN_OVERLAP_PERIODS` (propose `2`); closed UNDEFINED-reason
   set `{INSUFFICIENT_OVERLAP, ZERO_DIFFERENCE_VARIANCE}`.
9. ★ **Identity inputs** — the id-fold field list in §14.
10. ★ **Version** — v0.21.0.
11. ★ **Invariant additions** — SC-1 … SC-8 (§17).
12. ★ **Storage model** — shared sidecar `ResearchRecord`, no new store.
13. ★ **PIT / ex-post boundary** — ex-post; `boundary_kind="pit"` documents input side only.
14. ★ **Two-sided vs one-sided p-values** — propose two-sided.
15. ★ **Sharpe basis in `TrialSummary`** — annualized vs per-period Sharpe.

---

## 19. Open questions

1. **Φ sourcing (the central architectural question).** Extract to a shared `_stats`
   module (cleanest, mirrors `_linalg`, but touches `campaign` — permissible only as a
   byte-identical refactor preserving every Phase 23 id) vs a one-directional
   `comparison → campaign` import (no modification, slightly awkward dependency direction)
   vs a duplicated copy (rejected — divergence risk). Recommendation: shared `_stats` at
   implementation time.
2. **Sharpe-difference significance** — defer (recommended) or include the Memmel variance
   (needs cross-series correlation + higher moments; enlarges the surface).
3. **`N_MAX`** — 32 vs 64 (Phase 23 uses 64); the pairwise matrix is `O(N²)` cells, so a
   smaller cap may be prudent.
4. **Coverage granularity** — how much per-pair audit detail (dropped-period counts, axis
   spans) to seal without bloating the record.
5. **Self-comparison / duplicate ids in the spec** — reject duplicates in `__post_init__`
   (fail-closed) — confirm.
6. **Relationship to a future FDR layer** — should the pairwise matrix be explicitly
   designed as an FDR consumer's input (it already is; confirm no extra fields needed now).

---

## 20. Proposed files (implementation-time only — NOT created by this proposal)

New (all under `src/quantforge/comparison/`): `__init__.py`, `errors.py`, `version.py`,
`model.py`, `spec.py`, `align.py`, `compute.py`, `result.py`, `identity.py`, `engine.py`.

Modified (additive, implementation-time): `src/quantforge/workspace.py` (lazy
`comparison_engine` property + cache slot), `src/quantforge/__init__.py` (export
`StrategyComparison`, `StrategyComparisonSpecification`), and — **only if** Φ is shared —
`src/quantforge/campaign/normal.py` re-imports a new `src/quantforge/_stats/normal.py`
(byte-identical refactor).

New tests: `tests/comparison/` (see §21).

Docs (implementation-time): `docs/phase24-strategy-comparison-locked.md`,
`docs/data-model.md` (§ SC-* block), `docs/index.md`, `README.md` (capability bullet +
v0.21.0 row), `ARCHITECTURE.md` (implemented-layers row + intro blurb → Phases 1–24).

---

## 21. Test strategy

- **Identity & round-trip** — `from_dict(to_dict(r))` is byte-identical; `result_hash` and
  `strategy_comparison_id` reproduce; a tampered stored id is ignored (re-derived).
- **Determinism** — full run under both pytest orderings; recompute is a byte-identical
  store no-op; a differing payload under the same id fails closed.
- **Transitive pinning** — changing any referenced `WalkForwardEvaluation` (hence its
  `result_hash`) changes `strategy_comparison_id`.
- **Commensurability** — mismatched `schedule_id` / engine version / `periods_per_year` /
  `risk_free_per_period` raises `ComparisonConsistencyError`; missing / wrong-id / non-
  `REALIZED` reference raises.
- **Alignment** — axis-index reconstruction is correct across window drops; two strategies
  with disjoint valid windows → `INSUFFICIENT_OVERLAP`; overlap correctly intersected.
- **Numerical correctness** — hand-computed `mean_diff`, `stderr`, `t_stat`, `p_value`,
  `sharpe_diff` on small fixtures; **antisymmetry** (`cmp(i,j)` sign-flips `cmp(j,i)`);
  **self-difference identity** (a strategy vs itself, if permitted, → `mean_diff=0`,
  `sharpe_diff=0`, UNDEFINED t-stat via zero variance) — used to validate SC-4/SC-8.
- **UNDEFINED preservation** — zero paired-difference variance → UNDEFINED `t_stat`/`p_value`
  with KNOWN `mean_diff`; clamping of `p_value` to `[0,1]`.
- **Ex-post posture** — the type exposes no as-of accessor and is not a `BacktestResult`
  (static/structural assertion).
- **Gate parity with Phase 23** — ruff check + format, mypy across all files, pytest both
  orderings, zero new runtime deps.

---

## 22. Documentation changes (implementation-time only)

`docs/phase24-strategy-comparison-locked.md` (new locked spec, modeled on Phase 23);
`docs/data-model.md` (append the SC-* invariant block after CE-6 in §12); `docs/index.md`
(Phase 24 entry + Status → "Phases 1–24"); `README.md` (core-capability bullet + v0.21.0
version-table row); `ARCHITECTURE.md` (intro blurb → Phases 1–24 + a "Strategy comparison"
implemented-layers row). **None of these are touched by this proposal.**

---

## 23. Version

**v0.21.0** (the +0.01.0 step continuing v0.16.0 → v0.20.0). Package `__version__` remains
`"0.0.0"` per repo convention — versioning is expressed via content-addressed ids and the
README version table, not the module attribute. No `pyproject`/packaging change; no new
runtime dependency.

---

## 24. Final recommendation

Adopt **Phase 24 = Pairwise Out-of-Sample Strategy Comparison** (`StrategyComparison`, ★
names pending approval), a **category-A** capability that gives QuantForge its missing
relative/comparative testing layer: aligning the realized OOS return series of `2..N`
commensurable `WalkForwardEvaluation` records on the shared date axis and sealing an
upper-triangle matrix of paired-difference statistics (mean-return difference, standard
error, t-statistic, two-sided p-value via the reused Phase 23 Φ, descriptive Sharpe
difference, overlap count). It consumes the one series payload nothing else reads, is
explicitly foreshadowed by Phase 23, introduces **no new numerical primitive**, **no
`_linalg` change**, **no RNG/iteration**, **no new store**, and **no runtime dependency**;
it is purely **ex-post** with no PIT surface or forward-information fabrication; and it
reuses the proven upper-triangle matrix-cell result skeleton and the standard
resolve→verify→commensurable→align→compute→seal→write engine flow.

The obvious roadmap-continuation candidates are rejected for concrete, verified reasons:
risk decomposition of `PortfolioOptimization` is **tautological for GMV** (`%CCTRᵢ = wᵢ`
exactly — documented in Phase 22 itself), and mean-variance/max-Sharpe optimization is a
**look-ahead fabrication** (ex-post μ as forward return; rejected by Phase 21 / PO-3 /
invariant 8). MinTRL and FDR/Bonferroni are same-class refinements of Phase 23; bootstrap
and constrained-QP variants violate the no-RNG / no-iteration determinism rule.

**Do not implement until this proposal is explicitly approved.** ★-marked decisions —
especially the artifact/package names, the Φ-sharing approach, and the Sharpe-difference
significance scope — need sign-off first.

---

### Concise final report

- **Selected capability:** Pairwise Out-of-Sample Strategy Comparison — paired-difference
  performance comparison across `2..N` commensurable `WalkForwardEvaluation`s (category A).
- **Why:** the platform can rank and selection-bias-correct strategies but cannot compare
  two head-to-head OOS; this consumes the only unread series payload
  (`WalkForwardEvaluation.oos_returns`), is explicitly foreshadowed by Phase 23 as "a
  separate future capability," needs no new numerical primitive / `_linalg` change / RNG /
  store / dependency, and is purely ex-post with no PIT or forward-fabrication risk.
- **≥5 alternatives analyzed:** MinTRL (B, defer), FDR/family-wise correction (B, defer),
  equality-constrained GMV (B, defer, needs `_linalg` matrix-multiply), covariance
  shrinkage/EWMA (B, defer), CSCV PBO (borderline A/B, defer, combinatorial + overlaps 23),
  OOS analytics reuse (B/C, defer); **rejected:** risk decomposition (D — tautological for
  GMV), mean-variance (D/E — forward fabrication), bootstrap/White/Hansen (E — RNG),
  constrained QP / risk-parity (E — iteration).
- **Key architectural decisions:** shared sidecar `ResearchRecord` (no new store); reuse
  the upper-triangle matrix-cell skeleton; commensurability on
  schedule/engine/`periods_per_year`/`risk_free_per_period`; **axis-index** alignment
  reconstructed from sealed per-window ranges (resolving the date-unlabeled + window-drop
  frictions); identity folds referenced `result_hash`es (resolving the audit-only,
  non-hashed `oos_returns` tension); Φ reused (recommended shared `_stats/normal.py`
  byte-identical refactor).
- **Invariant findings:** all interactions COMPOSE/CONSTRAIN; two TENSIONs (audit-only
  input; window-drop asymmetry) each resolved fail-closed; the CONTRADICTIONs (forward μ,
  iteration/RNG) apply only to rejected alternatives; no invariant is weakened; proposed
  new SC-1 … SC-8.
- **Numerical / determinism findings:** exact-Decimal only; one `Decimal.sqrt` per pair;
  reused correctly-rounded Φ; no float, RNG, wall-clock, or data-dependent iteration; no
  `_linalg` change; recompute-stable and idempotent under the fail-closed store.
- **Proposed package/files:** `src/quantforge/comparison/` (`__init__`, `errors`, `version`,
  `model`, `spec`, `align`, `compute`, `result`, `identity`, `engine`); additive
  `workspace.py` + `__init__.py` wiring; optional shared `_stats/normal.py`;
  `tests/comparison/`.
- **Proposed version:** v0.21.0 (package `__version__` stays `"0.0.0"`).
- **Proposal path:** `docs/phase24-strategy-comparison-proposal.md`.
- **Exact repository changes made by this task:** created this one file
  (`docs/phase24-strategy-comparison-proposal.md`). Nothing else.
- **Confirmation:** **NO implementation occurred.** No source files, tests, or locked
  specification were created; `README.md`, `ARCHITECTURE.md`, `docs/index.md`,
  `docs/data-model.md`, and all existing source/test files are **unchanged**; package
  `__version__` is **unchanged**; **no commit, push, tag, or release** was performed. STOP —
  awaiting explicit approval of the Phase 24 proposal before any implementation.
