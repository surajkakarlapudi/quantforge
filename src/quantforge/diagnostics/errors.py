"""Exception hierarchy for the signal-diagnostics layer (Phase 16, §7).

Rooted at :class:`SignalDiagnosticsError` so a caller can catch every failure of this
layer with one type. Phase 16 is a *pure consumer* of Phases 9/10/11 (the *diagnostic
sibling* of the Phase 12 backtester): it resolves the universe PIT as-of each evaluation
date, reads the signal cross-section as a :class:`~quantforge.panel.model.PitPanel`, and
pairs it with a realized forward return from PIT-gated adjusted prices — computing new
cross-sectional predictive-power statistics. It consumes no ``BacktestResult`` and reads
the raw corpora only through the existing PIT accessors, so its only failures are of the
request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§7):

* A **data / research condition** — a statistic that is genuinely undefined for the data
  (a date with fewer than two eligible pairs, zero signal or return variance, an empty
  quantile bucket, no valid dates for a method) — is **never** an exception. It is
  recorded as a first-class UNDEFINED :class:`~quantforge.diagnostics.model.StatValue`
  carrying *why*, and surfaced — never fabricated, never a divide-by-zero, never
  silently dropped. A member lacking a PIT signal at ``T`` or a computable forward
  return is excluded from that date's pair set and counted in coverage (SD-4).
* A **configuration / consistency defect** — an empty name, an unknown IC method,
  ``quantiles < 2``, a malformed horizon, a non-``MetricPeriod`` period, a corpus pin
  that does not match the pinned corpus, a non-unique corpus normalizer — *is* raised.
  These are our bugs, surfaced rather than silently resolved. A raised error is always
  preferable to a wrong diagnostics record.
"""

from __future__ import annotations

__all__ = [
    "SignalDiagnosticsConfigurationError",
    "SignalDiagnosticsConsistencyError",
    "SignalDiagnosticsError",
]


class SignalDiagnosticsError(Exception):
    """Base class for all signal-diagnostics-layer errors."""


class SignalDiagnosticsConfigurationError(SignalDiagnosticsError):
    """A diagnostics request is internally inconsistent — our bug.

    Raised for a malformed
    :class:`~quantforge.diagnostics.spec.SignalDiagnosticsSpecification` (an empty
    ``name`` / ``signal`` / ``spec_version`` / corpus pin, a ``period`` that is not a
    :class:`~quantforge.metrics.model.MetricPeriod`, ``quantiles`` that is not an
    ``int`` or is ``< 2``, an empty / out-of-vocabulary / duplicated ``ic_methods``, a
    ``forward_horizon`` not of the form ``"<n>d"`` with ``n >= 1``, a ``universe`` or
    ``schedule`` missing its content-addressed identity), for a non-specification
    argument to ``evaluate``, or for a study in which **no** scheduled date has at least
    two eligible pairs (so every IC on every method would be UNDEFINED and the whole
    record meaningless — the Phase 15 ``_MIN_PERIODS`` precedent). We refuse to guess a
    diagnostics request's intent, exactly as Phase 12 refuses a misconfigured backtest.
    """


class SignalDiagnosticsConsistencyError(SignalDiagnosticsError):
    """A record cannot be honestly computed from the pinned corpora — surfaced.

    Fail-closed guard for the corpus-pin contract (SD-1, §7): the fundamentals
    ``dataset_version_id`` or the market ``market_dataset_version_id`` re-derived from
    the universe's source companies and their securities does not match the spec's
    declared pin, or the corpus does not admit a single normalizing dataset version (a
    non-unique normalizer). Because a diagnostic reads both corpora PIT-as-of over an
    append-only store, an unpinned or drifted corpus would silently change the answer;
    the mismatch is raised — never silently computed around. A corrupt / non-finite
    decimal read from the corpus is likewise raised, never guessed.
    """
