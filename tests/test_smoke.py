"""Smoke tests for the foundational package.

These verify only that the package is importable and exposes a version. They
will grow as real functionality lands.
"""

from __future__ import annotations

import openfinance


def test_package_imports() -> None:
    assert openfinance is not None


def test_version_is_exposed() -> None:
    assert isinstance(openfinance.__version__, str)
    assert openfinance.__version__
