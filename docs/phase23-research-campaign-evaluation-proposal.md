# Phase 23 — Out-of-Sample Research-Campaign Evaluation with Selection-Bias Correction (PROPOSAL)

> **Status: DESIGN ONLY. Not approved. Nothing implemented.** This document
> proposes the next capability and its architecture for review. No source, tests,
> or locked spec exist. Per the Phase 23 charter it creates exactly one file (this
> proposal) and changes nothing else — no README/ARCHITECTURE/index/data-model
> edit, no source, no tests, no commit, no tag.
>
> **Recommended capability:** a **research-campaign evaluation** that consumes an
> **ordered set of `N` sealed `WalkForwardEvaluation` records** (Phase 22 — the
> newest terminal leaf) as the trials of one search, and computes a
> **selection-bias-corrected significance of the best out-of-sample (OOS)
> strategy**: the **Probabilistic Sharpe Ratio (PSR)** and the **Deflated Sharpe
> Ratio (DSR)** — the canonical López de Prado backtest-overfitting statistic that
> corrects the maximum observed OOS Sharpe for (a) the number of trials `N` and
> (b) the non-normality (skew / kurtosis) and length of each trial's OOS return
> series. The result is a new sealed, content-addressed, ex-post
> `ResearchCampaignEvaluation` record.
>
> **Version:** **v0.20.0** (Phase 22 = v0.19.0).
>
> **Load-bearing decision requiring approval (§19 ★1):** v1 introduces a
> deterministic **exact-`Decimal` standard-normal CDF `Φ` and its inverse `Z⁻¹`**
> (a new *internal* `campaign/normal.py`, **not** an `_linalg` change). This is the
> only genuinely new numerical primitive; it is float-free and deterministic under
> the pinned context (the `Decimal.sqrt` precedent already used for volatility).
> A determinism-safe **fallback (comparison-only v1, no `Φ`)** is offered in §7 A′
> and §19 ★1 in case the reviewer declines to introduce `Φ`.

---

## 1. Executive Summary

Phases 19–22 built the project's first end-to-end **portfolio-construction-and-validation
spine**: characteristic-sorted factor return series (`FactorPortfolio`, P19) → their
covariance structure (`FactorRiskModel`, P20) → a fully-invested global minimum-variance
weight vector (`PortfolioOptimization`, P21) → a **walk-forward out-of-sample evaluation**
of that recipe with a strict train-before-test split (`WalkForwardEvaluation`, P22).
Repository inspection establishes three facts that determine the next phase:

1. **`WalkForwardEvaluation` is now the terminal leaf.** A repo-wide search confirms
   `walk_forward_id` / `WalkForwardEvaluation` appear only inside `walkforward/`, the
   `Workspace.walk_forward_engine` factory property, and the top-level re-export. **No
   functional consumer exists.** Phase 22 turned the Phase-21 leaf into an input; Phase 23
   does the same for Phase 22.

2. **The one OOS number a researcher actually trusts is systematically over-stated the
   moment they run more than one trial.** A single `WalkForwardEvaluation` seals an OOS
   Sharpe ratio (`summary.annualized_sharpe`) and the chained per-period OOS return series
   (`oos_returns`). But research is never one trial: a quant runs the P19→P22 chain over
   many signals / training policies / universes and **keeps the best**. The maximum of `N`
   noisy Sharpe ratios is upward-biased even when every strategy is worthless — the
   canonical **data-snooping / backtest-overfitting** problem. **Nothing in the repository
   corrects for it.** This is the single largest remaining *validity* gap after OOS
   evaluation itself.

3. **The repository already told us this is the next phase, and named its exact
   prerequisite.** Phase 22's proposal (`§7 F`) evaluated *"Multiple-testing / data-mining
   correction (Bonferroni / BH-FDR / deflated Sharpe)"* and returned **"Verdict: DEFER —
   genuine future phase, weaker fit now,"** with two concerns: *"the input is a heterogeneous
   set of previously-sealed records with no natural single-artifact container; it does not
   consume Phase 21; it is a meta-analysis layer better sequenced once a 'research campaign'
   grouping artifact exists."* Both concerns are now resolved (§4): a campaign of
   **homogeneous** `WalkForwardEvaluation` trials **is** the natural single-artifact
   container, and it **transitively consumes Phase 21** (each trial *is* a Phase-21 consumer).

Phase 23 answers exactly that. It is a **pure consumer** that references an ordered set of
`N` sealed `WalkForwardEvaluation` records (the trials of one declared campaign), re-derives
each trial's per-period OOS excess-return distribution from its sealed `oos_returns`, and
computes:

- per trial: the per-period OOS **Sharpe**, its **skew** and **kurtosis**, the OOS length
  `n`, and the **Probabilistic Sharpe Ratio** `PSR(SR*)` against a baseline `SR*`;
- across the campaign: the number of trials `N`, the **variance of the trials' Sharpe
  ratios** `V[{SR_i}]`, the **expected maximum Sharpe under the null** `SR₀`, and the
  headline **Deflated Sharpe Ratio** `DSR = PSR(SR₀)` of the selected (max-Sharpe) trial —
  the probability that the *best* strategy's true Sharpe genuinely exceeds what a search of
  `N` worthless strategies would have thrown up by chance.

This is the **first genuine consumer of Phase 22's output**, it is the project's first
**meta-analysis / selection-bias** layer, it introduces the project's first **research-campaign
grouping artifact** (the deferred prerequisite), and it composes only pinned scalar statistics
of already-sealed OOS series — no new corpus read, no new PIT surface, no `_linalg` change, no
modification to any prior phase. It preserves every existing invariant and is ex-post
throughout.

It is deliberately **not** mean-variance / constrained optimization, risk attribution, or a
report-scope extension — the repository shows each of those is blocked by a missing PIT-safe
`μ`, by exact-`Decimal` determinism, by GMV tautology, or is a presentation convenience (§7).

---

## 2. Repository State

### 2.1 The capability spine as actually implemented (verified from source)

| Phase | Package | Sealed record | Reads | Reached via |
|---|---|---|---|---|
| 9 | `universe` | `Universe` (PIT membership) | corpora | `Workspace` |
| 10 | `panel` | PIT fundamental panels | corpora | `panel_engine` |
| 11 | `market` | PIT market data | corpora | `price_engine` |
| 12 | `backtest` | `BacktestResult` | corpora + strategy | `backtest_engine` |
| 13 | `experiment` | `ExperimentResult` / `BacktestComparison` | sealed backtests | `experiment_engine` |
| 14 | `report` | `ResearchReport` (reference-only) | sealed backtests/experiments | `report_engine` |
| 15 | `analytics` | `PerformanceAnalytics` | sealed `BacktestResult` (store) | `analytics_engine` |
| 16 | `diagnostics` | `SignalDiagnostics` | corpora (P9/10/11) | `signal_diagnostics_engine` |
| 17 | `attribution` | `FactorAttribution` | subject + K factor `BacktestResult`s (store) | `attribution_engine` |
| 18 | `crosssection` | `CrossSectionalRegression` | corpora (P9/10/11) | `crosssection_engine` |
| 19 | `factorportfolio` | `FactorPortfolio` | corpora (P9/10/11) | `factor_portfolio_engine` |
| 20 | `factorrisk` | `FactorRiskModel` | N `FactorPortfolio`s (store) | `factor_risk_engine` |
| 21 | `optimization` | `PortfolioOptimization` | 1 `FactorRiskModel` (store) | `optimization_engine` |
| 22 | `walkforward` | `WalkForwardEvaluation` | 1 `PortfolioOptimization` (store) | `walk_forward_engine` |

### 2.2 Shared infrastructure (verified)

- **`ResearchRecord` Protocol** (`factors/store.py`): minimal — a `research_result_id: str`
  property + `to_dict() -> dict[str, object]`. No `from_dict` on the protocol (decoding is
  supplied to `read_as`), no result-kind, no format version on the protocol.
- **`ResearchResultStore`** (`factors/store.py`): `write(result) -> Path` (write-once,
  atomic via tmp + `os.replace`, idempotent on a byte-identical payload; a differing payload
  under an existing id raises `FactorConsistencyError`), `read_as(id, from_dict) -> T | None`
  (typed decode), `read(id)`, `has(id)`. One JSON file per result under `<root>/research/`,
  filename `= id.replace(":", "-") + ".json"`, wrapped as
  `{"research_result_format_version": 1, "research_result": result.to_dict()}` and dumped
  with `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)`. Reached through
  `Workspace.research_result_store` (lazily built at `<availability_root>.parent`).
- **Identity primitive:** `sha256_hex(bytes)` (`sec/artifacts.py`), imported by every phase's
  `identity.py`/`version.py`. **No** shared `canonical_json`: each identity module inlines
  `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",",":"))`, NUL-joins
  components with `"\x00"`, and prefixes `sha256:`.
- **`_linalg`** (private): exactly `ldl`, `ldl_solve`, `inverse_diagonal` — exact-`Decimal`,
  no float/numpy, run inside the caller's pinned `localcontext`. **No** normal-CDF, error
  function, or root-finder. **Phase 23 does not touch `_linalg`.**
- **Distribution moments already exist** (`analytics/compute.py`): population
  `skewness = μ₃/σ³` and `excess_kurtosis = μ₄/σ⁴ − 3`, UNDEFINED-preserving
  (`INSUFFICIENT_PERIODS` / `ZERO_VARIANCE`). So skew/kurtosis is *not* a new formula — only
  `Φ`/`Z⁻¹` is (§9, §19 ★1).
- **Decimal discipline:** precision 34, `ROUND_HALF_EVEN`, `localcontext` everywhere;
  volatility via `Decimal.sqrt(context)`; no float, wall-clock, or RNG in any value or id.
- **`Workspace`**: each engine is a lazy, cached `@property` typed `-> object` that defers the
  engine import and constructs `Engine(self)`, sharing the one `research_result_store`.

### 2.3 The three facts that drive Phase 23

- **Terminal leaf.** `WalkForwardEvaluation` has no functional consumer (only `walkforward/`,
  the `Workspace` factory, and the re-export reference it). The evaluation is produced and
  never *compared*.
- **Sealed-but-unread OOS distribution.** `WalkForwardEvaluation` seals `oos_returns` (the
  chained per-period OOS return series), `risk_free_per_period`, `summary` (including
  `annualized_sharpe` and `n_valid_periods`), `schedule_id`, `factor_portfolio_engine_version_id`,
  the carried corpus pins, and a `result_hash` — everything a selection-bias correction needs.
  Nothing reads any of it.
- **The prerequisite the repo named is now buildable.** P22 §7 F deferred multiple-testing
  correction "once a 'research campaign' grouping artifact exists." That grouping artifact —
  a homogeneous, ordered, content-addressed set of OOS trials — is exactly what Phase 23's
  `ResearchCampaignSpecification` introduces.

---

## 3. Selected Capability

**Out-of-sample research-campaign evaluation with selection-bias (Deflated Sharpe)
correction.**

Input: an ordered set of `2..N_MAX` sealed `WalkForwardEvaluation` ids (the trials of one
declared search) + a baseline Sharpe `SR*` (default `0`). Computation: resolve and re-verify
each trial (transitively pinning its optimization → risk model → factors → corpora);
enforce commensurability (one shared `schedule_id`); for each trial re-derive from its sealed
`oos_returns` the per-period excess-return **Sharpe**, **skew**, **kurtosis**, and length `n`,
and the **PSR** against `SR*`; across the campaign compute `N`, the trials-Sharpe variance
`V[{SR_i}]`, the expected-maximum-Sharpe null threshold `SR₀`, and the **Deflated Sharpe
Ratio** `DSR = PSR(SR₀)` of the selected (max-Sharpe) trial. Output: a sealed
`ResearchCampaignEvaluation` holding the per-trial statistic table, the selected trial, and
the campaign-level `V[SR]` / `SR₀` / `DSR`. Ex-post, content-addressed, write-once.

The capability is **evaluative-of-evaluations** (a meta-analysis): it does not re-run any
construction or re-estimate anything; it aggregates pinned scalar statistics of already-sealed
OOS series. It performs **no execution** — it is not a `BacktestResult` (CE-2).

---

## 4. Why This Capability Now

1. **It closes the validity loop that OOS evaluation opened.** Phase 22 lets a researcher ask
   *"does this recipe work out of sample?"* for one recipe. The instant they ask it for many
   recipes and keep the best — which is the actual research workflow — the answer is biased.
   The **only** honest way to report the best OOS result is to deflate it for the size of the
   search. Until Phase 23 exists, the P19→P22 spine produces OOS Sharpe ratios that a careful
   reader cannot trust as reported.
2. **It is the first genuine consumer of Phase 22.** It turns the new terminal leaf into an
   input and (transitively, CE-1) pins each trial's optimization, risk model, factors, and
   corpora.
3. **Its two previously-blocking concerns are now resolved.** P22 §7 F deferred it because
   (a) *"it does not consume Phase 21"* and (b) *"the input is a heterogeneous set … with no
   natural single-artifact container … better sequenced once a 'research campaign' grouping
   artifact exists."* Now: (a) each trial is a `WalkForwardEvaluation`, itself the Phase-21
   consumer, so the campaign is squarely on the P21 spine; and (b) a set of `N`
   **homogeneous** `WalkForwardEvaluation`s (same record type, same OOS-Sharpe semantics,
   commensurable schedule) **is** the natural single-artifact container. The deferral's own
   exit condition is met.
4. **Every prerequisite exists.** The OOS return series are sealed (`oos_returns`); the
   trial count and per-trial length are sealed; skew/kurtosis is an existing exact-`Decimal`
   method (`analytics/compute.py`); the shared sidecar, identity discipline, and Decimal
   context are in place. The *only* new numerical surface is `Φ`/`Z⁻¹` (§9, §19 ★1).
5. **The alternatives are blocked or tautological (§7).** Mean-variance needs a PIT-safe `μ`
   (does not exist); constrained optimization breaks exact-`Decimal` determinism; risk
   attribution is tautological for GMV; report-scope extension is a convenience, not research.

---

## 5. Research Workflow Gap

Today a researcher can go: *signal → factor portfolio → risk model → GMV weights →
walk-forward OOS evaluation → **?***. The arrow after a *single* OOS evaluation is empty, and
the arrow that matters most is the one across *many* OOS evaluations:

> *I ran the whole chain on 40 candidate signals and the best one has an OOS Sharpe of 1.3.
> Given that I searched 40 strategies, and given that this one's OOS returns are skewed and
> fat-tailed over only 60 periods, what is the probability its true Sharpe is actually above
> zero — i.e., that I have not simply selected the luckiest of 40 coin-flips?*

Phase 23 provides that arrow. It establishes the reusable **research-campaign** grouping
primitive (an ordered, pinned set of comparable trials) and the **selection-bias correction**
that any future meta-analysis (Bonferroni/FDR over t-stats, minimum-track-record-length,
probability-of-backtest-overfitting) can build on without re-inventing it.

### 5.1 Why the uncorrected OOS Sharpe is not enough (the skeptical core)

Let `SR_i` be the per-period OOS Sharpe of trial `i`, estimated over `n_i` periods.

- **The maximum is biased upward.** Even if every strategy has a true Sharpe of exactly `0`,
  `E[max_i SR_i]` grows with the number of trials `N` (roughly `√V[SR] · √(2 ln N)` for large
  `N`). Reporting `max_i SR_i` and its naïve single-trial significance overstates the result
  by a factor that increases with how hard you searched.
- **Non-normality inflates single-trial significance too.** The variance of an estimated
  Sharpe over `n` periods is *not* `1/n`; it is inflated by negative skew and excess kurtosis
  (Lo 2002; Mertens). A strategy that makes small gains punctuated by rare large losses (the
  typical "picking up pennies" profile) has a far less significant Sharpe than the raw number
  suggests.

The **Deflated Sharpe Ratio** (López de Prado & Bailey, 2014) corrects for *both* at once:

```
DSR = PSR(SR₀)  =  Φ(  (SR_best − SR₀) · √(n_best − 1)
                       ─────────────────────────────────────────── )
                       √( 1 − γ₃·SR_best + ((γ₄ − 1)/4)·SR_best² )
```
where `γ₃`, `γ₄` are the skew and (non-excess) kurtosis of the *best* trial's per-period OOS
returns, and the selection-bias threshold is the expected maximum Sharpe under the null:
```
SR₀ = √V[{SR_i}] · [ (1 − γ) · Z⁻¹(1 − 1/N)  +  γ · Z⁻¹(1 − 1/(N·e)) ]
```
with `γ` the Euler–Mascheroni constant and `Z⁻¹` the inverse standard-normal CDF. Both
formulas collapse to a bare, over-optimistic significance **only if you ignore `N` and the
higher moments** — which is exactly what the platform does today. Phase 23 exists to stop
doing that.

---

## 6. Capability Matrix (Phases 15–22)

| Phase / record | Research question | Input artifact | Output artifact | Statistical domain | Diagnostic / Constructive / Meta | PIT / ex-post | Consumed downstream? | Explicitly deferred |
|---|---|---|---|---|---|---|---|---|
| **15** `PerformanceAnalytics` | Risk & benchmark-relative stats of a backtest | `BacktestResult` (store) | `PerformanceAnalytics` | TS risk / distribution / relative | Diagnostic | ex-post | **No** | multi-factor regression (→P17); batch analytics |
| **16** `SignalDiagnostics` | Does an as-of-`T` signal predict forward returns (IC)? | corpora | `SignalDiagnostics` | XS predictive | Diagnostic | ex-post | **No** | long-short (→P19) |
| **17** `FactorAttribution` | How much of a strategy's return do K factors explain? | subject + K factor backtests (store) | `FactorAttribution` | TS multi-factor OLS | Diagnostic | ex-post | **No** | HAC/GLS SE |
| **18** `CrossSectionalRegression` | Do K signals price forward returns (FM premia)? | corpora | `CrossSectionalRegression` | XS OLS + FM aggregation | Diagnostic | ex-post | **No** | HAC SE; WLS; standardization |
| **19** `FactorPortfolio` | Realized L/S quantile factor-return series? | corpora | `FactorPortfolio` | construction + series summary | **Constructive** | ex-post | **Yes → P20** | rolling; costs; weighting |
| **20** `FactorRiskModel` | Second-moment structure of N factor series? | N `FactorPortfolio`s (store) | `FactorRiskModel` | population covariance/correlation | Diagnostic | ex-post | **Yes → P21** | rolling cov; shrinkage |
| **21** `PortfolioOptimization` | GMV weights over Σ? | 1 `FactorRiskModel` (store) | `PortfolioOptimization` | closed-form GMV | **Constructive** | ex-post | **Yes → P22** | walk-forward; constraints; mean-variance |
| **22** `WalkForwardEvaluation` | Does the recipe work out of sample? | 1 `PortfolioOptimization` (store) | `WalkForwardEvaluation` | train→test OOS realization | **Evaluative** | ex-post | **No (terminal leaf)** | **multiple-testing correction**; report scope |
| **23 (proposed)** `ResearchCampaignEvaluation` | Is the *best of N* OOS strategies real, or selection luck? | **N `WalkForwardEvaluation`s (store)** | `ResearchCampaignEvaluation` | **cross-trial selection-bias (PSR/DSR)** | **Meta-analysis** | ex-post | (future: report/FDR) | — |

**Largest meaningful gap:** the evaluative branch (22) produces per-recipe OOS Sharpe ratios
that are **individually reported and never jointly corrected**. Phase 22 itself deferred the
multiple-testing correction, naming the exact missing prerequisite. Filling it is the
highest-value, best-justified next step; it consumes the terminal leaf, introduces the
deferred campaign artifact, and closes the validity loop.

---

## 7. Alternatives Considered

Each row states: what it is, why it matters, prerequisites present/missing, fit, duplication,
prior-phase change, new PIT/data needs, whether it seals a new artifact, phase-sizing,
sequencing, risks, verdict.

### A. Research-campaign evaluation with Deflated-Sharpe selection correction — **RECOMMENDED**
- **Why it matters:** the only honest way to report the best of many OOS results; the canonical
  cure for backtest overfitting; the exact capability P22 §7 F deferred to a future phase.
- **Prereqs present:** sealed `WalkForwardEvaluation.oos_returns` + `risk_free_per_period` +
  `n_valid_periods` + `schedule_id` + `result_hash`; an existing exact-`Decimal` skew/kurtosis
  method; the shared sidecar + identity + Decimal stack. **Missing:** a deterministic
  exact-`Decimal` `Φ`/`Z⁻¹` primitive (this phase, §9, §19 ★1) — the one new numerical surface.
- **Fit:** clean additive meta-analysis consumer; references `N` sealed `WalkForwardEvaluation`s
  (first consumer of P22) and pins each transitively (CE-1). Mirrors Phase 20's "ordered set of
  N sealed same-type inputs → one sealed output" structure exactly.
- **Duplicates a phase?** No. Phase 13 compares *`BacktestResult`s* by scalar metrics with **no
  OOS discipline and no multiple-testing correction**; Phase 23 corrects the *selection bias
  across OOS `WalkForwardEvaluation`s* — a statistic that appears nowhere in the repo.
- **Requires changing a prior phase?** No. It reads sealed Phase-22 fields already present; it
  adds no field to any prior record and no `_linalg` primitive.
- **New PIT / data requirements?** None. Inputs are ex-post OOS series; output is ex-post.
- **New sealed artifact?** Yes — `ResearchCampaignEvaluation`, and the campaign grouping spec.
- **Phase-sized?** Yes — a bounded single-artifact capability with one coherent new discipline
  (selection-bias correction) and one bounded new primitive (`Φ`/`Z⁻¹`).
- **Sequencing:** enables later FDR/Bonferroni over t-stats, minimum-track-record-length, and
  probability-of-backtest-overfitting — all of which consume the same campaign grouping.
- **Risks:** (i) the `Φ`/`Z⁻¹` primitive is a genuinely new numerical surface (mitigated: pure
  `Decimal`, deterministic, `Decimal.sqrt` precedent, exact termination rule, §9; and the §7 A′
  fallback exists); (ii) defining the search size `N` honestly (design ★2: `N` = all submitted
  trials, valid or not); (iii) scope creep into general FDR (bounded: v1 is DSR/PSR only).
- **Verdict: SELECT.**

### A′. Comparison-only campaign (rank + trials-Sharpe dispersion, **no `Φ`**) — fallback
- Identical inputs and record shape, but v1 seals only the ranked per-trial Sharpe/skew/kurtosis
  table, the trial count `N`, and `V[{SR_i}]` — **stopping short of PSR/DSR** (which need `Φ`).
- **Why weaker:** it surfaces the *ingredients* of the selection-bias problem but not the
  correction, so the researcher still cannot state a corrected significance. It avoids the only
  new numerical primitive, so it is strictly determinism-safe.
- **Verdict: FALLBACK** — adopt only if the reviewer declines to introduce `Φ`/`Z⁻¹` (§19 ★1).
  A later phase would then add `Φ` and the DSR on top of this same campaign artifact.

### B. Single-evaluation OOS calibration / risk-model bias test
- Consume **one** `WalkForwardEvaluation` and test whether predicted variance systematically
  differs from realized variance (`predicted_vs_realized`).
- **Why weaker:** single-record; the raw pairs are already sealed and exposed by P22; the added
  statistic (a bias ratio) is thin and does not consume the terminal leaf as a *set*. Real but
  small. **Verdict: DEFER** (a minor future add; note it).

### C. Mean-variance / maximum-Sharpe optimization
- **Blocker:** needs an expected-return vector `μ`. No PIT-safe expected-return artifact exists;
  ex-post factor means as forward `μ` is look-ahead fabrication (invariant 8; PO-3; P21 D-OBJ).
  **Verdict: REJECT** until a PIT-safe `μ` artifact is built.

### D. Constrained optimization (long-only / box / gross-exposure)
- **Blocker:** requires an iterative QP / active-set / interior-point solver — incompatible with
  the exact-`Decimal`, no-iteration, no-float determinism rule (invariant 21; P21 D-SOLVE).
  **Verdict: REJECT / SEQUENCE LATER** (the task's own warning aligns).

### E. Portfolio risk attribution / risk budgeting (MCTR / CCTR)
- **Blocker:** tautological for the current GMV artifact (percent contribution = weight; P22
  §5.1). Meaningful only once constrained / non-GMV portfolios exist. **Verdict: REJECT as
  premature** — depends on D first.

### F. Report-scope extension (make P15–22 artifacts reportable)
- **Concern:** a presentation/convenience layer, not a *research* capability ("does not merely
  add convenience APIs"). **Verdict: DEFER** (a small future reporting bump).

### G. Shrinkage / EWMA / robust / factor-model covariance
- Modifies/extends Phase 20's estimator vocabulary — prematurely expands an earlier phase.
  **Verdict: REJECT** (belongs inside a future P20 method extension, not here).

### H. Factor / portfolio exposure analytics
- The GMV weights *are* the factor exposures; exposure analytics over a weight vector is
  near-tautological and thin (P22 candidate H, rejected outright). **Verdict: REJECT.**

---

## 8. Prerequisite Analysis

| Prerequisite | Present? | Evidence / note |
|---|---|---|
| Sealed OOS **return series** per trial | ✅ | `WalkForwardEvaluation.oos_returns` (P22) |
| Per-trial OOS length `n` | ✅ | `summary.n_valid_periods` (= `len(oos_returns)`) |
| Per-trial risk-free (for excess Sharpe) | ✅ | `WalkForwardEvaluation.risk_free_per_period` |
| Shared calendar for commensurability | ✅ | `WalkForwardEvaluation.schedule_id` + `factor_portfolio_engine_version_id` |
| Transitive pin per trial | ✅ | `WalkForwardEvaluation.result_hash` (folds recipe→model→factors→corpus) |
| Skew / kurtosis (exact `Decimal`) | ✅ (compose or mirror) | `analytics/compute.py` population moments |
| Population variance / `√` | ✅ | established Decimal idiom (`Decimal.sqrt`) |
| Shared write-once sidecar + identity | ✅ | shared infra (§2.2) |
| Standard-normal CDF `Φ` and inverse `Z⁻¹` | ❌ (**this phase**) | new internal `campaign/normal.py`; exact-`Decimal`, no float (§9, §19 ★1) |
| Euler–Mascheroni constant `γ` | ❌ (**this phase**) | a documented 34-digit `Decimal` literal (a constant, not a computation) |
| Expected-return vector `μ` | ❌ (not needed) | DSR uses only realized OOS Sharpe + moments |
| Iterative QP / `_linalg` change | ❌ (not needed) | no matrix solve; `_linalg` untouched |
| Bootstrap / resampling | ❌ (**disallowed**) | would need an RNG (invariant 21); the parametric DSR avoids it |

**Missing prerequisites that are genuinely required: exactly one** — a deterministic
exact-`Decimal` `Φ`/`Z⁻¹` primitive (with `γ` as a documented constant). This is the single
load-bearing decision (§19 ★1). Distribution-free bootstrap alternatives (White's Reality
Check, Hansen's SPA) are **off the table** because they require an RNG, which invariant 21
forbids — so a *parametric* correction (DSR) is not merely the strongest choice, it is the
*only* determinism-compatible one.

---

## 9. Contradiction / Invariant Analysis

Interactions classified **COMPOSES** (fits cleanly), **CONSTRAINS** (allowed but bounds the
design), **TENSION** (needs explicit handling), **CONTRADICTION** (would force rejection).
Analyzed against global **1–30 (+22a)**, and families **SD-1..4, XS-1..4, P19-1..5, FR-1..5,
PO-1..5, WF-1..6**.

| Invariant / rule | Class | Explanation |
|---|---|---|
| **1–5** immutability / provenance | COMPOSES | No raw/fact writes; reads only sealed research records. |
| **6–17** PIT & availability | COMPOSES | No corpus read, no `as_of` query; inputs are ex-post OOS series. |
| **18, 19, 20, 21** determinism / versioning / no wall-clock / no RNG | **CONSTRAINS** | All arithmetic (incl. `Φ`, `Z⁻¹`) under the pinned context; `Φ`/`Z⁻¹` are float-free, deterministic, with an exact termination rule (§14); **no bootstrap/RNG** (this is *why* DSR, not Reality Check). |
| **22, 22a, 23** amendments / supersession | COMPOSES | Not applicable; no fact history involved. |
| **27** mode explicit | COMPOSES | No resolution query; consumes sealed ex-post artifacts. |
| **28** `REVISED` is not a PIT source | COMPOSES | Output is ex-post, never a PIT value (CE-2). |
| **29** PIT monotonic / past-closed | COMPOSES (n/a) | No PIT query; the trials' internal WF-2 split is already sealed and inherited. |
| **8** acceptance ≠ availability / no fabricated data | COMPOSES | No `μ`, no imputation; an undefined trial Sharpe is a first-class UNDEFINED cell (CE-4), never invented. |
| **SD-1 / XS-1 / P19-1** corpus pinning | COMPOSES | Corpus pins are **inherited** (surfaced as `pin_mismatch`) from each trial; never re-derived. |
| **FR-1 / PO-1 / WF-1** reference verification + transitive pinning | COMPOSES → **CE-1** | Resolve + verify each referenced `WalkForwardEvaluation` (id match, `status == REALIZED`); fold each `result_hash`; transitively pin recipe → model → factors → corpora. |
| **FR-3** commensurability (one `schedule_id` / engine version) | COMPOSES → **CE-3** | Require all trials share one `schedule_id` and one `factor_portfolio_engine_version_id`; mismatch fails closed; corpus-pin difference surfaced, never reconciled. |
| **FR-4 / XS-4 / P19-4 / PO-4 / WF-4** fail-closed degeneracy, never repaired | COMPOSES → **CE-4** | A trial whose OOS Sharpe is undefined (`n < 2`, zero dispersion) is a recorded UNDEFINED trial cell, excluded from selection/dispersion; `< MIN_VALID_TRIALS` → the campaign statistics are UNDEFINED, never fabricated. |
| **PO-2 / FR-2 / WF-3 …** "not a PIT value" | COMPOSES → **CE-2** | Ex-post; not a `Pit*` type; no as-of accessor; `boundary_kind="pit"` documents only the underlying PIT walks. |
| **PO-5 / FR-5 / P19-5 / WF-3** "not a `BacktestResult`; no execution" | COMPOSES → **CE-2** | Distinct record type; no fills/cash/positions/costs. |
| **PO-3 / WF-5** single methodology; no fabricated inputs | COMPOSES → **CE-5/CE-6** | One correction method (DSR); no shrinkage; no `μ`; composed skew/kurtosis + `Φ`/`Z⁻¹` versions folded into engine identity. |
| **Identity / content-addressing** | CONSTRAINS | Fold engine + method + decimal-context + `Φ`-primitive version + ordered trial `(id, result_hash)` + `schedule_id` + baseline `SR*` + the answer hash; `research_result_id` aliases the new id. |
| **`ResearchRecord` / write-once store** | COMPOSES | New record implements the Protocol; seals write-once to the shared sidecar; byte-identical idempotent re-seal. |
| **Introducing a transcendental (`Φ`, `Z⁻¹`) into an exact-`Decimal` codebase** | **TENSION** | *Not* a contradiction. The project already computes an irrational (`Decimal.sqrt`) to context precision for volatility; a `Decimal`-series `Φ` and a fixed-tolerance `Z⁻¹` are the same category — deterministic, float-free, reproducible to prec-34. Resolved by (a) computing under an explicit `localcontext`, (b) an **exact** stopping rule (halt when the next series term rounds to `0` at the context precision, plus a hard max-term cap), and (c) a **fixed-iteration** monotone bisection for `Z⁻¹` with a guaranteed-terminating exact bracket test. Surfaced as the load-bearing ★1 (§19), with the §7 A′ fallback if rejected. |
| **P21's rejection of "iterative solvers"** | **TENSION (rebutted)** | P21 rejected iteration because *constrained-QP* active-set/interior-point paths are combinatorial and lack finite exact-`Decimal` termination. `Z⁻¹` is a 1-D bisection on a monotone smooth function with a closed bracket `[−k, +k]` and a fixed iteration count for a target precision — it terminates deterministically. This is categorically different and does not reopen the P21 objection. |
| **Bootstrap / permutation multiple-testing (Reality Check / SPA)** | **CONTRADICTION** (for a *rejected* alternative) | Documented to show why Phase 23 is *parametric*: a resampling test needs an RNG, violating invariant 21. The DSR is closed-form given `Φ`/`Z⁻¹`, so no contradiction arises for the recommended capability. |

**No contradiction forces rejection of the recommended capability.** The two TENSIONs
(introducing `Φ`; the iteration objection) are resolved by the `Decimal.sqrt` precedent, an
exact termination rule, and the categorical difference between 1-D monotone bisection and
constrained-QP iteration. The one CONTRADICTION is with a *rejected* alternative (bootstrap),
reinforcing the parametric choice.

---

## 10. Architecture

New package **`src/quantforge/campaign/`**, mirroring the P20/P21/P22 layout:

- `errors.py` — `CampaignError` → `CampaignConfigurationError`, `CampaignConsistencyError`.
- `version.py` — `ResearchCampaignEngineVersion` (folds the pinned decimal context **and** the
  composed method versions — the campaign method version, the reused skew/kurtosis moment
  version, and the `Φ`/`Z⁻¹` primitive version — into `config_hash`); constants
  `CAMPAIGN_SPEC_VERSION = "campaign/1"`, `CAMPAIGN_ENGINE_VERSION = "campaign-engine/1"`,
  `CAMPAIGN_METHOD_VERSION = "campaign-method/1"`, `NORMAL_PRIMITIVE_VERSION = "campaign-normal/1"`;
  `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`).
- `normal.py` — **the one new numerical primitive (★1):** `standard_normal_cdf(x, *, context)`
  (`Φ`, via a `Decimal` series/complementary-error-function with an exact stopping rule) and
  `standard_normal_ppf(p, *, context)` (`Z⁻¹`, a fixed-iteration monotone bisection on `Φ`);
  the documented `EULER_MASCHERONI` constant. Pure, float-free, reads no store. **Not** in
  `_linalg` — kept phase-local so `_linalg` stays exactly `ldl`/`ldl_solve`/`inverse_diagonal`.
- `model.py` — vocabulary: `TrialStatus` (`VALID` | `UNDEFINED`); `CampaignUndefinedReason`
  (closed: `INSUFFICIENT_OOS_PERIODS`, `ZERO_OOS_VARIANCE`, `INSUFFICIENT_VALID_TRIALS`);
  `StatValue` (KNOWN decimal string | UNDEFINED + reason), reusing the established cell
  discipline; `TrialStat` (per-trial block); `trial_label(index) -> "trial_{index+1}"`.
- `spec.py` — `ResearchCampaignSpecification` (declarative request; §12).
- `moments.py` — pure per-series statistics: per-period excess-return mean, population
  variance/volatility, Sharpe, skew, kurtosis over one trial's `oos_returns` (compose
  `analytics` moments if cleanly importable, else a self-contained `campaign-method/1`
  computation — §19 ★3, the P22 compose-vs-inline decision).
- `compute.py` — the pure compute core: per trial → `TrialStat` (Sharpe/skew/kurtosis/`n`/PSR);
  across trials → select best, `V[{SR_i}]`, `SR₀`, `DSR = PSR(SR₀)`. Pure; reads no store.
- `result.py` — `ResearchCampaignEvaluation` (`ResearchRecord`; `.seal` / `to_dict` /
  `from_dict`), plus `TrialStat`; constants `CAMPAIGN_RESULT_FORMAT_VERSION = "campaign-result/1"`,
  `BOUNDARY_PIT = "pit"`, `MIN_VALID_TRIALS = 2`, `N_MAX = 64` (see §19 ★5).
- `identity.py` — `campaign_result_hash`, `campaign_id`; domain tag `campaign/1`.
- `engine.py` — `ResearchCampaignEngine`: resolve + verify each referenced
  `WalkForwardEvaluation` → check commensurability (CE-3) → per-trial moments/PSR →
  cross-trial `V[SR]`/`SR₀`/`DSR` → `.seal(...)` → `store.write`.
- `__init__.py` — exports `ResearchCampaignSpecification`, `ResearchCampaignEvaluation`
  (+ vocabulary/errors).

**Edits to existing source (all additive, none altering any existing identity):**
1. `workspace.py` — one lazy `campaign_engine` `@property` (+ private cache slot), following the
   `walk_forward_engine` template (typed `-> object`, deferred import).
2. `src/quantforge/__init__.py` — top-level re-exports of `ResearchCampaignSpecification` and
   `ResearchCampaignEvaluation` (engine reached via `Workspace`), added to the sorted `__all__`.
3. `tests/test_smoke.py` — one additive export assertion.

**No edit to** `_linalg`, `walkforward`, `optimization`, `factorrisk`, `factorportfolio`,
`analytics`, `backtest`, or any other prior-phase identity/vocabulary. If `analytics`' moment
functions are not cleanly importable as window-agnostic pure functions, the fallback is a
self-contained `campaign-method/1` moment computation in `moments.py` (still exact-`Decimal`),
not a modification of `analytics` — surfaced in §19 ★3.

---

## 11. Data Flow

```
ResearchCampaignSpecification { trial_ids[2..N_MAX], benchmark_sharpe="0", name, ... }
        │
        ▼  ResearchCampaignEngine.evaluate(spec)
resolve each WalkForwardEvaluation by id                                — fail closed (CE-1)
   store.read_as(id, WalkForwardEvaluation.from_dict); verify research_result_id == id;
   verify status is REALIZED (an UNDEFINED walk carries no OOS series to correct)   (CE-1)
   fold each trial's result_hash (transitive pin: WF → PO → FR → factors → corpora)
        │
        ▼
check commensurability: one shared schedule_id AND one                  — fail closed (CE-3)
   factor_portfolio_engine_version_id across all trials; carry corpus pins (surface pin_mismatch)
        │
        ▼  per trial i (deterministic, exact-Decimal):
   e_t = r_t − risk_free_per_period   over oos_returns                  (per-period excess)
   μ_i, σ_i² = Σ(e−μ)²/n, σ_i = √σ_i²                                   (population; Decimal.sqrt)
   if n_i < 2                          → UNDEFINED trial (INSUFFICIENT_OOS_PERIODS)  — CE-4
   if σ_i == 0                         → UNDEFINED trial (ZERO_OOS_VARIANCE)         — CE-4
   SR_i = μ_i / σ_i ;  γ₃_i = m₃/σ³ ;  γ₄_i = m₄/σ⁴   (skew, non-excess kurtosis)
   PSR_i(SR*) = Φ( (SR_i − SR*)·√(n_i−1) / √(1 − γ₃_i·SR_i + ((γ₄_i−1)/4)·SR_i²) )
        │
        ▼  across trials:
   N = number of submitted trials              (the honest search size, incl. UNDEFINED — ★2)
   V = population variance of { SR_i : VALID }                                        — CE-4
   if #VALID < MIN_VALID_TRIALS (2)   → SR₀ / DSR UNDEFINED (INSUFFICIENT_VALID_TRIALS) — CE-4
   best = argmax_i SR_i  (tie → lowest index)                                          — ★2
   SR₀ = √V · [ (1−γ)·Z⁻¹(1 − 1/N) + γ·Z⁻¹(1 − 1/(N·e)) ]                              — CE-5
   DSR = PSR_best(SR₀) = Φ( (SR_best − SR₀)·√(n_best−1) / √(1 − γ₃·SR_best + ((γ₄−1)/4)·SR_best²) )
        │
        ▼
ResearchCampaignEvaluation.seal(...)  →  ResearchResultStore.write (write-once, idempotent)
        │
        ▼
store.read_as(id, ResearchCampaignEvaluation.from_dict)   (byte-identical typed round-trip)
```

---

## 12. Public API

```python
from quantforge import (
    Workspace,
    ResearchCampaignSpecification,
    ResearchCampaignEvaluation,
)

ws = Workspace.open(root)

spec = ResearchCampaignSpecification(
    name="value-momentum-quality-search",
    trial_ids=(wf_id_1, wf_id_2, ..., wf_id_40),   # sealed WalkForwardEvaluation ids (2..N_MAX)
    benchmark_sharpe="0",                          # SR* baseline for PSR (per-period); default "0"
)

campaign = ws.campaign_engine.evaluate(spec)       # sealed, write-once

campaign.n_trials                 # the honest search size N (all submitted trials)
campaign.trial_stats              # per trial: label, sharpe, n_periods, skew, kurtosis, psr (StatValue cells)
campaign.selected_label           # label of the max-Sharpe trial (or UNDEFINED cell)
campaign.trials_sharpe_variance   # V[{SR_i}] over VALID trials (StatValue)
campaign.expected_max_sharpe      # SR₀ selection-bias threshold (StatValue)
campaign.deflated_sharpe          # DSR = PSR(SR₀) of the selected trial (StatValue)  ← headline
campaign.pin_mismatch             # inherited corpus-pin flag
campaign.research_result_id       # == campaign.campaign_id

again = ws.research_result_store.read_as(
    campaign.research_result_id, ResearchCampaignEvaluation.from_dict
)
```

`ResearchCampaignEngine` is reached only through `Workspace.campaign_engine` (lazy, cached,
`-> object`). `evaluate(spec) -> ResearchCampaignEvaluation` is the single entry point. No
`Company` method is added.

**`ResearchCampaignSpecification` (frozen slots):** `name`, `trial_ids` (`tuple[str, ...]`),
`benchmark_sharpe` (`str`, default `"0"`), `spec_version = "campaign/1"`. Construction-time
validation (fail closed): non-empty `name` / `spec_version`; `2 ≤ len(trial_ids) ≤ N_MAX`;
`trial_ids` distinct and non-empty; `benchmark_sharpe` a parseable decimal string. It reads no
store — it cannot know whether the trials exist (engine's job, CE-1), whether they are
commensurable (CE-3), or whether any trial's Sharpe is defined (needs the resolved data).

---

## 13. Identity and Hashing

- Domain tags via shared `sha256_hex`, NUL-separated, canonical JSON, `sha256:`-prefixed:
  record `campaign/1`; engine `campaign-engine/1`; method `campaign-method/1`; normal primitive
  `campaign-normal/1`.
- `campaign_engine_version_id = sha256(code_version "campaign-engine/1", config_hash)` where
  `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=campaign-method/1\x00
  moment=<skew/kurtosis method version>\x00normal=campaign-normal/1")`. **Folding the moment
  and normal-primitive versions** makes the campaign's identity change if the moment definition
  or the `Φ`/`Z⁻¹` implementation changes.
- `campaign_result_hash = sha256(canonical JSON over the ordered computed-output blocks: each
  per-trial block in request order — `{block:"trial", index, status, reason?, sharpe?, n_periods?,
  skew?, kurtosis?, psr?}` — then the campaign block `{block:"campaign", selected_index?,
  trials_sharpe_variance, expected_max_sharpe, deflated_sharpe}`)`. Sensitive to every computed
  value and to trial order.
- `campaign_id = sha256`, NUL-joined, in order: `campaign/1`, `campaign_engine_version_id`,
  `name`, `spec_version`, each trial's `(walk_forward_id, result_hash)` in request order
  (transitive pin, CE-1), the shared `schedule_id`, `benchmark_sharpe`, and `campaign_result_hash`.
- `research_result_id` aliases `campaign_id`.

**Folds (change identity):** engine + method + decimal-context + **moment + normal-primitive**
versions; the declared request (name, spec version, ordered trial ids, baseline `SR*`); each
trial's `result_hash` (transitive pin through WF→PO→FR→factors→corpus); the computed answer.
**Does NOT fold:** the record format version (container concern); inherited corpus pins
(surfaced via `pin_mismatch`); presentation, wall-clock, RNG, `id()`, or iteration order (trials
carry explicit request-order indices).

---

## 14. Determinism / Decimal Rules

- All arithmetic under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); volatility
  via `Decimal.sqrt(context)`. **No float anywhere**, no RNG, no wall-clock, no bootstrap.
- **`Φ` (standard-normal CDF)** is computed as an exact-`Decimal` series (e.g. the Maclaurin
  series of `erf`, or a complementary continued fraction for large `|x|`) evaluated under the
  context, with an **exact termination rule**: stop when the next term rounds to `0` at the
  context precision (plus a hard maximum-term cap that is never reached for the argument range
  the DSR produces). Deterministic and reproducible to prec-34 — the `Decimal.sqrt` precedent.
- **`Z⁻¹` (inverse CDF)** is a **fixed-iteration monotone bisection** on `Φ` over a closed
  bracket `[−k, +k]` (`k` chosen so `Φ(−k)` underflows the target quantile range for all
  `N ≤ N_MAX`), iterated a fixed number of times sufficient for prec-34, with an exact bracket
  test. It terminates deterministically for every input — categorically unlike the constrained-QP
  iteration P21 rejected (§9).
- **`γ` (Euler–Mascheroni)** is a documented 34-digit `Decimal` constant, not a computation.
- Same trial set + same baseline `SR*` → same `campaign_id` and byte-identical payload on any
  machine. A repeated evaluation is a byte-identical no-op (store idempotence).

---

## 15. Failure / UNDEFINED Semantics

Follows the established split — **defects raise, data conditions are recorded.**

**Raised** (`CampaignConfigurationError` / `CampaignConsistencyError`):
- Malformed spec (empty `name`/`spec_version`; `< 2` or `> N_MAX` trials; duplicate/empty trial
  id; unparseable `benchmark_sharpe`). *(configuration)*
- A non-`ResearchCampaignSpecification` argument. *(configuration)*
- Any `trial_id` absent; a payload that is not a `WalkForwardEvaluation`; a resolved-id
  disagreement; a trial whose roll-up `status` is not `REALIZED` (an UNDEFINED walk has no OOS
  series to correct). *(consistency, CE-1)*
- Trials that are not commensurable — more than one distinct `schedule_id` **or** more than one
  `factor_portfolio_engine_version_id` across the set. *(consistency, CE-3)*

**Recorded as first-class `UNDEFINED` (never raised, never fabricated, never repaired — CE-4):**
- A trial with `< 2` OOS periods → `TrialStatus.UNDEFINED`, reason `INSUFFICIENT_OOS_PERIODS`
  (Sharpe/skew/kurtosis/PSR all UNDEFINED); excluded from selection and from `V[SR]`.
- A trial with zero OOS population dispersion → `ZERO_OOS_VARIANCE`; same treatment.
- Fewer than `MIN_VALID_TRIALS = 2` VALID-Sharpe trials → `trials_sharpe_variance`,
  `expected_max_sharpe`, `deflated_sharpe`, and `selected_label` are UNDEFINED with reason
  `INSUFFICIENT_VALID_TRIALS`. The record is still sealed and persisted (the per-trial table is
  informative even when the campaign statistic is undefined).

**Surfaced, never raised (inherited D-PIN convention):** a non-singular corpus-pin set carried
from the referenced trials → `pin_mismatch = True`.

Note the deliberate asymmetry (★2): the *search size* `N = n_trials` counts **all submitted
trials, valid or not**, because every trial submitted was genuinely "tried" — under-counting `N`
would under-deflate the best Sharpe, defeating the phase's purpose (CE-5). The *dispersion*
`V[SR]` uses only VALID trials (an UNDEFINED Sharpe carries no value to include).

---

## 16. Persistence

Zero new store types. `ResearchCampaignEvaluation` is a `ResearchRecord` written write-once to
the existing `<root>/research/` sidecar via `ResearchResultStore.write`. Idempotent:
re-evaluating an identical spec is a byte-identical no-op; a differing payload under an existing
id fails closed via the store's guard. `from_dict` is the fail-closed inverse; derived ids are
re-computed, never read from state, so `from_dict(to_dict(r))` re-emits identical bytes and a
tampered stored id is ignored. It stores **no** copy of any trial's OOS series or corpus — only
the transitive `(walk_forward_id, result_hash)` references, the shared `schedule_id`, the carried
pins, the per-trial statistic table, and the campaign-level `V[SR]`/`SR₀`/`DSR`.

---

## 17. Testing Strategy

New `tests/campaign/` (`__init__.py`, `builders.py`, `test_spec.py`, `test_normal.py`,
`test_moments.py`, `test_compute.py`, `test_identity.py`, `test_result.py`, `test_engine.py`),
offline and synthetic. As in `tests/walkforward`, builders **synthesize** `N` sealed
`WalkForwardEvaluation`s (each over a synthesized optimization→risk-model→factor chain) directly
from hand-chosen OOS return series persisted to a real sidecar, giving exact control over per-trial
Sharpe/skew/kurtosis, commensurability, and degeneracy while exercising the true resolve → verify
→ per-trial → cross-trial → seal path.

- **Normal primitive** (`test_normal`, the ★1 surface) — `Φ` against hand-computed reference
  values at known points (`Φ(0)=0.5`, symmetry `Φ(−x)=1−Φ(x)`, monotonicity), to prec-34;
  `Z⁻¹` round-trips `Φ(Z⁻¹(p)) == p` to a stated tolerance; determinism of repeated evaluation;
  behaviour at the argument range the DSR actually produces; the exact-termination rule halts.
- **Moments** (`test_moments`) — hand-computed per-period Sharpe/skew/kurtosis on tiny series
  under the pinned context; agreement with the `analytics` definitions (if composed); UNDEFINED
  on `n<2` and zero-variance.
- **Compute core** (`test_compute`) — hand-computed `V[SR]`, `SR₀`, `DSR` on a tiny `N=3`
  campaign; the selection argmax + tie-break (lowest index); the `N`-counts-all-trials rule
  (★2) vs `V[SR]`-uses-valid-only; DSR monotonic in `N` (more trials → lower DSR, all else
  equal) and in skew/kurtosis (fatter/left-tailed → lower PSR); UNDEFINED campaign statistics
  when `#VALID < 2`.
- **Spec validation** — minimal request; canonical payload; every fail-closed path (empty
  fields; `<2`/`>N_MAX` trials; duplicate ids; bad `benchmark_sharpe`).
- **Identity** — `campaign_id` fold + per-input sensitivity (engine version, name, trial ids,
  each trial's `result_hash`, `schedule_id`, `benchmark_sharpe`, result hash); moment + normal
  version folding; `campaign_result_hash` per-block + order sensitivity (reordering trials
  changes the id).
- **Result** — byte-identical `to_dict`/`from_dict`; derived-id survival; `research_result_id`
  alias; `pin_mismatch`; ex-post boundary (no `pit`/`as_of` accessor; not a `BacktestResult`);
  tampered-id ignored; differing-answer id sensitivity.
- **Engine end-to-end** — a multi-trial known DSR; CE-1 reference verification (missing /
  non-`WalkForwardEvaluation` / id-mismatch / non-REALIZED trial each fail closed); CE-3
  commensurability failures (mixed `schedule_id` / engine version); UNDEFINED trials excluded
  from selection/dispersion; persistence + round-trip; idempotent re-eval;
  two-independent-workspaces agreement; `pin_mismatch` surfaced; `campaign_engine` wiring cached.
- `tests/test_smoke.py` — additive export assertion.

Quality gate identical to prior phases: `ruff check` / `ruff format --check` / `mypy src tests`
/ `pytest -q` and `pytest -q -p no:randomly`, all green; **zero runtime dependencies**.

---

## 18. Documentation Impact

*After* implementation and a green gate (never before):
- **New:** `docs/phase23-research-campaign-evaluation-locked.md` (reflecting the actual build +
  any disclosed deviations).
- **Update:** `README.md` (capability bullet + v0.20.0 row + Next), `ARCHITECTURE.md` (a
  "Research-campaign evaluation" row + phase-count bump to 1–23), `docs/index.md` (Phase 23
  entry + Status → Phases 1–23), `docs/data-model.md §12` (append the **CE-1..CE-6** block;
  additive, weakening nothing).

This proposal modifies **none** of those files.

---

## 19. Approval-Gated Decisions

Mark ★ = load-bearing (materially shapes identity, semantics, or scope).

1. ★★ **Introduce a deterministic exact-`Decimal` normal-CDF `Φ` and inverse `Z⁻¹`
   primitive** (new `campaign/normal.py`, **not** `_linalg`). This is the single largest
   decision: it is the only genuinely new numerical surface, and it is what makes the DSR
   possible. Determinism argument in §9/§14 (the `Decimal.sqrt` precedent; exact termination;
   `γ` as a documented constant; bisection ≠ constrained-QP iteration). **Fallback (§7 A′):** if
   the reviewer declines to introduce `Φ`, ship a **comparison-only v1** (ranked per-trial
   Sharpe/skew/kurtosis + `N` + `V[SR]`, **no PSR/DSR**), deferring the correction to a later
   phase on the same campaign artifact. *Approve introducing `Φ`/`Z⁻¹`, or select the fallback.*
2. ★ **Search-size convention `N`.** `N` counts **all submitted trials** (valid or UNDEFINED),
   not just valid ones — under-counting would under-deflate the best Sharpe and defeat the
   phase (CE-5). `V[SR]` uses valid trials only. *Approve the `N`-counts-all / `V`-uses-valid
   asymmetry, and the argmax tie-break (lowest request index).*
3. ★ **Compose vs inline the skew/kurtosis moments.** Recommend **compose** the exact-`Decimal`
   moment definitions from `analytics/compute.py` and fold their method version (§13); fallback
   is a self-contained `campaign-method/1` moment computation (no edit to `analytics`). *Approve
   compose-vs-inline.*
4. ★ **Input artifact = an ordered set of sealed `WalkForwardEvaluation`s.** Alternative:
   consume `FactorPortfolio`/`SignalDiagnostics`/`CrossSectionalRegression` t-stats directly.
   Recommend `WalkForwardEvaluation` — it is the newest terminal leaf, its Sharpe is
   **out-of-sample** (the only defensible input for a selection-bias correction), and it gives
   maximal transitive pinning (CE-1). *Approve the input type.*
5. ★ **`N_MAX` and `MIN_VALID_TRIALS`.** Recommend `MIN_VALID_TRIALS = 2` and `N_MAX = 64`
   (a real search is dozens of trials; `Z⁻¹(1 − 1/(N·e))` stays well-bracketed for `N ≤ 64`).
   *Approve the floors/caps.*
6. ★ **Commensurability rule (CE-3).** Require one shared `schedule_id` **and** one
   `factor_portfolio_engine_version_id` across trials; corpus-pin difference surfaced, not raised.
   Alternative: allow arbitrary trials (weaker null). *Approve the shared-schedule requirement.*
7. ★ **Baseline `SR*` for PSR** is a spec field defaulting to `"0"` (per-period). *Approve the
   field + default.*
8. ★ **Per-period (not annualized) Sharpe + moments** are re-derived from `oos_returns` +
   `risk_free_per_period` (the DSR is defined on per-period statistics), **not** taken from the
   sealed `summary.annualized_sharpe`. *Approve re-derivation.*
9. **PSR/DSR formula + moment convention** — PSR uses non-excess kurtosis `γ₄` (so
   `(γ₄−1)/4`); the `analytics` method seals *excess* kurtosis (`γ₄−3`), converted as
   `γ₄ = excess + 3`. *Approve the exact formula + conversion.*
10. **Fold the composed moment + normal-primitive versions into engine identity** (§13).
    *Approve.*
11. **UNDEFINED reason vocabulary** = `{INSUFFICIENT_OOS_PERIODS, ZERO_OOS_VARIANCE,
    INSUFFICIENT_VALID_TRIALS}` (closed). *Approve.*
12. **Naming** — package `campaign`; types `ResearchCampaignSpecification` /
    `ResearchCampaignEvaluation`; engine `ResearchCampaignEngine.evaluate`; property
    `campaign_engine`; domain tags `campaign/1`, `campaign-engine/1`, `campaign-method/1`,
    `campaign-normal/1`. *Approve names.*
13. ★ **Version = v0.20.0.** *Approve.*
14. **Sealed campaign outputs** = per-trial statistic table + selected label + `V[SR]` + `SR₀`
    + `DSR`. Pairwise horse-race (paired-difference OOS t-stats between the best and each other)
    is **out of scope for v1** (§22) — it needs cross-trial return alignment and is a separate
    capability. *Approve the v1 output set.*

No decision on this list is silently pre-made; each is surfaced for approval.

---

## 20. New Invariants (proposed, phase-local — not added to the global catalog now)

Naming follows the established convention (SD-/XS-/P19-/FR-/PO-/WF-). These would be added to
`docs/data-model.md §12` **only at implementation time**, additively — they do not weaken 1–30.

- **CE-1. Reference verification and transitive pinning.** The campaign resolves each referenced
  `walk_forward_id` from the shared sidecar, re-verifies that the resolved record's
  `research_result_id` equals the requested id and that its roll-up `status` is `REALIZED`, and
  folds each trial's sealed `result_hash` (in request order) into `campaign_id` — so the
  campaign's identity is transitively sensitive to any change in any trial, its recipe, risk
  model, factors, or corpora. Any missing / non-decoding / id-mismatched / non-REALIZED trial
  fails closed. *(The FR-1 / PO-1 / WF-1 discipline, one layer up.)*
- **CE-2. A campaign evaluation is not a PIT value and not a `BacktestResult`.**
  `ResearchCampaignEvaluation` is a meta-statistic of ex-post OOS series and is itself ex-post;
  it is not a `Pit*` type, exposes no as-of accessor (`boundary_kind="pit"` documents only the
  underlying PIT walks), is a distinct record type, and simulates no fills / cash / positions /
  costs. *(The WF-3 / PO-2 / PO-5 discipline, one layer up.)*
- **CE-3. Commensurability, fail closed; pins surfaced.** Every referenced trial must share one
  exact `schedule_id` **and** one `factor_portfolio_engine_version_id` (the trials are OOS
  evaluations on the same rebalance calendar, produced by one factor-construction engine logic);
  a difference is raised, never silently aligned. A corpus-pin difference across trials is **not**
  raised — it is carried and surfaced as `pin_mismatch`. *(The FR-3 convention, adapted to a set
  of walk-forwards.)*
- **CE-4. Fail-closed degeneracy, never repaired.** A trial with fewer than two OOS periods or
  zero OOS dispersion is a recorded `UNDEFINED` trial cell (Sharpe/skew/kurtosis/PSR UNDEFINED
  together), excluded from selection and from `V[SR]` — never a divide-by-zero, fabricated `0`,
  or dropped-silently trial. A campaign with fewer than `MIN_VALID_TRIALS = 2` valid-Sharpe
  trials records `V[SR]` / `SR₀` / `DSR` / selection as `UNDEFINED` (`INSUFFICIENT_VALID_TRIALS`);
  the record still seals. *(The XS-4 / P19-4 / FR-4 / PO-4 / WF-4 posture, adapted to trials.)*
- **CE-5. Honest selection-bias accounting.** The deflated statistic **must** fold the search
  size `N` (= the count of *all* submitted trials, valid or not) and the trials-Sharpe dispersion
  `V[SR]` into the correction, and the reported `DSR` is the significance of the **selected
  (max-Sharpe)** trial. `N` is never under-counted; the correction is never omitted when it is
  computable. *Necessary because the entire point of the phase is to prevent the under-correction
  that inflates the best-of-N Sharpe (§5.1); silently dropping trials from `N` would re-create
  the bias.*
- **CE-6. Single methodology source; deterministic transcendentals; no fabricated inputs.** The
  correction uses one method (PSR/DSR) with the composed exact-`Decimal` moment definitions and
  the phase-local `Φ`/`Z⁻¹` primitive (all versions folded into engine identity); no second
  moment estimator, no shrinkage, no bootstrap/RNG, no expected-return / benchmark input beyond
  the declared `SR*`. `Φ` and `Z⁻¹` are computed under the pinned context with an exact
  termination rule (§14); `γ` is a documented constant. *(The WF-5 / PO-3 discipline, extended to
  cover the new numerical primitive.)*

---

## 21. Proposed Files (implementation stage only — none created now)

```
src/quantforge/campaign/__init__.py
src/quantforge/campaign/errors.py
src/quantforge/campaign/version.py
src/quantforge/campaign/normal.py        ← the one new numerical primitive (★1)
src/quantforge/campaign/model.py
src/quantforge/campaign/spec.py
src/quantforge/campaign/moments.py
src/quantforge/campaign/compute.py
src/quantforge/campaign/result.py
src/quantforge/campaign/identity.py
src/quantforge/campaign/engine.py

tests/campaign/__init__.py
tests/campaign/builders.py
tests/campaign/test_spec.py
tests/campaign/test_normal.py
tests/campaign/test_moments.py
tests/campaign/test_compute.py
tests/campaign/test_identity.py
tests/campaign/test_result.py
tests/campaign/test_engine.py

docs/phase23-research-campaign-evaluation-locked.md   (post-implementation)
```

Additive edits at implementation stage: `src/quantforge/workspace.py` (+`campaign_engine`),
`src/quantforge/__init__.py` (2 re-exports), `tests/test_smoke.py` (1 assertion), and the §18
doc updates. **None of these is created or edited by this proposal.**

---

## 22. Out of Scope (strict)

- **Any resampling / bootstrap / permutation test** (White's Reality Check, Hansen's SPA,
  Monte-Carlo PBO) — requires an RNG; forbidden by invariant 21. v1 is the closed-form parametric
  DSR only.
- **Bonferroni / Holm / Benjamini–Hochberg FDR over arbitrary t-stats** — a separate future
  meta-analysis on the same campaign artifact; v1 is the single best-of-N DSR/PSR statistic.
- **Pairwise horse-race / paired-difference OOS t-stats** between trials — needs cross-trial
  return alignment; a separate future capability (§19.14).
- **Minimum-track-record-length, probability-of-backtest-overfitting (combinatorial CV)** — later
  additions on the campaign grouping.
- **Consuming heterogeneous record types** (mixing `FactorPortfolio` / `SignalDiagnostics` /
  `WalkForwardEvaluation` in one campaign) — v1 is homogeneous `WalkForwardEvaluation` trials
  (CE-3).
- **Mean-variance / max-Sharpe / constrained optimization / risk attribution** — blocked by a
  missing PIT-safe `μ`, by determinism, or by GMV tautology (§7 C/D/E).
- **Shrinkage / EWMA / robust covariance** — would expand Phase 20's estimator (§7 G).
- **Report-scope extension** — presentation convenience, not research (§7 F).
- **Any modification to Phase 12/19/20/21/22 vocabulary, engine, or identity; any `_linalg`
  change; any new store, database, PIT surface, data source, UI, or runtime dependency.**
- **Any PIT-eligible / tradable output** — the evaluation is ex-post only (CE-2).

---

## 23. Version

Phase 20 = v0.17.0, Phase 21 = v0.18.0, Phase 22 = v0.19.0 (each phase a `+0.01.0` minor bump;
confirmed by the README release table **and** git tags — `git tag` shows `v0.19.0` as the latest
and there is no `v0.20.0`). **Phase 23 releases as `v0.20.0`.** Domain tags: `campaign/1`
(record), `campaign-engine/1` (engine), `campaign-method/1` (method), `campaign-normal/1`
(the `Φ`/`Z⁻¹` primitive).

---

## 24. Open Questions

1. **`Φ` implementation shape** — Maclaurin `erf` series (accurate near `0`, slow in the tails)
   vs a complementary continued fraction for large `|x|` vs a hybrid. The DSR argument range is
   modest (`|x|` rarely exceeds ~5 for `N ≤ 64`), so a hybrid with an exact term-cap is
   recommended. *(Resolve during implementation; does not change the public shape; §19 ★1.)*
2. **`Z⁻¹` bracket `k` and iteration count** — choose `k` and the fixed bisection depth so the
   result is exact to prec-34 for all `N ≤ N_MAX`. *(§14; does not change the public shape.)*
3. **Compose vs inline moments** — are `analytics`' skew/kurtosis functions cleanly importable
   as pure window-agnostic functions, or entangled with `AnalyticsEngine`? If entangled, declare
   a self-contained `campaign-method/1` moment computation (no edit to `analytics`). *(§19 ★3.)*
4. **`benchmark_sharpe` scale** — per-period (recommended, matches the per-period DSR) vs
   annualized-then-converted. *(§19.7/§19.8.)*
5. **Selected-trial reporting** — seal the selected trial's **label** and request-index
   (recommended) so a reader can trace it back to the specific `walk_forward_id`. *(§19.14.)*
6. **`N_MAX` exact value** — `64` proposed; a larger cap widens the `Z⁻¹` tail bracket. *(§19 ★5.)*

---

## Final Recommendation

Implement **Phase 23 = Out-of-Sample Research-Campaign Evaluation with Selection-Bias
Correction** as specified above: a pure-consumer, ex-post, content-addressed
`ResearchCampaignEvaluation` that references an ordered set of `N` sealed `WalkForwardEvaluation`
trials, re-derives each trial's per-period OOS Sharpe / skew / kurtosis / length from its sealed
`oos_returns`, and computes the **Probabilistic and Deflated Sharpe Ratios** — correcting the
best-of-`N` OOS Sharpe for the size of the search and the non-normality of returns — at
**v0.20.0**, composing the existing exact-`Decimal` moment definitions, introducing exactly one
new deterministic numerical primitive (`Φ`/`Z⁻¹`, §19 ★1, with a comparison-only fallback),
changing no prior phase and no `_linalg`, and preserving every existing invariant while adding
CE-1..CE-6.

It is the **first genuine consumer of Phase 22**, the project's first **meta-analysis /
selection-bias** layer, and it builds precisely the **research-campaign grouping artifact** that
Phase 22 named as the prerequisite for the multiple-testing correction it deferred. It is
explicitly **not** mean-variance, constrained optimization, risk attribution, or a report-scope
extension — each of which the repository shows to be blocked by a missing PIT-safe `μ`, by
determinism, by GMV tautology, or by being a presentation convenience.

**Awaiting explicit approval before any implementation.**
