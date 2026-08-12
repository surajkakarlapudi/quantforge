"""The content-addressed identities for the research-campaign layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim -
``sha256:`` prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and
**no** dependence on the wall clock, a random value, an object ``id()``, or
iteration order. Re-declaring the identical request over the identical sealed
trials reproduces every id on any machine - the identical construction Phase
20's :mod:`quantforge.factorrisk.identity` uses, with a fresh domain tag so a
Phase 23 id can never collide with a lower-layer one.

The engine-version id (``campaign_engine_version_id``) is **not** computed here:
it is a property of :class:`~quantforge.campaign.version.CampaignEngineVersion`
(it folds the pinned decimal context, the statistical-method version, and the
normal-primitive version), so there is a single source of truth for it, never a
second competing implementation.

Like Phase 20, Phase 23 references *sealed artifacts* - the ``N``
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` trials - by their
``result_hash``, folded in **request order**. A walk-forward record's ``result_hash``
already content-addresses its full out-of-sample answer, and its
``walk_forward_evaluation_id`` in turn folds that ``result_hash``; so folding
each trial's ``result_hash`` here makes the campaign's id **transitively**
sensitive to any change in any referenced trial (CE-1).

The ids, and what each pins (§10):

    campaign_result_hash = sha256( canonical JSON over the ordered
        computed-output cells: the per-trial statistic block (Sharpe, skew,
        kurtosis, PSR) in request order, then the campaign block (valid count,
        selected index, selected Sharpe, dispersion, expected-max Sharpe,
        deflated Sharpe), each reduced to its canonical cell form )
        - sensitive to every computed statistic.
    campaign_id = sha256( domain "campaign/1", campaign_engine_version_id, name,
        spec_version, the ORDERED trial_id list, benchmark_sharpe, the ORDERED
        trial result_hashes, campaign_result_hash )
        - so the id is sensitive to any change in the request, any referenced
          trial, the trial order, the benchmark, or the computed answer.
          Honestly self-verifying.

``research_result_id`` aliases ``campaign_id`` (a single id - the campaign
evaluation is a value record whose id already folds its output). Both trial
lists are folded in **request order** (not sorted): order is semantic - it fixes
the ``trial_1..trial_N`` labels, the selection index, and (as the count) the
size of the search - so ``(A, B)`` and ``(B, A)`` are distinct requests with
distinct ids.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "campaign_id",
    "campaign_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``campaign-engine/1`` tag lives on the version dataclass; here only the record tag.
_CAMPAIGN_DOMAIN = "campaign/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def campaign_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (the per-trial
    statistic cells in request order, then the single campaign-summary cell),
    each tagged by its block and reduced to a canonical dict, serialized with the
    canonical-JSON discipline so equal answers always yield identical bytes.
    Sensitive to every computed value: a single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def campaign_id(
    *,
    campaign_engine_version_id: str,
    name: str,
    spec_version: str,
    trial_ids: list[str],
    benchmark_sharpe: str,
    trial_result_hashes: list[str],
    result_hash: str,
) -> str:
    """The identity of a whole campaign record - request, inputs **and** answer (§10).

    Folds the engine-logic + method + normal + decimal-context version
    (``campaign_engine_version_id``), the declared request (name, spec version,
    the **ordered** ``trial_id`` list, and the canonical ``benchmark_sharpe``),
    the **referenced content hashes** (each trial's ``result_hash`` in the same
    order, so the id is transitively sensitive to any change in any sealed
    trial), and the sealed ``campaign_result_hash`` over the computed answer.
    Same request + same sealed trials => same id on any machine; a change to
    *any* fold yields a different id, never a silently different record under the
    same id (CE-1).

    Both trial lists are folded as ordered JSON arrays - order is semantic (it fixes the
    trial labels, the selection index, and the search size), so it is preserved, never
    sorted.
    """
    payload = _SEP.join(
        (
            _CAMPAIGN_DOMAIN,
            campaign_engine_version_id,
            name,
            spec_version,
            _canonical_json(trial_ids),
            benchmark_sharpe,
            _canonical_json(trial_result_hashes),
            result_hash,
        )
    )
    return _sha256(payload)
