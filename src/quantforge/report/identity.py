"""The content-addressed identities for the research-reporting layer (locked §9).

Every identity here follows the project's §11 discipline verbatim — ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``,
or iteration order. Re-declaring the identical report request over the identical sidecar
reproduces every id, on any machine — the identical construction the Phase 13
:mod:`quantforge.experiment.identity` uses, with fresh domain tags so a Phase 14 id can
never collide with a lower-layer one.

The reporting layer performs **no** numeric derivation (it only aggregates
already-sealed strings), so ``report_engine_version_id`` folds only its domain tag — the
experiment-engine pattern, not the decimal-context ``*EngineVersion`` dataclass pattern.

The ids, and what each pins (locked §9):

    report_reference_digest = { kind, reference_id, content_hash, detail }
                              — the per-reference fingerprint sealed into result_hash;
                                because content_hash is the referenced record's
                                result_hash (or a comparison's comparison_id), sealing
                                the digest is equivalent to sealing the referenced
                                content: any drift in a referenced artifact changes it.
    report_result_hash      = sha256( canonical JSON of
                                       {"report-reference/1": ordered digests} )
    report_id               = sha256( domain "report/1", name, spec_version, scope,
                                       subject_id,
                                       canonical JSON of the sorted (kind, id) reference
                                       descriptors,
                                       canonical JSON of the sorted (statistic, order)
                                       comparison directives )
                              — the REQUEST identity (declaration + which artifacts).
    report_result_id        = sha256( report_id, report_engine_version_id, result_hash )
                              — the sidecar key, aliased to research_result_id.
    report_engine_version_id = sha256( domain "report-engine/1" )

``report_id`` folds every input that can materially change *what research is reported*:
the report name, the spec-schema version, the top-level scope, the subject id, every
referenced record id (as a sorted set of ``(kind, id)`` descriptors), and every
comparison directive (as a sorted set of ``(statistic, order)`` pairs). Via
``result_hash`` it is additionally sensitive to every referenced record's own
``result_hash`` / ``comparison_id`` — so a report's identity changes iff the research it
reports on, or the reporting intent, changes. It deliberately folds **no** presentation,
schema/format version, wall clock, RNG, or object identity (locked D2, D9): a heading
change or a renderer edit can never change ``report_id``.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "report_engine_version_id",
    "report_id",
    "report_reference_digest",
    "report_result_hash",
    "report_result_id",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a canonical-JSON payload, or a decimal string, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tags. A new tag (or a bump) yields distinct ids without altering any
# already-computed id — the extensibility discipline shared with every prior phase.
_REPORT_DOMAIN = "report/1"
_REPORT_REFERENCE_DOMAIN = "report-reference/1"
_REPORT_ENGINE_DOMAIN = "report-engine/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def report_reference_digest(
    *,
    kind: str,
    reference_id: str,
    content_hash: str,
    detail: dict[str, object],
) -> dict[str, object]:
    """The per-reference fingerprint sealed into ``result_hash`` (locked §9).

    A canonical dict of the four identity-bearing fields of a
    :class:`~quantforge.report.result.ReportReference`. ``content_hash`` is the
    referenced record's ``result_hash`` (for a ``backtest`` / ``experiment``) or the
    recomputed ``comparison_id`` (for a ``comparison``); folding it makes the report
    identity sensitive to *any* change in *any* referenced artifact. ``detail`` is the
    reporting intent (empty for a record reference; the ``statistic`` / ``order`` /
    ``member_scope`` / ``comparison_version_id`` for a comparison), copied verbatim so
    equal references always digest identically.
    """
    return {
        "kind": kind,
        "reference_id": reference_id,
        "content_hash": content_hash,
        "detail": dict(detail),
    }


def report_result_hash(ordered_reference_digests: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered reference digests (locked §9).

    ``ordered_reference_digests`` is the report's references in their stored order, each
    a :func:`report_reference_digest`; serialized with the canonical-JSON discipline
    under the reference domain tag so equal manifests always yield identical bytes.
    Sensitive to every referenced content hash: a single drifted artifact changes it.
    """
    return _sha256(
        _canonical_json({_REPORT_REFERENCE_DOMAIN: ordered_reference_digests})
    )


def report_id(
    *,
    name: str,
    spec_version: str,
    scope: str,
    subject_id: str,
    sorted_reference_descriptors: list[list[str]],
    comparison_directives: list[list[str]],
) -> str:
    """The identity of the report *request* — declaration **and** referenced set (§9).

    Folds the report name, the specification-schema version, the top-level scope, the
    subject id, the sorted ``(kind, reference_id)`` descriptors of every reference (a
    *set* identity, so reference order never changes the id), and the sorted
    ``(statistic, order)`` comparison directives. It folds **no** presentation, schema
    version, or time (locked D2, D9). Same declaration + same referenced artifacts ⇒
    same id on any machine.
    """
    payload = _SEP.join(
        (
            _REPORT_DOMAIN,
            name,
            spec_version,
            scope,
            subject_id,
            _canonical_json(sorted_reference_descriptors),
            _canonical_json(comparison_directives),
        )
    )
    return _sha256(payload)


def report_result_id(
    *, report_id: str, report_engine_version_id: str, result_hash: str
) -> str:
    """``sha256(report_id, engine version, result_hash)`` — the sidecar key (§9).

    The :class:`~quantforge.report.result.ResearchReport`'s ``research_result_id``
    aliases this, so the record persists to the shared write-once sidecar with no new
    store (locked D1). It pins the request (``report_id``), the engine logic
    (``report_engine_version_id`` — a semantic input that *is* folded, D9), and the
    sealed manifest (``result_hash``).
    """
    payload = _SEP.join((report_id, report_engine_version_id, result_hash))
    return _sha256(payload)


def report_engine_version_id() -> str:
    """``sha256(domain "report-engine/1")`` — the engine-logic version (§9).

    The reporting layer performs no numeric derivation of its own (it references
    already-sealed artifacts and recomputes comparisons deterministically), so its
    version folds only the domain tag; a change to the reporting logic bumps the tag,
    yielding a distinct id without altering any already-computed one.
    """
    return _sha256(_REPORT_ENGINE_DOMAIN)
