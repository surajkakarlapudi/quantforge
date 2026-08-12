"""The correction-method vocabulary + honest dependence labels (MC-6)."""

from __future__ import annotations

from quantforge.multiplicity.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
    method_dependence,
    method_error_rate,
)


def test_error_rate_labels() -> None:
    assert method_error_rate(CorrectionMethod.BONFERRONI) is ErrorRate.FAMILY_WISE
    assert method_error_rate(CorrectionMethod.HOLM) is ErrorRate.FAMILY_WISE
    assert (
        method_error_rate(CorrectionMethod.BENJAMINI_HOCHBERG)
        is ErrorRate.FALSE_DISCOVERY
    )
    assert (
        method_error_rate(CorrectionMethod.BENJAMINI_YEKUTIELI)
        is ErrorRate.FALSE_DISCOVERY
    )


def test_only_hochberg_assumes_independence() -> None:
    # Bonferroni, Holm, Benjamini-Yekutieli are valid under arbitrary dependence; only
    # Benjamini-Hochberg assumes independence / PRDS (MC-6).
    assert (
        method_dependence(CorrectionMethod.BONFERRONI) is DependenceAssumption.ARBITRARY
    )
    assert method_dependence(CorrectionMethod.HOLM) is DependenceAssumption.ARBITRARY
    assert (
        method_dependence(CorrectionMethod.BENJAMINI_YEKUTIELI)
        is DependenceAssumption.ARBITRARY
    )
    assert (
        method_dependence(CorrectionMethod.BENJAMINI_HOCHBERG)
        is DependenceAssumption.INDEPENDENCE_OR_PRDS
    )


def test_every_method_has_labels() -> None:
    for method in CorrectionMethod:
        assert method_error_rate(method) in ErrorRate
        assert method_dependence(method) in DependenceAssumption
