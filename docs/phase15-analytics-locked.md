# Phase 15 — Performance & Benchmark-Relative Analytics (LOCKED)

> **Status:** Locked normative specification. Decisions **D1–D11** were approved as
> recommended; this document is the source of truth for the implementation and
> supersedes the recommendations in
> [phase15-proposal.md](phase15-proposal.md). Every conditional reference in the proposal
> ("recommended", "if the reviewer prefers…") is resolved here to a committed decision.
>
> **One-line thesis:** Phase 15 adds a deterministic, content-addressed **risk &
> benchmark-relative analytics** layer strictly *above* Phase 12, a **pure consumer** of
> already-sealed, PIT-correct `BacktestResult`s. It computes the statistic family the
> Phase 12 `stats.py` docstring explicitly deferred — downside/drawdown risk, historical
> VaR/CVaR, return-distribution moments, and (against a **benchmark that is itself a
> sealed backtest**) tracking error, information ratio, capture, and single-factor OLS
> alpha/beta — under the same pinned `Decimal` context, sealing the answer as a new
> `PerformanceAnalytics` `ResearchRecord` to the existing sidecar. It introduces **no**
> new data source, no new PIT resolution, no benchmark ingestion, no runtime dependency,
> and no database, and it computes **no** value from anything not already sealed and
> PIT-eligible.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D1** | The computed analytics **is** a `ResearchRecord` (`PerformanceAnalytics`) persisted write-once to the existing `<root>/research/sha256-<hex>.json` sidecar. It implements the Protocol (`research_result_id` alias + deterministic `to_dict`/`from_dict`). No new store, no new format, no database. |
| **D2** | Phase 15 **adds only what Phase 12 does not already seal.** Return / volatility / Sharpe / max-drawdown / turnover are **not** recomputed; the absolute block is exactly the deferred family. A reader joins to the subject's sealed `PerformanceStatistics` for the already-sealed numbers. No second, drifting source of truth. |
| **D3** | A **benchmark is another sealed `BacktestResult`.** No index-price ingestion, no fabricated series, no caller-supplied returns. A market proxy is expressed as an equal-weight buy-and-hold backtest. Relative statistics require subject and benchmark to share `schedule_id`, equal `period_returns` length, **and** a commensurable `backtest_engine_version_id`, enforced fail-closed. |
| **D4** | **Single-factor OLS alpha/beta is in scope**, computed with closed-form scalar `Decimal` arithmetic only (`beta = cov(r_p, r_b)/var(r_b)`, `alpha = mean(r_p) − [rf + beta·(mean(r_b) − rf)]`). No matrix, no linear-algebra dependency. Multi-factor regression is explicitly deferred to a future phase. |
| **D5** | Undefinable statistics are **first-class `UNDEFINED` values carrying a reason** — never a raise, never a fabricated `0`, never `NaN`/`Inf`, never a silent omission, never a divide-by-zero. Every statistic is present as KNOWN-or-UNDEFINED. |
| **D6** | The record has **one id.** `analytics_id` folds the engine+formula+decimal-context version, the declared request, both referenced backtests' `result_hash`, and the sealed `result_hash` over the computed answer; `research_result_id` aliases it (mirrors `BacktestResult.backtest_id`). No separate definition/result split. |
| **D7** | VaR/CVaR is **historical, nearest-rank** (empirical quantile): for confidence `c`, `k = ceil((1-c)·n)`, `var` = the `k`-th smallest period return (signed), `cvar` = the mean of the `k` smallest. No interpolation, no distribution assumption, no bootstrapping/Monte-Carlo, no RNG. The quantile method is folded into `analytics-stats/1`. |
| **D8** | The **annualization convention** (`risk_free_per_period`, `periods_per_year`) is **folded into `analytics_id`.** Two analytics identical except for convention report distinctly-annualized numbers, so they are materially different and take distinct ids. |
| **D9** | A new numbered data-model invariant (**#31**) is **not** added to the `data-model.md` §12 registry in this phase. The "pure consumer, no new PIT resolution" property is upheld by §M/§G of the proposal and the existing PIT invariants (6–17); it is documented here (§4) as a Phase 15 property, not a new registry entry. *(The proposal's D9 recommended (a), subject to a documentation-registry policy call; the locked resolution is (b) — keep it a per-phase property, no registry edit.)* |
| **D10** | One analytics record covers **one subject (+ optional benchmark)**, not an experiment-wide batch. Batch analytics is a thin future loop over this primitive. |
| **D11** | Skewness / kurtosis are **population moments, excess kurtosis** (`skewness = μ₃/σ³`, `excess_kurtosis = μ₄/σ⁴ − 3`), matching `stats.py`'s population-volatility choice. The definition is folded into the formula version. |

### 1.1 Deviations from the proposal (disclosed)

Two implementation choices depart from the letter of the proposal; both are recorded here
for auditability.

1. **A seventh `AnalyticsUndefinedReason`, `ZERO_VARIANCE`, was added** beyond the six the
   proposal named (§J.3). Principle 5 / D5 require a first-class reason for *every* zero
   denominator; a **constant subject** return series has population variance 0, which makes
   `skewness`, `excess_kurtosis` (absolute block), and `correlation` (relative block)
   genuinely `0/0` — undefined, not zero (a constant series has no shape and no linear
   relationship). `ZERO_BENCHMARK_VARIANCE` names the benchmark-side zero denominator;
   `ZERO_VARIANCE` is its required subject-side companion. Without it those cells would have
   to fabricate a value or divide by zero, both forbidden. It is folded into the record like
   any other reason and changes no identity discipline.
2. **A canonicalization fix in `spec.py`.** The confidence / convention canonicalizer
   originally used `str(+parsed)`, which preserves trailing zeros, so `"0.95"` and `"0.9500"`
   did **not** fold to one string — contradicting the documented set-identity contract (D8,
   §L) that spelling never changes `analytics_id`. It now uses `format(parsed.normalize(),
   "f")` (`_canonical_form`), which strips trailing-zero/exponent differences and forces
   fixed-point (so a normalized value never lands in scientific notation). This is a
   correctness fix to honor the stated contract; it folds into `analytics_id` via the
   embedded request.

---

## 2. Architecture (locked)

Phase 15 is a thin analytics layer strictly *above* Phase 12, a **pure consumer** of
already-sealed, PIT-correct `BacktestResult`s. It follows the extension recipe every prior
phase uses: versioned immutable request object → fail-closed engine reached from
`Workspace` via a lazy, cycle-free `@property` → distinct result type → content-addressed
identity with fresh domain tags → data conditions recorded as first-class values, defects
raised → compute-on-demand with the shared write-once sidecar. Unlike Phases 13/14 (which
*rank* and *reference* sealed statistics), Phase 15 **computes new numbers** — but only
those Phase 12 deferred, never those it already seals.

```
                 AnalyticsSpecification            (declarative request, content-addressed)
                          |
                          v
   Workspace.analytics_engine  --->  AnalyticsEngine.compute(spec)
                          |                 |
                          |   resolve subject (+ optional benchmark) from the shared sidecar
                          |   verify each result_hash (fail closed on absent / drift / non-PIT)
                          |   verify commensurability (same schedule_id & length & engine
                          |   version; surface corpus pin_mismatch, never raise)
                          v                 v
        compute absolute (+ relative) + VaR statistics under the pinned Decimal context
        (UNDEFINED-preserving; no float; no RNG; no wall-clock)
                          |
                          v
             PerformanceAnalytics (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
             store.read_as(id, PerformanceAnalytics.from_dict)   (typed, byte-identical round-trip)
```

**New package `src/quantforge/analytics/`** (mirrors `experiment/` / `report/`):

- `errors.py` — `AnalyticsError` → `AnalyticsConfigurationError`, `AnalyticsConsistencyError`.
- `identity.py` — `analytics_result_hash`, `analytics_id`. Fresh record domain tag
  `analytics/1`.
- `version.py` — `AnalyticsEngineVersion` (folds the pinned decimal context **and** the
  formula-method version `analytics-stats/1` into `config_hash`); `ANALYTICS_ENGINE_VERSION
  = "analytics-engine/1"`, `ANALYTICS_FORMULA_VERSION = "analytics-stats/1"`;
  `default_decimal_context()`. Mirrors `backtest/version.py`, extended with the formula knob.
- `model.py` — `AnalyticsStatus`/`AnalyticsUndefinedReason` vocabulary; the closed v1
  statistic key sets (`ABSOLUTE_KEYS`, `RELATIVE_KEYS`, `VAR_KEYS`); `StatValue` (a KNOWN
  decimal string **or** UNDEFINED+reason).
- `compute.py` — the pure statistic functions (`parse_returns`, `absolute_statistics`,
  `relative_statistics`, `var_statistics`). Pure; read no store; take decimal-string
  vectors + convention, return decimal strings / UNDEFINED cells.
- `spec.py` — `AnalyticsSpecification`, full construction-time validation;
  `ANALYTICS_SPEC_VERSION = "analytics/1"`.
- `result.py` — `ANALYTICS_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, `PerformanceAnalytics`
  (a `ResearchRecord` with `.seal`/`to_dict`/`from_dict`).
- `engine.py` — `AnalyticsEngine` (constructed from `Workspace`; composes
  `research_result_store` + `AnalyticsEngineVersion`): resolve → verify → compute → seal →
  write-once.
- `__init__.py` — package exports.

**The only edits to existing source** (both additive, neither altering any existing identity):

1. `workspace.py` — one lazy `analytics_engine` `@property` (+ its `self._analytics_engine
   = None` cache line), following the `experiment_engine` / `report_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of `AnalyticsSpecification` and
   `PerformanceAnalytics` (spec + result only; the engine is reached via `Workspace`).

**No edit to** `backtest/*` (including `stats.py`, `result.py`, `version.py`), `experiment/*`
(including `analysis.py`), `report/*`, `factors/store.py`, or any identity/version module of
a prior phase.

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
wall-clock, no RNG.

### 3.1 `AnalyticsSpecification` (declarative request)

```
AnalyticsSpecification(
    name: str,                                    # non-empty
    subject_id: str,                              # non-empty sealed backtest_id
    benchmark_id: str | None = None,              # a sealed backtest_id; None => absolute-only
    var_confidences: tuple[str, ...] = ("0.95",), # decimal strings, each strictly in (0,1)
    risk_free_per_period: str = "0",              # MAR / rf convention (decimal string, >= 0)
    periods_per_year: str = "1",                  # annualization convention (decimal string, > 0)
    spec_version: str = "analytics/1",
)
# derived at construction, never supplied:
sorted_var_confidences: tuple[str, ...]           # canonicalized, sorted, de-duplicated (a set)
```

Construction-time validation (fail closed, `AnalyticsConfigurationError`): empty `name`;
empty `subject_id`; `benchmark_id == subject_id` (a strategy is not its own benchmark);
empty `var_confidences`; a `var_confidence` that is non-string, non-decimal, non-finite,
`≤ 0`, `≥ 1`, or a duplicate by canonical form; non-string/non-decimal/non-finite/negative
`risk_free_per_period`; non-string/non-decimal/non-finite/non-positive `periods_per_year`;
empty `spec_version`. `var_confidences` is canonicalized (`_canonical_form` — trailing-zero
independent) and treated as a **set** for identity: order and duplicate spelling never
change the id. Reads no store, no wall clock. `to_dict()` emits `var_confidences` in its
sorted, canonical, de-duplicated form.

### 3.2 `PerformanceAnalytics` (implements `ResearchRecord`)

```
PerformanceAnalytics(
    analytics_engine_version_id: str,
    analytics_spec: dict[str, object],            # the full AnalyticsSpecification.to_dict()
    subject_ref: tuple[str, str],                 # (backtest_id, result_hash)
    benchmark_ref: tuple[str, str] | None,        # (backtest_id, result_hash) or None
    boundary_kind: str,                           # "pit" (v1 PIT-only; D10 discipline)
    schedule_id: str,                             # the shared schedule the returns align on
    periods: int,                                 # length of the return vector analysed
    absolute: tuple[tuple[str, StatValue], ...],  # sorted by key (ABSOLUTE_KEYS)
    relative: tuple[tuple[str, StatValue], ...],  # sorted by key (RELATIVE_KEYS); () when no benchmark
    var: tuple[tuple[str, StatValue, StatValue], ...],  # (confidence, VaR, CVaR), sorted by confidence
    risk_free_per_period: str,
    periods_per_year: str,
    dataset_version_ids: tuple[str, ...],         # distinct, sorted pins across subject(+benchmark)
    market_dataset_version_ids: tuple[str, ...],
    formula_version: str,                         # "analytics-stats/1"
    result_hash: str,                             # canonical JSON over the ordered computed outputs
)

# derived, never stored as state:
analytics_id        property -> sha256 folding engine version + spec identity
                                + referenced content hashes + result_hash
research_result_id  property -> alias of analytics_id  (the ResearchRecord key)
pin_mismatch        property -> True iff a benchmark is present AND >1 distinct pin appears
                                in either the fundamentals or the market dimension
```

- `StatValue` is the UNDEFINED-preserving cell: `StatValue.known("<decimal string>")` **or**
  `StatValue.undefined(<AnalyticsUndefinedReason>)`. Exactly one of `value`/`reason` is
  populated (enforced at construction). Never a bare float, never silently omitted.
- `to_dict()` keys (deterministic, `sort_keys=True`): `analytics_id`, `research_result_id`
  (alias so the generic reader keys correctly), and every field above. A KNOWN cell emits
  `value` only; an UNDEFINED cell emits `reason` only.
- `from_dict` is the fail-closed inverse; `analytics_id`/`research_result_id` are re-derived
  by their properties, **never read from state**, so `from_dict(to_dict(r))` re-emits
  identical bytes and the same `result_hash`, and a tampered stored id is ignored.
- `.seal(...)` is the identity-computing constructor (mirrors `ExperimentResult.seal`): it
  folds the ordered computed-output cells (absolute, then relative, then VaR — each tagged
  by its block so two structurally different records can never collide) into `result_hash`,
  so identity is a pure function of the request + referenced content + computed answer,
  never caller-supplied.

**What the model deliberately does NOT hold:** section titles, prose, display order, any
presentation; the referenced backtests' bodies/ledgers (pointer-only, like
`ExperimentResult`); any float; any wall-clock or RNG value.

### 3.3 Closed v1 statistic vocabulary

Extending any set is an explicit future edit that hashes distinctly (a new key changes the
`result_hash`) — never an implicit fallback.

- **`ABSOLUTE_KEYS`** (10, over subject returns + derived equity curve; benchmark not
  required): `best_period_return`, `calmar`, `downside_deviation`, `excess_kurtosis`,
  `max_drawdown_duration_periods`, `max_drawdown_recovery_periods`,
  `positive_period_fraction`, `skewness`, `sortino`, `worst_period_return`.
- **`RELATIVE_KEYS`** (9, subject vs benchmark; both required and aligned; block empty
  when no benchmark): `active_return`, `alpha`, `beta`, `correlation`,
  `cumulative_active_return`, `down_capture`, `information_ratio`, `tracking_error`,
  `up_capture`.
- **`VAR_KEYS`** (`var`, `cvar`) — the two historical nearest-rank tail statistics computed
  per requested confidence.

`AnalyticsUndefinedReason` (closed, 7): `INSUFFICIENT_PERIODS`, `ZERO_DOWNSIDE`,
`ZERO_VARIANCE` (subject-side constant series — §1.1), `ZERO_BENCHMARK_VARIANCE`,
`ZERO_TRACKING_ERROR`, `NO_DRAWDOWN`, `UNRECOVERED_DRAWDOWN`.

---

## 4. Formula methods (locked, folded into `analytics-stats/1`)

Changing any of these bumps `ANALYTICS_FORMULA_VERSION`, so a value computed under one
method can never be silently reinterpreted under another.

- **Population moments (D11):** `variance = Σ(x−μ)²/n`; `skewness = μ₃/σ³`;
  `excess_kurtosis = μ₄/σ⁴ − 3`. A constant series (`σ = 0`) → `ZERO_VARIANCE` for
  skewness/excess-kurtosis, never a fabricated `0`.
- **Annualization:** ratios (Sortino, information ratio) are scaled by `√(periods_per_year)`
  exactly as `stats.py` annualizes Sharpe; raw dispersions (downside deviation, tracking
  error) are reported **per period**.
- **Downside deviation** is measured against the `risk_free_per_period` MAR target over
  **all** `n` observations: `√(Σ min(rᵢ − target, 0)²/n)`. Zero → Sortino `ZERO_DOWNSIDE`.
- **Drawdown** is scale-invariant, computed on the equity curve compounded from the sealed
  returns (`e₀ = 1`, `eᵢ = eᵢ₋₁·(1 + rᵢ)`) — equal to the sealed curve divided by its
  opening equity, so it matches the sealed `max_drawdown` by the identical formula with no
  second source of truth. **Duration** = periods from pre-drawdown peak to the max-drawdown
  trough (first occurrence on ties → deterministic); **recovery** = periods from that trough
  until the peak level is regained (`UNRECOVERED_DRAWDOWN` if never regained by series end).
  A curve that never falls below its running peak → `NO_DRAWDOWN` for Calmar/duration/recovery.
- **Calmar** = `mean · periods_per_year / max_drawdown_magnitude`.
- **Historical VaR/CVaR (D7):** for confidence `c`, `k = ceil((1−c)·n)` (clamped to `≥ 1`);
  `var` = the `k`-th smallest period return (ascending, signed — a negative value is a loss);
  `cvar` = the arithmetic mean of the `k` smallest returns. No interpolation, no distribution
  assumption, no resampling, no RNG. With `n ≥ 2` and `c ∈ (0, 1)`, `1 ≤ k ≤ n`, so both are
  KNOWN.
- **Relative:** `active_return = mean(r_p) − mean(r_b)`;
  `cumulative_active_return = (Π(1+r_pᵢ) − 1) − (Π(1+r_bᵢ) − 1)`;
  `tracking_error = pstd(r_p − r_b)` (per period); `information_ratio = mean(active) /
  tracking_error · √ppy` (`ZERO_TRACKING_ERROR` when the active series has no dispersion);
  single-factor OLS `beta = cov(r_p, r_b)/var(r_b)`, `alpha = (mean(r_p) − rf) − beta·(mean(r_b)
  − rf)` (`ZERO_BENCHMARK_VARIANCE` when the benchmark never moved); `correlation = cov /
  (std_p · std_b)` (`ZERO_BENCHMARK_VARIANCE` if the benchmark is flat, `ZERO_VARIANCE` if the
  subject is flat); up/down capture = mean subject return over mean benchmark return in the
  benchmark's up (`r_b > 0`) / down (`r_b < 0`) periods (`ZERO_BENCHMARK_VARIANCE` when there
  are no qualifying periods or their sum is zero).

All arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`),
never the ambient process context. `Decimal.sqrt(context)` covers all roots. No float
touches any value.

---

## 5. Identity / determinism (locked)

- Domain tag via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): record tag `analytics/1`;
  engine tag `analytics-engine/1`; formula tag `analytics-stats/1`.
- `analytics_engine_version_id = sha256(code_version "analytics-engine/1", config_hash)`
  where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=analytics-stats/1")`.
  Any change to the decimal context **or** a formula method yields a new engine id.
- `analytics_result_hash = sha256(canonical JSON over the ordered computed-output cells:
  absolute, then relative, then var — each tagged by block and reduced to its `(key/confidence,
  status, value)` form)`. Sensitive to every computed cell.
- `analytics_id = sha256`, NUL-joined: `analytics/1`, `analytics_engine_version_id`, `name`,
  `spec_version`, `subject_id`, `benchmark_id or ""`, canonical-JSON of the sorted
  `var_confidences`, `risk_free_per_period`, `periods_per_year`, subject `result_hash`,
  `benchmark result_hash or ""`, and `analytics_result_hash`.
- `research_result_id` aliases `analytics_id` (single id — D6).

**Folds (changes identity):** engine-logic + formula + decimal-context version ✔, the full
declared request (name, spec version, subject/benchmark ids, sorted VaR confidences, the
annualization convention — D8) ✔, both referenced backtests' `result_hash` ✔, the computed
statistics (via `result_hash`) ✔. **Does NOT fold:** the record schema/format version
(`ANALYTICS_RESULT_FORMAT_VERSION` — a container concern, Phase 14 D9 discipline), any
presentation, wall-clock, RNG, `id()`, or iteration order (all set-valued inputs are sorted).

Same spec + same sealed inputs → same `analytics_id` and same bytes on any machine.

---

## 6. PIT semantics, provenance, storage (locked D1, D3, §M/§N/§P)

- **Pure PIT consumer.** Phase 15 performs no PIT resolution and takes no `as_of`. Its
  inputs are `BacktestResult.period_returns`, each produced by the Phase 12 engine under
  BT-2 (every decision at `T` saw only PIT-eligible-at-`T` data). Reading a sealed return
  vector cannot introduce look-ahead — the record adds no new look-ahead surface (D9).
- **PIT-only v1.** Backtests are PIT-only by construction (no `RevisedBacktest`). The record
  carries an explicit, un-defaulted `boundary_kind = "pit"`; a future REVISED analytics
  scope is reserved and explicitly labelled (Phase 14 D10 discipline). The PIT boundary
  needs no runtime probe: a `BacktestResult` is PIT-only, so the sealed record carries
  `"pit"` unconditionally.
- **Benchmark PIT integrity.** Because the benchmark is itself a sealed `BacktestResult`
  (D3), its returns are PIT-correct by the same construction — there is no unprovenanced
  external index series that could smuggle in look-ahead.
- **Provenance by reference, never by copy.** The record pins subject and benchmark by
  `(backtest_id, result_hash)`; each referenced backtest already carries complete lineage
  to raw SEC/market bytes, so the analytics record's provenance is exactly as strong, with
  no duplication or divergence. The convention (`risk_free_per_period`, `periods_per_year`)
  is stored and folded into identity (D8). Corpus pins are carried through as distinct,
  sorted sets; `pin_mismatch` surfaces a subject/benchmark disagreement, never raised.
- **Storage.** Zero new store types; the `ResearchResultStore` writes the record to
  `<root>/research/sha256-<hex>.json` in the existing container
  (`{"research_result_format_version": 1, "research_result": ...}`), atomic, `indent=2,
  sort_keys=True, ensure_ascii=False`. Write-once and idempotent: re-computing identical
  analytics is a byte-identical no-op; a differing payload under an existing id fails closed
  via the store's guard.

---

## 7. Failure / UNDEFINED behavior (locked §Q)

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`AnalyticsConfigurationError` / `AnalyticsConsistencyError`):
- Empty `name`; empty `subject_id`; `benchmark_id == subject_id`; a `var_confidence` outside
  `(0,1)`, non-finite, or duplicated; non-decimal/negative `risk_free_per_period`;
  non-decimal/non-positive `periods_per_year`; a non-`AnalyticsSpecification` argument to
  `compute`. *(configuration)*
- Fewer than **2** subject return observations (`_MIN_PERIODS` — below which every
  dispersion-based statistic would be UNDEFINED and the whole record meaningless): raised as
  configuration rather than sealing an all-UNDEFINED record. *(configuration)*
- `subject_id` or `benchmark_id` absent from the sidecar; a resolved record whose
  `research_result_id` disagrees with the requested id; a referenced record whose recomputed
  `result_hash` no longer matches its sealed value (drift); subject and benchmark with
  different `schedule_id`, unequal `period_returns` length, or incommensurable
  `backtest_engine_version_id`. *(consistency)*

**Recorded as first-class UNDEFINED (never raised, never fabricated):** per-statistic
undefinability with an `AnalyticsUndefinedReason` — Sortino with `ZERO_DOWNSIDE`; skewness /
excess kurtosis / correlation with `ZERO_VARIANCE` (constant subject); beta / alpha /
correlation / capture with `ZERO_BENCHMARK_VARIANCE`; information ratio with
`ZERO_TRACKING_ERROR`; Calmar / duration with `NO_DRAWDOWN`; recovery with
`UNRECOVERED_DRAWDOWN`. There is no divide-by-zero anywhere: a zero denominator becomes a
recorded UNDEFINED, exactly as Phase 7 metrics and Phase 10 derivations do. A corpus
`pin_mismatch` is surfaced on the record (a boolean property), never raised.

---

## 8. Public API (locked)

```python
from quantforge import AnalyticsSpecification, PerformanceAnalytics, Workspace

ws = Workspace.open(root)

# absolute risk profile of one sealed backtest
spec = AnalyticsSpecification(name="risk-profile", subject_id=strategy_backtest_id)
analytics = ws.analytics_engine.compute(spec)          # a sealed, write-once PerformanceAnalytics

# benchmark-relative evaluation vs a sealed equal-weight buy-and-hold backtest
rel = AnalyticsSpecification(
    name="vs-equal-weight",
    subject_id=strategy_backtest_id,
    benchmark_id=equal_weight_backtest_id,             # a sealed BacktestResult, never external data
    var_confidences=("0.95", "0.99"),
    periods_per_year="12",
)
result = ws.analytics_engine.compute(rel)

# typed read-back (byte-identical round-trip)
again = ws.research_result_store.read_as(result.research_result_id, PerformanceAnalytics.from_dict)
```

`AnalyticsEngine` is reached only through `Workspace.analytics_engine` (a lazy, cached,
cycle-free `@property`; engines are not re-exported at top level). `compute(spec) ->
PerformanceAnalytics` is the single entry point. No `Company` method is added (analytics
spans results, not one filer — Phase 13 D6 discipline).

---

## 9. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 15 suite added), deterministic across runs.
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src tests`
  clean (strict).
- Zero runtime dependencies (stdlib `hashlib`/`json`/`dataclasses`/`Decimal` only); no float
  in any path; no wall-clock/RNG in any identity or value; single-factor OLS is closed-form
  scalar `Decimal` (no linear-algebra dependency).
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** — the only source edits are the additive
  `Workspace.analytics_engine` property/cache line and the `__init__.py` re-exports; no edit
  to any identity/version module or to `backtest/*` (incl. `stats.py`), `experiment/*` (incl.
  `analysis.py`), or `report/*`.
- Byte-identical `PerformanceAnalytics` round-trip test proves `from_dict` introduces no
  drift and that a tampered stored id is ignored; a `TestDeterminism` double-build proves
  `to_dict()` byte-equality, id sensitivity to each input, and `var_confidences`-order
  invariance.
- Docs updated; `ARCHITECTURE.md` "Performance & benchmark-relative analytics" row flipped
  to ✅ only when green.

---

## 10. Test coverage (locked)

New package `tests/analytics/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_compute.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline over the
fictional CIKs `9999999991`/`9999999992`, covering: construction validation and
`var_confidences` set-canonicalization (IDENTITY / spec); each statistic against
hand-computed decimal strings on tiny fixed vectors, UNDEFINED preservation with the right
reason, and determinism (COMPUTE / DRAWDOWN / DOWNSIDE / DISTRIBUTION / VAR-CVAR); `analytics_id`
folding + order-invariance + sensitivity (IDENTITY); byte-identical `to_dict`/`from_dict`,
id re-derivation, tampered-id ignore, `pin_mismatch` surfacing (ROUND TRIP / PERSISTENCE);
resolve/verify/seal/write-once, fail-closed on absent/drifted/too-short/incommensurable/non-spec
input (FAIL-CLOSED / PIT); `Workspace` wiring and shared-sidecar reuse (WORKSPACE); and two
independently-populated corpora yielding byte-identical analytics (REPRODUCIBILITY).
