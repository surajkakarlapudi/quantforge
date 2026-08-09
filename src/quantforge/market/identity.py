"""Content-addressed identities for the Market Data Layer (Phase 11, §14).

Reuses **both** existing identity conventions (proposal §2.5, D8): the Phase 1
bare-hex content addressing for immutable raw vendor bytes (the blob name *is* its
``sha256_hex``), and the derived-identity ``sha256:``-prefixed, ``_SEP = "\\x00"``
NUL-joined, canonical-JSON convention for every derived market identity. Nothing
here depends on the wall clock, a random value, or iteration order (invariant 13).

The derived identities (proposal §14):

    security_id            = "cik:<CIK>#class:<normalized-class>"   (offline default)
                           | "figi:<FIGI>"                        (optional enrichment)
    price_observation_id   = sha256( market_transformation_version_id, security_id,
                                     trading_date, currency, field, value )
    corporate_action_id    = sha256( market_transformation_version_id, security_id,
                                     action_kind, ex_date, canonical action payload )
    market_availability_policy_id
                           = sha256( policy_id, policy_version, rule_definition_hash )
    adjusted_series_id     = sha256( adjustment_version, security_id, boundary_key,
                                     ordered unadjusted obs ids, ordered action ids )

``price_obs_key = (security_id, trading_date, field)`` is the per-field selection
key (proposal §6) — a plain NUL-joined string, **not** a content hash, because it is
a resolver lookup key (mirroring the Phase 5 ``Fact.obs_key``), not an identity. A
per-field key makes a vendor's partial correction of one field a clean,
independently-resolvable observation.

Ticker is **never** an identity component (proposal §7, D2): a ``security_id`` is
derived from the CIK plus a normalized share-class label (or an external FIGI), so
a later ticker reuse can never retroactively re-point historical bars.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex
from quantforge.sec.endpoints import cik10

__all__ = [
    "adjusted_series_id",
    "boundary_key",
    "company_id_of_security_id",
    "corporate_action_id",
    "market_availability_policy_id",
    "normalize_security_class",
    "price_obs_key",
    "price_observation_id",
    "security_id",
]

# The NUL separator shared across every id space in the project (data-model §11);
# it cannot occur in a hash, a CIK, a date, a currency code, or a field name, so a
# joined payload is unambiguous.
_SEP = "\x00"


def normalize_security_class(security_class: str) -> str:
    """Normalize a share-class label into the stable form used in ``security_id``.

    Lower-cased, surrounding whitespace stripped, and internal whitespace runs
    collapsed to single hyphens, so ``"Common Stock"`` and ``" common  stock "``
    both normalize to ``"common-stock"``. The class label is a *stable* attribute of
    the instrument (not a mutable ticker), so folding it into identity is safe.
    Fails closed on an empty label — a security with no defensible class is a defect,
    not something to guess.
    """
    collapsed = "-".join(security_class.strip().lower().split())
    if not collapsed:
        raise ValueError("security_class must be a non-empty label")
    if _SEP in collapsed or "#" in collapsed:
        raise ValueError(
            f"security_class contains a reserved character: {security_class!r}"
        )
    return collapsed


def security_id(
    *,
    cik: str | int | None = None,
    security_class: str | None = None,
    figi: str | None = None,
) -> str:
    """Canonical instrument identity (proposal §7, D2) — ticker is never identity.

    Two forms, both stable under ticker churn:

    * ``figi:<FIGI>`` — the preferred form when an **external** FIGI mapping is
      available (FIGI is not in EDGAR APIs, so it is optional enrichment, never
      required for the layer to function).
    * ``cik:<CIK>#class:<normalized-class>`` — the offline default, derivable
      entirely from data QuantForge already resolves (the CIK) plus a normalized
      share-class label.

    Exactly one form must be requestable: pass ``figi``, **or** both ``cik`` and
    ``security_class``. Anything else is a configuration error.
    """
    if figi is not None:
        token = figi.strip()
        if not token:
            raise ValueError("figi must be a non-empty identifier")
        if cik is not None or security_class is not None:
            raise ValueError("pass either figi or (cik, security_class), not both")
        return f"figi:{token}"
    if cik is None or security_class is None:
        raise ValueError(
            "security_id requires figi=... or both cik=... and security_class=..."
        )
    return f"cik:{cik10(cik)}#class:{normalize_security_class(security_class)}"


def company_id_of_security_id(value: str) -> str | None:
    """Recover the ``company_id`` a ``cik:…#class:…`` ``security_id`` belongs to.

    Realizes the ``Company 1─∞ Security`` edge (proposal §7): the market anchor
    (``security_id``) maps back to the fundamental anchor (``company_id``) so a
    Phase 12 join of a ``PitPanel`` (keyed by ``company_id``) to a ``PitPriceSeries``
    (keyed by ``security_id``) is well defined. Returns ``None`` for a ``figi:`` form
    (its issuer requires the external mapping, not derivable offline).
    """
    if not value.startswith("cik:"):
        return None
    body = value[len("cik:") :]
    cik_part = body.split("#", 1)[0]
    return f"cik:{cik10(cik_part)}"


def price_obs_key(*, security_id: str, trading_date: str, field: str) -> str:
    """The per-field resolver selection key ``(security_id, trading_date, field)``.

    A plain NUL-joined string (not a content hash): it is the lookup key the
    :class:`~quantforge.market.resolve.MarketPointInTimeResolver` groups observations
    by, mirroring the Phase 5 ``Fact.obs_key``. Per-field so a vendor's correction of
    one field (e.g. a fixed ``close``) is an independently-resolvable observation.
    """
    return _SEP.join((security_id, trading_date, field))


def price_observation_id(
    *,
    market_transformation_version_id: str,
    security_id: str,
    trading_date: str,
    currency: str,
    field: str,
    value: str,
) -> str:
    """``sha256(tv_id, security_id, trading_date, currency, field, value)`` (§14).

    The content-addressed identity of one canonical, unadjusted price observation.
    ``value`` is the exact decimal serialized as a string, so identity never depends
    on float representation. Re-deriving the same bar under the same market
    transformation version reproduces the same id (invariant 13).
    """
    payload = _SEP.join(
        (
            market_transformation_version_id,
            security_id,
            trading_date,
            currency,
            field,
            value,
        )
    )
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def corporate_action_id(
    *,
    market_transformation_version_id: str,
    security_id: str,
    action_kind: str,
    ex_date: str,
    payload: dict[str, object],
) -> str:
    """``sha256(tv_id, security_id, action_kind, ex_date, canonical payload)`` (§14).

    ``payload`` is the action's kind-specific fields (ratio, amount, successor, …);
    it is serialized with the project's canonical-JSON discipline
    (``sort_keys=True``, no whitespace) so two equal actions always hash identically
    and re-deriving reproduces the id.
    """
    canonical_payload = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    joined = _SEP.join(
        (
            market_transformation_version_id,
            security_id,
            action_kind,
            ex_date,
            canonical_payload,
        )
    )
    return f"sha256:{sha256_hex(joined.encode('utf-8'))}"


def market_availability_policy_id(
    *, policy_id: str, policy_version: str, rule_definition_hash: str
) -> str:
    """``sha256(policy_id, policy_version, rule_definition_hash)`` - Phase 5 shape."""
    payload = _SEP.join((policy_id, policy_version, rule_definition_hash))
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def boundary_key(*, kind: str, value: str) -> str:
    """The serialized boundary discriminator, mirroring the Phase 10 helper.

    ``"pit:<as_of>"`` (a point-in-time price/series) or ``"rev:<dataset_version_id>"``
    (REVISED), so a PIT and a REVISED answer of the same instrument never collide in
    a content hash.
    """
    return f"{kind}:{value}"


def adjusted_series_id(
    *,
    adjustment_version: str,
    security_id: str,
    boundary_key: str,
    unadjusted_obs_ids: list[str],
    action_ids: list[str],
) -> str:
    """``sha256(adjustment_version, security_id, boundary_key, obs, actions)`` (§14).

    The identity of a *derived* adjusted series. Because it pins the ordered
    unadjusted observation ids **and** the ordered (PIT-eligible) corporate-action
    ids it composed, plus the adjustment version, the same inputs at the same
    boundary reproduce the same id and the same adjusted values — reproducibly,
    forever (invariant 13). Order is preserved verbatim (the lists are not
    re-sorted): the series' date order is load-bearing.
    """
    components = [adjustment_version, security_id, boundary_key]
    components.extend(unadjusted_obs_ids)
    components.append(_SEP)  # a section marker between obs ids and action ids
    components.extend(action_ids)
    payload = _SEP.join(components)
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"
