# Phase 33 — Strategy Admissibility (LOCKED)

> **Status:** Locked normative specification. The Phase 33 proposal was **implemented as
> recommended** — the single capability of
> [phase33-strategy-admissibility-proposal.md](phase33-strategy-admissibility-proposal.md):
> resolve exactly three sealed ex-post verdicts of one strategy — one
> `WalkForwardStability` (Phase 27), one `CalibrationSignificance` (Phase 29), and one
> `NetOfCostSignificance` (Phase 32) — read each layer's already-computed answer verbatim,
> and seal a single joint admissibility verdict: `ADMISSIBLE` only when the book was STABLE,
> the two-sided calibration p-value `> alpha` (not significantly mis-calibrated), and the
> one-sided net-of-cost p-value `<= alpha` with a PROFITABLE edge (significantly profitable
> after costs); `INADMISSIBLE` when every criterion was decidable and at least one failed;
> `UNDEFINED` (fail closed) when any criterion could not be decided. This document reflects
> the **actual implementation** and is the source of truth; it supersedes the proposal.
> Every ★-marked decision in the proposal is resolved here.
>
> **One-line thesis:** Phase 33 adds a deterministic, content-addressed **strategy
> admissibility** layer — the **first multi-source consumer** in the research spine and the
> capstone over the ex-post validator battery — answering the one question no single
> validator states: *taken together, is this strategy admissible?* Given a declarative
> `AdmissibilitySpecification` naming exactly one sealed `WalkForwardStability` id, one
> `CalibrationSignificance` id, and one `NetOfCostSignificance` id plus a declared level
> `alpha`, `AdmissibilityEngine.evaluate(...)` resolves all three records from the shared
> Phase 8 research sidecar, re-verifies each (present, correctly typed, id matches), reduces
> each to the primitive fact it contributes (its sealed status / p-value / edge direction,
> read verbatim — AD-4), decides the three admissibility criteria and their fail-closed
> roll-up under one pinned `Decimal` context, and seals a `StrategyAdmissibility`
> `ResearchRecord` write-once to the existing sidecar. It introduces **no** new numerical
> primitive (it evaluates only exact-`Decimal` comparisons of the consumed p-values against
> `alpha` — the `Φ` CDF was already applied and sealed by the significance layers), **no**
> `_linalg`/`_stats` change, **no** RNG, **no** floating point, **no** iterative solver,
> **no** new store, and **no** new PIT surface, and modifies no prior phase's vocabulary,
> engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **A single joint admissibility verdict over three sealed ex-post verdicts of one strategy.** The analyzed object is exactly the trio: one `WalkForwardStability` (its `stability_status`), one `CalibrationSignificance` (its `significance_status` + two-sided `summary.p_value`), and one `NetOfCostSignificance` (its `significance_status` + one-sided `summary.p_value` + `summary.edge_direction`). It seals the roll-up `verdict`, the canonical `alpha`, and the three ordered `Criterion` cells (STABILITY, CALIBRATION, NET_OF_COST_EDGE). **No** new computed magnitude, **no** composite score, **no** cross-strategy ranking, **no** per-period detail. It performs **no execution**, resolves **no** data at any `T`, and is **not** a `BacktestResult`. |
| **D-INPUT** | **The first multi-source pure-consumer layer, strictly *above* Phases 27/29/32.** It resolves exactly **three** already-sealed records from the shared sidecar by id, reads their sealed statuses / p-values / edge direction (never re-derives them, never reads anything beneath any of the three), and **modifies no** prior-phase vocabulary, engine, or identity. All three sources descend from one `WalkForwardEvaluation`(22) root. It is the first layer that resolves more than one sealed terminal artifact. |
| **D-COMPUTE** | **A pure exact-`Decimal` conjunction of three criteria; no transcendental.** Under the pinned context, against a declared `alpha ∈ (0, 1)`: STABILITY PASSes iff STABLE (else UNDEFINED — never FAILs); CALIBRATION PASSes iff the two-sided p `> alpha`, FAILs iff `<= alpha`, UNDEFINED iff the source is not TESTED or its p not KNOWN; NET_OF_COST_EDGE PASSes iff the one-sided p `<= alpha` **and** the edge is PROFITABLE, FAILs if decidable-but-not, UNDEFINED iff the source is not TESTED or its p not KNOWN. The three comparisons are the only arithmetic; **no** `Φ`, **no** `Decimal.sqrt`, **no** new statistical method (the `Φ` CDF was applied and sealed by Phases 29 / 32). |
| **D-ROLLUP** | **Fail-closed roll-up; UNDEFINED dominates a FAIL.** `UNDEFINED` iff **any** criterion is UNDEFINED; `ADMISSIBLE` iff **all three** PASS; else `INADMISSIBLE` (every criterion decidable, at least one FAIL). A strategy whose stability, calibration, or after-cost edge could not even be assessed is never silently called inadmissible — the verdict is undefined. |
| **D-STABILITY** | **The stability criterion never FAILs.** The stability layer's `stability_status` is binary (STABLE vs UNDEFINED — it asserts "not assessable", never "unstable"), so the criterion is PASS iff STABLE, else UNDEFINED (`STABILITY_UNDEFINED`). Treating UNDEFINED stability as a FAIL was rejected: a non-assessable book is not the same as an unstable one. *(Recorded in the proposal §6.5 / §11, not a deviation.)* |
| **D-CALIBRATION** | **The calibration criterion reads the two-sided p-value against `alpha`.** PASS iff `p > alpha` (fail to reject calibration — the risk model is not significantly mis-calibrated); FAIL iff `p <= alpha` (significantly mis-calibrated). The direction mirrors Phase 29's non-directional two-sided variance-ratio-vs-`1` test. UNDEFINED (`CALIBRATION_UNDEFINED`) iff the source was not TESTED or its `p_value` cell is not KNOWN. |
| **D-NETEDGE** | **The net-of-cost-edge criterion reads the one-sided p-value AND the edge direction.** PASS iff `p <= alpha` **and** `edge_direction is PROFITABLE` (significantly positive after costs); FAIL if decidable but either condition fails (insignificant, or significant-but-unprofitable/flat). The direction mirrors Phase 32's one-sided upper-tailed mean-return-vs-`0` test. UNDEFINED (`NET_OF_COST_UNDEFINED`) iff the source was not TESTED or its `p_value` cell is not KNOWN. |
| **D-CONSUME** | **Sealed answers are consumed verbatim; no statistic is recomputed.** The engine reads the source `stability_status`, the two `summary.p_value` strings (parsed once into `Decimal`), the two `significance_status` values, and the `edge_direction` — and never recomputes a p-value, never re-derives a moment, never evaluates a CDF, and never reads anything beneath the three source records. The sealed answers are authoritative (the NC-4 / CS-4 / NS-4 posture, one layer up). |
| **D-EXPOST** | **The output is ex-post, never PIT.** A decision over three already-ex-post verdicts is itself ex-post. `StrategyAdmissibility` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` documents only that the *underlying factor portfolios* (beneath each consumed verdict's walk-forward) were PIT walks; it never claims the admissibility output is a PIT value. No new corpus read, no availability logic, no new PIT resolution. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order.** All comparisons run under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); the three exact-`Decimal` comparisons of two consumed p-values against `alpha` are the only operations — **no transcendental at all** (no `Φ`, no `Decimal.sqrt`); the observed-p `detail` strings are canonicalized `str(+value)`. No RNG, no data-dependent iteration order, no `_linalg`/`_stats` change, no new numerical primitive. The engine version folds the decimal context and the method version into `config_hash`; there is **no** normal-primitive fold (Phase 33 evaluates no standard-normal primitive). |
| **D-IDENTITY** | **Content-addressed, transitively pinned across three sources, self-verifying.** `admissibility_id` folds the engine version, the request (name, spec version), each of the three source ids **and** each source's `result_hash` (the three transitive pins, AD-1), the declared `alpha` (AD-5), and the `result_hash` over the computed answer. `research_result_id` aliases `admissibility_id`; derived ids are re-emitted by properties, never read from stored state. Domain tag `admissibility/1`. |
| **D-STORE** | **One write-once record in the existing `ResearchResultStore`; no new store, no migration.** `StrategyAdmissibility` satisfies the `ResearchRecord` Protocol and persists to `research/sha256-<hex>.json`, storing only *pointers* to the three sources (never a copy of their contents). An idempotent re-write of a byte-identical payload is a no-op; a conflicting payload under the same id raises `FactorConsistencyError` (the existing store contract). |
| **D-PARAMS** | **One per-request numerical parameter: `alpha`.** The single approved methodology has exactly one tunable input — the declared significance level `alpha` (default `DEFAULT_ALPHA = "0.05"`), a decimal string strictly inside `(0, 1)`, canonicalized at construction (`str(Decimal(alpha).normalize())`) and folded into `admissibility_id` so a change to it is a distinguishable record. The joint-decision rule itself has no other tunable input; a declarable criteria set / weights is a disclosed future extension (§10). |
| **D-INVARIANTS** | **AD-1..AD-6 are documented both as phase-local invariants here (§7) and as a small additive `data-model.md §12` block** mirroring the WF-/CE-/SC-/MC-/RC-/WS-/MT-/CS-/NC-/NS- blocks (they do not weaken existing invariants). |
| **D-VERSION** | This phase releases as **`v0.30.0`** (Phase 32 = v0.29.0). Domain tag `admissibility/1`; engine-version string `admissibility-engine/1`; method string `admissibility-method/1`; spec-version string `admissibility/1`; record-format string `admissibility-result/1`. There is **no** normal-primitive string (no `Φ` is evaluated). The package `__version__` string is unchanged `"0.0.0"` (versioning is by content-addressed ids + the README table, not a semver string). No `pyproject`/packaging change; no new runtime dependency. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; neither changes an identity discipline or weakens an invariant.

- **The record carries a `method_version` field.** As in Phases 27–32, the implementation
  stores `method_version` (default `ADMISSIBILITY_METHOD_VERSION`) as a first-class record
  field, round-tripped through `to_dict` / `from_dict`. It is **not** folded into
  `admissibility_id` separately — the method version already reaches the id through
  `admissibility_engine_version_id` (whose `config_hash` folds it), so folding it twice would
  be redundant; the stored field is an auditable record of the method that produced the
  answer. `from_dict` requires it (fail closed on absence), so a record's stored bytes
  disclose their producing method without changing identity discipline.
- **The summary type is named `AdmissibilitySummary` (not a `*Summary` in a significance
  namespace).** The proposal (§6.6) named it `AdmissibilitySummary`; the implementation keeps
  that name. No public top-level export changes: only `AdmissibilitySpecification` and
  `StrategyAdmissibility` are re-exported from `quantforge`.
- **No `Φ` and no `Decimal.sqrt`.** Unlike every prior significance layer, Phase 33 evaluates
  **no** transcendental. The proposal (§6.5, §9) already committed to this — the consumed
  p-values were produced by the `Φ` CDF sealed upstream, and Phase 33 only compares them
  against `alpha` in exact `Decimal`. There is consequently no normal-primitive version to
  fold (a deliberate absence relative to the Phase 29 / 32 `*_NORMAL_VERSION` fold).

Resolved ★ decisions of note: capability = a single joint admissibility verdict over three
sealed ex-post verdicts of one strategy; sources = one `WalkForwardStability` + one
`CalibrationSignificance` + one `NetOfCostSignificance`, each consumed by id; output
`StrategyAdmissibility`; package `admissibility`, domain tag `admissibility/1`; public names
`AdmissibilitySpecification` / `StrategyAdmissibility`; three criteria in fixed order with the
fail-closed UNDEFINED-dominant roll-up; stability never FAILs; exact-`Decimal` comparisons only,
no new primitive, no `Φ`; ex-post, not a `Pit*`, `boundary_kind = "pit"` documenting the input
side; `alpha` the single parameter, canonicalized + folded, `DEFAULT_ALPHA = "0.05"`; identity
fold as in §5; v0.30.0; no `_linalg`/`_stats` change; a sibling package, no prior-phase edit;
shared write-once `ResearchResultStore`.

---

## 2. What was built

New package **`src/quantforge/admissibility/`** (mirrors the P22–P32 layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `AdmissibilityError` → `AdmissibilityConfigurationError`, `AdmissibilityConsistencyError`. |
| `version.py` | `AdmissibilityEngineVersion` (folds the pinned decimal context + `admissibility-method/1` into `config_hash`; **no** normal fold); constants `ADMISSIBILITY_SPEC_VERSION` / `ADMISSIBILITY_ENGINE_VERSION` / `ADMISSIBILITY_METHOD_VERSION`; `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `model.py` | The closed `AdmissibilityVerdict` (`admissible`, `inadmissible`, `undefined`), `CriterionKind` (`stability`, `calibration`, `net_of_cost_edge`), `CriterionStatus` (`pass`, `fail`, `undefined`), `AdmissibilityUndefinedReason` (`stability_undefined`, `calibration_undefined`, `net_of_cost_undefined`), and the `Criterion` cell (kind + status + optional `detail` + `reason`, with `passed()` / `failed()` / `undefined()` constructors and `to_dict` / `from_dict`; construction enforces "UNDEFINED ⇔ reason present"). |
| `spec.py` | `AdmissibilitySpecification` (declarative request; fail-closed validation of `name` / three source ids / `spec_version`; `alpha` validated `(0, 1)` and canonicalized `str(Decimal(alpha).normalize())`; `spec_version = "admissibility/1"`); `DEFAULT_ALPHA = "0.05"`. |
| `compute.py` | The pure exact-`Decimal` rule: `decide_admissibility(inputs, *, alpha, context) → AdmissibilityComputation`; `AdmissibilityInputs` (the primitive facts extracted verbatim); the `_stability_criterion` / `_calibration_criterion` / `_net_edge_criterion` / `_roll_up` helpers. |
| `result.py` | `StrategyAdmissibility` (`ResearchRecord`; `seal` / `to_dict` / `from_dict`, derived ids, `verdict` / three source-ref accessors), `AdmissibilitySummary`; `ADMISSIBILITY_RESULT_FORMAT_VERSION = "admissibility-result/1"`, `BOUNDARY_PIT = "pit"`. |
| `identity.py` | `admissibility_result_hash`, `admissibility_id`; domain tag `admissibility/1`. |
| `engine.py` | `AdmissibilityEngine.evaluate(spec)` (the three-source resolver + `_resolve_stability` / `_resolve_calibration` / `_resolve_net_of_cost` + `_inputs` reducer). |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `workspace.py` — one lazy `admissibility_engine` `@property` (+ private `_admissibility_engine`
   cache slot), following the `net_of_cost_significance_engine` template (typed `-> object`,
   deferred import of `AdmissibilityEngine` to avoid the module-load cycle).
2. `src/quantforge/__init__.py` — top-level re-exports of `AdmissibilitySpecification` and
   `StrategyAdmissibility`, added to the sorted `__all__`.

**No edit to** `_linalg`, `_stats`, `netcostsig`, `netcost`, `stability`, `calsig`, `campaign`,
`walkforward`, `comparison`, `multiplicity`, `mintrl`, `campaignmult`, `optimization`, `factorrisk`,
`factorportfolio`, `analytics`, `backtest`, or any other prior-phase identity/vocabulary. Phase 33
evaluates **no** numerical primitive and adds none, so `_stats/normal.py` and `_linalg/` are
untouched.

---

## 3. Data flow

```
AdmissibilitySpecification { name, source_stability_id, source_calibration_significance_id,
                             source_net_of_cost_significance_id, alpha, spec_version }
        │
        ▼  AdmissibilityEngine.evaluate(spec)
type-check spec is an AdmissibilitySpecification                              — AdmissibilityConfigurationError
        │
        ▼
resolve the THREE source records by id                                        — fail closed (AD-1)
   store.read_as(id, WalkForwardStability.from_dict)
   store.read_as(id, CalibrationSignificance.from_dict)
   store.read_as(id, NetOfCostSignificance.from_dict)
   for each: present? decodes as the expected type? research_result_id == id?    — else AdmissibilityConsistencyError
        │
        ▼
reduce each verdict to its primitive fact                                     — AD-4 (verbatim)
   _inputs(stability, calibration, net_of_cost) → AdmissibilityInputs
      stability_stable = (stability_status is STABLE)
      calibration_defined / calibration_p (two-sided, TESTED + KNOWN)
      net_defined / net_p (one-sided) / net_profitable (edge is PROFITABLE)
        │
        ▼  under localcontext(prec 34, ROUND_HALF_EVEN):
   decide_admissibility(inputs, alpha=Decimal(spec.alpha), context)           — AD-2/AD-3
      STABILITY:        PASS iff STABLE           else UNDEFINED (never FAIL)
      CALIBRATION:      PASS iff p > alpha; FAIL iff p <= alpha; else UNDEFINED
      NET_OF_COST_EDGE: PASS iff p <= alpha AND PROFITABLE; FAIL if decidable-not; else UNDEFINED
      roll-up:          UNDEFINED if any UNDEFINED; ADMISSIBLE if all PASS; else INADMISSIBLE
        │
        ▼
AdmissibilitySummary { verdict, alpha, criteria = (STABILITY, CALIBRATION, NET_OF_COST_EDGE) }
        │
        ▼
StrategyAdmissibility.seal(...)  (result_hash folds the answer; boundary_kind = "pit";
   stability_ref / calibration_ref / net_of_cost_ref = (source id, source result_hash))  — AD-1/AD-6
        │
        ▼
ResearchResultStore.write(admissibility)   (write-once, idempotent)           — D-STORE
        │
        ▼
store.read_as(id, StrategyAdmissibility.from_dict)   (byte-identical typed round-trip)
```

---

## 4. Public API

```python
from quantforge import (
    Workspace,
    AdmissibilitySpecification,
    StrategyAdmissibility,
)

ws = Workspace.open(root)

spec = AdmissibilitySpecification(
    name="strategy:admissibility",
    source_stability_id=stability_id,  # one sealed WalkForwardStability id
    source_calibration_significance_id=calibration_id,  # one sealed CalibrationSignificance id
    source_net_of_cost_significance_id=net_of_cost_id,  # one sealed NetOfCostSignificance id
    alpha="0.05",  # optional; default DEFAULT_ALPHA
)

admissibility = ws.admissibility_engine.evaluate(spec)  # sealed, write-once

admissibility.verdict  # ADMISSIBLE / INADMISSIBLE / UNDEFINED
admissibility.summary  # AdmissibilitySummary: verdict + alpha + 3 criteria
admissibility.summary.failed_criteria  # the kinds that FAILed (empty unless INADMISSIBLE)
admissibility.summary.undefined_criteria  # the kinds that are UNDEFINED
admissibility.source_stability_id  # the pinned stability source id
admissibility.source_calibration_significance_id  # the pinned calibration source id
admissibility.source_net_of_cost_significance_id  # the pinned net-of-cost source id
admissibility.source_stability_result_hash  # a transitive pin (one of three)
admissibility.research_result_id  # == admissibility.admissibility_id

again = ws.research_result_store.read_as(
    admissibility.research_result_id, StrategyAdmissibility.from_dict
)
```

`AdmissibilityEngine` is reached only through `Workspace.admissibility_engine` (lazy, cached,
`-> object`). `evaluate(spec) -> StrategyAdmissibility` is the single entry point.

`AdmissibilitySpecification` (frozen slots): `name`, `source_stability_id`,
`source_calibration_significance_id`, `source_net_of_cost_significance_id`,
`alpha = "0.05"`, `spec_version = "admissibility/1"`. Construction-time validation (fail closed):
non-empty `name` / `spec_version` / three source ids; `alpha` a decimal string strictly inside
`(0, 1)`, canonicalized once.

`AdmissibilitySummary` carries the roll-up `verdict`, the canonical `alpha`, and the three ordered
`Criterion` cells (each a `kind` + `status` + an optional audit `detail` (the observed p-value or
status label) + a `reason` populated iff UNDEFINED).

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `admissibility_engine_version_id = sha256(code_version "admissibility-engine/1", config_hash)`
  where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=admissibility-method/1")`.
  Folding the method version makes the record's identity change if the criterion pass-tests or the
  roll-up change. There is **no** normal-primitive fold (no `Φ` is evaluated).
- `admissibility_result_hash = sha256(canonical JSON over the ordered computed-output cells: a
  single `{block:"summary", verdict, alpha, criteria}` descriptor)`. Sensitive to the verdict and
  every per-criterion status.
- `admissibility_id = sha256`, NUL-joined, in order: `admissibility/1`,
  `admissibility_engine_version_id`, `name`, `spec_version`, `source_stability_id`,
  `source_stability_result_hash`, `source_calibration_significance_id`,
  `source_calibration_result_hash`, `source_net_of_cost_significance_id`,
  `source_net_of_cost_result_hash`, `alpha`, and `admissibility_result_hash`. The three
  `source_result_hash` values are the transitive pins (AD-1); `alpha` is folded (AD-5).
- `research_result_id` aliases `admissibility_id`. Derived ids are re-emitted by properties, never
  read from stored state — a tampered stored id is ignored and `from_dict(to_dict(r))` re-emits
  identical bytes. The record-format version and the stored `method_version` are **not** folded (a
  container / audit concern; the method reaches the id through the engine version).

---

## 6. Determinism / Decimal rules

- All decision arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`):
  the three exact-`Decimal` comparisons of the two consumed p-values against `alpha`. **No
  transcendental at all** — no `Φ`, no `Decimal.sqrt`; the `Φ` CDF was applied and sealed upstream
  by Phases 29 / 32, and Phase 33 only compares the sealed p-values. **No float anywhere**, no RNG,
  no wall-clock, no `id()`, no data-dependent iteration order.
- The observed-p `detail` strings are canonicalized as `str(+value)` inside the pinned context;
  `alpha` is canonicalized `str(Decimal(alpha).normalize())` at spec construction.
- Same three source records + same request → same `admissibility_id` and byte-identical payload on
  any machine. A repeated `evaluate` is a byte-identical no-op (store idempotence). Two engines over
  the same immutable sidecar agree. Because Phase 33 folds all three sources' `result_hash`, any
  upstream change (in any of the three verdicts or anything beneath) changes this record's id while
  a byte-identical recompute reproduces identical bytes (the Phase 22/23/29/31/32 audit standard,
  extended to a three-source fan-in).

---

## 7. Invariants (AD-1..AD-6)

Additive to `data-model.md §12`; these do not weaken existing invariants.

- **AD-1 — Multi-source reference verification and transitive pinning.** Each of the three source
  ids is resolved from the shared sidecar via `store.read_as(id, <T>.from_dict)`, re-verified
  (`research_result_id == id`, and that it decodes as its expected type — a `WalkForwardStability`, a
  `CalibrationSignificance`, or a `NetOfCostSignificance`), and its `result_hash` folded into
  `admissibility_id`; through each source's own id this pins the walk-forward / optimization /
  risk-model / factor chain beneath it. Any missing, non-decoding, or id-mismatched reference (at any
  of the three) fails closed with `AdmissibilityConsistencyError`; no source is copied, only pinned.
  *(The NC-1 / CS-1 / NS-1 discipline, extended from one source to three.)*
- **AD-2 — Fail-closed roll-up; the record always seals.** `UNDEFINED` iff **any** criterion is
  UNDEFINED (UNDEFINED dominates a FAIL — a strategy whose stability, calibration, or after-cost edge
  could not even be assessed is never silently called inadmissible); `ADMISSIBLE` iff all three PASS;
  else `INADMISSIBLE`. A consumed verdict that is itself UNDEFINED is a data condition, never an
  exception: it seals an UNDEFINED criterion with a first-class reason and a fail-closed UNDEFINED
  roll-up. The record always seals.
- **AD-3 — Per-criterion pass definitions.** STABILITY: PASS iff the source book was STABLE, else
  UNDEFINED (`STABILITY_UNDEFINED`) — it **never FAILs** (the stability status is binary). CALIBRATION:
  PASS iff the two-sided p-value `> alpha`, FAIL iff `<= alpha`, UNDEFINED (`CALIBRATION_UNDEFINED`)
  iff the source was not TESTED or its p-value is not KNOWN. NET_OF_COST_EDGE: PASS iff the one-sided
  p-value `<= alpha` **and** the edge is PROFITABLE, FAIL if decidable but not both, UNDEFINED
  (`NET_OF_COST_UNDEFINED`) iff the source was not TESTED or its p-value is not KNOWN.
- **AD-4 — Sealed answers are consumed verbatim, never recomputed.** The source `stability_status`,
  the two `summary.p_value` strings (parsed once into `Decimal`), the two `significance_status`
  values, and the `edge_direction` are read directly; the engine recomputes no statistic, re-derives
  no moment, evaluates no CDF, and reads nothing beneath the three source records. The sealed answers
  are authoritative. *(The NC-4 / CS-4 / NS-4 posture, over three sources.)*
- **AD-5 — The declared level is canonicalized and folded.** `alpha` is validated `(0, 1)` and
  canonicalized once at spec construction (`str(Decimal(alpha).normalize())`, so `"0.05"` and
  `"0.050"` are the same request), and folded into `admissibility_id`, so a change to the declared
  level is a distinguishable record. `DEFAULT_ALPHA = "0.05"`.
- **AD-6 — A strategy admissibility is not a PIT value and not a `BacktestResult`.** A decision over
  three already-ex-post verdicts is itself ex-post: `StrategyAdmissibility` is **not** a `Pit*` type,
  exposes no as-of accessor, is a distinct record type, simulates no fills, and opens no new corpus /
  availability surface. `boundary_kind = "pit"` documents only that the *underlying factor
  portfolios* (beneath each consumed verdict's walk-forward) were PIT walks — the label describes the
  input side, never the ex-post output. *(The NC-6 / CS-6 / NS-6 discipline, one layer up.)*

---

## 8. Failure / UNDEFINED semantics

**Raised** — `AdmissibilityConfigurationError`: a non-`AdmissibilitySpecification` argument to the
engine; a malformed spec (empty `name` / `spec_version` / any source id; an `alpha` that is not a
decimal string strictly inside `(0, 1)`). `AdmissibilityConsistencyError` (AD-1): any of the three
source ids absent from the sidecar; a payload that does not decode as its expected type; a resolved-id
disagreement.

**Recorded as first-class UNDEFINED** (AD-2/AD-3, never raised): a source verdict that is itself
UNDEFINED (an UNDEFINED `stability_status`; a calibration or net-of-cost source not TESTED, or whose
`p_value` cell is not KNOWN) seals the corresponding criterion UNDEFINED with a first-class reason,
and the roll-up fails closed to UNDEFINED (UNDEFINED dominates any FAIL). The record always seals.

**Store contract:** a byte-identical re-write is an idempotent no-op; a differing payload under the
same admissibility id raises `FactorConsistencyError` (the existing write-once guard).

---

## 9. Testing

`tests/admissibility/` (offline, synthetic). Because the engine reads **only** the three source
records via `store.read_as`, the builders (`tests/admissibility/builders.py`) construct synthetic
`WalkForwardStability` / `CalibrationSignificance` / `NetOfCostSignificance` records directly —
sealing hand-chosen summaries (a STABLE / UNDEFINED book; a TESTED calibration with a KNOWN two-sided
p-value above or below `alpha`; a TESTED net-of-cost with a KNOWN one-sided p-value and a
PROFITABLE / UNPROFITABLE edge; non-TESTED / non-KNOWN variants of each) via each source type's
`seal` and writing them to the store — rather than running the full factor → optimization →
walk-forward → stability / calibration / net-of-cost chains. Every id / hash each synthetic record
pins is an obviously-fictional placeholder (Principle 8): Phase 33 pins each source by
`(id, result_hash)` and never resolves anything beneath it.

Suites (across the package):
- `test_spec` — the default spec version and `DEFAULT_ALPHA`, the canonical `to_dict`, fail-closed
  rejection of empty fields and out-of-range `alpha`, `alpha` canonicalization (`"0.050"` → `"0.05"`),
  frozenness.
- `test_model` — the `Criterion` construction guards ("UNDEFINED ⇔ reason present"), `to_dict` /
  `from_dict` round-trip, fail-closed decode of corrupt cells (unknown kind / status / reason), and
  the closed verdict / kind / status / reason vocabularies.
- `test_version` — the engine-version fold of decimal context + method version (and the deliberate
  absence of a normal fold), `sha256:`-prefixed determinism, per-input id sensitivity.
- `test_compute` — the pure rule over synthetic `AdmissibilityInputs`: the ADMISSIBLE path (all
  PASS); each FAIL path (miscalibration; insignificant or unprofitable edge); each UNDEFINED path
  (each of the three sources undefined); UNDEFINED dominates a FAIL; the `alpha`-flips-a-verdict case;
  the never-FAIL stability branch; repeated computation identical.
- `test_identity` — `sha256:`-prefixed, deterministic, each-fold-changes-the-id (each of the three
  `source_result_hash` pins, the `alpha` fold, the answer), result-hash sensitive to the verdict and
  each criterion, and the domain separation (`id ≠ result_hash`).
- `test_result` — seal folds the answer, derived id aliases `research_result_id`, byte-identical
  round-trip (each verdict), id re-derived not read from state (tampered stored id ignored), a
  verdict/criterion change changes the hash and the id, the three source-ref accessors, and that the
  record is not a `Pit*` type and exposes no `as_of`.
- `test_public_api` — public exports and the lazy/cached `Workspace.admissibility_engine`.
- `test_engine` — happy ADMISSIBLE path (three MEASURED/TESTED/STABLE sources, all three refs
  pinned), INADMISSIBLE (miscalibration / unprofitable), UNDEFINED (each of the three sources
  undefined), `alpha` flips the verdict, boundary carried and the record not PIT; recompute
  byte-identical and idempotent; every fail-closed guard (absent each source, a wrong-typed record, a
  non-source record, id-mismatch via a path-swapped payload, a non-spec argument, and a tampered
  stored payload → `FactorConsistencyError`).

**Gate (all green): `ruff check .` / `ruff format --check .` / `mypy src tests` / `pytest -q` /
`pytest -q -p no:randomly` (2291 tests pass); zero new runtime dependencies; every prior-phase id
preserved (no prior source touched beyond the additive `workspace.py` / `__init__.py` re-exports).**
