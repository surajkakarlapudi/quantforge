# Public Availability & Point-in-Time (Phase 5)

The availability layer derives the fourth data-model state — *"available to a
hypothetical researcher"* (data-model §PA.1 state 4) — for each SEC filing, and
serves the two **knowledge-state** queries that state exists for: **point-in-time
(PIT)** ("what would a researcher have known as of instant *T*?") and **revised**
("what is the latest known value now, over a pinned snapshot?"). It is a *sidecar*
over the immutable Phase 4 canonical `Fact` records — it never rewrites them.

Package: `src/openfinance/availability/`.

This layer follows [docs/data-model.md](data-model.md) exactly — the availability
state and policy (§PA), the knowledge-state semantics (§KS), the point-in-time
predicate and selection order (§6.1, §6.3), the timezone rule (§6.4), the
versioned policy and dataset manifest (§9), and the fail-closed / determinism
invariants (§12, invariants 6–17, 22a, 27–30). Section references below point
into the data model.

> **This layer decides *availability*, never *truth*.** It computes a conservative,
> defensible estimate of when a filing became public from immutable evidence under
> a *versioned, replaceable policy* — and when the evidence cannot defend a
> timestamp it returns `UNKNOWN` and excludes the filing from research rather than
> guess. It never resolves which restatement is "correct"; it only orders what was
> knowable when. It loses nothing and it never mutates a canonical Fact.

---

## 1. Purpose

The layer answers two questions over one filer's canonical facts:

> **PIT** — given an observation key and a historical instant *T*, which single
> Fact would a researcher, restricted to filings public by *T*, have seen?
>
> **REVISED** — over a pinned `DatasetVersion`, what is the latest known Fact for
> that observation key today?

Both are the *same* §6.3 selection; they differ only in the `as_of` boundary
(§KS.1). The API makes them **impossible to confuse** (see §5).

It produces, per filing, one **`FilingAvailability`** triple —
`(derived_public_availability_timestamp, availability_status,
availability_policy_id)` — joined to *every* Fact of that filing at query time
(invariant 17), never copied onto the Fact rows.

It is **derived state**. A policy change re-derives a *new* availability record
under a new `availability_policy_id`; the canonical fact store is untouched
(Decision 3). It can be deleted and rebuilt to byte-identical output.

Explicitly out of scope: factor construction, backtesting, portfolio
construction, and any investment recommendation (data-model §22).

## 2. Relationship to Phases 1–4

There is no second HTTP client and no second storage system (requirement 18). The
chain is:

```
SEC EVIDENCE → ACQUISITION → REGISTRY → RAW XBRL → CANONICAL → AVAILABILITY/PIT
   (SEC)        (Phase 1)    (Phase 2)  (Phase 3)  (Phase 4)      (Phase 5)
```

- **Phase 1** owns acquisition, the content-addressed `ArtifactStore`, and the
  `retrieved_at` of each artifact. Phase 5 joins `retrieved_at` **only** at
  derivation, as an upper bound on availability (invariant 11, Decision 1) — it
  never touches raw/canonical identity.
- **Phase 2** owns filing identity and the SEC-supplied `acceptanceDateTime`,
  `filingDate`, `reportDate`, and `form`. Phase 5 reads these as derivation
  evidence via the *same* `company_id` / `filing_id` functions.
- **Phase 4** owns the immutable canonical `Fact` (with `obs_key` + `filing_id`).
  Phase 5 reads those Facts read-only and joins availability by `filing_id`.
- **Phase 5** adds a small derived `AvailabilityStore` alongside — not inside —
  the earlier stores, mirroring the Phase 2 `RegistryStore` file layout. No
  database is introduced.

## 3. Architecture

Each concern is a separate module with a single responsibility.

| Module | Responsibility |
| --- | --- |
| `errors.py` | `AvailabilityError` → `PolicyConfigurationError`, `ModeError`, `AvailabilityConsistencyError`; the fail-closed vocabulary. |
| `calendar.py` | Self-contained deterministic US-Eastern DST + federal-holiday business calendar (no `zoneinfo`/`tzdata`). |
| `timestamps.py` | Aware-UTC parse/format choke point; a naive `as_of` is rejected (§6.4, invariant 15). |
| `version.py` | `AvailabilityPolicy` + `AvailabilityRule` (versioned, form-scoped, era-bounded rule as *declarative data*); `DatasetVersion` (Merkle-root snapshot manifest); `edgar_std_v1()`. |
| `model.py` | `AvailabilityStatus`, `FilingEvidence` (derivation inputs), `FilingAvailability` (the derived triple + evidence + deciding policy). |
| `policy.py` | `select_policy` + `derive` — the pure, deterministic deriver (§PA.2, §PA.3). |
| `store.py` | `AvailabilityStore` — deterministic sidecar storage, one file per filer, keyed by `filing_id` (Decision 3). |
| `resolve.py` | `PointInTimeResolver` + the distinct `PitValue` / `RevisedValue` result types (§KS, invariants 27–30). |
| `ingest.py` | `AvailabilityIngestor` — the façade composing Phases 1/2/4 with derive + store + resolve. |

Data flow for one filer:

```
FilingRegistry.list_filings(cik)  +  ArtifactStore retrieved_at   (evidence assembly)
        │
        ▼
derive(evidence, policies) → FilingAvailability     (offline, deterministic, fail-closed)
        │
        ▼
AvailabilityStore.write_company(...)                (sidecar, keyed by filing_id)
        │
        ▼
PointInTimeResolver(canonical facts, availability)  → PitValue | RevisedValue
```

## 4. Deriving availability (§PA.2, §PA.3)

`derive(evidence, policies)` turns one filing's immutable evidence into a
`FilingAvailability` triple. It is a **pure function** — no wall-clock read, no
RNG, no dependence on iteration order (invariant 13).

### 4.1 Policy selection (exactly one, or fail closed)

A policy governs a filing when the filing's `form` is in the policy `form_scope`
(or the scope is the `"*"` wildcard) **and** the acceptance date falls in
`[effective_from, effective_to)`. **Exactly one** active/provisional policy must
match; two overlapping scopes are a `PolicyConfigurationError` — we never
arbitrate between policies (fail closed). No matching policy (e.g. a pre-era
filing) yields `UNKNOWN`.

### 4.2 The `edgar-std/v1` rule (recon §15)

The initial policy encodes the reconnaissance-observed dissemination convention as
a conservative **derived** estimate:

- Convert the acceptance instant (stored as-supplied UTC, never converted on
  ingest — §6.4) to US-Eastern wall-clock **inside the policy calendar**.
- If acceptance is on a business day at/before the **17:30 ET** cutoff,
  availability is that day's cutoff instant; otherwise it rolls to the **next US
  business day's** cutoff instant. Rounding to the cutoff (never earlier)
  implements §PA.3's "round later on uncertainty."
- **Floor at acceptance** (invariant 10 — availability never precedes acceptance;
  `filing_date` is *never* used as a lower bound).
- **Cap at `retrieved_at`** (invariant 11 — availability never exceeds when we
  actually retrieved the artifact). If even acceptance follows retrieval the
  evidence is inconsistent → `UNKNOWN`.

### 4.3 Availability status (the fail-closed valve)

- **`derived`** — computed from acceptance + a policy rule (conservative). The
  only positive status the initial policy produces.
- **`unknown`** — the policy cannot defend a reliable timestamp (missing /
  unparseable / pre-era acceptance, or inconsistent retrieval evidence). Carries
  **no** timestamp and **no** policy id (invariant 12) and is **never**
  PIT-eligible (invariant 9). We never fall back to `filing_date`.
- **`verified`** — requires *direct* dissemination/index evidence and a policy
  that trusts it. **The initial policy never produces `verified`** (Decision 4):
  `dissemination_evidence_trusted = False`, so that branch is dormant until real
  dissemination evidence and a validated successor policy version exist.

### 4.4 The self-contained Eastern calendar (why no `zoneinfo`)

Determinism and reproducibility (invariants 13, 21) forbid depending on a value
that varies by machine. The IANA tz database is **not present on every platform**
(notably a bare Windows install — no `tzdata` wheel is a runtime dependency of
this zero-dependency project), and its version drifts. So `calendar.py` encodes
the **post-Energy-Policy-Act (2007) US-Eastern DST rule** directly (DST from the
2nd Sunday of March to the 1st Sunday of November, EDT = UTC−4, EST = UTC−5) plus
the US federal-holiday rules EDGAR observes (weekend observance; Juneteenth from
2021). This is safe **because the policy is era-bounded**: `edgar-std/v1` sets
`effective_from = 2009` (the XBRL era, well after the 2007 regime change), so the
calendar is only ever applied where it is exactly correct. A pre-2007 era would
require a *different* policy version with a *different* calendar (invariant 14),
never a mutation of this one.

## 5. PIT vs REVISED — impossible to confuse (§KS, invariants 27–30)

The central safety requirement: a factor engine or backtest typed to PIT history
must be **structurally unable** to consume revised history.

- **No default mode (invariant 27).** There is no `get_value()`. The caller must
  call `knowledge_state_as_of(obs_key, as_of)` (PIT) or `revised_truth(obs_key,
  dataset_version)` (REVISED). Each requires its own explicit argument.
- **Distinct result types (invariant 28).** `PitValue` and `RevisedValue` are
  unrelated frozen dataclasses. A `RevisedValue` can never be passed where a
  `PitValue` is expected. The *only* bridge is the explicit, auditable
  `RevisedValue.reinterpret_as_pit(resolver, as_of)`, which **re-runs** the PIT
  resolution at `as_of` (it does not reuse the revised winner) — so every crossing
  from revised to PIT is a visible, intentional call.
- **Naive `as_of` rejected (invariant 15).** A timezone-naive PIT `as_of` raises
  `ModeError` — an ambiguous boundary is a look-ahead risk.
- **REVISED is reproducible, not wall-clock (invariants 21, 30).** `revised_truth`
  resolves at the **ingestion frontier** — the maximum eligible availability
  instant present in the pinned fact set — a deterministic stand-in for "now" that
  reproduces exactly for a pinned `DatasetVersion`.

### 5.1 The §6.1 eligibility gate (fail closed)

An observation is PIT-eligible iff **(A)** its status ∈ {`verified`, `derived`}
(never `unknown`), **(B)** it has a known availability timestamp, and **(C)** that
timestamp `<= as_of`. A fact whose filing has no availability record is treated as
`unknown` and excluded. Only the explicit `all_observations(...,
include_unknown_availability=True)` **audit** path (never a research path) can
surface ineligible observations.

### 5.2 The §6.3 selection (a strict total order, invariant 16)

Among eligible observations the winner is chosen by, in order: **availability
descending → acceptance descending → amendment (`/A`) outranks base form →
accession descending**. This is a strict total order, so the winner is
deterministic.

### 5.3 Worked example (§KS.3)

FY2019 revenue reported as $100M by the original 10-K (available 2020-03-01) and
restated to $80M by an amendment (available 2022-05-01), sharing one `obs_key`:

| Query | Result |
| --- | --- |
| `PIT(2021-01-01)` | **$100M** — only the original is available yet |
| `PIT(2023-01-01)` | **$80M** — the restatement is now available and outranks it |
| `REVISED(snapshot)` | **$80M** — latest known at the ingestion frontier |

`PIT(2021)` is unchanged whether or not the 2022 restatement exists in the store
(PIT is past-closed), and the eligible set only grows as `as_of` advances
(monotonicity, invariant 29).

## 6. Versioning & reproducibility (§9)

- **`AvailabilityPolicy`** is immutable and content-addressed:
  `availability_policy_id = sha256(policy_id, policy_version,
  rule_definition_hash)`. The rule is *declarative data* (`AvailabilityRule`), so
  any change to the rule necessarily yields a new id — a policy is **never mutated
  in place** (invariant 14). Re-declaring the identical policy reproduces the same
  id (invariant 20). `edgar-std/v1` is `provisional` / `unvalidated` (Decision 2).
- **`DatasetVersion`** pins a `REVISED` answer: its `dataset_version_id` is a
  Merkle root over the transformation version + the sorted availability-policy
  set + sorted raw-document ids + sorted fact ids. Order-independent but sensitive
  to any content change (invariant 19), so a snapshot cannot be mutated without
  changing its identity.

## 7. Persistence

`AvailabilityStore` writes one deterministic JSON document per filer under
`availability/cik-<zero-padded-cik>.json`, mirroring the Phase 2 `RegistryStore`
layout so registry and availability files align 1:1 by `company_id`. Records are
emitted **sorted by `filing_id`** with `sort_keys=True` (no wall-clock, no
iteration-order dependence); the applied policy-id set is stored (sorted) so the
file self-describes which policy versions produced it. Writes are atomic (temp
file + `fsync` + `os.replace`). The envelope records `availability_format_version`
(the on-disk container version, distinct from any policy version). It is derived
state — safe to delete and regenerate byte-for-byte.

## 8. `retrieved_at` — used, never propagated (Decision 1)

`retrieved_at` is joined **only** during availability derivation, as an upper
bound on availability (invariant 11). It is read from the Phase 1
`AcquisitionMetadata` in the façade (the earliest retrieval across a filing's
artifacts — the tightest true bound) and placed on `FilingEvidence`. It **never**
participates in raw identity, canonical identity, `obs_key`, `fact_id`, or any
deterministic content hash.

## 9. Fail-closed behavior

- Missing / unparseable / pre-era acceptance → `UNKNOWN` (never a `filing_date`
  fallback).
- Retrieval evidence inconsistent with the estimate (even acceptance follows
  retrieval) → `UNKNOWN`.
- Two overlapping active/provisional policy scopes → `PolicyConfigurationError`.
- An unimplemented `rule_kind` → `PolicyConfigurationError` (we never guess a
  rule's intent).
- A naive PIT `as_of` → `ModeError`.
- `unknown` availability is **never** PIT-eligible; a fact with no availability
  record is excluded from every research path.

## 10. Security considerations

- **Raw and canonical source are never rewritten.** The Phase 4 fact store is
  read-only here and the Phase 1 blobs are never touched. A policy change produces
  a *new* availability record; canonical Facts are immutable (Decision 3).
- **No network I/O.** Derivation and resolution are fully offline.
- **No wall-clock in identity or in REVISED.** Policy ids, dataset-version ids, and
  the `REVISED` ingestion frontier are pure functions of content — deterministic
  and reproducible across machines.
- **Fail closed, never invent.** `UNKNOWN` (and exclusion from research) is always
  preferable to a guessed availability.
- **PIT integrity is structural.** The distinct result types make an accidental
  look-ahead (consuming revised history as PIT) a type error, not a silent bug.

## 11. Testing

Per-module unit tests cover: the self-contained calendar (DST transition
boundaries across years, ET offsets, the UTC↔ET round trip, business-day/holiday
logic incl. Juneteenth-2021 and weekend observance); the deriver (cutoff /
next-business-day / weekend / winter-vs-summer offset, invariants 10 & 11,
determinism, fail-closed on missing/unparseable/pre-era acceptance, and Decision 4
— never `verified` under the initial policy, with a successor-policy test proving
the `verified` machinery exists but is policy-gated); policy selection
(exactly-one, no-match, overlap error, unsupported rule kind, form-scope
exclusion); the model's invariant-12 `__post_init__`; versioning (policy-id and
Merkle-root determinism and sensitivity); the store round-trip and byte-identical
determinism regardless of input order; the aware-UTC timestamp choke point; and
the façade's `retrieved_at` join + resolver construction.

The **resolver adversarial suite** encodes the §KS.3 worked example
($100M→$80M), the fail-closed gate (an `unknown` restatement never supersedes the
base; a fact without an availability record is excluded; the opt-in audit path),
monotonicity (invariant 29), the §6.3 total-order tiebreaks (amendment outranks
base; later availability outranks the amendment flag; accession-descending final
tiebreak), and the mode separation (naive `as_of` rejected; `PitValue` vs
`RevisedValue` are distinct types; `reinterpret_as_pit` re-resolves rather than
reusing the revised winner).

## 12. Live validation

`live_availability_validation.py` (run **outside** the repo, fully offline) builds
the registry from stored submissions artifacts, derives availability, and resolves
PIT/REVISED for Apple (320193), Tesla (1318605), and Berkshire (1067983) — 3,001
filings. It confirms on real data: every derived availability ≥ acceptance and ≤
retrieval; status is only `derived`/`unknown`, never `verified`; the sidecar
store round-trips and derivation is byte-deterministic; PIT and REVISED return
distinct types; the eligible set is monotone in `as_of`; and every canonical fact
(1,042 / 1,618 / 3,224 obs_keys) joins to an availability record and resolves to a
known PIT value.
