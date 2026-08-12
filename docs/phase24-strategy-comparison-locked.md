# Phase 24 — Pairwise Out-of-Sample Strategy Comparison (LOCKED)

> **Status:** Locked normative specification. The Phase 24 proposal was **approved as
> recommended** — the recommended capability (§4 / §18 of the proposal, not the deferred
> alternatives): consume an ordered set of `2..N_MAX` sealed `WalkForwardEvaluation`
> records that share a rebalance schedule, producing factor-portfolio engine version,
> annualization convention, and per-period risk-free rate; align their realized
> out-of-sample (OOS) per-period return series; and seal an **upper-triangle** matrix of
> **paired-difference** comparison cells (mean per-period return difference, its standard
> error and `t` statistic, a deterministic two-sided `p` value, the descriptive Sharpe
> point difference, and the overlap count), plus a per-strategy summary and a coverage
> block. This document reflects the **actual implementation** and is the source of truth;
> it supersedes the recommendations in
> [phase24-strategy-comparison-proposal.md](phase24-strategy-comparison-proposal.md).
> Every ★-marked decision in the proposal is resolved here to a committed decision, and
> the two disclosed deviations from the proposal are recorded in §1.1.
>
> **One-line thesis:** Phase 24 adds a deterministic, content-addressed **relative /
> comparative testing** layer — the platform's first head-to-head OOS comparison, and the
> second genuine *consumer* of the Phase 22 terminal leaf (alongside Phase 23's absolute
> selection-bias correction). Given a declarative `StrategyComparisonSpecification` naming
> an ordered set of `2..N_MAX(=32)` sealed `WalkForwardEvaluation` records (the *strategies*
> of one comparison), `StrategyComparisonEngine.compare(...)` resolves each strategy from
> the shared Phase 8 research sidecar, re-verifies it (and that it is `REALIZED`), enforces
> that the strategies are **commensurable** (one shared `schedule_id`,
> `factor_portfolio_engine_version_id`, `periods_per_year`, **and** `risk_free_per_period`),
> **reconstructs** each strategy's realized OOS return series by re-resolving its transitive
> `optimization → risk model → factors` chain and recomputing the deterministic
> complete-case **calendar-date** axis, then over each upper-triangle `(i<j)` pair forms the
> paired-difference series over the shared calendar dates and seals the mean difference, its
> population-variance standard error, the paired `t` statistic, the two-sided `p = 2·(1 −
> Φ(|t|))`, and the descriptive Sharpe difference. It seals a `StrategyComparison`
> `ResearchRecord` write-once to the existing sidecar. It introduces **no** new numerical
> primitive (it reuses the Phase 23 exact-`Decimal` normal `Φ`, now extracted to a shared
> `_stats` module), **no** `_linalg` change, **no** RNG, **no** data-dependent iteration,
> **no** new store, **no** runtime dependency, **no** new PIT surface, and **no**
> modification to any prior phase's vocabulary, engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **Pairwise paired-difference OOS comparison, measurement-only.** For each unordered strategy pair, align the two realized OOS return series and seal the mean per-period difference, its standard error, the paired `t`, a two-sided `p` value, a descriptive Sharpe point difference, and the overlap. **No** family-wise / FDR multiple-comparison adjustment (a clean future consumer, SC-7); **no** Sharpe-difference significance (Jobson–Korkie/Memmel needs cross-series correlation + higher moments — deferred, §11.4); **no** finite-sample `t`-distribution (large-sample normal `p`, disclosed). It performs **no execution** and is **not** a `BacktestResult` (SC-6). |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 22.** It resolves an ordered set of `2..N_MAX` already-sealed `WalkForwardEvaluation` records (the strategies) from the shared sidecar, and transitively their `optimization → risk model → factors → corpora`. It reads **no** raw corpus, fabricates **no** expected-return / `μ`, and **modifies no** prior-phase vocabulary, engine, or identity. It is the second functional consumer of the Phase 22 terminal leaf, and the first to read `oos_returns` as a *series*. |
| **D-ALIGN** | **Date reconstruction, aligned by calendar-date intersection (deviation, §1.1).** A sealed `WalkForwardEvaluation` seals **no dates** — its per-window `[test_start, test_end)` ranges are indices into a complete-case date axis it computed but did not store, and each strategy has its *own* axis. So Phase 24 **reconstructs** each strategy's axis by re-resolving its transitive chain and recomputing the complete-case date axis with the **identical** logic the walk-forward engine used (`_known_returns` / `_common_dates`), maps each REALIZED window's returns to `(as_of → return)`, and aligns each pair by **calendar-date intersection** — *not* by the proposal's SC-3 axis-index alignment (which would compare returns from different instants whenever two strategies' axes differ). Two fail-closed guards bind the reconstruction to the sealed record: the reconstructed axis length must equal the sealed `common_periods`, and the concatenated REALIZED windows must reproduce the sealed chained `oos_returns` exactly (SC-1/SC-3). |
| **D-STATS** | **Exact-`Decimal` paired-difference statistics (`comparison-method/1`).** Over the shared dates with overlap `T ≥ MIN_OVERLAP_PERIODS = 2`: `d_t = r_t^i − r_t^j`; `d̄ = Σd/T`; **population** variance `s²_d = Σ(d−d̄)²/T` (divisor `T`, the project's population-moment convention); `stderr = √(s²_d / T)` (one `Decimal.sqrt`); `t = d̄ / stderr`; `p = 2·(1 − Φ(|t|))` clamped to `[0,1]` via the shared exact-`Decimal` `Φ`. All under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`). |
| **D-SHARPE** | **Descriptive Sharpe difference of the sealed *annualized* OOS Sharpe (★15 → annualized).** `sharpe_diff = Sharpe_i − Sharpe_j`, differencing each strategy's **sealed** `summary.annualized_sharpe` (a pure descriptive passthrough, never recomputed). No significance test is attached (D-SCOPE). KNOWN when both legs sealed a KNOWN Sharpe and the pair overlaps; UNDEFINED `UNDEFINED_STRATEGY_SHARPE` when either leg's sealed Sharpe is undefined (§1.1). |
| **D-NORMAL** | **Reuse the Phase 23 exact-`Decimal` normal `Φ`, extracted to a shared `_stats/normal.py` (proposal §19 option a, the recommended path).** The `Φ` / `Z⁻¹` implementation now lives in `quantforge/_stats/normal.py` (the deterministic-primitive analogue of `_linalg`); `campaign/normal.py` re-exports the three public names verbatim so every Phase 23 import, its `campaign-normal/1` pin, and every sealed Phase 23 id are unchanged — a **byte-identical refactor**. Phase 24 imports `standard_normal_cdf` from the shared module for its two-sided `p` value. **No** new primitive, **no** `_linalg` change. |
| **D-ANTISYM** | **Only the `i<j` upper triangle is stored; `(j,i)` is a derived sign-flip (SC-8).** `StrategyComparison.cell(i,j)` returns the stored cell for `i<j` and its `transpose()` for `i>j` — sign-flipping `mean_diff` / `t_stat` / `sharpe_diff`, preserving `p_value` / `stderr_diff` / `overlap_periods`, swapping labels. `i==j` raises (the matrix has no diagonal). The sign flip is **exact**: `Decimal.copy_negate` (context-free), not unary `-` (which would round to the ambient context); a negated zero is re-canonicalized to positive zero. |
| **D-DEGENERACY** | **Fail-closed, UNDEFINED-preserving, never repaired (SC-4).** A pair with overlap `< MIN_OVERLAP_PERIODS` → an all-UNDEFINED cell (`INSUFFICIENT_OVERLAP`); a pair whose paired-difference has exactly zero population variance → UNDEFINED `t_stat`/`p_value` (`ZERO_DIFFERENCE_VARIANCE`) with `mean_diff`/`stderr_diff`/`sharpe_diff` KNOWN; a pair where either leg's sealed Sharpe is undefined → UNDEFINED `sharpe_diff` (`UNDEFINED_STRATEGY_SHARPE`) with the paired-difference statistics unaffected. No branch divides by zero; the record always seals. |
| **D-EXPOST** | **The output is ex-post, never PIT (SC-6).** A comparison of realized OOS series is ex-post. `StrategyComparison` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` documents only that the *underlying strategies were PIT walks*; it never claims the comparison statistic is a PIT value. Set unconditionally, so **no new PIT resolution** is introduced. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order (SC-5).** All arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); the standard error via `Decimal.sqrt`; the reused `Φ`'s internal bisection is fixed-depth. Canonical cell strings are `str(value)` produced inside the pinned context. Alignment is pure string/set manipulation over sealed decimal strings. The engine version folds the decimal context **and** the composed method + normal-primitive versions. |
| **D-INVARIANTS** | **SC-1..SC-8 are documented both as phase-local invariants here and as a small additive `data-model.md §12` block** mirroring the SD-/XS-/P19-/FR-/PO-/WF-/CE- blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.21.0`** (Phase 23 = v0.20.0). Domain tag `comparison/1`; engine-version string `comparison-engine/1`; method string `comparison-method/1`; normal-primitive string `comparison-normal/1`; record-format string `comparison-result/1`; `N_MAX = 32`, `MIN_OVERLAP_PERIODS = 2`. The package `__version__` string is unchanged `"0.0.0"` (versioning is by content-addressed ids + the README table, not a semver string). No `pyproject`/packaging change; no new runtime dependency. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; neither changes an identity discipline nor weakens an invariant.

- **Alignment by calendar-date reconstruction, not axis index (proposal SC-3 changed).**
  The proposal's SC-3 aligned two strategies by **axis index** reconstructed from each
  strategy's sealed per-window `(test_start, test_end)` ranges. During implementation this
  was found to be **unsound**: a `WalkForwardEvaluation` seals no dates, and each strategy
  has its *own* complete-case date axis (its factors' complete-case intersection can
  differ), so equal axis indices need not denote the same calendar instant. Aligning by
  axis index would compare returns from different dates whenever two strategies' axes
  differ. The implementation therefore **reconstructs each strategy's calendar-date axis**
  — re-resolving the transitive chain `optimization_ref → PortfolioOptimization.risk_model_ref
  → FactorRiskModel factor refs → FactorPortfolio.per_period`, verifying every id and
  `result_hash` against the pin (SC-1), and recomputing the complete-case axis with the
  **identical** `_known_returns` / `_common_dates` logic the walk-forward engine used
  (WF-6) — maps each REALIZED window's `oos_returns[k]` to `common_dates[test_start + k]`,
  and aligns each pair by **calendar-date intersection**. This is `comparison-method/1`.
  Consequence: `align.py` performs the transitive-chain reconstruction (with two
  fail-closed drift guards binding it to the sealed `common_periods` and `oos_returns`),
  and SC-3 below is stated as *date-reconstruction* alignment.
- **A third UNDEFINED reason `UNDEFINED_STRATEGY_SHARPE` (proposal §18.8 closed set was
  two).** The proposal's closed vocabulary was `{INSUFFICIENT_OVERLAP,
  ZERO_DIFFERENCE_VARIANCE}` (with a `DEGENERATE_INPUT` fallback anticipated, disclosed
  "like Phase 23's 4th reason"). Implementation adds `UNDEFINED_STRATEGY_SHARPE`, recorded
  on the `sharpe_diff` cell (and the per-strategy summary Sharpe) when a strategy's sealed
  annualized OOS Sharpe is itself UNDEFINED (its chained OOS series had zero return
  variance), so the descriptive Sharpe difference cannot be formed. The paired-difference
  `t` statistic is unaffected. Structurally rare (a REALIZED walk almost always has a
  defined Sharpe), retained as a fail-closed guard rather than a fabricated difference. The
  vocabulary remains closed — now with three members. (Exactly the Phase 23 precedent of a
  disclosed additional reason.)

Resolved ★ decisions of note: **★2** artifact name `StrategyComparison`; **★3** package
`comparison`; **★4** `N_MAX = 32`; **★5** paired-difference t-test + descriptive
`sharpe_diff`, Sharpe-difference significance deferred; **★6** `Φ` via the shared
`_stats/normal.py` byte-identical refactor; **★7** complete-case alignment (by date, per
D-ALIGN); **★8** `MIN_OVERLAP_PERIODS = 2`; **★14** two-sided p-values; **★15** the
`TrialSummary` Sharpe is the sealed **annualized** OOS Sharpe.

---

## 2. What was built

New package **`src/quantforge/comparison/`** (mirrors the P20/P22/P23 layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `ComparisonError` → `ComparisonConfigurationError`, `ComparisonConsistencyError`. |
| `version.py` | `StrategyComparisonEngineVersion` (folds the pinned decimal context + `comparison-method/1` + `comparison-normal/1` into `config_hash`); constants `COMPARISON_SPEC_VERSION`/`COMPARISON_ENGINE_VERSION`/`COMPARISON_METHOD_VERSION`/`COMPARISON_NORMAL_VERSION`; `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `model.py` | `ComparisonStatus` (`KNOWN`/`UNDEFINED`); `StatStatus`; the **closed** `ComparisonUndefinedReason` (three members, §1.1); `StatValue` (KNOWN decimal string \| UNDEFINED + reason); `strategy_label(index) → "strategy_{index+1}"`. |
| `spec.py` | `StrategyComparisonSpecification` (declarative request; fail-closed validation); `N_MAX = 32`, `_MIN_STRATEGIES = 2`. |
| `align.py` | **The date-reconstruction alignment (D-ALIGN):** `reconstruct_strategy(evaluation, store) → ReconstructedStrategy{walk_forward_id, returns: dict[as_of,str], axis_periods}`; transitive-chain resolution (fail closed) + the walk engine's complete-case axis (WF-6). |
| `compute.py` | Pure exact-`Decimal` paired-difference core: `compare_pair(...) → PairComputation`; `MIN_OVERLAP_PERIODS = 2`. Reuses `_stats.normal.standard_normal_cdf`. |
| `result.py` | `StrategyComparison` (`ResearchRecord`; `seal`/`to_dict`/`from_dict`, derived ids, `cell`/`transpose`), `ComparisonCell`, `TrialSummary`, `Coverage`; `COMPARISON_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`. |
| `identity.py` | `strategy_comparison_result_hash`, `strategy_comparison_id`; domain tag `comparison/1`. |
| `engine.py` | `StrategyComparisonEngine.compare(spec)`. |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `src/quantforge/_stats/normal.py` — **new shared module**; the byte-identical extraction
   of `campaign/normal.py`'s `Φ` / `Z⁻¹` / `EULER_MASCHERONI` (D-NORMAL). `campaign/normal.py`
   now re-exports these three names verbatim, so every Phase 23 id is preserved.
2. `workspace.py` — one lazy `comparison_engine` `@property` (+ private cache slot),
   following the `campaign_engine` template (typed `-> object`, deferred import).
3. `src/quantforge/__init__.py` — top-level re-exports of `StrategyComparisonSpecification`
   and `StrategyComparison`, added to the sorted `__all__`.
4. `tests/test_smoke.py` — one additive export assertion.

**No edit to** `_linalg`, `walkforward`, `optimization`, `factorrisk`, `factorportfolio`,
`campaign` (beyond the byte-identical `normal.py` re-export), `analytics`, `backtest`, or
any other prior-phase identity/vocabulary.

---

## 3. Data flow

```
StrategyComparisonSpecification { walk_forward_ids[2..N_MAX], name, spec_version }
        │
        ▼  StrategyComparisonEngine.compare(spec)
resolve each WalkForwardEvaluation by id, in request order                 — fail closed (SC-1)
   store.read_as(id, WalkForwardEvaluation.from_dict); verify research_result_id == id;
   verify roll-up status is REALIZED
        │
        ▼
enforce commensurability: one shared schedule_id AND                       — fail closed (SC-2)
   factor_portfolio_engine_version_id AND periods_per_year AND risk_free_per_period
        │
        ▼  per strategy (deterministic, fail closed — SC-1/SC-3):
   re-resolve optimization_ref → risk_model_ref → factor refs (verify id + result_hash)
   recompute complete-case calendar axis  (identical to walk engine _known_returns/_common_dates)
   guard: len(axis) == sealed common_periods                                (WF-6)
   map each REALIZED window's oos_returns[k] → common_dates[test_start+k] → {as_of: return}
   guard: concatenated REALIZED returns == sealed oos_returns
        │
        ▼  per upper-triangle pair (i<j), over the shared calendar dates:
   T = |dates_i ∩ dates_j|
   T < MIN_OVERLAP_PERIODS (2) → UNDEFINED cell (INSUFFICIENT_OVERLAP)                — SC-4
   d_t = r_t^i − r_t^j ; d̄ = Σd/T ; s²_d = Σ(d−d̄)²/T                    (population; Decimal.sqrt)
   s²_d == 0 → t/p UNDEFINED (ZERO_DIFFERENCE_VARIANCE), mean_diff KNOWN               — SC-4
   stderr = √(s²_d/T) ; t = d̄/stderr ; p = 2·(1 − Φ(|t|)) clamped [0,1]               — SC-5
   sharpe_diff = Sharpe_i − Sharpe_j  (sealed annualized; UNDEFINED_STRATEGY_SHARPE if a leg undefined)
        │
        ▼
StrategyComparison.seal(...)  →  ResearchResultStore.write (write-once, idempotent)
        │
        ▼
store.read_as(id, StrategyComparison.from_dict)   (byte-identical typed round-trip)
```

Corpus pins (`dataset_version_ids`, `market_dataset_version_ids`) are the sorted-distinct
union of the referenced records' pins; more than one distinct value surfaces `pin_mismatch`
(never raised) — identical to Phase 20/23.

---

## 4. Public API

```python
from quantforge import (
    Workspace,
    StrategyComparisonSpecification,
    StrategyComparison,
)

ws = Workspace.open(root)

spec = StrategyComparisonSpecification(
    name="value-vs-momentum-vs-quality",
    walk_forward_ids=(
        wf_id_1,
        wf_id_2,
        ...,
        wf_id_k,
    ),  # 2..N_MAX sealed WalkForwardEvaluation ids
)

comparison = ws.comparison_engine.compare(spec)  # sealed, write-once

comparison.cell(0, 1)  # ComparisonCell for the ordered pair (upper-triangle stored)
comparison.cell(1, 0)  # its exact (j,i) transpose (sign-flipped mean/t/sharpe)
comparison.trials  # tuple[TrialSummary]: label, sharpe, n_valid_periods, axis_periods
comparison.coverage  # n_strategies, n_pairs, n_defined_pairs, n_undefined_pairs
comparison.walk_forward_ids  # referenced ids, request order
comparison.pin_mismatch  # inherited corpus-pin flag
comparison.research_result_id  # == comparison.strategy_comparison_id

again = ws.research_result_store.read_as(
    comparison.research_result_id, StrategyComparison.from_dict
)
```

`StrategyComparisonEngine` is reached only through `Workspace.comparison_engine` (lazy,
cached, `-> object`). `compare(spec) -> StrategyComparison` is the single entry point.

`StrategyComparisonSpecification` (frozen slots): `name`, `walk_forward_ids`
(`tuple[str, ...]`), `spec_version = "comparison/1"`. Construction-time validation (fail
closed): non-empty `name` / `spec_version`; `2 ≤ len(walk_forward_ids) ≤ N_MAX`;
`walk_forward_ids` a tuple, distinct and non-empty (self-comparison rejected).

Each `ComparisonCell` carries `i`, `j`, `label_i`, `label_j`, `status`, `overlap_periods`,
and the five UNDEFINED-preserving `StatValue`s (`mean_diff`, `stderr_diff`, `t_stat`,
`p_value`, `sharpe_diff`), plus an optional pair-level `reason`.

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `strategy_comparison_engine_version_id = sha256(code_version "comparison-engine/1", config_hash)`
  where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=comparison-method/1\x00normal=comparison-normal/1")`.
  Folding the method and normal-primitive versions makes the comparison's identity change
  if the alignment/paired-difference/Sharpe method or the shared `Φ` implementation changes.
- `strategy_comparison_result_hash = sha256(canonical JSON over the ordered computed-output
  cells: each per-strategy `{block:"strategy", label, sharpe, n_valid_periods, axis_periods}`
  in request order, then each pairwise `{block:"pair", i, j, status, overlap_periods,
  mean_diff, stderr_diff, t_stat, p_value, sharpe_diff, reason?}` in upper-triangle `(i,j)`
  ascending order)`. The derivable `label_i`/`label_j` are omitted from the pairwise cell
  (the `i`/`j` indices fold them). Sensitive to every computed value and to strategy order.
- `strategy_comparison_id = sha256`, NUL-joined, in order: `comparison/1`,
  `strategy_comparison_engine_version_id`, `name`, `spec_version`, the ordered
  `walk_forward_ids` (canonical JSON array), the ordered strategy `result_hash`es (canonical
  JSON array; transitive pin, SC-1), `periods_per_year`, and `strategy_comparison_result_hash`.
- `research_result_id` aliases `strategy_comparison_id`. Derived ids are re-emitted by
  properties, never read from stored state — a tampered stored id is ignored and
  `from_dict(to_dict(r))` re-emits identical bytes. The record-format version is **not**
  folded (a container concern); inherited corpus pins are **not** folded (surfaced via
  `pin_mismatch`). Coverage is **not** folded (a pure function of the sealed cells).

---

## 6. Determinism / Decimal rules

- All arithmetic under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); the
  standard error via `Decimal.sqrt(context)`; the two-sided `p` value via the shared
  correctly-rounded `Φ` (whose internal bisection is fixed-depth, Phase 23). **No float
  anywhere**, no RNG, no wall-clock, no `id()`, no iteration-order dependence.
- Alignment is pure string/set manipulation over already-canonical sealed decimal strings —
  no arithmetic, no decimal context. Pair order is `i` then `j>i` ascending; the shared
  dates are iterated in ascending (lexicographic) order.
- Antisymmetric sign flips use `Decimal.copy_negate` (context-free, exact), never unary `-`
  (which rounds to the ambient context); a negated zero re-canonicalizes to positive zero.
- Same strategy set → same `strategy_comparison_id` and byte-identical payload on any
  machine. A repeated evaluation is a byte-identical no-op (store idempotence). Two
  independent workspaces over the same immutable sidecar agree. Because `oos_returns` is not
  folded into the *walk-forward* hash but is a deterministic function of that record's
  pinned config (whose identity *is* folded via `result_hash`), and Phase 24 folds each
  referenced `result_hash`, any upstream change changes this record's id while a
  byte-identical recompute reproduces identical bytes (the Phase 22 audit-only-series
  standard, one layer up).

---

## 7. Invariants (SC-1..SC-8)

Additive to `data-model.md §12`; these do not weaken invariants 1–30.

- **SC-1 — Reference verification and transitive pinning.** Each `walk_forward_id` is
  resolved from the shared sidecar, re-verified (`research_result_id == id`, roll-up
  `status == REALIZED`), and its `result_hash` folded (in request order) into
  `strategy_comparison_id`; the transitive reconstruction chain (optimization → risk model →
  factors) is likewise re-resolved and each id + `result_hash` verified against the pin. Any
  missing / non-decoding / id-mismatched / non-REALIZED / drifted reference fails closed.
  *(The FR-1 / PO-1 / WF-1 / CE-1 discipline, one layer up.)*
- **SC-2 — Commensurability, fail closed; pins surfaced.** All strategies share one exact
  `schedule_id`, `factor_portfolio_engine_version_id`, `periods_per_year`, **and**
  `risk_free_per_period`; a disagreement raises `ComparisonConsistencyError`. A corpus-pin
  difference is **not** raised — it is carried as the sorted distinct union and surfaced as
  `pin_mismatch`. *(The CE-3 convention, adapted to a set of walk-forwards.)*
- **SC-3 — Date-reconstruction alignment (deviation, §1.1).** OOS returns are aligned by
  reconstructed **calendar date**, never by raw position and never by axis index: each
  strategy's complete-case date axis is recomputed with the walk-forward engine's exact
  logic (WF-6), each REALIZED window's returns mapped onto it, and the reconstruction bound
  to the sealed `common_periods` and chained `oos_returns` by two fail-closed guards.
  Alignment is complete-case per pair (the intersection of the two date sets).
- **SC-4 — Fail-closed degeneracy, never repaired.** Overlap `< MIN_OVERLAP_PERIODS` → an
  all-UNDEFINED cell (`INSUFFICIENT_OVERLAP`); exact zero paired-difference variance →
  UNDEFINED `t_stat`/`p_value` (`ZERO_DIFFERENCE_VARIANCE`) with `mean_diff`/`stderr_diff`/
  `sharpe_diff` KNOWN; an undefined leg Sharpe → UNDEFINED `sharpe_diff`
  (`UNDEFINED_STRATEGY_SHARPE`) with the paired-difference statistics unaffected. No
  divide-by-zero branch; the record always seals. *(The XS-4 / P19-4 / FR-4 / PO-4 / WF-4 /
  CE-4 posture, adapted to pairs.)*
- **SC-5 — Single deterministic methodology.** One exact-`Decimal` paired-difference method;
  the shared `Φ` reused unchanged; no RNG, no data-dependent iteration; two-sided p-values
  only; one `Decimal.sqrt` per pair; no `_linalg` change and no new primitive. *(The WF-5 /
  CE-5 discipline, reusing the extracted primitive.)*
- **SC-6 — A comparison is not a PIT value and not a `BacktestResult`.** It is an ex-post
  statistic of realized OOS series; not a `Pit*` type, no as-of accessor
  (`boundary_kind="pit"` documents only the underlying PIT walks), a distinct record type,
  no fills/cash/positions/costs. *(The WF-3 / PO-2 / CE-6 discipline, one layer up; the line
  that rejects the mean-variance alternative.)*
- **SC-7 — Measurement-only.** The artifact seals per-pair statistics with no family-wise /
  FDR multiple-comparison adjustment; that correction is left to a future consumer of this
  matrix (mirroring how Phase 22 seals Sharpes and Phase 23 corrects for selection).
- **SC-8 — Antisymmetry.** Only `i<j` cells are stored; `cell(j,i)` is the exact sign-flip
  of `mean_diff`/`t_stat`/`sharpe_diff` with `p_value`/`stderr_diff`/`overlap_periods`
  preserved and labels swapped; `i==j` has no cell (the matrix has no diagonal).

---

## 8. Failure / UNDEFINED semantics

**Raised** — `ComparisonConfigurationError`: a non-`StrategyComparisonSpecification`
argument; a malformed spec (empty `name`/`spec_version`; `< 2` or `> N_MAX` strategies;
non-tuple, duplicate, or empty walk-forward id). `ComparisonConsistencyError` (SC-1/SC-2):
a `walk_forward_id` absent; a payload that is not a `WalkForwardEvaluation`; a resolved-id
disagreement; a strategy whose roll-up `status` is not `REALIZED`; strategies that are not
commensurable; a reconstruction chain that is absent, id-mismatched, hash-drifted, or that
disagrees with the sealed `common_periods` / `oos_returns`.

**Recorded as first-class UNDEFINED** (SC-4, never raised): `INSUFFICIENT_OVERLAP` (pair),
`ZERO_DIFFERENCE_VARIANCE` (`t_stat`/`p_value`), `UNDEFINED_STRATEGY_SHARPE`
(`sharpe_diff` and the per-strategy summary Sharpe). **Surfaced, never raised:**
`pin_mismatch` on a non-singular corpus-pin union.

---

## 9. Testing

`tests/comparison/` (offline, synthetic). Unlike the campaign layer — which reads only each
trial's chained OOS series and can be tested against a *synthesized* walk with a placeholder
reference — Phase 24 **reconstructs** each strategy's transitive chain, so its builders run
the **real** Phase 22 walk-forward engine over a real Phase 19/20/21 chain (reusing
`tests.walkforward.builders`) to produce genuine sealed strategies whose reconstruction
succeeds. Two strategies built from the *same* factor series (differing only by `name`) seal
distinct records with identical OOS returns (the walk reads only the return series, never
names) → exercises the zero-difference-variance path; a strategy built over a disjoint date
axis shares no OOS date → the insufficient-overlap path.

Suites: `test_spec` (fail-closed validation), `test_compute` (pure paired-difference
statistics: overlap, population variance/stderr, zero-mean → `p=1`, unit-interval `p`,
zero-variance → UNDEFINED `t`/`p`, undefined-leg-Sharpe, directional Sharpe, determinism),
`test_align` (reconstruction reproduces the sealed OOS series exactly; determinism;
missing-chain fail-closed), `test_identity` (sha256-prefixed, deterministic,
order-sensitive, each-fold-changes-the-id, result-hash cell/order sensitivity),
`test_result` (byte-identical round-trip; transpose antisymmetry incl. the exact
no-ambient-rounding regression guard and canonical positive-zero; `StatValue` fail-closed
construction), `test_engine` (happy path, 3-strategy matrix, persistence/reproducibility,
order-changes-id, transpose-matches-a-reversed-computation, insufficient-overlap recorded,
zero-difference-variance recorded, and every SC-1/SC-2 fail-closed path). Plus a
`tests/test_smoke.py` export assertion.

**Gate (all green): `ruff check` / `ruff format --check` / `mypy src tests` / `pytest -q` /
`pytest -q -p no:randomly`; zero new runtime dependencies; every sealed Phase 23 id
preserved (the `_stats/normal.py` extraction is byte-identical).**
