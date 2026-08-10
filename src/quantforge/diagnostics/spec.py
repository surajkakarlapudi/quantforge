"""The declarative, content-addressed signal-diagnostics request (§3.1).

A **signal-diagnostics request** names one signal metric, the explicit fiscal period it
is read for, a Phase 9 universe specification, a Phase 12 evaluation schedule of
``as_of`` instants, a forward-return horizon, a quantile count, the IC methods to
compute, and the two corpus pins (fundamentals + market). Like every request in this
project it is a frozen value whose identity is a pure content hash of *what was
declared* — the engine resolves and interprets it; it never executes caller code
(mirrors :class:`~quantforge.analytics.spec.AnalyticsSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.diagnostics.errors.SignalDiagnosticsConfigurationError`): an empty
``name`` / ``signal`` / ``spec_version`` / corpus pin; a ``period`` that is not a
:class:`~quantforge.metrics.model.MetricPeriod`; ``quantiles`` that is not an ``int`` or
is ``< 2``; an empty / out-of-vocabulary / duplicated ``ic_methods``; a
``forward_horizon`` not of the form ``"<n>d"`` with ``n >= 1``; a ``universe`` /
``schedule`` missing its content-addressed identity. It reads no store and no wall clock
— it cannot know whether the referenced corpora exist (that is the engine's fail-closed
pin-verification step); it validates only the request's internal shape.

``ic_methods`` is canonicalized and treated as a **set** for identity: order and
duplicate spelling never change the id (``("spearman", "pearson")`` and ``("pearson",
"spearman")`` fold identically). The corpus *content* is folded by
:func:`~quantforge.diagnostics.identity.diagnostics_id` at the engine, from the declared
pins — so the spec is a stable declaration independent of whether the corpora have been
read yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from quantforge.diagnostics.errors import SignalDiagnosticsConfigurationError
from quantforge.diagnostics.model import ICMethod
from quantforge.metrics.model import MetricPeriod
from quantforge.universe.specification import UniverseSpecification

if TYPE_CHECKING:
    from quantforge.backtest.schedule import RebalanceSchedule

__all__ = [
    "DIAGNOSTICS_SPEC_VERSION",
    "SignalDiagnosticsSpecification",
]

#: The specification-schema version, folded into ``diagnostics_id`` (§5). Bump it when
#: the serialized meaning of a request changes — never when engine logic changes (that
#: is :data:`~quantforge.diagnostics.version.DIAGNOSTICS_ENGINE_VERSION`). Mirrors
#: ``analytics/1`` and ``experiment/1``.
DIAGNOSTICS_SPEC_VERSION = "diagnostics/1"

#: The single supported forward-horizon representation (§1.2): a trading-day count. A
#: calendar / schedule-step form is out of scope for v1 and hashes distinctly if ever
#: added, so it can never silently reinterpret a stored id.
_HORIZON_RE = re.compile(r"^([0-9]+)d$")

#: The closed IC-method vocabulary (D6). A method not in this set is a configuration
#: defect; extending it is an explicit future edit that hashes distinctly.
_IC_METHODS: frozenset[str] = frozenset(m.value for m in ICMethod)


@dataclass(frozen=True, slots=True)
class SignalDiagnosticsSpecification:
    """A declarative, content-addressed signal-diagnostics request (§3.1).

    ``signal`` is a Phase 7 ``metric_key``; ``period`` the explicit
    :class:`~quantforge.metrics.model.MetricPeriod` it is read for (never inferred);
    ``universe`` a Phase 9
    :class:`~quantforge.universe.specification.UniverseSpecification`; ``schedule`` a
    Phase 12 :class:`~quantforge.backtest.schedule.RebalanceSchedule` of evaluation
    ``as_of`` instants; ``forward_horizon`` a ``"<n>d"`` trading-day count;
    ``quantiles`` the bucket count (``q >= 2``); ``ic_methods`` the closed set of IC
    methods (treated as a set for identity); ``dataset_version_id`` /
    ``market_dataset_version_id`` the two corpus pins re-verified at evaluate (SD-1).
    Constructing this reads no store and no wall clock; it validates its own shape,
    exactly as the backtest / analytics layers refuse a misconfigured request.
    """

    name: str
    signal: str
    period: MetricPeriod
    universe: UniverseSpecification
    # A RebalanceSchedule; annotated via TYPE_CHECKING so mypy sees the real surface
    # while the module avoids a load-time import (validated by duck-typing below).
    schedule: RebalanceSchedule
    forward_horizon: str
    quantiles: int
    dataset_version_id: str
    market_dataset_version_id: str
    ic_methods: tuple[str, ...] = ("pearson", "spearman")
    spec_version: str = DIAGNOSTICS_SPEC_VERSION
    #: The parsed trading-day count — derived at construction, never supplied.
    horizon_days: int = field(init=False)
    #: The canonicalized, sorted, de-duplicated IC methods — derived at construction.
    #: Set-valued so order/spelling never changes identity.
    sorted_ic_methods: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise SignalDiagnosticsConfigurationError(
                "a diagnostics request must have a non-empty name"
            )
        if not isinstance(self.signal, str) or not self.signal:
            raise SignalDiagnosticsConfigurationError(
                "a diagnostics request must name a non-empty signal metric_key"
            )
        if not isinstance(self.period, MetricPeriod):
            raise SignalDiagnosticsConfigurationError(
                "period must be a MetricPeriod (an explicit fiscal period, never "
                "inferred)"
            )
        if not isinstance(self.universe, UniverseSpecification):
            raise SignalDiagnosticsConfigurationError(
                "universe must be a UniverseSpecification"
            )
        # The schedule is duck-typed to avoid importing backtest at module load; it must
        # expose the RebalanceSchedule surface the engine relies on.
        if not hasattr(self.schedule, "schedule_id") or not hasattr(
            self.schedule, "as_of_instants"
        ):
            raise SignalDiagnosticsConfigurationError(
                "schedule must be a RebalanceSchedule (with schedule_id + "
                "as_of_instants)"
            )
        if len(self.schedule.as_of_instants()) == 0:
            raise SignalDiagnosticsConfigurationError(
                "schedule must enumerate at least one evaluation as_of instant"
            )
        # ``bool`` is an ``int`` subclass; reject it explicitly — a boolean quantile
        # count is a configuration defect, not "1 or 0 buckets".
        if not isinstance(self.quantiles, int) or isinstance(self.quantiles, bool):
            raise SignalDiagnosticsConfigurationError("quantiles must be an int")
        if self.quantiles < 2:
            raise SignalDiagnosticsConfigurationError(
                "quantiles must be at least 2 (a portfolio sort needs two buckets)"
            )
        if not isinstance(self.forward_horizon, str):
            raise SignalDiagnosticsConfigurationError(
                "forward_horizon must be a string of the form '<n>d'"
            )
        match = _HORIZON_RE.match(self.forward_horizon)
        if match is None:
            raise SignalDiagnosticsConfigurationError(
                f"forward_horizon {self.forward_horizon!r} must be of the form '<n>d' "
                "(a trading-day count)"
            )
        horizon_days = int(match.group(1))
        if horizon_days < 1:
            raise SignalDiagnosticsConfigurationError(
                "forward_horizon must be at least 1 trading day"
            )
        object.__setattr__(self, "horizon_days", horizon_days)
        if not self.ic_methods:
            raise SignalDiagnosticsConfigurationError(
                "a diagnostics request must enumerate at least one ic_method"
            )
        seen: set[str] = set()
        for method in self.ic_methods:
            if not isinstance(method, str) or method not in _IC_METHODS:
                raise SignalDiagnosticsConfigurationError(
                    f"ic_method {method!r} is not one of "
                    f"{sorted(_IC_METHODS)} (the closed v1 vocabulary)"
                )
            if method in seen:
                raise SignalDiagnosticsConfigurationError(
                    f"duplicate ic_method {method!r}; each method must be distinct"
                )
            seen.add(method)
        object.__setattr__(self, "sorted_ic_methods", tuple(sorted(seen)))
        if not isinstance(self.dataset_version_id, str) or not self.dataset_version_id:
            raise SignalDiagnosticsConfigurationError(
                "dataset_version_id must be a non-empty fundamentals corpus pin"
            )
        if (
            not isinstance(self.market_dataset_version_id, str)
            or not self.market_dataset_version_id
        ):
            raise SignalDiagnosticsConfigurationError(
                "market_dataset_version_id must be a non-empty market corpus pin"
            )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise SignalDiagnosticsConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        ``ic_methods`` is emitted in its sorted, de-duplicated form so the serialized
        request — like the identity — is independent of the order and spelling the
        caller supplied. The ``period`` / ``universe`` / ``schedule`` are emitted in
        their own canonical serialized forms.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "signal": self.signal,
            "period": self.period.to_dict(),
            "universe": self.universe.to_dict(),
            "schedule": self.schedule.to_dict(),
            "forward_horizon": self.forward_horizon,
            "horizon_days": self.horizon_days,
            "quantiles": self.quantiles,
            "ic_methods": list(self.sorted_ic_methods),
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
        }
