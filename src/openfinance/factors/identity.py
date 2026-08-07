"""The content-addressed factor identities (``docs/factors.md`` §7).

Three deterministic hashes close the data-model §9 reproducibility loop for a
cross-sectional factor, composing with the existing Phase 5/7 pins:

    factor_definition_id = sha256( metric_key, formula_id, transform_id )
    result_hash          = sha256( canonical JSON of the ordered cell outcomes )
    research_result_id   = sha256( factor_definition_id, metric_engine_version_id,
                                   universe_id, period_key, boundary_key,
                                   result_hash )

``factor_definition_id`` maps onto data-model §9's reserved ``factor_definition_id``;
``metric_engine_version_id`` maps onto §9's reserved ``factor_version`` (§7). All
ids follow the §11 identity discipline verbatim: ``sha256:``-prefixed, NUL-joined
components, no wall-clock / RNG / iteration-order dependence. ``research_result_id``
pins the **request** (which factor definition, engine, universe, period, boundary)
**and** the **output** (via ``result_hash``), so re-running the same request
reproduces the same id and the same values — determinism made checkable (§12).
"""

from __future__ import annotations

import json

from openfinance.sec.artifacts import sha256_hex

__all__ = [
    "boundary_key",
    "factor_definition_id",
    "research_result_id",
    "result_hash",
]

_SEP = "\x00"


def factor_definition_id(*, metric_key: str, formula_id: str, transform_id: str) -> str:
    """``sha256(metric_key, formula_id, transform_id)`` — the factor *definition* (§7).

    Changing the metric, its formula version, or the transform yields a new
    definition id; re-declaring the identical factor reproduces it. Maps directly
    onto data-model §9's reserved ``factor_definition_id``.
    """
    payload = _SEP.join((metric_key, formula_id, transform_id))
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def boundary_key(*, kind: str, value: str) -> str:
    """The serialized boundary discriminator ``"pit:<as_of>"`` / ``"rev:<dv id>"``.

    Mirrors the Phase 7 metric-id boundary key (``resolve_input``/``identity``), so
    a PIT and a REVISED factor of the same definition/universe/period never collide.
    """
    return f"{kind}:{value}"


def result_hash(cell_outcomes: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered per-cell outcomes — the *output* fingerprint (§7).

    ``cell_outcomes`` is the ordered list of minimal per-cell dicts (member,
    status, value, reason, transformed value) in universe order; it is serialized
    with ``sort_keys=True`` and no whitespace so equal outputs always yield
    identical bytes. Order is preserved (the list is *not* re-sorted) because the
    cross-section's cell order is load-bearing (§12).
    """
    payload = json.dumps(
        cell_outcomes, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{sha256_hex(payload)}"


def research_result_id(
    *,
    factor_definition_id: str,
    metric_engine_version_id: str,
    universe_id: str,
    period_key: str,
    boundary_key: str,
    result_hash: str,
) -> str:
    """The identity of a whole factor request+output (§7, data-model §9).

    Pins the request (definition, engine version = §9 ``factor_version``, universe,
    period, boundary) **and** the output (``result_hash``). Same request ⇒ same id
    and same values, on any machine.
    """
    payload = _SEP.join(
        (
            factor_definition_id,
            metric_engine_version_id,
            universe_id,
            period_key,
            boundary_key,
            result_hash,
        )
    )
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"
