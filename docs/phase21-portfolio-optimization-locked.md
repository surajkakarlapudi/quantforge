# Phase 21 — Portfolio Optimization (Factor-Risk-Aware Minimum-Variance) (LOCKED)

> **Status:** Locked normative specification. The Phase 21 proposal was **approved as
> recommended** — fully-invested global minimum-variance only (Q1 deferred), package /
> type names as proposed (Q2), the sole v1 objective `minimum_variance` (Q3), Phase 20's
> `N_MAX = 16` inherited (Q4), and the `PO-1..PO-5` `data-model.md §12` block + docs added
> at implementation time (Q5). This document reflects the **actual implementation** and is
> the source of truth; it supersedes the recommendations in
> [phase21-portfolio-optimization-proposal.md](phase21-portfolio-optimization-proposal.md).
> Every conditional reference in the proposal ("recommended", "approval-gated") is
> resolved here to a committed decision.
>
> **One-line thesis:** Phase 21 adds a deterministic, content-addressed **portfolio
> optimizer** — the first optimization layer in the project, a pure consumer strictly
> *above* the Phase 20 factor-risk-modelling layer (as Phase 20 consumes Phase 19). Given a
> declarative `PortfolioOptimizationSpecification` naming exactly one sealed
> `FactorRiskModel`, `PortfolioOptimizationEngine.optimize(...)` resolves that model from
> the shared Phase 8 research sidecar, re-verifies it, reconstructs the full symmetric
> `N x N` factor covariance matrix `Σ` from its sealed upper-triangle covariance cells, and
> solves the **fully-invested global minimum-variance (GMV)** problem `min wᵀΣw s.t.
> 1ᵀw = 1` in **closed form** under the pinned `Decimal` context using the existing
> exact-`Decimal` `_linalg` `ldl`/`ldl_solve` primitives: `w = Σ⁻¹1 / (1ᵀΣ⁻¹1)`, achieved
> per-period variance `wᵀΣw`, and volatility. A non-positive-definite `Σ` is a first-class
> `UNDEFINED` `SINGULAR_COVARIANCE` result, never a divide-by-zero, pseudo-inverse, dropped
> factor, or regularized matrix. It seals a `PortfolioOptimization` `ResearchRecord`
> write-once to the existing sidecar. It composes Phase 20 only, consumes **no**
> `BacktestResult` and is not one, fabricates **no** expected returns, introduces **no**
> new data source, **no** new store, **no** runtime dependency, **no** new PIT surface,
> **no** `_linalg` change, and **no** database.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **The smallest architecturally honest optimizer:** a fully-invested global minimum-variance portfolio over the *N* factors of one sealed `FactorRiskModel`, `min wᵀΣw s.t. 1ᵀw = 1`, solved in closed form. No mean-variance, maximum-Sharpe, risk-parity, tracking-error, long-only/box/leverage/concentration (inequality) constraints, robust/Bayesian/Black-Litterman, walk-forward, transaction-cost, asset-level construction, or execution — each is deferred or rejected with a grounded repository reason (§9). |
| **D-INPUT** | **A new pure-consumer sibling layer strictly *above* Phase 20** (the analogue of Phase 20 consuming Phase 19). It resolves exactly one already-sealed `FactorRiskModel` from the shared research sidecar; it consumes **no** `BacktestResult` and produces none, reads **no** raw corpus and re-derives nothing from source, creates **no** second covariance source, and **modifies no** prior-phase vocabulary, engine, or identity. |
| **D-VARS** | **Decision variables are factor weights `w ∈ ℝᴺ`**, one weight per factor in the risk model's semantic order (`factor_1..factor_N`) — a linear combination of the sealed long/short factor portfolios, never asset weights (the repository seals no asset-level return/covariance artifact). A GMV weight may be negative (an honest long/short across factors); no non-negativity constraint applies in the fully-invested v1. |
| **D-OBJ** | **Objective = `minimum_variance` only** (closed vocabulary). It needs only `Σ` — no expected-return vector, no risk-free rate, no benchmark, no risk-aversion parameter. The ex-post factor **means** in the risk model are deliberately **unused** as `μ` (using realized in-sample means as a forward `μ` is the look-ahead the project forbids). Mean-variance / maximum-Sharpe are deferred pending a PIT-safe expected-return artifact (none exists). |
| **D-CONSTRAINT** | **One equality constraint: fully invested `1ᵀw = 1`.** A zero-parameter, exactly-representable budget constraint that makes GMV a portfolio and admits the closed form. `fully_invested` must be `True` in v1 (a `False` value would ask for the meaningless unconstrained minimum `w = 0` for a PD `Σ`); the flag is reserved so a future phase can add constraint variants without changing the request shape. General linear equality constraints `Aw = b` (proposal Q1) are **deferred**. |
| **D-COV** | **The sealed `FactorRiskModel` covariance is the single source, consumed as-is** — never recomputed, shrunk, or regularized (PO-3). `Σ` is reconstructed full-symmetric from the sealed **upper triangle** (`i <= j`), each per-period cell KNOWN by construction. GMV weights are invariant to positive scaling of `Σ`, so the **per-period** covariance is used and the achieved **per-period** variance is sealed (`covariance_basis = "per_period"`, folded into identity); a reader may annualize. |
| **D-SOLVE** | **Closed form via the existing exact-`Decimal` `_linalg` primitives — no `_linalg` change.** Factorize `Σ = LDLᵀ` (`ldl`); solve `Σx = 1` (`ldl_solve`); `s = Σxᵢ = 1ᵀΣ⁻¹1`; `wᵢ = xᵢ/s`; variance `wᵀΣw` as an inline quadratic form; volatility `√variance` via `Decimal.sqrt`. All under the pinned `localcontext`. No matrix inverse, no KKT system, no active set, **no iteration, no float, no RNG, no wall-clock**. |
| **D-SINGULAR** | **A non-positive-definite `Σ` is a first-class `UNDEFINED` `SINGULAR_COVARIANCE` result** (the exact `ldl` zero-pivot test — no float tolerance), never a divide-by-zero, pseudo-inverse, dropped factor, or regularized matrix (PO-4). Every weight cell and the variance/volatility are UNDEFINED together. The direct analogue of `SINGULAR_DESIGN` in the exact-`Decimal` OLS solver. A non-positive `s` or a negative quadratic form (both unreachable for a PD `Σ`) are treated defensively as `SINGULAR_COVARIANCE`. |
| **D-NMAX** | **`N_MAX = 16`, `_MIN_FACTORS = 2`, inherited from Phase 20** (re-checked fail-closed at the engine). A single-factor "portfolio" has the trivial GMV `w = 1` and no cross-factor structure; a factor count outside `2..N_MAX` is a consistency defect, raised — never optimized into a degenerate or oversized matrix. No separate optimizer cap. |
| **D-EXPOST** | **The output is ex-post, never PIT (PO-2).** A function of the ex-post `FactorRiskModel` `Σ` is itself ex-post. `PortfolioOptimization` is **not** a `Pit*` type, exposes **no** as-of accessor, and is inadmissible where a PIT signal/value is required. `boundary_kind = "pit"` documents only that the *underlying factor portfolios were PIT walks*; it never claims the weights are a PIT value. Set unconditionally (a `FactorRiskModel` is ex-post by construction), so **no new PIT resolution** is introduced. |
| **D-INVARIANTS** | **PO-1..PO-5 are documented both as phase-local invariants here and as a small additive `data-model.md §12` block** mirroring the SD-1..4 / XS-1..4 / P19-1..5 / FR-1..5 blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.18.0`** (Phase 20 = v0.17.0, confirmed by git tags). Domain tag `optimization/1`; engine-version string `optimization-engine/1`; solve-method string `optimization-solve/1`; record-format string `optimization-result/1`. The package `__version__` string is unchanged (versioning is by content-addressed ids, not a semver string). Any pre-existing README version-label drift is **not** fixed here. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; none changes an identity discipline or weakens an invariant.

1. **`name` and `spec_version` are not stored as separate top-level `PortfolioOptimization`
   fields.** The proposal §14.3 sketch listed neither explicitly, but for symmetry with the
   FR deviation the implementation reads both from the embedded `optimization_spec` dict
   (via the private `_spec_str` helper) inside the `optimization_id` property, avoiding a
   second stored copy and any drift between them. The identity fold is unchanged — the
   `name` and `spec_version` components of `optimization_id` are exactly the spec's own.
2. **The pure compute type is `MinVarianceSolution` (in `solve.py`).**
   `solve_min_variance(covariance, *, context)` returns a `MinVarianceSolution` (`status`,
   `weights`, `variance`, `volatility`); the engine wraps its weight `StatValue`s in
   `WeightCell`s (in factor order) and copies the blocks straight into
   `PortfolioOptimization.seal(...)`. The split keeps the pure compute layer free of the
   record/store vocabulary; the sealed shape and identity fold are exactly as proposed
   (the analogue of Phase 20's `MomentEstimate`).
3. **Version constants are split across `version.py` and `result.py`.**
   `OPTIMIZATION_SPEC_VERSION` / `OPTIMIZATION_ENGINE_VERSION` / `OPTIMIZATION_SOLVE_VERSION`
   live in `version.py`; `OPTIMIZATION_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, and
   `COVARIANCE_BASIS_PER_PERIOD` live in `result.py` (beside the record they describe). No
   value or fold changes. The sealed record's `formula_version` field carries
   `OPTIMIZATION_SOLVE_VERSION` (`"optimization-solve/1"`).
4. **`errors.py` defines the two-error hierarchy as proposed**
   (`PortfolioOptimizationError → PortfolioOptimizationConfigurationError,
   PortfolioOptimizationConsistencyError`).

---

## 2. Architecture (locked)

Phase 21 is a thin optimization layer *above* Phase 20, structurally the **pure-consumer
sibling of Phase 20** (which consumes sealed `FactorPortfolio`s) — because Phase 21, like
the risk model, references a **sealed artifact** (the one `FactorRiskModel`) by its
`result_hash`, rather than reading any raw corpus. It follows the extension recipe every
prior phase uses: a versioned immutable request object → a fail-closed engine reached from
`Workspace` via a lazy, cycle-free `@property` → a distinct result type → content-addressed
identity with fresh domain tags → data conditions recorded as first-class `UNDEFINED`
values, defects raised → compute-on-demand with the shared write-once sidecar. It folds the
referenced model's sealed `result_hash` into the optimization's identity, so the id is
**transitively** sensitive to any change in the risk model — and, through it, any referenced
factor or corpus — without re-reading a corpus (PO-1).

```
                 PortfolioOptimizationSpecification   (declarative request, content-addressed)
                          |
                          v
   Workspace.optimization_engine  --->  PortfolioOptimizationEngine.optimize(spec)
                          |                 |
                          |   resolve factor_risk_id from the shared sidecar          — fail closed
                          |     store.read_as(id, FactorRiskModel.from_dict)
                          |     verify resolved.research_result_id == requested id (PO-1)
                          |     payload not a FactorRiskModel -> fail closed (PO-1/PO-3)
                          |     (no content->hash recompute; risk model result_hash is FOLDED, PO-1)
                          |     factor count n in 2..N_MAX, else fail closed (PO-1)
                          |
                          |   reconstruct full symmetric Σ from the upper-triangle covariance:
                          |     each i<=j cell present, KNOWN, a finite decimal string   — fail closed (PO-3)
                          |     mirror Σ[j][i] = Σ[i][j]; NEVER repair/regularize/alter   (PO-4)
                          |
                          |   solve under the pinned Decimal context (prec 34, HALF_EVEN):
                          |     ldl(Σ)  ->  None  => SINGULAR_COVARIANCE (first-class UNDEFINED)  (PO-4)
                          |     else x = ldl_solve(L, D, ones);  s = Σ x_i  (= 1ᵀΣ⁻¹1 > 0)
                          |     w_i = x_i / s;  variance = wᵀΣw (inline);  volatility = √variance
                          v                 v
        PortfolioOptimization (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
        store.read_as(id, PortfolioOptimization.from_dict)  (typed, byte-identical round-trip)
```

**New package `src/quantforge/optimization/`** (mirrors `factorrisk/`):

- `errors.py` — `PortfolioOptimizationError` → `PortfolioOptimizationConfigurationError`,
  `PortfolioOptimizationConsistencyError`.
- `version.py` — `PortfolioOptimizationEngineVersion` (folds the pinned decimal context
  **and** the solve-method version `optimization-solve/1` into `config_hash`);
  `OPTIMIZATION_ENGINE_VERSION = "optimization-engine/1"`,
  `OPTIMIZATION_SOLVE_VERSION = "optimization-solve/1"`,
  `OPTIMIZATION_SPEC_VERSION = "optimization/1"`; `default_decimal_context()`. The id
  property is `optimization_engine_version_id`. (The engine-version id is **not**
  re-implemented in `identity.py` — one source of truth.)
- `identity.py` — `optimization_result_hash`, `optimization_id`. Fresh record domain tag
  `optimization/1`.
- `model.py` — `OptimizationStatus` / `OptimizationUndefinedReason` vocabulary; `StatValue`
  (a KNOWN decimal string **or** UNDEFINED+reason); `factor_label`; the nested `WeightCell`.
- `spec.py` — `PortfolioOptimizationSpecification`, full construction-time validation;
  `OBJECTIVE_MINIMUM_VARIANCE`.
- `solve.py` — the pure closed-form GMV solver (`solve_min_variance`, `MinVarianceSolution`).
  Pure; reads no store; takes a decimal-string `Σ` + context, returns KNOWN / UNDEFINED
  cells under the pinned context via `_linalg` `ldl`/`ldl_solve`.
- `result.py` — `OPTIMIZATION_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`,
  `COVARIANCE_BASIS_PER_PERIOD`, `PortfolioOptimization` (a `ResearchRecord` with `.seal` /
  `to_dict` / `from_dict`).
- `engine.py` — `PortfolioOptimizationEngine` (constructed from `Workspace`; reuses the
  workspace's shared Phase 8 research sidecar): resolve + verify the risk model →
  reconstruct `Σ` → solve → seal → write-once.
- `__init__.py` — package exports (`PortfolioOptimizationSpecification`,
  `PortfolioOptimization`, `WeightCell`, the vocabulary, errors, version, identity helpers).

**Edits to existing source** (all additive; none altering any existing identity):

1. `workspace.py` — one lazy `optimization_engine` `@property` (+ its
   `self._optimization_engine: object | None = None` cache line), following the
   `factor_risk_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of
   `PortfolioOptimizationSpecification` and `PortfolioOptimization` (spec + result only; the
   engine is reached via `Workspace`).
3. `tests/test_smoke.py` — one additive public-API export assertion.

**No edit to** `_linalg`, `backtest/*`, `analytics/*`, `attribution/*`, `crosssection/*`,
`experiment/*`, `report/*`, `diagnostics/*`, `factorportfolio/*`, `factorrisk/*`, `panel/*`,
`market/*`, `universe/*`, `factors/store.py`, or any identity/version module of a prior
phase. **No new PIT resolution, no new store, no new data source, no `_linalg` change, and
no execution logic** (Phase 21 does a closed-form solve only; it promotes no shared helper).

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
wall-clock, no RNG.

### 3.1 `PortfolioOptimizationSpecification` (declarative request)

```
PortfolioOptimizationSpecification(
    name: str,                              # non-empty
    factor_risk_id: str,                    # the sealed FactorRiskModel to optimize over (non-empty)
    objective: str = "minimum_variance",    # closed vocabulary (v1: exactly this)
    fully_invested: bool = True,            # v1: must be True (the one constraint); reserved for extension
    spec_version: str = "optimization/1",
)
```

Construction-time validation (fail closed, `PortfolioOptimizationConfigurationError`): an
empty `name` / `spec_version` / `factor_risk_id`; an `objective` outside the closed
vocabulary (`_OBJECTIVES = {"minimum_variance"}`); or `fully_invested` not identically
`True` (an explicit identity check — `bool` subclasses `int`, so `1` must not masquerade as
`True`). It reads no store and no wall clock — it cannot know whether the referenced id
exists (the engine's fail-closed resolution step) or whether `Σ` is positive-definite (that
needs the resolved matrix); it validates only the request's internal shape. The referenced
risk model's *content* is not part of the spec identity — that is folded by the engine from
the resolved record's `result_hash` — so the spec is a stable declaration independent of
whether the referenced result has been computed yet. `to_dict()` emits `{spec_version, name,
factor_risk_id, objective, fully_invested}`, embedded in the sealed record.

### 3.2 GMV compute block (`solve.py`, internal)

`solve_min_variance(covariance, *, context)` takes the full symmetric `N x N` matrix `Σ`
(`N >= 1`; the engine reconstructs it from the sealed upper-triangle cells) as a list of
`N` rows of already-canonical decimal strings, and returns a `MinVarianceSolution`:

```
MinVarianceSolution(
    status: OptimizationStatus,            # OPTIMAL | UNDEFINED
    weights: tuple[StatValue, ...],        # per-factor GMV weights in factor order
    variance: StatValue,                   # achieved per-period wᵀΣw
    volatility: StatValue,                 # √variance
)
```

`.optimal(...)` builds a KNOWN solution from canonical decimal strings; `.singular(n)`
builds the `UNDEFINED` `SINGULAR_COVARIANCE` solution (every weight, variance, and
volatility UNDEFINED together — never a partial answer). It fails closed
(`PortfolioOptimizationConsistencyError`) on `n < 1`, a ragged (non-square) matrix, or a
non-decimal / non-finite cell. `StatValue` is the UNDEFINED-preserving cell:
`StatValue.known("<decimal string>")` **or**
`StatValue.undefined(OptimizationUndefinedReason.SINGULAR_COVARIANCE)`; exactly one of
`value` / `reason` is populated (enforced at construction). Never a bare float, never
silently omitted.

### 3.3 `PortfolioOptimization` (implements `ResearchRecord`)

```
PortfolioOptimization(
    optimization_engine_version_id: str,
    optimization_spec: dict[str, object],        # the full PortfolioOptimizationSpecification.to_dict()
    objective: str,                              # "minimum_variance"
    constraint_spec: dict[str, object],          # {"fully_invested": True}
    covariance_basis: str,                       # "per_period"
    risk_model_ref: tuple[str, str],             # (factor_risk_id, result_hash) — transitive pin (PO-1)
    boundary_kind: str,                          # "pit" (documents the INPUT side; PO-2 — not a PIT value)
    schedule_id: str,                            # carried from the risk model
    factor_portfolio_engine_version_id: str,     # carried from the risk model
    n_factors: int,                              # N (= the risk model's factor count)
    factor_labels: tuple[str, ...],              # factor_1..factor_N (order = risk model order)
    status: OptimizationStatus,                  # OPTIMAL | UNDEFINED
    weights: tuple[WeightCell, ...],             # per-factor weights (UNDEFINED cells iff status UNDEFINED)
    portfolio_variance: StatValue,               # achieved wᵀΣw (UNDEFINED iff singular)
    portfolio_volatility: StatValue,             # √variance
    dataset_version_ids: tuple[str, ...],        # carried fundamentals pins (from the risk model)
    market_dataset_version_ids: tuple[str, ...], # carried market pins (from the risk model)
    formula_version: str,                        # "optimization-solve/1"
    result_hash: str,                            # canonical JSON over the ordered output cells
)

# derived, never stored as state:
optimization_id     property -> sha256 folding engine version + spec identity (name,
                                spec_version from the embedded spec) + objective + canonical
                                constraint spec + covariance basis + risk model id +
                                risk model result_hash + result_hash
research_result_id  property -> alias of optimization_id  (the ResearchRecord key)
factor_risk_id      property -> the referenced (optimized) risk model's id
pin_mismatch        property -> True iff either carried-pin tuple has length > 1 (surfaced)
```

- `WeightCell(label, value)` — one factor's optimal weight; `label` the name-free
  `factor_label` (`factor_1`, `factor_2`, …) matching the risk model's factor order;
  `value` a `StatValue` (KNOWN decimal string when `OPTIMAL`, or UNDEFINED
  `SINGULAR_COVARIANCE` when `Σ` is not positive-definite — every weight UNDEFINED
  together, never a partial vector). A GMV weight may be negative.
- `to_dict()` keys include `optimization_id`, `research_result_id` (alias so the generic
  reader keys correctly), and every field above; `risk_model_ref` serializes as a
  `[factor_risk_id, result_hash]` pair. A KNOWN cell emits `value` only; an UNDEFINED cell
  emits `reason` only.
- `from_dict` is the fail-closed inverse; `optimization_id` / `research_result_id` are
  re-derived by their properties, **never read from state**, so `from_dict(to_dict(r))`
  re-emits identical bytes and the same `result_hash`, and a tampered stored id is ignored.
  A malformed cell (unknown status, missing value/reason, unrecognized reason) is refused
  with a `ValueError`.
- `.seal(...)` is the identity-computing constructor: it folds the ordered computed-output
  cells (the status cell, then the per-factor weight cells in factor order, then the
  variance and volatility cells, each tagged by its block so two structurally different
  records can never collide) into `result_hash`, so identity is a pure function of the
  request + referenced content + computed answer, never caller-supplied.

**What the record deliberately does NOT hold:** any copy of `Σ` (only the `risk_model_ref`
pointer); any expected return; any float; any wall-clock or RNG value; any `Pit*` type or
as-of accessor (PO-2); any execution / holdings / cash / cost state (PO-5); any
presentation.

### 3.4 Closed v1 vocabulary

`OptimizationUndefinedReason` (closed, 1): `SINGULAR_COVARIANCE`. `OptimizationStatus` (2):
`OPTIMAL`, `UNDEFINED`. Extending the reason set is an explicit future edit that hashes
distinctly (a new reason changes `result_hash`) — never an implicit fallback.

---

## 4. Solve method (locked, folded into `optimization-solve/1`)

Changing any of these bumps `OPTIMIZATION_SOLVE_VERSION`, so a value computed under one
method can never be silently reinterpreted under another. All arithmetic runs under an
explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`), never the ambient process
context. `Decimal.sqrt(context)` covers the volatility root. No float touches any value.

- **Factorize (D-SOLVE / D-SINGULAR).** `Σ = LDLᵀ` via the shared exact-`Decimal`
  `ldl(Σ)`. Its exact zero-pivot test (a non-positive pivot) *is* the
  positive-definiteness / singularity test — no float tolerance. A `None` return is
  `SINGULAR_COVARIANCE`.
- **Solve.** `Σx = 1` (the all-ones vector) via `ldl_solve(L, D, ones)`; `x = Σ⁻¹1`.
- **Normalize.** `s = Σxᵢ = 1ᵀΣ⁻¹1` (strictly positive for a PD `Σ`); a non-positive `s`
  is treated defensively as `SINGULAR_COVARIANCE` so the fully-invested weight `w = x/s` is
  never a divide-by-zero. `wᵢ = xᵢ/s` — the closed-form GMV weights, summing to exactly one.
- **Variance (D-COV).** `wᵀΣw` as an inline quadratic form over the reconstructed `Σ` (a
  double loop of exact-`Decimal` multiply-adds; algebraically equal to `1/s`, so the
  computation self-verifies). A negative quadratic form (unreachable for a PD `Σ`) is
  treated defensively as `SINGULAR_COVARIANCE`.
- **Volatility.** `√(wᵀΣw)` via `Decimal.sqrt` under the pinned context.
- **Scale-invariance (D-COV).** GMV weights depend only on the direction of `Σ⁻¹1`, so
  scaling `Σ` by any positive constant leaves the weights unchanged (only the variance
  scales). This justifies using the per-period covariance and folding
  `covariance_basis = "per_period"` — the annualized covariance would give identical
  weights.
- **Degeneracy (never a divide-by-zero, never repaired).** A non-positive-definite `Σ`
  (rank-deficient / collinear factors / a zero-variance factor / too few common periods)
  has no inverse, so the fully-invested GMV is genuinely undefined and is recorded
  `UNDEFINED` `SINGULAR_COVARIANCE` — the covariance matrix is never repaired, regularized,
  or pseudo-inverted (PO-4).

---

## 5. Identity / determinism (locked)

- Domain tags via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): record tag `optimization/1`;
  engine tag `optimization-engine/1`; solve tag `optimization-solve/1`.
- `optimization_engine_version_id = sha256(code_version "optimization-engine/1",
  config_hash)` where `config_hash =
  sha256("prec=34\x00round=ROUND_HALF_EVEN\x00solve=optimization-solve/1")`. Any change to
  the decimal context **or** the solve method yields a new engine id.
- `optimization_result_hash = sha256(canonical JSON over the ordered computed-output cells:
  the status cell `{"block":"status", status}`, then the per-factor weight cells in factor
  order — each `{"block":"weight", label, value}` — then the variance cell
  `{"block":"variance", value}` and the volatility cell `{"block":"volatility", value}`)`.
  Sensitive to every computed value: one differing cell changes it. The factor count,
  labels, carried pins, and references are **not** folded here (they are request /
  provenance metadata, folded into `optimization_id` through the request + reference
  instead).
- `optimization_id = sha256`, NUL-joined, in this exact order: `optimization/1`,
  `optimization_engine_version_id`, `name`, `spec_version`, `objective`, the canonical-JSON
  `constraint_spec`, `covariance_basis`, `factor_risk_id`, `factor_risk_result_hash`, and
  `optimization_result_hash`.
- `research_result_id` aliases `optimization_id` (a single id).

**Folds (changes identity):** the engine-logic + solve-method + decimal-context version ✔;
the declared request (name, spec version, objective, the canonical-JSON constraint spec) ✔;
the covariance basis ✔; the **referenced content** — the risk model's `result_hash`, so the
id is **transitively** sensitive to any change in the risk model, its factors, or its corpus
(PO-1) ✔; the computed answer (via `optimization_result_hash`) ✔. **Does NOT fold:** the
record schema/format version (`OPTIMIZATION_RESULT_FORMAT_VERSION` — a container concern);
the carried corpus pins (surfaced via `pin_mismatch`, inherited from the risk model, not
folded — the D-PIN convention); `periods_per_year` (GMV weights are invariant to positive
scaling of `Σ`, so annualization cannot change the answer — folding it would create spurious
distinct ids for identical results); factor labels beyond their order (already fixed by the
risk model reference); any presentation, wall-clock, RNG, `id()`, or iteration order (the
weight cells preserve factor order).

`covariance_basis` is folded even though v1 fixes it to `"per_period"`, so a future
annualized-basis option can never collide. Same request + same sealed risk model → same
`optimization_id` and same bytes on any machine.

---

## 6. PIT semantics, provenance, storage (locked)

- **The output is ex-post, not PIT (PO-2).** The GMV weights are a function of the ex-post
  `FactorRiskModel` `Σ` and are themselves an ex-post research statistic, not a
  forward-usable PIT decision. `PortfolioOptimization` is **not** a `Pit*` type, exposes
  **no** as-of accessor, and is inadmissible where a PIT signal/value is required — the
  exact analogue of invariant 28 / SD-2 / XS-2 / P19-2 / FR-2. `boundary_kind = "pit"`
  documents only that the *underlying factor portfolios were PIT walks*; it does not claim
  the weights are a PIT value. The engine sets it unconditionally (a `FactorRiskModel` is
  ex-post over PIT-walked factor portfolios by construction — there is no revised variant —
  so no runtime PIT check is needed, and no new PIT resolution is introduced).
- **An optimization is not a `BacktestResult` and performs no execution (PO-5).**
  `PortfolioOptimization` is a distinct record type; it does not enter Phase 12's identity,
  cannot be passed where a `BacktestResult` is required (enforced by type), and simulates no
  fills, cash, positions, or costs — it is an allocation decision, not an execution.
- **Reference verification + transitive pinning (PO-1).** The referenced `factor_risk_id`
  is resolved from the shared sidecar via `store.read_as(id, FactorRiskModel.from_dict)`; a
  missing id, a payload that does not decode as a `FactorRiskModel` (e.g. a factor-portfolio
  id passed by mistake), or a resolved record whose own `research_result_id` disagrees with
  the requested id is a `PortfolioOptimizationConsistencyError` (we refuse to optimize an
  artifact we cannot materialize or trust). The risk model's sealed `result_hash` is
  **folded into the optimization's identity**, so the id is transitively sensitive to any
  change in the risk model.
- **Single covariance source; no fabricated inputs (PO-3).** The optimizer consumes the
  sealed covariance as-is and never recomputes, shrinks, or regularizes it, and never
  fabricates an expected-return, risk-free, or benchmark input; the v1 objective depends on
  `Σ` only. The factor count must lie in `2..N_MAX` (re-checked fail-closed).
- **Covariance reconstruction (PO-3/PO-4).** `Σ` is rebuilt dense `N x N` from the sealed
  **upper triangle** (`i <= j`), mirroring `Σ[i][j]` into `Σ[j][i]`. Re-verified fail-closed
  (never trusting the sealed record blindly): every index is in range with `i <= j`, no
  upper-triangle position is missing or set twice, and every used cell is KNOWN with a
  string value — an UNDEFINED, non-string, duplicated, or missing cell is a corrupt input
  and raises. The matrix is **never** repaired, regularized, or altered — a
  non-positive-definite `Σ` is the solve layer's UNDEFINED `SINGULAR_COVARIANCE` concern
  (PO-4), not this layer's to fix.
- **Fail-closed degeneracy (PO-4).** A non-positive-definite `Σ` is a recorded `UNDEFINED`
  `SINGULAR_COVARIANCE`, never a divide-by-zero, pseudo-inverse, dropped factor, or
  regularized matrix — exactly as the exact-`Decimal` OLS solver records `SINGULAR_DESIGN`.
- **Provenance.** The record embeds the full declared spec (`optimization_spec`), the
  `(factor_risk_id, result_hash)` reference, the objective, the constraint spec, the
  covariance basis, the shared `schedule_id` and producing `factor_portfolio_engine_version_id`
  (carried from the risk model), the factor count and ordered labels, the per-factor weights,
  the achieved variance/volatility, the engine/solve versions, and the carried corpus pins —
  so the whole optimization is reconstructible and auditable from the record plus the
  referenced risk model in the same sidecar. It stores **no copy** of `Σ`.
- **Storage.** Zero new store types; the `ResearchResultStore` writes the record to
  `<root>/research/sha256-<hex>.json` in the existing container. Write-once and idempotent:
  re-optimizing an identical request is a byte-identical no-op; a differing payload under an
  existing id fails closed via the store's guard.

---

## 7. Failure / UNDEFINED behavior (locked)

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`PortfolioOptimizationConfigurationError` / `PortfolioOptimizationConsistencyError`):
- Malformed spec: an empty `name` / `spec_version` / `factor_risk_id`; an `objective`
  outside the closed vocabulary; `fully_invested` not identically `True`. *(configuration,
  at construction)*
- A non-`PortfolioOptimizationSpecification` argument to `optimize`. *(configuration)*
- A `factor_risk_id` absent from the sidecar, a payload that does not decode as a
  `FactorRiskModel`, or a resolved record whose `research_result_id` disagrees with the
  request. *(consistency, PO-1/PO-3)*
- A referenced model with a factor count outside `2..N_MAX`. *(consistency, PO-1)*
- A covariance cell that is out of range / not upper-triangle, UNDEFINED, non-string,
  duplicated, or missing (a corrupt sealed risk model). *(consistency, PO-3)*
- A corrupt / non-finite decimal covariance cell, or a ragged (non-square) reconstructed
  matrix (caught in the solve layer). *(consistency, never guessed)*

**Recorded as first-class `UNDEFINED` (never raised, never fabricated, never repaired —
PO-4):** a non-positive-definite `Σ` (the exact `ldl` zero-pivot test, or the defensive
non-positive-`s` / negative-quadratic-form guards) → `status = UNDEFINED`, reason
`SINGULAR_COVARIANCE`; every weight cell UNDEFINED, and `portfolio_variance` /
`portfolio_volatility` UNDEFINED. For a PD `Σ`, `1ᵀΣ⁻¹1 > 0` always, so an `OPTIMAL` result
never divides by zero. The record is still sealed and persisted write-once.

**Surfaced, never raised (inherited D-PIN convention, PO-3):** more than one distinct
fundamentals `dataset_version_id` or market `market_dataset_version_id` carried from the
referenced risk model → `pin_mismatch = True` (mirrors `FactorRiskModel.pin_mismatch`). The
optimization is still sealed; a reader can see the referenced factors were not pinned
identically.

---

## 8. Public API (locked)

```python
from quantforge import (
    Workspace,
    PortfolioOptimizationSpecification,
    PortfolioOptimization,
)

ws = Workspace.open(root)
spec = PortfolioOptimizationSpecification(
    name="min-variance-value-momentum",
    factor_risk_id=risk_model_id,  # a sealed FactorRiskModel id (2..16 factors)
    # objective="minimum_variance"  (v1 default; the only supported objective)
    # fully_invested=True           (v1 default; the only supported constraint)
)
opt = ws.optimization_engine.optimize(spec)  # sealed, write-once PortfolioOptimization

opt.status  # OptimizationStatus.OPTIMAL | UNDEFINED
opt.weights  # per-factor WeightCell tuple, in factor order (factor_1..factor_N)
opt.portfolio_variance  # achieved per-period wᵀΣw (StatValue; UNDEFINED iff singular)
opt.portfolio_volatility  # √variance (StatValue)
opt.pin_mismatch  # True iff the referenced risk model carried non-singular corpus pins
opt.research_result_id  # == opt.optimization_id (ResearchRecord)

# typed read-back (byte-identical round-trip)
again = ws.research_result_store.read_as(
    opt.research_result_id, PortfolioOptimization.from_dict
)
```

`PortfolioOptimizationEngine` is reached only through `Workspace.optimization_engine` (a
lazy, cached, cycle-free `@property` annotated `-> object`; engines are not re-exported at
top level). `optimize(spec) -> PortfolioOptimization` is the single entry point. No
`Company` method is added (an optimization spans a set of factors, not one filer).

---

## 9. Out of scope (strict)

Deferred to later, explicitly-labelled phases; Phase 21 does not absorb any:
- **Mean-variance / maximum-Sharpe / any expected-return-dependent objective** — needs a
  PIT-safe expected-return vector `μ`; none exists (the ex-post factor means are not a
  forward `μ`).
- **Long-only / box / gross-exposure / leverage / concentration (inequality) constraints;
  any iterative QP / active-set / interior-point solver** — exact `Decimal` iteration has no
  guaranteed finite termination without float tolerances.
- **Risk-parity / equal-risk-contribution** or any nonlinear / iterative-root-finding
  objective.
- **Tracking-error / benchmark-relative optimization** — no benchmark-in-factor-space
  artifact exists.
- **General linear equality constraints `Aw = b`** (factor-neutral / target-exposure;
  proposal Q1) — closed-form-compatible but broadens the vocabulary and needs a small
  additive `_linalg` matrix-multiply helper; **deferred** (v1 is fully-invested only).
- **Robust / Bayesian / Black-Litterman / shrinkage optimization**; any regularization of
  `Σ`.
- **Walk-forward / rolling / regime-conditioned optimization**; a time series of decisions.
- **Transaction-cost-aware optimization**; any use of current holdings.
- **Asset-level portfolio construction** — no PIT-safe asset covariance exists; any second
  covariance source; any recomputation or shrinkage of the Phase 20 covariance.
- **Any execution logic** (fills, cash, positions, costs, accounting) — that is Phase 12.
- **Any PIT-eligible portfolio-decision artifact** (the output is ex-post only).
- **A generic optimizer / Python-callback framework**; any float, RNG, or wall-clock use;
  any new store, database, network, ingestion, UI, or API.
- **Any modification to Phase 20** (or any prior phase) vocabulary, engine, or identity;
  feeding a `PortfolioOptimization` into Phase 12 or Phase 17.

---

## 10. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 21 suite added), deterministic across runs
  (including `-p no:randomly`).
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src tests`
  clean (strict).
- Zero runtime dependencies (stdlib `hashlib` / `json` / `dataclasses` / `Decimal` +
  existing `_linalg` only); no float in any path; no wall-clock/RNG in any identity or
  value; the volatility uses `Decimal.sqrt` under the pinned context; **no `_linalg`
  change**.
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** — the only source edits are the additive
  `Workspace.optimization_engine` property/cache line and the `__init__.py` re-exports; no
  edit to any other identity/version module or to `_linalg`, `backtest/*`, `analytics/*`,
  `attribution/*`, `crosssection/*`, `diagnostics/*`, `factorportfolio/*`, `factorrisk/*`,
  `panel/*`, `market/*`, or `universe/*`.
- Byte-identical `PortfolioOptimization` round-trip test proves `from_dict` introduces no
  drift and a tampered stored id is ignored; a determinism double-build and a
  two-independent-workspaces build prove `to_dict()` byte-equality and id sensitivity to
  each input.
- PO-1 (reference resolution + verification; risk model `result_hash` folded → transitive
  pinning; missing / drifted / non-risk-model reference raised; factor count bound), PO-2
  (no `Pit*` type / no as-of accessor; ex-post; not a `BacktestResult`), PO-3 (single
  covariance source, consumed as-is; corrupt covariance cell raised; `pin_mismatch`
  surfaced), PO-4 (non-PD `Σ` → recorded UNDEFINED `SINGULAR_COVARIANCE`, never a
  divide-by-zero or repaired matrix), PO-5 (distinct record type) each covered by a test.
- Docs updated; `ARCHITECTURE.md` "Portfolio optimization" row added, `docs/index.md`
  Phase 21 entry added, the `data-model.md §12` PO-1..PO-5 block appended, and `README.md`
  advanced to `v0.18.0` only when green.

---

## 11. Test coverage (locked)

New package `tests/optimization/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_solve.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline and
fully synthetic. Rather than seed a full multi-filer corpus and estimate a covariance (that
path is proven end-to-end in `tests/factorrisk`), the builders **synthesize** a sealed
`FactorRiskModel` directly from a hand-chosen covariance matrix and persist it to a real
`ResearchResultStore` sidecar via the workspace — giving exact control over the covariance
(clean closed-form GMV cases, singular matrices, and factor counts up to and beyond
`N_MAX`) while still exercising the true resolve → verify → reconstruct → solve → seal →
persist path. Coverage:

- **Construction validation** — the minimal request, the order-preserving canonical
  payload, and every fail-closed path (empty name / `factor_risk_id` / `spec_version`,
  objective outside the vocabulary, `fully_invested` not `True`) (SPEC).
- **Exact-`Decimal` GMV** against hand-computed closed-form solutions under the pinned
  context — the single-factor trivial `w = 1`; the equal-variance diagonal `w = (½, ½)`;
  the three-factor diagonal `diag(1,1,2) → (0.4, 0.4, 0.2)`, variance `0.4`; the correlated
  pair admitting a **negative** weight (`[[1,1.5],[1.5,4]] → (1.25, −0.25)`, variance
  `0.875`); the fully-invested `Σw = 1` check; the variance = `wᵀΣw` self-consistency; the
  volatility = `√variance`; scale-invariance (`Σ` and `k·Σ` give identical weights); the
  singular cases (collinear, zero, indefinite) → `SINGULAR_COVARIANCE` UNDEFINED (no
  exception, no divide-by-zero); and the fail-closed empty / ragged / non-decimal /
  non-finite paths; determinism of a repeated solve (SOLVE).
- `optimization_id` folding + sensitivity to each fold (engine version, name, spec version,
  objective, covariance basis, `factor_risk_id`, risk model `result_hash`, result hash),
  the constraint-spec fold, `optimization_result_hash` determinism + per-cell + order
  sensitivity (IDENTITY).
- Byte-identical `to_dict` / `from_dict`, derived-id survival, `research_result_id` alias,
  `factor_risk_id` accessor, `pin_mismatch` flagging, the FR-independent `boundary_kind =
  "pit"`, the ex-post boundary (no `pit`/`as_of` accessor, not a `BacktestResult`),
  tampered-id ignored, differing-answer id sensitivity (RESULT).
- End-to-end over the builders: the multi-factor GMV known closed form, weight cells
  labelled in factor order, provenance carried from the risk model, a negative weight
  carried through; the singular risk model → recorded UNDEFINED (still sealed and
  persisted); the factor-count bound (single-factor refused, `> N_MAX` refused, exactly
  `N_MAX` accepted); PO-1 reference verification (missing reference, non-risk-model payload,
  non-spec argument each fail closed); identity sensitivity to the referenced model and the
  request name; persistence + byte-identical round-trip from the sidecar; re-optimization
  idempotent no-op; two independent workspaces agree; `pin_mismatch` surfaced; the
  `Workspace.optimization_engine` wiring is cached (ENGINE).
- `tests/test_smoke.py` — an additive public-API export assertion for
  `PortfolioOptimizationSpecification` / `PortfolioOptimization`.

No real financial or network data; the architecture does not require it.
