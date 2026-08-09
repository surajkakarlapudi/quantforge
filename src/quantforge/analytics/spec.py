"""The declarative, content-addressed analytics request (proposal §J.1).

An **analytics request** names one sealed subject backtest (and, optionally, one sealed
benchmark backtest), the VaR confidences to evaluate, and the annualization convention
(risk-free rate per period and periods per year). Like every request in this project it
is a frozen value whose identity is a pure content hash of *what was declared* — the
engine resolves and interprets it; it never executes caller code (mirrors
:class:`~quantforge.experiment.spec.ExperimentSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.analytics.errors.AnalyticsConfigurationError`): an empty ``name`` or
``subject_id``; a ``benchmark_id`` equal to the ``subject_id`` (a strategy is not its
own benchmark — ambiguous); a ``var_confidence`` that is not a finite decimal string
strictly in ``(0, 1)`` or is duplicated (by canonical form); a non-decimal or negative
``risk_free_per_period``; a non-decimal or non-positive ``periods_per_year``. It reads
no store and no wall clock — it cannot know whether the referenced ids exist (that is
the engine's fail-closed resolution step); it validates only the request's internal
shape.

``var_confidences`` is canonicalized and treated as a **set** for identity: order and
duplicate spelling never change the id (``("0.95", "0.99")`` and ``("0.99", "0.9500")``
fold identically). The subject / benchmark *content* is not part of the spec identity —
that is folded by :func:`~quantforge.analytics.identity.analytics_id` at the engine,
from the referenced backtests' ``result_hash`` — so the spec is a stable declaration
independent of whether the referenced results have been computed yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from quantforge.analytics.errors import AnalyticsConfigurationError

__all__ = [
    "ANALYTICS_SPEC_VERSION",
    "AnalyticsSpecification",
]

#: The specification-schema version, folded into ``analytics_id`` (proposal §L). Bump it
#: when the serialized meaning of a request changes — never when engine logic changes
#: (that is :data:`~quantforge.analytics.version.ANALYTICS_ENGINE_VERSION`). Mirrors
#: ``experiment/1`` and ``universe-spec/1``.
ANALYTICS_SPEC_VERSION = "analytics/1"

_ZERO = Decimal(0)
_ONE = Decimal(1)


def _canonical_form(parsed: Decimal) -> str:
    """The spelling-independent canonical string of a finite decimal (pre-checked).

    ``normalize()`` strips trailing-zero / exponent differences so ``"0.95"`` and
    ``"0.9500"`` fold to one string (the set-identity contract), and ``format(_, "f")``
    forces fixed-point so a normalized value never lands in scientific notation (which
    would make the id depend on spelling again). Every value that reaches here has
    already been validated finite and in range.
    """
    return format(parsed.normalize(), "f")


def _canonical_confidence(value: object) -> str:
    """Validate one VaR confidence, return its canonical decimal string (fail closed).

    A confidence must be a finite decimal string strictly inside ``(0, 1)`` — a
    probability mass in the body of the distribution, so its complement ``1 - c`` is a
    non-empty, non-whole tail. ``"0.95"`` and ``"0.9500"`` canonicalize identically so
    the set identity is spelling-independent. A non-string, non-decimal, non-finite, or
    out-of-range value is a configuration defect, raised.
    """
    if not isinstance(value, str) or not value:
        raise AnalyticsConfigurationError(
            f"var_confidence must be a non-empty decimal string, got {value!r}"
        )
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AnalyticsConfigurationError(
            f"var_confidence {value!r} is not a valid decimal string"
        ) from exc
    if not parsed.is_finite():
        raise AnalyticsConfigurationError(f"var_confidence {value!r} must be finite")
    if not (_ZERO < parsed < _ONE):
        raise AnalyticsConfigurationError(
            f"var_confidence {value!r} must be strictly inside (0, 1)"
        )
    return _canonical_form(parsed)


def _canonical_decimal(value: object, field_name: str, *, allow_zero: bool) -> str:
    """Validate a convention decimal string; return its canonical form (fail closed).

    Used for ``risk_free_per_period`` (``allow_zero=True``: a zero MAR / rf is the
    default and legitimate) and ``periods_per_year`` (``allow_zero=False``: annualizing
    by a non-positive period count is nonsensical). A non-string, non-decimal,
    non-finite, or negative (or, when disallowed, zero) value is raised.
    """
    if not isinstance(value, str) or not value:
        raise AnalyticsConfigurationError(
            f"{field_name} must be a non-empty decimal string, got {value!r}"
        )
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AnalyticsConfigurationError(
            f"{field_name} {value!r} is not a valid decimal string"
        ) from exc
    if not parsed.is_finite():
        raise AnalyticsConfigurationError(f"{field_name} {value!r} must be finite")
    if parsed < _ZERO:
        raise AnalyticsConfigurationError(
            f"{field_name} {value!r} must not be negative"
        )
    if not allow_zero and parsed == _ZERO:
        raise AnalyticsConfigurationError(
            f"{field_name} {value!r} must be strictly positive"
        )
    return _canonical_form(parsed)


@dataclass(frozen=True, slots=True)
class AnalyticsSpecification:
    """A declarative, content-addressed performance-analytics request (§J.1).

    ``subject_id`` is a sealed :class:`~quantforge.backtest.result.BacktestResult`'s
    ``backtest_id``; ``benchmark_id`` (optional) is another — ``None`` requests the
    absolute-only block. ``var_confidences`` are decimal strings each strictly in ``(0,
    1)``, treated as a set for identity. ``risk_free_per_period`` / ``periods_per_year``
    are the annualization convention threaded into every ratio and folded into identity
    (proposal D8). Constructing this reads no store and no wall clock; it validates its
    own shape, exactly as the backtest/experiment layers refuse a misconfigured request.
    """

    name: str
    subject_id: str
    benchmark_id: str | None = None
    var_confidences: tuple[str, ...] = ("0.95",)
    risk_free_per_period: str = "0"
    periods_per_year: str = "1"
    spec_version: str = ANALYTICS_SPEC_VERSION
    #: The canonicalized, sorted, de-duplicated confidences — derived at construction,
    #: never supplied. Set-valued so order/spelling never changes identity.
    sorted_var_confidences: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise AnalyticsConfigurationError(
                "an analytics request must have a non-empty name"
            )
        if not isinstance(self.subject_id, str) or not self.subject_id:
            raise AnalyticsConfigurationError(
                "an analytics request must name a non-empty subject_id"
            )
        if self.benchmark_id is not None:
            if not isinstance(self.benchmark_id, str) or not self.benchmark_id:
                raise AnalyticsConfigurationError(
                    "benchmark_id, when given, must be a non-empty backtest id"
                )
            if self.benchmark_id == self.subject_id:
                raise AnalyticsConfigurationError(
                    "benchmark_id must differ from subject_id; a strategy is not its "
                    "own benchmark"
                )
        if not self.var_confidences:
            raise AnalyticsConfigurationError(
                "an analytics request must enumerate at least one var_confidence"
            )
        seen: set[str] = set()
        for raw in self.var_confidences:
            canonical = _canonical_confidence(raw)
            if canonical in seen:
                raise AnalyticsConfigurationError(
                    f"duplicate var_confidence {raw!r} (canonical {canonical!r}); each "
                    "confidence must be distinct"
                )
            seen.add(canonical)
        object.__setattr__(self, "sorted_var_confidences", tuple(sorted(seen)))
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
            raise AnalyticsConfigurationError("spec_version must be a non-empty string")

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        ``var_confidences`` is emitted in its sorted, canonical, de-duplicated form so
        the serialized request — like the identity — is independent of the order and
        spelling the caller supplied.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "subject_id": self.subject_id,
            "benchmark_id": self.benchmark_id,
            "var_confidences": list(self.sorted_var_confidences),
            "risk_free_per_period": self.risk_free_per_period,
            "periods_per_year": self.periods_per_year,
        }
