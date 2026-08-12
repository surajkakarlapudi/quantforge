"""Smoke tests for the foundational package.

These verify only that the package is importable and exposes a version. They
will grow as real functionality lands.
"""

from __future__ import annotations

import quantforge


def test_package_imports() -> None:
    assert quantforge is not None


def test_version_is_exposed() -> None:
    assert isinstance(quantforge.__version__, str)
    assert quantforge.__version__


def test_crosssection_public_api_is_exported() -> None:
    # The Phase 18 request/result types are top-level; the engine is reached via the
    # Workspace, not re-exported here.
    assert quantforge.CrossSectionalRegressionSpecification is not None
    assert quantforge.CrossSectionalRegression is not None
    assert quantforge.FactorSpec is not None


def test_factorportfolio_public_api_is_exported() -> None:
    # The Phase 19 request/result types are top-level; the engine is reached via the
    # Workspace, not re-exported here.
    assert quantforge.FactorPortfolioSpecification is not None
    assert quantforge.FactorPortfolio is not None


def test_factorrisk_public_api_is_exported() -> None:
    # The Phase 20 request/result types are top-level; the engine is reached via the
    # Workspace, not re-exported here.
    assert quantforge.FactorRiskSpecification is not None
    assert quantforge.FactorRiskModel is not None


def test_optimization_public_api_is_exported() -> None:
    # The Phase 21 request/result types are top-level; the engine is reached via the
    # Workspace, not re-exported here.
    assert quantforge.PortfolioOptimizationSpecification is not None
    assert quantforge.PortfolioOptimization is not None


def test_walkforward_public_api_is_exported() -> None:
    # The Phase 22 request/result types are top-level; the engine is reached via the
    # Workspace, not re-exported here.
    assert quantforge.WalkForwardEvaluationSpecification is not None
    assert quantforge.WalkForwardEvaluation is not None


def test_campaign_public_api_is_exported() -> None:
    # The Phase 23 request/result types are top-level; the engine is reached via the
    # Workspace, not re-exported here.
    assert quantforge.ResearchCampaignSpecification is not None
    assert quantforge.ResearchCampaignEvaluation is not None


def test_comparison_public_api_is_exported() -> None:
    # The Phase 24 request/result types are top-level; the engine is reached via the
    # Workspace, not re-exported here.
    assert quantforge.StrategyComparisonSpecification is not None
    assert quantforge.StrategyComparison is not None


def test_multiplicity_public_api_is_exported() -> None:
    # The Phase 25 request/result types are top-level; the engine is reached via the
    # Workspace, not re-exported here.
    assert quantforge.MultipleComparisonSpecification is not None
    assert quantforge.MultipleComparisonCorrection is not None
