# Phase 14 — Research Reporting & Explainability (LOCKED)

> **Status:** Locked normative specification. Decisions **D1–D10** were approved as
> recommended; this document is the source of truth for the implementation and
> supersedes the recommendations in
> [phase14-reporting-proposal.md](phase14-reporting-proposal.md). Every conditional
> reference in the proposal ("recommended", "if the user wants…") is resolved here to a
> committed decision.
>
> **One-line thesis:** Phase 14 turns QuantForge's already-sealed research artifacts into
> a single, content-addressed, deterministic, human-explainable **`ResearchReport`** — a
> thin *manifest of references* to sealed `ResearchRecord`s plus the reporting intent,
> persisted write-once to the existing sidecar, and rendered to human-readable form by a
> *separate* renderer that never touches research identity. It reuses every existing
> store, identity, and PIT invariant; adds no new source layer, no database, and no
> runtime dependency.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D1** | A `ResearchReport` **is** a `ResearchRecord` persisted write-once to the existing `<root>/research/sha256-<hex>.json` sidecar. It implements the Protocol (`research_result_id` alias + deterministic `to_dict`/`from_dict`). No new store, no new format, no database. |
| **D2** | `report_id` folds the **reporting request + referenced artifact content hashes only** — `report_engine_version_id`, the report spec (name, scope, subject id, comparison directives), and `result_hash` over the ordered reference digests. It **never** folds presentation, schema/format version, or wall-clock/RNG. A heading or renderer change can never change `report_id`. |
| **D3** | **Reference-only model.** The report stores only `(kind, reference_id, content_hash, detail)` per reference — never a copy of a referenced record's body/ledger or any financial value. Provenance is preserved *by reference* (single source of truth, no divergence). |
| **D4** | Canonical machine-readable form is a JSON dict via `to_dict`/`from_dict` with a **byte-identical round-trip** (`from_dict(to_dict(r))` re-emits an identical `to_dict()` and the same `result_hash`), inside the store's existing container. Markdown/HTML/PDF are renderings of the JSON, never the artifact. |
| **D5** | A `BacktestComparison` is referenced **by intent** (`statistic`, `order`, `member_scope`, `comparison_version_id`) with `content_hash = comparison_id`, and **recomputed deterministically** at build and at render via `BacktestComparison.of_experiment(...)`. Phase 13 `analysis.py` is **not** modified; no new persisted record is added. |
| **D6** | Phase 14 ships **exactly one** pure reference renderer: `render_markdown(report, store) -> str`. No HTML, PDF, charts, or web UI. The renderer output is not a `ResearchRecord`, is not content-addressed, and is not written to the sidecar. |
| **D7** | The closed v1 report scope vocabulary is exactly `{backtest, experiment}`. A comparison is a *directive within* an experiment report, never a top-level scope. Anything outside the vocabulary fails closed. Extending the set is an explicit future edit, never an implicit fallback. |
| **D8** | Reports are **immutable, write-once, content-addressed, and byte-for-byte rebuildable.** Rebuilding an identical report is a byte-identical no-op; a differing payload under the same id fails closed via the store's `FactorConsistencyError` guard. No wall-clock/RNG anywhere. |
| **D9** | The report **schema/format version** (`REPORT_RESULT_FORMAT_VERSION`) is **not** part of report identity (a container/format concern). The **engine-logic version** (`report_engine_version_id`) **is** folded (a semantic concern). A pure format migration never forks the identity of a report about unchanged research. |
| **D10** | V1 is **PIT-only** with an explicit, un-defaulted `boundary_kind = "pit"`. The report fails closed on any boundary disagreement. A REVISED scope (`boundary_kind = "revised"`) is reserved for a future distinct, explicitly-labeled scope; commingling PIT and REVISED is disallowed. |

---

## 2. Architecture (locked)

Phase 14 is a thin reporting layer strictly *above* Phase 13, a **pure consumer** of
already-sealed, PIT-correct research artifacts (`BacktestResult`, `ExperimentResult`, and
the derived `BacktestComparison`). It follows the extension recipe every prior phase
uses: versioned immutable request object → fail-closed engine reached from `Workspace`
via a lazy, cycle-free `@property` → distinct result types → content-addressed identity
with fresh domain tags → data conditions recorded/surfaced as first-class values, defects
raised → compute-on-demand with the shared write-once sidecar. It computes **no** new
financial number.

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
   render_markdown(report, store) -> str        store.read_as(id, ResearchReport.from_dict)
   (deterministic Markdown; PURE FUNCTION;       (first-class typed object, byte-identical round-trip)
    NOT stored, NOT identity-bearing)
```

**New package `src/quantforge/report/`:**

- `errors.py` — `ReportError` → `ReportConfigurationError`, `ReportConsistencyError`
  (mirrors `experiment/errors.py`).
- `identity.py` — `report_reference_digest`, `report_result_hash`, `report_id`,
  `report_result_id`, `report_engine_version_id`. Fresh domain tags `report/1`,
  `report-reference/1`, `report-engine/1`.
- `spec.py` — `ComparisonDirective`, `ReportSpecification`, the closed v1 scope
  vocabulary, full construction-time validation.
- `result.py` — `REPORT_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT`, `ReportReference`,
  `ResearchReport` (a `ResearchRecord` with `.seal`/`to_dict`/`from_dict`).
- `engine.py` — `ReportEngine` (constructed from `Workspace`, composes
  `research_result_store`): resolve → verify content hashes → seal → write-once.
- `render.py` — `render_markdown(report, store) -> str`: the single reference renderer, a
  pure, deterministic function that resolves references and formats the ten §10 sections.
- `__init__.py` — package exports.

**The only edits to existing source** (all additive, none altering any existing identity):

1. `workspace.py` — one lazy `report_engine` `@property` (+ its `self._report_engine =
   None` cache line), following the `experiment_engine` template verbatim.
2. `src/quantforge/__init__.py` — top-level re-exports of `ResearchReport`,
   `ReportSpecification`, `ReportReference` (spec + result types only; the engine is
   reached via `Workspace`).

**No edit to** `backtest/*`, `experiment/*` (including `analysis.py`), `factors/store.py`,
or any identity/version module.

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only where numeric
(the report carries **no** numeric field of its own in v1 — it only references), no
wall-clock, no RNG.

### 3.1 `ReportReference` (sealed)

```
ReportReference(
    kind: str,            # "backtest" | "experiment" | "comparison"
    reference_id: str,    # backtest_id / experiment_result_id / comparison_id
    content_hash: str,    # record -> its result_hash; comparison -> its comparison_id
    detail: dict[str, object] = {},   # reporting intent for a comparison ONLY:
                                      #   {"statistic", "order", "member_scope",
                                      #    "comparison_version_id"}
)
```

`to_dict` / `from_dict`, byte-identical round-trip. `detail` is empty for
`backtest`/`experiment` references; for a `comparison` it records exactly the inputs a
reader needs to *recompute* the comparison (D5). `digest()` → the `(kind, reference_id,
content_hash, canonical detail)` fingerprint folded into `result_hash`.

### 3.2 `ResearchReport` (implements `ResearchRecord`)

```
ResearchReport(
    report_engine_version_id: str,
    report_spec: dict[str, object],            # the full ReportSpecification.to_dict()
    scope: str,                                # "backtest" | "experiment"
    references: tuple[ReportReference, ...],   # ordered; the content-addressed pointers
    boundary_kind: str,                        # "pit" (v1 is PIT-only; D10)
    result_hash: str,                          # canonical JSON over ordered digests
)

# derived, not stored as state:
report_id           property  -> sha256 over (report_spec identity + sorted reference descriptors)
report_result_id    property  -> sha256 over (report_id + engine_version_id + result_hash)
research_result_id  property  -> alias of report_result_id  (the ResearchRecord key)
```

- `to_dict()` keys (deterministic): `report_result_id`, `research_result_id` (alias so the
  generic reader keys correctly), `report_id`, `report_engine_version_id`, `report_spec`,
  `scope`, `references`, `boundary_kind`, `result_hash`.
- `from_dict` is the fail-closed inverse; the two id aliases are re-derived by their
  properties, **never read from state**, so `from_dict(to_dict(r))` re-emits an identical
  `to_dict` and the same `result_hash` — a tampered stored `report_id` is simply ignored.
- `.seal(...)` is the identity-computing constructor (mirrors `ExperimentResult.seal`): it
  folds the ordered reference digests into `result_hash`, so identity is a pure function of
  the reporting request + referenced content and is never supplied by the caller.

**What the model deliberately does NOT hold:** section titles, headings, prose, display
order, Markdown/HTML, colors, chart specs, or any presentation; and no referenced record's
body — it is pointer-only, exactly like `ExperimentResult`'s run ledger.

### 3.3 `ReportSpecification` / `ComparisonDirective` (declarative request)

```
ComparisonDirective(statistic: str, order: str = "descending")
    # statistic ∈ RANKABLE_STATISTICS, order ∈ {descending, ascending}, validated at construction

ReportSpecification(
    name: str,                                     # non-empty
    scope: str,                                    # "backtest" | "experiment"
    subject_id: str,                               # non-empty backtest_id / experiment_result_id
    comparisons: tuple[ComparisonDirective, ...] = (),   # valid only when scope == "experiment"
    spec_version: str = "report/1",
)
```

`comparisons` on a `backtest` scope raises; a duplicate `(statistic, order)` directive
raises; the same statistic under distinct orders is allowed. The report never invents a
statistic — it reuses the Phase 13 closed `RANKABLE_STATISTICS` vocabulary.

---

## 4. Identity / determinism (locked)

- Domain tags via the shared `sha256_hex`, NUL (`\x00`) separated, canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): `report/1`,
  `report-reference/1`, `report-engine/1`.
- The report layer performs **no numeric derivation** (it only aggregates already-sealed
  strings), so `report_engine_version_id()` folds only its domain tag — the experiment
  pattern, not the decimal-context dataclass pattern.
- `report_reference_digest(kind, reference_id, content_hash, detail)` — the sealed
  fingerprint.
- `report_result_hash(ordered_reference_digests)`.
- `report_id(name, spec_version, scope, subject_id, sorted_reference_descriptors,
  comparison_directives)` — the **request** identity, sorted where set-semantics apply so
  reference tuple order and directive order never change the id.
- `report_result_id(report_id, report_engine_version_id, result_hash)` — the sidecar key,
  aliased to `research_result_id`.

**Folds (changes identity):** engine-logic version ✔, the report spec (name, scope,
subject id, comparison directives) ✔, every referenced record id ✔, and — via
`result_hash` — every referenced record's `result_hash` / `comparison_id` ✔. A report's
identity is therefore sensitive to *any* change in *any* artifact it reports on — honestly.

**Does NOT fold (leaves identity unchanged):** report schema/format version (D9),
presentation config, section headings, display ordering, renderer output, wall-clock, RNG,
`id()`.

---

## 5. Content vs presentation boundary (locked §10)

The split is enforced *structurally*, not by convention.

- **Content (in `ResearchReport`, folded into `report_id`):** *which* artifacts
  (references by id + content hash), the *reporting intent* (scope, comparison directives),
  and the *boundary label*.
- **Presentation (in `render.py`, NOT folded into anything):** section titles and order,
  headings, prose, tables vs prose, Markdown vs HTML vs PDF, number formatting, chart
  choices. A presentation change produces different renderer bytes but the **same**
  `report_id` and the **same** stored record.

The ten rendered sections — Executive Summary, Research Definition, Dataset & PIT
Configuration, Universe, Strategy, Backtest Results, Experiment Comparison, Provenance,
Warnings / Undefined Data, Reproduction Information — are a **stable, documented renderer
contract**, not model state. Each is derived by resolving the references from the store and
reading the sealed `to_dict()`s; the renderer invents nothing and prints every figure
verbatim (as a decimal string) or from a deterministically recomputed `BacktestComparison`.

---

## 6. PIT semantics, provenance, storage (locked D3, D5, D10)

- **PIT-only v1.** `backtest` and `experiment` are PIT-only by construction (the backtest
  engine consumes the PIT-only `PitPriceSeries` hand-off; there is no `RevisedBacktest`).
  A v1 report carries `boundary_kind = "pit"` explicitly (no default) and the renderer
  labels it. A future REVISED scope is distinct and explicitly labeled (D10).
- **Provenance by reference, never by copy.** The report pins each artifact by
  `(reference_id, content_hash)`; each referenced record already carries its complete
  lineage down to raw source, so the report's provenance is exactly as strong as the
  source's, without duplication or divergence risk.
- **Comparisons by intent.** A `comparison` reference carries the `detail` intent; its
  `content_hash` is the `comparison_id` addressing exactly those inputs. Build and render
  each recompute the `BacktestComparison` and require the recomputed `comparison_id` to
  equal the pinned `content_hash`, failing closed on drift (R4) — a verifiably reproducible
  comparison with no persisted record and no edit to `analysis.py`.
- **Storage.** Zero new store types; write-once sidecar only; re-running an identical
  report is a byte-identical no-op write; a differing payload under an existing id fails
  closed via the store's `FactorConsistencyError` guard.

---

## 7. Failure / UNDEFINED behavior (locked §17)

Follows the existing split exactly — **defects raise, conditions are recorded** — and adds
no new UNDEFINED semantics.

**Raised** (`ReportConfigurationError` / `ReportConsistencyError`): empty `name`; unknown
`scope`; empty `subject_id`; a `comparisons` directive when `scope != "experiment"`; a
duplicate directive; a `statistic`/`order` outside the closed vocabulary; a `subject_id` or
referenced id absent from the sidecar; a referenced record whose recomputed `content_hash`
does not match; a recomputed comparison whose `comparison_id` no longer matches the pinned
`content_hash`; a referenced record whose implied boundary disagrees with the declared
`boundary_kind`.

**Recorded / surfaced (never raised, never fabricated), by reading the sealed summaries:**
unfilled orders (`Fill.status != "filled"` + `reason`), unrecognized corporate actions
(`AppliedAction.unrecognized`), comparison members excluded for a non-finite statistic
(`comparison.excluded`), and corpus `pin_mismatch`. There is **no first-class warning
type**; the "Warnings / Undefined Data" rendered section is a presentation grouping of
recorded conditions, not model state.

---

## 8. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 14 suite added), deterministic across runs.
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src tests`
  clean (strict).
- Zero runtime dependencies (stdlib `hashlib`/`json`/`dataclasses`/`Decimal` only); no
  float in any path; no wall-clock/RNG in any identity or value.
- No new store, no database; only `<root>/research/` written.
- **No existing record identity changes** — the only source edits are the additive
  `Workspace.report_engine` property/cache line and the `__init__.py` re-exports; no edit to
  any identity/version module or to `backtest/*`/`experiment/*` (including `analysis.py`).
- Byte-identical `ResearchReport` round-trip test proves `from_dict` introduces no drift and
  that presentation edits/double-render leave `report_id` and the stored bytes invariant.
- Docs updated; `ARCHITECTURE.md` "Research Reporting" row flipped to ✅ only when green.
