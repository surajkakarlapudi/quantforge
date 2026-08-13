# Phase 29 — Risk-Forecast Calibration Significance (LOCKED)

> **Status:** Locked normative specification. The Phase 29 proposal was **implemented as
> recommended** — the single capability of
> [phase29-calibration-significance-proposal.md](phase29-calibration-significance-proposal.md):
> consume exactly one sealed `RiskForecastCalibration` (Phase 26), read its aggregate
> `mean_variance_ratio` (`m`), population `variance_ratio_dispersion` (`s`), and
> calibratable-window count (`K = n_calibratable`) verbatim, and seal a **one-sample,
> two-sided large-sample significance test** of the null hypothesis that the mean variance
> ratio equals `1` (perfect calibration on average) — `standard_error = s/√K`,
> `t = (m − 1)/standard_error`, `p = 2·(1 − Φ(|t|))` clamped to `[0, 1]` — plus the
> descriptive bias direction. This document reflects the **actual implementation** and is
> the source of truth; it supersedes the proposal. Every ★-marked decision in the proposal
> is resolved here.
>
> **One-line thesis:** Phase 29 adds a deterministic, content-addressed **calibration
> significance** layer — the first consumer of Phase 26's sealed `RiskForecastCalibration`
> summary, answering the one question the calibration record never states: *is the risk
> model's mean variance ratio statistically distinguishable from perfect calibration?* It is
> the calibration analogue of Phase 24's paired-difference significance test
> (`comparison.compute.compare_pair`), applied as a **one-sample** test about the null mean
> `1`. Given a declarative `CalibrationSignificanceSpecification` naming exactly one sealed
> `RiskForecastCalibration` id, `CalibrationSignificanceEngine.evaluate(...)` resolves the
> one calibration from the shared Phase 8 research sidecar, re-verifies it (present, a
> `RiskForecastCalibration`, id matches), gates on its `calibration_status` and the
> KNOWN-ness of its aggregate cells, computes the one-sample statistics under one pinned
> `Decimal` context, and seals a `CalibrationSignificance` `ResearchRecord` write-once to the
> existing sidecar. It introduces **no** new numerical primitive (it reuses the deterministic
> exact-`Decimal` `standard_normal_cdf` for `Φ`, and `Decimal.sqrt` is the only other
> transcendental), **no** `_linalg`/`_stats` change, **no** RNG, **no** floating point,
> **no** iterative solver, **no** new store, and **no** new PIT surface, and modifies no
> prior phase's vocabulary, engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **One-sample two-sided significance test of the mean variance ratio against the null `1`, over one calibration.** The analyzed object is exactly the source `RiskForecastCalibration`'s aggregate calibratable-window family: its sealed `mean_variance_ratio` (`m`), `variance_ratio_dispersion` (`s`), and `n_calibratable` (`K`). It seals `standard_error`, `t_statistic`, `p_value` (UNDEFINED-preserving cells), the descriptive `bias_direction`, the carried `mean_variance_ratio` / `null_mean_ratio` / `n_calibratable`, and the roll-up `significance_status`. **No** per-window test, **no** cross-calibration family (one source only), **no** correction/multiplicity layer, **no** annualization. It performs **no execution**, resolves **no** data at any `T`, and is **not** a `BacktestResult`. |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 26.** It resolves exactly **one** already-sealed `RiskForecastCalibration` from the shared sidecar by id, reads its sealed `calibration_status` / `summary.mean_variance_ratio` / `summary.variance_ratio_dispersion` / `coverage.n_calibratable` / `boundary_kind` (never re-derives them, never reads the per-window `variance_ratio` cells, the `aggregate_bias`, or anything beneath the calibration), and **modifies no** prior-phase vocabulary, engine, or identity. It is the first consumer of the aggregate calibration summary Phase 26 sealed. |
| **D-COMPUTE** | **Closed-form exact-`Decimal` one-sample statistics; one reused `Φ` and one `Decimal.sqrt`.** Under the pinned context, with `K` the calibratable-window count, `m` the sealed mean, `s` the sealed population dispersion, and null mean `1`: `standard_error = s/√K`; `t_statistic = (m − 1)/standard_error`; `p_value = 2·(1 − Φ(|t|))` clamped to `[0, 1]`, with `Φ` the reused exact-`Decimal` `standard_normal_cdf`. `standard_error = s/√K` equals Phase 24's `√(variance/n)` (there `s = √variance`), so Phase 29 uses the **same** population-moment convention already in the codebase — no new statistical method. The descriptive `bias_direction` is `UNDER_FORECAST` when `m > 1`, `OVER_FORECAST` when `m < 1`, `UNBIASED` when `m == 1` (known whenever `m` is known). |
| **D-STATUS** | **`significance_status` defensible only on a tested source.** `TESTED` iff the source is `CALIBRATED` **and** its aggregate mean / dispersion cells are KNOWN **and** the dispersion is non-zero; else `UNDEFINED` with a first-class reason. The mean and bias direction still seal whenever the source mean is KNOWN, even when `t` / `p` are UNDEFINED. |
| **D-GATE** | **Only a `CALIBRATED` source with KNOWN aggregate cells is tested.** A source whose `calibration_status` is `UNDEFINED` (below the Phase-26 floor, or no calibratable windows), or whose sealed `mean_variance_ratio` / `variance_ratio_dispersion` cell is not KNOWN, seals every statistic UNDEFINED (`SOURCE_NOT_CALIBRATED`) — never imputed, never coerced. `n_calibratable` is reported `0` and `bias_direction` `None` in that case. |
| **D-ZERO** | **Zero dispersion is a first-class UNDEFINED, never a divide-by-zero.** When `variance_ratio_dispersion == 0` (all per-window ratios identical) the `standard_error` is a KNOWN `0`, but `t_statistic` / `p_value` are UNDEFINED (`ZERO_RATIO_DISPERSION`); `mean_variance_ratio` and `bias_direction` stay KNOWN. Never a division by a zero denominator. |
| **D-CONSUME** | **Sealed statistics are consumed verbatim.** The engine parses the source's sealed `mean_variance_ratio` / `variance_ratio_dispersion` decimal strings once (into `Decimal`) and reads `coverage.n_calibratable`; it never recomputes them from the per-window `variance_ratio` cells, never re-derives a moment, and never reads returns. The sealed answer is authoritative (the RC-4 / MT-4 posture, one layer up). |
| **D-EXPOST** | **The output is ex-post, never PIT.** A significance test over an already-ex-post calibration is itself ex-post. `CalibrationSignificance` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` is carried unchanged from the source calibration and documents only that the *underlying factor portfolios were PIT walks*; it never claims the significance output is a PIT value. No new corpus read, no availability logic, no new PIT resolution. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order.** All arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); exact subtraction, division, `Decimal.sqrt` (the standard error), the reused `standard_normal_cdf` (`Φ` via an erf series — bounded, terminating, deterministic; **not** a convergence-tolerance loop), and the `[0, 1]` clamp are the only operations; canonicalization is `str(+value)`. No RNG, no data-dependent iteration order, no `_linalg`/`_stats` change, no new numerical primitive. The engine version folds the decimal context, the method version, **and** the normal-primitive version into `config_hash`. |
| **D-IDENTITY** | **Content-addressed, transitively pinned, self-verifying.** `calibration_significance_id` folds the engine version, the request (name, spec version, source calibration id), the source calibration's `result_hash` (the transitive pin), the `null_mean_ratio` tested, and the `result_hash` over the computed answer. `research_result_id` aliases `calibration_significance_id`; derived ids are re-emitted by properties, never read from stored state. Domain tag `calsig/1`. |
| **D-STORE** | **One write-once record in the existing `ResearchResultStore`; no new store, no migration.** `CalibrationSignificance` satisfies the `ResearchRecord` Protocol and persists to `research/sha256-<hex>.json`. An idempotent re-write of a byte-identical payload is a no-op; a conflicting payload under the same id raises `FactorConsistencyError` (the existing store contract). |
| **D-PARAMS** | **No per-request numerical parameter.** The single approved methodology has no tunable numeric input; the null mean is the fixed platform constant `NULL_MEAN_RATIO = "1"`, folded into `calibration_significance_id` (as Phase 26 folds `MIN_CALIBRATABLE_WINDOWS` and Phase 28 folds `MIN_DETERMINED_TRIALS`) so a change to it is a distinguishable record. |
| **D-INVARIANTS** | **CS-1..CS-6 are documented both as phase-local invariants here (§7) and as a small additive `data-model.md §12` block** mirroring the WF-/CE-/SC-/MC-/RC-/WS-/MT- blocks (they do not weaken existing invariants). |
| **D-VERSION** | This phase releases as **`v0.26.0`** (Phase 28 = v0.25.0). Domain tag `calsig/1`; engine-version string `calsig-engine/1`; method string `calsig-method/1`; normal-primitive string `calsig-normal/1`; spec-version string `calsig/1`; record-format string `calsig-result/1`. The package `__version__` string is unchanged `"0.0.0"` (versioning is by content-addressed ids + the README table, not a semver string). No `pyproject`/packaging change; no new runtime dependency. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; neither changes an identity discipline or weakens an invariant.

- **The record carries a `method_version` field.** The proposal (§4) enumerated the
  method-version string among the folded identity components (through the engine version)
  but did not spell out a *stored* `method_version` on the record. The implementation stores
  `method_version` (default `CALSIG_METHOD_VERSION`) as a first-class record field,
  round-tripped through `to_dict` / `from_dict`. It is **not** folded into
  `calibration_significance_id` separately — the method version already reaches the id
  through `calibration_significance_engine_version_id` (whose `config_hash` folds it), so
  folding it twice would be redundant; the stored field is an auditable record of the method
  that produced the answer. `from_dict` requires it (fail closed on absence), so a record's
  stored bytes disclose their producing method without changing identity discipline.
  (Mirrors the Phase 27 / Phase 28 deviation.)
- **The large-sample normal approximation is the sealed methodology; the finite-sample
  Student-`t` is deferred (★).** As disclosed in the proposal (§2.2), the two-sided p-value
  uses `2·(1 − Φ(|t|))` — the identical `(★)` deferral disclosed by Phase 24's
  `comparison.compute`. No new statistical primitive is introduced; a finite-sample `t`
  distribution is a possible later phase.

Resolved ★ decisions of note: capability = one-sample two-sided significance test of the
mean variance ratio against the null `1` over one calibration; source is exactly one
`RiskForecastCalibration`, consumed by id; output `CalibrationSignificance`; package
`calsig`, domain tag `calsig/1`; public names `CalibrationSignificanceSpecification` /
`CalibrationSignificance`; `standard_error = s/√K`, `t = (m − 1)/se`, `p = 2·(1 − Φ(|t|))`
clamped; exact-`Decimal`, reuse `standard_normal_cdf`, no new primitive; ex-post, not a
`Pit*`, boundary carried; gate on `CALIBRATED` + KNOWN aggregate cells, zero-dispersion
UNDEFINED, `NULL_MEAN_RATIO = "1"` folded; identity fold as in §5; v0.26.0; no
`_linalg`/`_stats` change; a sibling package, no prior-phase edit; shared write-once
`ResearchResultStore`.

---

## 2. What was built

New package **`src/quantforge/calsig/`** (mirrors the P20/P22/P23/P24/P25/P26/P27/P28
layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `CalSigError` → `CalSigConfigurationError`, `CalSigConsistencyError`. |
| `version.py` | `CalibrationSignificanceEngineVersion` (folds the pinned decimal context + `calsig-method/1` + `calsig-normal/1` into `config_hash`); constants `CALSIG_SPEC_VERSION` / `CALSIG_ENGINE_VERSION` / `CALSIG_METHOD_VERSION` / `CALSIG_NORMAL_VERSION`; `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `model.py` | The closed `SignificanceStatus` (`tested`, `undefined`), `SignificanceUndefinedReason` (`source_not_calibrated`, `zero_ratio_dispersion`), `BiasDirection` (`under_forecast`, `over_forecast`, `unbiased`), `StatStatus`, and the UNDEFINED-preserving `SignificanceStat` cell (`known` / `undefined` / `to_dict` / `from_dict`). |
| `spec.py` | `CalibrationSignificanceSpecification` (declarative request; fail-closed validation of `name` / `source_calibration_id`; `spec_version = "calsig/1"`). |
| `compute.py` | The pure exact-`Decimal` procedure: `test_calibration_significance(family, *, null_mean, context) → SignificanceComputation`; `CalibratableFamily` (the carried `mean_variance_ratio` / `variance_ratio_dispersion` / `n_calibratable`); the `_bias_direction` helper. |
| `result.py` | `CalibrationSignificance` (`ResearchRecord`; `seal` / `to_dict` / `from_dict`, derived ids, `significance_status` / `source_calibration_id` / `source_result_hash` accessors), `SignificanceSummary`; `CALSIG_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`, `NULL_MEAN_RATIO = "1"`. |
| `identity.py` | `calibration_significance_result_hash`, `calibration_significance_id`; domain tag `calsig/1`. |
| `engine.py` | `CalibrationSignificanceEngine.evaluate(spec)`. |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `workspace.py` — one lazy `calibration_significance_engine` `@property` (+ private
   `_calibration_significance_engine` cache slot), following the `mintrl_engine` template
   (typed `-> object`, deferred import of `CalibrationSignificanceEngine` to avoid the
   module-load cycle).
2. `src/quantforge/__init__.py` — top-level re-exports of
   `CalibrationSignificanceSpecification` and `CalibrationSignificance`, added to the sorted
   `__all__`.

**No edit to** `_linalg`, `calibration`, `campaign`, `walkforward`, `comparison`,
`multiplicity`, `stability`, `mintrl`, `optimization`, `factorrisk`, `factorportfolio`,
`analytics`, `backtest`, or any other prior-phase identity/vocabulary. Phase 29 **reuses**
`quantforge._stats.normal.standard_normal_cdf` verbatim (the same primitive Phase 24 uses)
and adds no primitive to `_stats`, so `_stats/normal.py` is untouched.

---

## 3. Data flow

```
CalibrationSignificanceSpecification { name, source_calibration_id, spec_version }
        │
        ▼  CalibrationSignificanceEngine.evaluate(spec)
type-check spec is a CalibrationSignificanceSpecification                     — CalSigConfigurationError
        │
        ▼
resolve the ONE source calibration by id                                     — fail closed (CS-1)
   store.read_as(id, RiskForecastCalibration.from_dict)
   present? decodes as a RiskForecastCalibration? research_result_id == id?      — else CalSigConsistencyError
        │
        ▼
gate the source into a CalibratableFamily or None                            — CS-2
   calibration_status is CALIBRATED AND mean / dispersion cells KNOWN
      → CalibratableFamily(m, s, K)   (parse the two decimal strings once)
   else → None
        │
        ▼  under localcontext(prec 34, ROUND_HALF_EVEN):
   test_calibration_significance(family, null_mean=Decimal("1"), context)     — CS-3/CS-5
     family is None            → all UNDEFINED SOURCE_NOT_CALIBRATED
     dispersion == 0           → se KNOWN "0"; t / p UNDEFINED ZERO_RATIO_DISPERSION; mean + direction KNOWN
     else                      → se = s/√K; t = (m − 1)/se; p = 2·(1 − Φ(|t|)) clamped [0, 1]; TESTED
        │
        ▼
SignificanceSummary { mean_variance_ratio, null_mean_ratio, n_calibratable,
   standard_error, t_statistic, p_value, significance_status, bias_direction, status_reason }
        │
        ▼
CalibrationSignificance.seal(...)  (result_hash folds the answer;
   boundary_kind carried from source; source_ref = (source id, source result_hash))  — CS-1/CS-6
        │
        ▼
ResearchResultStore.write(significance)   (write-once, idempotent)           — D-STORE
        │
        ▼
store.read_as(id, CalibrationSignificance.from_dict)   (byte-identical typed round-trip)
```

---

## 4. Public API

```python
from quantforge import (
    Workspace,
    CalibrationSignificanceSpecification,
    CalibrationSignificance,
)

ws = Workspace.open(root)

spec = CalibrationSignificanceSpecification(
    name="calibration:significance",
    source_calibration_id=calibration_id,  # exactly one sealed RiskForecastCalibration id
)

significance = ws.calibration_significance_engine.evaluate(spec)  # sealed, write-once

significance.significance_status  # TESTED / UNDEFINED (roll-up)
significance.summary  # SignificanceSummary: statistics + bias direction + status
significance.source_calibration_id  # the pinned source calibration id
significance.source_result_hash  # the transitive pin
significance.research_result_id  # == significance.calibration_significance_id

again = ws.research_result_store.read_as(
    significance.research_result_id, CalibrationSignificance.from_dict
)
```

`CalibrationSignificanceEngine` is reached only through
`Workspace.calibration_significance_engine` (lazy, cached, `-> object`).
`evaluate(spec) -> CalibrationSignificance` is the single entry point.

`CalibrationSignificanceSpecification` (frozen slots): `name`, `source_calibration_id`,
`spec_version = "calsig/1"`. Construction-time validation (fail closed): non-empty `name` /
`spec_version` / `source_calibration_id`. There is no numerical request parameter (the null
mean is the platform constant `NULL_MEAN_RATIO`).

`SignificanceSummary` carries the carried `mean_variance_ratio` cell, the `null_mean_ratio`
string (`"1"`), the `n_calibratable` count, three UNDEFINED-preserving `SignificanceStat`
cells (`standard_error`, `t_statistic`, `p_value`), the descriptive `bias_direction` (or
`None`), the roll-up `significance_status`, and an optional `status_reason`.

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `calibration_significance_engine_version_id = sha256(code_version "calsig-engine/1",
  config_hash)` where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=
  calsig-method/1\x00normal=calsig-normal/1")`. Folding the method and normal versions makes
  the record's identity change if the source-gating, the one-sample statistics, or the
  reused CDF primitive changes.
- `calibration_significance_result_hash = sha256(canonical JSON over the ordered
  computed-output cells: a single `{block:"summary", ...}` descriptor holding the carried
  mean, null mean, count, standard error, `t`, `p`, status, bias direction, and reason)`.
  Sensitive to every carried and computed statistic.
- `calibration_significance_id = sha256`, NUL-joined, in order: `calsig/1`,
  `calibration_significance_engine_version_id`, `name`, `spec_version`,
  `source_calibration_id`, `source_result_hash` (the transitive pin, CS-1),
  `null_mean_ratio`, and `calibration_significance_result_hash`.
- `research_result_id` aliases `calibration_significance_id`. Derived ids are re-emitted by
  properties, never read from stored state — a tampered stored id is ignored and
  `from_dict(to_dict(r))` re-emits identical bytes. The record-format version and the stored
  `method_version` are **not** folded (a container / audit concern; the method reaches the
  id through the engine version).

---

## 6. Determinism / Decimal rules

- All significance arithmetic runs under an explicit `localcontext` (precision 34,
  `ROUND_HALF_EVEN`): the standard error `s/√K` (a `Decimal.sqrt` of the integer window
  count), the `t` statistic `(m − 1)/se`, the two-sided `p = 2·(1 − Φ(|t|))`, and the
  `[0, 1]` clamp. `Φ` is the reused deterministic `standard_normal_cdf` (an erf series —
  bounded, terminating; **not** a convergence-tolerance loop). **No float anywhere**, no
  RNG, no wall-clock, no `id()`, no data-dependent iteration order.
- Values are canonicalized as `str(+value)` inside the pinned context.
- Same source calibration + same request → same `calibration_significance_id` and
  byte-identical payload on any machine. A repeated `evaluate` is a byte-identical no-op
  (store idempotence). Two engines over the same immutable sidecar agree. Because Phase 29
  folds the source calibration's `result_hash`, any upstream change changes this record's id
  while a byte-identical recompute reproduces identical bytes (the Phase 22/23/28 audit
  standard, one layer up).

---

## 7. Invariants (CS-1..CS-6)

Additive to `data-model.md §12`; these do not weaken existing invariants.

- **CS-1 — Reference verification and transitive pinning.** The single
  `source_calibration_id` is resolved from the shared sidecar via
  `store.read_as(id, RiskForecastCalibration.from_dict)`, re-verified
  (`research_result_id == id`, and that it decodes as a `RiskForecastCalibration`), and its
  `result_hash` folded into `calibration_significance_id`; through the source calibration's
  own id this pins the walk-forward / optimization / risk-model / factor chain beneath it
  (RC-1). Any missing, non-decoding, or id-mismatched reference fails closed with
  `CalSigConsistencyError`; the source is never copied, only pinned. *(The RC-1 / MT-1
  discipline, one layer up.)*
- **CS-2 — Source-status gating: only a `CALIBRATED` source is tested.** A source whose
  `calibration_status` is not `CALIBRATED` (below the Phase-26 floor, or no calibratable
  windows), or whose sealed `mean_variance_ratio` / `variance_ratio_dispersion` cell is not
  KNOWN, seals a first-class UNDEFINED record (`SOURCE_NOT_CALIBRATED`) with every statistic
  UNDEFINED, `n_calibratable = 0`, and `bias_direction = None` — never imputed, never
  coerced to a metric. The record still seals (a data condition is never an exception).
- **CS-3 — UNDEFINED-preserving, no divide-by-zero.** When the sealed
  `variance_ratio_dispersion` is `0` (all per-window ratios identical) the `standard_error`
  is a KNOWN `0`, but `t_statistic` / `p_value` are first-class UNDEFINED
  (`ZERO_RATIO_DISPERSION`) — never a division by a zero denominator; `mean_variance_ratio`
  and `bias_direction` stay KNOWN. *(The RC-3 / MT-3 posture, adapted to a one-sample test.)*
- **CS-4 — Sealed statistics are consumed verbatim, never recomputed.** The source's
  already-sealed `mean_variance_ratio` / `variance_ratio_dispersion` cells and
  `coverage.n_calibratable` are read (the two decimal strings parsed once into `Decimal`);
  the engine never recomputes them from the per-window `variance_ratio` cells, never
  re-derives a moment, and never reads returns. The sealed answer is authoritative. *(The
  RC-4 / MT-4 posture of operating over already-sealed strings, one layer up.)*
- **CS-5 — Single deterministic large-sample two-sided normal test.** One exact-`Decimal`
  method: `standard_error = s/√K`, `t_statistic = (m − 1)/standard_error`,
  `p_value = 2·(1 − Φ(|t|))` clamped to `[0, 1]` — the same population-moment standard-error
  convention as Phase 24 (`√(variance/n)` with `s = √variance`) — all under one pinned
  decimal context (prec 34, `ROUND_HALF_EVEN`) folded into the engine identity, with `Φ` the
  deterministic exact-`Decimal` `standard_normal_cdf` reused verbatim from
  `quantforge/_stats/normal.py` (shared with Phase 24) and `Decimal.sqrt` the only other
  transcendental. The null mean `1` (`NULL_MEAN_RATIO`) is folded into the id. The
  finite-sample Student-`t` distribution is deferred (★), the identical deferral Phase 24
  discloses. No RNG, no float, no data-dependent iteration, no `_linalg`/`_stats` change, no
  new primitive. *(The SC-5 discipline, reusing exact `Decimal` arithmetic.)*
- **CS-6 — A calibration-significance analysis is not a PIT value and not a
  `BacktestResult`.** A significance test over an already-ex-post calibration is itself
  ex-post: `CalibrationSignificance` is **not** a `Pit*` type, exposes no as-of accessor, is
  a distinct record type, simulates no fills, and opens no new corpus / availability surface.
  `boundary_kind = "pit"` — carried unchanged from the source calibration — documents only
  that the *underlying factor portfolios* were PIT walks. *(The RC-6 / MT-6 discipline, one
  layer up.)*

---

## 8. Failure / UNDEFINED semantics

**Raised** — `CalSigConfigurationError`: a non-`CalibrationSignificanceSpecification`
argument to the engine; a malformed spec (empty `name` / `spec_version` /
`source_calibration_id`). `CalSigConsistencyError` (CS-1): the `source_calibration_id`
absent from the sidecar; a payload that does not decode as a `RiskForecastCalibration`; a
resolved-id disagreement.

**Recorded as first-class UNDEFINED** (CS-2/CS-3, never raised): a non-`CALIBRATED` source
(or one with a non-KNOWN aggregate cell) seals every statistic UNDEFINED
(`SOURCE_NOT_CALIBRATED`); a zero-dispersion source seals `t_statistic` / `p_value` UNDEFINED
(`ZERO_RATIO_DISPERSION`) with `standard_error` a KNOWN `0` and the mean / bias direction
KNOWN. The record always seals.

**Store contract:** a byte-identical re-write is an idempotent no-op; a differing payload
under the same significance id raises `FactorConsistencyError` (the existing write-once
guard).

---

## 9. Testing

`tests/calsig/` (offline, synthetic). Because the engine reads **only** the source
`RiskForecastCalibration` via `store.read_as`, the builders (`tests/calsig/builders.py`)
construct synthetic `RiskForecastCalibration` records directly — sealing hand-chosen
`CalibrationSummary` / `CalibrationCoverage` cells (CALIBRATED with KNOWN mean / dispersion,
a zero-dispersion source, a non-CALIBRATED source, or a CALIBRATED source with a
non-KNOWN mean) via `RiskForecastCalibration.seal` and writing them to the store — rather
than running the full factor → optimization → walk-forward → calibration chain.

Suites (**44 tests** across the package):
- `test_spec` — the default spec version, the canonical `to_dict`, fail-closed rejection of
  empty fields, frozenness.
- `test_model` — the KNOWN/UNDEFINED `SignificanceStat` construction guards, `to_dict` /
  `from_dict` round-trip, fail-closed decode of corrupt cells (unknown status / reason), and
  the closed status/reason vocabularies.
- `test_compute` — the pure procedure over synthetic `CalibratableFamily` families: the
  exact `standard_error` / `t` / `p` against a hand-computed value, the symmetric two-sided
  `p` and opposite `bias_direction` for a mirrored mean, the `UNBIASED` direction at
  `m == 1`, the `ZERO_RATIO_DISPERSION` UNDEFINED cells (mean + direction still KNOWN), the
  absent-family all-UNDEFINED `SOURCE_NOT_CALIBRATED` case, the `p ∈ [0, 1]` clamp for a tiny
  `t`, and repeated computation identical. (Imported as `run_significance` to avoid pytest
  collecting the `test_`-prefixed procedure name.)
- `test_identity` — `sha256:`-prefixed, deterministic, each-fold-changes-the-id (including
  the transitive `source_result_hash` pin and the `null_mean_ratio` fold), result-hash
  sensitive to a single cell, and the engine-version fold of context + method.
- `test_result` — seal folds the answer, derived id aliases `research_result_id`,
  byte-identical round-trip (tested and undefined summaries), id re-derived not read from
  state (tampered stored id ignored), a `t` change changes the hash and the id, and that the
  record is not a `Pit*` type and exposes no `as_of`.
- `test_public_api` — public exports and the lazy/cached
  `Workspace.calibration_significance_engine`.
- `test_engine` — happy path (a CALIBRATED source tested, statistics match a fixture, source
  reference pinned), the `SOURCE_NOT_CALIBRATED` gate (non-CALIBRATED and non-KNOWN-mean
  sources), the `ZERO_RATIO_DISPERSION` UNDEFINED cells, boundary carried and the record not
  PIT; recompute byte-identical and idempotent; and every fail-closed guard (absent source,
  non-`RiskForecastCalibration` record, id-mismatch via a path-swapped payload, non-spec
  argument, and a tampered stored payload → `FactorConsistencyError`).

**Gate (all green): `ruff check .` / `ruff format --check .` / `mypy src tests` /
`pytest -q` / `pytest -q -p no:randomly`; zero new runtime dependencies; every prior-phase
id preserved (no prior source touched beyond the additive `workspace.py` / `__init__.py`
re-exports).**
