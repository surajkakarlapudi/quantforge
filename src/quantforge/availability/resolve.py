"""Point-in-time & revised resolution with impossible-to-confuse result types.

This module answers the two knowledge-state questions of §KS over the *same*
immutable Fact set joined to the sidecar availability triples:

* :meth:`PointInTimeResolver.knowledge_state_as_of` — the **PIT** view: "what value
  would a researcher have known as of instant ``T``?" Returns a :class:`PitValue`.
* :meth:`PointInTimeResolver.revised_truth` — the **REVISED** view: "what is the
  latest known value now, over a pinned :class:`DatasetVersion`?" Returns a
  :class:`RevisedValue`.

The two are the *same* §6.3 selection differing only in the ``as_of`` boundary
(§KS.1), but the API makes them **impossible to confuse** (Additional Requirement,
invariants 27-30):

* **No default mode (invariant 27).** There is no ``get_value()``; the caller must
  call one method or the other. Each requires its own explicit argument — ``PIT``
  a timezone-aware ``as_of`` (a naive one is rejected, invariant 15), ``REVISED`` a
  pinned :class:`DatasetVersion`.
* **Distinct result types (invariant 28).** :class:`PitValue` and
  :class:`RevisedValue` are unrelated frozen types. A ``RevisedValue`` can never be
  passed where a ``PitValue`` is required; converting requires the explicit,
  auditable :meth:`RevisedValue.reinterpret_as_pit` (which itself demands an
  ``as_of`` and re-resolves), so a backtest/factor typed to ``PitValue`` structurally
  cannot consume revised history.
* **Fail-closed gate (invariants 6, 9).** Both modes apply the full §6.1 predicate:
  ``unknown`` availability is never eligible, and no observation with availability
  ``> as_of`` is ever returned. Only an explicit ``include_unknown_availability``
  audit path (never a research path) surfaces ineligible observations.
* **Total-order selection (invariant 16).** §6.3 ranking is a strict total order,
  so the winner is deterministic.

The resolver is constructed with the fact set and an availability lookup, and does
no I/O itself — the façade (:mod:`quantforge.availability.ingest`) wires it to the
stores.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from quantforge.availability.errors import ModeError
from quantforge.availability.model import FilingAvailability
from quantforge.availability.timestamps import ensure_aware_utc, parse_utc
from quantforge.availability.version import DatasetVersion
from quantforge.canonical.model import Fact
from quantforge.registry.model import is_amendment_form

__all__ = [
    "EligibleObservation",
    "PitValue",
    "PointInTimeResolver",
    "RevisedValue",
]


@dataclass(frozen=True, slots=True)
class EligibleObservation:
    """A Fact joined to its filing's availability triple, for ranking/audit.

    Carries the availability fields *by join*, never mutated onto the Fact
    (invariant 7). ``availability_timestamp`` is the aware-UTC instant parsed from
    the triple (``None`` only for ``unknown``, which is never eligible).
    """

    fact: Fact
    availability: FilingAvailability
    availability_timestamp: datetime | None

    @property
    def obs_key(self) -> str:
        return self.fact.obs_key


def _availability_instant(av: FilingAvailability) -> datetime | None:
    ts = av.derived_public_availability_timestamp
    return parse_utc(ts) if ts is not None else None


def _acceptance_instant(fact_av: FilingAvailability) -> datetime | None:
    ts = fact_av.evidence.acceptance_timestamp_utc
    if ts is None:
        return None
    try:
        return parse_utc(ts)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class PitValue:
    """The value knowable as of a historical instant — a **PIT** result (§KS.5).

    A distinct type from :class:`RevisedValue` so a PIT-typed consumer (factor,
    backtest) can never be silently handed revised history (invariant 28). Carries
    the winning observation and full provenance (the winning fact, its availability
    triple, and the ``as_of`` that produced it); ``fact is None`` means no eligible
    observation existed by ``as_of`` (a legitimate "not yet knowable" answer, not
    an error).
    """

    obs_key: str
    as_of: datetime
    fact: Fact | None
    availability: FilingAvailability | None
    eligible_count: int

    @property
    def is_known(self) -> bool:
        return self.fact is not None


@dataclass(frozen=True, slots=True)
class RevisedValue:
    """The latest known value over a pinned snapshot — a **REVISED** result (§KS.5).

    Deliberately *not* interchangeable with :class:`PitValue`. To use a revised
    figure in a PIT context the caller must call :meth:`reinterpret_as_pit` with an
    explicit ``as_of`` — an auditable, intentional conversion, never implicit
    (invariant 28). ``dataset_version_id`` pins the ingestion frontier so the
    answer is reproducible (§KS.2).
    """

    obs_key: str
    dataset_version_id: str
    fact: Fact | None
    availability: FilingAvailability | None
    eligible_count: int

    @property
    def is_known(self) -> bool:
        return self.fact is not None

    def reinterpret_as_pit(
        self, resolver: PointInTimeResolver, as_of: datetime
    ) -> PitValue:
        """Explicit, auditable conversion to a PIT answer at ``as_of``.

        This does **not** reuse the revised winner; it re-runs the PIT resolution
        at ``as_of`` over the same history, so the result genuinely reflects what
        was knowable then. The method exists precisely so that any crossing from
        revised to PIT is a visible, intentional call — never an implicit cast.
        """
        return resolver.knowledge_state_as_of(self.obs_key, as_of)


class PointInTimeResolver:
    """Resolve PIT / revised values over one immutable fact set + availability.

    Construction takes the facts and a ``filing_id → FilingAvailability`` mapping.
    Facts whose filing has no availability record are treated as ``unknown``
    (fail closed) — they are never returned by a research path.
    """

    def __init__(
        self,
        facts: Iterable[Fact],
        availability_by_filing: Mapping[str, FilingAvailability],
    ) -> None:
        self._facts: tuple[Fact, ...] = tuple(facts)
        self._availability = dict(availability_by_filing)

    # -- eligibility & ranking ----------------------------------------------

    def _availability_for(self, fact: Fact) -> FilingAvailability | None:
        return self._availability.get(fact.filing_id)

    def _observations_for_key(self, obs_key: str) -> list[EligibleObservation]:
        """All observations (any status) for ``obs_key``, availability joined."""
        out: list[EligibleObservation] = []
        for fact in self._facts:
            if fact.obs_key != obs_key:
                continue
            av = self._availability_for(fact)
            if av is None:
                # No availability record → treat as unknown (fail closed).
                continue
            out.append(
                EligibleObservation(
                    fact=fact,
                    availability=av,
                    availability_timestamp=_availability_instant(av),
                )
            )
        return out

    @staticmethod
    def _is_eligible(obs: EligibleObservation, as_of: datetime) -> bool:
        """The full §6.1 predicate: status gate, then temporal boundary."""
        av = obs.availability
        if not av.is_pit_eligible:  # (A) fail-closed gate — unknown excluded
            return False
        if obs.availability_timestamp is None:  # (B) known boundary exists
            return False
        return obs.availability_timestamp <= as_of  # (C) not the future

    @staticmethod
    def _rank_key(obs: EligibleObservation) -> tuple[object, ...]:
        """§6.3 total-order ranking key (descending fields negated for sort).

        Rank most-recent-known first: availability desc, then acceptance desc,
        then ``/A`` outranks base form, then accession desc. We build a key sorted
        **ascending** that puts the winner first by negating each descending
        field. Timestamps are compared via POSIX seconds; the amendment flag and
        accession are compared as their natural order, negated.
        """
        assert obs.availability_timestamp is not None  # eligible ⇒ present
        avail = obs.availability_timestamp.timestamp()
        acc_instant = _acceptance_instant(obs.availability)
        acceptance = (
            acc_instant.timestamp() if acc_instant is not None else float("-inf")
        )
        form = obs.fact.provenance.accession  # accession for final tiebreak
        is_amendment = is_amendment_form(_form_of(obs))
        # Ascending sort → smallest first, so negate the "desc" fields. For the
        # amendment flag, /A should outrank base ⇒ amendment sorts first ⇒ use 0
        # for amendment and 1 for base. Accession desc ⇒ invert lexthan via a
        # reverse marker handled by the caller.
        return (
            -avail,
            -acceptance,
            0 if is_amendment else 1,
            _AccessionDesc(form),
        )

    def _select(
        self, obs_key: str, as_of: datetime
    ) -> tuple[EligibleObservation | None, int]:
        """Return the §6.3 winner among eligible observations, and eligible count."""
        eligible = [
            obs
            for obs in self._observations_for_key(obs_key)
            if self._is_eligible(obs, as_of)
        ]
        if not eligible:
            return None, 0
        eligible.sort(key=self._rank_key)
        return eligible[0], len(eligible)

    # -- PIT view -----------------------------------------------------------

    def knowledge_state_as_of(self, obs_key: str, as_of: datetime) -> PitValue:
        """Resolve the PIT value for ``obs_key`` at historical ``as_of``.

        ``as_of`` must be timezone-aware (invariant 15); a naive instant raises
        :class:`ModeError`. Applies the §6.1 gate then §6.3 selection. Returns a
        :class:`PitValue` — never a bare fact — so the result type records the
        mode (invariant 28). An ``obs_key`` with no eligible observation by
        ``as_of`` yields a ``PitValue`` with ``fact=None`` (legitimately unknown).
        """
        aware = _require_aware(as_of)
        winner, count = self._select(obs_key, aware)
        return PitValue(
            obs_key=obs_key,
            as_of=aware,
            fact=winner.fact if winner else None,
            availability=winner.availability if winner else None,
            eligible_count=count,
        )

    def eligible_history_as_of(
        self, obs_key: str, as_of: datetime
    ) -> list[EligibleObservation]:
        """The full eligible lineage for ``obs_key`` at ``as_of`` (§6.3 order).

        For audit/lineage. Ranked winner-first by the §6.3 total order. Still
        fail-closed: ``unknown`` observations are excluded.
        """
        aware = _require_aware(as_of)
        eligible = [
            obs
            for obs in self._observations_for_key(obs_key)
            if self._is_eligible(obs, aware)
        ]
        eligible.sort(key=self._rank_key)
        return eligible

    # -- REVISED view -------------------------------------------------------

    def revised_truth(
        self, obs_key: str, dataset_version: DatasetVersion
    ) -> RevisedValue:
        """Resolve the latest known value over a pinned ``dataset_version``.

        ``REVISED`` is ``PIT`` at the ingestion frontier (§KS.2): we resolve at the
        maximum availability instant present in this fact set (the frontier), which
        is deterministic and reproducible for a pinned snapshot — never a wall-clock
        read (invariant 21, 30). Requires an explicit :class:`DatasetVersion` so a
        caller cannot obtain revised semantics by omitting an argument (invariant
        27). Returns a :class:`RevisedValue`, inadmissible as a PIT source
        (invariant 28).
        """
        frontier = self._ingestion_frontier()
        winner, count = self._select(obs_key, frontier)
        return RevisedValue(
            obs_key=obs_key,
            dataset_version_id=dataset_version.dataset_version_id,
            fact=winner.fact if winner else None,
            availability=winner.availability if winner else None,
            eligible_count=count,
        )

    def _ingestion_frontier(self) -> datetime:
        """The latest availability instant across all eligible observations.

        This is the reproducible stand-in for "now" (§KS.2): resolving at it
        admits every currently-public observation. Deterministic over a pinned
        fact set. If nothing is eligible anywhere, returns the min datetime so no
        observation clears — a fail-closed empty frontier.
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

    # -- audit path (opt out of PIT) ----------------------------------------

    def all_observations(
        self, obs_key: str, *, include_unknown_availability: bool = False
    ) -> list[EligibleObservation]:
        """Every observation for ``obs_key`` — an explicit audit/lineage path.

        Never a research path: it is reachable only by explicitly opting into
        ``include_unknown_availability`` to also surface ``unknown`` observations
        (invariant 9). Without the flag it returns only status-eligible
        observations regardless of ``as_of`` (no temporal filter) for lineage
        inspection.
        """
        obs = self._observations_for_key(obs_key)
        if include_unknown_availability:
            return obs
        return [o for o in obs if o.availability.is_pit_eligible]


class _AccessionDesc:
    """A sort wrapper giving *descending* accession order within an ascending key.

    §6.3 step 4 breaks the final tie by ``accession_number`` **descending**. Our
    rank key sorts ascending, so we wrap the accession string and invert its
    comparison, keeping the overall key a clean tuple. Total order is preserved.
    """

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __lt__(self, other: _AccessionDesc) -> bool:
        # Descending: a "smaller" wrapped value is the lexicographically larger
        # accession, so it sorts earlier (wins) in an ascending sort.
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _AccessionDesc) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)


def _form_of(obs: EligibleObservation) -> str:
    """The filing's form for the ``/A``-outranks-base tiebreak.

    The Fact does not carry the form; the availability evidence does. We use the
    evidence form (populated by the façade from the FilingRecord). Falls back to
    the empty string (treated as non-amendment) when absent.
    """
    return obs.availability.evidence.form or ""


def _require_aware(as_of: datetime) -> datetime:
    """Return ``as_of`` as aware UTC, or raise :class:`ModeError` if naive."""
    try:
        return ensure_aware_utc(as_of)
    except ValueError as exc:
        raise ModeError(
            "PIT as_of must be timezone-aware (a naive instant is an ambiguous "
            "look-ahead risk, invariant 15)"
        ) from exc
