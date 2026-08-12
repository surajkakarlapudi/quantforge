"""The declarative, content-addressed multiplicity-correction request (§14).

A **multiple-comparison-correction request** names exactly one sealed
:class:`~quantforge.comparison.result.StrategyComparison`, a declared significance level
``alpha``, and an **ordered** set of
:class:`~quantforge.multiplicity.model.CorrectionMethod`\\ s to apply to that
comparison's KNOWN pairwise ``p`` value family. Like every request in this project it is
a frozen value whose identity is a pure content hash of *what was declared* - the engine
resolves and interprets it; it never executes caller code (mirrors
:class:`~quantforge.comparison.spec.StrategyComparisonSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.multiplicity.errors.MultiplicityConfigurationError`): an empty
``name`` / ``spec_version`` / ``source_strategy_comparison_id``; an ``alpha`` that is
not a decimal string strictly inside the open interval ``(0, 1)``; an empty method tuple
or a duplicated method. It reads no store and no wall clock - it cannot know whether the
referenced comparison exists (that is the engine's fail-closed resolution step) or how
many pairwise cells it holds; it validates only the request's internal shape.

``alpha`` is **canonicalized** at construction to a stable decimal string (via
:func:`decimal.Decimal.normalize`), so ``"0.05"`` and ``"0.050"`` declare the identical
request with the identical id (they would otherwise seal byte-different records for
identical arithmetic). The **method order is preserved** (never sorted): unlike the
strategy order of a comparison it is not semantically load-bearing (the correction of
each method is independent of the others), but it fixes the order the methods read back
in, and is folded into the id, so a differently-ordered request is a distinct record.
Duplicate methods are rejected (a method applied twice carries no information).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.multiplicity.errors import MultiplicityConfigurationError
from quantforge.multiplicity.model import CorrectionMethod
from quantforge.multiplicity.version import MULTIPLICITY_SPEC_VERSION

__all__ = [
    "DEFAULT_METHODS",
    "MultipleComparisonSpecification",
]

#: The approved default method set (load-bearing decision 3): Holm (family-wise, valid
#: under arbitrary dependence) and Benjamini-Yekutieli (false-discovery, valid under
#: arbitrary dependence). Both control their error rate for the *dependent* pairwise
#: family without an independence assumption; Benjamini-Hochberg is available but must
#: be named explicitly (it assumes independence / PRDS - MC-6).
DEFAULT_METHODS: tuple[CorrectionMethod, ...] = (
    CorrectionMethod.HOLM,
    CorrectionMethod.BENJAMINI_YEKUTIELI,
)

_ZERO = Decimal(0)
_ONE = Decimal(1)


def _canonical_alpha(alpha: str) -> str:
    """Canonicalize an ``alpha`` string to a stable decimal form in ``(0, 1)``.

    Parses ``alpha`` as a ``Decimal``, requires it strictly inside the open interval
    ``(0, 1)``, and returns ``str(value.normalize())`` so trailing-zero variants
    (``"0.05"`` / ``"0.050"``) collapse to one canonical string (and thus one id). Fails
    closed on a non-decimal, non-finite, or out-of-range value.
    """
    try:
        value = Decimal(alpha)
    except (InvalidOperation, ValueError) as exc:
        raise MultiplicityConfigurationError(
            f"alpha {alpha!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise MultiplicityConfigurationError(
            f"alpha {alpha!r} must be a finite decimal"
        )
    if not (_ZERO < value < _ONE):
        raise MultiplicityConfigurationError(
            f"alpha {alpha!r} must lie strictly inside the open interval (0, 1)"
        )
    return str(value.normalize())


@dataclass(frozen=True, slots=True)
class MultipleComparisonSpecification:
    """A declarative, content-addressed multiplicity-correction request.

    ``source_strategy_comparison_id`` is the ``research_result_id`` of exactly one
    sealed :class:`~quantforge.comparison.result.StrategyComparison`; ``alpha`` is the
    declared significance level (a decimal string strictly inside ``(0, 1)``,
    canonicalized here); ``methods`` is an **ordered**, duplicate-free tuple of
    :class:`~quantforge.multiplicity.model.CorrectionMethod`\\ s (defaulting to
    :data:`DEFAULT_METHODS`). Constructing this reads no store and no wall clock; it
    validates its own shape, exactly as the comparison / campaign layers refuse a
    misconfigured request.
    """

    name: str
    source_strategy_comparison_id: str
    alpha: str
    methods: tuple[CorrectionMethod, ...] = DEFAULT_METHODS
    spec_version: str = MULTIPLICITY_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise MultiplicityConfigurationError(
                "a multiplicity-correction request must have a non-empty name"
            )
        if (
            not isinstance(self.source_strategy_comparison_id, str)
            or not self.source_strategy_comparison_id
        ):
            raise MultiplicityConfigurationError(
                "source_strategy_comparison_id must be a non-empty "
                "strategy-comparison id"
            )
        if not isinstance(self.methods, tuple) or not self.methods:
            raise MultiplicityConfigurationError(
                "methods must be a non-empty tuple of CorrectionMethod values"
            )
        seen: set[CorrectionMethod] = set()
        for method in self.methods:
            if not isinstance(method, CorrectionMethod):
                raise MultiplicityConfigurationError(
                    "each method must be a CorrectionMethod value"
                )
            if method in seen:
                raise MultiplicityConfigurationError(
                    f"duplicate method {method.value!r}; each requested method must be "
                    "distinct (applying a method twice carries no information)"
                )
            seen.add(method)
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise MultiplicityConfigurationError(
                "spec_version must be a non-empty string"
            )
        # Canonicalize alpha to a stable decimal string. Idempotent (normalizing an
        # already-canonical alpha is a no-op), so re-validating a round-tripped instance
        # is harmless. frozen dataclass => set via object.__setattr__.
        object.__setattr__(self, "alpha", _canonical_alpha(self.alpha))

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        ``methods`` is emitted in its declared order (preserved, never sorted), so the
        serialized request - like the identity - reads back in request order.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "source_strategy_comparison_id": self.source_strategy_comparison_id,
            "alpha": self.alpha,
            "methods": [method.value for method in self.methods],
        }
