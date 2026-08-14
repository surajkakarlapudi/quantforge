"""The declarative, content-addressed strategy-admissibility request (§14).

A **strategy-admissibility request** names the three sealed ex-post verdicts of one
strategy to combine into a single admissibility decision: exactly one
:class:`~quantforge.stability.result.WalkForwardStability`, one
:class:`~quantforge.calsig.result.CalibrationSignificance`, and one
:class:`~quantforge.netcostsig.result.NetOfCostSignificance`, plus the declared
significance level ``alpha`` at which the calibration and net-of-cost tests are read.
Like every request in this project it is a frozen value whose identity is a pure content
hash of *what was declared* - the engine resolves and interprets it; it never executes
caller code (mirrors
:class:`~quantforge.netcostsig.spec.NetOfCostSignificanceSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.admissibility.errors.AdmissibilityConfigurationError`): an empty
``name`` / ``spec_version`` / any source id, or an ``alpha`` that is not a decimal
string strictly inside ``(0, 1)``. It **canonicalizes** ``alpha`` once
(``str(Decimal(alpha).normalize())``) so ``"0.05"`` and ``"0.050"`` are the same request
and yield the same id. It reads no store and no wall clock - it cannot know whether the
referenced records exist (that is the engine's fail-closed resolution step) or whether
they are defined; it validates only the request's internal shape.

``alpha`` is the single per-request numerical parameter (it is folded into the id, not
imputed): the level below which the net-of-cost edge's one-sided p-value is deemed
significantly profitable, and above which the calibration's two-sided p-value is deemed
not significantly mis-calibrated. The joint-decision rule itself is the single approved
method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from quantforge.admissibility.errors import AdmissibilityConfigurationError
from quantforge.admissibility.version import ADMISSIBILITY_SPEC_VERSION

__all__ = ["DEFAULT_ALPHA", "AdmissibilitySpecification"]

#: The default declared significance level - the conventional 5%. A decimal string,
#: canonicalized at construction and folded into ``admissibility_id`` (§14).
DEFAULT_ALPHA = "0.05"

_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class AdmissibilitySpecification:
    """A declarative, content-addressed strategy-admissibility request.

    Each ``source_*_id`` is the ``research_result_id`` of exactly one sealed ex-post
    verdict of the same strategy. ``alpha`` is the declared significance level (a
    decimal string strictly inside ``(0, 1)``, canonicalized at construction).
    Constructing this reads no store and no wall clock; it validates its own shape,
    exactly as the significance layers refuse a misconfigured request.
    """

    name: str
    source_stability_id: str
    source_calibration_significance_id: str
    source_net_of_cost_significance_id: str
    alpha: str = DEFAULT_ALPHA
    spec_version: str = field(default=ADMISSIBILITY_SPEC_VERSION)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise AdmissibilityConfigurationError(
                "a strategy-admissibility request must have a non-empty name"
            )
        for label, value in (
            ("source_stability_id", self.source_stability_id),
            (
                "source_calibration_significance_id",
                self.source_calibration_significance_id,
            ),
            (
                "source_net_of_cost_significance_id",
                self.source_net_of_cost_significance_id,
            ),
        ):
            if not isinstance(value, str) or not value:
                raise AdmissibilityConfigurationError(
                    f"{label} must be a non-empty research-result id"
                )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise AdmissibilityConfigurationError(
                "spec_version must be a non-empty string"
            )
        object.__setattr__(self, "alpha", _canonical_alpha(self.alpha))

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed
        record)."""
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "source_stability_id": self.source_stability_id,
            "source_calibration_significance_id": (
                self.source_calibration_significance_id
            ),
            "source_net_of_cost_significance_id": (
                self.source_net_of_cost_significance_id
            ),
            "alpha": self.alpha,
        }


def _canonical_alpha(raw: object) -> str:
    """Validate + canonicalize the declared ``alpha`` (fail closed).

    ``alpha`` must be a decimal string strictly inside ``(0, 1)``; it is returned in the
    project's canonical form ``str(Decimal(alpha).normalize())`` so equal levels are the
    same request (and the same id) regardless of the caller's spelling.
    """
    if not isinstance(raw, str) or not raw:
        raise AdmissibilityConfigurationError(
            "alpha must be a non-empty decimal string"
        )
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise AdmissibilityConfigurationError(
            f"alpha must be a decimal string, got {raw!r}"
        ) from exc
    if not value.is_finite() or value <= _ZERO or value >= _ONE:
        raise AdmissibilityConfigurationError(
            f"alpha must be strictly inside (0, 1), got {raw!r}"
        )
    return str(value.normalize())
