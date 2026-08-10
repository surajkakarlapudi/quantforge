"""The declarative, content-addressed attribution request (proposal §12, §21 D1/D3).

An **attribution request** names one sealed subject backtest and an **ordered** list of
*K* sealed factor backtests (each itself a ``BacktestResult`` — the Phase 15 D3
"benchmark is a sealed backtest" convention generalized from one benchmark to *K*
factors, D1), plus the annualization convention (risk-free rate per period and periods
per year). Like every request in this project it is a frozen value whose identity is a
pure content hash of *what was declared* — the engine resolves and interprets it; it
never executes caller code (mirrors
:class:`~quantforge.analytics.spec.AnalyticsSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.attribution.errors.AttributionConfigurationError`): an empty
``name`` or ``subject_id``; an empty ``factor_ids`` tuple; a factor id that is empty,
duplicated, or equal to the ``subject_id`` (a strategy cannot be a factor explaining
itself); more than :data:`K_MAX` factors (D3); a non-decimal or negative
``risk_free_per_period``; a non-decimal or non-positive ``periods_per_year``. It reads
no store and no wall clock — it cannot know whether the referenced ids exist (that is
the engine's fail-closed resolution step) or whether the subject has enough periods for
*K* factors (that needs the resolved return length); it validates only the request's
internal shape.

The **factor order is semantic** and is preserved exactly (never sorted or
de-canonicalized): it fixes the design-matrix column order and therefore the coefficient
labels, so ``(value, size)`` and ``(size, value)`` are distinct requests with distinct
ids. Duplicate factor ids are rejected (a factor regressed on itself twice is a
collinear design by construction). The subject / factor *content* is not part of the
spec identity — that is folded by
:func:`~quantforge.attribution.identity.attribution_id` at the engine, from the
referenced backtests' ``result_hash`` — so the spec is a stable declaration independent
of whether the referenced results have been computed yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.attribution.errors import AttributionConfigurationError

__all__ = [
    "ATTRIBUTION_SPEC_VERSION",
    "K_MAX",
    "AttributionSpecification",
]

#: The specification-schema version, folded into ``attribution_id`` (proposal §8). Bump
#: it when the serialized meaning of a request changes — never when engine logic changes
#: (that is :data:`~quantforge.attribution.version.ATTRIBUTION_ENGINE_VERSION`). Mirrors
#: ``analytics/1`` / ``experiment/1``.
ATTRIBUTION_SPEC_VERSION = "attribution/1"

#: The maximum number of factors a v1 attribution request may declare (approved D3). The
#: linear solve is a ``(K+1)x(K+1)`` exact-``Decimal`` factorization; capping *K* keeps
#: the cost bounded and the model interpretable. Exceeding it is a configuration defect,
#: raised — never silently truncated.
K_MAX = 8

_ZERO = Decimal(0)


def _canonical_form(parsed: Decimal) -> str:
    """The spelling-independent canonical string of a finite decimal (pre-checked).

    ``normalize()`` strips trailing-zero / exponent differences and ``format(_, "f")``
    forces fixed-point so a normalized value never lands in scientific notation (which
    would make the id depend on spelling). Every value that reaches here has already
    been validated finite and in range.
    """
    return format(parsed.normalize(), "f")


def _canonical_decimal(value: object, field_name: str, *, allow_zero: bool) -> str:
    """Validate a convention decimal string; return its canonical form (fail closed).

    Used for ``risk_free_per_period`` (``allow_zero=True``: a zero rf is the default and
    legitimate) and ``periods_per_year`` (``allow_zero=False``: annualizing by a
    non-positive period count is nonsensical). A non-string, non-decimal, non-finite, or
    negative (or, when disallowed, zero) value is raised.
    """
    if not isinstance(value, str) or not value:
        raise AttributionConfigurationError(
            f"{field_name} must be a non-empty decimal string, got {value!r}"
        )
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AttributionConfigurationError(
            f"{field_name} {value!r} is not a valid decimal string"
        ) from exc
    if not parsed.is_finite():
        raise AttributionConfigurationError(f"{field_name} {value!r} must be finite")
    if parsed < _ZERO:
        raise AttributionConfigurationError(
            f"{field_name} {value!r} must not be negative"
        )
    if not allow_zero and parsed == _ZERO:
        raise AttributionConfigurationError(
            f"{field_name} {value!r} must be strictly positive"
        )
    return _canonical_form(parsed)


@dataclass(frozen=True, slots=True)
class AttributionSpecification:
    """A declarative, content-addressed multi-factor attribution request (§12).

    ``subject_id`` is a sealed :class:`~quantforge.backtest.result.BacktestResult`'s
    ``backtest_id``; ``factor_ids`` is an **ordered**, non-empty tuple of other such ids
    (each a factor explaining the subject), at most :data:`K_MAX` long, with no
    duplicate and none equal to the subject. ``risk_free_per_period`` /
    ``periods_per_year`` are the annualization convention threaded into the
    excess-return construction and folded into identity. Constructing this reads no
    store and no wall clock; it validates its own shape, exactly as the
    backtest/analytics layers refuse a misconfigured request.
    """

    name: str
    subject_id: str
    factor_ids: tuple[str, ...]
    risk_free_per_period: str = "0"
    periods_per_year: str = "1"
    spec_version: str = ATTRIBUTION_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise AttributionConfigurationError(
                "an attribution request must have a non-empty name"
            )
        if not isinstance(self.subject_id, str) or not self.subject_id:
            raise AttributionConfigurationError(
                "an attribution request must name a non-empty subject_id"
            )
        if not isinstance(self.factor_ids, tuple) or not self.factor_ids:
            raise AttributionConfigurationError(
                "an attribution request must enumerate at least one factor id"
            )
        if len(self.factor_ids) > K_MAX:
            raise AttributionConfigurationError(
                f"an attribution request declares {len(self.factor_ids)} factors; at "
                f"most K_MAX={K_MAX} are allowed (fail closed rather than truncate)"
            )
        seen: set[str] = set()
        for factor_id in self.factor_ids:
            if not isinstance(factor_id, str) or not factor_id:
                raise AttributionConfigurationError(
                    "each factor id must be a non-empty backtest id"
                )
            if factor_id == self.subject_id:
                raise AttributionConfigurationError(
                    "a factor id must differ from subject_id; a strategy cannot be a "
                    "factor explaining itself"
                )
            if factor_id in seen:
                raise AttributionConfigurationError(
                    f"duplicate factor id {factor_id!r}; each factor must be distinct "
                    "(a repeated factor is a collinear design by construction)"
                )
            seen.add(factor_id)
        object.__setattr__(
            self,
            "risk_free_per_period",
            _canonical_decimal(
                self.risk_free_per_period, "risk_free_per_period", allow_zero=True
            ),
        )
        object.__setattr__(
            self,
            "periods_per_year",
            _canonical_decimal(
                self.periods_per_year, "periods_per_year", allow_zero=False
            ),
        )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise AttributionConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        ``factor_ids`` is emitted in its declared order (order is semantic — it fixes
        the regression's column order and coefficient labels), so the serialized request
        — like the identity — preserves order and never sorts.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "subject_id": self.subject_id,
            "factor_ids": list(self.factor_ids),
            "risk_free_per_period": self.risk_free_per_period,
            "periods_per_year": self.periods_per_year,
        }
