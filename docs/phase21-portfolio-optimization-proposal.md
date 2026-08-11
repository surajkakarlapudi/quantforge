# Phase 21 — Portfolio Optimization (Factor-Risk-Aware Minimum-Variance) (PROPOSAL)

> **Status:** Proposal only. Nothing implemented. No source, tests, README,
> ARCHITECTURE.md, docs/index.md, docs/data-model.md, or any locked spec is modified by
> this document. Every recommendation here is conditional and awaits explicit approval
> before any Phase 21 code is written. Proposed release: **`v0.18.0`** (Phase 20 =
> `v0.17.0`).

---

## 1. Executive summary

Phase 20 established the risk-modelling capability class: given *N* sealed
`FactorPortfolio` return series it seals a `FactorRiskModel` carrying the per-factor mean
and volatility vectors, the `N x N` **population covariance** matrix `Σ`, and the
companion correlation matrix — all ex-post, all exact `Decimal`, all content-addressed.
Phase 20's own locked spec (§9) names Phase 21 as the intended consumer of that
covariance: *"Portfolio optimization / mean-variance / risk-parity weighting (needs the
covariance matrix this phase produces — the phase after this, Phase 21)."*

This proposal recommends the **smallest architecturally honest optimizer** that Phase 20
makes possible: a deterministic, closed-form **global minimum-variance (GMV) portfolio
over the *N* factors of a single sealed `FactorRiskModel`**, subject to the single
equality constraint that the factor weights sum to one (fully invested). Formally:

```
minimize   wᵀ Σ w      over w ∈ ℝᴺ
subject to 1ᵀ w = 1
```

whose unique closed-form solution when `Σ` is positive-definite is

```
w* = Σ⁻¹ 1 / (1ᵀ Σ⁻¹ 1),   achieved variance = 1 / (1ᵀ Σ⁻¹ 1).
```

The **decision variables are weights across the *N* factors** (i.e. across
`FactorPortfolio` combinations), never asset weights — because the only covariance the
repository provides in a PIT-disciplined, sealed form is the *factor* covariance, and no
asset-level return/covariance artifact exists (§7). The optimizer **consumes the sealed
`FactorRiskModel` `Σ` as-is** (it never recomputes covariance — Phase 20 is the single
source), and it **fabricates no expected returns**, which is exactly why the objective is
minimum-variance and not mean-variance or maximum-Sharpe (§8). The output is an **ex-post
research result**, not a PIT decision surface (§12).

Critically, the entire capability is implementable with the **existing** exact-`Decimal`
`_linalg` primitives (`ldl`, `ldl_solve`) — **no new linear algebra, no runtime
dependency, no float, no RNG, no wall-clock, no new store, no database, no new PIT
resolution, and no execution logic** (§11). The non-positive-definite covariance case is
already detected exactly by `ldl` (a non-positive pivot → `None`), so a singular /
rank-deficient `Σ` becomes a **first-class `UNDEFINED` result** (reason
`SINGULAR_COVARIANCE`), never a fabricated or repaired answer (§15) — the direct analogue
of the `SINGULAR_DESIGN` posture already in `_linalg/decimal_ols.py`.

Everything else in the classic optimization menu (long-only, box constraints, mean-variance,
maximum-Sharpe, tracking-error, risk-parity, robust/Black-Litterman, walk-forward,
asset-level construction, execution) is **explicitly rejected or deferred** (§5, §25),
because each either fabricates an input the repository cannot supply PIT-honestly, or
requires an *iterative* solver (active-set / interior-point / root-finding) that cannot be
made exactly deterministic in `Decimal` without float tolerances — narrowing Phase 21
rather than weakening the determinism principle.

---

## 2. Repository findings

Verbatim reconnaissance of the current tree (`src/quantforge/…`, `docs/…`), treated as
authoritative.

### 2.1 `_linalg` — exactly what exists (inspected directly)

`src/quantforge/_linalg/` is a two-file, dependency-free, exact-`Decimal` layer. Its
**entire public surface** is three functions (`__init__.py`):

- `ldl(a) -> (L, D) | None` — LDLᵀ (Cholesky-family) factorization of a symmetric matrix.
  A pivot `D[j] <= 0` (an **exact** `Decimal` zero-pivot test, no float tolerance) means
  `A` is **not positive-definite** and returns `None`.
- `ldl_solve(L, D, b) -> x` — solves `A·x = b` from the factorization (forward / diagonal
  / back substitution).
- `inverse_diagonal(L, D) -> [Decimal]` — the diagonal of `A⁻¹` (one solve per unit
  vector).

**What the layer therefore supports today:** matrix–vector solves of a **symmetric
positive-definite** system, exact **positive-definiteness / singularity detection**, and
(by repeated `ldl_solve` against unit vectors) any column of `A⁻¹`.

**What it does NOT contain:** a general matrix-multiply, a quadratic-form evaluator, a
KKT / saddle-system solver (the current PD-only pivot test rejects indefinite systems by
construction), active-set / interior-point machinery, or any constrained-optimization
routine. The docstring is explicit that these primitives were promoted verbatim from the
Phase 17 OLS solver so the regression layers share **one** verified implementation; they
are pure functions run inside a caller-supplied `localcontext`.

**Consequence for Phase 21:** the fully-invested GMV closed form needs only `ldl` +
`ldl_solve` (solve `Σ x = 1`, normalize). **No `_linalg` change is required** for the
recommended v1 (§11). The Phase 20 spec's mention of "optimization as a future consumer"
does **not** imply any solver capability was pre-built — it was not; I verified this
directly rather than assuming.

### 2.2 `FactorRiskModel` — the interface Phase 21 consumes (inspected directly)

`FactorRiskModel` (`factorrisk/result.py`, `factorrisk/model.py`) is a sealed
`ResearchRecord` exposing:

- `factors: tuple[FactorMoment, ...]` — per-factor `mean`, `volatility`,
  `annualized_volatility`, each a `StatValue` (KNOWN decimal string, or UNDEFINED). The
  **means are ex-post realized means**, not forecasts.
- `covariance: tuple[CovarianceCell, ...]` — the **upper triangle** (`i <= j`) of the
  `N x N` population covariance, each cell `value` (per-period) + `annualized`. **Every
  covariance cell is numerically KNOWN** (a zero covariance is a real number); the lower
  triangle is implied by symmetry (D-TRIANGLE).
- `correlation: tuple[CorrelationCell, ...]` — upper-triangle correlation; a cell is
  UNDEFINED `ZERO_VARIANCE` when a factor's volatility is exactly `0`.
- `factor_refs: tuple[(label, factor_portfolio_id, result_hash), ...]` — the **ordered**
  factor references (request order fixes the matrix row/column order and the
  `factor_1..factor_N` labels).
- `schedule_id`, `factor_portfolio_engine_version_id` — the single shared rebalance
  schedule and producing-engine version (commensurability, FR-3).
- `periods` (the analysed common window `M`), `periods_per_year`, `coverage` (audit),
  `dataset_version_ids` / `market_dataset_version_ids` (carried corpus pins),
  `pin_mismatch` (surfaced), `boundary_kind = "pit"` (documents the *input* side; the
  model is ex-post, FR-2), `result_hash`, and derived `factor_risk_id` /
  `research_result_id`.

**Valid optimization inputs:** the covariance matrix `Σ` (reconstructed full-symmetric
from the upper triangle) and the factor ordering/labels. The per-factor **means are
deliberately NOT used** as expected returns (§8). Correlation, annualized scalings,
coverage, and pins are not solver inputs (GMV weights are invariant to positive scaling
of `Σ`, so per-period vs annualized covariance give identical weights — the optimizer
uses the per-period covariance and folds that choice into identity, §13).

### 2.3 `FactorPortfolio` — why the optimizer stays at the factor level (agent-verified)

A `FactorPortfolio` (Phase 19) exposes a **realized ex-post per-period factor-return
series** (`per_period[*].factor_return`), leg-level equal-weight means (`long_return`,
`short_return`), leg **membership** (`company_ids`, audit-only, not folded), and an
ex-post `summary`. It exposes **no per-asset weights, no per-asset returns, no
asset-level covariance, and no forward/PIT expected return**. Asset-level optimization
would require re-deriving per-asset returns from the two pinned corpora (the record
stores no raw values) and inventing an asset covariance source — both forbidden (§7).

### 2.4 Shared architecture — the extension recipe (agent-verified)

- **Workspace lazy-engine pattern:** each engine is a cached `@property` typed `-> object`
  that imports its engine class *inside* the body (cycle-free) and constructs it with the
  whole `Workspace` (`Engine(self)`); the engine pulls the shared store and upstream
  engines off `self`. Adding `optimization_engine` is the identical three-line edit Phase
  20 made for `factor_risk_engine`.
- **`ResearchResultStore`:** `write(record)` is **write-once** — byte-identical payload
  under an existing id is an idempotent no-op; a *differing* payload under an existing id
  raises `FactorConsistencyError` (never overwrites). `read_as(id, from_dict)` is generic.
  Files live at `<root>/research/sha256-<hex>.json`. **No new store is needed or allowed.**
- **`ResearchRecord` Protocol:** `research_result_id: str` + deterministic `to_dict()`.
  A Phase 21 result satisfying this persists with zero store changes (plus a `from_dict`
  for typed read-back).

### 2.5 Invariant catalog (agent-verified)

Numbered integrity invariants **1–30** (data-model §12), plus the additive phase-local
families **SD-1..4** (Phase 16), **XS-1..4** (Phase 18), **P19-1..5** (Phase 19),
**FR-1..5** (Phase 20). Load-bearing for Phase 21:

- **Inv. 27:** every resolution query specifies exactly one mode (`PIT(as_of=T)` or
  `REVISED`); never defaulted.
- **Inv. 28:** `REVISED` (and, by the phase-local analogues SD-2/XS-2/P19-2/FR-2, any
  ex-post artifact) **must never feed a research/factor/backtest computation defined
  as-of a historical `T`**; enforced at the API/type boundary.
- **Inv. 29:** PIT is `as_of`-monotonic and past-closed.
- **Inv. 30:** both views share one immutable append-only history.
- The **"not a PIT value"** pattern (SD-2 → XS-2 → P19-2 → FR-2): each ex-post artifact is
  not a `Pit*` type, exposes no as-of accessor, and carries `boundary_kind = "pit"` only
  to document the *input* side.
- The **UNDEFINED convention:** a degenerate computation is a **recorded** first-class
  `UNDEFINED` value carrying *why*, never raised, never fabricated (`0`/`NaN`/`Inf`),
  never silently dropped.

### 2.6 Determinism / Decimal conventions

Every derived layer runs its arithmetic under an explicit `localcontext` of **precision
34, `ROUND_HALF_EVEN`**, folded into the engine version's `config_hash`; canonical
decimal strings via `str(+Decimal(...))`; identity via `sha256:`-prefixed, `\x00`-joined
components with canonical JSON (`sort_keys=True, ensure_ascii=False,
separators=(",",":")`); no wall-clock, RNG, `id()`, or iteration-order dependence. Version
is expressed by content-addressed ids, not the `pyproject` `__version__` (which is
`0.0.0`); git tags mark releases (`v0.17.0` present).

---

## 3. Capability gap

QuantForge can now **describe** the second-moment structure of a set of factors but cannot
yet **act** on it. There is no layer that turns a covariance matrix into an allocation
decision. Every prior analytics layer (15–20) *measures* (performance, diagnostics,
attribution, regression, factor construction, risk); none *optimizes*. The natural,
long-signalled next capability — named in Phase 20 §9 — is a deterministic optimizer that
consumes the sealed `Σ` and produces factor weights. The gap is precisely: **"given a
sealed factor risk model, what is the minimum-variance combination of those factors?"**

The gap is real (no such capability exists), bounded (one objective, one constraint,
closed-form), and honest (it needs only inputs the repository already seals).

---

## 4. Selected capability

**Global minimum-variance portfolio over the *N* factors of one sealed
`FactorRiskModel`, fully invested (`1ᵀw = 1`), solved in closed form.**

It meets every selection criterion from the objective:

- **Uses the `FactorRiskModel` meaningfully** — `Σ` is the whole input; the result is
  literally the minimum-variance point on the factor frontier.
- **Genuine new research capability** — the first optimizer in the project; not measured
  by any prior phase.
- **Does not duplicate Phase 12** — it produces an *allocation decision* (weights), not an
  execution simulation (§21). No fills, cash, positions, costs, or accounting.
- **No new ingestion, no database, no runtime dependency, no new store** — pure consumer
  of a sealed artifact, persisted to the existing sidecar.
- **Deterministic and exhaustively testable** — a closed form over exact `Decimal`; small
  hand-checkable matrices; byte-identical across machines.
- **Exact `Decimal` throughout** — solved with the existing `ldl`/`ldl_solve`.
- **Defensible identity** — folds the engine version, objective, constraint spec, and the
  risk model's `result_hash` (transitive pinning), plus the computed weights (§13).
- **Fits `ResearchRecord`** — a sealed `PortfolioOptimization` record, write-once (§16).

---

## 5. Alternatives considered (≥5 rejected/deferred)

Each is rejected or deferred with the specific repository reason.

1. **Mean-variance (`max μᵀw − λ/2·wᵀΣw`) — REJECTED for v1.** Requires an expected-return
   vector `μ`. The only returns the repository seals are the **ex-post realized factor
   means** in the `FactorRiskModel`; treating those as forward expected returns is exactly
   the look-ahead fabrication the objective forbids (an in-sample "optimal" that used the
   realized future). UNDEFINED/absent is preferable to an invented input. Deferred until a
   PIT-safe expected-return artifact exists (none does).

2. **Maximum-Sharpe (`max (μᵀw − r_f)/√(wᵀΣw)`) — REJECTED.** Same fatal dependency on `μ`
   as (1), plus a risk-free rate; additionally the tangency solution is undefined without a
   forward `μ`. No PIT-safe `μ` source → rejected.

3. **Long-only / box-constrained QP (`w_i >= 0`, `l_i <= w_i <= u_i`) — DEFERRED.**
   Inequality constraints turn the closed form into an **iterative** active-set /
   interior-point QP. Exact `Decimal` iteration has no guaranteed finite termination
   without float tolerances or a convergence epsilon — which would violate the "no float /
   exact determinism" principle. Narrowing Phase 21 to the equality-only closed form is
   preferred over weakening determinism. (The GMV weights may be negative — an honest
   long/short factor combination — which is acceptable and fully defined.)

4. **Risk-parity / equal-risk-contribution — DEFERRED.** The ERC weights solve a
   *nonlinear* fixed-point system with no closed form; the standard solution is iterative
   root-finding — same non-termination / float-tolerance problem as (3).

5. **Tracking-error minimization (`min (w−b)ᵀΣ(w−b)`) — DEFERRED.** Needs a benchmark
   weight vector `b` in the same factor space. No sealed benchmark-in-factor-space artifact
   exists; inventing `b` is an unsupported input. (It is also just an affine shift of the
   equality-constrained problem, so it can be revisited once a benchmark artifact exists.)

6. **Asset-level portfolio construction — REJECTED.** No PIT-safe asset-return or
   asset-covariance artifact exists (§2.3); would require a second covariance source
   (forbidden — Phase 20 is the single source) and new ingestion. Silently inventing an
   asset-level system is explicitly disallowed by the objective.

7. **Richer Phase 12 portfolio construction / execution-aware optimization — REJECTED.**
   Execution (fills, cash, costs, accounting) is Phase 12's domain. An optimizer is a
   *pre-execution decision*; folding execution in would collide with Phase 12 (§21).

8. **Walk-forward / rolling optimization — DEFERRED.** Needs rolling/windowed covariance
   (explicitly out of Phase 20 scope) and would produce a *time series of decisions* — a
   large new PIT-decision surface. Out of scope for a first optimizer.

9. **Robust / Bayesian / Black-Litterman optimization — DEFERRED.** Needs priors, views,
   and an expected-return model; far beyond minimal; numerically heavy. No inputs exist.

10. **Transaction-cost-aware optimization — DEFERRED.** Needs a cost model and current
    holdings; that is execution-adjacent (Phase 12), and no holdings artifact exists.

11. **Generic optimizer / callback framework — REJECTED.** A pluggable objective/constraint
    callback is a Python escape hatch that destroys deterministic identity and is explicitly
    forbidden. Phase 21 pins **one** objective in a closed vocabulary that hashes distinctly.

12. **Reporting / UI for optimizations — REJECTED (out of scope).** Presentation is never
    part of a value layer here.

---

## 6. Architectural fit

Phase 21 is the **pure-consumer sibling of Phase 20**, one layer higher — exactly as Phase
20 consumes Phase 19 and Phase 15/17 consume Phase 12. It follows the identical extension
recipe: a versioned immutable request → a fail-closed engine reached from `Workspace` via
a lazy cycle-free `@property` → a distinct sealed result type → content-addressed identity
with fresh domain tags → data conditions recorded as first-class `UNDEFINED`, defects
raised → compute-on-demand persisted write-once to the shared sidecar.

```
                 PortfolioOptimizationSpecification   (declarative request, content-addressed)
                          |
                          v
   Workspace.optimization_engine  --->  PortfolioOptimizationEngine.optimize(spec)
                          |                 |
                          |   resolve factor_risk_id from the shared sidecar          — fail closed
                          |     store.read_as(id, FactorRiskModel.from_dict)
                          |     verify resolved.research_result_id == requested id (PO-1)
                          |     (no content->hash recompute; risk model result_hash is FOLDED, PO-1)
                          |
                          |   reconstruct full symmetric Σ from the upper-triangle covariance
                          |     (per-period cells; every cell KNOWN by construction)
                          |
                          |   solve under the pinned Decimal context (prec 34, HALF_EVEN):
                          |     ldl(Σ)  ->  None  => SINGULAR_COVARIANCE (first-class UNDEFINED)  (PO-4)
                          |     else x = ldl_solve(L, D, ones);  s = Σ x_i  (= 1ᵀΣ⁻¹1 > 0)
                          |     w_i = x_i / s;  variance = wᵀΣw;  volatility = √variance
                          v                 v
        PortfolioOptimization (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
        store.read_as(id, PortfolioOptimization.from_dict)  (typed, byte-identical round-trip)
```

**Edits to existing source** (all additive; none altering any existing identity):

1. `workspace.py` — one lazy `optimization_engine` `@property` (+ its
   `self._optimization_engine: object | None = None` cache line), mirroring
   `factor_risk_engine`.
2. `src/quantforge/__init__.py` — top-level re-exports of
   `PortfolioOptimizationSpecification` and `PortfolioOptimization` (spec + result only;
   the engine is reached via `Workspace`).
3. `tests/test_smoke.py` — one additive public-API export assertion.

**No edit** to `_linalg`, `backtest/*`, `analytics/*`, `attribution/*`, `crosssection/*`,
`diagnostics/*`, `factorportfolio/*`, `factorrisk/*`, `factors/store.py`, `panel/*`,
`market/*`, `universe/*`, or any prior identity/version module.

---

## 7. Decision-variable analysis

> *"What are the decision variables?"*

**Weights `w ∈ ℝᴺ` across the *N* factors of the referenced `FactorRiskModel`** — i.e.
weights across `FactorPortfolio` combinations (option 1 of the objective's list). The
*i*-th weight is the allocation to the factor whose covariance-matrix row/column is `i`
(`factor_1..factor_N`, the risk model's semantic order). The result is a **meta-portfolio**:
a linear combination of the sealed long/short factor portfolios.

**Why not asset weights (option 3).** The `FactorRiskModel` provides an `N x N` *factor*
covariance. There is **no asset-level return matrix or asset covariance** anywhere in the
repository (§2.3): `FactorPortfolio` exposes only realized factor-return series and
unweighted leg membership. Optimizing asset weights would require inventing an asset
covariance source, violating "do not create a second covariance source" and "do not
silently invent an asset-level portfolio construction system." The factor covariance is
the natural — and only — `Σ` the architecture supplies.

**Why not factor exposures (option 2) or signal weights.** Exposures/signal weights would
require a factor-model regression mapping assets → exposures with a PIT-safe covariance of
*residuals + factors*, which does not exist as a sealed artifact. Factor weights over the
sealed factor covariance is the honest, grounded choice.

The weight vector is dimensioned by the risk model's *N* (2..16, inherited from Phase 20's
`N_MAX`), ordered by the risk model's factor order, and each weight is an exact `Decimal`
string in the sealed result.

---

## 8. Objective-function analysis

The objective must be supportable by **sealed data that exists**. Enumerated:

| Objective | Needs | Available? | Verdict |
|---|---|---|---|
| **Minimum variance** `min wᵀΣw` | `Σ` only | **Yes** (`FactorRiskModel.covariance`) | **Selected** |
| Mean-variance `max μᵀw − λ/2 wᵀΣw` | `Σ`, forward `μ`, `λ` | `μ` **not** PIT-safe | Rejected (§5.1) |
| Maximum-Sharpe `max (μᵀw−r_f)/√(wᵀΣw)` | `Σ`, forward `μ`, `r_f` | `μ` **not** PIT-safe | Rejected (§5.2) |
| Tracking-error `min (w−b)ᵀΣ(w−b)` | `Σ`, benchmark `b` | no `b` artifact | Deferred (§5.5) |

**Minimum variance is the only objective every input of which the repository already
seals honestly.** It needs `Σ` and nothing else — no expected return, no risk-free rate,
no benchmark, no risk-aversion parameter. The ex-post factor **means** in the risk model
are available but are **deliberately unused**: they are realized in-sample means, and
using them as a forward `μ` is precisely the look-ahead the project forbids. Per the
objective's instruction, **UNDEFINED/absent is preferable to an invented `μ`** — so the
first optimizer optimizes the one thing it can compute honestly, and defers every
return-dependent objective until a PIT-safe expected-return artifact exists.

The achieved objective value `wᵀΣw` (portfolio variance) and its square root (portfolio
volatility) are sealed alongside the weights as first-class results.

---

## 9. Constraint vocabulary

The **smallest defensible** vocabulary is a **single equality constraint**:

- **Fully invested: `1ᵀw = 1`.** Essential (without it the minimum-variance problem is
  unbounded below only if `Σ` is not PD; with PD `Σ` the unconstrained minimum is `w=0`,
  which is meaningless — the budget constraint is what makes GMV a portfolio).
  Deterministic, exactly representable (`Σ w_i = 1`), trivially testable, and — crucially —
  admits the **closed-form** solution `w* = Σ⁻¹1/(1ᵀΣ⁻¹1)`.

**Deliberately excluded from v1** (each would break the closed form or lack an input):

- **Long-only `w_i >= 0` / box `l_i <= w_i <= u_i`** — inequality constraints ⇒ iterative
  QP (§5.3). Deferred.
- **Gross-exposure / leverage caps `Σ|w_i| <= L`** — non-smooth (absolute value) ⇒
  iterative. Deferred.
- **Maximum concentration `w_i <= c`** — inequality ⇒ iterative. Deferred.
- **Factor neutrality / target exposure `Aw = b`** — these are *additional equality*
  constraints, which **do** preserve a closed form (§11.2), but they broaden the request
  vocabulary and need a small `_linalg` addition; recommended as an **approval-gated**
  extension, not v1 (§24, Q1).

v1 is therefore a **fixed, zero-parameter constraint** (fully invested), which keeps the
identity trivial and the solver a single PD solve. No generic constraint engine is
introduced.

---

## 10. `FactorRiskModel` interface (what Phase 21 reads, and what it must not)

Phase 21 consumes, from the resolved `FactorRiskModel`:

- **`covariance` (upper triangle, per-period cells)** — reconstructed into the full
  symmetric `Σ`. This is the single covariance source; Phase 21 **never recomputes**
  covariance (satisfies "do not create a second covariance source").
- **`factor_refs` order + labels** — fixes `w`'s dimension `N`, ordering, and the
  `factor_1..factor_N` weight labels; carried into the result for provenance.
- **`result_hash` and `research_result_id` (`factor_risk_id`)** — folded into the
  optimization identity for transitive pinning (PO-1).
- **`schedule_id`, `factor_portfolio_engine_version_id`, `periods`, `periods_per_year`,
  `dataset_version_ids`, `market_dataset_version_ids`, `pin_mismatch`** — carried through
  (audit / surfaced provenance; `pin_mismatch` re-surfaced, never raised).

Phase 21 **does not** use: the per-factor **means** (would be an invented `μ`), the
**correlation** matrix (redundant with `Σ` for GMV), the **annualized** covariance (GMV
weights are scale-invariant, so per-period is chosen and folded — §13), or the coverage
audit block.

A covariance cell is always numerically KNOWN in a sealed `FactorRiskModel` (only
*correlation* can be UNDEFINED); the engine still fail-closes if a covariance cell decodes
as non-finite or UNDEFINED (a corrupt sealed record).

---

## 11. Linear-algebra requirements

### 11.1 v1 (fully invested) — **zero `_linalg` additions**

The recommended v1 uses only the existing primitives:

1. Reconstruct full symmetric `Σ` (list-of-lists of `Decimal`) from the upper triangle.
2. `f = ldl(Σ)`. If `f is None` → `Σ` is **not positive-definite** → first-class
   `SINGULAR_COVARIANCE` UNDEFINED result (§15). No float tolerance; the exact zero-pivot
   test already implements this.
3. `x = ldl_solve(L, D, ones)` where `ones = [1,…,1]` (this is `Σ⁻¹1`).
4. `s = Σ x_i` (a plain sum; equals `1ᵀΣ⁻¹1`, strictly positive for PD `Σ`).
5. `w_i = x_i / s`; **achieved variance** `= wᵀΣw` computed as an inline quadratic form
   over the reconstructed `Σ` (a double loop of `Decimal` multiply-adds — no helper
   needed, and it self-verifies the algebraic identity `wᵀΣw = 1/s`); **volatility**
   `= variance.sqrt(context)`.

All steps are exact `Decimal` under the pinned `localcontext`, byte-identical across
machines, and terminate in fixed time (`O(N³)` factorization, `N <= 16`). **No matrix
inverse (only a solve), no KKT system, no active set, no iteration.**

### 11.2 If linear equality constraints are later approved (§24, Q1)

`min wᵀΣw` s.t. `Aw = b` (with `A` a `k x N` full-row-rank constraint matrix) has the
closed form `w* = Σ⁻¹Aᵀ(AΣ⁻¹Aᵀ)⁻¹b`, computed with **only PD solves**: solve `Σ X = Aᵀ`
(k `ldl_solve`s against `Σ`), form the small `k x k` Gram `M = A X` (PD when `A` is full
row rank and `Σ` is PD), solve `M y = b` via a second `ldl`, then `w = X y`. This needs
**one** tiny additive `_linalg` helper — an exact `Decimal` matrix-multiply (or a
`quadratic_form`/`matmul`) to form `A X` and `A Xᵀ` — and **no** indefinite/KKT solver
(the current PD-only `ldl` suffices, applied twice). It would be added additively to
`_linalg` with its own tests, changing no existing primitive. **Recommended to defer**
(keep v1 to fully-invested); flagged as approval-gated.

**No `scipy` / `numpy` / `cvxpy` / any runtime dependency** is proposed under any option.

---

## 12. PIT / ex-post boundary (load-bearing)

**The optimization is ex-post only.** Its sole input, `Σ`, is the ex-post second-moment
structure of realized factor returns (FR-2). A function of an ex-post input is itself
ex-post: **the GMV weights are an ex-post research statistic, not a forward-usable PIT
decision.** Concretely:

- `PortfolioOptimization` is **not** a `Pit*` type and exposes **no** as-of accessor — the
  exact analogue of invariant 28 / SD-2 / XS-2 / P19-2 / FR-2. It is inadmissible anywhere
  a PIT signal/value is required (enforced by type, not convention).
- `boundary_kind = "pit"` documents only that the *underlying factor portfolios were PIT
  walks* (their signal side was PIT-eligible) — it never claims the weights are a PIT
  value. The engine sets it unconditionally (a `FactorRiskModel` is ex-post by
  construction; there is no revised variant), so **no new PIT resolution is introduced**.
- Phase 21 consumes **no** raw corpus, resolves **no** data at any `T`, and re-derives
  nothing from source. It therefore cannot introduce a look-ahead surface: it only reads a
  sealed artifact and does deterministic algebra.

**It does not produce a PIT-eligible decision artifact.** A genuinely forward-usable
optimizer would require a PIT-safe forward covariance *and* a PIT-safe expected-return
input available at each decision date `T`; neither exists. Phase 21 therefore explicitly
produces an **ex-post research result** and reserves any PIT-eligible "portfolio decision
as-of `T`" for a future, explicitly-labelled phase that first establishes those PIT
inputs. Blurring the two is exactly what invariant 28 forbids.

New phase-local invariants **PO-1..PO-5** (§17) codify this; they are additive and weaken
no existing invariant.

---

## 13. Identity design

A single content-addressed `optimization_id` (aliased by `research_result_id`), following
the §10/§11 discipline verbatim (`sha256:`, `\x00`-joined, canonical JSON, request order
preserved).

```
optimization_result_hash = sha256( canonical JSON over the ordered computed-output cells:
                                    the status; then the per-factor weight cells in factor
                                    order (label, weight StatValue); then the achieved
                                    portfolio variance and volatility StatValues )

optimization_id = sha256( NUL-joined, in order:
    domain "optimization/1",
    optimization_engine_version_id,      # folds code + solve-method + decimal context
    name,
    spec_version,
    objective,                           # "minimum_variance"  (closed vocabulary)
    constraint_id,                       # canonical JSON of the constraint spec (v1: {"fully_invested": true})
    covariance_basis,                    # "per_period"  (which covariance the solve used)
    factor_risk_id,                      # the referenced risk model's id (request identity)
    factor_risk_result_hash,             # the referenced risk model's answer (TRANSITIVE PIN, PO-1)
    optimization_result_hash )           # the computed weights + achieved variance/vol
```

**Folds (any change changes the id):** the engine-logic + solve-method + decimal-context
version; the declared request (name, spec version, objective, constraint spec); the
covariance basis; the **referenced content** (`factor_risk_result_hash`, so the id is
**transitively** sensitive to any change in the risk model, its factors, or its corpus —
PO-1); and the computed answer (`optimization_result_hash`).

**Deliberately NOT folded** (would over-sensitize or is audit-only): the record
schema/format version (`OPTIMIZATION_RESULT_FORMAT_VERSION`, a container concern); the
carried corpus pins (surfaced via `pin_mismatch`, inherited from the risk model, not
folded — the D-PIN convention); `periods_per_year` (GMV weights are invariant to positive
scaling of `Σ`, so annualization cannot change the answer — folding it would create
spurious distinct ids for identical results); factor labels beyond their order (the order
is already fixed by the risk model reference); any presentation, wall-clock, RNG, `id()`,
or iteration order.

**Identity sensitivity check:** every value that changes the mathematical answer changes
the id — the objective, the constraint spec, the covariance content (via
`factor_risk_result_hash`), and the weights (via `optimization_result_hash`). The engine
version captures the decimal context and solve method. `covariance_basis` is folded even
though v1 fixes it to `per_period`, so a future annualized-basis option can never collide.
Audit-only metadata (pins, coverage, format version) is not folded, matching Phase 20.

`optimization_engine_version_id = sha256(code_version "optimization-engine/1", config_hash)`
where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00solve=optimization-solve/1")`
— identical construction to `FactorRiskEngineVersion`, so the pinned decimal context and
the solve-method version are load-bearing (any change → new engine id → new
`optimization_id`).

---

## 14. Result / data model

All types `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
float, no wall-clock, no RNG.

### 14.1 `PortfolioOptimizationSpecification` (declarative request)

```
PortfolioOptimizationSpecification(
    name: str,                         # non-empty
    factor_risk_id: str,               # the sealed FactorRiskModel to optimize over (non-empty)
    objective: str = "minimum_variance",   # closed vocabulary (v1: exactly this)
    fully_invested: bool = True,       # v1: must be True (the one constraint); reserved for extension
    spec_version: str = "optimization/1",
)
```

Construction-time validation (fail closed, `PortfolioOptimizationConfigurationError`): an
empty `name` / `spec_version` / `factor_risk_id`; an `objective` outside the closed
vocabulary; `fully_invested` not `True` (v1). It reads no store and no wall clock — it
cannot know whether the referenced id exists or whether `Σ` is PD (the engine's
fail-closed steps). `to_dict()` emits `{spec_version, name, factor_risk_id, objective,
fully_invested}`, embedded in the sealed record.

### 14.2 Result vocabulary (`model.py`)

- `OptimizationStatus`: `OPTIMAL`, `UNDEFINED`.
- `OptimizationUndefinedReason` (closed, v1): `SINGULAR_COVARIANCE` — `Σ` is not
  positive-definite (rank-deficient / collinear factors / a zero-variance factor / too few
  common periods), so `Σ⁻¹1` does not exist and the GMV is genuinely undefined. Recorded,
  never a divide-by-zero or a repaired answer.
- `StatValue` — the UNDEFINED-preserving cell (KNOWN decimal string **or** UNDEFINED +
  reason), mirroring Phase 17/19/20 exactly.
- `WeightCell(label, value: StatValue)` — one factor's weight; `label` the name-free
  `factor_label(i)` matching the risk model's order.

### 14.3 `PortfolioOptimization` (implements `ResearchRecord`)

```
PortfolioOptimization(
    optimization_engine_version_id: str,
    optimization_spec: dict[str, object],       # the full spec.to_dict()
    objective: str,                             # "minimum_variance"
    constraint_spec: dict[str, object],         # v1: {"fully_invested": true}
    covariance_basis: str,                       # "per_period"
    risk_model_ref: tuple[str, str],            # (factor_risk_id, result_hash) — transitive pin (PO-1)
    boundary_kind: str,                          # "pit" (documents the INPUT side; PO-2 — not a PIT value)
    schedule_id: str,                            # carried from the risk model
    factor_portfolio_engine_version_id: str,     # carried from the risk model
    n_factors: int,                              # N (= the risk model's factor count)
    factor_labels: tuple[str, ...],             # factor_1..factor_N (order = risk model order)
    status: OptimizationStatus,                  # OPTIMAL | UNDEFINED
    weights: tuple[WeightCell, ...],            # per-factor weights (UNDEFINED cells iff status UNDEFINED)
    portfolio_variance: StatValue,               # achieved wᵀΣw (UNDEFINED iff singular)
    portfolio_volatility: StatValue,             # √variance
    dataset_version_ids: tuple[str, ...],       # carried, sorted/deduped
    market_dataset_version_ids: tuple[str, ...], # carried, sorted/deduped
    formula_version: str,                        # "optimization-solve/1"
    result_hash: str,                            # over the ordered output cells
)

# derived, never stored as state:
optimization_id     property -> sha256 folding engine version + spec identity + objective
                                + constraint spec + covariance basis + risk model id + risk
                                model result_hash + optimization_result_hash
research_result_id  property -> alias of optimization_id
pin_mismatch        property -> True iff either carried-pin tuple has length > 1 (surfaced)
```

- `.seal(...)` computes `result_hash` from the ordered output cells (status → weight cells
  in factor order → variance → volatility), so identity is a pure function of request +
  referenced content + answer. Carried pins and labels are **not** folded (audit/order).
- `to_dict` / `from_dict` are the fail-closed, byte-identical inverse pair;
  `optimization_id` / `research_result_id` re-derived by properties (never read from
  state); a malformed cell raises `ValueError`.
- **Deliberately does NOT hold:** any copy of `Σ` (only the `risk_model_ref` pointer); any
  float; any `Pit*` type or as-of accessor (PO-2); any expected return; any execution /
  holdings / cash / cost state (PO-5).

---

## 15. Failure / UNDEFINED semantics

Follows the project split exactly — **defects raise, degenerate data conditions are
recorded.**

**Raised** (`PortfolioOptimizationConfigurationError` / `…ConsistencyError`):

- Malformed spec: empty `name` / `spec_version` / `factor_risk_id`; `objective` outside the
  closed vocabulary; `fully_invested` not `True` (v1); a non-spec argument to `optimize`.
  *(configuration)*
- `factor_risk_id` absent from the sidecar, or a resolved record whose
  `research_result_id` disagrees with the request, or that is not a `FactorRiskModel`.
  *(consistency, PO-1)*
- A covariance cell that decodes as non-finite or UNDEFINED (a corrupt sealed risk model —
  covariance cells are KNOWN by construction). *(consistency)*
- A risk model with fewer than 2 factors (cannot occur for a valid `FactorRiskModel`, but
  fail-closed regardless). *(consistency)*

**Recorded as first-class `UNDEFINED` (never raised, never fabricated, never repaired):**

- **Singular / non-positive-definite `Σ`** (`ldl` returns `None`): `status = UNDEFINED`,
  reason `SINGULAR_COVARIANCE`; every weight cell UNDEFINED; `portfolio_variance` /
  `portfolio_volatility` UNDEFINED. This is the honest analogue of `SINGULAR_DESIGN` in
  `_linalg/decimal_ols.py` — no divide-by-zero, no pseudo-inverse, no dropped factor, no
  ridge regularization. The problem is genuinely undefined for that covariance and is
  recorded as such. (For PD `Σ`, `1ᵀΣ⁻¹1 > 0` always, so `OPTIMAL` never divides by zero.)

**Surfaced, never raised (inherited D-PIN convention):** more than one distinct
fundamentals or market corpus pin carried from the risk model → `pin_mismatch = True`.

**Never** silently repaired: an infeasible/degenerate problem is recorded UNDEFINED, never
made feasible by dropping a factor, relaxing the budget, or perturbing `Σ`.

---

## 16. Persistence model

Identical to Phase 20: **no new store, no database, no new format.** The
`PortfolioOptimization` satisfies `ResearchRecord` (`research_result_id` + deterministic
`to_dict`), so `ResearchResultStore.write(model)` persists it write-once to
`<root>/research/sha256-<hex>.json` in the existing sidecar. Re-optimizing an identical
request is a byte-identical no-op; a differing payload under an existing id fails closed
via the store's guard. Typed read-back via `store.read_as(id,
PortfolioOptimization.from_dict)`. The engine reaches the shared store off the
`Workspace`, exactly as `FactorRiskEngine` does.

---

## 17. Phase-local invariants (proposed PO-1..PO-5)

Additive; documented here and (on approval) as a small `data-model.md §12` block mirroring
the FR-1..5 block. They **weaken no invariant 1–30**.

- **PO-1. Reference verification and transitive pinning.** The engine resolves the
  referenced `factor_risk_id` from the shared sidecar and re-verifies the resolved
  record's `research_result_id` equals the requested id; a missing id or key/content
  disagreement fails closed. The risk model's sealed `result_hash` is folded into
  `optimization_id`, so identity is transitively sensitive to any change in the risk model
  (and, through it, its factors and corpus). *(The FR-1 discipline, one layer up.)*
- **PO-2. An optimization is not a PIT value.** A `PortfolioOptimization` is a function of
  the ex-post `FactorRiskModel` `Σ` and is itself ex-post; not a `Pit*` type, no as-of
  accessor, inadmissible where a PIT signal/value is required. `boundary_kind = "pit"`
  documents that the underlying factor portfolios were PIT walks, not that the weights are
  a PIT value. *(Direct analogue of invariant 28 / FR-2.)*
- **PO-3. Single covariance source; no fabricated inputs.** The optimizer consumes the
  sealed `FactorRiskModel` covariance as-is and never recomputes or shrinks it, and never
  fabricates an expected-return, risk-free, or benchmark input; the v1 objective
  (minimum-variance) depends on `Σ` only. *(Enforces "do not create a second covariance
  source" and "UNDEFINED preferable to invented input.")*
- **PO-4. Fail-closed degeneracy, never repaired.** A non-positive-definite `Σ` (exact
  `ldl` zero-pivot test) is a recorded `UNDEFINED` `SINGULAR_COVARIANCE` result, never a
  divide-by-zero, pseudo-inverse, dropped factor, or regularized `Σ`. An infeasible/
  degenerate problem is recorded, never silently made feasible. *(The XS-4/P19-4/FR-4
  fail-closed posture for an optimizer.)*
- **PO-5. An optimization is not a `BacktestResult` and performs no execution.** A
  distinct record type; it does not enter Phase 12's identity, cannot be passed where a
  `BacktestResult` is required (enforced by type), and simulates no fills, cash, positions,
  or costs — it is an allocation decision, not an execution. *(The FR-5 discipline; the
  Phase 12 boundary of §21.)*

---

## 18. Full contradiction / invariant matrix

Classification: **COMPOSES** (works with, no tension) · **CONSTRAINS** (imposes a design
rule Phase 21 must obey) · **TENSION** (needs care, resolved below) · **CONTRADICTION**
(would violate — none survive).

| Invariant | Class | Analysis |
|---|---|---|
| 1–5 (raw immutability/provenance) | COMPOSES | Phase 21 reads no raw bytes/facts; touches none of this. |
| 6–17 (PIT/availability) | COMPOSES | Phase 21 resolves no data at any `T`; it reads a sealed ex-post artifact. No PIT query is issued, so no eligibility rule is engaged. |
| 18 (deterministic ids from inputs+version) | COMPOSES | The closed-form solve under the pinned context is byte-identical for identical inputs+version. |
| 19 (`DatasetVersion` immutable/hashed) | COMPOSES | Corpus pins are carried from the risk model, never recomputed. |
| 20 (versions immutable) | CONSTRAINS | The new `optimization-engine/1` / `optimization-solve/1` versions are immutable once released; any solve-method change bumps them. |
| 21 (no wall-clock/RNG/order dependence) | CONSTRAINS | Enforced: `Decimal` only, canonical ordering, no RNG/time. |
| 22, 22a, 23 (amendments/supersession) | COMPOSES | Not engaged; Phase 21 reads no facts. |
| 24 (`company_id` = registrant) | COMPOSES | No company-level data touched. |
| 25 (nil facts) | COMPOSES | Not engaged. |
| 26 (loss-preserving normalization) | COMPOSES | Not engaged. |
| **27 (mode explicit)** | COMPOSES | Phase 21 issues no resolution query, so no mode is required; it consumes a sealed record. |
| **28 (`REVISED`/ex-post never feeds as-of-`T` computation)** | CONSTRAINS | **Load-bearing.** Phase 21's output is ex-post and is barred (by PO-2, by type: not a `Pit*`) from any as-of-`T` research/backtest input. Resolved by making `PortfolioOptimization` a non-PIT type with no as-of accessor. |
| 29 (PIT monotonic/past-closed) | COMPOSES | No PIT series produced. |
| 30 (one immutable history) | COMPOSES | Reads only sealed artifacts; writes only a new content-addressed record; overwrites nothing. |
| SD-1..4 (Phase 16) | COMPOSES | Independent layer; Phase 21 references no `SignalDiagnostics`. The SD-2 "not a PIT value" pattern is the precedent PO-2 follows. |
| XS-1..4 (Phase 18) | COMPOSES | Independent; the XS-4 UNDEFINED-recording posture is the precedent PO-4 follows. |
| P19-1..5 (Phase 19) | COMPOSES / CONSTRAINS | Phase 21 depends on `FactorPortfolio` only transitively (through the risk model). P19-5 (not a `BacktestResult`) is the precedent for PO-5. CONSTRAINS: Phase 21 must not reach into `FactorPortfolio` for asset data (none exists). |
| FR-1 (reference verification + transitive pin) | COMPOSES | PO-1 is FR-1 one layer up; folds the risk model `result_hash`. |
| FR-2 (risk model not a PIT value) | COMPOSES | PO-2 inherits and extends: a function of an ex-post input is ex-post. |
| FR-3 (commensurability; pins surfaced) | COMPOSES | The single referenced risk model already guarantees one `schedule_id` / one producing engine internally; Phase 21 re-surfaces `pin_mismatch`, raises nothing new. |
| FR-4 (complete-case; degeneracy UNDEFINED) | COMPOSES | PO-4 mirrors it for the optimizer (non-PD `Σ` → UNDEFINED). |
| FR-5 (risk model not a `BacktestResult`) | COMPOSES | PO-5 mirrors it for the optimization. |

**Potential tensions, resolved:**

- **T1 — "optimizer produces a portfolio decision" vs invariant 28.** A portfolio *is*
  something you'd act on at a date `T`, which sounds PIT-eligible. Resolved by PO-2: the
  input `Σ` is ex-post, so the weights are an ex-post *research* statistic (the
  minimum-variance point of the realized factor covariance), explicitly **not** a PIT
  decision, typed as non-PIT. A future PIT-eligible optimizer is a separate phase.
- **T2 — GMV weights can be negative** (long/short across factors) vs an intuition that a
  "portfolio" is long-only. No invariant requires non-negativity; long-only is an
  inequality-constrained variant deferred to a future phase (§5.3). Negative weights are
  honest and fully defined for the fully-invested GMV.
- **T3 — reusing `_linalg` (promoted for OLS) for optimization.** No tension: the
  primitives are pure symmetric-PD solvers with an exact singularity test — exactly what
  GMV needs. v1 adds nothing to `_linalg`, so no shared-helper drift risk.

**No contradiction survives analysis.** Every interaction is COMPOSES or a CONSTRAINS that
the design already obeys; the two would-be tensions are resolved by the ex-post typing
(PO-2) and by deferring inequality constraints.

---

## 19. Proposed package / files

New package `src/quantforge/optimization/` (mirrors `factorrisk/`):

```
src/quantforge/optimization/
    __init__.py     # exports: spec, result, cells, errors, version, identity helpers
    errors.py       # PortfolioOptimizationError -> ...ConfigurationError, ...ConsistencyError
    version.py      # PortfolioOptimizationEngineVersion; OPTIMIZATION_{ENGINE,SOLVE,SPEC}_VERSION; default_decimal_context()
    identity.py     # optimization_result_hash, optimization_id; domain tag "optimization/1"
    model.py        # OptimizationStatus, OptimizationUndefinedReason, StatValue, WeightCell, factor_label
    spec.py         # PortfolioOptimizationSpecification + construction-time validation
    solve.py        # PURE closed-form GMV solver over decimal-string Σ (uses _linalg ldl/ldl_solve); returns a MinVarianceSolution
    result.py       # OPTIMIZATION_RESULT_FORMAT_VERSION, BOUNDARY_PIT, PortfolioOptimization (ResearchRecord)
    engine.py       # PortfolioOptimizationEngine (Workspace-constructed): resolve+verify risk model -> reconstruct Σ -> solve -> seal -> write-once
```

(`solve.py` is the analogue of `factorrisk/stats.py` — the pure compute layer, free of the
record/store vocabulary; it takes decimal-string `Σ` + context and returns KNOWN/UNDEFINED
weight cells.)

Tests: `tests/optimization/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_solve.py`, `test_identity.py`, `test_result.py`, `test_engine.py`).

Additive edits to existing files (no identity change): `workspace.py` (one lazy property +
cache line), `src/quantforge/__init__.py` (two re-exports), `tests/test_smoke.py` (one
assertion).

**`_linalg`:** **no change** for v1. (Only if equality constraints are approved would a
single additive matrix-multiply helper + its tests be added — §11.2, §24 Q1.)

---

## 20. Testing strategy

Offline over the existing fictional-CIK corpus (reuse the Phase 20 factor-risk builders,
which reuse Phase 19/18), no network, no real data.

- **SPEC** — the minimal request; the order-preserving canonical payload; every
  fail-closed path (empty name / `factor_risk_id` / `spec_version`, objective outside the
  vocabulary, `fully_invested` not `True`, non-spec argument).
- **SOLVE (exact `Decimal`, hand-checked)** — GMV over a hand-built `2 x 2` `Σ` with a
  known closed-form answer (e.g. `Σ = [[4,1],[1,2]]` → `w = Σ⁻¹1/(1ᵀΣ⁻¹1)`, verified by
  hand and byte-checked); the achieved variance equals `1/(1ᵀΣ⁻¹1)` (self-consistency of
  `wᵀΣw`); weights sum to exactly `1`; a diagonal `Σ` → weights `∝ 1/σ²_i`; the
  scale-invariance check (`Σ` and `k·Σ` give identical weights) justifying `covariance_basis
  = per_period`; the **singular** cases (`Σ` with a zero-variance factor; two identical
  factors; a rank-deficient `Σ`) → `SINGULAR_COVARIANCE` UNDEFINED, no exception, no
  divide-by-zero; a ragged/asymmetric input → fail closed.
- **IDENTITY** — `optimization_id` folding + sensitivity to each input (engine version,
  name, spec version, objective, constraint spec, covariance basis, `factor_risk_id`, risk
  model `result_hash`, `optimization_result_hash`); `optimization_result_hash`
  per-cell/order sensitivity + key-order independence; the engine-version's dependence on
  the pinned precision + solve method.
- **RESULT** — byte-identical `to_dict`/`from_dict`; derived-id survival;
  `research_result_id` alias; `boundary_kind = "pit"`; `pin_mismatch` flagging; UNDEFINED
  weight-cell round-trip; tampered-id ignored; malformed-cell rejection.
- **ENGINE (end-to-end)** — over the builders: resolve a sealed `FactorRiskModel`, solve,
  seal, persist, byte-identical round-trip; re-optimization idempotent no-op; two
  independent corpora agree; **PO-1** missing/drifted reference fails closed; **PO-2** the
  ex-post boundary (no `pit`/`as_of` accessor, not a `BacktestResult`); **PO-4** a
  singular risk model → recorded UNDEFINED; determinism double-build byte-equality
  (including under `-p no:randomly`).

---

## 21. Relationship to Phase 12 (critical)

Phase 21 must not become a second backtester. The boundary is bright:

| Phase 12 (backtesting) | Phase 21 (optimization) |
|---|---|
| Execution *simulation* | A mathematical *allocation decision* |
| Fills, cash, positions, costs | None — no execution state |
| Rebalance execution over time | A single static weight vector |
| Portfolio accounting / ledger | A sealed weight/variance result |
| Consumes a strategy + schedule + corpora | Consumes one sealed ex-post covariance |
| Produces a `BacktestResult` | Produces a `PortfolioOptimization` (distinct type, PO-5) |

Phase 21 produces **target factor weights** (and the achieved variance/volatility) as a
**standalone ex-post optimization result**. It does **not** simulate execution, does not
chain over dates, and is not intended (in v1) to be *consumed* by another phase — a future
phase that wanted to backtest an optimized allocation would be a separate, explicitly-
labelled capability. There is no execution logic anywhere in Phase 21.

---

## 22. Version proposal

**`v0.18.0`** (Phase 20 = `v0.17.0`, confirmed by git tag). The package `__version__`
string stays `0.0.0` (versioning is by content-addressed ids, not semver). The git tag is
applied only after all gates are green and only on explicit approval; **no tag/commit/
release is created by this proposal.**

---

## 23. Open questions

1. **Additional linear equality constraints (factor-neutrality / target exposure `Aw =
   b`)?** Closed-form-compatible (§11.2) but needs one additive `_linalg` matrix-multiply
   helper and a richer constraint vocabulary. Recommendation: **defer** (v1 fully-invested
   only). *(Approval-gated — §24 Q1.)*
2. **Should the achieved `portfolio_variance` use the per-period or annualized `Σ`?**
   Weights are identical either way (scale-invariant); the *variance value* differs by
   `periods_per_year`. Recommendation: seal the **per-period** variance (matching
   `covariance_basis = per_period`) and let a reader annualize; do not seal both.
3. **Should `SINGULAR_COVARIANCE` distinguish sub-reasons** (zero-variance factor vs
   collinear pair vs `M < N`)? Recommendation: **no** — one reason (the `ldl` non-PD test
   is a single exact condition); a reader can inspect the referenced risk model. Extending
   the reason set later hashes distinctly.
4. **Any per-factor weight bounds surfaced as diagnostics** (e.g. flag `|w_i| > k`)?
   Recommendation: **no** — no thresholds, no presentation in a value layer.

## 24. Approval-gated decisions

- **Q1 — equality-constraint extension.** Include general `Aw = b` (factor-neutral /
  target-exposure) in v1 (adds one `_linalg` matmul helper + vocabulary), or ship
  fully-invested GMV only? **Recommend: fully-invested only.**
- **Q2 — package/type names.** `optimization` / `PortfolioOptimizationSpecification` /
  `PortfolioOptimization` / `PortfolioOptimizationEngine`; domain tag `optimization/1`;
  engine `optimization-engine/1`; solve `optimization-solve/1`. Confirm before they are
  baked into identity (changing them later is a breaking identity change).
- **Q3 — objective vocabulary.** v1 pins exactly `{"minimum_variance"}`. Confirm this is
  the sole v1 objective (mean-variance/max-Sharpe explicitly deferred pending a PIT-safe
  `μ`).
- **Q4 — `N` bound.** Inherit Phase 20's `N_MAX = 16` implicitly (the risk model already
  caps `N`); confirm no separate optimizer cap is wanted.
- **Q5 — data-model block.** On approval, append a `PO-1..PO-5` block to `data-model.md
  §12` (mirroring FR-1..5) and add an ARCHITECTURE.md row + docs/index.md entry — **at
  implementation time, not now.**

## 25. Explicit out-of-scope list (strict)

Phase 21 does **not** include, and reserves for future explicitly-labelled phases:

- Mean-variance, maximum-Sharpe, or any expected-return-dependent objective (no PIT-safe
  `μ`).
- Long-only, box, gross-exposure/leverage, or concentration (inequality) constraints; any
  iterative QP / active-set / interior-point solver.
- Risk-parity / equal-risk-contribution or any nonlinear/iterative-root-finding objective.
- Tracking-error / benchmark-relative optimization (no benchmark-in-factor-space artifact).
- Robust / Bayesian / Black-Litterman / shrinkage optimization; any regularization of `Σ`.
- Walk-forward / rolling / regime-conditioned optimization; a time series of decisions.
- Transaction-cost-aware optimization; any use of current holdings.
- **Asset-level** portfolio construction (no PIT-safe asset covariance exists); any second
  covariance source; any recomputation or shrinkage of the Phase 20 covariance.
- Any **execution** logic (fills, cash, positions, costs, accounting) — that is Phase 12.
- Any **PIT-eligible** portfolio-decision artifact (the output is ex-post only).
- A generic optimizer / Python-callback framework; any float, RNG, or wall-clock use; any
  new store, database, network, ingestion, UI, or API.
- Any modification to Phase 20 (or any prior phase) vocabulary, engine, or identity;
  feeding a `PortfolioOptimization` into Phase 12 or Phase 17.

---

## 26. Summary

Phase 21 should add the **smallest honest optimizer** the architecture now supports: a
**fully-invested global minimum-variance portfolio over the *N* factors of one sealed
`FactorRiskModel`**, decision variables = **factor weights**, objective = **`min wᵀΣw`**
(no fabricated expected returns), constraint = **`1ᵀw = 1`**, solved **closed-form with
the existing `_linalg` `ldl`/`ldl_solve`** (no new linear algebra, no dependency, no
float, no RNG, no clock, no new store, no execution). Non-positive-definite `Σ` is a
first-class **`SINGULAR_COVARIANCE` UNDEFINED** result, never repaired. The output is
**ex-post, not PIT** (new invariants PO-1..PO-5, the invariant-28 analogue), sealed as a
`PortfolioOptimization` `ResearchRecord` write-once to the existing sidecar. Proposed
release **`v0.18.0`**. Every richer objective, every inequality constraint, and every
asset-level or execution capability is explicitly deferred or rejected with a grounded
repository reason.
