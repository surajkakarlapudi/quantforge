"""Deterministic exact-``Decimal`` standard-normal CDF Φ and inverse-CDF Z⁻¹ (★1).

Phase 23's Probabilistic and Deflated Sharpe Ratios need the standard-normal CDF ``Φ``
and its inverse ``Z⁻¹``. Since Phase 24 reuses ``Φ`` for its two-sided paired-difference
p-value, the implementation now lives in the shared :mod:`quantforge._stats.normal`
(the deterministic-primitive analogue of :mod:`quantforge._linalg`); this module
re-exports the three public names verbatim so the campaign layer's imports and its
:data:`~quantforge.campaign.version.CAMPAIGN_NORMAL_VERSION` pin are unchanged - the
extraction is a byte-identical refactor and every sealed Phase 23 id is preserved.
"""

from __future__ import annotations

from quantforge._stats.normal import (
    EULER_MASCHERONI,
    standard_normal_cdf,
    standard_normal_ppf,
)

__all__ = [
    "EULER_MASCHERONI",
    "standard_normal_cdf",
    "standard_normal_ppf",
]
