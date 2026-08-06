"""OpenFinance: reproducible, point-in-time financial research infrastructure.

The public API is intentionally small. The front door is :class:`Company`::

    from openfinance import Company

    apple = Company.resolve("AAPL")
    for filing in apple.filings():
        print(filing.form, filing.filing_date)
    facts = apple.facts()

``Company`` is a thin façade over the deterministic, provenance-first layers
(acquisition → registry → raw XBRL → canonical facts → point-in-time); it adds no
data model of its own. The point-in-time result types (:class:`PitValue` /
:class:`RevisedValue`) are re-exported so the PIT-vs-revised distinction is
visible at the import site; they remain defined in the availability layer.
"""

from __future__ import annotations

from openfinance.availability.resolve import PitValue, RevisedValue
from openfinance.company import Company
from openfinance.identity.model import CompanyIdentity
from openfinance.workspace import Workspace

__all__ = [
    "Company",
    "CompanyIdentity",
    "PitValue",
    "RevisedValue",
    "Workspace",
    "__version__",
]

__version__ = "0.0.0"
