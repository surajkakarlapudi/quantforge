"""The declarative, content-addressed research-campaign request (§14).

A **research-campaign request** names an **ordered** set of ``N`` sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` records - the "trials" of
one research campaign, each an out-of-sample evaluation of a distinct strategy recipe -
plus a benchmark Sharpe ``SR*`` (the per-trial Probabilistic-Sharpe-Ratio threshold,
``0`` by default). Like every request in this project it is a frozen value whose
identity is a pure content hash of *what was declared* - the engine resolves and
interprets it; it never executes caller code (mirrors
:class:`~quantforge.factorrisk.spec.FactorRiskSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.campaign.errors.CampaignConfigurationError`): an empty ``name`` or
``spec_version``; fewer than :data:`_MIN_TRIALS` (two - a selection-bias correction
needs at least a pair to estimate the cross-trial Sharpe dispersion) or more than
:data:`N_MAX` trial ids; a trial id that is empty or duplicated; a non-decimal or
non-finite ``benchmark_sharpe``. It reads no store and no wall clock - it cannot know
whether the referenced ids exist (that is the engine's fail-closed resolution step) or
whether the trials are commensurable (that needs the resolved records); it validates
only the request's internal shape.

The **trial order is semantic** and is preserved exactly (never sorted): the count of
submitted trials *is* the size ``N`` of the search the Deflated Sharpe Ratio deflates
against (CE-2, every submitted trial counts, valid or not), and the order fixes the
``trial_1..trial_N`` labels and the selection index - so ``(A, B)`` and ``(B, A)`` are
distinct requests with distinct ids. Duplicate trial ids are rejected (the same OOS
series twice would understate the search). The trial *content* is not part of the spec
identity - that is folded by :func:`~quantforge.campaign.identity.campaign_id` at the
engine, from the referenced records' ``result_hash`` - so the spec is a stable
declaration independent of whether the referenced results have been computed yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.campaign.errors import CampaignConfigurationError
from quantforge.campaign.version import CAMPAIGN_SPEC_VERSION

__all__ = [
    "N_MAX",
    "ResearchCampaignSpecification",
]

#: The maximum number of trials a v1 research-campaign request may declare (approved
#: decision, ★5). A campaign's selection-bias correction is an exact-``Decimal``
#: computation over ``N`` trials; capping ``N`` keeps the per-trial table interpretable
#: and the cost bounded. Set higher than the factor-risk ``N_MAX`` of 16 because a
#: research campaign legitimately enumerates far more competing strategy variants than a
#: covariance matrix has factors, and the campaign cost is linear in ``N`` (no ``N x N``
#: matrix). Exceeding it is a configuration defect, raised - never silently truncated.
N_MAX = 64

#: The minimum number of trials: a selection-bias correction needs at least a pair to
#: estimate the cross-trial Sharpe dispersion (a single trial is not a search). Fewer is
#: a configuration defect, raised.
_MIN_TRIALS = 2


def _canonical_decimal(raw: object, *, what: str) -> str:
    """Canonicalize a finite decimal string; fail closed otherwise.

    ``benchmark_sharpe`` is folded into identity, so it must be canonical: two spellings
    of the same number must yield one id. A non-string, non-decimal, or non-finite value
    is a configuration defect, raised rather than guessed. Any finite sign is accepted
    (a benchmark Sharpe threshold may legitimately be zero or negative), unlike a
    strictly positive annualization convention.
    """
    if not isinstance(raw, str) or not raw:
        raise CampaignConfigurationError(
            f"{what} must be a non-empty decimal string, got {raw!r}"
        )
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise CampaignConfigurationError(
            f"{what} {raw!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise CampaignConfigurationError(f"{what} {raw!r} must be finite")
    return str(+value)


@dataclass(frozen=True, slots=True)
class ResearchCampaignSpecification:
    """A declarative, content-addressed research-campaign-evaluation request.

    ``trial_ids`` is an **ordered** tuple of sealed
    :class:`~quantforge.walkforward.result.WalkForwardEvaluation` ids (each a distinct
    strategy's out-of-sample evaluation), at least :data:`_MIN_TRIALS` and at most
    :data:`N_MAX` long, with no duplicate. ``benchmark_sharpe`` is the per-period Sharpe
    threshold ``SR*`` the per-trial Probabilistic Sharpe Ratio tests against, folded
    into identity. Constructing this reads no store and no wall clock; it validates
    its own shape, exactly as the walk-forward / factor-risk layers refuse a
    misconfigured request.
    """

    name: str
    trial_ids: tuple[str, ...]
    benchmark_sharpe: str = "0"
    spec_version: str = CAMPAIGN_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise CampaignConfigurationError(
                "a research-campaign request must have a non-empty name"
            )
        if not isinstance(self.trial_ids, tuple):
            raise CampaignConfigurationError(
                "trial_ids must be a tuple of sealed walk-forward-evaluation ids"
            )
        if len(self.trial_ids) < _MIN_TRIALS:
            raise CampaignConfigurationError(
                f"a research-campaign request must enumerate at least {_MIN_TRIALS} "
                "trial ids (a selection-bias correction needs a pair)"
            )
        if len(self.trial_ids) > N_MAX:
            raise CampaignConfigurationError(
                f"a research-campaign request declares {len(self.trial_ids)} "
                f"trials; at most N_MAX={N_MAX} are allowed (fail closed rather than "
                "truncate)"
            )
        seen: set[str] = set()
        for trial_id in self.trial_ids:
            if not isinstance(trial_id, str) or not trial_id:
                raise CampaignConfigurationError(
                    "each trial id must be a non-empty walk-forward-evaluation id"
                )
            if trial_id in seen:
                raise CampaignConfigurationError(
                    f"duplicate trial id {trial_id!r}; each trial must be distinct "
                    "(the same OOS series twice would understate the size of the "
                    "search)"
                )
            seen.add(trial_id)
        object.__setattr__(
            self,
            "benchmark_sharpe",
            _canonical_decimal(self.benchmark_sharpe, what="benchmark_sharpe"),
        )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise CampaignConfigurationError("spec_version must be a non-empty string")

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        ``trial_ids`` is emitted in its declared order (order is semantic - it fixes the
        trial labels and the selection index, and the count is the search size), so the
        serialized request - like the identity - preserves order and never sorts.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "trial_ids": list(self.trial_ids),
            "benchmark_sharpe": self.benchmark_sharpe,
        }
