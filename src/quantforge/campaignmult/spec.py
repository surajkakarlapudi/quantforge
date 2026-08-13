"""The declarative, content-addressed campaign-multiplicity-correction request (§14).

A **campaign-multiplicity-correction request** names exactly one sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation`, a declared significance
level ``alpha``, and an **ordered** set of
:class:`~quantforge.campaignmult.model.CorrectionMethod`\\ s to apply to that campaign's
per-trial one-sided Probabilistic-Sharpe-Ratio p-value family (``p_i = 1 - PSR_i`` over
the trials whose ``psr`` the source sealed as KNOWN). Like every request in this project
it is a frozen value whose identity is a pure content hash of *what was declared* - the
engine resolves and interprets it; it never executes caller code (mirrors
:class:`~quantforge.multiplicity.spec.MultipleComparisonSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.campaignmult.errors.CampaignMultiplicityConfigurationError`): an
empty ``name`` / ``spec_version`` / ``source_campaign_id``; an ``alpha`` that is not a
decimal string strictly inside the open interval ``(0, 1)``; an empty method tuple or a
duplicated method. It reads no store and no wall clock - it cannot know whether the
referenced campaign exists (that is the engine's fail-closed resolution step) or how
many trials it holds; it validates only the request's internal shape.

``alpha`` is **canonicalized** at construction to a stable decimal string (via
:func:`decimal.Decimal.normalize`), so ``"0.05"`` and ``"0.050"`` declare the identical
request with the identical id. The **method order is preserved** (never sorted): the
correction of each method is independent of the others, but the order fixes the order
the methods read back in, and is folded into the id, so a differently-ordered request is
a distinct record. Duplicate methods are rejected (a method applied twice carries no
information).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.campaignmult.errors import CampaignMultiplicityConfigurationError
from quantforge.campaignmult.model import CorrectionMethod
from quantforge.campaignmult.version import CAMPAIGNMULT_SPEC_VERSION
from quantforge.multiplicity.spec import DEFAULT_METHODS

__all__ = [
    "DEFAULT_METHODS",
    "CampaignMultiplicitySpecification",
]

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
        raise CampaignMultiplicityConfigurationError(
            f"alpha {alpha!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise CampaignMultiplicityConfigurationError(
            f"alpha {alpha!r} must be a finite decimal"
        )
    if not (_ZERO < value < _ONE):
        raise CampaignMultiplicityConfigurationError(
            f"alpha {alpha!r} must lie strictly inside the open interval (0, 1)"
        )
    return str(value.normalize())


@dataclass(frozen=True, slots=True)
class CampaignMultiplicitySpecification:
    """A declarative, content-addressed campaign-multiplicity-correction request.

    ``source_campaign_id`` is the ``research_result_id`` of exactly one sealed
    :class:`~quantforge.campaign.result.ResearchCampaignEvaluation`; ``alpha`` is the
    declared significance level (a decimal string strictly inside ``(0, 1)``,
    canonicalized here); ``methods`` is an **ordered**, duplicate-free tuple of
    :class:`~quantforge.campaignmult.model.CorrectionMethod`\\ s (defaulting to
    :data:`DEFAULT_METHODS`). Constructing this reads no store and no wall clock; it
    validates its own shape, exactly as the multiplicity / campaign layers refuse a
    misconfigured request.
    """

    name: str
    source_campaign_id: str
    alpha: str
    methods: tuple[CorrectionMethod, ...] = DEFAULT_METHODS
    spec_version: str = CAMPAIGNMULT_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise CampaignMultiplicityConfigurationError(
                "a campaign-multiplicity-correction request must have a non-empty name"
            )
        if not isinstance(self.source_campaign_id, str) or not self.source_campaign_id:
            raise CampaignMultiplicityConfigurationError(
                "source_campaign_id must be a non-empty research-campaign id"
            )
        if not isinstance(self.methods, tuple) or not self.methods:
            raise CampaignMultiplicityConfigurationError(
                "methods must be a non-empty tuple of CorrectionMethod values"
            )
        seen: set[CorrectionMethod] = set()
        for method in self.methods:
            if not isinstance(method, CorrectionMethod):
                raise CampaignMultiplicityConfigurationError(
                    "each method must be a CorrectionMethod value"
                )
            if method in seen:
                raise CampaignMultiplicityConfigurationError(
                    f"duplicate method {method.value!r}; each requested method must be "
                    "distinct (applying a method twice carries no information)"
                )
            seen.add(method)
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise CampaignMultiplicityConfigurationError(
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
            "source_campaign_id": self.source_campaign_id,
            "alpha": self.alpha,
            "methods": [method.value for method in self.methods],
        }
