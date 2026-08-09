"""Point-in-time & revised market resolution with distinct result types (§9, D9).

The market analogue of :class:`quantforge.availability.resolve.PointInTimeResolver`,
mirroring it exactly. It answers the two knowledge-state questions over the *same*
immutable :class:`~quantforge.market.model.PriceObservation` set joined (by
``session_key``) to the sidecar :class:`~quantforge.market.model.MarketAvailability`
triples:

* :meth:`MarketPointInTimeResolver.price_as_of` - the **PIT** view: "what price
  would a researcher have known as of instant ``T``?" Returns a
  :class:`~quantforge.market.result.PitPrice`.
* :meth:`MarketPointInTimeResolver.revised_price` - the **REVISED** view: "what is
  the latest known price now, over a pinned snapshot?" Returns a
  :class:`~quantforge.market.result.RevisedPrice`.

The two are the *same* selection differing only in the ``as_of`` boundary, but the
API makes them **impossible to confuse** (invariants 27-30), exactly as Phase 5
does:

* **No default mode (invariant 27).** There is no ``price()``; PIT requires a
  timezone-aware ``as_of`` (a naive one raises :class:`ModeError`, invariant 15),
  REVISED requires a pinned :class:`~quantforge.availability.version.DatasetVersion`.
* **Distinct result types (invariant 28).** ``PitPrice`` / ``RevisedPrice`` are
  unrelated frozen types; the only bridge is
  :meth:`~quantforge.market.result.RevisedPrice.reinterpret_as_pit`, which re-runs
  resolution.
* **Fail-closed gate (invariants 8-9).** Both modes apply the full predicate:
  ``UNKNOWN`` availability is never eligible, and no observation with availability
  ``> as_of`` is ever returned. A key with no eligible observation is a first-class
  ``UNDEFINED`` price carrying a reason, never an exception.
* **Total-order selection.** Availability desc → observation-id desc is a strict
  total order (a vendor correction with a later availability wins), so the winner is
  deterministic (§9 restatement semantics).

The resolver does no I/O; the :class:`~quantforge.market.engine.PriceEngine` wires it
to the stores.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from quantforge.availability.errors import ModeError
from quantforge.availability.timestamps import (
    ensure_aware_utc,
    format_utc_z,
    parse_utc,
)
from quantforge.market.identity import price_obs_key
from quantforge.market.model import (
    MarketAvailability,
    PriceField,
    PriceObservation,
    PriceStatus,
    PriceUndefinedReason,
)
from quantforge.market.result import PitPrice, PriceProvenance, RevisedPrice
from quantforge.market.version import MarketDatasetVersion

__all__ = [
    "EligiblePriceObservation",
    "MarketPointInTimeResolver",
]


@dataclass(frozen=True, slots=True)
class EligiblePriceObservation:
    """A :class:`PriceObservation` joined to its session's availability triple.

    Carries availability by join, never mutated onto the observation (invariant 7).
    ``availability_timestamp`` is the aware-UTC instant parsed from the triple
    (``None`` only for ``UNKNOWN``, which is never eligible).
    """

    observation: PriceObservation
    availability: MarketAvailability
    availability_timestamp: datetime | None

    @property
    def obs_key(self) -> str:
        return self.observation.obs_key


def _availability_instant(av: MarketAvailability) -> datetime | None:
    ts = av.derived_public_availability_timestamp
    return parse_utc(ts) if ts is not None else None


class MarketPointInTimeResolver:
    """Resolve PIT / revised prices over one observation set + availability (§9).

    Construction takes the observations and a ``session_key → MarketAvailability``
    mapping. An observation whose session has no availability record is treated as
    ``UNKNOWN`` (fail closed) - it is never returned by a research path.
    """

    def __init__(
        self,
        observations: Iterable[PriceObservation],
        availability_by_session: Mapping[str, MarketAvailability],
    ) -> None:
        self._observations: tuple[PriceObservation, ...] = tuple(observations)
        self._availability = dict(availability_by_session)

    # -- eligibility & ranking ----------------------------------------------

    def _observations_for_key(self, key: str) -> list[EligiblePriceObservation]:
        """All observations (any status) for ``obs_key``, availability joined."""
        out: list[EligiblePriceObservation] = []
        for obs in self._observations:
            if obs.obs_key != key:
                continue
            av = self._availability.get(obs.session_key)
            if av is None:
                # No availability record → treat as unknown (fail closed).
                continue
            out.append(
                EligiblePriceObservation(
                    observation=obs,
                    availability=av,
                    availability_timestamp=_availability_instant(av),
                )
            )
        return out

    @staticmethod
    def _is_eligible(obs: EligiblePriceObservation, as_of: datetime) -> bool:
        """The full predicate: status gate, then temporal boundary."""
        av = obs.availability
        if not av.is_pit_eligible:  # (A) fail-closed gate - unknown excluded
            return False
        if obs.availability_timestamp is None:  # (B) known boundary exists
            return False
        return obs.availability_timestamp <= as_of  # (C) not the future

    @staticmethod
    def _rank_key(obs: EligiblePriceObservation) -> tuple[object, ...]:
        """Total-order ranking key - winner first (§9 restatement semantics).

        Rank most-recently-knowable first: availability desc, then, as a
        deterministic final tiebreak, ``price_observation_id`` desc (a stable
        content hash; a later correction that shares an availability instant is
        disambiguated reproducibly). Ascending sort with negated/inverted fields
        puts the winner at index 0.
        """
        assert obs.availability_timestamp is not None  # eligible ⇒ present
        avail = obs.availability_timestamp.timestamp()
        return (-avail, _ObsIdDesc(obs.observation.price_observation_id))

    def _select(
        self, key: str, as_of: datetime
    ) -> tuple[EligiblePriceObservation | None, list[EligiblePriceObservation], int]:
        """Return the winner, all-present observations, and eligible count."""
        present = self._observations_for_key(key)
        eligible = [o for o in present if self._is_eligible(o, as_of)]
        if not eligible:
            return None, present, 0
        eligible.sort(key=self._rank_key)
        return eligible[0], present, len(eligible)

    # -- PIT view -----------------------------------------------------------

    def price_as_of(
        self,
        security_id: str,
        trading_date: str,
        as_of: datetime,
        *,
        field: PriceField = PriceField.CLOSE,
    ) -> PitPrice:
        """Resolve the PIT price for one bar field at historical ``as_of`` (§17).

        ``as_of`` must be timezone-aware (invariant 15); a naive instant raises
        :class:`ModeError`. Applies the fail-closed gate then total-order selection.
        Always returns a :class:`PitPrice` - a key with no eligible observation by
        ``as_of`` yields a ``PitPrice`` with ``status=UNDEFINED`` and
        ``reason=NOT_KNOWABLE_YET`` (or ``NOT_REPORTED`` / ``UNAVAILABLE``), never an
        exception.
        """
        aware = _require_aware(as_of)
        key = price_obs_key(
            security_id=security_id, trading_date=trading_date, field=field.value
        )
        winner, present, count = self._select(key, aware)
        provenance = self._provenance(
            "pit", format_utc_z(aware), winner, present, count
        )
        if winner is None:
            reason = self._undefined_reason(present, aware)
            return PitPrice(
                security_id=security_id,
                trading_date=trading_date,
                field=field,
                status=PriceStatus.UNDEFINED,
                value_numeric_str=None,
                currency=None,
                reason=reason,
                provenance=provenance,
                as_of=aware,
            )
        return PitPrice(
            security_id=security_id,
            trading_date=trading_date,
            field=field,
            status=PriceStatus.KNOWN,
            value_numeric_str=winner.observation.value_numeric_str,
            currency=winner.observation.currency,
            reason=None,
            provenance=provenance,
            as_of=aware,
        )

    # -- REVISED view -------------------------------------------------------

    def revised_price(
        self,
        security_id: str,
        trading_date: str,
        dataset_version: MarketDatasetVersion,
        *,
        field: PriceField = PriceField.CLOSE,
    ) -> RevisedPrice:
        """Resolve the latest known price over a pinned ``dataset_version`` (§9).

        REVISED is PIT at the reproducible ingestion frontier (the max availability
        instant across eligible observations), never a wall-clock read (invariants
        21, 30). Requires an explicit :class:`DatasetVersion` so a caller cannot
        obtain revised semantics by omitting an argument (invariant 27). Returns a
        :class:`RevisedPrice`, inadmissible as a PIT source (invariant 28).
        """
        frontier = self._ingestion_frontier()
        key = price_obs_key(
            security_id=security_id, trading_date=trading_date, field=field.value
        )
        winner, present, count = self._select(key, frontier)
        provenance = self._provenance(
            "rev",
            dataset_version.dataset_version_id,
            winner,
            present,
            count,
        )
        if winner is None:
            reason = self._undefined_reason(present, frontier)
            return RevisedPrice(
                security_id=security_id,
                trading_date=trading_date,
                field=field,
                status=PriceStatus.UNDEFINED,
                value_numeric_str=None,
                currency=None,
                reason=reason,
                provenance=provenance,
                dataset_version_id=dataset_version.dataset_version_id,
            )
        return RevisedPrice(
            security_id=security_id,
            trading_date=trading_date,
            field=field,
            status=PriceStatus.KNOWN,
            value_numeric_str=winner.observation.value_numeric_str,
            currency=winner.observation.currency,
            reason=None,
            provenance=provenance,
            dataset_version_id=dataset_version.dataset_version_id,
        )

    def _ingestion_frontier(self) -> datetime:
        """The latest availability instant across all eligible observations.

        The reproducible stand-in for "now": resolving at it admits every currently
        knowable observation. Deterministic over a pinned observation set. If
        nothing is eligible anywhere, returns the min datetime so no observation
        clears - a fail-closed empty frontier.
        """
        latest: datetime | None = None
        for av in self._availability.values():
            inst = _availability_instant(av)
            if inst is None or not av.is_pit_eligible:
                continue
            if latest is None or inst > latest:
                latest = inst
        if latest is None:
            return datetime.min.replace(tzinfo=UTC)
        return latest

    # -- provenance & reasons ------------------------------------------------

    def _provenance(
        self,
        boundary_kind: str,
        boundary_value: str,
        winner: EligiblePriceObservation | None,
        present: list[EligiblePriceObservation],
        eligible_count: int,
    ) -> PriceProvenance:
        candidates = tuple(sorted(o.observation.price_observation_id for o in present))
        tv_id = ""
        if winner is not None:
            tv_id = winner.observation.market_transformation_version_id
        elif present:
            tv_id = present[0].observation.market_transformation_version_id
        status = PriceStatus.KNOWN if winner is not None else PriceStatus.UNDEFINED
        return PriceProvenance(
            market_transformation_version_id=tv_id,
            boundary_kind=boundary_kind,
            boundary_value=boundary_value,
            selected_price_observation_id=(
                winner.observation.price_observation_id if winner else None
            ),
            selected_raw_document_sha256=(
                winner.observation.raw_document_sha256 if winner else None
            ),
            selected_source_id=winner.observation.source_id if winner else None,
            availability_policy_id=(
                winner.availability.availability_policy_id if winner else None
            ),
            availability_timestamp=(
                winner.availability.derived_public_availability_timestamp
                if winner
                else None
            ),
            present_candidates=candidates,
            eligible_count=eligible_count,
            result_status=status,
            result_reason=None,
        )

    @staticmethod
    def _undefined_reason(
        present: list[EligiblePriceObservation], as_of: datetime
    ) -> PriceUndefinedReason:
        """Classify *why* a key resolved to UNDEFINED (fail-closed, §16)."""
        if not present:
            # The source never reported any bar for this key.
            return PriceUndefinedReason.NOT_REPORTED
        # Some observation exists. If every one is UNKNOWN-availability, it is
        # structurally unavailable; otherwise it exists but is not yet knowable.
        if all(not o.availability.is_pit_eligible for o in present):
            return PriceUndefinedReason.UNAVAILABLE
        return PriceUndefinedReason.NOT_KNOWABLE_YET

    def all_observations(
        self, key: str, *, include_unknown_availability: bool = False
    ) -> list[EligiblePriceObservation]:
        """Every observation for ``obs_key`` - an explicit audit/lineage path.

        Never a research path: only by explicitly opting into
        ``include_unknown_availability`` are ``UNKNOWN`` observations surfaced. This
        mirrors the Phase 5 resolver's audit escape hatch.
        """
        obs = self._observations_for_key(key)
        if include_unknown_availability:
            return obs
        return [o for o in obs if o.availability.is_pit_eligible]


class _ObsIdDesc:
    """A sort wrapper giving *descending* observation-id order in an ascending key.

    The final tiebreak orders ``price_observation_id`` **descending** (a stable
    content hash). Our rank key sorts ascending, so we invert the comparison. Total
    order is preserved.
    """

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __lt__(self, other: _ObsIdDesc) -> bool:
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _ObsIdDesc) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)


def _require_aware(as_of: datetime) -> datetime:
    """Return ``as_of`` as aware UTC, or raise :class:`ModeError` if naive."""
    try:
        return ensure_aware_utc(as_of)
    except ValueError as exc:
        raise ModeError(
            "PIT as_of must be timezone-aware (a naive instant is an ambiguous "
            "look-ahead risk, invariant 15)"
        ) from exc
