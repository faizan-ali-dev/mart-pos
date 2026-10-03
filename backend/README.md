# Mart POS — Backend (Django + DRF)

Backend API for the Mart POS MVP: retail billing with thermal receipts, inventory/stock
management, khata (credit ledger), WhatsApp notifications, multi-tenant user management,
and an owner dashboard via Django admin + reporting endpoints.

Spec: [`../mvp-feature-spec.md`](../mvp-feature-spec.md)

## Stack

- Python 3.12, Django 5.x, Django REST Framework, django-cors-headers
- Auth: DRF TokenAuthentication (`POST /api/auth/login/`)
- Dev DB: SQLite. Production-ready for Postgres via `DATABASE_URL`

## Setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo   # demo data (DEV ONLY passwords, see below)
.venv/bin/python manage.py runserver   # http://127.0.0.1:8000
```

Admin dashboard: http://127.0.0.1:8000/admin/

## Demo logins (dev only — change in production)

| Username   | Password   | Role     |
|------------|------------|----------|
| admin      | admin123   | superuser|
| owner      | demo123    | owner    |
| manager    | demo123    | manager  |
| cashier    | demo123    | cashier  |

## Tests

```bash
.venv/bin/python manage.py test
```

## Environment variables

| Variable                  | Default                | Notes                                    |
|---------------------------|------------------------|------------------------------------------|
| `DJANGO_SECRET_KEY`       | dev-only insecure key  | **Set this in production**               |
| `DJANGO_DEBUG`            | `1`                    | Set `0` in production                    |
| `DJANGO_ALLOWED_HOSTS`    | `*`                    | Comma-separated                          |
| `DATABASE_URL`            | `sqlite:///db.sqlite3` | Or `postgres://user:pass@host:5432/db`   |
| `WHATSAPP_PROVIDER`       | `dummy`                | `meta` for the official Meta Cloud API   |
| `WHATSAPP_TOKEN`          | —                      | Meta Cloud API token (provider=meta)     |
| `WHATSAPP_PHONE_NUMBER_ID`| —                      | Meta phone number ID (provider=meta)     |

## Key design decisions

- **Multi-tenancy:** every record carries `tenant_id`; all API querysets are filtered to
  `request.user.tenant`. One tenant = one mart business.
- **Bills are immutable:** no update/delete at model, API, or admin level. Offline-first
  sync can therefore never conflict — bills are only ever created.
- **Atomic bill creation:** stock validation → totals → bill/lines/payments → stock
  deduction → khata receivable, all in one transaction with row locks.
- **Weighted-average cost:** each GRN line updates `Product.purchase_price` from the
  previous on-hand quantity and cost.
- **Khata payments allocate FIFO** against the oldest unpaid dues; allocation detail is
  stored on the payment.
- **WhatsApp** goes through a swappable provider interface (`notifications/providers.py`).
  Dev default is a dummy provider that logs sends as `simulated` — no real messages leave
  the machine without Meta credentials.

## API overview (prefix `/api/`)

- `auth/login/` (POST), `auth/me/` (GET), `auth/logout/` (POST)
- `tenants/tenants/`, `tenants/stores/`, `tenants/users/` (+ `{id}/reset-password/`)
- `catalog/categories/`, `catalog/brands/`, `catalog/products/` (`?search=`, `?barcode=`)
- `inventory/locations/`, `inventory/stock-levels/` (`?low_stock=true`),
  `inventory/purchase-orders/`, `inventory/grns/` (POST receives stock),
  `inventory/adjustments/`, `inventory/batches/`, `inventory/alerts/`
- `billing/bills/` (GET `?date=`, POST), `billing/bills/<id>/` (GET only),
  `billing/parked-bills/`, `billing/shifts/` (+ `<id>/close/`), `billing/returns/`
- `khata/customers/`, `khata/suppliers/`, `khata/ledger/` (`?customer=`, `?supplier=`),
  `khata/payments/` (POST applies FIFO), `khata/aging/`
- `notifications/templates/`, `notifications/messages/`, `notifications/rules/`,
  `notifications/send-test/` (POST)
- `reports/daily-summary/` (`?date=`)
- `catalog/price-slabs/` (CRUD, `?product=`), `reports/wholesale-summary/` (`?date=`, `?customer=`)
- `expenses/categories/` (CRUD), `expenses/expenses/` (CRUD, `?from=&to=&category=`),
  `expenses/summary/` (`?from=&to=` → `{total, by_category[]}`)
- `promotions/promotions/` (CRUD, `?promo_type=`, `?is_active=`)
- `billing/payouts/` (GET, POST — auto-attaches to your open shift)
- `reports/sales/` (`?from=&to=&search=&category=&sale_type=&payment_mode=&export=`),
  `reports/purchases/` (`?from=&to=&supplier=&search=&export=`),
  `reports/profit/` (`?from=&to=`), `reports/daily-summary/` (now incl.
  `expenses_total`, `payouts_total`, `net_profit`)

### Wholesale pricing

Customers have `customer_type` (`retail`/`wholesale`) and `wholesale_discount_percent`.
A bill is wholesale when `sale_type="wholesale"` is passed, or auto-detected when the
bill's customer is wholesale-type (explicit `sale_type` always wins).

Rules (all inside the atomic bill transaction):

1. **Rate:** each line uses `product.wholesale_price`, falling back to `retail_price`
   when the wholesale price is 0/unset.
2. **Volume slabs:** the `PriceSlab` with the highest `min_qty <= line qty` gives a
   line discount. Slab and manual line discounts are **not stacked — the larger wins**.
   The applied slab is stored on the line (`slab_discount_percent`) and returned as
   `applied_rate` / `slab_discount_percent` in the bill response.
3. **Customer discount:** `customer.wholesale_discount_percent` applies automatically at
   bill level and **stacks additively** with any manual bill discount, **capped at 50%**
   of subtotal in total. (Manual bill discounts still need a reason; the automatic one
   is labelled in `bill_discount_reason`.)
4. Credit-limit enforcement works unchanged for wholesale khata sales — wholesale
   customers just get higher limits.

Seed demo wholesale data (idempotent, needs `seed_demo` first):

```bash
.venv/bin/python manage.py seed_wholesale
```

This marks "Kamran Sheikh" wholesale (limit 200000, 2% auto discount), sets
wholesale prices and volume slabs on 5 demo products (e.g. Dalda Cooking Oil:
24+ → 3%, 60+ → 5%).

`GET /api/reports/wholesale-summary/` returns wholesale-only `{date, bills_count,
total_sales, by_customer[], top_items[], margin_estimate}`. `margin_estimate` allocates
the bill-level discount to lines proportionally and uses the current weighted-average
`purchase_price`, so treat it as an estimate.

### Promotion engine

`POST /api/promotions/promotions/` (owner/manager). Types: `bogo` (buy X get Y
free), `bundle` (discount % on two products bought together), `percent` / `flat`
(bill-level). Scheduling: `start_date`/`end_date`, `days_of_week` (0=Monday..6=Sunday,
empty = every day), `time_start`/`time_end`. Only promotions live *right now* apply.

Evaluated inside the atomic bill transaction:

1. **bogo:** for every `buy_qty` of `buy_product` in the cart → `get_qty` of
   `get_product` added as a FREE line (`is_free=true`, rate 0). Stock is still
   deducted; the free grant is capped at available stock ("while stocks last").
2. **bundle:** cart must contain `buy_qty` of `buy_product` AND `get_qty` of
   `get_product` → `discount_percent` off those lines. Promo vs existing
   (slab/manual) line discount: **larger wins, never stacked**.
3. **percent/flat:** applies when subtotal >= `min_bill_amount`. Only the **best**
   bill-level promo applies. It stacks additively with manual + wholesale
   auto-discounts, still **capped at 50%** of subtotal in total.

The bill response carries `applied_promotions: [{id, name, type, description}]`
(also stored on the bill for receipts/reprints).

### Expenses (kharcha)

`expenses/categories/` + `expenses/expenses/` (owner/manager). Track rent, bijli,
salaries… per day with payment mode and notes. `expenses/summary/?from=&to=`
gives `{total, by_category[]}`. Expenses feed the profit report and the
daily-summary's `net_profit`.

### Cash payouts

`POST /api/billing/payouts/` `{amount, purpose: supplier_payment|expense|other,
supplier?, notes?}` — cash out of the drawer, auto-attached to your open shift
(400 when there is none). `supplier_payment` also records a khata payment
against the supplier (FIFO, cannot exceed the payable). Payouts reduce the
shift's `expected_cash`: opening + cash sales − cash refunds − payouts.

### Filtered reports + CSV/Excel export

- `GET /api/reports/sales/` — line-level sales with `?from=&to=&search=`
  (bill no / product / SKU) `&category=&sale_type=&payment_mode=`.
- `GET /api/reports/purchases/` — GRN lines with `?from=&to=&supplier=&search=`.
- Both paginate as JSON by default; add `?export=csv` or `?export=xlsx` for a
  file download of **all** filtered rows (`Content-Disposition: attachment`).
  (Named `export`, not `format`: DRF reserves `?format=` for content negotiation.)
- `GET /api/reports/profit/?from=&to=` → `{sales_total, returns_total,
  net_sales, cogs_estimate, gross_profit, expenses_total, payouts_total,
  net_profit}`. `cogs_estimate` uses each product's *current* weighted-average
  cost (an estimate; free bogo lines count as cost too).

Seed growth-module demo data (idempotent, needs `seed_demo` first):

```bash
.venv/bin/python manage.py seed_growth
```

Creates a bogo promo (buy 2 cooking oil → 1 salt free), a weekend 5%-over-2000
promo, expense categories + 3 sample expenses, and 1 sample payout.

### Bill create payload

```json
{
  "lines": [{"product": 1, "qty": "2", "discount_percent": "10.00"}],
  "payments": [{"mode": "cash", "amount": "180.00"}, {"mode": "card", "amount": "20.00"}],
  "bill_discount_amount": "0.00",
  "bill_discount_reason": "",
  "customer": 3,
  "tendered": "500.00",
  "shift": 1,
  "sale_type": "wholesale",
  "notes": ""
}
```

Payment modes: `cash`, `card`, `bank_transfer`, `khata` (requires `customer`).
Response is the full bill including `bill_no`, `grand_total`, and `change_due`.
Omit `sale_type` (or pass `null`) to auto-detect from the customer's type.
