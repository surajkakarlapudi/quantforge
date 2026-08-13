"""The declarative, content-addressed minimum-track-record-length request (§14).

A **minimum-track-record-length request** names exactly one sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation` to evaluate, together
with a confidence level ``alpha`` and a benchmark Sharpe ``SR*``. Like every request in
this project it is a frozen value whose identity is a pure content hash of *what was
declared* - the engine resolves and interprets it; it never executes caller code
(mirrors :class:`~quantforge.campaign.spec.ResearchCampaignSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.mintrl.errors.MinTrlConfigurationError`): an empty ``name`` /
``spec_version`` / ``source_campaign_id``; a ``confidence`` that is not a finite decimal
strictly inside ``(0, 1)`` (so ``Z_alpha = Φ⁻¹(alpha)`` is defined); a non-decimal or
non-finite ``benchmark_sharpe`` (any finite sign is accepted - a benchmark Sharpe may
legitimately be zero or negative). Both numerical parameters are **canonicalized**
(``str(+Decimal(...))``) so two spellings of the same number yield one id. It reads no
store and no wall clock - it cannot know whether the referenced campaign exists (that is
the engine's fail-closed resolution step) or how many trials it holds; it validates only
the request's internal shape.

The determined-trials floor is the fixed platform constant
:data:`~quantforge.mintrl.result.MIN_DETERMINED_TRIALS` (folded into the id by the
engine + identity, not the request), and the metric set is the single approved
methodology - so a MinTRL request is fully described by the name, the one source id, the
confidence, and the benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.mintrl.errors import MinTrlConfigurationError
from quantforge.mintrl.version import MINTRL_SPEC_VERSION

__all__ = ["MinimumTrackRecordLengthSpecification"]

_ZERO = Decimal(0)
_ONE = Decimal(1)


def _canonical_decimal(raw: object, *, what: str) -> str:
    """Canonicalize a finite decimal string; fail closed otherwise.

    The value is folded into identity, so it must be canonical: two spellings of the
    same number must yield one id. A non-string, non-decimal, or non-finite value is a
    configuration defect, raised rather than guessed.
    """
    if not isinstance(raw, str) or not raw:
        raise MinTrlConfigurationError(
            f"{what} must be a non-empty decimal string, got {raw!r}"
        )
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise MinTrlConfigurationError(
            f"{what} {raw!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise MinTrlConfigurationError(f"{what} {raw!r} must be finite")
    return str(+value)


@dataclass(frozen=True, slots=True)
class MinimumTrackRecordLengthSpecification:
    """A declarative, content-addressed minimum-track-record-length request.

    ``source_campaign_id`` is the ``research_result_id`` of exactly one sealed
    :class:`~quantforge.campaign.result.ResearchCampaignEvaluation`. ``confidence`` is
    the significance level ``alpha`` (a finite decimal strictly inside ``(0, 1)``;
    ``Z_alpha = Φ⁻¹(alpha)``); ``benchmark_sharpe`` is the per-period Sharpe threshold
    ``SR*`` the MinTRL is computed against (``0`` by default). Both are canonicalized
    and folded into identity. Constructing this reads no store and no wall clock; it
    validates its own shape, exactly as the campaign / calibration layers refuse a
    misconfigured request.
    """

    name: str
    source_campaign_id: str
    confidence: str = "0.95"
    benchmark_sharpe: str = "0"
    spec_version: str = MINTRL_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise MinTrlConfigurationError(
                "a minimum-track-record-length request must have a non-empty name"
            )
        if not isinstance(self.source_campaign_id, str) or not self.source_campaign_id:
            raise MinTrlConfigurationError(
                "source_campaign_id must be a non-empty research-campaign id"
            )
        confidence = _canonical_decimal(self.confidence, what="confidence")
        if not (_ZERO < Decimal(confidence) < _ONE):
            raise MinTrlConfigurationError(
                f"confidence {self.confidence!r} must be strictly inside (0, 1) so "
                "Z_alpha = inverse-normal(confidence) is defined"
            )
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(
            self,
            "benchmark_sharpe",
            _canonical_decimal(self.benchmark_sharpe, what="benchmark_sharpe"),
        )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise MinTrlConfigurationError("spec_version must be a non-empty string")

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed
        record)."""
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "source_campaign_id": self.source_campaign_id,
            "confidence": self.confidence,
            "benchmark_sharpe": self.benchmark_sharpe,
        }
