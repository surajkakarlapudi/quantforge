"""The declarative, content-addressed factor-risk request (§11).

A **factor-risk request** names an **ordered** set of *N* sealed
:class:`~quantforge.factorportfolio.result.FactorPortfolio` records (each a factor whose
return series is a covariance/correlation input) plus the annualization convention
(``periods_per_year``). Like every request in this project it is a frozen value whose
identity is a pure content hash of *what was declared* - the engine resolves and
interprets it; it never executes caller code (mirrors
:class:`~quantforge.attribution.spec.AttributionSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.factorrisk.errors.FactorRiskConfigurationError`): an empty ``name``
or ``spec_version``; fewer than :data:`_MIN_FACTORS` (two - a covariance needs a pair)
or more than :data:`N_MAX` factor ids (bounding the ``N x N`` estimate); a factor id
that is
empty or duplicated; a non-decimal, non-finite, or non-positive ``periods_per_year``. It
reads no store and no wall clock - it cannot know whether the referenced ids exist (that
is the engine's fail-closed resolution step) or whether the factors are commensurable /
have a long-enough common window (those need the resolved series); it validates only the
request's internal shape.

The **factor order is semantic** and is preserved exactly (never sorted or
de-canonicalized): it fixes the matrix row/column order and therefore the
``factor_1..factor_N`` labels, so ``(A, B)`` and ``(B, A)`` are distinct requests with
distinct ids. Duplicate factor ids are rejected (a factor's covariance with itself is
its own variance - a degenerate second entry by construction). The factor *content* is
not
part of the spec identity - that is folded by
:func:`~quantforge.factorrisk.identity.factor_risk_id` at the engine, from the
referenced records' ``result_hash`` - so the spec is a stable declaration independent
of whether the referenced results have been computed yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.factorrisk.errors import FactorRiskConfigurationError
from quantforge.factorrisk.version import FACTORRISK_SPEC_VERSION

__all__ = [
    "N_MAX",
    "FactorRiskSpecification",
]

#: The maximum number of factors a v1 factor-risk request may declare (approved
#: decision,
#: §11). The estimate is an ``N x N`` exact-``Decimal`` covariance/correlation matrix
#: over the complete-case common window; capping *N* keeps the cost bounded and the
#: matrix
#: interpretable. Exceeding it is a configuration defect, raised - never silently
#: truncated.
N_MAX = 16

#: The minimum number of factors: a covariance/correlation matrix needs at least a pair
#: (a single-factor "matrix" is just that factor's variance, degenerate). Fewer is a
#: configuration defect, raised.
_MIN_FACTORS = 2

_ZERO = Decimal(0)


def _canonical_decimal(raw: object, *, what: str) -> str:
    """Canonicalize a strictly-positive finite decimal string; fail closed otherwise.

    ``periods_per_year`` is folded into identity, so it must be canonical: two
    spellings of the same number must yield one id. A non-string, non-decimal,
    non-finite, or
    non-positive value is a configuration defect, raised rather than guessed
    (annualizing by a non-positive period count is nonsensical).
    """
    if not isinstance(raw, str) or not raw:
        raise FactorRiskConfigurationError(
            f"{what} must be a non-empty decimal string, got {raw!r}"
        )
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise FactorRiskConfigurationError(
            f"{what} {raw!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise FactorRiskConfigurationError(f"{what} {raw!r} must be finite")
    if value <= _ZERO:
        raise FactorRiskConfigurationError(f"{what} {raw!r} must be strictly positive")
    return str(+value)


@dataclass(frozen=True, slots=True)
class FactorRiskSpecification:
    """A declarative, content-addressed factor-risk (covariance/correlation) request.

    ``factor_portfolio_ids`` is an **ordered** tuple of sealed
    :class:`~quantforge.factorportfolio.result.FactorPortfolio` ids (each a factor whose
    KNOWN ``(as_of, factor_return)`` series is a covariance input), at least
    :data:`_MIN_FACTORS`
    and at most :data:`N_MAX` long, with no duplicate.
    ``periods_per_year`` is the annualization convention threaded into the annualized
    volatility / covariance scalings and folded into identity. Constructing this reads
    no store and no wall clock; it validates its own shape, exactly as the attribution /
    factor-portfolio layers refuse a misconfigured request.
    """

    name: str
    factor_portfolio_ids: tuple[str, ...]
    periods_per_year: str = "1"
    spec_version: str = FACTORRISK_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise FactorRiskConfigurationError(
                "a factor-risk request must have a non-empty name"
            )
        if not isinstance(self.factor_portfolio_ids, tuple):
            raise FactorRiskConfigurationError(
                "factor_portfolio_ids must be a tuple of sealed factor-portfolio ids"
            )
        if len(self.factor_portfolio_ids) < _MIN_FACTORS:
            raise FactorRiskConfigurationError(
                f"a factor-risk request must enumerate at least {_MIN_FACTORS} factor "
                "ids (a covariance needs a pair)"
            )
        if len(self.factor_portfolio_ids) > N_MAX:
            raise FactorRiskConfigurationError(
                f"a factor-risk request declares {len(self.factor_portfolio_ids)} "
                f"factors; at most N_MAX={N_MAX} are allowed (fail closed rather than "
                "truncate)"
            )
        seen: set[str] = set()
        for factor_id in self.factor_portfolio_ids:
            if not isinstance(factor_id, str) or not factor_id:
                raise FactorRiskConfigurationError(
                    "each factor id must be a non-empty factor-portfolio id"
                )
            if factor_id in seen:
                raise FactorRiskConfigurationError(
                    f"duplicate factor id {factor_id!r}; each factor must be distinct "
                    "(a factor's covariance with itself is just its own variance)"
                )
            seen.add(factor_id)
        object.__setattr__(
            self,
            "periods_per_year",
            _canonical_decimal(self.periods_per_year, what="periods_per_year"),
        )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise FactorRiskConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        ``factor_portfolio_ids`` is emitted in its declared order (order is semantic -
        it fixes the matrix row/column order and the factor labels), so the serialized
        request - like the identity - preserves order and never sorts.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "factor_portfolio_ids": list(self.factor_portfolio_ids),
            "periods_per_year": self.periods_per_year,
        }
