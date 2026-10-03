"""
Inventory business logic. All mutating operations are atomic and take row locks
(select_for_update) so concurrent billing/GRN can't corrupt stock counts.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Case, F, IntegerField, Sum, Value, When

from catalog.models import Product

from .models import Batch, GRN, GRNLine, StockAdjustment, StockLevel, StockLocation


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def get_or_create_level(tenant, product, location, lock=False):
    qs = StockLevel.objects
    if lock:
        qs = qs.select_for_update()
    level, _ = qs.get_or_create(
        tenant=tenant, product=product, location=location, defaults={"qty": Decimal("0")}
    )
    if lock:
        # get_or_create doesn't lock on the create path; re-fetch with lock.
        level = StockLevel.objects.select_for_update().get(pk=level.pk)
    return level


def total_stock_qty(tenant, product) -> Decimal:
    agg = StockLevel.objects.filter(tenant=tenant, product=product).aggregate(
        total=Sum("qty")
    )
    return agg["total"] or Decimal("0")


def deduct_stock(tenant, product, qty: Decimal, user=None) -> None:
    """
    Remove ``qty`` from stock, preferring the shop floor, then godown.
    Raises ValidationError when available stock is insufficient.
    Must be called inside an atomic block.
    """
    if qty <= 0:
        raise ValidationError("Quantity must be positive.")
    locations = list(
        StockLocation.objects.filter(tenant=tenant, is_active=True).order_by(
            Case(
                When(location_type=StockLocation.SHOP_FLOOR, then=Value(0)),
                When(location_type=StockLocation.GODOWN, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
    )
    remaining = qty
    for location in locations:
        if remaining <= 0:
            break
        level = get_or_create_level(tenant, product, location, lock=True)
        take = min(level.qty, remaining)
        if take > 0:
            level.qty -= take
            level.save(update_fields=["qty", "updated_at"])
            remaining -= take
    if remaining > 0:
        available = qty - remaining
        raise ValidationError(
            f"Insufficient stock for {product.sku}: need {qty}, have {available}."
        )


def add_stock(tenant, product, location, qty: Decimal) -> StockLevel:
    """Add ``qty`` to a specific location. Must be called inside an atomic block."""
    if qty <= 0:
        raise ValidationError("Quantity must be positive.")
    level = get_or_create_level(tenant, product, location, lock=True)
    level.qty += qty
    level.save(update_fields=["qty", "updated_at"])
    return level


def _check_tenant_product(tenant, product: Product):
    if product.tenant_id != tenant.id:
        raise ValidationError(f"Product {product.sku} does not belong to this tenant.")
    if not product.is_active:
        raise ValidationError(f"Product {product.sku} is inactive.")


@transaction.atomic
def receive_grn(
    *,
    tenant,
    supplier,
    location,
    lines: list,
    supplier_invoice_no="",
    on_credit=False,
    notes="",
    received_by=None,
) -> GRN:
    """
    Create a GRN, add stock, and update each product's weighted-average cost.

    lines: [{product (obj or id), qty, purchase_rate, expiry_date (optional)}]
    """
    from khata.models import LedgerEntry
    from khata.services import record_payable

    if supplier.tenant_id != tenant.id:
        raise ValidationError("Supplier does not belong to this tenant.")
    if location.tenant_id != tenant.id:
        raise ValidationError("Location does not belong to this tenant.")
    if not lines:
        raise ValidationError("GRN must have at least one line.")

    grn = GRN.objects.create(
        tenant=tenant,
        supplier=supplier,
        supplier_invoice_no=supplier_invoice_no,
        location=location,
        on_credit=on_credit,
        notes=notes,
        received_by=received_by,
    )
    total_cost = Decimal("0")
    for entry in lines:
        product = entry["product"]
        if not isinstance(product, Product):
            product = Product.objects.get(pk=product)
        _check_tenant_product(tenant, product)
        qty = Decimal(str(entry["qty"]))
        rate = Decimal(str(entry["purchase_rate"]))
        if qty <= 0 or rate < 0:
            raise ValidationError("GRN line qty must be > 0 and rate >= 0.")
        expiry = entry.get("expiry_date")

        line_total = _q2(qty * rate)
        grn_line = GRNLine.objects.create(
            grn=grn,
            product=product,
            qty=qty,
            purchase_rate=rate,
            expiry_date=expiry,
            line_total=line_total,
        )
        total_cost += line_total

        # Weighted-average cost BEFORE adding the new stock.
        old_qty = total_stock_qty(tenant, product)
        old_cost = product.purchase_price
        if old_qty > 0:
            new_cost = _q2((old_qty * old_cost + qty * rate) / (old_qty + qty))
        else:
            new_cost = _q2(rate)
        product.purchase_price = new_cost
        product.save(update_fields=["purchase_price", "updated_at"])

        add_stock(tenant, product, location, qty)

        if product.track_expiry and expiry:
            Batch.objects.create(
                tenant=tenant,
                product=product,
                expiry_date=expiry,
                qty=qty,
                grn_line=grn_line,
            )

    grn.total_cost = _q2(total_cost)
    grn.save(update_fields=["total_cost"])

    if on_credit and total_cost > 0:
        record_payable(
            tenant=tenant,
            supplier=supplier,
            amount=_q2(total_cost),
            notes=f"GRN-{grn.id} {supplier_invoice_no}".strip(),
            created_by=received_by,
        )
    return grn


@transaction.atomic
def apply_adjustment(
    *,
    tenant,
    product,
    location,
    adjustment_type,
    qty_change,
    reason,
    created_by=None,
    approved_by=None,
) -> StockAdjustment:
    """Manual stock correction. Negative changes need manager/owner approval."""
    _check_tenant_product(tenant, product)
    if location.tenant_id != tenant.id:
        raise ValidationError("Location does not belong to this tenant.")
    qty_change = Decimal(str(qty_change))
    if qty_change == 0:
        raise ValidationError("qty_change cannot be zero.")
    if not reason:
        raise ValidationError("A reason is required for every stock adjustment.")
    if qty_change < 0:
        if approved_by is None or approved_by.role not in ("owner", "manager"):
            raise ValidationError(
                "Stock-reducing adjustments require manager/owner approval."
            )
        if approved_by.tenant_id != tenant.id:
            raise ValidationError("Approver does not belong to this tenant.")

    level = get_or_create_level(tenant, product, location, lock=True)
    new_qty = level.qty + qty_change
    if new_qty < 0:
        raise ValidationError(
            f"Adjustment would take {product.sku} below zero (have {level.qty})."
        )
    level.qty = new_qty
    level.save(update_fields=["qty", "updated_at"])

    return StockAdjustment.objects.create(
        tenant=tenant,
        product=product,
        location=location,
        adjustment_type=adjustment_type,
        qty_change=qty_change,
        reason=reason,
        approved_by=approved_by,
        created_by=created_by,
    )


def low_stock_items(tenant):
    """Products whose total stock is at or below their reorder level."""
    from django.db.models import OuterRef, Subquery

    totals = (
        StockLevel.objects.filter(product=OuterRef("pk"))
        .values("product")
        .annotate(total=Sum("qty"))
        .values("total")
    )
    return (
        Product.objects.filter(tenant=tenant, is_active=True)
        .annotate(total_qty=Subquery(totals))
        .filter(total_qty__lte=F("reorder_level"))
    )


def expiring_batches(tenant, within_days=90):
    """Non-empty batches expiring within ``within_days``."""
    today = date.today()
    from datetime import timedelta

    return (
        Batch.objects.filter(
            tenant=tenant,
            qty__gt=0,
            expiry_date__lte=today + timedelta(days=within_days),
        )
        .select_related("product")
        .order_by("expiry_date")
    )
