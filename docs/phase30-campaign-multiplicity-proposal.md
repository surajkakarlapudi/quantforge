# Phase 30 - Campaign-Level Multiplicity (proposal)

> Status: **proposal**. This document designs the next capability and validates it
> against the repository's invariants and architectural boundaries before any code is
> written. The normative record of what was actually built is
> `docs/phase30-campaign-multiplicity-locked.md`.

## 0. One-sentence statement

**Correct the per-trial Probabilistic-Sharpe-Ratio significance of one sealed
`ResearchCampaignEvaluation` for the multiplicity of the search** - treat the campaign's
per-trial one-sided p-values `p_i = 1 - PSR_i` as a single hypothesis family and seal,
for each requested correction method, the family-wise / false-discovery adjusted p-value
plus a rejection flag at a declared `alpha`.

## 1. Why this is the honest next capability

Phase 23 (`campaign`) already seals, per trial, a Probabilistic Sharpe Ratio
`PSR_i = P(SR_i > SR*)` against a benchmark Sharpe `SR*`, and *one* campaign-level
Deflated Sharpe Ratio that deflates the **single selected** best trial for the size of
the search. But a researcher who reads the per-trial table and asks *"which of these
trials individually beat the benchmark once I account for having run the whole family of
PSR tests?"* has no honest answer today: the raw per-trial `PSR_i` values are an
uncorrected family of `N` one-sided tests, and eyeballing "which `PSR_i > 0.95`" is
exactly the uncontrolled multiple-comparison error the platform elsewhere refuses.

Phase 25 (`multiplicity`) already solves precisely this shape - it corrects the KNOWN
pairwise p-value family of one sealed `StrategyComparison`. Phase 30 is the **campaign
analogue**: the *same* correction core applied to the *campaign's* per-trial PSR family.
It is a pure consumer strictly above Phase 23, adds no new statistical primitive, and
reuses `quantforge.multiplicity.compute.correct_family` **verbatim**.

This is "the smallest concrete capability the architecture honestly supports": the
per-trial `psr` block already exists and is sealed; the correction core already exists
and is pure; the only added arithmetic is the exact-Decimal transform `p = 1 - PSR`.

### 1.1 Relationship to existing phases (no boundary crossed)

| Concern | Phase 25 (`multiplicity`) | Phase 30 (`campaignmult`) |
| --- | --- | --- |
| Source (exactly one sealed record) | `StrategyComparison` | `ResearchCampaignEvaluation` |
| Family members | KNOWN pairwise `p` cells | per-trial `p_i = 1 - PSR_i` for KNOWN `psr` |
| p-value origin | sealed two-sided pairwise `p` | derived from sealed one-sided `PSR` |
| Exclusion | UNDEFINED pairwise `p` (with `ComparisonUndefinedReason`) | UNDEFINED `psr` (with `CampaignUndefinedReason`) |
| Correction core | `multiplicity.compute.correct_family` | **reused verbatim** |
| Method vocabulary | `multiplicity.model` | **reused verbatim** |
| Ex-post, not PIT | yes (MC-6) | yes (CM-6) |

Phase 28 (`mintrl`) and Phase 29 (`calsig`) established the "pure consumer of one sealed
campaign / calibration" pattern; Phase 30 is the first consumer of the campaign's
per-trial **`psr`** block (Phase 28 read `sharpe`/`skew`/`kurtosis`, not `psr`).

## 2. Package

New package `src/quantforge/campaignmult/` (mirrors `multiplicity` / `mintrl` /
`calsig`):

```
version.py    CampaignMultiplicityEngineVersion + version strings; pins decimal context,
              own method version, AND the reused multiplicity-method version (transitive
              pin of the reused correction core).
errors.py     CampaignMultiplicityError / *ConfigurationError / *ConsistencyError.
model.py      (thin) re-exports the reused CorrectionMethod / ErrorRate /
              DependenceAssumption vocabulary; no new enums.
spec.py       CampaignMultiplicitySpecification (name, source_campaign_id, alpha, methods,
              spec_version) + DEFAULT_METHODS (reused).
identity.py   campaign_multiplicity_id / campaign_multiplicity_result_hash; domain
              "campaignmult/1".
result.py     CampaignMultiplicityCorrection + TrialFamilyCell / ExcludedTrialCell /
              TrialMethodCell / MethodResult / CampaignMultiplicityCoverage.
engine.py     CampaignMultiplicityEngine.correct(spec).
__init__.py   public re-exports.
```

No new store, no new ingestion, no new PIT surface, no runtime dependency, no
`_linalg`/`_stats` expansion (the reused `correct_family` needs none, and `p = 1 - PSR`
is a single Decimal subtraction).

## 3. Data flow (engine `correct`)

1. **Resolve** `source_campaign_id` via
   `store.read_as(id, ResearchCampaignEvaluation.from_dict)`; a missing id or non-campaign
   payload raises `CampaignMultiplicityConsistencyError` (fail closed, CM-1).
2. **Verify** the resolved `research_result_id` equals the requested id (CM-1).
3. **Collect the family** (CM-3): walk `source.trials` in sealed request order. A trial
   whose `psr` cell is KNOWN joins the family - its `p_i = 1 - PSR_i` computed once under
   the pinned context (exact Decimal; `PSR ∈ [0,1] ⇒ p ∈ [0,1]`, no clamp, no repair). A
   trial whose `psr` cell is UNDEFINED becomes a first-class `ExcludedTrialCell` carrying
   the source's own `CampaignUndefinedReason` - never imputed, never coerced to a number.
4. **Correct** the family by each requested method via
   `multiplicity.compute.correct_family(family_p, methods, alpha, context=...)` -
   reused verbatim. Empty family ⇒ empty per-method cells, never a divide-by-zero.
5. **Seal + persist** a `CampaignMultiplicityCorrection`; its `result_hash` folds the
   answer, its id transitively pins `source.result_hash`. Write-once, idempotent.

## 4. Public API

- `CampaignMultiplicitySpecification(name, source_campaign_id, alpha,
  methods=DEFAULT_METHODS, spec_version)`.
- `CampaignMultiplicityCorrection` - sealed `ResearchRecord`
  (`research_result_id` aliases `campaign_multiplicity_id`).
- `Workspace.campaign_multiplicity_engine.correct(spec)`.
- Top-level `quantforge.CampaignMultiplicitySpecification` /
  `quantforge.CampaignMultiplicityCorrection`.

## 5. Identity (§10, §11)

```
campaign_multiplicity_result_hash = sha256( canonical JSON over ordered output cells:
    family descriptor (family size m, excluded count), then each KNOWN family cell
    (index, label, psr, p_value), then each excluded cell (index, label, reason), then
    per method the honest labels (error_rate, dependence) and each family cell's
    (index, p_adjusted, rejected) )
campaign_multiplicity_id = sha256( domain "campaignmult/1",
    campaign_multiplicity_engine_version_id, name, spec_version, source_campaign_id,
    source_result_hash, alpha, ORDERED method list, campaign_multiplicity_result_hash )
```

The engine version folds the pinned decimal context, Phase 30's own method version, and
the **reused** `MULTIPLICITY_METHOD_VERSION` (so a change to the shared correction core
changes this record's identity - an honest transitive pin of the reused algorithm).

## 6. Determinism

Exact Decimal only (one `1 - PSR` subtraction plus the reused correction arithmetic),
under an explicit prec-34 `ROUND_HALF_EVEN` `localcontext`; no float, no RNG, no
wall-clock, no iteration-order dependence (family order = sealed trial order; the
correction's internal total order is `(p, family_index)`).

## 7. Invariants (CM-1..CM-6)

- **CM-1 Reference & transitive pin.** Corrects exactly one sealed
  `ResearchCampaignEvaluation`, pinned by `(id, result_hash)`; a missing / drifted /
  wrong-type reference fails closed.
- **CM-2 Explicit family & coverage.** The record states `n_trials_total`,
  `family_size`, and `n_excluded`; every member and every exclusion is enumerated.
- **CM-3 Exclusions first-class.** A trial with an UNDEFINED `psr` is recorded with its
  `CampaignUndefinedReason`, never imputed / coerced / dropped; empty family ⇒ no
  divide-by-zero.
- **CM-4 PSR verbatim + honest transform.** Each family member's `psr` is consumed
  verbatim; `p = 1 - PSR` is the only added arithmetic (exact Decimal, in `[0,1]` by
  construction, no clamp/repair).
- **CM-5 Single reused correction core + honest labels.** The adjusted p-values come
  from `correct_family` verbatim under the pinned context; rejection is uniformly
  `p_adj ≤ alpha`; each method's error-rate / dependence labels are the single source of
  truth in `multiplicity.model` (Benjamini-Hochberg's independence/PRDS assumption can
  never be mislabeled dependence-robust).
- **CM-6 Ex-post, not PIT.** The correction is an ex-post statistic; the record is not a
  `Pit*` type and exposes no as-of accessor. `boundary_kind = "pit"` documents the input
  side only.

## 8. Failure semantics

Data condition (UNDEFINED `psr`) ⇒ recorded exclusion, never raised. Configuration
defect (empty name / spec_version / source id; `alpha` outside `(0,1)`; empty or
duplicated method list) ⇒ `CampaignMultiplicityConfigurationError`. Consistency defect
(source absent / undecodable / id mismatch) ⇒ `CampaignMultiplicityConsistencyError`.

## 9. Testing

`tests/campaignmult/` with builders that synthesize a `ResearchCampaignEvaluation`
directly (hand-chosen `TrialStat.psr` cells) and seal it: compute (p=1-PSR transform,
family collection, empty family, method wiring), engine (resolve/verify/exclusion/seal/
idempotent/fail-closed), identity (transitive pin sensitivity, method-order sensitivity),
result (round-trip), spec (canonical alpha, duplicate/empty methods), model
(vocabulary re-export). Full suite must stay green in both pytest orderings.
