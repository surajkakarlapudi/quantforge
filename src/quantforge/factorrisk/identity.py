"""The content-addressed identities for the factor-risk layer (§10).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical sealed inputs reproduces every id,
on any machine - the identical construction Phase 17's
:mod:`quantforge.attribution.identity` and Phase 19's
:mod:`quantforge.factorportfolio.identity` use, with a fresh domain tag so a Phase 20 id
can never collide with a lower-layer one.

The engine-version id (``factor_risk_engine_version_id``) is **not** computed here: it
is a property of :class:`~quantforge.factorrisk.version.FactorRiskEngineVersion` (it
folds the pinned decimal context and the formula-method version, exactly as
:class:`~quantforge.attribution.version.AttributionEngineVersion` does), so there is a
single source of truth for it, never a second competing implementation.

Like Phase 17 (and unlike Phase 19, which references the raw corpora by their corpus
pin), Phase 20 references *sealed artifacts* - the *N*
:class:`~quantforge.factorportfolio.result.FactorPortfolio` records - by their
``result_hash``, folded in **request order**. A ``FactorPortfolio``'s ``result_hash``
already content-addresses its full computed answer (its per-period factor-return panel
and summary), and its ``factor_portfolio_id`` in turn folds that ``result_hash``; so
folding each factor's ``result_hash`` here makes the risk model's id **transitively**
sensitive to any change in any referenced factor (FR-1).

The ids, and what each pins (§10):

    factor_risk_result_hash = sha256( canonical JSON over the ordered computed-output
                                    cells: the per-factor moment block (mean,
                                    volatility, annualized volatility) in factor order,
                                    then the
                                    upper-triangle covariance cells (i<=j), then the
                                    upper-triangle correlation cells (i<=j), each
                                    reduced to its canonical cell form )
                            - sensitive to every computed statistic.
    factor_risk_id = sha256( domain "factorrisk/1", factor_risk_engine_version_id, name,
                                    spec_version, the ORDERED factor_portfolio_id list,
                                    periods_per_year, the ORDERED factor result_hashes,
                                    factor_risk_result_hash )
                            - so the id is sensitive to any change in the request, any
                              referenced factor, the factor order, the annualization
                              convention, or the computed answer. Honestly
                              self-verifying.

``research_result_id`` aliases ``factor_risk_id`` (a single id - the risk model, like an
attribution record, is a value record whose id already folds its output). Both factor
lists are folded in **request order** (not sorted): order is semantic - it fixes the
matrix row/column order and the ``factor_1..factor_N`` labels - so ``(A, B)`` and
``(B, A)`` are distinct requests with distinct ids.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "factor_risk_id",
    "factor_risk_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``factorrisk-engine/1`` tag lives on the version dataclass; here only the record tag.
_FACTORRISK_DOMAIN = "factorrisk/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def factor_risk_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (the per-factor moment cells
    in factor order, then the upper-triangle covariance cells for ``i <= j``, then the
    upper-triangle correlation cells for ``i <= j``), each tagged by its block and
    reduced to a canonical dict, serialized with the canonical-JSON discipline so equal
    answers always yield identical bytes. Sensitive to every computed value: a single
    differing cell changes it. The coverage summary is **not** folded (it is audit
    metadata fully determined by the inputs).
    """
    return _sha256(_canonical_json(output_cells))


def factor_risk_id(
    *,
    factor_risk_engine_version_id: str,
    name: str,
    spec_version: str,
    factor_portfolio_ids: list[str],
    periods_per_year: str,
    factor_result_hashes: list[str],
    result_hash: str,
) -> str:
    """The identity of a whole factor-risk record - request, inputs **and** answer
    (§10).

    Folds the engine-logic + formula + decimal-context version
    (``factor_risk_engine_version_id``), the declared request (name, spec version, the
    **ordered** ``factor_portfolio_id`` list, and the ``periods_per_year`` annualization
    convention), the **referenced content hashes** (each factor's ``result_hash`` in the
    same order, so the id is transitively sensitive to any change in any sealed input),
    and the sealed ``factor_risk_result_hash`` over the computed answer. Same request +
    same sealed inputs => same id on any machine; a change to *any* fold yields a
    different id, never a silently different record under the same id (FR-1).

    Both factor lists are folded as ordered JSON arrays - order is semantic (it fixes
    the matrix row/column order and the factor labels), so it is preserved, never
    sorted.
    """
    payload = _SEP.join(
        (
            _FACTORRISK_DOMAIN,
            factor_risk_engine_version_id,
            name,
            spec_version,
            _canonical_json(factor_portfolio_ids),
            periods_per_year,
            _canonical_json(factor_result_hashes),
            result_hash,
        )
    )
    return _sha256(payload)
