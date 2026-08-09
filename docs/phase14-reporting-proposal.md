# Phase 14 — Research Reporting & Explainability (PROPOSAL)

> **Status:** Proposal for review. **No implementation exists.** No source or tests have
> been modified. Nothing has been committed or pushed. The sole deliverable of this phase
> gate is this document. Decisions **D1–D10** below are *recommendations*; a `-locked`
> normative document (matching the Phase 10/11/13 precedent) is written only after the
> user approves the decisions.
>
> **One-line thesis:** Phase 14 turns QuantForge's already-sealed research artifacts into a
> single, content-addressed, deterministic, human-explainable **`ResearchReport`** — a thin
> *manifest of references* to sealed `ResearchRecord`s plus the reporting intent, persisted
> write-once to the existing sidecar, and rendered to human-readable form by a *separate*
> renderer that never touches research identity. It reuses every existing store, identity,
> and PIT invariant; adds no new source layer, no database, and no runtime dependency.

---

## 1. Phase objective

Phase 14 is **Research Reporting & Explainability**: a reproducible reporting layer that sits
strictly **above** Phase 13 and is a **pure consumer** of already-created, sealed research
artifacts (`BacktestResult`, `ExperimentResult`, and the derived `BacktestComparison`). Its job
is to transform those artifacts into a structured, machine-readable, content-addressed
**research report** that can *explain* a piece of research — what was researched, what data and
PIT boundaries were used, which dataset versions were pinned, which universe/strategy/experiment
spec drove it, which backtests ran, which statistics were produced, how results were compared,
what provenance supports them, what corporate actions applied, what values were undefined, what
fail-closed conditions occurred, which engine versions produced the artifacts, and exactly how
the research can be reproduced.

Phase 14 is emphatically **not** a second backtesting engine, analytics engine, statistics
engine, or data-processing layer. It computes no new financial number. It reads what lower
phases already sealed, pins *which* artifacts a report is about (by id **and** content hash),
records the *reporting intent* (e.g. "rank these children by Sharpe, descending"), and produces
a canonical artifact from which any number of presentations (Markdown, HTML, PDF, a future web
UI, an API response) can be rendered **without changing research semantics**.

---

## 2. Current architecture context

Phases 1–13 are implemented, stdlib-only, deterministic, and content-addressed. The facts that
govern this design (verified by reading the source, not the roadmap):

**Identity discipline (uniform across every layer).** `sha256_hex(data: bytes) -> str` from
`quantforge.sec.artifacts` is the one hash primitive. Content-hash ids are
`f"sha256:{sha256_hex(payload.encode('utf-8'))}"` (the `sha256:` prefix *is* part of the id).
Canonical JSON is `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",",":"))`.
Composite ids are NUL-joined (`_SEP = "\x00"`). Each layer folds material inputs under a **fresh
domain tag** (`experiment/1`, `sweep-axis/1`, `backtest-comparison/1`, …) so ids can never
collide across layers. A *version id* for a layer that does no numeric derivation is just the
`sha256` of its domain tag alone (the experiment layer's `experiment_engine_version_id()`
pattern); a layer that pins a decimal context folds `config_hash = sha256("prec=..\x00round=..")`
(the backtest/metric `*EngineVersion` dataclass pattern). Ids never depend on wall-clock, RNG,
`id()`, or iteration order.

**The reuse surface — `ResearchRecord` + `ResearchResultStore` (`factors/store.py`).**
`ResearchRecord` is a `@runtime_checkable` Protocol: a `research_result_id: str` property plus a
deterministic `to_dict() -> dict[str, object]`. `ResearchResultStore` writes one file per record
at `<root>/research/sha256-<hex>.json`, **write-once** (a differing payload under an existing id
raises `FactorConsistencyError`), atomically (tmp + fsync + `os.replace`), serialized with
`json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)` inside a container
`{"research_result_format_version": 1, "research_result": result.to_dict()}`. It depends only on
the Protocol — **not** on any concrete class — so a new record type persists with **no new
store**. Generic reader `read_as(id, from_dict)`; existence check `has(id)`.

**The records a report will reference (all `ResearchRecord`s, all with `from_dict`, byte-identical
round-trip — Phase 13 D3):**

| Record | `research_result_id` | Corpus / version pins it carries |
|---|---|---|
| `factors.ResearchResult` | stored field | `dataset_version_id`, `metric_engine_version_id` (= `factor_version`) |
| `panel.PanelResearchResult` | property → `panel_id` | `dataset_version_id`, `metric_engine_version_id` |
| `backtest.BacktestResult` | property → `backtest_id` | `dataset_version_id`, `market_dataset_version_id`, `backtest_engine_version_id`, `strategy_version`, `cost_model_id`, `accounting_version_id`, `schedule_id` |
| `experiment.ExperimentResult` | property → `experiment_result_id` (sha256) | `experiment_engine_version_id`, `dataset_version_id`, `market_dataset_version_id`; a pointer-only ledger of child `backtest_id`s |

**The one derived artifact that is NOT a persisted record — `BacktestComparison`
(`experiment/analysis.py`).** It has `comparison_id` + `comparison_version_id`, a `to_dict`, and
`pin_mismatch`, but **no `research_result_id` and no `from_dict`**, and it is never written to the
sidecar. It is a *pure deterministic function* of already-sealed backtests + `(statistic, order)`:
`comparison_id` folds `comparison_version_id`, `statistic_key`, `order`, and the sorted member
`backtest_id`s. This shapes D3/D7 below: a report references a comparison by recording its
*inputs* (which is exactly what `comparison_id` already addresses), and a reader **recomputes** it
deterministically from the sidecar — Phase 14 does **not** persist it and does **not** add a store.

**Provenance & UNDEFINED (already first-class in the referenced records).** Every result carries a
`provenance`/summary field for both `KNOWN` and `UNDEFINED` outcomes (zero information loss).
Missingness is never `None`/exception at the value level: `MetricStatus.UNDEFINED` +
`UndefinedReason` (`MISSING_INPUT`, `NIL_INPUT`, `DIVIDE_BY_ZERO`, …), rolled up as
`{reason: count}` maps (`FactorStatus.undefined_by_reason`, `PanelStatus.undefined_by_reason`). In
a backtest ledger, fail-closed data conditions are recorded string flags (`Fill.status="unfilled"`
+ `reason`, `AppliedAction.unrecognized=True`), never guessed. A comparison surfaces its own
conditions as `excluded: (backtest_id, reason)` and `pin_mismatch: bool | None`. Configuration /
consistency **defects** raise; data **conditions** are recorded. There is no first-class "warning"
type anywhere — conditions are either *recorded values* or *raised defects*.

**PIT vs REVISED (type-separation, data-model §KS).** PIT and REVISED are **distinct frozen
types** (`PitValue`/`RevisedValue`, `PitPanel`/`RevisedPanel`, `PitPrice`/`RevisedPrice`, …), not a
flag, and are deliberately non-substitutable (invariant 28). Backtests are **PIT-only**: the
engine consumes the PIT-only `PitPriceSeries` hand-off; there is deliberately no `RevisedBacktest`
and no `RevisedPriceSeries`. So `BacktestResult`, `ExperimentResult`, and `BacktestComparison` are
inherently PIT.

**Composition root — `Workspace` (`workspace.py`).** Engines are reached via lazy, cycle-free
`@property`s that lazy-import inside the method body and cache once. `research_result_store` is
rooted at `self._availability_store.root.parent` → `<root>/research/`. The top-level `__init__.py`
re-exports declarative **spec** types and sealed **result** types (and `Workspace`), but **not**
the engines (`ExperimentEngine`, `BacktestEngine` are reached via the workspace).

**Structural template — `docs/phase13-comparative-research-locked.md`.** The exact discipline to
mirror: versioned immutable request object → fail-closed engine reached from `Workspace` via a
lazy cycle-free `@property` → distinct result types → content-addressed identity with fresh domain
tags → data conditions recorded as first-class values, defects raised → compute-on-demand with the
shared write-once sidecar. (Note for the record: the user's reading list named
`docs/phase12-backtesting-locked.md`, but no locked doc exists for Phase 12 — only
`docs/phase12-backtesting-proposal.md`. Phases 10, 11, and 13 do have `-locked.md` docs. Phase 12
was read from its proposal + source.)

---

## 3. Contradiction analysis

Every existing invariant, checked against this proposal. **If any proposal weakened an invariant,
it is rejected and redesigned; none below do.**

1. **No look-ahead / PIT integrity (Eng. Principle 4, invariant BT-2).** A report performs *no
   resolution* and takes *no `as_of`*. It references records that were already sealed PIT-correctly.
   It cannot introduce look-ahead because it computes nothing over historical data. **No conflict.**
2. **PIT vs REVISED separation (data-model §KS, invariants 27–28).** V1 report scope is
   backtest/experiment, which are PIT-only by construction; the report records a `boundary_kind`
   and never presents a REVISED artifact as PIT. A future REVISED-panel report must be a distinct,
   explicitly-labeled scope (§12, §26). **No conflict; the type separation is preserved and the
   fail-closed labeling is added.**
3. **Immutable raw data / no rewrite of a `Fact` (Eng. Principle 2).** The report is additive and
   read-only over sealed artifacts. It writes only a new `<root>/research/…json` file. **No conflict.**
4. **Content-addressed identity (data-model §11).** The report is content-addressed with a fresh
   domain tag; `report_id` is a pure function of the reporting request + the referenced content
   hashes. **No conflict; it *extends* the discipline.**
5. **Deterministic serialization / byte-identical round-trip.** The report implements `to_dict` /
   `from_dict` with a byte-identical round-trip test, exactly as `ExperimentResult`. **No conflict.**
6. **Write-once storage (`FactorConsistencyError` guard).** The report persists via the existing
   store; an identical rebuild is a byte-identical no-op; a differing payload under the same id
   fails closed. **No conflict; it *relies on* the guarantee.**
7. **`ResearchRecord` semantics.** The report satisfies the Protocol (`research_result_id` +
   `to_dict`). This is precisely the extension point the Protocol was designed for. **No conflict.**
8. **`DatasetVersion` / `MarketDatasetVersion` pinning; `backtest_id`/`experiment_id` determinism;
   `result_hash` semantics.** The report *references* these ids and folds each referenced record's
   `result_hash` (or `comparison_id`) into its own `result_hash`, so a report's identity is
   sensitive to any change in any artifact it reports on — honestly. It never recomputes or
   re-defines them. **No conflict.**
9. **Phase 13 comparison semantics.** `BacktestComparison` stays a pure, non-persisted, derived
   view. The report records its *inputs* (member ids + `statistic` + `order` + `comparison_version_id`
   → i.e. `comparison_id`); a reader recomputes it deterministically. Phase 14 does **not** turn it
   into a stored record and does **not** edit `analysis.py`. **No conflict; no scope creep.**
10. **`strategy_version`, corporate-action provenance, `UNDEFINED` semantics, fail-closed behavior.**
    All of these live in the referenced records and are surfaced *by reference* — the report copies
    no ledger, fabricates no value, and adds no new UNDEFINED semantics. **No conflict.**
11. **Zero runtime deps / no database (Eng. Principle 10; Tech notes).** The report uses only
    `hashlib`/`json`/`dataclasses` and the existing store. **No conflict.**
12. **Provenance preservation (Eng. Principle 3).** Because the report pins each referenced record
    by `(id, content_hash)`, and every referenced record already carries the full lineage to raw
    source, the report preserves *complete* provenance by reference without duplicating (and thus
    without risking divergence from) it. **No conflict; this is strictly stronger than embedding.**

**One tension surfaced and resolved (not a contradiction):** a report should be *human-explainable*,
which pulls toward embedding rich content; but *identity stability* and *provenance non-duplication*
pull toward reference-only. The resolution (D3, D6, §10) is the content/presentation split: the
**canonical model is reference-only**; a **separate renderer** resolves references from the store
and produces the rich human artifact. Presentation richness lives in the renderer, not in identity.

---

## 4. Problem statement

QuantForge can *produce* reproducible research (sealed backtests, experiments, comparisons) but has
no artifact that *explains* a piece of research as a coherent whole. Today a human must manually
assemble: which experiment, which children, which statistic ranked them, which corpus was pinned,
what was undefined, how to reproduce it. That assembly is ad hoc, non-reproducible, and not
content-addressed — the antithesis of the rest of the system.

Phase 14 must provide a **single canonical artifact** that (a) names exactly which sealed artifacts
a report is about, (b) records the reporting intent, (c) is itself content-addressed, immutable,
deterministic, and write-once, (d) preserves full provenance by reference, (e) never fabricates or
recomputes a financial number, (f) can be rebuilt byte-for-byte on any machine, and (g) can be
rendered to any presentation without changing (d)–(f). The problem is *organization and
explainability under the existing invariants* — not new computation.

---

## 5. Design goals

- **G1 — Pure consumer.** Reference already-sealed artifacts; compute no new financial value.
- **G2 — Content-addressed identity.** `report_id` is a pure function of the reporting request +
  referenced content hashes, under a fresh domain tag.
- **G3 — Content/presentation separation.** The canonical model holds *content* (references,
  reporting intent, boundary); *presentation* (titles, ordering-for-display, prose, Markdown/HTML)
  lives in a renderer and **never** affects `report_id`.
- **G4 — Reuse everything.** Same `ResearchRecord` Protocol, same write-once sidecar, same identity
  primitives, same fail-closed split. No new store, no database, no runtime dependency.
- **G5 — Provenance by reference, not by copy.** Pin each artifact by `(id, content_hash)`; never
  duplicate its ledger (duplication invites divergence).
- **G6 — Determinism & byte-for-byte rebuildability.** Same references + same intent → identical
  `report_id` and `to_dict` on any machine; idempotent write-once; no wall-clock, no RNG.
- **G7 — Fail closed.** A reference that cannot be resolved from the sidecar, or whose content hash
  no longer matches, is a defect and **raises** — never a partial or silently-stale report.
- **G8 — Honest surfacing.** Undefined counts, excluded members, `pin_mismatch`, unrecognized
  corporate actions, and unfilled orders are surfaced *by reading the sealed summaries*, never
  fabricated and never hidden.
- **G9 — Explicit, minimal public API.** Declarative `ReportSpecification` → `ReportEngine.build`
  → sealed `ResearchReport`; a pure `render(...)` function. Small, closed v1 scope vocabulary.
- **G10 — UI-ready without UI.** Establish the canonical artifact so a future UI is a *pure
  consumer* of it; build no UI in Phase 14.

---

## 6. Non-goals (explicitly rejected scope)

Phase 14 will **not** deliver, and this proposal explicitly rejects: a web UI, any frontend
framework, authentication, hosted SaaS, user accounts, cloud deployment, dashboards; portfolio
construction, live trading, order routing, recommendations, or investment advice; arbitrary
Python/callback strategy execution; market-data or filing ingestion/connectors; any new
statistical, analytics, or backtesting engine; any new financial computation; any new persisted
record type for comparisons; any edit that changes the identity of an existing record; PDF/HTML/web
rendering (deferred — §19, §26); and any database or new store.

---

## 7. Proposed architecture

A thin reporting layer strictly above Phase 13, following the exact extension recipe of every prior
phase.

```
                 ReportSpecification              (declarative reporting request, content-addressed)
                          |
                          v
     Workspace.report_engine  --->  ReportEngine.build(spec)
                          |                 |
                          |   resolve & verify each referenced id from the shared sidecar
                          |   (fail closed if absent; verify content_hash matches — G7)
                          v                 v
                 ResearchReport (sealed ResearchRecord) --> ResearchResultStore (existing sidecar)
                          |
             +------------+-------------------------------+
             v                                            v
   render(report, store) -> str                 store.read_as(id, ResearchReport.from_dict)
   (deterministic Markdown; PURE FUNCTION;       (first-class typed object, byte-identical round-trip)
    NOT stored, NOT identity-bearing)
```

**New package `src/quantforge/report/`:**

- `errors.py` — `ReportError` → `ReportConfigurationError`, `ReportConsistencyError` (mirrors
  `experiment/errors.py`).
- `identity.py` — `report_reference_digest`, `report_result_hash`, `report_id`, `report_result_id`,
  plus `report_engine_version_id()`. Fresh domain tags `report/1`, `report-reference/1`,
  `report-engine/1`.
- `spec.py` — `ReportSpecification`, `ReportReference` request descriptors, the closed v1 scope
  vocabulary, full construction-time validation.
- `result.py` — `ResearchReport` (a `ResearchRecord` with `from_dict`) + `ReportReference` (sealed).
- `engine.py` — `ReportEngine` (constructed from `Workspace`; composes `research_result_store`):
  resolve → verify → seal → write-once.
- `render.py` — `render_markdown(report, store) -> str`: the single reference renderer, a pure,
  deterministic function that resolves references and formats them; **not** a record, **not** stored.
- `__init__.py` — package exports.

**The only edits to existing source** (all additive, none altering any existing identity):

1. `workspace.py` — one lazy `report_engine` `@property` (+ its `self._report_engine = None` cache
   line), following the `experiment_engine` template verbatim.
2. `src/quantforge/__init__.py` — top-level re-exports of `ResearchReport`, `ReportSpecification`,
   `ReportReference` (spec + result types only; the engine is reached via `Workspace`), added
   alphabetically to the import block and `__all__`.

**No edit to** `backtest/*`, `experiment/*` (including `analysis.py`), `factors/store.py`, or any
identity/version module. `ResearchResultStore` already accepts any `ResearchRecord`, so the report
persists with no store change.

---

## 8. `ResearchReport` data model

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric (the report
carries **no** numeric fields of its own in v1 — it only references), no wall-clock, no RNG.

### 8.1 `ReportReference` (sealed)

```
ReportReference(
    kind: str,            # "backtest" | "experiment" | "comparison"  (closed v1 scope vocabulary)
    reference_id: str,    # backtest_id / experiment_result_id / comparison_id
    content_hash: str,    # the thing that changes iff the referenced content changes:
                          #   record  -> its result_hash
                          #   comparison -> its comparison_id (self-addressing: folds
                          #                 comparison_version_id + statistic + order + members)
    detail: dict[str, object] = {},   # reporting intent for a derived comparison ONLY:
                                      #   {"statistic": "sharpe", "order": "descending",
                                      #    "member_scope": "experiment_children",
                                      #    "comparison_version_id": "sha256:…"}
)
```

`to_dict` / `from_dict`, byte-identical round-trip. `detail` is empty for `backtest`/`experiment`
references; for a `comparison` it records exactly the inputs a reader needs to *recompute* the
comparison (D3, D7). `digest()` → the `(kind, reference_id, content_hash, canonical detail)`
fingerprint folded into `result_hash`.

### 8.2 `ResearchReport` (implements `ResearchRecord`)

```
ResearchReport(
    report_engine_version_id: str,
    report_spec: dict[str, object],    # the full ReportSpecification.to_dict() — reproducibility
    scope: str,                        # "backtest" | "experiment"  (top-level subject kind, v1)
    references: tuple[ReportReference, ...],   # ordered; the content-addressed pointers
    boundary_kind: str,                # "pit"  (v1 is PIT-only; see §12)
    result_hash: str,                  # canonical JSON over ordered ReportReference.digest()s
)

# derived, not stored as state:
report_id           property  -> sha256 over (report_spec identity + sorted reference digests)
report_result_id    property  -> sha256 over (report_id + engine_version_id + result_hash)
research_result_id  property  -> alias of report_result_id  (the ResearchRecord key)
```

- `to_dict()` keys (deterministic): `report_result_id`, `research_result_id` (alias so the generic
  reader keys correctly), `report_id`, `report_engine_version_id`, `report_spec`, `scope`,
  `references` (list of `ReportReference.to_dict()`), `boundary_kind`, `result_hash`.
- `from_dict` is the fail-closed inverse (`_req_str`/`_req_list`/`_req_dict` idioms from
  `experiment/result.py`); the two id aliases are re-derived by their properties, never read from
  state, so `from_dict(to_dict(r))` re-emits an identical `to_dict` and the same `result_hash`.
- `.seal(...)` classmethod is the identity-computing constructor (mirrors `ExperimentResult.seal`):
  it folds the ordered reference digests into `result_hash`, so identity is a pure function of the
  reporting request + referenced content and is never supplied by the caller.

**What the model deliberately does NOT hold:** section titles, headings, prose, display order,
Markdown/HTML, colors, chart specs, or any presentation. Those are the renderer's concern (§10,
§19). The model also does not embed any referenced record's body — it is pointer-only, exactly like
`ExperimentResult`'s run ledger.

### 8.3 `ReportSpecification` (declarative request; content-addressed; in `spec.py`)

```
ReportSpecification(
    name: str,                         # non-empty
    scope: str,                        # "backtest" | "experiment"
    subject_id: str,                   # the backtest_id or experiment_result_id being reported
    comparisons: tuple[ComparisonDirective, ...] = (),   # optional reporting intent:
                                       #   (statistic, order) over the subject's members
    spec_version: str = "report/1",
)
```

`ComparisonDirective(statistic: str, order: str)` — validated against `RANKABLE_STATISTICS` and
`{"descending","ascending"}` **at construction** (fail closed, reusing the same closed vocabulary
Phase 13 already defines; the report never invents a statistic). A `comparisons` directive is only
valid when `scope == "experiment"` (a single-backtest report has nothing to rank); otherwise
construction raises.

---

## 9. Identity model

Mirrors `experiment/identity.py` exactly, with fresh domain tags so a report id can never collide
with any lower layer. The report layer performs **no numeric derivation** (it only aggregates
already-sealed strings), so `report_engine_version_id()` folds only its domain tag — the experiment
pattern, not the decimal-context dataclass pattern.

```
report_engine_version_id() -> _sha256("report-engine/1")

report_reference_digest(kind, reference_id, content_hash, detail: dict) -> dict   # the sealed fingerprint

report_result_hash(ordered_reference_digests: list[dict]) -> str
    = _sha256(_canonical_json({"report-reference/1": ordered_reference_digests}))

report_id(*, name, spec_version, scope, subject_id, sorted_reference_descriptors, comparison_directives) -> str
    # folds name, spec_version, scope, subject_id, the sorted reference (kind,id) descriptors,
    # and the sorted comparison directives (statistic, order) — the REQUEST identity

report_result_id(*, report_id, report_engine_version_id, result_hash) -> str
    # the sidecar key: sha256 over the three, aliased to research_result_id
```

**What `report_id` / `report_result_id` fold (and therefore what changes identity):**
`report_engine_version_id` ✔, the report spec (name, scope, subject id, comparison directives) ✔,
every referenced record id ✔, and — via `result_hash` — every referenced record's `result_hash` /
`comparison_id` ✔. Consequently, a report's identity is sensitive to *any* change in *any* artifact
it reports on: change a dataset pin, a strategy, a cost model, or a single child backtest, and the
referenced record's id/`result_hash` changes, and the report id changes — honestly.

**What it does NOT fold (and therefore what leaves identity unchanged):** report *schema/format*
version (a container concern — see §14/§28 D-note), presentation config, section headings, display
ordering, renderer output, wall-clock, RNG, or object identity. This is the concrete realization of
"a heading change H2→H3 must not change `report_id`."

---

## 10. Content vs presentation boundary

This is the load-bearing design principle. The split is enforced *structurally*, not by convention:

- **Content (in `ResearchReport`, folded into `report_id`):** *which* artifacts (references by id +
  content hash), the *reporting intent* (scope, comparison directives), and the *boundary label*.
  This is everything whose change should change the research artifact.
- **Presentation (in `render.py`, NOT folded into anything):** section titles and order, headings,
  prose, tables vs prose, Markdown vs HTML vs PDF vs web, number formatting, chart choices. A
  presentation change produces different bytes *out of the renderer* but the **same** `report_id`
  and the **same** stored record.

**Do the ten candidate sections (Executive Summary, Research Definition, Dataset & PIT
Configuration, Universe, Strategy, Backtest Results, Experiment Comparison, Provenance,
Warnings/Undefined Data, Reproduction Information) belong in the model?** **No — they belong in the
renderer.** Each is a *presentation* of facts that already live in the referenced sealed records.
The renderer resolves the references from the store and derives every section from the sealed
`to_dict()`s:

| Rendered section | Sourced (by reference) from |
|---|---|
| Executive Summary | scope + subject id + best comparison entry (recomputed) |
| Research Definition | `report_spec` (name, scope) + the subject's `base_backtest_request` / strategy_version |
| Dataset & PIT Configuration | subject's `dataset_version_id`, `market_dataset_version_id`, `boundary_kind` |
| Universe | subject's `universe_id` (+ `Universe.describe()` if resolvable) |
| Strategy | subject's `strategy_version`, `cost_model_id`, `schedule_id`, `accounting_version_id` |
| Backtest Results | `BacktestResult.performance.statistics` (verbatim decimal strings) |
| Experiment Comparison | recomputed `BacktestComparison` from the `comparison` reference `detail` |
| Provenance | the version-id chain on each referenced record (down to raw source) |
| Warnings / Undefined Data | `Fill.status="unfilled"` reasons, `AppliedAction.unrecognized`, `comparison.excluded`, `pin_mismatch`, any `undefined_by_reason` on referenced factor/panel records |
| Reproduction Information | `report_spec` + all referenced ids + engine version ids (§ below) |

The **section structure is a stable, documented renderer contract**, not model state. This keeps
`report_id` invariant under presentation edits while still guaranteeing a rich, explainable output.

---

## 11. Provenance model

**By reference, never by copy (G5).** The report pins each artifact by `(reference_id,
content_hash)`. Because every referenced `ResearchRecord` already carries its complete lineage —
`dataset_version_id` / `market_dataset_version_id` (→ raw document ids, fact ids, policy ids),
`*_engine_version_id`, `strategy_version`, `cost_model_id`, per-rebalance `SignalRef` lineage,
`AppliedAction` corporate-action ids with `availability_timestamp`, and `PriceProvenance` down to
`selected_raw_document_sha256` — the report inherits *full* provenance simply by naming the record
and pinning its content hash. Copying that lineage into the report would risk divergence (two
sources of truth) and bloat identity; referencing it makes the report's provenance exactly as
strong as the source's, by construction.

The renderer's Provenance section walks the version-id chain of each resolved reference and prints
it; it invents nothing. The report's own provenance is: *this report is about exactly these
`(id, content_hash)` artifacts, produced by report engine version X, under boundary "pit".*

---

## 12. PIT / REVISED semantics

- V1 report scope (`backtest`, `experiment`) is **PIT-only** by construction: backtests consume the
  PIT-only `PitPriceSeries` hand-off; there is no `RevisedBacktest`. So a v1 `ResearchReport` carries
  `boundary_kind = "pit"`, and the renderer labels it as a point-in-time research report.
- The report **records `boundary_kind` explicitly** (no default, mirroring the "no default mode"
  invariant) and the renderer must display it. A report may never present REVISED data as PIT.
- **Can a report contain REVISED data?** Not in v1, because its referenced record types are PIT-only.
  If a *future* phase adds a report scope over `RevisedPanel`/`RevisedFactor`, it must be a **distinct
  scope** with `boundary_kind = "revised"`, must record the `dataset_version_id` the REVISED view was
  pinned to, and the renderer must label every REVISED figure as such — never commingled with PIT
  figures in a way that lets one substitute for the other (data-model §KS.5, invariant 28). Phase 14
  fails closed if a reference's implied boundary disagrees with the report's declared `boundary_kind`.

---

## 13. Referencing existing `ResearchRecord`s

- **Referenced, not embedded (D3).** The report stores only `(kind, reference_id, content_hash,
  detail)` per reference — never a copy of the referenced record's body/ledger. This mirrors
  `ExperimentResult`'s pointer-only run ledger.
- **Resolution & verification at build time (G7).** `ReportEngine.build` calls
  `store.read_as(reference_id, <Type>.from_dict)` for each `backtest`/`experiment` reference. A
  missing id → `ReportConsistencyError` (fail closed; we refuse to report on an artifact we cannot
  materialize). The engine recomputes each referenced record's `content_hash` from the freshly-read
  record and requires it to match what the spec/expansion implies; a mismatch → `ReportConsistencyError`
  (a report can never silently reference a drifted artifact).
- **Comparisons are referenced by intent and recomputed (D7).** A `comparison` reference carries the
  `detail` (`statistic`, `order`, `member_scope`, `comparison_version_id`); its `content_hash` is the
  `comparison_id` that already addresses exactly those inputs. At build the engine recomputes the
  `BacktestComparison` via `BacktestComparison.of_experiment(experiment, store, statistic=…, order=…)`
  and requires the resulting `comparison_id` to equal the reference's `content_hash` — so a stored
  report is verifiably about a specific, reproducible comparison **without persisting the comparison
  or editing `analysis.py`.** At render, the renderer recomputes it identically for display.
- **Referenced records read via `store.read_as(id, from_dict)`.** Every referenced record type has a
  byte-identical `from_dict` (Phase 13 D3), so resolution yields first-class typed objects.

---

## 14. Serialization format

- The **canonical machine-readable representation is a JSON dict** produced by `ResearchReport.to_dict`
  and consumed by `from_dict`, byte-identically round-tripping (proven by test) — identical in shape
  and discipline to every other record. This dict *is* the report; Markdown/HTML/PDF are renderings
  of it, not the artifact.
- Persisted through the existing store's container: `{"research_result_format_version": 1,
  "research_result": report.to_dict()}`, serialized deterministically with
  `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)` (the store owns this).
- A **report schema version** (`REPORT_RESULT_FORMAT_VERSION = "report-result/1"`, module constant,
  exactly like `EXPERIMENT_RESULT_FORMAT_VERSION`) documents the serialized meaning. Per §9 it is
  **not** folded into `report_id` (it is a container/format concern, not research content); bumping
  it is a future migration event. (See §28 D-note on the deliberate choice here.)

---

## 15. Persistence strategy

- **Reuse the existing `ResearchResultStore` sidecar (D-analogue of Phase 13 D4).** No new store, no
  database. The report is a `ResearchRecord`; `ResearchResultStore.write(report)` lands it at
  `<root>/research/sha256-<report_result_id-hex>.json`.
- **Write-once, idempotent.** Rebuilding an identical report is a byte-identical no-op write; a
  differing payload under the same id fails closed via the store's `FactorConsistencyError` guard.
- **Reached from the `Workspace`** via `workspace.research_result_store` (the engine composes it
  exactly as `ExperimentEngine` reaches it). Read back via `store.read_as(report_result_id,
  ResearchReport.from_dict)`.

---

## 16. Determinism strategy

- No wall-clock, no RNG, no `id()`, no set/dict-iteration dependence anywhere in a value or id
  (references are stored in a deterministic order; ids sort their inputs where set-semantics apply).
- Identity via the shared primitives (`sha256_hex`, NUL separator, canonical JSON) under fresh domain
  tags; the report folds no float — it references decimal strings and never arithmetic.
- **Byte-for-byte rebuildability:** given the same immutable sidecar and the same `ReportSpecification`,
  `ReportEngine.build` re-resolves the same references, recomputes the same content hashes, and seals
  a byte-identical `ResearchReport` on any machine. Recomputed comparisons are deterministic
  (`BacktestComparison` uses exact `Decimal` compare under the pinned prec-34 ROUND_HALF_EVEN context,
  tie-broken by `backtest_id`).

---

## 17. Failure / undefined / warning semantics

Follows the existing split exactly — **defects raise, conditions are recorded** — and adds no new
UNDEFINED semantics of its own.

**Raised** (`ReportConfigurationError` / `ReportConsistencyError`): empty `name`; unknown `scope`;
a `comparisons` directive when `scope != "experiment"`; a `statistic`/`order` outside the closed
vocabulary; a `subject_id` or referenced id absent from the sidecar; a referenced record whose
recomputed `content_hash` does not match; a referenced record whose implied boundary disagrees with
the declared `boundary_kind`.

**Recorded / surfaced (never raised, never fabricated), by reading the sealed summaries:** undefined
metric/panel cells (`undefined_by_reason`), unfilled orders (`Fill.status="unfilled"` + `reason`),
unrecognized corporate actions (`AppliedAction.unrecognized`), comparison members excluded for a
non-finite statistic (`comparison.excluded`), and corpus `pin_mismatch`. The report surfaces these
counts/flags *as read from the referenced records*; it invents no value and hides no condition.

**On "warnings":** consistent with the rest of the codebase, there is **no first-class warning
type**. A "Warnings / Undefined Data" *rendered section* is a presentation grouping of the recorded
conditions above; it is not model state.

---

## 18. Public API proposal

Minimal, explicit, mirroring the experiment layer.

```python
# src/quantforge/report/spec.py
class ComparisonDirective:  # frozen; validates statistic ∈ RANKABLE_STATISTICS, order ∈ {desc,asc}
    statistic: str
    order: str


class ReportSpecification:  # frozen; content-addressed; full construction-time validation
    name: str
    scope: str  # "backtest" | "experiment"
    subject_id: str
    comparisons: tuple[ComparisonDirective, ...] = ()
    spec_version: str = "report/1"

    def to_dict(self) -> dict[str, object]: ...


# src/quantforge/report/result.py
class ReportReference:  # frozen; to_dict/from_dict/digest
    kind: str
    reference_id: str
    content_hash: str
    detail: dict


class ResearchReport:  # frozen; implements ResearchRecord; from_dict; .seal(...)
    report_engine_version_id: str
    report_spec: dict
    scope: str
    references: tuple[ReportReference, ...]
    boundary_kind: str
    result_hash: str

    @property
    def report_id(self) -> str: ...
    @property
    def report_result_id(self) -> str: ...
    @property
    def research_result_id(self) -> str: ...  # alias of report_result_id
    def to_dict(self) -> dict[str, object]: ...
    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "ResearchReport": ...


# src/quantforge/report/engine.py
class ReportEngine:  # constructed from Workspace; composes research_result_store
    def __init__(
        self, workspace: Workspace, *, research_store: ResearchResultStore | None = None
    ) -> None: ...
    @property
    def report_engine_version_id(self) -> str: ...
    def build(
        self, spec: ReportSpecification
    ) -> ResearchReport: ...  # resolve → verify → seal → write-once


# src/quantforge/report/render.py
def render_markdown(
    report: ResearchReport, store: ResearchResultStore
) -> str: ...  # pure; not stored


# src/quantforge/workspace.py  (additive)
Workspace.report_engine  # lazy @property -> ReportEngine(self)

# src/quantforge/__init__.py  (additive re-exports)
(
    ResearchReport,
    ReportSpecification,
    ReportReference,
)  # spec + result types only; engine via Workspace
```

`Company` gains **no** Phase 14 method (the reporting layer is engine-/standalone-only, exactly as
the backtester, experiment layer, and universe matrix are — Phase 13 D6 precedent).

---

## 19. Rendering strategy

- Phase 14 ships **exactly one reference renderer**: `render_markdown(report, store) -> str`, a
  **pure, deterministic function** that resolves references from the store and formats the ten
  sections of §10. Its purpose is to *prove the content/presentation boundary*: it consumes the
  canonical artifact and produces human-readable text without any feedback into identity or storage.
- The renderer output is **not** a `ResearchRecord`, is **not** content-addressed, and is **not**
  written to the sidecar. Re-rendering the same report yields the same string (deterministic), but
  editing the renderer changes only its output — never `report_id`.
- **HTML, PDF, charts, and any web UI are deferred** (§26). Charts in particular require a rendering
  dependency and belong to a future presentation phase, never to the canonical model. Markdown was
  chosen for v1 because it is stdlib-only, diffable, and deterministic.

---

## 20. Future UI hand-off

The canonical `ResearchReport` (its `to_dict()` JSON) is the **stable contract** a future UI
consumes. A UI phase would: read a `ResearchReport` by id from the sidecar, resolve its references
(the UI is itself a *pure consumer*, exactly like `render_markdown`), and present them — with zero
changes to research semantics or identity. Future presentations (HTML export, PDF, an interactive
web UI, an API endpoint returning the report JSON) are all *additional renderers* over the same
artifact. Because presentation is structurally separated from content (§10), none of them can alter
`report_id`, the stored record, or any referenced artifact. The UI is explicitly **out of Phase 14**.

---

## 21. Decisions D1–D10

Each recommendation is what a `-locked` doc would commit **if approved**.

### D1 — Is a `ResearchReport` a `ResearchRecord` persisted to the existing sidecar?
- **Question:** Should the report be a first-class `ResearchRecord` in the existing write-once store,
  or a new artifact type/store?
- **Options:** (a) A `ResearchRecord` in the existing sidecar; (b) a new store/format; (c) a
  non-persisted, render-only object.
- **Recommendation:** **(a).** Implement the Protocol (`research_result_id` alias + deterministic
  `to_dict`/`from_dict`), persist write-once to `<root>/research/`.
- **Reason:** The Protocol is the designed extension point; the store already accepts any
  `ResearchRecord`; this gives immutability, content-addressing, and idempotent write-once for free
  (Phase 13 D4 precedent) with zero new infrastructure.
- **Consequence:** No new store, no database, no runtime dependency. A report is reproducible,
  addressable, and byte-identically rebuildable, and coexists with the artifacts it references in one
  sidecar.

### D2 — What does `report_id` fold (and what must it never fold)?
- **Question:** Which inputs are material to report identity?
- **Options:** (a) request + referenced content hashes only; (b) also fold presentation/format;
  (c) fold a wall-clock/build timestamp.
- **Recommendation:** **(a).** Fold `report_engine_version_id`, the report spec (name, scope,
  subject id, comparison directives), and `result_hash` over the ordered referenced content hashes.
  Never fold presentation, schema/format version, or time.
- **Reason:** Content = identity. A report must change id iff the research it reports on, or the
  reporting intent, changes — and must **not** change when a heading or renderer changes.
- **Consequence:** `report_id` is stable across presentation edits and sensitive to any change in any
  referenced artifact (via its `result_hash`/`comparison_id`). This directly realizes the
  content/presentation design principle.

### D3 — Embed referenced results, or reference them by id?
- **Question:** Should the report copy referenced record bodies, or store pointers?
- **Options:** (a) reference-only `(id, content_hash)`; (b) embed full `to_dict()` bodies; (c) hybrid
  (embed a summary, reference the rest).
- **Recommendation:** **(a)** reference-only, mirroring `ExperimentResult`'s run ledger.
- **Reason:** Referencing preserves *full* provenance without duplication (single source of truth,
  no divergence risk), keeps identity thin, and lets the renderer resolve on demand. Embedding would
  duplicate ledgers and risk two-sources-of-truth drift.
- **Consequence:** A reader/renderer must resolve references from the sidecar (fail closed if absent).
  The report is a thin, content-addressed manifest. Provenance is exactly as strong as the source's.

### D4 — Canonical representation and round-trip.
- **Question:** What is the canonical machine-readable form?
- **Options:** (a) JSON dict via `to_dict`/`from_dict` with byte-identical round-trip; (b) a bespoke
  binary/text format; (c) Markdown/HTML as the canonical form.
- **Recommendation:** **(a).** JSON dict, byte-identical round-trip (test-proven), inside the store's
  existing container.
- **Reason:** Uniform with every other record; deterministic; diffable; renderer-agnostic. Markdown
  as canonical would fuse content with presentation — rejected.
- **Consequence:** Markdown/HTML/PDF/UI are *renderings* of the JSON, never the artifact. `from_dict`
  yields a first-class typed object.

### D5 — How is a comparison referenced, given it is not a persisted record?
- **Question:** `BacktestComparison` has no `research_result_id`/`from_dict` and is never stored. How
  does a report reference it?
- **Options:** (a) reference by *intent* (`statistic`, `order`, member scope) with `content_hash =
  comparison_id`, and recompute deterministically on build/render; (b) make `BacktestComparison` a
  persisted `ResearchRecord` (edit `analysis.py`, add `from_dict`, write to sidecar); (c) embed the
  comparison `to_dict()` inline.
- **Recommendation:** **(a).**
- **Reason:** A comparison is a *pure deterministic function* of already-sealed backtests +
  `(statistic, order)`, and `comparison_id` already content-addresses exactly those inputs. Recompute
  is exact and cheap; (b) is scope creep that edits Phase 13 source and adds a stored record for a
  derived view; (c) embeds volatile derived content into identity/storage.
- **Consequence:** No edit to `experiment/analysis.py`; no new persisted record. The report is
  verifiably about a specific, reproducible comparison; the renderer recomputes it identically for
  display. The reporting intent (`statistic`, `order`) is folded into `report_id`.

### D6 — Does Phase 14 build rendering, and how much?
- **Question:** Should Phase 14 include human-readable rendering, and in which formats?
- **Options:** (a) one deterministic Markdown/text renderer as a pure, non-stored function; (b) no
  renderer (canonical artifact only); (c) Markdown + HTML + PDF now.
- **Recommendation:** **(a).**
- **Reason:** One renderer *proves* the content/presentation boundary and makes the phase immediately
  useful, while staying stdlib-only and identity-neutral. (b) leaves the boundary unproven; (c) pulls
  in dependencies (PDF/HTML/charts) and is premature presentation work.
- **Consequence:** `render_markdown(report, store) -> str` ships as a pure function; it is not a
  record, not content-addressed, not stored. HTML/PDF/charts/web UI are deferred (§19, §26).

### D7 — What are the v1 report scopes (the closed vocabulary)?
- **Question:** What can a v1 report be *about*?
- **Options:** (a) `backtest` and `experiment` (with optional comparison directives on experiments);
  (b) add a standalone `comparison` scope; (c) add factor/panel/universe scopes now.
- **Recommendation:** **(a).** Top-level `scope ∈ {"backtest", "experiment"}`; a comparison is a
  *directive within* an experiment report, not a standalone scope. Extending the vocabulary is an
  explicit future edit, never an implicit fallback (Phase 13 D7 precedent).
- **Reason:** Backtests and experiments are the sealed *research outcomes*; they carry the full
  strategy/corpus/PIT story. A comparison alone lacks the definitional context a report needs;
  factor/panel/universe reports are valuable but widen scope and (for REVISED panels) cross the PIT
  boundary — defer them.
- **Consequence:** Smallest useful v1 = a single-backtest report and a single-experiment report
  (the latter optionally ranking its children). Anything outside the vocabulary fails closed.

### D8 — Immutability, storage, and rebuildability.
- **Question:** What are the report's mutability and reproducibility guarantees?
- **Options:** (a) immutable, write-once, byte-for-byte rebuildable; (b) mutable/updatable in place;
  (c) append-only versions with mutable "latest".
- **Recommendation:** **(a).**
- **Reason:** Consistent with every artifact in the system; write-once + content-addressing make a
  report an auditable, reproducible fact. Mutability would break identity and provenance.
- **Consequence:** Rebuilding an identical report is a byte-identical no-op; a differing payload under
  the same id fails closed. No wall-clock/RNG anywhere.

### D9 — Report schema/format version vs identity.
- **Question:** Should a report *schema/format* version participate in `report_id`?
- **Options:** (a) no — it is a container/format concern (`REPORT_RESULT_FORMAT_VERSION`), documented
  but not folded into identity; (b) yes — fold it into `report_id`; (c) fold it into `result_hash`.
- **Recommendation:** **(a).**
- **Reason:** The schema version describes *how the same research content is serialized*, not *what
  research is reported*. Folding it would make a pure format migration spuriously change the id of a
  report about unchanged research — the same anti-pattern as a heading changing the id. (Mirrors how
  `EXPERIMENT_RESULT_FORMAT_VERSION` is a documented constant, not an identity input.)
- **Consequence:** A future format bump is a migration event handled at the container/reader level; it
  does not fork the identity of existing reports. The **engine logic** version
  (`report_engine_version_id`) *is* folded (it governs *what* the report means), so a semantic change
  to report construction correctly changes identity.

### D10 — PIT/REVISED labeling and boundary discipline.
- **Question:** How does a report handle PIT vs REVISED?
- **Options:** (a) v1 is PIT-only (backtest/experiment), record `boundary_kind` explicitly, fail
  closed on any boundary disagreement, and reserve a distinct labeled REVISED scope for the future;
  (b) allow mixed PIT/REVISED in one report; (c) leave boundary implicit.
- **Recommendation:** **(a).**
- **Reason:** Backtests/experiments are PIT-only by construction; the "no default mode" and PIT/REVISED
  non-substitutability invariants (data-model §KS) require an explicit, un-defaulted boundary and
  forbid presenting REVISED as PIT.
- **Consequence:** Every v1 report carries `boundary_kind = "pit"` and the renderer labels it as such.
  A future REVISED-panel report is a distinct scope with `boundary_kind = "revised"` and its
  `dataset_version_id` recorded; commingling is disallowed and fails closed.

---

## 22. Alternatives considered

- **A1 — Report as a rich embedded snapshot (embed all referenced bodies).** Rejected (D3): duplicates
  provenance, risks divergence, bloats identity, and fuses volatile ledgers into the report.
- **A2 — Make `BacktestComparison` a persisted `ResearchRecord`.** Rejected (D5): scope creep into
  Phase 13 source for a derived view that is already fully reproducible by content-addressed intent.
- **A3 — Markdown/HTML as the canonical artifact.** Rejected (D4): fuses content with presentation;
  a formatting change would change identity.
- **A4 — Fold presentation/format into `report_id`.** Rejected (D2, D9): violates the core design
  principle; heading/format changes would spuriously change identity.
- **A5 — A new report store / database.** Rejected (D1, §15): the existing write-once sidecar already
  provides everything; a database violates the zero-dependency, no-DB invariant.
- **A6 — Ship no renderer (canonical artifact only).** Rejected (D6): leaves the content/presentation
  boundary unproven and the phase not demonstrably useful.
- **A7 — Ship HTML/PDF/charts now.** Rejected (D6, §19, §26): premature presentation work requiring
  dependencies; belongs to a future UI/presentation phase.
- **A8 — A `Company.report(...)` convenience method.** Rejected (§18): engine-/standalone-only,
  consistent with Phase 12/13 (Phase 13 D6).

---

## 23. Testing strategy

All tests offline, deterministic, synthetic (fictional tickers/CIKs like `9999999991`; no real
market data), stdlib-only, over a `tmp_path` sidecar. Mirrors `tests/experiment/`.

- **Identity:** `report_id`/`report_result_id` deterministic and reproducible across two builds;
  sensitive to name, scope, subject id, comparison directives, and to *any* change in a referenced
  record's `result_hash`/`comparison_id`; **insensitive** to renderer/presentation (proven by
  rendering twice and asserting identical `report_id` and stored bytes).
- **Round-trip:** `ResearchReport.from_dict(to_dict(r))` re-emits an identical `to_dict` and the same
  `result_hash` (byte-identical, like `ExperimentResult`).
- **Persistence:** write-once idempotent no-op on identical rebuild; `FactorConsistencyError` on a
  forced differing payload under the same id; read-back via `store.read_as(id,
  ResearchReport.from_dict)` yields an equal typed object.
- **Fail closed:** absent `subject_id`/reference → `ReportConsistencyError`; content-hash mismatch →
  `ReportConsistencyError`; `comparisons` on a `backtest` scope, unknown `scope`, or bad
  `statistic`/`order` → `ReportConfigurationError`.
- **Comparison-by-intent:** a report's recomputed comparison `comparison_id` equals the reference's
  `content_hash`; recomputation is deterministic across runs.
- **Surfacing (never fabricate/hide):** a synthetic corpus producing an unfilled order / unrecognized
  action / excluded member / `pin_mismatch` is reflected in the rendered "Warnings/Undefined" section
  with the exact recorded reasons; an all-undefined experiment renders an honest empty ranking.
- **Determinism sweep:** the whole new suite passes twice with identical results; no wall-clock/RNG in
  any value or id.

---

## 24. Quality gates

- `uv run pytest` green (all phases; Phase 14 suite added), passing twice deterministically.
- `uv run ruff check .` and `uv run ruff format --check .` clean; `uv run mypy src tests` clean
  (strict).
- Zero runtime dependencies (stdlib `hashlib`/`json`/`dataclasses` only); no float in any path; no
  wall-clock/RNG in any identity or value.
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** (no edit to any identity/version module or to
  `backtest/*`/`experiment/*`); the only source edits are the additive `Workspace.report_engine`
  property and the `__init__.py` re-exports.
- Docs updated; a `docs/phase14-reporting-locked.md` written and the `ARCHITECTURE.md` component
  table extended with a "Research Reporting" row flipped to ✅ **only** once the full suite is green.

---

## 25. Implementation file plan

New package `src/quantforge/report/`:

- `errors.py` — `ReportError` → `ReportConfigurationError`, `ReportConsistencyError`.
- `identity.py` — domain tags `report/1`, `report-reference/1`, `report-engine/1`; `_sha256` +
  `_canonical_json` helpers (copied idiom); `report_reference_digest`, `report_result_hash`,
  `report_id`, `report_result_id`, `report_engine_version_id`.
- `spec.py` — `ComparisonDirective`, `ReportSpecification`, closed v1 scope vocabulary, full
  construction-time validation.
- `result.py` — `REPORT_RESULT_FORMAT_VERSION = "report-result/1"`, `ReportReference`,
  `ResearchReport` (`ResearchRecord` with `.seal`/`to_dict`/`from_dict`).
- `engine.py` — `ReportEngine` (from `Workspace`): resolve → verify content hashes → seal →
  write-once.
- `render.py` — `render_markdown(report, store) -> str` (pure, deterministic; the ten §10 sections).
- `__init__.py` — exports.

Additive edits to existing source (no identity change):

- `src/quantforge/workspace.py` — lazy `report_engine` `@property` + cache line.
- `src/quantforge/__init__.py` — re-export `ResearchReport`, `ReportSpecification`, `ReportReference`.

New tests `tests/report/`: `builders.py`, `test_spec.py`, `test_identity.py`, `test_result.py`,
`test_engine.py`, `test_render.py`.

Docs: this proposal; on approval, `docs/phase14-reporting-locked.md`; `docs/index.md` entry;
`ARCHITECTURE.md` row; `README.md` capability line.

---

## 26. Future-phase boundaries

Explicitly **after** Phase 14, never inside it:

- **Presentation phase:** HTML export, PDF, charts/visualizations, an interactive web UI, an API
  endpoint — all *pure consumers* of the `ResearchReport` JSON; none change research semantics.
- **REVISED-scope reports:** a distinct, explicitly-labeled report scope over `RevisedPanel` /
  `RevisedFactor`, with `boundary_kind = "revised"` and a recorded `dataset_version_id`.
- **Additional subject scopes:** factor, panel, and universe reports (widen the closed v1 vocabulary
  by explicit edit).
- **Multi-subject / comparative-across-experiments reports** and cross-report indices.
- **Any UI, auth, hosting, accounts, dashboards, portfolio construction, live trading, or advice** —
  permanently out of the research engine's scope.

---

## 27. Risks

- **R1 — Renderer scope creep back into the model.** *Mitigation:* the model holds zero presentation;
  a test asserts `report_id` and stored bytes are invariant across renderer changes/double-render.
- **R2 — Provenance duplication drift.** *Mitigation:* reference-only (D3); the report never copies a
  ledger, so there is no second source of truth to diverge.
- **R3 — Stale references.** *Mitigation:* build-time resolution + content-hash verification fail
  closed (G7); a report can never silently reference a drifted or missing artifact.
- **R4 — Comparison recompute divergence.** *Mitigation:* `content_hash = comparison_id` is verified
  at build; recomputation is exact `Decimal` under the pinned context; a mismatch raises.
- **R5 — PIT/REVISED confusion in a future scope.** *Mitigation:* explicit `boundary_kind`, no
  default, fail closed on disagreement; REVISED reserved for a distinct labeled scope (D10).
- **R6 — Schema-version churn changing ids.** *Mitigation:* schema/format version is not folded into
  identity (D9); only engine-logic version is.
- **R7 — Identity collision with a lower layer.** *Mitigation:* fresh domain tags (`report/1`,
  `report-reference/1`, `report-engine/1`).

---

## 28. Final recommendation

Adopt Phase 14 as a thin **Research Reporting & Explainability** layer strictly above Phase 13,
implemented as: a declarative, content-addressed **`ReportSpecification`** → a fail-closed
**`ReportEngine`** reached from `Workspace` via a lazy cycle-free `@property` → a sealed
**`ResearchReport`** that is a `ResearchRecord` (reference-only manifest + reporting intent +
explicit PIT boundary) persisted write-once to the existing sidecar → a **separate, pure
`render_markdown` function** that proves the content/presentation split without touching identity or
storage. Reuse every existing store, identity primitive, and PIT invariant; add no new store, no
database, and no runtime dependency; edit no existing record's identity. Recommend approving
**D1–D10** as stated.

> **D-note (schema version, for the reviewer):** D9 deliberately keeps
> `REPORT_RESULT_FORMAT_VERSION` *out* of `report_id` (a format/container concern), while folding the
> engine-logic `report_engine_version_id` *into* it (a semantic concern). This is the same split the
> experiment layer uses (`EXPERIMENT_RESULT_FORMAT_VERSION` is a documented constant, not an identity
> input; `experiment_engine_version_id` is folded). If the reviewer prefers format-version-in-identity,
> that is the single most likely knob to flip before locking — flag it in review.

**Requires the user's approval before any implementation:** the whole of D1–D10 (in particular D5
comparison-by-intent-recompute, D6 the single Markdown renderer, D7 the `{backtest, experiment}`
scope vocabulary, and D9 schema-version-not-in-identity), the additive `Workspace.report_engine`
property and `__init__.py` re-exports as the only existing-source edits, and the go-ahead to write
`docs/phase14-reporting-locked.md`. **No code, tests, docs-beyond-this-proposal, commits, or pushes
will be made until then.**
