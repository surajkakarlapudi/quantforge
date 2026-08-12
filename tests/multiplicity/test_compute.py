"""The pure multiplicity-correction procedures (§11, §12, MC-3/MC-4/MC-5).

Exact-arithmetic hand-calculations, ordering / monotonicity / capping invariants, the
tie rule (MC-4), the uniform ``p_adj <= alpha`` rejection rule (MC-5), and the
empty-family guard (MC-3).
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.multiplicity.compute import correct_family
from quantforge.multiplicity.model import CorrectionMethod
from quantforge.multiplicity.version import default_decimal_context

CTX = default_decimal_context()
ALL_METHODS = (
    CorrectionMethod.BONFERRONI,
    CorrectionMethod.HOLM,
    CorrectionMethod.BENJAMINI_HOCHBERG,
    CorrectionMethod.BENJAMINI_YEKUTIELI,
)


def _p(values: list[str]) -> list[Decimal]:
    return [Decimal(v) for v in values]


def _by_method(
    p_values: list[str], methods: tuple[CorrectionMethod, ...], alpha: str
) -> dict[CorrectionMethod, tuple[tuple[Decimal, ...], tuple[bool, ...]]]:
    out = correct_family(_p(p_values), methods, Decimal(alpha), context=CTX)
    return {c.method: (c.adjusted, c.rejected) for c in out}


# -- hand-calculations (m = 2, exact) ----------------------------------------


def test_hand_calc_two_hypotheses() -> None:
    # p = (0.01, 0.04), alpha = 0.05. All multipliers (2/1, 2/2) and c(2)=3/2 are exact.
    res = _by_method(["0.01", "0.04"], ALL_METHODS, "0.05")

    bonf_adj, bonf_rej = res[CorrectionMethod.BONFERRONI]
    assert [Decimal("0.02"), Decimal("0.08")] == list(bonf_adj)
    assert bonf_rej == (True, False)

    holm_adj, holm_rej = res[CorrectionMethod.HOLM]
    assert [Decimal("0.02"), Decimal("0.04")] == list(holm_adj)
    assert holm_rej == (True, True)

    bh_adj, bh_rej = res[CorrectionMethod.BENJAMINI_HOCHBERG]
    assert [Decimal("0.02"), Decimal("0.04")] == list(bh_adj)
    assert bh_rej == (True, True)

    # Benjamini-Yekutieli: BH scaled by c(2) = 3/2.
    by_adj, by_rej = res[CorrectionMethod.BENJAMINI_YEKUTIELI]
    assert [Decimal("0.03"), Decimal("0.06")] == list(by_adj)
    assert by_rej == (True, False)


def test_bonferroni_caps_at_one() -> None:
    # 4 hypotheses, a large p: 4 * 0.5 = 2.0 -> capped at 1.
    res = _by_method(
        ["0.5", "0.01", "0.02", "0.03"], (CorrectionMethod.BONFERRONI,), "0.05"
    )
    adj, _ = res[CorrectionMethod.BONFERRONI]
    assert adj[0] == Decimal("1")
    assert all(v <= Decimal("1") for v in adj)


def test_ties_receive_identical_adjusted_values() -> None:
    # Equal p values must collapse to one shared adjusted value under every method
    # (MC-4).
    for method in ALL_METHODS:
        adj, _ = _by_method(["0.02", "0.02"], (method,), "0.05")[method]
        assert adj[0] == adj[1], method


def test_duplicate_p_across_larger_family_is_identical() -> None:
    # Three equal p values -> three identical adjusted values under every method.
    for method in ALL_METHODS:
        adj, _ = _by_method(["0.03", "0.03", "0.03"], (method,), "0.05")[method]
        assert adj[0] == adj[1] == adj[2], method


def test_adjusted_maps_back_to_family_order() -> None:
    # p given OUT of sorted order; the adjusted values must return in family order,
    # i.e. the largest p (index 0) gets the largest Holm adjusted value.
    adj, _ = _by_method(["0.04", "0.01"], (CorrectionMethod.HOLM,), "0.05")[
        CorrectionMethod.HOLM
    ]
    # family index 0 has the larger raw p, so it must not be smaller than index 1.
    assert adj[0] >= adj[1]
    assert adj[0] == Decimal("0.04")
    assert adj[1] == Decimal("0.02")


def test_step_procedures_are_monotone_in_sorted_rank() -> None:
    # Adjusted values are non-decreasing along ascending p under every step method.
    p_values = ["0.001", "0.01", "0.02", "0.2", "0.5"]
    for method in ALL_METHODS:
        adj, _ = _by_method(p_values, (method,), "0.05")[method]
        # adj is in family order == ascending p order here, so it must be
        # non-decreasing.
        assert list(adj) == sorted(adj), method


def test_yekutieli_is_never_below_hochberg() -> None:
    # The harmonic penalty c(m) >= 1, so BY adjusted >= BH adjusted cell-for-cell.
    p_values = ["0.001", "0.01", "0.02", "0.2", "0.5"]
    res = _by_method(p_values, ALL_METHODS, "0.05")
    bh, _ = res[CorrectionMethod.BENJAMINI_HOCHBERG]
    by, _ = res[CorrectionMethod.BENJAMINI_YEKUTIELI]
    assert all(y >= b for y, b in zip(by, bh, strict=True))


def test_rejection_is_p_adj_at_or_below_alpha() -> None:
    # Boundary: an adjusted value exactly equal to alpha is rejected (<=, not <).
    # Bonferroni of p=0.025 over m=2 is exactly 0.05 == alpha.
    _, rej = _by_method(["0.025", "0.9"], (CorrectionMethod.BONFERRONI,), "0.05")[
        CorrectionMethod.BONFERRONI
    ]
    assert rej == (True, False)


def test_empty_family_returns_empty_tuples() -> None:
    # m = 0 must never divide by zero; every method yields empty adjusted/rejected
    # (MC-3).
    out = correct_family([], ALL_METHODS, Decimal("0.05"), context=CTX)
    assert len(out) == len(ALL_METHODS)
    for computation in out:
        assert computation.adjusted == ()
        assert computation.rejected == ()


def test_single_hypothesis_is_unchanged() -> None:
    # m = 1: every method leaves the single p value unadjusted (all multipliers are 1).
    for method in ALL_METHODS:
        adj, rej = _by_method(["0.03"], (method,), "0.05")[method]
        assert adj == (Decimal("0.03"),)
        assert rej == (True,)


def test_repeated_calls_are_byte_identical() -> None:
    # Determinism: identical inputs yield identical canonical strings every time.
    p_values = ["0.001", "0.01", "0.02", "0.2", "0.5"]
    first = _by_method(p_values, ALL_METHODS, "0.05")
    second = _by_method(p_values, ALL_METHODS, "0.05")
    for method in ALL_METHODS:
        assert [str(v) for v in first[method][0]] == [str(v) for v in second[method][0]]
