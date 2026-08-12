# Phase 19 — Characteristic-Sorted Long/Short Factor-Portfolio Construction (Factor Return Series) — PROPOSAL

> **Status:** Proposal only. No implementation, no source files, no tests, no
> doc/README/ARCHITECTURE/index/data-model edits, no locked spec, no
> commit/tag/release. This document is the **sole deliverable** of this step.
> Nothing here is approved until the maintainer explicitly approves it.

> **One-line thesis:** Phase 19 adds a deterministic, content-addressed
> **characteristic-sorted factor-portfolio construction** layer: at each scheduled
> rebalance date `T`, sort a Phase 9 universe into `Q` quantiles by a
> **PIT-eligible-at-`T`** signal, form a **long** (top quantile) and **short**
> (bottom quantile) leg, and realize each leg's **forward** return over a
> `"<n>d"` horizon; the factor's per-period return is the **long-minus-short**
> spread. Chaining these per-rebalance spreads yields a sealed **factor return
> series** (`FactorPortfolio`) with per-period leg holdings, coverage, and a
> summary (cumulative/mean/volatility/annualized-Sharpe/t-stat/hit-rate). It
> composes Phases 9/10/11 only (exactly as Phases 16 and 18 do), consumes **no**
> `BacktestResult`, **modifies no prior phase**, and seals a `ResearchRecord` to
> the existing sidecar. It is the first member of a **new capability class —
> portfolio construction** — distinct from the diagnostic (16), regression
> (17/18), and general-simulation (12) families, and it is the artifact a future
> factor-risk-model / factor-attribution extension will consume.

> Governing prior specs (source of truth): [data-model.md](data-model.md)
> (invariants 1–30, §KS, §11 identity discipline; SD-1..4, XS-1..4),
> [phase12-backtesting-proposal.md](phase12-backtesting-proposal.md) (BT-1..4),
> [phase16-signal-diagnostics-locked.md](phase16-signal-diagnostics-locked.md),
> [phase18-cross-sectional-regression-locked.md](phase18-cross-sectional-regression-locked.md),
> [ARCHITECTURE.md](../ARCHITECTURE.md) (10 Engineering Principles).

---

## 1. Selected capability

**Characteristic-sorted long/short factor-portfolio construction (factor return
series estimation).**

Given a declarative `FactorPortfolioSpecification` — one signal
`(metric_key, MetricPeriod)`, a Phase 9 `UniverseSpecification`, a Phase 12
`RebalanceSchedule` of evaluation `as_of` instants, a `"<n>d"` forward horizon, a
quantile count `Q`, a leg-weighting scheme, and both corpus pins — the
`FactorPortfolioEngine.construct(...)`:

1. re-verifies **both** corpora (fundamentals `dataset_version_id` **and** market
   `market_dataset_version_id`) and fails closed on any mismatch or non-unique
   normalizer (P19-1);
2. at each scheduled `T`, rebuilds membership **PIT as-of `T`** (Phase 9
   `build_as_of`, survivorship-free);
3. reads the signal cross-section as a **PIT-eligible-at-`T`** `PitPanel` via
   Phase 10 `panel_across(..., as_of=T)` (P19-3), keeping KNOWN cells only;
4. pairs each member with its realized **forward** return over `[T, T+h]` trading
   days through the Phase 11 PIT-gated adjusted view (the Phase 16/18
   forward-return machinery, reused verbatim); a member lacking the signal at `T`
   or a computable forward return is **excluded and recorded in coverage, never
   imputed** (P19-4);
5. sorts the surviving members into `Q` quantile buckets by the PIT signal (the
   Phase 16 `quantile_buckets` rule, reused verbatim), forms the **long** leg
   (top bucket) and **short** leg (bottom bucket), equal-weights within each leg,
   and computes the per-period factor return
   `f_T = mean(forward returns of long leg) − mean(forward returns of short leg)`
   (dollar-neutral, gross), also recording each leg's own mean return and
   membership;
6. aggregates the `M` valid per-period returns into a **factor return series** and
   a summary: cumulative (compounded) factor return, mean period return,
   population volatility, annualized Sharpe, the mean's t-statistic
   (`mean / (popStd/√M)`), and hit rate — every undefinable cell a first-class
   `UNDEFINED` value with a reason;
7. seals a content-addressed `FactorPortfolio` `ResearchRecord` write-once to the
   shared Phase 8 sidecar.

The factor return series is **forward-looking, ex-post — not a PIT value** (the
SD-2 / XS-2 analog, P19-2): it is not a `Pit*` type and exposes no as-of
accessor; `boundary_kind = "pit"` documents only that the *signal* side was
PIT-eligible.

**Proposed package name:** `factorportfolio` (see decision D-NAME for
alternatives). Result type `FactorPortfolio`; spec
`FactorPortfolioSpecification`; engine `FactorPortfolioEngine`; entry
`construct(spec) -> FactorPortfolio`.

---

## 2. Why this, and why Phase 19

### 2.1 The gap

The research surface now contains: signal *diagnostics* (Phase 16 IC, Phase 18
Fama–MacBeth premia — "does this characteristic predict / is it priced?"), a
general *long-only* strategy *simulator* (Phase 12), and *ex-post analysis* of
completed simulations (Phase 13 comparison, 14 reporting, 15 risk/benchmark
analytics, 17 attribution). The 2×2 regression/diagnostic matrix is **complete**:

| Regression axis \ predictor count | Univariate | Multivariate |
| --- | --- | --- |
| **Time-series** (portfolio return over time) | Phase 15 single-factor α/β | Phase 17 attribution |
| **Cross-sectional** (returns across members at each date) | Phase 16 IC | Phase 18 Fama–MacBeth |

What the system **cannot** produce is the single most fundamental object in
empirical asset pricing: a **factor return series** — the realized return stream
of a long/short characteristic-sorted portfolio (the SMB/HML/momentum
construction method). Phase 12 is structurally incapable of it: its strategy
vocabulary is a *closed* `signal → rank → select → weight` with `select` ∈
{`top_n:<k>`} and `weight` ∈ {`equal`}, **long-only** (verified in
`backtest/spec.py`: `_SELECT_TOP_N`, `_WEIGHT_EQUAL`; `engine.py:_target_weights`
"equal-weight the selected names … long-only, v1"). There is no way to express
a short leg, a dollar-neutral spread, or a quantile-spread portfolio anywhere in
the codebase.

### 2.2 Why it belongs specifically in Phase 19

- **It opens a genuinely new capability class.** Phases 15–18 filled the four
  cells of the regression/diagnostic matrix. Phase 19 does not add a fifth
  regression variant (that would be a refinement — see rejected Alt C/D); it
  introduces **portfolio construction**, a distinct family whose output is a
  *tradable factor artifact*, not a statistic about one.
- **Its prerequisites are exactly Phases 9/10/11 + the Phase 16/18
  forward-return/quantile machinery — all of which now exist.** It reuses the
  PIT universe build, the `panel_across` PIT signal read, the PIT-gated adjusted
  forward return, and the `quantile_buckets` assignment verbatim. Nothing is
  missing; it is not premature.
- **It was deliberately deferred until now.** Phase 16 §3 named factor-portfolio
  construction as the missing prerequisite for "real" attribution and explicitly
  seeded its quantile-spread machinery "as the seed a future factor-portfolio /
  attribution phase can build on." Phase 18's proposal listed "long/short
  factor-portfolio construction" as Candidate B and deferred it — but *only*
  because the framing there was "modify Phase 12." This proposal adopts the
  **sibling** realization (D-SCOPE, D-INPUT), which delivers the same capability
  with **zero** prior-phase identity churn, honoring the six-phase pure-consumer
  discipline. The capability is right; the sibling realization is what makes it
  right *now*.
- **It is the README's literal "Next" row** ("Long/short factor-portfolio
  construction / richer execution & cost models"), backed by repository evidence,
  not memory.

### 2.3 Why it was **not** Phases 15/16/17/18

- **Not 15/16:** those are *diagnostic/analytic measures* (correlation, α/β).
  Constructing a portfolio and realizing its return *series* is a different act;
  it necessarily comes *after* Phase 16, because it depends on the very
  forward-return + quantile machinery Phase 16 introduced. Phase 16 deliberately
  stopped at a single top-minus-bottom *scalar per date* to avoid smuggling
  portfolio construction into a diagnostic layer (its own §3 rationale).
- **Not 17/18:** those *run regressions*. A factor return series is an *input*
  they would like to have, not a regression; building it is orthogonal to running
  one. Phase 19 sits alongside 17/18 and, going forward, feeds them.

### 2.4 What Phase 19 unlocks (future phases)

- A **factor-risk-model / factor-covariance** phase (needs *multiple* sealed
  factor return series — which do not exist until Phase 19 builds them; this is
  precisely the "prerequisite missing → reject as premature" case for that
  capability today).
- A future **Phase 17 extension** that accepts a `FactorPortfolio` return series
  as a legitimate factor (real Fama–French-style factors, replacing the current
  constraint that a Phase 17 factor be a long-only `top_n` `BacktestResult`).
- **Holdings-based exposure analytics** (Phase 18 Candidate E), which is
  premature *until* a long/short portfolio layer motivates it — Phase 19 removes
  that blocker.
- Multi-signal **composite / orthogonalized factors**, **value/rank-weighted**
  legs, and **transaction-cost-aware net** factor returns (all explicitly out of
  scope here — §9).

---

## 3. Alternatives considered and rejected

Eight candidates were evaluated. None is manufactured; each is a real option the
repository state suggests.

### Alt A — Characteristic-sorted long/short factor-portfolio construction *(SELECTED)*
- **Adds:** per-rebalance quantile long/short leg formation over PIT signals;
  realized forward-return legs; a chained factor return series + per-period
  holdings + coverage + summary; sealed `FactorPortfolio`.
- **Consumes:** Phases 9/10/11 (+ Phase 16 forward-return/quantile helpers). A
  new *constructive* sibling of the Phase 16 diagnostic.
- **Belongs now:** opens the portfolio-construction class; prerequisites all
  exist; the field-standard factor-construction object the system lacks.
- **Duplicates existing?** No. Phase 16 = a diagnostic *scalar* (one
  top-minus-bottom forward-return per date, no weights, no series, "not a
  portfolio"). Phase 12 = a *general execution simulator* (long-only, share-level
  fills, cash, costs, corporate-action accounting). Phase 19 = a
  *characteristic-sorted long/short return series with holdings*, gross,
  forward-return-based — a distinct object (see §5.7, §6 rows 11–13).

### Alt B — Extend Phase 12 with long/short weighting *(REJECTED — modifies a sealed prior phase)*
- Add `weight: long_short` / `select: quantile_spread` to Phase 12's closed
  vocabulary. **Reject:** this bumps `strategy_version` → `backtest_engine_version_id`
  → **re-hashes every `backtest_id`**, breaks the six-phase pure-consumer
  discipline, and is the exact objection Phase 18 raised against its Candidate B.
  It is a legitimate but disruptive versioning event that, if ever done, deserves
  an explicit, separately-gated "Phase-12-v2" — not to be smuggled in here. Alt A
  achieves the capability as a sibling with zero prior-phase identity churn.

### Alt C — Pooled / panel regression with fixed effects *(REJECTED — refinement of Phase 18)*
- Stack all (member, date) observations into one regression with entity/time
  fixed effects. **Reject:** same inputs and same LDLᵀ machinery as Phase 18; the
  only real differentiator is clustered/robust standard errors — which is the
  HAC refinement Phase 18 §9 explicitly deferred. A refinement of an existing
  regression cell, not a new capability class.

### Alt D — HAC / Newey–West standard errors for Phase 17/18 *(REJECTED — too narrow)*
- **Reject:** a thin inferential refinement (a lag-selection knob), not a phase;
  Phase 18 §9 already earmarked it as an additive extension.

### Alt E — Signal preprocessing / neutralization layer *(REJECTED — extension, no artifact of its own)*
- Cross-sectional z-scoring, winsorization, sector/industry neutralization,
  orthogonalization. **Reject:** it is an *input transform* with no sealed
  research artifact of its own; Phases 16 and 18 explicitly deferred it as a
  "future closed-vocabulary extension" to *their* specs. Better as an additive
  extension to 16/18 than a standalone phase; borders on infrastructure.

### Alt F — Holdings-based exposure / characteristic attribution over the Phase 12 ledger *(REJECTED — premature; sequenced after Phase 19)*
- Portfolio-weighted signal exposures from the rich Phase 12 rebalance ledger
  (which *does* persist per-period weights + share-level positions — confirmed).
  **Reject for now:** exposure analytics are far more meaningful once *long/short*
  portfolios exist; building them before the factor-portfolio layer that
  motivates them risks rework. Phase 19 is the natural predecessor.

### Alt G — Cross-artifact synthesis / meta-report (IC vs premia vs attribution) *(REJECTED — reporting/convenience)*
- **Reject:** a reporting/convenience layer, not a genuine new quant capability
  (the task forbids convenience/reporting-only phases); Phase 14 already owns
  reporting, and it can gain a scope for these records in a later additive edit.

### Alt H — Factor risk model / covariance-matrix estimation *(REJECTED — prerequisite missing)*
- **Reject as premature:** it requires *multiple* factor return series as input,
  which do not exist until Phase 19 produces them. This is the textbook
  "reject rather than smuggle the prerequisite" case; it is the phase *after* 19.

**One line each:** B (modifies Phase 12 — its own gated phase), C (Phase 18
refinement), D (too narrow), E (16/18 extension, not a phase), F (premature —
after 19), G (reporting/convenience), H (premature — needs 19's output first).

---

## 4. Repository findings (authoritative, from the current tree)

Verified by direct source reading (not memory):

- **Six consecutive pure-consumer/sibling phases (13–18)** establish the template
  Phase 19 follows verbatim: a `Workspace`-wired **lazy engine**, a declarative
  content-addressed `*Specification`, resolve/verify → compute → seal →
  write-once `ResearchRecord` to the shared `<root>/research/sha256-<hex>.json`
  sidecar.
- **Shared sidecar** (`factors/store.py`): the `@runtime_checkable ResearchRecord`
  protocol requires exactly `research_result_id: str` (property) and
  `to_dict() -> dict`. `ResearchResultStore.write()` is **write-once /
  byte-identical-idempotent / fail-closed** (a differing payload under the same
  id raises `FactorConsistencyError`); `read_as(id, from_dict)` decodes; file
  naming slugifies `sha256:…` → `sha256-….json`. A new record rides the same
  store with **no store change**.
- **`Workspace` lazy-engine pattern** (`workspace.py`): add
  `self._factor_portfolio_engine: object | None = None` in `__init__`, plus a
  cached `@property` that imports and constructs `FactorPortfolioEngine(self)` on
  first use (the exact shape of every engine Phase 13–18). The Phase 16/18
  engines are reached as `workspace.signal_diagnostics_engine` /
  `workspace.crosssection_engine`.
- **Phase 16 forward-return + quantile machinery** (`diagnostics/compute.py`):
  `forward_return(base_price, end_price, *, context) -> str | None` (the exact
  arithmetic Phase 18 imports), plus `quantile_buckets` (`floor(i·q/n)`),
  `top_minus_bottom`. Phase 18's engine already **imports `forward_return` from
  `quantforge.diagnostics.compute`** and replicates the `_forward_return` /
  `_close_dates` / `_session_available_at` helper shape. Phase 19 does the same
  (D-FWD) — a zero-new-prior-edit reuse.
- **Composition surfaces confirmed:**
  - `UniverseBuilder.build_as_of(spec, as_of, *, classifications=()) -> ConstructionResult`;
    `Universe.company_ids -> tuple[str, ...]` (members are `company_id = cik:…`;
    **no** security ids at the universe layer).
  - `PanelEngine.panel_across(metric_key, factor_universe, PeriodAxis.of([period]), as_of) -> PitPanel`
    — note it consumes the **Phase 8 factor universe**
    (`quantforge.factors.universe.Universe`), so Phase 19 bridges Phase 9
    `company_ids` → factor universe exactly as Phase 16/18 do; matrix cells are
    never dropped, `UNDEFINED` preserved with reason.
  - `PriceEngine.adjusted_series_as_of(security_id, PriceAxis, as_of, *, field=CLOSE, adjustment=None) -> PitPriceSeries`;
    `dataset_version_for(security_id) -> MarketDatasetVersion`.
  - Fundamentals key on `company_id` (`cik:<CIK>`), prices on `security_id`
    (`cik:<CIK>#class:<class>`), joined by
    `market/identity.py:company_id_of_security_id`. A company with ≠ 1 tradable
    security is dropped (multi-share-class deferred — inherited from Phase 16/18).
- **Identity / Decimal discipline** (uniform across 13–18): `sha256:` prefix,
  `_SEP = "\x00"` NUL-join, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256_hex`
  from `quantforge.sec.artifacts`; all arithmetic under
  `Context(prec=34, rounding=ROUND_HALF_EVEN)` via explicit `localcontext`;
  `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=<f>/1")`;
  `<x>_engine_version_id = sha256(code_version \x00 config_hash)`.
- **`StatValue` UNDEFINED pattern** is copied (not shared) into each sibling's
  `model.py`: `status ∈ {KNOWN, UNDEFINED}`, exactly one of `value: str | None`
  / `reason: <X>UndefinedReason | None`; closed key/reason sets.
- **Phase 12 seals a rich rebalance ledger** (per-period `target_weights` +
  share-level `positions` + `cash` + `equity` + `turnover`) and per-period
  `period_returns` — confirming Alt F is *feasible* but *premature* (needs 19
  first).
- **`Decimal.sqrt()` under the pinned context is already used** for an annualized
  Sharpe in Phase 12 (`backtest/stats.py`), so an annualized-Sharpe summary cell
  (D-SUMMARY) is precedented and deterministic.
- **Version state.** Git tags exist through **`v0.15.0`** (Phase 18). Phase 19 is
  therefore **`v0.16.0`** (§10). The package `__version__` string stays `"0.0.0"`
  (versioning is by content-addressed ids). The pre-existing README
  version-label drift (Phase 15 mislabeled `v0.11.0`, etc.) is **not** fixed here.
- **No source bug** must be fixed to understand or build this design.

---

## 5. Architecture

Established pattern, adopted verbatim:

```
declarative FactorPortfolioSpecification            (content-addressed request)
    → Workspace.factor_portfolio_engine (lazy)      (composition root)
        → re-verify BOTH corpus pins (P19-1, fail closed)
        → per T: build universe @T / read PIT signal @T / read forward returns   (compose 9/10/11)
        → per T: quantile-sort → long/short legs → f_T = mean(long) − mean(short) (construct)
        → aggregate factor return series + summary across valid periods           (aggregate)
        → seal FactorPortfolio (result_hash over ordered cells)                    (seal)
        → ResearchResultStore.write(...)  write-once to shared sidecar             (persist)
```

### 5.1 Package / module structure (new package `src/quantforge/factorportfolio/`)
Mirrors the Phase 16/18 layout exactly:
- `errors.py` — `FactorPortfolioError → FactorPortfolioConfigurationError, FactorPortfolioConsistencyError`.
- `version.py` — `FACTORPORTFOLIO_SPEC_VERSION`, `FACTORPORTFOLIO_ENGINE_VERSION`,
  `FACTORPORTFOLIO_FORMULA_VERSION`, `FACTORPORTFOLIO_RESULT_FORMAT_VERSION`,
  `default_decimal_context()`, `FactorPortfolioEngineVersion` →
  `factor_portfolio_engine_version_id`.
- `identity.py` — `_SEP`, domain tag `factorportfolio/1`, `_canonical_json`,
  `factor_portfolio_result_hash(cells)`, `factor_portfolio_id(...)`.
- `model.py` — `FactorPortfolioStatus`, `FactorPortfolioUndefinedReason`,
  `StatValue` (copied pattern), `LegKind` (`long`/`short`), `PerPeriodReturn`,
  `LegMembership`, `FactorReturnSummary`, `DateCoverage`, `CoverageSummary`.
- `spec.py` — `FactorPortfolioSpecification`.
- `stats.py` — quantile leg formation, per-period spread, and the series summary
  (mean / population std / annualized Sharpe / t-stat / cumulative / hit-rate).
- `engine.py` — `FactorPortfolioEngine`.
- `__init__.py` — re-exports `FactorPortfolioSpecification`, `FactorPortfolio`.

### 5.2 Public API
```python
# spec.py
@dataclass(frozen=True, slots=True)
class FactorPortfolioSpecification:
    name: str
    signal: str  # Phase 7 metric_key (non-empty)
    period: MetricPeriod  # explicit fiscal period the signal is read for
    universe: UniverseSpecification  # Phase 9 declarative request
    schedule: RebalanceSchedule  # Phase 12 as_of instants (rebalance dates T)
    forward_horizon: str  # r"^[0-9]+d$"  (trading-day horizon; Phase 16 form)
    quantiles: int  # Q >= 2 (long = top bucket, short = bottom bucket)
    dataset_version_id: str  # fundamentals corpus pin
    market_dataset_version_id: str  # market corpus pin
    weighting: str = "equal"  # leg weighting; v1 closed vocabulary {"equal"}
    risk_free_per_period: str = (
        "0"  # provenance + annualized-Sharpe; folded into identity
    )
    periods_per_year: str = "1"  # annualization convention; folded into identity
    spec_version: str = FACTORPORTFOLIO_SPEC_VERSION  # "factorportfolio/1"
    # derived (init=False): horizon_days: int


# engine.py — reached via Workspace.factor_portfolio_engine
class FactorPortfolioEngine:
    def __init__(self, workspace: Workspace) -> None: ...
    def construct(self, spec: FactorPortfolioSpecification) -> FactorPortfolio: ...
```

`construct` is the single entry point (the `evaluate`/`estimate`/`compute`
analog). It composes the Phase 9 universe builder, Phase 10 panel engine, and
Phase 11 price engine through their public accessors; it re-resolves nothing and
duplicates no resolution logic.

### 5.3 Workspace integration
Additive, identical to the Phase 16/18 pattern:
- add `self._factor_portfolio_engine: object | None = None` in `__init__`;
- add a lazy cached `factor_portfolio_engine` `@property` importing
  `FactorPortfolioEngine` on first use (cycle-free), constructed from `self`.
No other `Workspace` change.

### 5.4 Identity model
`factor_portfolio_id` folds, NUL-joined, in this exact order (domain tag first):
1. `"factorportfolio/1"` (domain)
2. `factor_portfolio_engine_version_id`
3. `name`
4. `spec_version`
5. `signal`
6. `period.period_key`
7. `universe.specification_id`
8. `schedule.schedule_id`
9. `str(horizon_days)`
10. `str(quantiles)`
11. `weighting`
12. `risk_free_per_period` (canonicalized decimal string)
13. `periods_per_year` (canonicalized decimal string)
14. `dataset_version_id`
15. `market_dataset_version_id`
16. `result_hash` (see §5.6)

`research_result_id` is a property aliasing `factor_portfolio_id`. The id is a
**derived property**, recomputed from the embedded spec + refs + `result_hash` on
every access, so a tampered stored id is ignored (the Phase 15/16/17/18
discipline).

### 5.5 Result model
```python
@dataclass(frozen=True, slots=True)
class FactorPortfolio:  # satisfies ResearchRecord
    factor_portfolio_engine_version_id: str
    factor_portfolio_spec: dict  # embedded spec.to_dict()
    name: str
    spec_version: str
    signal: str
    period_key: str
    universe_specification_id: str
    schedule_id: str
    horizon_days: int
    quantiles: int
    weighting: str
    boundary_kind: str  # "pit"  (documents the SIGNAL side only; P19-2)
    risk_free_per_period: str
    periods_per_year: str
    dataset_version_id: str
    market_dataset_version_id: str
    per_period: tuple[
        PerPeriodReturn, ...
    ]  # one per VALID rebalance date, schedule order
    summary: FactorReturnSummary
    coverage: CoverageSummary
    formula_version: str
    result_hash: str
```
- `PerPeriodReturn(as_of: str, n_members: int, long_membership: LegMembership, short_membership: LegMembership, long_return: StatValue, short_return: StatValue, factor_return: StatValue)`
  — the per-rebalance spread; a period below the member floor or with an empty
  long/short leg yields `UNDEFINED` legs/return, recorded, never dropped.
- `LegMembership(kind: LegKind, company_ids: tuple[str, ...])` — the ordered
  members assigned to that leg (audit; **not** folded into identity — see §5.6).
- `FactorReturnSummary(cumulative_return: StatValue, mean_period_return: StatValue, volatility: StatValue, annualized_sharpe: StatValue, mean_t_stat: StatValue, hit_rate: StatValue, n_valid_periods: int)`.
- `CoverageSummary(per_date: tuple[DateCoverage, ...], total_resolved, total_dropped_for_signal, total_dropped_for_return, total_undefined_periods)`;
  `DateCoverage(as_of, resolved_members, eligible, dropped_for_signal, dropped_for_return, period_status)`.

### 5.6 What is sealed (`result_hash`)
`result_hash = factor_portfolio_result_hash(_output_cells(...))` = sha256 over
ordered block-tagged cells: the **`per_period`** block (each period's
`as_of`, `n_members`, `long_return`, `short_return`, `factor_return` — schedule
order, **not re-sorted**) → the **`summary`** block (the six summary cells).
Per-period `n_members` and leg returns are result-changing facts and are sealed
(the Phase 16/18 precedent of sealing per-date diagnostics). **Leg membership
and coverage counts are audit metadata and are NOT folded** (they are recoverable
from the pinned corpora; this mirrors Phase 16/18 excluding coverage from the
seal). `boundary_kind = "pit"` documents that the **signal side** was
PIT-eligible; the record is **not** a `Pit*` type and exposes **no as-of
accessor** (P19-2).

### 5.7 Versioning model
`FACTORPORTFOLIO_ENGINE_VERSION = "factorportfolio-engine/1"`,
`FACTORPORTFOLIO_FORMULA_VERSION = "factorportfolio-stats/1"`,
`FACTORPORTFOLIO_SPEC_VERSION = "factorportfolio/1"`,
`FACTORPORTFOLIO_RESULT_FORMAT_VERSION = "factorportfolio-result/1"` (a container
concern — **not** folded into `factor_portfolio_id`, per the 13–18 precedent).
`config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=factorportfolio-stats/1")`;
`factor_portfolio_engine_version_id = sha256(FACTORPORTFOLIO_ENGINE_VERSION \x00 config_hash)`.
Any formula or code change bumps a version → a different `factor_portfolio_id`.
Release **`v0.16.0`**.

### 5.8 Persistence & serialization
Write-once to the existing `ResearchResultStore` (`<root>/research/`), reached via
`workspace.research_result_store` (the engine exposes a `research_store`
property, overridable in tests, exactly as the siblings do; Phase 16/18 write via
`factor_engine.research_store.write(...)`). No new store, no database. `to_dict()`
emits canonical JSON and includes both `factor_portfolio_id` and its
`research_result_id` alias; `from_dict()` is the fail-closed byte-identical
inverse. Idempotent recompute is a no-op; a differing payload under the same id
fails closed via the store (`FactorConsistencyError`).

### 5.9 Deterministic behavior
No wall-clock, no RNG, no `id()`/iteration-order dependence (universe/panel/price
order is deterministic; the per-period series preserves schedule order; leg
membership is sorted by `company_id`; tie-breaking within a quantile boundary is
the deterministic `quantile_buckets` rule on a stable member ordering). All
arithmetic under the pinned `Decimal` context. Same spec + same pinned corpora ⇒
identical `factor_portfolio_id`, per-period series, and summary on any machine.

### 5.10 Interaction with existing phases (summary; full table in §6)
- **Phase 9/10/11:** COMPOSES (read-only, through public accessors).
- **Phase 16:** COMPOSES-adjacent (reuses forward-return + `quantile_buckets`
  shape; distinct output — a constructive series, not a diagnostic scalar).
- **Phase 12:** none at the identity level (does **not** consume/produce a
  `BacktestResult`, does not touch Phase 12); TENSION ("does it duplicate the
  backtester?") resolved in §6 row 12.
- **Phase 13/14/15/17/18:** none (does not consume an experiment, report,
  analytics, attribution, or regression record).

---

## 6. Invariant / contradiction analysis

`COMPOSES` = read-only reuse, no new tension; `CONSTRAINS` = an existing invariant
dictates the design; `TENSION` = a resolvable design pressure; `CONTRADICTION` =
an unresolvable conflict.

| # | Interaction | Class | Analysis |
| --- | --- | --- | --- |
| 1 | **PIT correctness** (inv. 6, 29) | CONSTRAINS | The signal side reads only PIT-eligible-at-`T` values via `panel_across(as_of=T)`; no post-`T` fundamentals enter leg formation. Codified as **P19-3**. |
| 2 | **PIT vs REVISED / ex-post separation** (inv. 27, 28) | CONSTRAINS | The realized forward return (and thus the factor return series) is post-`T` — *not* a PIT value; the record is not a `Pit*` type and exposes no as-of accessor; it can never feed an as-of-`T` computation. Codified as **P19-2** (direct SD-2 / XS-2 / inv. 28 analog). |
| 3 | **Immutable dataset behavior** (inv. 1, 5, 8) | COMPOSES | Reads only immutable canonical facts / prices; writes nothing back; no fact/price mutation. |
| 4 | **Corpus pinning** (BT-1, SD-1, XS-1, inv. 19) | CONSTRAINS | Both `dataset_version_id` and `market_dataset_version_id` are declared, re-derived, and verified; mismatch or non-unique normalizer fails closed; a changed corpus yields a different `factor_portfolio_id`. Codified as **P19-1**. |
| 5 | **Survivorship handling** (Phase 9) | COMPOSES | Universe rebuilt at each `T` via `build_as_of`, inheriting Phase 9 survivorship-correct membership; no delisted-name leakage. |
| 6 | **Content-addressed identity** (inv. 19) | COMPOSES | `factor_portfolio_id` folds the request, both pins, engine/formula version, and the answer's `result_hash`. |
| 7 | **Deterministic serialization** (inv. 13, 18, 21) | COMPOSES | `sha256:` + NUL-join + canonical JSON; ordered inputs preserved, set/leg inputs sorted. |
| 8 | **Write-once persistence** (Phase 8 store) | COMPOSES | Reuses the write-once, byte-identical-idempotent, fail-closed sidecar; no new store. |
| 9 | **Provenance** (inv. 3) | COMPOSES | Record embeds spec + pins + versions + per-period series + leg membership + coverage; fully reconstructible from the record + the two pinned corpora. |
| 10 | **Fail-closed behavior** (SD-4, XS-4) | CONSTRAINS | A member lacking the PIT signal at `T` or a forward return is excluded and counted; a period below the member floor or with an empty long/short leg is a recorded `UNDEFINED` period, never dropped or fabricated. Configuration defects (unknown metric, `Q < 2`, unknown weighting, `< 2` valid periods) raise. Codified as **P19-4**. |
| 11 | **Phase 16 diagnostic semantics** | COMPOSES + **TENSION (resolved)** | Reuses the forward-return / `quantile_buckets` shape. *Tension:* is this Phase 16 again? **Resolved:** Phase 16 emits a per-date *diagnostic scalar* (top-minus-bottom forward return), no weights, no series, explicitly "not a portfolio." Phase 19 forms a *weighted long/short portfolio* and emits a *chained return series with holdings + performance summary* — a constructive artifact, a different object and question (predictive power vs realized factor performance). Not a duplication. |
| 12 | **Phase 12 backtester semantics** (BT-1..4) | COMPOSES + **TENSION (resolved)** | *Tension:* does producing a "portfolio return series" duplicate the backtester? **Resolved:** Phase 12 is a *general execution simulator* — long-only, share-level fills, cash, cost model, corporate-action accounting, mark-to-market equity curve. Phase 19 is *characteristic-sorted academic factor construction* in return space — long/short, gross, no fills/cash/costs, forward-return-based; and it does precisely what Phase 12 *structurally cannot* (a short leg / dollar-neutral spread). It **modifies no Phase 12 code, bumps no Phase 12 version, and produces no `BacktestResult`.** Orthogonal purpose; not a duplication. |
| 13 | **Phase 17 attribution / Phase 18 regression semantics** (FA-1..4, XS-1..4) | COMPOSES (future) | Consumes neither. A future phase may teach attribution to accept a `FactorPortfolio` return series as a factor; no such scope is reserved now (the Phase 17 Open-Q6 precedent). |
| 14 | **Phase 15 benchmark semantics** | (none) | Consumes no `BacktestResult`, no benchmark; no interaction. |
| 15 | **Decimal conventions** (no float) | CONSTRAINS | All leg means, spreads, and summary stats under `Context(prec=34, ROUND_HALF_EVEN)`; `Decimal.sqrt()` for annualized Sharpe (Phase 12 precedent). No float, no NumPy, no RNG. |
| 16 | **Undefined-value semantics** | CONSTRAINS | Every undefinable statistic (empty long/short leg, insufficient members, no/one valid period, zero-variance series for the Sharpe/t-stat) is a first-class `UNDEFINED` `StatValue` with a closed reason — never `NaN`/`Inf`/`0`/divide-by-zero. |
| 17 | **ResearchRecord reuse** | COMPOSES | Record exposes `research_result_id` + `to_dict`; nothing else required. |

**Contradiction analysis:** none found. The two substantive tensions (rows 11,
12 — "is this Phase 16 or the backtester again?") are resolved by the
capability-class distinction: *portfolio construction* is a genuinely new class,
neither a diagnostic scalar nor a general execution simulator. No existing
invariant is weakened; P19-1..5 are strict additions modeled on SD-1..4 / XS-1..4.

---

## 7. Approval-gated decisions

Each lists the recommended option first, then alternatives, then why it matters.
Load-bearing decisions (identity/methodology, marked **★**) require explicit
approval before implementation.

**★ D-SCOPE — Capability scope.**
- *Recommended:* single-signal, long/short, quantile-sorted factor construction
  with equal-weight legs; per-rebalance forward-return spread chained into a
  return series. Defer multi-signal composites, optimization, and net-of-cost.
- *Alternatives:* multi-signal composite factor now; include a full execution
  model now.
- *Why it matters:* fixes the phase boundary and what the sealed artifact means.

**★ D-INPUT — Realization: sibling over 9/10/11, not a Phase 12 extension.**
- *Recommended:* build as a **new sibling layer over Phases 9/10/11** (like 16/18);
  **do not** consume or produce a `BacktestResult`, and **do not** modify Phase
  12's strategy vocabulary or engine version.
- *Alternatives:* extend Phase 12 (Alt B) — re-hashes every `backtest_id`.
- *Why it matters:* this is the single most consequential decision. The sibling
  path preserves all prior identity; the Phase-12 path is a repo-wide versioning
  event.

**★ D-NAME — Package / type naming.**
- *Recommended:* package `factorportfolio`; `FactorPortfolioSpecification`,
  `FactorPortfolio`, `FactorPortfolioEngine`; entry `construct`.
- *Alternatives:* package `portfolio` (risks implying optimization); `factorreturns`
  (`FactorReturnSeries`); `sorts` (`SortedPortfolio`).
- *Why it matters:* the domain tag (`factorportfolio/1`) and engine-version-id
  string derive from the choice and are baked into every `factor_portfolio_id`;
  changing it later is a breaking identity change.

**★ D-LEG — Leg definition & factor-return convention.**
- *Recommended:* long = **top** quantile bucket, short = **bottom** bucket
  (high-minus-low on the **raw** signal, no sign flip); `f_T = mean(long forward
  returns) − mean(short forward returns)` (dollar-neutral, gross). Record each
  leg's own mean return and membership.
- *Alternatives:* configurable direction / sign; long-only or short-only factor;
  top-vs-rest instead of top-vs-bottom.
- *Why it matters:* defines the sign and meaning of every reported number; must
  be pinned in `formula_version`.

**★ D-WEIGHT — Leg weighting.**
- *Recommended:* **equal-weight within each leg** in v1 (closed vocabulary
  `{"equal"}`).
- *Alternatives:* value-weight (needs a market-cap PIT signal — a second signal
  and more identity inputs); rank/signal-proportional weight.
- *Why it matters:* weighting changes every factor return; keep v1 minimal and
  fold `weighting` into identity so a future scheme hashes distinctly.

**D-QUANTILE — Quantile-assignment rule.**
- *Recommended:* reuse the Phase 16 `quantile_buckets` rule (`floor(i·Q/n)` over a
  deterministically ordered member list) **verbatim**, for commensurability with
  the diagnostic layer.
- *Alternatives:* a divergent bucketing rule.
- *Why it matters:* a second bucketing definition in the codebase would diverge
  from Phase 16's diagnostic and confuse cross-layer comparison.

**D-FWD — Forward-return definition reuse.**
- *Recommended:* reuse the Phase 16/18 `"<n>d"` trading-day PIT-gated adjusted
  forward return **verbatim** (import `forward_return` from
  `quantforge.diagnostics.compute`; replicate the `_forward_return` helper as
  Phase 18 does). No new prior-phase edit.
- *Alternatives:* promote the forward-return helper to a neutral shared module
  (as `_linalg` was promoted in Phase 18) — a behavior-preserving prior-phase
  edit; or define calendar/log returns.
- *Why it matters:* keeps Phase 19 commensurable with 16/18 and adds no second,
  divergent return definition. *Recommend reuse-by-import (zero prior edit); a
  shared-module promotion is offered only if the maintainer prefers to remove the
  `diagnostics` → `crosssection`/`factorportfolio` coupling — but that is out of
  scope for v1.*

**★ D-SUMMARY — Series summary & annualization.**
- *Recommended:* seal a summary mirroring Phase 12's return-series vocabulary
  applied to the factor return series: **cumulative (compounded)** factor return
  `∏(1+f_T) − 1`, mean period return, **population** volatility, **annualized
  Sharpe** `(mean − rf)/vol · sqrt(periods_per_year)` (via `Decimal.sqrt()`, the
  Phase 12 precedent), the mean's **t-statistic** `mean/(popStd/√M)`, and hit
  rate. Fold `risk_free_per_period` + `periods_per_year` into identity (the Phase
  17 provenance precedent).
- *Alternatives:* per-period-only summary with no annualization (the Phase 18
  minimalism); arithmetic (non-compounded) cumulative.
- *Why it matters:* determines the annualization convention and whether the
  artifact is directly commensurable with Phase 12/15/17 statistics. The std
  convention (population vs sample) and compounding must be pinned in
  `formula_version`.

**★ D-UNDEFINED — Degenerate / minimum-count behavior.**
- *Recommended:* a per-period **member floor** `n_members ≥ 2·Q` (both legs
  non-empty and `Q` well-defined) — a period below it, or with an empty long or
  short leg, is a recorded `UNDEFINED` period (P19-4), **not** a raise; a
  **minimum valid-periods** guard `M ≥ 2` for the summary — below it the *run*
  raises `FactorPortfolioConfigurationError` (the Phase 18 AG-5 / `_MIN_VALID_DATES`
  analog, so an all-`UNDEFINED` record is never sealed). Zero-variance series →
  `UNDEFINED` Sharpe/t-stat.
- *Alternatives:* raise on the first empty leg; seal an all-`UNDEFINED` record.
- *Why it matters:* fixes the fail-closed-config vs sealed-partial-`UNDEFINED`
  boundary; must be pinned and tested.

**D-INVARIANTS — Invariant placement.**
- *Recommended:* keep **P19-1..P19-5 as phase-local invariants** documented in the
  locked spec (the Phase 17 D6 / Phase 18 precedent), **not** added to the
  numbered `data-model.md §12` registry — though, symmetry with the SD-1..4 /
  XS-1..4 additive blocks in §12 suggests adding a short **P19 block** there too.
  *Recommend a small additive `data-model.md §12` block mirroring XS-1..4* (they
  "do not weaken 1–30"), consistent with how SD/XS were handled.
- *Why it matters:* determines whether `data-model.md` is edited in the doc pass.

**D-VERSION — Release version.**
- *Recommended:* **`v0.16.0`** (Phase 18 = `v0.15.0`, confirmed by git tags).
- *Alternatives:* none with repository support.
- *Why it matters:* see §10.

**D-DIRECTION-KNOB — Rank direction (deferred, flagged).**
- *Recommended:* v1 fixes high-minus-low on the raw signal (no `rank_direction`
  field). A future `rank_direction ∈ {descending, ascending}` (Phase 12
  vocabulary) can flip the factor sign, folded into identity when added.
- *Why it matters:* keeps v1 identity minimal; documents the intended extension
  point.

---

## 8. New invariants (phase-local: P19-1 … P19-5)

Modeled on SD-1..4 / XS-1..4; strict additions that do not weaken invariants
1–30.

- **P19-1 — Corpus pinning for a factor portfolio.** A run records and, on re-run,
  re-verifies **both** the fundamentals `dataset_version_id` and the market
  `market_dataset_version_id`; a mismatch — or a corpus that does not admit a
  single normalizing transformation version — fails closed, and a changed corpus
  yields a different `factor_portfolio_id`. (The SD-1 / XS-1 analog.)
- **P19-2 — A factor return series is not a PIT value.** `FactorPortfolio` chains
  realized *forward* (post-`T`) returns and can never be substituted where a PIT
  as-of-`T` value/signal is required; it is not a `Pit*` type and exposes no
  as-of accessor. `boundary_kind = "pit"` documents that the *signal side* was
  PIT-eligible, not that the series is a PIT value. (The direct analog of inv. 28
  / SD-2 / XS-2.)
- **P19-3 — Signal PIT-eligibility.** The signal at every rebalance date `T` is
  read PIT-eligible-at-`T` (via `panel_across(..., as_of=T)`, inv. 29); no post-`T`
  data ever contaminates leg formation.
- **P19-4 — Fail-closed pairing & leg formation.** A member lacking the PIT signal
  at `T` or a computable forward return is excluded from that period and recorded
  in coverage; it is never imputed, zero-filled, or fabricated. A period below the
  member floor (`n_members < 2·Q`) or with an empty long or short leg is a recorded
  `UNDEFINED` period, never raised and never silently dropped. (cf. inv. 9, 12;
  SD-4 / XS-4.)
- **P19-5 — A factor portfolio is not a `BacktestResult`.** `FactorPortfolio` is a
  distinct record type; it is not interchangeable with a sealed `BacktestResult`,
  does not enter Phase 12's identity, and must not be passed where a
  `BacktestResult` is required (enforced by type). This keeps the Phase 12
  execution-simulation and Phase 19 factor-construction artifacts distinct.

---

## 9. Out of scope (strict)

Deferred to later, explicitly-labelled phases; Phase 19 must not absorb any:
- **Any modification to Phase 12** (its vocabulary, engine, or identity) — Alt B is
  its own gated phase.
- **Multi-signal composite / orthogonalized factors**, signal neutralization,
  z-scoring, winsorization (Alt E — a future 16/18/19 closed-vocabulary extension).
- **Value / rank / signal-proportional leg weighting** (D-WEIGHT; a future closed
  vocabulary).
- **Transaction-cost-aware / net-of-cost factor returns**, execution modelling,
  cash, share-level fills (that is Phase 12's domain; a net-return extension is
  future).
- **Factor risk model / covariance-matrix estimation** (Alt H — needs multiple
  factor series first; the phase after this).
- **Feeding `FactorPortfolio` into Phase 17 attribution** (a future Phase 17
  extension; no scope reserved now).
- **Rolling/windowed factor performance**, sub-period / regime conditioning.
- **Calendar/step forward-horizon forms** and **multi-share-class** forward returns
  (the Phase 16 §22 deferrals, inherited — a company with ≠ 1 tradable security is
  dropped and recorded).
- **A REVISED scope** for the construction (reserved for a future
  explicitly-labelled phase, per the Phase 15/17/18 precedent). v1 is
  PIT-signal / ex-post only.
- **Batch/multi-signal runs** (one spec = one factor study; batching is a thin
  future loop).

---

## 10. Versioning

**Recommendation: `v0.16.0`.** Git tags exist through **`v0.15.0`** (Phase 18);
sequence Phase 18 → v0.15.0, **Phase 19 → v0.16.0**. The package `__version__`
string stays `"0.0.0"` (versioning is by content-addressed ids, per the
established precedent). No repository evidence supports a different number. The
pre-existing README/Phase-17-doc version-label drift (documented in the Phase 18
proposal §4) is **not** fixed in this phase.

---

## 11. Implementation scope (only if approved)

### New files — `src/quantforge/factorportfolio/`
- `__init__.py`, `errors.py`, `version.py`, `identity.py`, `model.py`, `spec.py`,
  `stats.py`, `result.py`, `engine.py`.
- *(No `_linalg` change — Phase 19 does no OLS; D-FWD recommends import-reuse, so
  no prior-phase source is promoted.)*

### Existing files — additive changes only
- `src/quantforge/workspace.py` — add `self._factor_portfolio_engine = None` and
  the lazy `factor_portfolio_engine` property (no other change).
- `src/quantforge/__init__.py` — re-export `FactorPortfolioSpecification` and
  `FactorPortfolio` and add to `__all__` (engine reached via `Workspace`, never
  re-exported — the sibling convention).
- **No other prior-phase source is touched.**

### Tests — `tests/factorportfolio/`
- `__init__.py`, `builders.py` (a small deterministic multi-member universe,
  panel signals, price forward returns — synthetic offline data only).
- `test_spec.py` — validation (empty name; non-empty signal + `MetricPeriod`;
  `Q ≥ 2`; horizon grammar; weighting vocabulary; required pins; canonicalized
  `risk_free_per_period` / `periods_per_year`; `to_dict`/`from_dict` round-trip).
- `test_identity.py` — fold order & sensitivity: changing the signal, period,
  universe/schedule/horizon/quantiles/weighting/either annualization field/either
  pin ⇒ different `factor_portfolio_id`; determinism across runs; tampered stored
  id ignored.
- `test_stats.py` — exact-`Decimal` quantile assignment; leg means; long-minus-short
  spread; cumulative/mean/vol/Sharpe/t-stat/hit-rate against hand-computed small
  cases; empty leg / insufficient members / zero-variance → `UNDEFINED`;
  cross-check the spread's sign against the Phase 16 top-minus-bottom on the same
  data.
- `test_result.py` — seal, `result_hash` cell ordering (`per_period` schedule
  order, then `summary`), byte-identical round-trip, `research_result_id` alias,
  leg membership/coverage excluded from the seal.
- `test_engine.py` — end-to-end over builders: corpus-pin re-verification &
  fail-closed mismatch (P19-1); PIT signal read at `T` (P19-3, no post-`T`
  leakage); factor-return-not-PIT / no as-of accessor (P19-2); fail-closed
  coverage (dropped-for-signal / dropped-for-return / empty-leg / below-floor
  UNDEFINED period) (P19-4); `M < 2` raises; write-once idempotency and
  differing-payload fail-closed; not-a-spec argument raises.
- `tests/test_smoke.py` — add an import/round-trip smoke assertion (additive).

### Documentation (only after implementation is green — **not** in this phase)
- **Locked spec:** `docs/phase19-factor-portfolio-locked.md` (normative;
  P19-1..5, decision table, identity fold, test matrix).
- **README.md:** add a capability bullet + a `v0.16.0` status row.
- **ARCHITECTURE.md:** add a "Factor-portfolio construction" component row; extend
  the implemented-layers note to Phases 1–19.
- **docs/index.md:** add a Phase 19 entry; update the Status paragraph.
- **docs/data-model.md:** add a **P19-1..P19-5** additive block to §12 mirroring
  the SD-1..4 / XS-1..4 blocks (per D-INVARIANTS).

---

## 12. Numerical methodology (strict)

- **Exact `Decimal` only**, under `Context(prec=34, ROUND_HALF_EVEN)` applied via
  explicit `localcontext`. No float, no NumPy, no pandas.
- **No RNG, no wall-clock, no iteration-order dependence.** Quantile boundaries
  are integer arithmetic on a deterministically ordered member list; leg means are
  exact `Σ/n`; the spread is exact subtraction.
- **Annualized Sharpe** uses `Decimal.sqrt(periods_per_year)` under the pinned
  context — already precedented in Phase 12 `backtest/stats.py`; deterministic to
  context precision.
- **Cumulative return** is the compounded product `∏(1+f_T) − 1` (pinned in
  `formula_version`); **volatility** is population std; the **t-statistic** is
  `mean/(popStd/√M)`.
- **Every undefinable statistic** is a first-class `UNDEFINED` `StatValue` with a
  closed reason (`EMPTY_LONG_LEG`, `EMPTY_SHORT_LEG`, `INSUFFICIENT_MEMBERS`,
  `NO_VALID_PERIODS`, `SINGLE_VALID_PERIOD`, `ZERO_RETURN_VARIANCE`) — never
  fabricated, never `NaN`/`Inf`, never divide-by-zero.

---

## 13. Final report (this step)

- **Selected capability:** characteristic-sorted long/short factor-portfolio
  construction — a sealed, content-addressed **factor return series** with
  per-period leg holdings, coverage, and a performance summary.
- **Why Phase 19:** opens a new capability class (portfolio construction); all
  prerequisites exist (Phases 9/10/11 + Phase 16/18 machinery); it is the
  repeatedly-deferred, README-"Next" gap; it was correctly *not* 15/16/17/18
  (those are diagnostics/regressions); it unlocks factor risk models, real-factor
  attribution, and holdings-based analytics.
- **Alternatives rejected:** B (modifies Phase 12), C (Phase 18 refinement), D
  (too narrow), E (16/18 extension), F (premature — after 19), G
  (reporting/convenience), H (premature — needs 19's output).
- **Contradiction/invariant analysis:** no contradiction; two tensions (vs Phase
  16 and vs Phase 12) resolved by the capability-class distinction; P19-1..5 are
  strict additions.
- **Approval-gated decisions:** D-SCOPE, D-INPUT, D-NAME, D-LEG, D-WEIGHT,
  D-QUANTILE, D-FWD, D-SUMMARY, D-UNDEFINED, D-INVARIANTS, D-VERSION,
  D-DIRECTION-KNOB (load-bearing marked ★).
- **New invariants:** P19-1..P19-5 (phase-local; a mirrored §12 block recommended).
- **Package/modules:** `src/quantforge/factorportfolio/` (9 modules) mirroring the
  Phase 16/18 layout.
- **Version:** `v0.16.0` (git tags confirm through v0.15.0).
- **Proposal path:** `docs/phase19-factor-portfolio-proposal.md` (this file — the
  sole deliverable).

No implementation, tests, source edits, or documentation edits outside this
proposal were performed. No commit, push, tag, or release was performed.
**No implementation begins until the maintainer explicitly approves this
proposal.**
