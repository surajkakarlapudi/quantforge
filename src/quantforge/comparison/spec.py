"""The declarative, content-addressed strategy-comparison request (§14).

A **strategy-comparison request** names an **ordered** set of ``N`` sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` records - the competing
strategies of one head-to-head comparison, each an out-of-sample evaluation of a
distinct strategy recipe. Like every request in this project it is a frozen value whose
identity is a pure content hash of *what was declared* - the engine resolves and
interprets it; it never executes caller code (mirrors
:class:`~quantforge.campaign.spec.ResearchCampaignSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.comparison.errors.ComparisonConfigurationError`): an empty ``name``
or ``spec_version``; fewer than :data:`_MIN_STRATEGIES` (two - a comparison needs at
least a pair) or more than :data:`N_MAX` walk-forward ids; a walk-forward id that is
empty or duplicated. It reads no store and no wall clock - it cannot know whether the
referenced ids exist (that is the engine's fail-closed resolution step) or whether the
strategies are commensurable (that needs the resolved records); it validates only the
request's internal shape.

The **strategy order is semantic** and is preserved exactly (never sorted): it fixes the
``strategy_1..strategy_N`` labels and the upper-triangle ``(i < j)`` pair order - so
``(A, B)`` and ``(B, A)`` are distinct requests with distinct ids (with pairwise
statistics that differ only by the antisymmetry of the difference, SC-8). Duplicate ids
are rejected (comparing a strategy against itself is a degenerate, zero-difference pair
that carries no information). The strategy *content* is not part of the spec identity -
that is folded by :func:`~quantforge.comparison.identity.strategy_comparison_id` at the
engine, from the referenced records' ``result_hash`` - so the spec is a stable
declaration independent of whether the referenced results have been computed yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.comparison.errors import ComparisonConfigurationError
from quantforge.comparison.version import COMPARISON_SPEC_VERSION

__all__ = [
    "N_MAX",
    "StrategyComparisonSpecification",
]

#: The maximum number of strategies a v1 comparison request may declare (approved
#: decision). A comparison seals an upper-triangle matrix of ``N·(N-1)/2`` pairwise
#: cells; capping ``N`` keeps the matrix interpretable and the cost bounded. Set to 32 -
#: below the campaign ``N_MAX`` of 64 because the pairwise cost is quadratic in ``N``
#: (an ``N x N`` matrix), not linear. Exceeding it is a configuration defect, raised -
#: never silently truncated.
N_MAX = 32

#: The minimum number of strategies: a head-to-head comparison needs at least a pair.
#: Fewer is a configuration defect, raised.
_MIN_STRATEGIES = 2


@dataclass(frozen=True, slots=True)
class StrategyComparisonSpecification:
    """A declarative, content-addressed strategy-comparison request.

    ``walk_forward_ids`` is an **ordered** tuple of sealed
    :class:`~quantforge.walkforward.result.WalkForwardEvaluation` ids (each a distinct
    strategy's out-of-sample evaluation), at least :data:`_MIN_STRATEGIES` and at most
    :data:`N_MAX` long, with no duplicate. Constructing this reads no store and no wall
    clock; it validates its own shape, exactly as the walk-forward / campaign layers
    refuse a misconfigured request.
    """

    name: str
    walk_forward_ids: tuple[str, ...]
    spec_version: str = COMPARISON_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ComparisonConfigurationError(
                "a strategy-comparison request must have a non-empty name"
            )
        if not isinstance(self.walk_forward_ids, tuple):
            raise ComparisonConfigurationError(
                "walk_forward_ids must be a tuple of sealed walk-forward-evaluation ids"
            )
        if len(self.walk_forward_ids) < _MIN_STRATEGIES:
            raise ComparisonConfigurationError(
                f"a strategy-comparison request must enumerate at least "
                f"{_MIN_STRATEGIES} walk-forward ids (a comparison needs a pair)"
            )
        if len(self.walk_forward_ids) > N_MAX:
            raise ComparisonConfigurationError(
                f"a strategy-comparison request declares {len(self.walk_forward_ids)} "
                f"strategies; at most N_MAX={N_MAX} are allowed (fail closed rather "
                "than truncate)"
            )
        seen: set[str] = set()
        for walk_forward_id in self.walk_forward_ids:
            if not isinstance(walk_forward_id, str) or not walk_forward_id:
                raise ComparisonConfigurationError(
                    "each strategy id must be a non-empty walk-forward-evaluation id"
                )
            if walk_forward_id in seen:
                raise ComparisonConfigurationError(
                    f"duplicate strategy id {walk_forward_id!r}; each strategy must be "
                    "distinct (comparing a strategy against itself is a degenerate, "
                    "zero-difference pair)"
                )
            seen.add(walk_forward_id)
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise ComparisonConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        ``walk_forward_ids`` is emitted in its declared order (order is semantic - it
        fixes the strategy labels and the upper-triangle pair order), so the serialized
        request - like the identity - preserves order and never sorts.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "walk_forward_ids": list(self.walk_forward_ids),
        }
