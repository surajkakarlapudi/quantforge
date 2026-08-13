"""The Phase 27 walk-forward turnover & stability layer (public surface).

This package turns a declarative
:class:`~quantforge.stability.spec.WalkForwardStabilitySpecification` (naming exactly
one sealed :class:`~quantforge.walkforward.result.WalkForwardEvaluation`) into a sealed,
content-addressed :class:`~quantforge.stability.result.WalkForwardStability`: the
per-window stability of each REALIZED window's GMV weight vector (gross leverage,
concentration, effective breadth, largest position, and one-way turnover against the
immediately-preceding REALIZED window) plus the aggregate turnover / concentration
profile over the walk. It is the first consumer of Phase 22's reserved-but-unconsumed
per-window ``weights`` payload; it is a pure consumer strictly above Phase 22 and
introduces no new store, no new PIT surface, and no new numerical primitive.
"""

from __future__ import annotations

from quantforge.stability.result import WalkForwardStability
from quantforge.stability.spec import WalkForwardStabilitySpecification

__all__ = [
    "WalkForwardStability",
    "WalkForwardStabilitySpecification",
]
