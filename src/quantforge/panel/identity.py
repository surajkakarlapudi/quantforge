"""The content-addressed panel identities (``docs/phase10-panel-locked.md`` §5).

Three deterministic hashes close the data-model §9 reproducibility loop for a
point-in-time fundamental panel, composing with the existing Phase 5/7/8 pins:

    panel_definition_id = sha256( metric_key, formula_id, derivation_id, axis_id,
                                  shape )
    result_hash         = sha256( canonical JSON of the ordered cell outcomes )
    panel_id            = sha256( panel_definition_id, metric_engine_version_id,
                                  member_key, boundary_key, result_hash )

``panel_definition_id`` maps onto data-model §9's reserved ``factor_definition_id``
(one axis wider); ``metric_engine_version_id`` maps onto §9's reserved
``factor_version``. All ids follow the §11 identity discipline verbatim:
``sha256:``-prefixed, NUL-joined components, no wall-clock / RNG / iteration-order
dependence. ``panel_id`` pins the **request** (which definition, engine, member(s),
boundary) **and** the **output** (via ``result_hash``), so re-running the same
request reproduces the same id and the same values — determinism made checkable
(§12).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "boundary_key",
    "panel_definition_id",
    "panel_id",
    "result_hash",
]

_SEP = "\x00"


def panel_definition_id(
    *,
    metric_key: str,
    formula_id: str,
    derivation_id: str,
    axis_id: str,
    shape: str,
) -> str:
    """``sha256(metric_key, formula_id, derivation_id, axis_id, shape)`` (§5).

    The panel *definition* — the reproducible identity of the question, independent
    of the boundary or the answer. Changing the metric, its formula version, the
    derivation, the axis, or the shape yields a new definition id; re-declaring the
    identical panel reproduces it. Maps onto data-model §9's ``factor_definition_id``.
    """
    payload = _SEP.join((metric_key, formula_id, derivation_id, axis_id, shape))
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def boundary_key(*, kind: str, value: str) -> str:
    """The serialized boundary discriminator (§5).

    ``"pit:<as_of>"`` (period-series / matrix), ``"pit-vintage:<sorted as_of list>"``
    (vintage), or ``"rev:<dataset_version_id>"`` (REVISED). Mirrors the Phase 7/8
    boundary key so a PIT, a vintage, and a REVISED panel of the same
    definition/member never collide.
    """
    return f"{kind}:{value}"


def result_hash(cell_outcomes: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered per-cell outcomes — the *output* fingerprint (§5).

    ``cell_outcomes`` is the ordered list of minimal per-cell dicts (coordinate,
    status, value, reason, derived value) in cell order; it is serialized with
    ``sort_keys=True`` and no whitespace so equal outputs always yield identical
    bytes. Order is preserved (the list is *not* re-sorted) because the panel's cell
    order is load-bearing (§12).
    """
    payload = json.dumps(
        cell_outcomes, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{sha256_hex(payload)}"


def panel_id(
    *,
    panel_definition_id: str,
    metric_engine_version_id: str,
    member_key: str,
    boundary_key: str,
    result_hash: str,
) -> str:
    """The identity of a whole panel request+output (§5, data-model §9).

    Pins the request (definition, engine version = §9 ``factor_version``, member(s)
    = a ``universe_id`` for the matrix or a ``company_id`` for a per-filer panel,
    boundary) **and** the output (``result_hash``). Same request ⇒ same id and same
    values, on any machine, independent of execution order or wall-clock.
    """
    payload = _SEP.join(
        (
            panel_definition_id,
            metric_engine_version_id,
            member_key,
            boundary_key,
            result_hash,
        )
    )
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"
