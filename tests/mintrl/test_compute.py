"""The pure minimum-track-record-length arithmetic (§11, §12, MT-3/MT-4/MT-5).

Exact-arithmetic checks of the per-trial MinTRL formula (recomputed independently
against the same pinned primitives), the two per-trial UNDEFINED guards
(``SHARPE_NOT_ABOVE_BENCHMARK`` / ``DEGENERATE_SHARPE_ESTIMATOR``), the sufficiency test
and excess length, the aggregate statistics, the empty-family guard (MT-3), the
below-floor UNDEFINED status (MT-5), and determinism. Also the PSR-inverse identity:
feeding the computed MinTRL back through the argument of Phase 23's PSR recovers
``Z_alpha``.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from quantforge._stats.normal import standard_normal_ppf
from quantforge.mintrl.compute import EvaluableTrial, evaluate_mintrl
from quantforge.mintrl.model import (
    MinTrlStatus,
    MinTrlUndefinedReason,
    StatStatus,
)
from quantforge.mintrl.version import default_decimal_context

CTX = default_decimal_context()

_ONE = Decimal(1)
_FOUR = Decimal(4)


def _trial(
    label: str, *, n: int, sharpe: str, skew: str, kurtosis: str
) -> EvaluableTrial:
    return EvaluableTrial(
        label=label,
        n=n,
        sharpe=Decimal(sharpe),
        skew=Decimal(skew),
        kurtosis=Decimal(kurtosis),
    )


def _expected_min_trl(
    *, sharpe: str, skew: str, kurtosis: str, benchmark: str, confidence: str
) -> Decimal:
    """Recompute MinTRL independently under the same context + normal primitive."""
    sr = Decimal(sharpe)
    g3 = Decimal(skew)
    g4 = Decimal(kurtosis)
    bm = Decimal(benchmark)
    with localcontext(CTX):
        z = standard_normal_ppf(Decimal(confidence), context=CTX)
        v = _ONE - g3 * sr + ((g4 - _ONE) / _FOUR) * sr * sr
        ratio = z / (sr - bm)
        return +(_ONE + v * ratio * ratio)


# -- per-trial formula (exact recompute) -------------------------------------


def test_min_trl_matches_independent_recompute() -> None:
    out = evaluate_mintrl(
        [_trial("trial_1", n=100, sharpe="0.5", skew="0", kurtosis="3")],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=1,
        context=CTX,
    )
    (cell,) = out.trials
    expected = _expected_min_trl(
        sharpe="0.5", skew="0", kurtosis="3", benchmark="0", confidence="0.95"
    )
    assert cell.min_trl.value == str(expected)
    # excess = observed - MinTRL; n=100 dwarfs a ~13-period MinTRL, so it is sufficient.
    with localcontext(CTX):
        expected_excess = str(+(Decimal(100) - expected))
    assert cell.excess_length.value == expected_excess


def test_moments_carried_verbatim() -> None:
    # MT-4: the sealed moment strings are carried through unchanged (canonicalized).
    out = evaluate_mintrl(
        [_trial("trial_1", n=10, sharpe="0.50", skew="0.0", kurtosis="3.00")],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=1,
        context=CTX,
    )
    (cell,) = out.trials
    # Canonical inputs are carried through unchanged (canonicalized via str(+value)).
    assert (cell.sharpe, cell.skew, cell.kurtosis) == ("0.50", "0.0", "3.00")


# -- PSR-inverse identity ----------------------------------------------------


def test_psr_argument_recovers_z_alpha() -> None:
    # MinTRL - 1 = V·(Z/(SR-SR*))², so (SR-SR*)·√(MinTRL-1)/√V = Z_alpha exactly-ish.
    sharpe, skew, kurtosis, benchmark, confidence = "0.4", "0", "3", "0", "0.9"
    out = evaluate_mintrl(
        [_trial("trial_1", n=10, sharpe=sharpe, skew=skew, kurtosis=kurtosis)],
        confidence=Decimal(confidence),
        benchmark=Decimal(benchmark),
        min_determined=1,
        context=CTX,
    )
    (cell,) = out.trials
    assert cell.min_trl.value is not None
    with localcontext(CTX):
        z = standard_normal_ppf(Decimal(confidence), context=CTX)
        sr = Decimal(sharpe)
        v = _ONE - Decimal(skew) * sr + ((Decimal(kurtosis) - _ONE) / _FOUR) * sr * sr
        min_trl = Decimal(cell.min_trl.value)
        argument = (sr - Decimal(benchmark)) * (min_trl - _ONE).sqrt(CTX) / v.sqrt(CTX)
    # Round both to a tolerance well inside prec-34 to absorb the √(square) rounding.
    assert argument.quantize(Decimal("1.000000000000000000")) == z.quantize(
        Decimal("1.000000000000000000")
    )


# -- per-trial UNDEFINED guards ----------------------------------------------


def test_sharpe_not_above_benchmark_is_undefined() -> None:
    out = evaluate_mintrl(
        [
            _trial("trial_1", n=10, sharpe="0.2", skew="0", kurtosis="3"),
            _trial("trial_2", n=10, sharpe="0.2", skew="0", kurtosis="3"),
        ],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0.2"),  # SR == benchmark: no finite record suffices
        min_determined=2,
        context=CTX,
    )
    for cell in out.trials:
        assert cell.min_trl.status is StatStatus.UNDEFINED
        assert cell.min_trl.reason is MinTrlUndefinedReason.SHARPE_NOT_ABOVE_BENCHMARK
        # The excess inherits the same reason - never coerced to a number.
        assert cell.excess_length.reason is (
            MinTrlUndefinedReason.SHARPE_NOT_ABOVE_BENCHMARK
        )
    assert out.summary.mintrl_status is MinTrlStatus.UNDEFINED
    assert (
        out.summary.status_reason
        is MinTrlUndefinedReason.INSUFFICIENT_DETERMINED_TRIALS
    )


def test_below_benchmark_is_undefined() -> None:
    out = evaluate_mintrl(
        [_trial("trial_1", n=10, sharpe="0.1", skew="0", kurtosis="3")],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0.5"),  # SR < benchmark
        min_determined=1,
        context=CTX,
    )
    (cell,) = out.trials
    assert cell.min_trl.reason is MinTrlUndefinedReason.SHARPE_NOT_ABOVE_BENCHMARK


def test_degenerate_estimator_is_undefined() -> None:
    # V = 1 - 3·1 + ((1-1)/4)·1 = -2 ≤ 0 → degenerate, checked before the benchmark.
    out = evaluate_mintrl(
        [_trial("trial_1", n=10, sharpe="1", skew="3", kurtosis="1")],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=1,
        context=CTX,
    )
    (cell,) = out.trials
    assert cell.min_trl.status is StatStatus.UNDEFINED
    assert cell.min_trl.reason is MinTrlUndefinedReason.DEGENERATE_SHARPE_ESTIMATOR
    assert cell.excess_length.reason is (
        MinTrlUndefinedReason.DEGENERATE_SHARPE_ESTIMATOR
    )


# -- sufficiency -------------------------------------------------------------


def test_sufficiency_frequency_counts_records_meeting_min_trl() -> None:
    # A huge-n trial is sufficient; a tiny-n trial with the same MinTRL is not.
    out = evaluate_mintrl(
        [
            _trial("trial_1", n=100000, sharpe="0.5", skew="0", kurtosis="3"),
            _trial("trial_2", n=3, sharpe="0.5", skew="0", kurtosis="3"),
        ],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=2,
        context=CTX,
    )
    long, short = out.trials
    assert long.excess_length.value is not None
    assert short.excess_length.value is not None
    assert Decimal(long.excess_length.value) > 0  # observed exceeds MinTRL
    assert Decimal(short.excess_length.value) < 0  # observed short of MinTRL
    assert out.summary.sufficient_frequency.value == "0.5"


# -- aggregates --------------------------------------------------------------


def test_aggregates_over_determined_family() -> None:
    out = evaluate_mintrl(
        [
            _trial("trial_1", n=10, sharpe="0.5", skew="0", kurtosis="3"),
            _trial("trial_2", n=10, sharpe="0.3", skew="0", kurtosis="3"),
        ],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=2,
        context=CTX,
    )
    a = _expected_min_trl(
        sharpe="0.5", skew="0", kurtosis="3", benchmark="0", confidence="0.95"
    )
    b = _expected_min_trl(
        sharpe="0.3", skew="0", kurtosis="3", benchmark="0", confidence="0.95"
    )
    s = out.summary
    assert s.mintrl_status is MinTrlStatus.EVALUATED
    assert s.n_determined == 2
    with localcontext(CTX):
        mean = +((a + b) / 2)
        disp = +((((a - mean) ** 2 + (b - mean) ** 2) / 2).sqrt())
        mean_str, disp_str = str(mean), str(disp)
    assert s.mean_min_trl.value == mean_str
    assert s.min_trl_dispersion.value == disp_str
    assert s.max_min_trl.value == str(max(a, b))
    assert s.min_min_trl.value == str(min(a, b))


# -- empty family (MT-3) -----------------------------------------------------


def test_empty_family_is_all_undefined_never_divides() -> None:
    out = evaluate_mintrl(
        [],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=2,
        context=CTX,
    )
    assert out.trials == ()
    s = out.summary
    for cell in (
        s.mean_min_trl,
        s.min_trl_dispersion,
        s.max_min_trl,
        s.min_min_trl,
        s.sufficient_frequency,
    ):
        assert cell.status is StatStatus.UNDEFINED
        assert cell.reason is MinTrlUndefinedReason.NO_DETERMINED_TRIALS
    assert s.n_determined == 0
    assert s.mintrl_status is MinTrlStatus.UNDEFINED
    assert s.status_reason is MinTrlUndefinedReason.INSUFFICIENT_DETERMINED_TRIALS


def test_all_undefined_trials_yield_no_determined() -> None:
    # Two trials both below benchmark → determined family is empty.
    out = evaluate_mintrl(
        [
            _trial("trial_1", n=10, sharpe="0.1", skew="0", kurtosis="3"),
            _trial("trial_2", n=10, sharpe="0.1", skew="0", kurtosis="3"),
        ],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0.5"),
        min_determined=2,
        context=CTX,
    )
    assert out.summary.n_determined == 0
    assert out.summary.mean_min_trl.reason is (
        MinTrlUndefinedReason.NO_DETERMINED_TRIALS
    )


# -- floor / status (MT-5) ---------------------------------------------------


def test_single_determined_below_floor_is_undefined_status() -> None:
    out = evaluate_mintrl(
        [_trial("trial_1", n=10, sharpe="0.5", skew="0", kurtosis="3")],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=2,
        context=CTX,
    )
    s = out.summary
    # The one per-trial MinTRL still seals KNOWN, but the roll-up status is UNDEFINED.
    assert out.trials[0].min_trl.status is StatStatus.KNOWN
    assert s.n_determined == 1
    assert s.mintrl_status is MinTrlStatus.UNDEFINED
    assert s.status_reason is MinTrlUndefinedReason.INSUFFICIENT_DETERMINED_TRIALS
    # The aggregate over the single determined trial is still KNOWN.
    assert s.mean_min_trl.status is StatStatus.KNOWN
    assert s.min_trl_dispersion.value == "0"


def test_single_determined_at_floor_one_is_evaluated() -> None:
    out = evaluate_mintrl(
        [_trial("trial_1", n=10, sharpe="0.5", skew="0", kurtosis="3")],
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=1,
        context=CTX,
    )
    assert out.summary.mintrl_status is MinTrlStatus.EVALUATED
    assert out.summary.status_reason is None


# -- determinism -------------------------------------------------------------


def test_repeated_calls_are_byte_identical() -> None:
    trials = [
        _trial("trial_1", n=10, sharpe="0.5", skew="0.1", kurtosis="3.5"),
        _trial("trial_2", n=20, sharpe="0.3", skew="-0.2", kurtosis="4"),
    ]
    first = evaluate_mintrl(
        trials,
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=2,
        context=CTX,
    )
    second = evaluate_mintrl(
        trials,
        confidence=Decimal("0.95"),
        benchmark=Decimal("0"),
        min_determined=2,
        context=CTX,
    )
    assert [c.min_trl.value for c in first.trials] == [
        c.min_trl.value for c in second.trials
    ]
    assert first.summary.mean_min_trl.value == second.summary.mean_min_trl.value
    assert (
        first.summary.min_trl_dispersion.value
        == second.summary.min_trl_dispersion.value
    )
