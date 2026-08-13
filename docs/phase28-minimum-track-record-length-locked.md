# Phase 28 — Minimum Track-Record Length (MinTRL) (LOCKED)

> **Status:** Locked normative specification. The Phase 28 proposal was **implemented as
> recommended** — the single capability of
> [phase28-minimum-track-record-length-proposal.md](phase28-minimum-track-record-length-proposal.md):
> consume exactly one sealed `ResearchCampaignEvaluation`, treat its VALID trials (each
> carrying KNOWN `sharpe` / `skew` / `kurtosis` / `n`) as the evaluable family, and per
> trial seal the Bailey–López de Prado minimum track-record length
> `MinTRL(SR*) = 1 + V·(Z_alpha/(SR − SR*))²` plus the aggregate MinTRL profile across the
> family — answering *how long an out-of-sample record a strategy must accumulate before
> its observed Sharpe is significant, at confidence `alpha`, against a benchmark Sharpe
> `SR*`*. This document reflects the **actual implementation** and is the source of truth;
> it supersedes the proposal. Every ★-marked decision in the proposal is resolved here.
>
> **One-line thesis:** Phase 28 adds a deterministic, content-addressed **minimum
> track-record length** layer — the platform's first *statistical-power /
> track-record-adequacy* capability and the first consumer of Phase 23's reserved-but-
> unconsumed per-trial moment block (the `ResearchCampaignEvaluation` sealed each trial's
> `sharpe` / `skew` / `kurtosis` / `n`; Phase 28 reads exactly those). Given a declarative
> `MinimumTrackRecordLengthSpecification` naming exactly one sealed
> `ResearchCampaignEvaluation` id (plus a confidence `alpha ∈ (0, 1)`, default `0.95`, and
> a benchmark Sharpe `SR*`, default `0`), `MinimumTrackRecordLengthEngine.evaluate(...)`
> resolves the one campaign from the shared Phase 8 research sidecar, re-verifies it
> (present, a `ResearchCampaignEvaluation`, id matches), classifies each trial into the
> evaluable family (each carrying its KNOWN moments parsed once to `Decimal`) or a
> first-class exclusion (every UNDEFINED / moment-missing trial recorded, never imputed),
> computes per evaluable trial the MinTRL and `excess_length = n − MinTRL`, and over the
> determined family the aggregate mean / population dispersion / max / min MinTRL and the
> `sufficient_frequency` — all under one pinned `Decimal` context — and seals a
> `MinimumTrackRecordLength` `ResearchRecord` write-once to the existing sidecar. It
> introduces **no** new numerical primitive (it reuses the deterministic exact-`Decimal`
> `standard_normal_ppf` for `Z_alpha`, and `Decimal.sqrt` is the only other transcendental),
> **no** `_linalg`/`_stats` change, **no** RNG, **no** floating point, **no** iterative
> solver (the only iteration is the *already-pinned* fixed 240-step `standard_normal_ppf`
> bisection), **no** new store, and **no** new PIT surface, and modifies no prior phase's
> vocabulary, engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **Per-trial MinTRL + aggregate profile over the evaluable-trial family of one campaign.** The family is exactly the source `ResearchCampaignEvaluation`'s VALID trials — each carrying KNOWN `sharpe` / `skew` / `kurtosis` / `n` — in sealed source order. Per evaluable trial seal the carried moments, `min_track_record_length`, and `excess_length`; over the determined family seal `mean_min_trl` / `min_trl_dispersion` / `max_min_trl` / `min_min_trl` / `sufficient_frequency` / `n_determined` and `mintrl_status`; seal the coverage (`n_trials`, `n_evaluable`, `n_excluded`). **No** cross-campaign family (one source only); **no** correction/test on the MinTRL family; **no** annualization (MinTRL is reported in the source's per-period units). It performs **no execution**, resolves **no** data at any `T`, and is **not** a `BacktestResult`. |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 23.** It resolves exactly **one** already-sealed `ResearchCampaignEvaluation` from the shared sidecar by id, reads each trial's sealed `status` / `n` / `sharpe` / `skew` / `kurtosis` (never re-derives them, never reads the `psr` cell, the campaign summary, or anything beneath the campaign), and **modifies no** prior-phase vocabulary, engine, or identity. It is the first consumer of the per-trial moment block Phase 23 sealed but no prior consumer (Phase 24, 25) ever read. |
| **D-COMPUTE** | **Closed-form exact-`Decimal` MinTRL and aggregates; one reused `Z⁻¹` and one `Decimal.sqrt`.** Per evaluable trial under the pinned context: the Phase-23 PSR estimator variance `V = 1 − γ₃·SR + ((γ₄−1)/4)·SR²`; if `V ≤ 0` the MinTRL is UNDEFINED (`DEGENERATE_SHARPE_ESTIMATOR`); else if `SR ≤ SR*` it is UNDEFINED (`SHARPE_NOT_ABOVE_BENCHMARK`); else `MinTRL = 1 + V·(Z_alpha/(SR − SR*))²` and `excess_length = n − MinTRL`, with `Z_alpha = Φ⁻¹(alpha)` evaluated once via the reused `standard_normal_ppf`. Over the `K` determined trials: `mean_min_trl = (Σ MinTRLₖ)/K`; population `min_trl_dispersion = √(Σ(MinTRLₖ − mean)²/K)`; `max`/`min_min_trl`; `sufficient_frequency = |{k : nₖ ≥ MinTRLₖ}|/K`. MinTRL is the exact algebraic inverse of the Phase-23 PSR (`PSR = α` solved for `n`), so it reuses the identical estimator-variance term and degeneracy guard — no new statistical method. |
| **D-STATUS** | **`mintrl_status` defensible only at the floor.** `EVALUATED` iff `K ≥ MIN_DETERMINED_TRIALS`, else `UNDEFINED` with `INSUFFICIENT_DETERMINED_TRIALS`; the per-trial cells and the aggregates still seal either way. A family with no determined trials (`K = 0`) seals every aggregate cell as a first-class UNDEFINED (`NO_DETERMINED_TRIALS`) — never a divide-by-zero, never a fabricated length. |
| **D-EXCLUDE** | **UNDEFINED / moment-missing trials are excluded, never imputed.** A source trial the campaign sealed non-VALID is removed from the evaluable family and recorded as a first-class `ExcludedTrial` carrying `TRIAL_UNDEFINED`; a defensively/structurally-unreachable VALID trial whose `sharpe` / `skew` / `kurtosis` is not KNOWN is recorded `MOMENTS_UNDEFINED` — never coerced to a metric, never imputed, never silently dropped; `n_evaluable + n_excluded = n_trials`. An evaluable trial whose Sharpe does not exceed the benchmark (`SHARPE_NOT_ABOVE_BENCHMARK`) or whose estimator variance is non-positive (`DEGENERATE_SHARPE_ESTIMATOR`) seals a first-class UNDEFINED `min_track_record_length` cell whose `excess_length` inherits the same reason. |
| **D-CONSUME** | **Sealed moments are consumed verbatim.** The engine parses each evaluable trial's sealed `sharpe` / `skew` / `kurtosis` decimal strings once (into `Decimal`) and never re-estimates a Sharpe, re-derives a moment from returns, or reads returns. The three moments are carried into the sealed cell as canonical strings; `n` is the source's OOS period count. A VALID trial whose consumed moment cells are malformed (a non-KNOWN cell where classification required KNOWN) is caught by the exclusion classifier (`MOMENTS_UNDEFINED`), never coerced. |
| **D-EXPOST** | **The output is ex-post, never PIT.** A MinTRL analysis over an already-ex-post campaign is itself ex-post. `MinimumTrackRecordLength` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` is carried unchanged from the source campaign and documents only that the *underlying trials were PIT walks*; it never claims the MinTRL output is a PIT value. No new corpus read, no availability logic, no new PIT resolution. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order.** All arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); exact sums / products / divisions, comparisons, `max`/`min`, `Decimal.sqrt` (population dispersion), and the reused `standard_normal_ppf` (the fixed 240-step bisection — bounded, terminating, deterministic; **not** a convergence-tolerance loop) are the only operations; canonicalization is `str(+value)`. No RNG, no data-dependent iteration order, no `_linalg`/`_stats` change, no new numerical primitive. The engine version folds the decimal context, the method version, **and** the normal-primitive version into `config_hash`. |
| **D-IDENTITY** | **Content-addressed, transitively pinned, self-verifying.** `minimum_track_record_length_id` folds the engine version, the request (name, spec version, the canonical `confidence` and `benchmark_sharpe`), the source campaign's `research_result_id` **and** its `result_hash` (the transitive pin), the `MIN_DETERMINED_TRIALS` floor, and the `result_hash` over the computed answer. `research_result_id` aliases `minimum_track_record_length_id`; derived ids are re-emitted by properties, never read from stored state. Domain tag `mintrl/1`. |
| **D-STORE** | **One write-once record in the existing `ResearchResultStore`; no new store, no migration.** `MinimumTrackRecordLength` satisfies the `ResearchRecord` Protocol and persists to `research/sha256-<hex>.json`. An idempotent re-write of a byte-identical payload is a no-op; a conflicting payload under the same id raises `FactorConsistencyError` (the existing store contract). |
| **D-PARAMS** | **Two folded request parameters.** `confidence` (canonical decimal in `(0, 1)`, default `0.95`) and `benchmark_sharpe` (canonical finite decimal, default `0`), both numerically canonicalized at spec construction and folded into `minimum_track_record_length_id`. There is no other numerical parameter; the determined-trials floor is the platform constant `MIN_DETERMINED_TRIALS`. |
| **D-FLOOR** | **`MIN_DETERMINED_TRIALS = 2`**, a module constant in `result.py` (not a spec field, mirroring campaign's `MIN_VALID_TRIALS` and stability's `MIN_STABILITY_TRANSITIONS`), folded into `minimum_track_record_length_id` so a change to it is a distinguishable record. A single determined trial carries no cross-trial dispersion. |
| **D-INVARIANTS** | **MT-1..MT-6 are documented both as phase-local invariants here (§7) and as a small additive `data-model.md §12` block** mirroring the WF-/CE-/SC-/MC-/RC-/WS- blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.25.0`** (Phase 27 = v0.24.0). Domain tag `mintrl/1`; engine-version string `mintrl-engine/1`; method string `mintrl-method/1`; normal-primitive string `mintrl-normal/1`; spec-version string `mintrl/1`; record-format string `mintrl-result/1`. The package `__version__` string is unchanged `"0.0.0"` (versioning is by content-addressed ids + the README table, not a semver string). No `pyproject`/packaging change; no new runtime dependency. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; neither changes an identity discipline or weakens an invariant.

- **The record carries a `method_version` field.** The proposal (§8) enumerated the
  method-version string among the folded identity components but did not spell out a
  *stored* `method_version` on the record. The implementation stores `method_version`
  (default `MINTRL_METHOD_VERSION`) as a first-class record field, round-tripped through
  `to_dict` / `from_dict`. It is **not** folded into `minimum_track_record_length_id`
  separately — the method version already reaches the id through
  `minimum_track_record_length_engine_version_id` (whose `config_hash` folds it), so
  folding it twice would be redundant; the stored field is an auditable record of the
  method that produced the answer. `from_dict` requires it (fail closed on absence), so a
  record's stored bytes disclose their producing method without changing identity
  discipline. (Mirrors the Phase 27 deviation.)
- **The engine entry point is `evaluate`, not `analyze`.** The proposal (§5.5) named the
  method `evaluate`; this is confirmed (the stability layer used `analyze`; the campaign
  and MinTRL layers use `evaluate`). Noted only to make the reused-verb choice explicit.

Resolved ★ decisions of note: capability = per-trial MinTRL + aggregate profile of one
campaign; source is exactly one `ResearchCampaignEvaluation`, consumed by id; output
`MinimumTrackRecordLength`; package `mintrl`, domain tag `mintrl/1`; public names
`MinimumTrackRecordLengthSpecification` / `MinimumTrackRecordLength`; per-trial MinTRL +
excess + aggregate profile; exact-`Decimal`, reuse `standard_normal_ppf`, no new primitive;
ex-post, not a `Pit*`, boundary carried; exclude-never-impute UNDEFINED trials,
`MIN_DETERMINED_TRIALS = 2`; `confidence` / `benchmark_sharpe` folded; identity fold as in
§5; v0.25.0; no `_linalg`/`_stats` change; a sibling package, no prior-phase edit; shared
write-once `ResearchResultStore`.

---

## 2. What was built

New package **`src/quantforge/mintrl/`** (mirrors the P20/P22/P23/P24/P25/P26/P27 layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `MinTrlError` → `MinTrlConfigurationError`, `MinTrlConsistencyError`. |
| `version.py` | `MinimumTrackRecordLengthEngineVersion` (folds the pinned decimal context + `mintrl-method/1` + `mintrl-normal/1` into `config_hash`); constants `MINTRL_SPEC_VERSION` / `MINTRL_ENGINE_VERSION` / `MINTRL_METHOD_VERSION` / `MINTRL_NORMAL_VERSION`; `decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `model.py` | The closed `MinTrlStatus` (`evaluated`, `undefined`), `MinTrlExcludedReason` (`trial_undefined`, `moments_undefined`), `MinTrlUndefinedReason` (`sharpe_not_above_benchmark`, `degenerate_sharpe_estimator`, `no_determined_trials`, `insufficient_determined_trials`), `StatStatus`, and the UNDEFINED-preserving `MinTrlStat` cell (`known` / `undefined` / `to_dict` / `from_dict`). |
| `spec.py` | `MinimumTrackRecordLengthSpecification` (declarative request; fail-closed validation + numeric canonicalization of `confidence`/`benchmark_sharpe`; `name`, `source_campaign_id`, `confidence`, `benchmark_sharpe`, `spec_version = "mintrl/1"`). |
| `compute.py` | The pure exact-`Decimal` procedures: `evaluate_mintrl(evaluable, *, confidence, benchmark, min_determined, context) → MinTrlComputation`; `EvaluableTrial`, `TrialMinTrlComputation`, `MinTrlSummaryComputation`; the per-trial MinTRL (`_trial_min_trl`) and the family aggregate (`_summarize`). |
| `result.py` | `MinimumTrackRecordLength` (`ResearchRecord`; `seal` / `to_dict` / `from_dict`, derived ids, `mintrl_status` / `source_campaign_id` / `source_result_hash` accessors), `TrialMinTrlCell`, `ExcludedTrial`, `MinTrlSummary`, `MinTrlCoverage`; `MIN_DETERMINED_TRIALS = 2`, `MINTRL_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`. |
| `identity.py` | `minimum_track_record_length_result_hash`, `minimum_track_record_length_id`; domain tag `mintrl/1`. |
| `engine.py` | `MinimumTrackRecordLengthEngine.evaluate(spec)`. |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `workspace.py` — one lazy `mintrl_engine` `@property` (+ private `_mintrl_engine`
   cache slot), following the `stability_engine` template (typed `-> object`, deferred
   import of `MinimumTrackRecordLengthEngine` to avoid the module-load cycle).
2. `src/quantforge/__init__.py` — top-level re-exports of
   `MinimumTrackRecordLengthSpecification` and `MinimumTrackRecordLength`, added to the
   sorted `__all__`.

**No edit to** `_linalg`, `campaign`, `walkforward`, `calibration`, `comparison`,
`multiplicity`, `stability`, `optimization`, `factorrisk`, `factorportfolio`, `analytics`,
`backtest`, or any other prior-phase identity/vocabulary. Phase 28 **reuses**
`quantforge._stats.normal.standard_normal_ppf` verbatim (the same primitive Phase 23 uses)
and adds no primitive to `_stats`, so `_stats/normal.py` is untouched.

---

## 3. Data flow

```
MinimumTrackRecordLengthSpecification { name, source_campaign_id, confidence, benchmark_sharpe, spec_version }
        │
        ▼  MinimumTrackRecordLengthEngine.evaluate(spec)
type-check spec is a MinimumTrackRecordLengthSpecification                   — MinTrlConfigurationError
        │
        ▼
resolve the ONE source campaign by id                                       — fail closed (MT-1)
   store.read_as(id, ResearchCampaignEvaluation.from_dict)
   present? decodes as a ResearchCampaignEvaluation? research_result_id == id?  — else MinTrlConsistencyError
        │
        ▼
classify each trial in sealed source order                                  — MT-2/MT-3/MT-4
   VALID + all moments KNOWN → parse sharpe/skew/kurtosis once → EvaluableTrial
   non-VALID → ExcludedTrial(TRIAL_UNDEFINED)
   VALID + a moment not KNOWN → ExcludedTrial(MOMENTS_UNDEFINED)   (defensive)
        │
        ▼  under localcontext(prec 34, ROUND_HALF_EVEN):
   evaluate_mintrl(evaluable, confidence, benchmark, min_determined=MIN_DETERMINED_TRIALS, context)  — MT-3/MT-5
     Z_alpha = Φ⁻¹(confidence)  (reused standard_normal_ppf, once)
     per evaluable trial: V = 1 − γ₃·SR + ((γ₄−1)/4)·SR²
        V ≤ 0            → UNDEFINED DEGENERATE_SHARPE_ESTIMATOR
        SR ≤ SR*         → UNDEFINED SHARPE_NOT_ABOVE_BENCHMARK
        else             → MinTRL = 1 + V·(Z_alpha/(SR−SR*))²;  excess = n − MinTRL
     determined family (K):  mean; population dispersion = √(Σ(m−mean)²/K); max; min;
                             sufficient_frequency = |{n ≥ MinTRL}|/K   (UNDEFINED NO_DETERMINED_TRIALS if K=0)
     mintrl_status = EVALUATED iff K ≥ floor, else UNDEFINED(INSUFFICIENT_DETERMINED_TRIALS)
        │
        ▼
coverage = { n_trials, n_evaluable, n_excluded }   (n_evaluable + n_excluded = n_trials)  — MT-2
        │
        ▼
MinimumTrackRecordLength.seal(...)  (result_hash folds the answer;
   boundary_kind carried from source; source_ref = (source id, source result_hash))  — MT-1/MT-6
        │
        ▼
ResearchResultStore.write(mintrl)   (write-once, idempotent)                — D-STORE
        │
        ▼
store.read_as(id, MinimumTrackRecordLength.from_dict)   (byte-identical typed round-trip)
```

---

## 4. Public API

```python
from quantforge import (
    Workspace,
    MinimumTrackRecordLengthSpecification,
    MinimumTrackRecordLength,
)

ws = Workspace.open(root)

spec = MinimumTrackRecordLengthSpecification(
    name="campaign:min-track-record",
    source_campaign_id=campaign_id,  # exactly one sealed ResearchCampaignEvaluation id
    confidence="0.95",  # optional; canonical decimal in (0, 1), default 0.95
    benchmark_sharpe="0",  # optional; canonical finite decimal, default 0
)

mintrl = ws.mintrl_engine.evaluate(spec)  # sealed, write-once

mintrl.mintrl_status  # EVALUATED / UNDEFINED (roll-up)
mintrl.coverage  # n_trials, n_evaluable, n_excluded
mintrl.trials  # tuple[TrialMinTrlCell]: per-evaluable-trial cells in source order
mintrl.excluded  # tuple[ExcludedTrial]: (label, reason) for excluded trials
mintrl.summary  # MinTrlSummary: aggregate MinTRL profile + status
mintrl.source_campaign_id  # the pinned source campaign id
mintrl.source_result_hash  # the transitive pin
mintrl.research_result_id  # == mintrl.minimum_track_record_length_id

again = ws.research_result_store.read_as(
    mintrl.research_result_id, MinimumTrackRecordLength.from_dict
)
```

`MinimumTrackRecordLengthEngine` is reached only through `Workspace.mintrl_engine`
(lazy, cached, `-> object`). `evaluate(spec) -> MinimumTrackRecordLength` is the single
entry point.

`MinimumTrackRecordLengthSpecification` (frozen slots): `name`, `source_campaign_id`,
`confidence`, `benchmark_sharpe`, `spec_version = "mintrl/1"`. Construction-time
validation (fail closed): non-empty `name` / `spec_version` / `source_campaign_id`;
`confidence` a finite decimal strictly inside `(0, 1)`; `benchmark_sharpe` a finite
decimal (negative allowed); both numerically canonicalized (`str(+Decimal(...))`).

Each `TrialMinTrlCell` carries `label`, `observed_length` (the source `n`), the carried
`sharpe` / `skew` / `kurtosis` (canonical decimal strings), and the UNDEFINED-preserving
`min_track_record_length` and `excess_length` cells. Each `MinTrlSummary` carries five
UNDEFINED-preserving `MinTrlStat` cells (`mean_min_trl`, `min_trl_dispersion`,
`max_min_trl`, `min_min_trl`, `sufficient_frequency`), the `n_determined` count, the
roll-up `mintrl_status`, and an optional `status_reason`.

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `minimum_track_record_length_engine_version_id = sha256(code_version "mintrl-engine/1",
  config_hash)` where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=
  mintrl-method/1\x00normal=mintrl-normal/1")`. Folding the method and normal versions
  makes the record's identity change if the evaluable-trial selection, the per-trial
  MinTRL, any aggregate, or the reused quantile primitive changes.
- `minimum_track_record_length_result_hash = sha256(canonical JSON over the ordered
  computed-output cells: the coverage descriptor
  `{block:"coverage", n_trials, n_evaluable, n_excluded}`, then each evaluable trial
  `{block:"trial", label, observed_length, sharpe, skew, kurtosis,
  min_track_record_length, excess_length}` in source order, then each
  `{block:"excluded", label, reason}`, then `{block:"summary", ...}`)`. Sensitive to every
  carried moment (MT-4) and every computed metric and aggregate.
- `minimum_track_record_length_id = sha256`, NUL-joined, in order: `mintrl/1`,
  `minimum_track_record_length_engine_version_id`, `name`, `spec_version`,
  `source_campaign_id`, `source_result_hash` (the transitive pin, MT-1), `confidence`,
  `benchmark_sharpe`, `str(MIN_DETERMINED_TRIALS)`, and
  `minimum_track_record_length_result_hash`.
- `research_result_id` aliases `minimum_track_record_length_id`. Derived ids are re-emitted
  by properties, never read from stored state — a tampered stored id is ignored and
  `from_dict(to_dict(r))` re-emits identical bytes. The record-format version and the
  stored `method_version` are **not** folded (a container / audit concern; the method
  reaches the id through the engine version). Coverage is **not** folded beyond the
  descriptor (it is a pure function of the sealed trial / excluded lists).

---

## 6. Determinism / Decimal rules

- All MinTRL arithmetic runs under an explicit `localcontext` (precision 34,
  `ROUND_HALF_EVEN`): the per-trial estimator variance `V`, the ratio
  `Z_alpha/(SR − SR*)`, the MinTRL and `excess_length`, the aggregate mean, the `max`/`min`,
  the population dispersion (a `Decimal.sqrt` of a mean-of-squared-deviations), and the
  `sufficient_frequency`. `Z_alpha = Φ⁻¹(confidence)` is the reused deterministic
  `standard_normal_ppf` (the fixed 240-step bisection — bounded, terminating; **not** a
  convergence-tolerance loop), evaluated once. **No float anywhere**, no RNG, no
  wall-clock, no `id()`, no data-dependent iteration order.
- Values are canonicalized as `str(+value)` inside the pinned context; each per-trial
  MinTRL is computed once and reused for every aggregate, so a cell's value and the
  aggregates over it can never disagree.
- Same source campaign + same request → same `minimum_track_record_length_id` and
  byte-identical payload on any machine. A repeated `evaluate` is a byte-identical no-op
  (store idempotence). Two engines over the same immutable sidecar agree. Because Phase 28
  folds the source campaign's `result_hash`, any upstream change changes this record's id
  while a byte-identical recompute reproduces identical bytes (the Phase 22/23 audit
  standard, one layer up).

---

## 7. Invariants (MT-1..MT-6)

Additive to `data-model.md §12`; these do not weaken invariants 1–30.

- **MT-1 — Reference verification and transitive pinning.** The single
  `source_campaign_id` is resolved from the shared sidecar via
  `store.read_as(id, ResearchCampaignEvaluation.from_dict)`, re-verified
  (`research_result_id == id`, and that it decodes as a `ResearchCampaignEvaluation`), and
  its `result_hash` folded into `minimum_track_record_length_id`; through the source
  campaign's own id this pins the walk-forward / optimization / risk-model / factor chain
  beneath it (RC-1). Any missing, non-decoding, or id-mismatched reference fails closed
  with `MinTrlConsistencyError`; the source is never copied, only pinned. *(The RC-1 /
  CE-1 / MC-1 / WS-1 discipline, one layer up.)*
- **MT-2 — The analyzed object is an explicit, sealed family of trials.** Every source
  trial is classified into exactly one of {an evaluable per-trial MinTRL cell, an
  `ExcludedTrial` (UNDEFINED)}, in source order; the coverage (`n_trials`, `n_evaluable`,
  `n_excluded` with `n_evaluable + n_excluded = n_trials`) is sealed so the effective
  sample each aggregate used is auditable and never inferred. One source only (no
  cross-campaign family in v0.25.0).
- **MT-3 — Exclusions and UNDEFINED cells are first-class and never a divide-by-zero.** A
  trial the source sealed UNDEFINED is a first-class `ExcludedTrial` (`TRIAL_UNDEFINED`);
  a defensive VALID-but-missing-moment source trial is `MOMENTS_UNDEFINED` — neither is
  coerced to a metric or imputed. An evaluable trial whose Sharpe does not exceed the
  benchmark (`SHARPE_NOT_ABOVE_BENCHMARK`) or whose Sharpe-estimator variance is
  non-positive (`DEGENERATE_SHARPE_ESTIMATOR`) is a first-class UNDEFINED cell whose
  `excess_length` inherits the same reason, never a division by a zero or negative
  denominator and never a `√` of a non-positive. A determined family below
  `MIN_DETERMINED_TRIALS` seals `mintrl_status` UNDEFINED
  (`INSUFFICIENT_DETERMINED_TRIALS`) with the per-trial cells still sealed; an empty
  determined family seals every aggregate UNDEFINED (`NO_DETERMINED_TRIALS`). Never a
  divide-by-zero. *(The RC-3 / MC-3 / WS-3 posture, adapted to trials.)*
- **MT-4 — Carried moments are consumed verbatim, never recomputed.** Each evaluable
  trial's already-sealed `sharpe` / `skew` / `kurtosis` / `n` cells are read as decimal
  strings and parsed once; the engine never re-derives a moment from returns, never
  re-estimates a Sharpe, and carries the three moments verbatim into the sealed cell. A
  trial whose consumed moment cells are malformed (a non-KNOWN cell where the
  classification required KNOWN) is excluded `MOMENTS_UNDEFINED`, never coerced. *(The
  RC-4 / WS-4 posture of operating over already-sealed strings, one layer up.)*
- **MT-5 — Single deterministic methodology.** One exact-`Decimal` method per cell — the
  Bailey–López de Prado `MinTRL = 1 + V·(Z_alpha/(SR − SR*))²` with
  `V = 1 − γ₃·SR + ((γ₄−1)/4)·SR²` (the identical Sharpe-estimator variance the Phase-23
  PSR uses, of which MinTRL is the exact algebraic inverse), `excess_length = n − MinTRL`,
  and across the determined family the mean / population dispersion / max / min MinTRL and
  the `sufficient_frequency` — all under one pinned decimal context (prec 34,
  `ROUND_HALF_EVEN`) folded into the engine identity, with `Z_alpha = Φ⁻¹(alpha)` computed
  once via the deterministic exact-`Decimal` `standard_normal_ppf` bisection reused
  verbatim from `quantforge/_stats/normal.py` (shared with Phase 23) and `Decimal.sqrt`
  the only other transcendental. `mintrl_status` is `EVALUATED` iff the determined family
  meets `MIN_DETERMINED_TRIALS` (folded into the id), else UNDEFINED; the per-trial cells
  and aggregates still seal. No RNG, no float, no data-dependent iteration, no
  `_linalg`/`_stats` change, no new primitive. *(The RC-5 / MC-5 / WS-5 discipline,
  reusing exact `Decimal` arithmetic.)*
- **MT-6 — A minimum-track-record-length analysis is not a PIT value and not a
  `BacktestResult`.** A MinTRL analysis over an already-ex-post campaign is itself ex-post:
  `MinimumTrackRecordLength` is **not** a `Pit*` type, exposes no as-of accessor, is a
  distinct record type, simulates no fills, and opens no new corpus / availability surface.
  `boundary_kind = "pit"` — carried unchanged from the source campaign — documents only
  that the *underlying trials* were PIT walks. *(The RC-6 / MC-6 / WS-6 discipline, one
  layer up.)*

---

## 8. Failure / UNDEFINED semantics

**Raised** — `MinTrlConfigurationError`: a non-`MinimumTrackRecordLengthSpecification`
argument to the engine; a malformed spec (empty `name` / `spec_version` /
`source_campaign_id`; a `confidence` outside `(0, 1)` or non-decimal; a non-finite
`benchmark_sharpe`). `MinTrlConsistencyError` (MT-1): the `source_campaign_id` absent from
the sidecar; a payload that does not decode as a `ResearchCampaignEvaluation`; a
resolved-id disagreement.

**Recorded as first-class UNDEFINED** (MT-3, never raised): each non-VALID trial is
excluded and recorded as an `ExcludedTrial` with `TRIAL_UNDEFINED`; a defensively
moment-missing VALID trial is excluded `MOMENTS_UNDEFINED`; an evaluable trial with
`SR ≤ SR*` seals `min_track_record_length` / `excess_length` UNDEFINED
(`SHARPE_NOT_ABOVE_BENCHMARK`); an evaluable trial with `V ≤ 0` seals them UNDEFINED
(`DEGENERATE_SHARPE_ESTIMATOR`); a determined family below the floor seals
`mintrl_status = UNDEFINED (INSUFFICIENT_DETERMINED_TRIALS)`; a family with no determined
trials seals every aggregate UNDEFINED (`NO_DETERMINED_TRIALS`).

**Store contract:** a byte-identical re-write is an idempotent no-op; a differing payload
under the same MinTRL id raises `FactorConsistencyError` (the existing write-once guard).

---

## 9. Testing

`tests/mintrl/` (offline, synthetic). Because the engine reads **only** the source
`ResearchCampaignEvaluation` via `store.read_as`, the builders (`tests/mintrl/builders.py`)
construct synthetic `ResearchCampaignEvaluation` records directly — sealing hand-chosen
per-trial moment cells (VALID with KNOWN `sharpe` / `skew` / `kurtosis`, or UNDEFINED
trials) via `ResearchCampaignEvaluation.seal` and writing them to the store — rather than
running the full factor → optimization → walk-forward → campaign chain.

Suites (**63 tests** across the package):
- `test_spec` (11) — the default spec version / parameter defaults, the canonical
  `to_dict`, numeric canonicalization of `confidence` / `benchmark_sharpe`, fail-closed
  rejection of empty fields / out-of-range `confidence` / non-decimal inputs, a negative
  benchmark accepted, frozenness.
- `test_model` (7) — the KNOWN/UNDEFINED `MinTrlStat` construction guards, `to_dict` /
  `from_dict` round-trip, fail-closed decode of corrupt cells, and the closed
  status/reason vocabularies.
- `test_compute` (13) — the pure procedures over synthetic `EvaluableTrial` families:
  the exact MinTRL against a hand-computed value, `excess_length`, the
  `DEGENERATE_SHARPE_ESTIMATOR` and `SHARPE_NOT_ABOVE_BENCHMARK` UNDEFINED cells, the
  aggregate mean / dispersion / max / min / `sufficient_frequency`, the `K = 0`
  `NO_DETERMINED_TRIALS` all-UNDEFINED family, the below-floor
  `INSUFFICIENT_DETERMINED_TRIALS`, and repeated computation identical.
- `test_identity` (5) — `sha256:`-prefixed, deterministic, each-fold-changes-the-id
  (including the transitive `source_result_hash` pin, the `confidence` / `benchmark_sharpe`
  parameters, and the `MIN_DETERMINED_TRIALS` fold), result-hash sensitive to a single
  cell, and order sensitivity.
- `test_result` (10) — seal folds the answer, derived id aliases `research_result_id`,
  byte-identical round-trip, id re-derived not read from state (tampered stored id
  ignored), the accessors, that the record is not a `Pit*` type and exposes no `as_of`,
  a MinTRL change and a carried-moment change each change the hash, `from_dict` rejects an
  unknown excluded reason, and an all-UNDEFINED summary round-trips with its
  `status_reason`.
- `test_public_api` (2) — public exports and the lazy/cached `Workspace.mintrl_engine`.
- `test_engine` (15) — happy path (full family, aggregates match a fixture, per-trial
  cells map back to source order), source reference pinned, UNDEFINED-trial exclusion,
  the `SHARPE_NOT_ABOVE_BENCHMARK` / `DEGENERATE_SHARPE_ESTIMATOR` UNDEFINED cells,
  below-floor still seals, `confidence` / `benchmark_sharpe` change the answer and the id,
  boundary carried and the record not PIT; recompute byte-identical and idempotent; and
  every fail-closed guard (absent source, non-`ResearchCampaignEvaluation` record,
  id-mismatch via a path-swapped payload, non-spec argument, and a tampered stored payload
  → `FactorConsistencyError`).

**Gate (all green): `ruff check .` / `ruff format --check .` / `mypy src tests` /
`pytest -q` / `pytest -q -p no:randomly`; zero new runtime dependencies; every prior-phase
id preserved (no prior source touched beyond the additive `workspace.py` / `__init__.py`
re-exports).**
