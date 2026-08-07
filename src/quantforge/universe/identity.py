"""Content-addressed identities for deterministic universe construction (Phase 9.2).

Phase 9.1 content-addresses a *resolved membership* (:attr:`Universe.universe_id`).
Phase 9.2 adds the identities that make the **construction** reproducible and
auditable, following the §11 identity discipline verbatim — ``sha256:``-prefixed,
NUL-joined components, no wall-clock / RNG / iteration-order dependence — exactly as
:mod:`quantforge.factors.identity` does for a cross-sectional factor:

    filter_id           = sha256( canonical JSON of the filter's declaration )
    classification_id   = sha256( scheme, m0=s0, m1=s1, … over sorted members )
    specification_id    = sha256( name, spec_version, ordered filter_ids )
    construction_id      = sha256( specification_id, construction_version_id,
                                    boundary_key, universe_id )

``specification_id`` pins **what** was requested (the ordered rules); it is
independent of any data or boundary, so the same rules always hash identically.
``construction_id`` pins a whole *evaluation* — the specification, the builder
code version, the PIT/REVISED boundary, and the resulting ordered membership — so
re-running the same specification with the same builder over the same data
reproduces the same id and the same universe (determinism made checkable, §12).

Filters serialize to a canonical JSON declaration and hash from it, so a filter's
identity is a pure function of its declared parameters and cannot drift with field
order or whitespace (the same technique as
:func:`quantforge.factors.identity.result_hash`).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "boundary_key",
    "classification_id",
    "construction_id",
    "filter_id",
    "specification_id",
]

# A separator that cannot occur in a company_id (they are `cik:`+digits), so a
# joined payload is unambiguous — the §11 identity convention shared with the
# Phase 9.1 universe, the factor universe, and the metric-id hashing.
_SEP = "\x00"


def _canonical_json(payload: object) -> bytes:
    """Canonical JSON bytes: sorted keys, no whitespace — stable across runs.

    The identical serialization Phase 8 uses for ``result_hash`` (§7), so equal
    declarations always yield identical bytes regardless of dict insertion order.
    """
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def filter_id(declaration: dict[str, object]) -> str:
    """``sha256`` over a filter's canonical-JSON declaration — the filter's identity.

    ``declaration`` is the filter's :meth:`UniverseFilter.to_dict` payload (its kind
    plus declared parameters). Re-declaring the identical filter reproduces the id;
    changing any parameter yields a new one.
    """
    return f"sha256:{sha256_hex(_canonical_json(declaration))}"


def classification_id(scheme: str, assignments: dict[str, str]) -> str:
    """``sha256(scheme, m0=s0, m1=s1, …)`` over the sorted classification pairs.

    Order-independent by construction (members are emitted sorted), so two callers
    that supply the same ``company_id → sector`` mapping under the same ``scheme``
    pin one identity regardless of how they built the dict.
    """
    pairs = (f"{cid}={sector}" for cid, sector in sorted(assignments.items()))
    payload = _SEP.join(("classification", scheme, *pairs))
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def boundary_key(*, kind: str, value: str) -> str:
    """The serialized boundary discriminator ``"pit:<as_of>"`` / ``"rev:<dv id>"``.

    Mirrors the Phase 7 / Phase 8 boundary key so a PIT and a REVISED construction
    of the same specification never collide.
    """
    return f"{kind}:{value}"


def specification_id(
    *, name: str, spec_version: str, filter_ids: tuple[str, ...]
) -> str:
    """``sha256(name, spec_version, filter_id0, filter_id1, …)`` — the *request*.

    Order-sensitive over the filters (filters apply in declared order, so the order
    is load-bearing) and independent of any data or boundary. Re-declaring the
    identical specification reproduces it.
    """
    payload = _SEP.join(("specification", name, spec_version, *filter_ids))
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def construction_id(
    *,
    specification_id: str,
    construction_version_id: str,
    boundary_key: str,
    universe_id: str,
) -> str:
    """The identity of a whole construction: request + builder + boundary + output.

    Pins the specification, the builder code version, the PIT/REVISED boundary, and
    the resulting content-addressed ``universe_id``. Same specification + same
    builder + same data ⇒ same id and same membership, on any machine (§12).
    """
    payload = _SEP.join(
        (
            "construction",
            specification_id,
            construction_version_id,
            boundary_key,
            universe_id,
        )
    )
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"
