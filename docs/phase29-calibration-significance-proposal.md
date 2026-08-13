# Phase 29 - Risk-Forecast Calibration Significance (proposal)

**Status:** proposal (design, pre-implementation). Version target **v0.26.0**.
**Package:** `quantforge.calsig` (calibration-significance).
**Depends on:** Phase 26 `quantforge.calibration` (the sealed
`RiskForecastCalibration`) and the reused deterministic exact-`Decimal`
standard-normal CDF `quantforge._stats.normal.standard_normal_cdf`.

## 1. The question the calibration record never answers

A sealed `RiskForecastCalibration` (Phase 26) reports, over the calibratable
windows of one walk-forward, the aggregate `mean_variance_ratio` (the average of
the per-window `realized / predicted` variance ratios), the pooled
`aggregate_bias`, and the population `variance_ratio_dispersion`. It states the
*magnitude* of the risk model's mis-calibration but never whether that
mis-calibration is **statistically distinguishable from perfect calibration** -
i.e. whether the mean variance ratio differs significantly from `1`.

Phase 29 answers exactly that one question and nothing more:

> Over the calibratable-window family of one sealed `RiskForecastCalibration`, is
> the mean variance ratio significantly different from `1` (perfect calibration on
> average)?

This is the calibration analogue of Phase 24's paired-difference significance test
(`comparison.compute.compare_pair`), applied as a **one-sample** test about the
null mean `1`.

## 2. Method (single, deterministic, closed-form)

Let the source's sealed calibratable family have `K = n_calibratable` windows,
sealed mean `m = mean_variance_ratio` and sealed population dispersion
`s = variance_ratio_dispersion` (the population standard deviation of the
per-window variance ratios). With `NULL_MEAN_RATIO = 1`:

```
standard_error = s / sqrt(K)                # population-moment convention (Phase 24)
t_statistic    = (m - 1) / standard_error
p_value        = 2 * (1 - Phi(|t_statistic|))   # two-sided, clamped to [0, 1]
```

`Phi` is the reused exact-`Decimal` `standard_normal_cdf`. All arithmetic runs
under the pinned decimal context (precision 34, `ROUND_HALF_EVEN`); the only
transcendentals are `Decimal.sqrt` and the reused `Phi`. There is no RNG, no
float, no wall clock, and no data-dependent iteration.

`standard_error = s / sqrt(K)` equals Phase 24's `sqrt(variance / n)` (there
`variance` is the population variance and `s = sqrt(variance)`), so Phase 29 uses
the **same** population-moment convention already in the codebase.

**Descriptive bias direction** (no significance): `UNDER_FORECAST` when `m > 1`
(realized variance exceeds predicted, the model under-forecasts risk),
`OVER_FORECAST` when `m < 1`, `UNBIASED` when `m == 1`. Known whenever `m` is
known.

### 2.1 Consume the sealed statistics verbatim (CS-4)

Phase 29 reads `mean_variance_ratio`, `variance_ratio_dispersion`, and
`n_calibratable` **from the sealed `RiskForecastCalibration` summary / coverage**
and consumes them verbatim - it never recomputes them from the per-window
`variance_ratio` cells. This mirrors the moment-consumed-verbatim discipline of
Phase 28 (MT-4) and Phase 26 (RC-4): the sealed answer is authoritative.

### 2.2 Large-sample deferral (disclosed, matches Phase 24)

The two-sided p-value uses the **large-sample normal** approximation
`2 * (1 - Phi(|t|))`, deferring a finite-sample Student-`t` distribution to a
later phase - the identical `(★)` deferral disclosed by Phase 24's
`comparison.compute`. It reuses no new statistical primitive.

## 3. Fail-closed states (never fabricated)

| Condition | Outcome |
|---|---|
| source id absent / not a `RiskForecastCalibration` / id mismatch | **raise** `CalSigConsistencyError` (CS-1) |
| source `calibration_status` is `UNDEFINED` (below the Phase-26 floor, or no calibratable windows), or its sealed mean / dispersion cell is not `KNOWN` | seal record, everything `UNDEFINED` `SOURCE_NOT_CALIBRATED` (CS-2) |
| `variance_ratio_dispersion == 0` (all ratios identical) | `standard_error = 0`; `t_statistic` / `p_value` `UNDEFINED` `ZERO_RATIO_DISPERSION`; `mean_variance_ratio` and `bias_direction` stay `KNOWN` (CS-3) |
| otherwise | `significance_status = TESTED`; `t_statistic` / `p_value` `KNOWN` |

The record **always seals** (a data condition is never an exception); only a
request / reference-consistency defect raises. There is a **single per-request
numerical parameter: none** - the null mean is the fixed platform constant
`NULL_MEAN_RATIO = 1`, folded into the id (as Phase 26 folds
`MIN_CALIBRATABLE_WINDOWS`).

## 4. The sealed record

`CalibrationSignificance` (a `ResearchRecord`, `research_result_id` aliases
`calibration_significance_id`) pins the source calibration by
`(source_calibration_id, source_result_hash)` and holds one
`SignificanceSummary`:

* `mean_variance_ratio` (carried verbatim), `null_mean_ratio` (`"1"`),
  `n_calibratable`,
* `standard_error`, `t_statistic`, `p_value` (UNDEFINED-preserving cells),
* `bias_direction`,
* `significance_status` (`TESTED` / `UNDEFINED`) + `status_reason`.

Identity:

```
calibration_significance_result_hash = sha256( canonical-JSON [ {block: summary, ...} ] )
calibration_significance_id = sha256( "calsig/1", engine_version_id, name,
    spec_version, source_calibration_id, source_result_hash, null_mean_ratio,
    result_hash )
```

so the id is transitively sensitive to the source calibration's `result_hash`
(and everything beneath it), the null mean, and the computed answer.

**Ex-post, not PIT (CS-6):** not a `Pit*` type, no `as_of`, not a
`BacktestResult`; `boundary_kind` is carried from the source verbatim.

## 5. Invariants (CS-1..CS-6)

* **CS-1** Fail-closed reference resolution + transitive pin.
* **CS-2** Source-status gating: only a `CALIBRATED` source is tested; otherwise a
  first-class `UNDEFINED` `SOURCE_NOT_CALIBRATED`, always sealed.
* **CS-3** UNDEFINED-preserving, no divide-by-zero (zero dispersion).
* **CS-4** Sealed mean / dispersion / count consumed verbatim, never recomputed.
* **CS-5** Single deterministic large-sample two-sided normal test; null mean `1`
  folded into the id; finite-sample `t` deferred (★).
* **CS-6** Ex-post, not PIT.

## 6. Boundaries honored

No new store (write-once to the shared Phase 8 sidecar). No new ingestion, no UI,
no runtime dependency. No `_linalg` / `_stats` expansion (reuses
`standard_normal_cdf` verbatim). Deterministic exact-`Decimal` throughout.
