# Phase 25 — Multiple-Comparison Correction (LOCKED)

> **Status:** Locked normative specification. The Phase 25 proposal was **approved as
> recommended** — the recommended capability C1 (§4 / §24 of the proposal, not the deferred
> alternatives C2–C12): consume exactly one sealed `StrategyComparison`, treat its KNOWN
> pairwise `p` values as a single hypothesis family, and at a declared `alpha` seal, for each
> requested `CorrectionMethod`, every family member's method-adjusted `p` value plus a
> rejection flag — defaulting to Holm (family-wise error) and Benjamini–Yekutieli
> (false-discovery rate), both valid under arbitrary dependence, with Bonferroni and an
> explicitly independence/PRDS-labeled Benjamini–Hochberg available. This document reflects
> the **actual implementation** and is the source of truth; it supersedes the recommendations
> in
> [phase25-multiple-comparison-correction-proposal.md](phase25-multiple-comparison-correction-proposal.md).
> Every ★-marked decision in the proposal is resolved here to a committed decision.
>
> **One-line thesis:** Phase 25 adds a deterministic, content-addressed **multiplicity
> correction** layer — the platform's first consumer of a *meta-analysis* artifact (turning
> Phase 24's terminal-leaf `StrategyComparison` into a non-terminal node) and its first
> family-wise / false-discovery-rate control, the future consumer SC-7 explicitly deferred
> to. Given a declarative `MultipleComparisonSpecification` naming exactly one sealed
> `StrategyComparison` id, a declared `alpha ∈ (0, 1)`, and an ordered, duplicate-free tuple
> of `CorrectionMethod`s, `MultipleComparisonEngine.correct(...)` resolves the one comparison
> from the shared Phase 8 research sidecar, re-verifies it (present, a `StrategyComparison`,
> id matches), collects the family of its KNOWN pairwise `p` values (each UNDEFINED pairwise
> cell recorded as a first-class exclusion, never imputed), corrects that family by each
> method under one pinned `Decimal` context (a single ascending sort plus closed-form
> step-up / step-down recursions and the Benjamini–Yekutieli harmonic constant
> `c(m) = Σ_{k=1}^{m} 1/k`), and seals a `MultipleComparisonCorrection` `ResearchRecord`
> write-once to the existing sidecar. It introduces **no** new numerical primitive (it reuses
> no standard-normal `Φ` — it consumes already-sealed `p` values), **no** `_linalg` change,
> **no** RNG, **no** floating point, **no** iterative numerical solver, **no** new store, and
> **no** new PIT surface, and modifies no prior phase's vocabulary, engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **Multiplicity correction over the KNOWN pairwise `p`-value family of one comparison (C1).** The family is exactly the source `StrategyComparison`'s KNOWN pairwise `p` values, in sealed upper-triangle order. For each requested method, seal every family member's adjusted `p` value and a rejection flag at the declared `alpha`, plus the honest error-rate / dependence labels; seal the coverage (`n_pairs_total`, family size `m`, `n_excluded`). **No** cross-comparison family (one source only, §20); **no** multiple `alpha` levels (a single scalar, §20); **no** Šidák (would need an exact `Decimal` power, §20); **no** consumption of Phase 23 trials (C2), MinTRL (C3), PBO/CSCV (C4), constrained GMV (C6). It performs **no execution**, resolves **no** data at any `T`, and is **not** a `BacktestResult`. |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 24.** It resolves exactly **one** already-sealed `StrategyComparison` from the shared sidecar by id, reads its sealed pairwise cells (never re-derives them), and **modifies no** prior-phase vocabulary, engine, or identity. It is the first consumer of a meta-analysis artifact — a *second-order* meta-analysis (multiplicity control), distinct from Phase 23's absolute selection-bias and Phase 24's pairwise testing. |
| **D-METHODS** | **Default methods = Holm (FWE) + Benjamini–Yekutieli (FDR), both valid under arbitrary dependence; Bonferroni and Benjamini–Hochberg available, the latter only as an explicitly independence/PRDS-labeled variant (★3).** The pairwise `p` values are dependent (pairs share strategies), so the default set is dependence-robust. Every method seals its honest `error_rate` and `dependence` label from a single source of truth (`model.method_error_rate` / `model.method_dependence`), so Benjamini–Hochberg's independence / PRDS assumption is sealed alongside its results and can never be mistaken for a dependence-robust guarantee. This is the honest resolution of the proposal §8 dependence TENSION. |
| **D-COMPUTE** | **Closed-form exact-`Decimal` step procedures, one ascending sort (`comparison`-free, no solver).** In the ascending-sorted rank space `p_(1) ≤ … ≤ p_(m)` (ties broken by the family `(i, j)` index — a total order): **Bonferroni** `p_adj_(k) = min(1, m·p_(k))`; **Holm** raw `(m−k+1)·p_(k)` under a forward **running max**, capped at 1; **Benjamini–Hochberg** raw `(m/k)·p_(k)` under a backward **running min**, capped at 1; **Benjamini–Yekutieli** the same scaled by the harmonic constant `c(m) = Σ_{k=1}^{m} 1/k` (an exact finite `Decimal` sum, summed ascending). The running min / max make tied `p` values receive **identical** adjusted values (MC-4). Adjusted values map back to family order before sealing. |
| **D-REJECT** | **One uniform rejection rule: `p_adj ≤ alpha` for every method (MC-5).** Rejection is defined uniformly as the adjusted value being at or below `alpha` (`≤`, not `<`, so a boundary adjusted value exactly equal to `alpha` is rejected), so the sealed adjusted value and its rejection flag can never disagree — the record is internally self-consistent. |
| **D-EXCLUDE** | **UNDEFINED `p` cells are excluded, never imputed (★4, MC-3).** A pairwise cell the source sealed with an UNDEFINED `p` value (`INSUFFICIENT_OVERLAP` or `ZERO_DIFFERENCE_VARIANCE`) is removed from the family and recorded as a first-class `ExcludedCell` carrying the source's own `ComparisonUndefinedReason` — never coerced to a number, never imputed, never silently dropped. The effective family size `m` and the excluded set are both sealed. An empty family (`m = 0`) seals empty per-method cell lists — never a divide-by-zero, never a fabricated rejection. |
| **D-ALPHA** | **`alpha` is validated and canonicalized at spec construction (fail closed, ★7 / §18).** Construction parses `alpha` as a `Decimal`, requires it finite and strictly inside `(0, 1)`, and canonicalizes it via `str(Decimal.normalize())`, so `"0.05"` and `"0.050"` declare the identical request with the identical id. A non-decimal, non-finite, or out-of-range `alpha` raises `MultiplicityConfigurationError` — never silently clamped. |
| **D-EXPOST** | **The output is ex-post, never PIT (★ / MC-6).** A multiplicity correction over already-ex-post pairwise `p` values is itself ex-post. `MultipleComparisonCorrection` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` is carried unchanged from the source comparison and documents only that the *underlying strategies were PIT walks*; it never claims the correction is a PIT value. No new corpus read, no availability logic, no new PIT resolution. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order (MC-4/MC-5).** All arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); the sort key is a total order; the harmonic sum is a finite deterministic accumulation; capping uses exact `Decimal` `min`. No RNG, no iteration-to-convergence, no `_linalg`, no new numerical primitive. The engine version folds the decimal context **and** the method version into `config_hash`. |
| **D-IDENTITY** | **Content-addressed, transitively pinned, self-verifying (MC-1).** `multiple_comparison_id` folds the engine version, the request (name, spec version, `alpha`, ordered method list), the source comparison's `research_result_id` **and** its `result_hash` (the transitive pin), and the `result_hash` over the computed answer. `research_result_id` aliases `multiple_comparison_id`; derived ids are re-emitted by properties, never read from stored state. Domain tag `multiplicity/1`. |
| **D-STORE** | **One write-once record in the existing `ResearchResultStore`; no new store, no migration.** `MultipleComparisonCorrection` satisfies the `ResearchRecord` Protocol and persists to `research/sha256-<hex>.json`. An idempotent re-write of a byte-identical payload is a no-op; a conflicting payload under the same id raises `FactorConsistencyError` (the existing store contract). |
| **D-INVARIANTS** | **MC-1..MC-6 are documented both as phase-local invariants here (§7) and as a small additive `data-model.md §12` block** mirroring the SD-/XS-/P19-/FR-/PO-/WF-/CE-/SC- blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.22.0`** (Phase 24 = v0.21.0). Domain tag `multiplicity/1`; engine-version string `multiplicity-engine/1`; method string `multiplicity-method/1`; spec-version string `multiplicity/1`; record-format string `multiplicity-result/1`. The package `__version__` string is unchanged `"0.0.0"` (versioning is by content-addressed ids + the README table, not a semver string). No `pyproject`/packaging change; no new runtime dependency. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; none changes an identity discipline or weakens an invariant.

- **The MC-* block is six invariants (MC-1..MC-6), not the proposal's loose §8 list.** The
  proposal enumerated the invariant *analysis* (COMPOSES / TENSION lines) but did not fix a
  numbered MC-* block. The implementation fixes six: MC-1 (reference verification & transitive
  pinning), MC-2 (the corrected object is a sealed, explicit family with coverage), MC-3
  (UNDEFINED cells excluded, never imputed), MC-4 (ties collapse to one adjusted value;
  monotone; capped at 1), MC-5 (single deterministic methodology; one uniform `p_adj ≤ alpha`
  rejection), MC-6 (honest method labels sealed; a correction is not a PIT value). MC-6
  deliberately bundles the two "self-describing honesty" guarantees (the sealed dependence
  labels and the ex-post/non-PIT boundary), mirroring how SC-6 bundles the ex-post typing with
  the not-a-`BacktestResult` guarantee.
- **`Bonferroni` is included in the shipped `CorrectionMethod` vocabulary.** The proposal's
  ★7 left "include Bonferroni?" as a non-load-bearing default to confirm at approval.
  Implementation includes it (single-step FWE), so the closed method set is
  `{BONFERRONI, HOLM, BENJAMINI_HOCHBERG, BENJAMINI_YEKUTIELI}`. It is **not** in the default
  set (that stays Holm + Benjamini–Yekutieli), but is available when named explicitly. Šidák
  remains deferred (it would need an exact `Decimal` power — §20).

Resolved ★ decisions of note: **★1** capability = C1 (multiplicity over the Phase 24 matrix);
**★2** source is exactly one `StrategyComparison`, consumed by id; **★3** default methods Holm
+ Benjamini–Yekutieli, Benjamini–Hochberg only as an explicitly labeled independence/PRDS
variant; **★4** UNDEFINED cells excluded (not imputed), `m` + excluded set sealed; **★5** no new
numerical primitive and no `_linalg` change; **★6** v0.22.0, package `multiplicity`, domain tag
`multiplicity/1`, artifact `MultipleComparisonCorrection`; **★7** method-set membership
(Bonferroni included, Šidák deferred, single `alpha`).

---

## 2. What was built

New package **`src/quantforge/multiplicity/`** (mirrors the P20/P22/P23/P24 layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `MultiplicityError` → `MultiplicityConfigurationError`, `MultiplicityConsistencyError`. |
| `version.py` | `MultipleComparisonEngineVersion` (folds the pinned decimal context + `multiplicity-method/1` into `config_hash`; **no** normal-primitive version — none is reused); constants `MULTIPLICITY_SPEC_VERSION` / `MULTIPLICITY_ENGINE_VERSION` / `MULTIPLICITY_METHOD_VERSION`; `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `model.py` | The closed `CorrectionMethod` (`bonferroni`, `holm`, `benjamini_hochberg`, `benjamini_yekutieli`), `ErrorRate` (`family_wise`, `false_discovery`), `DependenceAssumption` (`arbitrary`, `independence_or_prds`); `method_error_rate` / `method_dependence` — the single source of truth for the honest labels. |
| `spec.py` | `MultipleComparisonSpecification` (declarative request; fail-closed validation + `alpha` canonicalization); `DEFAULT_METHODS = (HOLM, BENJAMINI_YEKUTIELI)`. |
| `compute.py` | The pure exact-`Decimal` procedures: `correct_family(p_values, methods, alpha, *, context) → tuple[MethodComputation, ...]`; the total-order sort, the four step procedures, `_harmonic`, `_running_min_capped` / `_running_max_capped`, `_min1`. |
| `result.py` | `MultipleComparisonCorrection` (`ResearchRecord`; `seal` / `to_dict` / `from_dict`, derived ids, `correction(method)` accessor), `FamilyCell`, `ExcludedCell`, `MethodCell`, `MethodResult`, `MultiplicityCoverage`; `MULTIPLICITY_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`. |
| `identity.py` | `multiple_comparison_result_hash`, `multiple_comparison_id`; domain tag `multiplicity/1`. |
| `engine.py` | `MultipleComparisonEngine.correct(spec)`. |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `workspace.py` — one lazy `multiplicity_engine` `@property` (+ private `_multiplicity_engine`
   cache slot), following the `comparison_engine` template (typed `-> object`, deferred import
   of `MultipleComparisonEngine` to avoid the module-load cycle).
2. `src/quantforge/__init__.py` — top-level re-exports of `MultipleComparisonSpecification`
   and `MultipleComparisonCorrection`, added to the sorted `__all__`.
3. `tests/test_smoke.py` — one additive export assertion
   (`test_multiplicity_public_api_is_exported`).

**No edit to** `_linalg`, `_stats`, `comparison`, `campaign`, `walkforward`, `optimization`,
`factorrisk`, `factorportfolio`, `analytics`, `backtest`, or any other prior-phase
identity/vocabulary. Phase 25 reuses **no** standard-normal primitive (it consumes
already-sealed `p` values), so `_stats/normal.py` is untouched.

---

## 3. Data flow

```
MultipleComparisonSpecification { name, source_strategy_comparison_id, alpha, methods[1..], spec_version }
        │
        ▼  MultipleComparisonEngine.correct(spec)
type-check spec is a MultipleComparisonSpecification                        — MultiplicityConfigurationError
        │
        ▼
resolve the ONE source comparison by id                                     — fail closed (MC-1)
   store.read_as(id, StrategyComparison.from_dict)
   present? decodes as a StrategyComparison? research_result_id == id?       — else MultiplicityConsistencyError
        │
        ▼
collect the family (walk the sealed upper-triangle cells in order)          — MC-2/MC-3
   p_value KNOWN     → FamilyCell + Decimal(p) into the family
   p_value UNDEFINED → ExcludedCell carrying the source's reason (never imputed)
        │
        ▼  per requested method, under localcontext(prec 34, ROUND_HALF_EVEN):
   correct_family(family_p, methods, Decimal(alpha), context)               — MC-4/MC-5
     sort ascending (ties → family index; total order)
     Bonferroni  min(1, m·p)
     Holm        (m−k+1)·p_(k)  → forward running max → cap 1
     BH          (m/k)·p_(k)     → backward running min → cap 1
     BY          (m·c(m)/k)·p_(k), c(m)=Σ 1/k → backward running min → cap 1
     map adjusted values back to family order; rejected := p_adj ≤ alpha
   → MethodResult { method, error_rate, dependence, cells[(i,j,p_adjusted,rejected)], n_rejected }
        │
        ▼
coverage = { n_pairs_total = |cells|, family_size = m, n_excluded }         — MC-2
        │
        ▼
MultipleComparisonCorrection.seal(...)  (result_hash folds the answer;
   boundary_kind carried from source; source_ref = (source id, source result_hash))  — MC-1/MC-6
        │
        ▼
ResearchResultStore.write(correction)   (write-once, idempotent)            — D-STORE
        │
        ▼
store.read_as(id, MultipleComparisonCorrection.from_dict)   (byte-identical typed round-trip)
```

---

## 4. Public API

```python
from quantforge import (
    Workspace,
    MultipleComparisonSpecification,
    MultipleComparisonCorrection,
)
from quantforge.multiplicity import CorrectionMethod

ws = Workspace.open(root)

spec = MultipleComparisonSpecification(
    name="value-vs-momentum-vs-quality:multiplicity",
    source_strategy_comparison_id=comparison_id,  # exactly one sealed StrategyComparison id
    alpha="0.05",  # decimal string, strictly in (0, 1)
    # methods defaults to (HOLM, BENJAMINI_YEKUTIELI); override to add Bonferroni / BH
)

correction = ws.multiplicity_engine.correct(spec)  # sealed, write-once

correction.family_size  # m = number of KNOWN pairwise p values corrected
correction.coverage  # n_pairs_total, family_size, n_excluded
correction.excluded  # tuple[ExcludedCell]: (i, j, labels, reason) for UNDEFINED pairs
correction.correction(
    CorrectionMethod.HOLM
)  # MethodResult: labels + per-cell (p_adjusted, rejected)
correction.alpha  # the declared, canonicalized significance level
correction.source_strategy_comparison_id  # the pinned source comparison id
correction.source_result_hash  # the transitive pin
correction.research_result_id  # == correction.multiple_comparison_id

again = ws.research_result_store.read_as(
    correction.research_result_id, MultipleComparisonCorrection.from_dict
)
```

`MultipleComparisonEngine` is reached only through `Workspace.multiplicity_engine` (lazy,
cached, `-> object`). `correct(spec) -> MultipleComparisonCorrection` is the single entry
point.

`MultipleComparisonSpecification` (frozen slots): `name`, `source_strategy_comparison_id`,
`alpha`, `methods = DEFAULT_METHODS`, `spec_version = "multiplicity/1"`. Construction-time
validation (fail closed): non-empty `name` / `spec_version` / `source_strategy_comparison_id`;
`alpha` a finite decimal strictly in `(0, 1)` (canonicalized); `methods` a non-empty tuple of
distinct `CorrectionMethod` values.

Each `MethodResult` carries `method`, `error_rate`, `dependence`, `cells`
(`tuple[MethodCell]`, in family order, each `(i, j, p_adjusted, rejected)`), and `n_rejected`.

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `multiplicity_engine_version_id = sha256(code_version "multiplicity-engine/1", config_hash)`
  where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=multiplicity-method/1")`.
  Folding the method version makes the correction's identity change if the family collection,
  sort, adjusted-`p` procedures, harmonic constant, monotonicity, capping, or rejection rule
  changes. **No** normal-primitive version is folded — none is reused.
- `multiple_comparison_result_hash = sha256(canonical JSON over the ordered computed-output
  cells: the family descriptor `{block:"family_descriptor", family_size, n_excluded}`, then
  each KNOWN family cell `{block:"family", i, j, p_value}` in source upper-triangle order, then
  each excluded cell `{block:"excluded", i, j, reason}`, then per method
  `{block:"method", method, error_rate, dependence, cells:[{i, j, p_adjusted, rejected}]}`)`.
  The derivable `label_i` / `label_j` are omitted (the `i` / `j` indices fold them). Sensitive
  to every computed adjusted value and rejection flag.
- `multiple_comparison_id = sha256`, NUL-joined, in order: `multiplicity/1`,
  `multiplicity_engine_version_id`, `name`, `spec_version`, `source_strategy_comparison_id`,
  `source_result_hash` (the transitive pin, MC-1), `alpha`, the ordered method list (canonical
  JSON array — folded in **request order**, never sorted), and `multiple_comparison_result_hash`.
- `research_result_id` aliases `multiple_comparison_id`. Derived ids are re-emitted by
  properties, never read from stored state — a tampered stored id is ignored and
  `from_dict(to_dict(r))` re-emits identical bytes. The record-format version is **not** folded
  (a container concern). Coverage is **not** folded beyond the descriptor's two counts (it is a
  pure function of the sealed family / excluded lists).

---

## 6. Determinism / Decimal rules

- All correction arithmetic runs under an explicit `localcontext` (precision 34,
  `ROUND_HALF_EVEN`): the `m·p`, `(m/k)·p`, and `(m·c(m)/k)·p` multipliers, the harmonic
  constant `c(m) = Σ_{k=1}^{m} 1/k` (summed ascending in `k`), the running min / running max
  monotonicity enforcement, the `min(1, ·)` cap, and the `p_adj ≤ alpha` rejection comparison.
  **No float anywhere**, no RNG, no wall-clock, no `id()`, no iteration-to-convergence, no
  data-dependent iteration order.
- The sort is a **total order** (`p` ascending, ties broken by the family `(i, j)` index), so
  tied `p` values receive identical adjusted values and the assignment is machine-independent.
- Adjusted values are produced as `str(value)` inside the pinned context; capping uses exact
  `Decimal` `min`, never a float clamp.
- Same source comparison + same request → same `multiple_comparison_id` and byte-identical
  payload on any machine. A repeated `correct` is a byte-identical no-op (store idempotence).
  Two engines over the same immutable sidecar agree. Because Phase 25 folds the source
  comparison's `result_hash`, any upstream change changes this record's id while a
  byte-identical recompute reproduces identical bytes (the Phase 24 audit standard, one layer
  up).

---

## 7. Invariants (MC-1..MC-6)

Additive to `data-model.md §12`; these do not weaken invariants 1–30.

- **MC-1 — Reference verification and transitive pinning.** The single
  `source_strategy_comparison_id` is resolved from the shared sidecar via
  `store.read_as(id, StrategyComparison.from_dict)`, re-verified (`research_result_id == id`,
  and that it decodes as a `StrategyComparison`), and its `result_hash` folded into
  `multiple_comparison_id`; through the source comparison's own id this pins every walk-forward
  and its transitive chain beneath it (SC-1). Any missing, non-decoding, or id-mismatched
  reference fails closed with `MultiplicityConsistencyError`; the source is never copied, only
  pinned. *(The SC-1 / CE-1 discipline, one layer up.)*
- **MC-2 — The corrected object is a sealed, explicit family.** The family is exactly the KNOWN
  pairwise `p` values of the one source comparison, in sealed upper-triangle order; the coverage
  (`n_pairs_total`, family size `m = family_size`, `n_excluded`, with
  `m + n_excluded = n_pairs_total`) is sealed so the effective family size the adjustment used
  is auditable and never inferred. One source only (no cross-comparison family in v0.22.0).
- **MC-3 — UNDEFINED `p` cells are excluded, never imputed.** A pairwise cell the source sealed
  with an UNDEFINED `p` value (`INSUFFICIENT_OVERLAP` or `ZERO_DIFFERENCE_VARIANCE`) is removed
  from the family and recorded as a first-class `ExcludedCell` carrying the source's own
  `ComparisonUndefinedReason` — never coerced to a number, never imputed, never silently
  dropped. An empty family (`m = 0`) seals empty per-method cell lists, never a divide-by-zero.
  *(The SC-4 / inv-15 fail-closed posture, adapted to a family.)*
- **MC-4 — Ties collapse to one adjusted value; monotone; capped at 1.** The family is sorted
  under a total order (`p` ascending, ties → family `(i, j)` index), and each method's
  monotonicity is enforced by an exact-`Decimal` running min (BH / BY, backward) or running max
  (Holm, forward), so equal input `p` values receive **identical** adjusted values and no
  adjusted value exceeds `1` (exact `Decimal` `min`, never a float clamp).
- **MC-5 — Single deterministic methodology; one uniform rejection rule.** One exact-`Decimal`
  correction per family — a single ascending sort plus the closed-form Bonferroni / Holm /
  Benjamini–Hochberg / Benjamini–Yekutieli step recursions (the BY harmonic constant an exact
  finite `Decimal` sum) — all under one pinned decimal context folded into the engine identity.
  Rejection is defined **uniformly** as `p_adj ≤ alpha` for every method, so the sealed adjusted
  value and its rejection flag can never disagree. No RNG, no float, no iteration-to-convergence,
  no `_linalg` change, no new primitive. *(The SC-5 / WF-5 discipline, over sealed `p` strings.)*
- **MC-6 — Honest method labels sealed; and a correction is not a PIT value.** Each method seals
  its honest `error_rate` (family-wise for Bonferroni / Holm, false-discovery for BH / BY) and
  `dependence` label; Bonferroni, Holm, and Benjamini–Yekutieli are valid under **arbitrary**
  dependence, and Benjamini–Hochberg's **independence / PRDS** assumption is sealed alongside
  its results so it can never be mistaken for a dependence-robust guarantee. A multiplicity
  correction over already-ex-post pairwise `p` values is itself ex-post:
  `MultipleComparisonCorrection` is **not** a `Pit*` type, exposes no as-of accessor, is a
  distinct record type, and opens no new corpus / availability surface. `boundary_kind = "pit"`
  — carried unchanged from the source comparison — documents only that the *underlying
  strategies* were PIT walks. *(The SC-6 / CE-6 discipline, one layer up.)*

---

## 8. Failure / UNDEFINED semantics

**Raised** — `MultiplicityConfigurationError`: a non-`MultipleComparisonSpecification`
argument to the engine; a malformed spec (empty `name` / `spec_version` /
`source_strategy_comparison_id`; an `alpha` that is not a finite decimal strictly inside
`(0, 1)`; an empty method tuple; a duplicated or non-`CorrectionMethod` method).
`MultiplicityConsistencyError` (MC-1): the `source_strategy_comparison_id` absent from the
sidecar; a payload that does not decode as a `StrategyComparison`; a resolved-id disagreement.

**Recorded as first-class UNDEFINED** (MC-3, never raised): each pairwise cell the source
sealed with an UNDEFINED `p` value — `INSUFFICIENT_OVERLAP` or `ZERO_DIFFERENCE_VARIANCE` — is
excluded from the family and recorded as an `ExcludedCell` with that reason. An empty family
(`m = 0`) seals with empty per-method cell lists and `n_rejected = 0`.

**Store contract:** a byte-identical re-write is an idempotent no-op; a differing payload under
the same correction id raises `FactorConsistencyError` (the existing write-once guard).

---

## 9. Testing

`tests/multiplicity/` (offline, synthetic). Because the engine reads **only** the source
`StrategyComparison` via `store.read_as`, the builders (`tests/multiplicity/builders.py`)
construct synthetic `StrategyComparison` records directly — sealing hand-chosen per-pair
`p` values (KNOWN decimal strings or UNDEFINED reasons) via `StrategyComparison.seal` and
writing them to the store — rather than running the full factor → walk-forward → comparison
chain. (The builder inverts the `ComparisonUndefinedReason`-is-a-`str` check: a KNOWN `p`
value is `not isinstance(entry, ComparisonUndefinedReason)`, so an exclusion-reason enum is
never mistaken for a `p`-value string.)

Suites (**53 tests** across the package, plus the smoke assertion):
- `test_spec` (10) — fail-closed validation, `alpha` canonicalization, default methods,
  method-order preservation, duplicate/empty rejection, round-trip re-validation stability.
- `test_model` (3) — the error-rate labels, that only Benjamini–Hochberg assumes independence,
  and that every method has both labels.
- `test_compute` (11) — the pure procedures: the `m = 2` exact hand-calculation for all four
  methods (`p = (0.01, 0.04)`, `alpha = 0.05`: Bonferroni `[0.02, 0.08]` (T, F), Holm
  `[0.02, 0.04]` (T, T), BH `[0.02, 0.04]` (T, T), BY `[0.03, 0.06]` (T, F), where
  `c(2) = 3/2`), the cap-at-1, ties → identical adjusted values, duplicate `p` across a larger
  family, adjusted-values map back to family order, monotonicity along ascending rank,
  BY ≥ BH cell-for-cell, the `p_adj ≤ alpha` boundary (Bonferroni of `0.025` over `m = 2` is
  exactly `0.05`), the empty-family guard, the single-hypothesis-unchanged case, and repeated
  calls byte-identical.
- `test_identity` (5) — `sha256:`-prefixed, deterministic, method-order-folded,
  each-fold-changes-the-id, result-hash sensitive to a single cell.
- `test_result` (8) — seal folds the answer, derived id aliases `research_result_id`,
  byte-identical round-trip, id re-derived not read from state (tampered stored id ignored),
  the accessors, `correction()` raises for an absent method, not-a-`Pit*`-and-no-as-of, and
  `from_dict` rejects an unknown reason.
- `test_engine` (16) — happy path (full family corrected, default Holm + BY in request order,
  strongest signal rejected), source reference pinned, honest dependence labels sealed;
  UNDEFINED cells excluded / never imputed and an all-UNDEFINED empty family; boundary carried
  and the record not PIT; recompute byte-identical and idempotent, write-once no conflict for
  the same id; identity sensitivity to the source answer, `alpha`, and method order; and every
  MC-1 fail-closed guard (absent source, non-`StrategyComparison` record, id-mismatch via a
  path-swapped payload, non-spec argument, and a tampered stored payload → `FactorConsistencyError`).

**Gate (all green): `ruff check .` / `ruff format --check .` / `mypy src tests` / `pytest -q` /
`pytest -q -p no:randomly`; 1844 tests pass; zero new runtime dependencies; every prior-phase
id preserved (no prior source touched beyond the additive `workspace.py` / `__init__.py`
re-exports and the smoke assertion).**
