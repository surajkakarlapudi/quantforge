# Phase 20 — Factor Risk Model (Factor Covariance & Correlation Estimation) (LOCKED)

> **Status:** Locked normative specification. Decisions **D-SCOPE, D-INPUT, D-NAME,
> D-ALIGN, D-MOMENT, D-STORE, D-CORR, D-COMMENSURABLE, D-PIN, D-NMAX, D-UNDEFINED,
> D-INVARIANTS, D-VERSION** were approved as recommended; this document is the source of
> truth for the implementation and supersedes the recommendations in
> [phase20-factor-risk-model-proposal.md](phase20-factor-risk-model-proposal.md). Every
> conditional reference in the proposal ("recommended", "approval needed") is resolved
> here to a committed decision.
>
> **One-line thesis:** Phase 20 adds a deterministic, content-addressed **factor risk
> model** — the first member of a new **risk-modelling** capability class, a pure
> consumer strictly *above* the Phase 19 factor-portfolio-construction layer (as Phase 15
> analytics consumes Phase 12 backtests). Given a declarative `FactorRiskSpecification`
> naming an **ordered** set of *N* sealed `FactorPortfolio` records (each a factor whose
> KNOWN `(as_of, factor_return)` series is a covariance input) plus an annualization
> convention, `FactorRiskEngine.estimate(...)` resolves each referenced factor from the
> shared Phase 8 research sidecar, re-verifies it, enforces that all *N* share one
> `schedule_id` and one `factor_portfolio_engine_version_id`, aligns their KNOWN return
> series on a **complete-case** common time axis, and estimates the second-moment
> structure under the pinned `Decimal` context: the per-factor mean and **population**
> volatility vectors, the `N x N` population **covariance** matrix, and the companion
> **correlation** matrix (per-period and annualized where applicable, stored as the
> **upper triangle** only). It seals a `FactorRiskModel` `ResearchRecord` write-once to
> the existing Phase 8 sidecar under the same pinned context. It composes Phase 19 only,
> consumes **no** `BacktestResult` and is not one, introduces **no** new data source,
> **no** new store, **no** runtime dependency, **no** new PIT surface, and **no**
> database.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **Estimate the second-moment structure of an ordered set of *N* factor return series:** the per-factor mean + population volatility vectors, the `N x N` population covariance matrix, and the companion correlation matrix (per-period and annualized). No optimizer, no shrinkage/factor-model estimator, no expected-return model, no rolling/windowed estimate — those are reserved for later, explicitly-labelled phases (§9). |
| **D-INPUT** | **A new pure-consumer sibling layer strictly *above* Phase 19** (the analogue of Phase 15/17 consuming Phase 12). It resolves already-sealed `FactorPortfolio` records from the shared research sidecar; it consumes **no** `BacktestResult` and produces none, reads **no** raw corpus and re-derives nothing from source, and **modifies no** prior-phase vocabulary, engine, or identity. |
| **D-NAME** | **Package `factorrisk`.** Public types `FactorRiskSpecification`, `FactorRiskModel`; engine `FactorRiskEngine` (reached via `Workspace`, not re-exported). The domain tag is `factorrisk/1`; the engine-version string is `factorrisk-engine/1`; the formula-method string is `factorrisk-stats/1`; the record-format string is `factorrisk-result/1`. These are baked into every `factor_risk_id`; changing them later is a breaking identity change. |
| **D-ALIGN** | **Complete-case alignment.** The estimation window is the intersection of the `as_of` instants where **every** factor carries a KNOWN return, in shared ascending date order; a date where any factor is UNDEFINED is excluded (never filled, interpolated, or zero-imputed). `M` is that window's length. A minimum common window of `_MIN_PERIODS = 2` is required — fewer raises `FactorRiskConfigurationError` (FR-4). |
| **D-MOMENT** | **Population moments (÷M), not sample (÷M−1).** `mean_i = (1/M)Σ f_{i,t}`; `vol_i = √((1/M)Σ(f_{i,t}−mean_i)²)`; `cov(i,j) = (1/M)Σ(f_{i,t}−mean_i)(f_{j,t}−mean_j)`. A covariance/correlation matrix is internally consistent only when every second moment shares one divisor, and the population divisor makes a positive-variance factor's self-correlation exactly `1`. Pinned in `factorrisk-stats/1`. |
| **D-STORE** | **Upper-triangle storage** (`i <= j`) for both the covariance and the correlation matrix; the lower triangle is implied by symmetry and never stored (D-TRIANGLE). The diagonal `cov(i,i)` is the factor's own population variance, recomputed from the sum of squared deviations (never squared back from the rounded volatility). |
| **D-CORR** | **`corr(i,j) = cov(i,j)/(vol_i·vol_j)`.** When either factor's volatility over the common window is exactly `0` the denominator is zero, so the correlation cell is a first-class `UNDEFINED` `ZERO_VARIANCE` — including its own diagonal (`0/0`) — never a divide-by-zero, `0`, `NaN`, or `Inf`. A positive-variance factor's diagonal correlation is a KNOWN exact `1`. |
| **D-COMMENSURABLE** | **Strict comparability, fail closed.** Every referenced factor must share one exact `schedule_id` **and** one `factor_portfolio_engine_version_id` (their return series must align on a common rebalance calendar and be produced by one engine logic — the Phase 13/15/17 precedent). A difference is raised (`FactorRiskConsistencyError`); mismatched series are never silently aligned. |
| **D-PIN** | **Corpus pins are carried and surfaced, never reconciled.** The distinct fundamentals `dataset_version_id`s and market `market_dataset_version_id`s across the referenced factors are carried (sorted, deduped); more than one distinct pin in either dimension sets `pin_mismatch = True` (surfaced, never raised — the `FactorAttribution.pin_mismatch` convention). A model may legitimately span factors run over different corpus snapshots, but a reader must see it. |
| **D-NMAX** | **`N_MAX = 16` factors; `_MIN_FACTORS = 2`.** A covariance needs at least a pair (a single-factor "matrix" is just that factor's variance); capping *N* keeps the `N x N` exact-`Decimal` estimate bounded and interpretable. Exceeding it is a configuration defect, raised — never silently truncated. |
| **D-UNDEFINED** | **One UNDEFINED reason:** `ZERO_VARIANCE`, on a correlation cell whose factor has zero volatility over the common window. Means, volatilities (KNOWN even at exactly `0`), and every covariance cell (a zero covariance is a real number) stay KNOWN. Fewer than `_MIN_PERIODS` common dates is a **raised** configuration defect, never a sealed all-UNDEFINED record (the Phase 15 `_MIN_PERIODS` / Phase 16 `_MIN_PAIRS` / Phase 18 `_MIN_VALID_DATES` / Phase 19 `_MIN_VALID_PERIODS` precedent). |
| **D-INVARIANTS** | **FR-1..FR-5 are documented both as phase-local invariants here and as a small additive `data-model.md §12` block** mirroring the SD-1..4 / XS-1..4 / P19-1..5 blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.17.0`** (Phase 19 = v0.16.0, confirmed by git tags). The package `__version__` string is unchanged (versioning is by content-addressed ids, not a semver string). Any pre-existing README version-label drift is **not** fixed here. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; none changes an identity discipline or weakens an invariant.

1. **`name` and `spec_version` are not stored as separate top-level `FactorRiskModel`
   fields.** The proposal §9.2 sketch listed them alongside the other fields; the
   implementation reads them from the embedded `factor_risk_spec` dict (via the private
   `_spec_str` helper) inside the `factor_risk_id` property. This avoids storing the same
   value twice and any drift between the two copies. The identity fold is unchanged — the
   `name` and `spec_version` components of `factor_risk_id` are exactly the spec's own.
2. **The pure compute type is `MomentEstimate` (in `stats.py`).** `estimate_moments(...)`
   returns a `MomentEstimate` (`factors`, `covariance`, `correlation`); the engine copies
   its blocks straight into `FactorRiskModel.seal(...)`. The split keeps the pure compute
   layer free of the record/store vocabulary; the sealed shape and identity fold are
   exactly as proposed.
3. **Version constants are split across `version.py` and `result.py`.**
   `FACTORRISK_SPEC_VERSION` / `FACTORRISK_ENGINE_VERSION` / `FACTORRISK_FORMULA_VERSION`
   live in `version.py`; `FACTORRISK_RESULT_FORMAT_VERSION` lives in `result.py` (beside
   the record it versions). No value or fold changes.
4. **`errors.py` defines the two-error hierarchy as proposed**
   (`FactorRiskError → FactorRiskConfigurationError, FactorRiskConsistencyError`).

---

## 2. Architecture (locked)

Phase 20 is a thin factor-risk-modelling layer *above* Phase 19, structurally the
**pure-consumer sibling of Phase 15 / Phase 17** (which consume sealed `BacktestResult`s)
— the correct precedent because Phase 20, like attribution, references **sealed
artifacts** (the *N* `FactorPortfolio` records) by their `result_hash`, rather than
reading the raw corpora. It follows the extension recipe every prior phase uses: a
versioned immutable request object → a fail-closed engine reached from `Workspace` via a
lazy, cycle-free `@property` → a distinct result type → content-addressed identity with
fresh domain tags → data conditions recorded as first-class values, defects raised →
compute-on-demand with the shared write-once sidecar. Unlike Phase 19 (which references
the raw corpora by their corpus pins), Phase 20 folds each referenced factor's sealed
`result_hash` into the model's identity, so the id is **transitively** sensitive to any
change in any referenced factor without re-reading a corpus (FR-1).

```
                 FactorRiskSpecification    (declarative request, content-addressed)
                          |
                          v
   Workspace.factor_risk_engine  --->  FactorRiskEngine.estimate(spec)
                          |                 |
                          |   resolve each factor_portfolio_id from the shared sidecar   — fail closed
                          |     store.read_as(id, FactorPortfolio.from_dict)
                          |     verify each resolved record.research_result_id == requested id (FR-1)
                          |     (no content->hash recompute; each factor's result_hash is FOLDED, FR-1)
                          |
                          |   verify commensurability (FR-3)                              — fail closed
                          |     one shared schedule_id AND one factor_portfolio_engine_version_id
                          |     (corpus pin_mismatch is SURFACED on the record, never raised — D-PIN)
                          |
                          |   complete-case alignment (FR-4):
                          |     common dates = intersection of as_of where EVERY factor is KNOWN
                          |     M = len(common dates), ascending; require M >= 2           — fail closed
                          |     series[i] = factor i's KNOWN returns on the common axis
                          |
                          |   estimate under the pinned Decimal context (prec 34, HALF_EVEN):
                          |     mean_i, population vol_i (via Decimal.sqrt)
                          |     upper-triangle cov(i,j) = (1/M)Σ(f_i-mean_i)(f_j-mean_j)   (i <= j)
                          |     upper-triangle corr(i,j) = cov/(vol_i*vol_j)               (i <= j)
                          |       vol_i == 0 or vol_j == 0 -> UNDEFINED ZERO_VARIANCE       (never /0)
                          |     annualized: vol*√ppy, cov*ppy
                          v                 v
             FactorRiskModel (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
             store.read_as(id, FactorRiskModel.from_dict)  (typed, byte-identical round-trip)
```

**New package `src/quantforge/factorrisk/`** (mirrors `attribution/` / `factorportfolio/`):

- `errors.py` — `FactorRiskError` → `FactorRiskConfigurationError`,
  `FactorRiskConsistencyError`.
- `version.py` — `FactorRiskEngineVersion` (folds the pinned decimal context **and** the
  formula-method version `factorrisk-stats/1` into `config_hash`);
  `FACTORRISK_ENGINE_VERSION = "factorrisk-engine/1"`,
  `FACTORRISK_FORMULA_VERSION = "factorrisk-stats/1"`,
  `FACTORRISK_SPEC_VERSION = "factorrisk/1"`; `default_decimal_context()`. The id property
  is `factor_risk_engine_version_id`. (The engine-version id is **not** re-implemented in
  `identity.py` — one source of truth.)
- `identity.py` — `factor_risk_result_hash`, `factor_risk_id`. Fresh record domain tag
  `factorrisk/1`.
- `model.py` — `FactorRiskStatus` / `FactorRiskUndefinedReason` vocabulary; `StatValue` (a
  KNOWN decimal string **or** UNDEFINED+reason); `factor_label`; the nested records
  `FactorMoment`, `CovarianceCell`, `CorrelationCell`, `FactorCoverage`, `CoverageSummary`.
- `spec.py` — `FactorRiskSpecification`, full construction-time validation; `N_MAX`.
- `stats.py` — the pure second-moment estimator (`estimate_moments`, `MomentEstimate`).
  Pure; reads no store; takes decimal-string vectors, returns KNOWN / UNDEFINED cells
  under the pinned context.
- `result.py` — `FACTORRISK_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, `FactorRiskModel` (a
  `ResearchRecord` with `.seal` / `to_dict` / `from_dict`).
- `engine.py` — `FactorRiskEngine` (constructed from `Workspace`; reuses the workspace's
  shared Phase 8 research sidecar): resolve + verify each factor → verify commensurability
  → complete-case align → estimate → seal → write-once.
- `__init__.py` — package exports (`FactorRiskSpecification`, `FactorRiskModel`, the cells,
  errors, version, identity helpers).

**Edits to existing source** (all additive; none altering any existing identity):

1. `workspace.py` — one lazy `factor_risk_engine` `@property` (+ its
   `self._factor_risk_engine: object | None = None` cache line), following the
   `factor_portfolio_engine` / `attribution_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of `FactorRiskSpecification` and
   `FactorRiskModel` (spec + result only; the engine is reached via `Workspace`).
3. `tests/test_smoke.py` — one additive public-API export assertion.

**No edit to** `backtest/*`, `analytics/*`, `attribution/*`, `crosssection/*`,
`experiment/*`, `report/*`, `diagnostics/*`, `factorportfolio/*`, `panel/*`, `market/*`,
`universe/*`, `factors/store.py`, `_linalg`, or any identity/version module of a prior
phase. **No new PIT resolution, no new store, no new data source, and no OLS** (Phase 20
does closed-form population second moments only; it promotes no shared helper).

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
wall-clock, no RNG.

### 3.1 `FactorRiskSpecification` (declarative request)

```
FactorRiskSpecification(
    name: str,                               # non-empty
    factor_portfolio_ids: tuple[str, ...],   # ORDERED; 2..N_MAX; non-empty, no duplicate
    periods_per_year: str = "1",             # canonicalized positive finite decimal; folded into identity
    spec_version: str = "factorrisk/1",
)
```

Construction-time validation (fail closed, `FactorRiskConfigurationError`): an empty
`name` / `spec_version`; a `factor_portfolio_ids` that is not a `tuple`, has fewer than
`_MIN_FACTORS = 2` or more than `N_MAX = 16` entries, or contains an empty or duplicate
id; a non-decimal, non-finite, or non-positive `periods_per_year` (canonicalized in place
via `str(+Decimal(...))` so two spellings of the same number yield one id — e.g.
`"012"` → `"12"`, `"1.2E1"` → `"12"`). It reads no store and no wall clock — it cannot
know whether the referenced ids exist (that is the engine's fail-closed resolution step),
whether the factors are commensurable, or whether the common window is long enough (those
need the resolved series); it validates only the request's internal shape. **Factor order
is semantic** and preserved exactly (never sorted): it fixes the matrix row/column order
and the `factor_1..factor_N` labels, so `(A, B)` and `(B, A)` are distinct requests with
distinct ids. `to_dict()` emits `{spec_version, name, factor_portfolio_ids (in declared
order), periods_per_year}`, embedded in the sealed record.

### 3.2 Second-moment compute block (`stats.py`, internal)

`estimate_moments(series, *, periods_per_year, context)` takes the complete-case-aligned
matrix — an ordered list of *N* factor return series, each a list of the **same** `M`
already-canonical decimal strings, in shared date order — and returns a `MomentEstimate`:

```
MomentEstimate(
    factors: tuple[FactorMoment, ...],        # per-factor mean + population vol + annualized vol
    covariance: tuple[CovarianceCell, ...],   # upper triangle (i <= j), per-period + annualized
    correlation: tuple[CorrelationCell, ...], # upper triangle (i <= j)
)
```

It fails closed (`FactorRiskConsistencyError`) on `n < 2`, `m < 2`, a ragged matrix, or a
non-decimal / non-finite cell. `StatValue` is the UNDEFINED-preserving cell:
`StatValue.known("<decimal string>")` **or**
`StatValue.undefined(FactorRiskUndefinedReason.ZERO_VARIANCE)`; exactly one of `value` /
`reason` is populated (enforced at construction). Never a bare float, never silently
omitted.

### 3.3 `FactorRiskModel` (implements `ResearchRecord`)

```
FactorRiskModel(
    factor_risk_engine_version_id: str,
    factor_risk_spec: dict[str, object],              # the full FactorRiskSpecification.to_dict()
    factor_refs: tuple[tuple[str, str, str], ...],    # ordered (label, factor_portfolio_id, result_hash)
    boundary_kind: str,                               # "pit" (documents the INPUT side; FR-2 — not a PIT value)
    schedule_id: str,                                 # the one shared rebalance-schedule identity
    factor_portfolio_engine_version_id: str,          # the one shared producing-engine version
    periods: int,                                     # M, the analysed common-window length
    periods_per_year: str,
    factors: tuple[FactorMoment, ...],                # per-factor moment records (factor order)
    covariance: tuple[CovarianceCell, ...],           # upper triangle (i <= j)
    correlation: tuple[CorrelationCell, ...],         # upper triangle (i <= j)
    coverage: CoverageSummary,                        # audit metadata; NOT folded
    dataset_version_ids: tuple[str, ...],             # carried fundamentals pins (sorted, deduped)
    market_dataset_version_ids: tuple[str, ...],      # carried market pins (sorted, deduped)
    formula_version: str,                             # "factorrisk-stats/1"
    result_hash: str,                                 # canonical JSON over the ordered output cells
)

# derived, never stored as state:
factor_risk_id       property -> sha256 folding engine version + spec identity (name,
                                 spec_version from the embedded spec) + ordered factor ids
                                 + periods_per_year + ordered factor result_hashes + result_hash
research_result_id   property -> alias of factor_risk_id  (the ResearchRecord key)
factor_portfolio_ids property -> the referenced ids in request order (matrix row/column order)
pin_mismatch         property -> True iff either carried-pin tuple has length > 1
```

- `FactorMoment(label, mean, volatility, annualized_volatility)` — one factor's first- and
  second-moment scalars; `label` the name-free `factor_label` (`factor_1`, `factor_2`,
  …). Each moment a `StatValue`, KNOWN over a valid window (volatilities KNOWN even at
  exactly `0`).
- `CovarianceCell(i, j, value, annualized)` — one upper-triangle covariance entry
  (`i <= j`); `value` the per-period population covariance, `annualized` the
  `value·periods_per_year` scaling. Both cells KNOWN over a valid window.
- `CorrelationCell(i, j, value)` — one upper-triangle correlation entry; `value` is
  `cov(i,j)/(vol_i·vol_j)`, UNDEFINED `ZERO_VARIANCE` when either factor's volatility is
  exactly `0`, else KNOWN (the positive-variance diagonal is exactly `1`).
- `FactorCoverage(label, factor_portfolio_id, available, used)` — per-factor coverage:
  `available` the number of KNOWN per-period returns the input carried, `used` the number
  that survived complete-case alignment (equal for every factor — the common `M` — but
  stored per factor so a reader sees each factor's contribution vs the alignment).
- `CoverageSummary(per_factor, aligned_periods, dropped_for_alignment)` — the aligned
  window size `M` and the total KNOWN returns that fell outside the common window
  (`Σ available − N·M`). Audit metadata; **not** folded into `result_hash`.
- `to_dict()` keys include `factor_risk_id`, `research_result_id` (alias so the generic
  reader keys correctly), and every field above; `factor_refs` serialize as
  `{"label": …, "ref": [id, result_hash]}`. A KNOWN cell emits `value` only; an UNDEFINED
  cell emits `reason` only.
- `from_dict` is the fail-closed inverse; `factor_risk_id` / `research_result_id` are
  re-derived by their properties, **never read from state**, so `from_dict(to_dict(r))`
  re-emits identical bytes and the same `result_hash`, and a tampered stored id is
  ignored. A malformed cell (unknown status, missing value/reason, unrecognized reason) is
  refused with a `ValueError`.
- `.seal(...)` is the identity-computing constructor: it folds the ordered computed-output
  cells (the per-factor moment cells in factor order, then the upper-triangle covariance
  cells, then the upper-triangle correlation cells, each tagged by its block so two
  structurally different records can never collide) into `result_hash`, so identity is a
  pure function of the request + referenced content + computed answer, never
  caller-supplied. **The coverage summary is audit metadata and is NOT folded into
  `result_hash`** (§5) — it is fully determined by the same inputs, so it never
  desynchronizes.

**What the model deliberately does NOT hold:** any copy of a factor's return series (only
pointers `(label, factor_portfolio_id, result_hash)` and the derived moments); any float;
any wall-clock or RNG value; any `Pit*` type or as-of accessor (FR-2); the lower matrix
triangle (implied by symmetry); any presentation.

### 3.4 Closed v1 vocabulary

`FactorRiskUndefinedReason` (closed, 1): `ZERO_VARIANCE`. `FactorRiskStatus` (2): `KNOWN`,
`UNDEFINED`. Extending the reason set is an explicit future edit that hashes distinctly (a
new reason changes `result_hash`) — never an implicit fallback.

---

## 4. Formula methods (locked, folded into `factorrisk-stats/1`)

Changing any of these bumps `FACTORRISK_FORMULA_VERSION`, so a value computed under one
method can never be silently reinterpreted under another. All arithmetic runs under an
explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`), never the ambient process
context. `Decimal.sqrt(context)` covers all roots. No float touches any value.

- **Per-factor mean (D-MOMENT).** `mean_i = (1/M) Σ_t f_{i,t}` over the `M` complete-case
  common dates.
- **Per-factor population volatility (D-MOMENT).**
  `vol_i = √( (1/M) Σ_t (f_{i,t} − mean_i)² )` (via `Decimal.sqrt` under the pinned
  context — the Phase 12/19 precedent). Population (÷M), not sample (÷M−1). KNOWN even at
  exactly `0`.
- **Population covariance (D-MOMENT / D-STORE).**
  `cov(i,j) = (1/M) Σ_t (f_{i,t} − mean_i)(f_{j,t} − mean_j)`, symmetric, so only the upper
  triangle (`i <= j`) is computed; the diagonal `cov(i,i)` is the factor's own population
  variance, recomputed from the sum of squared deviations (not squared back from the
  rounded volatility).
- **Correlation (D-CORR).** `corr(i,j) = cov(i,j) / (vol_i · vol_j)`. When either `vol_i`
  or `vol_j` is exactly `0` the correlation is UNDEFINED `ZERO_VARIANCE` (never a
  divide-by-zero); otherwise KNOWN, and the diagonal `corr(i,i)` of a positive-variance
  factor is exactly `1` (`cov(i,i)` and `vol_i²` are the identical sum-of-squares
  expression under the pinned context).
- **Annualization (D-MOMENT).** `annualized_vol_i = vol_i · √periods_per_year` and
  `annualized_cov(i,j) = cov(i,j) · periods_per_year` (variances/covariances scale linearly
  in time, volatilities by the square root — the Phase 12/19 convention). Correlation is
  scale-free and carries no annualized companion.
- **Degeneracy (never a divide-by-zero).** A zero-volatility factor's mean, its (zero)
  volatility, and every covariance cell involving it stay KNOWN (a zero covariance is a real
  number); only the correlation cells that would divide by the zero volatility are UNDEFINED
  `ZERO_VARIANCE`. A common window shorter than `_MIN_PERIODS = 2` is a **raised**
  configuration defect, not a sealed record.

---

## 5. Identity / determinism (locked)

- Domain tags via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): record tag `factorrisk/1`;
  engine tag `factorrisk-engine/1`; formula tag `factorrisk-stats/1`.
- `factor_risk_engine_version_id = sha256(code_version "factorrisk-engine/1", config_hash)`
  where `config_hash =
  sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=factorrisk-stats/1")`. Any change to
  the decimal context **or** a formula method yields a new engine id.
- `factor_risk_result_hash = sha256(canonical JSON over the ordered computed-output cells:
  the per-factor moment cells in factor order — each `{"block":"factor", label, mean,
  volatility, annualized_volatility}` — then the upper-triangle covariance cells (`i <= j`)
  — each `{"block":"cov", i, j, value, annualized}` — then the upper-triangle correlation
  cells (`i <= j`) — each `{"block":"corr", i, j, value}`)`. Sensitive to every computed
  statistic: one differing cell changes it. The coverage summary is **not** folded.
- `factor_risk_id = sha256`, NUL-joined, in this exact order: `factorrisk/1`,
  `factor_risk_engine_version_id`, `name`, `spec_version`, the ORDERED
  `factor_portfolio_id` list (canonical JSON), `periods_per_year`, the ORDERED factor
  `result_hash` list (canonical JSON), and `factor_risk_result_hash`.
- `research_result_id` aliases `factor_risk_id` (a single id). Both factor lists are folded
  in **request order** (not sorted): order is semantic — it fixes the matrix row/column
  order and the `factor_1..factor_N` labels — so `(A, B)` and `(B, A)` are distinct ids.

**Folds (changes identity):** the engine-logic + formula + decimal-context version ✔; the
declared request (name, spec version, the ordered factor id list, the annualization
convention `periods_per_year`) ✔; the **referenced content** — each factor's `result_hash`
in request order, so the id is **transitively** sensitive to any change in any referenced
factor (FR-1) ✔; the computed statistics (via `result_hash`) ✔. **Does NOT fold:** the
record schema/format version (`FACTORRISK_RESULT_FORMAT_VERSION` — a container concern);
the coverage summary (audit metadata); the carried corpus pins (surfaced via
`pin_mismatch`, not folded); any presentation, wall-clock, RNG, `id()`, or iteration order
(the matrix cells preserve upper-triangle order; the carried corpus-pin component sets are
sorted).

Same request + same sealed inputs → same `factor_risk_id` and same bytes on any machine.

---

## 6. PIT semantics, provenance, storage (locked)

- **The output is ex-post, not PIT (FR-2).** A covariance/correlation matrix of realized
  factor returns is an ex-post research statistic, not a forward-usable PIT value.
  `FactorRiskModel` is **not** a `Pit*` type, exposes **no** as-of accessor, and is
  inadmissible where a PIT signal/value is required — the exact analogue of invariant 28 /
  SD-2 / XS-2 / P19-2. `boundary_kind = "pit"` documents only that the *underlying factor
  portfolios were PIT walks* (their signal side was PIT-eligible); it does not claim the
  matrix is a PIT value. The engine sets it unconditionally (a `FactorPortfolio` is PIT-only
  by construction — there is no revised variant — so no runtime PIT check is needed, and no
  new PIT resolution is introduced).
- **A factor risk model is not a `BacktestResult` (FR-5).** `FactorRiskModel` is a distinct
  record type; it does not enter Phase 12's identity and cannot be passed where a
  `BacktestResult` is required (enforced by type). It is also distinct from
  `FactorPortfolio` — it holds no return series, only pointers and the derived moments.
- **Reference verification + transitive pinning (FR-1).** Each referenced
  `factor_portfolio_id` is resolved from the shared sidecar via
  `store.read_as(id, FactorPortfolio.from_dict)`; a missing id is a `FactorRiskConsistencyError`
  (we refuse to model an artifact that was never sealed), and a resolved record whose own
  `research_result_id` disagrees with the requested id is a corrupt sidecar and raises.
  Unlike Phase 17 (which recomputes a backtest's `result_hash` from its ledger), a
  `FactorPortfolio` exposes no public content→hash recompute; instead each factor's sealed
  `result_hash` is **folded into the model's identity**, so the model's id is transitively
  sensitive to any change in any referenced factor.
- **Commensurability re-verified (FR-3).** Before estimating, the engine asserts every
  factor shares one exact `schedule_id` (their return series align on a common rebalance
  calendar) **and** one `factor_portfolio_engine_version_id` (they were produced by one
  engine logic — the Phase 13/15/17 precedent); any difference is a `FactorRiskConsistencyError`
  (fail closed, never silently aligned). A corpus pin difference is **not** raised — it is
  carried and surfaced as `pin_mismatch` (D-PIN).
- **Complete-case alignment (FR-4).** The estimation window is the intersection of the
  `as_of` instants where **every** factor carries a KNOWN return (an UNDEFINED period
  carries no return and is excluded — never filled or interpolated), in shared ascending
  date order; a duplicate KNOWN `as_of` within a factor is a corrupt input and raises. A
  window shorter than `_MIN_PERIODS = 2` has no dispersion to estimate and raises
  `FactorRiskConfigurationError` — an all-degenerate matrix is never sealed.
- **Fail-closed cells (FR-4).** A correlation whose factor has zero volatility over the
  common window is a recorded `UNDEFINED` `ZERO_VARIANCE`, never a divide-by-zero,
  fabricated `0`, `NaN`, or `Inf` — exactly as Phase 7 metrics / Phase 15 analytics /
  Phase 16 diagnostics / Phase 18 regressions / Phase 19 portfolios do.
- **Provenance.** The record embeds the full declared spec (`factor_risk_spec`), the ordered
  `(label, factor_portfolio_id, result_hash)` references, the shared `schedule_id` and
  producing `factor_portfolio_engine_version_id`, the analysed period count `M`, the
  annualization convention, the engine/formula versions, the per-factor moments, the
  upper-triangle covariance/correlation matrices, the coverage summary, and the carried
  corpus pins — so the whole estimation is reconstructible and auditable from the record
  plus the referenced factors in the same sidecar. It stores **no copy** of any factor
  return series.
- **Storage.** Zero new store types; the `ResearchResultStore` writes the record to
  `<root>/research/sha256-<hex>.json` in the existing container. Write-once and idempotent:
  re-estimating an identical request is a byte-identical no-op; a differing payload under an
  existing id fails closed via the store's guard.

---

## 7. Failure / UNDEFINED behavior (locked)

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`FactorRiskConfigurationError` / `FactorRiskConsistencyError`):
- Malformed spec: an empty `name` / `spec_version`; a non-`tuple` `factor_portfolio_ids`;
  fewer than `_MIN_FACTORS = 2` or more than `N_MAX = 16` ids; an empty or duplicate id; a
  non-decimal / non-finite / non-positive `periods_per_year`. *(configuration, at
  construction)*
- A non-`FactorRiskSpecification` argument to `estimate`. *(configuration)*
- **Insufficient common window:** fewer than `_MIN_PERIODS = 2` complete-case common
  estimation dates — the second moment has no dispersion to estimate, so the run raises
  rather than sealing a degenerate matrix (the Phase 15/16/18/19 minimum-window precedent).
  *(configuration)*
- A referenced `factor_portfolio_id` absent from the sidecar, or a resolved record whose
  `research_result_id` disagrees with the request. *(consistency)*
- Factors that are not commensurable — a differing `schedule_id` or
  `factor_portfolio_engine_version_id` (FR-3). *(consistency)*
- A corrupt / non-finite decimal read from a factor return, or a duplicate KNOWN `as_of`
  within a factor. *(consistency, never guessed)*

**Recorded as first-class UNDEFINED (never raised, never fabricated — FR-4):** a
correlation cell `corr(i,j)` where the volatility of factor `i` or factor `j` over the
common window is exactly `0` → `ZERO_VARIANCE` (its own zero-variance diagonal included).
The factor's mean, its (zero) volatility, and every covariance cell involving it stay
KNOWN. There is no divide-by-zero anywhere: a zero denominator becomes a recorded
UNDEFINED.

**Surfaced, never raised (D-PIN, FR-3):** more than one distinct fundamentals
`dataset_version_id` or market `market_dataset_version_id` across the referenced factors →
`pin_mismatch = True` (mirrors `FactorAttribution.pin_mismatch`). The model is still
estimated; a reader can see the references were not pinned identically.

---

## 8. Public API (locked)

```python
from quantforge import (
    Workspace,
    FactorRiskSpecification,
    FactorRiskModel,
)

ws = Workspace.open(root)
spec = FactorRiskSpecification(
    name="value-momentum-risk",
    factor_portfolio_ids=(  # ORDERED; each a sealed FactorPortfolio id; 2..16; no duplicate
        value_factor_id,
        momentum_factor_id,
    ),
    periods_per_year="252",  # annualization convention (folded into identity)
)
model = ws.factor_risk_engine.estimate(spec)  # sealed, write-once FactorRiskModel

model.factors  # per-factor FactorMoment — mean / population volatility / annualized volatility
model.covariance  # upper-triangle CovarianceCell tuple (i <= j), per-period + annualized
model.correlation  # upper-triangle CorrelationCell tuple (i <= j)
model.coverage  # per-factor + aligned-window coverage (audit metadata, not folded)
model.pin_mismatch  # True iff the factors differ on any carried corpus pin (surfaced)
model.research_result_id  # == model.factor_risk_id (ResearchRecord)

# typed read-back (byte-identical round-trip)
again = ws.research_result_store.read_as(
    model.research_result_id, FactorRiskModel.from_dict
)
```

`FactorRiskEngine` is reached only through `Workspace.factor_risk_engine` (a lazy, cached,
cycle-free `@property` annotated `-> object`; engines are not re-exported at top level).
`estimate(spec) -> FactorRiskModel` is the single entry point. No `Company` method is added
(a factor risk model spans a set of factors, not one filer).

---

## 9. Out of scope (strict)

Deferred to later, explicitly-labelled phases; Phase 20 does not absorb any:
- **Portfolio optimization / mean-variance / risk-parity weighting** (needs the covariance
  matrix this phase produces — the phase after this, Phase 21).
- **Shrinkage / factor-model / Ledoit-Wolf / EWMA covariance estimators** (v1 is the plain
  population sample estimator; a future closed-vocabulary method extension that hashes
  distinctly).
- **Expected-return / alpha models** and any forward-usable (PIT) risk output — v1 is
  ex-post only.
- **Rolling / windowed / regime-conditioned covariance**, sub-period estimates.
- **A REVISED scope** for the estimate (reserved for a future explicitly-labelled phase).
- **Feeding a `FactorRiskModel` into Phase 17 attribution or Phase 12 backtesting** (no
  scope reserved now).
- **Any modification to Phase 19** (its vocabulary, engine, or identity), or to any prior
  phase.
- **Non-`FactorPortfolio` factor inputs** (e.g. a raw return series or a `BacktestResult`)
  — v1 references only sealed `FactorPortfolio` records.
- **Batch / multi-model runs** (one spec = one risk model; batching is a thin future loop).

---

## 10. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 20 suite added), deterministic across runs
  (including `-p no:randomly`).
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src tests`
  clean (strict).
- Zero runtime dependencies (stdlib `hashlib` / `json` / `dataclasses` / `Decimal` only);
  no float in any path; no wall-clock/RNG in any identity or value; the volatilities /
  annualization use `Decimal.sqrt` under the pinned context (the Phase 12/19 precedent, no
  numpy).
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** — the only source edits are the additive
  `Workspace.factor_risk_engine` property/cache line and the `__init__.py` re-exports; no
  edit to any other identity/version module or to `backtest/*`, `analytics/*`,
  `attribution/*`, `crosssection/*`, `diagnostics/*`, `factorportfolio/*`, `panel/*`,
  `market/*`, or `universe/*`.
- Byte-identical `FactorRiskModel` round-trip test proves `from_dict` introduces no drift
  and a tampered stored id is ignored; a determinism double-build and a two-independent-corpora
  build prove `to_dict()` byte-equality and id sensitivity to each input (including factor
  order).
- FR-1 (reference resolution + verification; each factor's `result_hash` folded → transitive
  pinning; missing/drifted reference raised), FR-2 (no `Pit*` type / no as-of accessor;
  ex-post; not a `BacktestResult`), FR-3 (one `schedule_id` + one producing-engine version
  required, else raised; corpus `pin_mismatch` surfaced), FR-4 (complete-case alignment;
  `M < 2` raised; zero-variance correlation → recorded UNDEFINED, never a divide-by-zero),
  FR-5 (distinct record type) each covered by a test.
- Docs updated; `ARCHITECTURE.md` "Factor risk model" row added, `docs/index.md` Phase 20
  entry added, the `data-model.md §12` FR-1..FR-5 block appended, and `README.md` advanced
  to `v0.17.0` only when green.

---

## 11. Test coverage (locked)

New package `tests/factorrisk/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_stats.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline over
fictional CIKs `9999999901..` (reusing the Phase 19 factor-portfolio corpus verbatim,
which in turn reuses the Phase 18 cross-section corpus — the same multi-filer universe
admits two distinct non-collinear signals, `current_ratio` and `quick_ratio`, so two
factor portfolios over the same universe + schedule yield two commensurable factor return
series), covering:

- **Construction validation** — the minimal two-factor request, the order-preserving
  canonical payload, the `periods_per_year` canonicalization (`"012"` → `"12"`,
  `"1.2E1"` → `"12"`), `N_MAX` acceptance, and every fail-closed path (empty name, `< 2` or
  `> N_MAX` ids, duplicate id, empty id, non-`tuple` ids, non-decimal / zero / negative
  `periods_per_year`, empty `spec_version`) (SPEC).
- **Exact-`Decimal` second-moment estimation** against hand-checked synthetic series under
  the pinned context — means + population volatility (`[1,2,3]` → mean `2`, vol `√(2/3)`),
  the diagonal covariance = population variance, the perfectly anti-correlated pair
  (`[1,2,3]` vs `[3,2,1]` → cov `−2/3`, corr `−1`), the positive-variance diagonal
  correlation `1`, annualization scaling (`vol·√ppy`, `cov·ppy`), the constant factor's
  KNOWN zero volatility, its `ZERO_VARIANCE` correlation cells (including the `0/0`
  diagonal) with the covariance staying KNOWN `0`, and the fail-closed ragged /
  single-period / non-decimal paths (STATS).
- `factor_risk_id` folding + sensitivity to each input (engine version, name, spec version,
  the ordered factor id list, `periods_per_year`, the ordered factor result-hash list,
  result hash), the semantic factor order (reversal → distinct id), `factor_risk_result_hash`
  determinism + per-cell + order sensitivity + key-order independence, and the
  engine-version's dependence on the pinned precision + formula (IDENTITY).
- Byte-identical `to_dict` / `from_dict`, derived-id survival, `research_result_id` alias,
  `boundary_kind = "pit"`, `factor_portfolio_ids` follow ref order, result-hash sensitivity
  to a covariance cell, coverage **not** folded, `pin_mismatch` flagging, UNDEFINED-cell
  round-trip, tampered-id ignored, malformed-cell rejection (RESULT).
- End-to-end over the builders: the full upper-triangle matrix over two commensurable
  factors (`periods == 2`, cells `(0,0),(0,1),(1,1)`), factor refs + coverage in request
  order with each ref folding the child's `result_hash` (FR-1), distinct factors → distinct
  moments, annualization carried; persistence + byte-identical round-trip from the sidecar;
  re-estimation idempotent no-op; two independent corpora agree; factor order changes
  identity; the FR-2 ex-post boundary (no `pit`/`as_of` accessor, not a `BacktestResult`);
  FR-1 missing reference fails closed; FR-3 different-schedule fails closed; FR-4 the
  estimation window is the common KNOWN axis with full coverage and nothing dropped
  (ENGINE).
- `tests/test_smoke.py` — an additive public-API export assertion for
  `FactorRiskSpecification` / `FactorRiskModel`.

No real financial or network data; the architecture does not require it.
