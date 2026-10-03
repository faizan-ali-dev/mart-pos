"""Khata (credit ledger) business logic: receivables, payables, FIFO allocation."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import Customer, KhataPayment, LedgerEntry, Supplier


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def party_balance(tenant, customer=None, supplier=None) -> Decimal:
    qs = LedgerEntry.objects.filter(tenant=tenant)
    if customer is not None:
        qs = qs.filter(customer=customer)
    else:
        qs = qs.filter(supplier=supplier)
    agg = qs.aggregate(total=Sum("amount"))
    return _q2(agg["total"] or Decimal("0"))


def _create_entry(*, tenant, customer, supplier, entry_type, amount, notes="",
                  bill=None, due_date=None, created_by=None) -> LedgerEntry:
    if (customer is None) == (supplier is None):
        raise ValidationError("Exactly one of customer / supplier is required.")
    if customer is not None and customer.tenant_id != tenant.id:
        raise ValidationError("Customer does not belong to this tenant.")
    if supplier is not None and supplier.tenant_id != tenant.id:
        raise ValidationError("Supplier does not belong to this tenant.")
    amount = _q2(Decimal(str(amount)))
    balance_after = _q2(party_balance(tenant, customer, supplier) + amount)
    return LedgerEntry.objects.create(
        tenant=tenant,
        customer=customer,
        supplier=supplier,
        entry_type=entry_type,
        bill=bill,
        amount=amount,
        balance_after=balance_after,
        due_date=due_date,
        notes=notes,
        created_by=created_by,
    )


def record_receivable(*, tenant, customer: Customer, amount, bill=None,
                      notes="", created_by=None) -> LedgerEntry:
    """A credit sale: customer now owes more."""
    if amount <= 0:
        raise ValidationError("Receivable amount must be positive.")
    return _create_entry(
        tenant=tenant,
        customer=customer,
        supplier=None,
        entry_type=LedgerEntry.ENTRY_SALE,
        amount=amount,
        bill=bill,
        notes=notes,
        created_by=created_by,
    )


def record_payable(*, tenant, supplier: Supplier, amount, notes="", created_by=None) -> LedgerEntry:
    """A credit purchase: we now owe the supplier more."""
    if amount <= 0:
        raise ValidationError("Payable amount must be positive.")
    return _create_entry(
        tenant=tenant,
        customer=None,
        supplier=supplier,
        entry_type=LedgerEntry.ENTRY_PURCHASE,
        amount=amount,
        notes=notes,
        created_by=created_by,
    )


def unpaid_dues(tenant, customer=None, supplier=None):
    """Due entries (sale/purchase) with a remaining balance, oldest first (FIFO)."""
    qs = LedgerEntry.objects.filter(tenant=tenant).select_for_update()
    if customer is not None:
        qs = qs.filter(customer=customer, entry_type=LedgerEntry.ENTRY_SALE)
    else:
        qs = qs.filter(supplier=supplier, entry_type=LedgerEntry.ENTRY_PURCHASE)
    dues = []
    for entry in qs.order_by("created_at", "id"):
        remaining = _q2(entry.amount - entry.allocated_amount)
        if remaining > 0:
            entry._remaining = remaining
            dues.append(entry)
    return dues


@transaction.atomic
def record_khata_payment(*, tenant, customer=None, supplier=None, amount,
                         mode=KhataPayment.MODE_CASH, reference="",
                         created_by=None) -> KhataPayment:
    """
    Record a payment and allocate it FIFO against the oldest unpaid dues.
    Raises ValidationError if the payment exceeds the outstanding balance.
    """
    if (customer is None) == (supplier is None):
        raise ValidationError("Exactly one of customer / supplier is required.")
    amount = _q2(Decimal(str(amount)))
    if amount <= 0:
        raise ValidationError("Payment amount must be positive.")

    dues = unpaid_dues(tenant, customer, supplier)
    total_due = _q2(sum((d._remaining for d in dues), Decimal("0")))
    if amount > total_due:
        raise ValidationError(
            f"Payment ({amount}) exceeds outstanding balance ({total_due})."
        )

    allocation = []
    remaining = amount
    for due in dues:
        if remaining <= 0:
            break
        take = min(due._remaining, remaining)
        due.allocated_amount = _q2(due.allocated_amount + take)
        due.save(update_fields=["allocated_amount"])
        allocation.append({"ledger_entry": due.id, "allocated": str(_q2(take))})
        remaining = _q2(remaining - take)

    payment = KhataPayment.objects.create(
        tenant=tenant,
        customer=customer,
        supplier=supplier,
        amount=amount,
        mode=mode,
        reference=reference,
        allocation=allocation,
        created_by=created_by,
    )
    # Mirror the payment in the ledger so statements stay complete.
    _create_entry(
        tenant=tenant,
        customer=customer,
        supplier=supplier,
        entry_type=LedgerEntry.ENTRY_PAYMENT,
        amount=-amount,
        notes=f"KhataPayment-{payment.id} {reference}".strip(),
        created_by=created_by,
    )
    return payment


def adjust_balance(*, tenant, customer=None, supplier=None, amount, notes="",
                   created_by=None) -> LedgerEntry:
    """Manual signed correction (e.g. khata refund on a return)."""
    return _create_entry(
        tenant=tenant,
        customer=customer,
        supplier=supplier,
        entry_type=LedgerEntry.ENTRY_PAY_ADJUST,
        amount=amount,
        notes=notes,
        created_by=created_by,
    )


def aging_report(tenant):
    """Outstanding receivables per customer bucketed by age of oldest unpaid dues."""
    from datetime import date

    today = date.today()
    result = []
    for customer in Customer.objects.filter(tenant=tenant, is_active=True).order_by("name"):
        dues = unpaid_dues(tenant, customer=customer)
        if not dues:
            continue
        buckets = {"0_30": Decimal("0"), "31_60": Decimal("0"), "61_90": Decimal("0"), "over_90": Decimal("0")}
        for due in dues:
            age = (today - due.created_at.date()).days
            if age <= 30:
                buckets["0_30"] += due._remaining
            elif age <= 60:
                buckets["31_60"] += due._remaining
            elif age <= 90:
                buckets["61_90"] += due._remaining
            else:
                buckets["over_90"] += due._remaining
        total = _q2(sum(buckets.values(), Decimal("0")))
        result.append(
            {
                "customer": customer.id,
                "customer_name": customer.name,
                "phone": customer.phone,
                "total_due": str(total),
                "buckets": {k: str(_q2(v)) for k, v in buckets.items()},
            }
        )
    return result
