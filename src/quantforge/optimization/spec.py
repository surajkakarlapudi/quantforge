"""The declarative, content-addressed portfolio-optimization request (§14).

A **portfolio-optimization request** names exactly one sealed
:class:`~quantforge.factorrisk.result.FactorRiskModel` (the covariance matrix to
optimize over), the objective (``minimum_variance`` in v1), and the fully-invested
constraint. Like every request in this project it is a frozen value whose identity is a
pure content hash of *what was declared* - the engine resolves and interprets it; it
never executes caller code (mirrors
:class:`~quantforge.factorrisk.spec.FactorRiskSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.optimization.errors.PortfolioOptimizationConfigurationError`): an
empty ``name`` / ``spec_version`` / ``factor_risk_id``; an ``objective`` outside the
closed vocabulary (:data:`_OBJECTIVES`); or ``fully_invested`` not ``True`` (the only v1
constraint). It reads no store and no wall clock - it cannot know whether the referenced
id exists (that is the engine's fail-closed resolution step) or whether the covariance
is positive-definite (that needs the resolved matrix); it validates only the request's
internal shape.

The referenced risk model's *content* is not part of the spec identity - that is folded
by :func:`~quantforge.optimization.identity.optimization_id` at the engine, from the
resolved record's ``result_hash`` - so the spec is a stable declaration independent of
whether the referenced result has been computed yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.optimization.errors import PortfolioOptimizationConfigurationError
from quantforge.optimization.version import OPTIMIZATION_SPEC_VERSION

__all__ = [
    "OBJECTIVE_MINIMUM_VARIANCE",
    "PortfolioOptimizationSpecification",
]

#: The only objective the v1 optimizer supports (approved decision, §8).
#: Minimum-variance needs only the covariance matrix - no expected-return vector, which
#: the repository cannot supply PIT-honestly. Mean-variance / maximum-Sharpe are
#: deferred pending a PIT-safe expected-return artifact.
OBJECTIVE_MINIMUM_VARIANCE = "minimum_variance"

#: The closed objective vocabulary. An objective outside this set is a configuration
#: defect, raised - never silently reinterpreted. Extending it later hashes distinctly
#: via ``optimization_id`` (the objective is folded), so no collision can occur.
_OBJECTIVES = frozenset({OBJECTIVE_MINIMUM_VARIANCE})


@dataclass(frozen=True, slots=True)
class PortfolioOptimizationSpecification:
    """A declarative, content-addressed global minimum-variance request.

    ``factor_risk_id`` is the sealed
    :class:`~quantforge.factorrisk.result.FactorRiskModel` whose ``N x N`` covariance
    matrix is the optimization input. ``objective`` is the closed-vocabulary objective
    (``minimum_variance`` in v1). ``fully_invested`` is the single equality constraint
    ``1ᵀw = 1`` (must be ``True`` in v1; the flag is reserved so a future phase can add
    constraint variants without changing the request shape). Constructing this reads no
    store and no wall clock; it validates its own shape, exactly as the factor-risk /
    attribution layers refuse a misconfigured request.
    """

    name: str
    factor_risk_id: str
    objective: str = OBJECTIVE_MINIMUM_VARIANCE
    fully_invested: bool = True
    spec_version: str = OPTIMIZATION_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise PortfolioOptimizationConfigurationError(
                "a portfolio-optimization request must have a non-empty name"
            )
        if not isinstance(self.factor_risk_id, str) or not self.factor_risk_id:
            raise PortfolioOptimizationConfigurationError(
                "factor_risk_id must be a non-empty sealed FactorRiskModel id"
            )
        if self.objective not in _OBJECTIVES:
            raise PortfolioOptimizationConfigurationError(
                f"objective {self.objective!r} is not supported; the v1 optimizer "
                f"supports exactly {sorted(_OBJECTIVES)!r} (fail closed rather than "
                "silently reinterpret)"
            )
        # ``fully_invested`` is the single v1 constraint and must be True. It is not a
        # tunable: a False value would ask for an unconstrained minimum-variance problem
        # (whose solution is the meaningless ``w = 0`` for a positive-definite Σ), so it
        # is refused rather than solved into a degenerate answer. ``bool`` is a subclass
        # of ``int``; an explicit identity check keeps ``1`` from masquerading as True.
        if self.fully_invested is not True:
            raise PortfolioOptimizationConfigurationError(
                "fully_invested must be True; the v1 optimizer supports only the "
                "fully-invested constraint 1ᵀw = 1 (long-only / box / other "
                "constraints are out of scope)"
            )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise PortfolioOptimizationConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        Emits the objective and the fully-invested flag alongside the referenced risk
        model id, so the serialized request fully determines the declared optimization.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "factor_risk_id": self.factor_risk_id,
            "objective": self.objective,
            "fully_invested": self.fully_invested,
        }
