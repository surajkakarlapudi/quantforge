# Phase 33 Proposal — Strategy Admissibility (Taken Together, Is This Strategy Admissible?)

**Status: DESIGN ONLY — PROPOSAL. Nothing described here is implemented.**
No source, test, `README`, `ARCHITECTURE`, `docs/index.md`, or `docs/data-model.md` file has been
created or modified by this document. This is a capability-frontier investigation and a design
proposal awaiting approval. Implementation is explicitly out of scope and is flagged as such in
every section (see **§12 DESIGN ONLY vs IMPLEMENTATION**).

- **Proposed version:** `v0.30.0`
- **Proposed capability class:** *the first multi-source integrator* — the first consumer in the
  research spine that resolves **more than one** sealed terminal artifact, combining the three
  ex-post verdicts of one strategy (stability, calibration significance, net-of-cost significance)
  into a single admissibility decision. It answers the one question no single validator states:
  *taken together, is this strategy admissible?*
- **Repository state at time of writing:** `HEAD` at Phase 32 (`v0.29.0`, `netcostsig`) —
  Net-of-Cost Significance is the immediate parent. The next honest phase is **Phase 33**.
- **Direction:** the user selected *Strategy Admissibility* — the multi-terminal integrator that
  was repeatedly deferred through Phases 29–32 (the alternatives — equality-constrained GMV, a
  higher-moment net-Sharpe test — remain open for later phases; see §5).

---

## 0. Scope of the investigation

Per the standing mandate, this proposal is preceded by a repository-wide read: the sealed-artifact
/ consumer graph, the shared numerical primitives (`_linalg`, `_stats`), the shared
`ResearchResultStore`, the three source packages this phase consumes (`stability`(27), `calsig`(29),
`netcostsig`(32)), the pure-consumer template every prior layer follows, and the binding invariants
in `docs/data-model.md §12`. Sections §1–§5 record the findings that constrain the design; §6
onward is the proposal proper.

The existing architecture and invariants are **binding**. A candidate is rejected the moment it
would violate exact-`Decimal` determinism, introduce RNG / floating point / wall-clock dependence,
cross a PIT boundary, break content-addressed identity or write-once persistence, require a second
store, fabricate a financial input, add unnecessary ingestion, or add an unnecessary numerical
primitive.

---

## 1. Current architecture map (as of Phase 32 / `v0.30.0`-pending)

Main package `src/quantforge/` (src layout, zero runtime dependencies). Research/analytics layers
are sibling packages with the same shape (`spec.py` + `engine.py` + `result.py` +
`compute.py`/`model.py` + `identity.py` + `version.py`): `backtest/`(12) … `stability/`(27),
`mintrl/`(28), `calsig/`(29), `campaignmult/`(30), `netcost/`(31), **`netcostsig/`(32)**. A
`Workspace` facade exposes every engine as a lazy property.

**Shared internal primitives (deliberately minimal):**
- `_linalg/decimal_ols.py` — exact-`Decimal` `ldl` / `ldl_solve` / `inverse_diagonal`.
- `_stats/normal.py` — exact-`Decimal` `standard_normal_cdf` (`Φ`) and `standard_normal_ppf`
  (`Z⁻¹`). **This phase reuses neither** — it evaluates no transcendental of its own; the `Φ` CDF
  was already applied and sealed by the significance layers (Phases 29 / 32). Phase 33 performs only
  exact-`Decimal` comparisons of the consumed p-values against the declared `alpha`.

**The store.** One shared `ResearchResultStore` (`factors/store.py`): one JSON file per result,
write-once by byte-comparison (`FactorConsistencyError` on a differing payload under an existing
id), atomic writes, re-derived id property. There is exactly one store; no database.

---

## 2. Terminal artifacts and the three leaves this phase consumes

**Producer → consumer edges (verified by `store.read_as(...)` in each `engine.py`):**

```
FactorPortfolio(19) → FactorRiskModel(20) → PortfolioOptimization(21) → WalkForwardEvaluation(22)
WalkForwardEvaluation(22) ─┬→ ResearchCampaignEvaluation(23) ─┬→ MinimumTrackRecordLength(28)      [trial moments]
                           │                                  └→ CampaignMultiplicityCorrection(30) [trial psr]
                           ├→ StrategyComparison(24) → MultipleComparisonCorrection(25)             [pairwise p]
                           ├→ RiskForecastCalibration(26) → CalibrationSignificance(29)             [calib summary]
                           └→ WalkForwardStability(27) ─┬→ NetOfCostPerformance(31) → NetOfCostSignificance(32) [net p]
                                                        └→ (stability_status)
```

**All three sources descend from one `WalkForwardEvaluation`(22) root** — the same walk of one
strategy. Phase 33 is the first layer that resolves more than one of them at once:

- **`WalkForwardStability`(27)** — reads its `stability_status` (`STABLE` / `UNDEFINED`: the layer
  never asserts "unstable", only "not assessable").
- **`CalibrationSignificance`(29)** — reads its `significance_status` (`TESTED` / `UNDEFINED`) and
  the **two-sided** `summary.p_value` cell (a variance-ratio-vs-`1` test — whether the risk model is
  significantly mis-calibrated).
- **`NetOfCostSignificance`(32)** — reads its `significance_status` (`TESTED` / `UNDEFINED`), the
  **one-sided** `summary.p_value` cell, and the `summary.edge_direction`
  (`PROFITABLE` / `UNPROFITABLE` / `FLAT`).

**The gap the validator battery leaves open.** Each of the three layers answers exactly one
question about one strategy — is the book stable? is the risk model calibrated? is the after-cost
edge real? — and seals it as a first-class ex-post verdict. Nothing yet reads all three and asks the
*joint* question a portfolio manager actually faces: *given all three verdicts, is this strategy
admissible?* Phase 33 is that integrator — the capstone over the validator battery.

---

## 3. Why this capability (boundary analysis)

Phases 29–32 repeatedly deferred the "multi-terminal admissibility integrator" as the highest
structural-value move at the boundary, pending an explicit ruling on the "convenience / meta-report"
line — i.e. is a layer that only *reads and combines* already-sealed verdicts a genuine
content-addressed research artifact, or merely a report? The completion of the net-of-cost
significance branch (Phase 32) resolves that question: the three ex-post verdicts of a strategy now
exist as sealed leaves, and combining them under a declared decision rule is itself a *decision* —
a reproducible, content-addressed, transitively-pinned research statement, not a transient report.

Three signals argue for it now:

1. **It is the first genuinely new topological move since Phase 22.** Every layer built since is a
   single-source consumer (one artifact in, one verdict out). Strategy admissibility is the **first
   multi-source consumer**: it resolves three sealed artifacts, verifies each independently, folds
   all three `result_hash` values, and is transitively sensitive to any change beneath any of them.
   This exercises the reference-verification and transitive-pinning discipline at a fan-in it has
   never been tested at.
2. **It closes the validator battery with the question it was built to answer.** Stability,
   calibration significance, and net-of-cost significance were each built as an independent gate.
   Admissibility is the conjunction those gates were always implicitly building toward — the single
   verdict a strategy is or is not fit to trade.
3. **No new machinery, the lowest-risk possible integrator.** It reuses the pure-consumer template
   verbatim, adds **no** numerical primitive (the `Φ` CDF was already applied by the significance
   layers — Phase 33 only compares sealed p-values against `alpha` in exact `Decimal`), touches no
   `_linalg`/`_stats`, adds no RNG/float/wall-clock, no ingestion, no new store, no PIT surface.

The one honest caveat (disclosed, not hidden): a pure integrator seals no *new* computed magnitude —
it re-derives no statistic, only combines. That is by design (AD-4: verbatim consumption), and it is
exactly what makes the phase low-risk. Its value is the joint verdict and its transitive pin, not a
new number. The higher-machinery alternatives (constrained GMV; a higher-moment net-Sharpe test)
remain available and are explicitly **not** foreclosed by this phase.

---

## 4. Binding invariants (the rejection filter)

The same ten as the canon; every design choice below is tested against them:

1. **Exact `Decimal`, no float** (pinned `prec=34, ROUND_HALF_EVEN`; scale/sign folded once;
   canonical string serialization).
2. **No RNG.** 3. **No wall-clock.** 4. **PIT boundaries** (research artifacts above Phase 12 are
   ex-post — not a `Pit*` type, no as-of accessor; `boundary_kind` documents only the underlying
   walk). 5. **Content-addressed identity** (folds engine/method/decimal-context version + full
   declared spec + each referenced id **and** its `result_hash` (transitive pin) + a `result_hash`
   over the ordered computed answer). 6. **Write-once persistence** (one shared store;
   byte-identical round-trip or `FactorConsistencyError`; no new store). 7. **No fabricated
   financial data** (a consumed UNDEFINED verdict yields an UNDEFINED criterion, never an imputed
   pass/fail). 8. **No unnecessary ingestion.** 9. **No unnecessary numerical primitive** (adds
   none; evaluates no transcendental). 10. **Fail-closed degeneracy** (a criterion whose source is
   undefined is a first-class recorded `UNDEFINED`; the roll-up fails closed to UNDEFINED, never a
   silent inadmissible).

Strategy Admissibility passes all ten. It reads three already-sealed verdicts, compares two sealed
p-values against `alpha`, seals a fail-closed joint verdict, and pins all three sources transitively.

---

## 5. Candidate framing (brief)

The full ≥16-candidate survey lives in the Phase 31 proposal §5 and is not repeated. The user
selected **Strategy Admissibility** — the multi-terminal integrator repeatedly deferred through the
significance phases:

| Candidate | Class | Disposition |
|-----------|-------|-------------|
| **Strategy admissibility** (this proposal) | architecture-honest | **SELECTED** — the first multi-source consumer; resolves the three ex-post verdicts of one strategy; adds no primitive; closes the validator battery. |
| Higher-moment net-Sharpe significance | architecture-honest | Deferred — needs a Phase 31 payload extension (sealing net-series skew/kurtosis) before a PSR/DSR-style net test is possible. Open for a later phase. |
| Equality-constrained GMV `Aw=b` | questionable | Deferred — needs an additive `_linalg` matmul + a second `ldl` solve; the canon repeatedly flags this as "a different (larger) phase" that bumps invariant 9. Open for a later phase. |

---

## 6. The proposal proper — Strategy Admissibility

### 6.1 One-sentence statement

**Combine the three sealed ex-post verdicts of one strategy into a single admissibility decision**:
resolve one `WalkForwardStability`, one `CalibrationSignificance`, and one `NetOfCostSignificance`,
read each layer's already-computed answer verbatim, and seal an `ADMISSIBLE` / `INADMISSIBLE` /
`UNDEFINED` verdict — `ADMISSIBLE` only when the book was STABLE, the two-sided calibration p-value
`> alpha` (not significantly mis-calibrated), and the one-sided net-of-cost p-value `<= alpha` with
a PROFITABLE edge (significantly profitable after costs), against a declared level `alpha`.

### 6.2 New package `src/quantforge/admissibility/` (mirrors `netcostsig/`)

```
version.py    AdmissibilityEngineVersion + ADMISSIBILITY_{SPEC,ENGINE,METHOD}_VERSION; folds the
              pinned decimal context AND Phase 33's own method version into config_hash. There is
              NO normal-version fold — Phase 33 evaluates no standard-normal primitive of its own.
errors.py     AdmissibilityError → *ConfigurationError, *ConsistencyError.
model.py      AdmissibilityVerdict (ADMISSIBLE | INADMISSIBLE | UNDEFINED); CriterionKind
              (STABILITY | CALIBRATION | NET_OF_COST_EDGE); CriterionStatus (PASS | FAIL |
              UNDEFINED); AdmissibilityUndefinedReason (STABILITY_UNDEFINED |
              CALIBRATION_UNDEFINED | NET_OF_COST_UNDEFINED); the Criterion cell (kind + status +
              optional detail + reason, with passed()/failed()/undefined() constructors).
spec.py       AdmissibilitySpecification(name, source_stability_id,
              source_calibration_significance_id, source_net_of_cost_significance_id, alpha,
              spec_version) — alpha the single per-request numerical parameter, canonicalized at
              construction and folded into the id. Validates its own shape (fail closed).
identity.py   admissibility_id / admissibility_result_hash; domain "admissibility/1".
compute.py    AdmissibilityInputs (the primitive facts) + AdmissibilityComputation +
              decide_admissibility(inputs, *, alpha, context).
result.py     StrategyAdmissibility (sealed ResearchRecord) + AdmissibilitySummary; BOUNDARY_PIT.
engine.py     AdmissibilityEngine.evaluate(spec).
__init__.py   public re-exports (sorted __all__).
```

Wired additively: `Workspace.admissibility_engine` (lazy `@property`, deferred import, private cache
slot) and top-level `quantforge.AdmissibilitySpecification` / `quantforge.StrategyAdmissibility`
re-exports. **No new store, no new ingestion, no new PIT surface, no runtime dependency, no
`_linalg`/`_stats` expansion, no new numerical primitive.**

### 6.3 The declarative request (`spec.py`)

```
AdmissibilitySpecification:
    name:                               str  # non-empty
    source_stability_id:                str  # research_result_id of one WalkForwardStability
    source_calibration_significance_id: str  # research_result_id of one CalibrationSignificance
    source_net_of_cost_significance_id: str  # research_result_id of one NetOfCostSignificance
    alpha:                              str = "0.05"     # declared level, canonicalized
    spec_version:                       str = "admissibility/1"
```

`alpha` is the single numerical parameter: the level below which the net-of-cost one-sided p-value
is deemed significantly profitable, and above which the calibration two-sided p-value is deemed not
significantly mis-calibrated. It is validated at construction (a decimal string strictly inside
`(0, 1)`), canonicalized once (`str(Decimal(alpha).normalize())`, so `"0.05"` and `"0.050"` are the
same request), and folded into `admissibility_id` (AD-5). The joint-decision rule itself is the
single approved method (no other tunable input).

### 6.4 Engine flow (`engine.py`) — the first multi-source resolver

1. **Reject** a non-`AdmissibilitySpecification` argument → `AdmissibilityConfigurationError`.
2. **Resolve** each of the three source ids from the shared sidecar via
   `store.read_as(id, <T>.from_dict)` for `T ∈ {WalkForwardStability, CalibrationSignificance,
   NetOfCostSignificance}`. For each: a missing id, an undecodable payload (not the expected type),
   or a resolved record whose `research_result_id` disagrees with the request →
   `AdmissibilityConsistencyError` (fail closed, AD-1). Each resolution also transitively pins the
   source's own `result_hash`; each source's id in turn pins the walk chain beneath it.
3. **Reduce** each verdict to its primitive fact (AD-4), reading the sealed statuses / p-values /
   edge direction verbatim — never recomputing any statistic (`_inputs(stability, calibration,
   net_of_cost) → AdmissibilityInputs`).
4. **Decide** the joint verdict under the version's decimal context (`decide_admissibility`, §6.5).
5. **Seal + persist**: seal a `StrategyAdmissibility` (its `result_hash` folds the answer, its id
   transitively pins all three sources' `result_hash`), carrying `boundary_kind = "pit"` to document
   the input side (AD-6), and persist write-once. An identical re-build is a byte-identical no-op.

### 6.5 The pure decision rule (`compute.py`)

Three criteria in the **fixed order** STABILITY, CALIBRATION, NET_OF_COST_EDGE (so the answer seal
is deterministic), evaluated under an explicit `localcontext`:

- **Stability** — PASS iff the source book was STABLE; else UNDEFINED (`STABILITY_UNDEFINED`). The
  stability layer's status is binary (STABLE vs UNDEFINED — it never asserts "unstable"), so this
  criterion **never FAILs**: it passes or is undefined.
- **Calibration** (two-sided, null variance ratio `1`) — PASS iff the sealed p-value `> alpha` (fail
  to reject calibration — not significantly mis-calibrated); FAIL iff `<= alpha` (significantly
  mis-calibrated); UNDEFINED (`CALIBRATION_UNDEFINED`) iff the source was not TESTED / its p-value is
  not KNOWN.
- **Net-of-cost edge** (one-sided upper-tailed, null mean `0`) — PASS iff the sealed p-value
  `<= alpha` **and** the edge is PROFITABLE (significantly positive after costs); FAIL otherwise
  (decidable but not both); UNDEFINED (`NET_OF_COST_UNDEFINED`) iff the source was not TESTED / its
  p-value is not KNOWN.

**The fail-closed roll-up (AD-2):** `UNDEFINED` iff **any** criterion is UNDEFINED (a strategy whose
stability, calibration, or after-cost edge could not even be assessed is not silently called
inadmissible — the verdict is undefined); `ADMISSIBLE` iff all three PASS; otherwise `INADMISSIBLE`
(every criterion decidable, at least one FAIL). **UNDEFINED dominates a FAIL.**

The rule is a set of exact-`Decimal` comparisons; it evaluates **no** transcendental, has **no** RNG,
**no** float, and **no** data-dependent iteration.

### 6.6 What gets sealed (`result.py`)

`AdmissibilitySummary`:

```
verdict   AdmissibilityVerdict            # the roll-up
alpha     str                             # the canonical declared level tested
criteria  tuple[Criterion, ...]           # the three ordered cells (STABILITY, CALIBRATION,
                                          # NET_OF_COST_EDGE), each kind + status + optional
                                          # audit detail (observed p-value / status label) +
                                          # reason (iff UNDEFINED)
```

`StrategyAdmissibility` (frozen dataclass, `slots=True`, a `ResearchRecord`): the sealed
`admissibility_engine_version_id`, the `admissibility_spec` dict, three
`(source_id, source_result_hash)` refs (`stability_ref`, `calibration_ref`, `net_of_cost_ref`),
`boundary_kind` (`"pit"`), the `summary`, and the stored `method_version`. `seal(...)` folds the
summary into `result_hash`; `admissibility_id` / `research_result_id` are re-derived properties;
`to_dict`/`from_dict` round-trip byte-identically and fail closed on a malformed payload. It stores
only *pointers* to the three sources, never a copy of their contents (the pointer-only discipline).

### 6.7 Identity (`identity.py`)

```
admissibility_result_hash = sha256( canonical JSON over the ordered computed-output cells:
    the single {block:"summary", verdict, alpha, criteria} block )
admissibility_id = sha256( domain "admissibility/1",
    admissibility_engine_version_id, name, spec_version,
    source_stability_id, source_stability_result_hash,
    source_calibration_significance_id, source_calibration_result_hash,
    source_net_of_cost_significance_id, source_net_of_cost_result_hash,
    alpha, admissibility_result_hash )
```

The engine version folds the pinned decimal context (prec 34, `ROUND_HALF_EVEN`) and Phase 33's own
`ADMISSIBILITY_METHOD_VERSION`. There is **no** normal-primitive fold (no `Φ` is evaluated here). The
declared `alpha` is folded into the id (AD-5). Folding all three sources' `result_hash` makes the
verdict's id transitively sensitive to any change in any consumed verdict or anything beneath it
(AD-1). `research_result_id` aliases `admissibility_id`.

---

## 7. Invariants (AD-1..AD-6)

- **AD-1 Multi-source reference verification & transitive pinning.** Resolves each of the three
  source ids via `store.read_as(id, <T>.from_dict)`, re-verifies `research_result_id == id` and that
  each decodes as its expected type, and folds each `result_hash` into the admissibility id; through
  each source's own id this pins the walk / optimization / risk-model / factor chain beneath it. Any
  missing, non-decoding, or id-mismatched reference (at any of the three) fails closed with
  `AdmissibilityConsistencyError`; no source is copied, only pinned.
- **AD-2 Fail-closed roll-up; the record always seals.** `UNDEFINED` iff any criterion is UNDEFINED
  (UNDEFINED dominates a FAIL — a strategy whose stability / calibration / edge could not be assessed
  is never silently called inadmissible); `ADMISSIBLE` iff all PASS; else `INADMISSIBLE`. A consumed
  verdict that is itself UNDEFINED is a data condition, never an exception — it seals an UNDEFINED
  criterion and a fail-closed UNDEFINED roll-up.
- **AD-3 Per-criterion pass definitions.** Stability: PASS iff STABLE, else UNDEFINED (never FAILs).
  Calibration: PASS iff two-sided p `> alpha`, FAIL iff `<= alpha`, UNDEFINED iff source not
  TESTED / p not KNOWN. Net-of-cost edge: PASS iff one-sided p `<= alpha` and PROFITABLE, FAIL if
  decidable-but-not, UNDEFINED iff source not TESTED / p not KNOWN.
- **AD-4 Verbatim consumption; no recomputation.** Every input (the stability status, the two
  p-values, the edge direction) is read verbatim from a source record's sealed cells; the engine
  recomputes no statistic and evaluates no transcendental (the `Φ` CDF was applied and sealed by the
  significance layers). The sealed answers are authoritative.
- **AD-5 The declared level is canonicalized and folded.** `alpha` is canonicalized once
  (`str(Decimal(alpha).normalize())`, so equal levels are the same request regardless of spelling)
  and folded into `admissibility_id`, so a change to the declared level is a distinguishable record.
- **AD-6 A strategy admissibility is not a PIT value and not a `BacktestResult`.** A decision over
  three already-ex-post verdicts is itself ex-post: `StrategyAdmissibility` is **not** a `Pit*` type,
  exposes no as-of accessor, is a distinct record type, and simulates no fills.
  `boundary_kind = "pit"` documents only that the *underlying factor portfolios* (beneath each
  consumed verdict's walk-forward) were PIT walks — the label describes the input side, never the
  ex-post output.

---

## 8. Failure semantics

- **Data condition** (any consumed verdict itself UNDEFINED — the book never assessable, the
  calibration or net-of-cost test never run) → the corresponding criterion is UNDEFINED and the
  roll-up fails closed to UNDEFINED; recorded, never raised.
- **Configuration defect** (empty `name` / `spec_version` / any source id; an `alpha` outside
  `(0, 1)`; a non-spec argument) → `AdmissibilityConfigurationError`.
- **Consistency defect** (any source absent / undecodable / wrong type / id mismatch) →
  `AdmissibilityConsistencyError`.

---

## 9. Determinism

Exact `Decimal` only — three comparisons of two consumed p-values against `alpha` — all under an
explicit prec-34 `ROUND_HALF_EVEN` `localcontext`. **No transcendental is evaluated** (the `Φ` CDF
was applied and sealed upstream); no float, RNG, wall-clock, UUID, or iteration-order dependence; the
engine holds no mutable per-run state, so two builds of the same spec over the same immutable sidecar
are byte-identical.

---

## 10. Test plan (mirrors `tests/netcostsig/`, ~55–70 tests)

- `test_spec` — shape validation (empty name / any source id / spec_version refused; `alpha` outside
  `(0, 1)` refused; `alpha` canonicalized `"0.050"` → `"0.05"`), `to_dict` determinism, frozen.
- `test_model` — the `Criterion` construction invariants (UNDEFINED must carry a reason; PASS/FAIL
  must not) + round-trip; the closed `AdmissibilityVerdict` / `CriterionKind` / `CriterionStatus` /
  `AdmissibilityUndefinedReason` vocabularies.
- `test_version` — the engine-version fold (method + decimal-context, **no** normal fold),
  per-input id sensitivity.
- `test_identity` — deterministic result-hash + id; per-fold sensitivity (each of the three
  `source_result_hash` pins, `alpha`, the answer); domain separation (`id ≠ result_hash`).
- `test_compute` — the ADMISSIBLE path (all PASS); each FAIL path (miscalibration, unprofitable /
  insignificant edge); each UNDEFINED path (each source undefined); UNDEFINED dominates a FAIL; the
  `alpha`-flips-a-verdict case; repeated computation identical.
- `test_result` — byte-identical round-trip; id re-derived not stored; the three source-ref
  accessors; hash sensitive to the verdict and each criterion; not a `Pit*` type / no `as_of`;
  `from_dict` fails closed.
- `test_engine` — golden end-to-end over three builder-sealed sources (happy ADMISSIBLE, all three
  refs pinned); INADMISSIBLE (miscalibration / unprofitable); UNDEFINED (each of the three sources);
  `alpha` flips the verdict; boundary carried and record not PIT; idempotent byte-identical rebuild;
  every fail-closed guard (absent each source, wrong-typed, a non-source record, id-mismatch, non-spec
  argument, tampered payload → `FactorConsistencyError`).
- `test_public_api` — top-level + package re-exports; the lazy/cached `Workspace.admissibility_engine`.

Full-suite determinism evidenced by two runs (default + `-p no:randomly`).

---

## 11. Open decisions & deferred work (to disclose in the locked doc)

- **Stability never FAILs.** The stability layer's status is binary (STABLE / UNDEFINED); the
  criterion therefore has no FAIL branch. *Alternative:* treat UNDEFINED stability as a FAIL.
  Recommendation: keep it UNDEFINED-dominant (a non-assessable book is not the same as an unstable
  one), consistent with the fail-closed posture.
- **Fixed conjunctive rule vs weighted / declarable criteria.** The rule is a fixed AND over three
  criteria. *Alternative:* a declared subset of active criteria, or weights. Recommendation: the
  fixed conjunction for this phase (the single approved method); a declarable criteria set is a clean
  later extension folded into identity.
- **A sealed computed magnitude.** Phase 33 seals no new number (AD-4: verbatim consumption).
  *Alternative:* a composite admissibility *score*. Recommendation: no — a score would fabricate a
  cross-verdict metric with no principled scale; the joint verdict + per-criterion cells are the
  honest output.
- **Multi-strategy admissibility ranking.** Deferred: a layer that admits/ranks several strategies'
  admissibility records would be a further multi-source consumer, cleanly built on this leaf.

---

## 12. DESIGN ONLY vs IMPLEMENTATION

This document is a proposal. **No code, test, or documentation has been written or modified.** No
package `src/quantforge/admissibility/` exists; `Workspace` and the top-level `__init__.py` are
unchanged; `README.md`, `ARCHITECTURE.md`, `docs/index.md`, and `docs/data-model.md` are unchanged by
this document. Implementation, wiring, tests, docs, and the quality gates are explicitly out of scope
and would follow only upon approval, as a separate step.

---

## 13. Repository status at time of writing

- Branch `main`; `HEAD` at Phase 32 (`v0.29.0`, `netcostsig`); working tree otherwise clean.
- **This proposal adds exactly one untracked file:** `docs/phase33-strategy-admissibility-proposal.md`.
- **No commit, push, tag, or release has been made.**
