"""The :class:`PriceEngine` façade — the Phase 12 market-data hand-off (§17, D10).

The market layer's I/O boundary and the **only** surface a future backtester (Phase
12) touches. It composes — never re-resolves — the already-built pieces:

1. a provider-neutral :class:`~quantforge.market.provider.MarketDataProvider` (via
   :meth:`ingest`) fetches immutable raw vendor bytes, stored content-addressed in
   the reused Phase 1 :class:`~quantforge.sec.storage.ArtifactStore`;
2. the deterministic :class:`~quantforge.market.canonical.MarketCanonicalizer`
   normalizes them into canonical, **unadjusted**
   :class:`~quantforge.market.model.PriceObservation` /
   :class:`~quantforge.market.model.CorporateAction` records + per-session evidence;
3. :func:`~quantforge.market.policy.derive_market_availability` derives the
   fail-closed availability triple for each session under a versioned
   :class:`~quantforge.market.policy.MarketAvailabilityPolicy`;
4. all of the above is persisted to the file-based
   :class:`~quantforge.market.store.MarketDataStore` (derived, rebuildable state);
5. the :class:`~quantforge.market.resolve.MarketPointInTimeResolver` answers PIT /
   REVISED queries, and :func:`~quantforge.market.adjust.adjust_pit_series` derives
   the split/dividend view on demand.

**PIT-only hand-off (D10).** The three §17 methods a backtester consumes —
:meth:`price_as_of`, :meth:`price_series_as_of`, :meth:`adjusted_series_as_of` —
return typed :class:`~quantforge.market.result.PitPrice` /
:class:`~quantforge.market.result.PitPriceSeries` results and **structurally refuse**
to hand back a :class:`~quantforge.market.result.RevisedPrice` (there is no
``RevisedPriceSeries`` at all). REVISED is reachable only via the explicitly-named
:meth:`revised_price` over a pinned
:class:`~quantforge.market.version.MarketDatasetVersion`. There is **no default-mode
accessor** (invariant 14/27): PIT requires a timezone-aware ``as_of``; a naive one
raises :class:`~quantforge.availability.errors.ModeError` at the Phase 5 choke point.

The engine does not implement the backtester, portfolio construction, weighting, or
any alpha/return logic — only the market-data interface (Phase 11 scope boundary).
"""

from __future__ import annotations

from datetime import datetime

from quantforge.availability.timestamps import ensure_aware_utc, parse_utc
from quantforge.market.adjust import adjust_pit_series
from quantforge.market.axis import PriceAxis
from quantforge.market.canonical import CanonicalMarketData, MarketCanonicalizer
from quantforge.market.errors import MarketPolicyConfigurationError
from quantforge.market.model import (
    CorporateAction,
    CorporateActionKind,
    MarketAvailability,
    MarketDataSource,
    MarketObservationEvidence,
    PriceField,
    PriceObservation,
)
from quantforge.market.policy import (
    MarketAvailabilityPolicy,
    derive_market_availability,
    market_eod_std_v1,
)
from quantforge.market.provider import DateRange, MarketDataProvider, RawMarketDocument
from quantforge.market.resolve import MarketPointInTimeResolver
from quantforge.market.result import PitPrice, PitPriceSeries, RevisedPrice
from quantforge.market.store import MarketDataStore
from quantforge.market.version import (
    AdjustmentVersion,
    MarketDatasetVersion,
    MarketTransformationVersion,
)
from quantforge.sec.storage import ArtifactStore

__all__ = ["PriceEngine"]


class PriceEngine:
    """Ingest, resolve, and adjust point-in-time market data (§17, §2, D10).

    Constructed from a :class:`~quantforge.market.store.MarketDataStore` (derived
    state) and a raw :class:`~quantforge.sec.storage.ArtifactStore` (immutable vendor
    bytes). The transformation version, availability policies, and adjustment version
    are all injectable so a test pins them explicitly and reproducibly.
    """

    def __init__(
        self,
        store: MarketDataStore,
        *,
        raw_store: ArtifactStore | None = None,
        transformation_version: MarketTransformationVersion | None = None,
        policies: tuple[MarketAvailabilityPolicy, ...] | None = None,
    ) -> None:
        self._store = store
        self._raw_store = (
            raw_store if raw_store is not None else ArtifactStore(store.raw_root)
        )
        self._canonicalizer = MarketCanonicalizer(
            transformation_version=transformation_version
        )
        # The default policy set is the single provisional EOD policy; a caller may
        # inject a validated/era-specific set. A copy so the engine never shares a
        # mutable default.
        self._policies: tuple[MarketAvailabilityPolicy, ...] = (
            policies if policies is not None else (market_eod_std_v1(),)
        )

    @property
    def store(self) -> MarketDataStore:
        return self._store

    @property
    def raw_store(self) -> ArtifactStore:
        return self._raw_store

    @property
    def transformation_version(self) -> MarketTransformationVersion:
        return self._canonicalizer.transformation_version

    @property
    def policies(self) -> tuple[MarketAvailabilityPolicy, ...]:
        return self._policies

    # -- ingestion -----------------------------------------------------------

    def ingest(
        self,
        provider: MarketDataProvider,
        security_id: str,
        date_range: DateRange,
        *,
        source: MarketDataSource,
        with_actions: bool = True,
    ) -> CanonicalMarketData:
        """Fetch, store raw, normalize, derive availability, and persist (§8, §9).

        Pulls the instrument's daily bars (and, when ``with_actions``, its corporate
        actions) from the provider, stores the immutable bytes content-addressed in
        the raw tier, canonicalizes them, derives each session's availability under
        this engine's policy set, and writes the derived canonical + availability
        sidecars. Returns the :class:`CanonicalMarketData` for inspection. Purely a
        function of the provider's bytes and the pinned versions — no wall clock.
        """
        bars_doc = provider.fetch_daily_bars(security_id, date_range)
        self._store_raw(bars_doc)
        actions_doc: RawMarketDocument | None = None
        if with_actions:
            actions_doc = provider.fetch_corporate_actions(security_id, date_range)
            self._store_raw(actions_doc)

        canonical = self._canonicalizer.canonicalize(
            bars_document=bars_doc,
            actions_document=actions_doc,
            source=source,
        )
        self._persist(canonical)
        return canonical

    def _store_raw(self, document: RawMarketDocument) -> None:
        """Persist a raw vendor document to the immutable content-addressed tier."""
        self._raw_store.store(document.as_artifact())

    def _persist(self, canonical: CanonicalMarketData) -> None:
        """Merge into the append-only canonical + availability sidecars (§9).

        A later ingestion (a vendor *correction*, a wider date range) must **add**
        observations, never overwrite the file and destroy the prior vintage
        (invariant 4). Because every record is content-addressed, the merge is a set
        union keyed by id: a re-ingested identical bar collapses to the same id
        (idempotent), while a corrected value is a new id that coexists with the old
        one so PIT can still reproduce the pre-correction answer and the resolver's
        total-order selection can pick the correction. The write remains
        byte-deterministic (the store sorts by id).
        """
        security_id = canonical.instrument.security_id
        observations = self._merge_observations(security_id, canonical.observations)
        actions = self._merge_actions(security_id, canonical.actions)

        availability = self._merge_availability(security_id, canonical.evidence)
        policy_ids = sorted(
            {
                a.availability_policy_id
                for a in availability
                if a.availability_policy_id is not None
            }
        )
        self._store.write_instrument(
            canonical.instrument,
            observations,
            actions,
            market_transformation_version_id=(
                self._canonicalizer.transformation_version_id
            ),
        )
        self._store.write_availability(security_id, availability, policy_ids)

    def _merge_observations(
        self, security_id: str, new_observations: tuple[PriceObservation, ...]
    ) -> list[PriceObservation]:
        """Union stored + new observations, deduplicated by content id (invariant 4)."""
        by_id: dict[str, PriceObservation] = {
            o.price_observation_id: o
            for o in self._store.read_observations(security_id)
        }
        for obs in new_observations:
            by_id.setdefault(obs.price_observation_id, obs)
        return list(by_id.values())

    def _merge_actions(
        self, security_id: str, new_actions: tuple[CorporateAction, ...]
    ) -> list[CorporateAction]:
        """Union stored + new corporate actions, deduplicated by content id."""
        by_id: dict[str, CorporateAction] = {
            a.corporate_action_id: a for a in self._store.read_actions(security_id)
        }
        for action in new_actions:
            by_id.setdefault(action.corporate_action_id, action)
        return list(by_id.values())

    def _merge_availability(
        self, security_id: str, evidence: tuple[MarketObservationEvidence, ...]
    ) -> list[MarketAvailability]:
        """Re-derive this batch's sessions and merge with the stored sidecars (§9).

        A session already present keeps its stored triple unless the freshly-derived
        one is *later* to become knowable (a more conservative boundary, e.g. a later
        retrieval cap); we round LATER on any change so a re-ingest can never move a
        session's availability earlier and admit look-ahead (§9).
        """
        by_session: dict[str, MarketAvailability] = {
            a.session_key: a for a in self._store.read_availability(security_id)
        }
        for ev in evidence:
            derived = derive_market_availability(ev, self._policies)
            existing = by_session.get(derived.session_key)
            by_session[derived.session_key] = _later_availability(existing, derived)
        return list(by_session.values())

    # -- resolver wiring -----------------------------------------------------

    def _resolver_for(self, security_id: str) -> MarketPointInTimeResolver:
        """Build a resolver over one instrument's stored observations + availability.

        Reads the canonical observations (integrity-checked on read) and the
        availability sidecars, joins them by ``session_key``, and returns a fresh
        resolver. Pure over the stored state.
        """
        observations = self._store.read_observations(security_id)
        availability = self._store.read_availability_map(security_id)
        return MarketPointInTimeResolver(observations, availability)

    def dataset_version_for(self, security_id: str) -> MarketDatasetVersion:
        """The reproducible per-instrument market snapshot pin (§14).

        Pins every stored observation id, corporate-action id, raw-document sha, and
        availability-policy id for the instrument, plus the normalizer version — so a
        REVISED answer over it is reproducible (invariant 19).
        """
        observations = self._store.read_observations(security_id)
        actions = self._store.read_actions(security_id)
        availability = self._store.read_availability(security_id)
        policy_ids = tuple(
            sorted(
                {
                    a.availability_policy_id
                    for a in availability
                    if a.availability_policy_id is not None
                }
            )
        )
        raw_ids = tuple(sorted({o.raw_document_sha256 for o in observations}))
        return MarketDatasetVersion(
            market_transformation_version_id=(
                self._canonicalizer.transformation_version_id
            ),
            market_availability_policy_ids=policy_ids,
            raw_document_ids=raw_ids,
            price_observation_ids=tuple(
                sorted(o.price_observation_id for o in observations)
            ),
            corporate_action_ids=tuple(sorted(a.corporate_action_id for a in actions)),
        )

    # -- PIT hand-off (§17, D10) --------------------------------------------

    def price_as_of(
        self,
        security_id: str,
        trading_date: str,
        as_of: datetime,
        *,
        field: PriceField = PriceField.CLOSE,
    ) -> PitPrice:
        """The PIT unadjusted price for one bar field at ``as_of`` (§17, D10).

        ``as_of`` must be timezone-aware (a naive instant raises
        :class:`~quantforge.availability.errors.ModeError`). A bar not knowable by
        ``as_of`` (or never reported) is a first-class ``UNDEFINED``
        :class:`PitPrice`, never an exception. Structurally PIT — cannot return a
        :class:`RevisedPrice`.
        """
        resolver = self._resolver_for(security_id)
        return resolver.price_as_of(security_id, trading_date, as_of, field=field)

    def price_series_as_of(
        self,
        security_id: str,
        axis: PriceAxis,
        as_of: datetime,
        *,
        field: PriceField = PriceField.CLOSE,
    ) -> PitPriceSeries:
        """The PIT **unadjusted** price series over a declared axis (§17, D10).

        One :class:`PitPrice` cell per axis date at the single ``as_of``,
        UNDEFINED-preserving (never dropped, never forward-filled). This is the
        canonical (unadjusted) hand-off surface; :meth:`adjusted_series_as_of` layers
        the derived split/dividend view on top.
        """
        aware = ensure_aware_utc(as_of)
        resolver = self._resolver_for(security_id)
        cells = tuple(
            resolver.price_as_of(security_id, date, aware, field=field)
            for date in axis.dates
        )
        return PitPriceSeries(
            security_id=security_id,
            field=field,
            as_of=aware,
            axis_id=axis.axis_id,
            cells=cells,
        )

    def adjusted_series_as_of(
        self,
        security_id: str,
        axis: PriceAxis,
        as_of: datetime,
        *,
        field: PriceField = PriceField.CLOSE,
        adjustment: AdjustmentVersion | None = None,
    ) -> PitPriceSeries:
        """The PIT **adjusted** (split/dividend) price series over an axis (§10, §17).

        Resolves the unadjusted series, filters the corporate actions to those
        PIT-eligible as of ``as_of`` (so a future split cannot alter a past adjusted
        price — no look-ahead, §10), computes each session's PIT-eligible pre-ex-date
        reference close for dividend adjustment, and composes the derived adjusted
        series (:func:`~quantforge.market.adjust.adjust_pit_series`). The adjustment
        convention is pinned by ``adjustment`` (default: splits only). Missing
        reference data fails closed to an ``UNDEFINED`` cell, never a guess.
        """
        aware = ensure_aware_utc(as_of)
        adjustment_version = adjustment or AdjustmentVersion()
        resolver = self._resolver_for(security_id)
        unadjusted = tuple(
            resolver.price_as_of(security_id, date, aware, field=field)
            for date in axis.dates
        )
        eligible_actions = self._pit_eligible_actions(security_id, aware)
        reference_closes = self._dividend_reference_closes(
            security_id, aware, eligible_actions, field
        )
        return adjust_pit_series(
            adjustment_version=adjustment_version,
            security_id=security_id,
            field=field,
            as_of=aware,
            axis_id=axis.axis_id,
            axis_dates=axis.dates,
            unadjusted_cells=unadjusted,
            actions=eligible_actions,
            reference_closes=reference_closes,
        )

    # -- REVISED (explicitly named, never a default) ------------------------

    def revised_price(
        self,
        security_id: str,
        trading_date: str,
        dataset_version: MarketDatasetVersion | None = None,
        *,
        field: PriceField = PriceField.CLOSE,
    ) -> RevisedPrice:
        """The latest known price over a pinned market snapshot (§9) — never PIT.

        Requires an explicit :class:`MarketDatasetVersion` (built from the
        instrument's snapshot when omitted) so a caller can never obtain revised
        semantics by omitting an argument (invariant 27). Returns a
        :class:`RevisedPrice`, which the PIT hand-off will not accept (invariant 28).
        """
        dv = (
            dataset_version
            if dataset_version is not None
            else self.dataset_version_for(security_id)
        )
        resolver = self._resolver_for(security_id)
        return resolver.revised_price(security_id, trading_date, dv, field=field)

    # -- adjustment helpers --------------------------------------------------

    def _pit_eligible_actions(
        self, security_id: str, as_of: datetime
    ) -> list[CorporateAction]:
        """Corporate actions whose session is PIT-eligible by ``as_of`` (§10).

        The look-ahead gate for adjustment: an action is admitted only if its
        session's availability is PIT-eligible and its availability timestamp is at
        or before ``as_of``. A future split/dividend not yet knowable is excluded, so
        the adjusted series it feeds cannot see the future.
        """
        actions = self._store.read_actions(security_id)
        availability = self._store.read_availability_map(security_id)
        eligible: list[CorporateAction] = []
        for action in actions:
            av = availability.get(action.session_key)
            if av is None or not av.is_pit_eligible:
                continue
            ts = av.derived_public_availability_timestamp
            if ts is None:
                continue
            if parse_utc(ts) <= as_of:
                eligible.append(action)
        return eligible

    def _dividend_reference_closes(
        self,
        security_id: str,
        as_of: datetime,
        eligible_actions: list[CorporateAction],
        field: PriceField,
    ) -> dict[str, str | None]:
        """For each eligible dividend, the PIT-eligible close before its ex-date (§10).

        The dividend adjustment needs the last PIT-eligible **close** on a trading day
        strictly before the ex-date. We resolve the close on each candidate prior
        trading date (drawn from the stored observations) at ``as_of`` and take the
        latest KNOWN one. ``None`` when none is knowable → the adjuster fails that
        cell closed with ``MISSING_ADJUSTMENT_REFERENCE`` (never guessed).
        """
        dividends = [
            a for a in eligible_actions if a.action_kind is CorporateActionKind.DIVIDEND
        ]
        if not dividends:
            return {}
        resolver = self._resolver_for(security_id)
        # The trading dates we actually hold a close for, ascending.
        close_dates = sorted(
            {
                o.trading_date
                for o in self._store.read_observations(security_id)
                if o.field is PriceField.CLOSE
            }
        )
        references: dict[str, str | None] = {}
        for dividend in dividends:
            ex_date = dividend.ex_date
            reference: str | None = None
            # Walk trading dates strictly before the ex-date, latest first.
            for date in reversed([d for d in close_dates if d < ex_date]):
                price = resolver.price_as_of(
                    security_id, date, as_of, field=PriceField.CLOSE
                )
                if price.is_known and price.value_numeric_str is not None:
                    reference = price.value_numeric_str
                    break
            references[ex_date] = reference
        return references

    # -- integrity -----------------------------------------------------------

    def check_currency_consistency(self, security_id: str) -> None:
        """Fail closed if one instrument's observations mix currencies (§16).

        A price series that silently mixes currencies is a defect, not a result;
        surfaced as :class:`MarketPolicyConfigurationError`. Volume observations are
        exempt (a share count has no currency semantics).
        """
        currencies = {
            o.currency
            for o in self._store.read_observations(security_id)
            if o.field is not PriceField.VOLUME
        }
        if len(currencies) > 1:
            raise MarketPolicyConfigurationError(
                f"instrument {security_id!r} mixes currencies {sorted(currencies)}; "
                "a price series must be single-currency (§16)"
            )


def _later_availability(
    existing: MarketAvailability | None, derived: MarketAvailability
) -> MarketAvailability:
    """Pick the more conservative of two triples for the same session (§9).

    Used when re-ingesting a session already on disk. Fail-closed ``UNKNOWN`` beats a
    PIT-eligible triple (we never downgrade a session to knowable on a re-ingest that
    saw worse evidence); between two eligible triples the one that becomes knowable
    *later* wins, so availability can only ever move later, never earlier - a re-ingest
    can never retroactively admit look-ahead. ``None`` (nothing stored) yields the
    derived triple unchanged.
    """
    if existing is None:
        return derived
    if not existing.is_pit_eligible:
        return existing
    if not derived.is_pit_eligible:
        return derived
    existing_ts = existing.derived_public_availability_timestamp
    derived_ts = derived.derived_public_availability_timestamp
    # Both eligible ⇒ both timestamps are present; keep the later (more conservative).
    if existing_ts is not None and derived_ts is not None and derived_ts > existing_ts:
        return derived
    return existing
