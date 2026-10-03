"""Promotion evaluation used inside the atomic bill-creation service.

Only promotions live *right now* (date range + weekday + time window) apply:

- bogo:   for every ``buy_qty`` of ``buy_product`` in the cart, the customer
           gets ``get_qty`` of ``get_product`` FREE (rate 0 line, stock deducted).
           Free quantity is capped at available stock ("while stocks last").
- bundle:  if the cart has ``buy_qty`` of ``buy_product`` AND ``get_qty`` of
           ``get_product``, those lines get ``discount_percent`` off. The promo
           discount and the line's existing (slab/manual) discount are NOT
           stacked — the larger one wins.
- percent/flat: bill-level discount when subtotal >= min_bill_amount. Only the
           BEST one applies (no stacking of bill-level promos).
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from inventory.services import total_stock_qty

from .models import Promotion


def _q2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def active_promotions(tenant, now: datetime):
    """Promotions of this tenant that are live at ``now`` (Meta ordering applies)."""
    return [
        p
        for p in Promotion.objects.filter(tenant=tenant, is_active=True)
        .select_related("buy_product", "get_product")
        .order_by("-priority", "name")
        if p.is_live(now)
    ]


def _valid_product(tenant, product):
    return (
        product is not None
        and product.tenant_id == tenant.id
        and product.is_active
    )


def apply_line_promotions(tenant, computed_lines: list, now: datetime):
    """
    Apply bogo (free items) and bundle (line %) promotions.

    computed_lines: [{product, qty, rate, discount_percent, discount_amount,
                      slab_discount_percent, line_total}]
    Returns (updated_lines, free_items, applied) where
      free_items = [{product, qty}]  (bogo grants)
      applied    = [{id, name, type, description}]
    """
    promos = active_promotions(tenant, now)
    applied = []
    free_items = []

    # --- bogo ---
    for promo in promos:
        if promo.promo_type != Promotion.TYPE_BOGO:
            continue
        buy, get = promo.buy_product, promo.get_product
        if not _valid_product(tenant, buy) or not _valid_product(tenant, get):
            continue
        if not promo.buy_qty or promo.buy_qty <= 0:
            continue
        buy_qty_in_cart = sum(
            (cl["qty"] for cl in computed_lines if cl["product"].id == buy.id),
            Decimal("0"),
        )
        times = int(buy_qty_in_cart // promo.buy_qty)
        if times <= 0:
            continue
        free_qty = _q2(times * (promo.get_qty or Decimal("1")))
        # "While stocks last": cap the free grant at available stock.
        available = total_stock_qty(tenant, get)
        free_qty = min(free_qty, available)
        if free_qty <= 0:
            continue
        free_items.append({"product": get, "qty": free_qty})
        applied.append(
            {
                "id": promo.id,
                "name": promo.name,
                "type": promo.promo_type,
                "description": (
                    f"Buy {promo.buy_qty} {buy.sku}, get {free_qty} "
                    f"{get.sku} free"
                ),
            }
        )

    # --- bundle ---
    for promo in promos:
        if promo.promo_type != Promotion.TYPE_BUNDLE:
            continue
        buy, get = promo.buy_product, promo.get_product
        if not _valid_product(tenant, buy) or not _valid_product(tenant, get):
            continue
        pct = promo.discount_percent or Decimal("0")
        if pct <= 0:
            continue
        buy_qty_in_cart = sum(
            (cl["qty"] for cl in computed_lines if cl["product"].id == buy.id),
            Decimal("0"),
        )
        get_qty_in_cart = sum(
            (cl["qty"] for cl in computed_lines if cl["product"].id == get.id),
            Decimal("0"),
        )
        if buy_qty_in_cart < (promo.buy_qty or Decimal("1")):
            continue
        if get_qty_in_cart < (promo.get_qty or Decimal("1")):
            continue
        for cl in computed_lines:
            if cl["product"].id not in (buy.id, get.id):
                continue
            gross = _q2(cl["qty"] * cl["rate"])
            promo_discount = _q2(gross * pct / 100)
            if promo_discount > cl["discount_amount"]:
                cl["discount_amount"] = promo_discount
                cl["discount_percent"] = _q2(promo_discount * 100 / gross) if gross else Decimal("0")
                cl["line_total"] = _q2(gross - promo_discount)
        applied.append(
            {
                "id": promo.id,
                "name": promo.name,
                "type": promo.promo_type,
                "description": f"{pct}% off {buy.sku} + {get.sku} bundle",
            }
        )

    return computed_lines, free_items, applied


def best_bill_promotion(tenant, subtotal: Decimal, now: datetime):
    """
    Best bill-level (percent/flat) promotion for this subtotal.
    Returns (promotion, amount, description) or (None, Decimal("0"), "").
    Only one bill-level promo ever applies.
    """
    best = None
    best_amt = Decimal("0")
    for promo in active_promotions(tenant, now):
        if promo.promo_type == Promotion.TYPE_PERCENT:
            if not promo.discount_percent or subtotal < promo.min_bill_amount:
                continue
            amt = _q2(subtotal * promo.discount_percent / 100)
            desc = f"{promo.discount_percent}% off bills over {promo.min_bill_amount}"
        elif promo.promo_type == Promotion.TYPE_FLAT:
            if not promo.discount_amount or subtotal < promo.min_bill_amount:
                continue
            amt = min(_q2(promo.discount_amount), subtotal)
            desc = f"Rs {promo.discount_amount} off bills over {promo.min_bill_amount}"
        else:
            continue
        # Strict > keeps the earlier (higher-priority) promo on ties.
        if amt > best_amt:
            best, best_amt, best_desc = promo, amt, desc
    if best is None:
        return None, Decimal("0"), ""
    return best, best_amt, f"{best.name}: {best_desc}"
