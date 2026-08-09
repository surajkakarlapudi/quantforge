"""Derived, PIT-gated split/dividend price adjustment (§10, D4/D5).

Adjusted prices are **never stored**; they are computed on demand here by composing
the immutable unadjusted series with the immutable
:class:`~quantforge.market.model.CorporateAction` history, exactly as
[the proposal §10](../docs/phase11-market-data-locked.md) requires. Because this
function consumes **only** corporate actions that are PIT-eligible as of the query's
``as_of`` (the caller filters them), it **cannot introduce look-ahead**: a future
split/dividend that is not yet knowable at ``as_of`` simply is not in ``actions``, so
it cannot alter a past adjusted price. Same inputs + same
:class:`~quantforge.market.version.AdjustmentVersion` ⇒ identical adjusted series,
reproducibly, forever (invariant 13).

Convention (:class:`~quantforge.market.version.AdjustmentVersion.convention`):

* ``"split"`` - back-adjust for split ratios only. A price on a date *strictly
  before* a split's ex-date is divided by the split ratio, so a pre-split print is
  comparable to post-split prints (a 7:1 split turns a 700 pre-split close into 100).
* ``"split-dividend"`` - additionally reinvest cash dividends (total-return style). A
  price strictly before a dividend's ex-date is multiplied by ``(1 - amount /
  reference_close)``, where ``reference_close`` is the **PIT-eligible** close on the
  last trading day strictly before the ex-date. If that reference close is not
  available, the affected earlier cells become a first-class ``UNDEFINED`` with
  :attr:`~quantforge.market.model.PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE`
  - the adjustment is **never guessed** (Principle 8).

All arithmetic uses the pinned decimal context (precision 34, ``ROUND_HALF_EVEN``);
no float ever enters an adjusted value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext

from quantforge.availability.timestamps import format_utc_z
from quantforge.market.identity import adjusted_series_id, boundary_key
from quantforge.market.model import (
    CorporateAction,
    CorporateActionKind,
    PriceField,
    PriceStatus,
    PriceUndefinedReason,
)
from quantforge.market.result import PitPrice, PitPriceSeries, PriceProvenance
from quantforge.market.version import AdjustmentVersion

__all__ = ["adjust_pit_series"]


def adjust_pit_series(
    *,
    adjustment_version: AdjustmentVersion,
    security_id: str,
    field: PriceField,
    as_of: datetime,
    axis_id: str,
    axis_dates: Sequence[str],
    unadjusted_cells: Sequence[PitPrice],
    actions: Sequence[CorporateAction],
    reference_closes: Mapping[str, str | None],
) -> PitPriceSeries:
    """Compute the adjusted PIT series for ``field`` over an axis (§10).

    Parameters
    ----------
    adjustment_version:
        Pins the convention (splits only vs splits + dividends) and decimal context.
    axis_dates / unadjusted_cells:
        The requested trading dates and the resolver's *unadjusted* PIT cell for
        each (same length, same order).
    actions:
        The corporate actions **already filtered to PIT-eligibility** as of
        ``as_of`` (the engine gates them so this function cannot see the future).
    reference_closes:
        For the ``split-dividend`` convention: ``ex_date → reference close string``
        (the PIT-eligible close on the last trading day strictly before the ex-date),
        or ``None`` when unavailable. Ignored for the ``split`` convention.

    Returns a :class:`PitPriceSeries` marked ``adjusted=True`` with its
    ``adjustment_version`` and ``adjusted_series_id`` populated. UNDEFINED cells are
    preserved (never dropped, never forward-filled).
    """
    convention = adjustment_version.convention
    include_dividends = convention == "split-dividend"

    splits = _sorted_actions(actions, CorporateActionKind.SPLIT)
    dividends = (
        _sorted_actions(actions, CorporateActionKind.DIVIDEND)
        if include_dividends
        else []
    )

    out_cells: list[PitPrice] = []
    with localcontext(adjustment_version.decimal_context()):
        for trading_date, cell in zip(axis_dates, unadjusted_cells, strict=True):
            out_cells.append(
                _adjust_cell(
                    security_id=security_id,
                    field=field,
                    as_of=as_of,
                    trading_date=trading_date,
                    cell=cell,
                    splits=splits,
                    dividends=dividends,
                    reference_closes=reference_closes,
                )
            )

    # The identity pins the ordered unadjusted observation ids that were actually
    # composed (the KNOWN cells' winning observations) and the ordered action ids.
    obs_ids = [
        c.provenance.selected_price_observation_id
        for c in unadjusted_cells
        if c.provenance.selected_price_observation_id is not None
    ]
    action_ids = [a.corporate_action_id for a in (*splits, *dividends)]
    series_id = adjusted_series_id(
        adjustment_version=adjustment_version.adjustment_version,
        security_id=security_id,
        boundary_key=boundary_key(kind="pit", value=format_utc_z(as_of)),
        unadjusted_obs_ids=obs_ids,
        action_ids=action_ids,
    )
    return PitPriceSeries(
        security_id=security_id,
        field=field,
        as_of=as_of,
        axis_id=axis_id,
        cells=tuple(out_cells),
        adjusted=True,
        adjustment_version=adjustment_version.adjustment_version,
        adjusted_series_id=series_id,
    )


def _adjust_cell(
    *,
    security_id: str,
    field: PriceField,
    as_of: datetime,
    trading_date: str,
    cell: PitPrice,
    splits: Sequence[CorporateAction],
    dividends: Sequence[CorporateAction],
    reference_closes: Mapping[str, str | None],
) -> PitPrice:
    """Adjust one cell by the cumulative factor of actions ex-dated after it."""
    # An unadjusted cell that is already UNDEFINED stays UNDEFINED (its reason is
    # carried through) - there is nothing to adjust.
    if not cell.is_known or cell.value_numeric_str is None:
        return cell

    try:
        value = Decimal(cell.value_numeric_str)
    except InvalidOperation:
        return _undefined_cell(cell, PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE)

    factor = Decimal(1)

    # Splits: a price strictly before the ex-date is divided by the ratio.
    for split in splits:
        if split.ex_date <= trading_date:
            continue
        ratio_raw = split.payload.get("ratio")
        if not isinstance(ratio_raw, str):
            return _undefined_cell(
                cell, PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE
            )
        try:
            ratio = Decimal(ratio_raw)
        except InvalidOperation:
            return _undefined_cell(
                cell, PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE
            )
        if ratio <= 0:
            return _undefined_cell(
                cell, PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE
            )
        factor = factor / ratio

    # Dividends: a price strictly before the ex-date is scaled by (1 - D / C_prev),
    # where C_prev is the PIT-eligible close before the ex-date. Missing reference →
    # the adjustment cannot be defended → UNDEFINED (never guessed).
    for dividend in dividends:
        if dividend.ex_date <= trading_date:
            continue
        amount_raw = dividend.payload.get("amount")
        if not isinstance(amount_raw, str):
            return _undefined_cell(
                cell, PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE
            )
        ref_raw = reference_closes.get(dividend.ex_date)
        if ref_raw is None:
            return _undefined_cell(
                cell, PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE
            )
        try:
            amount = Decimal(amount_raw)
            ref_close = Decimal(ref_raw)
            if ref_close <= 0:
                raise InvalidOperation
            div_factor = Decimal(1) - (amount / ref_close)
        except (InvalidOperation, DivisionByZero):
            return _undefined_cell(
                cell, PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE
            )
        if div_factor <= 0:
            return _undefined_cell(
                cell, PriceUndefinedReason.MISSING_ADJUSTMENT_REFERENCE
            )
        factor = factor * div_factor

    adjusted_value = value * factor
    return PitPrice(
        security_id=security_id,
        trading_date=trading_date,
        field=field,
        status=PriceStatus.KNOWN,
        value_numeric_str=_normalize_decimal(adjusted_value),
        currency=cell.currency,
        reason=None,
        provenance=cell.provenance,
        as_of=as_of,
    )


def _undefined_cell(cell: PitPrice, reason: PriceUndefinedReason) -> PitPrice:
    """A cell whose adjustment could not be defended - first-class UNDEFINED."""
    provenance = PriceProvenance(
        market_transformation_version_id=(
            cell.provenance.market_transformation_version_id
        ),
        boundary_kind=cell.provenance.boundary_kind,
        boundary_value=cell.provenance.boundary_value,
        selected_price_observation_id=cell.provenance.selected_price_observation_id,
        selected_raw_document_sha256=cell.provenance.selected_raw_document_sha256,
        selected_source_id=cell.provenance.selected_source_id,
        availability_policy_id=cell.provenance.availability_policy_id,
        availability_timestamp=cell.provenance.availability_timestamp,
        present_candidates=cell.provenance.present_candidates,
        eligible_count=cell.provenance.eligible_count,
        result_status=PriceStatus.UNDEFINED,
        result_reason=reason,
    )
    return PitPrice(
        security_id=cell.security_id,
        trading_date=cell.trading_date,
        field=cell.field,
        status=PriceStatus.UNDEFINED,
        value_numeric_str=None,
        currency=cell.currency,
        reason=reason,
        provenance=provenance,
        as_of=cell.as_of,
    )


def _sorted_actions(
    actions: Sequence[CorporateAction], kind: CorporateActionKind
) -> list[CorporateAction]:
    """Actions of one kind, in a deterministic total order (ex_date, then id)."""
    selected = [a for a in actions if a.action_kind is kind]
    selected.sort(key=lambda a: (a.ex_date, a.corporate_action_id))
    return selected


def _normalize_decimal(value: Decimal) -> str:
    """Canonical string for an adjusted value - deterministic, no exponent noise."""
    normalized = value.normalize()
    # Avoid scientific notation (e.g. 1E+2) so the string form is stable/readable.
    return format(normalized, "f")
