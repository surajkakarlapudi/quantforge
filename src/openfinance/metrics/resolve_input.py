"""Resolve one formula input to a single fact value — the concept-selection rule.

This module houses §7 of ``docs/metrics.md``: turning one :class:`InputBinding`
(an ordered ``(taxonomy, local_name)`` candidate list + period/dimension/unit
selectors) into exactly one resolved numeric value, or a first-class ``UNDEFINED``
reason — never a guess, never a fabricated concept.

The load-bearing subtlety (§7.0): a :class:`~openfinance.canonical.model.Fact`'s
``obs_key`` embeds the *year-versioned* concept URI and the *raw structural*
``unit_ref``, so a formula **cannot** construct an ``obs_key`` a priori. Instead we
match candidates against the filer's facts by ``(taxonomy, local_name)`` — exactly
the prefix-/version-independent identity Phase 4 guarantees — collect the *distinct*
``obs_key``s a candidate produced, and resolve each through the **Phase 5** resolver
in the metric's mode. Selection is deterministic (first candidate in list order that
yields a ``KNOWN`` numeric fact wins, Decision D3), and every present candidate is
recorded for audit (§9). Phase 7 never re-implements eligibility or restatement
ordering — that is Phase 5's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from openfinance.availability.resolve import (
    PitValue,
    PointInTimeResolver,
    RevisedValue,
)
from openfinance.availability.timestamps import format_utc_z
from openfinance.availability.version import DatasetVersion
from openfinance.canonical.model import Fact
from openfinance.metrics.formula import InputBinding
from openfinance.metrics.model import (
    InputResolution,
    MetricPeriod,
    MetricStatus,
    UndefinedReason,
)
from openfinance.metrics.units import ResolvedUnit, unit_of_fact
from openfinance.xbrl.contexts import PeriodType
from openfinance.xbrl.dimensions import dimensions_hash

__all__ = ["MetricBoundary", "ResolvedInput", "resolve_input"]

#: The ``dimensions_hash`` of the consolidated (undimensioned) context — the
#: sha256 of the empty sentinel. Computed once from the Phase 3 primitive so it can
#: never drift from what canonicalization writes onto a consolidated fact (§7.2,
#: §20). ``dimensions_hash(())`` hashes ``EMPTY_DIMENSIONS_SENTINEL``.
CONSOLIDATED_DIMENSIONS_HASH = dimensions_hash(())


@dataclass(frozen=True, slots=True)
class MetricBoundary:
    """A knowledge-state boundary that resolves an ``obs_key`` in exactly one mode.

    Carries *either* a timezone-aware ``as_of`` (PIT) *or* a pinned
    :class:`DatasetVersion` (REVISED), never both — so a single metric evaluation
    resolves all inputs at one consistent boundary (§5.1). ``resolve`` dispatches to
    the matching Phase 5 method, returning its distinct
    :class:`~openfinance.availability.resolve.PitValue` /
    :class:`~openfinance.availability.resolve.RevisedValue`.
    """

    as_of: datetime | None
    dataset_version: DatasetVersion | None

    @classmethod
    def pit(cls, as_of: datetime) -> MetricBoundary:
        return cls(as_of=as_of, dataset_version=None)

    @classmethod
    def revised(cls, dataset_version: DatasetVersion) -> MetricBoundary:
        return cls(as_of=None, dataset_version=dataset_version)

    @property
    def kind(self) -> str:
        """``"pit"`` or ``"rev"`` — the boundary discriminator (§6.2)."""
        return "pit" if self.as_of is not None else "rev"

    @property
    def value(self) -> str:
        """The serialized boundary: aware-UTC ``as_of`` (PIT) or dataset id (REV)."""
        if self.as_of is not None:
            return format_utc_z(self.as_of)
        assert self.dataset_version is not None
        return self.dataset_version.dataset_version_id

    def resolve(
        self, resolver: PointInTimeResolver, obs_key: str
    ) -> PitValue | RevisedValue:
        """Resolve ``obs_key`` via the Phase 5 resolver in this boundary's mode."""
        if self.as_of is not None:
            return resolver.knowledge_state_as_of(obs_key, self.as_of)
        assert self.dataset_version is not None
        return resolver.revised_truth(obs_key, self.dataset_version)


@dataclass(frozen=True, slots=True)
class ResolvedInput:
    """One input's resolved value + unit + audit record, for the evaluator (§7).

    ``value``/``unit`` are populated only when ``resolution.status`` is ``KNOWN``;
    an ``UNDEFINED`` input carries ``None`` for both and the failing reason in
    ``resolution``. The evaluator combines the values; it reads the resolution for
    provenance.
    """

    resolution: InputResolution
    value: Decimal | None
    unit: ResolvedUnit | None

    @property
    def status(self) -> MetricStatus:
        return self.resolution.status


def _period_aligned(fact: Fact, binding: InputBinding, period: MetricPeriod) -> bool:
    """Whether ``fact`` aligns to the requested period under the binding's kind (§6.4).

    * An ``INSTANT`` input must be an instant fact **at the request's**
      ``period_end`` — the balance point for an ``INSTANT`` metric, or the *ending*
      balance for a ``DURATION`` metric (the single mixed-period rule, §6.4).
    * A ``DURATION`` input must be a duration fact spanning **exactly** the request's
      ``(period_start, period_end)`` — never a different span.

    A period that does not align is simply not a match (it is excluded from
    candidate resolution); the metric fails closed to ``MISSING_INPUT`` /
    ``PERIOD_UNALIGNED`` only if *no* aligned fact exists for a required input.
    """
    if binding.period_kind is PeriodType.INSTANT:
        return fact.period_type is PeriodType.INSTANT and (
            fact.period_end == period.period_end
        )
    # DURATION input: the exact fiscal span.
    return (
        fact.period_type is PeriodType.DURATION
        and fact.period_start == period.period_start
        and fact.period_end == period.period_end
    )


def _is_consolidated(fact: Fact) -> bool:
    """Whether ``fact`` is the consolidated (undimensioned) observation (§7.2)."""
    return fact.dimensions_hash == CONSOLIDATED_DIMENSIONS_HASH


def _obs_keys_for_candidate(
    facts: list[Fact],
    binding: InputBinding,
    period: MetricPeriod,
    taxonomy: str,
    local_name: str,
) -> list[str]:
    """Distinct, sorted ``obs_key``s matching a candidate, pre-filtered (§7.0, §7.1).

    Matches by ``(taxonomy, local_name)`` — never a pre-built ``obs_key`` — among
    the consolidated, period-aligned facts. Sorted so multiple structural units for
    one concept resolve in a deterministic order.
    """
    keys = {
        fact.obs_key
        for fact in facts
        if fact.taxonomy.value == taxonomy
        and fact.concept.local_name == local_name
        and _is_consolidated(fact)
        and _period_aligned(fact, binding, period)
    }
    return sorted(keys)


def resolve_input(
    binding: InputBinding,
    facts: list[Fact],
    resolver: PointInTimeResolver,
    boundary: MetricBoundary,
    period: MetricPeriod,
) -> ResolvedInput:
    """Resolve one :class:`InputBinding` to a single value or an ``UNDEFINED`` reason.

    Walks ``binding.concept_candidates`` in order (§7 steps 1-5): for each candidate
    it matches obs_keys by ``(taxonomy, local_name)``, resolves each through the
    Phase 5 ``boundary`` (mode-consistent), and takes the **first** candidate that
    yields a ``KNOWN``, non-nil, numeric fact whose unit matches the expectation
    (Decision D3). Every candidate that resolved to a known fact is recorded in
    ``present_candidates`` for audit — the selected one and the discarded ones.

    Fails closed with a specific reason and **no** exception (§13): ``NIL_INPUT`` for
    a nil fact, ``NON_NUMERIC_INPUT`` for a text-only fact, ``UNIT_MISMATCH`` for a
    unit outside the expected family, else ``MISSING_INPUT`` when nothing resolved.
    """
    present_labels: list[str] = []
    selected: _Winner | None = None
    saw_nil = False
    saw_non_numeric = False
    saw_unit_mismatch = False

    for candidate in binding.concept_candidates:
        candidate_present = False
        for obs_key in _obs_keys_for_candidate(
            facts, binding, period, candidate.taxonomy.value, candidate.local_name
        ):
            resolved = boundary.resolve(resolver, obs_key)
            fact = resolved.fact
            if fact is None:  # not known at this boundary (fail-closed, not present)
                continue
            candidate_present = True
            if fact.is_nil:  # nil ≠ zero (invariant 25) — present but not a number
                saw_nil = True
                continue
            if fact.value_numeric_str is None:  # only value_text — non-numeric
                saw_non_numeric = True
                continue
            unit = unit_of_fact(fact, binding.unit_expectation)
            if unit is None:  # present & numeric but wrong unit family (no convert)
                saw_unit_mismatch = True
                continue
            if selected is None:  # first valid candidate wins (list order, D3)
                selected = _Winner(
                    candidate_label=candidate.label,
                    taxonomy=candidate.taxonomy.value,
                    local_name=candidate.local_name,
                    fact=fact,
                    availability_policy_id=(
                        resolved.availability.availability_policy_id
                        if resolved.availability is not None
                        else None
                    ),
                    unit=unit,
                    value=Decimal(fact.value_numeric_str),
                )
        if candidate_present:
            present_labels.append(candidate.label)

    if selected is not None:
        return ResolvedInput(
            resolution=InputResolution(
                name=binding.name,
                status=MetricStatus.KNOWN,
                selected_taxonomy=selected.taxonomy,
                selected_local_name=selected.local_name,
                selected_fact_id=selected.fact.fact_id,
                selected_availability_policy_id=selected.availability_policy_id,
                present_candidates=tuple(present_labels),
            ),
            value=selected.value,
            unit=selected.unit,
        )

    # Nothing usable — choose the most informative fail-closed reason (§7.4, §13).
    if saw_nil:
        reason = UndefinedReason.NIL_INPUT
    elif saw_non_numeric:
        reason = UndefinedReason.NON_NUMERIC_INPUT
    elif saw_unit_mismatch:
        reason = UndefinedReason.UNIT_MISMATCH
    else:
        reason = UndefinedReason.MISSING_INPUT
    return ResolvedInput(
        resolution=InputResolution(
            name=binding.name,
            status=MetricStatus.UNDEFINED,
            present_candidates=tuple(present_labels),
            reason=reason,
        ),
        value=None,
        unit=None,
    )


@dataclass(frozen=True, slots=True)
class _Winner:
    """The first valid candidate for an input (internal to ``resolve_input``)."""

    candidate_label: str
    taxonomy: str
    local_name: str
    fact: Fact
    availability_policy_id: str | None
    unit: ResolvedUnit
    value: Decimal
