"""Pure, deterministic cross-sectional statistic functions (§4).

Everything Phase 16 computes, in stdlib :class:`~decimal.Decimal` under the engine's
pinned context — no numpy, no float, no wall-clock, no RNG (Principle 10). The inputs
are per-date parallel vectors of ``(company_id, signal_string, forward_return_string)``
for
the eligible members; every statistic is a pure function of those, so identical inputs
reproduce identical strings on any machine.

These functions read no store and hold no state; the engine resolves the PIT signal and
the realized forward returns and hands their vectors here. A statistic that is genuinely
undefined for the data (fewer than two pairs, a zero denominator, an empty bucket, no
valid dates) is returned as a first-class UNDEFINED
:class:`~quantforge.diagnostics.model.StatValue` with a reason — **never** a
divide-by-zero, a fabricated ``0``, a ``NaN``/``Inf``, or a silent omission (§7, D11).

**Pinned formula methods** (folded into ``diagnostics-stats/1``; changing one bumps
:class:`~quantforge.diagnostics.version.SignalDiagnosticsEngineVersion`):

* **Population moments** (matching ``analytics/compute.py``): ``cov = Σ(x-x̄)(y-ȳ)/n``,
  ``pstd = √(Σ(x-x̄)²/n)``.
* **Pearson IC** ``= cov(x, y) / (pstd(x)·pstd(y))``; a zero signal / return dispersion
  is ``ZERO_SIGNAL_VARIANCE`` / ``ZERO_RETURN_VARIANCE``, never divided.
* **Spearman IC** is the Pearson IC of the **average-rank** vectors: tied values receive
  the average of their contiguous ``1..n`` positions.
* **Quantile buckets** order members by (signal ascending, then ``company_id``); the
  member at ``0``-based ordinal ``i`` is assigned ``bucket = floor(i·q/n)`` (clamped to
  ``q-1``). Each non-empty bucket's cell is the mean forward return of its members; an
  empty bucket is ``EMPTY_BUCKET``. The **top-minus-bottom spread** is bucket ``q-1``
  minus bucket ``0``.
* **IC summary** over the dates a method's IC is KNOWN: ``mean_ic``; ``ic_std`` (pop);
  ``ic_information_ratio = mean_ic/ic_std`` (per period); ``ic_t_stat =
  mean_ic/ic_std·√n``; ``hit_rate = #(IC>0)/n``.
"""

from __future__ import annotations

from decimal import Context, Decimal, InvalidOperation, localcontext

from quantforge.diagnostics.errors import SignalDiagnosticsConfigurationError
from quantforge.diagnostics.model import DiagnosticUndefinedReason, StatValue

__all__ = [
    "forward_return",
    "ic_summary",
    "pearson_ic",
    "quantile_buckets",
    "quantile_profile",
    "rank_ic",
    "top_minus_bottom",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)


# -- parsing -----------------------------------------------------------------


def _parse_decimal(raw: str, *, what: str) -> Decimal:
    """Parse one finite :class:`~decimal.Decimal` (fail closed).

    A non-decimal or non-finite element is a corrupt corpus value and raises
    :class:`SignalDiagnosticsConfigurationError` rather than being guessed.
    """
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise SignalDiagnosticsConfigurationError(
            f"{what} {raw!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise SignalDiagnosticsConfigurationError(f"{what} {raw!r} must be finite")
    return +value


def forward_return(base_price: str, end_price: str, *, context: Context) -> str | None:
    """The realized forward return ``end/base - 1`` as a canonical string (§4).

    Both prices are PIT-gated adjusted closes read at the window-end ``as_of``. Returns
    ``None`` when the base price is non-positive (no meaningful return can be formed) —
    the engine then drops the member for return (SD-4). A non-finite or non-decimal
    price is a corrupt corpus value and raises.
    """
    with localcontext(context):
        base = _parse_decimal(base_price, what="adjusted price")
        end = _parse_decimal(end_price, what="adjusted price")
        if base <= _ZERO:
            return None
        return str(+((end / base) - _ONE))


# -- small population-moment helpers (run inside an active localcontext) ------


def _mean(xs: list[Decimal]) -> Decimal:
    return sum(xs, _ZERO) / Decimal(len(xs))


def _pvariance(xs: list[Decimal], mean: Decimal) -> Decimal:
    n = Decimal(len(xs))
    return sum(((x - mean) * (x - mean) for x in xs), _ZERO) / n


def _pstd(xs: list[Decimal], mean: Decimal, *, context: Context) -> Decimal:
    return _pvariance(xs, mean).sqrt(context)


def _covariance(
    xs: list[Decimal], ys: list[Decimal], mx: Decimal, my: Decimal
) -> Decimal:
    n = Decimal(len(xs))
    return sum(((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)), _ZERO) / n


def _known(value: Decimal) -> StatValue:
    """A KNOWN cell holding the canonical string form of ``value`` (under context)."""
    return StatValue.known(str(+value))


def _undef(reason: DiagnosticUndefinedReason) -> StatValue:
    return StatValue.undefined(reason)


def _average_ranks(values: list[Decimal]) -> list[Decimal]:
    """Average (fractional) ranks over ``1..n``; ties share the mean of their positions.

    Deterministic: values are ranked by magnitude, and equal values receive the average
    of the contiguous positions they occupy, so the rank vector never depends on input
    order among ties.
    """
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [_ZERO] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        # positions i..j (0-based) => ranks (i+1)..(j+1); average of the block
        block_sum = sum(range(i + 1, j + 2))
        avg = Decimal(block_sum) / Decimal(j - i + 1)
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


# -- Information Coefficient -------------------------------------------------


def _pearson(xs: list[Decimal], ys: list[Decimal], *, context: Context) -> StatValue:
    """Population Pearson correlation of two equal-length vectors (fail-closed
    reasons)."""
    mx = _mean(xs)
    my = _mean(ys)
    sx = _pstd(xs, mx, context=context)
    sy = _pstd(ys, my, context=context)
    if sx == _ZERO:
        return _undef(DiagnosticUndefinedReason.ZERO_SIGNAL_VARIANCE)
    if sy == _ZERO:
        return _undef(DiagnosticUndefinedReason.ZERO_RETURN_VARIANCE)
    cov = _covariance(xs, ys, mx, my)
    return _known(cov / (sx * sy))


def pearson_ic(
    signals: list[str], returns: list[str], *, context: Context
) -> StatValue:
    """Pearson IC between the raw signal and forward-return vectors (§4).

    Fewer than two pairs → ``INSUFFICIENT_PAIRS``; a constant signal → ``ZERO_SIGNAL_
    VARIANCE``; a constant forward-return series → ``ZERO_RETURN_VARIANCE``. Never a
    divide-by-zero.
    """
    if len(signals) != len(returns):
        raise SignalDiagnosticsConfigurationError(
            "signal and return vectors must be the same length"
        )
    if len(signals) < 2:
        return _undef(DiagnosticUndefinedReason.INSUFFICIENT_PAIRS)
    with localcontext(context):
        xs = [_parse_decimal(s, what="signal") for s in signals]
        ys = [_parse_decimal(r, what="forward return") for r in returns]
        return _pearson(xs, ys, context=context)


def rank_ic(signals: list[str], returns: list[str], *, context: Context) -> StatValue:
    """Spearman rank IC — Pearson of the average-rank vectors (§4).

    Fewer than two pairs → ``INSUFFICIENT_PAIRS``; a fully constant signal (all ranks
    equal) → ``ZERO_SIGNAL_VARIANCE``; a fully constant forward-return series →
    ``ZERO_RETURN_VARIANCE``. Ties use average ranks, deterministically.
    """
    if len(signals) != len(returns):
        raise SignalDiagnosticsConfigurationError(
            "signal and return vectors must be the same length"
        )
    if len(signals) < 2:
        return _undef(DiagnosticUndefinedReason.INSUFFICIENT_PAIRS)
    with localcontext(context):
        xs = [_parse_decimal(s, what="signal") for s in signals]
        ys = [_parse_decimal(r, what="forward return") for r in returns]
        rank_x = _average_ranks(xs)
        rank_y = _average_ranks(ys)
        return _pearson(rank_x, rank_y, context=context)


# -- quantile buckets --------------------------------------------------------


def quantile_buckets(
    members: list[tuple[str, str, str]], quantiles: int, *, context: Context
) -> tuple[StatValue, ...]:
    """Mean forward return per quantile bucket (§4).

    ``members`` is the eligible list of ``(company_id, signal_string,
    forward_return_string)``. Members are ordered by (signal ascending, then
    ``company_id``); the member at ``0``-based ordinal ``i`` is assigned
    ``bucket = floor(i·q/n)`` (clamped to ``q-1``). Each bucket's cell is the mean
    forward return of its members; an empty bucket → ``EMPTY_BUCKET``. Returns ``q``
    cells,
    bucket ``0`` .. ``q-1``.
    """
    with localcontext(context):
        n = len(members)
        if n == 0:
            return tuple(
                _undef(DiagnosticUndefinedReason.EMPTY_BUCKET) for _ in range(quantiles)
            )
        parsed = [
            (
                cid,
                _parse_decimal(sig, what="signal"),
                _parse_decimal(ret, what="forward return"),
            )
            for cid, sig, ret in members
        ]
        ordered = sorted(parsed, key=lambda t: (t[1], t[0]))
        buckets: list[list[Decimal]] = [[] for _ in range(quantiles)]
        for i, (_cid, _sig, ret) in enumerate(ordered):
            b = (i * quantiles) // n
            if b >= quantiles:
                b = quantiles - 1
            buckets[b].append(ret)
        cells: list[StatValue] = []
        for bucket in buckets:
            if not bucket:
                cells.append(_undef(DiagnosticUndefinedReason.EMPTY_BUCKET))
            else:
                cells.append(_known(_mean(bucket)))
        return tuple(cells)


def top_minus_bottom(
    bucket_means: tuple[StatValue, ...], *, context: Context
) -> StatValue:
    """Bucket ``q-1`` mean minus bucket ``0`` mean (§4).

    ``EMPTY_BUCKET`` when either endpoint bucket is undefined (there is no spread to
    form).
    """
    if len(bucket_means) < 2:
        return _undef(DiagnosticUndefinedReason.EMPTY_BUCKET)
    bottom = bucket_means[0]
    top = bucket_means[-1]
    if bottom.value is None or top.value is None:
        return _undef(DiagnosticUndefinedReason.EMPTY_BUCKET)
    with localcontext(context):
        return _known(Decimal(top.value) - Decimal(bottom.value))


def quantile_profile(
    per_date_bucket_means: list[tuple[StatValue, ...]],
    per_date_spreads: list[StatValue],
    quantiles: int,
    *,
    context: Context,
) -> tuple[tuple[StatValue, ...], StatValue]:
    """Across-date mean per bucket + mean spread (§4).

    For each bucket, average the per-date KNOWN means (dates where the bucket was
    ``EMPTY_BUCKET`` are excluded); a bucket KNOWN on no date → ``EMPTY_BUCKET``. The
    mean spread averages the per-date KNOWN spreads; none KNOWN → ``NO_VALID_DATES``.
    """
    with localcontext(context):
        bucket_cells: list[StatValue] = []
        for b in range(quantiles):
            known_vals: list[Decimal] = []
            for row in per_date_bucket_means:
                if b >= len(row):
                    continue
                cell_value = row[b].value
                if cell_value is not None:
                    known_vals.append(Decimal(cell_value))
            if not known_vals:
                bucket_cells.append(_undef(DiagnosticUndefinedReason.EMPTY_BUCKET))
            else:
                bucket_cells.append(_known(_mean(known_vals)))
        known_spreads = [
            Decimal(s.value) for s in per_date_spreads if s.value is not None
        ]
        if not known_spreads:
            mean_spread = _undef(DiagnosticUndefinedReason.NO_VALID_DATES)
        else:
            mean_spread = _known(_mean(known_spreads))
        return tuple(bucket_cells), mean_spread


# -- IC summary --------------------------------------------------------------


def ic_summary(
    per_date_ic: list[StatValue], *, context: Context
) -> tuple[StatValue, StatValue, StatValue, StatValue, StatValue, int]:
    """Summarise one method's per-date IC series (§4).

    Returns ``(mean_ic, ic_std, ic_information_ratio, ic_t_stat, hit_rate,
    n_valid_dates)``. Over the dates the IC is KNOWN: ``mean_ic``; ``ic_std``
    (population); ``ic_information_ratio = mean_ic/ic_std`` (per period, no
    annualisation); ``ic_t_stat = mean_ic/ic_std·√n``; ``hit_rate = #(IC>0)/n``. Zero
    KNOWN dates → every cell ``NO_VALID_DATES``. A zero-dispersion IC series → the
    ratio/t-stat are ``ZERO_RETURN_VARIANCE`` (a constant IC series has no dispersion to
    divide by), never a divide-by-zero.
    """
    known = [Decimal(v.value) for v in per_date_ic if v.value is not None]
    n_valid = len(known)
    if n_valid == 0:
        undef = _undef(DiagnosticUndefinedReason.NO_VALID_DATES)
        return (undef, undef, undef, undef, undef, 0)
    with localcontext(context):
        mean = _mean(known)
        std = _pstd(known, mean, context=context)
        mean_cell = _known(mean)
        std_cell = _known(std)
        positive = sum(1 for x in known if x > _ZERO)
        hit_rate = _known(Decimal(positive) / Decimal(n_valid))
        if std == _ZERO:
            ratio = _undef(DiagnosticUndefinedReason.ZERO_RETURN_VARIANCE)
            t_stat = _undef(DiagnosticUndefinedReason.ZERO_RETURN_VARIANCE)
        else:
            ir = mean / std
            ratio = _known(ir)
            t_stat = _known(ir * Decimal(n_valid).sqrt(context))
        return (mean_cell, std_cell, ratio, t_stat, hit_rate, n_valid)
