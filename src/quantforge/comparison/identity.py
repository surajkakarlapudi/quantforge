"""The content-addressed identities for the strategy-comparison layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``, or
iteration order. Re-declaring the identical request over the identical sealed strategies
reproduces every id on any machine - the identical construction
:mod:`quantforge.campaign.identity` uses, with a fresh domain tag so a Phase 24 id can
never collide with a lower-layer one.

The engine-version id (``strategy_comparison_engine_version_id``) is **not** computed
here: it is a property of
:class:`~quantforge.comparison.version.StrategyComparisonEngineVersion` (it folds the
pinned decimal context, the statistical-method version, and the normal-primitive
version), so there is a single source of truth for it, never a second competing
implementation.

Like Phase 23, Phase 24 references *sealed artifacts* - the ``N``
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` strategies - by their
``result_hash``, folded in **request order**. A walk-forward record's ``result_hash``
already content-addresses its full out-of-sample answer (and its per-window ranges,
which drive the date reconstruction), and its ``walk_forward_id`` in turn folds that
``result_hash``; so folding each strategy's ``result_hash`` here makes the comparison's
id **transitively** sensitive to any change in any referenced strategy (SC-1) - the
guarantee that lets a comparison reference the reconstructed (non-hashed) per-window OOS
returns without weakening identity.

The ids, and what each pins (§10):

    strategy_comparison_result_hash = sha256( canonical JSON over the ordered
        computed-output cells: the per-strategy summary block (label, Sharpe, valid
        period count, reconstructed axis length) in request order, then the pairwise
        block (each upper-triangle cell's paired-difference statistics), each reduced to
        its canonical cell form )
        - sensitive to every computed statistic.
    strategy_comparison_id = sha256( domain "comparison/1",
        strategy_comparison_engine_version_id, name, spec_version, the ORDERED
        walk_forward_id list, the ORDERED strategy result_hashes, periods_per_year,
        strategy_comparison_result_hash )
        - so the id is sensitive to any change in the request, any referenced strategy,
          the strategy order, the shared annualization convention, or the computed
          answer. Honestly self-verifying.

``research_result_id`` aliases ``strategy_comparison_id`` (a single id - the comparison
is a value record whose id already folds its output). Both strategy lists are folded in
**request order** (not sorted): order is semantic - it fixes the ``strategy_1..N``
labels and the upper-triangle pair order - so ``(A, B)`` and ``(B, A)`` are distinct
requests with distinct ids.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "strategy_comparison_id",
    "strategy_comparison_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``comparison-engine/1`` tag lives on the version dataclass; here only the record tag.
_COMPARISON_DOMAIN = "comparison/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def strategy_comparison_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (the per-strategy summary
    cells in request order, then the upper-triangle pairwise cells), each tagged by its
    block and reduced to a canonical dict, serialized with the canonical-JSON discipline
    so equal answers always yield identical bytes. Sensitive to every computed value: a
    single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def strategy_comparison_id(
    *,
    strategy_comparison_engine_version_id: str,
    name: str,
    spec_version: str,
    walk_forward_ids: list[str],
    strategy_result_hashes: list[str],
    periods_per_year: str,
    result_hash: str,
) -> str:
    """The identity of a whole comparison record - request, inputs **and** answer (§10).

    Folds the engine-logic + method + normal + decimal-context version
    (``strategy_comparison_engine_version_id``), the declared request (name, spec
    version, the **ordered** ``walk_forward_id`` list), the **referenced content
    hashes** (each strategy's ``result_hash`` in the same order, so the id is
    transitively sensitive to any change in any sealed strategy), the shared
    ``periods_per_year`` (the annualization convention the commensurability contract
    pins), and the sealed ``strategy_comparison_result_hash`` over the computed answer.
    Same request + same sealed strategies => same id on any machine; a change to *any*
    fold yields a different id, never a silently different record under the same id
    (SC-1).

    Both strategy lists are folded as ordered JSON arrays - order is semantic (it fixes
    the strategy labels and the upper-triangle pair order), so it is preserved, never
    sorted.
    """
    payload = _SEP.join(
        (
            _COMPARISON_DOMAIN,
            strategy_comparison_engine_version_id,
            name,
            spec_version,
            _canonical_json(walk_forward_ids),
            _canonical_json(strategy_result_hashes),
            periods_per_year,
            result_hash,
        )
    )
    return _sha256(payload)
