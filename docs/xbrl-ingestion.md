# Raw XBRL Ingestion (Phase 3)

The raw XBRL ingestion layer transforms the immutable SEC XBRL **instance**
artifacts acquired by Phase 1 (the [SEC Acquisition Layer](sec-acquisition.md))
and attributed to filings by Phase 2 (the [Filing Registry](filing-registry.md))
into an immutable, fully-provenanced, deterministically-serialized **raw fact**
representation. It preserves the reported observation *exactly as filed* and
performs **no semantic normalization** — no unit conversion, no concept merging,
no ratios, no choosing between competing observations, no point-in-time
selection, no public-availability determination. All of that is Phase 4.

Package: `src/quantforge/xbrl/`.

This layer follows [docs/data-model.md](data-model.md) exactly — the
`RawDocument` and `RawFact` entities (§4), their identifiers (§11), and the
loss-preserving invariants (§12). Section references below (§4, §11, §15.5, …)
point into the data model.

> **The one job of this layer is to lose nothing.** Every design choice below
> exists to guarantee that the raw source remains recoverable and that no
> reported distinction is silently collapsed. If a decision would trade
> information loss for convenience, this layer fails closed instead.

---

## 1. Purpose

The layer answers exactly one question, for one stored XBRL instance:

> What did this filing report, exactly, before anyone interpreted it?

It produces, per instance:

- a **`RawDocument`** — the content-addressed identity and provenance of the
  parsed instance bytes;
- a set of **`RawContext`** records — entity, period (instant/duration/forever),
  and the full dimensional segment (explicit + typed members);
- a set of **`RawUnit`** records — the structural unit definition
  (simple measure list or `divide` ratio), uninterpreted;
- a set of **`RawFact`** records — one per reported item fact, with the raw
  lexical value, a best-effort numeric parse, `decimals`/`scale`/`sign`, nil
  status, unit reference, dimensional hash, and complete provenance.

It is **derived state**. The Phase 1 content-addressed store is the
authoritative system of record; this layer is a deterministic function of it and
can be deleted and rebuilt to byte-identical output. It **never overwrites raw
SEC artifacts** and never writes into the Phase 1 store.

Explicitly out of scope (Phase 4 and beyond): the canonical `Fact`, unit
canonicalization/currency inference, concept normalization, restatement
resolution, point-in-time selection, public-availability policy, factors,
backtesting.

## 2. Relationship to Phases 1 and 2

There is no second HTTP client and no second storage system (requirement 16).
The chain is:

```
RAW SEC EVIDENCE → ACQUISITION ARTIFACTS → FILING REGISTRY → RAW XBRL FACTS → [Phase 4]
      (SEC)            (Phase 1 store)         (Phase 2)         (Phase 3)
```

- **Phase 1** owns acquisition and the content-addressed `ArtifactStore`. Phase 3
  reads the exact instance bytes back from it (`read_blob`, which re-verifies the
  content hash on read) and never writes there.
- **Phase 2** owns filing identity. Phase 3 attributes every fact to a filing
  using the *same* canonical identity functions (`company_id`, `filing_id`,
  `canonical_accession`), so a fact's `filing_id`/`company_id` are exactly the
  registry's — never a divergent scheme.
- **Phase 3** adds a small derived store (`RawXbrlStore`) alongside — not inside —
  the Phase 1 store, following the Phase 2 file-store precedent. No database is
  introduced (requirement 17); the data model lists DuckDB/Parquet (§10) only as
  a *future* materialization of this same shape.

## 3. Architecture

The layer is deliberately modular (requirement 15); each concern is a separate
module with a single responsibility.

| Module | Responsibility |
| --- | --- |
| `errors.py` | `XbrlError` → `MalformedXbrlError` / `UnsupportedXbrlError`; the fail-closed vocabulary. |
| `version.py` | `XbrlParserVersion` — the deterministic parser/transformation version id (§9/§11). |
| `qnames.py` | Stable, prefix-independent QName resolution to Clark notation; `NamespaceContext` (fails closed on prefix rebinding). |
| `namespaces.py` | The well-known XBRL namespace URIs. |
| `dimensions.py` | `RawDimension` and the deterministic `dimensions_hash` canonicalization (§15.5). |
| `units.py` | `RawUnit` — structural unit representation and the `unit_ref` identity token. |
| `contexts.py` | `RawContext` — entity, period, dimensions. |
| `model.py` | `RawDocument`, `RawFact`, `RawFactProvenance`; identity functions; best-effort numeric parse. |
| `parser.py` | Element-level extraction: contexts, units, dimensions, facts. The core. |
| `store.py` | `RawXbrlStore` — deterministic, one-file-per-instance derived storage. |
| `ingest.py` | `XbrlIngestor` — the façade that composes Phase 1 + Phase 2 + parser + store. |

Data flow for one instance:

```
ArtifactStore.read_blob(sha256)         # exact bytes, hash-verified
        │
        ▼
parse_instance(bytes, SourceIdentity)   # offline, deterministic, fail-closed
        │   ├── contexts  (entity / period / dimensions)
        │   ├── units     (simple / divide)
        │   └── facts      (raw value / numeric / decimals / scale / sign / nil)
        ▼
RawXbrlStore.write_instance(parsed)     # deterministic JSON, one file per instance
```

## 4. Raw XBRL structures supported

The parser accepts a **standard XBRL instance document**: an `{xbrli}xbrl` root
with contexts, units, and item facts. Both filing eras produce the same model
(data model §15.10):

- **Pre-inline era** (roughly pre-2020): a standalone `.xml` instance.
- **Inline / iXBRL era** (roughly 2020+): the SEC-extracted `*_htm.xml` instance
  that accompanies the inline document.

Structures extracted and preserved:

- **Contexts** — entity identifier + scheme; period as **instant**, **duration**
  (`startDate`/`endDate`), or **forever**; the full dimensional segment from both
  `<segment>` (under `<entity>`) and `<scenario>` (under `<context>`).
- **Dimensions** — **explicit** members (`xbrldi:explicitMember`) and **typed**
  members (`xbrldi:typedMember`, one structured child element). Never discarded
  (requirement 4); companyfacts drops these, so the instance is authoritative.
- **Units** — **simple** measure lists (e.g. `iso4217:USD`, `xbrli:shares`) and
  **`divide`** ratios (numerator/denominator measure sets, e.g. `USD/shares`).
  Custom `<issuer>:*` measures pass through as resolved QNames, uninterpreted.
- **Facts** — any element carrying a `contextRef`. Numeric and non-numeric,
  `us-gaap`/`dei`/`srt` and custom `<issuer>:*` concepts handled identically.
  `decimals` (including `INF`), `scale`, and `sign` preserved verbatim; nil
  status is first-class.

Concepts, axes, and members are canonicalized to **Clark notation**
(`{namespace-uri}local`), which is prefix-independent: the same logical concept
resolves identically regardless of the prefix a given filing chose (§II.7).

## 5. Deterministic identity

Identity is a pure function of source content (§11). No wall-clock timestamp,
random value, or input ordering enters any id (§12, invariants 18 & 21).

- **`raw_document_id` = `sha256:<hex>` of the exact source bytes.** Identical
  bytes are the same document. The bytes are *not* copied here — they remain in
  the Phase 1 store, recoverable by content hash.
- **`raw_fact_id` = `sha256(raw_document_id, xbrl_context_ref, concept,
  unit_ref, segment_key, ordinal)`**, NUL-joined. It deliberately **excludes the
  parser version** and every mutable/normalized value: re-parsing identical bytes
  with any parser version reproduces the same fact ids.
  - `unit_ref` is the *structural* unit identity (measure QNames + numerator/
    denominator role), not the document-local `unit_id`, so structurally
    identical units share a ref regardless of source prefixes.
  - `segment_key` is the `dimensions_hash` (below).
  - `ordinal` disambiguates genuine duplicate observations that are otherwise
    identical within one document (§13 case 8), so **no fact is ever silently
    dropped**.
- **`dimensions_hash` = `sha256:<hex>`** of the canonical dimensions key
  (§15.5): the sorted set of `(axis, member)` pairs in Clark notation, with typed
  members serialized as `[typed]child=normalized-text`, and the undimensioned
  context mapped to a stable empty sentinel. Sorting makes it order-independent;
  Clark notation makes it prefix-independent.

## 6. Provenance

Every `RawFact` carries a `RawFactProvenance` tracing it back to (requirement 7):

`filing_id` · `accession` · `company_id` · `source_artifact_sha256` ·
`source_artifact_type` · `source_url` · `source_document_name` ·
`transformation_version_id`.

Provenance is descriptive audit metadata and is **not** part of `raw_fact_id`;
the id is pure content. The `transformation_version_id` records *which parser*
produced the record so a re-derivation under a changed parser is attributable.

## 7. Loss-preserving guarantees (the invariants)

- **nil ≠ zero.** A fact with `xsi:nil="true"` sets `is_nil = True`,
  `value_raw = None`, `value_numeric = None`. It is never coerced to `0`. A
  concept that is simply *absent* produces no fact at all — silence is not a nil.
- **Raw value always survives.** `value_raw` is the exact lexical string. The
  best-effort `value_numeric` (a `Decimal`, never a `float`) is populated only
  when the raw string parses safely and finitely; on any doubt it is `None` and
  the raw string is retained. `scale` is never applied to the value; `sign` is
  never folded in.
- **Precision metadata retained.** `decimals` (including `INF`) and `scale` are
  stored verbatim as strings.
- **Units never coerced.** An unknown or custom unit remains an uninterpreted set
  of measure QNames; it is never mapped to a canonical currency token.
- **Dimensions never discarded.** Every explicit and typed member is preserved
  and contributes to the deterministic hash.

## 8. Fail-closed behavior

The layer raises rather than fabricate financial data (requirement 12):

- Non-well-formed XML, an empty document, or a root that is not `{xbrli}xbrl`
  → `MalformedXbrlError`.
- A fact referencing an **undeclared context or unit** → `MalformedXbrlError`
  (we never invent the missing context/unit).
- A **duplicate context id** or **duplicate unit id** → `MalformedXbrlError`
  (references would be ambiguous).
- A context with no period, no entity, or no identifier scheme
  → `MalformedXbrlError`.
- A namespace **prefix rebound to a different URI** → `UnsupportedXbrlError`
  (global QName resolution would be ambiguous; we refuse to guess).
- A **typed member with other than exactly one child element**
  → `UnsupportedXbrlError`.

A malformed document never yields a partial `ParsedInstance` with fabricated
facts — the parse either produces the complete, faithful model or raises.

## 9. Security considerations

- **Source bytes are never mutated.** The parser receives bytes it only reads;
  the authoritative copy is the immutable Phase 1 blob. The raw source is always
  recoverable.
- **Entity-expansion defense.** Any `DOCTYPE`/DTD declaration is rejected
  (`UnsupportedXbrlError`) before parsing. Python's `xml.etree.ElementTree`
  expands internal general entities, which is the "billion laughs" /
  quadratic-blowup denial-of-service vector; a valid XBRL instance never carries
  a DTD, so rejecting one closes the vector without a custom parser and never
  refuses legitimate SEC data.
- **No network I/O.** Ingestion is fully offline; it consumes only
  already-acquired artifacts. Acquisition stays in Phase 1.
- **No secrets.** Nothing here reads or persists credentials; the recorded
  User-Agent in provenance is the public request identity, not a secret.
- **Deterministic, rebuildable derived state.** The derived store can be deleted
  and regenerated byte-for-byte, so a corrupted derived file is never
  authoritative.

## 10. Persistence

`RawXbrlStore` writes one deterministic JSON document per instance under
`raw_xbrl/sha256-<hex>.json`, named by `raw_document_id`. Contexts, units, and
facts are emitted in a stable sorted order (`sort_keys=True`, no wall-clock, no
iteration-order dependence), and writes are atomic (temp file + `fsync` +
`os.replace`). Re-parsing the same bytes overwrites idempotently with identical
content. The envelope records `raw_xbrl_format_version` (the on-disk container
version, distinct from the parser version) and the `transformation_version_id`.

## 11. Limitations (current parser version)

- Only standard XBRL **instance** documents are parsed. Linkbases (calculation,
  definition, label, presentation) and the taxonomy schema are acquired by
  Phase 1 but not interpreted here; concept/axis semantics they define are a
  later concern.
- Inline iXBRL is parsed via the SEC-extracted `*_htm.xml` instance, not by
  interpreting the inline HTML directly.
- A namespace prefix rebound to a different URI within one document is refused
  rather than resolved per-scope.
- Numeric parsing is intentionally conservative: values that do not parse as a
  finite `Decimal` (including `NaN`/`Infinity` lexical forms) leave
  `value_numeric = None` with the raw string preserved.

## 12. Testing

Unit tests cover contexts (instant/duration/forever, explicit/typed/multiple
dimensions, scenario), units (simple/divide/custom), facts (numeric,
non-numeric, nil, decimals incl. `INF`, scale, sign, custom concepts),
deterministic identity, malformed/unsupported inputs, provenance, the store
round-trip and byte-determinism, and offline ingestion from stored artifacts.

A dedicated adversarial suite asserts **no information loss**: two facts
differing only by dimension, only by context, nil vs zero, only by decimals,
only by unit, the same concept across periods, and the same period across
filings are each kept distinct; a genuine duplicate is preserved via `ordinal`.
