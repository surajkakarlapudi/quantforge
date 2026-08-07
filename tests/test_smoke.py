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
