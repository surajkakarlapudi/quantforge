"""The content-addressed identities for the factor-portfolio layer (§5.4, §5.6).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical pinned corpora reproduces every
id, on any machine - the identical construction Phase 16's
:mod:`quantforge.diagnostics.identity` and Phase 18's
:mod:`quantforge.crosssection.identity` use, with a fresh domain tag so a Phase 19 id
can never collide with a lower-layer one.

The engine-version id (``factor_portfolio_engine_version_id``) is **not** computed here:
it is a property of
:class:`~quantforge.factorportfolio.version.FactorPortfolioEngineVersion` (it folds the
pinned decimal context and the formula-method version), so there is a single source of
truth for it, never a second competing implementation.

Like Phase 16 (and unlike Phase 17, which references sealed backtests by their
``result_hash``), Phase 19 reads the **raw corpora** and references them by **corpus
pin** - the content-addressed fundamentals ``dataset_version_id`` and market
``market_dataset_version_id`` - so the id stays sensitive to any corpus change without
folding a sealed artifact hash.

The ids, and what each pins (§5.4, §5.6):

    factor_portfolio_result_hash = sha256( canonical JSON over the ordered computed
                                    outputs: the per-period factor-return panel
                                    (schedule order), then the aggregated summary block,
                                    each reduced to its canonical cell form )
                            - sensitive to every computed statistic.
    factor_portfolio_id = sha256( domain "factorportfolio/1",
                                    factor_portfolio_engine_version_id, name,
                                    spec_version, signal, period_key, universe
                                    specification_id, schedule_id, horizon_days,
                                    quantiles, weighting, risk_free_per_period,
                                    periods_per_year, both corpus pins, and
                                    factor_portfolio_result_hash )
                            - so the id is sensitive to any change in the request,
                              either corpus, or the computed answer. Honestly
                              self-verifying.

``research_result_id`` aliases ``factor_portfolio_id`` (a single id - the factor
portfolio, like a diagnostic, is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "factor_portfolio_id",
    "factor_portfolio_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``factorportfolio-engine/1`` tag lives on the version dataclass; here only the record
# tag.
_FACTORPORTFOLIO_DOMAIN = "factorportfolio/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def factor_portfolio_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§5.6).

    ``output_cells`` is the ordered list of computed-statistic cells (each a canonical
    dict, in the record's stored order: the per-period factor-return block in schedule
    order, then the summary block), serialized with the canonical-JSON discipline so
    equal answers always yield identical bytes. Sensitive to every computed statistic: a
    single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def factor_portfolio_id(
    *,
    factor_portfolio_engine_version_id: str,
    name: str,
    spec_version: str,
    signal: str,
    period_key: str,
    universe_specification_id: str,
    schedule_id: str,
    horizon_days: int,
    quantiles: int,
    weighting: str,
    risk_free_per_period: str,
    periods_per_year: str,
    dataset_version_id: str,
    market_dataset_version_id: str,
    result_hash: str,
) -> str:
    """The identity of a whole factor-portfolio record - request, corpora +
    answer (§5.4).

    Folds the engine-logic + formula + decimal-context version
    (``factor_portfolio_engine_version_id``), the full declared request (name, spec
    version, the signal ``metric_key`` and its ``period_key``, the universe
    ``specification_id``, the evaluation ``schedule_id``, the forward-horizon
    trading-day count, the quantile count, the leg-weighting scheme, and the
    annualization convention - the canonicalized ``risk_free_per_period`` and
    ``periods_per_year``), **both** content-addressed corpus pins (fundamentals +
    market), and the sealed ``factor_portfolio_result_hash`` over the computed answer.
    Same request + same pinned corpora => same id on any machine; a change to *any* fold
    yields a different id, never a silently different record under the same id (P19-1).
    """
    payload = _SEP.join(
        (
            _FACTORPORTFOLIO_DOMAIN,
            factor_portfolio_engine_version_id,
            name,
            spec_version,
            signal,
            period_key,
            universe_specification_id,
            schedule_id,
            str(horizon_days),
            str(quantiles),
            weighting,
            risk_free_per_period,
            periods_per_year,
            dataset_version_id,
            market_dataset_version_id,
            result_hash,
        )
    )
    return _sha256(payload)
