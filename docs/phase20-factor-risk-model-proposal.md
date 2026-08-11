# Phase 20 — Factor Risk Model: Factor Covariance & Correlation Estimation (PROPOSAL)

> **Status: DESIGN ONLY — awaiting approval.** No source, tests, locked spec, or
> release work exist yet. This document proposes the capability, its architecture,
> its identity/PIT discipline, and the decisions that need sign-off before any
> implementation begins. It follows the structure of
> [phase19-factor-portfolio-proposal.md](phase19-factor-portfolio-proposal.md) and
> [phase18-cross-sectional-regression-proposal.md](phase18-cross-sectional-regression-proposal.md).
>
> **Proposed version: `v0.17.0`** (Phase 19 = v0.16.0, confirmed by git tag
> `v0.16.0`). No existing version label is changed.

---

## 1. Executive summary

Phase 20 adds a **factor risk model** — the deterministic estimation of a **factor
covariance matrix**, the companion **correlation matrix**, per-factor
**volatilities**, and the per-factor **mean-return vector** — over a set of
already-sealed Phase 19 `FactorPortfolio` factor return series. It is a **pure
consumer** of sealed `ResearchRecord`s (the exact posture of Phase 15 analytics and
Phase 17 attribution over backtests, here applied to Phase 19 factor portfolios): it
resolves *N* referenced `FactorPortfolio` ids from the shared research sidecar,
re-verifies each one's content hash (fail closed on absence or drift), aligns their
KNOWN `(as_of, factor_return)` series on a **common time axis**, and computes the
`N × N` population covariance and correlation matrices plus the volatility and mean
vectors under the pinned exact-`Decimal` context. It seals a content-addressed
`FactorRiskModel` write-once to the existing sidecar.

It is the capability **Phase 19 explicitly named as its successor** ("Factor risk
model / covariance-matrix estimation — needs multiple factor series first; the phase
after this", `docs/phase19-factor-portfolio-locked.md` §9). It is also the **missing
prerequisite** for portfolio/risk optimization (candidate D): a minimum-variance,
risk-constrained, or factor-neutral optimizer is undefined without a covariance
matrix, and no covariance matrix exists anywhere in the system today.

Crucially, Phase 20 introduces **no new PIT resolution surface at all**: like
analytics and attribution, it reads *only* sealed records from the sidecar and never
touches the universe, panel, or price layers. It adds no runtime dependency, no
database, no new store, no RNG, and no wall-clock; it modifies no prior artifact's
identity. It is a strictly additive sibling in the "consumes-sealed-artifacts" family.

---

## 2. Problem statement

Phase 19 can produce a factor return series, one signal at a time — but a **single
factor's return series answers no risk question by itself**. The questions a
quantitative researcher asks next are inherently *multi-factor and second-moment*:

- How volatile is each factor?
- How correlated are two factors — is my "value" factor just a slow "size" factor?
- What is the joint covariance structure of my factor set — the object every
  portfolio optimizer, risk budget, and factor-neutrality constraint is defined over?

None of these can be answered today. The system computes:
- a **scalar** covariance/correlation between a backtest and one benchmark
  (`analytics/compute._covariance`, Phase 15) — two series only, no matrix;
- design-matrix cross-products `XᵀX` inside the OLS of Phase 17/18 — a Gram matrix of
  *regressors*, not a covariance of *return series*, and never surfaced as an artifact;
- coefficient standard errors via `_linalg.inverse_diagonal` — the **diagonal** of one
  inverse, never a full matrix.

There is **no `N × N` covariance or correlation matrix over multiple return series
anywhere in the codebase, and no artifact that carries one.** Phase 20 fills exactly
that gap, and only that gap.

---

## 3. Why now

1. **The input finally exists and is clean.** Phase 19 seals one `FactorPortfolio`
   per signal, each exposing a directly-extractable KNOWN `(as_of, factor_return)`
   series (`per_period[i].as_of`, `per_period[i].factor_return`), UNDEFINED-preserving
   so gaps are explicit. Before Phase 19 there were no factor return series to relate.
2. **Phase 19 named it as the next phase**, and deliberately scoped covariance *out*
   ("needs multiple factor series first; the phase after this").
3. **It is the load-bearing prerequisite for the optimization spine (candidate D).**
   Minimum-variance / target-risk / factor-neutral portfolios are all functions of a
   covariance matrix. Building optimization first would smuggle in covariance
   estimation implicitly; building the risk model first makes it a first-class,
   auditable, content-addressed artifact that an optimizer later *consumes*.
4. **The consuming pattern is mature.** Phases 13, 14, and 17 have established exactly
   how to reference N sealed records, fold their hashes transitively, and fail closed
   on drift. Phase 20 is a faithful instance of that pattern applied to a new record
   family (Phase 19 portfolios) and a new statistic (a second-moment matrix).

---

## 4. Existing capabilities reused

| Reused | From | How Phase 20 uses it |
|---|---|---|
| `FactorPortfolio` sealed record + `from_dict` | Phase 19 | The *N* inputs; each contributes one KNOWN factor return series (`per_period → factor_return`), its `schedule_id`, `factor_portfolio_engine_version_id`, corpus pins, and `result_hash`. |
| `ResearchResultStore` (shared sidecar) | Phase 8 | Resolve each referenced `factor_portfolio_id` via `read_as(id, FactorPortfolio.from_dict)`; seal the `FactorRiskModel` write-once. **No new store.** |
| `ResearchRecord` protocol | Phase 8 | `FactorRiskModel` implements it (`research_result_id` property + `to_dict`), reusing the write-once / byte-identical / fail-closed sidecar I/O. |
| `sha256_hex`, `_SEP="\x00"`, canonical JSON (`sort_keys=True, ensure_ascii=False, separators=(",",":")`) | shared identity idiom | Content-addressed `factor_risk_id` and `result_hash`. |
| Pinned decimal context (prec 34, `ROUND_HALF_EVEN`), `Decimal.sqrt` | every prior compute phase | All arithmetic; `sqrt` for volatilities and correlations (Phase 12/19 precedent). |
| `StatValue` KNOWN/UNDEFINED cell idiom | Phases 15/16/18/19 | Every matrix/vector cell is a KNOWN decimal string or an UNDEFINED reason — never a fabricated `0`, `NaN`, or divide-by-zero. |
| Multi-artifact reference discipline (ordered refs, fold child `result_hash`, fail closed on absence/`research_result_id` drift) | Phases 13/14/17 | The reference model (§8) is a direct instance of this precedent. |

**Deliberately NOT reused / NOT needed:** `_linalg` (`ldl`/`ldl_solve`/
`inverse_diagonal`). A covariance matrix is a sum of products — **it requires no
matrix factorization and no inversion.** The *inverse* of the covariance matrix (the
object a min-variance optimizer needs) is intentionally **out of scope** and is the
prerequisite candidate D still lacks (§9, §19). Phase 20 therefore adds nothing to
`_linalg`.

---

## 5. Alternatives considered (candidate ranking)

Every serious candidate from the brief, evaluated on the required axes (problem
solved; why unsolved by 1–19; sealed artifacts consumed; genuinely new artifact; new
look-ahead surface; prior-phase edit; new dependency/store; above/beside; capability
vs convenience; enough substance).

### Rank 1 — **A. Factor risk / covariance modeling** *(SELECTED)*

- **Problem:** no second-moment structure over factor returns exists.
- **Why unsolved:** Phase 19 stops at single-factor series and defers this by name.
- **Consumes:** *N* sealed `FactorPortfolio` records (their KNOWN factor series).
- **New artifact:** yes — the first `N × N` matrix artifact in the system
  (`FactorRiskModel`).
- **New look-ahead surface:** none — reads only sealed ex-post records; introduces no
  new PIT resolution; typed non-PIT (FR-2).
- **Prior-phase edit:** none beyond an additive `Workspace` property + `__init__`
  re-exports.
- **New dependency/store:** none.
- **Above/beside:** *beside* Phase 19 (a consumer sibling), *above* it in the DAG.
- **Capability vs convenience:** capability — a distinct estimator with its own
  methodology, degeneracy semantics, and identity.
- **Substance:** high — new matrix data model, new cross-series commensurability
  discipline, prerequisite for the entire optimization spine.

### Rank 2 — **C. Factor portfolio families / factor return matrix**

A genuine artifact (an aligned `N`-factor return matrix) — but it is a **strict
sub-component of A**. Building the covariance model *requires* first aligning the *N*
series into a common-axis matrix; A therefore delivers C's core value (the aligned
matrix, surfaced in coverage/provenance) *plus* the risk statistics. A standalone
"family" that only bundles series without a new second-moment result would be close to
the "batch convenience wrapper" the brief warns against. **Folded into A**, deferred as
a standalone.

### Rank 3 — **D. Portfolio / risk optimization**

High value, but **explicitly blocked**: an optimizer is a function of a covariance
matrix (which does not exist until A) *and* needs a matrix inverse / PSD linear solve
(`_linalg` today has only `ldl`/`ldl_solve`/`inverse_diagonal`, no full inverse). Per
the brief's instruction to "explicitly identify that prerequisite rather than
smuggling it into Phase 20," the covariance matrix (A) is that prerequisite. Optimization
becomes a clean Phase 21 that *consumes a sealed `FactorRiskModel`*. **Deferred.**

### Rank 4 — **B. Holdings-based factor exposure**

Feasible without modifying Phase 12 (the sealed `BacktestResult.ledger` persists
per-rebalance `positions` as unadjusted shares **and** `target_weights`), but it (a)
requires **re-marking** positions from the pinned market corpus to get realized dollar
weights — a recompute step with its own PIT-marking care — and (b) needs a factor model
to express exposures *against* (regressing holdings' returns on factor returns, or
projecting characteristics). It sits **above or beside** a risk model, not before it.
Valuable, but neither foundational nor prerequisite-unblocking. **Deferred.**

### Rank 5 — **E. Multiple-testing / statistical robustness**

Coherent eventually, but the pipeline does not yet generate enough *discovered signals*
to correct across, and it is a statistical-hygiene layer that can sit above diagnostics
or portfolios later. It does not unblock the risk→optimization spine. **Deferred.**

### Rank 6 — **F. Walk-forward / out-of-sample**

Valuable and PIT-sensitive, but Phase 12 already performs as-of walks and Phase 13
already sweeps parameter grids; a train/test split is primarily an
experiment-orchestration extension, not a new second-moment capability, and it does not
unblock optimization. **Deferred.**

**Conclusion:** A is the single highest-value missing capability, the explicitly-named
successor, the prerequisite for D, and the cleanest possible composition (sidecar-only
consumer, zero new PIT surface). C is subsumed by it; B/D/E/F remain deferred.

---

## 6. Architecture

Phase 20 is a thin factor-risk-estimation layer that sits **above Phase 19** and is a
**consumer sibling** of Phase 15 analytics / Phase 17 attribution — the correct
precedent because, like those, it consumes *already-sealed* records from the sidecar
rather than re-reading raw corpora. It never touches the universe, panel, or price
layers, so it inherits their PIT correctness transitively and adds no new resolution.

```
        FactorRiskSpecification            (declarative request, content-addressed)
        { name, ordered factor_portfolio_ids, periods_per_year, ... }
                     |
                     v
   Workspace.factor_risk_engine  --->  FactorRiskEngine.estimate(spec)
                     |                  |
                     |   resolve each factor_portfolio_id from the shared sidecar        — fail closed
                     |     store.read_as(id, FactorPortfolio.from_dict)
                     |     verify present + research_result_id == id + result_hash        (FR-1)
                     |
                     |   commensurability (FR-3):
                     |     require one common schedule_id across all N
                     |     require one common factor_portfolio_engine_version_id
                     |     surface distinct corpus pins as pin_mismatch (never reconcile)
                     |
                     |   align (FR-4): common estimation dates = the as_of where
                     |     EVERY referenced factor has a KNOWN factor_return (complete-case)
                     |     require M >= _MIN_PERIODS (=2) common dates                     — fail closed
                     |
                     |   compute under pinned Decimal context:
                     |     mean_i, vol_i (population std)
                     |     cov(i,j) = (1/M) Σ (f_i - mean_i)(f_j - mean_j)   [N×N, symmetric]
                     |     corr(i,j) = cov(i,j)/(vol_i·vol_j)  (UNDEFINED if a vol is 0)
                     |     annualized vol_i = vol_i·√ppy ; annualized cov(i,j) = cov·ppy
                     v                  v
        FactorRiskModel (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                     |
        store.read_as(id, FactorRiskModel.from_dict)  (typed, byte-identical round-trip)
```

**New package `src/quantforge/factorrisk/`** (mirrors `attribution/` / `factorportfolio/`):

- `errors.py` — `FactorRiskError` → `FactorRiskConfigurationError`,
  `FactorRiskConsistencyError`.
- `version.py` — `FactorRiskEngineVersion` (folds the pinned decimal context + the
  formula-method version into `config_hash`); constants
  `FACTORRISK_ENGINE_VERSION = "factorrisk-engine/1"`,
  `FACTORRISK_FORMULA_VERSION = "factorrisk-stats/1"`,
  `FACTORRISK_SPEC_VERSION = "factorrisk/1"`; `default_decimal_context()`; the id
  property `factor_risk_engine_version_id`.
- `identity.py` — `factor_risk_result_hash`, `factor_risk_id`; domain tag
  `factorrisk/1`.
- `model.py` — `FactorRiskStatus` / `FactorRiskUndefinedReason`; `StatValue`; the
  nested cells `FactorMoment` (per-factor label/mean/vol/annualized vol),
  `CovarianceCell`, `CorrelationCell`, and the `CoverageSummary` (aligned M,
  per-factor available counts, common schedule).
- `spec.py` — `FactorRiskSpecification`, full construction-time validation.
- `stats.py` — the pure estimator (`factor_moments`, `covariance_matrix`,
  `correlation_matrix`); take decimal-string vectors, return KNOWN/UNDEFINED cells; no
  store access.
- `result.py` — `FACTORRISK_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, `FactorRiskModel`
  (`ResearchRecord` with `.seal` / `to_dict` / `from_dict`).
- `engine.py` — `FactorRiskEngine` (from `Workspace`; reuses the shared research
  sidecar): resolve + verify + commensurability + align + compute + seal + write-once.
- `__init__.py` — exports `FactorRiskSpecification`, `FactorRiskModel`.

**Edits to existing source (all additive; none altering any existing identity):**

1. `workspace.py` — one lazy `factor_risk_engine` `@property` (+ its private cache
   line), following the `attribution_engine` / `factor_portfolio_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of `FactorRiskSpecification` and
   `FactorRiskModel` (spec + result only; the engine is reached via `Workspace`).
3. `tests/test_smoke.py` — one additive public-API export assertion.

**No edit to** `factorportfolio/*`, `backtest/*`, `analytics/*`, `attribution/*`,
`crosssection/*`, `diagnostics/*`, `panel/*`, `market/*`, `universe/*`, `_linalg/*`, or
any identity/version module of a prior phase. **No new PIT resolution, no new store.**

---

## 7. Data flow

1. **Resolve (FR-1).** For each `factor_portfolio_id` in the ordered spec, read the
   record via `store.read_as(id, FactorPortfolio.from_dict)`. Missing → raise
   `FactorRiskConsistencyError`. A read record whose `research_result_id != id` → raise
   (sidecar drift). A record that is not a `FactorPortfolio` → raise (type).
2. **Commensurability (FR-3).** Collect each factor's `schedule_id` and
   `factor_portfolio_engine_version_id`; if not all identical → raise
   (incommensurable). Collect the two corpus pins from each; the union of distinct
   fundamentals pins / market pins is stored, and `pin_mismatch = True` is surfaced if
   more than one distinct value appears in either (never reconciled, never raised —
   the FA-1 precedent).
3. **Extract series.** For each factor, build the map `as_of → factor_return` over only
   `per_period` cells whose `factor_return.status is KNOWN`.
4. **Align (FR-4, complete-case).** The estimation date set is the sorted intersection
   of as_of keys where **every** factor is KNOWN. Let `M = |dates|`. If `M < _MIN_PERIODS`
   (=2) → raise `FactorRiskConfigurationError` (cannot estimate dispersion; also fires
   when any factor has no KNOWN return, which forces an empty intersection). Assemble
   the `N × M` return matrix in factor order, columns in ascending `as_of` order.
5. **Compute** under an explicit `localcontext(prec=34, ROUND_HALF_EVEN)`:
   per-factor `mean_i`, population `vol_i = √((1/M)Σ(f_i-mean_i)²)`; the symmetric
   `cov(i,j) = (1/M)Σ(f_i-mean_i)(f_j-mean_j)`; `corr(i,j) = cov(i,j)/(vol_i·vol_j)`
   (UNDEFINED `ZERO_VARIANCE` if `vol_i` or `vol_j` is exactly 0; diagonal is exactly 1
   for a positive-variance factor); annualized `vol_i·√ppy` and `cov(i,j)·ppy`.
6. **Seal** the `FactorRiskModel` (identity computed in `.seal`) and `store.write(...)`
   (write-once; byte-identical rebuild is an idempotent no-op).

---

## 8. Proposed API

```python
from quantforge import Workspace, FactorRiskSpecification, FactorRiskModel

ws = Workspace.open(root)

spec = FactorRiskSpecification(
    name="core-factor-risk",
    factor_portfolio_ids=(  # ORDERED, order-semantic (fixes row/col order)
        value_factor_id,  # each a sealed Phase 19 FactorPortfolio id
        momentum_factor_id,
        quality_factor_id,
    ),
    periods_per_year="252",  # annualization convention (folded into identity)
)

model = ws.factor_risk_engine.estimate(spec)  # sealed, write-once FactorRiskModel

model.factors  # ordered FactorMoment: (label, mean, volatility, annualized_volatility)
model.covariance  # ordered CovarianceCell: (i, j, value)  upper triangle (i <= j), factor order
model.correlation  # ordered CorrelationCell: (i, j, value)  upper triangle, factor order
model.coverage  # aligned M, per-factor available counts, common schedule_id, pin_mismatch
model.research_result_id  # == model.factor_risk_id (ResearchRecord key)

again = ws.research_result_store.read_as(
    model.research_result_id, FactorRiskModel.from_dict
)
```

`FactorRiskEngine` is reached only through `Workspace.factor_risk_engine` (a lazy,
cached, cycle-free `@property` annotated `-> object`; engines are not re-exported at
top level). `estimate(spec) -> FactorRiskModel` is the single entry point. No `Company`
method is added (a risk model spans a set of factors, not one filer).

---

## 9. Data model

All types `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
float/wall-clock/RNG.

### 9.1 `FactorRiskSpecification` (declarative request)

```
FactorRiskSpecification(
    name: str,                              # non-empty
    factor_portfolio_ids: tuple[str, ...],  # ORDERED, 2..N_MAX, unique, each non-empty
    periods_per_year: str = "1",            # canonicalized decimal; folded into identity
    spec_version: str = "factorrisk/1",
)
```

Construction-time validation (fail closed, `FactorRiskConfigurationError`): empty
`name` / `spec_version`; fewer than 2 or more than `N_MAX` factor ids; any empty or
non-`str` id; a duplicate id (a factor cannot appear twice — its self-correlation is a
trivial 1 and would corrupt ordering semantics); a non-decimal / non-finite
`periods_per_year` (canonicalized in place via `str(+Decimal(...))` so two spellings of
the same number yield one id). It reads no store — it cannot know whether the ids
resolve (the engine's FR-1 step) or whether the series are commensurable (the engine's
FR-3/FR-4 steps); it validates only the request's internal shape. `to_dict()` emits the
canonical request payload.

### 9.2 `FactorRiskModel` (implements `ResearchRecord`)

```
FactorRiskModel(
    factor_risk_engine_version_id: str,
    factor_risk_spec: dict[str, object],          # full FactorRiskSpecification.to_dict()
    name: str,
    spec_version: str,
    factor_refs: tuple[tuple[str, str, str], ...], # (label, factor_portfolio_id, result_hash), order-semantic
    boundary_kind: str,                            # "pit" — documents the underlying signal side only (FR-2)
    schedule_id: str,                              # the single common schedule of the inputs
    factor_portfolio_engine_version_id: str,       # the single common producing-engine version
    periods: int,                                  # M, the aligned complete-case date count
    periods_per_year: str,
    factors: tuple[FactorMoment, ...],             # per-factor moments, factor order
    covariance: tuple[CovarianceCell, ...],        # upper triangle (i <= j), factor order
    correlation: tuple[CorrelationCell, ...],      # upper triangle (i <= j), factor order
    coverage: CoverageSummary,                     # audit metadata (NOT folded)
    dataset_version_ids: tuple[str, ...],          # sorted, deduped fundamentals pins across inputs
    market_dataset_version_ids: tuple[str, ...],   # sorted, deduped market pins across inputs
    formula_version: str,                          # "factorrisk-stats/1"
    result_hash: str,
)

# derived, never stored as state:
factor_risk_id     property -> sha256 folding engine version + request + child hashes + result_hash
research_result_id property -> alias of factor_risk_id
pin_mismatch       property -> len(dataset_version_ids) > 1 or len(market_dataset_version_ids) > 1
```

- `FactorMoment(label, mean: StatValue, volatility: StatValue, annualized_volatility:
  StatValue)` — the diagonal/first-moment block; `label` = `factor_1..factor_N` in
  spec order (identity-invisible display label, the attribution precedent).
- `CovarianceCell(i: int, j: int, value: StatValue)` / `CorrelationCell(i, j, value)` —
  `i <= j` (upper triangle; the matrix is symmetric, so the lower triangle is implied
  and never stored). Covariance cells are KNOWN (a covariance is always defined given
  `M ≥ 2`); a correlation cell is UNDEFINED `ZERO_VARIANCE` when either factor's
  volatility is exactly 0.
- `CoverageSummary(per_factor: tuple[(label, factor_portfolio_id, available, used),
  ...], aligned_periods, dropped_for_alignment)` — how many KNOWN periods each factor
  had vs how many survived complete-case alignment. Audit only; **not folded**.
- `to_dict()` keys include `factor_risk_id`, `research_result_id` (alias), and every
  field above; a KNOWN cell emits `value`, an UNDEFINED cell emits `reason`.
- `from_dict` is the fail-closed inverse; `factor_risk_id` / `research_result_id` are
  re-derived by their properties, never read from state, so `from_dict(to_dict(r))`
  re-emits identical bytes and a tampered stored id is ignored. A malformed cell is
  refused with a `ValueError`.
- `.seal(...)` folds the ordered computed-output cells into `result_hash` (§10). The
  coverage summary and the per-factor available/used counts are audit metadata and are
  **not** folded (they are fully determined by the inputs).

### 9.3 Closed v1 vocabulary

`FactorRiskUndefinedReason` (closed): `ZERO_VARIANCE` (a correlation cell involving a
zero-volatility factor). `FactorRiskStatus`: `KNOWN`, `UNDEFINED`. Extending the reason
set is an explicit future edit that hashes distinctly.

---

## 10. Identity / content-addressing design

Domain tags via `sha256_hex`, NUL (`\x00`) separated, canonical JSON
(`sort_keys=True, ensure_ascii=False, separators=(",",":")`): record tag
`factorrisk/1`; engine tag `factorrisk-engine/1`; formula tag `factorrisk-stats/1`.

- `factor_risk_engine_version_id = sha256(code_version "factorrisk-engine/1",
  config_hash)` where `config_hash =
  sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=factorrisk-stats/1")`.
- `factor_risk_result_hash = sha256(canonical JSON over the ordered computed cells)`:
  the per-factor moment block (`{"block":"factor", label, mean, volatility,
  annualized_volatility}` in factor order), then the covariance block
  (`{"block":"cov", i, j, value}` for `i <= j`, factor order), then the correlation
  block (`{"block":"corr", i, j, value}`, same order). One differing cell changes it.
- `factor_risk_id = sha256`, NUL-joined, in this exact order (mirroring the Phase 17
  attribution fold): `factorrisk/1`, `factor_risk_engine_version_id`, `name`,
  `spec_version`, canonical-JSON **ordered** `factor_portfolio_ids`, `periods_per_year`,
  canonical-JSON **ordered** factor `result_hash`es, `result_hash`.
- `research_result_id` aliases `factor_risk_id`.

**Folds (changes identity):** engine + formula + decimal-context version ✔; the full
declared request (name, spec version, the **ordered** factor id list, the annualization
convention) ✔; each referenced factor's **content hash** — transitively pinning each
input's whole sealed output, the Phase 13/17 doctrine (a `factor_portfolio_id` already
folds that factor's request + both corpus pins + its own `result_hash`, so folding the
id *and* the child `result_hash` pins the input exactly) ✔; the computed matrices (via
`result_hash`) ✔.

**Does NOT fold:** the record schema/format version
(`FACTORRISK_RESULT_FORMAT_VERSION` — a container concern), the coverage summary (audit
metadata), any presentation, wall-clock, RNG, `id()`, or iteration order (factor order
follows the spec; matrix cells follow factor order; the corpus-pin tuples are sorted).

Same ordered set of sealed inputs + same annualization → same `factor_risk_id` and the
same bytes on any machine.

---

## 11. PIT / no-look-ahead analysis

- **Zero new PIT resolution.** Phase 20 reads *only* sealed `FactorPortfolio` records
  from the sidecar. It never calls `panel_across`, `build_as_of`, or any price
  accessor. Global invariants 6–17 (the PIT eligibility machinery) are untouched — the
  layer has no as_of boundary of its own.
- **The output is ex-post, not PIT (FR-2).** A covariance/correlation matrix is a
  full-sample second-moment statistic over realized (post-`T`) factor returns — the
  same ex-post character as Phase 17 attribution and Phase 18 premia. `FactorRiskModel`
  is **not** a `Pit*` type, exposes **no** as-of accessor, and is inadmissible where a
  PIT signal/value is required (the analogue of invariant 28 / P19-2 / FA-2 / XS-2).
  `boundary_kind = "pit"` documents only that the *underlying factors' signal side* was
  PIT-eligible (a property inherited from each input's P19-3), not that the matrix is a
  PIT value.
- **No new leakage surface introduced by combining series.** The only new operation is
  aligning series that each already used their own ex-post forward returns. Complete-case
  alignment selects estimation dates purely from the *already-sealed* KNOWN sets — it
  peeks at no data beyond what each factor already (ex-post) incorporated. The full-sample
  covariance makes no claim of being knowable at any historical `T`; FR-2 enforces that
  by type.
- **Transitive PIT inheritance.** Because each input is a Phase 19 record whose signal
  side was read PIT-eligibly (P19-3) and whose corpus pins were re-verified (P19-1), the
  risk model inherits that discipline; folding the child `result_hash`es means any change
  to an input's PIT-correctness changes the risk model's identity (FR-1).

---

## 12. Failure / UNDEFINED semantics

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`FactorRiskConfigurationError` / `FactorRiskConsistencyError`):
- Malformed spec: empty `name`/`spec_version`; `< 2` or `> N_MAX` factor ids; an empty
  or non-`str` id; a duplicate id; a non-decimal / non-finite `periods_per_year`.
  *(configuration)*
- A non-`FactorRiskSpecification` argument to `estimate`. *(configuration)*
- A referenced `factor_portfolio_id` absent from the sidecar, or a read record whose
  `research_result_id != id` (drift), or a record that is not a `FactorPortfolio`
  (type). *(consistency — the Phase 14 `ReportEngine` precedent)*
- **Incommensurable inputs:** the factors do not all share one `schedule_id`, or do not
  all share one `factor_portfolio_engine_version_id`. *(consistency, FR-3)*
- **Insufficient common data:** fewer than `_MIN_PERIODS = 2` complete-case common dates
  (also fires when any factor contributes no KNOWN return). *(configuration, FR-4)*
- A corrupt / non-finite decimal read from a factor's `factor_return` cell.
  *(consistency, never guessed)*

**Recorded as first-class UNDEFINED (never raised, never fabricated — FR-4):** a factor
whose population volatility over the common window is exactly 0 → every **correlation**
cell involving it is `ZERO_VARIANCE` (its mean, volatility=`0`, and every covariance
cell stay KNOWN). There is no divide-by-zero anywhere: a zero denominator in the
correlation becomes a recorded UNDEFINED, exactly as Phases 15/16/18/19 do.

**Note on corpus pins:** distinct fundamentals or market pins across the inputs are
**surfaced** as `pin_mismatch = True` (and stored in the two pin tuples), never raised
and never reconciled — the Phase 17 FA-1 / Phase 13 `BacktestComparison` precedent. A
coherent risk model will normally be built over commensurable corpora, but factors over
different universes can legitimately differ; the flag makes the condition auditable.

---

## 13. Persistence model

Zero new store types. The `ResearchResultStore` writes the record to
`<root>/research/sha256-<hex>.json` in the existing container. Write-once and
idempotent: re-estimating an identical model is a byte-identical no-op; a differing
payload under an existing id fails closed via the store's guard. `read_as(id,
FactorRiskModel.from_dict)` round-trips byte-identically.

---

## 14. Invariants (proposed FR-1..FR-5; additive — do not weaken 1–30)

- **FR-1. Reference verification & transitive pinning.** A factor-risk run resolves and
  re-verifies each referenced `factor_portfolio_id` from the sidecar — fail closed on
  absence or on `research_result_id != id` (drift) — and folds each input's
  `result_hash` into `factor_risk_id`, so any change to a referenced factor yields a
  different `factor_risk_id`. (The Phase 13/14/17 reference-verification analog.)
- **FR-2. A factor risk model is not a PIT value.** A `FactorRiskModel` is a full-sample
  ex-post second-moment statistic over realized factor returns; it is not a `Pit*` type
  and exposes no as-of accessor; `boundary_kind = "pit"` documents only that the
  underlying factors' signal side was PIT-eligible. (The direct analog of invariant 28 /
  P19-2 / FA-2 / XS-2.)
- **FR-3. Commensurability.** All referenced factors must share one `schedule_id` and
  one `factor_portfolio_engine_version_id`; a mismatch fails closed. Distinct corpus
  pins are surfaced as `pin_mismatch`, never silently reconciled. (The FA-3 / FA-1
  analog.)
- **FR-4. Complete-case estimation & fail-closed degeneracy.** The estimation dates are
  exactly the as_of where **every** referenced factor has a KNOWN return (complete-case);
  a window below `_MIN_PERIODS = 2` (or any factor with no KNOWN return) fails closed; a
  zero-variance factor yields UNDEFINED correlation cells, never a fabricated value or a
  divide-by-zero. (The SD-4 / XS-4 / P19-4 analog for a cross-series estimator.)
- **FR-5. A factor risk model is neither a `BacktestResult` nor a `FactorPortfolio`.** A
  `FactorRiskModel` is a distinct record type; it does not enter Phase 12's or Phase
  19's identity and must not be passed where either is required (enforced by type). It
  consumes `FactorPortfolio`s and produces none. (The P19-5 analog, extended.)

These would be added to `docs/data-model.md §12` as an additive block **only during the
implementation/documentation step, after approval** — this proposal does not modify
`data-model.md`.

---

## 15. Testing strategy

New package `tests/factorrisk/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_stats.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline,
synthetic only:

- **Spec validation** — every fail-closed path (empty name; `< 2` / `> N_MAX` ids;
  empty/non-str id; duplicate id; non-decimal / non-finite `periods_per_year`); the
  annualization canonicalization; the order-preserving canonical payload.
- **Exact-`Decimal` estimator** against hand-computed references — a two-factor,
  three-period example with known means, population variances, covariance, and
  correlation (including the exact off-diagonal and the diagonal `1`); the annualized
  scaling (`ppy=4` → vol·2, cov·4); a perfectly-correlated pair (`corr = 1`), a
  perfectly-anti-correlated pair (`corr = -1`), an orthogonal pair (`cov = 0`,
  `corr = 0`); a zero-variance factor → `ZERO_VARIANCE` correlation cells with a KNOWN
  `0` variance/covariance; determinism (byte-stable, `-p no:randomly`).
- **Identity** — `factor_risk_id` fold + sensitivity to each input (engine version,
  name, spec version, factor id **order**, the id set, `periods_per_year`, any child
  `result_hash`); `factor_risk_result_hash` determinism + per-cell sensitivity +
  key-order independence; engine-version dependence on the pinned precision + formula.
- **Result** — byte-identical `to_dict`/`from_dict`; derived-id survival;
  `research_result_id` alias; `boundary_kind = "pit"`; result-hash sensitivity to a
  covariance/correlation cell; coverage **not** folded; UNDEFINED-cell round-trip;
  tampered-id ignored; malformed-cell rejection.
- **Engine (end-to-end over builders)** — build ≥3 sealed `FactorPortfolio`s over one
  shared schedule/synthetic corpus (reusing the Phase 19 builders), estimate the model,
  assert the matrix against hand values; persistence + byte-identical round-trip;
  re-estimation idempotent no-op; FR-1 (absent id raises; `research_result_id` drift
  raises; wrong record type raises); FR-3 (mixed `schedule_id` raises; mixed engine
  version raises; distinct corpus pins → `pin_mismatch = True`, not raised); FR-4
  (a factor with no KNOWN return → raise; `< 2` common dates → raise; zero-variance
  factor → `ZERO_VARIANCE` correlation cells); FR-2 (no `pit`/`as_of` accessor; not a
  `BacktestResult` / `FactorPortfolio`).
- `tests/test_smoke.py` — an additive export assertion for `FactorRiskSpecification` /
  `FactorRiskModel`.

No real financial or network data. Synthetic data only.

---

## 16. Quality gates

- `uv run pytest` green (all phases; Phase 20 suite added), deterministic across runs
  (including `-p no:randomly`).
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src` clean
  (strict).
- Zero runtime dependencies (stdlib `hashlib` / `json` / `dataclasses` / `Decimal`
  only); no float in any path; no wall-clock/RNG in any identity or value; volatilities
  and correlations use `Decimal.sqrt` under the pinned context.
- No new store, no database; only `<root>/research/` written; **no `_linalg` change**.
- No existing record identity changes — the only source edits are the additive
  `Workspace.factor_risk_engine` property/cache line and the `__init__.py` re-exports.
- Byte-identical `FactorRiskModel` round-trip + determinism double-build; FR-1..FR-5
  each covered by a test.

---

## 17. Out-of-scope (strict)

Deferred to later, explicitly-labelled phases; Phase 20 absorbs none:
- **Any matrix inversion / precision matrix / `_linalg` extension** — the object a
  min-variance optimizer needs; the deferred prerequisite for candidate D.
- **Portfolio / risk optimization** (min-variance, target-risk, factor-neutral,
  risk-budgeting) — candidate D, a future phase that *consumes* a sealed
  `FactorRiskModel`.
- **Risk decomposition of a given portfolio** (marginal / component contributions to
  risk) — needs portfolio weights; belongs with optimization/holdings analysis.
- **Idiosyncratic / residual risk, a full factor risk *model* (asset-on-factor
  exposures + specific variances)** — a distinct, larger capability; Phase 20 is the
  factor–factor covariance only.
- **Shrinkage / Ledoit-Wolf / EWMA / robust estimators, and any RNG-based estimator** —
  v1 is the exact population estimator; shrinkage is a future closed-vocabulary knob.
- **Pairwise-complete covariance** (see §18) — v1 is complete-case only.
- **Rolling / windowed / regime-conditioned covariance** — v1 is full-sample.
- **Holdings-based factor exposure** (candidate B) and **multiple-testing corrections**
  (candidate E) and **walk-forward/OOS** (candidate F) — separate future phases.
- **Batch estimation over many factor sets** — one spec = one risk model; batching is a
  thin future loop.

---

## 18. Approval-gated decisions

These need explicit sign-off before implementation; the **recommended** option is
listed first.

- **D-METHOD-1 — Alignment policy: complete-case (listwise) [recommended] vs
  pairwise-complete.** Complete-case (estimate over the dates where *all* factors are
  KNOWN) guarantees a positive-semidefinite matrix, is fully deterministic, and is the
  simplest to reason about — important because the matrix is the future optimizer's
  input. Pairwise-complete uses more data per pair but can produce a non-PSD matrix
  (a hazard for optimization). **Recommend complete-case.**
- **D-METHOD-2 — Population [recommended] vs sample covariance (÷M vs ÷(M−1)).** Phases
  16/18/19 use the population convention throughout (Fama–MacBeth `popStd/√M`, Phase 19
  population volatility). **Recommend population**, for consistency with the existing
  factor layers.
- **D-COMMENSURABILITY — Require one common `schedule_id` [recommended] vs intersect
  as_of across differing schedules.** Strict same-`schedule_id` mirrors Phase 17 FA-3
  and makes alignment exact and auditable. Cross-schedule intersection is more permissive
  but introduces alignment ambiguity. **Recommend strict same-`schedule_id`.**
- **D-PINS — Surface distinct corpus pins as `pin_mismatch` [recommended] vs hard-fail.**
  Surfacing mirrors Phase 17 FA-1 / Phase 13 `BacktestComparison`. **Recommend surface.**
- **D-NMAX — `N_MAX` cap on the factor count.** Phase 17/18 use `K_MAX = 8`. A covariance
  matrix is often wanted over more factors; **recommend `N_MAX = 16`** (an `N × N`
  exact-Decimal matrix at N=16 is trivial to compute). Alternative: reuse `8` for
  cross-phase symmetry.
- **D-ANNUALIZE — Include annualized vol + covariance cells [recommended] vs store only
  per-period matrices + the `periods_per_year` convention.** Annualization is a cheap,
  exact scaling and is what a researcher usually reports. **Recommend include** (both
  per-period and annualized), with `periods_per_year` folded into identity either way.
- **D-MEANVEC — Include the per-factor mean-return vector [recommended] vs omit.** The
  mean vector is the expected-return input a future optimizer pairs with the covariance.
  It is nearly free. **Recommend include.**
- **D-TRIANGLE — Store the upper triangle only [recommended] vs the full `N × N`.** The
  matrix is symmetric; storing `i <= j` halves the payload with no information loss and
  fixes a canonical cell order. **Recommend upper triangle.**

---

## 19. Open questions

1. **Optimizer prerequisite (explicitly flagged, not resolved here).** A min-variance /
   target-risk optimizer (candidate D) will require a positive-definite **matrix inverse
   / PSD linear solve** that `_linalg` does not expose today (only `ldl`, `ldl_solve`,
   `inverse_diagonal`). Whether that lands as a `_linalg` extension or a dedicated solver
   is a Phase 21 decision; Phase 20 deliberately does not build it.
2. **Zero-variance-factor policy.** v1 records `ZERO_VARIANCE` correlation cells and
   keeps the factor in the covariance matrix (variance/covariance = 0). Should such a
   degenerate factor instead be rejected at spec time? Recommend keeping it (recorded,
   not raised) — consistent with the UNDEFINED-preserving posture — but flag for review.
3. **Cross-factor label collisions / provenance display.** Labels are
   `factor_1..factor_N` (identity-invisible). Should the record also carry each factor's
   `name`/`signal` from its `FactorPortfolio` for readability (audit-only, not folded)?
   Minor; can be added to coverage without touching identity.
4. **Minimum-period floor value.** `_MIN_PERIODS = 2` is the dispersion floor used
   across the project; a covariance over 2 points is defined but noisy. Whether to raise
   the floor is a methodology choice deferred to review.

---

## 20. Proposed implementation files

*(Created only after approval; listed for scope review.)*

```
src/quantforge/factorrisk/__init__.py
src/quantforge/factorrisk/errors.py
src/quantforge/factorrisk/version.py
src/quantforge/factorrisk/identity.py
src/quantforge/factorrisk/model.py
src/quantforge/factorrisk/spec.py
src/quantforge/factorrisk/stats.py
src/quantforge/factorrisk/result.py
src/quantforge/factorrisk/engine.py

tests/factorrisk/__init__.py
tests/factorrisk/builders.py
tests/factorrisk/test_spec.py
tests/factorrisk/test_stats.py
tests/factorrisk/test_identity.py
tests/factorrisk/test_result.py
tests/factorrisk/test_engine.py
```

Additive edits to existing files (identity-preserving): `src/quantforge/workspace.py`
(one lazy `factor_risk_engine` property + cache line), `src/quantforge/__init__.py`
(re-export `FactorRiskSpecification`, `FactorRiskModel`), `tests/test_smoke.py` (one
export assertion). Documentation (locked spec, README row, ARCHITECTURE row, index
entry, `data-model.md` FR-1..FR-5 block) is a separate post-implementation step.

---

## 21. Version

**`v0.17.0`.** Phase 19 is `v0.16.0` (git tag confirmed). The package `__version__`
string stays `"0.0.0"` (versioning is by content-addressed ids, not a semver string, per
the established convention). No existing version label is changed.

---

*This is a design proposal. No source code, tests, locked specification, README,
ARCHITECTURE, `docs/index.md`, or `docs/data-model.md` change is made by it, and nothing
is committed, tagged, or released. Implementation awaits explicit approval.*
