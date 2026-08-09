# Phase 11 — Point-in-Time Market Data Layer (LOCKED architecture)

> **Status: LOCKED, implemented.** The Phase 11 proposal
> ([phase11-market-data-proposal.md](phase11-market-data-proposal.md)) was
> approved and decisions D1-D10 are settled (section 1). This document is the
> normative locked architecture; the implementation lives in
> `src/quantforge/market/`. Changes to the price/corporate-action data model,
> PIT/REVISED behavior, availability semantics, instrument-identity rules, the
> provider seam, or the D1-D10 locks require updating this document first.
>
> This layer is purely additive. It edits no existing store, relaxes no existing
> invariant, adds no runtime dependency, and mirrors Phase 5 structurally over a
> new source. It builds **none** of the Phase 12 backtester.

---

## 1. Decisions D1-D10 - final choices

| # | Decision | Final choice | Status |
| --- | --- | --- | --- |
| **D1** | Scope / grain | **Daily OHLCV, equities only.** One `PriceObservation` per `(security_id, trading_date, field)`; intraday / multi-asset are future axes. | LOCKED (extensible by new version) |
| **D2** | Instrument identity | Reuse the designed `security_id`: `cik:<CIK>#class:<normalized-class>` offline default, `figi:<FIGI>` optional external enrichment. **Ticker is never identity.** | LOCKED - architectural commitment |
| **D3** | PIT availability | Session close + policy publication lag, **floored at close**, **capped at `retrieved_at`**, fail-closed to `UNKNOWN`. "Round LATER on uncertainty." | LOCKED (policy vocabulary extensible) |
| **D4** | Stored price | **Unadjusted is canonical.** Adjusted prices are a derived, versioned, PIT-gated view - never the stored value. | LOCKED - architectural commitment |
| **D5** | Corporate actions | **First-class immutable, PIT-gated records** (split, dividend, symbol-change, delisting; merger represented structurally). | LOCKED (kinds extensible; each semantics immutable) |
| **D6** | Provider abstraction | A `MarketDataProvider` Protocol + adapters outside core; the canonical layer imports no vendor; a fake backend powers tests. | LOCKED |
| **D7** | Storage | Content-addressed raw tier + thin derived `MarketDataStore`, under a sibling `<root>/market/` tree. **No database.** | LOCKED (reversible/additive) |
| **D8** | Identity / versioning | Reuse both conventions (raw = bare hex; derived = `sha256:`-prefixed NUL-joined canonical JSON) + a `MarketDatasetVersion` contribution. | LOCKED - identity is a commitment |
| **D9** | Revised / latest | **Distinct `PitPrice` / `RevisedPrice` types**, two methods, no default, explicit `reinterpret_as_pit`. | LOCKED - architectural commitment |
| **D10** | Phase 12 hand-off | Narrow PIT-only contract: `price_as_of` + `price_series_as_of` + `adjusted_series_as_of`, all returning PIT types over a content-addressed axis; nothing else. `strategy_version` stays unset. | LOCKED |

### 1.1 D9 - explicit lock (as approved)

- Use **distinct `PitPrice` and `RevisedPrice` types**.
- Preserve the existing PIT/REVISED type separation used by `PitValue` /
  `RevisedValue` (Phase 5), `PitFactor` / `RevisedFactor` (Phase 8), and
  `PitPanel` / `RevisedPanel` (Phase 10).
- A `RevisedPrice` **must never** be accepted where a `PitPrice` is required -
  enforced at the type boundary, not by convention (invariant 28). They share no
  base that would let one substitute for the other in a PIT-typed signature.
- Any revised -> PIT conversion must **explicitly re-resolve at the requested
  `as_of`** (`RevisedPrice.reinterpret_as_pit(resolver, as_of)` re-runs
  resolution; it never rescales or reuses the revised value).

### 1.2 D2 - explicit lock (as approved)

- **Canonical default form:** `security_id = cik:<CIK>#class:<normalized-class>`,
  derivable entirely offline from the CIK plus a normalized share-class label.
- **Preferred form when available:** `security_id = figi:<FIGI>` - optional
  external enrichment, never required for the layer to function.
- `Company (cik:...) 1--inf Security (security_id)`. `company_id` stays the
  fundamental anchor; `security_id` is the market-data anchor; the two join over
  the `Company 1-inf Security` edge.
- **Ticker is never identity.** Tickers/exchanges live on the `Instrument` as
  effective-dated history rows. A ticker change is a new history row, never a new
  identity and never a mutation. A ticker reused by a different issuer can never
  retroactively re-point old bars (bound to `security_id`, not ticker).

---

## 2. Final market-data model

Each canonical entity mirrors an SEC-stack entity's role, keeping the mental
model uniform. Implemented in `src/quantforge/market/model.py`.

| Market entity | Mirrors (SEC) | Role |
| --- | --- | --- |
| `MarketDataSource` | `Source` | The publisher/vendor; source-level trust/rules and default currency as policy data. |
| `Instrument` | `Security` | The tradable instrument keyed by `security_id`; owns effective-dated `TickerHistory` (never identity) and `company_id`. |
| `RawMarketDocument` | `RawDocument` | Immutable content-addressed vendor bytes with retrieval provenance. |
| `PriceObservation` (canonical) | `Fact` | The normalized daily bar for `(security_id, trading_date, field)` in a stated currency - **unadjusted** (D4). |
| `CorporateAction` | *(new, same pattern)* | First-class immutable split / dividend / symbol-change / delisting / merger record with its own availability. |
| `MarketAvailabilityPolicy` | `AvailabilityPolicy` | Versioned, era-bounded, declarative rule mapping a bar's evidence -> availability timestamp + status. |
| `MarketObservationEvidence` | `FilingEvidence` | The per-session anchors the availability policy consumes. |
| `MarketAvailability` | availability triple | `(timestamp, status, policy_id)`; `__post_init__` enforces that `UNKNOWN` carries neither timestamp nor policy and `VERIFIED`/`DERIVED` carry both. |
| `MarketDatasetVersion` | `DatasetVersion` | Market leaves (`mktraw`/`price`/`action`/`mktpol`) extending the reproducible snapshot manifest. |

**Per-field key.** A canonical observation is keyed by
`price_obs_key = (security_id, trading_date, field)` with
`field in {open, high, low, close, volume}`, so the Phase 5 resolver's per-key
selection semantics transfer directly and a vendor's partial correction of a
single field is a clean, independently-resolvable observation.

**Result types** (`src/quantforge/market/result.py`) - frozen, slotted, sharing a
`_PriceBase` (never itself a public accessor target):

| Field | Meaning |
| --- | --- |
| `security_id`, `trading_date`, `field` | The coordinate. |
| `status` | `KNOWN` \| `UNDEFINED`. |
| `value_numeric_str` | Exact `Decimal` serialized as a string; `None` when `UNDEFINED`. |
| `currency` | Explicit; `None` when `UNDEFINED`. |
| `reason` | `PriceUndefinedReason` when `UNDEFINED` (`NOT_KNOWABLE_YET`, `NOT_REPORTED`, `MISSING_ADJUSTMENT_REFERENCE`, ...); `None` when `KNOWN`. |
| `provenance` | Full `PriceProvenance` chain (section 7). |

Distinguishing field: `PitPrice` carries no snapshot pin (it is resolved at an
`as_of`); `RevisedPrice.dataset_version_id` is the pinned snapshot. `PitPriceSeries`
is an ordered tuple of cells over a `PriceAxis`, carrying `adjusted: bool` and, when
adjusted, an `adjusted_series_id`.

---

## 3. PIT vs REVISED behavior

- **Two methods, no default (invariant 27).** `price_as_of` / `price_series_as_of`
  / `adjusted_series_as_of` (PIT) require a timezone-aware `as_of` (a naive instant
  is rejected at the **reused** Phase 5 `timestamps.py` choke point);
  `revised_price` (REVISED) requires a `MarketDatasetVersion`.
- **Two result types (invariant 28, D9).** `PitPrice` != `RevisedPrice`; a
  `RevisedPrice` can never be passed where a `PitPrice` is required.
- **Restatement / vendor correction.** Because raw bytes are immutable and
  content-addressed, a correction is a **new** raw document and a **new**
  observation with its own availability. The store is **append-only**: both
  vintages coexist. The resolver's total order (**availability desc, then
  `observation_id` desc**) selects the bar knowable at `as_of`; PIT reproduces the
  price as it was known then; REVISED reproduces the latest at the pinned snapshot.
- **Past-closed & monotonic (invariant 29).** As `as_of` advances a cell goes
  `UNDEFINED -> KNOWN` (or a value changes when a correction becomes knowable);
  never the reverse.
- **REVISED is reproducible, not wall-clock (invariants 21, 30).** Resolved at the
  ingestion frontier (max availability instant across eligible observations) over
  the pinned snapshot, never a wall-clock read.
- **Explicit crossing only.** `RevisedPrice.reinterpret_as_pit(resolver, as_of)`
  re-runs resolution at `as_of`; never an implicit cast.

---

## 4. Availability / PIT semantics (D3)

The heart of the layer, mirroring Phase 5. **A historical price must not become
eligible before the system's defined availability boundary.** Implemented in
`src/quantforge/market/policy.py`.

**Anchors per session** (`MarketObservationEvidence`):

| Anchor | Role |
| --- | --- |
| `trading_date` (effective) | The exchange session the bar describes. **Never** an availability lower bound - a close is not knowable during its own session. |
| `observation_timestamp` | Descriptive evidence of when the vendor stamped the record. |
| `retrieved_at` | Phase-1-style retrieval time of the raw bytes; an **upper bound** on availability. |
| `availability_timestamp` (derived) | The **only** PIT-eligible boundary. |

**Derivation, a pure function.** The v1 default policy `market-eod-std`
(`market_eod_std_v1()`) maps a session to availability = **session close
(16:00 ET) + publication lag (240 min)**, **floored at the session close** (a bar
can never be knowable before its own session ends - the analogue of Phase 5's
"never before acceptance") and **capped at `retrieved_at`** (invariant-11
analogue). Anything undatable -> `UNKNOWN` -> **excluded** (fail-closed).
Worked example: a `2020-01-02` session becomes knowable at
`2020-01-03T01:00:00Z` under the default (16:00 EST + 240 min = 20:00 EST =
01:00 UTC next day). "Round LATER on uncertainty, never earlier" - so a re-ingest
can never admit look-ahead (`_later_availability` keeps the later of stored vs
re-derived when both are eligible).

**Status semantics** reuse `AvailabilityStatus` (imported from
`quantforge.availability.model`, not re-exported):
- `VERIFIED` - direct dissemination evidence the policy trusts. **Dormant in v1.**
- `DERIVED` - computed from close + publication lag. **The v1 default.**
- `UNKNOWN` - undatable -> never eligible (fail-closed).

`is_pit_eligible` = status in `(VERIFIED, DERIVED)` **and** a timestamp is present.

---

## 5. Corporate-action model (D4/D5)

**Adjusted close is not sound as the stored canonical value.** It silently folds
every future split/dividend into a single number, so two backtests run on
different days see different history for the same past date - textbook look-ahead
and a reproducibility violation. It also destroys the raw truth (returns need the
unadjusted price and the action separately) and bakes an opaque, unversioned
convention into the system of record.

**The model.** A `CorporateAction` is a first-class immutable record (mirroring
`Fact`), one per event, carrying its own availability so it is PIT-gated:

| Kind | Key fields | Backtester need |
| --- | --- | --- |
| **Split** | `ex_date`, `ratio` (exact Decimal) | Price continuity / share counts. |
| **Dividend** | `ex_date`, `pay_date`, `amount`, `currency` | Total-return; reinvestment. |
| **Symbol change** | `ex_date`, `old_ticker`, `new_ticker` | Ticker history (section 1.2), not identity. |
| **Delisting** | `ex_date`, `reason` | Terminal event; survivorship-bias-free (history preserved). |
| **Merger** | `ex_date`, successor `security_id`, `terms` | **Structurally represented only**; return-treatment is a Phase 12 concern. |

**Adjusted prices are a derived, versioned view** (`src/quantforge/market/adjust.py`).
Given the immutable unadjusted series + the immutable action history, an adjustment
function (pure, versioned by `AdjustmentVersion`, PIT-gated so only actions
**knowable as of `as_of`** are applied) computes an adjusted series **on demand**.
Because it consumes only `<= as_of`-eligible actions it **cannot introduce
look-ahead** (the same argument Phase 10 uses for derivations). Conventions:
`split` (default; splits only) and `split-dividend` (also reinvests dividends off a
PIT reference close); `AdjustmentVersion.__post_init__` raises on any unknown
convention. A pre-ex cell whose reference close is not available fails closed to
`UNDEFINED(MISSING_ADJUSTMENT_REFERENCE)` - never guessed. Same inputs + same
adjustment version => identical `adjusted_series_id` and values, forever.

---

## 6. Instrument identity, provider abstraction, storage

**Identity (D2)** - see section 1.2. `Instrument.company_id` recovers the filer
(`cik:<CIK>`); `TickerHistory` rows are effective-dated and cosmetic.

**Provider abstraction (D6).** `MarketDataProvider` is a narrow `typing.Protocol`
(`fetch_daily_bars` / `fetch_corporate_actions -> RawMarketDocument`). The canonical
layer imports **no** vendor. `FakeMarketDataProvider` (in-repo, offline, synthetic)
powers every test; a real vendor adapter lives outside core and is an optional
extra - **zero new runtime dependencies**. Source-level trust/currency live on
`MarketDataSource` as policy data. A vendor API key, when a real adapter exists,
lives only in a git-ignored `.env` read through the injectable-config pattern - it
never enters identity, provenance, or the repo.

**Storage (D7).** No database. A sibling `<root>/market/` tree, additive to the
Workspace root; the SEC acquisition tree is byte-for-byte unchanged:

```
<root>/market/
    raw/          # immutable content-addressed vendor bytes (Phase 1 ArtifactStore pattern)
    canonical/    # derived PriceObservation / CorporateAction / Instrument, one JSON file per instrument
    availability/ # derived market-data availability (per instrument)
```

The derived `MarketDataStore` mirrors `AvailabilityStore`: one JSON file per
instrument, atomic write (temp -> `flush` -> `os.fsync` -> `os.replace`),
`sort_keys=True`, deterministic ordering (obs by `price_observation_id`, actions by
`corporate_action_id`), no wall-clock/RNG. **Append-only**: a re-ingest merges by
content id (idempotent) and never overwrites prior observations. The derived tier is
**safe to delete and rebuild byte-identically** from the immutable raw tier. Reads
fail closed on a corrupted/tampered id or a non-object document
(`MarketConsistencyError`).

---

## 7. Identity, provenance, and reproducibility (D8)

All derived ids `sha256:`-prefixed, `_SEP = "\x00"` NUL-joined, canonical JSON
(`sort_keys=True, ensure_ascii=False, separators=(",", ":")`); raw documents use
bare-hex content addressing.

```
price_observation_id = sha256( market_transformation_version_id ∥ security_id
                              ∥ trading_date ∥ currency ∥ field ∥ value )
corporate_action_id  = sha256( market_transformation_version_id ∥ security_id
                              ∥ action_kind ∥ ex_date ∥ canonical action payload )
adjusted_series_id   = sha256( adjustment_version ∥ security_id ∥ boundary_key
                              ∥ ordered unadjusted obs ids ∥ ordered action ids )
```

`MarketDatasetVersion` extends the Merkle-root manifest with tagged, sorted leaves
(`mktraw`/`price`/`action`/`mktpol`), so any change to market inputs yields a new
`dataset_version_id` (invariant 19).

**Provenance chain** (`PriceProvenance` on every result, KNOWN or UNDEFINED):

```
PriceObservation -> RawMarketDocument -> vendor bytes (content-addressed)
   ├─ market_transformation_version_id (normalizer)
   ├─ security_id -> Instrument -> Company (cik:...)
   ├─ market_availability_policy_id -> MarketAvailabilityPolicy
   └─ selected_source_id, boundary_kind, present_candidates (corrections that lost the total order)
```

**Guarantee:** same inputs + same versions + same boundary => identical ids and
values, on any machine, independent of order/wall-clock/cache. Maps onto the
data-model section 9 `ResearchResult`; `strategy_version` **absent** - reserved for
Phase 12.

---

## 8. Backtester hand-off contract (D10)

Phase 12 must be able to ask **"the price of instrument X knowable as of T"**
without Phase 11 implementing any strategy, portfolio, weighting, or performance
logic. The contract is tiny and **PIT-only**:

```python
price_as_of(security_id, trading_date, as_of, *, field=close) -> PitPrice
price_series_as_of(security_id, date_axis, as_of, *, field=close) -> PitPriceSeries
adjusted_series_as_of(security_id, date_axis, as_of, *, adjustment) -> PitPriceSeries
```

- **`PitPrice` is the typed hand-off** - a future backtester's signature consumes
  `PitPrice` / `PitPriceSeries` and **structurally refuses** `RevisedPrice`
  (invariant 28). The look-ahead safety boundary is a type, not a convention.
- **The date axis is the rebalance schedule** - an explicit, content-addressed
  `PriceAxis` (`of([...])` or the pure `business_daily(...)` generator), reusing the
  Phase 10 axis philosophy. No new time model.
- **Fundamentals join prices** through the `Company 1-inf Security` edge.
- **`strategy_version` stays unset.** Phase 11 fills only the market-data pins.
- **Explicitly not in the contract:** returns aggregation, portfolio NAV,
  weighting, turnover, transaction costs, benchmarks, or any performance statistic.

---

## 9. Workspace / API integration

Strictly additive, mirroring Phases 7/8/10. `Workspace.open()` wires the new
`<root>/market/` tree; a lazy, cached `Workspace.price_engine` property
(import-on-first-use to avoid a module-load cycle) builds a `PriceEngine` over a
`MarketDataStore` at `<root>/market`. A workspace that never touches prices pays
nothing. Curated top-level exports keep the PIT/REVISED distinction visible:

```python
from quantforge import PitPrice, RevisedPrice
from quantforge.market import (
    PriceEngine, PriceAxis, MarketDataProvider, FakeMarketDataProvider,
    DateRange, RawMarketDocument, PitPrice, PitPriceSeries, RevisedPrice,
)
```

No default-mode accessor (invariant 27 at the front door): there is
`price_as_of(...)` and `revised_price(...)`, never a mode-guessing `price()`.

---

## 10. What Phase 11 explicitly does NOT do

- **No backtesting, portfolio construction, weighting, rebalancing, optimization,
  alpha/return evaluation, transaction-cost modeling, or performance analytics.**
  `strategy_version` stays unset. These are Phase 12+.
- **No investment recommendations, UI, website, or market-data visualization.**
- **No intraday / tick / quote / order-book data.** Daily bars only (D1).
- **No real-time or streaming feeds.** Historical, reproducible bars only.
- **No derivatives, options, futures, FX, or fixed-income analytics.** Equities only.
- **No market data as a fundamentals source.** Prices never rewrite, override, or
  merge into a canonical SEC `Fact`. Fundamentals remain 100% SEC.
- **No adjusted-close-as-truth** (D4) and **no silent historical rewriting** when a
  corporate action appears (invariant 4).
- **No new identifier system** (D2); ticker is never identity.
- **No database** (D7); no bundled real market data (tests use synthetic fakes).

---

## 11. Room for Phase 12 and future extensions

Each future item is addable as a **new version** that hashes distinctly and never
alters an existing id (the Phase 10 D7 extensibility discipline): finer grains
(intraday, VWAP, quotes); more asset classes; `figi:` enrichment promoting
`security_id` without breaking historical bars; additional adjustment conventions
(total-return, spinoff/rights); `VERIFIED` availability when a source publishes
trustworthy dissemination timestamps (the dormant rule is already provided for); a
transparent value cache keyed by `adjusted_series_id`; and Phase 12's economic
treatment of merger succession. The `PitPrice` typed hand-off and the reserved
`strategy_version` mean Phase 12 slots in **beneath, not through** Phase 11 with no
schema change.

---

*This document is the locked Phase 11 architecture. The implementation
(`src/quantforge/market/`) satisfies the determinism, fail-closed, immutability,
provenance, and PIT/REVISED invariants of [data-model.md section 12](data-model.md)
(esp. 4, 5, 8-9, 11, 13, 15, 18-19, 21, 27-30) and realizes the reserved `Source`
and `Security` entities as its first consumer.*
