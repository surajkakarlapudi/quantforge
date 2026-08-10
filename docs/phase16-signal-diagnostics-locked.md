# Phase 16 — Cross-Sectional Signal Diagnostics (LOCKED)

> **Status:** Locked normative specification. Decisions **D1–D11** were approved as
> recommended and the five §24 open questions are resolved here; this document is the
> source of truth for the implementation and supersedes the recommendations in
> [phase16-signal-diagnostics-proposal.md](phase16-signal-diagnostics-proposal.md). Every
> conditional reference in the proposal ("recommended", "if the reviewer prefers…") is
> resolved here to a committed decision.
>
> **One-line thesis:** Phase 16 adds a deterministic, content-addressed **cross-sectional
> signal diagnostics** layer — the *diagnostic sibling* of the Phase 12 backtester, above
> Phases 9/10/11 and a **pure consumer** of them. Given a declarative
> `SignalDiagnosticsSpecification`, `SignalDiagnosticsEngine.evaluate(...)` reads an
> as-of-`T` signal cross-section (Phase 10 `panel_across`), pairs it with each member's
> realized **forward** return over a horizon (Phase 11 PIT-gated adjusted prices), and per
> evaluation date computes the **Information Coefficient** (Spearman rank IC + Pearson IC),
> **quantile-bucket** mean forward returns, and the **top-minus-bottom spread**; it
> summarises the IC series and seals a `SignalDiagnostics` `ResearchRecord` write-once to
> the existing Phase 8 sidecar under the same pinned `Decimal` context. It introduces **no**
> new data source, **no** new PIT resolution, **no** new store, **no** runtime dependency,
> and **no** database, and it consumes **no** `BacktestResult`.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D1** | The selected Phase 16 capability is **cross-sectional signal diagnostics** (IC + quantile forward-return profile) — the standard pre-backtest signal-evaluation step, entirely absent today. It composes Phases 9/10/11 only, consumes no `BacktestResult`, and unblocks a future long/short factor-portfolio + multi-factor attribution phase. |
| **D2** | The engine lives at the **`Workspace` level** (`workspace.signal_diagnostics_engine`), a lazy cached `@property` annotated `-> object` with an import-in-body, mirroring `panel_engine` / `analytics_engine`. `Company` gains nothing. |
| **D3** | The signal cross-section is read by **reusing Phase 10 `panel_across`** — no second fundamental-data path. It inherits Phase 10's PIT and UNDEFINED semantics unchanged. |
| **D4** | The forward return is built from the **Phase 11 PIT-gated adjusted view** at the window-end `as_of` (`T + horizon`), never an unadjusted spot price — split/dividend consistency without revision leak. This pins `market_dataset_version_id`. |
| **D5** | A `SignalDiagnostics` is a **distinct forward-looking type, inadmissible where a PIT as-of-`T` value/signal is required** (**SD-2**, the analog of invariant 28). It is not a `Pit*` type and exposes no as-of accessor; its `boundary_kind = "pit"` documents only that the *signal* was PIT-eligible. |
| **D6** | IC is computed **both** ways (Spearman rank IC + Pearson IC), with **average-rank** tie handling and **population** moments (matching `analytics/compute.py`). The definitions are folded into `formula_version` (`diagnostics-stats/1`). |
| **D7** | Quantile buckets use a **fixed `q ≥ 2`** with a deterministic average-rank + floor-based assignment rule (§4); the **top-minus-bottom spread** is bucket `q−1` minus bucket `0`. `quantiles` folds into `diagnostics_id`. |
| **D8** | **Both** corpus pins (fundamentals `dataset_version_id`, market `market_dataset_version_id`) are recorded and **re-verified** on evaluate; a mismatch fails closed and a changed corpus yields a different `diagnostics_id` (**SD-1**, the BT-1 analog). |
| **D9** | Identity **reuses the §11 discipline** (`sha256:` prefix, `_SEP = "\x00"` NUL-join, canonical JSON) with a fresh record domain tag `diagnostics/1`. Because Phase 16 reads *raw corpora* (not sealed research artifacts), it references them by **corpus pin**, not by a `result_hash`; the pins are content-addressed, so `diagnostics_id` stays sensitive to any corpus change. |
| **D10** | Persistence **reuses the existing `ResearchResultStore` sidecar** via the `ResearchRecord` Protocol (`research_result_id` alias + deterministic `to_dict`/`from_dict`). No new store, no new format, no database. |
| **D11** | Every undefinable cell is a **first-class `UNDEFINED` value carrying a reason** (`StatValue`, reused from the Phase 15 discipline) — never a raise, never a fabricated `0`, never `NaN`/`Inf`, never a divide-by-zero, never a silent omission (**SD-4**). A member lacking a PIT signal at `T` or a computable forward return is excluded and counted in coverage, never imputed. |

### 1.1 Resolved open questions (§24)

The proposal left five questions open with recommendations; all five are resolved here as
recommended and are load-bearing for the implementation.

1. **Horizon representation.** The `forward_horizon` is a **trading-day count** (e.g.
   `"21d"`) realized over a Phase 11 `PriceAxis`, so the window is corporate-calendar
   aware — not a calendar-day step and not a count of schedule steps. The forward window is
   `[T, T+h]` in *trading days*: the start is the latest PIT-eligible close on-or-before
   `T`, the end is the close `h` trading days later, both read through the PIT-gated
   adjusted view at the window-end `as_of`.
2. **IC information-ratio convention.** The IC information ratio is **per-period**
   (`mean_ic / ic_std`) with a **separate** t-stat (`mean_ic / ic_std · √n`); there is **no
   annualisation** by `√(periods_per_year)`, because evaluation dates need not be uniformly
   spaced. No annualization convention enters the spec or identity.
3. **Signal period vs evaluation date.** v1 fixes **one explicit `MetricPeriod`** for the
   whole study (simple and honest). Per-`T` period selection ("most recent annual as-of
   `T`") is a documented follow-on; no period-resolution rule is smuggled in now.
4. **Bucket boundary / tie rule.** Deterministic **average-rank + floor-based bucketing**
   (§4): members are ranked by (signal value ascending, then `company_id`) with ties
   receiving the average of their contiguous positions for IC; for bucketing, members are
   placed by their `0..n−1` ordinal position via `bucket = floor(position · q / n)`, so the
   assignment is total-ordered and reproducible regardless of value ties.
5. **Version numbering.** Phase 16 is the next bump on the README scheme: **`v0.12.0`**
   (Phase 15 is labelled `v0.11.0`). The package `__version__` string is unchanged
   (versioning is by content-addressed ids, not a semver string).

### 1.2 Deviations from the proposal (disclosed)

One implementation choice is recorded here for auditability; it changes no identity
discipline and weakens no invariant.

1. **`spec.py` canonicalizes the horizon.** The proposal names `forward_horizon` as "a
   declared trading-day count or calendar step". v1 accepts **only** the trading-day form
   `"<n>d"` with `n ≥ 1` (calendar/step forms are out of scope, §22 of the proposal) and
   canonicalizes it to the integer trading-day count folded into `diagnostics_id`. A
   malformed horizon raises `SignalDiagnosticsConfigurationError` at construction. This is a
   scope-narrowing to the single supported representation, not a new capability.

---

## 2. Architecture (locked)

Phase 16 is a thin diagnostics layer *above* Phases 9/10/11, **parallel to** Phase 12 (the
diagnostic sibling of the backtester) and independent of it. It follows the extension recipe
every prior phase uses: versioned immutable request object → fail-closed engine reached from
`Workspace` via a lazy, cycle-free `@property` → distinct result type → content-addressed
identity with fresh domain tags → data conditions recorded as first-class values, defects
raised → compute-on-demand with the shared write-once sidecar. Unlike Phases 13/14/15 (which
consume sealed `BacktestResult`s), Phase 16 reads the **raw corpora** through the existing
PIT accessors and pins them by `DatasetVersion`.

```
                 SignalDiagnosticsSpecification     (declarative request, content-addressed)
                          |
                          v
   Workspace.signal_diagnostics_engine  --->  SignalDiagnosticsEngine.evaluate(spec)
                          |                 |
                          |   verify both corpus pins (fundamentals + market) — fail closed (SD-1)
                          |
                          |   for each eval as_of T in the schedule (in order):
                          |     resolve universe PIT as-of T           (Phase 9)
                          |     read signal cross-section panel_across(..., as_of=T)  (Phase 10)
                          |     forward return over [T, T+h] via adjusted view        (Phase 11)
                          |     drop members w/o PIT signal or forward return -> coverage (SD-4)
                          |     compute per-date rank IC, Pearson IC, bucket means, spread
                          v                 v
        summarise IC series + mean quantile profile under the pinned Decimal context
        (UNDEFINED-preserving; no float; no RNG; no wall-clock)
                          |
                          v
             SignalDiagnostics (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
             store.read_as(id, SignalDiagnostics.from_dict)   (typed, byte-identical round-trip)
```

**New package `src/quantforge/diagnostics/`** (mirrors `analytics/`):

- `errors.py` — `SignalDiagnosticsError` → `SignalDiagnosticsConfigurationError`,
  `SignalDiagnosticsConsistencyError`.
- `version.py` — `SignalDiagnosticsEngineVersion` (folds the pinned decimal context **and**
  the formula-method version `diagnostics-stats/1` into `config_hash`);
  `DIAGNOSTICS_ENGINE_VERSION = "diagnostics-engine/1"`, `DIAGNOSTICS_FORMULA_VERSION =
  "diagnostics-stats/1"`; `default_decimal_context()`. Mirrors `analytics/version.py`. The
  version id property is `signal_diagnostics_engine_version_id`.
- `identity.py` — `diagnostics_result_hash`, `diagnostics_id`. Fresh record domain tag
  `diagnostics/1`.
- `model.py` — `DiagnosticStatus`/`DiagnosticUndefinedReason` vocabulary; the closed v1 key
  sets; `StatValue` (a KNOWN decimal string **or** UNDEFINED+reason); the nested records
  `PerDateIC`, `QuantileProfile`, `ICSummary`, `CoverageSummary`, `ICMethod`.
- `compute.py` — the pure statistic functions (`parse_pairs`, `rank_ic`, `pearson_ic`,
  `quantile_buckets`, `top_minus_bottom`, `ic_summary`, `forward_return`). Pure; read no
  store; take decimal-string vectors, return decimal strings / UNDEFINED cells.
- `spec.py` — `SignalDiagnosticsSpecification`, full construction-time validation;
  `DIAGNOSTICS_SPEC_VERSION = "diagnostics/1"`.
- `result.py` — `DIAGNOSTICS_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, `SignalDiagnostics`
  (a `ResearchRecord` with `.seal`/`to_dict`/`from_dict`).
- `engine.py` — `SignalDiagnosticsEngine` (constructed from `Workspace`; composes the Phase
  9 universe builder, Phase 10 panel engine, Phase 11 price engine, the Phase 7 metric
  engine for pin derivation, and the shared `research_result_store` +
  `SignalDiagnosticsEngineVersion`): verify pins → per-date evaluate → summarise → seal →
  write-once.
- `__init__.py` — package exports.

**The only edits to existing source** (both additive, neither altering any existing identity):

1. `workspace.py` — one lazy `signal_diagnostics_engine` `@property` (+ its
   `self._signal_diagnostics_engine: object | None = None` cache line), following the
   `analytics_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of `SignalDiagnosticsSpecification`
   and `SignalDiagnostics` (spec + result only; the engine is reached via `Workspace`).

**No edit to** `backtest/*`, `analytics/*`, `experiment/*`, `report/*`, `panel/*`,
`market/*`, `universe/*`, `factors/store.py`, or any identity/version module of a prior
phase. **No `BacktestResult` is read.**

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric, no
wall-clock, no RNG.

### 3.1 `SignalDiagnosticsSpecification` (declarative request)

```
SignalDiagnosticsSpecification(
    name: str,                                    # non-empty
    signal: str,                                  # non-empty Phase 7 metric_key
    period: MetricPeriod,                          # explicit fiscal period — never inferred
    universe: UniverseSpecification,               # Phase 9 spec (has .specification_id)
    schedule: RebalanceSchedule,                   # Phase 12 eval as_of instants (non-empty)
    forward_horizon: str,                          # "<n>d" trading-day count, n >= 1
    quantiles: int,                                # q >= 2
    ic_methods: tuple[str, ...] = ("pearson", "spearman"),  # closed {"pearson","spearman"}, non-empty
    dataset_version_id: str,                        # non-empty fundamentals corpus pin
    market_dataset_version_id: str,                 # non-empty market corpus pin
    spec_version: str = "diagnostics/1",
)
# derived at construction, never supplied:
horizon_days: int                                  # parsed from forward_horizon, >= 1
sorted_ic_methods: tuple[str, ...]                 # canonicalized, sorted, de-duplicated (a set)
```

Construction-time validation (fail closed, `SignalDiagnosticsConfigurationError`): empty
`name`; empty `signal`; `period` not a `MetricPeriod`; `universe` without a
`specification_id`; `schedule` without a `schedule_id` or with an empty date axis;
`forward_horizon` not matching `^[0-9]+d$` or with `n < 1`; `quantiles` not an `int` or
`< 2`; empty `ic_methods`; an `ic_method` not in the closed set `{"pearson","spearman"}` or
duplicated; empty `dataset_version_id`; empty `market_dataset_version_id`; empty
`spec_version`. `ic_methods` is canonicalized and treated as a **set** for identity: order
and duplicate spelling never change the id. Reads no store, no wall clock. `to_dict()` emits
`ic_methods` in its sorted, de-duplicated form and the `period` / `universe` / `schedule` in
their canonical serialized forms.

### 3.2 Nested records

```
ICMethod(StrEnum): PEARSON = "pearson", SPEARMAN = "spearman"      # closed

PerDateIC(
    as_of: str,                                    # UTC-Z instant of the evaluation date
    n_pairs: int,                                  # eligible (signal, forward-return) pairs
    ic: tuple[tuple[str, StatValue], ...],         # (method, IC), sorted by method
    bucket_means: tuple[StatValue, ...],           # q cells, bucket 0 .. q-1, mean fwd return
    top_minus_bottom_spread: StatValue,            # bucket q-1 mean minus bucket 0 mean
)

QuantileProfile(
    bucket_means: tuple[StatValue, ...],           # across-date mean per bucket (q cells)
    mean_spread: StatValue,                         # across-date mean top-minus-bottom spread
)

ICSummary(
    per_method: tuple[tuple[str, ICMethodSummary], ...],   # sorted by method
)
ICMethodSummary(
    mean_ic: StatValue, ic_std: StatValue,
    ic_information_ratio: StatValue,               # mean_ic / ic_std (per period)
    ic_t_stat: StatValue,                          # mean_ic / ic_std * sqrt(n)
    hit_rate: StatValue,                           # fraction of valid dates with IC > 0
    n_valid_dates: int,
)

CoverageSummary(
    per_date: tuple[DateCoverage, ...],            # one per evaluation date, in schedule order
    total_eligible: int, total_dropped_for_signal: int, total_dropped_for_return: int,
)
DateCoverage(as_of: str, resolved_members: int, eligible: int,
             dropped_for_signal: int, dropped_for_return: int)
```

`StatValue` is the UNDEFINED-preserving cell: `StatValue.known("<decimal string>")` **or**
`StatValue.undefined(<DiagnosticUndefinedReason>)`. Exactly one of `value`/`reason` is
populated (enforced at construction). Never a bare float, never silently omitted.

### 3.3 `SignalDiagnostics` (implements `ResearchRecord`)

```
SignalDiagnostics(
    signal_diagnostics_engine_version_id: str,
    diagnostics_spec: dict[str, object],           # the full SignalDiagnosticsSpecification.to_dict()
    boundary_kind: str,                            # "pit" (signal side; SD-2 — not a PIT value)
    dataset_version_id: str,                        # fundamentals corpus pin (re-verified)
    market_dataset_version_id: str,                 # market corpus pin (re-verified)
    schedule_id: str,                              # the evaluation schedule identity
    per_date: tuple[PerDateIC, ...],               # per evaluation date, schedule order
    quantile_profile: QuantileProfile,
    ic_summary: ICSummary,
    coverage: CoverageSummary,
    formula_version: str,                          # "diagnostics-stats/1"
    result_hash: str,                              # canonical JSON over the ordered computed outputs
)

# derived, never stored as state:
diagnostics_id      property -> sha256 folding engine version + spec identity
                                + both corpus pins + result_hash
research_result_id  property -> alias of diagnostics_id  (the ResearchRecord key)
```

- `to_dict()` keys (deterministic, `sort_keys=True`): `diagnostics_id`, `research_result_id`
  (alias so the generic reader keys correctly), and every field above. A KNOWN cell emits
  `value` only; an UNDEFINED cell emits `reason` only.
- `from_dict` is the fail-closed inverse; `diagnostics_id`/`research_result_id` are
  re-derived by their properties, **never read from state**, so `from_dict(to_dict(r))`
  re-emits identical bytes and the same `result_hash`, and a tampered stored id is ignored.
- `.seal(...)` is the identity-computing constructor: it folds the ordered computed-output
  cells (per-date IC + bucket means + spread, then the quantile profile, then the IC
  summary — each tagged by its block so two structurally different records can never
  collide) into `result_hash`, so identity is a pure function of the request + both corpus
  pins + computed answer, never caller-supplied.

**What the model deliberately does NOT hold:** section titles, prose, display order, any
presentation; any copied financial value beyond the computed statistics; any float; any
wall-clock or RNG value; any `Pit*` type or as-of accessor (SD-2).

### 3.4 Closed v1 vocabulary

`DiagnosticUndefinedReason` (closed, 5): `INSUFFICIENT_PAIRS`, `ZERO_SIGNAL_VARIANCE`,
`ZERO_RETURN_VARIANCE`, `EMPTY_BUCKET`, `NO_VALID_DATES`. Extending it is an explicit future
edit that hashes distinctly (a new reason changes the `result_hash`) — never an implicit
fallback.

---

## 4. Formula methods (locked, folded into `diagnostics-stats/1`)

Changing any of these bumps `DIAGNOSTICS_FORMULA_VERSION`, so a value computed under one
method can never be silently reinterpreted under another. All arithmetic runs under an
explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`), never the ambient process
context. `Decimal.sqrt(context)` covers all roots. No float touches any value.

- **Forward return.** For member security `s`, `fwd = P_adj(T+h) / P_adj(T) − 1`, where both
  endpoints are read through the Phase 11 **PIT-gated adjusted view** at the window-end
  `as_of` (`T+h` trading days), `T` and `T+h` being trading-date endpoints of a `PriceAxis`.
  A missing/UNKNOWN endpoint, a non-positive base price, or a delisting inside the window
  with no recovery price → the member is **dropped for return** (SD-4), never zero-filled.
- **Average-rank (Spearman).** Both the signal vector and the forward-return vector are
  converted to ranks over `1..n`; tied values receive the **average** of their contiguous
  positions. Spearman rank IC is the Pearson correlation of the two rank vectors. Ranking
  order is deterministic (value ascending, then `company_id`), so ties never depend on
  iteration order.
- **Population Pearson IC.** `ic = cov(x, y) / (pstd(x) · pstd(y))` with population moments
  (`cov = Σ(xᵢ−x̄)(yᵢ−ȳ)/n`, `pstd = √(Σ(xᵢ−x̄)²/n)`). Zero signal variance →
  `ZERO_SIGNAL_VARIANCE`; zero forward-return variance → `ZERO_RETURN_VARIANCE`; never a
  divide-by-zero. Spearman uses ranks, so a value tie does not by itself make it undefined
  (only a fully constant rank vector — every value identical — is `ZERO_SIGNAL_VARIANCE` /
  `ZERO_RETURN_VARIANCE`).
- **Insufficient pairs.** A date with `< 2` eligible pairs → both IC methods are
  `INSUFFICIENT_PAIRS`; that date contributes no IC to the summary and no bucket means.
- **Quantile buckets (D7).** Members are ordered by (signal value ascending, then
  `company_id`); the member at `0`-based ordinal `i` is assigned `bucket = floor(i · q / n)`
  (clamped to `q−1`). Each non-empty bucket's cell is the arithmetic mean forward return of
  its members; an **empty** bucket (possible when `n < q`) → `EMPTY_BUCKET`. The
  **top-minus-bottom spread** is `bucket_mean[q−1] − bucket_mean[0]`; if either endpoint
  bucket is empty, the spread is `EMPTY_BUCKET`.
- **Quantile profile.** Across dates, each bucket's profile cell is the arithmetic mean of
  that bucket's per-date KNOWN means (dates where the bucket was `EMPTY_BUCKET` are excluded
  from that bucket's average; a bucket KNOWN on no date → `EMPTY_BUCKET`). `mean_spread` is
  the mean of the per-date KNOWN spreads (`INSUFFICIENT_PAIRS` / `EMPTY_BUCKET` dates
  excluded; none KNOWN → `NO_VALID_DATES`).
- **IC summary (per method).** Over the dates where that method's IC is KNOWN:
  `mean_ic = mean(ic)`; `ic_std = pstd(ic)` (population); `ic_information_ratio = mean_ic /
  ic_std` (per period — no annualisation, resolved §1.1); `ic_t_stat = mean_ic / ic_std ·
  √n_valid`; `hit_rate = (#dates with IC > 0) / n_valid`. `n_valid = 0` → every summary cell
  `NO_VALID_DATES` for that method (but the whole run is not raised as long as *some* method
  on *some* date is KNOWN — see §7). `ic_std = 0` → `ic_information_ratio` and `ic_t_stat`
  are `ZERO_RETURN_VARIANCE` (a constant IC series has no dispersion to divide by), never a
  divide-by-zero. `n_valid = 1` → `ic_std = 0` by construction, so the ratio/t-stat are
  likewise `ZERO_RETURN_VARIANCE`; `mean_ic` and `hit_rate` remain KNOWN.

---

## 5. Identity / determinism (locked)

- Domain tag via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): record tag `diagnostics/1`;
  engine tag `diagnostics-engine/1`; formula tag `diagnostics-stats/1`.
- `signal_diagnostics_engine_version_id = sha256(code_version "diagnostics-engine/1",
  config_hash)` where `config_hash =
  sha256("prec=34\x00round=ROUND_HALF_EVEN\x00formula=diagnostics-stats/1")`. Any change to
  the decimal context **or** a formula method yields a new engine id.
- `diagnostics_result_hash = sha256(canonical JSON over the ordered computed-output cells:
  the per-date IC cells + bucket means + spread, then the quantile profile, then the IC
  summary — each tagged by block and reduced to its canonical `(scope, key, method, status,
  value)` form)`. Sensitive to every computed cell.
- `diagnostics_id = sha256`, NUL-joined: `diagnostics/1`,
  `signal_diagnostics_engine_version_id`, `name`, `spec_version`, `signal`, the canonical
  `period.period_key`, the universe `specification_id`, the `schedule_id`, the canonical
  `horizon_days`, `quantiles`, canonical-JSON of the sorted `ic_methods`, both corpus pins
  (`dataset_version_id`, `market_dataset_version_id`), and `diagnostics_result_hash`.
- `research_result_id` aliases `diagnostics_id` (single id).

**Folds (changes identity):** engine-logic + formula + decimal-context version ✔, the full
declared request (name, spec version, signal, period, universe id, schedule id, horizon,
quantiles, sorted IC methods) ✔, **both** corpus pins ✔, the computed statistics (via
`result_hash`) ✔. **Does NOT fold:** the record schema/format version
(`DIAGNOSTICS_RESULT_FORMAT_VERSION` — a container concern), any presentation, wall-clock,
RNG, `id()`, or iteration order (all set-valued inputs are sorted). Phase 16 references raw
corpora **by pin**, not by a sealed artifact's `result_hash`; the pins are content-addressed
`DatasetVersion` ids, so `diagnostics_id` stays sensitive to any corpus change (SD-1).

Same spec + same pinned corpora → same `diagnostics_id` and same bytes on any machine.

---

## 6. PIT semantics, provenance, storage (locked)

- **Signal side is strictly PIT (SD-3).** The signal cross-section at each evaluation date
  `T` is read via `panel_across(..., as_of=T)`, so it uses only data available `≤ T`
  (invariant 29). No future data ever enters the signal side; the engine adds no eligibility
  logic and re-ranks no observation.
- **Forward-return side is the evaluation target, not a PIT input.** The realized return over
  `[T, T+h]` is, by definition, information from after `T`. It is used only to *score* the
  as-of-`T` signal; it is never an input to any decision and is never reusable as an
  as-of-`T` value. Endpoints are read through the Phase 11 PIT-gated adjusted view at the
  **window-end `as_of`** (`T+h`), so both endpoints are eligible and only corporate actions
  available by the window end are applied — pinned via `market_dataset_version_id`,
  reproducible, no revision leak (D4).
- **The result is a distinct forward-looking type (SD-2).** `SignalDiagnostics` is an ex-post
  research statistic. It is **not** a `Pit*` type, exposes **no** as-of accessor, and is
  inadmissible where a PIT signal/value is required — the exact analog of invariant 28.
  `boundary_kind = "pit"` documents that the *signal* was PIT-eligible; it does not claim the
  diagnostic itself is a PIT value.
- **Corpus pins (SD-1).** The engine re-derives the fundamentals `DatasetVersion` (union over
  the universe's source companies via the Phase 7 metric engine) and the market
  `MarketDatasetVersion` (union over the mapped securities via the Phase 11 price engine),
  asserts each equals the spec's declared pin, and fails closed
  (`SignalDiagnosticsConsistencyError`) on any mismatch or on a non-unique normalizer. Both
  pins are folded into `diagnostics_id`, so a changed corpus yields a different id.
- **Provenance.** For every evaluation date the coverage ledger records the resolved-member
  count, the eligible-pair count, and the dropped-for-signal / dropped-for-return breakdown,
  so exclusions are auditable, never silent. Because the signal is a `panel_across` result,
  the diagnostic traces back to the same PIT panel machinery (and thence to canonical facts
  and availability evidence). No copied financial values beyond the computed statistics; the
  diagnostic references corpora by pin.
- **Storage.** Zero new store types; the `ResearchResultStore` writes the record to
  `<root>/research/sha256-<hex>.json` in the existing container, atomic (`indent=2,
  sort_keys=True, ensure_ascii=False`). Write-once and idempotent: re-computing identical
  diagnostics is a byte-identical no-op; a differing payload under an existing id fails
  closed via the store's guard (`FactorConsistencyError`).

---

## 7. Failure / UNDEFINED behavior (locked)

Follows the existing split exactly — **defects raise, data conditions are recorded.**

**Raised** (`SignalDiagnosticsConfigurationError` / `SignalDiagnosticsConsistencyError`):
- Malformed spec: empty `name`/`signal`/`spec_version`/pins; non-`MetricPeriod` `period`;
  `quantiles` non-`int` or `< 2`; empty or out-of-vocabulary or duplicated `ic_methods`;
  malformed `forward_horizon`; a `universe`/`schedule` missing its identity. *(configuration,
  at construction)*
- A non-`SignalDiagnosticsSpecification` argument to `evaluate`. *(configuration)*
- **No valid evaluation dates** — every scheduled date has `< 2` eligible pairs (so every
  IC on every method would be UNDEFINED and the whole record meaningless): raised as a
  configuration defect rather than sealing an all-UNDEFINED record (the Phase 15
  `_MIN_PERIODS` precedent). *(configuration)*
- A corpus pin mismatch or a non-unique fundamentals/market normalizer. *(consistency)*
- A corrupt / non-finite decimal from the corpus. *(raised, never guessed)*

**Recorded as first-class UNDEFINED (never raised, never fabricated):** a member with an
UNDEFINED signal at `T`, or with no computable forward return, is excluded from that date's
pair set and counted in coverage (SD-4). A date with `< 2` pairs → that date's IC is
`INSUFFICIENT_PAIRS`. Zero signal variance → `ZERO_SIGNAL_VARIANCE`; zero forward-return
variance → `ZERO_RETURN_VARIANCE` (Pearson; Spearman only when the rank vector is fully
constant). An empty quantile bucket → `EMPTY_BUCKET`. A per-method summary over zero KNOWN
dates → `NO_VALID_DATES`; a zero-dispersion IC series → `ZERO_RETURN_VARIANCE` for the
ratio/t-stat. There is no divide-by-zero anywhere: a zero denominator becomes a recorded
UNDEFINED, exactly as Phase 7 metrics and Phase 15 analytics do.

---

## 8. Public API (locked)

```python
from quantforge import SignalDiagnosticsSpecification, SignalDiagnostics, Workspace
from quantforge.backtest import RebalanceSchedule  # reused as the eval axis
from quantforge.metrics import MetricPeriod
from quantforge.xbrl.contexts import PeriodType

ws = Workspace.open(root)
spec = SignalDiagnosticsSpecification(
    name="current-ratio-ic",
    signal="current_ratio",
    period=MetricPeriod(
        period_type=PeriodType.INSTANT, period_start=None, period_end="2022-12-31"
    ),
    universe=universe_spec,
    schedule=RebalanceSchedule.month_end_closes("2018-01-31", "2022-12-31"),
    forward_horizon="21d",
    quantiles=5,
    ic_methods=("spearman", "pearson"),
    dataset_version_id=fundamentals_pin,
    market_dataset_version_id=market_pin,
)
diag = ws.signal_diagnostics_engine.evaluate(
    spec
)  # a sealed, write-once SignalDiagnostics
diag.ic_summary  # mean IC, IR, t-stat, hit rate (per method)
diag.quantile_profile  # mean forward return per bucket + spread
diag.research_result_id  # == diag.diagnostics_id (ResearchRecord)

# typed read-back (byte-identical round-trip)
again = ws.research_result_store.read_as(
    diag.research_result_id, SignalDiagnostics.from_dict
)
```

`SignalDiagnosticsEngine` is reached only through `Workspace.signal_diagnostics_engine` (a
lazy, cached, cycle-free `@property` annotated `-> object`; engines are not re-exported at
top level). `evaluate(spec) -> SignalDiagnostics` is the single entry point. No `Company`
method is added (diagnostics span a cross-section, not one filer).

---

## 9. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 16 suite added), deterministic across runs.
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src tests`
  clean (strict).
- Zero runtime dependencies (stdlib `hashlib`/`json`/`dataclasses`/`Decimal`/`re` only); no
  float in any path; no wall-clock/RNG in any identity or value; rank/Pearson IC and
  bucketing are closed-form scalar `Decimal` (no linear-algebra dependency).
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** — the only source edits are the additive
  `Workspace.signal_diagnostics_engine` property/cache line and the `__init__.py`
  re-exports; no edit to any identity/version module or to `backtest/*`, `analytics/*`,
  `panel/*`, `market/*`, or `universe/*`.
- Byte-identical `SignalDiagnostics` round-trip test proves `from_dict` introduces no drift
  and that a tampered stored id is ignored; a `TestDeterminism` double-build proves
  `to_dict()` byte-equality, id sensitivity to each input, and `ic_methods`-order
  invariance.
- SD-1 (pin mismatch fails closed; changed corpus → different id), SD-2 (no `Pit*`
  type / no as-of accessor), SD-3 (post-`T` signal excluded), SD-4 (UNDEFINED/missing
  excluded + counted) each covered by a test.
- Docs updated; `ARCHITECTURE.md` "Cross-sectional signal diagnostics" row flipped to ✅
  only when green.

---

## 10. Test coverage (locked)

New package `tests/diagnostics/` (`__init__.py`, `builders.py`, `test_spec.py`,
`test_compute.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline over the
fictional CIKs `9999999991`/`9999999992` (reusing `tests/backtest/builders.populate` +
`FakeMarketDataProvider`), covering:

- **Construction validation** and `ic_methods` set-canonicalization; horizon parsing; all
  fail-closed spec paths (SPEC).
- Each statistic against hand-computed decimal strings on tiny fixed cross-sections — rank
  IC, Pearson IC, quantile bucket means, top-minus-bottom spread, IC summary — UNDEFINED
  preservation with the right reason, and average-rank tie determinism (COMPUTE).
- `diagnostics_id` folding + `ic_methods`-order-invariance + sensitivity to each input
  (signal, period, universe, schedule, horizon, quantiles, IC methods, engine version,
  either corpus pin, computed answer) (IDENTITY).
- Byte-identical `to_dict`/`from_dict`, id re-derivation, tampered-id ignore (ROUND
  TRIP / PERSISTENCE); write-once idempotent no-op + fail-closed on differing payload.
- **PIT correctness / look-ahead prevention:** a signal made available only *after* `T` is
  excluded at `T` (SD-3); a red-team assertion that the signal side never sees post-`T`
  data.
- **Forward-return honesty (SD-2):** `SignalDiagnostics` exposes **no** `Pit*` / as-of
  accessor and is not accepted anywhere a PIT value is required (type/API boundary).
- **Corpus pin (SD-1):** a mismatched pin fails closed; a different corpus yields a
  different `diagnostics_id`.
- **Fail-closed / undefined (SD-4):** UNDEFINED signal excluded + counted; missing forward
  price excluded + counted; `< 2` pairs → `INSUFFICIENT_PAIRS`; zero variance → the right
  reason; empty bucket → `EMPTY_BUCKET`; no valid dates → config error.
- **Interaction:** reuses Phase 9/10/11 engines unchanged; no Phase 1–15 test regresses
  (WORKSPACE / REPRODUCIBILITY — two independently-populated corpora yield byte-identical
  diagnostics).

No real financial or network data; the architecture does not require it.
