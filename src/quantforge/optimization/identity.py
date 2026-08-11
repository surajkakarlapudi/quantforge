"""The content-addressed identities for the portfolio-optimization layer (§13).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical sealed risk model reproduces every
id, on any machine - the identical construction the factor-risk / attribution layers
use, with a fresh domain tag so a Phase 21 id can never collide with a lower-layer one.

The engine-version id (``optimization_engine_version_id``) is **not** computed here: it
is a property of
:class:`~quantforge.optimization.version.PortfolioOptimizationEngineVersion` (it folds
the pinned decimal context and the solve-method version, exactly as
:class:`~quantforge.factorrisk.version.FactorRiskEngineVersion` does), so there is a
single source of truth for it, never a second competing implementation.

Like the factor-risk layer, Phase 21 references a *sealed artifact* - the one
:class:`~quantforge.factorrisk.result.FactorRiskModel` - by both its id and its
``result_hash``, folded in. A ``FactorRiskModel``'s ``result_hash`` content-addresses
its full computed answer (its covariance / correlation / moment cells), and its
``factor_risk_id`` in turn folds that ``result_hash``; so folding the referenced
``result_hash`` here makes the optimization's id **transitively** sensitive to any
change in the risk model - and, through it, in any referenced factor or corpus (PO-1).

The ids, and what each pins (§13):

    optimization_result_hash = sha256( canonical JSON over the ordered computed-output
                                    cells: the status, then the per-factor weight cells
                                    in factor order, then the portfolio variance and
                                    volatility, each reduced to its canonical cell )
                            - sensitive to every computed value.
    optimization_id = sha256( domain "optimization/1", optimization_engine_version_id,
                                    name, spec_version, objective, constraint_id (the
                                    canonical-JSON constraint spec), covariance_basis,
                                    factor_risk_id, factor_risk_result_hash,
                                    optimization_result_hash )
                            - so the id is sensitive to any change in the request, the
                              objective, the constraint spec, the covariance basis, the
                              referenced risk model (its request identity *and* its
                              answer), or the computed weights. Honestly self-verifying.

``research_result_id`` aliases ``optimization_id`` (a single id - the optimization, like
a risk model, is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "optimization_id",
    "optimization_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``optimization-engine/1`` tag lives on the version dataclass; here only the record
# tag.
_OPTIMIZATION_DOMAIN = "optimization/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def optimization_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§13).

    ``output_cells`` is the ordered list of computed cells (the status cell, then the
    per-factor weight cells in factor order, then the portfolio-variance and
    portfolio-volatility cells), each tagged by its block and reduced to a canonical
    dict, serialized with the canonical-JSON discipline so equal answers always yield
    identical bytes. Sensitive to every computed value: a single differing cell changes
    it.
    """
    return _sha256(_canonical_json(output_cells))


def optimization_id(
    *,
    optimization_engine_version_id: str,
    name: str,
    spec_version: str,
    objective: str,
    constraint_spec: dict[str, object],
    covariance_basis: str,
    factor_risk_id: str,
    factor_risk_result_hash: str,
    result_hash: str,
) -> str:
    """The identity of an optimization record - request, input **and** answer (§13).

    Folds the engine-logic + solve + decimal-context version
    (``optimization_engine_version_id``), the declared request (name, spec version,
    objective, and the canonical-JSON constraint spec), the covariance basis, the
    **referenced risk model** (its ``factor_risk_id`` request identity *and* its
    ``factor_risk_result_hash`` answer, so the id is transitively sensitive to any
    change in the risk model), and the sealed ``optimization_result_hash`` over the
    computed weights + variance. Same request + same sealed risk model => same id on any
    machine; a change to *any* fold yields a different id, never a silently different
    record under the same id (PO-1).

    The constraint spec is folded as canonical JSON (not a bare string), so a future
    richer constraint vocabulary hashes distinctly from the v1 ``{"fully_invested":
    true}`` without any collision.
    """
    payload = _SEP.join(
        (
            _OPTIMIZATION_DOMAIN,
            optimization_engine_version_id,
            name,
            spec_version,
            objective,
            _canonical_json(constraint_spec),
            covariance_basis,
            factor_risk_id,
            factor_risk_result_hash,
            result_hash,
        )
    )
    return _sha256(payload)
