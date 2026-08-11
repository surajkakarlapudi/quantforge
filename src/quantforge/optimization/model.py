"""The portfolio-optimization result vocabulary: status, reasons, cells, labels.

A **portfolio-optimization record** is the global minimum-variance (GMV) factor-weight
vector over the ``N x N`` covariance matrix of a sealed
:class:`~quantforge.factorrisk.result.FactorRiskModel`: one weight per factor (in the
risk model's factor order), plus the achieved per-period portfolio variance and its
volatility. This module defines the fail-closed result vocabulary those numbers live in,
plus the nested cell that carries a weight:

* :class:`OptimizationStatus` / :class:`OptimizationUndefinedReason` - the fail-closed
  vocabulary. ``UNDEFINED`` is a first-class value carrying *why* the GMV could not be
  computed for the data (a non-positive-definite covariance matrix,
  ``SINGULAR_COVARIANCE``), never an exception, never ``0`` / ``NaN`` / ``Inf`` / a
  divide-by-zero (§15, PO-4).
  Mirrors the factor-risk / attribution reason enums.
* :class:`StatValue` - the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. Never a bare float, never silently omitted.
* :class:`WeightCell` - one factor's optimal weight, keyed to its position label.
* :func:`factor_label` - the deterministic, name-free factor label keyed to a factor's
  position in the referenced risk model (which fixes the weight-vector order).

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "OptimizationStatus",
    "OptimizationUndefinedReason",
    "StatValue",
    "WeightCell",
    "factor_label",
]


class OptimizationStatus(StrEnum):
    """Whether the optimization resolved to a portfolio (``OPTIMAL``) or not."""

    OPTIMAL = "optimal"
    UNDEFINED = "undefined"


class OptimizationUndefinedReason(StrEnum):
    """Why an optimization is ``UNDEFINED`` - fail-closed, never fabricated (§15, PO-4).

    Every reason preserves information: it records the *absence* of a computable
    solution (a covariance matrix whose inverse does not exist) rather than inventing
    one, never a divide-by-zero, never a repaired / regularized / pseudo-inverted
    matrix.
    """

    #: The ``N x N`` covariance matrix ``Σ`` is not positive-definite (rank-deficient /
    #: collinear factors / a zero-variance factor / too few common periods), detected by
    #: the exact zero-pivot test of the shared LDLᵀ factorization. ``Σ⁻¹1`` does not
    #: exist, so the fully-invested GMV ``w = Σ⁻¹1 / (1ᵀΣ⁻¹1)`` is genuinely undefined.
    #: Recorded, never solved around - the direct analogue of ``SINGULAR_DESIGN`` in the
    #: exact-``Decimal`` OLS solver.
    SINGULAR_COVARIANCE = "singular_covariance"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (PO-4).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.5")`` - a computed decimal string (canonicalized by the solve
      layer via ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(OptimizationUndefinedReason.SINGULAR_COVARIANCE)`` - a value
      genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    optimization analogue of the factor-risk / attribution ``StatValue``.
    """

    status: OptimizationStatus
    value: str | None = None
    reason: OptimizationUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is OptimizationStatus.OPTIMAL:
            if not isinstance(self.value, str) or self.reason is not None:
                raise ValueError(
                    "a KNOWN StatValue must carry a decimal-string value and no reason"
                )
        else:  # UNDEFINED
            if self.reason is None or self.value is not None:
                raise ValueError(
                    "an UNDEFINED StatValue must carry a reason and no value"
                )

    @classmethod
    def known(cls, value: str) -> StatValue:
        """A KNOWN cell holding a canonical decimal string."""
        return cls(status=OptimizationStatus.OPTIMAL, value=value)

    @classmethod
    def undefined(cls, reason: OptimizationUndefinedReason) -> StatValue:
        """An UNDEFINED cell recording why the value could not be computed."""
        return cls(status=OptimizationStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only - so
        the two are impossible to confuse and the serialized bytes are minimal. A KNOWN
        cell's ``status`` is emitted as ``"optimal"`` and an UNDEFINED cell's as
        ``"undefined"`` (the :class:`OptimizationStatus` values), so a cell round-trips
        through :meth:`from_dict` unambiguously.
        """
        if self.status is OptimizationStatus.OPTIMAL:
            return {"status": self.status.value, "value": self.value}
        assert self.reason is not None  # guaranteed by __post_init__
        return {"status": self.status.value, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StatValue:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed - the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("StatValue.status must be a string")
        try:
            status = OptimizationStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StatValue status {status_raw!r}") from exc
        if status is OptimizationStatus.OPTIMAL:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StatValue must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StatValue must carry a reason string")
        try:
            reason = OptimizationUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown OptimizationUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)


def factor_label(index: int) -> str:
    """The deterministic label of the ``index``-th factor (0-based).

    ``factor_1``, ``factor_2``, ... in the referenced risk model's factor order - a
    stable, name-free label keyed to the factor's position (which fixes the
    weight-vector order). The record also carries the risk model reference, so the
    numeric label never loses provenance. Identical to
    :func:`quantforge.factorrisk.model.factor_label` by construction, so the labels of a
    risk model and its optimization line up one-to-one.
    """
    if index < 0:
        raise ValueError("factor index must be non-negative")
    return f"factor_{index + 1}"


@dataclass(frozen=True, slots=True)
class WeightCell:
    """One factor's optimal weight ``(label, value)`` (§14).

    ``label`` is the name-free :func:`factor_label` for the factor's position in the
    referenced risk model; ``value`` is the GMV weight as a :class:`StatValue` - a KNOWN
    decimal string when the optimization is ``OPTIMAL``, or an UNDEFINED
    ``SINGULAR_COVARIANCE`` cell when the covariance matrix is not positive-definite
    (every weight is UNDEFINED together, never a partial vector). A GMV weight may be
    negative (an honest long/short combination across factors); no non-negativity
    constraint applies in the fully-invested v1.
    """

    label: str
    value: StatValue

    def to_dict(self) -> dict[str, object]:
        return {"label": self.label, "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> WeightCell:
        label = raw.get("label")
        if not isinstance(label, str):
            raise ValueError("WeightCell.label must be a string")
        value = raw.get("value")
        if not isinstance(value, dict):
            raise ValueError("WeightCell.value must be an object")
        return cls(label=label, value=StatValue.from_dict(value))
