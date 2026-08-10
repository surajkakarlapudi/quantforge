"""The declarative, content-addressed cross-sectional-regression request (§3.1).

A **cross-sectional-regression request** names an **ordered** tuple of ``K`` factor
signals (each a :class:`FactorSpec` - a ``metric_key`` and the explicit
:class:`~quantforge.metrics.model.MetricPeriod` it is read for), a Phase 9 universe
specification, a Phase 12 evaluation schedule of ``as_of`` instants, a forward-return
horizon, whether to include an intercept, and the two corpus pins (fundamentals +
market). Like every request in this project it is a frozen value whose identity is a
pure content hash of *what was declared* - the engine resolves and interprets it; it
never executes caller code (mirrors
:class:`~quantforge.attribution.spec.AttributionSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.crosssection.errors.CrossSectionConfigurationError`): an empty
``name`` / ``spec_version`` / corpus pin; an empty factor tuple or more than
:data:`K_MAX` factors; a factor that is not a :class:`FactorSpec`, whose ``metric_key``
is empty, or whose ``period`` is not a :class:`~quantforge.metrics.model.MetricPeriod`;
a duplicate factor (same ``metric_key`` **and** period - a repeated column is a
collinear design by construction); a ``forward_horizon`` not of the form ``"<n>d"``
with ``n >= 1``; a ``universe`` / ``schedule`` missing its content-addressed identity.
It reads no store and no wall clock - it cannot know whether the referenced corpora
exist (that is the engine's fail-closed pin-verification step); it validates only the
request's internal shape.

The **factor order is semantic** and is preserved exactly (never sorted): it fixes the
design-matrix column order and therefore the coefficient labels, so ``[(a, p), (b, p)]``
and ``[(b, p), (a, p)]`` are distinct requests with distinct ids. The corpus *content*
is folded by :func:`~quantforge.crosssection.identity.crosssection_id` at the engine,
from the declared pins - so the spec is a stable declaration independent of whether the
corpora have been read yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from quantforge.crosssection.errors import CrossSectionConfigurationError
from quantforge.metrics.model import MetricPeriod
from quantforge.universe.specification import UniverseSpecification

if TYPE_CHECKING:
    from quantforge.backtest.schedule import RebalanceSchedule

__all__ = [
    "CROSSSECTION_SPEC_VERSION",
    "K_MAX",
    "CrossSectionalRegressionSpecification",
    "FactorSpec",
]

#: The specification-schema version, folded into ``crosssection_id`` (§5). Bump it when
#: the serialized meaning of a request changes - never when engine logic changes (that
#: is :data:`~quantforge.crosssection.version.CROSSSECTION_ENGINE_VERSION`). Mirrors
#: ``attribution/1`` / ``diagnostics/1``.
CROSSSECTION_SPEC_VERSION = "crosssection/1"

#: The maximum number of factors a v1 request may declare (approved AG-9, the Phase 17
#: bound). The per-date linear solve is a
#: ``(K + include_intercept)x(K + include_intercept)`` exact-``Decimal`` factorization;
#: capping ``K`` keeps the cost bounded and the model interpretable. Exceeding it is a
#: configuration defect, raised - never silently truncated.
K_MAX = 8

#: The single supported forward-horizon representation (§1.2): a trading-day count. A
#: calendar / schedule-step form is out of scope for v1 and hashes distinctly if ever
#: added, so it can never silently reinterpret a stored id. Mirrors Phase 16 verbatim.
_HORIZON_RE = re.compile(r"^([0-9]+)d$")


@dataclass(frozen=True, slots=True)
class FactorSpec:
    """One declared factor signal: a ``metric_key`` read for an explicit period (§3.1).

    ``metric_key`` is a Phase 7 metric key; ``period`` the explicit
    :class:`~quantforge.metrics.model.MetricPeriod` it is read for (never inferred).
    ``label`` is a **display-only** convenience: identity uses the factor's ordinal
    position (``factor_1..factor_K``, like Phase 17), so two specs that differ only in a
    factor's ``label`` produce the same id. Validated by the owning
    :class:`CrossSectionalRegressionSpecification` (a factor is not independently
    validated on construction, mirroring how Phase 17 validates factor ids in the spec).
    """

    metric_key: str
    period: MetricPeriod
    label: str | None = None

    @property
    def descriptor(self) -> list[str]:
        """The identity descriptor ``[metric_key, period_key]`` (label excluded).

        Folded, in request order, into ``crosssection_id`` - so the id is sensitive to
        the signal and its period but never to the display label.
        """
        return [self.metric_key, self.period.period_key]

    def to_dict(self) -> dict[str, object]:
        """The canonical factor payload (deterministic; embedded in the sealed
        record)."""
        return {
            "metric_key": self.metric_key,
            "period": self.period.to_dict(),
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class CrossSectionalRegressionSpecification:
    """A declarative, content-addressed cross-sectional-regression request (§3.1).

    ``factors`` is an **ordered**, non-empty tuple of :class:`FactorSpec` (at most
    :data:`K_MAX`, no duplicate ``(metric_key, period)``); ``universe`` a Phase 9
    :class:`~quantforge.universe.specification.UniverseSpecification`; ``schedule`` a
    Phase 12 :class:`~quantforge.backtest.schedule.RebalanceSchedule` of evaluation
    ``as_of`` instants; ``forward_horizon`` a ``"<n>d"`` trading-day count;
    ``include_intercept`` whether the per-date design carries a constant term (default
    on, folded into identity); ``dataset_version_id`` / ``market_dataset_version_id``
    the two corpus pins re-verified at estimate (XS-1). Constructing this reads no store
    and no wall clock; it validates its own shape, exactly as the backtest / attribution
    layers refuse a misconfigured request.
    """

    name: str
    factors: tuple[FactorSpec, ...]
    universe: UniverseSpecification
    # A RebalanceSchedule; annotated via TYPE_CHECKING so mypy sees the real surface
    # while the module avoids a load-time import (validated by duck-typing below).
    schedule: RebalanceSchedule
    forward_horizon: str
    dataset_version_id: str
    market_dataset_version_id: str
    include_intercept: bool = True
    spec_version: str = CROSSSECTION_SPEC_VERSION
    #: The parsed trading-day count - derived at construction, never supplied.
    horizon_days: int = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise CrossSectionConfigurationError(
                "a cross-sectional-regression request must have a non-empty name"
            )
        if not isinstance(self.factors, tuple) or not self.factors:
            raise CrossSectionConfigurationError(
                "a request must enumerate at least one factor"
            )
        if len(self.factors) > K_MAX:
            raise CrossSectionConfigurationError(
                f"a request declares {len(self.factors)} factors; at most "
                f"K_MAX={K_MAX} are allowed (fail closed rather than truncate)"
            )
        seen: set[tuple[str, str]] = set()
        for factor in self.factors:
            if not isinstance(factor, FactorSpec):
                raise CrossSectionConfigurationError("each factor must be a FactorSpec")
            if not isinstance(factor.metric_key, str) or not factor.metric_key:
                raise CrossSectionConfigurationError(
                    "each factor must name a non-empty metric_key"
                )
            if not isinstance(factor.period, MetricPeriod):
                raise CrossSectionConfigurationError(
                    "each factor.period must be a MetricPeriod (an explicit fiscal "
                    "period, never inferred)"
                )
            key = (factor.metric_key, factor.period.period_key)
            if key in seen:
                raise CrossSectionConfigurationError(
                    f"duplicate factor {factor.metric_key!r} for the same period; each "
                    "(metric_key, period) must be distinct (a repeated column is a "
                    "collinear design by construction)"
                )
            seen.add(key)
        if not isinstance(self.universe, UniverseSpecification):
            raise CrossSectionConfigurationError(
                "universe must be a UniverseSpecification"
            )
        # The schedule is duck-typed to avoid importing backtest at module load; it must
        # expose the RebalanceSchedule surface the engine relies on.
        if not hasattr(self.schedule, "schedule_id") or not hasattr(
            self.schedule, "as_of_instants"
        ):
            raise CrossSectionConfigurationError(
                "schedule must be a RebalanceSchedule (with schedule_id + "
                "as_of_instants)"
            )
        if len(self.schedule.as_of_instants()) == 0:
            raise CrossSectionConfigurationError(
                "schedule must enumerate at least one evaluation as_of instant"
            )
        if not isinstance(self.forward_horizon, str):
            raise CrossSectionConfigurationError(
                "forward_horizon must be a string of the form '<n>d'"
            )
        match = _HORIZON_RE.match(self.forward_horizon)
        if match is None:
            raise CrossSectionConfigurationError(
                f"forward_horizon {self.forward_horizon!r} must be of the form '<n>d' "
                "(a trading-day count)"
            )
        horizon_days = int(match.group(1))
        if horizon_days < 1:
            raise CrossSectionConfigurationError(
                "forward_horizon must be at least 1 trading day"
            )
        object.__setattr__(self, "horizon_days", horizon_days)
        # ``bool`` is its own type here (not coerced) - reject a non-bool explicitly so
        # a truthy int can never masquerade as the intercept flag.
        if not isinstance(self.include_intercept, bool):
            raise CrossSectionConfigurationError("include_intercept must be a bool")
        if not isinstance(self.dataset_version_id, str) or not self.dataset_version_id:
            raise CrossSectionConfigurationError(
                "dataset_version_id must be a non-empty fundamentals corpus pin"
            )
        if (
            not isinstance(self.market_dataset_version_id, str)
            or not self.market_dataset_version_id
        ):
            raise CrossSectionConfigurationError(
                "market_dataset_version_id must be a non-empty market corpus pin"
            )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise CrossSectionConfigurationError(
                "spec_version must be a non-empty string"
            )

    @property
    def factor_descriptors(self) -> list[list[str]]:
        """The ordered ``[[metric_key, period_key], ...]`` identity descriptors (§5).

        In declared order (order is semantic - it fixes the regression's column order
        and coefficient labels), so it is preserved, never sorted. Folded into
        ``crosssection_id``; the display labels are excluded.
        """
        return [factor.descriptor for factor in self.factors]

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        ``factors`` is emitted in its declared order (order is semantic). The
        ``universe`` / ``schedule`` are emitted in their own canonical serialized forms.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "factors": [f.to_dict() for f in self.factors],
            "universe": self.universe.to_dict(),
            "schedule": self.schedule.to_dict(),
            "forward_horizon": self.forward_horizon,
            "horizon_days": self.horizon_days,
            "include_intercept": self.include_intercept,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
        }
