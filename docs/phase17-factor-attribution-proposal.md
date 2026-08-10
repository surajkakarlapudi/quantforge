# Phase 17 — Multi-Factor Performance Attribution (Design Proposal)

> **Status: PROPOSAL — DESIGN ONLY. Not approved. No code exists.**
> This document is the sole deliverable of the Phase 17 design step. It proposes
> *whether and how* QuantForge should add a multi-factor performance-attribution
> layer on the foundations of Phases 1–16. It modifies no production source, adds
> no dependency, writes no code, and changes no test. The implementation gate
> (§20/§21) enumerates exactly what would change **if and only if** this design is
> approved.
>
> Governing prior specs (source of truth): [data-model.md](data-model.md)
> (invariants 1–30, SD-1..SD-4, BT-1..BT-4),
> [phase12-backtesting-proposal.md](phase12-backtesting-proposal.md),
> [phase13-comparative-research-locked.md](phase13-comparative-research-locked.md),
> [phase15-analytics-locked.md](phase15-analytics-locked.md),
> [phase16-signal-diagnostics-locked.md](phase16-signal-diagnostics-locked.md),
> [ARCHITECTURE.md](../ARCHITECTURE.md) (10 Engineering Principles).

---

## 1. Capability selection

**Selected capability: multi-factor performance attribution.**

Phase 17 adds a deterministic, content-addressed layer that decomposes the
realized period-return series of a **sealed** subject `BacktestResult` into the
contributions of *K* explanatory **factor return series**, where each factor is
itself a sealed `BacktestResult` (exactly the Phase 15 D3 convention: "a benchmark
is another sealed `BacktestResult`", generalized from one benchmark to *K*
factors). It runs an ordinary-least-squares multiple regression of the subject's
excess return on the *K* factor excess returns and reports, as first-class
`UNDEFINED`-preserving statistics:

- per-factor **betas** (loadings) and the **intercept (alpha)**;
- the closed-form regression diagnostics computable in exact `Decimal`
  arithmetic: R², adjusted R², residual standard error, and per-coefficient
  standard errors / t-statistics under the classical OLS covariance
  `σ̂²(XᵀX)⁻¹`;
- a **return decomposition** for the sample: the portion of the subject's mean
  excess return attributable to each factor (`βₖ · mean(factorₖ)`) versus the
  unexplained mean (alpha), with residuals retained for provenance.

This is the multi-factor generalization of the single-factor OLS alpha/beta that
Phase 15 shipped (§4 D4 of Phase 15) and **explicitly deferred** the rest of:
> "Single-factor OLS alpha/beta is in scope … **Multi-factor regression is
> explicitly deferred to a future phase.**" — phase15-analytics-locked.md D4.

It is also the exact capability named as the Phase 16 follow-on:
> "It composes Phases 9/10/11 only … and **unblocks a future long/short
> factor-portfolio + multi-factor attribution phase.**" — phase16 D1.

and the README "Next" row: "Multi-factor attribution / richer execution & cost
models."

---

## 2. Why it belongs in Phase 17

1. **It is the single most-signaled deferred research capability.** Three
   independent locked documents point at it: Phase 15 D4 (defers *multi-factor
   regression* by name), Phase 16 D1 (names a *multi-factor attribution phase*),
   and the README "Next" row. No other candidate is named this consistently.

2. **It is a genuine research capability, not convenience.** Attribution answers
   a question the stack cannot answer today: *"Is this strategy's return explained
   by exposure to known factors, or is there residual multi-factor alpha?"* That
   is the natural analytic successor to Phase 15 (which can only regress against a
   *single* benchmark) and Phase 16 (which measures a *single* signal's predictive
   power). Neither can decompose realized performance across several explanatory
   series simultaneously.

3. **It is a pure consumer of already-sealed, PIT-correct artifacts.** Like
   Phases 13/14/15, it reads sealed `BacktestResult`s from the shared research
   sidecar and derives a new sealed record. It introduces **no new data source,
   no new store, no new dependency, and touches no PIT resolver.** All PIT and
   corpus-pinning guarantees are inherited, not re-implemented — the strongest
   possible position for preserving the invariant catalog.

4. **It sequences correctly.** It sits strictly above Phase 12 (needs sealed
   backtests to exist) and beside Phase 15 (shares the "benchmark/factor is a
   sealed backtest" convention and the `_verify_commensurable` idiom). It depends
   on nothing that does not already exist. It does *not* require the deferred
   Python-callback strategy, richer execution models, a covariance/optimizer
   layer, or any new market data — so it does not front-run a later phase.

5. **The math is honestly computable under the zero-dependency, exact-`Decimal`
   constraint.** OLS on *K* factors reduces to solving the *K+1* normal equations
   `(XᵀX)β = Xᵀy`. For the small *K* attribution targets (v1 caps *K*; §17), this
   is a symmetric positive-(semi)definite linear solve done exactly with a
   `Decimal` Cholesky/LDLᵀ factorization — no float, no numpy, no RNG. Rank
   deficiency (collinear factors) is detected during factorization and yields a
   first-class `UNDEFINED` result, never a fabricated coefficient (§11).

---

## 3. Alternatives considered and rejected

At least four plausible Phase 17 candidates were evaluated against the rejection
criteria (violates an invariant; duplicates existing functionality; silently
weakens PIT; belongs to a later phase; is primarily presentation/convenience;
needs an unnecessary dependency).

| Candidate | Verdict | Reason for rejection (or selection) |
|---|---|---|
| **A. Multi-factor performance attribution** | **SELECTED** | Named deferral (Phase 15 D4, Phase 16 D1, README Next). Pure consumer; no new source/store/dep; math is exact-`Decimal`. Completes the single-factor stub honestly. |
| **B. Long/short factor-portfolio construction** | Rejected | Substantially a *Phase 12 strategy-vocabulary enhancement* (new `weight`/`select` steps, gross/net targets). Phase 12 D10 already admits dollar-neutral L/S; extending the weighting vocabulary is a Phase 12 v2 refinement that risks **duplicating engine-owned execution (BT-3)** rather than adding a new research layer. Better sequenced as a Phase 12 extension, not a new phase. |
| **C. Richer execution & cost models** (market impact, partial fills, borrow) | Rejected | Explicitly a Phase 12 v1 *out-of-scope refinement* (Phase 12 §I, Q39), not a new research conclusion. It changes how a backtest is *simulated*, i.e. it belongs *inside* the Phase 12 engine (would edit a prior engine, violating the additive-layer discipline), and expands the trust surface without answering a new research question. |
| **D. Cross-sectional factor-premium estimation (Fama–MacBeth)** | Rejected | Heavily overlaps Phase 16 machinery (per-`T` cross-sectional signal/return pairing). A second cross-sectional-regression layer beside Phase 16 would **duplicate functionality** (SD-* territory) and blur the diagnostics boundary. The time-series attribution of a *portfolio's realized returns* (candidate A) is distinct and non-overlapping. |
| **E. Covariance / risk model (portfolio variance decomposition)** | Rejected | Primarily a *building block for the deferred portfolio optimizer* (Phase 12 §I out-of-scope). Delivers little standalone research value without the optimizer, is `Decimal`-heavy (large PSD matrices), and would **belong to a later phase** (it is infrastructure for optimization, which v1 excludes). |
| **F. Batch analytics over an experiment** | Rejected | Phase 15 D10 already calls this "a thin future loop over this primitive" — it is a *convenience wrapper*, not a new research capability, and thus fails the "no convenience layer" bar. |

Candidate A uniquely satisfies every gate: named deferral, genuine research
value, pure consumer, no new dependency/store/source, no invariant weakening, and
correct sequencing.

---

## 4. Full contradiction / invariant analysis

Each row states an existing invariant (with its source), the Phase 17 touch-point,
a **verdict** (**COMPOSES** — Phase 17 consumes the invariant unchanged;
**CONSTRAINS** — the invariant forces a Phase 17 design choice; **TENSION** — a
non-obvious but resolvable interaction handled explicitly; **CONTRADICTION** — a
hard conflict requiring a stop), and the resolution. **No row is a
CONTRADICTION.**

### 4.1 Immutability / provenance (inv. 1–5)

| # | Invariant | Touch-point | Verdict | Resolution |
|---|---|---|---|---|
| 1 | Every artifact immutable & content-addressed | The attribution record | **COMPOSES** | `FactorAttribution` is a new frozen, content-addressed `ResearchRecord` sealed once; never mutated. |
| 2 | Raw/source data append-only | — | **COMPOSES** | Phase 17 reads only sealed `BacktestResult`s; writes only its own sidecar record. No source is touched. |
| 3–4 | No silent rewriting; full lineage | Referenced backtests | **COMPOSES** | The record stores `(backtest_id, result_hash)` **pointers** (never copies of ledgers/returns), like Phase 14/15. Lineage is the referenced ids + both corpus pins per referenced backtest. |
| 5 | Provenance is first-class | Regression inputs | **COMPOSES / CONSTRAINS** | The record retains which backtests supplied `y` and each `xₖ`, their `result_hash`es, the shared `schedule_id`, the period count, and the annualization convention (§9). |

### 4.2 PIT / availability (inv. 6–17)

| # | Invariant | Touch-point | Verdict | Resolution |
|---|---|---|---|---|
| 6–10 | PIT eligibility, total-order selection, no look-ahead | Regression inputs | **COMPOSES** | Phase 17 performs **no `as_of` resolution**. It consumes already-sealed period-return vectors whose every element was produced by a PIT-correct Phase 12 walk. It adds no new data read against the corpus. |
| 11 | `security_id` is identity; ticker never is | — | **COMPOSES** | No security-level access; operates on sealed portfolio-level return series only. |
| 12 | Fail-closed availability; UNKNOWN never eligible | Missing return cells | **COMPOSES / CONSTRAINS** | Phase 12 already sealed a dense `period_returns` vector (fail-closed at simulation time). Phase 17 requires the subject and every factor to share the same `schedule_id` and equal-length `period_returns` (§4.7, FA-3); it never imputes a missing period. |
| 13–17 | Availability policy, ingestion vs availability | — | **COMPOSES** | Inherited entirely through the sealed backtests; Phase 17 introduces no availability logic. |

### 4.3 Determinism / versioning (inv. 18–21)

| # | Invariant | Touch-point | Verdict | Resolution |
|---|---|---|---|---|
| 18 | Deterministic, content-addressed identity | `attribution_id` | **COMPOSES / CONSTRAINS** | Same scheme as every existing id: `sha256:` prefix, `_SEP="\x00"` NUL-join, canonical JSON (`sort_keys=True, ensure_ascii=False, separators=(",",":")`). New domain tags (§8). |
| 19 | Reproducibility end-to-end | The regression | **COMPOSES / CONSTRAINS** | Guaranteed by: sealed inputs (byte-identical `period_returns`), `factor` ordering fixed by the request (not by dict/set iteration), pinned `Decimal` context (precision 34, `ROUND_HALF_EVEN`) reused from the analytics engine-version pattern, no float, no wall-clock, no RNG. |
| 20 | Versioned transformations | Regression formulae | **COMPOSES / CONSTRAINS** | A `attribution-engine/1` code version + `attribution-stats/1` formula version fold into the engine-version id (like `analytics-engine/1` + `analytics-stats/1`). Any formula change hashes distinctly. |
| 21 | No default PIT/REVISED mode | The record | **COMPOSES** | v1 is PIT-only by construction (`boundary_kind="pit"`, documenting that the underlying backtests were PIT walks). No mode flag; a REVISED attribution scope is reserved and explicitly labelled (§14, mirroring Phase 14 D10 / Phase 15 §6). |

### 4.4 Amendments / history (inv. 22, 22a, 23) — **COMPOSES.** No filing history is
touched; Phase 17 never reads facts or amendments.

### 4.5 Additional (inv. 24–26) — **COMPOSES.** No new store, no DB (inv. 26 /
Principle 10): the record persists via the existing `ResearchResultStore` sidecar.

### 4.6 Knowledge-state vs revised (inv. 27–30) — the critical block

| # | Invariant | Touch-point | Verdict | Resolution |
|---|---|---|---|---|
| 27 | No default; PIT and REVISED are distinct | Attribution scope | **COMPOSES** | v1 is a single explicit PIT-only scope; no default mode. |
| 28 | **REVISED is not a PIT source** | The attribution *output* | **COMPOSES / CONSTRAINS** | **This is the load-bearing constraint.** A regression of realized returns is an **ex-post research statistic**, not a forward-usable PIT value. Therefore `FactorAttribution` is **not** a `Pit*` type, exposes **no** as-of accessor, and is **inadmissible** where a PIT signal/value is required — exactly the SD-2 discipline Phase 16 adopted for forward-looking diagnostics. This yields new invariant **FA-2** (§15). No contradiction: Phase 17 declines to masquerade as PIT, so it cannot leak revised/ex-post data into a PIT decision. |
| 29–30 | Type-boundary separation of Pit*/Revised* | Inputs | **COMPOSES** | Inputs are sealed `BacktestResult`s (PIT walks). Phase 17 constructs neither `Pit*` nor `Revised*`; it produces its own non-PIT statistic type. |

### 4.7 Phase-12/15/16 invariants (BT-1..BT-4, SD-1..SD-4)

| # | Invariant | Verdict | Resolution |
|---|---|---|---|
| BT-1 | Corpus pin recorded & verified | **COMPOSES / CONSTRAINS** | Phase 17 inherits pinned corpora through each referenced backtest. It surfaces a `pin_mismatch` flag when referenced backtests were run over different corpora (like Phase 15's surfaced pin difference) — never silently reconciled. Folds every referenced `result_hash` into `attribution_id` (FA-1). |
| BT-2 | PIT-only strategy boundary | **COMPOSES** | Not applicable to a consumer; no strategy boundary is created. |
| BT-3 | Engine-owned execution | **COMPOSES** | Phase 17 executes nothing; it only reads sealed results. Rejecting candidate B protects this. |
| BT-4 | Fail-closed simulation | **COMPOSES / CONSTRAINS** | Analogue at the estimation layer: FA-4 — singular/collinear design, insufficient periods, or zero-variance regressand yield first-class `UNDEFINED` cells with reasons; never a fabricated coefficient or divide-by-zero. |
| SD-1 | Corpus pin surfaced, changed corpus → new id | **COMPOSES** | Same discipline as FA-1. |
| SD-2 | A forward-looking diagnostic is not a PIT value | **COMPOSES** | FA-2 is the direct analogue for an ex-post attribution statistic. |
| SD-3 | Signal read PIT-eligible-at-T | **COMPOSES** | Inherited via sealed backtests; no new signal read. |
| SD-4 | Fail-closed pairing, auditable coverage, no imputation | **COMPOSES / CONSTRAINS** | FA-3 (commensurability) + FA-4 (fail-closed estimation) are the analogues: mismatched/short series fail closed, never padded. |

**Conclusion.** Phase 17 is a clean additive composition. It introduces **no hard
contradiction**, weakens no invariant, and adds four *per-phase* invariants
(FA-1..FA-4) that are direct analogues of the Phase 12/15/16 disciplines. The
single load-bearing constraint (inv. 28 / SD-2) is honored by making the
attribution record explicitly **not** a PIT type. Proceeding to the design.

---

## 5. Architecture and composition map

Phase 17 is an **additive consumer layer**, structurally a sibling of Phase 15
(`analytics`). Proposed package `src/quantforge/attribution/`.

- **Read-only over lower layers.** It reads sealed `BacktestResult`s via
  `ResearchResultStore.read_as(id, BacktestResult.from_dict)` and writes only its
  own record back to the same sidecar. It calls no PIT resolver, no market/panel
  engine, and never re-derives a return.
- **Workspace-hosted engine** (like `analytics_engine`): a lazy, cached,
  cycle-free `attribution_engine` property on `Workspace`, annotated `-> object`
  with the concrete import in the property body (the established template).
- **Reuses identity/versioning conventions verbatim**: `_SEP="\x00"`, `sha256:`
  prefix, canonical JSON, per-phase domain tags, an `AttributionEngineVersion`
  dataclass folding the pinned `Decimal` context + formula version (exactly the
  `AnalyticsEngineVersion` pattern, which is the correct precedent because Phase 17
  *does* arithmetic — unlike experiment/report which do not).
- **Zero new runtime dependencies**: stdlib `Decimal` only.

Composition (existing APIs Phase 17 would call):

| Phase 17 need | Existing API (verbatim) | Returns |
|---|---|---|
| Resolve subject & each factor | `ResearchResultStore.read_as(id, BacktestResult.from_dict)` | `BacktestResult` |
| Subject/factor return vector | `result.performance.statistics.period_returns` | `tuple[str, ...]` |
| Commensurability keys | `result.schedule_id`, `result.backtest_engine_version_id`, `len(period_returns)` | — |
| Drift detection | recompute `result_hash` from `ledger` `outcome_digest`s, compare to sealed | (reuse Phase 15 idiom) |
| Corpus pins | `result.dataset_version_id`, `result.market_dataset_version_id` | — |
| Persist | `ResearchResultStore.write(record)` | write-once sidecar |
| Decimal context | pinned precision 34, `ROUND_HALF_EVEN` (attribution engine-version) | `decimal.Context` |

---

## 6. Data-flow

`AttributionEngine.attribute(spec: AttributionSpecification) -> FactorAttribution`:

1. **Resolve & verify** the subject and each of the *K* factor backtests from the
   sidecar (present → `research_result_id == requested` → recomputed `result_hash`
   equals sealed value; any failure raises — the Phase 15 fail-closed idiom).
2. **Verify commensurability** (FA-3): every factor must share the subject's
   `schedule_id`, have an equal-length `period_returns`, and share the same
   `backtest_engine_version_id`. Mismatch raises `AttributionConsistencyError`.
   Distinct corpus pins across references are **surfaced** (`pin_mismatch`),
   not raised.
3. **Build the regression** under the pinned `Decimal` context:
   `y = subject.period_returns − rf`; design matrix
   `X = [1 | x₁−rf | … | x_K−rf]` (intercept column + *K* factor excess-return
   columns), all as exact `Decimal`.
4. **Solve** the normal equations `(XᵀX)β = Xᵀy` via `Decimal` Cholesky/LDLᵀ.
   If `XᵀX` is singular / not positive-definite within an exact-arithmetic zero
   test (collinear or degenerate factors), the whole coefficient block is
   `UNDEFINED(SINGULAR_DESIGN)` (FA-4).
5. **Compute** residuals `e = y − Xβ`, SSR, SST, R², adjusted R² (guarding
   `n − K − 1 > 0`), residual variance `σ̂² = SSR/(n−K−1)`, coefficient covariance
   `σ̂²·(XᵀX)⁻¹`, per-coefficient standard errors and t-stats, and the sample
   return decomposition (`βₖ·mean(xₖ−rf)` per factor + alpha). Each undefinable
   cell is a first-class `UNDEFINED` with a reason.
6. **Seal**: fold the ordered output cells into `result_hash`; compute
   `attribution_id`; `store.write(record)` (write-once, idempotent byte-identical).

---

## 7. PIT / no-look-ahead implications

- Phase 17 performs **no `as_of` resolution and no corpus read**. Every input is
  a sealed period-return series that a Phase 12 PIT walk already produced under
  the no-look-ahead guarantee (BT-2). Attribution cannot introduce look-ahead
  because it introduces no new temporal decision.
- The output is **ex-post** (a regression over the whole realized sample). Per
  inv. 28 / SD-2 it is therefore **not** a PIT value: `FactorAttribution` is not a
  `Pit*` type and exposes no as-of accessor (FA-2). It can never be handed to a
  layer that requires a PIT signal.
- `boundary_kind="pit"` on the record documents only that the *underlying
  backtests were PIT walks* — precisely the Phase 16 convention where the label
  describes the signal side, not the ex-post statistic.

---

## 8. Identity and reproducibility model

Two-part identity following the **single-id** pattern of Phase 15 (a value record
whose id folds its own output), because Phase 17 — like analytics — computes a
result rather than orchestrating pointers:

- **Domain tags (fresh):** spec `attribution/1`; engine `attribution-engine/1`;
  formula `attribution-stats/1`; result-hash block tag `attribution/1`.
- **`result_hash`** = `sha256:` over canonical JSON of the ordered output cells
  (coefficients block → diagnostics block → decomposition block), each cell a
  `(key, StatValue)` — same construction as `analytics_result_hash`.
- **`attribution_id`** = `sha256:` over the NUL-join of:
  `attribution-engine-version-id`, `name`, `spec_version`, `subject_id`,
  canonical JSON of the **ordered** factor id list, `risk_free_per_period`,
  `periods_per_year` (annualization convention, folded into the id but **not** the
  result_hash — the Phase 12/15 precedent), the subject `result_hash`, canonical
  JSON of the ordered factor `result_hash`es, and this record's `result_hash`.
- **`research_result_id`** aliases `attribution_id` (single-id pattern; matches
  `analytics_id`/`backtest_id`).
- **Reproducibility (inv. 19):** byte-identical inputs (sealed vectors) + fixed
  factor ordering (from the request) + pinned `Decimal` context + a fixed,
  documented linear-algebra algorithm (Cholesky with an exact zero pivot test) +
  no float/wall-clock/RNG ⇒ byte-identical `attribution_id` and `result_hash` on
  any machine.

**FA-1 (corpus-pin surfacing):** the `attribution_id` folds every referenced
`result_hash`; a changed corpus changes the referenced backtest's `result_hash`,
hence a different `attribution_id` — never a silently different result under the
same id.

---

## 9. Provenance model

The record answers "what did this attribution regress, and over what?" It retains:

- `subject_ref: (backtest_id, result_hash)`;
- `factor_refs: tuple[(name, backtest_id, result_hash), ...]` in the **request
  order** (order is semantic — it fixes the column order and the coefficient
  labels);
- the shared `schedule_id` and the period count `n`;
- `risk_free_per_period`, `periods_per_year`;
- the distinct `dataset_version_id`s / `market_dataset_version_id`s observed
  across references (as tuples, like `PerformanceAnalytics`), plus the
  `pin_mismatch` flag;
- the retained **residual series** (optional, §17) for auditability, or its digest.

It stores **no copy** of any referenced return vector or ledger — only pointers
and content hashes (Phase 14/15 reference-only discipline).

---

## 10. Persistence / reuse strategy

- **Reuse the existing `ResearchResultStore` sidecar** via the `ResearchRecord`
  Protocol (`research_result_id` + `to_dict`), exactly as Phases 10/13/14/15/16
  do. `FactorAttribution.from_dict` is the strict fail-closed inverse for typed
  round-trip.
- **Write-once, idempotent, fail-closed:** identical `attribution_id` must map to
  byte-identical bytes; a differing payload under the same id raises (the store's
  existing `FactorConsistencyError` behavior).
- **No new store, no database** (inv. 26, Principle 10). Records live at
  `<root>/research/sha256-<hex>.json`.

---

## 11. Error / fail-closed behavior

**Hard raises** (configuration/consistency defects only):

- referenced backtest absent, id-mismatch, or `result_hash` drift →
  `AttributionConsistencyError`;
- incommensurable inputs (schedule/length/engine-version mismatch) →
  `AttributionConsistencyError` (FA-3);
- fewer than `K + 2` periods (insufficient degrees of freedom for *K* factors +
  intercept + ≥1 residual df) → `AttributionConfigurationError`;
- fewer than one or more than `K_MAX` factors, empty/duplicate factor ids, factor
  id == subject id → `AttributionConfigurationError`.

**First-class `UNDEFINED`** (recorded, never raised — FA-4):

- `SINGULAR_DESIGN` — `XᵀX` not positive-definite (collinear/degenerate factors);
  the whole coefficient/diagnostics block is UNDEFINED;
- `INSUFFICIENT_PERIODS` — a diagnostic needing `n − K − 1 > 0` when that fails;
- `ZERO_VARIANCE` — regressand or a regressor has zero sample variance (t-stats /
  R² undefinable);
- `ZERO_RESIDUAL_VARIANCE` — perfect in-sample fit (standard errors undefinable).

No fabricated coefficient, no divide-by-zero, no imputed period.

---

## 12. Public API

```python
from quantforge import Workspace, AttributionSpecification

ws = Workspace.open(root)
spec = AttributionSpecification(
    name="three-factor-attrib",
    subject_id=strategy_backtest_id,  # a sealed BacktestResult id
    factor_ids=(  # ordered; each a sealed BacktestResult id
        value_factor_backtest_id,
        size_factor_backtest_id,
        momentum_factor_backtest_id,
    ),
    risk_free_per_period="0",
    periods_per_year="12",  # annualization convention (folded into id)
)
attribution = ws.attribution_engine.attribute(
    spec
)  # -> FactorAttribution (sealed, write-once)

attribution.coefficients  # ordered (label, StatValue) — alpha + per-factor beta
attribution.diagnostics  # R2, adj_R2, residual_std_error, per-coef std_err/t_stat
attribution.decomposition  # per-factor mean-excess-return contribution + alpha
attribution.research_result_id  # == attribution.attribution_id (ResearchRecord)
attribution.pin_mismatch  # surfaced flag, never raised
```

Public types re-exported from `quantforge`: `AttributionSpecification`,
`FactorAttribution` (result), and the shared `StatValue`/status vocabulary if not
already re-exported. The **engine is reached only via `Workspace`** (not
re-exported) — consistent with every prior phase.

---

## 13. Workspace integration

Add one lazy, cached, cycle-free property mirroring `analytics_engine`:

```python
@property
def attribution_engine(self) -> object:  # concrete type imported in body
    from quantforge.attribution.engine import AttributionEngine

    if self._attribution_engine is None:
        self._attribution_engine = AttributionEngine(self)
    return self._attribution_engine
```

It reuses `self.research_result_store`. No other Workspace change; no change to any
Phase 1–16 engine or store.

---

## 14. Versioning strategy

- README table: Phase 17 → **`v0.14.0`** (Phase 16 is `v0.12.0`), on completion
  only.
- Engine version `attribution-engine/1` + formula version `attribution-stats/1`,
  folded (with the pinned `Decimal` config: `prec=34\x00round=ROUND_HALF_EVEN\x00
  formula=attribution-stats/1`) into `attribution_engine_version_id` — the
  `AnalyticsEngineVersion` construction.
- Statistic/reason **sets are closed**; extending any set is an explicit future
  edit that hashes distinctly (a new key/reason changes `result_hash`) — never an
  implicit fallback (the Phase 15/16 §3.x discipline).
- A **REVISED attribution scope** is reserved and, if ever built, distinct and
  explicitly labelled (`boundary_kind="revised"`) — never commingled with PIT
  (Phase 14 D10 / Phase 15 §6 discipline).

---

## 15. New invariants

Following Phase 15's D9 precedent (a new per-phase property is documented in the
phase's locked doc, **not** necessarily added to the numbered `data-model.md §12`
registry), Phase 17 proposes four per-phase invariants:

- **FA-1 (reference & corpus pinning):** an attribution record folds the
  `result_hash` of its subject and every factor into `attribution_id`; distinct
  corpus pins across references are surfaced (`pin_mismatch`), never silently
  reconciled. A changed corpus yields a different `attribution_id`.
- **FA-2 (ex-post, not PIT):** `FactorAttribution` is an ex-post research
  statistic — not a `Pit*` type, exposing no as-of accessor, inadmissible where a
  PIT signal/value is required (the inv. 28 / SD-2 analogue).
- **FA-3 (commensurable inputs):** the subject and every factor must share
  `schedule_id`, equal `period_returns` length, and the same
  `backtest_engine_version_id`; otherwise the run fails closed. Returns are never
  padded, truncated, or realigned.
- **FA-4 (fail-closed estimation):** a singular/collinear design, insufficient
  periods, or a zero-variance regressand/regressor yields first-class `UNDEFINED`
  cells with reasons; never a fabricated coefficient or divide-by-zero.

Whether any of these is promoted to a numbered `data-model.md §12` invariant is an
approval-gated decision (D6); the default (Phase 15 precedent) is per-phase, no
registry edit.

---

## 16. Testing strategy

Pure offline/synthetic; `uv run` pytest + ruff + ruff format --check + mypy
(strict, src + tests), as every prior phase.

- **Determinism/golden:** same spec → byte-identical `attribution_id` /
  `result_hash`.
- **Numerical correctness:** hand-computed OLS on small synthetic
  `period_returns` — verify betas, alpha, R², adjusted R², std errors, t-stats
  against exact `Decimal` reference values; a single-factor case reproduces the
  Phase 15 alpha/beta (regression-parity test).
- **Fail-closed estimation:** collinear factors → `SINGULAR_DESIGN`; `n = K+1` →
  `INSUFFICIENT_PERIODS` on residual-df diagnostics; zero-variance regressand →
  `ZERO_VARIANCE`; perfect fit → `ZERO_RESIDUAL_VARIANCE`.
- **Commensurability:** differing `schedule_id` / length / engine version →
  `AttributionConsistencyError`; distinct corpus pins → `pin_mismatch` surfaced,
  not raised.
- **Resolution/drift:** absent reference, id-mismatch, and tampered
  `result_hash` each raise.
- **Round-trip:** `to_dict`/`from_dict` byte-identical; write-once idempotence and
  differing-payload rejection.
- **Type-boundary (FA-2):** `FactorAttribution` exposes no `Pit*`/as-of accessor
  (a red-team test that it cannot substitute where a PIT value is required).

---

## 17. Performance considerations

- `K` is small by design (attribution studies use a handful of factors). v1 caps
  `K ≤ K_MAX` (proposed default **8**; approval-gated D3), so the linear solve is a
  `(K+1)×(K+1)` exact-`Decimal` Cholesky — negligible cost dominated by the O(n·K)
  matrix assembly over `n` periods.
- No caching layer is proposed; determinism makes results recomputable, and the
  write-once sidecar already provides retrieval.
- Retaining the full residual series is O(n); the approval-gated D4 chooses
  between storing the residual vector (auditable) versus only its digest (compact).

## 18. Security / correctness considerations

- Exact `Decimal` throughout; the only numerically delicate step is the linear
  solve. The design uses a symmetric factorization with an **exact pivot zero
  test** (a non-positive/￼zero pivot ⇒ `SINGULAR_DESIGN`), so near-collinearity
  degrades to a first-class UNDEFINED rather than an unstable coefficient — no
  float tolerance heuristics enter identity.
- No untrusted input execution (declarative spec only). No new I/O beyond the
  existing sidecar reads/writes. No network, no dependency, no DB.
- Reference resolution re-verifies `result_hash` (drift detection) before
  regressing — a tampered sidecar record fails closed.

## 19. Documentation changes (on completion only)

- New `docs/phase17-factor-attribution-locked.md` (the normative locked spec).
- `docs/index.md`: a Phase 17 bullet + Status line update.
- `ARCHITECTURE.md`: a component-status row (Planned → ✅ Exists).
- `README.md`: capability bullet + Project-Status row `v0.14.0`; advance "Next".
- `docs/data-model.md`: **only** if D6 promotes an FA-* invariant to §12
  (default: no edit; per-phase documentation in the locked doc, Phase 15 D9
  precedent).

None of these are edited during the design step.

## 20. Explicit out-of-scope (v1)

- **Rolling/windowed attribution** (time-varying betas) — v1 is a single
  full-sample regression.
- **Robust / heteroskedasticity-consistent standard errors** (HAC/Newey–West),
  GLS, WLS, ridge/regularized regression, stepwise selection.
- **Factor construction** — Phase 17 does *not* build factor portfolios; each
  factor must already be a sealed `BacktestResult` (candidate B remains a separate
  future phase).
- **External factor libraries / index ingestion** — no Fama–French files, no
  fabricated series (the Phase 15 D3 discipline).
- **Cross-sectional (Fama–MacBeth) premia** — candidate D, rejected/deferred.
- **Covariance/risk models and optimization** — candidate E, deferred.
- **Bootstrapped/Monte-Carlo confidence intervals, RNG** — none (Phase 15 D7
  discipline).
- **REVISED attribution scope** — reserved, explicitly labelled if ever built.
- **Presentation** — no renderer in this layer; a Phase 14-style report could
  reference an attribution record in a later edit, out of scope here.
- **Batch attribution over an experiment** — a thin future loop, out of scope.

## 21. Approval-gated decisions

- **D1 — Factor model:** each factor is a **sealed `BacktestResult`** (generalize
  Phase 15 D3 from one benchmark to *K* factors). *Recommended: yes.* Alternative
  (caller-supplied return series / external index files) is rejected — it would
  reintroduce fabricated/un-pinned data. **Architectural** (defines the input
  contract).
- **D2 — Identity pattern:** single id (`attribution_id`, `research_result_id`
  aliases it), folding all referenced `result_hash`es + annualization convention.
  *Recommended: yes* (matches analytics). **Architectural.**
- **D3 — `K_MAX`:** cap the number of factors (proposed **8**). *Approval needed*
  for the exact cap.
- **D4 — Residual retention:** store the full residual vector (auditable) vs only
  its digest (compact). *Recommended: digest + summary stats* to keep the record
  compact; approval needed.
- **D5 — Standard-error basis:** classical OLS covariance `σ̂²(XᵀX)⁻¹` only in v1
  (robust SEs out of scope §20). *Recommended: yes.*
- **D6 — Invariant registration:** keep FA-1..FA-4 as **per-phase** invariants in
  the locked doc (Phase 15 D9 precedent), *not* added to `data-model.md §12`.
  *Recommended: per-phase;* approval needed if any should be promoted.
- **D7 — Version label:** README `v0.14.0`. *Recommended: yes.*

## 22. Open questions

1. **Excess-return convention:** subtract `risk_free_per_period` from *both* the
   subject and each factor (excess-on-excess, recommended), or from the subject
   only? (Affects the intercept's interpretation.)
2. **Intercept annualization:** report alpha per-period and separately annualized
   by `periods_per_year` (like Phase 15), or per-period only?
3. **Degenerate-factor policy:** if *one* factor is collinear with others, fail
   the whole coefficient block (`SINGULAR_DESIGN`, recommended — honest and
   simple) or drop that factor and report the reduced model? (Dropping silently
   changes the model the caller requested.)
4. **`K_MAX` value** (D3) — is 8 the right cap, or higher/lower?
5. **Residual retention** (D4) — full vector vs digest?
6. Should a later Phase-14 report scope be reserved now to reference attribution
   records, or left entirely to that phase?

---

## Final note

Nothing in this document is built until it is explicitly approved. No source, no
test, no README/ARCHITECTURE/index/data-model edit, no commit, no push, no tag,
no release has been made as part of this design step.
