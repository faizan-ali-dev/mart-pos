"""
Billing business logic.

Bill creation is a single atomic transaction:
  validate -> compute totals -> create bill/lines/payments -> deduct stock
  -> khata receivable (for credit sales).

Bills are immutable after creation (see models.Bill.save).
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from catalog.models import PriceSlab, Product
from inventory.services import add_stock, deduct_stock
from khata.models import Customer
from khata.services import adjust_balance, party_balance, record_receivable
from tenants.models import Tenant

from .models import Bill, BillLine, Payment, Return, ReturnLine, Shift


def _q2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _next_bill_no(tenant: Tenant) -> str:
    """Atomic per-tenant bill sequence. Call inside a transaction with the tenant locked."""
    tenant.bill_seq += 1
    tenant.save(update_fields=["bill_seq"])
    return f"{tenant.code}-{tenant.bill_seq:06d}"


def _open_shift_for(tenant, user) -> Shift | None:
    return (
        Shift.objects.filter(tenant=tenant, opened_by=user, status=Shift.STATUS_OPEN)
        .order_by("-opened_at")
        .first()
    )


def _slab_discount_percent(tenant, product: Product, qty: Decimal) -> Decimal:
    """Discount % of the highest PriceSlab with min_qty <= qty, else 0."""
    slab = (
        PriceSlab.objects.filter(tenant=tenant, product=product, min_qty__lte=qty)
        .order_by("-min_qty")
        .first()
    )
    return _q2(slab.discount_percent) if slab else Decimal("0")


@transaction.atomic
def create_bill(
    *,
    tenant,
    cashier,
    lines: list,
    payments: list,
    bill_discount_percent=Decimal("0"),
    bill_discount_amount=Decimal("0"),
    bill_discount_reason="",
    customer=None,
    tendered=None,
    notes="",
    shift=None,
    sale_type=None,
) -> Bill:
    """
    Create a complete bill atomically.

    lines:    [{product (obj|id), qty, discount_percent=0, discount_amount=0}]
    payments: [{mode, amount, reference=""}]
    sale_type: "retail" | "wholesale" | None. When None, auto-detects: a
        customer with customer_type="wholesale" makes the bill wholesale.

    Wholesale pricing rules:
      - Line rate = product.wholesale_price (falls back to retail_price when 0).
      - Volume slab: the PriceSlab with the highest min_qty <= line qty gives
        a discount on the line. Slab and manual line discounts are NOT stacked:
        the larger of the two wins.
      - Bill level: customer.wholesale_discount_percent applies automatically
        and stacks ADDITIVELY with any manual bill discount, capped at 50% of
        subtotal in total.
    """
    if cashier.tenant_id != tenant.id:
        raise ValidationError("Cashier does not belong to this tenant.")
    if not lines:
        raise ValidationError("A bill must have at least one line.")
    if not payments:
        raise ValidationError("A bill must have at least one payment.")

    # Lock the tenant row so bill numbers are unique under concurrency.
    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)

    if shift is None:
        shift = _open_shift_for(tenant, cashier)
    elif shift.tenant_id != tenant.id or shift.status != Shift.STATUS_OPEN:
        raise ValidationError("Shift is not open or belongs to another tenant.")
    if shift is None:
        raise ValidationError("No open shift. Open a shift before billing.")

    bill_discount_percent = _q2(bill_discount_percent)
    bill_discount_amount = _q2(bill_discount_amount)
    if bill_discount_percent and bill_discount_amount:
        raise ValidationError("Give either bill discount percent or amount, not both.")
    if (bill_discount_percent or bill_discount_amount) and not bill_discount_reason:
        raise ValidationError("A reason is required for bill-level discounts.")

    # --- resolve customer early: wholesale pricing depends on their type ---
    if customer is not None and not isinstance(customer, Customer):
        try:
            customer = Customer.objects.get(pk=customer, tenant=tenant)
        except Customer.DoesNotExist:
            raise ValidationError("Customer not found.")
    if customer is not None and customer.tenant_id != tenant.id:
        raise ValidationError("Customer does not belong to this tenant.")

    if sale_type is None:
        sale_type = (
            Bill.SALE_WHOLESALE
            if customer is not None
            and customer.customer_type == Customer.TYPE_WHOLESALE
            else Bill.SALE_RETAIL
        )
    elif sale_type not in dict(Bill.SALE_CHOICES):
        raise ValidationError(f"Invalid sale type: {sale_type}.")
    is_wholesale = sale_type == Bill.SALE_WHOLESALE

    # --- lines: validate stock + compute ---
    computed_lines = []
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for entry in lines:
        product = entry["product"]
        if not isinstance(product, Product):
            try:
                product = Product.objects.get(pk=product, tenant=tenant)
            except Product.DoesNotExist:
                raise ValidationError(f"Product {entry['product']} not found.")
        if product.tenant_id != tenant.id:
            raise ValidationError(f"Product {product.sku} does not belong to this tenant.")
        if not product.is_active:
            raise ValidationError(f"Product {product.sku} is inactive.")
        qty = _q2(entry["qty"]).quantize(Decimal("0.001"))
        if qty <= 0:
            raise ValidationError("Line quantity must be positive.")
        # Wholesale rate: product.wholesale_price, falling back to retail when unset (0).
        if is_wholesale and product.wholesale_price > 0:
            rate = _q2(product.wholesale_price)
        else:
            rate = _q2(product.retail_price)
        gross = _q2(qty * rate)
        d_pct = _q2(entry.get("discount_percent", 0))
        d_amt = _q2(entry.get("discount_amount", 0))
        if d_pct and d_amt:
            raise ValidationError("Give either line discount percent or amount, not both.")
        # Slab vs manual line discount: NOT stacked, the larger one wins.
        slab_pct = (
            _slab_discount_percent(tenant, product, qty) if is_wholesale else Decimal("0")
        )
        manual_discount = _q2(gross * d_pct / 100) if d_pct else d_amt
        slab_discount = _q2(gross * slab_pct / 100)
        discount = max(manual_discount, slab_discount)
        if discount > gross:
            raise ValidationError(f"Discount exceeds line total for {product.sku}.")
        eff_pct = _q2(discount * 100 / gross) if gross else Decimal("0")
        line_total = _q2(gross - discount)
        tax_total += _q2(line_total * product.tax_percent / 100)
        subtotal += line_total
        computed_lines.append(
            {
                "product": product,
                "qty": qty,
                "rate": rate,
                "discount_percent": eff_pct,
                "discount_amount": discount,
                "slab_discount_percent": slab_pct,
                "line_total": line_total,
            }
        )

    # --- bill-level discount: manual + automatic wholesale customer discount ---
    # They stack additively, capped at 50% of subtotal in total. Without an
    # automatic discount the manual discount is applied exactly as before.
    auto_pct = (
        _q2(customer.wholesale_discount_percent)
        if is_wholesale and customer is not None
        else Decimal("0")
    )
    if auto_pct:
        if bill_discount_percent:
            manual_pct_equiv = bill_discount_percent
        elif bill_discount_amount and subtotal:
            manual_pct_equiv = _q2(bill_discount_amount * 100 / subtotal)
        else:
            manual_pct_equiv = Decimal("0")
        total_pct = min(manual_pct_equiv + auto_pct, Decimal("50"))
        bill_discount = _q2(subtotal * total_pct / 100)
    else:
        bill_discount = (
            _q2(subtotal * bill_discount_percent / 100)
            if bill_discount_percent
            else bill_discount_amount
        )
    if bill_discount > subtotal:
        raise ValidationError("Bill discount exceeds subtotal.")
    if auto_pct and not bill_discount_reason:
        bill_discount_reason = f"Wholesale customer discount ({auto_pct}%)"
    grand_total = _q2(subtotal - bill_discount + tax_total)

    # --- payments ---
    computed_payments = []
    paid_total = Decimal("0")
    khata_amount = Decimal("0")
    for p in payments:
        mode = p["mode"]
        if mode not in dict(Payment.MODE_CHOICES):
            raise ValidationError(f"Invalid payment mode: {mode}.")
        amount = _q2(p["amount"])
        if amount <= 0:
            raise ValidationError("Payment amounts must be positive.")
        computed_payments.append(
            {"mode": mode, "amount": amount, "reference": p.get("reference", "")}
        )
        paid_total += amount
        if mode == Payment.MODE_KHATA:
            khata_amount += amount
    if abs(paid_total - grand_total) > Decimal("0.01"):
        raise ValidationError(
            f"Payments ({paid_total}) must equal grand total ({grand_total})."
        )

    if khata_amount:
        if customer is None:
            raise ValidationError("A customer is required for khata (credit) sales.")
        if tenant.block_khata_over_limit and customer.credit_limit > 0:
            outstanding = party_balance(tenant, customer=customer)
            if outstanding + khata_amount > customer.credit_limit:
                raise ValidationError(
                    f"Credit limit exceeded for {customer.name}: "
                    f"limit {customer.credit_limit}, outstanding {outstanding}, "
                    f"this sale {khata_amount}."
                )

    change_due = Decimal("0")
    if tendered is not None:
        tendered = _q2(tendered)
        if tendered < grand_total:
            raise ValidationError("Tendered amount is less than the grand total.")
        change_due = _q2(tendered - grand_total)

    # --- persist ---
    bill = Bill.objects.create(
        tenant=tenant,
        bill_no=_next_bill_no(tenant),
        shift=shift,
        cashier=cashier,
        customer=customer,
        sale_type=sale_type,
        subtotal=_q2(subtotal),
        bill_discount=_q2(bill_discount),
        bill_discount_reason=bill_discount_reason,
        tax_total=_q2(tax_total),
        grand_total=grand_total,
        tendered=tendered,
        change_due=change_due,
        notes=notes,
    )
    for cl in computed_lines:
        BillLine.objects.create(bill=bill, **cl)
    for cp in computed_payments:
        Payment.objects.create(bill=bill, **cp)

    # Stock leaves the shop (raises ValidationError on insufficient stock,
    # which rolls the whole bill back).
    for cl in computed_lines:
        deduct_stock(tenant, cl["product"], cl["qty"])

    if khata_amount:
        record_receivable(
            tenant=tenant,
            customer=customer,
            amount=khata_amount,
            bill=bill,
            notes=f"Credit sale {bill.bill_no}",
            created_by=cashier,
        )
    return bill


@transaction.atomic
def create_return(*, tenant, bill, lines: list, reason: str,
                  refund_mode: str, created_by) -> Return:
    """
    Return items against a bill: restock + record refund.

    lines: [{bill_line (id), qty}]
    """
    if not reason:
        raise ValidationError("A reason is required for returns.")
    if refund_mode not in dict(Return.REFUND_CHOICES):
        raise ValidationError(f"Invalid refund mode: {refund_mode}.")
    if bill.tenant_id != tenant.id:
        raise ValidationError("Bill does not belong to this tenant.")
    if not lines:
        raise ValidationError("Return must have at least one line.")

    # Lock the bill's lines while we check already-returned quantities.
    bill_lines = {bl.id: bl for bl in bill.lines.select_for_update().all()}
    total_refund = Decimal("0")
    computed = []
    for entry in lines:
        bl = bill_lines.get(entry["bill_line"])
        if bl is None:
            raise ValidationError(f"Bill line {entry['bill_line']} not found on this bill.")
        qty = Decimal(str(entry["qty"])).quantize(Decimal("0.001"))
        if qty <= 0:
            raise ValidationError("Return quantity must be positive.")
        already = (
            bl.return_lines.aggregate(t=Sum("qty"))["t"] or Decimal("0")
        )
        if qty > bl.qty - already:
            raise ValidationError(
                f"Cannot return {qty} of {bl.product.sku}: only {bl.qty - already} returnable."
            )
        line_total = _q2(qty * bl.rate)
        total_refund += line_total
        computed.append({"bill_line": bl, "product": bl.product, "qty": qty,
                         "rate": bl.rate, "line_total": line_total})
    total_refund = _q2(total_refund)

    ret = Return.objects.create(
        tenant=tenant,
        bill=bill,
        reason=reason,
        refund_mode=refund_mode,
        total_refund=total_refund,
        created_by=created_by,
    )
    for c in computed:
        ReturnLine.objects.create(return_obj=ret, **c)
        # Restock to the shop floor (fallback: first active location).
        from inventory.models import StockLocation

        location = (
            StockLocation.objects.filter(
                tenant=tenant, location_type=StockLocation.SHOP_FLOOR, is_active=True
            ).first()
            or StockLocation.objects.filter(tenant=tenant, is_active=True).first()
        )
        if location is None:
            raise ValidationError("No active stock location to restock into.")
        add_stock(tenant, c["product"], location, c["qty"])

    if refund_mode == Return.REFUND_KHATA:
        if bill.customer is None:
            raise ValidationError("Khata refund needs a customer on the original bill.")
        adjust_balance(
            tenant=tenant,
            customer=bill.customer,
            amount=-total_refund,
            notes=f"Return on {bill.bill_no}: {reason}",
            created_by=created_by,
        )
    return ret


@transaction.atomic
def close_shift(*, shift: Shift, counted_cash, notes="", closed_by=None) -> Shift:
    """Close a shift: expected = opening + cash sales - cash refunds; diff = counted - expected."""
    if shift.status != Shift.STATUS_OPEN:
        raise ValidationError("Shift is already closed.")
    counted_cash = _q2(counted_cash)

    cash_sales = (
        Payment.objects.filter(
            bill__shift=shift, mode=Payment.MODE_CASH
        ).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    cash_refunds = (
        Return.objects.filter(
            bill__shift=shift, refund_mode=Return.REFUND_CASH
        ).aggregate(t=Sum("total_refund"))["t"]
        or Decimal("0")
    )
    expected = _q2(shift.opening_cash + cash_sales - cash_refunds)

    shift.expected_cash = expected
    shift.counted_cash = counted_cash
    shift.difference = _q2(counted_cash - expected)
    shift.status = Shift.STATUS_CLOSED
    shift.closed_at = timezone.now()
    if notes:
        shift.notes = (shift.notes + "\n" + notes).strip() if shift.notes else notes
    shift.save(
        update_fields=["expected_cash", "counted_cash", "difference", "status",
                       "closed_at", "notes"]
    )
    return shift


def day_summary(tenant, target_date: date) -> dict:
    """Daily sales summary for the owner dashboard / WhatsApp day-close."""
    bills = Bill.objects.filter(tenant=tenant, created_at__date=target_date)
    returns = Return.objects.filter(tenant=tenant, created_at__date=target_date)

    by_mode = {mode: Decimal("0") for mode, _ in Payment.MODE_CHOICES}
    for row in (
        Payment.objects.filter(bill__in=bills).values("mode").annotate(t=Sum("amount"))
    ):
        by_mode[row["mode"]] = _q2(row["t"] or 0)
    payouts = Decimal("0")
    for ret in returns:
        by_mode[ret.refund_mode] = _q2(by_mode.get(ret.refund_mode, Decimal("0")) - ret.total_refund)
        if ret.refund_mode == Return.REFUND_CASH:
            payouts += ret.total_refund

    total_sales = _q2(sum(by_mode.values(), Decimal("0")))
    top_items = list(
        BillLine.objects.filter(bill__in=bills)
        .values("product__sku", "product__name")
        .annotate(qty=Sum("qty"), revenue=Sum("line_total"))
        .order_by("-qty")[:10]
    )
    for item in top_items:
        item["qty"] = str(item["qty"])
        item["revenue"] = str(_q2(item["revenue"] or 0))

    return {
        "date": target_date.isoformat(),
        "bills_count": bills.count(),
        "returns_count": returns.count(),
        "total_sales": str(total_sales),
        "by_mode": {k: str(v) for k, v in by_mode.items()},
        "payouts": str(_q2(payouts)),
        "top_items": top_items,
    }
