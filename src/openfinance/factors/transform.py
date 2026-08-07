"""Pure cross-sectional transforms over the KNOWN cells (``docs/factors.md`` §6.2).

A transform is a **pure, deterministic function of the KNOWN cells of one
one-``as_of`` vector** — it introduces no new data and no new boundary, so it
cannot add look-ahead (every input was already ``as_of``-eligible). Included per
Decision F3.

Three disciplines are absolute (§6.2, §12; data-model Principle 8):

* **Population = KNOWN cells only.** ``UNDEFINED`` cells are *excluded* from the
  statistic and stay ``UNDEFINED`` in the output — never imputed to a mean/median,
  which would fabricate data.
* **Exact arithmetic under the Phase 7 pinned context.** ``Decimal`` only, no
  ``float``; all arithmetic runs inside the caller-supplied
  :class:`decimal.Context` (precision 34, ``ROUND_HALF_EVEN``), which is already
  folded into ``metric_engine_version_id`` — so a transform result is
  byte-reproducible and its context is already a version pin.
* **Deterministic order.** Ranks and percentiles break ties by ``company_id``
  ascending, so ``rank`` is a total order and every transform is a pure function of
  the (member → value) map.

A transform is identified by a canonical ``transform_id`` string (``"none"``,
``"rank"``, ``"zscore"``, ``"minmax"``, or ``"winsorize:<lower>:<upper>"``) that is
hashed into ``factor_definition_id`` (§7). A degenerate population (zero standard
deviation for ``zscore``, zero range for ``minmax``) fails closed to ``UNDEFINED``
for every cell — never a division blow-up — and an all-``UNDEFINED`` population
yields an all-``UNDEFINED`` transformed vector rather than an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from enum import StrEnum

from openfinance.canonical.numeric import canonical_decimal_str
from openfinance.factors.errors import FactorConfigurationError

__all__ = ["Transform", "TransformKind"]


class TransformKind(StrEnum):
    """The closed set of supported cross-sectional transforms (§6.2)."""

    NONE = "none"
    RANK = "rank"
    ZSCORE = "zscore"
    MINMAX = "minmax"
    WINSORIZE = "winsorize"


@dataclass(frozen=True, slots=True)
class Transform:
    """A pure cross-sectional transform, identified by a canonical ``transform_id``.

    Construct via the factory classmethods (:meth:`none`, :meth:`rank`,
    :meth:`zscore`, :meth:`minmax`, :meth:`winsorize`) so the parameters and the
    ``transform_id`` can never drift apart. ``apply`` maps a ``company_id`` →
    ``Decimal`` population (the KNOWN cells only, in universe order) to a
    ``company_id`` → serialized value string, ``None`` for any member the transform
    leaves undefined.
    """

    kind: TransformKind
    lower: Decimal | None = None
    upper: Decimal | None = None

    # -- factories -----------------------------------------------------------

    @classmethod
    def none(cls) -> Transform:
        """The identity transform — the raw vector (the default, §6.2)."""
        return cls(TransformKind.NONE)

    @classmethod
    def rank(cls) -> Transform:
        """Ordinal 1-based rank, ascending by value, ties broken by ``company_id``."""
        return cls(TransformKind.RANK)

    @classmethod
    def zscore(cls) -> Transform:
        """Population z-score ``(x - mean) / stdev`` (population standard deviation)."""
        return cls(TransformKind.ZSCORE)

    @classmethod
    def minmax(cls) -> Transform:
        """Min-max scaling of the population to ``[0, 1]``."""
        return cls(TransformKind.MINMAX)

    @classmethod
    def winsorize(cls, lower: str | Decimal, upper: str | Decimal) -> Transform:
        """Clip each value to the ``[lower, upper]`` population percentiles.

        ``lower`` / ``upper`` are fractions in ``[0, 1]`` with ``lower <= upper``
        (e.g. ``"0.05"`` / ``"0.95"``). A malformed bound is a configuration bug,
        surfaced as :class:`FactorConfigurationError`.
        """
        lo, hi = Decimal(lower), Decimal(upper)
        if not (Decimal(0) <= lo <= hi <= Decimal(1)):
            raise FactorConfigurationError(
                f"winsorize percentiles must satisfy 0 <= lower <= upper <= 1; "
                f"got lower={lo}, upper={hi}"
            )
        return cls(TransformKind.WINSORIZE, lower=lo, upper=hi)

    @property
    def transform_id(self) -> str:
        """The canonical id hashed into ``factor_definition_id`` (§7)."""
        if self.kind is TransformKind.WINSORIZE:
            assert self.lower is not None and self.upper is not None
            return (
                f"{self.kind.value}:"
                f"{canonical_decimal_str(self.lower)}:"
                f"{canonical_decimal_str(self.upper)}"
            )
        return self.kind.value

    # -- application ---------------------------------------------------------

    def apply(
        self, population: dict[str, Decimal], context: Context
    ) -> dict[str, str | None]:
        """Apply this transform to the KNOWN-cell ``population`` (§6.2).

        ``population`` maps ``company_id`` → exact ``Decimal`` value for the KNOWN
        cells only, in universe order (insertion order is preserved for
        determinism). Returns a map ``company_id`` → serialized transformed value,
        or ``None`` for a member the transform leaves undefined (e.g. a degenerate
        population). The pinned ``context`` governs all arithmetic.
        """
        if self.kind is TransformKind.NONE or not population:
            # Identity, or an all-UNDEFINED population: nothing to transform.
            return {member: None for member in population}
        if self.kind is TransformKind.RANK:
            return self._rank(population)
        if self.kind is TransformKind.ZSCORE:
            return self._zscore(population, context)
        if self.kind is TransformKind.MINMAX:
            return self._minmax(population, context)
        if self.kind is TransformKind.WINSORIZE:
            return self._winsorize(population, context)
        # The TransformKind enum is closed; an unknown kind is our bug.
        raise FactorConfigurationError(f"unknown transform kind {self.kind!r}")

    def _rank(self, population: dict[str, Decimal]) -> dict[str, str | None]:
        """Ordinal 1-based rank, ascending by (value, company_id) — a total order."""
        ordered = sorted(population.items(), key=lambda kv: (kv[1], kv[0]))
        return {
            member: canonical_decimal_str(Decimal(position))
            for position, (member, _value) in enumerate(ordered, start=1)
        }

    def _zscore(
        self, population: dict[str, Decimal], context: Context
    ) -> dict[str, str | None]:
        """Population z-score; a zero standard deviation → all cells UNDEFINED.

        Every operation runs inside the pinned ``context`` (via ``localcontext``),
        not the ambient thread context — otherwise the bare ``+``/``-``/``/``/``**``
        would round to the process default (precision 28) while ``context.sqrt`` /
        ``context.divide`` round to 34, so a genuinely degenerate population (e.g. a
        single 34-digit value) would leave a nonzero residual mean and slip past the
        zero-stdev guard instead of failing closed (§6.2).
        """
        with localcontext(context):
            values = list(population.values())
            n = Decimal(len(values))
            mean = sum(values, Decimal(0)) / n
            variance = sum(((v - mean) ** 2 for v in values), Decimal(0)) / n
            stdev = context.sqrt(variance)
            if stdev == 0:
                # Degenerate: every value equals the mean (includes a single cell).
                # Fail closed — a z-score is undefined, never a blow-up (§6.2).
                return {member: None for member in population}
            return {
                member: canonical_decimal_str(context.divide(value - mean, stdev))
                for member, value in population.items()
            }

    def _minmax(
        self, population: dict[str, Decimal], context: Context
    ) -> dict[str, str | None]:
        """Scale the population to ``[0, 1]``; a zero range → all cells UNDEFINED.

        Runs inside the pinned ``context`` (via ``localcontext``) so the bare
        ``-`` computing the span rounds identically to the ``context.divide`` that
        uses it — otherwise a near-degenerate span could round to nonzero under the
        ambient context and slip past the zero-range guard (§6.2).
        """
        with localcontext(context):
            values = list(population.values())
            lo, hi = min(values), max(values)
            span = hi - lo
            if span == 0:
                # Degenerate: all values equal → scaling is undefined (0/0).
                # Fail closed.
                return {member: None for member in population}
            return {
                member: canonical_decimal_str(context.divide(value - lo, span))
                for member, value in population.items()
            }

    def _winsorize(
        self, population: dict[str, Decimal], context: Context
    ) -> dict[str, str | None]:
        """Clip each value to the ``[lower, upper]`` population percentiles (§6.2)."""
        assert self.lower is not None and self.upper is not None
        with localcontext(context):
            ordered = sorted(population.values())
            lo_bound = _percentile(ordered, self.lower, context)
            hi_bound = _percentile(ordered, self.upper, context)
            clipped: dict[str, str | None] = {}
            for member, value in population.items():
                bounded = value
                if bounded < lo_bound:
                    bounded = lo_bound
                elif bounded > hi_bound:
                    bounded = hi_bound
                clipped[member] = canonical_decimal_str(bounded)
        return clipped


def _percentile(ordered: list[Decimal], fraction: Decimal, context: Context) -> Decimal:
    """The ``fraction`` percentile of a sorted ``Decimal`` list (linear interpolation).

    Uses the standard ``index = fraction * (n - 1)`` position with linear
    interpolation between the two nearest ranks — deterministic and exact under the
    pinned ``context``. ``ordered`` is assumed non-empty and ascending.
    """
    n = len(ordered)
    if n == 1:
        return ordered[0]
    position = context.multiply(fraction, Decimal(n - 1))
    lower_index = int(position)  # floor toward zero; position is >= 0
    if lower_index >= n - 1:
        return ordered[n - 1]
    frac = position - Decimal(lower_index)
    low = ordered[lower_index]
    high = ordered[lower_index + 1]
    return low + context.multiply(frac, high - low)
