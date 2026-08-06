# SEC EDGAR Data Reconnaissance

> **Status: RECONNAISSANCE ONLY.** No ingestion pipeline, database, normalization,
> or PIT query code was created. All scripts and downloaded samples live in an
> isolated temporary directory **outside** the repository working tree
> (`C:\dev\openfinance-recon-tmp\`, sibling to the repo) and are **not**
> committed. This report records what real SEC data actually looks like and
> validates it against [docs/data-model.md](data-model.md).

## 1. Scope

Empirically inspect the SEC EDGAR interfaces OpenFinance is considering as
initial sources, and determine whether the approved data model matches reality.
Investigations 1–15 from the task brief are all covered. We deliberately looked
at **actual records**, not documentation, for every claim.

Method: a stdlib-only (`urllib`) fetcher with a declared User-Agent, 0.35s
rate-limit, and on-disk caching (so nothing is re-requested). No dependency was
installed. No API key exists (SEC needs none). The User-Agent contact is read
from `OPENFINANCE_SEC_USER_AGENT`; a generic non-personal placeholder was used —
**no personal email is hardcoded anywhere.**

## 2. SEC endpoints inspected

| Purpose | Endpoint | Observed |
|---------|----------|----------|
| Submissions (filing history) | `https://data.sec.gov/submissions/CIK##########.json` | 200; 143 KB for our company; **lenient** on User-Agent. |
| Company facts (all XBRL facts) | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | 200; 3.36 MB. |
| Filing directory index | `https://www.sec.gov/Archives/edgar/data/<cik>/<accn-nodashes>/index.json` | 200 **only with an email-format contact**; 403 otherwise. |
| XBRL instance document | `https://www.sec.gov/Archives/edgar/data/<cik>/<accn-nodashes>/<file>.xml` | 200; 24.6 MB raw, 842 KB gzipped. |

Two host families with **different access strictness**: `data.sec.gov` accepted a
plain UA; `www.sec.gov/Archives` returned **HTTP 403** until the UA contained an
email-style token. Documented in §17.

## 3. Company selected

**The Kraft Heinz Company** — CIK `0001637459`, ticker `KHC`, Nasdaq.

Chosen because it exhibits, in one issuer, every hard case the model must
survive:

- **A genuine restatement.** Its FY2018 10-K was filed **2019-06-07** — ~4 months
  late, preceded by an `NT 10-K` non-timely notice — and restated 2016/2017
  figures. This is the canonical "later filing changes a historical value" case.
- **Amendment forms present**: two `10-Q/A` (filed 2017-11-07).
- **11 × 10-K, 33 × 10-Q**, 2015→2026, substantial XBRL.
- **A prior name** (`H.J. Heinz Holding Corp` → `Kraft Heinz Co`) exercising the
  name-change path, and a merger-origin entity (Kraft + Heinz, 2015).
- **A 52/53-week fiscal calendar** (`fiscalYearEnd: "1226"`), so period-ends drift
  (2016-01-03, 2016-12-31, 2017-12-30, 2019-12-28 …) — never assume calendar.

Every finding below is from KHC's real data; a production validation set should
add more issuers (see §21).

## 4. Exact observed schemas

### 4.1 submissions JSON (top level)

Keys: `cik, entityType, sic, sicDescription, ownerOrg,
insiderTransactionForOwnerExists, insiderTransactionForIssuerExists, name,
tickers, exchanges, ein, lei, description, website, investorWebsite, category,
fiscalYearEnd, stateOfIncorporation, stateOfIncorporationDescription, addresses,
phone, flags, formerNames, filings`.

Observed types/values:
- `cik`: **string**, zero-padded to 10 (`"0001637459"`).
- `name`: `"Kraft Heinz Co"`. `tickers`: `["KHC"]` (list). `exchanges`:
  `["Nasdaq"]` (list). `sic`: `"2030"` (string). `fiscalYearEnd`: `"1226"`
  (MMDD, non-calendar). `lei`: **null** (not always present).
- `formerNames`: `[{"name":"H.J. Heinz Holding Corp","from":"2015-03-25T…Z","to":"2015-07-01T…Z"}]`
  — effective-dated, ISO-8601 UTC.
- `filings.recent`: a **columnar** object (parallel arrays), 874 rows here, plus
  `filings.files` for older overflow (empty for KHC — all history fit in one page).

`filings.recent` columns (parallel arrays, same length):
`accessionNumber, filingDate, reportDate, acceptanceDateTime, act, form,
fileNumber, filmNumber, items, core_type, size, isXBRL, isInlineXBRL,
isXBRLNumeric, primaryDocument, primaryDocDescription`.

| Column | Type | Example | Notes |
|--------|------|---------|-------|
| `accessionNumber` | str | `0001637459-19-000049` | `NNNNNNNNNN-NN-NNNNNN`, dashed. |
| `filingDate` | str (date) | `2019-06-07` | Date only, no time. "Deemed filed." |
| `reportDate` | str (date) | `2018-12-29` | Period-end; **empty for 168/874 rows** (e.g., Form 4). |
| `acceptanceDateTime` | str (datetime) | `2019-06-07T21:07:36.000Z` | **UTC** (see §8), ms precision, `Z`. Always present. |
| `form` | str | `10-K`, `10-K/A`, `10-Q/A`, `NT 10-K` | Amendment = base + `/A` suffix. |
| `size` | int | `24671049` | Bytes of the full submission. |
| `isXBRL`/`isInlineXBRL` | int (0/1) | | Older filings XBRL-but-not-inline; inline from ~2020. |
| `primaryDocument` | str | `khc-20181229.htm` | Filename of the primary doc. |

### 4.2 companyfacts JSON

Top level: `cik` (**int** `1637459` here — note: **unpadded**, unlike
submissions), `entityName`, `facts`.

`facts` → taxonomy (`dei`, `us-gaap`, `srt`, `ffd`) → concept →
`{label, description, units}` → unit string → **list of observations**.

Each observation's keys (exact, from scanning all 21,968 us-gaap observations):

| Key | Presence | Type | Meaning |
|-----|----------|------|---------|
| `end` | 21968/21968 | str date | Period end (or instant). |
| `val` | 21968/21968 | int/float | **Already fully scaled** (e.g. `18271000000`). |
| `accn` | 21968/21968 | str | Source accession. **Never missing.** |
| `form` | 21968/21968 | str | Source form. |
| `filed` | 21968/21968 | str date | Source filing date. |
| `fy` | present, **often null** | int/null | Filing's fiscal-year *focus* (not the fact's period). |
| `fp` | present, **often null** | str/null | Filing's fiscal-period focus (`FY`,`Q1`…). |
| `start` | 13468/21968 | str date | Present for durations, absent for instants. |
| `frame` | 8794/21968 | str/absent | e.g. `CY2012`, `CY2016Q4I`; only on "framed" facts. |

**Absent from companyfacts entirely:** `acceptanceDateTime`, any **dimension/
segment**, any **nil** marker, `decimals`/precision, and unit *scale* metadata.

## 5. Submissions findings

- The submissions endpoint is **sufficient to populate the `Filing` entity's
  core identity and evidence fields**: accession, form, filingDate, reportDate,
  and — critically — `acceptanceDateTime`, which companyfacts lacks.
- Amendments are represented purely by the `form` string (`10-K/A`, `10-Q/A`).
  There is **no explicit `amends_accession` link** in submissions — the base↔amendment
  relationship must be inferred (§9 open item in data-model was correct to flag this).
- `reportDate` is empty for non-periodic forms (Form 4, etc.). Fine — those
  produce no financial facts.
- `filings.files` provides pagination for issuers with more history than one page;
  a complete ingester must follow it (KHC didn't need it).

## 6. Companyfacts findings

- Provides a compact, **pre-consolidated** view: one taxonomy/concept/unit tree
  with every historical observation and its source accession.
- **Fact-level provenance available:** `accn`, `form`, `filed`. That is enough to
  join to a filing (see §7) but **`filed` is a date only** — no acceptance time.
- `val` is delivered **already scaled to base units**; there is **no scale field**
  and no `decimals`. Precision is therefore *lossy* vs the instance (§8).
- `fy`/`fp` are the **filer's document focus**, not the observation's period. The
  observation's period is defined solely by `start`/`end`. We saw the same
  period-end (`2017-12-30`) tagged `fy=2017/FY`, `fy=2018/Q1`, `fy=2019/FY` in
  different filings — proof `fy`/`fp` must **not** be part of the observation key.
- 22,033 total observations across all taxonomies for this one company.

## 7. Fact → Filing join findings

**The `companyfacts.accn → submissions.accessionNumber` join is reliable — for
undimensioned facts.**

- All 48 distinct accessions referenced by KHC's companyfacts matched the
  `NNNNNNNNNN-NN-NNNNNN` format; **0 malformed, 0 missing**.
- **0 companyfacts accessions were absent** from `submissions.recent`. (Caveat:
  for issuers using `filings.files` pagination, the join must include the
  overflow pages, or some accessions will appear "missing".)
- **Same fact appears under many accessions** — routine. A single period-end
  value is re-reported in later 10-Qs/10-Ks; grouping by `(concept, unit, start,
  end)` yielded **5,773 period-keys with >1 observation** (5,027 identical repeats
  + 746 with differing values). The `accn` distinguishes them correctly.
- **Edge case — same accession, same period, different value is possible** across
  concepts, but within one `(concept,unit,period,accn)` we saw no contradictions
  for KHC. Must still be guarded (data-model §13 case 8).

## 8. Timestamp findings

**`acceptanceDateTime` is UTC, not Eastern — this corrects the data model.**

Evidence (two independent proofs):
1. **Hour histogram** clusters bimodally at **20:00–22:00Z** and **11:00–13:00Z**.
   Interpreted as UTC these are ~15:00–17:00 ET (end of business day) and
   ~06:00–08:00 ET (morning) — exactly where filings should cluster. Interpreted
   as ET they'd fall at 3–5 AM, which is nonsensical.
2. **filingDate/acceptance-date mismatches (67 rows):** e.g. Form 4
   `filingDate=2026-03-03`, `acceptanceDateTime=2026-03-04T01:08Z`. Only
   consistent if `Z` is truly UTC: 01:08Z = 20:08 ET on **03-03**, matching the
   filingDate. An 8-K `filingDate=2026-05-13`, `accept=2026-05-12T21:31Z` =
   17:31 ET on 05-12 → accepted after the ~17:30 ET cutoff, **deemed filed next
   day**. This is the real "post-cutoff → next business day" behavior the
   availability policy must model — observed, not assumed.

Other facts:
- Precision: **milliseconds** (`.000Z`), always `Z`, always present in submissions.
- **`acceptanceDateTime` exists ONLY in submissions, never in companyfacts.** So
  companyfacts alone **cannot** establish the acceptance instant — a mandatory
  submissions join is required for any timestamp-based logic.
- `acceptance` and `filingDate` **routinely differ** (67/874 here), and acceptance
  can be **on a later UTC calendar day than filingDate** yet an **earlier ET
  instant** — confirming the data-model's decision to never order `filing_date`
  vs `acceptance_timestamp` (invariant 10 as revised).
- Per the brief: **no availability rule was inferred.** These are raw observations.

## 9. Amendment findings

Base vs amendment (`10-Q/A` pair filed 2017-11-07, restating Q1 & Q2 2017):

| Aspect | Observed |
|--------|----------|
| Form representation | `10-Q/A` (base `10-Q`), suffix-only. |
| Accession | Amendment has its **own new accession** (`…-17-000116/000117`), distinct from base. |
| Filing/acceptance | Own `filingDate` and `acceptanceDateTime`; the two /A's are 4 minutes apart (00:37:29Z vs 00:41:26Z) — **distinguishable only by acceptance time**. |
| Report period | `reportDate` points at the amended period (2017-04-01, 2017-07-01). |
| companyfacts exposure | **Both base and amended observations are present** in companyfacts, each tagged with its own `accn`/`form`. |
| Traceable to filing | Yes — both `accn`s resolve in submissions. |
| **`amends_accession` link** | **Not provided.** Must be inferred (form=`*/A` + matching period/issuer, or parsing the amendment document). |

## 10. Restatement findings

**The Historical Knowledge State model is empirically validated.**

`StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`,
period-end **2017-12-30**, appeared 11 times across filings:

| val (USD) | accn | form | filed |
|-----------|------|------|-------|
| **66,241,000,000** | …18-000015 | 10-K | 2018-02-16 (original) |
| 66,241,000,000 | …18-0000{99,116,124} | 10-Q | 2018 (repeated) |
| **66,070,000,000** | …19-000049 | 10-K | **2019-06-07 (restated)** |
| 66,070,000,000 | …20-000027 | 10-K | 2020-02-14 (carried forward) |

- The **old observation ($66.241B) remains available** — not overwritten. ✅
- The later observation references the **same fiscal period** (same `end`). ✅
- The accession **differs** (`18-000015` vs `19-000049`). ✅
- Concept/unit/period **match**; the only differences that mattered were `val`
  and availability. ✅
- 746 such differing-value period groups exist for KHC alone.

This is exactly the "$100M in 2020, $80M in 2022" scenario from data-model §KS,
observed in real data. A PIT query as-of 2019-01-01 must return $66.241B; as-of
2020-01-01, $66.070B. The append-only model represents this natively.

**But note the precision-drift restatement class:** `CommonStockSharesIssued`
period-end 2016-12-31 went `1,218,947,088` (2017 filings) → `1,219,000,000`
(2018+ filings, rounded to millions) — same economic value, different
**precision/scale**. The normalization layer must decide whether these are
"restatements" or precision changes (see §12, §13).

## 11. Dimension findings — **most consequential result**

**companyfacts contains ONLY undimensioned (consolidated) facts. All segment/
dimensional detail is dropped.** The XBRL instance is required for dimensions.

Proof, from the FY2018 instance (`khc-20181229.xml`):
- **1,247 contexts, 1,217 dimensional (97.6%)**, 30 undimensioned.
- Single concepts appear up to **208 times** in one filing, distinguished only by
  dimension members (e.g. `StatementEquityComponentsAxis` /
  `NoncontrollingInterestMember`).
- Direct comparison for `RevenueFromContractWithCustomerIncludingAssessedTax`:
  **instance = 157 facts (142 dimensional + 15 undimensioned)**; **companyfacts
  kept exactly the 15 undimensioned** ones from that accession.

Dimensions are expressed as XBRL `context/entity/segment/xbrldi:explicitMember`
(and `typedMember`), with `dimension="axis"` and a `member` value. This maps
cleanly onto the data-model's `dimensions` / `dimensions_hash`, **but the data
must come from the instance, not companyfacts.**

**Required change:** the canonical observation key (which includes
`dimensions_hash`) **cannot be built from companyfacts alone.** For dimensional
facts, OpenFinance must ingest and parse the **inline/standalone XBRL instance**.
companyfacts is usable only for the consolidated slice.

## 12. Unit findings

Units observed (companyfacts unit strings / instance measures):

| Unit | Source form | Notes |
|------|-------------|-------|
| `USD` | `iso4217:USD` | 574 concepts; monetary. |
| `shares` | `xbrli:shares` | Share counts. |
| `USD/shares` (`usdPerShare`) | `iso4217:USD` ÷ `xbrli:shares` | Per-share; unit is a ratio of two measures. |
| `pure`/`number` | `xbrli:pure` | Ratios, percentages (as decimals). |
| `EUR`, `INR`, `CAD`, `VEF/USD`, `VES_PER_USD` | `iso4217:*` | Multiple currencies + FX rates in one issuer. |
| `khc:Brand`, `khc:factory`, `khc:employee`, `khc:segment`, `goodwill_reporting_unit`, `annual_installment` | **custom company namespace** | Non-standard units — the normalizer must tolerate unknown/custom units. |

- **Values in companyfacts are already scaled to base units** (`val` is the true
  magnitude). But the **`decimals` attribute — which encodes precision/scale — is
  only in the instance**, not companyfacts. Instance `decimals` ranged
  `-9…5` and `INF`; `-6` (millions) dominated (6,963 facts).
- Ambiguity the normalizer must resolve: (a) `pure` used for both ratios and
  percentages — no built-in "is this ×100?" flag; (b) custom units have no
  standard meaning; (c) `USD/shares` is a compound unit needing structured
  parsing, not a string token match.

## 13. Nil / duplicate findings

- **Nil:** the XBRL instance had **0 `nil="true"` facts** for this filing, and
  **companyfacts has no nil representation at all** — a nil in the source would
  simply be *absent* from companyfacts. So companyfacts cannot distinguish
  "reported nil" from "not reported." (data-model §13 case 14 — absence ≠ nil —
  must be enforced at the instance level, not companyfacts.)
- **A `val=0` surprise:** `CommonStockSharesIssued`/`Outstanding` for period-end
  2016-12-31 was reported as **`0`** in the Q3-2017 10-Q (accn …17-000118) while
  other filings report ~1.2B. This is a real filer data-quality artifact — a
  literal zero, not nil. The canonical layer must treat it as a legitimate (if
  suspect) observation and let PIT/restatement logic handle supersession.
- **Duplicates:** 5,027 period-groups had **identical values across multiple
  filings** (pure repeats). Deduplication by `(concept,unit,period,dimensions,
  value)` is needed to avoid double-counting; but each repeat still carries a
  distinct `accn` and availability, which the PIT layer needs.
- **Missing frames:** only 8,794/21,968 observations have a `frame`; `frame` is
  **not** a reliable key and must be treated as optional metadata.

## 14. Filing-document findings

The filing directory index (`index.json`) for the restatement 10-K listed **188
files**, including the full XBRL package:

- `khc-20181229.xml` — **XBRL instance** (24.6 MB).
- `khc-20181229.xsd` — schema.
- `khc-20181229_cal.xml` — **calculation** linkbase.
- `khc-20181229_def.xml` — **definition** linkbase (dimensions live here).
- `khc-20181229_lab.xml` — **label** linkbase.
- `khc-20181229_pre.xml` — **presentation** linkbase.
- `FilingSummary.xml`, `R*.htm` rendered reports, the primary `.htm`, exhibits,
  images, css/js.

**For strong provenance OpenFinance should retain (content-addressed):** the
primary document, the XBRL **instance**, and the **schema + 4 linkbases**
(cal/def/lab/pre) — the def/lab linkbases are needed to interpret dimensions and
concept labels. The `index.json` itself is worth keeping as the filing manifest.
(Note the index's `type`/`size` fields were unreliable — several `type` values
were literally `"text.gif"` and some `size` fields empty — so don't trust index
metadata; trust the fetched bytes + hash.)

## 15. Public-availability evidence

Per the brief, **no availability rule was invented.** What the SEC actually
exposes as evidence:

| Evidence | Where | Strength for "available to a researcher" |
|----------|-------|------------------------------------------|
| `acceptanceDateTime` (UTC, ms) | submissions | Strong lower bound on *processing*; **"accepted" ≠ "available."** |
| `filingDate` (date) | submissions | Legal "deemed filed"; **not** retrievability, no intraday. |
| Filing directory `index.json` + `Last-Modified` header | Archives | The instance we fetched had `Last-Modified: 2019-06-07 21:10:48 GMT` — **~3 min after** its 21:07:36Z acceptance. Suggestive of near-real-time dissemination but is a *server* mtime, not a guaranteed public-visibility timestamp. |
| Our own **retrieval timestamp** | ingestion | Upper bound only. |
| Daily-index / full-text-index appearance | (not fetched this pass) | Would be the strongest *direct* dissemination evidence; not yet inspected. |

**Distinctions, as observed:**
- **Accepted** (acceptanceDateTime) and **deemed filed** (filingDate) demonstrably
  differ (67 cases) and can even fall on different calendar days.
- **Available through EDGAR**: the `Last-Modified` on the S3-served instance is
  the closest signal we found, ~3 minutes post-acceptance — but it is not a
  documented public-availability guarantee.
- **Available to a researcher**: **no field directly states this.**

**Conclusion:** the SEC does **not** expose an exact, authoritative "became
publicly available at" timestamp. `acceptanceDateTime` (UTC) + the historical
~17:30 ET dissemination convention + business calendar is the best *derivable*
estimate, and the daily/full-text index is the best *direct* evidence — but
neither is a certainty. This **confirms** the data-model's decision to make
availability a **derived, policy-versioned, statused (verified/derived/unknown),
fail-closed** quantity. It should not be treated as a raw SEC field.

## 16. Identifier findings

| Identifier | Stability | Verdict |
|------------|-----------|---------|
| **CIK** | SEC-assigned, permanent. Appears as `"0001637459"` (padded str) in submissions but `1637459` (int) in companyfacts. | **Primary company id.** Must canonicalize padding across endpoints. |
| Ticker (`KHC`) | Mutable; the model must not depend on it. KHC is post-merger; tickers change on M&A. | **Not an identifier.** Attribute only. |
| Company name | Mutable — `formerNames` shows `H.J. Heinz Holding Corp` → `Kraft Heinz Co` with effective dates. | **Not an identifier.** Effective-dated history. |
| Exchange (`Nasdaq`) | Mutable. | Attribute only. |
| `ein`, `lei` | `ein` present; **`lei` was null.** | Optional; `lei` not reliably available. |
| Accession number | SEC-assigned, immutable, globally unique. | **Primary filing id** (confirmed §7). |
| Security-level id (FIGI/CUSIP) | **Not present in either endpoint.** | Requires an external source; the data-model's `security_id` cannot be sourced from EDGAR company APIs alone. |

Confirms data-model §11: CIK for company, accession for filing. **New caveat:**
CIK is formatted **inconsistently** (padded string vs int) across the two
endpoints — canonicalization is mandatory. Security identifiers are **not
available from these endpoints** at all.

## 17. Access / rate-limit findings

- **No API key required.** SEC uses a **declared User-Agent** for identification.
- **`www.sec.gov/Archives` returns HTTP 403 without an email-format contact** in
  the UA; `data.sec.gov` was lenient. A production fetcher must send an
  email-style contact (sourced from config/env, never hardcoded personal data).
- **Rate guidance:** SEC's published limit is **≤ 10 requests/second**; there is
  **no `X-RateLimit-*` header** — throttling is by IP and can yield 403/429. Our
  fetcher used 0.35 s spacing (~3 req/s), comfortably safe.
- **Caching signals are excellent:** responses carry `ETag`, `Last-Modified`,
  `Accept-Ranges: bytes`, and are S3-backed (`x-amz-*`). `Content-Encoding: gzip`
  shrank the 24.6 MB instance to 842 KB on the wire. A respectful ingester should
  send `If-None-Match`/`If-Modified-Since` and honor gzip.
- **Recommended behavior:** declared UA w/ contact, ≤ ~5 req/s, ret/backoff on
  403/429, conditional requests, and persistent content-addressed caching so raw
  bytes are fetched exactly once.

## 18. Storage estimates

Observed sizes (one large issuer, ~11 years):

| Artifact | Size |
|----------|------|
| submissions JSON | 143 KB |
| companyfacts JSON | 3.36 MB (22,033 observations) |
| One XBRL instance (traditional) | 24.6 MB raw / **842 KB gzipped** |
| Filing index.json | 17.7 KB |

Extrapolation (order-of-magnitude, **not** downloaded): ~8,000 filing entities
with financials; SEC's *bulk* `submissions.zip` and `companyfacts.zip` are each
~1.5 GB compressed. Full XBRL instances for all issuers/all years are the large
cost — tens to low-hundreds of GB raw, but they **gzip ~30×** and are
content-addressed (fetch once).

**Verdict on the proposed architecture:** the **content-addressed raw store +
Parquet + DuckDB** design is **reasonable and appropriately sized** for a single
developer. companyfacts + submissions for the whole market is a few GB — trivial
for DuckDB. The instance corpus is the only heavy component; storing it gzipped
and content-addressed (as designed) keeps it manageable, and we only need the
instance when dimensional facts are required.

## 19. Data-model validation matrix

| Design assumption (data-model.md) | Observed reality | Valid? | Required change |
|---|---|---|---|
| CIK is the stable company id | CIK permanent; but formatted padded-str in submissions, int in companyfacts | **CONFIRMED** (w/ caveat) | Canonicalize CIK formatting on ingest. |
| Accession is the stable filing id | Uniform `NNNNNNNNNN-NN-NNNNNN`, 0 malformed/missing | **CONFIRMED** | none |
| Fact→Filing via `accn` join | 100% of companyfacts accns resolved in submissions | **CONFIRMED** | Must also read `filings.files` overflow pages for large issuers. |
| Fact carries acceptance timestamp | companyfacts has **no** acceptance time; only in submissions | **PARTIALLY CONFIRMED** | Availability/timestamps **require a submissions join**; companyfacts alone is insufficient (already flagged in data-model §15.2). |
| `acceptance_timestamp` is Eastern Time | It is **UTC** (`Z`), ms precision | **INVALIDATED** | Correct data-model §2/§6.4: store as UTC as given; apply any ET cutoff *after* converting to ET. |
| Availability ≠ acceptance; must be derived/policy/statused | SEC exposes **no** authoritative availability field; only acceptance+filingDate+index mtime | **CONFIRMED** | none — reconnaissance strengthens §PA. |
| No ordering assumed between filing_date and acceptance | Acceptance can be a **later UTC day** yet earlier ET instant than filingDate | **CONFIRMED** | none (revised invariant 10 was correct). |
| Observation key needs `dimensions_hash` | Dimensions exist and are essential (208 facts/concept) | **CONFIRMED** …but | **companyfacts has NO dimensions** — key must be built from the **XBRL instance**. Major sourcing change. |
| Units: USD/shares/USD-shares/pure/currency | All present + FX + **custom `khc:*` units** | **CONFIRMED** (broader) | Normalizer must tolerate custom/compound units. |
| Scale folded in; raw scale retained on RawFact | companyfacts `val` pre-scaled, **drops `decimals`**; instance keeps `decimals` | **PARTIALLY CONFIRMED** | To retain precision/scale, RawFact must come from the **instance**; companyfacts loses it (precision-drift restatements seen). |
| Period from XBRL context, not calendar | 52/53-wk calendar; period-ends drift; `fy`/`fp` are filing focus not period | **CONFIRMED** | Never use `fy`/`fp` in the observation key — use `start`/`end`. |
| Amendments = new observations, never overwrite | `10-Q/A` present; both base+amended in companyfacts w/ own accns | **CONFIRMED** | none |
| `amends_accession` link exists | **Not** in submissions/companyfacts | **INVALIDATED (must infer)** | Derive amendment linkage (form `/A` + period/issuer match or parse doc); deterministic + versioned. |
| Restatements preserve history (§KS) | $66.241B→$66.070B for same period, both retained | **CONFIRMED** | none — empirically validated. |
| nil is a first-class observation | Instance had 0 nil; **companyfacts cannot represent nil** (absent) | **PARTIALLY CONFIRMED** | Nil handling only possible from the instance; companyfacts absence ≠ nil. |
| Same fact in multiple filings | 5,773 multi-filing period-groups | **CONFIRMED** | none |
| Raw-vs-canonical separation | companyfacts is itself *derived/consolidated*; instance is rawer | **CONFIRMED** (reinforced) | Treat companyfacts as a **derived source**, not raw truth; the instance is the closer-to-raw record. |
| Security-level id (FIGI) | **Not present** in EDGAR company endpoints | **UNKNOWN / REQUIRES MORE DATA** | `security_id` needs an external mapping source; document as out-of-EDGAR. |
| Content-addressed + Parquet + DuckDB storage | Sizes modest; gzip ~30×; strong ETag/Last-Modified | **CONFIRMED** | none |

## 20. Architecture changes recommended

1. **companyfacts is a *derived, consolidated* source — not the provenance root,
   and not dimension-complete.** Reclassify it: good for a fast undimensioned
   backbone, but the **XBRL instance is the authoritative raw record** for
   dimensions, nil, and precision (`decimals`). The data-model's RawDocument/
   RawFact should be sourced from the **instance** whenever dimensional or
   precise facts are needed; companyfacts can seed the consolidated slice.
2. **Correct the timestamp timezone assumption.** `acceptanceDateTime` is **UTC**.
   Update data-model §2 (row 4) and §6.4: store as UTC; convert to ET only inside
   an AvailabilityPolicy that reasons about the ET cutoff.
3. **Mandate the submissions↔companyfacts join for any timing.** companyfacts has
   no acceptance time; the `Filing` entity's `acceptance_timestamp` must come from
   submissions, joined on accession. (Already an open item — promote to a hard
   requirement.)
4. **Amendment linkage must be derived, not read.** Add a versioned,
   deterministic step that computes `amends_accession` from form `/A` + issuer +
   period (or by parsing the amendment). Record it as data with its transformation
   version.
5. **CIK canonicalization.** Normalize CIK to zero-padded-10 on ingest (submissions
   gives padded str, companyfacts gives int).
6. **Security identifiers are out-of-EDGAR.** Document that `security_id` requires
   an external source (FIGI/CUSIP mapping); it cannot be populated from the
   company submissions/companyfacts endpoints.
7. **Precision/scale must be captured from the instance.** Add `decimals` to the
   RawFact evidence so precision-drift (e.g. `1,218,947,088` → `1,219,000,000`)
   is representable and auditable, and so we can distinguish a *precision* change
   from an economic *restatement*.
8. **Retain the full XBRL package for provenance:** instance + schema + cal/def/
   lab/pre linkbases + index.json, all content-addressed. Def/lab linkbases are
   required to interpret dimensions and labels.
9. **Access layer:** email-format contact in UA (from config), conditional
   requests (ETag/Last-Modified), gzip, ≤ ~5 req/s, backoff on 403/429.
10. **Do NOT trust index.json metadata** (`type`/`size` were wrong/empty); trust
    fetched bytes + hash.

## 21. Unknowns requiring additional investigation

1. **Daily-index / full-text-index dissemination timestamps** — not fetched this
   pass. This is the most promising *direct* public-availability evidence and
   should be inspected before finalizing any AvailabilityPolicy.
2. **Inline XBRL (iXBRL) parsing** — KHC's older filings were standalone `.xml`
   instances; 2020+ are inline (facts embedded in the primary `.htm`). We proved
   dimensions from a standalone instance; confirm the same extraction from inline
   filings (and whether SEC's `Financial_Report.xlsx`/`R*.htm` help).
3. **Cross-issuer generality** — all findings are from one issuer. Validate the
   UTC timestamp, dimension-drop, and accession-join claims across ≥5 diverse
   issuers (different fiscal calendars, foreign private issuers/20-F, financials).
4. **`filings.files` pagination** — KHC fit on one page; verify the overflow-page
   join for a heavy filer so accessions aren't spuriously "missing."
5. **Amendment-linkage reliability** — how often form `/A` + period is enough vs
   needing document parsing; quantify error rate.
6. **companyfacts vs instance value discrepancies** — does companyfacts ever
   disagree with the instance's undimensioned value (rounding, corrections)?
   Needs a systematic diff.
7. **Historical dissemination-cutoff changes** — the ~17:30 ET convention and SEC
   holiday calendar over time (pre-2005 vs now) — required to date old filings.
8. **Non-XBRL / pre-2009 filings** — no structured facts; likely the main
   `unknown`-availability population.

---

# Part II — Cross-Issuer Validation

> **Second reconnaissance phase.** The Part I findings above came from a single
> issuer (Kraft Heinz). This part re-runs the key investigations across **6
> diverse issuers** to determine whether those findings generalize before the
> ingestion contract is locked. Same isolation rules: stdlib-only fetch,
> declared email-format User-Agent from env, on-disk cache, everything under
> `C:\dev\openfinance-recon-tmp\`, nothing committed, no dependency installed.

## II.1 Issuer set

| Slug | Issuer | CIK | Profile exercised | Filing patterns |
|------|--------|-----|-------------------|-----------------|
| apple | Apple Inc. | 0000320193 | large accelerated filer, technology | 11 × 10-K, standalone→inline XBRL, 3 former names |
| jpmorgan | JPMorgan Chase & Co. | 0000019617 | financial, very high filing volume | 25,717 recent rows + **69 overflow pages**, 9 tickers/1 CIK, 4 former names |
| meta | Meta Platforms Inc. | 0001326801 | technology, **name + ticker change** | Facebook→Meta (2021), inline iXBRL, geographic dimensions |
| ge | General Electric Co. | 0000040545 | industrial, **heavy segments** | segment/legal-entity/product axes, typed members, reorganizations |
| tesla | Tesla Inc. | 0001318605 | **amended filings**, reincorporation | 6 × 10-K/A (partial), name change, DE→TX reincorporation |
| kraftheinz | Kraft Heinz Co. | 0001637459 | restatement + amendments (Part I) | genuine restatement, 2 × 10-Q/A, 52/53-wk calendar |

Sample sizes: **~30,600 submission rows** in the recent pages, **164,096
submission accessions** for JPMorgan alone once overflow pages were followed,
and **companyfacts observation counts** of 17,730 (meta) / 24,131 (tesla) /
25,135 (apple) / 40,427 (ge) / 52,369 (jpmorgan) / 22,033 (khc). Four full XBRL
instances were parsed (apple-2018, ge-2018, tesla-2018 standalone; meta-2025
inline) plus the Part I KHC-2018 instance.

## II.2 Timestamp validation — CONFIRMED, universally

| Issuer | rows | acceptanceDateTime format | bad | endsWith Z | filingDate≠accept-day |
|--------|------|---------------------------|-----|-----------|-----------------------|
| apple | 1000 | `(24,'Z')` ms | 0 | 1000/1000 | 86 |
| jpmorgan | 25717 | `(24,'Z')` ms | 0 | 25717/25717 | 2977 |
| meta | 1013 | `(24,'Z')` ms | 0 | 1013/1013 | 199 |
| ge | 1001 | `(24,'Z')` ms | 0 | 1001/1001 | 46 |
| tesla | 1001 | `(24,'Z')` ms | 0 | 1001/1001 | 378 |
| kraftheinz | 874 | `(24,'Z')` ms | 0 | 874/874 | 67 |

- **Timezone: UTC**, without exception. Every one of ~30,600 acceptance values
  is a 24-char `YYYY-MM-DDThh:mm:ss.000Z`. **0 bad formats, 100% `Z`-suffixed.**
- **Precision: milliseconds** (always `.000`).
- **Relationship to filingDate:** they routinely differ (Tesla 378, JPMorgan
  2977), and the direction is telling — for periodic reports, acceptance is often
  a UTC instant on the **day before** `filingDate` (post-ET-cutoff → deemed filed
  next business day). Concrete: Apple `10-Q` accepted `2024-08-01T22:03:34Z`
  (≈18:03 ET) → `filingDate=2024-08-02`. Tesla `10-K` accepted
  `2024-01-27T02:00:20Z` (a **Saturday**) → `filingDate=2024-01-29` (Monday).
- **Consistency across forms:** the format is identical for every form type;
  only the *mismatch rate* varies (ownership Form 4/3 dominate mismatches because
  they're filed late in the day).
- **Exceptions: none found.** No non-UTC, no missing, no alternate precision.

**Verdict:** the Part I finding generalizes. Store acceptance as UTC as given;
the data model's former ET assumption is corrected. Apply any ET cutoff *after*
converting UTC→ET inside the AvailabilityPolicy.

## II.3 CompanyFacts vs XBRL instance — rule CONFIRMED across issuers

Dimensional coverage in real instances (one 10-K each):

| Issuer (instance) | contexts | dimensional | typed members | distinct axes incl. |
|-------------------|----------|-------------|---------------|---------------------|
| apple 2018 | 356 | 337 (94%) | 0 | DebtInstrument, FairValueHierarchy, EquityComponents |
| ge 2018 | 1332 | 1313 (98%) | 7 | **BusinessSegments**, ConsolidationItems, **LegalEntity**, **ProductOrService** |
| tesla 2018 | 635 | 614 (96%) | 1 | DebtInstrument, BusinessAcquisition, PP&E-by-type |
| meta 2025 | 291 | 270 (92%) | 0 | FairValueHierarchy, **Geographical**, ClassOfStock |
| khc 2018 (Part I) | 1247 | 1217 (98%) | 0 | EquityComponents, NoncontrollingInterest |

The single starkest instance-vs-companyfacts gap, GE `RevenueFromContractWith
CustomerExcludingAssessedTax`: the **instance holds 214 facts (211 dimensional)**
for that one concept in one 10-K, while **companyfacts retains 43 observations
total across all filings ever** — because companyfacts keeps only the
undimensioned consolidated slice. Meta's revenue: 45 instance facts (33
dimensional, incl. geographic) vs companyfacts' undimensioned-only view.

- **Dimensions:** present and dominant (92–98%) for every issuer; **typed
  members** confirmed (GE 7, Tesla 1) — the model's typed-member handling is
  needed, not hypothetical. companyfacts drops **all** of them.
- **Nil:** 0 `nil="true"` in every instance sampled; companyfacts still has **no
  nil representation**. (Absence ≠ nil holds.)
- **decimals/precision:** present in every instance (`-9…4`, `INF`), dominated by
  `-6` (millions); still **absent from companyfacts**.
- **Contexts/units:** every instance carries custom `<issuer>:*` units
  (`ge:segment`, `meta:judicialCase`, `aapl:Customer`, `tsla:Vehicles`) and
  compound `USD/shares` (`divide`). No issuer was representable by a bare
  string-token unit vocabulary.

**Verdict — rule holds with no exceptions:** *XBRL instance = authoritative raw
provenance; CompanyFacts = derived/consolidated secondary source.* The
observation key (with `dimensions_hash`) must be built from the instance.

## II.4 Accession join — CONFIRMED, with the pagination caveat proven

`companyfacts.accn → submissions.accessionNumber`, all issuers:

| Issuer | cf observations | distinct cf accns | submissions accns (recent+overflow) | malformed | **missing** |
|--------|-----------------|-------------------|--------------------------------------|-----------|-------------|
| apple | 25,135 | 72 | 2,238 (+1 pg) | 0 | **0** |
| jpmorgan | 52,369 | 3,132 | 164,096 (**+69 pgs**) | 0 | **0** |
| meta | 17,730 | 59 | 4,155 (+2 pgs) | 0 | **0** |
| ge | 40,427 | 78 | 4,775 (+2 pgs) | 0 | **0** |
| tesla | 24,131 | 68 | 1,748 (+1 pg) | 0 | **0** |
| kraftheinz | 22,033 | 49 | 874 (+0 pgs) | 0 | **0** |

- **0 malformed, 0 missing** across all issuers — the join is reliable.
- **Pagination is mandatory, now proven:** JPMorgan's history spans **69 overflow
  `filings.files` pages** (164k accessions). Had we used only `filings.recent`,
  thousands of older companyfacts accessions would have appeared "missing." An
  ingester that ignores `filings.files` will produce false orphans.
- **Duplicates:** the same accession legitimately appears on many companyfacts
  observations (it's the source filing for thousands of facts); no *submission*
  accession duplicates were seen.

## II.5 Amendment relationship — no source link exists; classify as derived

Investigated Tesla (5 × 10-K/A) and Kraft Heinz (2 × 10-Q/A) in depth, plus the
full `/A` inventory across all issuers.

**What SEC exposes — checked exhaustively:**
- **submissions API columns:** `accessionNumber, filingDate, reportDate,
  acceptanceDateTime, act, form, fileNumber, filmNumber, items, core_type, size,
  isXBRL, isInlineXBRL, isXBRLNumeric, primaryDocument, primaryDocDescription`.
  **No base-accession field.**
- **companyfacts:** amendment facts are tagged with `form` (`10-K/A`) and their
  own `accn`, but there is **no link to the amended accession**.
- **SGML submission header** (fetched `…-index-headers.html` for Tesla's 2019
  10-K/A): carries `ACCESSION-NUMBER`, `TYPE=10-K/A`, `PERIOD=20191231`,
  `FILE-NUMBER=001-34756`, `FORMER-COMPANY` — but **no reference to the original
  10-K's accession.**

**What reliably establishes the relationship (derived):** form = base + `/A`,
same CIK, same `reportDate`, and a single matching base filing with consistent
chronology. Every 10-K/A and 10-Q/A in the set resolved to **exactly one** base
filing with the same `reportDate`:

| Amendment | reportDate | Resolved base (same reportDate) |
|-----------|-----------|----------------------------------|
| tesla 10-K/A `…20-018984` | 2019-12-31 | 10-K `…20-004475` |
| tesla 10-K/A `…21-022604` | 2020-12-31 | 10-K `…21-004599` |
| tesla 10-K/A `…22-016871` | 2021-12-31 | 10-K `…22-000796` |
| khc 10-Q/A `…17-000116` | 2017-04-01 | 10-Q `…17-000081` |
| khc 10-Q/A `…17-000117` | 2017-07-01 | 10-Q `…17-000101` |

**Classification of the resulting link:**

| Confidence | When | Frequency in recon |
|------------|------|--------------------|
| `SOURCE_ASSERTED` | SEC states the base accession | **never** (no such field anywhere) |
| `DERIVED_HIGH_CONFIDENCE` | `/A` + same CIK + same `reportDate` + exactly one base + chronology OK | all 7 periodic amendments |
| `DERIVED_LOW_CONFIDENCE` | `/A` + period but ambiguous/multiple base candidates | possible for re-reported periods |
| `UNKNOWN` | no defensible base | represent as standalone |

**Extra finding — partial amendments:** Tesla's 10-K/A filings contain only a
**cover-page XBRL stub** (schema + lab + pre + an `_htm.xml` with a handful of
dei facts) and **no financial instance** — 14-file packages vs the 165-file base
10-K. So an amendment can be legally significant while asserting *no* financial
facts. Supersession must be **per-`obs_key`**, not "amendment replaces filing."

**Model impact:** `amends_accession` is derived, carries
`amendment_link_confidence`, and PIT correctness must not depend on it (§7.1 of
the data model; supersession runs on `obs_key`+availability). Where no base is
defensible, represent uncertainty (`UNKNOWN`) — never guess.

## II.6 Restatement validation — CONFIRMED across all issuers

Every issuer shows same-period, differing-value observations retained across
filings with distinct accessions:

| Issuer | multi-filing period-keys | identical repeats | **differing-value (restatement candidates)** |
|--------|--------------------------|-------------------|----------------------------------------------|
| apple | 7,139 | 6,713 | **426** |
| jpmorgan | 14,554 | 13,544 | **1,010** |
| meta | 5,082 | 4,799 | **283** |
| ge | 10,706 | 6,432 | **4,274** |
| tesla | 6,712 | 5,694 | **1,018** |
| kraftheinz | 5,773 | 5,027 | **746** |

Confirmed for each: (a) the **old observation remains available** (both rows
present); (b) later observation has a **different accession**; (c) the **same
economic period carries multiple values**; (d) §KS PIT selection distinguishes
the knowledge states by availability time.

**Dimensions/units affect equivalence — proven:** several "restatements" are
actually **scale artifacts**, e.g. Tesla `DebtInstrumentCarryingAmount`
2016-12-31 = `7,511,760` (original 10-K) vs `7,511,760,000` (next 10-Q) — a ×1000
scale correction, not an economic restatement; JPMorgan showed a **sign flip**
(`±2,755,024,000,000`). This validates that `unit`/`scale` must be part of
equivalence and that raw `decimals`/`scale` must be preserved to tell a precision
change from a real restatement. Meta `OtherLiabilitiesNoncurrent` 2023-12-31
went `$8.884B → $1.370B` across the 2024 10-K vs 10-Q — a genuine reclassification
restatement, both retained.

## II.7 Dimension validation — deterministic hash confirmed feasible

Across issuers we saw **segment** (GE `StatementBusinessSegmentsAxis`, 402
contexts), **geographic** (Meta `StatementGeographicalAxis`), **product** (GE
`ProductOrServiceAxis`, 140), **legal-entity** (GE `LegalEntityAxis`, 219),
equity-component, fair-value-hierarchy, and **typed** dimensions (GE 7, Tesla 1).

A deterministic `dimensions_hash` is feasible with this canonical serialization
(validated by parsing all four instances):
- Explicit members: sorted list of `(axis_qname, member_qname)` pairs.
- Typed members: `(axis_qname, "[typed]" + child_element_qname + "=" +
  normalized_text_value)`.
- Namespaces resolved to stable QNames (prefixes vary between filings);
  undimensioned/default context → empty sentinel.
Sorting makes it order-independent; QName resolution makes it filing-independent.
(Serialization documented; **not** implemented — per instructions.)

## II.8 Unit validation — needs a structured representation

Real unit vocabulary across issuers:

| Kind | Examples observed | Representation needed |
|------|-------------------|-----------------------|
| Currency | `iso4217:USD`, `EUR`, `INR`, `CAD` + FX pairs | `unit_id` + `currency` |
| Shares | `xbrli:shares` | `unit_id` |
| Per-share (compound) | `USD/shares` via XBRL `divide` (num=`iso4217:USD`, den=`shares`) | `numerator` + `denominator` |
| Ratio | `xbrli:pure` (used for both ratios and percentages) | `unit_id`; percent-vs-ratio ambiguity noted |
| Duration | `utr:D` (Tesla) | `unit_id` |
| **Custom** | `ge:segment`, `meta:judicialCase`, `aapl:Customer`, `tsla:Vehicles`, `khc:Brand` | pass-through `unit_id`, tolerate unknown |

**Conclusion:** the canonical unit needs **unit identifier + numerator +
denominator + currency + scale + decimals** — a single token string is
insufficient (compound and custom units break it). Data model §3.1 updated to add
`unit_numerator`/`unit_denominator`; `scale`/`decimals` already present.

## II.9 Identifier validation — CIK holds; company≠security proven

| Issuer | CIK (subs / companyfacts) | tickers | former names (count) | change exercised |
|--------|---------------------------|---------|----------------------|------------------|
| apple | `"0000320193"` / `320193` | AAPL | 3 (Apple Computer→Apple) | name |
| jpmorgan | `"0000019617"` / `19617` | **9** (JPM + 8 preferred) | 4 (Chemical Banking→Chase→JPM) | **merger chain**, multi-security |
| meta | `"0001326801"` / `1326801` | META | 1 (**Facebook→Meta**) | **name + ticker** |
| ge | `"0000040545"` / `40545` | GE | 0 | reorganizations (no CIK change) |
| tesla | `"0001318605"` / `1318605` | TSLA | 1 (**Tesla Motors→Tesla**) | name; **DE→TX reincorporation** |
| kraftheinz | `"0001637459"` / `1637459` | KHC | 1 (H.J. Heinz→Kraft Heinz) | merger-origin name |

Findings:
- **CIK is a suitable stable company identity.** It survived every name change,
  ticker change, and even Tesla's state-of-incorporation change (DE→TX) — the
  legal entity changed domicile, CIK did not.
- **Required: canonicalize CIK format.** submissions returns a **zero-padded
  string**; companyfacts returns an **int** — for all 6 issuers. One `company_id`
  must absorb both.
- **Company ≠ Security is empirical, not theoretical:** JPMorgan exposes **9
  tickers under one CIK** (common + 8 preferred series). The `Company 1─∞
  Security` split is required.
- **Name history is available** via `formerNames` (effective-dated); maps onto
  the model's effective-dated `Company` history. No `EntityHistory` entity needed.
- **No Filer-vs-Company split needed** for these issuers (one CIK = filer =
  registrant throughout). True multi-CIK succession remains an open alias-mapping
  item (data-model §15.7).
- **`lei` was null for every issuer**; `ein` present. FIGI/CUSIP absent from both
  APIs → `security_id`(FIGI) needs an external source.

## II.10 Filing package validation — components consistent, era-dependent shape

Package components present (10-K each):

| Issuer/year | instance | schema (.xsd) | cal | def | lab | pre | extras |
|-------------|:---:|:---:|:---:|:---:|:---:|:---:|--------|
| apple 2018 | ✅ standalone `.xml` | ✅ | ✅ | ✅ | ✅ | ✅ | Financial_Report.xlsx |
| ge 2018 | ✅ standalone `.xml` | ✅ | ✅ | ✅ | ✅ | ✅ | Financial_Report.xlsx (253 files) |
| tesla 2018 | ✅ standalone `.xml` | ✅ | ✅ | ✅ | ✅ | ✅ | Financial_Report.xlsx |
| meta 2025 | ✅ inline `_htm.xml` | ✅ | ✅ | ✅ | ✅ | ✅ | **MetaLinks.json** (no xlsx) |
| tesla 2020 10-K/A | ⚠️ **cover-page stub only** | ✅ | — | — | ✅ | ✅ | no financial instance |

- The full **5-part linkbase set** (schema + cal + def + lab + pre) plus the
  instance is present for every full periodic filing → the model's
  content-addressed package (instance + schema + 4 linkbases + index) is the
  right retention set. The **def** linkbase (dimensions) and **lab** (labels) are
  required to interpret facts.
- **Era shape differs:** pre-~2020 = standalone instance + `Financial_Report.xlsx`;
  ~2020+ = inline iXBRL with extracted `*_htm.xml` + `MetaLinks.json`. Ingestion
  must handle both; both parse to the same fact model (validated on Meta 2025).
- **Some components are absent for partial amendments** (Tesla 10-K/A: no
  financial instance, no cal/def). Retention must tolerate missing components.
- **index.json metadata still unreliable** (`type` = `"text.gif"`, empty `size`)
  — trust fetched bytes + hash, confirmed again across issuers.

## II.11 Public availability — evidence ceiling established (do not finalize policy)

Investigated (no policy invented, no timestamps fabricated):

- **Daily index** (`daily-index/2019/QTR2/form.20190607.idx`): header literally
  reads *"Daily Index of EDGAR Dissemination Feed by Form Type."* It lists each
  filing's CIK/form/date/path — but at **date granularity only** (no intraday
  dissemination time). This is the best *direct* dissemination evidence and it is
  **date-level**.
- **Archive `Last-Modified`** vs acceptance, three issuers:
  | issuer | acceptance | archive Last-Modified | lag |
  |--------|-----------|-----------------------|-----|
  | apple | 2018-11-05T13:01:40Z | Mon, 05 Nov 2018 13:04:06 GMT | ~2.4 min |
  | ge | 2019-02-26T21:36:51Z | Tue, 26 Feb 2019 21:43:26 GMT | ~6.6 min |
  | tesla | 2019-02-19T11:10:16Z | Tue, 19 Feb 2019 11:14:05 GMT | ~3.8 min |
  Consistent ~2–7 min lag, both UTC — suggestive of near-real-time dissemination,
  but a **server mtime**, not a guaranteed public-visibility timestamp.
- **After-hours / weekend / holiday:** post-ET-cutoff periodic filings are
  **deemed filed the next business day** (Apple 10-Q accepted 22:03Z→next day;
  Tesla 10-K accepted Sat 02:00Z→Mon). Direct evidence the cutoff/calendar hazard
  is real and must live in the policy.

**Availability evidence classification (realistically obtainable):**

| Class | Evidence | Granularity |
|-------|----------|-------------|
| `VERIFIED` | direct dissemination-feed appearance | **date-level** (daily index) — rarely intraday |
| `DERIVED` | acceptance (UTC, ms) + policy cutoff/calendar | second-level, conservative |
| `UNKNOWN` | no acceptance, pre-XBRL, orphaned | — → fail closed |

**Implication for the model:** true intraday `VERIFIED` availability is
**rarely** attainable from SEC alone; most facts will be `DERIVED`, and a real
population will be `UNKNOWN`. The fail-closed design is not merely defensive —
it is the *expected common path* for anything lacking clean evidence. The
AvailabilityPolicy remains **unvalidated** (cutoff value + form/era variance +
holiday calendar still open); do not finalize it.

---

## Implementation Contract

What the eventual ingestion implementation **is allowed to assume**, separated by
guarantee strength. This is the load-bearing output of reconnaissance.

### GUARANTEED BY OBSERVED SEC DATA

Safe to rely on (validated across 6 issuers / ~180k accessions / 5 instances):

1. **`acceptanceDateTime` is UTC**, `YYYY-MM-DDThh:mm:ss.000Z`, millisecond
   precision, present on every submission. Store as-is; no ET conversion on
   ingest.
2. **Accession numbers** are uniform `NNNNNNNNNN-NN-NNNNNN`, immutable, unique,
   and a **reliable join key** between companyfacts and submissions (0 malformed,
   0 missing) — **provided `filings.files` overflow pages are followed.**
3. **CIK is stable** across name/ticker/reincorporation changes and is the
   correct company identity. It is formatted **padded-string in submissions,
   int in companyfacts** — canonicalize.
4. **XBRL instance is the authoritative fact source.** It carries dimensions
   (92–98% of contexts), typed members, `decimals`, nil, and full units.
5. **companyfacts is a derived, consolidated secondary source** — undimensioned
   only, no acceptance time, no nil, no `decimals`. Fine as a fast backbone;
   never the provenance root for dimensional/precise/nil facts.
6. **Restatements retain both observations** with distinct accessions; the same
   period legitimately carries multiple values across filings.
7. **The full XBRL package** (instance + schema + cal/def/lab/pre) is present for
   full periodic filings; the **def** and **lab** linkbases are needed for
   dimensions and labels.
8. **`formerNames`** provides effective-dated name history; company≠security is
   real (one CIK → many securities/tickers).
9. **Access:** no API key; `www.sec.gov/Archives` requires an **email-format**
   User-Agent (403 otherwise); `data.sec.gov` is lenient; ≤10 req/s; strong
   `ETag`/`Last-Modified`/gzip.

### DERIVED BY OPENFINANCE (must be computed, versioned, auditable)

Not given by SEC — the implementation must derive these deterministically and
record how/with what confidence:

1. **`derived_public_availability_timestamp` + `availability_status`** — from
   acceptance + a versioned `AvailabilityPolicy` (cutoff/calendar), fail-closed.
2. **`amends_accession` + `amendment_link_confidence`** — SEC provides **no**
   base-accession link anywhere; derive from form-`/A` + CIK + `reportDate` +
   single-candidate + chronology; classify `DERIVED_HIGH/LOW_CONFIDENCE` or
   `UNKNOWN`. Never required for PIT correctness.
3. **`dimensions_hash`** — from the instance's contexts (sorted explicit
   `(axis,member)` QNames; typed-member serialization); undimensioned → sentinel.
4. **Canonical units** — structured `unit_id`/`numerator`/`denominator`/
   `currency`/`scale`/`decimals`, from a `TransformationVersion`-owned map;
   tolerate custom `<issuer>:*` units.
5. **Normalized `value_numeric`** in base units (scale folded in), with raw
   `value`/`unit`/`scale`/`decimals` preserved on `RawFact` (distinguishes a
   precision/scale change from an economic restatement — Tesla ×1000, JPMorgan
   sign flip seen).
6. **Canonical `company_id`** absorbing the padded-string/int CIK discrepancy.
7. **PIT selection & the PIT-vs-REVISED distinction** — §6.3/§KS, over the
   append-only history.

### UNKNOWN / FAIL CLOSED (never guess)

The implementation must **refuse to invent** these and exclude affected facts
from normal PIT research:

1. **Exact intraday public-availability instant.** SEC's best direct evidence is
   **date-level** (daily dissemination index) + a server `Last-Modified`; no
   guaranteed intraday visibility timestamp exists. When a policy cannot defend a
   timestamp → `availability_status = unknown` → PIT-ineligible.
2. **The precise dissemination cutoff and its form/era variance, and the SEC
   holiday calendar.** Observed to matter (next-business-day rollovers) but not
   yet pinned; the `AvailabilityPolicy` stays `unvalidated` until it is.
3. **Amendment base accession** when ambiguous or absent → `UNKNOWN`; represent
   the amendment standalone.
4. **Availability of pre-XBRL / non-XBRL filings** → expected `unknown`
   population; do not fabricate.
5. **Security-level identity (FIGI/CUSIP)** — absent from EDGAR company APIs;
   requires an external source, not guessable.
6. **True multi-CIK merger/succession** mapping — needs explicit alias data, not
   inference.

---

## Part II — Final architecture review

**1. Is the current data model implementation-ready?**
**Yes, once the evidence-driven edits already applied to `docs/data-model.md`
are accepted.** Every core design decision survived cross-issuer validation:
append-only history, `obs_key` supersession, derived/fail-closed availability,
PIT-vs-REVISED, content-addressed provenance, CIK identity, company≠security.
No structural redesign is required and no new entity is warranted (Filer/Company,
AmendmentRelationship, RelationshipConfidence, AvailabilityEvidence, EntityHistory
were each evaluated and the existing model represents them cleanly).

**2. What exact changes are required before implementation?** (all now made in
the data model)
- Acceptance timestamp semantics: **UTC, ms** (was ET). *(§2, §6.4)*
- **Sourcing rule made explicit**: XBRL instance = raw provenance for
  dimensions/nil/decimals; companyfacts = derived backbone. *(§15.2/§15.5)*
- **`amends_accession` is derived** with `amendment_link_confidence`. *(§7.1,
  inv. 22a)*
- **Structured units** (`unit_numerator`/`unit_denominator` + existing
  scale/decimals). *(§3.1)*
- **CIK canonicalization** (padded-string vs int). *(§11)*
- **Mandatory `filings.files` pagination** for the accession join. *(§15.2)*
- **`security_id`(FIGI) is out-of-EDGAR**; capture `decimals`/scale on RawFact for
  precision-drift. *(§11, inv. 26 — already present)*

**3. What remains intentionally unknown?**
The exact intraday dissemination instant, the precise cutoff + its form/era
variance, and the SEC holiday calendar. The `AvailabilityPolicy` stays
`unvalidated`; borderline facts are `unknown` and PIT-excluded. This is by design.

**4. What must fail closed?**
Any fact whose availability cannot be defended (no acceptance, pre-XBRL, orphan,
out-of-scope form/era) → `availability_status = unknown` → never PIT-eligible.
Amendment links that are ambiguous → `UNKNOWN`, no guessed base. Unknown units →
preserved structurally, never dropped or coerced.

**5. What data must be preserved forever?**
Raw bytes (content-addressed): the **XBRL instance**, schema, and cal/def/lab/pre
linkbases, the primary document, the filing `index.json`, and the submissions +
companyfacts JSON. All raw availability **evidence** (acceptance, filingDate,
dissemination/index observations, retrieval time). Every `RawFact` with its raw
`value`/`unit`/`scale`/`decimals`/`context_ref`. All superseded observations
(restatement history). Every version record (Transformation, AvailabilityPolicy,
Dataset).

**6. What can safely be treated as derived (rebuildable, not preserved as truth)?**
companyfacts (a consolidated projection of the instances); the normalized `Fact`
(a deterministic function of RawFact + TransformationVersion); `dimensions_hash`,
canonical units, `value_numeric`; the availability triple; the amendment link;
`company_id` canonicalization; and both PIT and REVISED query results. All are
reproducible from preserved raw data + versioned code, so they may be recomputed
and need not be trusted as primary.

---

## Bottom line

The approved data model is **structurally sound and confirmed by real data**,
now across **6 diverse issuers** (Part II) — most importantly, the append-only
Historical-Knowledge-State/restatement design and the derived-fail-closed
availability model both matched reality exactly, and every candidate new entity
was found unnecessary. **The evidence-driven corrections are:** (1)
acceptanceDateTime is **UTC**, not ET; (2) **companyfacts drops all dimensions,
nil, and precision** — the XBRL **instance** must be the raw source for those;
(3) **`amends_accession` is not provided** by SEC and must be derived with
explicit confidence; (4) **structured units** and **CIK canonicalization**; (5)
**`filings.files` pagination is mandatory** for the accession join. None break
the model — they refine sourcing and field semantics. All corrections have been
applied to `docs/data-model.md`. See the **Implementation Contract** above for
exactly what the ingestion layer may assume, must derive, and must fail closed on.

**Verdict: the data model is implementation-ready.**
