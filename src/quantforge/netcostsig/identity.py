"""The content-addressed identities for the net-of-cost-significance layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical sealed net-of-cost record
reproduces every id on any machine - the identical construction
:mod:`quantforge.calsig.identity` uses, with a fresh domain tag so a Phase 32 id can
never collide with a lower-layer one.

The engine-version id (``net_of_cost_significance_engine_version_id``) is **not**
computed here: it is a property of
:class:`~quantforge.netcostsig.version.NetOfCostSignificanceEngineVersion` (it folds the
pinned decimal context, the statistical-method version, and the normal-primitive
version), so there is a single source of truth for it, never a second competing
implementation.

Like Phase 29, Phase 32 references a *sealed artifact* - exactly one
:class:`~quantforge.netcost.result.NetOfCostPerformance` - by its ``result_hash``. A
net-of-cost record's ``result_hash`` already content-addresses its full per-window
answer (and its ``net_of_cost_id`` in turn folds that ``result_hash`` and, transitively,
the stability / walk-forward / optimization / risk-model / factor chain beneath it); so
folding the source net-of-cost record's ``result_hash`` here makes the significance
test's id **transitively** sensitive to any change in the source net-of-cost record or
anything beneath it (NS-1).

The ids, and what each pins (§10):

    net_of_cost_significance_result_hash = sha256( canonical JSON over the ordered
        computed-output cells: the single aggregate significance summary block ) -
        sensitive to every computed statistic (net mean, standard error, t, p,
        direction, status).
    net_of_cost_significance_id = sha256( domain "netcostsig/1",
        net_of_cost_significance_engine_version_id, name, spec_version,
        source_net_of_cost_id, source_result_hash, null_mean_return,
        net_of_cost_significance_result_hash )
        - so the id is sensitive to any change in the request, the referenced
          net-of-cost record, the null mean tested, or the computed answer. Honestly
          self-verifying.

``research_result_id`` aliases ``net_of_cost_significance_id`` (a single id - the
significance is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "net_of_cost_significance_id",
    "net_of_cost_significance_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``netcostsig-engine/1`` tag lives on the version dataclass; here only the record tag.
_NETCOSTSIG_DOMAIN = "netcostsig/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def net_of_cost_significance_result_hash(
    output_cells: list[dict[str, object]],
) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (for Phase 32, the single
    aggregate significance summary), each tagged by its block and reduced to a canonical
    dict, serialized with the canonical-JSON discipline so equal answers always yield
    identical bytes. Sensitive to every computed statistic: a single differing cell
    changes it.
    """
    return _sha256(_canonical_json(output_cells))


def net_of_cost_significance_id(
    *,
    net_of_cost_significance_engine_version_id: str,
    name: str,
    spec_version: str,
    source_net_of_cost_id: str,
    source_result_hash: str,
    null_mean_return: str,
    result_hash: str,
) -> str:
    """The identity of a significance record - request, input **and** answer (§10).

    Folds the engine-logic + method + normal + decimal-context version
    (``net_of_cost_significance_engine_version_id``), the declared request (name, spec
    version), the **referenced content**: the source net-of-cost record's
    ``research_result_id`` and its ``result_hash`` (so the id is transitively sensitive
    to any change in the sealed net-of-cost record or anything beneath it), the
    ``NULL_MEAN_RETURN`` tested, and the sealed
    ``net_of_cost_significance_result_hash`` over the computed answer. Same request +
    same sealed net-of-cost record => same id on any machine; a change to *any* fold
    yields a different id, never a silently different record under the same id (NS-1).
    """
    payload = _SEP.join(
        (
            _NETCOSTSIG_DOMAIN,
            net_of_cost_significance_engine_version_id,
            name,
            spec_version,
            source_net_of_cost_id,
            source_result_hash,
            null_mean_return,
            result_hash,
        )
    )
    return _sha256(payload)
