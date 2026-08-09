"""Canonical market-data domain model (Phase 11, §6-§10).

Every entity here mirrors an existing SEC-stack entity's *role*, so the mental
model stays uniform (proposal §6):

* :class:`MarketDataSource` ← ``Source`` - the publisher/vendor of the bytes, with
  source-level trust/rules (its default currency, its calendar, whether its
  dissemination evidence may unlock ``VERIFIED``). Policy *data*, not code.
* :class:`Instrument` (a ``Security``) - the tradable instrument keyed by
  ``security_id``; owns effective-dated :class:`TickerHistory` rows that are
  **never** identity (proposal §7, D2).
* :class:`PriceObservation` ← ``Fact`` - one normalized, **unadjusted** daily field
  value for ``(security_id, trading_date, field)`` in a stated currency (proposal
  §8, D4). Per-field, so a vendor's correction of a single field is an
  independently-resolvable observation.
* :class:`CorporateAction` - a first-class immutable split / dividend /
  symbol-change / delisting / merger record (proposal §10, D5), so adjusted prices
  are a *derived* view (:mod:`quantforge.market.adjust`) and history is never
  silently rewritten.
* :class:`MarketObservationEvidence` ← ``FilingEvidence`` and
  :class:`MarketObservation Availability <MarketAvailability>` ← ``FilingAvailability``
  - the four market timestamps (§9) and the fail-closed derived availability triple.

Values are **exact decimals serialized as strings** under a pinned decimal context
(:mod:`quantforge.market.version`); no float ever enters identity or comparison
(proposal §8). Nothing here depends on the wall clock, a random value, or
iteration order (invariant 13).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from quantforge.availability.model import AvailabilityStatus
from quantforge.market.identity import (
    company_id_of_security_id,
    corporate_action_id,
    price_obs_key,
    price_observation_id,
)

__all__ = [
    "CorporateAction",
    "CorporateActionKind",
    "Instrument",
    "MarketAvailability",
    "MarketDataSource",
    "MarketObservationEvidence",
    "PriceField",
    "PriceObservation",
    "PriceStatus",
    "PriceUndefinedReason",
    "TickerHistory",
    "session_key",
]

# The NUL separator shared across every id space in the project (data-model §11).
_SEP = "\x00"


def session_key(security_id: str, event_date: str) -> str:
    """The availability join key ``(security_id, event_date)`` (a plain NUL-join).

    A price observation and a corporate action that share a security and a session
    date share one availability record - they are disseminated together for that
    session - mirroring how every ``Fact`` of a filing shares one
    :class:`~quantforge.availability.model.FilingAvailability` (invariant 17). Not a
    content hash: it is a resolver/store lookup key.
    """
    return _SEP.join((security_id, event_date))


class PriceField(StrEnum):
    """The OHLCV field a :class:`PriceObservation` carries (proposal §8, D1).

    Daily bars only; per-field so a vendor's partial correction of a single field
    is a clean, independently-resolvable observation (§6). Anything finer (VWAP,
    bid/ask) is a deferred future field set (§22), never a rewrite of these.
    """

    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"


class PriceStatus(StrEnum):
    """Whether a price resolved to a value (``KNOWN``) or not (``UNDEFINED``)."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class PriceUndefinedReason(StrEnum):
    """Why a PIT/REVISED price (or adjusted cell) is ``UNDEFINED`` - fail-closed (§16).

    A first-class value carrying *why*, never an exception, never ``0``/``NaN``/a
    forward-fill (Principle 8; mirrors the metrics/panel ``UNDEFINED`` vocabulary):

    * ``NOT_KNOWABLE_YET`` - no eligible observation existed by ``as_of`` (a
      legitimate "not yet public" answer, exactly ``PitValue.fact is None``).
    * ``UNAVAILABLE`` - every observation for the key is availability-``UNKNOWN``
      and therefore fail-closed excluded (§9, invariants 8-9).
    * ``NOT_REPORTED`` - the source never reported a bar for this
      ``(security_id, trading_date)`` (holiday, pre-listing, post-delisting, halt).
    * ``MISSING_ADJUSTMENT_REFERENCE`` - an adjusted (total-return) view could not
      find the PIT-eligible pre-ex-date close a dividend adjustment needs, so the
      earlier cells cannot be honestly adjusted (never guessed).
    """

    NOT_KNOWABLE_YET = "not_knowable_yet"
    UNAVAILABLE = "unavailable"
    NOT_REPORTED = "not_reported"
    MISSING_ADJUSTMENT_REFERENCE = "missing_adjustment_reference"


@dataclass(frozen=True, slots=True)
class MarketDataSource:
    """The publisher/vendor of market bytes - the ``Source`` entity (proposal §6, §11).

    Source-level trust/rules live here as *data*: the default currency a bar
    inherits when the vendor omits one, the business calendar its sessions follow,
    and whether its dissemination evidence may ever unlock ``VERIFIED`` availability
    (dormant in v1 - the canonical layer never trusts a vendor's own "published at"
    stamp until a validated policy says so, §9). The canonical model imports no
    concrete vendor; a provider adapter (outside core) maps a vendor's bytes onto
    this entity.
    """

    source_id: str
    name: str
    default_currency: str
    calendar: str = "us-eastern-business"
    dissemination_evidence_trusted: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "default_currency": self.default_currency,
            "calendar": self.calendar,
            "dissemination_evidence_trusted": self.dissemination_evidence_trusted,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MarketDataSource:
        return cls(
            source_id=_req_str(raw, "source_id"),
            name=_req_str(raw, "name"),
            default_currency=_req_str(raw, "default_currency"),
            calendar=_str_default(raw, "calendar", "us-eastern-business"),
            dissemination_evidence_trusted=bool(
                raw.get("dissemination_evidence_trusted", False)
            ),
        )


@dataclass(frozen=True, slots=True)
class TickerHistory:
    """One effective-dated ticker/exchange row on an :class:`Instrument` (§7).

    Tickers and exchanges are **effective-dated history, never identity** (proposal
    §7, D2). A symbol change (FB→META, a reused/recycled ticker across issuers) is a
    *new row*, not a mutation and not a re-pointed identity - so a later ticker reuse
    can never retroactively re-point a historical bar bound to a ``security_id``.
    """

    ticker: str
    exchange: str | None
    effective_from: str
    effective_to: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "exchange": self.exchange,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TickerHistory:
        return cls(
            ticker=_req_str(raw, "ticker"),
            exchange=_opt_str(raw, "exchange"),
            effective_from=_req_str(raw, "effective_from"),
            effective_to=_opt_str(raw, "effective_to"),
        )


@dataclass(frozen=True, slots=True)
class Instrument:
    """A tradable instrument (a ``Security``), keyed by ``security_id`` (§7, D2).

    ``company_id`` realizes the ``Company 1─∞ Security`` edge - recovered from the
    ``cik:…#class:…`` form so a Phase 12 join of fundamentals (keyed by
    ``company_id``) to prices (keyed by ``security_id``) is well defined; it is
    ``None`` for a ``figi:`` form (its issuer needs the external mapping). The
    ``ticker_history`` rows are effective-dated and **never** identity.
    """

    security_id: str
    security_type: str
    ticker_history: tuple[TickerHistory, ...] = ()

    @property
    def company_id(self) -> str | None:
        """The owning ``company_id`` for a ``cik:…`` form, else ``None`` (§7)."""
        return company_id_of_security_id(self.security_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "security_type": self.security_type,
            "company_id": self.company_id,
            "ticker_history": [t.to_dict() for t in self.ticker_history],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Instrument:
        history_raw = raw.get("ticker_history", [])
        history: list[TickerHistory] = []
        if isinstance(history_raw, list):
            history = [
                TickerHistory.from_dict(row)
                for row in history_raw
                if isinstance(row, dict)
            ]
        return cls(
            security_id=_req_str(raw, "security_id"),
            security_type=_req_str(raw, "security_type"),
            ticker_history=tuple(history),
        )


@dataclass(frozen=True, slots=True)
class PriceObservation:
    """A normalized, **unadjusted** daily field value - the market ``Fact`` (§8, D4).

    Identity (:attr:`price_observation_id`) is a content hash over
    ``(market_transformation_version_id, security_id, trading_date, currency, field,
    value)`` (§14): the exact decimal ``value_numeric_str`` is part of identity, so
    a vendor's *correction* is a **new** observation (a new id) rather than a
    mutation, and PIT selection can reproduce the pre-correction value. The stored
    value is the price as it *printed* on ``trading_date`` - adjusted prices are a
    derived view (:mod:`quantforge.market.adjust`), never stored here (D4).

    ``observation_timestamp_utc`` and ``retrieved_at`` are the §9 availability
    evidence (descriptive provenance, **not** identity, exactly as Phase 1's
    ``retrieved_at`` is never identity); ``source_id`` / ``raw_document_sha256``
    complete the lineage back to the immutable content-addressed vendor bytes.
    """

    market_transformation_version_id: str
    security_id: str
    trading_date: str
    field: PriceField
    value_numeric_str: str
    currency: str
    source_id: str
    raw_document_sha256: str
    observation_timestamp_utc: str | None = None
    retrieved_at: str | None = None

    @property
    def obs_key(self) -> str:
        """The per-field selection key ``(security_id, trading_date, field)``."""
        return price_obs_key(
            security_id=self.security_id,
            trading_date=self.trading_date,
            field=self.field.value,
        )

    @property
    def session_key(self) -> str:
        """The availability join key ``(security_id, trading_date)`` (§9)."""
        return session_key(self.security_id, self.trading_date)

    @property
    def price_observation_id(self) -> str:
        """The content-addressed identity of this observation (§14)."""
        return price_observation_id(
            market_transformation_version_id=self.market_transformation_version_id,
            security_id=self.security_id,
            trading_date=self.trading_date,
            currency=self.currency,
            field=self.field.value,
            value=self.value_numeric_str,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "price_observation_id": self.price_observation_id,
            "market_transformation_version_id": self.market_transformation_version_id,
            "security_id": self.security_id,
            "trading_date": self.trading_date,
            "field": self.field.value,
            "value_numeric": self.value_numeric_str,
            "currency": self.currency,
            "source_id": self.source_id,
            "raw_document_sha256": self.raw_document_sha256,
            "observation_timestamp_utc": self.observation_timestamp_utc,
            "retrieved_at": self.retrieved_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PriceObservation:
        return cls(
            market_transformation_version_id=_req_str(
                raw, "market_transformation_version_id"
            ),
            security_id=_req_str(raw, "security_id"),
            trading_date=_req_str(raw, "trading_date"),
            field=PriceField(_req_str(raw, "field")),
            value_numeric_str=_req_str(raw, "value_numeric"),
            currency=_req_str(raw, "currency"),
            source_id=_req_str(raw, "source_id"),
            raw_document_sha256=_req_str(raw, "raw_document_sha256"),
            observation_timestamp_utc=_opt_str(raw, "observation_timestamp_utc"),
            retrieved_at=_opt_str(raw, "retrieved_at"),
        )


class CorporateActionKind(StrEnum):
    """The first-class corporate-action kinds (proposal §10, D5).

    ``MERGER`` is represented *structurally* (the record exists and is addressable);
    its return-treatment is a Phase 12 concern, not modeled here.
    """

    SPLIT = "split"
    DIVIDEND = "dividend"
    SYMBOL_CHANGE = "symbol_change"
    DELISTING = "delisting"
    MERGER = "merger"


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """A first-class, immutable, PIT-gated corporate-action record (§10, D5).

    Mirrors ``Fact``: one record per event, content-addressed
    (:attr:`corporate_action_id`, §14), carrying its own §9 availability so it, too,
    is only applied to an adjusted view when knowable as of ``as_of`` (this is what
    makes adjustment look-ahead-free, §10). ``ex_date`` is the ex-date (splits,
    dividends) or the effective date (symbol change, delisting, merger); ``payload``
    holds the kind-specific fields (exact decimals as strings). Use the typed
    constructors - they validate the required payload and keep the canonical shape.
    """

    market_transformation_version_id: str
    security_id: str
    action_kind: CorporateActionKind
    ex_date: str
    payload: dict[str, object]
    source_id: str
    raw_document_sha256: str
    observation_timestamp_utc: str | None = None
    retrieved_at: str | None = None

    @property
    def corporate_action_id(self) -> str:
        """The content-addressed identity of this action (§14)."""
        return corporate_action_id(
            market_transformation_version_id=self.market_transformation_version_id,
            security_id=self.security_id,
            action_kind=self.action_kind.value,
            ex_date=self.ex_date,
            payload=self.payload,
        )

    @property
    def session_key(self) -> str:
        """The availability join key ``(security_id, ex_date)`` (§9)."""
        return session_key(self.security_id, self.ex_date)

    # -- typed constructors --------------------------------------------------

    @classmethod
    def split(
        cls,
        *,
        market_transformation_version_id: str,
        security_id: str,
        ex_date: str,
        ratio: str,
        source_id: str,
        raw_document_sha256: str,
        observation_timestamp_utc: str | None = None,
        retrieved_at: str | None = None,
    ) -> CorporateAction:
        """A stock split. ``ratio`` is new-shares-per-old-share (``"7"`` = 7:1)."""
        return cls(
            market_transformation_version_id=market_transformation_version_id,
            security_id=security_id,
            action_kind=CorporateActionKind.SPLIT,
            ex_date=ex_date,
            payload={"ratio": ratio},
            source_id=source_id,
            raw_document_sha256=raw_document_sha256,
            observation_timestamp_utc=observation_timestamp_utc,
            retrieved_at=retrieved_at,
        )

    @classmethod
    def dividend(
        cls,
        *,
        market_transformation_version_id: str,
        security_id: str,
        ex_date: str,
        amount: str,
        currency: str,
        pay_date: str | None = None,
        source_id: str,
        raw_document_sha256: str,
        observation_timestamp_utc: str | None = None,
        retrieved_at: str | None = None,
    ) -> CorporateAction:
        """A cash dividend of ``amount`` (per share) in ``currency``."""
        payload: dict[str, object] = {"amount": amount, "currency": currency}
        if pay_date is not None:
            payload["pay_date"] = pay_date
        return cls(
            market_transformation_version_id=market_transformation_version_id,
            security_id=security_id,
            action_kind=CorporateActionKind.DIVIDEND,
            ex_date=ex_date,
            payload=payload,
            source_id=source_id,
            raw_document_sha256=raw_document_sha256,
            observation_timestamp_utc=observation_timestamp_utc,
            retrieved_at=retrieved_at,
        )

    @classmethod
    def symbol_change(
        cls,
        *,
        market_transformation_version_id: str,
        security_id: str,
        effective_date: str,
        old_ticker: str,
        new_ticker: str,
        source_id: str,
        raw_document_sha256: str,
        observation_timestamp_utc: str | None = None,
        retrieved_at: str | None = None,
    ) -> CorporateAction:
        """A ticker change (ticker history, §7 - never identity)."""
        return cls(
            market_transformation_version_id=market_transformation_version_id,
            security_id=security_id,
            action_kind=CorporateActionKind.SYMBOL_CHANGE,
            ex_date=effective_date,
            payload={"old_ticker": old_ticker, "new_ticker": new_ticker},
            source_id=source_id,
            raw_document_sha256=raw_document_sha256,
            observation_timestamp_utc=observation_timestamp_utc,
            retrieved_at=retrieved_at,
        )

    @classmethod
    def delisting(
        cls,
        *,
        market_transformation_version_id: str,
        security_id: str,
        effective_date: str,
        reason: str,
        source_id: str,
        raw_document_sha256: str,
        observation_timestamp_utc: str | None = None,
        retrieved_at: str | None = None,
    ) -> CorporateAction:
        """A terminal delisting event (survivorship-bias-free - history is kept, §7)."""
        return cls(
            market_transformation_version_id=market_transformation_version_id,
            security_id=security_id,
            action_kind=CorporateActionKind.DELISTING,
            ex_date=effective_date,
            payload={"reason": reason},
            source_id=source_id,
            raw_document_sha256=raw_document_sha256,
            observation_timestamp_utc=observation_timestamp_utc,
            retrieved_at=retrieved_at,
        )

    @classmethod
    def merger(
        cls,
        *,
        market_transformation_version_id: str,
        security_id: str,
        effective_date: str,
        successor_security_id: str | None,
        terms: str,
        source_id: str,
        raw_document_sha256: str,
        observation_timestamp_utc: str | None = None,
        retrieved_at: str | None = None,
    ) -> CorporateAction:
        """A merger/acquisition - represented *structurally* only (§10; return
        treatment is deferred to Phase 12)."""
        payload: dict[str, object] = {"terms": terms}
        if successor_security_id is not None:
            payload["successor_security_id"] = successor_security_id
        return cls(
            market_transformation_version_id=market_transformation_version_id,
            security_id=security_id,
            action_kind=CorporateActionKind.MERGER,
            ex_date=effective_date,
            payload=payload,
            source_id=source_id,
            raw_document_sha256=raw_document_sha256,
            observation_timestamp_utc=observation_timestamp_utc,
            retrieved_at=retrieved_at,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "corporate_action_id": self.corporate_action_id,
            "market_transformation_version_id": self.market_transformation_version_id,
            "security_id": self.security_id,
            "action_kind": self.action_kind.value,
            "ex_date": self.ex_date,
            "payload": dict(self.payload),
            "source_id": self.source_id,
            "raw_document_sha256": self.raw_document_sha256,
            "observation_timestamp_utc": self.observation_timestamp_utc,
            "retrieved_at": self.retrieved_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CorporateAction:
        payload_raw = raw.get("payload", {})
        if not isinstance(payload_raw, dict):
            raise ValueError("payload must be an object")
        return cls(
            market_transformation_version_id=_req_str(
                raw, "market_transformation_version_id"
            ),
            security_id=_req_str(raw, "security_id"),
            action_kind=CorporateActionKind(_req_str(raw, "action_kind")),
            ex_date=_req_str(raw, "ex_date"),
            payload=dict(payload_raw),
            source_id=_req_str(raw, "source_id"),
            raw_document_sha256=_req_str(raw, "raw_document_sha256"),
            observation_timestamp_utc=_opt_str(raw, "observation_timestamp_utc"),
            retrieved_at=_opt_str(raw, "retrieved_at"),
        )


@dataclass(frozen=True, slots=True)
class MarketObservationEvidence:
    """The immutable raw inputs to market availability derivation (§9).

    The market analogue of :class:`~quantforge.availability.model.FilingEvidence`,
    carrying the four §9 timestamps for one ``(security_id, event_date)`` session:

    * ``event_date`` - the exchange session (a bar's ``trading_date`` or an action's
      ``ex_date``): the *economic* date, **never** an availability lower bound (a
      close is not knowable *during* its own session).
    * ``observation_timestamp_utc`` - when the vendor's record was stamped
      (descriptive evidence).
    * ``retrieved_at`` - the Phase-1-style retrieval instant: an **upper bound** on
      availability (invariant 11 analogue), joined only at derivation.

    The session-close instant is **not** stored here - a policy derives it from
    ``event_date`` via its declared calendar, so a re-derivation under a different
    calendar is a new policy version, never a rewrite of evidence.
    """

    security_id: str
    event_date: str
    observation_timestamp_utc: str | None = None
    retrieved_at: str | None = None

    @property
    def session_key(self) -> str:
        return session_key(self.security_id, self.event_date)

    def to_dict(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "event_date": self.event_date,
            "observation_timestamp_utc": self.observation_timestamp_utc,
            "retrieved_at": self.retrieved_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MarketObservationEvidence:
        return cls(
            security_id=_req_str(raw, "security_id"),
            event_date=_req_str(raw, "event_date"),
            observation_timestamp_utc=_opt_str(raw, "observation_timestamp_utc"),
            retrieved_at=_opt_str(raw, "retrieved_at"),
        )


@dataclass(frozen=True, slots=True)
class MarketAvailability:
    """The derived availability triple for one market session (§9).

    The market analogue of
    :class:`~quantforge.availability.model.FilingAvailability`, keyed by
    ``(security_id, event_date)`` and joined onto every :class:`PriceObservation` /
    :class:`CorporateAction` of that session (§9). Enforces the same invariant-12
    shape: ``UNKNOWN`` (fail-closed) must carry neither a timestamp nor a policy;
    ``VERIFIED``/``DERIVED`` must carry both. ``derived_public_availability_timestamp``
    is an aware-UTC ISO-8601 ``…Z`` string when eligible, else ``None``.
    """

    security_id: str
    event_date: str
    derived_public_availability_timestamp: str | None
    availability_status: AvailabilityStatus
    availability_policy_id: str | None
    policy_version: str | None
    policy_confidence: str | None
    policy_status: str | None
    reason: str
    evidence: MarketObservationEvidence

    def __post_init__(self) -> None:
        if self.availability_status is AvailabilityStatus.UNKNOWN:
            if self.derived_public_availability_timestamp is not None:
                raise ValueError("unknown availability must not carry a timestamp")
            if self.availability_policy_id is not None:
                raise ValueError("unknown availability must not reference a policy")
        else:
            status = self.availability_status.value
            if self.availability_policy_id is None:
                raise ValueError(f"{status} availability requires a policy id")
            if self.derived_public_availability_timestamp is None:
                raise ValueError(f"{status} availability requires a timestamp")

    @property
    def session_key(self) -> str:
        return session_key(self.security_id, self.event_date)

    @property
    def is_pit_eligible(self) -> bool:
        """Eligible iff status ∈ {verified, derived} and a timestamp exists."""
        return (
            self.availability_status.is_pit_eligible
            and self.derived_public_availability_timestamp is not None
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "event_date": self.event_date,
            "derived_public_availability_timestamp": (
                self.derived_public_availability_timestamp
            ),
            "availability_status": self.availability_status.value,
            "availability_policy_id": self.availability_policy_id,
            "policy_version": self.policy_version,
            "policy_confidence": self.policy_confidence,
            "policy_status": self.policy_status,
            "reason": self.reason,
            "evidence": self.evidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MarketAvailability:
        evidence_raw = raw["evidence"]
        if not isinstance(evidence_raw, dict):
            raise ValueError("evidence must be an object")
        return cls(
            security_id=_req_str(raw, "security_id"),
            event_date=_req_str(raw, "event_date"),
            derived_public_availability_timestamp=_opt_str(
                raw, "derived_public_availability_timestamp"
            ),
            availability_status=AvailabilityStatus(
                _req_str(raw, "availability_status")
            ),
            availability_policy_id=_opt_str(raw, "availability_policy_id"),
            policy_version=_opt_str(raw, "policy_version"),
            policy_confidence=_opt_str(raw, "policy_confidence"),
            policy_status=_opt_str(raw, "policy_status"),
            reason=_str_default(raw, "reason", ""),
            evidence=MarketObservationEvidence.from_dict(evidence_raw),
        )


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _str_default(raw: dict[str, object], key: str, default: str) -> str:
    value = raw.get(key, default)
    return value if isinstance(value, str) else default
