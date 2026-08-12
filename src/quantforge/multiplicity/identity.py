"""The content-addressed identities for the multiplicity-correction layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``, or
iteration order. Re-declaring the identical request over the identical sealed comparison
reproduces every id on any machine - the identical construction
:mod:`quantforge.comparison.identity` uses, with a fresh domain tag so a Phase 25 id can
never collide with a lower-layer one.

The engine-version id (``multiplicity_engine_version_id``) is **not** computed here: it
is a property of
:class:`~quantforge.multiplicity.version.MultipleComparisonEngineVersion` (it folds the
pinned decimal context and the statistical-method version), so there is a single source
of truth for it, never a second competing implementation.

Like Phase 24, Phase 25 references a *sealed artifact* - exactly one
:class:`~quantforge.comparison.result.StrategyComparison` - by its ``result_hash``. A
comparison record's ``result_hash`` already content-addresses its full pairwise answer
(and its ``strategy_comparison_id`` in turn folds that ``result_hash`` and,
transitively, every referenced walk-forward strategy); so folding the source
comparison's ``result_hash`` here makes the correction's id **transitively** sensitive
to any change in the source comparison or any strategy beneath it (MC-1).

The ids, and what each pins (§10):

    multiple_comparison_result_hash = sha256( canonical JSON over the ordered
        computed-output cells: the family descriptor (family size ``m``, excluded
        count), then each KNOWN family cell's ``(i, j, p_value)`` in source
        upper-triangle order, then each excluded cell's ``(i, j, reason)``, then per
        method the labels (error-rate, dependence) and each family cell's
        ``(i, j, p_adjusted, rejected)`` )
        - sensitive to every computed adjusted value and rejection flag.
    multiple_comparison_id = sha256( domain "multiplicity/1",
        multiplicity_engine_version_id, name, spec_version,
        source_strategy_comparison_id, source_result_hash, alpha, the ORDERED method
        list,
        multiple_comparison_result_hash )
        - so the id is sensitive to any change in the request, the referenced
          comparison, the significance level, the requested methods (or their order), or
          the computed answer. Honestly self-verifying.

``research_result_id`` aliases ``multiple_comparison_id`` (a single id - the correction
is a value record whose id already folds its output). The method list is folded in
**request order** (not sorted): the record reads back in the order the methods were
requested.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "multiple_comparison_id",
    "multiple_comparison_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``multiplicity-engine/1`` tag lives on the version dataclass; here only the record
# tag.
_MULTIPLICITY_DOMAIN = "multiplicity/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def multiple_comparison_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (the family descriptor, then
    the KNOWN family cells, then the excluded cells, then the per-method adjusted
    cells), each tagged by its block and reduced to a canonical dict, serialized with
    the canonical-JSON discipline so equal answers always yield identical bytes.
    Sensitive to every computed adjusted value and rejection flag: a single differing
    cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def multiple_comparison_id(
    *,
    multiplicity_engine_version_id: str,
    name: str,
    spec_version: str,
    source_strategy_comparison_id: str,
    source_result_hash: str,
    alpha: str,
    methods: list[str],
    result_hash: str,
) -> str:
    """The identity of a whole correction record - request, input **and** answer (§10).

    Folds the engine-logic + method + decimal-context version
    (``multiplicity_engine_version_id``), the declared request (name, spec version), the
    **referenced content**: the source comparison's ``research_result_id`` and its
    ``result_hash`` (so the id is transitively sensitive to any change in the sealed
    comparison or any strategy beneath it), the declared ``alpha``, the **ordered**
    method list, and the sealed ``multiple_comparison_result_hash`` over the computed
    answer. Same request + same sealed comparison => same id on any machine; a change to
    *any* fold yields a different id, never a silently different record under the same
    id (MC-1).

    The method list is folded as an ordered JSON array - it reads back in request order,
    so a differently-ordered request is a distinct record.
    """
    payload = _SEP.join(
        (
            _MULTIPLICITY_DOMAIN,
            multiplicity_engine_version_id,
            name,
            spec_version,
            source_strategy_comparison_id,
            source_result_hash,
            alpha,
            _canonical_json(methods),
            result_hash,
        )
    )
    return _sha256(payload)
