"""The declarative, content-addressed report request (locked §8.3, §18, D7).

A **report** is fully described by a declarative :class:`ReportSpecification` — never a
callback, a subclass, or arbitrary Python. This is the Phase 14 analogue of an
:class:`~quantforge.experiment.spec.ExperimentSpecification`: a frozen request whose
identity is a pure content hash of *what was declared* (which subject, at which scope,
ranked by which directives). The engine interprets it; it never executes code. That is
what keeps ``report_id`` an honest, reproducible identity.

The pieces, both frozen (``@dataclass(frozen=True, slots=True)``):

* :class:`ComparisonDirective` — one reporting intent to rank an experiment's children
  by a chosen ``statistic`` under an ``order``. Validated at construction against the
  **same closed vocabulary Phase 13 already defines**
  (:data:`~quantforge.experiment.analysis.RANKABLE_STATISTICS` and
  ``{descending, ascending}``) — the report never invents a statistic.
* :class:`ReportSpecification` — a name, a top-level ``scope`` (the closed v1 vocabulary
  ``{backtest, experiment}``, locked D7), the ``subject_id`` of the sealed artifact
  being
  reported, and an optional tuple of :class:`ComparisonDirective`s. A ``comparisons``
  directive is only valid when ``scope == "experiment"`` (a single-backtest report has
  nothing to rank); otherwise construction fails closed.

Nothing here reads a store or the wall clock; both types are pure, reproducible value
objects the engine consumes. Presentation (headings, prose, display order) lives in the
renderer, never here (locked §10).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantforge.experiment.analysis import RANKABLE_STATISTICS
from quantforge.report.errors import ReportConfigurationError

__all__ = [
    "REPORT_SCOPES",
    "REPORT_SPEC_VERSION",
    "ComparisonDirective",
    "ReportSpecification",
]

#: The specification-schema version, folded into ``report_id`` (locked §9). Bump it when
#: the serialized meaning of a report *request* changes — never when engine logic
#: changes
#: (that is ``report_engine_version_id``). Mirrors ``experiment/1``.
REPORT_SPEC_VERSION = "report/1"

# -- the closed v1 scope vocabulary (locked D7) ------------------------------
#
# What a v1 report can be *about*. A comparison is a directive *within* an experiment
# report, not a standalone scope. Anything outside this set fails closed until
# explicitly
# added (a new scope hashes distinctly — never an edit that changes an existing id).
_SCOPE_BACKTEST = "backtest"
_SCOPE_EXPERIMENT = "experiment"

#: The closed v1 scope vocabulary, sorted for stable display (locked D7).
REPORT_SCOPES: tuple[str, ...] = (_SCOPE_BACKTEST, _SCOPE_EXPERIMENT)

_SCOPES = frozenset(REPORT_SCOPES)

_ORDER_DESCENDING = "descending"
_ORDER_ASCENDING = "ascending"
_ORDERS = frozenset({_ORDER_DESCENDING, _ORDER_ASCENDING})


@dataclass(frozen=True, slots=True)
class ComparisonDirective:
    """One reporting intent: rank an experiment's children by a statistic (§8.3, D5).

    ``statistic`` must be a member of the closed v1
    :data:`~quantforge.experiment.analysis.RANKABLE_STATISTICS` set and ``order`` one of
    ``descending`` / ``ascending`` — validated **at construction**, reusing the exact
    vocabulary Phase 13's :class:`~quantforge.experiment.analysis.BacktestComparison`
    enforces, so the report can never request a ranking the comparison layer would
    refuse. This directive records only the *intent*; the engine recomputes the actual
    :class:`~quantforge.experiment.analysis.BacktestComparison` deterministically from
    the sidecar at build (locked D5), never persisting it.
    """

    statistic: str
    order: str = _ORDER_DESCENDING

    def __post_init__(self) -> None:
        if self.statistic not in RANKABLE_STATISTICS:
            raise ReportConfigurationError(
                f"comparison statistic {self.statistic!r} is not a rankable v1 "
                f"performance statistic; use one of {sorted(RANKABLE_STATISTICS)}"
            )
        if self.order not in _ORDERS:
            raise ReportConfigurationError(
                f"comparison order {self.order!r} must be one of {sorted(_ORDERS)}"
            )

    def to_dict(self) -> dict[str, object]:
        return {"statistic": self.statistic, "order": self.order}

    def descriptor(self) -> list[str]:
        """The ``[statistic, order]`` pair folded (sorted, as a set) into
        ``report_id``."""
        return [self.statistic, self.order]


@dataclass(frozen=True, slots=True)
class ReportSpecification:
    """A complete, declarative, content-addressed report request (§8.3, §18, D7).

    ``scope`` is the closed v1 vocabulary member the report is about
    (:data:`REPORT_SCOPES`, locked D7); ``subject_id`` is the ``backtest_id`` or
    ``experiment_result_id`` of the sealed artifact being reported. ``comparisons`` is
    an
    optional tuple of :class:`ComparisonDirective`s, valid **only** for an
    ``experiment``
    scope (a single backtest has no members to rank). Constructing this reads no store
    and
    no wall clock; it validates its own shape at construction, exactly as the
    backtest/experiment layers refuse a misconfigured request. A duplicate comparison
    directive (same ``statistic`` + ``order``) is a configuration bug, raised.
    """

    name: str
    scope: str
    subject_id: str
    comparisons: tuple[ComparisonDirective, ...] = field(default_factory=tuple)
    spec_version: str = REPORT_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ReportConfigurationError("a report must have a non-empty name")
        if self.scope not in _SCOPES:
            raise ReportConfigurationError(
                f"report scope {self.scope!r} is not in the closed v1 vocabulary "
                f"{sorted(_SCOPES)}; extending the set is an explicit future change, "
                "never an implicit fallback (locked D7)"
            )
        if not isinstance(self.subject_id, str) or not self.subject_id:
            raise ReportConfigurationError(
                "a report must name a non-empty subject_id (the backtest_id or "
                "experiment_result_id being reported)"
            )
        if self.comparisons and self.scope != _SCOPE_EXPERIMENT:
            raise ReportConfigurationError(
                f"comparison directives are only valid for an {_SCOPE_EXPERIMENT!r} "
                f"scope; a {self.scope!r} report has no members to rank"
            )
        seen: set[tuple[str, str]] = set()
        for directive in self.comparisons:
            if not isinstance(directive, ComparisonDirective):
                raise ReportConfigurationError(
                    "each report comparison must be a ComparisonDirective"
                )
            key = (directive.statistic, directive.order)
            if key in seen:
                raise ReportConfigurationError(
                    f"duplicate comparison directive {key!r}; each (statistic, order) "
                    "must be distinct"
                )
            seen.add(key)

    def sorted_comparison_descriptors(self) -> list[list[str]]:
        """The comparison directives sorted — a set identity, order-independent (§9)."""
        return sorted(
            (directive.descriptor() for directive in self.comparisons),
            key=lambda pair: (pair[0], pair[1]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "scope": self.scope,
            "subject_id": self.subject_id,
            "comparisons": [directive.to_dict() for directive in self.comparisons],
        }
