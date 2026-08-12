# Phase 23 — Out-of-Sample Research-Campaign Evaluation with Selection-Bias Correction (LOCKED)

> **Status:** Locked normative specification. The Phase 23 proposal was **approved as
> recommended** ("approved go ahead") — the recommended capability (§7 A, not the §7 A′
> comparison-only fallback): introduce the deterministic exact-`Decimal` standard-normal
> `Φ` / `Z⁻¹` primitive (★1), consume an ordered set of `N` sealed `WalkForwardEvaluation`
> trials, and seal the **Probabilistic** and **Deflated Sharpe Ratios** of the best OOS
> strategy. This document reflects the **actual implementation** and is the source of
> truth; it supersedes the recommendations in
> [phase23-research-campaign-evaluation-proposal.md](phase23-research-campaign-evaluation-proposal.md).
> Every conditional reference in the proposal ("recommended", "approval-gated") is resolved
> here to a committed decision, and the proposal's open questions (§24) are resolved in §1.1.
>
> **One-line thesis:** Phase 23 adds a deterministic, content-addressed **research-campaign
> evaluation** — the first genuine *consumer* of the Phase 22 terminal leaf and the
> project's first *meta-analysis / selection-bias* layer. Given a declarative
> `ResearchCampaignSpecification` naming an ordered set of `2..N_MAX` sealed
> `WalkForwardEvaluation` records (the *trials* of one research campaign) plus a per-period
> benchmark Sharpe `SR*`, `ResearchCampaignEngine.evaluate(...)` resolves each trial from
> the shared Phase 8 research sidecar, re-verifies it (and, transitively, its optimization →
> risk model → factors → corpora) and that it is `REALIZED`, enforces that the trials are
> **commensurable** (one shared `schedule_id` **and** one `factor_portfolio_engine_version_id`),
> re-derives from each trial's sealed `oos_returns` the per-period OOS **Sharpe**, **skew**,
> and **non-excess kurtosis** and the **Probabilistic Sharpe Ratio** `PSR(SR*)`, then across
> the campaign computes the search size `N`, the population **variance of the valid trials'
> Sharpe ratios**, the **expected-maximum Sharpe under the null** `SR₀`, and the headline
> **Deflated Sharpe Ratio** `DSR = PSR(SR₀)` of the selected (max-Sharpe) trial. It seals a
> `ResearchCampaignEvaluation` `ResearchRecord` write-once to the existing sidecar. It
> introduces exactly **one** new numerical primitive (a phase-local exact-`Decimal` `Φ`/`Z⁻¹`,
> **not** an `_linalg` change), **no** new data source, **no** new store, **no** runtime
> dependency, **no** new PIT surface, and **no** modification to any prior phase's vocabulary,
> engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **The one honest way to report the best of many OOS results: a selection-bias-corrected significance.** Given an ordered set of sealed OOS trials, re-derive each trial's per-period OOS Sharpe/skew/kurtosis + PSR, select the max-Sharpe trial, and deflate its significance for the size of the search (DSR). **No** bootstrap/permutation test (needs an RNG, invariant 21), **no** Bonferroni/Holm/BH-FDR over arbitrary t-stats, **no** pairwise horse-race, **no** minimum-track-record-length or combinatorial PBO, **no** heterogeneous trial types — each deferred or rejected with a grounded reason (§7 of the proposal). It performs **no execution** and is **not** a `BacktestResult` (CE-6). |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 22.** It resolves an ordered set of `2..N_MAX` already-sealed `WalkForwardEvaluation` records (the trials) from the shared sidecar, and transitively their optimization → risk model → factors → corpora. It reads **no** raw corpus, fabricates **no** expected-return / `μ`, and **modifies no** prior-phase vocabulary, engine, or identity. It is the first functional consumer of the Phase 22 terminal leaf. |
| **D-NORMAL** | **Introduce a deterministic exact-`Decimal` `Φ` / `Z⁻¹` primitive (★1), phase-local in `campaign/normal.py`, not in `_linalg`.** `Φ(x) = ½·(1 + erf(x/√2))`, with `erf` summed by its **all-positive-term** series `erf(z) = (2/√π)·e^{−z²}·Σₖ 2ᵏ z^{2k+1}/(1·3···(2k+1))` (no catastrophic cancellation), under a working context carrying `_GUARD_DIGITS = 12` extra digits, then rounded back and clamped to `[0, 1]`. `Z⁻¹(p)` for `p ∈ (0,1)` is a **fixed-iteration** (`_PPF_ITERATIONS = 240`) monotone bisection of `Φ` on the closed bracket `[−50, +50]` — no data-dependent early exit, so it is a pure function of `p` and the context. `π` (60-digit) and the Euler–Mascheroni `γ` (`EULER_MASCHERONI`, 50-digit) are documented `Decimal` literals, never truncated series. `_ERF_MAX_TERMS = 10 000` is an unreachable fail-closed backstop. `Decimal.sqrt`/`Decimal.exp` are correctly-rounded per the General Decimal Arithmetic Spec, so every value is bit-identical on any platform. The §7 A′ comparison-only fallback was **not** taken. |
| **D-MOMENTS** | **Inline a self-contained `campaign-method/1` moment computation (deviation, §1.1; proposal ★3 fallback).** `campaign/moments.py` computes the per-period excess-return mean, **population** variance/volatility (divisor `n`), per-period Sharpe `μ/σ`, skew `m₃/σ³`, and **non-excess** kurtosis `m₄/σ⁴` directly in exact `Decimal` — it does **not** import `analytics/compute.py`, whose moment functions are not cleanly importable as window-agnostic pure functions. No prior package is edited. |
| **D-PSR/DSR** | **The pinned López de Prado formulas (`campaign-method/1`).** Per trial: `PSR(SR*) = Φ( (SR − SR*)·√(n−1) / √(1 − γ₃·SR + ((γ₄−1)/4)·SR²) )`, with `γ₄` the **non-excess** kurtosis. Cross-trial: `SR₀ = √V·[(1−γ)·Z⁻¹(1 − 1/N) + γ·Z⁻¹(1 − 1/(N·e))]` where `V` is the **population** variance of the valid trials' Sharpe ratios, `γ` is Euler–Mascheroni, `e = exp(1)`; and `DSR = PSR(SR₀)` of the selected trial. Statistics are **per-period**, re-derived from `oos_returns` + each trial's inherited `risk_free_per_period` — **never** taken from the sealed `summary.annualized_sharpe`. |
| **D-N** | **The search size `N` counts *all* submitted trials, valid or not (CE-2); the dispersion `V` uses valid trials only.** Every trial submitted was genuinely tried; under-counting `N` would under-deflate the best Sharpe and defeat the phase. An UNDEFINED trial carries no Sharpe to include in `V`. The selection is `argmax` over valid Sharpe ratios, ties broken by the **lowest request index** (order-deterministic). |
| **D-COMMENSURABLE** | **Commensurability is required and fail-closed (CE-3): one shared `schedule_id` *and* one `factor_portfolio_engine_version_id` across all trials.** Otherwise the OOS Sharpe ratios are not drawn from one comparable search and the correction is meaningless; a disagreement raises `CampaignConsistencyError`. A corpus-pin **difference** across trials is **not** raised — it is carried as the sorted distinct union and surfaced as `pin_mismatch` (the D-PIN convention). |
| **D-DEGENERACY** | **Fail-closed, UNDEFINED-preserving, never repaired (CE-4).** A trial with `< 2` OOS periods → `INSUFFICIENT_OOS_PERIODS`; a trial with zero OOS population variance → `ZERO_OOS_VARIANCE`; a trial whose PSR estimator variance `1 − γ₃·SR + ((γ₄−1)/4)·SR²` is non-positive → `DEGENERATE_SHARPE_ESTIMATOR` (a razor-edge guard, §1.1). An UNDEFINED trial contributes no Sharpe to selection or `V`, but is retained in the sealed table with its reason — never a divide-by-zero, fabricated `0`, or silently dropped trial. A campaign with fewer than `MIN_VALID_TRIALS = 2` valid trials records the selection / `V` / `SR₀` / `DSR` as UNDEFINED `INSUFFICIENT_VALID_TRIALS`; **the record still seals**. |
| **D-EXPOST** | **The output is ex-post, never PIT (CE-6).** A selection-bias-corrected significance over realized OOS Sharpe ratios is ex-post. `ResearchCampaignEvaluation` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` documents only that the *underlying trials were PIT walks*; it never claims the campaign statistic is a PIT value. Set unconditionally, so **no new PIT resolution** is introduced. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order (CE-5).** All arithmetic — moments, `Φ`/`Z⁻¹`, the `V` population variance, the `SR₀` weighting — runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`). Canonical cell strings are `str(+value)` produced *inside* the pinned context. The engine version folds the decimal context **and** the composed method + normal-primitive versions, so a change to any yields a new, distinguishable engine id. |
| **D-INVARIANTS** | **CE-1..CE-6 are documented both as phase-local invariants here and as a small additive `data-model.md §12` block** mirroring the SD-/XS-/P19-/FR-/PO-/WF- blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.20.0`** (Phase 22 = v0.19.0, confirmed by git tags). Domain tag `campaign/1`; engine-version string `campaign-engine/1`; method string `campaign-method/1`; normal-primitive string `campaign-normal/1`; record-format string `campaign-result/1`; `N_MAX = 64`, `MIN_VALID_TRIALS = 2`. The package `__version__` string is unchanged (versioning is by content-addressed ids, not a semver string). Any pre-existing README version-label drift is **not** fixed here. |

### 1.1 Deviations from the proposal (disclosed) & open questions resolved

Recorded for auditability; none changes an identity discipline or weakens an invariant.

- **Moments inlined, not composed (proposal ★3 / §19.3, resolved to the fallback).** The
  proposal recommended *composing* `analytics/compute.py`'s skew/kurtosis and folding its
  version, with a self-contained `campaign-method/1` computation as the fallback if those
  functions were "entangled with `AnalyticsEngine`". They are not cleanly importable as
  window-agnostic pure functions, so the fallback was taken: `moments.py` computes the
  moments itself. Consequence: the engine identity folds `campaign-method/1` and
  `campaign-normal/1` (no `analytics` moment version to fold), exactly as §13 of this doc
  states.
- **A fourth UNDEFINED reason `DEGENERATE_SHARPE_ESTIMATOR` (proposal §19.11 closed set was
  three).** The proposal's closed vocabulary was `{INSUFFICIENT_OOS_PERIODS,
  ZERO_OOS_VARIANCE, INSUFFICIENT_VALID_TRIALS}`. Implementation adds a fourth,
  `DEGENERATE_SHARPE_ESTIMATOR`, recorded when the PSR estimator variance is non-positive.
  It is mathematically `≥ 0` for any valid moment set (the skew–kurtosis inequality
  `γ₄ ≥ 1 + γ₃²`) and so is reachable only in razor-edge degeneracies; it is retained as a
  fail-closed guard rather than a square-root-of-negative or divide-by-zero. The vocabulary
  remains closed — now with four members.
- **CE-numbering differs from the proposal §20.** The implemented invariant numbering (used
  throughout the source and in §9 below) is: **CE-1** reference verification + transitive
  pinning; **CE-2** honest search-size `N` (all submitted trials); **CE-3** commensurability;
  **CE-4** fail-closed degeneracy; **CE-5** single methodology source + deterministic
  transcendentals; **CE-6** not a PIT value / not a `BacktestResult`. The proposal §20 had
  swapped CE-2/CE-5/CE-6. This document and `data-model.md §12` use the implemented numbering.
- **Spec field named `benchmark_sharpe` (default `"0"`, per-period).** The `SR*` of the
  formulas is the request's `benchmark_sharpe` (proposal §19.7/§19.8 resolved: per-period,
  re-derived statistics).
- **Open questions (proposal §24) resolved:** (1) `Φ` shape = the all-positive-term `erf`
  series + `Φ = ½(1+erf(x/√2))` (accurate and cancellation-free over the DSR argument
  range); (2) `Z⁻¹` bracket `k = 50`, `240` fixed bisection iterations (halves to below
  `10⁻⁶⁰`, past any working precision); (3) moments inlined (above); (4) `benchmark_sharpe`
  per-period; (5) the selected trial's `trial_k` label is sealed in the summary; (6)
  `N_MAX = 64`.

---

## 2. What was built

New package **`src/quantforge/campaign/`** (mirrors the P20/P21/P22 layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `CampaignError` → `CampaignConfigurationError`, `CampaignConsistencyError`. |
| `version.py` | `CampaignEngineVersion` (folds the pinned decimal context + `campaign-method/1` + `campaign-normal/1` into `config_hash`); constants `CAMPAIGN_SPEC_VERSION`/`CAMPAIGN_ENGINE_VERSION`/`CAMPAIGN_METHOD_VERSION`/`CAMPAIGN_NORMAL_VERSION`; `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `normal.py` | **The one new numerical primitive (★1):** `standard_normal_cdf` (`Φ`), `standard_normal_ppf` (`Z⁻¹`), `EULER_MASCHERONI`. Pure, float-free, reads no store, **not** in `_linalg`. |
| `model.py` | `TrialStatus` (`VALID`/`UNDEFINED`); `StatStatus`; the **closed** `CampaignUndefinedReason` (four members, §1.1); `StatValue` (KNOWN decimal string \| UNDEFINED + reason); `trial_label(index) → "trial_{index+1}"`. |
| `spec.py` | `ResearchCampaignSpecification` (declarative request; fail-closed validation); `N_MAX = 64`, `_MIN_TRIALS = 2`. |
| `moments.py` | Self-contained exact-`Decimal` per-trial moments (`TrialMoments`, `trial_moments`). |
| `compute.py` | Pure PSR/DSR core: `probabilistic_sharpe`, `sharpe_dispersion`, `expected_max_sharpe`, `trial_statistics`, `campaign_statistics`; `MIN_VALID_TRIALS = 2`. |
| `result.py` | `ResearchCampaignEvaluation` (`ResearchRecord`; `seal`/`to_dict`/`from_dict`), `TrialStat`, `CampaignSummary`; `CAMPAIGN_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`. |
| `identity.py` | `campaign_result_hash`, `campaign_id`; domain tag `campaign/1`. |
| `engine.py` | `ResearchCampaignEngine.evaluate(spec)`. |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `workspace.py` — one lazy `campaign_engine` `@property` (+ private cache slot), following
   the `walk_forward_engine` template (typed `-> object`, deferred import).
2. `src/quantforge/__init__.py` — top-level re-exports of `ResearchCampaignSpecification`
   and `ResearchCampaignEvaluation`, added to the sorted `__all__`.
3. `tests/test_smoke.py` — one additive export assertion.

**No edit to** `_linalg`, `walkforward`, `optimization`, `factorrisk`, `factorportfolio`,
`analytics`, `backtest`, or any other prior-phase identity/vocabulary.

---

## 3. Data flow

```
ResearchCampaignSpecification { trial_ids[2..N_MAX], benchmark_sharpe="0", name, spec_version }
        │
        ▼  ResearchCampaignEngine.evaluate(spec)
resolve each WalkForwardEvaluation by id, in request order                 — fail closed (CE-1)
   store.read_as(id, WalkForwardEvaluation.from_dict); verify research_result_id == id;
   verify status is REALIZED; fold each trial's result_hash (transitive pin WF→PO→FR→…→corpus)
        │
        ▼
enforce commensurability: one shared schedule_id AND one                   — fail closed (CE-3)
   factor_portfolio_engine_version_id; carry sorted-distinct corpus pins (surface pin_mismatch)
        │
        ▼  per trial i (deterministic, exact-Decimal, under the pinned context):
   e_t = r_t − risk_free_per_period  over oos_returns              (per-period excess)
   μ, σ² = Σ(e−μ)²/n, σ = √σ²                                      (population; Decimal.sqrt)
   n < 2         → UNDEFINED (INSUFFICIENT_OOS_PERIODS)                              — CE-4
   σ == 0        → UNDEFINED (ZERO_OOS_VARIANCE)                                     — CE-4
   SR = μ/σ ; γ₃ = m₃/σ³ ; γ₄ = m₄/σ⁴  (non-excess kurtosis)
   PSR(SR*) = Φ( (SR − SR*)·√(n−1) / √(1 − γ₃·SR + ((γ₄−1)/4)·SR²) )    (None → DEGENERATE_…)
        │
        ▼  across trials:
   N = number of submitted trials             (the honest search size, incl. UNDEFINED — CE-2)
   V = population variance of { SR_i : VALID }                                       — CE-4
   #VALID < MIN_VALID_TRIALS (2) → V / SR₀ / DSR / selection UNDEFINED (INSUFFICIENT_VALID…) — CE-4
   selected = argmax_i SR_i  (tie → lowest index)                                    — D-N
   SR₀ = √V · [ (1−γ)·Z⁻¹(1 − 1/N) + γ·Z⁻¹(1 − 1/(N·e)) ]                            — CE-5
   DSR = PSR_selected(SR₀)                                                            (headline)
        │
        ▼
ResearchCampaignEvaluation.seal(...)  →  ResearchResultStore.write (write-once, idempotent)
        │
        ▼
store.read_as(id, ResearchCampaignEvaluation.from_dict)   (byte-identical typed round-trip)
```

---

## 4. Public API

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

campaign.trials                   # tuple[TrialStat]: label, status, n, sharpe, skew, kurtosis, psr
campaign.summary.valid_trials     # count of trials with a defined Sharpe
campaign.summary.selected_trial   # "trial_k" of the max-Sharpe trial (None if undefined)
campaign.summary.selected_sharpe  # StatValue
campaign.summary.sharpe_dispersion    # V over VALID trials (StatValue)
campaign.summary.expected_max_sharpe  # SR₀ selection-bias threshold (StatValue)
campaign.summary.deflated_sharpe      # DSR = PSR(SR₀) of the selected trial (StatValue) ← headline
campaign.trial_ids                # referenced ids, request order
campaign.pin_mismatch             # inherited corpus-pin flag
campaign.research_result_id       # == campaign.campaign_id

again = ws.research_result_store.read_as(
    campaign.research_result_id, ResearchCampaignEvaluation.from_dict
)
```

`ResearchCampaignEngine` is reached only through `Workspace.campaign_engine` (lazy, cached,
`-> object`). `evaluate(spec) -> ResearchCampaignEvaluation` is the single entry point.

`ResearchCampaignSpecification` (frozen slots): `name`, `trial_ids` (`tuple[str, ...]`),
`benchmark_sharpe` (`str`, default `"0"`), `spec_version = "campaign/1"`. Construction-time
validation (fail closed): non-empty `name` / `spec_version`; `2 ≤ len(trial_ids) ≤ N_MAX`;
`trial_ids` a tuple, distinct and non-empty; `benchmark_sharpe` a parseable finite decimal.

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `campaign_engine_version_id = sha256(code_version "campaign-engine/1", config_hash)` where
  `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=campaign-method/1\x00normal=campaign-normal/1")`.
  Folding the method and normal-primitive versions makes the campaign's identity change if
  the moment/PSR/DSR method or the `Φ`/`Z⁻¹` implementation changes.
- `campaign_result_hash = sha256(canonical JSON over the ordered computed-output cells: each
  per-trial `{block:"trial", label, status, n, sharpe, skew, kurtosis, psr}` in request
  order, then the campaign cell `{block:"campaign", valid_trials, selected_trial,
  selected_sharpe, sharpe_dispersion, expected_max_sharpe, deflated_sharpe}`)`. Sensitive to
  every computed value and to trial order.
- `campaign_id = sha256`, NUL-joined, in order: `campaign/1`, `campaign_engine_version_id`,
  `name`, `spec_version`, the ordered `trial_ids` (canonical JSON array), `benchmark_sharpe`,
  the ordered trial `result_hash`es (canonical JSON array; transitive pin, CE-1), and
  `campaign_result_hash`.
- `research_result_id` aliases `campaign_id`. Derived ids are re-emitted by properties, never
  read from stored state — a tampered stored id is ignored and `from_dict(to_dict(r))`
  re-emits identical bytes. The record-format version is **not** folded (a container concern);
  inherited corpus pins are **not** folded (surfaced via `pin_mismatch`).

---

## 6. Determinism / Decimal rules

- All arithmetic under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`);
  volatility and `SR₀`'s `√V` via `Decimal.sqrt(context)`; `e = exp(1)` via `Decimal.exp`.
  **No float anywhere**, no RNG, no wall-clock, no bootstrap, no `id()`, no iteration-order
  dependence.
- `Φ` is a guarded exact-`Decimal` series with a relative negligibility stop plus the
  unreachable `_ERF_MAX_TERMS` backstop; clamped to `[0, 1]`. `Z⁻¹` is a fixed 240-iteration
  bisection over `[−50, +50]` (no data-dependent early exit). `γ` (50-digit) and `π`
  (60-digit) are documented literals.
- Same trial set + same `benchmark_sharpe` → same `campaign_id` and byte-identical payload on
  any machine. A repeated evaluation is a byte-identical no-op (store idempotence). Two
  independent workspaces over the same immutable sidecar agree.

---

## 7. Invariants (CE-1..CE-6)

Additive to `data-model.md §12`; these do not weaken invariants 1–30. See §8 there for the
canonical block; summarized here:

- **CE-1 — Reference verification and transitive pinning.** Each `trial_id` is resolved from
  the shared sidecar, re-verified (`research_result_id == id`, roll-up `status == REALIZED`),
  and its `result_hash` folded (in request order) into `campaign_id`; any missing /
  non-decoding / id-mismatched / non-REALIZED trial fails closed. *(The FR-1 / PO-1 / WF-1
  discipline, one layer up.)*
- **CE-2 — Honest selection-bias accounting.** The search size `N` is the count of **all**
  submitted trials (valid or UNDEFINED); the dispersion `V` uses valid trials only; the DSR
  is the significance of the **selected (max-Sharpe)** trial. `N` is never under-counted and
  the correction is never omitted when computable.
- **CE-3 — Commensurability, fail closed; pins surfaced.** All trials share one exact
  `schedule_id` **and** one `factor_portfolio_engine_version_id`; a difference is raised, a
  corpus-pin difference is carried and surfaced as `pin_mismatch`, never reconciled. *(The
  FR-3 convention, adapted to a set of walk-forwards.)*
- **CE-4 — Fail-closed degeneracy, never repaired.** A trial with `< 2` OOS periods, zero
  OOS dispersion, or a degenerate PSR estimator is a recorded UNDEFINED cell, excluded from
  selection and `V`; a campaign with `< MIN_VALID_TRIALS` valid trials records
  `V`/`SR₀`/`DSR`/selection UNDEFINED; the record still seals. *(The XS-4 / P19-4 / FR-4 /
  PO-4 / WF-4 posture, adapted to trials.)*
- **CE-5 — Single methodology source; deterministic transcendentals; no fabricated inputs.**
  One correction method (PSR/DSR) with the inlined exact-`Decimal` moments and the
  phase-local `Φ`/`Z⁻¹` (all folded into engine identity); no second moment estimator, no
  shrinkage, no bootstrap/RNG, no expected-return/benchmark input beyond the declared `SR*`.
  `Φ`/`Z⁻¹` run under the pinned context with a fixed termination; `γ` is a documented
  constant. *(The WF-5 / PO-3 discipline, extended to the new primitive.)*
- **CE-6 — A campaign evaluation is not a PIT value and not a `BacktestResult`.** It is a
  meta-statistic of ex-post OOS series and is itself ex-post; not a `Pit*` type, no as-of
  accessor (`boundary_kind="pit"` documents only the underlying PIT walks), a distinct record
  type, no fills/cash/positions/costs. *(The WF-3 / PO-2 / PO-5 discipline, one layer up.)*

---

## 8. Failure / UNDEFINED semantics

**Raised** — `CampaignConfigurationError`: a non-`ResearchCampaignSpecification` argument; a
malformed spec (empty `name`/`spec_version`; `< 2` or `> N_MAX` trials; non-tuple, duplicate,
or empty trial id; non-decimal/non-finite `benchmark_sharpe`). `CampaignConsistencyError`
(CE-1/CE-3): a `trial_id` absent; a payload that is not a `WalkForwardEvaluation`; a
resolved-id disagreement; a trial whose roll-up `status` is not `REALIZED`; trials that are
not commensurable.

**Recorded as first-class UNDEFINED** (CE-4, never raised): `INSUFFICIENT_OOS_PERIODS`,
`ZERO_OOS_VARIANCE`, `DEGENERATE_SHARPE_ESTIMATOR` (per trial); `INSUFFICIENT_VALID_TRIALS`
(campaign). **Surfaced, never raised:** `pin_mismatch` on a non-singular corpus-pin union.

---

## 9. Testing

`tests/campaign/` (offline, synthetic): `builders.py` synthesizes sealed
`WalkForwardEvaluation` trials directly from hand-chosen OOS return series (exact control over
per-trial Sharpe/skew/kurtosis, commensurability, and degeneracy) and persists them to a real
sidecar, exercising the true resolve → verify → per-trial → cross-trial → seal → persist path.
Suites: `test_spec`, `test_normal` (`Φ` reference values, symmetry, monotonicity, unit-clamp;
`Z⁻¹` round-trip and known quantile; determinism), `test_moments`, `test_compute`,
`test_identity`, `test_result`, `test_engine` (happy path, reproducibility, order-sensitivity,
benchmark effect, every CE-1/CE-3 fail-closed path, UNDEFINED handling, pin union). Plus a
`tests/test_smoke.py` export assertion. **Gate (all green): `ruff check` / `ruff format
--check` / `mypy src tests` / `pytest -q` / `pytest -q -p no:randomly`; zero runtime
dependencies.**
