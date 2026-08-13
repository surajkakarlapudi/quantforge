"""The content-addressed identities for the minimum-track-record-length layer
(§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any
structured payload, and **no** dependence on the wall clock, a random value, an
object ``id()``, or iteration order. Re-declaring the identical request over the
identical sealed campaign reproduces every id on any machine - the identical
construction :mod:`quantforge.calibration.identity` uses, with a fresh domain tag
so a Phase 28 id can never collide with a lower-layer one.

The engine-version id (``minimum_track_record_length_engine_version_id``) is
**not** computed here: it is a property of
:class:`~quantforge.mintrl.version.MinimumTrackRecordLengthEngineVersion` (it
folds the pinned decimal context, the statistical-method version, and the
normal-primitive version), so there is a single source of truth for it, never a
second competing implementation.

Like Phase 26, Phase 28 references a *sealed artifact* - exactly one
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation` - by its
``result_hash``. A campaign record's ``result_hash`` already content-addresses
its full per-trial answer (and its ``campaign_id`` in turn folds that
``result_hash`` and, transitively, the walk-forward / optimization / risk-model /
factor chain beneath it); so folding the source campaign's ``result_hash`` here
makes the MinTRL evaluation's id **transitively** sensitive to any change in the
source campaign or anything beneath it (MT-1).

The ids, and what each pins (§10):

    minimum_track_record_length_result_hash = sha256( canonical JSON over the ordered
        computed-output cells: the coverage descriptor (trial / evaluable / excluded
        counts), then each evaluable trial's ``(label, observed_length, sharpe, skew,
        kurtosis, min_track_record_length, excess_length)`` in source order, then each
        excluded trial's ``(label, reason)``, then the aggregate MinTRL summary ) -
        sensitive to every computed length and aggregate.
    minimum_track_record_length_id = sha256( domain "mintrl/1",
        minimum_track_record_length_engine_version_id, name, spec_version,
        source_campaign_id, source_result_hash, confidence, benchmark_sharpe,
        min_determined_trials, minimum_track_record_length_result_hash )
        - so the id is sensitive to any change in the request (including the
          confidence and benchmark), the referenced campaign, the determined-trials
          floor, or the computed answer. Honestly self-verifying.

``research_result_id`` aliases ``minimum_track_record_length_id`` (a single id - the
evaluation is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "minimum_track_record_length_id",
    "minimum_track_record_length_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11);
# it cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload,
# so a joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior
# phase. The ``mintrl-engine/1`` tag lives on the version dataclass; here only
# the record tag.
_MINTRL_DOMAIN = "mintrl/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def minimum_track_record_length_result_hash(
    output_cells: list[dict[str, object]],
) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal
    (§10).

    ``output_cells`` is the ordered list of computed cells (the coverage
    descriptor, then the evaluable-trial cells, then the excluded-trial cells,
    then the aggregate summary), each tagged by its block and reduced to a
    canonical dict, serialized with the canonical-JSON discipline so equal answers
    always yield identical bytes. Sensitive to every computed length and aggregate:
    a single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def minimum_track_record_length_id(
    *,
    minimum_track_record_length_engine_version_id: str,
    name: str,
    spec_version: str,
    source_campaign_id: str,
    source_result_hash: str,
    confidence: str,
    benchmark_sharpe: str,
    min_determined_trials: int,
    result_hash: str,
) -> str:
    """The identity of a whole MinTRL record - request, input **and** answer (§10).

    Folds the engine-logic + method + normal + decimal-context version
    (``minimum_track_record_length_engine_version_id``), the declared request
    (name, spec version, the canonical ``confidence`` and ``benchmark_sharpe``),
    the **referenced content**: the source campaign's ``research_result_id`` and
    its ``result_hash`` (so the id is transitively sensitive to any change in the
    sealed campaign or anything beneath it), the ``MIN_DETERMINED_TRIALS`` floor
    that governs ``mintrl_status``, and the sealed
    ``minimum_track_record_length_result_hash`` over the computed answer. Same
    request + same sealed campaign => same id on any machine; a change to *any*
    fold yields a different id, never a silently different record under the same id
    (MT-1).
    """
    payload = _SEP.join(
        (
            _MINTRL_DOMAIN,
            minimum_track_record_length_engine_version_id,
            name,
            spec_version,
            source_campaign_id,
            source_result_hash,
            confidence,
            benchmark_sharpe,
            str(min_determined_trials),
            result_hash,
        )
    )
    return _sha256(payload)
