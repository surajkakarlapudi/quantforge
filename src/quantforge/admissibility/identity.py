"""The content-addressed identities for the strategy-admissibility layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical three sealed verdicts reproduces
every id on any machine - the identical construction
:mod:`quantforge.netcostsig.identity` uses, with a fresh domain tag so a Phase 33 id can
never collide with a lower-layer one.

The engine-version id (``admissibility_engine_version_id``) is **not** computed here: it
is a property of
:class:`~quantforge.admissibility.version.AdmissibilityEngineVersion` (it folds the
pinned decimal context and the decision-method version), so there is a single source of
truth for it, never a second competing implementation.

Phase 33 references **three** sealed artifacts - a
:class:`~quantforge.stability.result.WalkForwardStability`, a
:class:`~quantforge.calsig.result.CalibrationSignificance`, and a
:class:`~quantforge.netcostsig.result.NetOfCostSignificance` - each by its
``result_hash``. Each of those hashes already content-addresses its full answer (and
transitively its walk-forward / campaign chain beneath it); so folding all three
``result_hash`` values here makes the admissibility verdict's id **transitively**
sensitive to any change in any consumed verdict or anything beneath it (AD-1).

The ids, and what each pins (§10):

    admissibility_result_hash = sha256( canonical JSON over the ordered computed-output
        cells: the single admissibility summary block - the verdict, alpha, and the
        three ordered criteria ) - sensitive to the verdict and every per-criterion
        status.
    admissibility_id = sha256( domain "admissibility/1",
        admissibility_engine_version_id, name, spec_version, source_stability_id,
        source_stability_result_hash, source_calibration_significance_id,
        source_calibration_result_hash, source_net_of_cost_significance_id,
        source_net_of_cost_result_hash, alpha, admissibility_result_hash )
        - so the id is sensitive to any change in the request, any referenced verdict,
          the declared level, or the computed answer. Honestly self-verifying.

``research_result_id`` aliases ``admissibility_id`` (a single id - the admissibility is
a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "admissibility_id",
    "admissibility_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``admissibility-engine/1`` tag lives on the version dataclass; here only the record
# tag.
_ADMISSIBILITY_DOMAIN = "admissibility/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def admissibility_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (for Phase 33, the single
    admissibility summary block: the verdict, the declared alpha, and the three ordered
    criteria), each tagged by its block and reduced to a canonical dict, serialized with
    the canonical-JSON discipline so equal answers always yield identical bytes.
    Sensitive to the verdict and every per-criterion status: a single differing cell
    changes it.
    """
    return _sha256(_canonical_json(output_cells))


def admissibility_id(
    *,
    admissibility_engine_version_id: str,
    name: str,
    spec_version: str,
    source_stability_id: str,
    source_stability_result_hash: str,
    source_calibration_significance_id: str,
    source_calibration_result_hash: str,
    source_net_of_cost_significance_id: str,
    source_net_of_cost_result_hash: str,
    alpha: str,
    result_hash: str,
) -> str:
    """The identity of an admissibility record - request, inputs **and** answer (§10).

    Folds the engine-logic + method + decimal-context version
    (``admissibility_engine_version_id``), the declared request (name, spec version),
    the **referenced content**: each of the three source verdicts'
    ``research_result_id`` and ``result_hash`` (so the id is transitively sensitive to
    any change in any consumed verdict or anything beneath it), the declared ``alpha``,
    and the sealed ``admissibility_result_hash`` over the computed answer. Same request
    + same three sealed verdicts => same id on any machine; a change to *any* fold
    yields a different id, never a silently different record under the same id (AD-1).
    """
    payload = _SEP.join(
        (
            _ADMISSIBILITY_DOMAIN,
            admissibility_engine_version_id,
            name,
            spec_version,
            source_stability_id,
            source_stability_result_hash,
            source_calibration_significance_id,
            source_calibration_result_hash,
            source_net_of_cost_significance_id,
            source_net_of_cost_result_hash,
            alpha,
            result_hash,
        )
    )
    return _sha256(payload)
