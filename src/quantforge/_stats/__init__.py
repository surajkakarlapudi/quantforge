"""Shared deterministic exact-``Decimal`` statistical primitives.

This private package holds numerical primitives that more than one research layer
depends on and that must be **bit-identical** across platforms - the same reason the
linear-algebra kernels live in :mod:`quantforge._linalg`. The first inhabitant is the
standard-normal CDF ``Φ`` and its inverse ``Z⁻¹`` (:mod:`quantforge._stats.normal`),
originally introduced by the Phase 23 campaign layer and shared unchanged by the Phase
24 comparison layer's two-sided p-value.

Everything here is a pure function of its arguments and an explicit
:class:`~decimal.Context`; no wall clock, RNG, ``float``, ``id()``, or iteration-order
dependence enters any value.
"""

from __future__ import annotations
