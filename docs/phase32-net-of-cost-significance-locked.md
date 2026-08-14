# Phase 32 — Net-of-Cost Significance (LOCKED)

> **Status:** Locked normative specification. The Phase 32 proposal was **implemented as
> recommended** — the single capability of
> [phase32-net-of-cost-significance-proposal.md](phase32-net-of-cost-significance-proposal.md):
> consume exactly one sealed `NetOfCostPerformance` (Phase 31), read its aggregate KNOWN
> `net_mean` (`m`), population `net_volatility` (`σ`), and OOS-period count
> (`n = n_periods`) verbatim, and seal a **one-sample, upper-tailed, large-sample
> significance test** of the null hypothesis that the after-cost mean return equals `0` (no
> after-cost edge) — `standard_error = σ/√n`, `t = (m − 0)/standard_error`, `p = 1 − Φ(t)`
> clamped to `[0, 1]` — plus the descriptive edge direction. This document reflects the
> **actual implementation** and is the source of truth; it supersedes the proposal. Every
> ★-marked decision in the proposal is resolved here.
>
> **One-line thesis:** Phase 32 adds a deterministic, content-addressed **net-of-cost
> significance** layer — the first consumer of Phase 31's sealed `NetOfCostPerformance`
> terminal leaf, and the **first significance test applied to an economic (after-cost)
> quantity**, answering the one question the net-of-cost record never states: *is the
> after-cost edge statistically distinguishable from zero given the realized sample
> length?* It is the net-of-cost analogue of Phase 29's calibration significance test
> (`calsig.compute.test_calibration_significance`), applied as a **one-sample, one-sided
> (upper-tailed)** test about the null mean `0`. Given a declarative
> `NetOfCostSignificanceSpecification` naming exactly one sealed `NetOfCostPerformance` id,
> `NetOfCostSignificanceEngine.evaluate(...)` resolves the one net-of-cost record from the
> shared Phase 8 research sidecar, re-verifies it (present, a `NetOfCostPerformance`, id
> matches), gates on its `net_status` and the KNOWN-ness of its aggregate cells, computes
> the one-sample statistics under one pinned `Decimal` context, and seals a
> `NetOfCostSignificance` `ResearchRecord` write-once to the existing sidecar. It introduces
> **no** new numerical primitive (it reuses the deterministic exact-`Decimal`
> `standard_normal_cdf` for `Φ`, and `Decimal.sqrt` is the only other transcendental),
> **no** `_linalg`/`_stats` change, **no** RNG, **no** floating point, **no** iterative
> solver, **no** new store, and **no** new PIT surface, and modifies no prior phase's
> vocabulary, engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **One-sample upper-tailed significance test of the after-cost mean return against the null `0`, over one net-of-cost performance.** The analyzed object is exactly the source `NetOfCostPerformance`'s aggregate net-series family: its sealed `net_mean` (`m`), `net_volatility` (`σ`), and `n_periods` (`n`). It seals `standard_error`, `t_statistic`, `p_value` (UNDEFINED-preserving cells), the descriptive `edge_direction`, the carried `net_mean` / `null_mean_return` / `n_periods`, and the roll-up `significance_status`. **No** per-window test, **no** cross-record family (one source only), **no** correction/multiplicity layer, **no** annualization. It performs **no execution**, resolves **no** data at any `T`, and is **not** a `BacktestResult`. |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 31.** It resolves exactly **one** already-sealed `NetOfCostPerformance` from the shared sidecar by id, reads its sealed `net_status` / `summary.net_mean` / `summary.net_volatility` / `coverage.n_periods` / `boundary_kind` (never re-derives them, never reads the per-window cost/turnover cells or anything beneath the net-of-cost record), and **modifies no** prior-phase vocabulary, engine, or identity. It is the first consumer of the aggregate net-of-cost summary Phase 31 sealed. |
| **D-COMPUTE** | **Closed-form exact-`Decimal` one-sample statistics; one reused `Φ` and one `Decimal.sqrt`.** Under the pinned context, with `n` the OOS-period count, `m` the sealed after-cost mean, `σ` the sealed population volatility, and null mean `0`: `standard_error = σ/√n`; `t_statistic = (m − 0)/standard_error`; `p_value = 1 − Φ(t)` clamped to `[0, 1]`, with `Φ` the reused exact-`Decimal` `standard_normal_cdf`. `standard_error = σ/√n` is the same population-moment standard-error convention already in the codebase (Phase 24 `√(variance/n)` with `σ = √variance`; Phase 29 `s/√K`) — no new statistical method. Equivalently `t = (m/σ)·√n`, the classic Sharpe `t`-statistic. The descriptive `edge_direction` is `PROFITABLE` when `m > 0`, `UNPROFITABLE` when `m < 0`, `FLAT` when `m == 0` (known whenever `m` is known). |
| **D-ONESIDED** | **The sealed p-value is one-sided (upper-tailed), `p = 1 − Φ(t)`.** Net-of-cost profitability is inherently *directional* — the economically meaningful question is "does the strategy earn a positive after-cost return?", matching the one-sided posture of the Phase 23 PSR (`P(SR > SR*)`) rather than Phase 29's non-directional two-sided calibration bias. The two-sided value `2·(1 − Φ(|t|))` is trivially derivable from the sealed `t` and is **not** separately sealed. *(This is a deliberate design choice recorded in the proposal §6.5, not a deviation.)* |
| **D-STATUS** | **`significance_status` defensible only on a tested source.** `TESTED` iff the source is `MEASURED` **and** its aggregate `net_mean` / `net_volatility` cells are KNOWN **and** the volatility is non-zero; else `UNDEFINED` with a first-class reason. The mean and edge direction still seal whenever the source mean is KNOWN, even when `t` / `p` are UNDEFINED. |
| **D-GATE** | **Only a `MEASURED` source with KNOWN aggregate cells is tested.** A source whose `net_status` is `UNDEFINED`, or whose sealed `net_mean` / `net_volatility` cell is not KNOWN, seals every statistic UNDEFINED (`SOURCE_NOT_MEASURED`) — never imputed, never coerced. `n_periods` is reported `0` and `edge_direction` `None` in that case. |
| **D-ZERO** | **Zero net volatility is a first-class UNDEFINED, never a divide-by-zero.** When `net_volatility == 0` the `standard_error` is a KNOWN `0`, but `t_statistic` / `p_value` are UNDEFINED (`ZERO_NET_VOLATILITY`); `net_mean` and `edge_direction` stay KNOWN. Structurally unreachable for a `MEASURED` source (a KNOWN `net_sharpe` implies `σ > 0`) but guarded defensively, exactly as Phase 29 guards `ZERO_RATIO_DISPERSION`. Never a division by a zero denominator. |
| **D-CONSUME** | **Sealed statistics are consumed verbatim.** The engine parses the source's sealed `net_mean` / `net_volatility` decimal strings once (into `Decimal`) and reads `coverage.n_periods`; it never recomputes them from the per-window cells, never re-derives a moment, and never reads the net return series (which Phase 31 does not seal period-by-period anyway). The sealed answer is authoritative (the NC-4 / CS-4 posture, one layer up). |
| **D-EXPOST** | **The output is ex-post, never PIT.** A significance test over an already-ex-post net-of-cost figure is itself ex-post. `NetOfCostSignificance` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` is carried unchanged from the source and documents only that the *underlying returns were PIT walks*; it never claims the significance output is a PIT value. No new corpus read, no availability logic, no new PIT resolution. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order.** All arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); exact subtraction, division, `Decimal.sqrt` (the standard error), the reused `standard_normal_cdf` (`Φ` via an erf series — bounded, terminating, deterministic; **not** a convergence-tolerance loop), and the `[0, 1]` clamp are the only operations; canonicalization is `str(+value)`. No RNG, no data-dependent iteration order, no `_linalg`/`_stats` change, no new numerical primitive. The engine version folds the decimal context, the method version, **and** the normal-primitive version into `config_hash`. |
| **D-IDENTITY** | **Content-addressed, transitively pinned, self-verifying.** `net_of_cost_significance_id` folds the engine version, the request (name, spec version, source net-of-cost id), the source net-of-cost record's `result_hash` (the transitive pin), the `null_mean_return` tested, and the `result_hash` over the computed answer. `research_result_id` aliases `net_of_cost_significance_id`; derived ids are re-emitted by properties, never read from stored state. Domain tag `netcostsig/1`. |
| **D-STORE** | **One write-once record in the existing `ResearchResultStore`; no new store, no migration.** `NetOfCostSignificance` satisfies the `ResearchRecord` Protocol and persists to `research/sha256-<hex>.json`. An idempotent re-write of a byte-identical payload is a no-op; a conflicting payload under the same id raises `FactorConsistencyError` (the existing store contract). |
| **D-PARAMS** | **No per-request numerical parameter.** The single approved methodology has no tunable numeric input; the null mean is the fixed platform constant `NULL_MEAN_RETURN = "0"`, folded into `net_of_cost_significance_id` (as Phase 29 folds `NULL_MEAN_RATIO = "1"`) so a change to it is a distinguishable record. A *declared* benchmark net mean is a disclosed future extension (§10), not this phase. |
| **D-INVARIANTS** | **NS-1..NS-6 are documented both as phase-local invariants here (§7) and as a small additive `data-model.md §12` block** mirroring the WF-/CE-/SC-/MC-/RC-/WS-/MT-/CS-/NC- blocks (they do not weaken existing invariants). |
| **D-VERSION** | This phase releases as **`v0.29.0`** (Phase 31 = v0.28.0). Domain tag `netcostsig/1`; engine-version string `netcostsig-engine/1`; method string `netcostsig-method/1`; normal-primitive string `netcostsig-normal/1`; spec-version string `netcostsig/1`; record-format string `netcostsig-result/1`. The package `__version__` string is unchanged `"0.0.0"` (versioning is by content-addressed ids + the README table, not a semver string). No `pyproject`/packaging change; no new runtime dependency. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; neither changes an identity discipline or weakens an invariant.

- **The record carries a `method_version` field.** The proposal (§6.6) named the stored
  `method_version` on the record but the identity discussion (§6.7) folds it only through
  the engine version. The implementation stores `method_version` (default
  `NETCOSTSIG_METHOD_VERSION`) as a first-class record field, round-tripped through
  `to_dict` / `from_dict`. It is **not** folded into `net_of_cost_significance_id`
  separately — the method version already reaches the id through
  `net_of_cost_significance_engine_version_id` (whose `config_hash` folds it), so folding it
  twice would be redundant; the stored field is an auditable record of the method that
  produced the answer. `from_dict` requires it (fail closed on absence), so a record's
  stored bytes disclose their producing method without changing identity discipline.
  (Mirrors the Phase 27–31 deviation.)
- **The summary type is named `SignificanceSummary`.** The proposal (§6.6) referred to it as
  `NetOfCostSignificanceSummary`; the implementation names the dataclass
  `SignificanceSummary` (as Phase 29's `calsig.result.SignificanceSummary` does — the
  package namespace already disambiguates it). No public top-level export changes: only
  `NetOfCostSignificanceSpecification` and `NetOfCostSignificance` are re-exported from
  `quantforge`.
- **The large-sample normal approximation is the sealed methodology; the finite-sample
  Student-`t` is deferred (★).** As disclosed in the proposal (§6.5, §11), the p-value uses
  `1 − Φ(t)` — the identical `(★)` deferral disclosed by Phase 24 / 29. No new statistical
  primitive is introduced; a finite-sample `t` distribution is a possible later phase.

Resolved ★ decisions of note: capability = one-sample upper-tailed significance test of the
after-cost mean return against the null `0` over one net-of-cost performance; source is
exactly one `NetOfCostPerformance`, consumed by id; output `NetOfCostSignificance`; package
`netcostsig`, domain tag `netcostsig/1`; public names `NetOfCostSignificanceSpecification` /
`NetOfCostSignificance`; `standard_error = σ/√n`, `t = m/se`, `p = 1 − Φ(t)` clamped
(one-sided upper); exact-`Decimal`, reuse `standard_normal_cdf`, no new primitive; ex-post,
not a `Pit*`, boundary carried; gate on `MEASURED` + KNOWN aggregate cells, zero-volatility
UNDEFINED, `NULL_MEAN_RETURN = "0"` folded; identity fold as in §5; v0.29.0; no
`_linalg`/`_stats` change; a sibling package, no prior-phase edit; shared write-once
`ResearchResultStore`.

---

## 2. What was built

New package **`src/quantforge/netcostsig/`** (mirrors the P22/P23/P24/P25/P26/P27/P28/P29
layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `NetCostSigError` → `NetCostSigConfigurationError`, `NetCostSigConsistencyError`. |
| `version.py` | `NetOfCostSignificanceEngineVersion` (folds the pinned decimal context + `netcostsig-method/1` + `netcostsig-normal/1` into `config_hash`); constants `NETCOSTSIG_SPEC_VERSION` / `NETCOSTSIG_ENGINE_VERSION` / `NETCOSTSIG_METHOD_VERSION` / `NETCOSTSIG_NORMAL_VERSION`; `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `model.py` | The closed `SignificanceStatus` (`tested`, `undefined`), `NetCostSigUndefinedReason` (`source_not_measured`, `zero_net_volatility`), `EdgeDirection` (`profitable`, `unprofitable`, `flat`), `StatStatus`, and the UNDEFINED-preserving `SignificanceStat` cell (`known` / `undefined` / `to_dict` / `from_dict`). |
| `spec.py` | `NetOfCostSignificanceSpecification` (declarative request; fail-closed validation of `name` / `source_net_of_cost_id`; `spec_version = "netcostsig/1"`). |
| `compute.py` | The pure exact-`Decimal` procedure: `test_net_of_cost_significance(series, *, null_mean, context) → SignificanceComputation`; `MeasuredNetSeries` (the carried `net_mean` / `net_volatility` / `n_periods`); the `_edge_direction` helper. |
| `result.py` | `NetOfCostSignificance` (`ResearchRecord`; `seal` / `to_dict` / `from_dict`, derived ids, `significance_status` / `source_net_of_cost_id` / `source_result_hash` accessors), `SignificanceSummary`; `NETCOSTSIG_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`, `NULL_MEAN_RETURN = "0"`. |
| `identity.py` | `net_of_cost_significance_result_hash`, `net_of_cost_significance_id`; domain tag `netcostsig/1`. |
| `engine.py` | `NetOfCostSignificanceEngine.evaluate(spec)`. |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `workspace.py` — one lazy `net_of_cost_significance_engine` `@property` (+ private
   `_net_of_cost_significance_engine` cache slot), following the
   `calibration_significance_engine` / `net_of_cost_engine` template (typed `-> object`,
   deferred import of `NetOfCostSignificanceEngine` to avoid the module-load cycle).
2. `src/quantforge/__init__.py` — top-level re-exports of
   `NetOfCostSignificanceSpecification` and `NetOfCostSignificance`, added to the sorted
   `__all__`.

**No edit to** `_linalg`, `_stats`, `netcost`, `stability`, `calibration`, `campaign`,
`walkforward`, `comparison`, `multiplicity`, `mintrl`, `campaignmult`, `optimization`,
`factorrisk`, `factorportfolio`, `analytics`, `backtest`, or any other prior-phase
identity/vocabulary. Phase 32 **reuses** `quantforge._stats.normal.standard_normal_cdf`
verbatim (the same primitive Phase 24 and Phase 29 use) and adds no primitive to `_stats`,
so `_stats/normal.py` is untouched.

---

## 3. Data flow

```
NetOfCostSignificanceSpecification { name, source_net_of_cost_id, spec_version }
        │
        ▼  NetOfCostSignificanceEngine.evaluate(spec)
type-check spec is a NetOfCostSignificanceSpecification                       — NetCostSigConfigurationError
        │
        ▼
resolve the ONE source net-of-cost record by id                              — fail closed (NS-1)
   store.read_as(id, NetOfCostPerformance.from_dict)
   present? decodes as a NetOfCostPerformance? research_result_id == id?         — else NetCostSigConsistencyError
        │
        ▼
gate the source into a MeasuredNetSeries or None                             — NS-2
   net_status is MEASURED AND net_mean / net_volatility cells KNOWN
      → MeasuredNetSeries(m, σ, n)   (parse the two decimal strings once; n = coverage.n_periods)
   else → None
        │
        ▼  under localcontext(prec 34, ROUND_HALF_EVEN):
   test_net_of_cost_significance(series, null_mean=Decimal("0"), context)     — NS-3/NS-5
     series is None            → all UNDEFINED SOURCE_NOT_MEASURED (edge None, n=0)
     net_volatility == 0       → se KNOWN "0"; t / p UNDEFINED ZERO_NET_VOLATILITY; mean + edge KNOWN
     else                      → se = σ/√n; t = (m − 0)/se; p = 1 − Φ(t) clamped [0, 1]; TESTED
        │
        ▼
SignificanceSummary { net_mean, null_mean_return, n_periods,
   standard_error, t_statistic, p_value, significance_status, edge_direction, status_reason }
        │
        ▼
NetOfCostSignificance.seal(...)  (result_hash folds the answer;
   boundary_kind carried from source; source_ref = (source id, source result_hash))  — NS-1/NS-6
        │
        ▼
ResearchResultStore.write(significance)   (write-once, idempotent)           — D-STORE
        │
        ▼
store.read_as(id, NetOfCostSignificance.from_dict)   (byte-identical typed round-trip)
```

---

## 4. Public API

```python
from quantforge import (
    Workspace,
    NetOfCostSignificanceSpecification,
    NetOfCostSignificance,
)

ws = Workspace.open(root)

spec = NetOfCostSignificanceSpecification(
    name="net-of-cost:significance",
    source_net_of_cost_id=net_of_cost_id,  # exactly one sealed NetOfCostPerformance id
)

significance = ws.net_of_cost_significance_engine.evaluate(spec)  # sealed, write-once

significance.significance_status  # TESTED / UNDEFINED (roll-up)
significance.summary  # SignificanceSummary: statistics + edge direction + status
significance.source_net_of_cost_id  # the pinned source net-of-cost id
significance.source_result_hash  # the transitive pin
significance.research_result_id  # == significance.net_of_cost_significance_id

again = ws.research_result_store.read_as(
    significance.research_result_id, NetOfCostSignificance.from_dict
)
```

`NetOfCostSignificanceEngine` is reached only through
`Workspace.net_of_cost_significance_engine` (lazy, cached, `-> object`).
`evaluate(spec) -> NetOfCostSignificance` is the single entry point.

`NetOfCostSignificanceSpecification` (frozen slots): `name`, `source_net_of_cost_id`,
`spec_version = "netcostsig/1"`. Construction-time validation (fail closed): non-empty
`name` / `spec_version` / `source_net_of_cost_id`. There is no numerical request parameter
(the null mean is the platform constant `NULL_MEAN_RETURN`).

`SignificanceSummary` carries the carried `net_mean` cell, the `null_mean_return` string
(`"0"`), the `n_periods` count, three UNDEFINED-preserving `SignificanceStat` cells
(`standard_error`, `t_statistic`, `p_value`), the descriptive `edge_direction` (or `None`),
the roll-up `significance_status`, and an optional `status_reason`.

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `net_of_cost_significance_engine_version_id = sha256(code_version "netcostsig-engine/1",
  config_hash)` where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=
  netcostsig-method/1\x00normal=netcostsig-normal/1")`. Folding the method and normal
  versions makes the record's identity change if the source-gating, the one-sample
  statistics, or the reused CDF primitive changes.
- `net_of_cost_significance_result_hash = sha256(canonical JSON over the ordered
  computed-output cells: a single `{block:"summary", ...}` descriptor holding the carried
  net mean, null mean, period count, standard error, `t`, `p`, status, edge direction, and
  reason)`. Sensitive to every carried and computed statistic.
- `net_of_cost_significance_id = sha256`, NUL-joined, in order: `netcostsig/1`,
  `net_of_cost_significance_engine_version_id`, `name`, `spec_version`,
  `source_net_of_cost_id`, `source_result_hash` (the transitive pin, NS-1),
  `null_mean_return`, and `net_of_cost_significance_result_hash`.
- `research_result_id` aliases `net_of_cost_significance_id`. Derived ids are re-emitted by
  properties, never read from stored state — a tampered stored id is ignored and
  `from_dict(to_dict(r))` re-emits identical bytes. The record-format version and the stored
  `method_version` are **not** folded (a container / audit concern; the method reaches the
  id through the engine version).

---

## 6. Determinism / Decimal rules

- All significance arithmetic runs under an explicit `localcontext` (precision 34,
  `ROUND_HALF_EVEN`): the standard error `σ/√n` (a `Decimal.sqrt` of the integer period
  count), the `t` statistic `(m − 0)/se`, the one-sided `p = 1 − Φ(t)`, and the `[0, 1]`
  clamp. `Φ` is the reused deterministic `standard_normal_cdf` (an erf series — bounded,
  terminating; **not** a convergence-tolerance loop). **No float anywhere**, no RNG, no
  wall-clock, no `id()`, no data-dependent iteration order.
- Values are canonicalized as `str(+value)` inside the pinned context.
- Same source net-of-cost record + same request → same `net_of_cost_significance_id` and
  byte-identical payload on any machine. A repeated `evaluate` is a byte-identical no-op
  (store idempotence). Two engines over the same immutable sidecar agree. Because Phase 32
  folds the source net-of-cost record's `result_hash`, any upstream change changes this
  record's id while a byte-identical recompute reproduces identical bytes (the Phase
  22/23/29/31 audit standard, one layer up).

---

## 7. Invariants (NS-1..NS-6)

Additive to `data-model.md §12`; these do not weaken existing invariants.

- **NS-1 — Reference verification and transitive pinning.** The single
  `source_net_of_cost_id` is resolved from the shared sidecar via
  `store.read_as(id, NetOfCostPerformance.from_dict)`, re-verified
  (`research_result_id == id`, and that it decodes as a `NetOfCostPerformance`), and its
  `result_hash` folded into `net_of_cost_significance_id`; through the source's own id this
  pins the stability record / walk-forward / optimization / risk-model / factor chain
  beneath it (NC-1). Any missing, non-decoding, or id-mismatched reference fails closed with
  `NetCostSigConsistencyError`; the source is never copied, only pinned. *(The NC-1 / CS-1
  discipline, one layer up.)*
- **NS-2 — Source-status gating: only a `MEASURED` source is tested.** A source whose
  `net_status` is not `MEASURED`, or whose sealed `net_mean` / `net_volatility` cell is not
  KNOWN, seals a first-class UNDEFINED record (`SOURCE_NOT_MEASURED`) with every statistic
  UNDEFINED, `n_periods = 0`, and `edge_direction = None` — never imputed, never coerced to
  a metric. The record still seals (a data condition is never an exception).
- **NS-3 — UNDEFINED-preserving, no divide-by-zero.** When the sealed `net_volatility` is
  `0` the `standard_error` is a KNOWN `0`, but `t_statistic` / `p_value` are first-class
  UNDEFINED (`ZERO_NET_VOLATILITY`) — never a division by a zero denominator; `net_mean` and
  `edge_direction` stay KNOWN. *(The NC-3 / CS-3 posture, adapted to a one-sample net test.)*
- **NS-4 — Sealed statistics are consumed verbatim, never recomputed.** The source's
  already-sealed `net_mean` / `net_volatility` cells and `coverage.n_periods` are read (the
  two decimal strings parsed once into `Decimal`); the engine never recomputes them from the
  per-window cost/turnover cells, never re-derives a moment, and never reads the net return
  series (Phase 31 does not seal it period-by-period). The sealed answer is authoritative.
  *(The NC-4 / CS-4 posture of operating over already-sealed strings, one layer up.)*
- **NS-5 — Single deterministic large-sample one-sided normal test.** One exact-`Decimal`
  method: `standard_error = σ/√n`, `t_statistic = (m − 0)/standard_error`,
  `p_value = 1 − Φ(t)` clamped to `[0, 1]` — the same population-moment standard-error
  convention as Phase 24 (`√(variance/n)` with `σ = √variance`) and Phase 29 (`s/√K`) — all
  under one pinned decimal context (prec 34, `ROUND_HALF_EVEN`) folded into the engine
  identity, with `Φ` the deterministic exact-`Decimal` `standard_normal_cdf` reused verbatim
  from `quantforge/_stats/normal.py` (shared with Phase 24 / 29) and `Decimal.sqrt` the only
  other transcendental. The test is **one-sided upper** (directional profitability); the
  null mean `0` (`NULL_MEAN_RETURN`) is folded into the id. The finite-sample Student-`t`
  distribution is deferred (★), the identical deferral Phase 24 / 29 disclose. No RNG, no
  float, no data-dependent iteration, no `_linalg`/`_stats` change, no new primitive. *(The
  CS-5 discipline, reusing exact `Decimal` arithmetic.)*
- **NS-6 — A net-of-cost significance is not a PIT value and not a `BacktestResult`.** A
  significance test over an already-ex-post net-of-cost figure is itself ex-post:
  `NetOfCostSignificance` is **not** a `Pit*` type, exposes no as-of accessor, is a distinct
  record type, simulates no fills, and opens no new corpus / availability surface.
  `boundary_kind = "pit"` — carried unchanged from the source — documents only that the
  *underlying returns* were PIT walks. *(The NC-6 / CS-6 discipline, one layer up.)*

---

## 8. Failure / UNDEFINED semantics

**Raised** — `NetCostSigConfigurationError`: a non-`NetOfCostSignificanceSpecification`
argument to the engine; a malformed spec (empty `name` / `spec_version` /
`source_net_of_cost_id`). `NetCostSigConsistencyError` (NS-1): the `source_net_of_cost_id`
absent from the sidecar; a payload that does not decode as a `NetOfCostPerformance`; a
resolved-id disagreement.

**Recorded as first-class UNDEFINED** (NS-2/NS-3, never raised): a non-`MEASURED` source
(or one with a non-KNOWN aggregate cell) seals every statistic UNDEFINED
(`SOURCE_NOT_MEASURED`); a zero-volatility source seals `t_statistic` / `p_value` UNDEFINED
(`ZERO_NET_VOLATILITY`) with `standard_error` a KNOWN `0` and the mean / edge direction
KNOWN. The record always seals.

**Store contract:** a byte-identical re-write is an idempotent no-op; a differing payload
under the same significance id raises `FactorConsistencyError` (the existing write-once
guard).

---

## 9. Testing

`tests/netcostsig/` (offline, synthetic). Because the engine reads **only** the source
`NetOfCostPerformance` via `store.read_as`, the builders (`tests/netcostsig/builders.py`)
construct synthetic `NetOfCostPerformance` records directly — sealing hand-chosen
`NetOfCostSummary` / `NetOfCostCoverage` cells (MEASURED with KNOWN net mean / volatility, a
zero-volatility source, a non-MEASURED source, or a MEASURED source with a non-KNOWN mean)
via `NetOfCostPerformance.seal` and writing them to the store — rather than running the full
factor → optimization → walk-forward → stability → net-of-cost chain.

Suites (**52 tests** across the package):
- `test_spec` — the default spec version, the canonical `to_dict`, fail-closed rejection of
  empty fields, frozenness.
- `test_model` — the KNOWN/UNDEFINED `SignificanceStat` construction guards, `to_dict` /
  `from_dict` round-trip, fail-closed decode of corrupt cells (unknown status / reason), and
  the closed status/reason/direction vocabularies.
- `test_version` — the engine-version fold of decimal context + method + reused-normal
  versions, `sha256:`-prefixed determinism, per-input id sensitivity.
- `test_compute` — the pure procedure over synthetic `MeasuredNetSeries`: the exact
  `standard_error` / `t` / `p` against a hand-computed golden (`m=0.01`, `σ=0.05`, `n=100`
  → `se=0.005`, `t=2`, `p=1−Φ(2)`), the Sharpe identity `t = (m/σ)·√n`, the larger-`n`
  smaller-`p` power relation, the `PROFITABLE`/`UNPROFITABLE`/`FLAT` edge direction, the
  `ZERO_NET_VOLATILITY` UNDEFINED cells (mean + direction still KNOWN), the absent-series
  all-UNDEFINED `SOURCE_NOT_MEASURED` case, the `p ∈ [0, 1]` clamp, and repeated computation
  identical. (Imported as `run_significance` to avoid pytest collecting the `test_`-prefixed
  procedure name.)
- `test_identity` — `sha256:`-prefixed, deterministic, each-fold-changes-the-id (including
  the transitive `source_result_hash` pin and the `null_mean_return` fold), result-hash
  sensitive to a single cell, and the domain separation (`id ≠ result_hash`).
- `test_result` — seal folds the answer, derived id aliases `research_result_id`,
  byte-identical round-trip (tested and undefined summaries), id re-derived not read from
  state (tampered stored id ignored), a `t` change changes the hash and the id, and that the
  record is not a `Pit*` type and exposes no `as_of`.
- `test_public_api` — public exports and the lazy/cached
  `Workspace.net_of_cost_significance_engine`.
- `test_engine` — happy path (a MEASURED source tested, statistics match a fixture, source
  reference pinned), the `SOURCE_NOT_MEASURED` gate (non-MEASURED and non-KNOWN-mean
  sources), the `ZERO_NET_VOLATILITY` UNDEFINED cells, boundary carried and the record not
  PIT; recompute byte-identical and idempotent; every fail-closed guard (absent source,
  non-`NetOfCostPerformance` record, id-mismatch via a path-swapped payload, non-spec
  argument, and a tampered stored payload → `FactorConsistencyError`).

**Gate (all green): `ruff check .` / `ruff format --check .` / `mypy src tests` /
`pytest -q` / `pytest -q -p no:randomly`; zero new runtime dependencies; every prior-phase
id preserved (no prior source touched beyond the additive `workspace.py` / `__init__.py`
re-exports).**
