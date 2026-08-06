# Filing Registry (Phase 2)

The Filing Registry transforms the immutable SEC acquisition artifacts produced
by Phase 1 (the [SEC Acquisition Layer](sec-acquisition.md)) into a structured,
deterministic registry of SEC filings and their provenance. It knows **about**
filings — accession, form, reporting period, when filed, when accepted, the
primary document, which raw artifacts correspond, whether a filing is an
amendment and how defensibly that is known — but it **never interprets the
financial content** inside a filing. Fact extraction, XBRL parsing, units,
dimensions, and point-in-time resolution are all later phases.

Package: `src/openfinance/registry/`.

The registry follows [docs/data-model.md](data-model.md) exactly. It does not
introduce a competing schema. Section references below (§4, §7.1, §11, …) point
into the data model.

> **Three timestamps, none of which is public availability.** This is the single
> most important semantic constraint in this document, so it is stated up front
> and repeated where relevant:
>
> - **acceptance timestamp** (EDGAR `acceptanceDateTime`) is *not* public
>   availability.
> - **filing date** (`filingDate`) is *not* public availability.
> - **report date** (`reportDate`) is *not* public availability.
>
> Public availability is a *derived, policy-versioned* concept (dissemination
> rules, the 5:30 PM ET cutoff, weekends/holidays) that this layer deliberately
> **does not** implement. The registry stores the raw SEC-supplied values only;
> deriving availability belongs to the point-in-time layer in a later phase.

---

## 1. Purpose

The registry answers exactly these questions about a filer's filings, and no
more:

- What filings does a company have?
- For each filing: its accession number, form type, reporting period
  (`report_date`), when it was filed (`filing_date`), when EDGAR accepted it
  (`acceptance_timestamp_utc`), and its primary document.
- Which raw acquisition artifacts correspond to the filing (index, primary
  document, XBRL package components)?
- Is the filing an amendment, and — if so — how defensibly can its base filing
  be identified?
- What immutable evidence supports every record?

It is **derived state**. Raw artifacts are the authoritative system of record;
the registry is a deterministic function of them and can be deleted and rebuilt
at any time. The registry **never overwrites raw SEC artifacts** and never
writes into the Phase 1 store.

Explicitly out of scope (see §19): XBRL fact parsing, `RawFact`/`Fact`,
normalization, units, dimensions, point-in-time resolution, availability
policies, factors, backtesting, portfolios, web UI, AI, and database
infrastructure.

## 2. Relationship to Phase 1

The registry **reuses** Phase 1 wholesale — there is no second HTTP client and
no second storage system. The architectural chain is:

```
RAW SEC EVIDENCE → ACQUISITION ARTIFACTS → FILING REGISTRY → [XBRL parsing, Phase 3]
      (SEC)            (Phase 1 store)         (Phase 2)
```

Phase 2 depends on Phase 1 only through small, additive, read-only surface
added to Phase 1:

| Phase 1 addition | Purpose |
| --- | --- |
| `AcquisitionMetadata.from_dict` | Read persisted provenance records back off disk. |
| `ArtifactStore.iter_metadata()` | Iterate every stored artifact's metadata (skips unreadable/invalid records; never touches blobs unless asked). |
| `SecClient.store` property | Read-only access to the content-addressed store backing a client. |

Nothing in Phase 1's behavior changed. The registry consumes Phase 1 artifacts;
Phase 1 has no knowledge of the registry.

## 3. Inputs

The registry consumes two kinds of already-acquired Phase 1 artifacts:

- **Submissions artifacts** (`ArtifactType.SUBMISSIONS`) — SEC's per-filer
  filing history JSON: the primary `CIK##########.json` page plus every
  overflow page named in `filings.files`. These are the *inventory* the
  registry is built from.
- **Filing-package document artifacts** (every other `ArtifactType`: filing
  index, filing document, and the XBRL components — instance, schema,
  cal/def/lab/pre) — associated to filings by provenance, never parsed.

Two build entry points exist on `FilingRegistry`:

- `build_company_from_store(cik)` — build entirely offline from artifacts
  already in a Phase 1 `ArtifactStore`. This is the production path.
- `build_company_from_artifacts(submissions, *, documents=())` — build from an
  explicit list of artifacts, used by tests and by callers that manage
  acquisition themselves.

The registry performs **no network I/O**. Acquisition is Phase 1's job.

## 4. Outputs

The unit of output is a `FilingRecord` (see `model.py`), holding only facts
about a filing:

| Field | Meaning |
| --- | --- |
| `filing_id` | Canonical identity, `accession:` + dashed accession (§11). |
| `company_id` | Canonical filer identity, `cik:` + 10-digit CIK (§11). |
| `accession_number` | Canonical dashed accession. |
| `accession_number_original` | The accession string exactly as SEC supplied it. |
| `form` | SEC form label, verbatim (`10-K`, `10-K/A`, `8-K`, …). |
| `filing_date` | Legal "filed as of" date, or `None`. |
| `report_date` | Period of report, or `None` (non-periodic forms). |
| `acceptance_timestamp_utc` | EDGAR `acceptanceDateTime`, verbatim UTC, or `None`. |
| `primary_document` / `primary_document_description` | Primary doc filename + SEC description, or `None`. |
| `is_amendment` | Whether `form` carries a `/A` suffix. |
| `amends_accession` | Canonical accession of the base filing, when defensibly derived; else `None`. |
| `amendment_link_confidence` | `AmendmentLinkConfidence`, or `None` for non-amendments. |
| `documents` | Tuple of `DocumentReference` to corresponding raw artifacts. |
| `provenance` | `FilingProvenance` pointing back to the source artifact. |

Records serialize via `to_dict()` to a deterministic logical form (see §14).

## 5. Filing identity

Filing identity is `filing_id = "accession:" + <canonical dashed accession>`,
e.g. `accession:0000320193-23-000106`. Company identity is
`company_id = "cik:" + <zero-padded 10-digit CIK>`, e.g. `cik:0000320193`.

Per data-model §11, **an identifier must never depend on a mutable value** — never
a ticker, a company name, a reported figure, or a filesystem path. Identity is a
pure function of the accession number and CIK, both SEC-assigned stable
identifiers. Because identity excludes retrieval time, wall-clock, and random
values, the same filing always yields the same identity across machines and
runs (§14).

## 6. CIK handling

`company_id` is derived from the CIK using Phase 1's canonicalization, so the
submissions API's zero-padded string and the companyfacts API's integer map to
one identity. The CIK identifies the **filer/registrant**.

Per the data model, a single CIK is treated as the stable filer across name,
ticker, and reincorporation changes. **The registry does not silently assume the
CIK is an immutable economic-company identity**, and does not model a separate
economic-company entity — the data model does not define one at this layer, so
neither does the registry. Tickers and company names are never used as
identifiers.

## 7. Accession handling

The canonical accession form is the **dashed** 18-digit representation SEC
assigns (`NNNNNNNNNN-NN-NNNNNN`). `canonical_accession` accepts either the
dashed form or the 18-digit undashed form (as it appears in EDGAR URL paths) and
normalizes to dashed. Any other shape raises `AccessionFormatError` —
**the registry never invents or repairs an accession number.**

The original SEC representation is preserved verbatim in
`accession_number_original`, so a value that arrived undashed can still be
audited against the source even though identity uses the canonical form.

## 8. Date semantics

`filing_date` and `report_date` are kept **strictly separate** and are never
collapsed into one another:

- `filing_date` is the legal "filed as of" date.
- `report_date` is the period of report; it is `None` when SEC omits it (e.g.
  Form 4 and other non-periodic forms).

**Neither is public availability.** A test proves they stay distinct, and the
live validation (§18) confirms on real data that they differ for the large
majority of filings (e.g. 1,648 of Apple's 2,238 filings have
`filing_date != report_date`).

## 9. Timestamp semantics

`acceptance_timestamp_utc` stores EDGAR's `acceptanceDateTime` **exactly as
supplied, in UTC, at millisecond precision**. The registry does **not**:

- convert the timestamp to Eastern Time (no ET conversion at this layer);
- infer public availability from it;
- implement any dissemination / 5:30 PM ET / weekend / holiday rule.

Acceptance is when EDGAR accepted the submission. It is **not** when the filing
became publicly available. Absence is preserved as `None`.

## 10. Form handling

The `form` field is treated as **source metadata** and stored verbatim (`10-K`,
`10-K/A`, `10-Q`, `10-Q/A`, `8-K`, `8-K/A`, `4`, `13F-HR`, …). Missing or empty
form or accession on a row is a hard error (§16) — the registry never fabricates
a form. `is_amendment` is derived purely from the `/A` suffix of the label.
`filings_by_form(cik, form)` matches the SEC label **exactly and
case-sensitively**: `10-K` does not match `10-K/A`, because an amendment is a
distinct form.

## 11. Amendment semantics

SEC exposes **no** explicit "this filing amends accession X" field anywhere in
structured metadata (submissions, companyfacts) or the SGML header. Any linkage
is therefore *derived*, and the registry records **how defensibly** via
`AmendmentLinkConfidence` (data-model §7.1, invariant 22a), using the model's
exact terminology:

| Confidence | Rule |
| --- | --- |
| `SOURCE_ASSERTED` | SEC (or the filing itself) states the base accession explicitly. Reserved; not observed in structured metadata for periodic reports. |
| `DERIVED_HIGH_CONFIDENCE` | Form is exactly `base + "/A"`, **same CIK**, **same report date**, exactly **one** candidate base filing, and consistent chronology (amendment accepted after the base, compared on millisecond acceptance timestamps). |
| `DERIVED_LOW_CONFIDENCE` | `/A` + same report date, but the base is **ambiguous** (several candidates, exactly one of which precedes the amendment) or chronology could be compared only by date (acceptance timestamps unavailable). |
| `UNKNOWN` | No defensible base (missing report date, no matching base filing, orphan `/A`, or irreducible ambiguity). The amendment is represented standalone with `amends_accession = None`. |

**The system NEVER guesses.** It does **not** assume that "same issuer + same
period + `/A`" is sufficient on its own; chronology and uniqueness are required
before a high-confidence link is asserted. When a link cannot be defended, the
result is `UNKNOWN` — never a fabricated `amends_accession`. Amendment linkage
is never required for correctness of anything downstream; it is derived
convenience metadata.

**Critical non-case (data-model §13, case 11):** a regular filing that merely
*contains prior-period comparative information* (e.g. a 10-K whose statements
carry the prior fiscal year's columns) is **not** an amendment. Only a `/A` form
is ever considered for linkage, so a later 10-K reporting a prior period in its
comparatives is a standalone filing, linked to nothing. This is proven by a
dedicated test (`test_comparative_period_filing_is_not_an_amendment`).

## 12. Document association

The registry records **which acquired artifacts belong to which filing** — the
filing index, the primary document, and any XBRL package components — **without
parsing any of them**. Association is by **provenance**, not by guessing from
bytes: every non-submissions artifact carries acquisition metadata with the CIK
and accession it was fetched for, so a document attaches to a filing iff their
canonical accessions match **and** their CIKs agree.

Fail-closed rules:

- An artifact whose accession matches a filing but whose CIK **contradicts** it
  raises `DocumentAssociationError` — never attach across a CIK mismatch.
- An artifact with no accession in its provenance is **not** associated with any
  filing.
- The `is_primary_document` flag is set only when a document's source-URL
  basename exactly equals the filing's SEC-declared `primary_document` — no
  fuzzy matching.
- Submissions artifacts are registry *inputs*, not package documents, and are
  never associated as documents.
- Repeat acquisitions of the same bytes are de-duplicated by content hash;
  references are emitted in a stable sorted order.

## 13. Provenance

Every `FilingRecord` carries `FilingProvenance` that traces it back to the
immutable evidence it was derived from:

- `source_artifact_sha256` — the content hash of the submissions artifact the
  record was parsed out of (the record can always be traced to, and rebuilt
  from, that raw artifact).
- `source_artifact_type` — the Phase 1 artifact classification.
- `source_url` — the endpoint the artifact was retrieved from.
- `transformation_version_id` — the registry logic version that performed the
  derivation (§15).

Each associated `DocumentReference` likewise carries the artifact's content hash
and source URL. A derivation timestamp is intentionally **not** part of
provenance's logical identity (see §14). `filing_provenance(cik, accession)`
exposes a filing together with its provenance and document references.

## 14. Determinism

Given the same acquisition artifacts and the same `TransformationVersion`, the
registry produces **byte-identical** logical records, independent of artifact
iteration order. This is guaranteed structurally:

- **Identity** derives only from accession + CIK — never from retrieval time,
  wall-clock, or a random UUID.
- **Ordering independence** — records are keyed by accession into a map during
  the build, then emitted sorted by accession; documents within a record are
  sorted by `(artifact_type, sha256)`.
- **No nondeterministic fields in `to_dict()`** — the derivation timestamp is
  excluded from a record's canonical serialization, so a rebuild reproduces the
  same bytes regardless of when it runs.
- **On-disk bytes** are written with `sort_keys=True`, so re-serializing the
  same logical records yields identical files.

The live validation (§18) rebuilds Apple's registry twice and confirms the two
serializations are identical.

## 15. Versioning

Two independent version numbers are recorded:

- **`REGISTRY_LOGIC_VERSION`** (`"filing-registry/1"`) — the registry's
  derivation logic, the analogue of a code git SHA. A `TransformationVersion`
  combines it with a `config_hash` into a
  `transformation_version_id = "sha256:" + sha256(code_version \x00 config_hash)`.
  Changing the derivation logic in a way that can alter records must bump this
  (or pass a new `code_version`), producing a distinguishable id. The id depends
  **only** on code version and config — never on wall-clock, ordering, or a
  random value.
- **`REGISTRY_FORMAT_VERSION`** (`1`) — the on-disk file envelope version,
  distinct from the logic version: this governs the container shape, that
  governs the derived record content.

The transformation version id is written into every stored company file and
into every record's provenance.

## 16. Error handling

The registry **fails safely** — it preserves evidence and reports validation
errors rather than silently guessing or corrupting derived state:

| Situation | Behavior |
| --- | --- |
| Row with missing/empty accession | Hard error (`SourceValidationError`); never invent an accession. |
| Row with missing/empty form | Hard error (`SourceValidationError`); never fabricate a form. |
| Misaligned columnar arrays | Hard error; the source shape is corrupt. |
| Corrupt / non-JSON submissions bytes | `SourceValidationError` (evidence preserved; validation fails). |
| No resolvable CIK (neither metadata nor body) | `SourceValidationError`. |
| Missing report date / acceptance / description | Preserved as `None`; never fabricated. |
| Undefensible amendment link | `UNKNOWN`, not guessed. |
| Document accession matches but CIK contradicts | `DocumentAssociationError` (fail closed). |
| Document with no accession, or malformed accession | Skipped, not attached to the wrong filing. |
| Same accession appears twice with disagreeing attributes | `SourceValidationError` (`_check_consistent`); never silently pick one. |

`iter_metadata()` (Phase 1) is the one place that is intentionally lenient: it
skips individually unreadable/invalid metadata files so one bad file cannot
abort a whole-store scan — but any artifact it *does* yield is validated by the
registry as above.

## 17. Rebuild procedure

The registry is derived state and is safe to delete and regenerate:

1. Delete the registry store directory (e.g. `registry/filings/`). Raw
   artifacts in the Phase 1 store are untouched — they are authoritative.
2. For each filer, call `FilingRegistry.build_company_from_store(cik)`. This
   reads every stored submissions artifact for that CIK (primary + all overflow
   pages) and every stored filing-package artifact, then re-derives records
   entirely offline.
3. The regenerated files are byte-identical to the originals, provided the same
   artifacts and the same `TransformationVersion` are used (§14).

Rebuilding never mutates raw artifacts and never requires the network.

## 18. Live SEC validation

After the unit suite passed, the registry was validated against **live** SEC
data for a small, deliberately-chosen set of issuers. All downloaded artifacts
and the derived registry were stored **outside** the repository (git never sees
raw data). The validation script lives outside the repo, uses Phase 1's
`build_client()` for acquisition and `FilingRegistry` for derivation, and
requires an email-format `OPENFINANCE_SEC_USER_AGENT`.

Issuers and observed results:

| Issuer | CIK | Pages | Filings | Notes |
| --- | --- | --- | --- | --- |
| Apple Inc. | 320193 | 2 | 2,238 | Required baseline; 52 distinct forms. |
| Tesla, Inc. | 1318605 | 2 | 1,748 | Carries 10-K/A-style amendments (`/A` forms). |
| Berkshire Hathaway Inc. | 1067983 | 2 | 2,388 | Prolific filer, 60 distinct forms, substantial XBRL complexity. |

Confirmed on real data:

- **Pagination** — both the primary page and the overflow page(s) named in
  `filings.files` were acquired and merged for every issuer.
- **Date separation** — `filing_date != report_date` for the majority of
  filings (Apple 1,648; Tesla 1,001; Berkshire 1,390), proving the two dates are
  not collapsed.
- **Timestamps** — `acceptance_timestamp_utc` stored verbatim in UTC (e.g.
  `2017-07-10T22:30:23.000Z`), never converted.
- **Amendments** — confidence distributions were realistic and conservative,
  e.g. Tesla: `{UNKNOWN: 94, DERIVED_HIGH_CONFIDENCE: 16, DERIVED_LOW_CONFIDENCE: 1}`;
  Berkshire: `{UNKNOWN: 390, DERIVED_HIGH_CONFIDENCE: 113}`. The many `UNKNOWN`
  results are the system declining to guess a base it cannot defend.
- **Provenance** — every derived record (100%) carried a source-artifact hash.
- **Determinism** — rebuilding Apple's registry twice produced identical logical
  records.

## 19. Explicitly deferred functionality

The registry deliberately does **not** implement any of the following; they
belong to later phases and are called out here so the boundary is unambiguous:

- XBRL fact parsing; `RawFact` and `Fact`; normalization; units; dimensions.
- Point-in-time resolution and **public-availability derivation** — including
  dissemination rules, the 5:30 PM ET cutoff, and weekend/holiday handling.
  (Acceptance, filing date, and report date are **never** public availability.)
- Availability policies, factors, backtesting, and portfolio construction.
- Web UI, AI features, and any database infrastructure (Phase 2 uses a simple,
  deterministic file representation that can be materialized into
  DuckDB/Parquet later without reshaping).
