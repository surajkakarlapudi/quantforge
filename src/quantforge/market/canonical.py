"""Deterministic raw→canonical market normalization (§8, §2.4, D4).

The market analogue of the SEC XBRL→canonical-fact normalizer: a **pure, versioned**
function that turns immutable :class:`~quantforge.market.provider.RawMarketDocument`
vendor bytes into canonical, **unadjusted**
:class:`~quantforge.market.model.PriceObservation` /
:class:`~quantforge.market.model.CorporateAction` records plus the per-session
:class:`~quantforge.market.model.MarketObservationEvidence` that availability
derivation consumes. It is provider-neutral (§11): it parses a single **canonical
vendor JSON shape** that any adapter maps its vendor onto, so the canonical layer
never learns a vendor's private schema.

Canonical daily-bar payload (one instrument)::

    {
        "security_id": "cik:0000000001#class:common-stock",
        "security_type": "common-stock",
        "currency": "USD",
        "ticker_history": [
            {
                "ticker": "ZZZZ",
                "exchange": "TEST",
                "effective_from": "2020-01-02",
                "effective_to": null,
            }
        ],
        "bars": [
            {
                "trading_date": "2020-01-02",
                "open": "100",
                "high": "110",
                "low": "90",
                "close": "105",
                "volume": "1000",
                "observation_timestamp_utc": "2020-01-02T21:00:00Z",
            }
        ],
    }

Canonical corporate-action payload (one instrument)::

    {
        "security_id": "cik:0000000001#class:common-stock",
        "actions": [
            {"kind": "split", "ex_date": "2020-06-01", "ratio": "2"},
            {
                "kind": "dividend",
                "ex_date": "2020-03-01",
                "amount": "0.50",
                "currency": "USD",
                "pay_date": "2020-03-15",
            },
        ],
    }

Every numeric field is carried as an **exact decimal string** and re-serialized to a
canonical form (:func:`_canonical_numeric`) under the pinned decimal context, so
``"105.00"`` and ``"105"`` normalize identically and the derived
``price_observation_id`` is stable (invariant 13). A malformed vendor payload raises
:class:`~quantforge.market.errors.MarketDataError` — we never guess a bar's value.
Nothing here reads the wall clock, an RNG, or iteration order.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import TypedDict

from quantforge.market.errors import MarketDataError
from quantforge.market.model import (
    CorporateAction,
    CorporateActionKind,
    Instrument,
    MarketDataSource,
    MarketObservationEvidence,
    PriceField,
    PriceObservation,
    TickerHistory,
)
from quantforge.market.provider import RawMarketDocument
from quantforge.market.version import MarketTransformationVersion

__all__ = ["CanonicalMarketData", "MarketCanonicalizer"]

# The OHLCV field names as they appear in the canonical vendor JSON, paired with the
# PriceField they normalize to. A field absent from a bar simply yields no
# observation (a first-class "not reported", never a guessed zero).
_BAR_FIELDS: tuple[tuple[str, PriceField], ...] = (
    ("open", PriceField.OPEN),
    ("high", PriceField.HIGH),
    ("low", PriceField.LOW),
    ("close", PriceField.CLOSE),
    ("volume", PriceField.VOLUME),
)


class _CommonActionFields(TypedDict):
    """The provenance fields every corporate-action constructor shares (§10).

    Typed so ``**common`` unpacking is checkable: the ``str``-required fields and the
    optional (``str | None``) timestamps each land on the matching parameter.
    """

    market_transformation_version_id: str
    security_id: str
    source_id: str
    raw_document_sha256: str
    observation_timestamp_utc: str | None
    retrieved_at: str | None


@dataclass(frozen=True, slots=True)
class CanonicalMarketData:
    """The deterministic output of normalizing one instrument's raw documents (§8).

    Groups the canonical, unadjusted observations, the first-class corporate actions,
    the instrument metadata, and the per-session availability evidence, so the engine
    can derive availability and persist in one pass. ``evidence`` holds exactly one
    record per unique ``(security_id, event_date)`` session that appears in the bars
    or the actions (both a bar and a same-day action share one session, §9).
    """

    instrument: Instrument
    observations: tuple[PriceObservation, ...] = ()
    actions: tuple[CorporateAction, ...] = ()
    evidence: tuple[MarketObservationEvidence, ...] = ()


class MarketCanonicalizer:
    """Normalize raw vendor bytes → canonical records (§8, §2.4) — pure & versioned.

    Pins one :class:`~quantforge.market.version.MarketTransformationVersion`; its id
    is folded into every ``price_observation_id`` / ``corporate_action_id`` (§14), so
    re-normalizing under a different version can never be confused with this one.
    """

    def __init__(
        self, *, transformation_version: MarketTransformationVersion | None = None
    ) -> None:
        self._tv = transformation_version or MarketTransformationVersion()

    @property
    def transformation_version(self) -> MarketTransformationVersion:
        return self._tv

    @property
    def transformation_version_id(self) -> str:
        return self._tv.market_transformation_version_id

    def canonicalize(
        self,
        *,
        bars_document: RawMarketDocument,
        actions_document: RawMarketDocument | None = None,
        source: MarketDataSource,
    ) -> CanonicalMarketData:
        """Normalize one instrument's bar + (optional) action documents (§8).

        Both documents must carry the **same** ``security_id`` (a mismatch is a
        configuration/consistency defect, raised). Bars supply the instrument
        metadata (type, currency, ticker history); the actions document need only
        carry its ``security_id`` and ``actions``. Returns a
        :class:`CanonicalMarketData` whose records are content-addressed and
        deterministic.
        """
        bars_raw = _load(bars_document, "daily-bars")
        security_id = _req_str(bars_raw, "security_id", "daily-bars")
        security_type = _opt_str(bars_raw, "security_type") or "common-stock"
        default_currency = _opt_str(bars_raw, "currency") or source.default_currency
        ticker_history = _parse_ticker_history(bars_raw)
        instrument = Instrument(
            security_id=security_id,
            security_type=security_type,
            ticker_history=ticker_history,
        )

        retrieved_at = bars_document.metadata.retrieved_at
        raw_sha = bars_document.sha256

        observations: list[PriceObservation] = []
        sessions: dict[str, MarketObservationEvidence] = {}
        with localcontext(self._tv.decimal_context()):
            for bar in _req_list(bars_raw, "bars", "daily-bars"):
                if not isinstance(bar, dict):
                    raise MarketDataError("each daily bar must be an object")
                trading_date = _req_str(bar, "trading_date", "daily-bars")
                bar_currency = _opt_str(bar, "currency") or default_currency
                obs_ts = _opt_str(bar, "observation_timestamp_utc")
                for json_key, price_field in _BAR_FIELDS:
                    if json_key not in bar or bar[json_key] is None:
                        continue
                    value = _canonical_numeric(bar[json_key], json_key)
                    observations.append(
                        PriceObservation(
                            market_transformation_version_id=(
                                self.transformation_version_id
                            ),
                            security_id=security_id,
                            trading_date=trading_date,
                            field=price_field,
                            value_numeric_str=value,
                            currency=bar_currency,
                            source_id=source.source_id,
                            raw_document_sha256=raw_sha,
                            observation_timestamp_utc=obs_ts,
                            retrieved_at=retrieved_at,
                        )
                    )
                _record_session(
                    sessions, security_id, trading_date, obs_ts, retrieved_at
                )

        actions: list[CorporateAction] = []
        if actions_document is not None:
            actions_raw = _load(actions_document, "corporate-actions")
            actions_security = _req_str(actions_raw, "security_id", "corporate-actions")
            if actions_security != security_id:
                raise MarketDataError(
                    f"corporate-actions security_id {actions_security!r} does not "
                    f"match daily-bars security_id {security_id!r}"
                )
            a_retrieved = actions_document.metadata.retrieved_at
            a_sha = actions_document.sha256
            with localcontext(self._tv.decimal_context()):
                for raw_action in _req_list(
                    actions_raw, "actions", "corporate-actions"
                ):
                    if not isinstance(raw_action, dict):
                        raise MarketDataError("each corporate action must be an object")
                    action = self._parse_action(
                        raw_action, security_id, source, a_sha, a_retrieved
                    )
                    actions.append(action)
                    _record_session(
                        sessions,
                        security_id,
                        action.ex_date,
                        action.observation_timestamp_utc,
                        a_retrieved,
                    )

        return CanonicalMarketData(
            instrument=instrument,
            observations=tuple(observations),
            actions=tuple(actions),
            evidence=tuple(sessions[k] for k in sorted(sessions)),
        )

    def _parse_action(
        self,
        raw: dict[str, object],
        security_id: str,
        source: MarketDataSource,
        raw_sha: str,
        retrieved_at: str | None,
    ) -> CorporateAction:
        """Parse one canonical corporate action via the typed constructors (§10)."""
        kind_raw = _req_str(raw, "kind", "corporate-actions")
        try:
            kind = CorporateActionKind(kind_raw)
        except ValueError as exc:
            raise MarketDataError(
                f"unknown corporate action kind {kind_raw!r}"
            ) from exc
        ex_date = _req_str(raw, "ex_date", "corporate-actions")
        obs_ts = _opt_str(raw, "observation_timestamp_utc")
        common = _CommonActionFields(
            market_transformation_version_id=self.transformation_version_id,
            security_id=security_id,
            source_id=source.source_id,
            raw_document_sha256=raw_sha,
            observation_timestamp_utc=obs_ts,
            retrieved_at=retrieved_at,
        )
        if kind is CorporateActionKind.SPLIT:
            return CorporateAction.split(
                ex_date=ex_date,
                ratio=_canonical_numeric(raw.get("ratio"), "ratio"),
                **common,
            )
        if kind is CorporateActionKind.DIVIDEND:
            return CorporateAction.dividend(
                ex_date=ex_date,
                amount=_canonical_numeric(raw.get("amount"), "amount"),
                currency=_opt_str(raw, "currency") or source.default_currency,
                pay_date=_opt_str(raw, "pay_date"),
                **common,
            )
        if kind is CorporateActionKind.SYMBOL_CHANGE:
            return CorporateAction.symbol_change(
                effective_date=ex_date,
                old_ticker=_req_str(raw, "old_ticker", "corporate-actions"),
                new_ticker=_req_str(raw, "new_ticker", "corporate-actions"),
                **common,
            )
        if kind is CorporateActionKind.DELISTING:
            return CorporateAction.delisting(
                effective_date=ex_date,
                reason=_opt_str(raw, "reason") or "unspecified",
                **common,
            )
        # MERGER - represented structurally only (§10).
        return CorporateAction.merger(
            effective_date=ex_date,
            successor_security_id=_opt_str(raw, "successor_security_id"),
            terms=_opt_str(raw, "terms") or "unspecified",
            **common,
        )


def _record_session(
    sessions: dict[str, MarketObservationEvidence],
    security_id: str,
    event_date: str,
    observation_timestamp_utc: str | None,
    retrieved_at: str | None,
) -> None:
    """Record (or keep) one session's evidence; a session is derived once (§9).

    Bars and same-day actions share one ``(security_id, event_date)`` session. The
    first evidence seen for a session is kept; a later record for the same session
    keeps the earliest known ``observation_timestamp_utc`` so derivation is
    order-independent (invariant 13).
    """
    from quantforge.market.model import session_key as _session_key

    key = _session_key(security_id, event_date)
    existing = sessions.get(key)
    if existing is None:
        sessions[key] = MarketObservationEvidence(
            security_id=security_id,
            event_date=event_date,
            observation_timestamp_utc=observation_timestamp_utc,
            retrieved_at=retrieved_at,
        )
        return
    # Keep the earliest observation timestamp deterministically (min, None-aware).
    merged_obs = _min_optional(
        existing.observation_timestamp_utc, observation_timestamp_utc
    )
    merged_retrieved = _min_optional(existing.retrieved_at, retrieved_at)
    if (
        merged_obs != existing.observation_timestamp_utc
        or merged_retrieved != existing.retrieved_at
    ):
        sessions[key] = MarketObservationEvidence(
            security_id=security_id,
            event_date=event_date,
            observation_timestamp_utc=merged_obs,
            retrieved_at=merged_retrieved,
        )


def _min_optional(a: str | None, b: str | None) -> str | None:
    """The lexicographically-smaller of two optional ISO-8601 strings (None-aware)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a <= b else b


def _parse_ticker_history(raw: dict[str, object]) -> tuple[TickerHistory, ...]:
    rows_raw = raw.get("ticker_history", [])
    if not isinstance(rows_raw, list):
        raise MarketDataError("ticker_history must be a list")
    rows: list[TickerHistory] = []
    for row in rows_raw:
        if not isinstance(row, dict):
            raise MarketDataError("each ticker_history row must be an object")
        rows.append(TickerHistory.from_dict(row))
    # Deterministic order by effective_from then ticker — identity never depends on
    # a cosmetic input ordering.
    rows.sort(key=lambda t: (t.effective_from, t.ticker))
    return tuple(rows)


def _canonical_numeric(value: object, label: str) -> str:
    """Validate ``value`` as an exact decimal and re-serialize it canonically.

    Accepts a string or JSON number, parses it as a :class:`~decimal.Decimal` under
    the pinned context, and returns a stable string form (no scientific notation, no
    trailing-zero noise), so ``"105.00"`` and ``"105"`` yield one identity. A
    non-numeric value is a malformed vendor payload → :class:`MarketDataError` (never
    a guessed price).
    """
    if isinstance(value, bool) or value is None:
        raise MarketDataError(f"{label} must be a numeric value, got {value!r}")
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, int | float):
        text = str(value)
    else:
        raise MarketDataError(
            f"{label} must be a numeric value, got {type(value).__name__}"
        )
    if not text:
        raise MarketDataError(f"{label} must be a non-empty numeric value")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise MarketDataError(f"{label} {value!r} is not a valid decimal") from exc
    if not parsed.is_finite():
        raise MarketDataError(f"{label} {value!r} is not a finite decimal")
    normalized = parsed.normalize()
    return format(normalized, "f")


def _load(document: RawMarketDocument, label: str) -> dict[str, object]:
    """Decode a raw document's bytes as a canonical JSON object; fail closed."""
    try:
        parsed = json.loads(document.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketDataError(f"{label} payload is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MarketDataError(f"{label} payload must be a JSON object")
    return parsed


def _req_str(raw: dict[str, object], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise MarketDataError(f"{label} payload requires a non-empty {key!r} string")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise MarketDataError(f"{key} must be a string or null")
    return value


def _req_list(raw: dict[str, object], key: str, label: str) -> Iterable[object]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise MarketDataError(f"{label} payload requires a {key!r} list")
    return value
