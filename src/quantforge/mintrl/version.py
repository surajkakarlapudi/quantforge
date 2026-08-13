"""The minimum-track-record-length transformation version (Phase 28, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    minimum_track_record_length_engine_version_id = hash(code_version, config_hash)

For Phase 28 the "transformation" is the **minimum-track-record-length engine** that
turns a declarative
:class:`~quantforge.mintrl.spec.MinimumTrackRecordLengthSpecification` (naming exactly
one sealed :class:`~quantforge.campaign.result.ResearchCampaignEvaluation`, a confidence
level, and a benchmark Sharpe) into a sealed
:class:`~quantforge.mintrl.result.MinimumTrackRecordLength` - the per-trial Bailey-López
de Prado minimum track-record length and the aggregate MinTRL profile over the
campaign's trials. This module pins that engine logic with a stable version id,
following the exact pattern of
:class:`~quantforge.campaign.version.CampaignEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Three properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All MinTRL arithmetic - the
  per-trial ``1 + V·(Z_alpha/(SR-SR*))²`` (with
  ``V = 1 - gamma₃·SR + ((gamma₄-1)/4)·SR²``), the ``Decimal.sqrt`` dispersion, the
  mean / min / max / sufficient-frequency aggregates - runs under an explicit
  :class:`decimal.Context` (precision + rounding). It is folded into
  ``config_hash``, so a change to it necessarily produces a new, distinguishable
  ``minimum_track_record_length_engine_version_id``. The default is **precision 34,
  ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The method + normal versions are part of the version.** Phase 28 computes its own
  self-contained MinTRL method (:data:`MINTRL_METHOD_VERSION`) atop the *reused*
  deterministic exact-``Decimal`` standard-normal primitive
  (:data:`MINTRL_NORMAL_VERSION`: the ``Z⁻¹`` bisection of
  :mod:`quantforge._stats.normal`, shared with Phase 23). Both are folded into
  ``config_hash``, so a change to *either* yields a new, distinguishable engine id.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the MinTRL logic in a way that can alter a computed value must bump
:data:`MINTRL_ENGINE_VERSION` (the code version), :data:`MINTRL_METHOD_VERSION` (the
statistical method), or :data:`MINTRL_NORMAL_VERSION` (the normal primitive).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "MINTRL_ENGINE_VERSION",
    "MINTRL_METHOD_VERSION",
    "MINTRL_NORMAL_VERSION",
    "MINTRL_SPEC_VERSION",
    "MinimumTrackRecordLengthEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``minimum_track_record_length_id``
# (§13). Bump it when the serialized meaning of a request changes - never when engine
# logic changes (that is ``MINTRL_ENGINE_VERSION``). Shares the ``mintrl/1`` string with
# the identity domain tag by construction (the prior-phase precedent).
MINTRL_SPEC_VERSION = "mintrl/1"

# Bump whenever the MinTRL engine's orchestration logic changes in a way that can alter
# a computed value. The analogue of a code git SHA for the (as-yet uncommitted) engine;
# explicit and stable so derived identity never depends on the wall clock or a random
# value.
MINTRL_ENGINE_VERSION = "mintrl-engine/1"

# Bump whenever Phase 28's *statistical method* changes - the per-trial MinTRL formula
# (``1 + V·(Z_alpha/(SR-SR*))²`` with the shared PSR estimator-variance ``V``), the
# sufficiency test ``n ≥ MinTRL``, or the aggregate mean / dispersion / min / max /
# frequency definitions. Folded into ``config_hash`` alongside the normal-primitive
# version, so a method change is a new, distinguishable engine version (§13).
MINTRL_METHOD_VERSION = "mintrl-method/1"

# Bump whenever the *reused* deterministic exact-``Decimal`` standard-normal primitive
# changes - here only the ``Z⁻¹`` bisection of :mod:`quantforge._stats.normal` (Phase 28
# uses no ``Φ``). Folded into ``config_hash`` so a change to how the quantile
# ``Z_alpha`` is computed is a new, distinguishable engine version. Phase 28 reuses
# that primitive verbatim; this version string pins *which* primitive was used, never a
# copy of it.
MINTRL_NORMAL_VERSION = "mintrl-normal/1"

# The pinned decimal context for all MinTRL arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned MinTRL decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class MinimumTrackRecordLengthEngineVersion:
    """Immutable identity of the MinTRL-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 28's own statistical method (the MinTRL formula, the
        sufficiency test, the aggregates); folded into ``config_hash`` so a method
        change is a new version.
    normal_version:
        Revision string for the reused deterministic exact-``Decimal`` standard-normal
        primitive (the ``Z⁻¹`` bisection); folded into ``config_hash`` so a change to
        how ``Z_alpha`` is computed is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = MINTRL_ENGINE_VERSION
    method_version: str = MINTRL_METHOD_VERSION
    normal_version: str = MINTRL_NORMAL_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` of the decimal-context + method + normal."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
            f"\x00normal={self.normal_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def minimum_track_record_length_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for MinTRL math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
