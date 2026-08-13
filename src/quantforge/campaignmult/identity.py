"""The content-addressed identities for the campaign-multiplicity layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``, or
iteration order. Re-declaring the identical request over the identical sealed campaign
reproduces every id on any machine - the identical construction
:mod:`quantforge.multiplicity.identity` uses, with a fresh domain tag so a Phase 30 id
can never collide with a lower-layer one.

The engine-version id (``campaign_multiplicity_engine_version_id``) is **not** computed
here: it is a property of
:class:`~quantforge.campaignmult.version.CampaignMultiplicityEngineVersion` (it folds
the pinned decimal context, Phase 30's own method version, and the reused
correction-core version), so there is a single source of truth for it, never a second
competing implementation.

Like Phase 25, Phase 30 references a *sealed artifact* - exactly one
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation` - by its
``result_hash``. A campaign record's ``result_hash`` already content-addresses its full
per-trial answer (and its ``campaign_id`` in turn folds that ``result_hash`` and,
transitively, every referenced walk-forward trial); so folding the source campaign's
``result_hash`` here makes the correction's id **transitively** sensitive to any change
in the source campaign or any trial beneath it (CM-1).

The ids, and what each pins (§10):

    campaign_multiplicity_result_hash = sha256( canonical JSON over the ordered
        computed-output cells: the family descriptor (family size ``m``, excluded
        count), then each KNOWN family cell's ``(index, label, psr, p_value)`` in source
        trial order, then each excluded cell's ``(index, label, reason)``, then per
        method the labels (error-rate, dependence) and each family cell's ``(index,
        p_adjusted, rejected)`` )
        - sensitive to every consumed ``PSR``, every derived ``p`` value, every computed
          adjusted value, and every rejection flag.
    campaign_multiplicity_id = sha256( domain "campaignmult/1",
        campaign_multiplicity_engine_version_id, name, spec_version, source_campaign_id,
        source_result_hash, alpha, the ORDERED method list,
        campaign_multiplicity_result_hash )
        - so the id is sensitive to any change in the request, the referenced campaign,
          the significance level, the requested methods (or their order), or the
          computed answer. Honestly self-verifying.

``research_result_id`` aliases ``campaign_multiplicity_id`` (a single id - the
correction is a value record whose id already folds its output). The method list is
folded in **request order** (not sorted): the record reads back in the order the methods
were requested.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "campaign_multiplicity_id",
    "campaign_multiplicity_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``campaignmult-engine/1`` tag lives on the version dataclass; here only the record
# tag.
_CAMPAIGNMULT_DOMAIN = "campaignmult/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def campaign_multiplicity_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (the family descriptor, then
    the KNOWN family cells, then the excluded cells, then the per-method adjusted
    cells), each tagged by its block and reduced to a canonical dict, serialized with
    the canonical-JSON discipline so equal answers always yield identical bytes.
    Sensitive to every consumed ``PSR``, derived ``p`` value, computed adjusted value,
    and rejection flag: a single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def campaign_multiplicity_id(
    *,
    campaign_multiplicity_engine_version_id: str,
    name: str,
    spec_version: str,
    source_campaign_id: str,
    source_result_hash: str,
    alpha: str,
    methods: list[str],
    result_hash: str,
) -> str:
    """The identity of a whole correction record - request, input **and** answer (§10).

    Folds the engine-logic + method + correction + decimal-context version
    (``campaign_multiplicity_engine_version_id``), the declared request (name, spec
    version), the **referenced content**: the source campaign's ``research_result_id``
    and its ``result_hash`` (so the id is transitively sensitive to any change in the
    sealed campaign or any trial beneath it), the declared ``alpha``, the **ordered**
    method list, and the sealed ``campaign_multiplicity_result_hash`` over the computed
    answer. Same request + same sealed campaign => same id on any machine; a change to
    *any* fold yields a different id, never a silently different record under the same
    id (CM-1).

    The method list is folded as an ordered JSON array - it reads back in request order,
    so a differently-ordered request is a distinct record.
    """
    payload = _SEP.join(
        (
            _CAMPAIGNMULT_DOMAIN,
            campaign_multiplicity_engine_version_id,
            name,
            spec_version,
            source_campaign_id,
            source_result_hash,
            alpha,
            _canonical_json(methods),
            result_hash,
        )
    )
    return _sha256(payload)
