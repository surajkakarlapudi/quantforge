"""The content-addressed identities for the net-of-cost layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``, or
iteration order. Re-declaring the identical request over the identical sealed stability
record reproduces every id on any machine - the identical construction
:mod:`quantforge.calsig.identity` uses, with a fresh domain tag so a Phase 31 id can
never collide with a lower-layer one.

The engine-version id (``net_of_cost_engine_version_id``) is **not** computed here: it
is a property of :class:`~quantforge.netcost.version.NetOfCostEngineVersion` (it folds
the pinned decimal context, the cost-accounting method version, and the reused Phase 19
series-summary version), so there is a single source of truth for it, never a second
competing implementation.

Phase 31 references a *sealed artifact* - exactly one
:class:`~quantforge.stability.result.WalkForwardStability` - by its ``result_hash``. A
stability record's ``result_hash`` already content-addresses its full per-window answer
(and its ``walk_forward_stability_id`` in turn folds that ``result_hash`` and,
transitively, the walk-forward / optimization / risk-model / factor chain beneath it);
so folding the source stability record's ``result_hash`` here makes the net-of-cost
verdict's id **transitively** sensitive to any change in the source stability record,
the walk-forward beneath it (whose gross returns Phase 31 consumes), or anything below
(NC-1).

The ids, and what each pins (§10):

    net_of_cost_result_hash = sha256( canonical JSON over the ordered computed-output
        cells: the coverage descriptor, the per-window net-cost cells in source window
        order, the excluded cells, then the aggregate net-of-cost summary block ) -
        sensitive to every computed value (per-window gross / turnover / cost / net,
        the net moments, the cost drag, the break-even rate, the roll-up status).
    net_of_cost_id = sha256( domain "netcost/1", net_of_cost_engine_version_id, name,
        spec_version, source_stability_id, source_result_hash, cost_rate,
        net_of_cost_result_hash )
        - so the id is sensitive to any change in the request, the referenced stability
          record (transitively the gross walk beneath it), the declared cost rate, or
          the computed answer. Honestly self-verifying.

``research_result_id`` aliases ``net_of_cost_id`` (a single id - the net-of-cost record
is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "net_of_cost_id",
    "net_of_cost_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``netcost-engine/1`` tag lives on the version dataclass; here only the record tag.
_NETCOST_DOMAIN = "netcost/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def net_of_cost_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (the coverage descriptor, the
    per-window net-cost cells, the excluded cells, then the aggregate net-of-cost
    summary), each tagged by its block and reduced to a canonical dict, serialized with
    the canonical-JSON discipline so equal answers always yield identical bytes.
    Sensitive to every computed value: a single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def net_of_cost_id(
    *,
    net_of_cost_engine_version_id: str,
    name: str,
    spec_version: str,
    source_stability_id: str,
    source_result_hash: str,
    cost_rate: str,
    result_hash: str,
) -> str:
    """The identity of a net-of-cost record - request, input **and** answer (§10).

    Folds the engine-logic + method + reused-summary + decimal-context version
    (``net_of_cost_engine_version_id``), the declared request (name, spec version), the
    **referenced content**: the source stability record's ``research_result_id`` and its
    ``result_hash`` (so the id is transitively sensitive to any change in the sealed
    stability record or the gross walk beneath it), the **declared** ``cost_rate`` (the
    modeling assumption, NC-3), and the sealed ``net_of_cost_result_hash`` over the
    computed answer. Same request + same sealed stability record => same id on any
    machine; a change to *any* fold yields a different id, never a silently different
    record under the same id (NC-1).
    """
    payload = _SEP.join(
        (
            _NETCOST_DOMAIN,
            net_of_cost_engine_version_id,
            name,
            spec_version,
            source_stability_id,
            source_result_hash,
            cost_rate,
            result_hash,
        )
    )
    return _sha256(payload)
