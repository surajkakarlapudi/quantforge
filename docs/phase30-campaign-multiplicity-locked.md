# Phase 30 - Campaign-Level Multiplicity (locked)

> Status: **locked / normative**. This document records what was **actually built** for
> Phase 30, validated against the repository's invariants. Where the implementation
> departs from `docs/phase30-campaign-multiplicity-proposal.md`, the deviation is
> disclosed here. Released as **v0.27.0**.

## 0. One-sentence statement

**Correct the per-trial Probabilistic-Sharpe-Ratio significance of one sealed
`ResearchCampaignEvaluation` for the multiplicity of the search**: treat the campaign's
per-trial one-sided p-values `p_i = 1 - PSR_i` (over trials whose `psr` is KNOWN) as a
single hypothesis family and seal, for each requested correction method, the family-wise
/ false-discovery adjusted p-value plus a rejection flag at a declared `alpha`.

## 1. What was built

New package `src/quantforge/campaignmult/`, a pure consumer strictly **above** Phase 23
(`campaign`). It adds no new statistical primitive: it reuses
`quantforge.multiplicity.compute.correct_family` and the
`quantforge.multiplicity.model` method vocabulary **verbatim**, and the only added
arithmetic is the exact-Decimal transform `p = 1 - PSR`.

```
version.py    CampaignMultiplicityEngineVersion + version strings; folds the pinned
              decimal context, Phase 30's own method version, AND the reused
              MULTIPLICITY_METHOD_VERSION (transitive pin of the reused correction core).
errors.py     CampaignMultiplicityError / *ConfigurationError / *ConsistencyError.
model.py      Thin re-export of CorrectionMethod / ErrorRate / DependenceAssumption /
              method_error_rate / method_dependence from multiplicity.model (identity,
              not a parallel declaration) - no new enums.
spec.py       CampaignMultiplicitySpecification(name, source_campaign_id, alpha,
              methods=DEFAULT_METHODS, spec_version); DEFAULT_METHODS re-exported from
              multiplicity.spec.
identity.py   campaign_multiplicity_id / campaign_multiplicity_result_hash; domain
              "campaignmult/1".
result.py     CampaignMultiplicityCorrection + TrialFamilyCell / ExcludedTrialCell /
              TrialMethodCell / MethodResult / CampaignMultiplicityCoverage.
engine.py     CampaignMultiplicityEngine.correct(spec).
__init__.py   public re-exports (sorted __all__).
```

Wired additively: `Workspace.campaign_multiplicity_engine` (lazy `@property`, deferred
import, private cache slot) and top-level `quantforge.CampaignMultiplicitySpecification`
/ `quantforge.CampaignMultiplicityCorrection` re-exports. **No new store, no new
ingestion, no new PIT surface, no runtime dependency, no `_linalg`/`_stats` expansion.**

## 2. Data flow (engine `correct`) - as built

1. **Reject** a non-`CampaignMultiplicitySpecification` argument with
   `CampaignMultiplicityConfigurationError`.
2. **Resolve** `source_campaign_id` via
   `store.read_as(id, ResearchCampaignEvaluation.from_dict)`. A missing id, an
   undecodable payload (`KeyError`/`ValueError`), or a resolved record whose
   `research_result_id` disagrees with the request raises
   `CampaignMultiplicityConsistencyError` (fail closed, CM-1).
3. **Collect the family** (CM-3/CM-4) under the version's `localcontext`: walk
   `source.trials` in sealed request order. A trial whose `psr.status is KNOWN` joins the
   family - `p_value = 1 - Decimal(psr.value)`, canonicalized `p_str = str(+p_value)`,
   emitted as a `TrialFamilyCell(index, label, psr, p_value=p_str)`, and the *parsed-back*
   `Decimal(p_str)` is what enters the corrected family (the value corrected is exactly
   the value sealed). A trial whose `psr` is UNDEFINED becomes an `ExcludedTrialCell`
   carrying the source's own `CampaignUndefinedReason` - never imputed, never coerced.
4. **Correct** the family by each requested method via
   `correct_family(family_p, spec.methods, alpha, context=context)` (reused verbatim).
   Each `MethodComputation` is mapped to a `MethodResult` whose `error_rate` /
   `dependence` labels come from `method_error_rate` / `method_dependence` (single source
   of truth), and each `TrialMethodCell(index, p_adjusted, rejected)` aligns
   index-for-index (`zip(..., strict=True)`) to the family order. An empty family yields
   empty per-method cell lists - never a divide-by-zero.
5. **Seal + persist** a `CampaignMultiplicityCorrection` (its `result_hash` folds the
   answer; its id transitively pins `source.result_hash`) write-once to the shared
   sidecar. An identical re-build is a byte-identical no-op.

## 3. Identity (§10, §11) - as built

```
campaign_multiplicity_result_hash = sha256( canonical JSON over ordered output cells:
    family descriptor (family_size, n_excluded), then each KNOWN family cell
    (index, psr, p_value), then each excluded cell (index, reason), then per method the
    honest labels (error_rate, dependence) and each family cell's
    (index, p_adjusted, rejected) )
campaign_multiplicity_id = sha256( domain "campaignmult/1",
    campaign_multiplicity_engine_version_id, name, spec_version, source_campaign_id,
    source_result_hash, alpha, ORDERED method list, campaign_multiplicity_result_hash )
```

The engine version folds the pinned decimal context (prec 34, `ROUND_HALF_EVEN`),
Phase 30's own `CAMPAIGNMULT_METHOD_VERSION`, and the reused
`CAMPAIGNMULT_CORRECTION_VERSION = MULTIPLICITY_METHOD_VERSION` - so a change to the
shared correction core changes this record's identity (an honest transitive pin).

**Label is not folded beyond `index`.** `trial.label` is carried in the serialized cells
for readability but does not enter the hash payload (the trial `index` already folds
position); the coverage block's `n_trials_total` is likewise not folded (only
`family_size` + `n_excluded`, via the descriptor). This matches the test contract
(`test_coverage_counts_do_not_alter_hash_beyond_descriptor`).

## 4. Determinism

Exact Decimal only - one `1 - PSR` subtraction plus the reused correction arithmetic -
under an explicit prec-34 `ROUND_HALF_EVEN` `localcontext`. No float, no RNG, no
wall-clock, no UUID, no iteration-order dependence: family order is the sealed trial
order, and the correction's internal total order is `(p, family_index)`. The engine holds
no mutable per-run state, so two builds of the same spec over the same immutable sidecar
are byte-identical.

## 5. Invariants (CM-1..CM-6)

- **CM-1 Reference & transitive pin.** Corrects exactly one sealed
  `ResearchCampaignEvaluation`, pinned by `(id, result_hash)`; a missing / drifted /
  wrong-type / id-mismatched reference fails closed with
  `CampaignMultiplicityConsistencyError`.
- **CM-2 Explicit family & coverage.** The record states `n_trials_total`,
  `family_size`, and `n_excluded`; every member and every exclusion is enumerated.
- **CM-3 Exclusions first-class.** A trial with an UNDEFINED `psr` is recorded as an
  `ExcludedTrialCell` with its `CampaignUndefinedReason`, never imputed / coerced /
  dropped; an empty family yields empty per-method cells, never a divide-by-zero.
- **CM-4 PSR verbatim + honest transform.** Each family member's `psr` is consumed
  verbatim; `p = 1 - PSR` is the only added arithmetic (exact Decimal, in `[0, 1]` by
  construction because `PSR` is a `Phi` value in `[0, 1]`; no clamp / repair).
- **CM-5 Single reused correction core + honest labels.** Adjusted p-values come from
  `correct_family` verbatim under the pinned context; rejection is uniformly
  `p_adj <= alpha`; each method's error-rate / dependence labels are the single source of
  truth in `multiplicity.model`.
- **CM-6 Ex-post, not PIT.** The correction is an ex-post statistic; the record is
  **not** a `Pit*` type and exposes **no** `as_of` accessor. `boundary_kind = "pit"`
  documents the input side only (the underlying trials were PIT walks) and is carried
  through from the source campaign unchanged.

## 6. Failure semantics

- **Data condition** (UNDEFINED `psr`) => recorded exclusion, never raised.
- **Configuration defect** (empty name / spec_version / source id; `alpha` outside the
  open interval `(0, 1)` or non-finite; empty or duplicated method list; non-spec
  argument) => `CampaignMultiplicityConfigurationError`.
- **Consistency defect** (source absent / undecodable / id mismatch) =>
  `CampaignMultiplicityConsistencyError`.

## 7. Deviations from the proposal

- **`seal(..., method_version=...)`.** The engine passes its own `method_version` into
  `CampaignMultiplicityCorrection.seal` (the proposal's §5 sketch did not list it). It is
  used only to keep the sealed record self-describing; the id already folds the method
  version via the engine-version id, so this changes no identity.
- **Family-cell hash payload.** As disclosed in §3, `label` and coverage
  `n_trials_total` are serialized but not folded into the hash (position is folded via
  `index`; the descriptor folds `family_size` + `n_excluded`). The proposal's §5 listed
  `label` inside the family/excluded cell hash payload; the built hash folds `index`
  instead, which is strictly stronger (labels are derivable from index).

No other deviations. All other behavior matches the proposal.

## 8. Tests

`tests/campaignmult/` (42 tests): `test_spec` (canonical alpha, open-interval /
non-finite rejection, empty/duplicate/non-method rejection, method-order preservation),
`test_model` (vocabulary re-export identity), `test_version` (transitive-pin binding,
per-input id sensitivity), `test_identity`, `test_result` (byte-identical round-trip, id
re-emitted not read from state, coverage-does-not-alter-hash-beyond-descriptor, method
lookup, no `as_of`), `test_engine` (p=1-PSR + Bonferroni numeric check, first-class
exclusion, empty family, boundary + transitive pin carried, deterministic/idempotent,
method-order distinct records, fail-closed on missing / wrong-type source, non-spec
argument). Full suite green in both pytest orderings (2090 passed).
