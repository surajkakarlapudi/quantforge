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
