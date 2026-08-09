"""Market-data transformation & adjustment versions (proposal §14, §10, §2.4).

Two immutable, content-addressed versioning entities, both mirroring the Phase 4
:class:`~quantforge.canonical.version.CanonicalFactVersion` / Phase 7
:class:`~quantforge.metrics.version.MetricEngineVersion` pattern (the id is a
``sha256:`` hash of the content; nothing depends on the wall clock):

* :class:`MarketTransformationVersion` — the **normalizer** that turns immutable
  raw vendor bytes into canonical, *unadjusted* :class:`PriceObservation` /
  :class:`CorporateAction` records. Its id feeds ``price_observation_id`` and
  ``corporate_action_id`` (proposal §14), so a change to the normalizer's
  arithmetic/parsing necessarily yields distinguishable observation ids — a bar
  normalized under one version can never be confused with one under another.
* :class:`AdjustmentVersion` — the **derived** split/dividend adjustment function
  (proposal §10). Adjusted prices are never stored; they are computed on demand by
  composing PIT-eligible :class:`CorporateAction` records over the unadjusted
  series, and this version pins the exact adjustment convention (split-only vs
  split-and-dividend) and decimal context so the same inputs reproduce the same
  adjusted values, forever. Its id feeds ``adjusted_series_id`` (proposal §14).

Both fold the pinned decimal context (precision 34, ``ROUND_HALF_EVEN`` — the same
context the metrics layer pins, so price and fundamental arithmetic round
identically) into their ``config_hash``: division rounds (a 7:1 split ratio, a
dividend fraction), so the context is part of identity (invariants 13, 20 analogue).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.availability.version import merkle_root
from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "ADJUSTMENT_CONVENTIONS",
    "ADJUSTMENT_VERSION",
    "MARKET_TRANSFORMATION_VERSION",
    "AdjustmentVersion",
    "MarketDatasetVersion",
    "MarketTransformationVersion",
    "default_decimal_context",
]

# Bump when the canonicalizer's parsing/arithmetic changes in a way that can alter a
# derived canonical value. The market analogue of a code git SHA for the (as-yet
# uncommitted) normalizer; explicit and stable so derived identity never depends on
# the wall clock or a random value.
MARKET_TRANSFORMATION_VERSION = "market-transformation/1"

# Bump when the adjustment function's arithmetic/convention changes. A distinct
# version space from the normalizer: re-normalizing raw bytes and re-adjusting a
# series are independent transforms.
ADJUSTMENT_VERSION = "market-adjustment/1"

# The adjustment conventions this version implements. ``split`` folds only split
# ratios into a continuous price; ``split-dividend`` additionally reinvests cash
# dividends (total-return-style). A future convention (spinoff, rights) is a *new*
# version, never an edit (proposal §22).
ADJUSTMENT_CONVENTIONS = ("split", "split-dividend")

# The pinned decimal context for all market arithmetic. Precision 34 with banker's
# rounding — identical to the metrics layer, so a price-derived metric and a
# filing-derived metric round the same way. Applied only via an explicit
# ``localcontext`` in the adjuster, never the ambient process context.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN

_SEP = "\x00"


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned market decimal context.

    A new instance each call so a caller can never mutate the shared context and
    perturb determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class MarketTransformationVersion:
    """Immutable identity of the raw→canonical normalizer logic + config (§14).

    Attributes
    ----------
    code_version:
        Revision string for the canonicalizer logic (git SHA in practice).
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (a split ratio or a
        per-share value can round), so any change to it is a new version.
    """

    code_version: str = MARKET_TRANSFORMATION_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the decimal-context configuration."""
        payload = f"prec={self.decimal_precision}{_SEP}round={self.decimal_rounding}"
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def market_transformation_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§14)."""
        payload = f"{self.code_version}{_SEP}{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for market arithmetic."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)


@dataclass(frozen=True, slots=True)
class AdjustmentVersion:
    """Immutable identity of the derived adjustment function + convention (§10, §14).

    The adjustment is a *pure, versioned* function of the unadjusted series and the
    PIT-eligible corporate actions (proposal §10): same inputs + same
    :attr:`adjustment_version` ⇒ identical adjusted series. ``convention`` selects
    which actions participate (splits only, or splits + dividends).
    """

    code_version: str = ADJUSTMENT_VERSION
    convention: str = "split"
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    def __post_init__(self) -> None:
        if self.convention not in ADJUSTMENT_CONVENTIONS:
            raise ValueError(
                f"unknown adjustment convention {self.convention!r}; "
                f"expected one of {ADJUSTMENT_CONVENTIONS}"
            )

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of convention + decimal context."""
        payload = (
            f"convention={self.convention}{_SEP}"
            f"prec={self.decimal_precision}{_SEP}round={self.decimal_rounding}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def adjustment_version(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§14).

        This is the ``adjustment_version`` string that
        :func:`~quantforge.market.identity.adjusted_series_id` pins, so the derived
        adjusted-series identity encodes exactly which convention produced it.
        """
        payload = f"{self.code_version}{_SEP}{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for adjustment arithmetic."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)


@dataclass(frozen=True, slots=True)
class MarketDatasetVersion:
    """An immutable, content-addressed market snapshot manifest (§14, invariant 19).

    The market analogue of :class:`~quantforge.availability.version.DatasetVersion`:
    it pins everything needed to reproduce a market ``REVISED`` answer — the exact
    raw vendor documents, the canonical observations, the corporate actions, the
    normalizer version, and the market-availability-policy set. The id is a Merkle
    root (**reusing** the Phase 5 :func:`~quantforge.availability.version.merkle_root`
    verbatim) over the *tagged, sorted* member id lists, so any change — one more
    bar, a re-normalization, a re-derived availability under a new policy — yields a
    new id, and identical contents always yield the same id. It is impossible to
    mutate a snapshot without changing its identity.

    The section tags (``mktraw`` / ``price`` / ``action`` / ``mktpol`` / ``tv``)
    prevent a ``price_observation_id`` from ever colliding with a
    ``corporate_action_id`` or a raw sha in the leaf space, and keep the market
    leaf space disjoint from the SEC :class:`DatasetVersion` leaf space.
    """

    market_transformation_version_id: str
    market_availability_policy_ids: tuple[str, ...] = ()
    raw_document_ids: tuple[str, ...] = ()
    price_observation_ids: tuple[str, ...] = ()
    corporate_action_ids: tuple[str, ...] = ()
    parent_dataset_version_id: str | None = None
    notes: str = ""

    @property
    def dataset_version_id(self) -> str:
        """Merkle root over sorted, tagged members + tv id (§14, invariant 19)."""
        leaves: list[str] = [f"tv{_SEP}{self.market_transformation_version_id}"]
        leaves += [
            f"mktpol{_SEP}{p}" for p in sorted(self.market_availability_policy_ids)
        ]
        leaves += [f"mktraw{_SEP}{r}" for r in sorted(self.raw_document_ids)]
        leaves += [f"price{_SEP}{p}" for p in sorted(self.price_observation_ids)]
        leaves += [f"action{_SEP}{a}" for a in sorted(self.corporate_action_ids)]
        return merkle_root(leaves)

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_version_id": self.dataset_version_id,
            "market_transformation_version_id": self.market_transformation_version_id,
            "market_availability_policy_ids": sorted(
                self.market_availability_policy_ids
            ),
            "raw_document_ids": sorted(self.raw_document_ids),
            "price_observation_ids": sorted(self.price_observation_ids),
            "corporate_action_ids": sorted(self.corporate_action_ids),
            "parent_dataset_version_id": self.parent_dataset_version_id,
            "notes": self.notes,
        }
