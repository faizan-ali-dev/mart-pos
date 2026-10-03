# Mart POS — MVP

Web-based, offline-first Point of Sale for Pakistani marts — retail billing, inventory/stock, khata (credit ledger), WhatsApp notifications, user management. Built to be sold as SaaS to mart owners.

**Stack:** Django 5 + DRF (backend) · React 18 + Vite PWA (frontend) · SQLite dev / PostgreSQL prod

## Project layout

```
pos-mart/
├── mvp-feature-spec.md   # full feature specification (v1.0)
├── README.md             # this file
├── backend/              # Django API + admin  (see backend/README.md)
└── frontend/             # React PWA          (see frontend/README.md)
```

## Quick start (5 minutes)

**1. Backend**
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo      # demo tenant, products, users
.venv/bin/python manage.py runserver       # → http://127.0.0.1:8000
```
- API: `http://127.0.0.1:8000/api/` · Admin: `http://127.0.0.1:8000/admin/`
- Demo logins (dev only): `owner` / `manager` / `cashier` → password `demo123`; superuser `admin` → `admin123`

**2. Frontend**
```bash
cd frontend
cp .env.example .env        # VITE_API_URL defaults to http://localhost:8000
npm install
npm run dev                 # → http://localhost:5173
```
Login with a demo user above. Open a **shift** first (Shifts page) — billing requires it.

## What's included

- **Billing terminal** — barcode/scan search, cart, per-line + bill discounts, cash/card/bank/khata/split payments, tendered→change, hold & recall parked bills, returns, shift open/close with cash reconciliation, 80mm thermal receipt print (Urdu+English)
- **Inventory** — product master (SKU/barcode, Urdu names), CSV import, GRN stock-in with weighted-average cost, adjustments (damage/expiry/theft/found, approval-gated), low-stock / expiry / dead-stock alerts, barcode labels
- **Khata** — customer & supplier ledgers, credit sales, FIFO payment allocation, credit limits, aging report (30/60/90+), printable statements
- **Wholesale** — customer types (retail/wholesale), wholesale pricing, volume discount slabs, wholesale billing mode, TAX INVOICE print with amount-in-words, wholesale reports & dashboard split
- **Growth** — kharcha/expense tracking, cash payouts from counter, promotion engine (BOGO, bundles, scheduled offers), filtered sales/purchase/profit reports with CSV/Excel export, weighing-scale weight input (Web Serial)
- **WhatsApp in-app config** — per-tenant settings UI (test/live mode, credentials, test number), provider reads DB, Meta template support, PK phone auto-format
- **Invoice printing** — A4 invoice (retail + wholesale) alongside 80mm thermal, per-tenant default + per-bill toggle
- **Users** — owner/manager manage users per tenant: roles, activate/deactivate, password reset (Settings → Users, plus Django admin)
- **Dashboard** — today's sales, payment-mode split, top items, alerts
- **WhatsApp** — receipt, khata payment, overdue reminder, low-stock & day-close summaries (simulated in dev; plug Meta Cloud API via env, see backend/README.md)
- **Offline** — products/customers cached locally; bills queue in localStorage when the API is unreachable and auto-sync (basic queue; full Dexie sync = Phase 2)

## Key design decisions

- **Bills are immutable** once created — no update/delete, which also eliminates offline sync conflicts by design.
- **Tenant-scoped everything** (`tenant_id`) — one database serves many marts (SaaS-ready).
- **Atomic billing** — stock check, totals, payments, stock deduction and khata entries happen in one DB transaction with row locks.

## Verified

- Backend: 140 automated tests green (`manage.py test`) — billing totals, stock deduction, GRN average cost, khata FIFO, shift reconciliation, tenant isolation, user permissions, wholesale pricing/slabs, promotions, payouts, expenses, report exports, tenant settings & WhatsApp config.
- Frontend: `npm run build` passes; PWA manifest + service worker generated.
- Live smoke test: login → open shift → create bill (totals/change/stock deduction verified via API).

## Phase 2 (not built yet)

Multi-branch · supplier auto-reorder · loyalty points · full Dexie offline sync · e-commerce integration · employee attendance/payroll.
