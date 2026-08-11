# Phase 18 — Cross-Sectional Factor-Return Regression (Fama–MacBeth Premia) — PROPOSAL

> **Status:** Proposal only. No implementation, no source files, no tests, no
> doc/README/ARCHITECTURE edits, no locked spec, no commit/tag/release. This
> document is the sole deliverable of this step. Nothing here is approved until
> the maintainer explicitly approves it.

> **One-line thesis:** Phase 18 adds a deterministic, content-addressed
> **cross-sectional factor-return regression** layer (the Fama–MacBeth method):
> at each scheduled evaluation date `T`, regress the universe's realized
> **forward** returns on `K` **PIT-eligible-at-`T`** signals *across members*
> (one regression per date), then aggregate the per-date slope estimates into
> factor **premia** with time-series standard errors and t-statistics. It is the
> **multivariate cross-sectional generalization of Phase 16** (univariate IC),
> exactly as Phase 17 is the multivariate time-series generalization of Phase 15.
> It composes Phases 9/10/11 only, consumes **no** `BacktestResult`, modifies no
> prior phase, and seals a `CrossSectionalRegression` `ResearchRecord` to the
> existing sidecar.

---

## 1. Selected capability

**Cross-sectional factor-return regression (Fama–MacBeth premia estimation).**

At each evaluation instant `T` in a `RebalanceSchedule`, over a Phase 9 universe
resolved at `T`:

1. Read `K` signals (each a `(metric_key, MetricPeriod)`) as **PIT-eligible-at-`T`**
   cross-sections via Phase 10 `panel_across(..., as_of=T)` (invariant 29, the
   Phase 16 SD-3 discipline).
2. Read each member's realized **forward** return over a `"<n>d"` horizon via the
   Phase 11 PIT-gated adjusted price view — the *identical* forward-return
   machinery Phase 16 already uses.
3. Run one exact-`Decimal` OLS regression *across members*:
   `r_forward,i = γ₀,T + Σ_k γ_k,T · x_k,i + ε_i,T`, yielding a coefficient vector
   `γ_T = (γ₀,T, γ₁,T, …, γ_K,T)` — the **per-date factor returns**. A member
   lacking a PIT signal for **any** of the `K` factors at `T`, or a computable
   forward return, is excluded from that date's cross-section and recorded in
   coverage — never imputed (the Phase 16 SD-4 discipline).

Then aggregate across the `M` valid dates: the **premium** for each coefficient is
the time-series mean `γ̄_k = (1/M) Σ_T γ_k,T`; its standard error is the classic
Fama–MacBeth time-series standard error `se(γ̄_k) = std(γ_k,·) / √M`; and its
t-statistic is `γ̄_k / se(γ̄_k)`. The output is a first-class
`CrossSectionalRegression` record: the per-date coefficient panel, the aggregated
premia block, and a coverage summary — sealed write-once to the shared sidecar.

This is the field-standard test of whether a characteristic is *priced* — the
canonical academic complement to Phase 16's IC (predictive correlation) and
Phase 17's time-series attribution (portfolio return decomposition). It is
**forward-looking, ex-post — not a PIT value** (the SD-2 / FA-2 analog).

**Proposed package name:** `crosssection` (see approval-gated decision AG-1 for
alternatives). Result type `CrossSectionalRegression`; spec
`CrossSectionalRegressionSpecification`; engine `CrossSectionalRegressionEngine`.

---

## 2. Why it belongs in Phase 18

The system's last five phases (13–17) were each a **pure consumer / sibling
layer** that added *zero* changes to prior-phase identity and composed the sealed,
PIT-correct artifacts beneath it. Phase 18 continues that trajectory and closes an
obvious, deliberate gap in the research surface:

| Regression axis \ Predictor count | Univariate | Multivariate |
| --- | --- | --- |
| **Time-series** (portfolio return over time) | Phase 15 single-factor OLS α/β | Phase 17 multi-factor attribution |
| **Cross-sectional** (returns across members at each date) | **Phase 16 univariate IC** | **Phase 18 — this proposal** |

Phase 16 explicitly measures the *rank/linear correlation* of **one** signal with
forward returns; Phase 17 explicitly regresses a portfolio's return series on `K`
factor **portfolios'** return series. Neither answers the question *"controlling
for several characteristics simultaneously, what per-period cross-sectional
premium does each command, and is it statistically distinguishable from zero?"*
— which is precisely Fama–MacBeth. Phase 17's own framing ("the multivariate
generalization Phase 15 deferred") establishes the exact precedent for this being
its own phase: the univariate → multivariate step is a phase-worthy capability,
not a config flag.

It is the strongest candidate on every stated criterion: it composes existing
sealed/PIT-correct artifacts, preserves reproducibility / content-addressed
identity / determinism, reuses the `ResearchRecord`/sidecar architecture verbatim,
requires **no** change to any prior phase's identity or data, adds no runtime
dependency, no database, no RNG, no float, no wall-clock, and no
Python-callback escape hatch, and it has a clear architectural reason to exist as
its own phase (a new statistical object neither sibling produces).

---

## 3. Alternatives considered

Six candidates were evaluated before selecting.

### Candidate A — Cross-sectional factor-return regression / Fama–MacBeth premia *(SELECTED)*
- **Adds:** per-date cross-sectional OLS of forward returns on `K` PIT signals;
  aggregated premia + FM t-statistics; per-date coefficient panel; coverage.
- **Consumes:** Phase 9 (`UniverseBuilder`), Phase 10 (`panel_across`), Phase 11
  (adjusted PIT forward returns) — a diagnostic sibling of Phase 16.
- **Belongs now:** it is the univariate→multivariate cross-sectional
  generalization of Phase 16, mirroring 15→17; it is the canonical priced-factor
  test the system cannot currently perform.
- **New invariants/identity:** a per-date coefficient panel + premia block; both
  corpus pins re-verified (SD-1 analog, call it XS-1); forward-return-is-not-PIT
  (SD-2 analog, XS-2); signal PIT-eligibility (SD-3 analog, XS-3); fail-closed
  pairing (SD-4 analog, XS-4).
- **Duplicates existing?** No. Phase 16 = univariate correlation of one signal;
  Phase 17 = time-series regression of one portfolio's returns on factor
  portfolios. This is multivariate regression *across members at each date* —
  a distinct regression axis and a distinct output (premia in return units, not
  correlations, not portfolio betas).
- **Complexity:** Medium. Reuses the Phase 16 forward-return/pairing engine shape
  and the Phase 17 exact-`Decimal` LDLᵀ OLS solver pattern. New work is the
  per-date-regression loop + FM aggregation.
- **Research value:** Very high — the field-standard test of factor pricing.

### Candidate B — Long/short factor-portfolio construction *(REJECTED — defer)*
- **Adds:** long/short, dollar-neutral, and quantile-spread weighting to the
  strategy vocabulary (extending Phase 12's closed `signal→rank→select→weight`).
- **Consumes:** modifies Phase 12 itself.
- **Why deferred:** it **modifies a sealed prior phase**. Phase 12's
  `StrategySpecification` vocabulary is closed and folds into
  `strategy_version` → `backtest_engine_version_id` → `backtest_id`. Adding
  weighting schemes bumps the engine version and re-hashes the strategy identity —
  a direct **TENSION** with "avoid unnecessary changes to previous phases" and a
  break from the last five phases' pure-consumer discipline. It is legitimate and
  high-value, but it deserves its own carefully approval-gated phase that
  explicitly versions the Phase 12 engine; it should not ride in as Phase 18.
  (This is the README "Next" row; deferring it is a scope decision, not a denial.)

### Candidate C — Multiple-testing / data-mining correction over an experiment *(REJECTED — narrow)*
- **Adds:** deflated Sharpe ratio, Bonferroni/BH family-wise error, and haircut
  t-stats across a Phase 13 `ExperimentResult`'s children.
- **Consumes:** Phase 13 experiments (pure consumer).
- **Why rejected:** genuinely valuable and PIT-safe, but it is a **thin statistical
  refinement of the analytics family** (fits naturally as a future analytics
  extension), narrower in scope than a full regression layer, and it presumes a
  large swept experiment to be meaningful. Weaker architectural claim to its own
  phase; defer as a candidate for a later analytics-family phase.

### Candidate D — Rolling / windowed performance & risk analytics *(REJECTED — extension)*
- **Adds:** rolling Sharpe, rolling volatility, rolling beta over a sealed
  backtest's `period_returns`.
- **Consumes:** Phase 12 `BacktestResult` (pure consumer, Phase 15 shape).
- **Why rejected:** it is an **extension of Phase 15**, not a new capability class;
  it computes windowed views of statistics Phase 15 already defines. Low novelty;
  no clear reason to be its own phase versus a Phase 15 additive follow-on.

### Candidate E — Holdings-based exposure / characteristic analytics *(REJECTED — premature)*
- **Adds:** portfolio-weighted signal exposures and active exposures vs a
  benchmark, computed from the Phase 12 rebalance ledger's `positions`.
- **Consumes:** Phase 12 ledger + Phase 10 panel.
- **Why rejected:** it depends on holdings semantics that are richer once
  long/short portfolios exist (Candidate B); building exposure analytics *before*
  the portfolio-construction layer that motivates them is premature and would
  likely be reworked. Defer until after a portfolio-construction phase.

### Candidate F — Synthetic benchmark / index-construction layer *(REJECTED — redundant)*
- **Adds:** a declarative cap-/equal-weight index builder producing a benchmark
  return series.
- **Consumes:** Phase 9/10/11.
- **Why rejected:** **duplicates existing capability** — Phase 15/17 already accept
  "a benchmark that is itself a sealed backtest," and an equal-weight backtest is
  already expressible in Phase 12. Adds a parallel path to something the system
  already does. Rejected as redundant.

**Rejected, in one line each:** B (modifies Phase 12 — defer to its own gated
phase), C (analytics-family refinement — too narrow), D (Phase 15 extension — not
its own phase), E (premature — needs portfolios first), F (redundant with the
sealed-backtest-as-benchmark convention).

---

## 4. Repository findings (authoritative, from the current tree)

- **Five consecutive pure-consumer/sibling phases (13–17)** establish the template
  Phase 18 follows: a `Workspace`-wired lazy engine, a declarative
  content-addressed `*Specification`, resolve/verify → compute → seal → write-once
  `ResearchRecord` to the shared `<root>/research/sha256-<hex>.json` sidecar.
- **Shared sidecar contract** (`src/quantforge/factors/store.py`): the
  `@runtime_checkable ResearchRecord` protocol requires exactly
  `research_result_id: str` (property) and `to_dict() -> dict`. `write()` is
  **write-once / byte-identical-idempotent / fail-closed** (a differing payload
  under the same id raises `FactorConsistencyError`); `read_as(id, from_dict)` is
  the generic decoder; `has(id)` the existence check. File naming slugifies
  `sha256:…` → `sha256-….json`. **A new record only needs those two members to
  ride the same store — no store change.**
- **Phase 16 forward-return / pairing machinery** (`diagnostics/engine.py`) already
  does exactly what Phase 18's data step needs: per-`T` universe build
  (`build_as_of`), PIT signal read (`panel_across(..., as_of=T)`), PIT-gated
  adjusted forward return over `[T, T+h]` trading days, and fail-closed coverage
  accounting. Phase 18 reuses this shape; the only new step is the per-date
  regression and cross-date aggregation.
- **Phase 17 exact-`Decimal` OLS** (`attribution/stats.py`) implements the normal
  equations via LDLᵀ (`_ldl`, `_ldl_solve`, `_inverse_diagonal`) with an **exact
  zero-pivot test** (no float tolerance, no NumPy). Phase 18's per-date regression
  is the same linear algebra with a cross-member design matrix; the solver is
  reusable (see AG-6).
- **Composition surfaces confirmed:**
  - `UniverseBuilder.build_as_of(spec, as_of, *, classifications=()) -> ConstructionResult`.
  - `PanelEngine.panel_across(metric_key, universe, axis, as_of, *, derivation=None) -> PitPanel`
    (matrix cells never dropped; `UNDEFINED` preserved with reason).
  - `PriceEngine.adjusted_series_as_of(security_id, axis, as_of, *, field=CLOSE, adjustment=None) -> PitPriceSeries`
    and `price_as_of(...) -> PitPrice`; `dataset_version_for(security_id) -> MarketDatasetVersion`.
  - Fundamentals key on `company_id` (`cik:`), prices on `security_id`
    (`cik:<CIK>#class:<class>`), joined via `Instrument.company_id`.
- **Identity/Decimal discipline** (uniform across 13–17): `sha256:` prefix,
  `_SEP = "\x00"` NUL-join, canonical JSON (`sort_keys=True, ensure_ascii=False,
  separators=(",",":")`), `sha256_hex` from `quantforge.sec.artifacts`; all
  arithmetic under `Context(prec=34, rounding=ROUND_HALF_EVEN)` applied via
  explicit `localcontext`; `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN
  \x00formula=<stats>/1")`; `<x>_engine_version_id = sha256(code_version \x00
  config_hash)`.
- **`StatValue` UNDEFINED pattern** is copied (not shared) into each sibling's
  `model.py`: `status ∈ {KNOWN, UNDEFINED}` with exactly one of `value: str |
  None` / `reason: <X>UndefinedReason | None` populated; closed key/reason sets.
- **Version state (documented discrepancy — do not fix now).** Git tags exist
  through `v0.14.0`. The task's authoritative mapping is Phase 15→v0.12.0,
  Phase 16→**v0.13.0**, Phase 17→v0.14.0. However the **README status table**
  labels Phase 15 as `v0.11.0`, Phase 16 as `v0.12.0`, skips `v0.13.0`, and labels
  Phase 17 as `v0.14.0`; the Phase 17 locked doc (D7) likewise states "Phase 16 is
  v0.12.0." This is a pre-existing label drift in `README.md` / the Phase 17 doc.
  All sources agree Phase 17 = `v0.14.0`, so Phase 18 = **`v0.15.0`** regardless.
  The README table drift should be corrected in a docs pass (recorded in §12);
  **not fixed in this phase.**
- **`strategy_version` is a reserved-but-unused seam** across factor/panel/price
  records — irrelevant to Phase 18 (Phase 18 seals its own record; it does not
  need to be cited by a strategy).
- **No source bug found** that must be fixed to understand this design.

---

## 5. Architecture

Established pattern (adopted verbatim; the repository proves it is correct for a
sibling diagnostic layer):

```
declarative CrossSectionalRegressionSpecification   (content-addressed request)
    → Workspace.crosssection_engine (lazy)           (composition root)
        → resolve universe @T / read PIT signals @T / read forward returns   (compose 9/10/11)
        → re-verify BOTH corpus pins (XS-1, fail closed)
        → per-date exact-Decimal OLS across members → γ_T                     (compute)
        → aggregate premia + FM t-stats across valid dates                    (compute)
        → seal CrossSectionalRegression (result_hash over ordered cells)      (seal)
        → ResearchResultStore.write(...)  write-once to shared sidecar        (persist)
```

### Package / module structure (new package `src/quantforge/crosssection/`)
Mirrors the Phase 16/17 layout exactly:
- `errors.py` — `CrossSectionError → CrossSectionConfigurationError, CrossSectionConsistencyError`.
- `version.py` — `CROSSSECTION_SPEC_VERSION`, `CROSSSECTION_ENGINE_VERSION`,
  `CROSSSECTION_FORMULA_VERSION`, `CROSSSECTION_RESULT_FORMAT_VERSION`,
  `default_decimal_context()`, `crosssection_engine_version_id`.
- `identity.py` — `_SEP`, domain tag `crosssection/1`, `_canonical_json`,
  `crosssection_result_hash(cells)`, `crosssection_id(...)`.
- `model.py` — `CrossSectionStatus`, `CrossSectionUndefinedReason`, `StatValue`
  (copied pattern), `FactorSpec` (one `(metric_key, MetricPeriod, label)`),
  `PerDateCoefficients`, `PremiumEstimate`, `CoverageSummary`, `DateCoverage`.
- `spec.py` — `FactorSpec`, `CrossSectionalRegressionSpecification`.
- `result.py` — `CrossSectionalRegression` (the `ResearchRecord`).
- `stats.py` — per-date OLS (reusing/promoting the Phase 17 LDLᵀ primitives per
  AG-6) + Fama–MacBeth aggregation.
- `engine.py` — `CrossSectionalRegressionEngine`.
- `__init__.py` — re-exports `CrossSectionalRegressionSpecification`,
  `CrossSectionalRegression`, `FactorSpec`.

### Public API
```python
# spec.py
@dataclass(frozen=True, slots=True)
class FactorSpec:
    metric_key: str
    period: MetricPeriod
    label: str | None = None  # display only; identity uses ordinal position


@dataclass(frozen=True, slots=True)
class CrossSectionalRegressionSpecification:
    name: str
    factors: tuple[
        FactorSpec, ...
    ]  # ordered, 1..K_MAX; order is semantic (never sorted)
    universe: UniverseSpecification  # Phase 9 declarative request
    schedule: RebalanceSchedule  # Phase 12 as_of instants (evaluation dates T)
    forward_horizon: str  # r"^[0-9]+d$"  (trading-day horizon, Phase 16 form)
    dataset_version_id: str  # fundamentals corpus pin
    market_dataset_version_id: str  # market corpus pin
    include_intercept: bool = True  # γ₀ term (default on)
    spec_version: str = CROSSSECTION_SPEC_VERSION  # "crosssection/1"


# engine.py — reached via Workspace.crosssection_engine
class CrossSectionalRegressionEngine:
    def __init__(self, workspace: Workspace) -> None: ...
    def estimate(
        self, spec: CrossSectionalRegressionSpecification
    ) -> CrossSectionalRegression: ...
```

`estimate` is the single entry point (the `compute`/`evaluate`/`attribute`
analog). It composes the Phase 9 universe builder, Phase 10 panel engine, and
Phase 11 price engine through their public accessors; it re-resolves nothing and
duplicates no resolution logic.

### Workspace integration
Additive, identical to the Phase 16/17 pattern:
- add `self._crosssection_engine: object | None = None` in `__init__`;
- add a lazy cached `crosssection_engine` `@property` importing
  `CrossSectionalRegressionEngine` on first use (cycle-free), constructed from
  `self`. No other `Workspace` change.

### Identity model
`crosssection_id` folds, NUL-joined, in this exact order (domain tag first):
1. `"crosssection/1"` (domain)
2. `crosssection_engine_version_id`
3. `name`
4. `spec_version`
5. `_canonical_json` of the **ordered** factor descriptors
   `[(metric_key, period_key), …]` — **ordered array, never sorted** (factor order
   is semantic, as in Phase 17 `factor_ids`)
6. `universe.specification_id`
7. `schedule.schedule_id`
8. `str(horizon_days)`
9. `str(include_intercept)` (`"True"`/`"False"`)
10. `dataset_version_id`
11. `market_dataset_version_id`
12. `result_hash` (see below)

No annualization convention enters identity (the FM t-stat is per-period; there is
no `periods_per_year` — the Phase 16 §1.1 resolution). `research_result_id` is a
property aliasing `crosssection_id`. The id is a **derived property**,
recomputed from the embedded spec + refs + `result_hash` on every access, so a
tampered stored id is ignored (the Phase 15/16/17 discipline).

### Result model
```python
@dataclass(frozen=True, slots=True)
class CrossSectionalRegression:  # satisfies ResearchRecord
    crosssection_engine_version_id: str
    crosssection_spec: dict  # embedded spec.to_dict()
    boundary_kind: str  # "pit"  (documents the SIGNAL side only; XS-2)
    dataset_version_id: str
    market_dataset_version_id: str
    schedule_id: str
    factor_labels: tuple[str, ...]  # ordered, ["alpha"?, factor_1..factor_K]
    per_date: tuple[
        PerDateCoefficients, ...
    ]  # one per VALID evaluation date, schedule order
    premia: tuple[PremiumEstimate, ...]  # ordered, aligned to factor_labels
    coverage: CoverageSummary
    formula_version: str
    result_hash: str
```
- `PerDateCoefficients(as_of: str, n_members: int, coefficients: tuple[(label, StatValue), …], r_squared: StatValue)`
  — the per-date `γ_T` (each coefficient a `StatValue`; a singular per-date design
  yields all-`UNDEFINED` for that date, recorded, never dropped silently).
- `PremiumEstimate(label: str, mean: StatValue, std_error: StatValue, t_stat: StatValue, n_valid_dates: int)`
  — the aggregated Fama–MacBeth premium per coefficient.
- `CoverageSummary(per_date: tuple[DateCoverage, …], total_eligible, total_dropped_for_signal, total_dropped_for_return, total_dropped_for_singular_date)`;
  `DateCoverage(as_of, resolved_members, eligible, dropped_for_signal, dropped_for_return, regression_status)`.

`result_hash = crosssection_result_hash(_output_cells(...))` = sha256 over ordered
block-tagged cells: `per_date` block (each `{"block":"per_date", …}`, schedule
order, **not re-sorted**) → `premia` block (`{"block":"premia", …}`, factor order).
Coverage counts and `r_squared` per date are included in the seal (they are
result-changing facts), following Phase 16's inclusion of per-date diagnostics.
`boundary_kind = "pit"` documents that the **signal side** was PIT-eligible; the
record is **not** a `Pit*` type and exposes **no as-of accessor** (XS-2).

### Versioning model
`CROSSSECTION_ENGINE_VERSION = "crosssection-engine/1"`,
`CROSSSECTION_FORMULA_VERSION = "crosssection-stats/1"`,
`CROSSSECTION_SPEC_VERSION = "crosssection/1"`,
`CROSSSECTION_RESULT_FORMAT_VERSION = "crosssection-result/1"` (a container concern
— **not** folded into `crosssection_id`, per the 13–17 precedent). Any formula or
code change bumps a version → a different `crosssection_id`. Release **`v0.15.0`**.

### Persistence & serialization strategy
Write-once to the existing `ResearchResultStore` (`<root>/research/`), reached via
`workspace.research_result_store` (the engine exposes a `research_store` property,
overridable in tests, exactly as the siblings do). No new store, no database.
`to_dict()` emits canonical `sort_keys=True` JSON and includes both
`crosssection_id` and its `research_result_id` alias; `from_dict()` is the
fail-closed byte-identical inverse. Idempotent recompute is a no-op; a differing
payload under the same id fails closed via the store.

### Provenance strategy
The sealed record embeds the full declared spec (`crosssection_spec`), both corpus
pins, the schedule id, the engine/formula versions, and the complete per-date
coefficient panel + coverage — so the entire computation is reconstructible and
auditable from the record plus the two pinned corpora. Every value is a decimal
string or a `StatValue`; nothing is a copy of a raw financial value beyond the
derived statistics the phase itself computes.

### Deterministic behavior
No wall-clock, no RNG, no `id()`/iteration-order dependence (all set-valued inputs
are sorted; the ordered factor tuple and schedule order are preserved verbatim).
All arithmetic under the pinned `Decimal` context. Same spec + same pinned corpora
⇒ identical `crosssection_id`, per-date panel, and premia on any machine.

### Interaction with existing phases (summary; full table in §6)
- **Phase 9/10/11:** COMPOSES (read-only, through public accessors).
- **Phase 16:** COMPOSES-adjacent (reuses the forward-return/pairing shape; shares
  no code unless a helper is promoted — AG-6). Distinct output.
- **Phase 17:** COMPOSES-adjacent (reuses the exact-`Decimal` OLS primitives per
  AG-6). Distinct regression axis.
- **Phase 12/13/14/15:** none (does not consume a `BacktestResult` or experiment).

---

## 6. Invariant / contradiction analysis

Classification of every meaningful interaction. `COMPOSES` = read-only reuse with
no new tension; `CONSTRAINS` = an existing invariant dictates the design;
`TENSION` = a resolvable design pressure; `CONTRADICTION` = an unresolvable
conflict with an invariant.

| # | Interaction | Class | Analysis |
| --- | --- | --- | --- |
| 1 | **Point-in-time correctness** (inv. 6, 29) | CONSTRAINS | The signal side reads only PIT-eligible-at-`T` values via `panel_across(as_of=T)`; no post-`T` fundamentals enter a signal. Codified as **XS-3**. |
| 2 | **PIT vs REVISED / ex-post separation** (inv. 27, 28) | CONSTRAINS | The **forward** return is realized post-`T` and is therefore *not* a PIT value; the record is not a `Pit*` type and exposes no as-of accessor — it can never feed an as-of-`T` computation. Codified as **XS-2** (direct SD-2 / FA-2 / inv. 28 analog). |
| 3 | **Corpus pinning** (BT-1, SD-1, inv. 19) | CONSTRAINS | Both `dataset_version_id` and `market_dataset_version_id` are declared, re-derived, and verified; mismatch fails closed; a changed corpus yields a different `crosssection_id`. Codified as **XS-1**. |
| 4 | **Survivorship handling** (Phase 9) | COMPOSES | The universe is rebuilt at each `T` through Phase 9 `build_as_of`, inheriting Phase 9's survivorship-correct membership; no delisted-name leakage is introduced. |
| 5 | **Content-addressed identity** (inv. 19) | COMPOSES | `crosssection_id` folds the request, both pins, engine/formula version, and the answer's `result_hash`; standard discipline. |
| 6 | **Deterministic hashing / serialization** (inv. 13, 18, 21) | COMPOSES | `sha256:` + NUL-join + canonical JSON; ordered inputs preserved, set inputs sorted. |
| 7 | **Write-once persistence** (Phase 8 store) | COMPOSES | Reuses the write-once, byte-identical-idempotent, fail-closed sidecar; no new store. |
| 8 | **Provenance** (inv. 3) | COMPOSES | The record embeds spec + pins + versions + full per-date panel; fully reconstructible. |
| 9 | **Fail-closed behavior** (SD-4, FA-4) | CONSTRAINS | A member lacking any of the `K` PIT signals at `T` or a forward return is excluded and counted; a singular/degenerate per-date design is a recorded `UNDEFINED` date, never dropped or fabricated. Codified as **XS-4**. Configuration defects (unknown metric, `n < K + 2` never achievable, no valid dates) raise. |
| 10 | **ResearchRecord reuse** | COMPOSES | Record exposes `research_result_id` + `to_dict`; nothing else required. |
| 11 | **Engine-version conventions** | COMPOSES | `config_hash` over `prec=34/ROUND_HALF_EVEN/formula`; new package = new domain tag, no collision. |
| 12 | **Decimal conventions** (no float) | CONSTRAINS | All OLS + aggregation under `Context(prec=34, ROUND_HALF_EVEN)`; the exact-`Decimal` LDLᵀ solver (exact zero-pivot test) is reused — no float, no NumPy. |
| 13 | **Phase 15 benchmark semantics** | (none) | Phase 18 consumes no benchmark and no `BacktestResult`; no interaction. |
| 14 | **Phase 16 forward-diagnostic semantics** | COMPOSES + **TENSION (resolved)** | Reuses the forward-return / coverage shape and the SD-1..4 disciplines (as XS-1..4). *Tension:* does Phase 18 **duplicate** Phase 16? **Resolved:** Phase 16 is univariate rank/linear IC + quantile buckets of **one** signal; Phase 18 is multivariate OLS of forward returns on **K** signals producing regression **premia** (return units) + FM t-stats. Different statistic, different output object, different question (correlation vs pricing). Not a duplication. |
| 15 | **Phase 17 ex-post attribution semantics** | COMPOSES + **TENSION (resolved)** | Reuses the exact-`Decimal` OLS primitives. *Tension:* does it duplicate Phase 17? **Resolved:** Phase 17 regresses **one portfolio's return series over time** on `K` factor-**portfolio** return series (time-series axis, `n` = periods). Phase 18 regresses **many members' forward returns at each date** on `K` **characteristics** (cross-sectional axis, `n` = members), once per date, then aggregates across dates. Orthogonal regression axes; distinct outputs. Not a duplication. |
| 16 | **Undefined-value semantics** | CONSTRAINS | Every undefinable statistic (per-date singular design, zero regressand variance, insufficient members, insufficient valid dates, zero cross-date variance for a premium's std error) is a first-class `UNDEFINED` `StatValue` with a closed reason — never `NaN`/`Inf`/`0`/divide-by-zero. |
| 17 | **Comparison/analytics/reporting semantics** | (none / future) | No new comparison; a future reporting phase *may* reference this record, but no reporting scope is reserved here (the Phase 17 Open-Q6 precedent). |

**Contradiction analysis:** none found. The two substantive tensions (rows 14, 15
— "is this Phase 16 or Phase 17 again?") are resolved by the regression-axis
matrix in §2: cross-sectional-multivariate is a genuinely empty cell today. No
existing invariant is weakened; XS-1..4 are strict additions modeled on SD-1..4
(they "do not weaken 1–30").

---

## 7. Approval-gated decisions

Each decision lists the recommended option first, then alternatives, then why it
matters.

**AG-1 — Package / type naming.**
- *Recommended:* package `crosssection`; `CrossSectionalRegressionSpecification`,
  `CrossSectionalRegression`, `CrossSectionalRegressionEngine`, `FactorSpec`.
- *Alternatives:* package `premia` (`FactorPremia*`); package `famamacbeth`;
  package `xsreg`.
- *Why it matters:* names are load-bearing for imports and the public API surface;
  the domain tag (`crosssection/1`) and engine-version-id string derive from the
  choice and are baked into every `crosssection_id`. Changing it later is a
  breaking identity change.

**AG-2 — Per-date time-series standard error convention (the FM aggregation).**
- *Recommended:* **plain (iid) Fama–MacBeth** standard error
  `se(γ̄_k) = popStd(γ_k,·)/√M` (population std over valid dates), t = `γ̄_k/se`.
- *Alternatives:* Newey–West / HAC-adjusted FM standard errors (a lag choice);
  sample (n−1) std.
- *Why it matters:* it is the headline inferential statistic. Newey–West is a
  standard refinement but introduces a lag-selection parameter and more linear
  algebra; Phase 17 D5 **explicitly deferred HAC/robust estimators**, so deferring
  it here keeps the sibling consistent. The std convention (population vs sample)
  must be pinned into `formula_version`.

**AG-3 — Per-date regression weighting.**
- *Recommended:* **OLS (equal-weight members)** in v1.
- *Alternatives:* WLS (e.g., value-weighted by a market-cap metric); GLS.
- *Why it matters:* weighting changes every coefficient and the interpretation of
  the premium. WLS would require a weight metric (another PIT signal) and more
  identity inputs. Recommend deferring, consistent with Phase 17's
  classical-`(XᵀX)⁻¹`-only scope.

**AG-4 — Signal preprocessing (standardization) per date.**
- *Recommended:* **raw signals, no standardization** in v1 (do not smuggle a
  transform; the Phase 16 §1.1(3) "no period-resolution rule smuggled in"
  discipline).
- *Alternatives:* cross-sectional z-score per date; winsorization/trimming of
  outliers; rank-transform (which would make it a rank-FM hybrid, overlapping
  Phase 16).
- *Why it matters:* standardization changes coefficient scale/interpretation and
  would fold a new closed-vocabulary knob into identity. Keep v1 minimal;
  standardization is a clean future closed-vocabulary extension.

**AG-5 — Minimum-cross-section and minimum-valid-dates thresholds.**
- *Recommended:* per-date degrees-of-freedom guard `n_members ≥ K + include_intercept + 1`
  (the Phase 17 `n ≥ K + 2` analog) — a date below it is a recorded `UNDEFINED`
  date (XS-4), **not** a raise; and a **minimum valid-dates** guard `M ≥ 2` for the
  aggregation — below it the *run* raises `CrossSectionConfigurationError` (the
  Phase 16 `_MIN_PAIRS` / Phase 15 `_MIN_PERIODS` analog, so an all-`UNDEFINED`
  record is never sealed).
- *Alternatives:* raise on any singular per-date design; seal an all-`UNDEFINED`
  record instead of raising.
- *Why it matters:* it determines when the layer fails closed with a configuration
  error vs seals a partially-`UNDEFINED` record. Must be pinned and tested.

**AG-6 — Reuse vs duplicate the exact-`Decimal` OLS solver.**
- *Recommended:* **promote** the Phase 17 LDLᵀ primitives (`_ldl`, `_ldl_solve`,
  `_inverse_diagonal`, exact zero-pivot test) into a **shared internal
  linear-algebra helper** (e.g. `src/quantforge/_linalg/decimal_ols.py`) that both
  `attribution/stats.py` and `crosssection/stats.py` import — avoiding the
  duplication the task warns against.
- *Alternatives:* (a) copy the solver into `crosssection/stats.py` (duplication,
  but zero change to Phase 17); (b) `crosssection/stats.py` imports the private
  functions from `attribution/stats.py` directly (creates a cross-package
  dependency on private names).
- *Why it matters:* this is the **one place Phase 18 could touch Phase 17 source.**
  Promotion is a pure refactor that must not change Phase 17's numeric output or
  `attribution_engine_version_id` (the extracted code must be byte-for-byte
  behavior-preserving; verified by the existing Phase 17 test suite staying
  green). If the maintainer prefers **zero** prior-phase edits, choose alternative
  (a) — duplication — accepting the task's "avoid duplicating functionality" note
  as the lesser concern. **Recommend promotion, gated on Phase 17 tests remaining
  green and its engine-version-id unchanged.**

**AG-7 — Forward-return definition reuse.**
- *Recommended:* reuse Phase 16's **exact** `"<n>d"` trading-day adjusted forward
  return (same horizon grammar, same PIT-gated adjusted price view, same
  drop-on-missing/multi-share-class rule).
- *Alternatives:* calendar-day or step-based horizons (Phase 16 §22 deferred
  these); log returns.
- *Why it matters:* identical forward-return semantics keep Phase 18 commensurable
  with Phase 16 diagnostics and avoid a second, divergent return definition in the
  codebase.

**AG-8 — Intercept default.**
- *Recommended:* `include_intercept = True` (report γ₀), folded into identity.
- *Alternatives:* default off; force on.
- *Why it matters:* the intercept changes every slope and is a legitimate modeling
  choice; it must be an explicit, identity-folded field.

**AG-9 — Factor count bound `K_MAX`.**
- *Recommended:* `K_MAX = 8` (reuse the Phase 17 bound).
- *Alternatives:* a different cap; unbounded.
- *Why it matters:* bounds the design-matrix size and keeps determinism/perf
  predictable; consistency with Phase 17 is clean.

**AG-10 — Release version.**
- *Recommended:* **`v0.15.0`** (Phase 17 = v0.14.0).
- *Alternatives:* none with repository support.
- *Why it matters:* see §9. Also flags the README/Phase-17-doc version-label drift
  for a separate docs correction (not fixed in this phase).

---

## 8. Implementation scope (only if approved)

### New files — `src/quantforge/crosssection/`
- `src/quantforge/crosssection/__init__.py`
- `src/quantforge/crosssection/errors.py`
- `src/quantforge/crosssection/version.py`
- `src/quantforge/crosssection/identity.py`
- `src/quantforge/crosssection/model.py`
- `src/quantforge/crosssection/spec.py`
- `src/quantforge/crosssection/result.py`
- `src/quantforge/crosssection/stats.py`
- `src/quantforge/crosssection/engine.py`
- *(if AG-6 = promote)* `src/quantforge/_linalg/__init__.py`,
  `src/quantforge/_linalg/decimal_ols.py` — shared exact-`Decimal` OLS primitives.

### Existing files — additive changes only
- `src/quantforge/workspace.py` — add `self._crosssection_engine = None` and the
  lazy `crosssection_engine` property (no other change).
- `src/quantforge/__init__.py` — re-export
  `CrossSectionalRegressionSpecification`, `CrossSectionalRegression`, `FactorSpec`
  and add to `__all__` (engine reached via `Workspace`, never re-exported —
  the sibling convention).
- *(only if AG-6 = promote)* `src/quantforge/attribution/stats.py` — replace its
  private LDLᵀ helpers with imports from `_linalg.decimal_ols`, **behavior- and
  byte-identical**, Phase 17 tests must stay green and
  `attribution_engine_version_id` unchanged. **No other prior-phase file is touched.**

### Tests — `tests/crosssection/`
- `tests/crosssection/__init__.py`, `builders.py` (fixtures: a small deterministic
  multi-member universe, panel signals, price forward returns).
- `test_spec.py` — validation (empty name; 1..K_MAX factors; ordered factors never
  sorted; duplicate factor rejection; horizon grammar; required pins;
  `to_dict`/`from_dict` round-trip; `include_intercept` folded).
- `test_identity.py` — fold order & sensitivity: changing any factor, factor
  **order**, universe/schedule/horizon/intercept/either pin ⇒ different
  `crosssection_id`; determinism across runs; tampered stored id ignored.
- `test_stats.py` — exact-`Decimal` per-date OLS against hand-computed small cases;
  FM aggregation (mean/std/√M/t); singular design → `UNDEFINED`; zero-variance
  regressand → `UNDEFINED`; perfect fit; **cross-check** a single-factor case's
  premium sign/magnitude against Phase 16 IC direction on the same data.
- `test_result.py` — seal, `result_hash` cell ordering (per_date schedule order,
  premia factor order), byte-identical round-trip, `research_result_id` alias.
- `test_engine.py` — end-to-end over builders: corpus-pin re-verification &
  fail-closed mismatch (XS-1); PIT signal read at `T` (XS-3, no post-`T` leakage);
  forward-return-not-PIT / no as-of accessor (XS-2); fail-closed coverage
  (dropped-for-signal / dropped-for-return / singular-date) (XS-4); `M < 2` raises;
  write-once idempotency and differing-payload fail-closed; not-a-spec argument
  raises.
- `tests/test_smoke.py` — add an import/roundtrip smoke assertion (additive).

### Documentation (only after implementation is green — **not** in this phase)
- **Locked specification:** `docs/phase18-cross-sectional-regression-locked.md`
  (the normative spec, XS-1..4, decision table, identity fold, test matrix).
- **README.md:** add a capability bullet + a `v0.15.0` status row; and (separately)
  correct the pre-existing version-label drift in the table.
- **ARCHITECTURE.md:** add a "Cross-sectional factor-return regression" component
  row; extend the implemented-layers note.
- **docs/index.md:** add a Phase 18 entry.
- **docs/data-model.md:** add **XS-1..XS-4** to §12 as an additive block
  ("do not weaken 1–30"), mirroring the SD-1..4 block. *(Design-only doc; not
  edited in this phase.)*

---

## 9. Out of scope (strict)

Deferred to later, explicitly-labelled phases; Phase 18 must not absorb any of
these:
- **Long/short / dollar-neutral / quantile-spread portfolio construction**
  (Candidate B — modifies Phase 12; its own gated phase).
- **WLS / GLS / robust / HAC (Newey–West) standard errors** (AG-2/AG-3; the Phase
  17 D5 deferral, extended here).
- **Signal standardization / winsorization / rank transforms / neutralization**
  (AG-4; a future closed-vocabulary extension).
- **Rolling/windowed premia**, sub-period splits, regime conditioning.
- **Multiple-testing / data-mining corrections** across many signals (Candidate C).
- **Calendar/step forward-horizon forms** and multi-share-class forward returns
  (the Phase 16 §22 deferrals, inherited).
- **A REVISED scope** for the regression (reserved for a future explicitly-labelled
  phase, per the Phase 15/17 precedent). v1 is PIT-signal / ex-post only.
- **Reporting integration** (no `ReportSpecification` scope reserved; Phase 17
  Open-Q6 precedent).
- **Any change to a prior phase's identity, versions, or data** beyond the
  behavior-preserving AG-6 solver promotion (if approved).
- **Batch/multi-subject runs** (one spec = one regression study; batching is a
  thin future loop).

---

## 10. Versioning

**Recommendation: `v0.15.0`.** Sequence: Phase 14 → v0.11.0, Phase 15 → v0.12.0,
Phase 16 → v0.13.0, Phase 17 → v0.14.0, **Phase 18 → v0.15.0**. Git tags confirm
existence through v0.14.0; all sources agree Phase 17 = v0.14.0. The package
`__version__` string stays `"0.0.0"` (versioning is by content-addressed ids, per
the Phase 17 D7 precedent). No repository evidence supports a different number.
*(Note the pre-existing README/Phase-17-doc version-label drift documented in §4;
correcting it is a separate docs task, not part of this phase.)*

---

## 11. Open questions

1. **AG-6 direction** — promote the shared Decimal OLS helper (one behavior-
   preserving Phase 17 edit) vs duplicate (zero prior edit)? *Recommend promote.*
2. **AG-2** — plain FM std error in v1 with HAC deferred? *Recommend yes.*
3. **Per-date `r_squared` in the seal** — include (recommended, result-changing
   provenance) or omit to keep the seal minimal?
4. **Factor label policy** — auto-label `factor_1..factor_K` (identity by ordinal,
   like Phase 17) with an optional display `label`, or require explicit labels?
   *Recommend auto-label; display-only user label ignored by identity.*
5. **Should a premium's std error use population or sample std of the per-date
   coefficients?** *Recommend population, pinned in `formula_version` (AG-2).*

---

## 12. Recommended decisions (summary)

- Capability: **cross-sectional factor-return regression (Fama–MacBeth premia)**.
- Package `crosssection` (AG-1); `estimate(spec) -> CrossSectionalRegression`.
- Plain FM std errors, OLS, raw signals, intercept-on, `K_MAX = 8`, `M ≥ 2`
  (AG-2/3/4/5/8/9).
- Promote the shared exact-`Decimal` OLS solver into `_linalg` (AG-6), gated on
  Phase 17 tests green and its engine-version-id unchanged.
- Reuse Phase 16's forward-return definition verbatim (AG-7).
- Add invariants **XS-1..XS-4** (SD-1..4 analogs) to §12 as a strict additive
  block.
- Release **v0.15.0**; fix the README version-label drift in a separate docs pass.

---

## 13. Final implementation boundary

If approved, Phase 18 will:
- **create only** the `src/quantforge/crosssection/` package (+ optional
  `src/quantforge/_linalg/` if AG-6 = promote) and `tests/crosssection/`;
- **additively edit only** `src/quantforge/workspace.py`,
  `src/quantforge/__init__.py`, `tests/test_smoke.py`, and — only if AG-6 =
  promote — `src/quantforge/attribution/stats.py` (behavior-preserving);
- **touch no other prior-phase source**, add **no** runtime dependency, **no**
  database, **no** RNG, **no** float, **no** wall-clock, **no** Python-callback
  escape hatch;
- seal a write-once `CrossSectionalRegression` `ResearchRecord` to the existing
  shared sidecar; and
- produce the locked spec + doc/README/ARCHITECTURE/index/data-model edits **only
  after** the implementation is green — never in this proposal step.

No implementation begins until the maintainer explicitly approves this proposal.
```
