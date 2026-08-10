# Phase 17 — Multi-Factor Performance Attribution (LOCKED)

> **Status:** Locked normative specification. Decisions **D1–D7** were approved as
> recommended and the six §22 open questions are resolved here; this document is the
> source of truth for the implementation and supersedes the recommendations in
> [phase17-factor-attribution-proposal.md](phase17-factor-attribution-proposal.md). Every
> conditional reference in the proposal ("recommended", "approval needed") is resolved
> here to a committed decision.
>
> **One-line thesis:** Phase 17 adds a deterministic, content-addressed **multi-factor
> performance-attribution** layer — the multi-factor generalization Phase 15 explicitly
> deferred, a **pure consumer** of Phase 12. Given a declarative
> `AttributionSpecification` naming one sealed subject `BacktestResult` and an **ordered**
> list of *K* sealed factor `BacktestResult`s, `AttributionEngine.attribute(...)` resolves
> and verifies each referenced backtest, regresses the subject's excess return on the *K*
> factor excess returns via an exact-`Decimal` OLS (LDLᵀ normal-equation solve with an
> exact zero-pivot test), and seals a `FactorAttribution` `ResearchRecord` write-once to
> the existing Phase 8 sidecar under the same pinned `Decimal` context. It reports
> per-factor betas + alpha, R² / adjusted R² / residual standard error, classical
> coefficient standard errors / t-statistics, and the sample mean-excess-return
> decomposition — every undefinable cell a first-class `UNDEFINED` value with a reason. It
> introduces **no** new data source, **no** new PIT resolution, **no** new store, **no**
> runtime dependency, and **no** database, and it consumes only sealed `BacktestResult`s.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D1** | Each factor is a **sealed `BacktestResult`** (generalize Phase 15 D3 from one benchmark to *K* factors). Caller-supplied return series / external index files are rejected — they would reintroduce fabricated / un-pinned data. This defines the input contract: the subject and every factor is resolved from the shared research sidecar by `backtest_id`. |
| **D2** | **Single content-addressed id.** `research_result_id` aliases `attribution_id` (mirroring `analytics_id` / `BacktestResult.backtest_id`) — an attribution is a value record whose id already folds its output. `attribution_id` folds the engine version, the declared request, every referenced `result_hash`, and the answer's `result_hash`. |
| **D3** | **`K_MAX = 8`.** A request declaring more than 8 factors is a configuration defect, raised at construction — never silently truncated. The `(K+1)×(K+1)` exact-`Decimal` factorization stays bounded and the model interpretable. |
| **D4** | **Persist only a deterministic residual digest, not the residual series.** The record folds a `sha256:` digest of the ordered residual decimal strings (a `residual` output-cell block); the series itself is never stored. The digest still content-addresses the exact residuals (a changed series → a different digest → a different `result_hash` / `attribution_id`). |
| **D5** | **Classical OLS standard errors / t-statistics only.** Coefficient covariance is `sigma_sq·(XᵀX)⁻¹`; robust / HAC / GLS / WLS / regularized estimators are out of scope (§20 of the proposal). |
| **D6** | Keep **FA-1 through FA-4 as phase-local invariants** documented here (the Phase 15 D9 precedent), **not** added to the numbered `data-model.md §12` registry. No global invariant-catalog edit. |
| **D7** | This phase releases as **`v0.14.0`** (Phase 16 is `v0.12.0`). The package `__version__` string is unchanged (versioning is by content-addressed ids, not a semver string). |

### 1.1 Resolved open questions (§22)

The proposal left six questions open; all are resolved here and are load-bearing for the
implementation.

1. **Excess-return convention.** **Excess-on-excess.** The regressand is `y = subject −
   rf` and every regressor column is `xₖ − rf` (the risk-free per-period rate subtracted
   from *both* the subject and each factor), so the intercept is the subject's
   excess-return alpha net of the factors' excess exposures.
2. **Intercept annualization.** Use the existing QuantForge `periods_per_year` convention:
   the rate is validated and recorded on the record and **folded into `attribution_id`**
   for provenance, but v1 diagnostics are reported **per period** — no annualized-alpha
   cell is fabricated in v1 (the convention is retained for provenance and future use).
3. **Degenerate / singular factor.** **Fail the entire coefficient block closed with
   `SINGULAR_DESIGN`.** A collinear or degenerate design is never silently reduced by
   dropping the offending factor — dropping would change the model the caller requested.
   The whole coefficient / diagnostic / decomposition block is `UNDEFINED(SINGULAR_DESIGN)`
   and no residual is fabricated.
4. **`K_MAX` value.** **8** (D3).
5. **Residual retention.** **Digest only** (D4).
6. **Later Phase-14 report scope.** **Not reserved now.** A future reporting layer may
   reference an attribution record in a later edit; no reporting scope is reserved in this
   phase.

### 1.2 Deviations from the proposal (disclosed)

Recorded for auditability; none changes an identity discipline or weakens an invariant.

1. **`periods_per_year` default is `"1"`.** The proposal's example passes `"12"`; the spec
   defines the field with a default of `"1"` (no annualization) so a minimal request need
   not supply a convention. It is validated (finite, strictly positive) and canonicalized
   at construction and folded into `attribution_id`.
2. **The residual digest is folded via a dedicated `residual` output-cell block.** The
   proposal §8 lists "coefficients → diagnostics → decomposition" as the sealed cells; the
   implementation appends a fourth `{"block": "residual", "digest": …}` cell so the D4
   digest is inside `result_hash` (a changed residual series changes the id). This
   strengthens, not weakens, the answer seal.
3. **Diagnostics are a closed three-key set** (`adjusted_r_squared`, `r_squared`,
   `residual_std_error`), stored **sorted by key**; per-coefficient standard errors and
   t-statistics live on each coefficient cell (a `(label, estimate, std_error, t_stat)`
   quadruple), because they are indexed by coefficient, not global. This is the Phase 15
   closed-key discipline applied to the multi-factor case.

---

## 2. Architecture (locked)

Phase 17 is a thin attribution layer *above* Phase 12, structurally a **sibling of Phase
15** (`analytics`) — the correct precedent because Phase 17, like analytics, *does*
arithmetic (unlike experiment/report, which orchestrate pointers). It follows the
extension recipe every prior phase uses: versioned immutable request object → fail-closed
engine reached from `Workspace` via a lazy, cycle-free `@property` → distinct result type
→ content-addressed identity with fresh domain tags → data conditions recorded as
first-class values, defects raised → compute-on-demand with the shared write-once sidecar.
Like Phases 13/14/15 (and unlike Phase 16, which reads raw corpora), Phase 17 consumes
**sealed `BacktestResult`s** and references them by `(backtest_id, result_hash)`.

```
                 AttributionSpecification         (declarative request, content-addressed)
                          |
                          v
   Workspace.attribution_engine   --->   AttributionEngine.attribute(spec)
                          |                 |
                          |   resolve subject + each factor from the shared sidecar,
                          |     read_as(id, BacktestResult.from_dict)          — fail closed
                          |   verify each: id matches, result_hash recomputes  (drift detect)
                          |   verify commensurability (FA-3): same schedule_id,
                          |     equal period_returns length, same engine version
                          |   check degrees of freedom: n >= K + 2             — fail closed
                          |
                          |   regress excess-on-excess under the pinned Decimal context:
                          |     X = [1 | x1-rf | ... | xK-rf], y = subject-rf
                          |     solve (XᵀX)β = Xᵀy via exact-Decimal LDLᵀ + exact zero pivot
                          |     R², adj R², residual std err, coef std errs / t-stats,
                          |     mean-excess decomposition — UNDEFINED-preserving (FA-4)
                          v                 v
             surface carried corpus pins (distinct, sorted) -> pin_mismatch (never raised)
                          |
                          v
             FactorAttribution (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
             store.read_as(id, FactorAttribution.from_dict)   (typed, byte-identical round-trip)
```

**New package `src/quantforge/attribution/`** (mirrors `analytics/`):

- `errors.py` — `AttributionError` → `AttributionConfigurationError`,
  `AttributionConsistencyError`.
- `version.py` — `AttributionEngineVersion` (folds the pinned decimal context **and** the
  formula-method version `attribution-stats/1` into `config_hash`);
  `ATTRIBUTION_ENGINE_VERSION = "attribution-engine/1"`, `ATTRIBUTION_FORMULA_VERSION =
  "attribution-stats/1"`; `default_decimal_context()`. Mirrors `analytics/version.py`. The
  id property is `attribution_engine_version_id`.
- `identity.py` — `attribution_result_hash`, `attribution_id`, `residual_digest`. Fresh
  record domain tag `attribution/1`.
- `model.py` — `AttributionStatus` / `AttributionUndefinedReason` vocabulary; the closed
  v1 `DIAGNOSTIC_KEYS`; `INTERCEPT_LABEL` / `factor_label`; `StatValue` (a KNOWN decimal
  string **or** UNDEFINED+reason).
- `stats.py` — the pure OLS functions (`parse_returns`, `attribute_returns` and the
  exact-`Decimal` LDLᵀ helpers `_ldl`, `_ldl_solve`, `_inverse_diagonal`). Pure; read no
  store; take decimal-string vectors, return `AttributionEstimate` blocks of KNOWN /
  UNDEFINED cells.
- `spec.py` — `AttributionSpecification`, full construction-time validation;
  `ATTRIBUTION_SPEC_VERSION = "attribution/1"`; `K_MAX = 8`.
- `result.py` — `ATTRIBUTION_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, `FactorAttribution`
  (a `ResearchRecord` with `.seal` / `to_dict` / `from_dict`).
- `engine.py` — `AttributionEngine` (constructed from `Workspace`; reuses the shared
  `research_result_store` + `AttributionEngineVersion`): resolve + verify → commensurability
  → degrees-of-freedom → regress → seal → write-once.
- `__init__.py` — package exports.

**The only edits to existing source** (both additive, neither altering any existing
identity):

1. `workspace.py` — one lazy `attribution_engine` `@property` (+ its
   `self._attribution_engine: object | None = None` cache line), following the
   `analytics_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of `AttributionSpecification` and
   `FactorAttribution` (spec + result only; the engine is reached via `Workspace`).

**No edit to** `backtest/*`, `analytics/*`, `experiment/*`, `report/*`, `diagnostics/*`,
`panel/*`, `market/*`, `universe/*`, `factors/store.py`, or any identity/version module of
a prior phase. **No `as_of` resolution and no corpus read.**

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
wall-clock, no RNG.

### 3.1 `AttributionSpecification` (declarative request)

```
AttributionSpecification(
    name: str,                                     # non-empty
    subject_id: str,                               # non-empty sealed BacktestResult id
    factor_ids: tuple[str, ...],                    # ordered, non-empty, <= K_MAX,
                                                    #   no duplicate, none == subject_id
    risk_free_per_period: str = "0",                # non-negative decimal string (canonicalized)
    periods_per_year: str = "1",                    # strictly-positive decimal string (canonicalized)
    spec_version: str = "attribution/1",
)
```

Construction-time validation (fail closed, `AttributionConfigurationError`): empty `name`;
empty `subject_id`; empty `factor_ids`; more than `K_MAX = 8` factors; an empty factor id;
a factor id equal to `subject_id` (a strategy cannot be a factor explaining itself); a
duplicate factor id (a collinear design by construction); a non-decimal / non-finite /
negative `risk_free_per_period`; a non-decimal / non-finite / non-positive
`periods_per_year`; an empty `spec_version`. The decimal conventions are **canonicalized**
(`Decimal.normalize()` + fixed-point `format`) so `"0.0100"` and `"0.01"` yield the same
id. Reads no store, no wall clock — it cannot know whether the referenced ids exist or
whether the subject has enough periods (those are the engine's fail-closed steps). The
**factor order is semantic** and is preserved exactly (never sorted): it fixes the
design-matrix column order and the coefficient labels, so `(value, size)` and `(size,
value)` are distinct requests with distinct ids. `to_dict()` emits `factor_ids` in
declared order.

### 3.2 Estimation blocks (`AttributionEstimate`, internal)

`attribute_returns(...)` returns an internal `AttributionEstimate`:

```
AttributionEstimate(
    coefficients: tuple[(label, estimate, std_error, t_stat), ...],  # alpha first, then per factor
    diagnostics: tuple[(key, StatValue), ...],                        # sorted by DIAGNOSTIC_KEYS
    decomposition: tuple[(label, StatValue), ...],                    # alpha, then βₖ·mean(xₖ-rf)
    residuals: tuple[str, ...],                                       # engine folds only its digest (D4)
)
```

`StatValue` is the UNDEFINED-preserving cell: `StatValue.known("<decimal string>")` **or**
`StatValue.undefined(<AttributionUndefinedReason>)`. Exactly one of `value` / `reason` is
populated (enforced at construction). Never a bare float, never silently omitted.

### 3.3 `FactorAttribution` (implements `ResearchRecord`)

```
FactorAttribution(
    attribution_engine_version_id: str,
    attribution_spec: dict[str, object],            # the full AttributionSpecification.to_dict()
    subject_ref: tuple[str, str],                   # (backtest_id, result_hash)
    factor_refs: tuple[(label, backtest_id, result_hash), ...],   # ordered, request order
    boundary_kind: str,                             # "pit" (input side; FA-2 — not a PIT value)
    schedule_id: str,                               # the shared rebalance schedule identity
    periods: int,                                   # analysed period count n
    coefficients: tuple[(label, estimate, std_error, t_stat), ...],
    diagnostics: tuple[(key, StatValue), ...],
    decomposition: tuple[(label, StatValue), ...],
    residual_digest: str,                           # sha256 over the residual series (D4)
    risk_free_per_period: str,
    periods_per_year: str,
    dataset_version_ids: tuple[str, ...],           # distinct, sorted fundamentals pins
    market_dataset_version_ids: tuple[str, ...],    # distinct, sorted market pins
    formula_version: str,                           # "attribution-stats/1"
    result_hash: str,                               # canonical JSON over the ordered output cells
)

# derived, never stored as state:
attribution_id      property -> sha256 folding engine version + spec identity
                                + subject & ordered factor result_hashes + result_hash
research_result_id  property -> alias of attribution_id  (the ResearchRecord key)
pin_mismatch        property -> True iff > 1 distinct pin in either dimension (surfaced, never raised)
```

- `to_dict()` keys (deterministic, `sort_keys=True` at the store): `attribution_id`,
  `research_result_id` (alias so the generic reader keys correctly), and every field
  above. A KNOWN cell emits `value` only; an UNDEFINED cell emits `reason` only.
- `from_dict` is the fail-closed inverse; `attribution_id` / `research_result_id` are
  re-derived by their properties, **never read from state**, so `from_dict(to_dict(r))`
  re-emits identical bytes and the same `result_hash`, and a tampered stored id is ignored.
- `.seal(...)` is the identity-computing constructor: it folds the ordered computed-output
  cells (coefficients → diagnostics → decomposition → residual digest, each tagged by its
  block so two structurally different records can never collide) into `result_hash`, so
  identity is a pure function of the request + referenced content + computed answer, never
  caller-supplied.

**What the model deliberately does NOT hold:** any copy of a referenced return vector or
ledger (only `(backtest_id, result_hash)` pointers); the residual series (only its digest,
D4); any float; any wall-clock or RNG value; any `Pit*` type or as-of accessor (FA-2); any
presentation.

### 3.4 Closed v1 vocabulary

`AttributionUndefinedReason` (closed, 4): `SINGULAR_DESIGN`, `INSUFFICIENT_PERIODS`,
`ZERO_VARIANCE`, `ZERO_RESIDUAL_VARIANCE`. `DIAGNOSTIC_KEYS` (closed, sorted, 3):
`adjusted_r_squared`, `r_squared`, `residual_std_error`. Extending either set is an
explicit future edit that hashes distinctly (a new reason/key changes `result_hash`) —
never an implicit fallback.

---

## 4. Formula methods (locked, folded into `attribution-stats/1`)

Changing any of these bumps `ATTRIBUTION_FORMULA_VERSION`, so a value computed under one
method can never be silently reinterpreted under another. All arithmetic runs under an
explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`), never the ambient process
context. `Decimal.sqrt(context)` covers all roots. No float touches any value.

- **Excess-on-excess (open-question 1).** The regressand is `y = subject − rf` and each
  regressor column is `xₖ − rf` (`rf = risk_free_per_period`, subtracted from *both* sides),
  so the intercept is the subject's excess-return alpha net of the factors' excess
  exposures.
- **Design matrix.** `X = [1 | x₁−rf | … | x_K−rf]` (an intercept column plus *K* factor
  excess-return columns), `n` rows.
- **OLS solve.** The normal equations `(XᵀX)β = Xᵀy` are solved via an exact-`Decimal`
  LDLᵀ (Cholesky-family) factorization with an **exact zero-pivot test**: a non-positive
  pivot `D[j] <= 0` means `XᵀX` is not positive-definite (collinear / degenerate factors)
  and the whole coefficient block is `SINGULAR_DESIGN` — never a fabricated coefficient
  (FA-4). No float tolerance enters the test; the pivot is an exact `Decimal`.
- **R² / adjusted R².** `R² = 1 − SSR/SST` where `SST = Σ(yᵢ − ȳ)²` and `SSR = Σeᵢ²`;
  `adjusted R² = 1 − (1 − R²)·(n − 1)/(n − K − 1)`. `SST = 0` (a constant regressand) →
  both are `ZERO_VARIANCE`, never a divide-by-zero. The engine guarantees `n − K − 1 ≥ 1`,
  so the adjustment never divides by zero.
- **Residual variance / standard error.** `sigma_sq = SSR/(n − K − 1)`; residual standard
  error `= √sigma_sq`.
- **Coefficient standard errors / t-stats.** Coefficient covariance is `sigma_sq·(XᵀX)⁻¹`
  (D5, classical); each coefficient's standard error is `√(sigma_sq·(XᵀX)⁻¹ᵢᵢ)` (the
  diagonal of the inverse is obtained by one LDLᵀ solve per unit vector) and its
  t-statistic is `estimate / std_error`. At a **perfect in-sample fit** (`sigma_sq == 0`)
  the standard errors and t-statistics are `ZERO_RESIDUAL_VARIANCE` — the estimate itself
  stays KNOWN — never a division by a zero standard error.
- **Sample mean-excess decomposition.** The intercept contributes `alpha` and factor `k`
  contributes `βₖ · mean(xₖ − rf)`; they sum to the subject's mean excess return (the OLS
  residual mean is zero under an intercept).
- **Singular design.** When the factorization fails, every coefficient cell (estimate, std
  error, t-stat), every diagnostic, and every decomposition contribution is
  `UNDEFINED(SINGULAR_DESIGN)`, and the residual series is **empty** (there is no fitted
  model) — so its digest is the stable digest of the empty series, distinct from any real
  residual set.

---

## 5. Identity / determinism (locked)

- Domain tags via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): record tag `attribution/1`;
  engine tag `attribution-engine/1`; formula tag `attribution-stats/1`.
- `attribution_engine_version_id = sha256(code_version "attribution-engine/1",
  config_hash)` where `config_hash =
  sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=attribution-stats/1")`. Any change to
  the decimal context **or** a formula method yields a new engine id.
- `attribution_result_hash = sha256(canonical JSON over the ordered computed-output cells:
  coefficients, then diagnostics, then decomposition, then the residual-digest cell — each
  tagged by its block)`. Sensitive to every computed cell and to the residual digest.
- `residual_digest = sha256(canonical JSON over the ordered residual decimal strings)`.
- `attribution_id = sha256`, NUL-joined: `attribution/1`,
  `attribution_engine_version_id`, `name`, `spec_version`, `subject_id`, canonical-JSON of
  the **ordered** `factor_ids`, `risk_free_per_period`, `periods_per_year`, the subject
  `result_hash`, canonical-JSON of the **ordered** factor `result_hash`es, and
  `attribution_result_hash`.
- `research_result_id` aliases `attribution_id` (single id, D2).

**Folds (changes identity):** engine-logic + formula + decimal-context version ✔, the full
declared request (name, spec version, subject id, ordered factor ids, both convention
values) ✔, every referenced `result_hash` (subject + ordered factors — a changed corpus
changes a referenced `result_hash`, hence the id; FA-1) ✔, the computed statistics + the
residual digest (via `result_hash`) ✔. **Does NOT fold:** the record schema/format version
(`ATTRIBUTION_RESULT_FORMAT_VERSION` — a container concern), any presentation, wall-clock,
RNG, `id()`, or iteration order (the carried corpus-pin tuples are sorted). The factor
lists are folded in **request order**, never sorted.

Same request + same sealed inputs → same `attribution_id` and same bytes on any machine.

---

## 6. PIT semantics, provenance, storage (locked)

- **No look-ahead is possible.** Phase 17 performs **no `as_of` resolution and no corpus
  read**. Every input is a sealed `period_returns` series a Phase 12 PIT walk already
  produced under the no-look-ahead guarantee (BT-2). Attribution introduces no new temporal
  decision.
- **The output is ex-post, not PIT (FA-2).** A regression of realized returns is an ex-post
  research statistic. `FactorAttribution` is **not** a `Pit*` type, exposes **no** as-of
  accessor, and is inadmissible where a PIT signal/value is required — the exact analogue of
  invariant 28 / SD-2. `boundary_kind = "pit"` documents only that the *underlying
  backtests were PIT walks* (the input side); it does not claim the attribution itself is a
  PIT value.
- **Reference + drift verification.** For the subject and every factor the engine reads the
  record from the sidecar, asserts its `research_result_id` equals the requested id, and
  **recomputes** its `result_hash` from its ledger `outcome_digest`s, comparing to the
  sealed value — a tampered or replaced upstream record can never be silently analysed
  (`AttributionConsistencyError`).
- **Commensurability (FA-3).** Every factor must share the subject's exact `schedule_id`,
  an equal `period_returns` length, and the same `backtest_engine_version_id`; any mismatch
  fails closed. Returns are never padded, truncated, or realigned.
- **Corpus pins (FA-1).** The distinct `dataset_version_id`s and
  `market_dataset_version_id`s observed across the subject and factors are carried on the
  record (as sorted tuples) and folded into `attribution_id` via each referenced
  `result_hash`. A subject/factor disagreement is **surfaced** as `pin_mismatch` (more than
  one distinct pin in either dimension), never raised — a record may legitimately regress a
  strategy against factors run over a different corpus snapshot, but a reader must be able
  to see it.
- **Provenance.** The record retains `(backtest_id, result_hash)` for the subject and each
  factor (in request order), the shared `schedule_id`, the period count `n`, both
  convention values, and the carried corpus pins. It stores **no copy** of any referenced
  return vector or ledger — only pointers and content hashes (the Phase 14/15
  reference-only discipline).
- **Storage.** Zero new store types; the `ResearchResultStore` writes the record to
  `<root>/research/sha256-<hex>.json` in the existing container. Write-once and idempotent:
  re-computing an identical attribution is a byte-identical no-op; a differing payload under
  an existing id fails closed via the store's guard.

---

## 7. Failure / UNDEFINED behavior (locked)

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`AttributionConfigurationError` / `AttributionConsistencyError`):
- Malformed spec: empty `name` / `subject_id` / `spec_version`; empty / too-many (`>
  K_MAX`) / empty-element / duplicate / self-referencing `factor_ids`; non-decimal /
  negative `risk_free_per_period`; non-decimal / non-positive `periods_per_year`.
  *(configuration, at construction)*
- A non-`AttributionSpecification` argument to `attribute`. *(configuration)*
- **Insufficient periods:** `n < K + 2` (K loadings + intercept + ≥ 1 residual df) — raised
  rather than sealing a record with no residual degrees of freedom (the Phase 15
  `_MIN_PERIODS` precedent). *(configuration)*
- A referenced backtest absent from the sidecar, whose stored id disagrees with the
  request, or whose recomputed `result_hash` drifted. *(consistency)*
- An incommensurable factor (different `schedule_id`, unequal return length, different
  `backtest_engine_version_id`). *(consistency, FA-3)*
- A corrupt / non-finite decimal in a referenced `period_returns`. *(raised, never guessed)*

**Recorded as first-class UNDEFINED (never raised, never fabricated — FA-4):** a
singular/collinear design → the whole coefficient / diagnostic / decomposition block is
`SINGULAR_DESIGN` (no factor silently dropped, no coefficient fabricated). A zero-variance
regressand → `ZERO_VARIANCE` R² / adjusted R². A perfect in-sample fit → the coefficient
standard errors and t-statistics are `ZERO_RESIDUAL_VARIANCE` (the estimate stays KNOWN).
`INSUFFICIENT_PERIODS` guards any per-cell degenerate residual-df case (the engine fails
closed before computing below `n ≥ K + 2`). There is no divide-by-zero anywhere: a zero
denominator becomes a recorded UNDEFINED, exactly as Phase 7 metrics / Phase 15 analytics /
Phase 16 diagnostics do.

---

## 8. Public API (locked)

```python
from quantforge import Workspace, AttributionSpecification, FactorAttribution

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
)  # sealed, write-once FactorAttribution

attribution.coefficients  # ordered (label, estimate, std_error, t_stat) — alpha + per factor
attribution.diagnostics  # (key, StatValue): adjusted_r_squared, r_squared, residual_std_error
attribution.decomposition  # (label, StatValue): alpha + per-factor mean-excess contribution
attribution.research_result_id  # == attribution.attribution_id (ResearchRecord)
attribution.pin_mismatch  # surfaced flag, never raised

# typed read-back (byte-identical round-trip)
again = ws.research_result_store.read_as(
    attribution.research_result_id, FactorAttribution.from_dict
)
```

`AttributionEngine` is reached only through `Workspace.attribution_engine` (a lazy,
cached, cycle-free `@property` annotated `-> object`; engines are not re-exported at top
level). `attribute(spec) -> FactorAttribution` is the single entry point. No `Company`
method is added (attribution spans a subject + K factors, not one filer).

---

## 9. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 17 suite added), deterministic across runs.
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src tests`
  clean (strict).
- Zero runtime dependencies (stdlib `hashlib` / `json` / `dataclasses` / `Decimal` only);
  no float in any path; no wall-clock/RNG in any identity or value; the OLS solve is an
  exact-`Decimal` LDLᵀ factorization (no linear-algebra dependency, no numpy).
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** — the only source edits are the additive
  `Workspace.attribution_engine` property/cache line and the `__init__.py` re-exports; no
  edit to any identity/version module or to `backtest/*`, `analytics/*`, `diagnostics/*`,
  `panel/*`, `market/*`, or `universe/*`.
- Byte-identical `FactorAttribution` round-trip test proves `from_dict` introduces no drift
  and a tampered stored id is ignored; a determinism double-build proves `to_dict()`
  byte-equality and id sensitivity to each input.
- FA-1 (referenced `result_hash` folded; changed corpus → different id; pin difference
  surfaced not raised), FA-2 (no `Pit*` type / no as-of accessor), FA-3 (incommensurable
  factor fails closed), FA-4 (UNDEFINED-preserving estimation) each covered by a test.
- Docs updated; `ARCHITECTURE.md` "Multi-factor attribution" row flipped to ✅ and
  `README.md` advanced to `v0.14.0` only when green.

---

## 10. Test coverage (locked)

New package `tests/attribution/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_stats.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline over the
fictional CIKs reused from `tests/backtest/builders`, covering:

- **Construction validation** — every fail-closed spec path (empty fields, `K_MAX`
  ceiling, self / duplicate / empty factor ids, convention validation and
  canonicalization), the order-preserving canonical payload (SPEC).
- **Exact-`Decimal` OLS numerics** against hand-computed reference values — single-factor
  perfect line (alpha/beta recovery), two-factor exact plane, excess-on-excess, a noisy
  hand-computed case (`beta = 2.2`, `alpha = 2.6`), t = estimate/std_error, adjusted ≤ R²,
  decomposition sums to mean excess, and the fail-closed reasons (collinear / constant →
  `SINGULAR_DESIGN`, zero-variance regressand → `ZERO_VARIANCE`, perfect fit →
  `ZERO_RESIDUAL_VARIANCE`) with UNDEFINED preservation (STATS).
- `attribution_id` folding + sensitivity to each input (engine version, name, subject id,
  either convention, factor order, either referenced content hash, computed answer);
  `residual_digest` / `attribution_result_hash` determinism + sensitivity; the empty
  residual series has a stable distinct digest (IDENTITY).
- Byte-identical `to_dict` / `from_dict`, derived-id survival, UNDEFINED-cell round-trip,
  pin-mismatch surfacing, and the FA-2 boundary (not a `Pit*` type, no as-of accessor)
  (RESULT).
- End-to-end single-factor and multi-factor attribution over sealed backtests; factor
  order yields a distinct record; fail-closed on absent subject/factor, too-short subject,
  incommensurable schedule, non-spec argument, and drifted factor (rewritten stored
  `result_hash`); write-once idempotent rebuild; reproducibility across independent
  workspaces; workspace wiring (cached, shares sidecar); not-PIT boundary (ENGINE).

No real financial or network data; the architecture does not require it.
