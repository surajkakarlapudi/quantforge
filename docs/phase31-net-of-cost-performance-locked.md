# Phase 31 - Net-of-Cost Walk-Forward Performance (locked)

> Status: **locked / normative**. This document records what was **actually built** for
> Phase 31, validated against the repository's invariants. Where the implementation
> departs from `docs/phase31-net-of-cost-performance-proposal.md`, the deviation is
> disclosed here (§7). Target version **v0.28.0** (not yet committed / tagged / released).

## 0. One-sentence statement

**Charge a declared linear transaction cost against one sealed `WalkForwardStability`
and report net-of-cost performance**: read the per-REALIZED-window one-way
`turnover_from_prev` from the stability record and, transitively, the chained gross
out-of-sample (OOS) return series and its sealed gross summary from the one
`WalkForwardEvaluation` the stability record pins; subtract `cost_rate · turnover_w` at
each realized window's first OOS period; summarize the net series with the *reused*
Phase 19 series summary; and seal the net moments, the cost drag, and the parameter-free
break-even cost rate `Σ gross / Σ turnover`.

## 1. What was built

New package `src/quantforge/netcost/`, a pure consumer strictly **above** Phase 27
(`stability`). It adds no new statistical primitive: it reuses
`quantforge.factorportfolio.stats.series_summary` (the Phase 19 population-volatility /
annualized-Sharpe convention Phase 22 also used for the gross summary) **verbatim**, and
the only added arithmetic is exact-`Decimal` `cost_rate · turnover`, the per-period
subtraction, the aggregate drags, and one break-even division.

```
version.py    NetOfCostEngineVersion + version strings; folds the pinned decimal context,
              Phase 31's own NETCOST_METHOD_VERSION, AND the reused
              NETCOST_SUMMARY_VERSION = FACTORPORTFOLIO_FORMULA_VERSION (transitive pin of
              the reused Phase 19 summary that produces both net and gross Sharpe).
errors.py     NetOfCostError / *ConfigurationError / *ConsistencyError.
model.py      NetCostStatus / NetCostExcludedReason / NetCostUndefinedReason / StatStatus /
              NetCostStat (the UNDEFINED-preserving cell). Reason strings for the three
              series-moment cases are identical to FactorPortfolioUndefinedReason;
              WINDOW_UNDEFINED matches Phase 27's StabilityExcludedReason;
              NO_PRIOR_REALIZED_WINDOW matches Phase 27's StabilityUndefinedReason.
spec.py       NetOfCostSpecification(name, source_stability_id, cost_rate, spec_version);
              cost_rate canonicalized (non-negative finite decimal string) at construction.
identity.py   net_of_cost_id / net_of_cost_result_hash; domain "netcost/1".
compute.py    RealizedWindowInput / WindowNetCost / NetCostComputation +
              compute_net_of_cost (the pure accounting: cost placement, net summary,
              drags, break-even).
result.py     NetOfCostPerformance + WindowNetCostCell / ExcludedWindow /
              NetOfCostSummary / NetOfCostCoverage.
engine.py     NetOfCostEngine.evaluate(spec).
__init__.py   public re-exports (sorted __all__).
```

Wired additively: `Workspace.net_of_cost_engine` (lazy `@property`, deferred import,
private cache slot) and top-level `quantforge.NetOfCostSpecification` /
`quantforge.NetOfCostPerformance` re-exports. **No new store** (reuses the shared
`ResearchResultStore`), **no new ingestion, no new PIT surface, no runtime dependency, no
`_linalg` / `_stats` expansion.**

## 2. Data flow (engine `evaluate`) - as built

1. **Reject** a non-`NetOfCostSpecification` argument with
   `NetOfCostConfigurationError`.
2. **Resolve the stability record** (`source_stability_id`) via
   `store.read_as(id, WalkForwardStability.from_dict)`; then **resolve the walk-forward
   it pins** and verify the walk's `research_result_id` **and** `result_hash` equal the
   values the stability record pinned. A missing id, an undecodable payload, a wrong-type
   record, or any id / `result_hash` mismatch raises `NetOfCostConsistencyError` (fail
   closed, NC-1). This makes the net-of-cost id transitively sensitive to the stability
   record, the gross walk beneath it, and the whole optimization / risk-model / factor
   chain below.
3. **Align (the load-bearing step, NC-2/NC-4).** Gross performance is a *per-period*
   chained series (the walk's `oos_returns`); turnover is a *per-window* one-way quantity
   (the stability record's `turnover_from_prev`). They are **not** zippable. The engine
   verifies the stability record's REALIZED window indices equal the walk's REALIZED
   indices, its excluded windows equal the walk's UNDEFINED windows, and the
   concatenation of the per-window OOS sub-series equals the walk's chained gross series
   - any axis mismatch is a `NetOfCostConsistencyError`. It then builds one
   `RealizedWindowInput(index, oos_returns, turnover)` per realized window via
   `zip(..., strict=True)`.
4. **Compute** (`compute_net_of_cost`, under the version's `localcontext`): for each
   realized window with a KNOWN turnover, charge `cost = cost_rate · turnover_w` at the
   window's **first** OOS period only; a window with UNDEFINED turnover
   (`NO_PRIOR_REALIZED_WINDOW`) bears **zero** cost and its gross periods pass through
   unchanged (NC-3, no fabricated entry cost). Summarize the resulting net series with
   the reused Phase 19 summary; the gross moments are read **verbatim** from the source
   summary (NC-4). Cost drag = `gross_mean − net_mean`, Sharpe drag =
   `gross_sharpe − net_sharpe` (UNDEFINED-propagating). Break-even =
   `Σ gross / Σ turnover` when total turnover is strictly positive, else UNDEFINED
   `DEGENERATE_NO_TURNOVER` (never a divide-by-zero, NC-5).
5. **Seal + persist** a `NetOfCostPerformance` (its `result_hash` folds the answer; its
   id folds the declared `cost_rate` and transitively pins `source.result_hash`),
   write-once to the shared sidecar. An identical re-build is a byte-identical no-op.

## 3. Identity (§10, §11) - as built

```
net_of_cost_result_hash = sha256( canonical JSON over ordered output cells:
    the coverage descriptor, then each per-window net-cost cell in source window order
    (index, n_periods, gross_return, turnover, cost, net_return), then each excluded
    cell (index, reason), then the aggregate net-of-cost summary block )
net_of_cost_id = sha256( domain "netcost/1", net_of_cost_engine_version_id, name,
    spec_version, source_stability_id, source_result_hash, cost_rate,
    net_of_cost_result_hash )
```

The engine version folds the pinned decimal context (prec 34, `ROUND_HALF_EVEN`),
Phase 31's own `NETCOST_METHOD_VERSION`, and the reused
`NETCOST_SUMMARY_VERSION = FACTORPORTFOLIO_FORMULA_VERSION` - so a change to the shared
Phase 19 summary changes this record's identity (an honest transitive pin).

**`cost_rate` is folded into the id, not into the `result_hash`.** The result hash is the
seal over the *computed answer*; the declared cost rate is a request parameter. So two
requests differing only in `cost_rate` produce **different ids** but, at the same computed
answer, are otherwise distinguished only by the request fold - and because the answer
itself depends on the cost rate, the result hashes differ too whenever the cost changes
any cell. The dedicated test `test_cost_rate_changes_id_but_not_result_hash` pins the
degenerate case (identical answer cells across a spec-only `cost_rate` swap ⇒ equal
`result_hash`, distinct id). `research_result_id` aliases `net_of_cost_id`.

## 4. Determinism

Exact `Decimal` only - `cost_rate · turnover`, the per-period subtraction, the aggregate
drags, and one break-even division - plus the reused Phase 19 summary, all under an
explicit prec-34 `ROUND_HALF_EVEN` `localcontext`. The only elementary transcendental is
the `Decimal.sqrt` **inside** the reused summary (the net / gross Sharpe). No float, no
RNG, no wall-clock, no UUID, no iteration-order dependence: window order is the sealed
source order. The engine holds no mutable per-run state, so two builds of the same spec
over the same immutable sidecar are byte-identical. Evidenced by the idempotent-rebuild
and byte-identical round-trip tests, and by the full suite passing in both pytest
orderings.

## 5. Invariants (NC-1..NC-6)

- **NC-1 Reference & transitive pin.** Consumes exactly one sealed
  `WalkForwardStability` and, transitively, the one `WalkForwardEvaluation` it pins, each
  by `(id, result_hash)`; a missing / drifted / wrong-type / id-mismatched reference (at
  either level) fails closed with `NetOfCostConsistencyError`.
- **NC-2 Per-period cost placement.** The one-time rebalancing cost `cost_rate ·
  turnover_w` is borne at the realized window's **first** OOS period, because gross is a
  per-period chained series and turnover is per-window (they are not zippable). The
  engine verifies the two axes agree (indices + reconstructed chained series) before
  charging.
- **NC-3 Declared cost, no fabrication.** `cost_rate` is a **declared** non-negative
  finite decimal, canonicalized and folded into the id; never inferred, defaulted, or
  retrieved from a corpus. A realized window with no adjacent realized predecessor
  (`NO_PRIOR_REALIZED_WINDOW`) bears **zero** cost - **no** fabricated entry cost (a
  documented deviation from the proposal's `entry_cost_convention`, §7).
- **NC-4 Verbatim gross + reused summary.** The gross moments are read **verbatim** from
  the source walk's sealed summary (no re-derivation); the net series is summarized with
  the *identical* reused Phase 19 `series_summary` the walk used for gross, so the net
  Sharpe is directly comparable and, at `cost_rate = 0`, the net moments equal the gross
  moments byte-for-byte (the zero-cost identity). No new statistical primitive.
- **NC-5 Fail-closed degeneracy.** A never-trading strategy seals an UNDEFINED
  `DEGENERATE_NO_TURNOVER` break-even (never a divide-by-zero); a net series with zero
  population dispersion seals an UNDEFINED `net_sharpe` (`ZERO_RETURN_VARIANCE`) while
  keeping the net mean and (zero) net volatility KNOWN; drags against a missing moment
  are themselves UNDEFINED, never imputed. Excluded source windows are carried through
  first-class (`WINDOW_UNDEFINED`), never dropped.
- **NC-6 Ex-post, not PIT.** The net-of-cost verdict is an ex-post / counterfactual
  statistic; the record is **not** a `Pit*` type and exposes **no** `as_of` accessor.
  `boundary_kind = "pit"` documents the input side only (the underlying returns were PIT
  walks) and is carried through from the source unchanged. No new store, dependency, or
  PIT surface.

## 6. Failure semantics

- **Data condition** (a window with no prior realized predecessor; a never-trading
  strategy; a zero-dispersion net series; an excluded source window) => recorded UNDEFINED
  / excluded cell, never raised; the record seals honestly with its `net_status`.
- **Configuration defect** (empty name / spec_version / source id; a negative,
  non-finite, or non-decimal `cost_rate`; a non-spec argument) =>
  `NetOfCostConfigurationError`.
- **Consistency defect** (stability record or its pinned walk absent / undecodable /
  wrong type / id or `result_hash` mismatch; realized-index, exclusion, or chained-series
  axis mismatch) => `NetOfCostConsistencyError`.

## 7. Deviations from the proposal

- **No `entry_cost_convention` (no fabricated entry cost), NC-3.** The proposal's §9.5
  proposed charging an entry cost `c · gross_leverage` at the first / post-gap realized
  window by default. The built implementation charges **zero** cost there: with no
  adjacent realized predecessor there is no sealed `turnover_from_prev` to charge, and
  fabricating one from `gross_leverage` would mix a per-window level into a per-transition
  cost. The window's turnover / cost cells are UNDEFINED `NO_PRIOR_REALIZED_WINDOW` and
  its gross returns pass through. No `entry_cost_convention` spec flag exists.
- **`ZERO_RETURN_VARIANCE` reused instead of `DEGENERATE_SHARPE_ESTIMATOR`.** The
  proposal §9.11 labelled the zero-net-dispersion case `DEGENERATE_SHARPE_ESTIMATOR`. The
  built code reuses the Phase 19 `ZERO_RETURN_VARIANCE` reason string verbatim (parity
  with the reused summary's own UNDEFINED cells, so the mapping is by value and never
  re-interpreted).
- **Break-even is always sealed and parameter-free (no `break_even` flag).** The proposal
  gated the break-even rate behind a request flag. The built record always seals
  `break_even_cost_rate` as a first-class diagnostic (KNOWN, or UNDEFINED
  `DEGENERATE_NO_TURNOVER`); it needs no request parameter (it is a property of the gross
  edge against the turnover, independent of `cost_rate`).
- **No `annualize` flag.** The proposal proposed an `annualize` toggle. The built record
  inherits the walk's `periods_per_year` / `risk_free_per_period` conventions verbatim
  and applies the reused summary's fixed annualized-Sharpe convention (so net and gross
  are comparable); there is no separate flag.
- **Single declared cost rate.** The spec carries exactly one `cost_rate` (a cost *sweep*
  is expressed as multiple sealed records, each its own content-addressed id), rather than
  a vector of rates in one record.
- **Verbatim gross consumption made explicit (Approach B).** The gross moments are read
  verbatim from the walk's sealed summary rather than recomputed from the chained series;
  only the net series is (re)summarized. This is what guarantees the exact zero-cost
  identity.

No other deviations. All other behavior matches the proposal.

## 8. Tests

`tests/netcost/` (83 tests): `test_spec` (cost_rate canonicalization, zero permitted,
negative / non-finite / non-decimal refused, empty-field refusal, frozen), `test_model`
(cell construction invariants, round-trip, reason vocabulary), `test_version`
(transitive-pin binding, per-input id sensitivity, decimal-context fold), `test_identity`
(deterministic hash + id, per-fold sensitivity, cost_rate changes id, domain
separation), `test_compute` (golden per-window cells, golden aggregates, break-even =
Σgross/Σturnover, zero-cost identity, net-mean monotone-decreasing in cost,
degenerate-no-turnover, zero-net-variance undefines Sharpe only, multi-period window
charges only the first period), `test_result` (byte-identical round-trip, id re-derived
not stored, source_ref accessors, hash sensitivity to a window cell / the summary,
cost_rate changes id but not result_hash, undefined-summary round-trip, from_dict fails
closed), `test_engine` (golden end-to-end, persisted-and-readable, idempotent no-op,
zero-cost identity end-to-end, cost_rate changes id, excluded window carried,
degenerate-no-turnover seals undefined break-even, zero-net-variance seals undefined
Sharpe, workspace property cached, and fail-closed on non-spec / missing / wrong-type
source / differing-payload-same-id), `test_public_api` (top-level + package re-exports).
Full suite green in both pytest orderings (2173 passed).
