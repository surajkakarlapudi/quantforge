# Phase 25 — Multiple-Comparison Correction: Capability Investigation & Design Proposal

**Status:** PROPOSAL ONLY. Not approved, not implemented, no source, no tests, no locked
spec. Proposes **v0.22.0**. Awaiting explicit approval before any implementation.

---

## 1. Thesis

Phase 24 (`StrategyComparison`, v0.21.0) seals an upper-triangle matrix of `N(N−1)/2`
pairwise paired-difference tests, each carrying a two-sided `p` value. That matrix is a
**family of simultaneous hypotheses**, but Phase 24 reports each `p` value in isolation:
it deliberately leaves multiplicity uncorrected. Its own normative spec flags this as the
intended next consumer (SC-7: whether a family-wise or false-discovery-rate adjustment is
applied "is left to a future consumer of this matrix"). Reading `N(N−1)/2` raw `p` values
and declaring the smallest ones "significant" is textbook data-dredging: with `N = 10`
strategies that is 45 simultaneous tests, and at least one `p < 0.05` is expected by chance
alone even when every strategy is identical.

**Phase 25 should be a Multiple-Comparison Correction layer** that consumes exactly one
sealed `StrategyComparison`, treats its KNOWN pairwise `p` values as a hypothesis family,
and seals family-wise-error (Holm) and false-discovery-rate (Benjamini–Yekutieli,
Benjamini–Hochberg) adjusted `p` values plus a rejection set at a declared significance
level `alpha`. This is a **pure deterministic transform of already-sealed decimal `p`
values** — a total-order sort plus closed-form monotone step thresholds plus exact-`Decimal`
comparisons — so it needs no RNG, no iteration-to-convergence, no `_linalg`, and no new
numerical primitive. It is the first phase to *consume a meta-analysis artifact*, turning
Phase 24's terminal leaf into a non-terminal node and demonstrating that the
layered-consumer architecture composes to a second order.

## 2. Current capability gap

The platform can, today:

- produce sealed pairwise significance tests between strategies (Phase 24), and
- correct **absolute** selection bias for a *single* campaign's best trial via PSR/DSR
  (Phase 23).

It **cannot**, today:

- correct for **multiplicity** across a *family* of simultaneous comparisons. Phase 23's
  DSR deflates one Sharpe for the number of independent trials `N` behind a *selection*;
  it does not adjust a *set of reported p values* so that the family-wise error rate or
  the false-discovery rate is controlled. These are different statistical objects: DSR
  answers "is the winner's Sharpe real after I searched `N` ways?"; multiplicity correction
  answers "of these `M` reported comparisons, which survive at level `alpha` once I account
  for having run all `M`?"

The gap is real and is explicitly foreshadowed in the Phase 24 spec, not invented to give
an unused field a reader. The pairwise `p` matrix is a genuine research output that is
statistically *unsafe to interpret uncorrected*.

## 3. Why Phase 25 (and why now)

- **The artifact exists and is fresh.** `StrategyComparison` was sealed in the immediately
  preceding phase and is a terminal leaf. Consuming it is the natural continuation.
- **The correction is architecturally sanctioned.** SC-7 names a "future consumer of this
  matrix" as the intended home for FWE/FDR adjustment, and explicitly declines to fold it
  into Phase 24 (keeping Phase 24 a pure test producer). Phase 25 is that consumer.
- **It is determinism-native.** The inputs are already canonical decimal strings under the
  pinned context; the transform is order statistics on those strings. No new determinism
  risk is introduced.
- **It creates downstream capability, not a report.** A sealed rejection set (which
  comparisons are significant *after* correction) and adjusted `p` values are consumable by
  a future strategy-selection or portfolio-of-survivors layer — the same way the P19→P24
  chain grew.

## 4. Existing-architecture survey (ground truth, verified against the repo)

**The factor → evaluation chain (independent of `BacktestResult`):**

```
FactorPortfolio (P19) ─► FactorRiskModel (P20) ─► PortfolioOptimization (P21, GMV)
                                                          │ (recipe)
                                                          ▼
                                              WalkForwardEvaluation (P22)  ── terminal record
                                                          │
                              ┌───────────────────────────┴───────────────────────────┐
                              ▼                                                         ▼
              ResearchCampaignEvaluation (P23)                        StrategyComparison (P24)
              PSR/DSR absolute selection-bias                        pairwise paired-difference
                     ── TERMINAL LEAF                                     ── TERMINAL LEAF
```

**The backtest chain:** `BacktestResult` (P12) → `ExperimentResult`/`BacktestComparison`
(P13), `PerformanceAnalytics` (P15), `FactorAttribution` (P17) — all terminal leaves.

**Raw-corpus consumers:** `SignalDiagnostics` (P16), `CrossSectionalRegression` (P18),
`FactorPortfolio` (P19).

**Terminal leaves (no downstream consumer today):** P13, P15, P16, P17, P18, **P23, P24**.

**Shared numerical infra:**

- `_linalg/decimal_ols.py` — exact-`Decimal` LDLᵀ (`ldl`, `ldl_solve`, `inverse_diagonal`);
  used by OLS (P17/P18) and the GMV solve (P21).
- `_stats/normal.py` — exact-`Decimal` `standard_normal_cdf`, `standard_normal_ppf`,
  `EULER_MASCHERONI`; used by P23 (PSR/DSR) and P24 (two-sided `p`). `campaign/normal.py`
  re-exports these byte-identically.

**Identity/storage discipline (verified in `comparison/identity.py`, `comparison/version.py`):**
`sha256:` prefix, `_SEP="\x00"` NUL join, canonical JSON
(`sort_keys=True, ensure_ascii=False, separators=(",",":")`), per-phase domain tag
(`comparison/1`), a `TransformationVersion` folding `code_version` + `config_hash`
(decimal context + method versions), transitive pinning by folding each referenced record's
`result_hash` in request order, and a write-once `ResearchResultStore` sidecar
(`research/sha256-<hex>.json`).

**Dead / unconsumed payloads confirmed:** `FactorRiskModel.correlation`;
`FactorRiskModel.factors` (means/vols — the blocked μ); `PortfolioOptimization.weights`
/`variance`/`volatility` (P22 re-solves rather than reading them). None of these is a sound
Phase 25 target (see §7).

## 5. Candidate capabilities (≥8)

Each candidate is scored on the nine criteria. Attributes: **In** = inputs; **Out** =
output artifact; **Gap** = why missing; **Consumes** = phases; **Class?** = new capability
class; **Math** = numerical machinery; **_linalg?**; **PIT/Det/Id/Store** = implications;
**Downstream** = what it enables.

### C1 — Multiple-Comparison Correction over the Phase 24 pairwise `p` matrix  ★ RECOMMENDED
- **In:** one sealed `StrategyComparison`; a declared `alpha`; a set of methods
  (Holm-FWE, Benjamini–Yekutieli-FDR, Benjamini–Hochberg-FDR, Bonferroni-FWE).
- **Out:** `MultipleComparisonCorrection` — per-method adjusted `p` value per KNOWN pair
  cell, a rejection flag at `alpha`, the family size `m`, and the count/identity of cells
  excluded from the family (UNDEFINED `p`).
- **Gap:** SC-7 explicitly defers this to a future consumer; the matrix is unsafe to read
  uncorrected.
- **Consumes:** P24 (transitively P22/P21/…).
- **Class?** YES — first consumer of a meta-analysis artifact; a *second-order*
  meta-analysis (multiplicity control), distinct from P23's absolute selection-bias and
  P24's pairwise testing.
- **Math:** total-order sort of `(p, i, j)`; closed-form step-up/step-down adjusted-p
  recursions; Benjamini–Yekutieli harmonic constant `c(m)=Σ_{k=1}^m 1/k` as an exact
  `Decimal` sum. No transcendental, no root-finding.
- **_linalg?** No. **PIT:** ex-post (inputs already ex-post). **Det:** trivially
  deterministic (sort + exact comparisons, no float, no RNG, no iteration-to-convergence).
  **Id:** fold the source `strategy_comparison_id` + its `result_hash` + `alpha` + method
  set + spec/engine version. **Store:** one new sidecar record; no schema change elsewhere.
- **Downstream:** a rejection set / adjusted-p artifact consumable by a future
  strategy-selection or "portfolio of validated strategies" layer.

### C2 — Multiple-Comparison Correction over Phase 23 per-trial statistics
- **In:** one `ResearchCampaignEvaluation`; `alpha`; methods. **Out:** adjusted per-trial
  `p`/rejection set. **Gap:** trials are a hypothesis family too. **Consumes:** P23.
  **Class?** Partial — same machinery as C1 but overlaps P23's DSR purpose (both address
  "many trials"), so the marginal capability is smaller. **Math/_linalg/PIT/Det:** as C1.
  **Downstream:** modest — P23 already returns a selection-bias verdict.
- **Verdict:** viable but weaker than C1 (conceptual overlap with DSR; less clearly a new
  class). A clean *extension target* once C1's generic core exists.

### C3 — Minimum Track Record Length (MinTRL)
- **In:** a strategy's sealed Sharpe + higher moments (from P22/P23); `alpha`.
  **Out:** the minimum number of periods `T*` for the Sharpe to be significant.
  **Gap:** inverts P23's PSR; not currently produced. **Consumes:** P22/P23.
  **Class?** NO — an *inversion* of the existing per-trial PSR, per-strategy scalar.
  **Math:** closed form using existing `standard_normal_ppf`. **_linalg?** No.
  **PIT/Det:** ex-post, deterministic. **Downstream:** informative but per-strategy;
  does not create a new consumable family.
- **Verdict:** clean and cheap, but a refinement of P23 rather than a new class. Strong
  runner-up for a *small* phase; weaker on "new capability class" than C1.

### C4 — Probability of Backtest Overfitting (PBO) via CSCV
- **In:** an aligned `N×T` OOS performance matrix reconstructed across strategies (as P24
  does). **Out:** a PBO estimate. **Gap:** no overfitting-probability capability exists.
  **Consumes:** the P22 strategy set (like P24). **Class?** YES — genuinely new and
  celebrated (Bailey/López de Prado). **Math:** combinatorially-symmetric cross-validation:
  enumerate `C(S, S/2)` submatrix splits and a logit — **requires a natural-log primitive
  (new `_stats` addition)** and combinatorial enumeration that is **explosive beyond
  `S ≈ 16`**. **_linalg?** No, but new `Decimal.ln` primitive. **PIT/Det:** ex-post,
  deterministic (enumeration, no RNG) but heavy; needs a hard split-count bound.
  **Downstream:** a scalar overfitting probability.
- **Verdict:** a strong *future* phase, but larger than an honest next step: new numerical
  primitive + combinatorial bound + full performance-matrix reconstruction. Rejected as the
  Phase 25 pick on the "small enough to be honest" criterion, not on soundness.

### C5 — Sharpe-difference significance (Jobson–Korkie / Memmel)
- **In:** the two OOS return series of a pair (from P24's reconstruction). **Out:** an
  inferential test upgrading P24's *descriptive* `sharpe_diff`. **Gap:** P24 seals only a
  descriptive Sharpe difference. **Consumes:** P24 inputs. **Class?** NO — an *extension of
  Phase 24's own test*; it belongs inside P24, not a new phase (the task forbids "features
  that belong naturally inside an existing phase"). **Math:** cross-series correlation +
  higher moments + Φ (exists). **_linalg?** No. **PIT/Det:** ex-post, deterministic.
- **Verdict:** rejected as a *new phase* — it is a within-P24 enrichment.

### C6 — Equality-constrained GMV (general `Aw=b`)
- **In:** a `FactorRiskModel` + a linear equality constraint set. **Out:** a constrained
  minimum-variance `PortfolioOptimization` variant. **Gap:** P21 solves only the
  fully-invested (`1ᵀw=1`) GMV. **Consumes:** P20. **Class?** Partial — an *optimization
  extension* (P21 sibling). **Math:** closed-form KKT system via one additive `_linalg`
  block-solve helper. **_linalg?** YES (new helper). **PIT/Det:** ex-post, deterministic,
  closed-form (no iteration). **Downstream:** richer optimizers → richer walk-forwards.
- **Verdict:** sound and determinism-safe, but (a) touches `_linalg` (approval-gated), and
  (b) is a sibling-extension of P21 rather than a new capability *class*. Viable alternative
  but weaker on novelty and larger on surface than C1.

### C7 — OOS performance analytics on walk-forward series (drawdown / tail / moments)
- **In:** `WalkForwardEvaluation.oos_returns`. **Out:** drawdown/tail statistics.
  **Gap:** none real — Phase 15 already computes these on `BacktestResult`. **Class?** NO —
  a reuse/reporting convenience on a different series. **_linalg?** No.
- **Verdict:** REJECTED — reporting reuse of an existing capability, not a new class.

### C8 — Covariance shrinkage / EWMA estimator for `FactorRiskModel`
- **In:** factor portfolios. **Out:** a shrunk covariance. **Gap:** arguably an estimator
  improvement. **Class?** NO — belongs *inside* Phase 20's estimator, not a new phase.
- **Verdict:** REJECTED — extends an existing phase; not a new capability.

### C9 — Risk decomposition (MCTR / CCTR) of `PortfolioOptimization`
- **In:** GMV weights + covariance. **Out:** marginal/component risk contributions.
  **Gap:** apparent (weights are an unconsumed payload). **Class?** NO — **tautological for
  GMV**: the first-order condition `Σw ∝ 1` forces `%CCTRᵢ = wᵢ` exactly (already noted in
  the Phase 22 proposal). It reports what the weights already are.
- **Verdict:** REJECTED — mathematically vacuous for the only optimizer that exists.

### C10 — Single-evaluation OOS calibration (predicted vs realized risk)
- **In:** one `WalkForwardEvaluation`. **Out:** a calibration statistic. **Gap:** thin —
  P22 already seals `predicted_vs_realized`. **Class?** NO. **Verdict:** REJECTED — largely
  already present; a reporting reduction.

### C11 — Mean-variance / maximum-Sharpe optimization
- **Gap blocker:** requires a **PIT-safe expected-return (μ) artifact**, which the
  investigation confirmed **does not exist** anywhere in the platform. Using an ex-post mean
  as forward μ is look-ahead fabrication (rejected by P21/PO-3/invariant 8).
- **Verdict:** REJECTED — no PIT-safe input; would violate no-look-ahead.

### C12 — Bootstrap / White Reality Check / Hansen SPA
- **Gap blocker:** all require randomization/resampling → **RNG (invariant 21 forbids)**.
- **Verdict:** REJECTED — non-deterministic by construction.

## 6. Alternatives considered (head-to-head, the viable set)

The genuinely viable, criteria-passing candidates are **C1, C2, C3, C4, C6**. Ranking:

| Candidate | New class? | Small/honest | No new primitive | No `_linalg` | Det-native | Foreshadowed | Downstream |
|-----------|:---------:|:------------:|:----------------:|:-----------:|:----------:|:------------:|:----------:|
| **C1 multiplicity/P24** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes (SC-7)** | **Yes** |
| C2 multiplicity/P23 | Partial | Yes | Yes | Yes | Yes | Partial | Modest |
| C3 MinTRL | No (inverts PSR) | Yes | Yes | Yes | Yes | Deferred by P23 | Weak |
| C4 PBO/CSCV | Yes | **No** (heavy) | **No** (needs ln) | Yes | Yes (heavy) | No | Scalar |
| C6 constrained GMV | Partial | Medium | Yes | **No** | Yes | Deferred by P24 | Yes |

C1 is the unique candidate that is simultaneously a new capability class, small enough to be
honest, needs no new numerical primitive, touches no `_linalg`, is determinism-native, is
explicitly foreshadowed by the artifact it consumes, and creates a consumable downstream
artifact.

## 7. Rejected alternatives (and why)

- **C7 (WF performance analytics), C10 (WF calibration):** reporting reuse of existing
  capability — not a new class.
- **C8 (covariance shrinkage):** belongs inside Phase 20's estimator.
- **C9 (risk decomposition):** tautological for GMV (`%CCTRᵢ = wᵢ`).
- **C5 (Sharpe-diff test):** an enrichment that belongs inside Phase 24.
- **C11 (mean-variance / max-Sharpe):** no PIT-safe μ; look-ahead.
- **C12 (bootstrap / Reality Check / SPA):** RNG; violates invariant 21.
- **Constrained-QP / risk-parity optimizers:** iteration-to-convergence; violates the
  determinism discipline (invariant 21) as a closed-form phase would not.
- **"Consume `FactorRiskModel.correlation` / `PortfolioOptimization.weights`":** forcing a
  reader onto an unused field is exactly the anti-pattern the criteria forbid; each such
  reader here is either tautological (weights) or a plain restatement (correlation).

## 8. Invariant analysis (COMPOSES / CONSTRAINS / TENSION / CONTRADICTION)

Classifying C1 against the global invariants and the additive phase-local blocks:

- **Content-addressed identity + transitive pinning (inv 1–6, §10–11): COMPOSES.** Phase 25
  folds the source `strategy_comparison_id` and its `result_hash` in request order, exactly
  as P24 folds walk-forward `result_hash`es. A new domain tag (`multiplicity/1`) prevents
  id collision with lower layers.
- **Exact-`Decimal` determinism, no float / no RNG / no wall-clock / no iteration-order
  dependence (inv 19–21): COMPOSES.** The transform is a sort under a *total* order
  (`p` ascending, ties broken by `(i, j)`) plus exact-`Decimal` comparisons and additions
  under the pinned context (prec 34, `ROUND_HALF_EVEN`). No randomness, no convergence loop.
- **Fail-closed / UNDEFINED-preserving (inv 15; SC-4 precedent): COMPOSES.** UNDEFINED `p`
  cells (from `ZERO_DIFFERENCE_VARIANCE`, or pairs UNDEFINED for `INSUFFICIENT_OVERLAP`) are
  **excluded from the family**, and both the excluded count and the family size `m` are
  sealed. No UNDEFINED cell is coerced to a number.
- **PIT / no-look-ahead (inv 8, 27–30; KS): COMPOSES (no new PIT surface).** Inputs are
  already ex-post statistics; the correction reads sealed decimal strings and introduces no
  new corpus access, no `as_of`, no availability logic. `boundary_kind` remains documentary
  (the source comparison's).
- **Additive phase-local invariant block (SD-/XS-/…/SC- precedent): COMPOSES.** Phase 25
  adds an MC-* block; it does not alter any existing invariant or block.
- **FDR validity under dependence: TENSION (disclosed, not a contradiction).** The pairwise
  `p` values are *not* independent — pairs share strategies, so the family is dependent.
  This does **not** threaten determinism or identity; it is a *statistical validity*
  concern about which correction is honest. Resolution: default to procedures valid under
  arbitrary dependence — **Holm** (FWE, valid under any dependence) and
  **Benjamini–Yekutieli** (FDR, valid under arbitrary dependence via the `c(m)` harmonic
  penalty) — and offer **Benjamini–Hochberg** only as an explicitly labeled
  independence/PRDS-assuming variant, with the assumption sealed in the record. This is the
  same adversarial-honesty stance P23/P24 took (disclosed deviations, recorded assumptions).
  It is a TENSION to document, not a CONTRADICTION that blocks the phase.
- **No CONTRADICTION** with any invariant was found.

## 9. Data-flow analysis

```
StrategyComparison (sealed, P24)
   │  read: pairwise cells (i, j, status, p_value: StatValue), per-strategy summary,
   │        strategy_comparison_id, result_hash, name, spec_version
   ▼
MultipleComparisonEngine (Phase 25)
   1. Collect the family F = { (i,j) : pair KNOWN and p_value KNOWN }, size m = |F|.
   2. Record excluded cells E = pairwise cells with UNDEFINED p (with reason), |E|.
   3. Sort F by (Decimal(p) ascending, i ascending, j ascending)  — total order.
   4. For each requested method, compute adjusted p per cell + rejection flag at alpha:
        Bonferroni:   p_adj = min(1, m · p)
        Holm:         step-down max-running over m·p_(k) ... (1)·p_(m), capped at 1
        BH:           step-up min-running of (m/k)·p_(k), capped at 1
        BY:           BH with p scaled by c(m)=Σ_{k=1}^m 1/k, capped at 1
   5. Seal MultipleComparisonCorrection.
   ▼
ResearchResultStore sidecar  research/sha256-<hex>.json
```

All arithmetic (the `m·p`, `(m/k)·p`, running min/max, `c(m)` sum) runs inside an explicit
`decimal.localcontext(default_decimal_context())`. No value leaves as a float.

## 10. Numerical-method analysis

- **No new primitive.** Adjusted-p recursions are order statistics + rational arithmetic on
  the existing sealed decimal `p` strings. Bonferroni/Holm/BH/BY are all closed-form monotone
  step transforms; no Φ, no `ppf`, no `ln`, no matrix.
- **`c(m)` for Benjamini–Yekutieli** is an exact `Decimal` partial harmonic sum
  `Σ_{k=1}^m 1/k` under the pinned context — the only arithmetic beyond multiply/compare, and
  it is a finite deterministic sum (no series truncation ambiguity).
- **Capping at 1** uses exact `Decimal` `min`, never a float clamp.
- **Ties** are resolved by the `(i, j)` request-order key, so the sort is a total order and
  the adjusted-p assignment is unambiguous and machine-independent.

## 11. Determinism analysis

- Inputs are canonical decimal strings sealed under prec-34 `ROUND_HALF_EVEN`; Phase 25
  re-parses them with `Decimal(...)` inside an explicit `localcontext`.
- The sort key is a total order; no reliance on dict/set iteration order.
- No RNG, no wall-clock, no `id()`, no float. Re-running on any machine reproduces every
  adjusted `p`, every rejection flag, and the `result_hash` byte-for-byte.
- The engine version folds the pinned decimal context + method version into `config_hash`
  (P24 precedent), so any change that could alter a computed value forces a new engine id.

## 12. PIT analysis

Phase 25 opens **no** new point-in-time surface. It reads a sealed ex-post artifact and
produces an ex-post artifact. There is no `as_of`, no `REVISED`/`PIT` mode selection, no
corpus read, no availability logic, and therefore no new look-ahead risk. `boundary_kind`,
if surfaced, is documentary and inherited from the source comparison (mirrors the
"ex-post typing; `boundary_kind='pit'` only documents PIT-walked inputs" rule).

## 13. Identity analysis

Following `comparison/identity.py` exactly:

```
multiple_comparison_result_hash = sha256( canonical JSON over the ordered output cells:
    the family descriptor (m, excluded-count) then, per method, each family cell's
    { i, j, method, p_adj (StatValue), rejected (bool) } in the sorted family order )

multiple_comparison_id = sha256( _SEP.join(
    "multiplicity/1",                          # domain tag
    multiple_comparison_engine_version_id,     # code + config (decimal ctx + method)
    name,
    spec_version,                              # "multiplicity/1"
    source_strategy_comparison_id,             # the referenced record's id
    source_result_hash,                        # transitive pin to the P24 answer
    alpha,                                     # declared significance level (decimal str)
    canonical_json(method_list),               # ordered requested methods
    multiple_comparison_result_hash ) )
```

`research_result_id` aliases `multiple_comparison_id`. Folding both the source
`strategy_comparison_id` and its `result_hash` makes the correction **transitively** sensitive
to any change in the source comparison (and thus to any change in any referenced walk-forward),
exactly the guarantee SC-1 provides one layer down.

## 14. Storage analysis

- One new write-once record in the existing `ResearchResultStore`
  (`research/sha256-<hex>.json`), `RESEARCH_RESULT_FORMAT_VERSION = 1` unchanged.
- No change to any existing record schema, no new store, no migration.
- Idempotent re-write of an identical payload is a no-op; a conflicting payload under the
  same id raises `FactorConsistencyError` (existing store contract).

## 15. Proposed API (illustrative; names are approval-gated — see §19)

```python
# quantforge.multiplicity.spec
@dataclass(frozen=True, slots=True)
class MultipleComparisonSpecification:
    name: str
    source_strategy_comparison_id: str      # the sealed P24 record to consume
    alpha: str                              # declared significance level, decimal string
    methods: tuple[CorrectionMethod, ...]   # ordered; default (HOLM, BENJAMINI_YEKUTIELI)

# quantforge.multiplicity.model
class CorrectionMethod(StrEnum):
    BONFERRONI = "bonferroni"
    HOLM = "holm"
    BENJAMINI_HOCHBERG = "benjamini_hochberg"
    BENJAMINI_YEKUTIELI = "benjamini_yekutieli"

# quantforge.multiplicity.result
@dataclass(frozen=True, slots=True)
class MultipleComparisonCorrection:      # implements ResearchRecord
    name: str
    source_strategy_comparison_id: str
    source_result_hash: str
    alpha: str
    family_size: int                     # m = number of KNOWN p-value cells
    excluded: tuple[ExcludedCell, ...]   # UNDEFINED-p cells, with reason, excluded from F
    corrections: tuple[MethodResult, ...]  # per method: per-cell adjusted p + rejection
    engine_version: MultipleComparisonEngineVersion
    @property
    def research_result_id(self) -> str: ...
    def to_dict(self) -> dict[str, object]: ...

# reached via the Workspace, not re-exported as an engine (P24 precedent)
Workspace.multiplicity_engine.evaluate(spec) -> MultipleComparisonCorrection
```

Adjusted-p cells reuse the **UNDEFINED-preserving `StatValue`** discipline (a KNOWN decimal
string, never a bare float).

## 16. Proposed package structure

```
src/quantforge/multiplicity/
    __init__.py        # exports spec/result/model types
    spec.py            # MultipleComparisonSpecification
    model.py           # CorrectionMethod, StatValue reuse, ExcludedCell, MethodResult
    compute.py         # the deterministic adjusted-p procedures (Bonferroni/Holm/BH/BY)
    engine.py          # MultipleComparisonEngine (reads source record, seals output)
    result.py          # MultipleComparisonCorrection (ResearchRecord)
    identity.py        # multiple_comparison_id / _result_hash
    version.py         # MultipleComparisonEngineVersion + method/spec version constants
tests/multiplicity/
    ...                # see §17
```

Top-level `quantforge.__init__` gains `MultipleComparisonSpecification` and
`MultipleComparisonCorrection`; `Workspace` gains a lazy `multiplicity_engine` property
(the exact `None`-init + deferred-import + `Engine(self)` pattern used for
`comparison_engine`).

## 17. Proposed tests (scope only; not to be written until approved)

- **Determinism:** identical spec + identical sealed source → identical
  `multiple_comparison_id` and `result_hash`; stable under two `PYTHONHASHSEED`/iteration
  orderings.
- **Correctness vs hand-computed references:** small families (m = 3, 6) with known
  adjusted-p values for each method; the BY `c(m)` harmonic constant checked exactly.
- **Monotonicity:** Bonferroni ≥ Holm ≥ (per-cell) raw; BY ≥ BH; adjusted p capped at 1.
- **UNDEFINED handling:** a source with `ZERO_DIFFERENCE_VARIANCE` / `INSUFFICIENT_OVERLAP`
  cells excludes them from `m` and records them in `excluded`; empty family → a well-defined
  UNDEFINED-family record (no divide-by-zero).
- **Identity fold:** changing `alpha`, the method list/order, or the source `result_hash`
  changes `multiple_comparison_id`.
- **Store round-trip:** `read_as(MultipleComparisonCorrection)`; write-once idempotency;
  conflicting payload raises.
- **Smoke:** `test_multiplicity_public_api_is_exported`.

## 18. Failure / UNDEFINED semantics

- **Empty family (`m = 0`)** — every pairwise `p` was UNDEFINED (or `N < 2`): the record is
  sealed with `family_size = 0`, `corrections` empty, and a recorded reason; never a
  divide-by-zero, never a fabricated rejection.
- **A single UNDEFINED `p` cell** — excluded from the family, recorded in `excluded` with its
  `ComparisonUndefinedReason`; `m` counts only KNOWN cells.
- **`alpha` out of `(0, 1)`** — refused at spec construction (fail-closed), not silently
  clamped.
- **Source record not found / wrong type** — the engine fails closed via the store's
  `read_as` (no guessing).
- **New MC-* invariant block** documents these (additive, per the SC-/CE- precedent).

## 19. Approval-gated decisions (★ LOAD-BEARING)

1. **★ LOAD-BEARING — Recommended capability = C1 (multiplicity correction over the Phase 24
   pairwise matrix), not C2/C3/C4/C6.** Everything below is downstream of this choice.
2. **★ LOAD-BEARING — Source is exactly one `StrategyComparison` (P24), consumed by id.**
   (Alternative: also/instead consume P23 trial statistics — deferred as C2.)
3. **★ LOAD-BEARING — Default methods = Holm (FWE) + Benjamini–Yekutieli (FDR), both valid
   under arbitrary dependence; Benjamini–Hochberg offered only as an explicitly labeled
   independence/PRDS-assuming variant with the assumption sealed.** This is the honest
   resolution of the §8 dependence TENSION.
4. **★ LOAD-BEARING — UNDEFINED `p` cells are excluded from the family (not imputed), and both
   `m` and the excluded set are sealed.** Defines the statistical object being corrected.
5. **★ LOAD-BEARING — No new numerical primitive and no `_linalg` change.** If review prefers a
   design that would require either, that is a different (larger) phase.
6. **★ LOAD-BEARING — Version = v0.22.0; package `multiplicity`; domain tag `multiplicity/1`;
   artifact `MultipleComparisonCorrection`.** Names are provisional and approval-gated.
7. Method set membership (include Bonferroni? include Šidák?) — non-load-bearing default,
   confirm at approval.

## 20. Open questions

- Should the family optionally span **more than one** sealed comparison (a cross-comparison
  family)? Recommend **no** for v0.22.0 (one source, mirrors P21's single-input pattern);
  revisit as a later extension.
- Should `alpha` be a single scalar or a small declared set (to seal rejection sets at
  several levels at once)? Recommend a **single** `alpha` for honesty; multiple levels are a
  trivial later addition.
- Should Šidák (`1−(1−p)^m`) be offered? It needs an exact `Decimal` power; recommend
  **deferring** to avoid a new primitive.
- Where should the shared adjusted-p core live if C2 (P23 trials) is later approved — a
  neutral `_stats`-style helper, or duplicated? Recommend factoring the pure procedures into
  `multiplicity/compute.py` now so C2 can import them unchanged later.

## 21. Version

**v0.22.0** (minor, additive — a new capability layer; consistent with every prior phase's
minor bump). No existing public API changes.

## 22. Implementation scope (if approved)

- New `src/quantforge/multiplicity/` package (§16), ~7 modules mirroring `comparison/`.
- `quantforge.__init__` exports for the spec + result types.
- `Workspace.multiplicity_engine` lazy property.
- `tests/multiplicity/` (§17) + one smoke export assertion.
- Docs: README version row, ARCHITECTURE section, `docs/data-model.md` MC-* invariant block,
  `docs/index.md` entry — **only after** implementation is approved and complete.
- A locked spec `docs/phase25-multiple-comparison-correction-locked.md` to be authored at
  approval time (this proposal is not that spec).

## 23. Out-of-scope (explicitly)

- Consuming Phase 23 (C2), MinTRL (C3), PBO/CSCV (C4), constrained GMV (C6), Sharpe-difference
  testing (C5) — all deferred.
- Any RNG-based procedure (bootstrap / Reality Check / SPA), any mean-variance/max-Sharpe
  optimizer, any risk decomposition, any covariance-estimator change.
- Any new `_linalg` or `_stats` numerical primitive.
- Any modification to existing source, tests, README, ARCHITECTURE, `docs/index.md`, or
  `docs/data-model.md` (until approved implementation).

## 24. Final recommendation

Implement **Phase 25 = Multiple-Comparison Correction (C1)**: a `multiplicity` package that
consumes one sealed `StrategyComparison`, treats its KNOWN pairwise `p` values as a
hypothesis family, and seals Holm (FWE) and Benjamini–Yekutieli (FDR) adjusted `p` values —
with Benjamini–Hochberg as a disclosed independence-assuming variant — plus a rejection set
at a declared `alpha`, as `MultipleComparisonCorrection`, at **v0.22.0**.

It is the unique candidate that is a genuinely new capability class (the first consumer of a
meta-analysis artifact; a second-order multiplicity control distinct from P23's absolute
selection-bias), is explicitly foreshadowed by the artifact it consumes (SC-7), is small
enough to be architecturally honest, needs no new numerical primitive and no `_linalg`
change, is determinism-native (sort + closed-form exact-`Decimal` transforms, no RNG, no
iteration), opens no new PIT surface, composes with every invariant (the only tension —
FDR validity under dependence — is resolved by defaulting to dependence-robust procedures and
sealing the assumption), and creates a downstream-consumable rejection-set artifact rather
than a mere report.
