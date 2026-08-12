"""The content-addressed identities for the walk-forward-evaluation layer (§13).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical sealed optimization reproduces
every id, on any machine - the identical construction the optimization / factor-risk
layers use, with a fresh domain tag so a Phase 22 id can never collide with a
lower-layer one.

The engine-version id (``walk_forward_engine_version_id``) is **not** computed here: it
is a property of :class:`~quantforge.walkforward.version.WalkForwardEngineVersion` (it
folds the pinned decimal context and the four composed method versions), so there is a
single source of truth for it, never a second competing implementation.

Like the optimization layer, Phase 22 references a *sealed artifact* - the one
:class:`~quantforge.optimization.result.PortfolioOptimization` recipe - by both its id
and its ``result_hash``, folded in. An optimization's ``result_hash`` content-addresses
its full computed answer (its GMV weights + variance), and its ``optimization_id`` in
turn folds *its* referenced risk model's ``result_hash``; so folding the referenced
``result_hash`` here makes the walk-forward evaluation's id **transitively** sensitive
to any change in the optimization - and, through it, in the risk model, any factor, or
the corpus (WF-1). The inherited ``schedule_id`` (the rebalance calendar the factors
were built on) is also folded, preserving the proposal §13 schedule-pinning intent even
though Phase 22 takes no separate schedule input.

The ids, and what each pins (§13):

    walk_forward_result_hash = sha256( canonical JSON over the ordered computed-output
                                    cells: each window block in schedule order, then the
                                    chained OOS return series, then the summary block,
                                    then the aggregate realized-variance cell )
- sensitive to every computed value. walk_forward_id = sha256( domain "walkforward/1",
  walk_forward_engine_version_id, name, spec_version, canonical-JSON training_policy,
  schedule_id, optimization_id, optimization_result_hash, walk_forward_result_hash )
- so the id is sensitive to any change in the request, the training policy, the
  inherited rebalance calendar, the referenced optimization (its request identity *and*
  its answer), or the computed walk. Honestly self-verifying.

``research_result_id`` aliases ``walk_forward_id`` (a single id - the evaluation, like
an optimization, is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "walk_forward_id",
    "walk_forward_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``walkforward-engine/1`` tag lives on the version dataclass; here only the record tag.
_WALKFORWARD_DOMAIN = "walkforward/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def walk_forward_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§13).

    ``output_cells`` is the ordered list of computed cells (each window block in
    schedule order, then the chained OOS return series, then the summary block, then the
    aggregate realized-variance cell), each tagged by its block and reduced to a
    canonical dict, serialized with the canonical-JSON discipline so equal answers
    always yield identical bytes. Sensitive to every computed value: a single differing
    cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def walk_forward_id(
    *,
    walk_forward_engine_version_id: str,
    name: str,
    spec_version: str,
    training_policy: dict[str, object],
    schedule_id: str,
    optimization_id: str,
    optimization_result_hash: str,
    result_hash: str,
) -> str:
    """The identity of a walk-forward evaluation - request, input **and** answer (§13).

    Folds the engine-logic + composed-method + decimal-context version
    (``walk_forward_engine_version_id``), the declared request (name, spec version, and
    the canonical-JSON training policy), the inherited ``schedule_id`` (the rebalance
    calendar the factors were built on), the **referenced optimization** (its
    ``optimization_id`` request identity *and* its ``optimization_result_hash`` answer,
    so the id is transitively sensitive to any change in the optimization - and, through
    it, the risk model, factors, or corpus), and the sealed ``walk_forward_result_hash``
    over the computed walk. Same request + same sealed optimization => same id on any
    machine; a change to *any* fold yields a different id, never a silently different
    record under the same id (WF-1).

    The training policy is folded as canonical JSON (not a bare string), so a future
    richer policy vocabulary hashes distinctly from the v1 shape without any collision.
    """
    payload = _SEP.join(
        (
            _WALKFORWARD_DOMAIN,
            walk_forward_engine_version_id,
            name,
            spec_version,
            _canonical_json(training_policy),
            schedule_id,
            optimization_id,
            optimization_result_hash,
            result_hash,
        )
    )
    return _sha256(payload)
