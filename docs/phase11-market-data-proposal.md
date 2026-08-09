# Phase 11 — Point-in-Time Market Data Layer (PROPOSAL)

> **Status: SUPERSEDED — approved and implemented.** Decisions D1–D10 (§21) were
> approved; the normative locked architecture is now
> [phase11-market-data-locked.md](phase11-market-data-locked.md) and the
> implementation lives in `src/quantforge/market/`. This document is retained for
> historical context (the contradiction analysis and the options considered per
> decision); where it and the locked document differ, **the locked document
> governs**.

---

## 1. Executive summary

QuantForge today is an SEC-only, deterministic, point-in-time (PIT) fundamental
research engine. Every existing layer — acquisition (Phase 1), registry (Phase 2),
raw XBRL (Phase 3), canonical facts (Phase 4), availability/PIT (Phase 5),
metrics (Phase 7), factors/universe (Phases 8–9), and the fundamental panel
(Phase 10) — is a deterministic function of an immutable, content-addressed raw
store, gated by a fail-closed public-availability boundary, served as distinct
**PIT** and **REVISED** result types that cannot be confused at the type level.

A backtester (Phase 12) cannot be built honestly today because it needs to answer
**"what was the price of instrument *X* that was actually knowable as of timestamp
*T*?"** — and QuantForge has no price data and no market-data PIT model. Phase 10
deliberately blocked the return-based backtester on exactly this gap
([phase10-panel-locked.md §10–§11](phase10-panel-locked.md)).

This proposal designs the **Market Data Layer**: the price/market-data foundation,
built as *a new source beneath, not through, the existing stack* — exactly as
Phase 10 §11 reserved. The key finding of the contradiction analysis (§3) is that
**a market-data layer can be added without violating a single existing invariant**,
because the data model already anticipated it: the `Source` entity exists precisely
to add non-SEC publishers with their own trust/rules
([data-model.md §4](data-model.md)), the `Security` entity + `security_id` scheme
already separates instruments from filers with ticker-is-never-identity
([data-model.md §4, §11](data-model.md)), and the Phase 5 availability machinery
(`AvailabilityPolicy` / `derive()` / `DatasetVersion` / fail-closed `UNKNOWN`) is
source-agnostic and reusable per-source.

The proposal recommends the **smallest** such layer: canonical daily price/volume
observations for equity instruments, with **corporate actions represented as
first-class immutable records** (not silently baked into an adjusted close),
carried through the same *immutable-raw → derived → PIT* pipeline, served through a
new PIT resolver as distinct `PitPrice` / `RevisedPrice` types, and exposed to
Phase 12 through **one narrow, PIT-only hand-off contract**. It is explicitly *not*
a generic financial-data warehouse, and it builds *none* of the backtester.

---

## 2. Current architecture relevant to Phase 11

The facts below are load-bearing for the design; each is grounded in the existing
source.

**2.1 The immutable content-addressed acquisition store (Phase 1).**
`ArtifactStore` (`src/quantforge/sec/storage.py`) stores raw bytes at
`blobs/<sha256[:2]>/<sha256>` and one provenance record per retrieval at
`meta/<artifact_type>/<sha256>.json`. Writes are atomic (per-PID temp →
`flush` → `os.fsync` → `os.replace`); a blob's name *is* its hash, so it can never
be overwritten with different bytes, identical bytes dedupe, and "a failed download
never appears as a valid immutable artifact." `AcquisitionMetadata` records
`source_url`, `artifact_type`, `sha256`, `retrieved_at` (injected clock),
`http_status`, `user_agent`, `etag`, `last_modified`, `cik`, `accession`. Identity
is **only** the bytes' SHA-256; timestamps are descriptive provenance, never
identity. `ArtifactType` is a `StrEnum` of stable slugs.

**2.2 The provider-neutral network seam (Phase 1).**
The reusable network stack is **not** SEC-specific: `HttpTransport` is a
`typing.Protocol` (`send(HttpRequest) -> HttpResponse`), and
`RetryingHttpClient` / `RateLimiter` take the transport + injected `sleep` / `clock`
/ `monotonic` as constructor parameters. Only `endpoints.py` (URL builders) and the
typed `acquire_*` helpers are SEC-specific; the generic
`SecClient.acquire(url, artifact_type, *, cik=None, accession=None)` and the whole
transport/retry/throttle trio are reusable. Tests inject a fake transport that
satisfies `HttpTransport` structurally and never touch the network.

**2.3 The availability / PIT machinery (Phase 5).**
`src/quantforge/availability/` derives, per filing, a
`(derived_public_availability_timestamp, availability_status, availability_policy_id)`
triple via a **pure function** `derive(evidence, policies)` (`policy.py`).
`AvailabilityStatus` is `VERIFIED` / `DERIVED` / `UNKNOWN`; only the first two are
PIT-eligible; `UNKNOWN` fails closed and is *never* eligible. `AvailabilityPolicy`
is a versioned, form-scoped, era-bounded, declarative "data not code" rule whose
`availability_policy_id` is `sha256(policy_id ∥ policy_version ∥ rule_definition_hash)`.
`PointInTimeResolver` exposes `knowledge_state_as_of(obs_key, as_of) -> PitValue`
(PIT) and `revised_truth(obs_key, dataset_version) -> RevisedValue` (REVISED) — **no
`get_value()`, no default mode** (invariant 27). `PitValue` and `RevisedValue` are
unrelated frozen types (invariant 28); the only bridge is
`RevisedValue.reinterpret_as_pit(resolver, as_of)`, which **re-runs** resolution and
never casts. Naive `as_of` is rejected at the `timestamps.py` choke point
(invariant 15). REVISED resolves at a reproducible *ingestion frontier* (max
availability instant), never a wall-clock read (invariants 21, 30).

**2.4 The versioning trio.**
`TransformationVersion` (parser+normalizer code), `AvailabilityPolicy` (evidence →
availability rule), and `DatasetVersion` (a Merkle-root manifest naming the exact
raw-document ids, fact ids, transformation version, and policy set — the
reproducible snapshot REVISED resolves against). `DatasetVersion.dataset_version_id`
is a Merkle root over tagged, sorted leaves (`tv`/`pol`/`raw`/`fact`), so any change
yields a new id (invariant 19).

**2.5 Identity conventions.**
Two coexist. **(a)** The SEC artifact layer uses a *bare* 64-char hex digest
(`sha256_hex`, no prefix) as blob name. **(b)** Derived-identity layers (Phases 8+)
use the `sha256:`-prefixed, `_SEP = "\x00"` NUL-joined, canonical-JSON
(`sort_keys=True, ensure_ascii=False, separators=(",", ":")`) convention.
`company_id = "cik:" + zero-padded-10-digit CIK`. Store documents are written with
`json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)` atomically.

**2.6 The already-designed `Source` and `Security` entities.**
[data-model.md §4](data-model.md) already defines **`Source`** ("The publisher (SEC
EDGAR today). … modeling it lets us add other public sources later and attach
source-level trust/rules") and **`Security`** ("One company → many securities (share
classes, debt). Tickers/exchanges live here and change over time; they are **not**
identifiers"). [§11](data-model.md) already specifies
`security_id = figi:<FIGI>` when available, else `cik:<CIK>#class:<normalized-class>`,
with the recon caveat that **neither FIGI nor CUSIP is present in EDGAR's APIs**, so
a FIGI-form `security_id` needs an *external* mapping. Company≠Security is
empirically real (JPMorgan: 9 tickers / 1 CIK). These entities are **designed but
unimplemented** — Phase 11 is their first consumer.

**2.7 The composition root and the panel hand-off.**
`Workspace` (`src/quantforge/workspace.py`) wires per-phase stores/façades from one
data root and lazily builds cached engines (`metric_engine`, `factor_engine`,
`panel_engine`) — strictly additive, editing no prior store. Phase 10 exposes
`PitPanel` / `RevisedPanel`; [phase10-panel-locked.md §11](phase10-panel-locked.md)
states verbatim that "**`PitPanel` is the typed hand-off**," "the period axis is a
rebalance schedule," and "a market-data layer plugs in beneath, not through, Phase
10 … they become a *new source* with their **own** PIT-availability model (their own
`AvailabilityPolicy`, their own `DatasetVersion` contribution) — the same
immutable-raw → derived → PIT pipeline."

---

## 3. Contradiction analysis

**Question:** Can a market-data layer be added without violating any existing
invariant or architectural commitment? **Finding: yes — the architecture already
reserved the seams.** Each of the 12 required areas is examined below.

| # | Area | Existing invariant / commitment | Conflict? | Resolution |
|---|------|--------------------------------|:---------:|------------|
| 1 | **PIT correctness** | Data served as it was known at a date; look-ahead is a correctness bug (Principle 4). | **No** | A price observation gets its *own* availability boundary; the same `≤ as_of` predicate applies. §9. |
| 2 | **Availability semantics** | `VERIFIED`/`DERIVED`/`UNKNOWN`; `UNKNOWN` fails closed, never eligible (inv. 8–9). | **No** | Reuse the enum; add a market-data `AvailabilityPolicy` rule kind. A price whose availability can't be defended is `UNKNOWN` → excluded. §9. |
| 3 | **REVISED vs PIT separation** | Distinct methods, no default (inv. 27); distinct types (inv. 28); explicit re-resolve only. | **No** | New `PitPrice` / `RevisedPrice` mirror `PitValue` / `RevisedValue` exactly. §8, D9. |
| 4 | **Provenance** | Every derived value traces to raw bytes + transform (Principle 3). | **No** | Canonical prices carry lineage to the content-addressed raw vendor payload, exactly like `Fact → RawFact → RawDocument`. §15. |
| 5 | **Deterministic content-addressed identity** | `sha256:`-prefixed, NUL-joined canonical JSON (inv. 13, 19). | **No** | Reuse both conventions (raw = bare hex; derived = `sha256:` prefix). §14, D8. |
| 6 | **Immutable derived state** | Derived stores are safe to delete and rebuild byte-identically. | **No** | Canonical price store is derived; rebuilt from immutable raw. §13. |
| 7 | **No look-ahead** | Naive `as_of` rejected (inv. 15); REVISED at reproducible frontier (inv. 21, 30). | **No** | Reuse the Phase 5 `timestamps.py` choke point and frontier concept verbatim. §9. |
| 8 | **Provider-agnostic architecture** | Consistent with the `Source` entity + `HttpTransport` Protocol. | **No** | Canonical model is provider-neutral; a provider adapter maps vendor bytes → canonical. §11, D6. |
| 9 | **Minimal dependencies** | Zero runtime dependencies (Principle 10). | **No** | Reuse stdlib-only transport; offline fake backend for tests. No new dependency. §11, §19. |
| 10 | **Existing Workspace composition** | Additive lazy engines, no prior store edited. | **No** | Add a market root + lazy `price_engine`; edit nothing. §18, D7. |
| 11 | **Phase 10 backtester hand-off** | `PitPanel` typed hand-off; `strategy_version` reserved. | **No** | Phase 11 adds a *second* PIT hand-off (`PitPrice`/price series); `strategy_version` still unset. §17. |
| 12 | **SEC as fundamental-data source** | QuantForge fundamentals come from SEC EDGAR. | **No** | Prices are a **separate source**; fundamentals stay 100% SEC. Market data never rewrites a `Fact`. §5. |

**One genuine tension, resolved, not a contradiction.** [data-model.md §11](data-model.md)
notes FIGI/CUSIP are *not* in EDGAR APIs, so the FIGI-form `security_id` needs an
**external** mapping. This is a data-sourcing gap, not an architectural conflict: the
scheme already provides a fallback form `cik:<CIK>#class:<normalized-class>` that is
derivable from data QuantForge already has. Phase 11 adopts the fallback as the
canonical default and treats FIGI as an *optional external enrichment* (D2), so the
layer is fully functional offline with **zero** dependency on a proprietary
identifier vendor.

**Conclusion.** No invariant must be relaxed, and no existing type, store, or policy
must be edited. Phase 11 is purely additive and mirrors Phase 5 structurally.

---

## 4. Phase 11 scope

Phase 11 delivers the **smallest rigorous Market Data Layer**:

1. A **canonical price-observation model** — per `(instrument, trading date)` a daily
   OHLCV record of **unadjusted** raw prices plus volume, with explicit currency and
   the emitting source (§6, §8).
2. A **canonical instrument identity** (`security_id`, reusing the designed scheme)
   distinct from `company_id`, with effective-dated ticker/exchange history that is
   **never** identity (§7, D2).
3. A **corporate-action model** — splits, dividends, symbol changes, delistings,
   and (structurally) mergers — as **first-class immutable records**, so adjusted
   prices are *derived on demand* and never silently rewrite history (§10, D5).
4. A **market-data availability / PIT model** — each price observation carries its
   own `(observation, availability, effective/trading)` timestamps and a fail-closed
   availability boundary under a market-data `AvailabilityPolicy` (§9, D3/D9).
5. A **provider-neutral acquisition seam** — the canonical model depends on no single
   vendor; a provider adapter (and an offline fake backend for tests) maps vendor
   bytes → canonical (§11, §12, D6).
6. An **immutable content-addressed raw store + derived canonical store**, reusing
   the Phase 1 storage pattern; **no database** (§13, D7).
7. **Deterministic content-addressed identities and a market-data `DatasetVersion`
   contribution** for reproducible REVISED resolution (§14, D8).
8. A **narrow, PIT-only Phase 12 hand-off contract** — "the price of instrument *X*
   knowable as of *T*" and a price *series* over a declared date axis — with **no
   strategy, portfolio, weighting, or performance logic** (§17, D10).

---

## 5. Explicit non-goals

Phase 11 explicitly does **not** do the following (kept out unless the contradiction
analysis proved them unavoidable — none did):

- **No backtesting, portfolio construction, strategy weighting, rebalancing,
  optimization, alpha/return evaluation, transaction-cost modeling, or performance
  analytics.** `strategy_version` stays unset (data-model §9). These are Phase 12+.
- **No investment recommendations, UI, or website deployment.**
- **No intraday / tick / order-book / quote data.** Daily bars only (D1); a finer
  grain is a future axis (§22), not this phase.
- **No real-time or streaming feeds.** Historical, reproducible bars only.
- **No derivatives, options chains, futures curves, FX cross-rates, or fixed-income
  analytics.** Equity instruments only (D1).
- **No market data as a fundamentals source.** Prices never rewrite, override, or
  merge into a canonical SEC `Fact`. Fundamentals remain 100% SEC (contradiction
  area 12).
- **No adjusted-close-as-truth.** Adjusted prices are a *derived view* over
  first-class corporate actions, never the stored canonical value (D4/D5).
- **No new identifier system.** Instrument identity reuses the *already-designed*
  `security_id` scheme (D2); ticker is never identity.
- **No database.** Compute-on-demand + file sidecars, mirroring every prior phase
  (D7).
- **No bundled real market data.** Principle 8 ("no fabricated financial data; never
  ship example data that could be mistaken for real market data") is honored: tests
  use an obviously-synthetic offline fake backend (§19).

---

## 6. Market-data domain model

The layer introduces the following canonical entities. Each mirrors an existing
entity's role in the SEC stack, keeping the mental model uniform.

| Market-data entity | Mirrors (SEC) | Role |
|--------------------|---------------|------|
| **`MarketDataSource`** | `Source` | The publisher/vendor of the bytes (e.g. an exchange feed, a data vendor). A `Source` row with source-level trust/rules — the entity [data-model §4](data-model.md) reserved. |
| **`Instrument`** (a `Security`) | `Security` | The tradable instrument, keyed by `security_id`; owns effective-dated ticker/exchange/security-type history (never identity). §7. |
| **`RawMarketDocument`** | `RawDocument` | Immutable content-addressed vendor bytes exactly as fetched, with retrieval provenance. §13. |
| **`RawPriceObservation`** | `RawFact` | The bar **exactly as the vendor reported it** (raw field strings, raw currency, raw adjustment flags), before normalization. Enables re-normalization without re-fetching. |
| **`PriceObservation`** (canonical) | `Fact` | The normalized daily OHLCV bar for `(security_id, trading_date)` in a stated currency — **unadjusted** (D4). §8. |
| **`CorporateAction`** | *(new, same pattern)* | A first-class immutable split / dividend / symbol-change / delisting / (merger) record with its own availability. §10. |
| **`MarketAvailabilityPolicy`** | `AvailabilityPolicy` | Versioned, era-bounded, declarative rule mapping a bar's evidence → availability timestamp + status. §9. |
| **`MarketDatasetVersion`** contribution | `DatasetVersion` | The market-data leaves (raw doc ids, observation ids, action ids, policy ids) that extend the reproducible snapshot manifest. §14. |

`PriceObservation` is keyed by an `obs_key`-analogue,
`price_obs_key = (security_id, trading_date, field)` where `field ∈ {open, high, low,
close, volume}`, so the Phase 5 resolver's per-key selection semantics transfer
directly (a per-field key makes a vendor's partial correction of a single field a
clean, independently-resolvable observation).

---

## 7. Instrument identity

**Decision D2 (see §21).** QuantForge **does** need a canonical instrument identity
distinct from `company_id`, and it **already has one designed**:
`security_id` ([data-model §4, §11](data-model.md)).

- **Canonical form (default):** `security_id = cik:<CIK>#class:<normalized-class>`.
  Derivable entirely from data QuantForge already resolves (the CIK) plus a
  normalized share-class label. Fully offline, no vendor dependency.
- **Preferred form when available:** `security_id = figi:<FIGI>` — stable across
  ticker changes, but requires an **external** mapping (FIGI is not in EDGAR APIs).
  Treated as *optional enrichment*, never required for the layer to function (D2).
- **Relationships.**
  `Company (cik:…) 1───∞ Security (security_id)` — one filer, many instruments
  (JPMorgan: 9 tickers / 1 CIK). A `PriceObservation.security_id` foreign-keys to a
  `Security`, which foreign-keys to a `Company`. `company_id` remains the fundamental
  anchor; `security_id` is the market-data anchor; a metric/panel that wants to join
  fundamentals to prices does so through the `Company 1─∞ Security` edge.
- **Ticker is never identity.** Tickers and exchanges live on the `Security` as
  **effective-dated history rows** (the `EntityHistory` pattern already noted in
  [data-model §4](data-model.md)). A ticker change (AAPL splits, FB→META,
  reused/recycled tickers across issuers) is a new history row, **not** a new
  identity and **not** a mutation. This directly reuses the Phase-1 `TickerMap`
  finding that a ticker can map to *multiple* CIKs and must fail closed
  (`AmbiguousSymbolError`) rather than silently pick one — the market-data layer
  inherits that discipline: a historical price is bound to a `security_id`, so a
  later ticker reuse can never retroactively re-point old bars.
- **Delisting** is an effective-dated terminal event on the `Security` (a
  `CorporateAction`, §10), not a deletion — the instrument and its history remain
  addressable (no survivorship bias, per the README promise).

This makes historical instrument identity **stable under ticker churn**, satisfying
the requirement "handle ticker changes without breaking historical identity" and the
constraint "do not use ticker as the canonical identity."

---

## 8. Price observation model

A canonical `PriceObservation` is the normalized daily bar. Design choices:

- **Grain:** one **daily** bar per `(security_id, trading_date)` (D1). `trading_date`
  is the exchange session date (the *effective/trading* timestamp, §9).
- **Fields:** `open`, `high`, `low`, `close`, `volume` — **OHLCV** (D1 sub-decision).
  *Justification for OHLC, not close-only:* a backtester needs intraday extremes for
  honest fill/slippage assumptions (a limit or stop can only be assumed filled if the
  day's range crossed it), and close-only silently forecloses that. Volume is
  required for liquidity screens and is cheap. OHLCV is the smallest set that does not
  prematurely constrain Phase 12; anything finer (VWAP, bid/ask) is deferred (§22).
- **Values are exact decimals**, serialized as strings, under a pinned decimal
  context — mirroring the metrics layer's exact-`Decimal` discipline. No float
  arithmetic enters identity or comparison.
- **Currency is explicit** on every bar (a bar without a defensible currency is a
  defect, not a guess).
- **Unadjusted (raw) prices are the canonical stored value (D4).** The stored
  `close` is the price as it printed on `trading_date`. **Adjusted** prices (for
  splits/dividends) are computed **on demand** by composing the immutable
  `CorporateAction` records (§10) over the *unadjusted* series — never stored as the
  canonical value, never overwriting it. This is the single most important
  correctness choice in the layer (rationale in §10 and D4/D5).
- **Missing/undefined is first-class.** A requested `(security_id, trading_date)` the
  source never reported (holiday, pre-listing, post-delisting, halt) yields a
  first-class `UNDEFINED`/absent cell with a reason — never zero, never
  forward-filled, never imputed (Principle 8; mirrors Phase 10 `UNDEFINED`).

---

## 9. Availability / PIT semantics

This is the heart of the layer and mirrors Phase 5 exactly. **A historical price
must not become eligible before the system's defined availability boundary.**

**Four timestamps per bar** (mirroring the four temporal states of
[data-model §2/§PA](data-model.md); the Phase 5 `FilingEvidence` has the analogous
anchors):

| Timestamp | Meaning | Role |
|-----------|---------|------|
| **`trading_date` (effective)** | The exchange session the bar describes. | The economic date. **Never** an availability lower bound (a close is not knowable *during* its own session). |
| **`observation_timestamp`** | When the vendor's record for the bar was stamped/observed. | Descriptive evidence. |
| **`availability_timestamp` (derived)** | When the bar first became *knowable to a researcher* under policy. | **The only PIT-eligible boundary.** |
| **`retrieved_at`** | Phase-1-style retrieval time of the raw vendor bytes. | An **upper bound** on availability (invariant 11 analogue), joined only at derivation. |

**Availability derivation (D3), a pure function.** A market-data
`AvailabilityPolicy` (own `policy_id`, e.g. `market-eod-std`, own `policy_version`,
era-bounded, own declarative rule) maps a bar's evidence → `(availability_timestamp,
availability_status)`. The initial provisional rule: **an end-of-day bar for session
`D` becomes available no earlier than the exchange close of `D` plus a policy-defined
publication lag** (EOD data is disseminated after the close, often the same evening
or next morning). The derived instant is **floored at the session close** (a bar can
never be knowable before its own session ends — the market-data analogue of Phase 5
invariant 10, "never before acceptance") and **capped at `retrieved_at`** (invariant
11 analogue). Anything that cannot be defended → `UNKNOWN` → **excluded** (fail-closed
invariants 8–9). "Round LATER on uncertainty, never earlier."

**Status semantics** reuse `AvailabilityStatus`:
- `VERIFIED` — direct dissemination evidence from the source (a publication timestamp
  the policy trusts). Dormant in v1 unless a source supplies it.
- `DERIVED` — computed from session close + policy publication lag. The v1 default.
- `UNKNOWN` — undatable → never eligible.

**Two modes, no default (D9, invariant 27).** A new `MarketPointInTimeResolver`
mirrors `PointInTimeResolver`:
- `price_as_of(price_obs_key, as_of) -> PitPrice` (PIT). Requires a **timezone-aware**
  `as_of`; a naive instant is rejected at the **same Phase 5 `timestamps.py` choke
  point** (invariant 15) — the market-data layer imports and reuses it, it does not
  re-implement time handling.
- `revised_price(price_obs_key, dataset_version) -> RevisedPrice` (REVISED). Resolves
  at the reproducible **ingestion frontier** (max availability instant across
  eligible market observations), never a wall-clock read (invariants 21, 30).

**Restatement / vendor correction semantics.** Vendors correct historical bars.
Because raw bytes are immutable and content-addressed, a correction is a *new* raw
document and a *new* observation with its own availability — the resolver's total-order
selection (availability desc → observation desc, mirroring Phase 5 §6.3) picks the
bar that was knowable at `as_of`. PIT therefore reproduces "the price as it was known
then," including *pre-correction* values; REVISED reproduces the latest corrected
value at the pinned snapshot. **No default mode is introduced** — this matches the
existing architecture (the requirement's explicit caution). This is exactly the
`PitValue`/`RevisedValue` behavior, one domain over.

---

## 10. Corporate-action model

**This section answers the required deep question and does not assume adjusted close
is sufficient.**

**Why first-class corporate actions are mandatory for a correct backtester.** An
adjusted close silently folds *every* split and dividend to date into a single number.
Three failures make it unsound as the *stored* canonical value:

1. **Silent historical rewriting.** Every new dividend/split changes *all* prior
   adjusted closes. Two backtests run on different days would see different history
   for the *same* past date — a direct violation of reproducibility (Principle 6) and
   of the immutability the whole system rests on. The adjusted series is not
   point-in-time: it encodes *future* actions into *past* prices, which is textbook
   look-ahead.
2. **Loss of the raw truth.** Return, dividend-yield, and total-return computations
   need the *unadjusted* price and the *action* separately. An adjusted close cannot
   be inverted without the action history it destroyed.
3. **Ambiguity of adjustment convention.** Vendors differ (dividend-adjusted vs
   split-only; adjustment on ex-date vs pay-date). Storing "an adjusted close" bakes an
   opaque, unversioned transformation into the system of record — the exact opacity
   QuantForge exists to eliminate.

**The model.** A `CorporateAction` is a first-class immutable record (mirroring
`Fact`), one per event, carrying its own availability (§9) so it, too, is PIT-gated:

| Action kind | Key fields (illustrative) | Backtester need |
|-------------|---------------------------|-----------------|
| **Split** | `security_id`, `ex_date`, `ratio` (exact Decimal) | Adjust share counts / price continuity. |
| **Dividend** | `security_id`, `ex_date`, `pay_date`, `amount`, `currency` | Total-return; dividend reinvestment. |
| **Symbol change** | `security_id`, `effective_date`, `old_ticker`, `new_ticker` | Ticker history (§7), not identity. |
| **Delisting** | `security_id`, `effective_date`, `reason` | Terminal event; survivorship-bias-free. |
| **Merger / acquisition** | `security_id`, `effective_date`, successor `security_id`, terms | **Structurally represented** (the record exists and is addressable); the *return-treatment* of a merger is a Phase 12 concern, not modeled here. |

**Adjusted prices are a derived, versioned view.** Given the immutable unadjusted
series + the immutable action history, an *adjustment function* (pure, versioned by a
`TransformationVersion`-analogue, PIT-gated so only actions **knowable as of `as_of`**
are applied) computes an adjusted series **on demand**. Because it consumes only
`≤ as_of`-eligible actions, it **cannot introduce look-ahead** — the same argument
Phase 10 uses for derivations (§7 of the locked spec). Same inputs + same adjustment
version ⇒ identical adjusted series, reproducibly, forever.

**What this preserves:** the raw truth (unadjusted prints), reproducibility (past is
immutable; adjustments are a pure function of pinned, PIT-eligible actions), and
auditability (the adjustment convention is an explicit, versioned transform, not an
opaque vendor number). This is why the layer represents splits/dividends/
symbol-changes/delistings **directly** (D5) rather than trusting adjusted close (D4).

---

## 11. Provider abstraction

**Decision D6.** The canonical model is **provider-neutral**; the core depends on
**no** single vendor (not Yahoo, Alpha Vantage, Polygon, Bloomberg, Nasdaq, or any
other).

- **The seam already exists.** Reuse the Phase 1 `HttpTransport` Protocol +
  `HttpRequest`/`HttpResponse` + `RetryingHttpClient` + `RateLimiter` verbatim. They
  are not SEC-specific; only URL builders and typed helpers are.
- **A `MarketDataProvider` Protocol** (mirroring `TickerClient`'s narrow-Protocol
  style) defines the vendor-facing capability, e.g.
  `fetch_daily_bars(security, date_range) -> RawMarketDocument` and
  `fetch_corporate_actions(security, date_range) -> RawMarketDocument`. A concrete
  adapter (added later, outside core) implements it for one vendor and maps that
  vendor's bytes → canonical `RawPriceObservation` / `CorporateAction`. **The
  canonical layer never imports a provider.**
- **Source-level trust lives on `MarketDataSource`** (the `Source` entity's reserved
  purpose): a source can declare whether its dissemination evidence is trusted
  (`VERIFIED` vs `DERIVED`), its default currency, its calendar, etc. — as *policy
  data*, not code.
- **Zero new runtime dependencies (Principle 10).** The stdlib `urllib`-based
  transport already ships; no vendor SDK enters core. A vendor adapter that needs one
  is an optional extra, never a core dependency.
- **Offline by construction for tests (§19):** an in-repo **fake/synthetic**
  `MarketDataProvider` returns obviously-non-real bars, so the whole layer is testable
  with no network and no risk of shipping data mistakable for real (Principle 8).

---

## 12. Acquisition model

Mirrors Phase 1 exactly, provider-neutrally:

1. A provider adapter builds an `HttpRequest`, sends it through the injected
   `RetryingHttpClient` (retry/backoff/throttle, injected `sleep`/`clock` for
   deterministic tests), and receives raw vendor bytes.
2. The bytes are stored as an immutable content-addressed `RawMarketDocument` (§13)
   with `AcquisitionMetadata`-style provenance (`source_url`, a market-data
   `ArtifactType` slug, `sha256`, injected `retrieved_at`, `http_status`,
   `user_agent`, `etag`/`last_modified`, `security_id`). Identity is the bytes' hash;
   timestamps are provenance, never identity.
3. Conditional-request revalidation (`If-None-Match`/`If-Modified-Since`) and 304
   cache reuse work the same way, so repeated resolution is served offline from cache.
4. A deterministic canonicalizer parses `RawMarketDocument` → `RawPriceObservation` /
   `CorporateAction` → canonical `PriceObservation`, with full lineage — no re-fetch
   needed to re-normalize under a new transformation version.

No wall-clock, RNG, or host-tz dependence enters identity (invariant 13).

---

## 13. Storage model

**Decision D7. Smallest architecture that preserves provenance + reproducibility;
no database.**

Evaluated options: *(a)* compute-on-demand only, *(b)* persist raw only, *(c)*
persist raw + derived canonical, *(d)* immutable content-addressed artifacts, *(e)*
reuse the existing acquisition store, *(f)* a new `MarketDataStore`, *(g)* introduce a
DB. **Recommendation: (d)+(e)+(f)-as-thin-derived** — the same two-tier shape every
prior phase uses:

- **Raw tier — reuse the Phase 1 `ArtifactStore` pattern verbatim.** Content-addressed
  bytes at `blobs/<sha256[:2]>/<sha256>` with per-retrieval metadata. Whether this is
  the *same* `ArtifactStore` instance under `<root>/sec/` or a sibling
  `<root>/market/raw/` is a wiring detail (D7 sub-choice); the recommendation is a
  **sibling market-data root** so the SEC acquisition tree stays exactly as-is and the
  two sources remain cleanly separable — but the store *class* and atomic-write code
  are reused, not reimplemented.
- **Derived tier — a thin `MarketDataStore`** for canonical `PriceObservation` /
  `CorporateAction` / `Instrument` history, mirroring `AvailabilityStore`: one JSON
  file per instrument (e.g. `market/canonical/security-<slug>.json`), written
  atomically (temp → `flush` → `os.fsync` → `os.replace`), `sort_keys=True`,
  deterministic ordering, no wall-clock/RNG. Derived state — **safe to delete and
  rebuild byte-identically** from the immutable raw tier.
- **No DuckDB/Parquet, no Postgres.** [data-model §10](data-model.md) lists DuckDB as
  a *future* recommendation, but every implemented phase "introduces no database," and
  Phase 10 explicitly stays compute-on-demand. Phase 11 follows suit: adjusted prices,
  returns, and series are **computed on demand** from the pinned inputs (D4/D5), so no
  materialized analytical store is needed yet. A transparent cache keyed by a
  content-addressed id can be added later precisely because everything is a pure
  function of the pins. "Do not introduce a database unless the existing architecture
  makes it necessary" — it does not.

Directory layout (additive to the Workspace root; §18):

```
<root>/sec/          # Phase 1 SEC artifacts (UNCHANGED)
<root>/registry/     # Phase 2 (UNCHANGED)
<root>/canonical/    # Phase 4 (UNCHANGED)
<root>/availability/ # Phase 5 (UNCHANGED)
<root>/research/     # Phase 8 ResearchResult sidecar (UNCHANGED)
<root>/market/       # Phase 11 — NEW
    raw/             #   immutable content-addressed vendor bytes
    canonical/       #   derived PriceObservation / CorporateAction / Instrument
    availability/    #   derived market-data availability (per instrument)
```

---

## 14. Deterministic / content-addressed identity

**Decision D8.** Reuse both existing conventions (§2.5):

- **Raw market documents:** bare-hex content addressing (`sha256_hex` of the bytes),
  exactly like Phase 1 — the blob name *is* its hash.
- **Derived market identities:** the `sha256:`-prefixed, `_SEP = "\x00"` NUL-joined,
  canonical-JSON convention. Proposed ids:

```
price_observation_id  = sha256( market_transformation_version_id ∥ security_id
                                ∥ trading_date ∥ currency ∥ field ∥ value )
corporate_action_id   = sha256( market_transformation_version_id ∥ security_id
                                ∥ action_kind ∥ ex_date ∥ canonical action payload )
market_availability_policy_id
                      = sha256( policy_id ∥ policy_version ∥ rule_definition_hash )   # Phase-5 shape
adjusted_series_id    = sha256( adjustment_version ∥ security_id ∥ boundary_key
                                ∥ ordered unadjusted obs ids ∥ ordered action ids )
```

- **`MarketDatasetVersion` contribution.** Market-data leaves extend the Merkle-root
  manifest with tagged, sorted leaves (`mktraw`/`price`/`action`/`mktpol`), so any
  change to the market inputs yields a new `dataset_version_id` (invariant 19).
  REVISED market queries resolve against a pinned snapshot exactly like Phase 5.
- **Guarantee:** same inputs + same versions + same boundary ⇒ identical ids and
  identical values, on any machine, independent of order/wall-clock/cache
  (invariant 13). Hashing is canonical JSON with sorted keys; ordering is a declared
  total order; no RNG, no wall-clock reads.

---

## 15. Provenance

Every canonical market value traces to raw bytes and the transform that produced it
(Principle 3), mirroring `Fact → RawFact → RawDocument → SEC bytes`:

```
PriceObservation ─▶ RawPriceObservation ─▶ RawMarketDocument ─▶ vendor bytes (content-addressed)
       │                                                              │
       ├─ market_transformation_version_id (normalizer)              └─ AcquisitionMetadata (source_url, retrieved_at, http_status, etag…)
       ├─ security_id ─▶ Security ─▶ Company (cik:…)
       └─ market_availability_policy_id ─▶ MarketAvailabilityPolicy
CorporateAction ─▶ (same lineage)
AdjustedSeries ─▶ { ordered unadjusted PriceObservation ids, ordered CorporateAction ids, adjustment_version, boundary }
```

A `PitPrice` / `RevisedPrice` carries the full chain: winning observation id → raw
observation → raw document → vendor bytes, plus the availability policy, the discarded
candidates (corrections that lost the total-order selection), and the boundary — so a
price is as auditable as a fundamental fact. This maps onto the [data-model §9](data-model.md)
`ResearchResult` the same way panels do: `dataset_version_id`,
`transformation_version_id`, `availability_policy_ids`, `as_of_timestamp`,
`query_params`, `result_hash`; `strategy_version` **absent** (reserved for Phase 12).

---

## 16. Error / failure semantics

Mirrors the Phase 5 exception discipline (a small hierarchy rooted at a
`MarketDataError`), separating **data conditions** (first-class cells) from
**configuration defects** (exceptions):

- **Data conditions → first-class `UNDEFINED`/absent, never exceptions:** a bar the
  source never reported; a bar whose availability is `UNKNOWN` (fail-closed,
  excluded); a pre-listing/post-delisting/halt date. Recorded with a reason, never
  dropped, never imputed (Principle 8).
- **Configuration defects → raise:** naive `as_of` (`ModeError`, reused Phase 5 choke
  point); no explicit mode chosen; overlapping/uninterpretable market
  `AvailabilityPolicy` scopes (`PolicyConfigurationError`-analogue); an empty or
  malformed date axis; a currency mismatch within a series; a "revised" query where a
  PIT boundary is required.
- **Acquisition failures fail closed:** a hash mismatch or partial download never
  becomes a valid immutable artifact (reused Phase 1 guarantee); a vendor 4xx/5xx is
  surfaced, not silently swallowed.
- **Ambiguous instrument resolution fails closed:** a ticker that maps to multiple
  `security_id`s raises rather than guessing (reused `AmbiguousSymbolError`
  discipline, §7).

---

## 17. Backtester hand-off contract

**Decision D10. Define exactly what Phase 12 needs from Phase 11 — and nothing more.**

Phase 12 must be able to ask **"give me the price of instrument *X* that was actually
knowable as of timestamp *T*"** without Phase 11 implementing any strategy, portfolio,
weighting, or performance logic. The contract is deliberately tiny and **PIT-only**:

```
# Single point-in-time price (the core question):
price_as_of(security_id, as_of, *, field=close) -> PitPrice        # KNOWN (value+provenance) or UNDEFINED(reason)

# A PIT price series over an explicit, content-addressed date axis
# (the axis IS a rebalance schedule — phase10-panel-locked §11):
price_series_as_of(security_id, date_axis, as_of) -> PitPriceSeries # one PIT cell per date, UNDEFINED-preserving

# Adjusted (split/dividend) view, PIT-gated over knowable-as-of-T actions only:
adjusted_series_as_of(security_id, date_axis, as_of, *, adjustment) -> PitPriceSeries
```

Design commitments that make the hand-off safe and future-proof:

- **`PitPrice` is the typed hand-off** — mirroring `PitPanel`. A future backtester's
  signature consumes `PitPrice` / `PitPriceSeries` and **structurally refuses**
  `RevisedPrice` (D9, invariant 28). The look-ahead safety boundary is a type, not a
  convention.
- **The date axis is the rebalance schedule** — Phase 12's rebalance dates map
  directly onto a declared, content-addressed date axis, reusing the Phase 10
  `PeriodAxis` philosophy (explicit, pure-of-wall-clock, versioned into identity). No
  new time model.
- **Fundamentals ⋈ prices** happen through the `Company 1─∞ Security` edge (§7), so a
  Phase 12 strategy can align a `PitPanel` (fundamentals, keyed by `company_id`) with a
  `PitPriceSeries` (prices, keyed by `security_id`) on a shared as_of/axis.
- **`strategy_version` stays unset.** Phase 11 fills the market-data pins of the
  `ResearchResult`; the strategy pin remains reserved for Phase 12 (data-model §9), so
  Phase 12 cites the prices it consumed with **no schema change** — exactly the seam
  Phase 10 §11 promised.
- **Explicitly *not* in the contract:** returns aggregation, portfolio NAV, weighting,
  turnover, transaction costs, benchmarks, or any performance statistic. Those are
  Phase 12. Phase 11 stops at "the knowable price/series."

---

## 18. Workspace / API integration

Strictly additive, mirroring how Phases 7/8/10 extended the Workspace:

- **`Workspace.open()`** wires a new `<root>/market/` tree (raw + canonical +
  availability) alongside the existing trees. No existing store is touched; the SEC
  acquisition tree is byte-for-byte unchanged (contradiction area 10).
- **A lazy, cached `Workspace.price_engine` property** (import-on-first-use to avoid a
  module-load cycle, exactly like `metric_engine`/`panel_engine`) builds a
  `PriceEngine` that composes the market resolver, the canonical market store, and the
  instrument resolver. A workspace that never touches prices pays nothing.
- **Curated top-level exports** keep the PIT/REVISED distinction visible at the import
  site: `from quantforge import PitPrice, RevisedPrice`;
  `from quantforge.market import PriceEngine, PriceAxis, MarketDataProvider`.
- **No default-mode accessor** (invariant 27 at the front door): there is
  `price_as_of(...)` and `revised_price(...)`, never a mode-guessing `price()`.
- **`Company` / `Security` convenience (optional, thin).** A `Company` may expose
  `securities()` (its instruments) and delegate per-instrument price accessors, but
  the cross-instrument/matrix surface stays engine-only (it spans instruments), just as
  the Phase 10 cross-sectional matrix is engine-only.

---

## 19. Testing strategy

Mirrors the offline, deterministic testing already used throughout:

- **Offline by construction.** All tests inject a **synthetic** `MarketDataProvider`
  and/or fake `HttpTransport` (the Phase 1 structural-Protocol pattern). No test
  touches the network. Injected `sleep`/`clock`/`monotonic` make retry/throttle
  deterministic and sleepless.
- **No fabricated real data (Principle 8).** Fixture bars are obviously synthetic
  (round numbers, a fictional ticker like `TEST`/`ZZZZ`) so nothing could be mistaken
  for real market data; nothing real is committed to the repo.
- **PIT correctness tests:** a corrected/late bar becomes eligible only at/after its
  derived availability boundary; a naive `as_of` raises `ModeError`; `UNKNOWN`
  availability is excluded; a bar is never eligible before its session close.
- **Corporate-action tests:** adjusted series is a pure function of PIT-eligible
  actions; a *future* (not-yet-knowable) split does not alter a past adjusted price at
  an earlier `as_of` (look-ahead guard); unadjusted canonical values never change.
- **Determinism/identity tests:** same inputs ⇒ identical `price_observation_id` /
  `adjusted_series_id` / `MarketDatasetVersion`; ordering is total; re-deriving from
  raw reproduces the canonical store byte-identically.
- **Identity tests:** ticker reuse across issuers fails closed; a symbol change is a
  new history row, not a re-pointed identity; delisting preserves history.
- **Quality gate:** full `uv run` test suite + `ruff` + `mypy`, matching the existing
  bar (Principle 7 — anything affecting PIT integrity is covered).

---

## 20. Security / data-integrity considerations

- **No secrets in source control (Principle 9).** A vendor API key lives only in a
  git-ignored `.env` and is read through the injectable-config pattern
  (`SecConfig.from_env(environ=...)` analogue); it never enters identity, provenance,
  or the repo.
- **Immutable system of record.** Raw vendor bytes are append-only and
  content-addressed; a hash mismatch fails closed (a bad download never becomes a
  valid artifact). Canonical/adjusted data is derived and rebuildable.
- **No silent historical rewriting.** The corporate-action model (§10) is the primary
  data-integrity safeguard: adjusted prices are a versioned, PIT-gated *view*, so the
  stored past is immutable and reproducible.
- **Provenance is complete and auditable.** Every price traces to bytes + transform +
  policy; the adjustment convention is an explicit versioned transform, not an opaque
  vendor number.
- **Lawful, rate-limited acquisition.** The reused throttle/retry stack respects
  `Retry-After` and a configured max RPS; a provider adapter must carry an identifying
  User-Agent, matching the SEC-client discipline.
- **Licensing note.** Market data is frequently license-restricted; the layer stores
  only what a source's terms permit and records the source, but license *enforcement*
  is an operational concern flagged here, not code in this phase.

---

## 21. Proposed decisions requiring approval

Each decision: **question → viable options → recommendation → reason → architectural
consequence.** These are the locks that need explicit sign-off before implementation.

**D1 — Supported market-data scope.**
*Question:* What data grain and asset class is in scope? *Options:* (a) daily OHLCV,
equities only; (b) daily OHLCV + intraday; (c) multi-asset (options/futures/FX);
(d) close-only. *Recommendation:* **(a) daily OHLCV, equities only.** *Reason:* the
smallest set that lets Phase 12 make honest fill/liquidity assumptions without
over-building; OHLC (not close-only) is needed for stop/limit fills, volume for
liquidity. *Consequence:* one daily `PriceObservation` per `(security_id,
trading_date)`; intraday/multi-asset are future axes (§22), added as new versions
without changing existing ids.

**D2 — Instrument identity.**
*Question:* Does QuantForge need a canonical `instrument_id` separate from
`company_id`, and what is its form? *Options:* (a) reuse the designed `security_id`
(FIGI-preferred, `cik#class` fallback); (b) invent a new id; (c) use ticker.
*Recommendation:* **(a), with `cik:<CIK>#class:<normalized-class>` as the offline
default and `figi:<FIGI>` as optional external enrichment.** *Reason:* the scheme is
already designed ([data-model §4, §11](data-model.md)), works offline with no vendor
dependency, and keeps ticker as effective-dated history, never identity. *Consequence:*
`Company 1─∞ Security`; historical identity is stable under ticker churn; FIGI mapping
is optional, not a blocking dependency. (c) is rejected outright (the requirement's
explicit constraint).

**D3 — PIT availability semantics.**
*Question:* When does a historical bar become PIT-eligible? *Options:* (a) at session
close; (b) at session close + policy publication lag, floored at close, capped at
`retrieved_at`, fail-closed to `UNKNOWN`; (c) at `retrieved_at`. *Recommendation:*
**(b).** *Reason:* mirrors Phase 5 exactly — a bar is not knowable before its session
ends (analogue of "never before acceptance"), EOD data disseminates after close with a
lag, and undatable bars must fail closed. *Consequence:* a market `AvailabilityPolicy`
with a publication-lag rule; the same `≤ as_of` eligibility predicate and total-order
selection as Phase 5.

**D4 — Adjusted vs unadjusted price representation.**
*Question:* What is the canonical *stored* price? *Options:* (a) unadjusted, adjust on
demand; (b) adjusted close as canonical; (c) store both. *Recommendation:*
**(a) unadjusted is canonical; adjusted is a derived, versioned, PIT-gated view.**
*Reason:* an adjusted close silently rewrites history on every new action (violates
reproducibility + immutability + is look-ahead). *Consequence:* requires the
first-class corporate-action model (D5); adjusted series computed on demand from pinned
actions.

**D5 — Corporate actions.**
*Question:* Must splits/dividends/symbol-changes/delistings/mergers be represented
directly? *Options:* (a) yes, first-class immutable records; (b) no, rely on adjusted
close. *Recommendation:* **(a) first-class, immutable, PIT-gated records** (mergers
represented structurally; return-treatment deferred to Phase 12). *Reason:* the only
representation that preserves the raw truth, reproducibility, and an auditable
adjustment convention (§10). *Consequence:* a `CorporateAction` entity with its own
availability and provenance; adjustment is a versioned pure function.

**D6 — Provider abstraction.**
*Question:* How does the core stay provider-neutral? *Options:* (a) a
`MarketDataProvider` Protocol + adapters outside core, reusing the Phase 1 transport;
(b) hard-code one vendor. *Recommendation:* **(a).** *Reason:* zero new runtime
dependencies, offline-testable, and the `Source` entity already reserves source-level
trust. *Consequence:* the canonical model imports no vendor; a fake provider powers
tests; adapters are optional extras.

**D7 — Acquisition / storage.**
*Question:* Where and how is market data stored? *Options:* (a) reuse content-addressed
raw store + thin derived file sidecars, no DB; (b) DuckDB/Parquet; (c) a relational DB.
*Recommendation:* **(a), under a sibling `<root>/market/` tree.** *Reason:* every
implemented phase introduces no DB and stays compute-on-demand; adjusted/returns are
pure functions of the pins, so no analytical store is needed yet. *Consequence:*
Phase 1 storage class reused; derived market store mirrors `AvailabilityStore`; a
`panel_id`-style cache can be added later without a schema.

**D8 — Deterministic identity / versioning.**
*Question:* How are market identities and snapshots content-addressed? *Options:*
(a) reuse both existing conventions + a `MarketDatasetVersion` Merkle contribution;
(b) a new scheme. *Recommendation:* **(a).** *Reason:* consistency with the whole
codebase; reproducibility (invariants 13, 19). *Consequence:* `price_observation_id` /
`corporate_action_id` / `adjusted_series_id` as in §14; market leaves extend the
DatasetVersion manifest.

**D9 — Revised / latest semantics.**
*Question:* How are vendor corrections and "latest" values served? *Options:*
(a) distinct `PitPrice` / `RevisedPrice` types + two methods, no default, explicit
`reinterpret_as_pit`; (b) a single mutable "latest" value; (c) a default mode.
*Recommendation:* **(a).** *Reason:* mandatory consistency with invariants 27–30; a
default mode "conflicts with existing architecture" (the requirement's explicit
caution). *Consequence:* `MarketPointInTimeResolver` mirrors `PointInTimeResolver`;
REVISED resolves at the reproducible ingestion frontier over a pinned snapshot.

**D10 — Phase 12 hand-off.**
*Question:* What exactly does Phase 11 expose to the backtester? *Options:* (a) a
narrow PIT-only price/series contract; (b) also expose returns/portfolio helpers.
*Recommendation:* **(a) `price_as_of` + `price_series_as_of` + `adjusted_series_as_of`,
all returning PIT types over a content-addressed date axis; nothing else.** *Reason:*
answers "the price knowable as of T" without leaking strategy/performance logic into
Phase 11; `PitPrice` is the typed safety boundary; the axis is the rebalance schedule.
*Consequence:* `strategy_version` stays unset; Phase 12 consumes `PitPrice` and
structurally cannot be handed revised history.

---

## 22. Future extensions

Deliberately deferred, each addable as a **new version** that hashes distinctly and
never alters an existing id (the Phase 10 D7 extensibility discipline):

- **Finer grains:** intraday bars, VWAP, bid/ask/quote data — a new `PriceObservation`
  field set / grain, not a rewrite.
- **More asset classes:** options chains, futures, FX, fixed income — new instrument
  security-types and source rules.
- **`figi:` enrichment:** an external FIGI/CUSIP mapping source promotes `security_id`
  from the `cik#class` fallback to the preferred FIGI form without breaking historical
  bars.
- **Additional adjustment conventions:** total-return vs price-return, spinoff/rights
  handling — new versioned adjustment functions.
- **VERIFIED availability:** a source that publishes trustworthy dissemination
  timestamps unlocks `VERIFIED` status (dormant rule already provided for, §9).
- **Transparent value cache:** a content-addressed cache keyed by
  `adjusted_series_id` for speed, safe because values are pure functions of the pins.
- **Multi-CIK succession / mergers return-treatment:** the §15.7 alias mapping and
  Phase 12's economic treatment of merger events.

---

*This is a design-only proposal. Decisions D1–D10 require explicit approval before any
implementation begins. On approval, a locked architecture document
(`phase11-market-data-locked.md`) will supersede this one, and implementation will
proceed additively — reusing the Phase 1 storage/transport and Phase 5 PIT machinery,
editing no existing store, and honoring the determinism, immutability, provenance, and
PIT/REVISED invariants of [data-model.md §12](data-model.md).*
