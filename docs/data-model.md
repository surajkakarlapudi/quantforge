# Canonical Financial-Fact and Provenance Data Model

> **Status: DESIGN ONLY.** Nothing described here is implemented. No storage,
> schema, ingestion, or query code exists. This document defines the intended
> data model and the invariants a future implementation must enforce. It is the
> reference for the **Immutable Raw Data**, **Parsing / Normalization**,
> **Provenance**, and **Point-in-Time Data Layer** components in
> [ARCHITECTURE.md](../ARCHITECTURE.md).

The one guarantee this model exists to protect:

> A point-in-time research query must never use information that was not
> publicly available at the requested research timestamp.

Everything below is subordinate to that guarantee. Where correctness and
convenience conflict, correctness wins (Engineering Principle 1).

---

## 1. Design goals

1. **No look-ahead, ever.** A query as of time `T` sees only observations whose
   availability is *demonstrably known* (`availability_status ∈ {verified,
   derived}`) **and** `<= T`. Observations we cannot reliably date are excluded
   (fail-closed), not guessed. Enforced structurally, not by convention (§PA).
2. **Never overwrite history.** Amendments, corrections, and restatements are
   *new observations*, never mutations of prior ones. The historical
   information state is preserved exactly — so the same immutable history can
   answer both "what was knowable *then*?" (point-in-time) and "what is the
   revised truth *now*?" (revised) without conflating them (§KS).
3. **Full provenance.** Every canonical fact traces deterministically back
   through normalization → raw observation → raw bytes → public source.
4. **Determinism and reproducibility.** The same raw inputs + same
   transformation code always produce byte-identical canonical facts and
   identical query results. A research result names the exact snapshot and code
   that produced it.
5. **Separate raw truth from interpretation.** Immutable raw data is the system
   of record. Canonical facts are a *deterministic function* of it and can be
   fully rebuilt.
6. **Single-developer ergonomics, project-scale headroom.** Works well on one
   laptop with files + an embedded engine; the model does not have to change to
   grow into a serious open-source dataset.

---

## 2. Temporal terminology

The core discipline of this project is refusing to conflate distinct times. The
list below is ordered from "what the data is about" to "when we asked." Note
that the PIT-critical field (#7) is **not** any single SEC-supplied value — it
is a *policy-derived* estimate with an explicit reliability status, built from
several pieces of evidence (§2.1, and the dedicated §PA below).

| # | Term | Definition | Example | Source |
|---|------|------------|---------|--------|
| 1 | **Economic period** | The real-world span the value economically pertains to. Usually equals the fiscal period, but conceptually independent (e.g., a value "as of a merger date"). | Revenue *earned* Oct 2022–Sep 2023. | Interpretation |
| 2 | **Fiscal period** | The accounting period the company reports against: `period_start`, `period_end`, `period_type` (instant/duration), fiscal year, fiscal quarter. May not align to the calendar. | FY2023 = 2022-10-01 → 2023-09-30 (Apple-style). | XBRL context |
| 3 | **Filing date** | The date SEC stamps the submission ("filed as of" / "deemed filed"). **Date only, no time.** A legal/regulatory attribute, *not* evidence of public retrievability. | 2023-11-03 | EDGAR `filingDate` |
| 4 | **Acceptance timestamp** | The precise instant EDGAR *accepted* the submission for processing. **Millisecond precision, UTC** (EDGAR emits `…Z`; verified across 6 issuers / ~55k filings — §15/recon). "Accepted by SEC" ≠ "available to the public." | 2023-11-03T21:31:05.000Z (= 16:31 ET) | EDGAR `acceptanceDateTime` |
| 5 | **Dissemination / index evidence** | Observed evidence, *when available*, that a filing actually became retrievable through EDGAR: appearance in the full-text/daily index, a dissemination timestamp, or our own retrieval observation. Often absent for historical filings. | Filing appears in the 2023-11-03 daily index. | EDGAR indexes / observation |
| 6 | **Retrieval timestamp** | When *QuantForge itself* fetched the bytes. Proves the data was public *by then* — an **upper-bound** witness, never the original availability time. | 2026-08-05 10:00 ET | Ingestion |
| 7 | **Derived public-availability timestamp** | The **PIT-critical field**: a conservative estimate of when the information became available to a hypothetical researcher, produced by a versioned `AvailabilityPolicy` (§4) from evidence #3–#6, and carrying an `availability_status` of `verified` / `derived` / `unknown`. | 2023-11-06 06:00 ET (`derived`), or `unknown`. | Policy-derived |
| 8 | **Availability rule version** | The `AvailabilityPolicy` `(policy_id, policy_version)` that produced #7. Every derived availability references one. | `edgar-std/v3` | Policy record |
| 9 | **Research / as-of timestamp** | The instant a query claims to "stand at." Only observations with a **known** availability `<= as_of` are eligible (§6). | Query param. | Query |

### 2.1 Four states that are *not* the same thing

The requested distinction, made explicit. These are related but must not be
treated as identical without justification:

| State | Meaning | Field(s) | PIT weight |
|-------|---------|----------|-----------|
| **Accepted by SEC** | EDGAR accepted the submission for processing. | `acceptance_timestamp` | Necessary, **not** sufficient. Does not by itself prove public retrievability. |
| **Deemed filed** | The legal filing date/effectiveness. | `filing_date` | Regulatory attribute. **Not** evidence of retrievability; date-only. |
| **Available through EDGAR** | The filing was actually disseminated / indexed and could be fetched. | dissemination/index evidence, retrieval timestamp | Direct evidence of availability, when we have it. |
| **Available to a hypothetical researcher** | The conservative time by which a diligent researcher *could* have obtained the information. This is what PIT eligibility requires. | `derived_public_availability_timestamp` + `availability_status` | The boundary. Derived by policy from the three above; `unknown` if not defensible. |

The gap between "accepted" and "available to a researcher" is real (post-cutoff
and weekend/holiday dissemination, special processing for some form types, and
historical filings with no dissemination evidence at all). Collapsing it is the
classic look-ahead bug this project exists to prevent.

### 2.2 Why filing date and acceptance are not enough

- **Filing date (#3) is a date, not an instant, and is a legal attribute.**
  Never the eligibility boundary — it can precede actual retrievability and has
  no intraday resolution.
- **Acceptance (#4) is "accepted," not "available."** General EDGAR behavior is
  that submissions accepted after a daily cutoff, or on weekends/holidays, are
  disseminated later — but this is **not a single universal 5:30 PM rule**:
  dissemination behavior has varied over time and **differs by filing type**
  (some forms have special processing / delayed or immediate dissemination).
  Treating acceptance as availability leaks look-ahead.
- **Retrieval timestamp (#6) is an upper bound, not the answer.** That we
  fetched bytes at time *R* proves they were public *by R*; it says nothing
  about how much earlier they became public. Never set availability = retrieval.

**Public availability (#7) is therefore policy-derived, conservative, and
statused.** It is produced by a versioned `AvailabilityPolicy` (§4, §PA), rounds
**later, never earlier** on uncertainty, and is marked `unknown` — and thus
**PIT-ineligible** — whenever no defensible estimate exists. See the dedicated
§PA "Public Availability Semantics."

> ⚠️ **Assumptions to validate against real SEC data** (§15): the actual
> dissemination cutoffs and how they vary **by form type and era**, and the
> holiday/business calendar. This remains the highest-risk area of the model.
> *Resolved by reconnaissance* (see docs/sec-reconnaissance.md): the
> timezone/format of `acceptanceDateTime` (**UTC, ms precision, uniform across
> issuers**) and the shape of dissemination/index evidence (the EDGAR **daily
> index** is an explicit "dissemination feed" but at **date granularity**; the
> Archives `Last-Modified` header trails acceptance by ~2–7 min but is a server
> mtime, not a guaranteed public-visibility time).

---

## §PA. Public Availability Semantics

This section is the conceptual heart of the point-in-time guarantee. It exists
because the single most dangerous simplification in a PIT system is treating any
one SEC-supplied timestamp as "when the public could know."

### PA.1 Four states, again — and why they differ

Repeating §2.1 because it is the load-bearing distinction:

1. **Accepted by SEC** (`acceptance_timestamp`). EDGAR received and accepted the
   submission for processing. This is an *internal* event. It does **not** mean
   the document was simultaneously pushed to the public dissemination feed or
   the indexes a researcher reads.
2. **Deemed filed** (`filing_date`). A legal/regulatory determination of the
   filing's effective date. Date-only, no intraday resolution, and driven by
   rules that have nothing to do with when bytes hit a public server.
3. **Available through EDGAR** (dissemination/index evidence). The document
   actually appears in a public index / dissemination feed and can be fetched.
   This is the first state that is *evidence of public retrievability* — but SEC
   does not always expose a clean per-filing dissemination timestamp,
   especially for older filings.
4. **Available to a hypothetical researcher**
   (`derived_public_availability_timestamp` + `availability_status`). The
   conservative time by which a diligent outside researcher *could* have
   obtained the information. **This is the only state PIT eligibility is allowed
   to use.** It is derived, never read raw, and may be `unknown`.

General EDGAR behavior links these (post-cutoff/weekend acceptances disseminate
later), but the links are **not identities**, they **vary by form type and
era**, and there is **no universal 5:30 PM rule**. Any equation among these
states must be justified by a policy, not assumed.

### PA.2 The AvailabilityPolicy

Availability is produced by a pure function:

```
derive(evidence, policy) -> (derived_public_availability_timestamp, availability_status)
```

- **evidence** = `{ acceptance_timestamp, filing_date, dissemination/index
  evidence, RawDocument.retrieved_at }` for the filing.
- **policy** = one `AvailabilityPolicy` version (§9), selected by matching the
  filing's `form_type` against `form_scope` and its acceptance date against
  `[effective_from, effective_to)`. Exactly one active policy version must match
  a given (form, date); overlapping active scopes are a configuration error.
- The function is deterministic (invariant 13): no wall-clock, no RNG, no
  input-order dependence.

Policies are **form-scoped and era-bounded**, so different filing types (and the
same type across regulatory eras) can carry different rules without a universal
constant. A policy's `rule_definition` is declarative data (cutoff, business
calendar, evidence precedence, fail-closed condition), so it is auditable and
versioned.

### PA.3 Status and the fail-closed rule

`availability_status` is the safety valve:

| Status | Meaning | PIT-eligible? |
|--------|---------|:---:|
| `verified` | Backed by **direct** dissemination/index evidence of public availability. | ✅ |
| `derived` | Computed from acceptance + a validated policy rule (cutoff/calendar), without direct dissemination evidence. Conservative. | ✅ |
| `unknown` | The policy cannot defend *any* sufficiently reliable timestamp (missing acceptance, pre-XBRL filing with no index evidence, out-of-scope form, unvalidated era). | ❌ **Never** |

**Fail-closed is the core rule:** if QuantForge cannot establish a
sufficiently reliable availability, the fact is `unknown` and is **excluded from
all normal PIT research** — it does not silently fall back to acceptance,
filing date, or retrieval time. A too-early availability is a correctness bug
(look-ahead); withholding a fact is merely conservative. We always choose
conservative. When a policy *can* defend a timestamp but is uncertain about the
exact instant, it rounds **later, never earlier**.

Corollary: `retrieved_at` is used only as an **upper bound** (invariant 11) —
proof the data was public *by* our fetch — never as the availability itself.

### PA.4 Relationship to the core promise

> Never use information that was not demonstrably available by the research
> timestamp.

"Demonstrably" is why `unknown` cannot be eligible: absent a defensible basis,
we cannot *demonstrate* availability, so we must not use it. This section, the
§6.1 status gate, and invariants 8–14 are three views of that one promise.

### PA.5 Must be validated before production

Every `AvailabilityPolicy` ships `confidence: unvalidated` and (typically)
`status: provisional` until its rules — cutoffs, calendar, form scope, evidence
precedence — are checked against **real SEC filings** (see §15.1–15.3). Until a
policy is validated, it should derive conservatively and mark borderline cases
`unknown`. This document does **not** authorize downloading SEC data; validation
is a later, explicit step.

---

## 3. Canonical fact model

The canonical fact is one **observation of one concept, for one fiscal period,
in one dimensional context, as asserted by one filing.**

We do **not** model `NormalizedFact` and `FinancialObservation` as two things.
They are the same thing under two names; splitting them would be pure
duplication. There is one canonical entity: **`Fact`**. (`RawFact`, the
pre-normalization observation, *is* distinct from it — see §4.)

### 3.1 What lives on the `Fact`

Only the **economic content of the observation** plus **foreign keys** to the
entities that own the other attributes:

| Field | Type | Notes |
|-------|------|-------|
| `fact_id` | id | Deterministic content hash (§11). |
| `company_id` | fk → Company | Denormalized from filing for query speed; must equal the filing's registrant. |
| `security_id` | fk → Security, nullable | Only for security-scoped concepts (e.g., shares of a specific class, per-share EPS by class). Entity-level facts (Revenue) leave this null. |
| `taxonomy` | enum | e.g. `us-gaap`, `dei`, `ifrs-full`, `srt`. |
| `concept` | string | The XBRL tag, e.g. `RevenueFromContractWithCustomerExcludingAssessedTax`. |
| `period_type` | enum | `instant` or `duration`. |
| `period_start` | date, nullable | Null for instant concepts. |
| `period_end` | date | Present for both (instant = the point). |
| `fiscal_year` | int | As asserted (`dei:DocumentFiscalYearFocus` / context). |
| `fiscal_quarter` | int, nullable | 1–4, or null for annual/other. |
| `value_numeric` | decimal, nullable | Null when `is_nil` or non-numeric. |
| `value_text` | string, nullable | For non-numeric concepts. |
| `is_nil` | bool | XBRL `nil="true"` — an explicit "reported as nothing," which is itself information (§13, case 14). |
| `unit` | string | Canonical unit token, e.g. `USD`, `USD/shares`, `shares`, `pure`. Backed by structured fields (below) so compound and custom units are represented losslessly, not just as an opaque string (recon §Unit). |
| `unit_numerator` | string | The numerator measure QName (e.g. `iso4217:USD`). For simple units this is the whole unit. |
| `unit_denominator` | string, nullable | The denominator measure QName for a `divide` unit (e.g. `xbrli:shares` in `USD/shares`); null for simple units. |
| `currency` | string, nullable | ISO 4217 when monetary. |
| `scale` | int | Power-of-ten applied to reach `value_numeric` in base units. Normalized so stored values are in base units (scale folded in); `scale` retained for audit. |
| `decimals` | int, nullable | XBRL `decimals` precision attribute (audit + rounding). |
| `dimensions_hash` | hash | Hash of the sorted `(axis, member)` set for the XBRL context. `""`/sentinel for the default (undimensioned) context. |
| `dimensions` | json | The explicit `(axis, member)` pairs (segments). Kept so segmented facts don't collide with the consolidated fact. |
| `filing_id` | fk → Filing | The submission that **asserted** this observation. Owns form type, filing date, acceptance, availability evidence, amendment status. |
| `raw_fact_id` | fk → RawFact | The exact pre-normalization observation this was derived from. |
| `transformation_version_id` | fk → TransformationVersion | The code+config that produced this fact. |
| `derived_public_availability_timestamp` | timestamptz, nullable | **Denormalized copy** of the filing's derived availability, UTC. Null when `availability_status = unknown`. Denormalized *only* so the PIT predicate is a single-column index scan; must always equal `Filing.derived_public_availability_timestamp`, pinned by invariant (§12). |
| `availability_status` | enum | `verified` \| `derived` \| `unknown`. Denormalized copy of `Filing.availability_status`. **Only `verified` and `derived` are PIT-eligible** (§6); `unknown` is excluded from normal PIT research (invariant, §12). |
| `availability_policy_id` | fk → AvailabilityPolicy, nullable | The `(policy_id, policy_version)` that produced the timestamp/status. Null only when `unknown` *and* no policy could be applied. Every non-`unknown` availability references exactly one policy version. |

### 3.2 What does *not* live on the `Fact` (and why)

| Requested field | Where it actually lives | Reason |
|-----------------|-------------------------|--------|
| `form_type`, `filing_date`, `acceptance_timestamp`, `amendment_status`, accession number | **Filing** | One filing asserts thousands of facts. Storing these per-fact is massive duplication and invites drift. |
| `source_url`, `source_hash`, `source_document`, `raw_record_identifier` | **RawDocument** / **RawFact** | Provenance of the *bytes*, not of the economic value. Many facts share one document. |
| `normalization_version` | **TransformationVersion** (referenced) | It's a shared code version, not a per-fact scalar. |
| `dataset_version` | **DatasetVersion** (contains facts) | A fact does not belong to exactly one dataset version; a dataset version is a *set of* facts (§9). Putting `dataset_version` on a fact would either duplicate facts per snapshot or falsely imply 1:1. |

**Principle:** a field belongs on `Fact` only if it varies *per observation*.
Everything shared across many facts belongs on the entity that owns it, reached
by FK. The deliberate exceptions are the three availability fields
(`derived_public_availability_timestamp`, `availability_status`,
`availability_policy_id`), denormalized purely for PIT query performance and
pinned equal to the owning `Filing` by invariant. The raw availability
*evidence* (acceptance, filing date, dissemination/index, retrieval) lives on
`Filing`/`RawDocument`, not on the fact (§5, §PA).

---

## 4. Entities and relationships

Distinct entities, and the justification for each being separate:

| Entity | Keep separate? | Why |
|--------|:---:|-----|
| **Source** | ✅ | The publisher (SEC EDGAR today). Small dimension, but modeling it lets us add other public sources later and attach source-level trust/rules. Cheap. |
| **Company** (registrant) | ✅ | Anchored by CIK. Owns mutable-over-time metadata (name, SIC, fiscal-year-end) via history rows, never mutation. |
| **Security** | ✅ | One company → many securities (share classes, debt). Tickers/exchanges live here and change over time; they are **not** identifiers. |
| **Filing** | ✅ | The SEC submission (one accession). Owns form type, `filing_date`, `acceptance_timestamp`, dissemination/index evidence, amendment linkage (**derived**, with confidence — §7; SEC exposes no explicit base-accession field, confirmed across all recon issuers), and the **derived** availability triple (`derived_public_availability_timestamp`, `availability_status`, `availability_policy_id`). Both the availability triple and the amendment linkage are *computed*, not read raw (§PA, §7). |
| **AvailabilityPolicy** | ✅ | Versioned, form-scoped rule that maps availability *evidence* → derived availability timestamp + status. First-class so different filing types and eras get different rules, and so results are auditable and reproducible. Referenced by every non-`unknown` availability. See §PA / §9. |
| **RawDocument** | ✅ | The immutable *bytes* actually fetched (the primary XBRL/HTML document, the companyfacts JSON, index pages, etc.). Content-addressed. Carries the **retrieval timestamp** (upper-bound availability witness). Multiple RawFacts extracted from one document. |
| **RawFact** | ✅ | The observation **exactly as parsed**, before normalization (raw unit strings, raw scale/decimals, raw context id, raw value string). Distinct from `Fact` because it lets us **re-normalize** under a new `TransformationVersion` without re-fetching, and lets us diff "what the source said" vs "what we canonicalized." |
| **Fact** (canonical) | ✅ | The normalized observation. Unifies the requested `NormalizedFact` + `FinancialObservation` (§3). |
| **TransformationVersion** | ✅ | Versioned parser+normalizer code/config. Referenced by RawFact (parser) and Fact (normalizer). Composes with `AvailabilityPolicy` (which is separately versioned) to define the full derivation. |
| **DatasetVersion** | ✅ | Immutable manifest naming the exact set of RawDocuments and Facts, the TransformationVersion, **and the AvailabilityPolicy set** that constitute a reproducible snapshot. |

Collapsed on purpose: **`NormalizedFact` ≡ `FinancialObservation` ≡ `Fact`.**

**Entities considered after reconnaissance and deliberately *not* added** (the
existing model already represents each cleanly — adding them would be theoretical
completeness, violating the "no unnecessary entities" rule):

| Proposed entity | Verdict | Why the existing model suffices |
|-----------------|:---:|---------------------------------|
| **Filer vs Company** | Not needed | Recon confirms one CIK is the stable filer *and* registrant across name/ticker/reincorporation changes; `Company` (CIK) already is the filer identity, and `Security` already separates instruments (JPMorgan's 9 tickers/1 CIK fit `Company 1─∞ Security`). A separate legal-entity vs filer split is only needed for multi-CIK succession, deferred to the §15.7 alias mapping. |
| **AmendmentRelationship** (entity) | Not needed | A 1:1 (amendment→base) link with a confidence is two fields on `Filing` (`amends_accession`, `amendment_link_confidence`, §7.1), not a first-class entity. No many-to-many was observed. |
| **RelationshipConfidence** (entity) | Not needed | Modeled as an enum field (§7.1), not a table. |
| **AvailabilityEvidence** | Already present | The evidence set (`acceptance_timestamp`, `filing_date`, dissemination/index evidence, `RawDocument.retrieved_at`) is already owned by `Filing`/`RawDocument` and feeds `derive()` (§PA, §5). Recon surfaced no evidence type the existing fields cannot hold. |
| **EntityHistory** | Already present | Effective-dated history rows on `Company`/`Security` (name, SIC, FY-end, ticker) already cover this; recon's `formerNames` maps directly onto them. |

### Relationship diagram

```
Source 1───∞ Filing 1───∞ RawDocument 1───∞ RawFact ≥1──1 Fact
   │            │                                            │
   │            │                                            ├─ fk → Company
   │         (registrant)                                    ├─ fk → Security (nullable)
   │            └──────────── fk ────────────────────────────┤
   └─ fk from Company                                        │
                                                             ├─ fk → RawFact (provenance)
Company 1───∞ Security                                       └─ fk → TransformationVersion

TransformationVersion ──(parser)──▶ RawFact
TransformationVersion ──(normalizer)──▶ Fact

DatasetVersion ──manifest──▶ { set of RawDocument ids, set of Fact ids, TransformationVersion id }
```

The `RawFact ─▶ Fact` edge is **1:1 in the normal case**, but its exact
cardinality is: *one or more* RawFacts (per `(filing, transformation version)`)
map to *at most one* Fact, because `fact_id` hashes
`(transformation_version_id, filing_id, obs_key)` and **not** `raw_fact_id`
(§11). Consequences:

- Normal case: one RawFact → one Fact.
- Duplicate case: two RawFacts in the same filing that reduce to the same
  obs_key and value collapse to one Fact (§13 case 8). The Fact's `raw_fact_id`
  records the canonical representative (lowest `ordinal`); the other RawFact is
  retained and still resolves to the same Fact by re-derivation.
- Re-normalizing the same RawFact under a new `TransformationVersion` produces a
  *new* Fact (new `fact_id`); the old Fact is retained. So across all time a
  RawFact contributes to at most one Fact per `TransformationVersion`.

---

## 5. Provenance model

The required chain, made concrete with the FK that carries each link:

```
Public SEC source            Source row (edgar)
        │                         ▲ fk
        ▼                         │
Raw document (bytes)         RawDocument { sha256, source_url, retrieved_at, filing_id }
        │  parsed by TransformationVersion.parser
        ▼
Raw observation              RawFact { raw_document_id, context_ref, raw_value, raw_unit, ... }
        │  normalized by TransformationVersion.normalizer
        ▼
Canonical financial fact     Fact { raw_fact_id, transformation_version_id, filing_id,
                                    derived_public_availability_timestamp,
                                    availability_status, availability_policy_id, ... }
        │  selected by PIT query at as_of (status ∈ {verified,derived}), under DatasetVersion
        ▼
Research result              ResearchResult { dataset_version_id, transformation_version_id,
                                              availability_policy_set, factor_version,
                                              strategy_version, as_of, params }
```

**Availability-evidence sub-chain** (feeds the derived availability, §PA):

```
Filing { filing_date, acceptance_timestamp, dissemination/index evidence }
   +  RawDocument { retrieved_at, sha256 }          (evidence, all immutable)
        │  evaluated by AvailabilityPolicy (policy_id, policy_version), scoped by form type/era
        ▼
Filing { derived_public_availability_timestamp, availability_status, availability_policy_id }
```

Every arrow is a stored FK, so provenance is a join, not a guess. Given any
`fact_id` you can recover: the exact bytes (`RawDocument.sha256`), the source
URL and retrieval time, the raw observation string, the parser+normalizer
version, the asserting filing and *all* its availability evidence
(acceptance, filing date, dissemination/index, retrieval), the exact
`AvailabilityPolicy` version that produced its availability and status, and
every dataset snapshot that contains it. **No canonical fact may exist without a
resolvable `raw_fact_id` and `transformation_version_id`; and no
non-`unknown` availability may exist without a resolvable
`availability_policy_id`** (invariants, §12).

---

## 6. Point-in-time semantics

### 6.1 The eligibility predicate (status-gated, then temporal)

```
eligible(fact, as_of)  ⇔
      fact.availability_status ∈ { verified, derived }          -- (A) fail-closed gate
  AND fact.derived_public_availability_timestamp IS NOT NULL     -- (B) known boundary exists
  AND fact.derived_public_availability_timestamp <= as_of        -- (C) not the future
```

- **(A) fails closed.** A fact with `availability_status = unknown` is **never**
  PIT-eligible, regardless of any timestamp on it. This is the direct
  enforcement of the core promise: we never use information we cannot
  *demonstrably* show was available by `as_of`. Facts with `unknown` status are
  visible only to explicit audit/lineage queries that opt out of PIT
  (`include_unknown_availability=true`), never to normal research.
- **(B)/(C)** are the temporal boundary. Because availability is derived
  conservatively (rounds *later* on uncertainty, §PA), `<=` cannot admit
  look-ahead.

This predicate correctly *excludes* the future and the unknowable. It still does
**not** answer the second question: among all eligible observations of the same
concept/period, **which value was known** at `as_of`? Amendments and
restatements mean there are many — resolved in §6.3.

### 6.2 Fact identity for supersession

Two observations describe "the same thing" iff they share the **observation
key**:

```
obs_key = ( company_id, security_id, taxonomy, concept,
            period_type, period_start, period_end,
            unit, dimensions_hash )
```

Note: `security_id` and `dimensions_hash` are in the key, so the consolidated
figure and a per-segment figure are **different** things and never supersede
each other (§13, case 8). `unit` is in the key so a `USD` fact and a
`USD/shares` fact never collide.

### 6.3 The point-in-time selection rule

To resolve one value per `obs_key` as of `T`:

1. **Filter** to eligible observations via the full §6.1 predicate (status gate
   **then** `derived_public_availability_timestamp <= T`). `unknown`-status
   observations are already excluded here.
2. **Rank** the survivors by *when they became known*, most-recent-first:
   1. `derived_public_availability_timestamp` descending (latest known wins → an
      amendment/restatement supersedes the original *once it is public*);
   2. then `acceptance_timestamp` descending (finer tiebreak within a
      dissemination batch);
   3. then amendment supersedes original: an `/A` form outranks its base form;
   4. then `accession_number` descending (fully deterministic final tiebreak).
3. **Select** the top-ranked observation as the known value.

The full ordering is a **total order** (step 4 guarantees no ties), so the
selected value is deterministic — required for reproducibility.

A query may return either the resolved single value (default), or, for
audit/lineage, the entire eligible history for an `obs_key`.

### 6.4 Timezone handling

- All stored timestamps are **UTC** (`timestamptz` semantics).
- `acceptance_timestamp` is supplied by EDGAR **already in UTC** (`…Z`,
  millisecond precision — confirmed across all 6 reconnaissance issuers), so it
  is stored as-is; **no ET→UTC conversion on ingest** (the earlier design
  assumed ET and was wrong — see recon). Any policy that reasons about a daily
  cutoff or business calendar converts the stored UTC instant **to ET** *inside
  the `AvailabilityPolicy`* (§PA),
  because such rules are defined in ET and the ET↔UTC offset shifts with
  daylight saving; the resulting `derived_public_availability_timestamp` is then
  stored in UTC. The cutoff/calendar is **policy-owned and form-scoped**, not a
  hard-coded universal constant (§PA).
- The `as_of` parameter must be timezone-aware; a naive `as_of` is rejected (an
  ambiguous boundary is a look-ahead risk). Comparisons are UTC-vs-UTC.

### 6.5 Boundary condition (`<=` vs `<`)

Eligibility uses `<=`: a fact available at exactly `as_of` is knowable. Because
availability is second-precision and rounded *later* on uncertainty, the `<=`
boundary cannot admit look-ahead. Same-instant ties across different `obs_key`s
are irrelevant; ties within one `obs_key` are broken deterministically by §6.3.

### 6.6 Where an `as_of` can fall relative to a filing

For a given filing, the `as_of` timestamp lands in exactly one of these regions.
The behavior is a strict consequence of §6.1 — listed explicitly because these
are the cases where look-ahead usually creeps in:

| `as_of` relative to the filing | Fact eligible? | Rationale |
|--------------------------------|:---:|-----------|
| **Before availability** (`as_of < derived_public_availability_timestamp`) | ❌ No | Not yet public. The filing's facts do not exist to this query. |
| **After acceptance but before derived/verified availability** (`acceptance <= as_of < derived_availability`) | ❌ **No** | "Accepted" ≠ "available." This is the critical gap; the fact is withheld until derived availability. |
| **After availability** (`as_of >= derived_public_availability_timestamp`, status ∈ {verified, derived}) | ✅ Yes | Demonstrably available by `as_of`. |
| **Availability `unknown`** (any `as_of`) | ❌ **No** | Fail-closed gate (§6.1-A). Never eligible for normal PIT research at any `as_of`. |
| **`as_of` on a weekend / federal holiday** | Depends only on the timestamp comparison | No special-casing of the *research* timestamp. A non-business `as_of` is a perfectly valid instant; it simply won't clear any filing whose *derived availability* is later. The business-calendar logic lives entirely in the `AvailabilityPolicy` that set `derived_public_availability_timestamp` — never in the query. |

Consequence: the query engine treats `as_of` as a pure instant and applies §6.1
mechanically. All calendar/cutoff subtlety is pushed into (versioned) policy at
derivation time, so it is auditable and cannot be silently re-interpreted at
query time.

---

## 7. Amendment and restatement semantics

**Rule: filings never overwrite. Every filing's facts are retained forever.
Amendment/restatement is expressed purely through the PIT selection rule
(§6.3), never by deletion or mutation.**

- **10-K / 10-Q** produce facts asserted by that filing.
- **10-K/A, 10-Q/A** produce a *new* set of facts asserted by the amendment,
  each with the amendment's own **derived** availability and status.
  `Filing.amends_accession` links the `/A` to its base — but this link is
  **derived by QuantForge, not asserted by SEC** (see §7.1), so it carries an
  explicit confidence. Overlapping `obs_key`s
  now have two eligible observations once the amendment's availability is
  *known and cleared* (§6.1); §6.3 then picks the amendment. If the amendment's
  availability is `unknown`, it is **not** eligible and does **not** supersede
  the base — the earlier value continues to win, conservatively.
  Note (recon): an `/A` is often a **partial** amendment carrying only a
  cover-page XBRL stub and no financial instance (e.g. Tesla's 10-K/A filings) —
  so an amendment may assert *few or no* financial facts while still being a
  legally significant filing. Supersession is per-`obs_key`: an `/A` only
  supersedes the specific observations it actually re-asserts.
- **Restatement years later** (e.g., in a later 10-K's comparative columns, or a
  dedicated amendment) is just another filing asserting facts for the old
  period, with a much later availability. Same mechanism, same status gate.

### The 2020 vs 2022 query, same fiscal period

Consider FY2019 revenue, originally in a 10-K available 2020-02-01, then
restated in a filing available 2021-06-01.

- **Query as_of 2020-01-01:** the original 10-K is *not yet available*
  (2020-02-01 > 2020-01-01). FY2019 revenue may be entirely unknown, or known
  only from an earlier estimate. **The later restatement does not exist to this
  query.**
- **Query as_of 2022-01-01:** both the original (2020-02-01) and the restatement
  (2021-06-01) are eligible. §6.3 ranks the restatement first (later
  availability) → the query returns the **restated** value.

Same fiscal period, different *information state* — exactly the property the
model must preserve. The original observation is never destroyed; it is simply
out-ranked once a newer public observation exists.

### 7.1 Amendment linkage is derived, with explicit confidence

Reconnaissance established (across Apple, JPMorgan, Meta, GE, Tesla, Kraft
Heinz) that **SEC exposes no explicit "this filing amends accession X" field** —
not in the submissions API, not in companyfacts, and **not even in the SGML
submission header** (which carries form, period-of-report, and file number, but
never a base accession). Therefore `amends_accession` **cannot be read; it must
be derived**, and the model records *how confidently* via
`amendment_link_confidence`:

| `amendment_link_confidence` | Basis | Recon observation |
|-----------------------------|-------|-------------------|
| `SOURCE_ASSERTED` | SEC (or the filing itself) states the base accession explicitly. **Not observed in structured metadata for periodic reports**; reserved in case some form/era provides it. | none in submissions / companyfacts / SGML header |
| `DERIVED_HIGH_CONFIDENCE` | Form is exactly `base + "/A"`, **same CIK**, **same `reportDate` (period of report)**, and exactly **one** candidate base filing matches, with consistent chronology (amendment accepted after base). | every recon 10-K/A & 10-Q/A resolved to exactly one base with matching `reportDate` (Tesla 5×, Kraft Heinz 2×) |
| `DERIVED_LOW_CONFIDENCE` | `/A` + same period but the base is **ambiguous** (several candidates, e.g. an amended period re-reported across multiple filings) or period/chronology matched only approximately. | amended period appearing in several later filings |
| `UNKNOWN` | No defensible base identifiable (missing `reportDate`, orphan `/A`, cross-entity succession). Represent the amendment as a standalone filing; do **not** guess a base. | — |

Key properties, all enforced structurally:

- **The link is never required for PIT correctness.** §6.3 supersession is driven
  by `obs_key` + availability ordering, which works **without** knowing the base
  filing. The `/A`-outranks-base tiebreak (§6.3 step 3) is only a *finest* tie
  discriminator; the primary signal is availability time. So an `UNKNOWN` linkage
  degrades nothing — the amendment still supersedes correctly by being
  later-available.
- **Confidence is stored data, produced by a versioned `TransformationVersion`**
  (the linkage inference is deterministic code), so it is auditable, re-derivable,
  and can be *promoted* if SEC ever exposes a stronger signal.
- **The model represents uncertainty rather than inventing a link** — consistent
  with Engineering Principle 1 (correctness over convenience) and the fail-closed
  posture used for availability.

---

## §KS. Historical Knowledge State vs Revised Historical Truth

The model must answer two **fundamentally different** questions about the same
past economic period, and must never let one masquerade as the other.

### KS.1 The two views

| View | Question it answers | Terminology | The `as_of` used |
|------|---------------------|-------------|------------------|
| **Point-in-time knowledge state (PIT view)** | *"What value would a researcher have known as of timestamp `T`?"* — "What was **knowable then**?" | `knowledge_state(T)` | A **historical** research timestamp `T`, supplied by the caller. |
| **Revised / current historical truth (revised view)** | *"What is the latest known/revised value now believed about this historical period?"* — "What is **believed/reported now** about the past?" | `revised_truth` (a.k.a. `latest_known`) | The **present** — effectively `as_of = now` (or, more precisely, `as_of = +∞` over all data currently ingested). |

The critical insight: **both views are the *same* §6.3 selection over the *same*
immutable fact set — they differ only in the `as_of` boundary.** No new entity,
no separate "latest" table, no mutation is required. The revised view is simply
the PIT view evaluated at the present instant.

- PIT view: filter to `derived_public_availability_timestamp <= T` (status-gated
  per §6.1), then rank by §6.3, take the winner.
- Revised view: **the same procedure with `T = now`.** Because it uses the same
  ranking (latest-available wins), it naturally returns the most recent
  restatement that is currently public.

This is why we never store a "current value" that gets overwritten: overwriting
would destroy the PIT view. Instead, *both* answers are derived on demand from
the append-only history.

> Note the asymmetry: a PIT query at a historical `T` must **never** be affected
> by observations that became available after `T`; a revised query at `now` is
> allowed to see everything currently available. Conflating them — e.g. serving
> `revised_truth` to a backtest that asked for `knowledge_state(T)` — silently
> injects look-ahead bias. §KS.4 forbids this structurally.

### KS.2 Query semantics

A resolution query takes an explicit **temporal mode**. There is no default that
can be mistaken for the other:

```
resolve(obs_key, mode) where mode is exactly one of:

  PIT(as_of = T)        -- T is a required, timezone-aware, historical instant.
                        -- Eligibility + ranking per §6.1 and §6.3 with boundary T.
                        -- Returns the value knowable at T, or "unknown/none" if
                        --   no eligible observation existed by T.

  REVISED(basis = now)  -- Equivalent to PIT(as_of = ingestion frontier).
                        -- Returns the latest currently-known value for the period.
                        -- MUST NOT be substituted for PIT in research/backtest paths.
```

Both modes:

- operate over the identical `obs_key` history (§6.2);
- obey the same fail-closed availability gate (`unknown` availability is never
  returned by either mode — §6.1, invariant 9);
- return, on request, the full eligible lineage (audit), not just the winner.

They differ **only** in the `as_of` boundary. A `REVISED` result therefore
always equals a `PIT(as_of = T)` result for `T >= ` the latest relevant
availability — which is exactly why the distinction must be explicit rather than
implicit.

**Reproducibility of `REVISED`.** "Now" is not a wall-clock read: `REVISED`
resolves against a specific `DatasetVersion` (§9), whose immutable manifest
*is* the ingestion frontier. So `REVISED` over a pinned `DatasetVersion` is
fully deterministic and reproducible (no violation of the no-wall-clock
guarantee, §12 invariant 21) — re-running it against the same snapshot yields
the same value. What "the latest truth" *means* simply advances as new snapshots
are created; each snapshot's answer is fixed. Recording `dataset_version_id` on
a `ResearchResult` (§9) therefore pins a `REVISED` answer exactly as it pins a
`PIT` one.

### KS.3 Worked example (the required one)

FY2019 revenue for one company, two filings:

| Event | Availability | Observation (same `obs_key`) |
|-------|--------------|------------------------------|
| Original 10-K reports FY2019 revenue | 2020-03-01 | `$100M` |
| Restatement reports FY2019 revenue | 2022-05-01 | `$80M` |

Resolutions (all over the *same* immutable two-fact history):

| Query | Mode | Result | Why |
|-------|------|--------|-----|
| "known as of 2021?" | `PIT(2021-01-01)` | **`$100M`** | Only the original is available by 2021; the restatement (2022-05-01) does not yet exist to this query. |
| "known as of 2023?" | `PIT(2023-01-01)` | **`$80M`** | Both available; §6.3 ranks the later-available restatement first. |
| "latest revised truth?" | `REVISED(now)` | **`$80M`** | Present-day resolution = the most recent public observation. |

The `PIT(2021)` answer (`$100M`) and the `REVISED` answer (`$80M`) coexist
permanently and are both correct — for their respective questions. A backtest
standing at 2021 that used `$80M` would be using information that did not exist
until 2022: look-ahead bias, and a correctness bug.

### KS.4 Integrity invariants (added to §12)

These are added to the §12 list (as invariants 27–30) and repeated here for
locality:

27. **Mode is explicit and required.** Every resolution query specifies exactly
    one of `PIT(as_of=T)` or `REVISED`. There is no implicit default; a query
    without a mode is rejected, not silently treated as either.
28. **`REVISED` is not a PIT source.** A `REVISED` result must never feed a
    research, factor, or backtest computation that is defined as-of a historical
    `T`. Such computations accept **only** `PIT`-sourced values. This is
    enforced at the API/type boundary (§KS.5), not by convention.
29. **PIT is `as_of`-monotonic and past-closed.** For `T1 <= T2`, the eligible
    set at `T1` is a subset of that at `T2` (observations only *become* known,
    never un-become). Equivalently, a `PIT(T)` result depends only on
    observations with availability `<= T` and is invariant to any observation
    ingested or made available after `T`. `REVISED` is the limit as `T → now`.
30. **Both views share one immutable history.** `REVISED` and `PIT` read the
    same append-only fact set; neither is a materialized/overwritten "current"
    copy. A revised value is *never* written back onto, or in place of, the
    observation it supersedes (this would destroy the PIT view — cf. invariants
    5, 22).

### KS.5 API guidance

When the query/API layer is eventually built (not now), the distinction must be
**structurally unavoidable**, not a flag that defaults dangerously:

- **No default mode.** The temporal mode is a required argument. A caller cannot
  accidentally get `REVISED` semantics by omitting `as_of`.
- **Distinct result types.** `PIT` and `REVISED` should return *different types*
  (e.g. `PitValue` vs `RevisedValue`) so that a function expecting a
  PIT-sourced input cannot be handed a revised value without an explicit,
  auditable conversion. This makes invariant 28 a compile-time / type-check
  concern rather than a runtime hope.
- **`as_of` is mandatory and typed as an aware instant** for `PIT`; a naive or
  missing `as_of` is an error (cf. invariant 15).
- **Provenance on every result.** Both modes return the winning observation's
  provenance (filing, availability timestamp, status, policy, dataset version)
  so callers can see *which* observation and *which* `as_of` produced the value.
- **Backtests/factors accept only `PIT`.** The factor/backtest entry points are
  typed to consume `PitValue` bound to the run's `as_of`; `REVISED` values are
  reserved for descriptive/current-state reporting and are inadmissible there.
- **Naming that can't be confused.** Prefer explicit names —
  `knowledge_state_as_of(T)` and `revised_truth()` / `latest_known()` — over an
  overloaded `get_value()` whose behavior depends on a nullable `as_of`.

---

## 8. Immutability rules

**Immutable once written (append-only, never updated or deleted):**

- Raw source **bytes** (content-addressed by sha256).
- **Source hashes** (sha256 of the bytes).
- **Accession numbers** and other SEC-assigned identifiers.
- **RawDocument** rows and **RawFact** rows.
- **Filing evidence**: `acceptance_timestamp`, `filing_date`, captured
  dissemination/index evidence, and `RawDocument.retrieved_at` — the raw inputs
  to availability derivation, never edited.
- **Derived availability** (`derived_public_availability_timestamp`,
  `availability_status`, `availability_policy_id`) *for a given
  `AvailabilityPolicy` version* — re-deriving under a new policy produces new
  Facts, it does not edit these.
- **Fact** rows.
- **AvailabilityPolicy** records (each `(policy_id, policy_version)` immutable).
- **DatasetVersion** manifests.
- **TransformationVersion** records.

**How corrections happen without mutation:**

| Correction type | Represented as |
|-----------------|----------------|
| SEC re-disseminated / a new filing corrects a value | New `RawDocument` → new `RawFact` → new `Fact`, superseded automatically by §6.3. Old rows untouched. |
| Our parser/normalizer had a bug | New `TransformationVersion` → re-run over the **same** RawDocuments → **new** Facts (new ids). Old Facts retained. New `DatasetVersion` points at the new Facts. Nothing is edited in place. |
| Our **availability policy** was wrong (bad cutoff, missing holiday, wrong form scope) | New `AvailabilityPolicy` version → re-derive availability → **new** Facts with corrected `derived_public_availability_timestamp`/`availability_status` and the new `availability_policy_id`. Old Facts retained; a new `DatasetVersion` references the new policy set. The old snapshot still reproduces exactly (reproducibly wrong, superseded at the manifest level, never mutated). |
| We later obtained better availability **evidence** (e.g., a dissemination index we lacked) | The new evidence is *appended* (new `RawDocument`/evidence rows). Re-deriving under a policy version yields **new** Facts, possibly promoting `unknown → derived/verified`. Prior `unknown` Facts are retained, not rewritten. |

Because raw bytes are content-addressed, a "correction" to raw data is a logical
impossibility: different bytes → different hash → different `RawDocument`. You
can only *add*.

---

## 9. Versioning model

### TransformationVersion

Identifies the deterministic code+config that turns raw into canonical:

```
TransformationVersion {
  transformation_version_id,   # = hash(code_git_sha, config_hash)
  code_git_sha,                # exact source revision of parser+normalizer
  config_hash,                 # unit maps, taxonomy maps (NOT the availability rule)
  created_at,                  # audit only, not an input to determinism
  notes
}
```

Same raw + same `TransformationVersion` ⇒ byte-identical Facts (Engineering
Principle 5). Both `RawFact` (parser) and `Fact` (normalizer) reference it. The
availability rule is deliberately **not** here — it is separately versioned as
`AvailabilityPolicy` so it can be corrected, and scoped per form type/era,
without churning the parse/normalize version.

### AvailabilityPolicy

The versioned rule that derives availability from evidence (full definition in
§PA):

```
AvailabilityPolicy {
  policy_id,                   # logical family, e.g. "edgar-std", "edgar-form-8k"
  policy_version,              # monotonically increasing within a policy_id
  availability_policy_id,      # = hash(policy_id, policy_version, rule_definition_hash)
  effective_from,              # first filing acceptance date this version governs
  effective_to,                # nullable; last date governed (null = open-ended)
  form_scope: [ "10-K", "10-K/A", ... ],   # or a wildcard/default
  rule_definition,             # declarative: cutoff, business calendar, evidence precedence,
                               #   and the fail-closed condition → status
  status,                      # "active" | "provisional" | "deprecated"
  confidence,                  # "verified-against-sec" | "heuristic" | "unvalidated"
  created_at, notes
}
```

`rule_definition` is data, and `derive(evidence, policy)` is a pure
deterministic function — same evidence + same policy version ⇒ same
`(timestamp, status)`. Changing the rule means a **new** `policy_version`, never
an edit (invariant, §12).

### DatasetVersion

An immutable, content-addressed **manifest** — the reproducible snapshot:

```
DatasetVersion {
  dataset_version_id,          # = Merkle root over the sorted member id lists + tv id + policy set
  transformation_version_id,
  availability_policy_ids: [ availability_policy_id, ... ],  # sorted; every policy version used
  raw_document_ids: [ sha256, ... ],   # sorted
  fact_ids:         [ fact_id, ... ],  # sorted
  parent_dataset_version_id,   # nullable; lineage of snapshots
  created_at, notes
}
```

Because the id is a hash of its contents (including the availability-policy
set), two snapshots with identical contents have identical ids, and any change
(one more filing, a re-normalization, a re-derived availability) produces a new
id. It is impossible to mutate a snapshot without changing its identity.

### Reproducing a research result

A `ResearchResult` records everything needed to reproduce itself:

```
ResearchResult {
  dataset_version_id,          # which data snapshot
  transformation_version_id,   # which parse/normalize code (also implied by the snapshot)
  availability_policy_ids,     # which availability rule versions (also implied by the snapshot)
  factor_definition_id + factor_version,   # which factor code/params (git sha + config)
  strategy_version,            # git sha of strategy code (when backtesting exists)
  as_of_timestamp,             # the PIT boundary
  query_params,                # universe, concepts, dates
  result_hash                  # hash of the output, for verification
}
```

Re-running with the same pins (dataset, transformation, **availability
policy**, factor, strategy, as_of + params) must reproduce `result_hash`. This
closes the loop from raw bytes to research output — and makes the availability
rule an explicit, cited input to every result, not a hidden assumption.

---

## 10. Storage architecture

Recommendation, deliberately un-fancy, single-developer-first:

| Layer | Store | Format |
|-------|-------|--------|
| Raw bytes | Object-style store: local filesystem now, S3-compatible later. Content-addressed path `raw/<sha256[0:2]>/<sha256>`. | Original bytes (gzip transparently). |
| RawFact | Columnar files, partitioned by `company_id` (and period). | **Parquet**. |
| Fact | Columnar files, partitioned by `company_id`, clustered by `derived_public_availability_timestamp`; `availability_status` is a filter column pushed down before the temporal scan. | **Parquet**. |
| Metadata: Source, Company, Security, Filing, AvailabilityPolicy, TransformationVersion, DatasetVersion | Small relational tables. | **DuckDB** native tables (single `.duckdb` file). |
| Query engine | **DuckDB**, reading Parquet + native tables in one SQL context. | — |

Why this shape:

- **DuckDB** is an embedded, zero-server analytical engine — ideal for one
  developer, and it queries Parquet directly, so facts don't have to be loaded
  into a database to be queried.
- **Parquet** for the two high-cardinality append-only tables gives columnar
  scans, cheap partition pruning on `company_id` and time, and portability (any
  engine can read it later — a natural fit for an open dataset).
- **Object-addressed raw store** makes immutability physical: the filename *is*
  the hash.
- **No server, no ORM, no migrations** to start. Relational metadata lives in
  DuckDB tables; if the project outgrows a single node, the same Parquet files
  drop into Spark/DuckDB-cluster/warehouse without reshaping.

Not adopted now (avoid overengineering): Postgres, a lakehouse table format
(Iceberg/Delta), a message bus, or a bitemporal RDBMS. The append-only +
content-addressed + manifest design already gives the bitemporality we need
without that machinery. Revisit table formats only when concurrent multi-writer
ingestion becomes real.

---

## 11. Identifier strategy

Guiding rule: **an identifier must never depend on a mutable value** (ticker,
company name, reported figure, file path). Prefer SEC-assigned stable ids and
content hashes.

| Entity | Identifier | Construction | Why stable |
|--------|-----------|--------------|-----------|
| Company | `company_id` | `cik:` + zero-padded 10-digit CIK, e.g. `cik:0000320193`. **Canonicalize on ingest**: the submissions API returns CIK as a zero-padded *string* (`"0000320193"`) but companyfacts returns it as an *int* (`320193`) — confirmed for all 6 recon issuers; both must map to one `company_id`. | CIK is SEC-assigned and permanent. Recon confirms it survives name changes (Facebook→Meta, Tesla Motors→Tesla, Chemical Banking→…→JPMorgan), ticker changes, and reincorporation (Tesla DE→TX). Name/SIC/ticker change; CIK does not. |
| Security | `security_id` | Prefer `figi:<FIGI>` when available; else `cik:<CIK>#class:<normalized-class>`. | FIGI is stable; ticker/exchange are **not** used. **Recon caveat:** neither FIGI/CUSIP is present in EDGAR's submissions or companyfacts APIs, so `security_id` for the FIGI form needs an **external** mapping source (out-of-EDGAR). Company≠Security is empirically real: JPMorgan lists **9 tickers under one CIK** (common + 8 preferred series). |
| Filing | `filing_id` | The accession number, `accession:0000320193-23-000106`. | SEC-assigned, globally unique, immutable. |
| RawDocument | `raw_document_id` | `sha256:<hex>` of the exact bytes. | Content-addressed: identity = content. |
| RawFact | `raw_fact_id` | `sha256` of `(raw_document_id, xbrl_context_ref, concept, unit_ref, segment_key, ordinal)`. | Deterministic from raw content; re-parsing reproduces it. |
| Fact | `fact_id` | `sha256` of `(transformation_version_id, filing_id, canonical obs_key)`. | Deterministic; one canonical fact per (obs_key, filing, transformation version). Includes the transformation version, so re-normalization yields a *new distinct* id while old remains. `raw_fact_id` is a provenance FK, **not** part of identity — see §13 case 8. |
| AvailabilityPolicy | `availability_policy_id` | `sha256(policy_id, policy_version, rule_definition_hash)`. | Pins the exact availability rule; a changed rule is a new id, never an edit. |
| TransformationVersion | `transformation_version_id` | `sha256(code_git_sha, config_hash)`. | Pins exact code+config. |
| DatasetVersion | `dataset_version_id` | Merkle root over sorted `raw_document_ids` + `fact_ids` + `transformation_version_id` + sorted `availability_policy_ids`. | Content = identity; tamper-evident. |

All ids are deterministic and reproducible: re-ingesting the same bytes and
re-running the same transformation regenerates the same ids across machines.

---

## 12. Integrity invariants

The implementation must enforce these. Violations are correctness bugs, not
warnings.

**Immutability & provenance**
1. Raw bytes are immutable; a `RawDocument` is written once and never modified.
2. `sha256(RawDocument.bytes) == RawDocument.raw_document_id` — verified on
   read, not just write.
3. Every `Fact` has a resolvable `raw_fact_id` **and**
   `transformation_version_id`. No provenance-less fact may exist.
4. Every `RawFact` resolves to an existing `RawDocument`; every `RawDocument` to
   an existing `Filing` and `Source`.
5. RawFact and Fact rows are append-only: never updated, never deleted.

**Point-in-time & availability**
6. No query may return a `Fact` with
   `derived_public_availability_timestamp > as_of`.
7. `Fact.derived_public_availability_timestamp ==
   Filing.derived_public_availability_timestamp` and
   `Fact.availability_status == Filing.availability_status` and
   `Fact.availability_policy_id == Filing.availability_policy_id` for the fact's
   filing (the denormalized copies can never drift).
8. **Acceptance does not imply availability.** `acceptance_timestamp` alone
   never makes a fact PIT-eligible; eligibility requires a non-`unknown`
   `availability_status` and a derived timestamp. (Direct enforcement of the
   §PA distinction.)
9. **`unknown` availability is never PIT-eligible.** A `Fact` with
   `availability_status = unknown` is excluded from all normal PIT queries; it
   is reachable only via an explicit `include_unknown_availability` audit query
   that is not a research/backtest path. Fail-closed.
10. When present, `derived_public_availability_timestamp >=
    acceptance_timestamp` — derived availability never precedes acceptance.
    (Note: no ordering is assumed between `acceptance_timestamp` and
    `filing_date`; a post-cutoff acceptance can be *deemed filed* the next
    business day, so acceptance may precede the filing date. `filing_date` is
    therefore never used as a lower bound on availability.)
11. **Retrieval timestamp is only an upper bound.** `derived_public_availability
    _timestamp <= RawDocument.retrieved_at` must hold — we cannot claim a filing
    became available *after* we already fetched it. If a conservative policy
    ever derives a time later than the earliest `retrieved_at`, the derivation
    is **capped at `retrieved_at`** (hard evidence wins over estimate).
    Retrieval is nonetheless **never** used as the availability itself:
    realistically `retrieved_at` is far later than true availability (e.g., a
    2026 backfill of a 2019 filing), so it is an upper bound, not the answer.
12. **Every non-`unknown` availability references a policy version.** A `Fact`
    with `availability_status ∈ {verified, derived}` has a resolvable
    `availability_policy_id`; `unknown` facts may have a null policy id.
13. **Availability derivation is deterministic.** `derive(evidence, policy)`
    uses no wall-clock, no RNG, no input-order dependence; same evidence + same
    `availability_policy_id` ⇒ identical `(timestamp, status)`.
14. **Changing the availability rule creates a new version, never a mutation.**
    A corrected rule is a new `AvailabilityPolicy` version producing new Facts
    under a new `DatasetVersion`; historical Facts and snapshots are untouched
    (mirrors invariant 22 for filings and invariant 20 for
    `TransformationVersion`).
15. Every stored timestamp is timezone-aware UTC; `as_of` must be
    timezone-aware or the query is rejected.
16. The PIT selection ordering (§6.3) is a total order — deterministic winner
    for every `obs_key`.
17. A single filing's facts share one availability triple — a filing is
    disseminated as a unit, so all its facts get the same
    `(timestamp, status, policy_id)`.

**Determinism & versioning**
18. Given identical raw inputs and the same `TransformationVersion`, generated
    `RawFact`/`Fact` rows and their ids are byte-identical.
19. `DatasetVersion` is immutable; its id equals the hash of its contents
    (including the availability-policy set).
20. A `TransformationVersion` and an `AvailabilityPolicy` version are each
    immutable once created.
21. Normalization uses no wall-clock time, no RNG, and no dependence on input
    ordering.

**Amendments / history**
22. A new filing (amendment/restatement) never mutates or deletes prior Facts;
    supersession is expressed only through §6.3. An amendment with `unknown`
    availability does **not** supersede an eligible base fact.
22a. **Amendment linkage is derived and never required for correctness.**
    `amends_accession` is produced by a versioned `TransformationVersion` and
    carries an `amendment_link_confidence ∈ {SOURCE_ASSERTED,
    DERIVED_HIGH_CONFIDENCE, DERIVED_LOW_CONFIDENCE, UNKNOWN}` (§7.1). PIT
    supersession (§6.3) must remain correct when the confidence is `UNKNOWN`
    (i.e., it relies on `obs_key` + availability ordering, not on the link). An
    unproven link is never fabricated.
23. Distinct `obs_key`s (differing security, dimensions, unit, or period) never
    supersede one another.

**Additional critical invariants**
24. `company_id` on a `Fact` equals the registrant of its `filing_id`.
25. A `Fact` with `is_nil = true` has `value_numeric` null and is a first-class
    observation that can supersede or be superseded (an explicit "reported
    nothing" is information).
26. Unit/scale normalization is loss-preserving: original `raw_unit`,
    `raw_scale`, `raw_decimals` are retained on the `RawFact` so any
    normalization can be re-derived and audited.

**Knowledge-state vs revised-truth** (defined in §KS)
27. **Mode is explicit and required.** Every resolution query specifies exactly
    one of `PIT(as_of=T)` or `REVISED`; a query without a mode is rejected,
    never defaulted.
28. **`REVISED` is not a PIT source.** A `REVISED` result must never feed a
    research/factor/backtest computation defined as-of a historical `T`; those
    accept only `PIT`-sourced values (enforced at the API/type boundary, §KS.5).
29. **PIT is `as_of`-monotonic and past-closed.** A `PIT(T)` result depends only
    on observations with availability `<= T` and is invariant to anything
    ingested or made available after `T`; for `T1 <= T2` the eligible set at
    `T1` is a subset of that at `T2`. `REVISED` is the limit as `T → now`.
30. **Both views share one immutable history.** `REVISED` and `PIT` read the
    same append-only fact set; neither is a materialized/overwritten "current"
    copy, and a revised value is never written back over the observation it
    supersedes (cf. invariants 5, 22).

**Signal-diagnostics invariants** (Phase 16; additive — these do not weaken 1–30)
SD-1. **Corpus pinning for a diagnostic.** A signal-diagnostics run records and,
    on re-run, re-verifies **both** the fundamentals `dataset_version_id` and the
    market `market_dataset_version_id`; a mismatch fails closed, and a changed
    corpus yields a different `diagnostics_id`. (The BT-1 analog for a
    read-both-corpora diagnostic over an append-only store.)
SD-2. **A forward-looking diagnostic is not a PIT value.** A `SignalDiagnostics`
    incorporates realized *forward* (post-`T`) returns and can never be
    substituted where a PIT as-of-`T` value/signal is required; it is not a
    `Pit*` type and exposes no as-of accessor. `boundary_kind = "pit"` documents
    that the *signal* was PIT-eligible, not that the diagnostic is a PIT value.
    (The direct analog of invariant 28.)
SD-3. **Signal PIT-eligibility.** The signal at each evaluation date `T` is read
    PIT-eligible-at-`T` (via `panel_across(..., as_of=T)`, invariant 29); no
    post-`T` data ever contaminates the signal side.
SD-4. **Fail-closed pairing.** A member lacking a PIT signal at `T` or a
    computable forward return is excluded from that date's pair set and recorded
    in coverage; it is never imputed, zero-filled, or fabricated (cf. invariants
    9, 12).

**Cross-sectional-regression invariants** (Phase 18; additive — these do not weaken 1–30)
XS-1. **Corpus pinning for a regression.** A cross-sectional-regression run
    records and, on re-run, re-verifies **both** the fundamentals
    `dataset_version_id` and the market `market_dataset_version_id`; a mismatch —
    or a corpus that does not admit a single normalizing transformation version —
    fails closed, and a changed corpus yields a different `crosssection_id`. (The
    SD-1 analog for a read-both-corpora regression over an append-only store.)
XS-2. **A forward-looking regression is not a PIT value.** A
    `CrossSectionalRegression` regresses realized *forward* (post-`T`) returns on
    as-of-`T` signals and can never be substituted where a PIT as-of-`T`
    value/signal is required; it is not a `Pit*` type and exposes no as-of
    accessor. `boundary_kind = "pit"` documents that the *signal side* was
    PIT-eligible, not that the regression is a PIT value. (The direct analog of
    invariant 28 / SD-2.)
XS-3. **Signal PIT-eligibility.** Each factor's signal at every evaluation date
    `T` is read PIT-eligible-at-`T` (via `panel_across(..., as_of=T)`, invariant
    29); no post-`T` data ever contaminates any signal column.
XS-4. **Fail-closed pairing.** A member lacking **any** of the `K` PIT signals at
    `T` or a computable forward return is excluded from that date's cross-section
    and recorded in coverage; it is never imputed, zero-filled, or fabricated. A
    per-date design below the degrees-of-freedom floor
    (`n_members < K + include_intercept + 1`) or singular is a recorded
    `UNDEFINED` date, never raised and never silently dropped (cf. invariants 9,
    12; SD-4).

---

## 13. Adversarial cases

For each case: how the model behaves.

1. **2023 10-K reports FY2023 revenue.** One Filing (accession), one
   RawDocument, RawFacts per XBRL context, one Fact per obs_key. Availability is
   derived by the `AvailabilityPolicy` scoped to `10-K` for that era from the
   filing's evidence; if that policy yields a defensible timestamp, status is
   `verified`/`derived`, else `unknown` (and the facts are PIT-ineligible until
   better evidence or a policy revision arrives). Straightforward.

2. **A 10-K/A is filed later.** New Filing with `amends_accession` → base, new
   RawDocument/RawFacts/Facts. After the /A is public, overlapping obs_keys have
   two eligible observations; §6.3 selects the /A (later availability, and /A
   outranks base on tie). Original facts retained.

3. **A later filing changes a previously reported value.** Same as #2 even if
   the later filing is a regular 10-K/10-Q carrying a corrected prior-period
   figure — it's just another observation for that obs_key with later
   availability. Supersession is automatic and reversible by `as_of`.

4. **A restatement years later.** Identical mechanism; the availability gap is
   large. A query before the restatement's availability never sees it (§7
   worked example).

5. **Two filings on the same calendar day.** `filing_date` is a date and is
   *never* the boundary. Ordering uses `acceptance_timestamp` (second
   precision), then accession — deterministic. If both truly share an instant,
   accession-number tiebreak still yields one winner.

6. **A filing submitted after market close.** The **form-scoped**
   `AvailabilityPolicy` for that era decides. For forms whose policy encodes a
   daily-cutoff + next-business-day rule, an acceptance after the cutoff derives
   an availability on the next business day, so a query at 18:00 ET the same day
   does **not** see it. For a form whose policy specifies immediate
   dissemination, availability may be the acceptance instant. **There is no
   single universal 5:30 PM rule** — the behavior is whatever the applicable
   policy version says, and if no policy defensibly covers the case, status is
   `unknown` and the facts are excluded. This is the case the availability
   *policy* (not a hardcoded constant) exists for.

7. **Fiscal period ≠ calendar year.** `period_start`/`period_end`/`period_type`
   come from the XBRL context, not the calendar. `fiscal_year`/`fiscal_quarter`
   are the company's asserted focus. No calendar assumption anywhere.

8. **Multiple XBRL facts for the same economic concept.** If they differ by
   dimension (segment) or unit, their `obs_key`s differ → both kept, no
   collision. If two facts share an obs_key within one filing (genuine
   duplicate), they dedupe to one `Fact` (same `fact_id`); a contradiction
   (same obs_key, different value, same filing) is flagged as a data-quality
   error, not silently merged.

9. **Different units/scales.** Normalized to canonical base units;
   `value_numeric` is in base units with `scale` folded in. `unit` is part of
   the obs_key, so `USD` and `USD/shares` never merge. Raw unit/scale retained
   on RawFact (invariant 26).

10. **Company changes reporting structure.** New concepts/dimensions simply
    produce new obs_keys. Old facts remain valid observations for their periods.
    No migration; history is additive.

11. **A filing contains facts for prior periods** (comparatives). Those
    prior-period facts get **this filing's** availability triple (timestamp,
    status, policy), not the original period's. So a FY2022 figure appearing in
    the FY2023 10-K is a *distinct, later-available* observation of FY2022 — the
    raw material for detecting restatements. At an `as_of` just after FY2022's
    original filing, the original observation still wins; only after the FY2023
    filing's availability is *known and cleared* does the comparative compete.

12. **Company changes ticker.** Ticker lives on Security with effective-dated
    history; it is never an identifier. `company_id` (CIK) is unchanged. No fact
    is affected.

13. **Company changes CIK-related metadata** (name, SIC, FY-end). Stored as
    effective-dated history rows on Company; CIK/`company_id` unchanged. (True
    CIK reassignment/merger is rare and handled by an explicit alias/merger
    mapping, recorded as data, never by mutating facts — flagged as an open
    question, §15.)

14. **A value is missing or nil.** `nil="true"` → a Fact with `is_nil=true`,
    `value_numeric=null` (invariant 25) — an explicit observation that can
    supersede a prior non-null value. A concept simply *absent* from a filing
    produces **no** Fact (absence ≠ nil): we assert nothing rather than
    inventing a value.

15. **A fact appears in multiple filings.** Each filing yields its own
    RawDocument/RawFact/Fact with that filing's availability. They share an
    obs_key, so §6.3 orders them by knowledge time. Identical value across
    filings is harmless (the query just returns the latest-known); differing
    values are exactly the restatement/amendment case (#3, #4).

---

## 14. Example records

Illustrative only — not a schema, not real data. Shows the linkage and the PIT
behavior.

```jsonc
// Source
{ "source_id": "edgar", "name": "SEC EDGAR", "base_url": "https://www.sec.gov" }

// Company
{ "company_id": "cik:0000320193", "cik": 320193,
  "name_history": [ { "name": "APPLE INC", "effective_from": "2007-01-09" } ],
  "fiscal_year_end": "09-30" }

// AvailabilityPolicy (the versioned rule that derived availability below)
{ "availability_policy_id": "sha256:policyA…",
  "policy_id": "edgar-std", "policy_version": 3,
  "effective_from": "2015-01-01", "effective_to": null,
  "form_scope": ["10-K", "10-K/A", "10-Q", "10-Q/A"],
  "rule_definition": { "cutoff_et": "17:30", "post_cutoff": "next_business_day_open",
                       "business_calendar": "sec-federal-holidays",
                       "evidence_precedence": ["dissemination_index", "acceptance+cutoff"],
                       "fail_closed_if": "no acceptance AND no dissemination evidence" },
  "status": "provisional", "confidence": "unvalidated" }   // NOT yet checked vs real SEC data

// Filing (original 10-K, accepted after the ET cutoff on a Friday)
{ "filing_id": "accession:0000320193-19-000119", "source_id": "edgar",
  "company_id": "cik:0000320193", "form_type": "10-K",
  "filing_date": "2019-10-30",                              // "deemed filed" (date only)
  "acceptance_timestamp":                    "2019-10-30T22:12:33Z", // "accepted"; UTC (was 18:12 ET)
  "dissemination_evidence":                  null,          // none captured for this filing
  "derived_public_availability_timestamp":   "2019-10-31T13:30:00Z", // derived by edgar-std/v3
  "availability_status":                     "derived",     // not "verified": no direct index evidence
  "availability_policy_id":                  "sha256:policyA…",
  "amends_accession": null }

// RawDocument (the immutable bytes)
{ "raw_document_id": "sha256:9f2c…", "filing_id": "accession:0000320193-19-000119",
  "source_url": "https://www.sec.gov/Archives/edgar/data/320193/…/aapl-20190928.htm",
  "retrieved_at": "2026-08-05T10:00:00Z" }   // upper bound on availability, NOT the availability itself

// RawFact (exactly as parsed, pre-normalization)
{ "raw_fact_id": "sha256:1a7b…", "raw_document_id": "sha256:9f2c…",
  "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
  "context_ref": "FY2019", "raw_value": "260174", "raw_unit": "USD",
  "raw_scale": "6", "raw_decimals": "-6" }

// Fact (canonical, normalized to base USD)
{ "fact_id": "sha256:c4e0…", "company_id": "cik:0000320193",
  "security_id": null, "taxonomy": "us-gaap",
  "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
  "period_type": "duration", "period_start": "2018-09-30", "period_end": "2019-09-28",
  "fiscal_year": 2019, "fiscal_quarter": null,
  "value_numeric": 260174000000, "value_text": null, "is_nil": false,
  "unit": "USD", "currency": "USD", "scale": 6, "decimals": -6,
  "dimensions_hash": "", "dimensions": [],
  "filing_id": "accession:0000320193-19-000119",
  "raw_fact_id": "sha256:1a7b…",
  "transformation_version_id": "sha256:7d31…",
  "derived_public_availability_timestamp": "2019-10-31T13:30:00Z",  // copied from Filing
  "availability_status": "derived",
  "availability_policy_id": "sha256:policyA…" }

// A later restatement of the SAME obs_key (different filing, later availability)
{ "fact_id": "sha256:e880…", /* … same obs_key … */
  "value_numeric": 259900000000,
  "filing_id": "accession:0000320193-21-000056",
  "derived_public_availability_timestamp": "2021-06-01T13:30:00Z",
  "availability_status": "derived",
  "availability_policy_id": "sha256:policyA…" }

// An observation we CANNOT date reliably → excluded from PIT (fail-closed)
{ "fact_id": "sha256:f0f0…", /* … some obs_key … */
  "value_numeric": 12345000,
  "filing_id": "accession:0000000000-98-000001",   // pre-XBRL-era, no acceptance/index evidence
  "derived_public_availability_timestamp": null,
  "availability_status": "unknown",
  "availability_policy_id": null }
//   PIT queries never return sha256:f0f0 at ANY as_of (invariant 9).
//   Only an explicit include_unknown_availability audit query can see it.

// PIT resolution for the revenue obs_key:
//   as_of 2020-01-01  → only sha256:c4e0 eligible → value 260,174,000,000 (original)
//   as_of 2022-01-01  → both eligible; §6.3 ranks the 2021 one first → 259,900,000,000 (restated)

// DatasetVersion (immutable manifest)
{ "dataset_version_id": "sha256:aa01…", "transformation_version_id": "sha256:7d31…",
  "availability_policy_ids": ["sha256:policyA…"],
  "raw_document_ids": ["sha256:9f2c…", "…"], "fact_ids": ["sha256:c4e0…", "sha256:e880…", "…"],
  "parent_dataset_version_id": null }
```

---

## 15. Open design questions

Several of these have now been investigated empirically; see
docs/sec-reconnaissance.md for evidence. Status markers below: **[RESOLVED]**,
**[PARTIALLY RESOLVED]**, or **[OPEN]**.

1. **AvailabilityPolicy fidelity (highest risk).** **[PARTIALLY RESOLVED]** Each
   `AvailabilityPolicy` version ships as `confidence: unvalidated` until checked
   against **real** SEC filings. Recon *resolved*: `acceptanceDateTime` is **UTC,
   ms precision, uniform** across issuers; EDGAR's **daily index** is an explicit
   "dissemination feed" but at **date granularity** (no intraday dissemination
   time); the Archives `Last-Modified` header trails acceptance by ~2–7 min.
   Recon *confirmed the hazard*: post-ET-cutoff acceptances are **deemed filed the
   next business day** (observed for Apple/Meta/Tesla/Kraft Heinz 10-Qs; and a
   weekend Saturday acceptance → Monday filingDate for Tesla). Still **[OPEN]**:
   the exact cutoff value and how it varies **by form type and era**, and the
   authoritative SEC/business holiday calendar. Until validated a policy rounds
   **later** and returns `unknown` when it cannot defend a timestamp.

2. **companyfacts vs submissions join.** **[RESOLVED]** companyfacts carries
   **no acceptance timestamp** (only `filed`, a date), so acceptance **must** be
   joined from submissions per accession. Recon validated the join is **100%
   reliable**: across all 6 issuers (~180k submission accessions, ~9k distinct
   companyfacts accessions) there were **0 malformed and 0 missing** accessions —
   *provided* the submissions `filings.files` overflow pages are followed
   (JPMorgan needed 69 overflow pages; skipping them would falsely orphan
   thousands of accessions). Any value that cannot be tied to an accession with
   real availability evidence is `unknown` and PIT-ineligible (invariants 8–9).

3. **What counts as "verified" vs "derived" availability.** **[PARTIALLY
   RESOLVED]** Recon shows the strongest *direct* evidence realistically
   available is **date-level** (daily dissemination index) plus a server
   `Last-Modified` — neither gives a guaranteed intraday public-visibility
   instant. This implies `verified` (intraday, direct) will be **rare**; most
   facts will be `derived` (acceptance + policy cutoff) and a real population will
   be `unknown` (pre-XBRL, no evidence). Define the exact promotion bar as a
   policy decision; the evidence ceiling is now known.

4. **Frame/period canonicalization.** How to canonically derive
   `period_start/end` and fiscal focus when contexts disagree with `dei` focus
   tags; how to treat instant-vs-duration edge concepts.

5. **Dimensions_hash normalization.** **[PARTIALLY RESOLVED]** Recon confirms
   dimensions are pervasive (92–98% of contexts across Apple/GE/Tesla/Meta) and
   include **typed members** (GE, Tesla) and geographic/segment/product axes, and
   that companyfacts drops all of them — so the hash **must** be built from the
   XBRL instance. Canonical serialization validated in recon: **sorted
   `(axis_qname, member_qname)` pairs** for explicit members, and for typed
   members `(axis_qname, "[typed]" + child_element_qname + "=" + normalized_text)`;
   the default (undimensioned) context hashes to the empty sentinel. Namespaces
   must be resolved to stable QNames (prefixes vary by filing). Finalize the exact
   text/whitespace normalization for typed-member values before implementation.

6. **Unit canonicalization table.** **[PARTIALLY RESOLVED]** Recon enumerated the
   real vocabulary: `iso4217:*` (USD, EUR, INR, CAD, plus FX pairs), `xbrli:shares`,
   `xbrli:pure`, compound `USD/shares` (an XBRL `divide` of numerator/denominator
   measures), duration units (`utr:D`), and **many custom `<issuer>:*` units**
   (`ge:segment`, `meta:judicialCase`, `aapl:Customer`, `tsla:Vehicles`, …). The
   canonical representation therefore needs **structured** fields — `unit_id`,
   `numerator_measure`, `denominator_measure` (nullable), `currency` (nullable),
   plus `scale`/`decimals` — not a single string token. The authoritative map is
   owned by `TransformationVersion`; unknown/custom units must be tolerated
   (passed through structurally), never dropped.

7. **CIK merger/reassignment.** **[PARTIALLY RESOLVED]** Recon confirms CIK is
   stable across name changes, ticker changes, and reincorporation, and that
   `formerNames` (effective-dated) captures name history (JPMorgan shows a 4-name
   chain back to Chemical Banking). Still **[OPEN]**: true multi-CIK
   mergers/succession (two predecessor CIKs → one) need an explicit alias mapping
   (as data), never fact mutation. Case 13 depends on this.

8. **Same-obs_key contradictions within a single filing.** **[OPEN]** Not
   observed as a contradiction in recon, but multi-filing duplicate period-keys
   are extremely common (identical repeats: 4,799–13,544 per issuer) and a
   **val=0 pseudo-nil** artifact was seen (Kraft Heinz). Confirm the exact
   data-quality policy (flag, prefer most-precise `decimals`, etc.).

9. **Amendment linkage source.** **[RESOLVED]** SEC exposes **no** explicit
   base-accession link anywhere in structured metadata (submissions, companyfacts)
   or even the SGML submission header. Linkage **must be inferred**, deterministic
   and versioned, and carry `amendment_link_confidence` (§7.1). Confirmed across
   all 6 issuers.

10. **Non-XBRL / pre-XBRL filings.** **[PARTIALLY RESOLVED]** Recon confirms an
    era boundary in the *package*: pre-~2020 filings ship a **standalone** XBRL
    instance + `Financial_Report.xlsx`; ~2020+ are **inline** iXBRL with the
    instance extracted as `*_htm.xml` + a `MetaLinks.json`. Both parse to the same
    fact model (validated on Meta's 2025 inline 10-K). Truly pre-XBRL text-only
    filings remain the most likely `unknown`-availability population; decide
    whether the dataset simply starts at the XBRL era.

11. **Restatement vs comparative disambiguation.** Whether we ever need to
    *label* an observation as "restatement" vs "routine comparative" — the PIT
    math doesn't need the label, but research/UX might.

12. **Form-type policy coverage.** Enumerate which SEC form types need distinct
    availability policies (e.g., forms with historical delayed dissemination or
    special processing) versus a shared default, and how eras are bounded.

---

*This document is normative for the data model. Implementation of any component
must satisfy §12. Changes to the temporal rules (§2, §PA, §6), the availability
policy model (§PA, §9), the knowledge-state/revised-truth semantics (§KS), or
the invariants (§12) require updating this document first.*
