"""The declarative, content-addressed net-of-cost request (§14).

A **net-of-cost request** names exactly one sealed
:class:`~quantforge.stability.result.WalkForwardStability` to charge for trading, and
declares the linear transaction-cost rate ``cost_rate`` to apply. Like every request in
this project it is a frozen value whose identity is a pure content hash of *what was
declared* - the engine resolves and interprets it; it never executes caller code
(mirrors :class:`~quantforge.calsig.spec.CalibrationSignificanceSpecification` and
:class:`~quantforge.multiplicity.spec.MultipleComparisonSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.netcost.errors.NetOfCostConfigurationError`): an empty ``name`` /
``spec_version`` / ``source_stability_id``, or a ``cost_rate`` that is not a
**non-negative finite** decimal string. It reads no store and no wall clock - it cannot
know whether the referenced stability record exists (that is the engine's fail-closed
resolution step) or how many windows it holds; it validates only the request's internal
shape.

``cost_rate`` is the load-bearing modeling assumption of this layer (NC-3): a
**declared** linear one-way transaction-cost rate, in the same units as the sealed
one-way turnover (cost per unit of one-way turnover). It is **never** inferred from
data, retrieved from a corpus, or defaulted - a net-of-cost verdict is only as
meaningful as the cost model the researcher chose, so the choice is always explicit and
always folded into the id. It is **canonicalized** at construction to a stable decimal
string (via :func:`decimal.Decimal.normalize`), so ``"0.001"`` and ``"0.0010"`` declare
the identical request with the identical id. A rate of exactly ``0`` is permitted (it
declares a gross-equals-net counterfactual - the zero-cost identity); a negative rate is
refused (a transaction *rebate* is not this layer's model). The parameter-free
break-even cost rate
this layer also reports needs no request parameter - it is a diagnostic of the gross
edge against the turnover, independent of ``cost_rate``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.netcost.errors import NetOfCostConfigurationError
from quantforge.netcost.version import NETCOST_SPEC_VERSION

__all__ = ["NetOfCostSpecification"]

_ZERO = Decimal(0)


def _canonical_cost_rate(cost_rate: str) -> str:
    """Canonicalize a ``cost_rate`` string to a stable non-negative decimal form.

    Parses ``cost_rate`` as a ``Decimal``, requires it finite and ``>= 0``, and returns
    ``str(value.normalize())`` so trailing-zero variants (``"0.001"`` / ``"0.0010"``)
    collapse to one canonical string (and thus one id). Fails closed on a non-decimal,
    non-finite, or negative value. ``normalize()`` maps ``"0"`` / ``"0.0"`` to the
    canonical ``"0"`` (and ``"1E+1"`` etc. to a stable form); it never changes the
    numeric value, so the folded arithmetic is unaffected.
    """
    try:
        value = Decimal(cost_rate)
    except (InvalidOperation, ValueError) as exc:
        raise NetOfCostConfigurationError(
            f"cost_rate {cost_rate!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise NetOfCostConfigurationError(
            f"cost_rate {cost_rate!r} must be a finite decimal"
        )
    if value < _ZERO:
        raise NetOfCostConfigurationError(
            f"cost_rate {cost_rate!r} must be non-negative (a transaction rebate is "
            "not this layer's model)"
        )
    return str(value.normalize())


@dataclass(frozen=True, slots=True)
class NetOfCostSpecification:
    """A declarative, content-addressed net-of-cost request.

    ``source_stability_id`` is the ``research_result_id`` of exactly one sealed
    :class:`~quantforge.stability.result.WalkForwardStability`; ``cost_rate`` is the
    declared linear one-way transaction-cost rate (a non-negative finite decimal
    string, canonicalized here). Constructing this reads no store and no wall clock; it
    validates its own shape, exactly as the stability / calibration-significance layers
    refuse a misconfigured request.
    """

    name: str
    source_stability_id: str
    cost_rate: str
    spec_version: str = NETCOST_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise NetOfCostConfigurationError(
                "a net-of-cost request must have a non-empty name"
            )
        if (
            not isinstance(self.source_stability_id, str)
            or not self.source_stability_id
        ):
            raise NetOfCostConfigurationError(
                "source_stability_id must be a non-empty walk-forward-stability id"
            )
        if not isinstance(self.cost_rate, str) or not self.cost_rate:
            raise NetOfCostConfigurationError(
                "cost_rate must be a non-empty decimal string"
            )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise NetOfCostConfigurationError("spec_version must be a non-empty string")
        # Canonicalize cost_rate to a stable non-negative decimal string. Idempotent
        # (normalizing an already-canonical rate is a no-op), so re-validating a
        # round-tripped instance is harmless. frozen dataclass => set via
        # object.__setattr__.
        object.__setattr__(self, "cost_rate", _canonical_cost_rate(self.cost_rate))

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed
        record)."""
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "source_stability_id": self.source_stability_id,
            "cost_rate": self.cost_rate,
        }
