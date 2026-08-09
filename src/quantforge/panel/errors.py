"""Exception hierarchy for the point-in-time fundamental panel layer (Phase 10).

Rooted at :class:`PanelError` so a caller can catch every failure of this layer
with one type. Phase 10 *composes* the Phase 7 metric engine (and the Phase 8
cross-sectional fan-out) over a declared period axis at one shared boundary; it
computes no arithmetic of its own beyond the pure multi-period derivations
(``docs/phase10-panel-locked.md`` §8).

The governing posture matches Phases 7-8 (locked spec §8; data-model §12) — a
sharp split between two failure kinds:

* A **data condition** — a filer/period with no PIT-eligible fact at the boundary,
  or a derivation that cannot be computed because an input period is ``UNDEFINED``
  (a growth rate needs both endpoints; TTM needs four consecutive quarters) — is
  **never** an exception. It is a first-class ``UNDEFINED``
  :class:`~quantforge.panel.model.PanelCell` carrying the Phase 7
  :class:`~quantforge.metrics.model.UndefinedReason`. A panel over a long axis must
  record "undefined for period X, because Y" without aborting (zero information
  loss).
* A **configuration/consistency defect** — an empty or duplicate axis, a malformed
  generator, a period-kind mismatch for a derivation, a "revised vintage" (§3.1), a
  mixed engine version across cells, or stored derived state that violates an
  invariant on read — *is* raised. These are our bugs, surfaced rather than
  silently resolved. A raised error is always preferable to a wrong panel.
"""

from __future__ import annotations

__all__ = [
    "PanelConfigurationError",
    "PanelConsistencyError",
    "PanelError",
]


class PanelError(Exception):
    """Base class for all point-in-time fundamental-panel errors."""


class PanelConfigurationError(PanelError):
    """A panel request is internally inconsistent — our bug, surfaced (§8).

    Raised for an empty or duplicate period axis (a panel over no periods is a
    configuration bug, not an empty result), a malformed axis generator, a
    period-kind mismatch for a derivation, a "revised vintage" (REVISED has no
    ``as_of`` axis, §3.1), or a boundary/type misuse. We refuse to guess a panel's
    intent, exactly as Phase 8 refuses to guess a misconfigured universe and Phase 7
    a misconfigured formula.
    """


class PanelConsistencyError(PanelError):
    """A computed panel violates an invariant on read — fail-closed (§8, §12).

    Surfaced rather than trusted so a corrupted or contradictory panel can never
    silently masquerade as valid. In particular, cross-cell cells that do not share
    one ``metric_engine_version_id`` are a determinism violation and are raised,
    never silently reconciled (mirrors :class:`FactorConsistencyError`).
    """
