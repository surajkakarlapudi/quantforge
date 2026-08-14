# Phase 32 Proposal — Net-of-Cost Significance (Is the After-Cost Edge Statistically Real?)

**Status: DESIGN ONLY — PROPOSAL. Nothing described here is implemented.**
No source, test, `README`, `ARCHITECTURE`, `docs/index.md`, or `docs/data-model.md` file has been
created or modified by this document. This is a capability-frontier investigation and a design
proposal awaiting approval. Implementation is explicitly out of scope and is flagged as such in
every section (see **§12 DESIGN ONLY vs IMPLEMENTATION**).

- **Proposed version:** `v0.29.0`
- **Proposed capability class:** *statistical inference over an economic quantity* — the first
  significance test applied to an **after-cost** (net-of-cost) figure, and the first consumer of
  the terminal `NetOfCostPerformance` leaf that Phase 31 (`v0.28.0`) just created.
- **Repository state at time of writing:** `HEAD = 15d2cef`, tagged `v0.28.0` — Phase 31
  (Net-of-Cost Walk-Forward Performance) is committed and released; the working tree is clean. This
  proposal treats Phase 31 as the immediate parent. The next honest phase is **Phase 32**.
- **Direction:** the user selected *Net-of-Cost Significance* from the three architecture-honest
  candidates at the current boundary (the alternatives — a multi-terminal admissibility integrator,
  and equality-constrained GMV — remain open for later phases; see §5).

---

## 0. Scope of the investigation

Per the standing mandate, this proposal is preceded by a repository-wide read: the sealed-artifact
/ consumer graph, the shared numerical primitives (`_linalg`, `_stats`), the shared
`ResearchResultStore`, the Phase 29 `calsig` package (the exact template this phase mirrors), the
just-built Phase 31 `netcost` package (the source this phase consumes), and the binding invariants
in `docs/data-model.md §12`. Sections §1–§5 record the findings that constrain the design; §6
onward is the proposal proper.

The existing architecture and invariants are **binding**. A candidate is rejected the moment it
would violate exact-`Decimal` determinism, introduce RNG / floating point / wall-clock dependence,
cross a PIT boundary, break content-addressed identity or write-once persistence, require a second
store, fabricate an expected return / price / benchmark, add unnecessary ingestion, or add an
unnecessary numerical primitive.

---

## 1. Current architecture map (as of Phase 31 / `v0.29.0`-pending)

Main package `src/quantforge/` (src layout, zero runtime dependencies). Research/analytics layers
are sibling packages with the same shape (`spec.py` + `engine.py` + `result.py` +
`compute.py`/`model.py` + `identity.py` + `version.py`): `backtest/`(12) … `stability/`(27),
`mintrl/`(28), `calsig/`(29), `campaignmult/`(30), **`netcost/`(31)**. A `Workspace` facade exposes
every engine as a lazy property.

**Shared internal primitives (deliberately minimal):**
- `_linalg/decimal_ols.py` — exact-`Decimal` `ldl` / `ldl_solve` / `inverse_diagonal`.
- `_stats/normal.py` — exact-`Decimal` `standard_normal_cdf` (`Φ`, guarded all-positive-term `erf`
  series) and `standard_normal_ppf` (`Z⁻¹`). **This phase reuses `standard_normal_cdf` verbatim**
  — the same primitive Phase 24 and Phase 29 reuse; no new primitive is added.

**The store.** One shared `ResearchResultStore` (`factors/store.py`): one JSON file per result,
write-once by byte-comparison (`FactorConsistencyError` on a differing payload under an existing
id), atomic writes, re-derived id property. There is exactly one store; no database.

---

## 2. Terminal artifacts and the leaf this phase consumes

**Producer → consumer edges (verified by `store.read_as(...)` in each `engine.py`):**

```
FactorPortfolio(19) → FactorRiskModel(20) → PortfolioOptimization(21) → WalkForwardEvaluation(22)
WalkForwardEvaluation(22) ─┬→ ResearchCampaignEvaluation(23) ─┬→ MinimumTrackRecordLength(28)      [trial moments]
                           │                                  └→ CampaignMultiplicityCorrection(30) [trial psr]
                           ├→ StrategyComparison(24) → MultipleComparisonCorrection(25)             [pairwise p]
                           ├→ RiskForecastCalibration(26) → CalibrationSignificance(29)             [calib summary]
                           └→ WalkForwardStability(27) → NetOfCostPerformance(31)                   [per-window turnover]
```

**`NetOfCostPerformance` (31) is the newest terminal leaf** — no downstream consumer today. It
seals, among other cells, an aggregate `NetOfCostSummary` with a **KNOWN** `net_mean` and
`net_volatility` (the per-period arithmetic mean and *population* volatility of the after-cost OOS
return series, produced by the reused Phase 19 `series_summary`) and a `NetOfCostCoverage` carrying
`n_periods` (the number of OOS periods the net series summarizes), plus a `net_status`
(`MEASURED` / `UNDEFINED`). It transitively pins `WalkForwardStability`(27) →
`WalkForwardEvaluation`(22) → the optimization / risk-model / factor chain beneath.

**The gap Phase 31 leaves open.** Phase 31 seals the *magnitude* of the after-cost edge
(`net_mean`, `net_sharpe`, `cost_drag`) but never asks whether that edge is **statistically
distinguishable from zero given the realized sample length**. That is exactly the relationship
Phase 26 → Phase 29 already modeled: Phase 26 sealed the *magnitude* of mis-calibration; Phase 29
tested it. Phase 32 is the **net-of-cost analogue of Phase 29** — the first significance test on an
economic quantity.

---

## 3. Why this capability (boundary analysis)

The Phase 31 proposal's own boundary analysis (§6) argued the two principled next moves were
"(a) the first economic consumer of a terminal leaf" — which Phase 31 took — "or (b) the first
multi-terminal integrator." Net-of-Cost Significance is a refinement of neither and both: it is the
*inferential completion* of the economic branch Phase 31 opened, and it is the single lowest-risk,
most pattern-consistent way to make the new economic leaf answerable.

Three signals argue for it:

1. **Exact parallel to a shipped, locked phase.** Phase 29 (`calsig`) is a pure consumer of one
   sealed magnitude-artifact (`RiskForecastCalibration`) that reads three sealed aggregates
   verbatim, runs a one-sample large-sample test via the reused `Φ`, and seals a significance
   verdict. Phase 32 replaces "mean variance ratio vs null `1`" with "net mean return vs null `0`"
   and reuses the identical machinery. The design risk is minimal because the template is proven.
2. **A genuinely new dimension of inference.** Every significance/correction leaf to date (23 PSR,
   24, 25, 29, 30) tests a *gross* or *dimensionless* quantity. Nothing yet tests whether an
   **after-cost** return survives statistically. This is not "more correction"; it is the first
   inferential lens on money.
3. **No new machinery.** Reuses `standard_normal_cdf` verbatim; adds only `Decimal.sqrt` (already
   ubiquitous) and four exact-`Decimal` operations. No new primitive, no `_linalg`/`_stats` change,
   no RNG/float/wall-clock, no ingestion, no new store, no PIT surface.

The one honest caveat (disclosed, not hidden): this is the **fourth `Φ`-based significance leaf**.
The diminishing-returns concern the Phase 31 §6 analysis raised about "another statistical leaf" is
real. It is outweighed here because (a) the leaf tests a genuinely new *economic* quantity, (b) the
source leaf (31) would otherwise remain un-answerable, and (c) it is a faithful, low-risk mirror of
an already-approved phase rather than novel machinery. The higher-structural-value alternatives
(multi-terminal integrator; constrained GMV) remain available and are explicitly **not** foreclosed
by this phase.

---

## 4. Binding invariants (the rejection filter)

The same ten as the canon; every design choice below is tested against them:

1. **Exact `Decimal`, no float** (pinned `prec=34, ROUND_HALF_EVEN`; scale/sign folded once;
   canonical string serialization).
2. **No RNG.** 3. **No wall-clock.** 4. **PIT boundaries** (research artifacts above Phase 12 are
   ex-post — not a `Pit*` type, no as-of accessor; `boundary_kind` documents only the underlying
   walk). 5. **Content-addressed identity** (folds engine/method/decimal-context version + full
   declared spec + referenced id **and** its `result_hash` (transitive pin) + a `result_hash` over
   the ordered computed answer). 6. **Write-once persistence** (one shared store; byte-identical
   round-trip or `FactorConsistencyError`; no new store). 7. **No fabricated financial data**
   (UNDEFINED is preferable to an invented input). 8. **No unnecessary ingestion.** 9. **No
   unnecessary numerical primitive** (reuse `standard_normal_cdf`; add none). 10. **Fail-closed
   degeneracy** (every degenerate case a first-class recorded `UNDEFINED`, never a divide-by-zero;
   honest labels).

Net-of-Cost Significance passes all ten. It reads three already-sealed `Decimal`s, applies one
`Decimal.sqrt` and one reused `Φ`, seals a fail-closed verdict, and pins its source transitively.

---

## 5. Candidate framing (brief)

The full ≥16-candidate survey lives in the Phase 31 proposal §5 and is not repeated. The user
selected **Net-of-Cost Significance** from the three architecture-honest candidates at this
boundary:

| Candidate | Class | Disposition |
|-----------|-------|-------------|
| **Net-of-cost significance** (this proposal) | architecture-honest | **SELECTED** — pure consumer of `NetOfCostPerformance`; reuses `Φ`; no new primitive; first inference on an economic quantity. |
| Multi-terminal admissibility integrator | questionable | Deferred — highest structural value (first multi-source consumer, resolves the 6-orphaned-leaves boundary) but needs an explicit ruling on the "convenience/meta-report" line. Open for a later phase. |
| Equality-constrained GMV `Aw=b` | questionable | Deferred — needs an additive `_linalg` matmul + a second `ldl` solve; the canon repeatedly flags this as "a different (larger) phase" that bumps invariant 9. Open for a later phase. |

---

## 6. The proposal proper — Net-of-Cost Significance

### 6.1 One-sentence statement

**Test whether the after-cost mean return of one sealed `NetOfCostPerformance` is statistically
distinguishable from zero**: read its KNOWN `net_mean`, `net_volatility`, and `n_periods` verbatim
and seal a one-sample, upper-tailed, large-sample significance test — `standard_error = net_volatility / √n`,
`t = net_mean / standard_error`, `p = 1 − Φ(t)` — against the fixed null "no after-cost edge"
(`NULL_MEAN_RETURN = 0`), plus a descriptive `edge_direction`.

### 6.2 New package `src/quantforge/netcostsig/` (mirrors `calsig/`)

```
version.py    NetOfCostSignificanceEngineVersion + NETCOSTSIG_{SPEC,ENGINE,METHOD,NORMAL}_VERSION;
              folds the pinned decimal context, Phase 32's own method version, AND the reused
              _stats normal-primitive version (NETCOSTSIG_NORMAL_VERSION). Exact copy of the
              calsig version dataclass shape.
errors.py     NetOfCostSignificanceError / *ConfigurationError / *ConsistencyError.
model.py      SignificanceStatus (TESTED | UNDEFINED); EdgeDirection (PROFITABLE | UNPROFITABLE |
              FLAT); NetCostSigUndefinedReason (SOURCE_NOT_MEASURED | ZERO_NET_VOLATILITY);
              StatStatus + SignificanceStat (the UNDEFINED-preserving KNOWN-decimal-string / reason
              cell, mirroring calsig.model.SignificanceStat).
spec.py       NetOfCostSignificanceSpecification(name, source_net_of_cost_id, spec_version) — NO
              per-request numerical parameter (the null is a fixed platform constant), exactly like
              the calsig spec. Validates its own shape (fail closed).
identity.py   net_of_cost_significance_id / net_of_cost_significance_result_hash; domain
              "netcostsig/1".
compute.py    MeasuredNetSeries(net_mean, net_volatility, n_periods) + SignificanceComputation +
              test_net_of_cost_significance(family|None, *, null_mean, context).
result.py     NetOfCostSignificance (sealed ResearchRecord) + NetOfCostSignificanceSummary;
              NULL_MEAN_RETURN = "0".
engine.py     NetOfCostSignificanceEngine.evaluate(spec).
__init__.py   public re-exports (sorted __all__).
```

Wired additively: `Workspace.net_of_cost_significance_engine` (lazy `@property`, deferred import,
private cache slot) and top-level `quantforge.NetOfCostSignificanceSpecification` /
`quantforge.NetOfCostSignificance` re-exports. **No new store, no new ingestion, no new PIT surface,
no runtime dependency, no `_linalg`/`_stats` expansion.**

### 6.3 The declarative request (`spec.py`)

```
NetOfCostSignificanceSpecification:
    name:                 str            # non-empty
    source_net_of_cost_id: str           # the research_result_id of one sealed NetOfCostPerformance
    spec_version:         str = "netcostsig/1"
```

No numerical parameter. The null hypothesis is the fixed platform constant `NULL_MEAN_RETURN = "0"`
(a strategy with no after-cost edge earns zero), folded into identity — exactly as Phase 29 folds
its fixed `NULL_MEAN_RATIO = "1"`. This keeps the request a pure content-addressed reference and
avoids a fabricated benchmark (invariant 7). (A *declared* benchmark net mean is discussed as a
future extension in §11.)

### 6.4 Engine flow (`engine.py`) — mirrors `CalibrationSignificanceEngine`

1. **Reject** a non-`NetOfCostSignificanceSpecification` argument →
   `NetOfCostSignificanceConfigurationError`.
2. **Resolve** `source_net_of_cost_id` via
   `store.read_as(id, NetOfCostPerformance.from_dict)`. A missing id, an undecodable payload, or a
   resolved record whose `research_result_id` disagrees with the request →
   `NetOfCostSignificanceConsistencyError` (fail closed, NS-1). *(As in `calsig`, the resolution
   step also transitively pins the source's own `result_hash`; the source's id in turn pins the
   stability record / walk chain beneath it.)*
3. **Gate on defensibility** (NS-2): build a `MeasuredNetSeries` only when the source's
   `net_status is MEASURED` **and** its `net_mean` / `net_volatility` cells are both KNOWN — reading
   those decimal strings verbatim into `Decimal` (NS-4) and `n_periods` from `source.coverage`.
   Otherwise the family is `None` and the test is UNDEFINED `SOURCE_NOT_MEASURED` — recorded, never
   fabricated.
4. **Compute** the test (`test_net_of_cost_significance`) under the version's decimal context (§6.5).
5. **Seal + persist**: seal a `NetOfCostSignificance` (its `result_hash` folds the answer, its id
   transitively pins the source's `result_hash`), carrying `boundary_kind` through from the source
   unchanged, and persist write-once. An identical re-build is a byte-identical no-op.

### 6.5 The pure test (`compute.py`)

Given `MeasuredNetSeries(net_mean = m, net_volatility = σ, n_periods = n)` (or `None`) and the null
`μ₀ = 0`, under an explicit `localcontext`:

- **Absent family** (`None`): every statistic UNDEFINED `SOURCE_NOT_MEASURED`, `edge_direction =
  None`, `n_periods = 0`, `significance_status = UNDEFINED` (NS-2).
- **`edge_direction`** (descriptive, no significance; KNOWN whenever `m` is): `PROFITABLE` if
  `m > 0`, `UNPROFITABLE` if `m < 0`, `FLAT` if `m == 0`.
- **Zero-volatility guard** (`σ == 0`, NS-3): `standard_error = 0` (KNOWN), `t` / `p` UNDEFINED
  `ZERO_NET_VOLATILITY`; `net_mean` and `edge_direction` stay KNOWN; never a divide-by-zero.
  *(Structurally unreachable for a `MEASURED` source — a KNOWN `net_sharpe` implies `σ > 0` — but
  guarded defensively, exactly as `calsig` guards `ZERO_RATIO_DISPERSION`.)*
- **Otherwise:**
  - `standard_error = σ / √n`   *(the standard error of the mean; the **population**-volatility
    convention shared with Phase 24 / 29 — `√n`, not `√(n−1)`; the finite-sample correction and the
    Student-`t` distribution are the deferred ★, disclosed)*
  - `t = (m − μ₀) / standard_error = m / (σ / √n)`   *(equivalently `t = (m/σ)·√n` — the classic
    Sharpe `t`-statistic: the per-period Sharpe scaled by `√n`)*
  - `p = 1 − Φ(t)`   *(the **upper-tailed** large-sample p-value for `H0: μ ≤ 0` vs `H1: μ > 0`;
    a small `p` means the after-cost edge is real; clamped to `[0, 1]`; `Φ = standard_normal_cdf`
    reused verbatim under the pinned context)*
  - `significance_status = TESTED`.

**Why one-sided, not two-sided.** Phase 29's calibration bias is non-directional, so it seals a
two-sided `p`. Net-of-cost profitability is inherently *directional* — the economically meaningful
question is "does the strategy earn a positive after-cost return?", matching the one-sided posture
of the Phase 23 PSR (`P(SR > SR*)`). The proposal therefore seals the **upper-tailed** p-value as
the primary statistic. (The two-sided value `2·(1 − Φ(|t|))` is trivially derivable from the sealed
`t` and is not separately sealed; see §11 for the alternative of sealing both.)

### 6.6 What gets sealed (`result.py`)

`NetOfCostSignificanceSummary` (all cells UNDEFINED-preserving `SignificanceStat` unless noted):

```
net_mean            SignificanceStat   # carried verbatim from the source
null_mean_return    str = "0"          # the fixed null, echoed for readability + folded in id
n_periods           int                # the source's OOS-period count (0 when family absent)
standard_error      SignificanceStat
t_statistic         SignificanceStat
p_value             SignificanceStat   # upper-tailed
edge_direction      EdgeDirection | None
significance_status SignificanceStatus
status_reason       NetCostSigUndefinedReason | None
```

`NetOfCostSignificance` (frozen dataclass, `slots=True`, a `ResearchRecord`): the sealed
`net_of_cost_significance_engine_version_id`, the `net_of_cost_significance_spec` dict, the
`source_ref = (source_net_of_cost_id, source_result_hash)`, `boundary_kind` (carried), the
`summary`, and the stored `method_version`. `seal(...)` folds the summary into `result_hash`;
`net_of_cost_significance_id` / `research_result_id` are re-derived properties;
`to_dict`/`from_dict` round-trip byte-identically and fail closed on a malformed payload.

### 6.7 Identity (`identity.py`)

```
net_of_cost_significance_result_hash = sha256( canonical JSON over the ordered summary cells:
    net_mean, null_mean_return, n_periods, standard_error, t_statistic, p_value,
    edge_direction, significance_status, status_reason )
net_of_cost_significance_id = sha256( domain "netcostsig/1",
    net_of_cost_significance_engine_version_id, name, spec_version,
    source_net_of_cost_id, source_result_hash, null_mean_return,
    net_of_cost_significance_result_hash )
```

The engine version folds the pinned decimal context (prec 34, `ROUND_HALF_EVEN`), Phase 32's own
`NETCOSTSIG_METHOD_VERSION`, and the reused `NETCOSTSIG_NORMAL_VERSION` (which pins *which* `Φ`
primitive produced the p-value — an honest transitive pin of reused code). The fixed
`null_mean_return` is folded into the id (as Phase 29 folds `null_mean_ratio`). `research_result_id`
aliases `net_of_cost_significance_id`.

---

## 7. Invariants (NS-1..NS-6, the CS-1..CS-6 discipline one artifact over)

- **NS-1 Reference verification & transitive pinning.** Resolves the single
  `source_net_of_cost_id` via `store.read_as(id, NetOfCostPerformance.from_dict)`, re-verifies
  `research_result_id == id` and that it decodes as a `NetOfCostPerformance`, and folds its
  `result_hash` into the significance id; through the source's own id this pins the stability record
  / walk / optimization / risk-model / factor chain beneath it. Any missing, non-decoding, or
  id-mismatched reference fails closed with `NetOfCostSignificanceConsistencyError`; the source is
  never copied, only pinned.
- **NS-2 Gate on defensibility.** A significance record is `TESTED` only when the source's
  `net_status is MEASURED` and its `net_mean` / `net_volatility` cells are KNOWN; otherwise the
  record seals with every statistic UNDEFINED `SOURCE_NOT_MEASURED`, `n_periods = 0`,
  `edge_direction = None` — never imputed.
- **NS-3 Fail-closed degeneracy; the record always seals.** A zero-volatility source seals
  `standard_error` a KNOWN `0` but `t` / `p` UNDEFINED `ZERO_NET_VOLATILITY`, with `net_mean` and
  `edge_direction` still KNOWN — never a divide-by-zero. A data condition is never an exception;
  only a request / reference defect raises.
- **NS-4 Sealed statistics consumed verbatim.** `net_mean`, `net_volatility`, and `n_periods` are
  read verbatim from the sealed source summary — never recomputed from the per-window cells or the
  net return series (which Phase 31 does not seal period-by-period anyway).
- **NS-5 Reused primitive; honest method disclosure.** The p-value's `Φ` is
  `quantforge._stats.normal.standard_normal_cdf` reused verbatim under the pinned context; no new
  primitive, no `_linalg`/`_stats` change. The test is the **large-sample** normal approximation
  with the **population** standard error (`σ/√n`, matching Phase 24/29); the finite-sample
  Student-`t` distribution is the standing ★ deferral (disclosed, matching Phase 24/29). The test is
  **one-sided upper** (directional profitability), with `NULL_MEAN_RETURN = 0` fixed and folded.
- **NS-6 A net-of-cost significance is not a PIT value and not a `BacktestResult`.** A significance
  test over an already-ex-post net-of-cost figure is itself ex-post: `NetOfCostSignificance` is
  **not** a `Pit*` type, exposes no as-of accessor, is a distinct record type, simulates no fills,
  and opens no new corpus / availability surface. `boundary_kind = "pit"` — carried unchanged from
  the source — documents only that the *underlying returns* were PIT walks, not that the
  significance output is forward-usable. (The CS-6 / NC-6 discipline, one artifact over.)

---

## 8. Failure semantics

- **Data condition** (source not `MEASURED`; zero net volatility) → recorded UNDEFINED cells with
  the reason, never raised; the record seals with its `significance_status`.
- **Configuration defect** (empty `name` / `spec_version` / `source_net_of_cost_id`; a non-spec
  argument) → `NetOfCostSignificanceConfigurationError`.
- **Consistency defect** (source absent / undecodable / wrong type / id mismatch) →
  `NetOfCostSignificanceConsistencyError`.

---

## 9. Determinism

Exact `Decimal` only — one `√n`, one division, one subtraction, and the reused `Φ` — all under an
explicit prec-34 `ROUND_HALF_EVEN` `localcontext`. `Decimal.sqrt` (in `√n`) and the reused `Φ`'s
internal `erf` series are the only transcendentals. No float, RNG, wall-clock, UUID, or
iteration-order dependence; the engine holds no mutable per-run state, so two builds of the same
spec over the same immutable sidecar are byte-identical.

---

## 10. Test plan (mirrors `tests/calsig/`, ~40–55 tests)

- `test_spec` — shape validation (empty name / source id / spec_version refused), `to_dict`
  determinism, frozen.
- `test_model` — `SignificanceStat` construction invariants + round-trip; the closed
  `EdgeDirection` / `NetCostSigUndefinedReason` / `SignificanceStatus` vocabularies.
- `test_version` — the transitive-pin binding (method + reused-normal + decimal-context folds),
  per-input id sensitivity.
- `test_identity` — deterministic result-hash + id; per-fold sensitivity; `null_mean_return` folded;
  domain separation (`id ≠ result_hash`).
- `test_compute` — a golden case with hand-checked `standard_error` / `t` / `p`; the identity
  `t = (m/σ)·√n`; `edge_direction` for `m ≷ 0` and `m = 0`; absent-family → `SOURCE_NOT_MEASURED`;
  zero-volatility guard → `ZERO_NET_VOLATILITY` (SE KNOWN 0, t/p UNDEFINED); a larger `n` yielding a
  smaller `p` for the same Sharpe (power increases with sample length); p clamped to `[0, 1]`.
- `test_result` — byte-identical round-trip; id re-derived not stored; `source_ref` accessors;
  hash sensitive to each summary cell; undefined-summary round-trip; `from_dict` fails closed.
- `test_engine` — golden end-to-end over a builder-sealed `NetOfCostPerformance`; persisted &
  readable; idempotent no-op rebuild; `MEASURED` source → `TESTED`; non-`MEASURED` source →
  `SOURCE_NOT_MEASURED` sealed (not raised); boundary + transitive pin carried; workspace property
  cached; fail-closed on non-spec / missing / wrong-type (point at a stability or walk id) /
  differing-payload-same-id.
- `test_public_api` — top-level + package re-exports.

Full-suite determinism evidenced by two runs (default + `-p no:randomly`).

---

## 11. Open decisions & deferred work (to disclose in the locked doc)

- **One-sided vs two-sided p-value.** The proposal seals the **upper-tailed** p (directional
  profitability). *Alternative:* seal both a one-sided and a two-sided p-value. Recommendation:
  one-sided only (two-sided is derivable from the sealed `t`), matching the PSR posture; open to a
  reviewer preference for sealing both.
- **Fixed null vs declared benchmark.** The null is the fixed `NULL_MEAN_RETURN = 0` (parameter-free,
  mirrors Phase 29). *Alternative:* a declared benchmark per-period net mean `μ₀` (like Phase 28's
  `benchmark_sharpe`), folded into identity. Recommendation: fixed `0` for this phase (a genuine
  "no after-cost edge" null needs no fabricated input); a declared benchmark is a clean later
  extension.
- **Finite-sample Student-`t` (★).** Deferred, matching Phase 24 / 29 — it requires a new exact-
  `Decimal` `t`-CDF primitive (regularized incomplete beta), which bumps invariant 9.
- **Higher-moment (PSR/DSR-style) net-Sharpe significance.** A skew/kurtosis-adjusted test on the
  net series is deferred: Phase 31 seals only `net_mean` / `net_volatility`, not the net series'
  third/fourth moments. A future Phase 31 payload extension (sealing net-series skew/kurtosis) would
  unlock it — noted, not assumed.
- **Autocorrelation / HAC standard errors.** Deferred: the IID standard error `σ/√n` is the
  disclosed convention; a Newey-West-style correction needs the full net series (not just its
  moments), which is not sealed.

---

## 12. DESIGN ONLY vs IMPLEMENTATION

This document is a proposal. **No code, test, or documentation has been written or modified.** No
package `src/quantforge/netcostsig/` exists; `Workspace` and the top-level `__init__.py` are
unchanged; `README.md`, `ARCHITECTURE.md`, `docs/index.md`, and `docs/data-model.md` are unchanged
by this document. Implementation, wiring, tests, docs, and the quality gates are explicitly out of
scope and would follow only upon approval, as a separate step.

---

## 13. Repository status at time of writing

- Branch `main`, up to date with `origin/main`; `HEAD = 15d2cef`, tagged `v0.28.0` (Phase 31,
  committed + released); working tree otherwise clean.
- **This proposal adds exactly one untracked file:** `docs/phase32-net-of-cost-significance-proposal.md`.
- **No commit, push, tag, or release has been made.**
