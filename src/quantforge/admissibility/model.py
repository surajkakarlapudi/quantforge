"""The strategy-admissibility vocabulary: verdict, criteria, reasons, criterion cell.

A **strategy admissibility** reads, from three sealed ex-post verdicts of one strategy,
the answers each layer already computed - whether the book was STABLE
(:class:`~quantforge.stability.result.WalkForwardStability`), the two-sided calibration
p-value (:class:`~quantforge.calsig.result.CalibrationSignificance`), and the one-sided
net-of-cost edge p-value + direction
(:class:`~quantforge.netcostsig.result.NetOfCostSignificance`) - and asks the question
no single layer answers: *taken together, is this strategy admissible?* This module
defines the fail-closed vocabulary that decision lives in:

* :class:`AdmissibilityVerdict` - the roll-up: ``ADMISSIBLE`` (every criterion passed),
  ``INADMISSIBLE`` (every criterion was decidable and at least one failed), or
  ``UNDEFINED`` (at least one criterion could not be decided - fail-closed, AD-2).
* :class:`CriterionKind` - which of the three admissibility criteria a cell describes:
  ``STABILITY``, ``CALIBRATION``, ``NET_OF_COST_EDGE``.
* :class:`CriterionStatus` - whether a single criterion ``PASS``ed, ``FAIL``ed, or is
  ``UNDEFINED`` (its source verdict was itself undefined).
* :class:`AdmissibilityUndefinedReason` - why a criterion is UNDEFINED: its source
  verdict was undefined (``STABILITY_UNDEFINED`` / ``CALIBRATION_UNDEFINED`` /
  ``NET_OF_COST_UNDEFINED``).
* :class:`Criterion` - one evaluated criterion: its kind, its pass/fail/undefined
  status, an optional descriptive ``detail`` (the observed p-value or the source status
  label, for audit), and, when UNDEFINED, the reason. Never a bare bool, never silently
  omitted.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "AdmissibilityUndefinedReason",
    "AdmissibilityVerdict",
    "Criterion",
    "CriterionKind",
    "CriterionStatus",
]


class AdmissibilityVerdict(StrEnum):
    """The joint admissibility roll-up over the three criteria (AD-2).

    ``ADMISSIBLE`` only when every criterion PASSed; ``INADMISSIBLE`` when every
    criterion was decidable (none UNDEFINED) and at least one FAILed; ``UNDEFINED``
    (fail closed) when at least one criterion could not be decided because its source
    verdict was itself undefined. A sealed admissibility always records its verdict
    honestly - the record seals either way, never raising for a data condition.
    """

    ADMISSIBLE = "admissible"
    INADMISSIBLE = "inadmissible"
    UNDEFINED = "undefined"


class CriterionKind(StrEnum):
    """Which of the three admissibility criteria a :class:`Criterion` cell describes."""

    #: The walk-forward book was STABLE (tradeable turnover / concentration), read from
    #: the source :class:`~quantforge.stability.result.WalkForwardStability`.
    STABILITY = "stability"

    #: The risk model was **not** significantly mis-calibrated (the two-sided
    #: calibration p-value exceeds ``alpha``), read from the source
    #: :class:`~quantforge.calsig.result.CalibrationSignificance`.
    CALIBRATION = "calibration"

    #: The after-cost edge was significantly profitable (the one-sided net-of-cost
    #: p-value is at most ``alpha`` and the edge is PROFITABLE), read from the source
    #: :class:`~quantforge.netcostsig.result.NetOfCostSignificance`.
    NET_OF_COST_EDGE = "net_of_cost_edge"


class CriterionStatus(StrEnum):
    """Whether a single admissibility criterion passed, failed, or is undefined."""

    PASS = "pass"
    FAIL = "fail"
    UNDEFINED = "undefined"


class AdmissibilityUndefinedReason(StrEnum):
    """Why a criterion (and, through it, the roll-up) is UNDEFINED (AD-2).

    A closed vocabulary, one reason per source verdict, so a reader can always tell
    which consumed verdict was itself undefined.
    """

    #: The source :class:`~quantforge.stability.result.WalkForwardStability` was not
    #: STABLE-decidable (its ``stability_status`` is UNDEFINED - too few transitions /
    #: realized windows to assess stability). Recorded, never coerced to a pass or fail.
    STABILITY_UNDEFINED = "stability_undefined"

    #: The source :class:`~quantforge.calsig.result.CalibrationSignificance` was not
    #: TESTED, or its ``p_value`` cell is not KNOWN. There is no calibration p-value to
    #: compare against ``alpha``. Recorded, never fabricated.
    CALIBRATION_UNDEFINED = "calibration_undefined"

    #: The source :class:`~quantforge.netcostsig.result.NetOfCostSignificance` was not
    #: TESTED, or its ``p_value`` cell is not KNOWN. There is no after-cost p-value to
    #: compare against ``alpha``. Recorded, never fabricated.
    NET_OF_COST_UNDEFINED = "net_of_cost_undefined"


@dataclass(frozen=True, slots=True)
class Criterion:
    """One evaluated admissibility criterion: kind + status (+ detail / reason).

    Exactly one shape per status, enforced at construction:

    * ``Criterion.passed(CriterionKind.STABILITY, detail="stable")`` - a PASS,
      optionally carrying the observed quantity that justified it (a p-value string, a
      status label);
    * ``Criterion.failed(CriterionKind.CALIBRATION, detail="0.001")`` - a FAIL,
      optionally carrying the observed quantity;
    * ``Criterion.undefined(kind, reason)`` - a criterion whose source verdict was
      itself undefined, recorded with why (e.g.
      ``AdmissibilityUndefinedReason.NET_OF_COST_UNDEFINED``).

    ``detail`` is a descriptive audit string only; ``reason`` is populated iff the
    status is UNDEFINED. Never a bare bool, never silently omitted.
    """

    kind: CriterionKind
    status: CriterionStatus
    detail: str | None = None
    reason: AdmissibilityUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is CriterionStatus.UNDEFINED:
            if self.reason is None:
                raise ValueError("an UNDEFINED Criterion must carry a reason")
        elif self.reason is not None:
            raise ValueError("a PASS / FAIL Criterion must not carry a reason")

    @classmethod
    def passed(cls, kind: CriterionKind, *, detail: str | None = None) -> Criterion:
        """A criterion that PASSed, optionally recording the observed justification."""
        return cls(kind=kind, status=CriterionStatus.PASS, detail=detail)

    @classmethod
    def failed(cls, kind: CriterionKind, *, detail: str | None = None) -> Criterion:
        """A criterion that FAILed, optionally recording the observed justification."""
        return cls(kind=kind, status=CriterionStatus.FAIL, detail=detail)

    @classmethod
    def undefined(
        cls,
        kind: CriterionKind,
        reason: AdmissibilityUndefinedReason,
    ) -> Criterion:
        """A criterion whose source verdict was itself undefined (AD-2)."""
        return cls(kind=kind, status=CriterionStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{kind, status, detail?, reason?}`` cell (deterministic).

        A ``detail`` is emitted only when present; a ``reason`` only for an UNDEFINED
        criterion - so the serialized bytes are minimal and unambiguous.
        """
        payload: dict[str, object] = {
            "kind": self.kind.value,
            "status": self.status.value,
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        if self.reason is not None:
            payload["reason"] = self.reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Criterion:
        """Reconstruct a criterion from its :meth:`to_dict` payload; fail closed.

        A malformed cell (unknown kind / status / reason, or a wrong type) is a corrupt
        payload, refused with a :class:`ValueError` rather than guessed - the sidecar
        must never read back a cell whose meaning changed.
        """
        kind_raw = raw.get("kind")
        if not isinstance(kind_raw, str):
            raise ValueError("Criterion.kind must be a string")
        try:
            kind = CriterionKind(kind_raw)
        except ValueError as exc:
            raise ValueError(f"unknown CriterionKind {kind_raw!r}") from exc

        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("Criterion.status must be a string")
        try:
            status = CriterionStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown CriterionStatus {status_raw!r}") from exc

        detail_raw = raw.get("detail")
        detail: str | None
        if detail_raw is None:
            detail = None
        elif isinstance(detail_raw, str):
            detail = detail_raw
        else:
            raise ValueError("Criterion.detail must be a string or absent")

        reason_raw = raw.get("reason")
        reason: AdmissibilityUndefinedReason | None
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            try:
                reason = AdmissibilityUndefinedReason(reason_raw)
            except ValueError as exc:
                raise ValueError(
                    f"unknown AdmissibilityUndefinedReason {reason_raw!r}"
                ) from exc
        else:
            raise ValueError("Criterion.reason must be a string or absent")

        if status is CriterionStatus.UNDEFINED:
            if reason is None:
                raise ValueError("an UNDEFINED Criterion must carry a reason")
            return cls(kind=kind, status=status, detail=detail, reason=reason)
        if reason is not None:
            raise ValueError("a PASS / FAIL Criterion must not carry a reason")
        return cls(kind=kind, status=status, detail=detail)
