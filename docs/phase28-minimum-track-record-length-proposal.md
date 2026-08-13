# Phase 28 Proposal — Minimum Track Record Length (MinTRL)

> **Status: PROPOSAL / DESIGN.** Selected under the standing Phases 27–30 accelerated-batch
> directive (architecture correctness takes priority over phase count). This document records
> the design and the load-bearing decisions; the normative record of what was actually built is
> `docs/phase28-minimum-track-record-length-locked.md`.
>
> **Verified repository state (not assumed):** `HEAD = 394d529` "feat: add Phase 27 walk-forward
> turnover & stability"; latest tag `v0.24.0`. Phases 1–27 are implemented and released. This
> design read the live tree (`campaign/`, `calibration/`, `_stats/normal.py`), not prior
> summaries or memory.

---

## 0. Executive recommendation (one line)

**Phase 28 = Minimum Track Record Length (MinTRL)** — a pure ex-post consumer of **one** sealed
`ResearchCampaignEvaluation` (Phase 23) that reads its already-sealed per-trial out-of-sample
`sharpe` / `skew` / `kurtosis` / `n` and, per trial, seals the Bailey–López de Prado minimum
track-record length `MinTRL(SR*)` — *"how many out-of-sample periods would this strategy need
before its observed Sharpe is significant, at confidence `α`, against a benchmark Sharpe `SR*`?"*
— plus the aggregate MinTRL profile across the campaign's trials. It is the **first consumer of
Phase 23's per-trial moment block** (Phase 23 is otherwise a terminal leaf), needs **no** new
numerical primitive (it reuses the existing deterministic `standard_normal_ppf`), **no** `_linalg`
change, **no** prior-phase edit, and is exact-Decimal, deterministic, and ex-post-honest.

---

## 1. What Phase 23 seals (verified) and what MinTRL consumes

`ResearchCampaignEvaluation` (`campaign/result.py`) seals, per trial in request order, a
`TrialStat(label, status, n, sharpe, skew, kurtosis, psr)` where `status ∈ {VALID, UNDEFINED}`,
`n` is the OOS period count, and `sharpe` / `skew` / `kurtosis` / `psr` are UNDEFINED-preserving
`StatValue` cells (KNOWN canonical decimal string, or UNDEFINED with a `CampaignUndefinedReason`).
A `VALID` trial carries KNOWN `sharpe` / `skew` / `kurtosis` (all three are estimated together
from the same OOS moment set; a defined Sharpe ⇒ all three defined). `sharpe` is a **per-period**
Sharpe (the `campaign/moments.py` convention).

MinTRL consumes exactly the `(status, n, sharpe, skew, kurtosis)` per-trial block — never the
`psr`, never the campaign summary, never anything beneath the campaign. Phase 23 is currently a
**terminal leaf** (no consumer reads its per-trial moments); MinTRL is the first.

## 2. The MinTRL statistic (pinned formula)

Bailey & López de Prado (2012), *The Sharpe Ratio Efficient Frontier*:

```
MinTRL(SR*) = 1 + [ 1 - γ₃·SR + ((γ₄ - 1)/4)·SR² ] · ( Z_α / (SR - SR*) )²
```

where `SR` is the trial's per-period Sharpe, `SR*` the benchmark Sharpe (request parameter,
default `0`), `γ₃` its skew, `γ₄` its non-excess kurtosis, and `Z_α = Φ⁻¹(α)` the standard-normal
quantile at the request confidence `α` (default `0.95`).

This is the exact inverse of the Phase-23 Probabilistic Sharpe Ratio: `PSR(SR*) =
Φ((SR-SR*)·√(n-1)/√V)` with estimator variance `V = 1 - γ₃·SR + ((γ₄-1)/4)·SR²`; setting
`PSR = α` and solving for `n` yields `n = 1 + V·(Z_α/(SR-SR*))² = MinTRL`. So MinTRL reuses the
**identical** estimator-variance term and the identical degeneracy guard as Phase 23's PSR — no
new statistical method, only the algebraic inverse.

**Interpretation.** A trial's observed record of `n` periods is *sufficient* iff `n ≥ MinTRL`.
The per-trial `excess_length = n - MinTRL` (positive ⇒ already long enough).

## 3. Per-trial classification and UNDEFINED semantics (fail closed)

Each source trial is classified (mirroring the calibration layer's window classification):

- **Excluded from the evaluable family** — a trial the source sealed `UNDEFINED`
  (`TRIAL_UNDEFINED`); or, defensively/structurally-unreachable, a `VALID` trial whose
  `sharpe` / `skew` / `kurtosis` is not KNOWN (`MOMENTS_UNDEFINED`). Recorded as a first-class
  `ExcludedTrial(label, reason)`, never imputed.
- **Evaluable** — a `VALID` trial with KNOWN moments. It gets a per-trial cell; its
  `min_track_record_length` is either:
  - **KNOWN** — the computed `MinTRL` decimal (`determined` trial); or
  - **UNDEFINED `SHARPE_NOT_ABOVE_BENCHMARK`** — `SR ≤ SR*`, so no finite record establishes
    significance (`(SR-SR*)` non-positive); or
  - **UNDEFINED `DEGENERATE_SHARPE_ESTIMATOR`** — `V ≤ 0` (a razor-edge moment set; `V ≥ 0` for
    any valid moment set by the skew–kurtosis inequality `γ₄ ≥ 1 + γ₃²`), never a `√` of a
    non-positive number.

`n_trials = n_evaluable + n_excluded`; `n_determined ≤ n_evaluable` is the count of evaluable
trials with a KNOWN MinTRL. Aggregates are over the **determined** trials.

## 4. Aggregate summary

Over the determined trials (`K = n_determined ≥ 1`), all UNDEFINED-preserving cells:
`mean_min_trl`, `min_trl_dispersion` (population std), `max_min_trl`, `min_min_trl`,
`sufficient_frequency = |{ determined : n ≥ MinTRL }| / K`, plus the count `n_determined`.
`mintrl_status` is `EVALUATED` iff `K ≥ MIN_DETERMINED_TRIALS = 2` (a cross-trial dispersion needs
a pair), else `UNDEFINED` (`INSUFFICIENT_DETERMINED_TRIALS`). With `K = 0` every aggregate cell is
`UNDEFINED NO_DETERMINED_TRIALS` and the status is `UNDEFINED INSUFFICIENT_DETERMINED_TRIALS`; the
record still seals. (Exactly the calibration `K==0` / `K<min` split.)

---

## 5. Load-bearing decisions (★)

1. **★ Capability scope** — per-trial MinTRL + aggregate profile over one sealed campaign; a
   descriptive selection-bias adjunct, no correction/optimization/execution.
2. **★ Input artifact** — exactly one sealed `ResearchCampaignEvaluation` (by id). No multi-source
   family in v1.
3. **★ Output artifact** — `MinimumTrackRecordLength`.
4. **★ Package** — `src/quantforge/mintrl/`. **★ Domain tag** — `mintrl/1`.
5. **★ Public type names** — `MinimumTrackRecordLengthSpecification`, `MinimumTrackRecordLength`
   (+ nested `TrialMinTrlCell`, `ExcludedTrial`, `MinTrlSummary`, `MinTrlCoverage`); engine
   `MinimumTrackRecordLengthEngine.evaluate(spec)` reached via `Workspace.mintrl_engine`.
6. **★ Numerical methodology** — the pinned MinTRL formula (§2); reuses the existing
   `standard_normal_ppf` for `Z_α`; `Decimal.sqrt`/no other transcendental.
7. **★ Request parameters** — `confidence` (canonical decimal in `(0,1)`, default `0.95`) and
   `benchmark_sharpe` (canonical finite decimal, default `0`), both folded into identity.
8. **★ Determinism** — exact-Decimal, prec 34 / ROUND_HALF_EVEN; no RNG / float / wall-clock; the
   only iteration is the *already-pinned* fixed 240-step `standard_normal_ppf` bisection.
9. **★ PIT / ex-post** — ex-post; not a `Pit*` type; no as-of accessor; `boundary_kind="pit"`
   carried unchanged from the source campaign.
10. **★ UNDEFINED semantics** — §3; `MIN_DETERMINED_TRIALS = 2`, folded into identity.
11. **★ Identity fold** — domain, engine version, name, spec_version, `source_campaign_id`,
    `source_result_hash` (transitive pin), `confidence`, `benchmark_sharpe`,
    `MIN_DETERMINED_TRIALS`, `result_hash`.
12. **★ Version** — **v0.25.0**.
13. **★ `_linalg` / `_stats` changes** — **NONE.** MinTRL *reuses* `_stats.normal.standard_normal_ppf`
    verbatim; it adds no primitive and edits none.
14. **★ Sibling vs extension** — a **sibling** new package; **no** edit to `campaign/` vocabulary,
    engine, or identity. Only an additive `Workspace` property + top-level exports.
15. **★ Persistence** — shared `ResearchResultStore`, write-once, idempotent, fail-closed; no new
    store.

---

## 6. Numerical-method audit

- **Exact formulae:** the MinTRL of §2; `excess_length = n - MinTRL`; `mean_min_trl = ΣMinTRL/K`;
  `min_trl_dispersion = √(Σ(MinTRLₖ - mean)²/K)` (population); `sufficient_frequency =
  count(n≥MinTRL)/K`; `max`/`min`.
- **Decimal:** all values `Decimal` under an explicit `localcontext` (prec 34, ROUND_HALF_EVEN).
- **`Decimal.sqrt`** is the only elementary transcendental in this layer's own arithmetic.
- **`_stats` reuse:** `standard_normal_ppf(confidence, context=…)` for `Z_α` (the fixed 240-step
  bisection — deterministic, bounded, terminating; **not** a convergence-tolerance loop). Its
  version is folded via a `mintrl-normal/1` config component, mirroring Phase 23's
  `campaign-normal/1`.
- **`_linalg`?** unused. **RNG / wall-clock / input-order dependence?** none.

## 7. PIT / ex-post audit

- **Ex-post** — MinTRL is a function of realized OOS moments already sealed on the source campaign;
  no corpus/price/panel is re-read; no new PIT surface.
- **Not a `Pit*` type; no `as_of` accessor** (the inv-28 firewall). `boundary_kind="pit"` (carried
  from the source) documents only that the *underlying trials were PIT walks*.
- A terminal leaf: no ex-post field is fed back into any as-of-`T` computation.

## 8. Identity & persistence audit

- **Domain** `mintrl/1`; **record-format** `mintrl-result/1`; **engine/method/normal versions**
  `mintrl-engine/1` / `mintrl-method/1` / `mintrl-normal/1`.
- `minimum_track_record_length_id` folds domain, engine version, `name`, `spec_version`,
  `source_campaign_id`, `source_result_hash` (transitive pin of the whole chain beneath the
  campaign), `confidence`, `benchmark_sharpe`, `MIN_DETERMINED_TRIALS`, and `result_hash`.
- `result_hash` = canonical JSON over ordered computed cells — the coverage descriptor, then per
  evaluable trial (`label`, `observed_length`, `sharpe`, `skew`, `kurtosis`,
  `min_track_record_length`, `excess_length`) in source order, then excluded trials
  (`label`, `reason`), then the aggregate summary.
- `config_hash` over `prec=34\x00round=ROUND_HALF_EVEN\x00method=mintrl-method/1\x00normal=mintrl-normal/1`,
  folded into the engine version.
- Canonical serialization (`_SEP="\x00"`, canonical JSON, `sha256:`); derived ids re-emitted by
  properties. Write-once shared store; a differing payload under the same id raises
  `FactorConsistencyError`; a missing / non-`ResearchCampaignEvaluation` / id-mismatched source
  raises `MinTrlConsistencyError`.

---

## 9. Proposed phase-local invariants (MT-1 .. MT-6)

Additive to `data-model.md §12`; they do **not** weaken invariants 1–30 or any prior family.

- **MT-1 — Reference verification & transitive pinning.** The single `source_campaign_id` is
  resolved via `read_as(id, ResearchCampaignEvaluation.from_dict)`, re-verified
  (`research_result_id == id`; decodes as a `ResearchCampaignEvaluation`), and its `result_hash`
  folded into `minimum_track_record_length_id`. Missing/non-decoding/id-mismatched ⇒
  `MinTrlConsistencyError`.
- **MT-2 — Explicit evaluable family + sealed coverage.** Coverage (`n_trials`, `n_evaluable`,
  `n_excluded`; `n_evaluable + n_excluded = n_trials`) is sealed so the effective sample is
  auditable.
- **MT-3 — Undefined trials excluded, degenerate MinTRLs recorded UNDEFINED, never imputed.** A
  source-`UNDEFINED` (or defensively moments-undefined) trial is a first-class `ExcludedTrial`; an
  evaluable trial with `SR ≤ SR*` or `V ≤ 0` seals an UNDEFINED `min_track_record_length` cell
  with its reason. No divide-by-zero, no `√` of a non-positive, no fabricated length.
- **MT-4 — Moments consumed, never recomputed.** `sharpe` / `skew` / `kurtosis` / `n` are consumed
  exactly as the source campaign sealed them; MinTRL re-derives no moment and re-resolves nothing
  beneath the campaign.
- **MT-5 — Single deterministic methodology.** One exact-Decimal MinTRL under one pinned context
  (prec 34, ROUND_HALF_EVEN); the only transcendental beyond `Decimal.sqrt` is the pinned
  `standard_normal_ppf`; no RNG/float/wall-clock/`_linalg`/new primitive; one uniform definition of
  each statistic.
- **MT-6 — A MinTRL evaluation is not a PIT value and not a `BacktestResult`.** It is an ex-post
  significance-horizon statistic; not a `Pit*` type, no as-of accessor
  (`boundary_kind="pit"` documents only the underlying PIT walks), a distinct record type, no
  fills/cash/positions/costs.

---

## 10. Out of scope

Multi-source families; any correction/test on the MinTRL family; annualization conventions
(MinTRL is reported in the source's per-period units); rolling/regime MinTRL; any `_linalg`/`_stats`
change; any new store, RNG, float, corpus read, `as_of` surface, ingestion, UI, or API; any
modification to Phase 23 (or any prior phase) vocabulary, engine, or identity; feeding the
evaluation into any prior phase.
