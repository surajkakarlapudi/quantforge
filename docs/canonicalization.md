# Canonicalization (Phase 4)

The canonicalization layer transforms the immutable, loss-preserving
**`RawFact`** records produced by Phase 3 (the
[Raw XBRL Ingestion](xbrl-ingestion.md) layer) into deterministic, structured
**canonical `Fact`** records — one canonical observation per
`(obs_key, filing, transformation version)` — while retaining **complete
lineage** back to every raw fact, raw document, source artifact, and SEC filing.

Package: `src/quantforge/canonical/`.

This layer follows [docs/data-model.md](data-model.md) exactly — the canonical
`Fact` entity (§3), its observation key (§6.2), its identity (§11), the
transformation version (§9), the provenance chain (§5), and the fail-closed
determinism invariants (§12). Section references below point into the data model.

> **This layer structures without interpreting.** It classifies concepts and
> units, folds scale and sign into an exact value, and computes deterministic
> identity — but it never guesses a mapping, never resolves a restatement, never
> infers a fiscal period, and never manufactures a financial value. When the raw
> material is ambiguous it preserves the ambiguity (as `UNKNOWN`, as the original
> concept, as the raw structure) or fails closed. It loses nothing.

---

## 1. Purpose

The layer answers exactly one question, for one stored raw XBRL instance:

> What are the structured, comparable observations this filing reported — and how
> does each trace back, byte-for-byte, to its source?

It produces, per instance, a set of **`Fact`** records. Each Fact carries:

- **Identity** — a deterministic `fact_id` and the `obs_key` it derives from.
- **Concept** — the fully-qualified concept (Clark notation), its namespace URI,
  local name, and a `taxonomy` label.
- **Period** — `instant` / `duration` / `forever` with its defining dates.
- **Unit** — a conservative canonical token (`USD`, `shares`, `USD/shares`,
  `pure`, or `UNKNOWN`) plus a currency, backed by the raw structural unit.
- **Value** — the canonical `value_numeric` in **base units** (scale and sign
  folded exactly once, exact `Decimal`), or `value_text` for a non-numeric
  concept, with `is_nil` first-class (nil ≠ zero).
- **Dimensions** — every explicit and typed member, preserved, plus the
  deterministic `dimensions_hash`.
- **Raw survivors** — the raw lexical value, raw scale, raw sign, raw decimals.
- **Provenance** — the unbroken chain back to the SEC source.

It is **derived state**. The Phase 1 content-addressed store is the authoritative
system of record; Phase 3's raw store is its faithful parse; this layer is a
deterministic function of the raw records under a fixed transformation version and
can be deleted and rebuilt to byte-identical output. It **never writes into the
Phase 1 or Phase 3 stores** and never touches raw SEC artifacts.

Explicitly out of scope (Phase 5 and beyond, per data-model §22): point-in-time
selection, public-availability derivation, restatement resolution, factor
construction, backtesting, portfolio construction, investment recommendations.

## 2. Relationship to Phases 1–3

There is no second HTTP client and no second storage system (requirement 18). The
chain is:

```
RAW SEC EVIDENCE → ACQUISITION → FILING REGISTRY → RAW XBRL → CANONICAL FACT → [Phase 5]
      (SEC)         (Phase 1)      (Phase 2)        (Phase 3)     (Phase 4)
```

- **Phase 1** owns acquisition and the content-addressed `ArtifactStore`.
- **Phase 2** owns filing identity. Phase 4 attributes every Fact to a filing
  using the *same* canonical identity functions (`company_id`, `filing_id`), so a
  Fact's `filing_id`/`company_id` are exactly the registry's.
- **Phase 3** owns the immutable `RawFact`. Phase 4 reads those raw records back
  from the `RawXbrlStore` (read-only) and canonicalizes them **offline** — no
  network I/O ever enters this layer.
- **Phase 4** adds a small derived store (`CanonicalFactStore`) alongside — not
  inside — the earlier stores, following the Phase 2/3 file-store precedent. No
  database is introduced; the data model lists DuckDB/Parquet (§10) only as a
  *future* materialization of this same shape.

## 3. Architecture

The layer is deliberately modular; each concern is a separate module with a
single responsibility.

| Module | Responsibility |
| --- | --- |
| `errors.py` | `CanonicalError` → `CanonicalContradictionError`; the fail-closed vocabulary. |
| `version.py` | `CanonicalFactVersion` — the deterministic normalizer version id (§9/§11). |
| `taxonomy.py` | `Taxonomy` enum + `classify_taxonomy` (by namespace URI, never prefix; never a closed vocabulary). |
| `concept.py` | `Concept` + `concept_from_clark` — lossless concept, no mapping/merging. |
| `period.py` | `CanonicalPeriod` + `canonicalize_period` — instant/duration/forever, no fiscal inference. |
| `units.py` | `CanonicalUnit` + `canonicalize_unit` — conservative unit canonicalization, `UNKNOWN` when unsure. |
| `numeric.py` | Safe scale/sign folding into an exact `Decimal`; deterministic serialization; nil ≠ zero. |
| `model.py` | `Fact`, `FactProvenance`, `CanonicalDimension`; the `obs_key` and `fact_id` identity functions. |
| `canonicalize.py` | `Canonicalizer` — the pure core: RawFacts ⇒ canonical Facts, with duplicate collapse and contradiction detection. |
| `store.py` | `CanonicalFactStore` — deterministic, one-file-per-instance derived storage. |
| `ingest.py` | `CanonicalizationIngestor` — the façade composing the Phase 3 store + normalizer + canonical store. |

Data flow for one instance:

```
RawXbrlStore.read_instance(raw_document_id)   # RawDocument + contexts + units + facts
        │
        ▼
Canonicalizer.canonicalize_records(...)       # offline, deterministic, fail-closed
        │   ├── concept + taxonomy   (no mapping)
        │   ├── period               (no fiscal inference)
        │   ├── unit                 (UNKNOWN when unsure)
        │   ├── numeric              (scale & sign folded once; nil ≠ zero)
        │   └── obs_key → fact_id    (§6.2, §11)
        ▼
CanonicalFactStore.write_instance(result)     # deterministic JSON, one file per instance
```

The clean public API is conceptually `Canonicalizer(...).canonicalize(parsed)`
(requirement 19): given a `ParsedInstance` (or its constituent raw records) it
returns a `CanonicalizeResult`.

## 4. The canonical Fact model

A `Fact` is **one observation of one concept, for one period, in one dimensional
context, as asserted by one filing** (§3). Every raw distinction that could
separate two observations is preserved on it, and **no raw information is thrown
away** during canonicalization (requirement 1): the canonical value is *added*
alongside the raw lexical value, scale, sign, and decimals, which all survive
verbatim.

### 4.1 Concept and taxonomy handling (no aggressive mapping)

- Concepts are preserved in **Clark notation** (`{namespace-uri}local`), the
  stable, prefix-independent identity Phase 3 already produced. There is **no**
  concept-to-concept mapping, synonym table, or "canonical concept" — none can be
  established with high confidence in this phase, so the original always survives.
  `RevenueFromContractWithCustomerExcludingAssessedTax` stays distinct from
  `Revenues`; an issuer `<ticker>:*` concept stays intact.
- The `taxonomy` enum (`us-gaap`, `dei`, `srt`, `ifrs-full`, `custom`, `unknown`)
  is a convenience label *alongside* — never instead of — the fully-qualified
  concept. Classification is by **namespace URI stem** (`startswith` on the stable
  publisher stems, so yearly-versioned URIs classify correctly), **never by
  prefix**. An unrecognized *namespaced* URI is `custom` (an issuer extension,
  preserved, never rejected); an unqualified concept with no namespace is
  `unknown` (we never guess). This is a recognition list, **not** a closed
  vocabulary.

### 4.2 Period canonicalization (no fiscal inference)

A period is defined **solely by its dates**, never by a calendar or a fiscal
focus (recon §11 found the same period-end tagged FY2017/Q1-2018/FY2019 across
filings). `instant` → `period_end` carries the point; `duration` →
`period_start`/`period_end`; `forever` → preserved as its own type with no dates
(rather than coerced or dropped). Dates are the exact lexical `xsd:date` strings;
they are never reformatted, reparsed, or timezone-shifted. `fiscal_year` /
`fiscal_quarter` are **not** derived here — they are the *filing's* document
focus (reporting metadata), not per-observation truth (see §9, "deferred").

### 4.3 Unit canonicalization (conservative)

The **raw unit is always separated from the canonical unit.** Canonicalization
looks only at the declared measure QNames — **never** at the concept name — and
maps only the small set it can resolve unambiguously:

| Raw measure(s) | Canonical token | Currency |
| --- | --- | --- |
| single `iso4217:<CCC>` | `<CCC>` | `<CCC>` |
| single `xbrli:shares` | `shares` | — |
| single `xbrli:pure` | `pure` (not percent) | — |
| `divide` of `iso4217:<CCC>` / `xbrli:shares` | `<CCC>/shares` | `<CCC>` |

Everything else — multi-measure units, `utr:*` unit-registry measures (e.g.
`utr:D` days), custom `<issuer>:*` measures, unrecognized `divide` shapes, and a
non-numeric fact with no unit — is left `UNKNOWN` with `currency = None`. **An
unknown unit is never silently coerced or converted.** The raw structure (measure
QNames, numerator/denominator role, the document-local `unit_id`) always survives,
so a later transformation version can canonicalize more once a mapping is
justified.

### 4.4 Numeric value, scale, and sign

- **Exact arithmetic.** All numeric work uses `Decimal`, never binary `float`.
- **Scale folded exactly once.** Phase 3 deliberately does *not* apply `scale`;
  Phase 4 folds it in once — `value_numeric = raw_value × 10**scale`. So
  value=123 scale=3 becomes `123000` and is never scaled twice. Default scale is
  0. A non-integer `scale` on a numeric fact fails closed (`CanonicalError`) — we
  never fabricate a value from a guessed scale.
- **Sign folded exactly once.** XBRL `sign="-"` negates the reported magnitude;
  Phase 4 applies it once. Any `sign` other than absent or `-` is malformed and
  fails closed.
- **nil ≠ zero.** A nil fact yields `value_numeric = None` and `value_text =
  None`; it is *never* coerced to `0`, and `is_nil` stays `True`.
- **Non-numeric concepts** keep their raw text in `value_text`;
  `value_numeric = None`.
- **Deterministic serialization.** `value_numeric` is serialized in plain
  (never scientific) notation, trailing fractional zeros stripped, negative zero
  normalized to `"0"`, so equal magnitudes always serialize to identical bytes.
  Precision is not lost — it is carried separately by `decimals`.
- **Raw survivors.** `raw_value`, `raw_scale`, `raw_sign`, and `raw_decimals` are
  retained verbatim, so the fold is fully re-derivable and auditable. `decimals`
  is precision metadata only: `INF`/absent/non-integer degrades to `None` with the
  raw string retained (never a hard failure).

### 4.5 Dimensions (preserved, never collapsed)

Every explicit and typed member is preserved as a `CanonicalDimension`, and the
Phase 3 `dimensions_hash` (a sorted, prefix-independent, order-independent digest,
§15.5) is carried onto the Fact. **Two facts that differ only by dimension remain
distinct** — dimensions are part of the observation key.

## 5. Deterministic identity (§6.2, §11)

Identity is a pure function of the raw records + transformation version. It
depends on **no** ticker, company name, retrieval timestamp, wall clock, random
UUID, or mutable normalized value (requirement 12, invariant 18).

- **`obs_key`** — the observation key deciding when two observations describe "the
  same thing":

  ```
  obs_key = (company_id, security_id, concept, period_type,
             period_start, period_end, unit_ref, dimensions_hash)
  ```

  Two implementation refinements of the §6.2 tuple, documented here as
  refinements (not contradictions — see §11 below):
  - **concept** is the fully-qualified **Clark notation**, which *subsumes* the
    coarse `taxonomy` label. Using the enum instead would let two issuer concepts
    sharing a local name collide, so the qualified concept is authoritative.
  - **unit** is the **raw structural `unit_ref`** (measure QNames + role), not the
    derived canonical token — so two different units that both canonicalize to
    `UNKNOWN` never merge.

- **`fact_id` = `sha256(transformation_version_id, filing_id, obs_key)`**,
  NUL-joined, `sha256:`-prefixed. It **includes the transformation version** (so
  re-normalization under a new version yields a new, distinct Fact while the old
  one is retained — requirement 11) and **excludes `raw_fact_id`** (so a genuine
  duplicate raw fact collapses to one Fact).

### 5.1 RawFact → Fact cardinality (§4)

One *or more* RawFacts reduce to *at most one* Fact:

- A genuine **duplicate** — the same `obs_key` **and** the same canonical value
  within one filing — collapses to a single Fact. Its provenance lists *every*
  contributing raw fact (`raw_fact_ids`), and the canonical representative is the
  member with the lowest `(ordinal, raw_fact_id)`. Nothing is silently dropped:
  the collapse is auditable via `CanonicalizeResult.collapsed_duplicate_count`.
- A **precision variant** — the same `obs_key`, values that differ **only** as
  consistent roundings of a single most-precise figure (different `decimals`) —
  collapses to one Fact carrying the **most-precise** value. This is the resolved
  policy for data-model open-question 8 ("prefer most-precise `decimals`"), driven
  by a pattern that is pervasive in real filings: e.g. Apple's
  `UnrecognizedTaxBenefits` reported as `23,242,000,000` (`decimals=-6`) and
  `23,200,000,000` (`decimals=-8`), the latter being exactly the former rounded to
  the nearest 10⁸. Every contributing raw fact is retained in provenance; the
  representative is the most-precise member (ties broken by lowest
  `(ordinal, raw_fact_id)`). All rounding uses exact `Decimal` half-up arithmetic.
- A **contradiction** — the same `obs_key` but values that are **neither**
  identical **nor** consistent roundings of one most-precise value (a real value
  disagreement, a nil-vs-number mismatch, or a member whose `decimals` cannot be
  read) — is a source data-quality defect we must not arbitrate. We fail closed
  with `CanonicalContradictionError` (§13 case 8).

## 6. Provenance (the unbroken chain)

Every `Fact` carries a `FactProvenance` tracing it back to the SEC source
(requirement 13, §5):

```
Fact → raw_fact_id (+ every raw_fact_ids) → raw_document_id → source_artifact_sha256
     → source_url → filing_id / accession / company_id → transformation_version_id
```

`source_artifact_sha256` is the immutable Phase 1 blob; `source_url` the SEC URL;
`filing_id`/`accession`/`company_id` the Phase 2 identity, preserved verbatim.
`raw_fact_ids` lists every raw fact that reduced to the Fact, so a collapsed
duplicate is still fully traceable.

## 7. Restatements and amendments

- **Restatements are not resolved in Phase 4.** Two filings reporting the same
  economic period keep their own Facts, keyed by their distinct `filing_id`. Both
  are retained; choosing between them is a later point-in-time concern.
- **Amendments are not resolved here either.** A 10-K/A restating a value produces
  Facts under its own `filing_id`. Amendment status/confidence is a Phase 2
  registry concern; if it is `UNKNOWN` there, it stays `UNKNOWN` — Phase 4 does not
  re-derive it.

## 8. Transformation version (§9/§11)

`CanonicalFactVersion` pins the normalizer logic + config with a deterministic
`transformation_version_id = sha256(code_version, config_hash)`. Because the
version is **part of `fact_id`**, a future change to normalization logic produces
new, distinct Facts under a new version while the old Facts remain valid and
untouched — normalization is never silently mutated in place. The version depends
only on code + config, never on wall-clock time, a random value, or input order.
Changing normalization in a way that can alter derived Facts must bump the version.

## 9. Deliberately deferred (not contradictions with §3.1)

Documented here so the omissions are explicit, not silent:

- **`fiscal_year` / `fiscal_quarter`** — the filing's document focus (reporting
  metadata), not per-observation truth; deferred, and not inferred from dates.
- **`security_id`** — requires an external security master absent from EDGAR (a
  CIK identifies a filer/registrant, not a security). We fail closed to `None`
  rather than guess; it is a positional component of `obs_key` reserved for a
  later phase.
- **The three availability fields** (`derived_public_availability_timestamp`,
  `availability_status`, `availability_policy_id`) — Phase 5+ point-in-time
  concerns that data-model §22 explicitly forbids computing here.

## 10. Fail-closed behavior

The layer raises rather than fabricate or silently drop financial data
(requirement 17):

- A raw fact referencing an **unknown context** → `CanonicalError` (corrupted
  derived state; we never guess a period/dimension).
- An **uninterpretable `scale`** or an **unsupported `sign`** on a numeric fact →
  `CanonicalError` (we never fabricate a value).
- A context missing the date(s) its own period type requires → `CanonicalError`.
- Same `obs_key`, values that are **not** consistent roundings of a single
  most-precise figure, one filing → `CanonicalContradictionError` (we never
  arbitrate a genuine data-quality contradiction; see §5.1 for the precision
  variant collapse that is *not* a contradiction).

There are **no silent drops**: every raw fact either contributes to a Fact or
triggers an explicit error, and the result's counts make this auditable.

## 11. Consistency with the raw layer (no contradiction)

The Phase 3 `raw_fact_id` **excludes** the parser version (re-parsing identical
bytes with any parser reproduces the same raw ids). The Phase 4 `fact_id`
**includes** the transformation version. These are complementary by design, not
contradictory: the raw id is pure source content (so the raw layer is a stable
substrate), while the canonical id must change when the normalizer changes (so
re-normalization is a new, retained Fact rather than a silent mutation). The
`obs_key` refinements in §5 (Clark concept, raw structural unit ref) strengthen
the §6.2 tuple against collisions and are documented as refinements, not changes
to the approved model.

## 12. Persistence

`CanonicalFactStore` writes one deterministic JSON document per instance under
`canonical_facts/sha256-<hex>.json`, named by `raw_document_id`. Facts are emitted
**sorted by `fact_id`** and written with `sort_keys=True` (no wall-clock, no
iteration-order dependence), and writes are atomic (temp file + `fsync` +
`os.replace`). Re-canonicalizing the same instance overwrites idempotently with
identical bytes. The envelope records `canonical_facts_format_version` (the
on-disk container version, distinct from the normalizer version) and the
`transformation_version_id`. The store holds only derived state and is safe to
delete and regenerate.

## 13. Security considerations

- **Raw source is never rewritten.** The Phase 3 store is read-only here, and the
  Phase 1 blobs it references are never touched. The raw source remains fully
  recoverable.
- **No network I/O.** Canonicalization is fully offline; it consumes only
  already-derived raw records.
- **Unknown stays unknown.** Unknown units remain `UNKNOWN`; unknown taxonomies
  remain `custom`/`unknown`; nil stays nil. Nothing is silently coerced.
- **Fail closed, never invent.** A raised error is always preferable to a wrong or
  fabricated financial value.
- **No secrets, no wall-clock in identity.** Deterministic derived state can be
  deleted and regenerated byte-for-byte, so a corrupted derived file is never
  authoritative.

## 14. Testing

Per-module unit tests cover taxonomy classification (by URI stem, issuer
extensions, missing namespace), concept preservation (no merging of similar
concepts), period (instant/duration/forever, no reformatting, fail-closed),
conservative units (currency/shares/pure/per-share, `UNKNOWN` for everything
else), numeric handling (exact `Decimal` serialization, scale folded once incl.
value=123 scale=3, negative scale, sign folded once, scale+sign combined, nil ≠
zero, `INF` decimals, non-numeric text, very large/small values), identity
(`obs_key` component sensitivity, `fact_id` includes version + filing, Clark
concept prevents collisions), transformation version, the store round-trip and
byte-determinism, offline ingestion from the raw store, provenance completeness,
and end-to-end determinism.

A dedicated **adversarial information-loss suite** (requirement 15) asserts that
canonicalization never collapses distinct observations merely because they look
similar — at minimum the 15 mandated cases: same concept with different
dimensions / periods / units; nil vs zero; different decimals; different scale;
positive vs negative; custom issuer vs us-gaap concept sharing a local name; the
same economic period across two filings; amendment vs original; multiple
dimensions in different ordering (must *not* split); typed dimensions; two unknown
units (must *not* merge); unknown taxonomy (preserved); and duplicate raw facts
(collapse to one Fact with both raw ids retained). Companion tests cover the
precision-variant policy (§5.1): same-key values that are consistent roundings
collapse to the most-precise value (order-independently), while an inconsistent
rounding or an unreadable `decimals` still fails closed — alongside the base
same-key/different-value contradiction.
