"""Exception hierarchy for the research-reporting layer (Phase 14, locked §17).

Rooted at :class:`ReportError` so a caller can catch every failure of this layer with
one type. Phase 14 is a *pure consumer* of Phases 8-13: it references already-sealed
:class:`~quantforge.factors.store.ResearchRecord`s
(:class:`~quantforge.backtest.result.BacktestResult`,
:class:`~quantforge.experiment.result.ExperimentResult`) and the derived
:class:`~quantforge.experiment.analysis.BacktestComparison`, and produces a
content-addressed :class:`~quantforge.report.result.ResearchReport` manifest. It
resolves no data at any ``T`` and re-derives no financial number, so its only failures
are of the request or of a consistency invariant.

The governing posture mirrors the Phase 12/13 split (locked §17) verbatim:

* A **data / research condition** — an undefined metric cell, an unfilled order, an
  unrecognized corporate action, a comparison member excluded for a non-finite
  statistic, a corpus ``pin_mismatch`` — is **never** an exception. It lives in the
  referenced sealed record as a first-class recorded value and is *surfaced* by the
  renderer, never fabricated and never hidden.
* A **configuration / consistency defect** — an empty report name, an unknown scope, a
  comparison directive on a non-experiment scope, a statistic/order outside the closed
  vocabulary, a referenced id absent from the sidecar, a referenced record whose
  recomputed content hash no longer matches, a referenced boundary that disagrees with
  the declared one — *is* raised. These are our bugs, surfaced rather than silently
  resolved. A raised error is always preferable to a stale or wrong report.
"""

from __future__ import annotations

__all__ = [
    "ReportConfigurationError",
    "ReportConsistencyError",
    "ReportError",
]


class ReportError(Exception):
    """Base class for all research-reporting-layer errors."""


class ReportConfigurationError(ReportError):
    """A report request is internally inconsistent — our bug (locked §17).

    Raised for a malformed
    :class:`~quantforge.report.spec.ReportSpecification`: an empty ``name``, a ``scope``
    outside the closed v1 vocabulary (``backtest`` / ``experiment``), a ``comparisons``
    directive on a scope that has nothing to rank (anything other than ``experiment``),
    or a :class:`~quantforge.report.spec.ComparisonDirective` whose ``statistic`` is not
    a rankable v1 performance statistic or whose ``order`` is neither ``descending`` nor
    ``ascending``. We refuse to guess a report's intent, exactly as Phase 12/13 refuse a
    misconfigured backtest or experiment.
    """


class ReportConsistencyError(ReportError):
    """A report references an artifact it cannot honestly report on — surfaced (§17).

    Fail-closed guard for the reference contract (locked §13): a ``subject_id`` or
    referenced id absent from the research sidecar (we refuse to report on an artifact
    we cannot materialize), a referenced record whose recomputed ``content_hash`` no
    longer matches the one the request implies (a report can never silently reference a
    drifted artifact), a recomputed
    :class:`~quantforge.experiment.analysis.BacktestComparison`
    whose ``comparison_id`` disagrees with the reference's ``content_hash``, or a
    referenced artifact whose implied boundary disagrees with the report's declared
    ``boundary_kind`` — each is a consistency violation and is raised, never silently
    reported.
    """
