"""The deterministic universe-construction filters (Phase 9.2).

A :class:`~quantforge.universe.specification.UniverseSpecification` is an *ordered*
list of filters; the :class:`~quantforge.universe.builder.UniverseBuilder` applies
them left-to-right to resolve an eligible membership. This module defines the three
initial filter types and the surrounding vocabulary — and nothing more (no ranking,
no weighting, no optimization, no backtesting; those are later phases).

The layer **composes, never duplicates** the existing phases. A filter owns no
resolution, no arithmetic, and no external I/O:

* :class:`ExplicitCompanyFilter` resolves identifiers through the *existing*
  :class:`~quantforge.identity.resolve.CompanyResolver` (the Phase 9.1 doctrine: no
  new identifier system, no implicit "all filers").
* :class:`CompanyMetricFilter` evaluates a *registered* Phase 7 metric at one
  PIT/REVISED boundary via the *existing*
  :class:`~quantforge.metrics.engine.MetricEngine`. An unknown ``metric_key`` fails
  closed against the live :class:`~quantforge.metrics.registry.FormulaRegistry` —
  which is exactly what rejects a not-yet-modeled metric such as ``market_cap`` (SEC
  filings carry no share prices, so no such formula exists).
* :class:`SectorFilter` matches against a **caller-supplied**
  :class:`SectorClassification`. QuantForge stores no sector/SIC data, and this
  layer never fabricates it or reaches for an external API (Principle 8); the sector
  mapping is explicit, content-addressed reference data, exactly as a factor
  universe is explicit and caller-supplied.

Two failure kinds are kept sharply separate (mirroring Phases 7-8):

* A **data condition** — a metric ``UNDEFINED`` at the boundary, a threshold not
  met, or a company with no sector under the supplied classification — is **never**
  an exception. The company is dropped and recorded as an :class:`ExcludedCompany`
  carrying a machine-readable :class:`ExclusionReason` (zero information loss).
* A **specification defect** — narrowing before any explicit source is established,
  an unknown metric, or a sector rule with no classification supplied — *is* raised
  as :class:`~quantforge.universe.errors.UniverseSpecificationError`.

Every filter is a frozen, serializable value whose ``filter_id`` is a content hash
over its declaration, so identity is a pure function of the declared parameters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TYPE_CHECKING

from quantforge.metrics.model import MetricStatus
from quantforge.registry.identity import cik_from_company_id
from quantforge.universe.errors import UniverseSpecificationError
from quantforge.universe.identity import classification_id as _classification_id
from quantforge.universe.identity import filter_id as _filter_id

if TYPE_CHECKING:
    from quantforge.identity.model import CompanyIdentity
    from quantforge.metrics.model import (
        MetricPeriod,
        PitMetricValue,
        RevisedMetricValue,
    )

__all__ = [
    "CompanyMetricFilter",
    "ComparisonOperator",
    "ExcludedCompany",
    "ExclusionReason",
    "ExplicitCompanyFilter",
    "FilterContext",
    "FilterKind",
    "FilterOutcome",
    "SectorClassification",
    "SectorFilter",
    "UniverseFilter",
    "filter_from_dict",
]


class FilterKind(StrEnum):
    """The discriminator for a filter's serialized form (deterministic dispatch)."""

    EXPLICIT = "explicit"
    METRIC = "metric"
    SECTOR = "sector"


class ComparisonOperator(StrEnum):
    """The comparison a :class:`CompanyMetricFilter` / :class:`SectorFilter` applies.

    Numeric operators (``>``/``>=``/``<``/``<=``) are for metric thresholds; equality
    operators (``==``/``!=``) serve both metric equality and sector membership.
    """

    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    EQ = "eq"
    NE = "ne"

    def compare_decimal(self, left: Decimal, right: Decimal) -> bool:
        """Evaluate ``left <op> right`` for two exact decimals (total order)."""
        if self is ComparisonOperator.GT:
            return left > right
        if self is ComparisonOperator.GE:
            return left >= right
        if self is ComparisonOperator.LT:
            return left < right
        if self is ComparisonOperator.LE:
            return left <= right
        if self is ComparisonOperator.EQ:
            return left == right
        return left != right

    def compare_sector(self, actual: str, required: str) -> bool:
        """Evaluate a sector membership comparison (only ``==`` / ``!=`` are valid)."""
        if self is ComparisonOperator.EQ:
            return actual == required
        if self is ComparisonOperator.NE:
            return actual != required
        raise UniverseSpecificationError(
            f"a sector comparison supports only == / != (got {self.value!r})"
        )


class ExclusionReason(StrEnum):
    """Why a candidate was dropped by a filter — a first-class, recorded outcome.

    Never an error: an excluded company is a legitimate data condition, retained in
    provenance so "who was dropped, by which filter, and why?" is always answerable
    (zero information loss, mirroring the metric layer's ``UndefinedReason``).
    """

    #: An intersecting explicit filter's set did not contain the candidate.
    NOT_IN_EXPLICIT_SET = "not_in_explicit_set"
    #: The metric was ``UNDEFINED`` at the boundary (detail carries the reason).
    METRIC_UNDEFINED = "metric_undefined"
    #: The metric was ``KNOWN`` but the threshold comparison was false.
    METRIC_THRESHOLD_NOT_MET = "metric_threshold_not_met"
    #: The company has no sector under the supplied classification.
    SECTOR_UNCLASSIFIED = "sector_unclassified"
    #: The company's sector did not satisfy the required comparison.
    SECTOR_MISMATCH = "sector_mismatch"


@dataclass(frozen=True, slots=True)
class ExcludedCompany:
    """One company a filter dropped, with the filter and the reason (provenance)."""

    company_id: str
    filter_id: str
    filter_kind: FilterKind
    reason: ExclusionReason
    #: Optional human/machine detail: the undefined reason, the metric value, or the
    #: company's actual sector — enough to audit the drop without re-running.
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "filter_id": self.filter_id,
            "filter_kind": self.filter_kind.value,
            "reason": self.reason.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class FilterOutcome:
    """The result of applying one filter: kept candidates + recorded exclusions.

    ``kept`` preserves the input's first-seen order (order is load-bearing
    downstream); ``excluded`` preserves input order too, so the whole outcome is a
    deterministic function of the ordered input.
    """

    kept: tuple[CompanyIdentity, ...]
    excluded: tuple[ExcludedCompany, ...]


@dataclass(frozen=True, slots=True)
class SectorClassification:
    """A caller-supplied, content-addressed ``company_id → sector`` mapping.

    QuantForge derives no sector/SIC data of its own, so a :class:`SectorFilter`
    matches against explicit reference data the caller supplies — exactly as a factor
    universe is explicit and caller-supplied (Decision F1). ``scheme`` names the
    taxonomy (e.g. ``"gics"``, ``"sic-division"``) so two classifications under
    different schemes never silently mix. Assignments are keyed by the canonical
    ``company_id`` (never a ticker), matching how a resolved universe iterates.
    """

    scheme: str
    assignments: Mapping[str, str]

    def sector_of(self, company_id: str) -> str | None:
        """The company's sector under this scheme, or ``None`` if unclassified."""
        return self.assignments.get(company_id)

    @property
    def classification_id(self) -> str:
        """Content hash over ``scheme`` + the sorted ``company_id → sector`` pairs."""
        return _classification_id(self.scheme, dict(self.assignments))

    def to_dict(self) -> dict[str, object]:
        return {
            "scheme": self.scheme,
            "classification_id": self.classification_id,
            "assignments": dict(sorted(self.assignments.items())),
        }


class FilterContext:
    """The composition surface a filter reads at build time — never new logic.

    Wires a filter to the *existing* resolver and metric engine at one fixed
    PIT/REVISED boundary, plus any caller-supplied sector classifications. Built by
    the :class:`~quantforge.universe.builder.UniverseBuilder`; the two constructors
    (:meth:`pit` / :meth:`revised`) make the boundary explicit and impossible to
    confuse (invariant 27). A context carries no mutable state — evaluating a filter
    twice yields identical results.
    """

    def __init__(
        self,
        *,
        resolver: object,
        metric_engine: object,
        as_of: datetime | None,
        dataset_version: object | None,
        classifications: tuple[SectorClassification, ...] = (),
    ) -> None:
        # Exactly one boundary is set — enforced by the two named constructors.
        self._resolver = resolver
        self._metric_engine = metric_engine
        self._as_of = as_of
        self._dataset_version = dataset_version
        self._classifications = {c.scheme: c for c in classifications}

    @classmethod
    def pit(
        cls,
        *,
        resolver: object,
        metric_engine: object,
        as_of: datetime,
        classifications: tuple[SectorClassification, ...] = (),
    ) -> FilterContext:
        """A context that evaluates metric filters at a point-in-time ``as_of``."""
        return cls(
            resolver=resolver,
            metric_engine=metric_engine,
            as_of=as_of,
            dataset_version=None,
            classifications=classifications,
        )

    @classmethod
    def revised(
        cls,
        *,
        resolver: object,
        metric_engine: object,
        dataset_version: object,
        classifications: tuple[SectorClassification, ...] = (),
    ) -> FilterContext:
        """A context that evaluates metric filters over a pinned ``dataset_version``."""
        return cls(
            resolver=resolver,
            metric_engine=metric_engine,
            as_of=None,
            dataset_version=dataset_version,
            classifications=classifications,
        )

    @property
    def boundary_kind(self) -> str:
        """``"pit"`` or ``"rev"`` — the boundary discriminator for provenance."""
        return "pit" if self._as_of is not None else "rev"

    @property
    def boundary_value(self) -> str:
        """The aware-UTC ``as_of`` (PIT) or the ``dataset_version_id`` (REVISED)."""
        if self._as_of is not None:
            from quantforge.availability.timestamps import format_utc_z

            return format_utc_z(self._as_of)
        from quantforge.availability.version import DatasetVersion

        assert isinstance(self._dataset_version, DatasetVersion)
        return self._dataset_version.dataset_version_id

    def resolve(self, identifier: str, by: str | None) -> CompanyIdentity:
        """Resolve one identifier through the existing company identity layer."""
        from quantforge.identity.resolve import CompanyResolver

        assert isinstance(self._resolver, CompanyResolver)
        return self._resolver.resolve(identifier, by=by)

    def require_metric(self, metric_key: str) -> None:
        """Validate ``metric_key`` against the live registry — fail closed if unknown.

        Delegates to the Phase 7 :class:`FormulaRegistry`, so a not-yet-modeled
        metric (``market_cap`` and the like) is refused here rather than silently
        excluding every company. Re-raised as a specification defect.
        """
        from quantforge.metrics.engine import MetricEngine
        from quantforge.metrics.errors import FormulaConfigurationError

        assert isinstance(self._metric_engine, MetricEngine)
        try:
            self._metric_engine.registry.get(metric_key)
        except FormulaConfigurationError as exc:
            raise UniverseSpecificationError(
                f"CompanyMetricFilter names unknown metric_key {metric_key!r}; "
                f"known metrics: {self._metric_engine.registry.metric_keys()}"
            ) from exc

    def metric(
        self, metric_key: str, company_id: str, period: MetricPeriod
    ) -> PitMetricValue | RevisedMetricValue:
        """Evaluate a Phase 7 metric for one company at this context's boundary.

        Dispatches to the *existing* engine's PIT or REVISED method by boundary —
        never re-implementing eligibility, restatement order, or arithmetic.
        """
        from quantforge.availability.version import DatasetVersion
        from quantforge.metrics.engine import MetricEngine

        assert isinstance(self._metric_engine, MetricEngine)
        cik = cik_from_company_id(company_id)
        if self._as_of is not None:
            return self._metric_engine.metric_as_of(
                metric_key, cik, period, self._as_of
            )
        assert isinstance(self._dataset_version, DatasetVersion)
        return self._metric_engine.revised_metric(
            metric_key, cik, period, self._dataset_version
        )

    def classification(self, scheme: str) -> SectorClassification | None:
        """The caller-supplied classification for ``scheme``, if any."""
        return self._classifications.get(scheme)


class UniverseFilter(ABC):
    """One deterministic selection rule over an ordered candidate set.

    A filter is a pure, serializable value. :meth:`apply` narrows an ordered set of
    :class:`CompanyIdentity` candidates (or seeds it, for an explicit source),
    returning the kept candidates and the recorded exclusions. ``filter_id`` is a
    content hash over :meth:`to_dict`, so identity depends only on declared
    parameters.
    """

    @property
    @abstractmethod
    def kind(self) -> FilterKind:
        """The filter's kind discriminator."""

    @property
    @abstractmethod
    def is_source(self) -> bool:
        """Whether this filter can *establish* membership from an empty input.

        Only an explicit source may run first; a narrowing filter applied before any
        source is established is a specification defect (no implicit "all filers").
        """

    @abstractmethod
    def to_dict(self) -> dict[str, object]:
        """The canonical declaration hashed into :attr:`filter_id`."""

    @abstractmethod
    def apply(
        self,
        candidates: tuple[CompanyIdentity, ...] | None,
        context: FilterContext,
    ) -> FilterOutcome:
        """Apply the rule. ``candidates`` is ``None`` before any source has run."""

    @property
    def filter_id(self) -> str:
        """Content hash over the filter's declaration (§9.2)."""
        return _filter_id(self.to_dict())


@dataclass(frozen=True, slots=True)
class ExplicitCompanyFilter(UniverseFilter):
    """Select an explicit list of companies, resolved through the identity layer.

    As the **source** of a specification (run first, on an empty input) it resolves
    its identifiers into the seed membership, de-duplicated in first-seen order. Run
    *after* a source it acts as an intersecting whitelist: candidates not in its
    resolved set are excluded (:data:`ExclusionReason.NOT_IN_EXPLICIT_SET`). ``by``
    optionally forces the interpretation (``"ticker"``/``"cik"``/``"name"``) for
    every identifier, mirroring :meth:`Company.resolve`.
    """

    identifiers: tuple[str, ...]
    by: str | None = None

    @property
    def kind(self) -> FilterKind:
        return FilterKind.EXPLICIT

    @property
    def is_source(self) -> bool:
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "identifiers": list(self.identifiers),
            "by": self.by,
        }

    def apply(
        self,
        candidates: tuple[CompanyIdentity, ...] | None,
        context: FilterContext,
    ) -> FilterOutcome:
        # Resolve the declared identifiers into first-seen-ordered identities.
        resolved: list[CompanyIdentity] = []
        resolved_ids: set[str] = set()
        for identifier in self.identifiers:
            identity = context.resolve(identifier, self.by)
            if identity.company_id in resolved_ids:
                continue
            resolved_ids.add(identity.company_id)
            resolved.append(identity)

        if candidates is None:
            # Source role: the resolved set *is* the seed membership.
            return FilterOutcome(kept=tuple(resolved), excluded=())

        # Whitelist role: keep only prior candidates in the resolved set, in the
        # prior order; record the rest as excluded.
        kept: list[CompanyIdentity] = []
        excluded: list[ExcludedCompany] = []
        for candidate in candidates:
            if candidate.company_id in resolved_ids:
                kept.append(candidate)
            else:
                excluded.append(
                    ExcludedCompany(
                        company_id=candidate.company_id,
                        filter_id=self.filter_id,
                        filter_kind=self.kind,
                        reason=ExclusionReason.NOT_IN_EXPLICIT_SET,
                    )
                )
        return FilterOutcome(kept=tuple(kept), excluded=tuple(excluded))


@dataclass(frozen=True, slots=True)
class CompanyMetricFilter(UniverseFilter):
    """Keep companies whose Phase 7 metric satisfies a threshold at the boundary.

    Declares a registered ``metric_key`` (e.g. ``"working_capital"``), the
    fiscal :class:`MetricPeriod` to evaluate, a :class:`ComparisonOperator`, and a
    ``threshold`` (an exact decimal string, matching the metric layer's
    ``value_numeric_str`` discipline). At build time the metric is evaluated at the
    context's PIT/REVISED boundary via the existing engine:

    * ``UNDEFINED`` (input not yet public, missing, etc.) → excluded
      (:data:`ExclusionReason.METRIC_UNDEFINED`, detail = the reason);
    * ``KNOWN`` but the comparison is false → excluded
      (:data:`ExclusionReason.METRIC_THRESHOLD_NOT_MET`, detail = the value);
    * ``KNOWN`` and the comparison holds → kept.

    An unknown ``metric_key`` fails closed as a specification defect — the mechanism
    that rejects a not-yet-modeled metric such as ``market_cap``.
    """

    metric_key: str
    period: MetricPeriod
    operator: ComparisonOperator
    threshold: str

    @property
    def kind(self) -> FilterKind:
        return FilterKind.METRIC

    @property
    def is_source(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "metric_key": self.metric_key,
            "period": self.period.to_dict(),
            "operator": self.operator.value,
            "threshold": self.threshold,
        }

    def _threshold_decimal(self) -> Decimal:
        try:
            return Decimal(self.threshold)
        except InvalidOperation as exc:
            raise UniverseSpecificationError(
                f"CompanyMetricFilter threshold {self.threshold!r} is not a number"
            ) from exc

    def apply(
        self,
        candidates: tuple[CompanyIdentity, ...] | None,
        context: FilterContext,
    ) -> FilterOutcome:
        if candidates is None:
            raise UniverseSpecificationError(
                "a CompanyMetricFilter cannot establish membership; a specification "
                "must begin with an explicit source (there is no implicit universe)"
            )
        context.require_metric(self.metric_key)
        threshold = self._threshold_decimal()
        kept: list[CompanyIdentity] = []
        excluded: list[ExcludedCompany] = []
        for candidate in candidates:
            metric = context.metric(self.metric_key, candidate.company_id, self.period)
            drop = self._evaluate(candidate.company_id, metric, threshold)
            if drop is None:
                kept.append(candidate)
            else:
                excluded.append(drop)
        return FilterOutcome(kept=tuple(kept), excluded=tuple(excluded))

    def _evaluate(
        self,
        company_id: str,
        metric: PitMetricValue | RevisedMetricValue,
        threshold: Decimal,
    ) -> ExcludedCompany | None:
        """Return an :class:`ExcludedCompany` to drop the company, else ``None``."""
        if metric.status is not MetricStatus.KNOWN or metric.value_numeric_str is None:
            return ExcludedCompany(
                company_id=company_id,
                filter_id=self.filter_id,
                filter_kind=self.kind,
                reason=ExclusionReason.METRIC_UNDEFINED,
                detail=metric.reason.value if metric.reason is not None else None,
            )
        value = Decimal(metric.value_numeric_str)
        if self.operator.compare_decimal(value, threshold):
            return None
        return ExcludedCompany(
            company_id=company_id,
            filter_id=self.filter_id,
            filter_kind=self.kind,
            reason=ExclusionReason.METRIC_THRESHOLD_NOT_MET,
            detail=metric.value_numeric_str,
        )


@dataclass(frozen=True, slots=True)
class SectorFilter(UniverseFilter):
    """Keep companies whose sector matches, under a caller-supplied classification.

    Declares a ``scheme`` (which classification to read), a required ``sector``, and
    an equality :class:`ComparisonOperator` (``==`` / ``!=``). At build time the
    company's sector is looked up in the context's :class:`SectorClassification` for
    ``scheme``:

    * no classification supplied for the scheme → a **specification defect** (the
      caller declared a sector rule but supplied no data source for it);
    * company absent from the classification → excluded
      (:data:`ExclusionReason.SECTOR_UNCLASSIFIED`) — a data condition, never guessed;
    * classified but the comparison is false → excluded
      (:data:`ExclusionReason.SECTOR_MISMATCH`, detail = the actual sector).
    """

    scheme: str
    sector: str
    operator: ComparisonOperator = ComparisonOperator.EQ

    @property
    def kind(self) -> FilterKind:
        return FilterKind.SECTOR

    @property
    def is_source(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "scheme": self.scheme,
            "sector": self.sector,
            "operator": self.operator.value,
        }

    def apply(
        self,
        candidates: tuple[CompanyIdentity, ...] | None,
        context: FilterContext,
    ) -> FilterOutcome:
        if candidates is None:
            raise UniverseSpecificationError(
                "a SectorFilter cannot establish membership; a specification must "
                "begin with an explicit source (there is no implicit universe)"
            )
        if self.operator not in (ComparisonOperator.EQ, ComparisonOperator.NE):
            raise UniverseSpecificationError(
                f"SectorFilter supports only == / != (got {self.operator.value!r})"
            )
        classification = context.classification(self.scheme)
        if classification is None:
            raise UniverseSpecificationError(
                f"SectorFilter references scheme {self.scheme!r} but no "
                "SectorClassification for it was supplied; QuantForge derives no "
                "sector data, so it must be provided explicitly"
            )
        kept: list[CompanyIdentity] = []
        excluded: list[ExcludedCompany] = []
        for candidate in candidates:
            sector = classification.sector_of(candidate.company_id)
            if sector is None:
                excluded.append(
                    ExcludedCompany(
                        company_id=candidate.company_id,
                        filter_id=self.filter_id,
                        filter_kind=self.kind,
                        reason=ExclusionReason.SECTOR_UNCLASSIFIED,
                    )
                )
                continue
            matches = self.operator.compare_sector(sector, self.sector)
            if matches:
                kept.append(candidate)
            else:
                excluded.append(
                    ExcludedCompany(
                        company_id=candidate.company_id,
                        filter_id=self.filter_id,
                        filter_kind=self.kind,
                        reason=ExclusionReason.SECTOR_MISMATCH,
                        detail=sector,
                    )
                )
        return FilterOutcome(kept=tuple(kept), excluded=tuple(excluded))


def filter_from_dict(raw: dict[str, object]) -> UniverseFilter:
    """Reconstruct a :class:`UniverseFilter` from its serialized declaration.

    Dispatches on ``kind``; fails closed as a specification defect on an unknown or
    malformed declaration (a corrupt serialized filter must never silently become a
    no-op or a different filter).
    """
    from quantforge.metrics.model import MetricPeriod
    from quantforge.xbrl.contexts import PeriodType

    kind_raw = raw.get("kind")
    if not isinstance(kind_raw, str):
        raise UniverseSpecificationError("filter declaration missing a string 'kind'")
    try:
        kind = FilterKind(kind_raw)
    except ValueError as exc:
        raise UniverseSpecificationError(f"unknown filter kind {kind_raw!r}") from exc

    if kind is FilterKind.EXPLICIT:
        identifiers = raw.get("identifiers", [])
        if not isinstance(identifiers, list):
            raise UniverseSpecificationError(
                "explicit filter 'identifiers' must be a list"
            )
        by = raw.get("by")
        if by is not None and not isinstance(by, str):
            raise UniverseSpecificationError(
                "explicit filter 'by' must be a string or null"
            )
        return ExplicitCompanyFilter(
            identifiers=tuple(str(i) for i in identifiers), by=by
        )

    if kind is FilterKind.METRIC:
        period_raw = raw.get("period")
        if not isinstance(period_raw, dict):
            raise UniverseSpecificationError("metric filter 'period' must be an object")
        return CompanyMetricFilter(
            metric_key=_req_str(raw, "metric_key"),
            period=MetricPeriod(
                period_type=PeriodType(_req_str(period_raw, "period_type")),
                period_start=_opt_str(period_raw, "period_start"),
                period_end=_opt_str(period_raw, "period_end"),
            ),
            operator=ComparisonOperator(_req_str(raw, "operator")),
            threshold=_req_str(raw, "threshold"),
        )

    return SectorFilter(
        scheme=_req_str(raw, "scheme"),
        sector=_req_str(raw, "sector"),
        operator=ComparisonOperator(_req_str(raw, "operator")),
    )


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise UniverseSpecificationError(f"filter field {key!r} must be a string")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise UniverseSpecificationError(
            f"filter field {key!r} must be a string or null"
        )
    return value
