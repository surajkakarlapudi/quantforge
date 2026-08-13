"""Phase 30 reuses Phase 25's method vocabulary verbatim (CM-5/CM-6)."""

from __future__ import annotations

from quantforge import campaignmult as cm
from quantforge import multiplicity as mp


def test_vocabulary_is_the_same_objects_as_multiplicity() -> None:
    # Re-export, not a parallel declaration: identity, not just equality.
    assert cm.CorrectionMethod is mp.CorrectionMethod
    assert cm.ErrorRate is mp.ErrorRate
    assert cm.DependenceAssumption is mp.DependenceAssumption
    assert cm.method_error_rate is mp.method_error_rate
    assert cm.method_dependence is mp.method_dependence


def test_error_rate_labels() -> None:
    er = cm.ErrorRate
    m = cm.CorrectionMethod
    assert cm.method_error_rate(m.BONFERRONI) is er.FAMILY_WISE
    assert cm.method_error_rate(m.HOLM) is er.FAMILY_WISE
    assert cm.method_error_rate(m.BENJAMINI_HOCHBERG) is er.FALSE_DISCOVERY
    assert cm.method_error_rate(m.BENJAMINI_YEKUTIELI) is er.FALSE_DISCOVERY


def test_dependence_labels_flag_bh_as_independence_or_prds() -> None:
    dep = cm.DependenceAssumption
    m = cm.CorrectionMethod
    assert cm.method_dependence(m.BONFERRONI) is dep.ARBITRARY
    assert cm.method_dependence(m.HOLM) is dep.ARBITRARY
    assert cm.method_dependence(m.BENJAMINI_YEKUTIELI) is dep.ARBITRARY
    # The only method whose guarantee assumes independence / PRDS (CM-6).
    assert cm.method_dependence(m.BENJAMINI_HOCHBERG) is dep.INDEPENDENCE_OR_PRDS
