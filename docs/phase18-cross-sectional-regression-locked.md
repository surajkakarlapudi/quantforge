# Phase 18 — Cross-Sectional Factor-Return Regression (Fama–MacBeth Premia) (LOCKED)

> **Status:** Locked normative specification. Decisions **AG-1–AG-10** were approved as
> recommended and the five §11 open questions are resolved here; this document is the
> source of truth for the implementation and supersedes the recommendations in
> [phase18-cross-sectional-regression-proposal.md](phase18-cross-sectional-regression-proposal.md).
> Every conditional reference in the proposal ("recommended", "approval needed") is
> resolved here to a committed decision.
>
> **One-line thesis:** Phase 18 adds a deterministic, content-addressed
> **cross-sectional factor-return regression** layer (the Fama–MacBeth method) — the
> multivariate cross-sectional generalization of Phase 16, exactly as Phase 17 is the
> multivariate time-series generalization of Phase 15. Given a declarative
> `CrossSectionalRegressionSpecification` naming an **ordered** tuple of *K* factor
> signals (each a `(metric_key, MetricPeriod)`), a Phase 9 universe, a Phase 12 schedule
> of evaluation instants, and a `"<n>d"` forward horizon, `CrossSectionalRegressionEngine
> .estimate(...)` — at each scheduled date `T` — resolves membership PIT as-of `T`, reads
> the *K*-signal cross-section via `panel_across(as_of=T)`, pairs each member with its
> realized **forward** return over `[T, T+h]` trading days, runs one exact-`Decimal`
> cross-sectional OLS across members, then aggregates the per-date coefficients into
> factor **premia** with plain Fama–MacBeth time-series standard errors and t-statistics,
> and seals a `CrossSectionalRegression` `ResearchRecord` write-once to the existing Phase
> 8 sidecar under the same pinned `Decimal` context. It composes Phases 9/10/11 only,
> consumes **no** `BacktestResult`, introduces **no** new data source, **no** new store,
> **no** runtime dependency, and **no** database.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **AG-1** | **Package `crosssection`.** Public types `CrossSectionalRegressionSpecification`, `CrossSectionalRegression`, `FactorSpec`; engine `CrossSectionalRegressionEngine` (reached via `Workspace`, not re-exported). The domain tag is `crosssection/1`; the engine-version string is `crosssection-engine/1`; the formula-method string is `crosssection-stats/1`. These are baked into every `crosssection_id`; changing them later is a breaking identity change. |
| **AG-2** | **Plain (iid) Fama–MacBeth standard error.** `se(γ̄_k) = popStd(γ_k,·)/√M`, using the **population** standard deviation over the *M* valid dates, and `t = γ̄_k/se`. Newey–West / HAC-adjusted errors are out of scope (the Phase 17 D5 deferral, extended). The population-vs-sample convention is pinned into `crosssection-stats/1`. |
| **AG-3** | **OLS (equal-weight members) in v1.** WLS / GLS are out of scope — a weighting scheme would require another PIT signal and more identity inputs (consistent with Phase 17's classical-`(XᵀX)⁻¹`-only scope). |
| **AG-4** | **Raw signals, no standardization.** No per-date z-scoring, winsorization, trimming, rank-transform, or neutralization — no transform is smuggled into the regression (the Phase 16 §1.1(3) discipline). Standardization is a clean future closed-vocabulary extension that hashes distinctly. |
| **AG-5** | **Two thresholds.** (a) A per-date degrees-of-freedom guard `n_members ≥ K + include_intercept + 1` — a date below it is a recorded `UNDEFINED` date (`INSUFFICIENT_MEMBERS`, XS-4), **never** a raise; (b) a minimum-valid-dates guard `M ≥ 2` for the aggregation — a run yielding fewer than two *defined* regressions raises `CrossSectionConfigurationError` (the Phase 16 `_MIN_PAIRS` / Phase 15 `_MIN_PERIODS` precedent), so an all-`UNDEFINED` record is never sealed. |
| **AG-6** | **Promote the exact-`Decimal` OLS solver into shared `quantforge._linalg`.** The LDLᵀ (Cholesky-family) factorization with an exact zero-pivot test (`ldl`, `ldl_solve`, `inverse_diagonal`) lives in one shared internal helper that both `attribution/stats.py` and `crosssection/stats.py` import. This was a **behavior-preserving** promotion: Phase 17's numeric output and its `attribution_engine_version_id` are **unchanged** (verified by the Phase 17 suite staying green). |
| **AG-7** | **Reuse Phase 16's forward-return definition verbatim.** The same `"<n>d"` trading-day grammar, the same PIT-gated adjusted price view, the same drop-on-missing / multi-share-class rule (`diagnostics.compute.forward_return`). No second, divergent forward-return definition enters the codebase. |
| **AG-8** | **`include_intercept = True` by default**, folded into identity. The intercept (the per-date cross-sectional alpha `γ₀`) changes every slope and is an explicit, identity-folded modeling choice; a non-`bool` is rejected at construction. |
| **AG-9** | **`K_MAX = 8`** (reuse the Phase 17 bound). A request declaring more than 8 factors is a configuration defect, raised at construction — never silently truncated. |
| **AG-10** | This phase releases as **`v0.15.0`** (Phase 17 = v0.14.0). The package `__version__` string is unchanged (versioning is by content-addressed ids, not a semver string). |

### 1.1 Resolved open questions (§11)

The proposal left five questions open; all are resolved here and are load-bearing for the
implementation.

1. **AG-6 direction.** **Promote** the shared exact-`Decimal` OLS helper into
   `quantforge._linalg` — one behavior-preserving edit to `attribution/stats.py`. Gated on
   the Phase 17 suite staying green and `attribution_engine_version_id` unchanged; both
   hold.
2. **FM standard-error refinement.** **Plain FM standard error in v1**, HAC deferred
   (AG-2).
3. **Per-date `r_squared` in the seal.** **Included.** Each per-date coefficient block
   carries its `r_squared` `StatValue`, and it is folded into `result_hash` — it is a
   result-changing provenance fact (Phase 16's inclusion of per-date diagnostics).
4. **Factor-label policy.** **Auto-label `factor_1..factor_K`** by ordinal position
   (identity by ordinal, like Phase 17), with an optional display `label` on `FactorSpec`
   that identity **ignores** (two specs differing only in a factor's `label` produce the
   same id). The intercept, when present, is labelled `alpha`.
5. **Population vs sample dispersion.** **Population** standard deviation of the per-date
   coefficients, pinned in `crosssection-stats/1` (AG-2).

### 1.2 Deviations from the proposal (disclosed)

Recorded for auditability; none changes an identity discipline or weakens an invariant.

1. **`FactorSpec` lives in `spec.py`, not `model.py`.** The proposal §5 module map lists
   `FactorSpec` under `model.py`; the implementation defines it in `spec.py` beside the
   specification it belongs to (and `model.py` re-declares no factor type). The public
   re-export and the `(metric_key, period, label)` shape are exactly as proposed.
2. **The record field is `factor_descriptors`, not `factor_labels`.** The proposal §5
   result sketch lists a `factor_labels: tuple[str, ...]` field; the sealed record instead
   carries `factor_descriptors: tuple[(metric_key, period_key), ...]` (the ordered identity
   descriptors folded into `crosssection_id`) and derives the coefficient labels
   (`alpha`?, `factor_1..factor_K`) deterministically from the factor count + intercept
   flag. This strengthens identity (the id is sensitive to *which* signal/period, not only
   to an ordinal label) and matches the §5 identity fold, which was always specified over
   the descriptors.
3. **The premia block is tagged `"premium"` (singular) per cell.** The proposal §5 sketch
   writes `{"block":"premia", …}`; each premium *cell* is tagged `{"block":"premium", …}`
   (one cell per coefficient). The per-date cells are tagged `{"block":"per_date", …}` as
   proposed. This is a cell-level tag detail folded into `result_hash`; the block order
   (all per-date cells in schedule order, then all premium cells in factor order) is
   exactly as proposed.
4. **Version constants are split across `version.py` and `spec.py`/`result.py`.** The
   proposal §5 module map lists all four version constants under `version.py`;
   `CROSSSECTION_SPEC_VERSION` lives in `spec.py` and `CROSSSECTION_RESULT_FORMAT_VERSION`
   in `result.py` (each beside the type it versions), while `version.py` owns the engine +
   formula versions and the pinned decimal context. No value or fold changes.

---

## 2. Architecture (locked)

Phase 18 is a thin cross-sectional-regression layer *above* Phases 9/10/11, structurally
the **multivariate cross-sectional sibling of Phase 16** (`diagnostics`) — the correct
precedent because Phase 18, like the IC diagnostics, reads the **raw corpora** (universe
membership, PIT signals, PIT-gated adjusted forward returns) rather than sealed
`BacktestResult`s. It follows the extension recipe every prior phase uses: versioned
immutable request object → fail-closed engine reached from `Workspace` via a lazy,
cycle-free `@property` → distinct result type → content-addressed identity with fresh
domain tags → data conditions recorded as first-class values, defects raised →
compute-on-demand with the shared write-once sidecar. Like Phase 16 (and unlike Phase 17),
Phase 18 references the corpora by **corpus pin** (the fundamentals `dataset_version_id`
and market `market_dataset_version_id`), so the id stays sensitive to any corpus change
without folding a sealed artifact hash.

```
                 CrossSectionalRegressionSpecification    (declarative request, content-addressed)
                          |
                          v
   Workspace.crosssection_engine  --->  CrossSectionalRegressionEngine.estimate(spec)
                          |                 |
                          |   re-derive + verify BOTH corpus pins (XS-1)          — fail closed
                          |     fundamentals DatasetVersion + market MarketDatasetVersion
                          |     over the universe's explicit source companies/securities
                          |
                          |   per evaluation date T (schedule order):
                          |     build membership PIT as-of T          (Phase 9, survivorship-free)
                          |     read K-signal cross-section via panel_across(as_of=T)  (Phase 10, XS-3)
                          |     pair each member w/ realized forward return over [T, T+h]
                          |       through the Phase 11 PIT-gated adjusted view          (XS-2, XS-4)
                          |     if n_members >= K + intercept + 1:
                          |       one exact-Decimal cross-sectional OLS  (LDLᵀ + exact zero pivot)
                          |       -> per-date coefficients γ_T + R²   (UNDEFINED-preserving)
                          |     else: all-UNDEFINED per-date block (INSUFFICIENT_MEMBERS)
                          |
                          |   require >= 2 valid dates                             — fail closed (AG-5)
                          |   Fama-MacBeth aggregate each coefficient's series:
                          |     mean, plain population se = popStd/√M, t = mean/se  (UNDEFINED-preserving)
                          v                 v
             CrossSectionalRegression (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
             store.read_as(id, CrossSectionalRegression.from_dict)  (typed, byte-identical round-trip)
```

**New package `src/quantforge/crosssection/`** (mirrors `diagnostics/`):

- `errors.py` — `CrossSectionError` → `CrossSectionConfigurationError`,
  `CrossSectionConsistencyError`.
- `version.py` — `CrossSectionEngineVersion` (folds the pinned decimal context **and** the
  formula-method version `crosssection-stats/1` into `config_hash`);
  `CROSSSECTION_ENGINE_VERSION = "crosssection-engine/1"`, `CROSSSECTION_FORMULA_VERSION =
  "crosssection-stats/1"`; `default_decimal_context()`. The id property is
  `crosssection_engine_version_id`.
- `identity.py` — `crosssection_result_hash`, `crosssection_id`. Fresh record domain tag
  `crosssection/1`. (The engine-version id is **not** re-implemented here — it is a
  property of `CrossSectionEngineVersion`, one source of truth.)
- `model.py` — `CrossSectionStatus` / `CrossSectionUndefinedReason` vocabulary;
  `INTERCEPT_LABEL` / `factor_label`; `StatValue` (a KNOWN decimal string **or**
  UNDEFINED+reason); the nested records `PerDateCoefficients`, `PremiumEstimate`,
  `CoverageSummary`, `DateCoverage`.
- `stats.py` — the pure per-date OLS (`cross_section_ols`, `coefficient_labels`) and the
  Fama–MacBeth aggregation (`premium_estimate`). Pure; read no store; take
  decimal-string vectors, return KNOWN / UNDEFINED cells. Imports the LDLᵀ primitives
  from `quantforge._linalg`.
- `spec.py` — `FactorSpec`, `CrossSectionalRegressionSpecification`, full construction-time
  validation; `CROSSSECTION_SPEC_VERSION = "crosssection/1"`; `K_MAX = 8`.
- `result.py` — `CROSSSECTION_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`,
  `CrossSectionalRegression` (a `ResearchRecord` with `.seal` / `to_dict` / `from_dict`).
- `engine.py` — `CrossSectionalRegressionEngine` (constructed from `Workspace`; reuses the
  workspace's Phase 8 `FactorEngine` + shared research sidecar, Phase 10 `PanelEngine`,
  Phase 11 `PriceEngine`, and a Phase 9 `UniverseBuilder`): verify pins → per-date resolve
  + pair + regress → aggregate → seal → write-once.
- `__init__.py` — package exports.

**Shared linear-algebra helper `src/quantforge/_linalg/`** (AG-6 promotion): the
exact-`Decimal` LDLᵀ factorization with an exact zero-pivot test (`ldl` returns `None` on
a non-positive pivot → SINGULAR_DESIGN; `ldl_solve`; `inverse_diagonal`). Imported by both
`attribution/stats.py` and `crosssection/stats.py`.

**Edits to existing source** (all additive except the behavior-preserving AG-6 promotion,
none altering any existing identity):

1. `workspace.py` — one lazy `crosssection_engine` `@property` (+ its
   `self._crosssection_engine: object | None = None` cache line), following the
   `analytics_engine` / `attribution_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of
   `CrossSectionalRegressionSpecification`, `CrossSectionalRegression`, and `FactorSpec`
   (spec + result + factor only; the engine is reached via `Workspace`).
3. `src/quantforge/attribution/stats.py` — its private LDLᵀ helpers replaced by imports
   from `quantforge._linalg`, **behavior- and byte-identical**; the Phase 17 suite stays
   green and `attribution_engine_version_id` is unchanged.
4. `tests/test_smoke.py` — one additive public-API export assertion.

**No edit to** `backtest/*`, `analytics/*`, `experiment/*`, `report/*`, `diagnostics/*`
(beyond importing its `forward_return`), `panel/*`, `market/*`, `universe/*`,
`factors/store.py`, or any identity/version module of a prior phase. **No new PIT
resolution and no new store.**

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
wall-clock, no RNG.

### 3.1 `FactorSpec` + `CrossSectionalRegressionSpecification` (declarative request)

```
FactorSpec(
    metric_key: str,                 # a Phase 7 metric key, non-empty
    period: MetricPeriod,            # the explicit fiscal period it is read for (never inferred)
    label: str | None = None,        # display only; identity uses the ordinal position
)

CrossSectionalRegressionSpecification(
    name: str,                       # non-empty
    factors: tuple[FactorSpec, ...],  # ordered, non-empty, <= K_MAX, no duplicate (metric_key, period)
    universe: UniverseSpecification,  # Phase 9 declarative request
    schedule: RebalanceSchedule,      # Phase 12 as_of instants (evaluation dates T)
    forward_horizon: str,             # r"^[0-9]+d$" trading-day horizon (Phase 16 grammar)
    dataset_version_id: str,          # fundamentals corpus pin (non-empty)
    market_dataset_version_id: str,   # market corpus pin (non-empty)
    include_intercept: bool = True,   # γ₀ term (folded into identity)
    spec_version: str = "crosssection/1",
    horizon_days: int = <derived>,    # parsed from forward_horizon at construction, never supplied
)
```

Construction-time validation (fail closed, `CrossSectionConfigurationError`): empty `name`
/ `spec_version` / either corpus pin; an empty factor tuple or more than `K_MAX = 8`
factors; a factor that is not a `FactorSpec`, whose `metric_key` is empty, or whose
`period` is not a `MetricPeriod`; a duplicate `(metric_key, period)` (a repeated column is
a collinear design by construction — the **same** metric read for a **different** period is
allowed); a `universe` that is not a `UniverseSpecification`; a `schedule` missing the
`RebalanceSchedule` surface (`schedule_id` + `as_of_instants`) or enumerating zero
instants; a `forward_horizon` not of the form `"<n>d"` with `n ≥ 1`; a non-`bool`
`include_intercept` (a truthy int can never masquerade as the flag). It reads no store and
no wall clock — it cannot know whether the referenced corpora exist (that is the engine's
XS-1 step) or whether any date clears the DoF floor (the engine's fail-closed steps); it
validates only the request's internal shape. The **factor order is semantic** and is
preserved exactly (never sorted): it fixes the design-matrix column order and the
coefficient labels, so `[(a, p), (b, p)]` and `[(b, p), (a, p)]` are distinct requests with
distinct ids. `to_dict()` emits `factors` in declared order; `factor_descriptors` is the
ordered `[[metric_key, period_key], …]` identity view (labels excluded).

### 3.2 Estimation blocks (`PerDateEstimate`, internal)

`cross_section_ols(...)` returns an internal `PerDateEstimate`:

```
PerDateEstimate(
    coefficients: tuple[(label, StatValue), ...],  # alpha? first, then per factor (request order)
    r_squared: StatValue,                          # per-date coefficient of determination
    singular: bool,                                # True iff XᵀX not positive-definite
)
```

`premium_estimate(...)` returns `(mean, std_error, t_stat, n_valid_dates)` — three
`StatValue`s and the count `M` of valid dates that aggregated.

`StatValue` is the UNDEFINED-preserving cell: `StatValue.known("<decimal string>")` **or**
`StatValue.undefined(<CrossSectionUndefinedReason>)`. Exactly one of `value` / `reason` is
populated (enforced at construction). Never a bare float, never silently omitted.

### 3.3 `CrossSectionalRegression` (implements `ResearchRecord`)

```
CrossSectionalRegression(
    crosssection_engine_version_id: str,
    crosssection_spec: dict[str, object],           # the full CrossSectionalRegressionSpecification.to_dict()
    name: str,
    spec_version: str,
    factor_descriptors: tuple[(metric_key, period_key), ...],   # ordered, request order
    universe_specification_id: str,
    schedule_id: str,                               # the shared evaluation-schedule identity
    horizon_days: int,
    include_intercept: bool,
    boundary_kind: str,                             # "pit" (input side; XS-2 — not a PIT value)
    dataset_version_id: str,                        # fundamentals corpus pin
    market_dataset_version_id: str,                 # market corpus pin
    per_date: tuple[PerDateCoefficients, ...],      # one per evaluation date, schedule order
    premia: tuple[PremiumEstimate, ...],            # ordered, aligned to coefficient labels
    coverage: CoverageSummary,
    formula_version: str,                           # "crosssection-stats/1"
    result_hash: str,                               # canonical JSON over the ordered output cells
)

# derived, never stored as state:
crosssection_id     property -> sha256 folding engine version + request identity
                                + both corpus pins + result_hash
research_result_id  property -> alias of crosssection_id  (the ResearchRecord key)
```

- `PerDateCoefficients(as_of, n_members, coefficients: tuple[(label, StatValue), …],
  r_squared: StatValue)` — the per-date `γ_T` (each coefficient a `StatValue`; a singular
  or below-floor per-date design yields an all-`UNDEFINED` block, recorded, never dropped
  silently).
- `PremiumEstimate(label, mean, std_error, t_stat, n_valid_dates)` — the aggregated
  Fama–MacBeth premium per coefficient.
- `CoverageSummary(per_date: tuple[DateCoverage, …], total_eligible,
  total_dropped_for_signal, total_dropped_for_return, total_dropped_for_singular_date)`;
  `DateCoverage(as_of, resolved_members, eligible, dropped_for_signal, dropped_for_return,
  regression_status)` — `regression_status` is `"known"` when the date admitted a defined
  regression, else the reason value (`"insufficient_members"` / `"singular_design"`) that
  made the whole block UNDEFINED.
- `to_dict()` keys (deterministic, `sort_keys=True` at the store): `crosssection_id`,
  `research_result_id` (alias so the generic reader keys correctly), and every field
  above. A KNOWN cell emits `value` only; an UNDEFINED cell emits `reason` only.
- `from_dict` is the fail-closed inverse; `crosssection_id` / `research_result_id` are
  re-derived by their properties, **never read from state**, so `from_dict(to_dict(r))`
  re-emits identical bytes and the same `result_hash`, and a tampered stored id is ignored.
  A malformed cell (unknown status, missing value/reason, unrecognized reason) is refused
  with a `ValueError`.
- `.seal(...)` is the identity-computing constructor: it folds the ordered computed-output
  cells (the per-date coefficient panel in schedule order, then the premia block in factor
  order, each tagged by its block so two structurally different records can never collide)
  into `result_hash`, so identity is a pure function of the request + referenced corpora +
  computed answer, never caller-supplied. **The coverage summary is audit metadata and is
  NOT folded into `result_hash`** (§5) — it is fully determined by the same inputs, so it
  never desynchronizes.

**What the model deliberately does NOT hold:** any copy of a raw fundamentals or price
value (only the derived per-date coefficients, R², and premia); any float; any wall-clock
or RNG value; any `Pit*` type or as-of accessor (XS-2); any presentation.

### 3.4 Closed v1 vocabulary

`CrossSectionUndefinedReason` (closed, 6): `SINGULAR_DESIGN`, `INSUFFICIENT_MEMBERS`,
`ZERO_VARIANCE`, `NO_VALID_DATES`, `SINGLE_VALID_DATE`, `ZERO_COEFFICIENT_VARIANCE`.
`CrossSectionStatus` (2): `KNOWN`, `UNDEFINED`. Extending the reason set is an explicit
future edit that hashes distinctly (a new reason changes `result_hash`) — never an implicit
fallback.

---

## 4. Formula methods (locked, folded into `crosssection-stats/1`)

Changing any of these bumps `CROSSSECTION_FORMULA_VERSION`, so a value computed under one
method can never be silently reinterpreted under another. All arithmetic runs under an
explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`), never the ambient process
context. `Decimal.sqrt(context)` covers all roots. No float touches any value.

- **Per-date design matrix.** `X = [1? | x₁ | … | x_K]` (an optional intercept column plus
  *K* **raw** signal columns — no standardization, AG-4), `n` member rows. The regressand
  is the members' realized forward returns; each regressor column is a factor's PIT signal
  across those members.
- **Per-date OLS solve.** The normal equations `(XᵀX)β = Xᵀy` are solved via an
  exact-`Decimal` LDLᵀ (Cholesky-family) factorization with an **exact zero-pivot test**: a
  non-positive pivot `D[j] ≤ 0` means `XᵀX` is not positive-definite (collinear / degenerate
  signals across that date's members — including a constant signal duplicating the
  intercept) and the whole per-date coefficient block (and its R²) is `SINGULAR_DESIGN` —
  never a fabricated coefficient, never a silently dropped factor (XS-4). No float tolerance
  enters the test; the pivot is an exact `Decimal`.
- **Per-date R².** `R² = 1 − SSR/SST` where `SST = Σ(yᵢ − ȳ)²` and `SSR = Σeᵢ²`. `SST = 0`
  (a constant regressand across members) → `ZERO_VARIANCE`, never a divide-by-zero; the
  coefficients stay KNOWN. A no-intercept fit may yield a negative R² (this is correct and
  recorded as a KNOWN value).
- **Fama–MacBeth aggregation.** Writing `γ_k,T` for coefficient *k*'s value on valid date
  `T`, the premium is the time-series mean `γ̄_k = (1/M) Σ_T γ_k,T` over the *M* valid
  dates; its standard error is the plain (iid) `se_k = popStd(γ_k,·)/√M` where `popStd` is
  the **population** standard deviation (variance `= (1/M) Σ (γ_k,T − γ̄_k)²`) over the *M*
  valid dates; its t-statistic is `γ̄_k / se_k`. Only a date whose per-date regression was
  **defined and non-singular** contributes its coefficient to the series (a below-floor or
  singular date contributes nothing).
- **Aggregation degeneracies (never a divide-by-zero).** `M = 0` → the whole premium is
  `NO_VALID_DATES`. `M = 1` → the mean is KNOWN but the dispersion cells (standard error,
  t-statistic) are `SINGLE_VALID_DATE` (a single observation carries no dispersion). `M ≥ 2`
  with zero population dispersion (every per-date coefficient identical) → the standard
  error is a KNOWN exact `0` and the t-statistic is `ZERO_COEFFICIENT_VARIANCE`.
- **No annualization.** No `periods_per_year` convention exists — the Fama–MacBeth
  t-statistic is per-period, and no annualization value enters `crosssection_id`.

---

## 5. Identity / determinism (locked)

- Domain tags via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): record tag
  `crosssection/1`; engine tag `crosssection-engine/1`; formula tag `crosssection-stats/1`.
- `crosssection_engine_version_id = sha256(code_version "crosssection-engine/1",
  config_hash)` where `config_hash =
  sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=crosssection-stats/1")`. Any change to
  the decimal context **or** a formula method yields a new engine id.
- `crosssection_result_hash = sha256(canonical JSON over the ordered computed-output cells:
  the per-date coefficient panel in schedule order — each `{"block":"per_date", …}` — then
  the premia in factor order — each `{"block":"premium", …}`)`. Sensitive to every computed
  cell: each per-date coefficient, each per-date R², and each premium's mean / standard
  error / t-statistic. One differing cell changes it.
- `crosssection_id = sha256`, NUL-joined, in this exact order: `crosssection/1`,
  `crosssection_engine_version_id`, `name`, `spec_version`, canonical-JSON of the
  **ordered** `factor_descriptors`, `universe_specification_id`, `schedule_id`,
  `str(horizon_days)`, `str(include_intercept)`, `dataset_version_id`,
  `market_dataset_version_id`, and `crosssection_result_hash`.
- `research_result_id` aliases `crosssection_id` (single id).

**Folds (changes identity):** engine-logic + formula + decimal-context version ✔, the full
declared request (name, spec version, ordered factor descriptors, universe/schedule
identities, horizon day count, intercept flag) ✔, **both** corpus pins — a changed corpus
changes a pin (XS-1) ✔, the computed statistics (via `result_hash`) ✔. **Does NOT fold:**
the record schema/format version (`CROSSSECTION_RESULT_FORMAT_VERSION` — a container
concern), the coverage summary (audit metadata), the display `label` on a factor, any
presentation, wall-clock, RNG, `id()`, or iteration order (the carried corpus-pin
component sets are sorted). The factor descriptors are folded in **request order**, never
sorted.

Same request + same pinned corpora → same `crosssection_id` and same bytes on any machine.

---

## 6. PIT semantics, provenance, storage (locked)

- **The signal side is read PIT-correctly (XS-3).** At each evaluation date `T`, each
  factor's signal cross-section is read via `panel_across(..., as_of=T)` (invariant 29), so
  no post-`T` fundamentals ever contaminate a signal. Membership is rebuilt at each `T`
  through Phase 9 `build_as_of`, inheriting Phase 9's survivorship-correct membership.
- **The output is ex-post, not PIT (XS-2).** The **forward** return over `[T, T+h]` is
  realized *after* `T`, so the regression of realized returns is an ex-post research
  statistic. `CrossSectionalRegression` is **not** a `Pit*` type, exposes **no** as-of
  accessor, and is inadmissible where a PIT signal/value is required — the exact analogue of
  invariant 28 / SD-2. `boundary_kind = "pit"` documents only that the *signal side* was
  read PIT-eligibly; it does not claim the regression itself is a PIT value.
- **Forward return (AG-7, reused verbatim from Phase 16).** A member's `company_id` maps to
  its single tradable `security_id` (a company with no tradable security — or, for v1, more
  than one — is dropped for return, never guessed); the base trading date is the latest
  stored close on-or-before `T`, the end the close `h` trading days later; both endpoints
  are read through the Phase 11 PIT-gated adjusted view at the **window-end `as_of`** (the
  instant the `T+h` session becomes knowable), so split/dividend adjustment is consistent
  and free of revision leak. A missing/UNKNOWN endpoint, a non-positive base, or a window
  that runs past the stored history → the member is dropped for return (XS-4).
- **Corpus pins re-verified (XS-1).** Before touching any data the engine re-derives both
  the fundamentals `DatasetVersion` (the union of each source filer's per-filer snapshot)
  and the market `MarketDatasetVersion` (the union of each source security's per-instrument
  snapshot) over the universe's explicit source companies, and asserts each equals the
  spec's declared pin; a mismatch — or a corpus that does not admit a single normalizing
  transformation version — is a `CrossSectionConsistencyError` (fail closed, never silently
  reconciled). This reuses the Phase 16 machinery verbatim. A changed corpus yields a
  different pin, hence a different `crosssection_id`.
- **Fail-closed pairing (XS-4).** A member lacking **any** of the *K* PIT signals at `T`,
  or with no computable forward return, is excluded from that date's cross-section and
  counted in coverage (`dropped_for_signal` / `dropped_for_return`), never imputed,
  zero-filled, or fabricated. A per-date design below the DoF floor or singular is a
  recorded `UNDEFINED` date (counted in `total_dropped_for_singular_date` for a singular
  date), never raised, and contributes no coefficient to the premia.
- **Provenance.** The record embeds the full declared spec (`crosssection_spec`), both
  corpus pins, the ordered factor descriptors, the universe / schedule identities, the
  horizon day count, the intercept flag, the engine/formula versions, the complete per-date
  coefficient panel + premia, and the coverage summary — so the whole computation is
  reconstructible and auditable from the record plus the two pinned corpora. It stores **no
  copy** of any raw financial value beyond the derived statistics.
- **Storage.** Zero new store types; the `ResearchResultStore` writes the record to
  `<root>/research/sha256-<hex>.json` in the existing container. Write-once and idempotent:
  re-estimating an identical regression is a byte-identical no-op; a differing payload under
  an existing id fails closed via the store's guard.

---

## 7. Failure / UNDEFINED behavior (locked)

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`CrossSectionConfigurationError` / `CrossSectionConsistencyError`):
- Malformed spec: empty `name` / `spec_version` / either corpus pin; empty / too-many
  (`> K_MAX`) / non-`FactorSpec` / empty-`metric_key` / non-`MetricPeriod`-period /
  duplicate `(metric_key, period)` factors; a non-`UniverseSpecification` universe; a
  schedule missing its surface or enumerating zero instants; a malformed `forward_horizon`;
  a non-`bool` `include_intercept`. *(configuration, at construction)*
- A non-`CrossSectionalRegressionSpecification` argument to `estimate`, or a source filter
  that is not an `ExplicitCompanyFilter` (cannot pin a reproducible corpus).
  *(configuration)*
- **Insufficient valid dates:** fewer than `_MIN_VALID_DATES = 2` scheduled dates yield a
  defined, non-singular regression — the Fama–MacBeth aggregation would have no time-series
  dispersion, so the run raises rather than sealing an all-`UNDEFINED` record (the Phase 16
  `_MIN_PAIRS` / Phase 15 `_MIN_PERIODS` precedent). *(configuration)*
- A corpus-pin mismatch or a non-unique corpus normalizer (XS-1). *(consistency)*
- A corrupt / non-finite decimal read from a signal or forward-return value. *(consistency,
  never guessed)*

**Recorded as first-class UNDEFINED (never raised, never fabricated — XS-4):** a per-date
design below the DoF floor (`n_members < K + include_intercept + 1`) → the whole per-date
block is `INSUFFICIENT_MEMBERS`; a singular / collinear per-date design → the whole block is
`SINGULAR_DESIGN` (no factor silently dropped, no coefficient fabricated); a zero-variance
regressand → `ZERO_VARIANCE` R² (the coefficients stay KNOWN); a premium coefficient KNOWN
on no valid date → `NO_VALID_DATES`; on exactly one valid date → the mean is KNOWN but the
dispersion cells are `SINGLE_VALID_DATE`; a premium whose per-date series (over ≥ 2 dates)
has zero population dispersion → the t-statistic is `ZERO_COEFFICIENT_VARIANCE` (the mean and
the zero standard error stay KNOWN). There is no divide-by-zero anywhere: a zero denominator
becomes a recorded UNDEFINED, exactly as Phase 7 metrics / Phase 15 analytics / Phase 16
diagnostics do.

---

## 8. Public API (locked)

```python
from quantforge import (
    Workspace,
    CrossSectionalRegressionSpecification,
    CrossSectionalRegression,
    FactorSpec,
)

ws = Workspace.open(root)
spec = CrossSectionalRegressionSpecification(
    name="two-factor-premia",
    factors=(  # ordered; order is semantic (fixes column order + coefficient labels)
        FactorSpec(metric_key="current_ratio", period=PERIOD),
        FactorSpec(metric_key="quick_ratio", period=PERIOD),
    ),
    universe=universe_spec,  # a Phase 9 UniverseSpecification (explicit source filter)
    schedule=schedule,  # a Phase 12 RebalanceSchedule of evaluation instants T
    forward_horizon="1d",  # "<n>d" trading-day horizon
    dataset_version_id=fundamentals_pin,  # re-verified at estimate (XS-1)
    market_dataset_version_id=market_pin,
    include_intercept=True,  # γ₀ (folded into identity)
)
regression = ws.crosssection_engine.estimate(
    spec
)  # sealed, write-once CrossSectionalRegression

regression.per_date  # ordered PerDateCoefficients — one per evaluation date (schedule order)
regression.premia  # ordered PremiumEstimate — alpha? + per factor (Fama–MacBeth premia)
regression.coverage  # per-date + total coverage counts (audit metadata, not folded)
regression.research_result_id  # == regression.crosssection_id (ResearchRecord)

# typed read-back (byte-identical round-trip)
again = ws.research_result_store.read_as(
    regression.research_result_id, CrossSectionalRegression.from_dict
)
```

`CrossSectionalRegressionEngine` is reached only through `Workspace.crosssection_engine` (a
lazy, cached, cycle-free `@property` annotated `-> object`; engines are not re-exported at
top level). `estimate(spec) -> CrossSectionalRegression` is the single entry point. No
`Company` method is added (a regression spans a universe + K factors, not one filer).

---

## 9. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 18 suite added), deterministic across runs
  (including `-p no:randomly`).
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src tests`
  clean (strict).
- Zero runtime dependencies (stdlib `hashlib` / `json` / `dataclasses` / `Decimal` only);
  no float in any path; no wall-clock/RNG in any identity or value; the per-date OLS solve
  is an exact-`Decimal` LDLᵀ factorization (no linear-algebra dependency, no numpy).
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** — the only source edits are the additive
  `Workspace.crosssection_engine` property/cache line, the `__init__.py` re-exports, and the
  behavior-preserving AG-6 solver promotion (which leaves `attribution_engine_version_id`
  unchanged and the Phase 17 suite green); no edit to any other identity/version module or
  to `backtest/*`, `analytics/*`, `diagnostics/*` (beyond importing `forward_return`),
  `panel/*`, `market/*`, or `universe/*`.
- Byte-identical `CrossSectionalRegression` round-trip test proves `from_dict` introduces no
  drift and a tampered stored id is ignored; a determinism double-build proves `to_dict()`
  byte-equality and id sensitivity to each input.
- XS-1 (both pins folded + re-verified; changed corpus → different id; mismatch raised),
  XS-2 (no `Pit*` type / no as-of accessor; forward return is ex-post), XS-3 (signal read
  PIT-eligibly via `panel_across(as_of=T)`), XS-4 (fail-closed pairing + UNDEFINED-preserving
  per-date estimation) each covered by a test.
- Docs updated; `ARCHITECTURE.md` "Cross-sectional factor-return regression" row flipped to
  ✅ and `README.md` advanced to `v0.15.0` only when green.

---

## 10. Test coverage (locked)

New package `tests/crosssection/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_stats.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline over
fictional CIKs `9999999901..`, covering:

- **Construction validation** — every fail-closed spec path (empty fields, `K_MAX` ceiling,
  duplicate `(metric_key, period)` — same metric / different period allowed —, empty metric
  key, horizon grammar, required pins, non-`bool` intercept), the order-preserving canonical
  payload and factor descriptors (SPEC).
- **Exact-`Decimal` per-date OLS + FM aggregation** against hand-computed reference values —
  no-intercept single-factor exact solve (with a correct negative R²), exact line with
  intercept (R² = 1), constant-signal-with-intercept → `SINGULAR_DESIGN`, zero-variance
  regressand → coefficients KNOWN + R² `ZERO_VARIANCE`, two collinear signals → singular;
  the FM premium over two dates (exact mean / population se / t), single valid date →
  dispersion `SINGLE_VALID_DATE`, no dates → `NO_VALID_DATES`, zero cross-date dispersion →
  `ZERO_COEFFICIENT_VARIANCE`, negative-mean t sign, and rejection of a non-decimal /
  non-finite input (STATS).
- `crosssection_id` folding + sensitivity to each input (engine version, name, spec version,
  factor **order**, universe/schedule/horizon/intercept/either pin, result hash);
  `crosssection_result_hash` determinism + per-cell sensitivity + key-order independence; the
  engine-version's dependence on the pinned precision + formula (IDENTITY).
- Byte-identical `to_dict` / `from_dict`, derived-id survival, `research_result_id` alias,
  `boundary_kind = "pit"`, result-hash sensitivity to a coefficient, coverage **not** folded,
  UNDEFINED-cell round-trip, tampered-id ignored, malformed-cell rejection (RESULT).
- End-to-end over the builders: all dates/members resolve and premia cover alpha + both
  factors with full coverage; persistence + byte-identical round-trip from the sidecar;
  re-estimation idempotent no-op; two independent corpora agree; the XS-2 ex-post boundary
  (no as-of accessor, `boundary_kind = "pit"`); XS-1 corpus-pin mismatch fails closed; XS-4
  coverage (a member without a tradable security dropped for return; a below-DoF-floor
  cross-section → `INSUFFICIENT_MEMBERS`); the fail-closed single-scheduled-date /
  fewer-than-two-valid-dates raise (ENGINE).

No real financial or network data; the architecture does not require it.
