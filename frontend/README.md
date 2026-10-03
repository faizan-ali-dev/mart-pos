# Mart POS — Frontend (React)

Billing terminal, inventory, khata ledger, shifts, user management and settings for the Mart POS MVP.
Stack: **React 18 + Vite + react-router-dom + axios**, plain CSS. PWA-ready (manifest + service worker).

## Setup

```bash
cd frontend
cp .env.example .env        # set VITE_API_URL to your Django backend
npm install
npm run dev                # → http://localhost:5173
```

## Build

```bash
npm run build              # outputs to dist/
npm run preview            # serve the production build locally
```

`npm run build` must pass with no errors.

## Backend contract

Base URL comes from `VITE_API_URL` (default `http://localhost:8000`); every call goes to `<base>/api/...`.

- Auth: `POST /api/auth/login/` `{username,password}` → `{token, user}`; client sends `Authorization: Token <token>`.
- Catalog: `/api/catalog/products/` (`?search=`), `/api/catalog/categories/`
- Inventory: `/api/inventory/stock-levels/` (`?low_stock=true`), `/api/inventory/grns/` (POST `{supplier, supplier_invoice_no, lines:[{product,qty,purchase_rate,expiry_date}]}`), `/api/inventory/adjustments/` (POST `{product,location,qty_change,type,reason}`), `/api/inventory/alerts/`
- Billing: `/api/billing/bills/` (GET `?date=`, POST bill), `/api/billing/bills/<id>/`, `/api/billing/parked-bills/`, `/api/billing/shifts/` (+ `<id>/close/`)
- Khata: `/api/khata/customers/`, `/api/khata/suppliers/`, `/api/khata/ledger/` (`?customer=`), `/api/khata/payments/`, `/api/khata/aging/`
- Users (owner/manager only): `/api/tenants/users/` (GET/POST), `/api/tenants/users/<id>/` (PATCH), `/api/tenants/users/<id>/reset-password/` (POST)
- Notifications: `/api/notifications/templates/`, `/api/notifications/rules/`, `POST /api/notifications/send-test/`
- Reports: `/api/reports/daily-summary/` (`?date=`), `/api/reports/wholesale-summary/` (`?date=`, `?customer=`)
- Wholesale: `/api/catalog/price-slabs/` (CRUD `{product, min_qty, discount_percent}`); customer objects carry `customer_type` (`retail`|`wholesale`) and `wholesale_discount_percent`; `POST /api/billing/bills/` accepts `sale_type` (`retail`|`wholesale`), and bill lines may include `applied_rate` / `slab_discount_percent`

The UI is written defensively (DRF pagination `{results:[...]}` or plain arrays, tolerant field names) — see `src/api.js` `asList()`.

## Pages

| Route | Page |
|---|---|
| `/login` | Sign in (token stored in localStorage) |
| `/` | Dashboard — KPIs, payment split, top items, low-stock/expiry alerts |
| `/billing` | POS terminal — barcode search, cart, discounts, split payments, hold/recall, 80mm receipt print, shortcuts F2/F9/F10/Esc. **Wholesale mode**: Retail/Wholesale toggle, wholesale customers auto-flip the bill (WHOLESALE banner, wholesale rates, volume-slab badges), wholesale prints as TAX INVOICE |
| `/bills` | Bills history — filter by date, view (wholesale badge), reprint (invoice for wholesale) |
| `/wholesale` | **Wholesale** (owner/manager only) — price slabs per product, wholesale customers, wholesale report (totals, by-customer, top items, margin estimate) |
| `/inventory` | Products (+CSV import), stock levels, GRN, adjustments, alerts, categories |
| `/khata` | Customers + ledger + record payment + printable statement, aging report, suppliers |
| `/shifts` | Open/close shift with cash reconciliation, history |
| `/users` | User management — roles (owner/manager/cashier), activate/deactivate, reset password. Hidden from cashiers (friendly 403) |
| `/settings` | Shop profile, WhatsApp rules/templates/test, offline queue & cache |

## Offline behavior (basic, real)

- Products + customers are cached in `localStorage` (topbar **⟳ Refresh data** re-caches).
- If a bill POST fails with a **network error**, the payload is queued in `localStorage` (`pos_queue_bills`); the topbar shows the pending count.
- The queue auto-flushes on boot, on `online` events, and every 30s; **Settings → Data & offline** has a manual "Retry sync now".
- Bills are immutable once created, so queued bills never conflict.
- The service worker (`public/sw.js`) caches the app shell; **API traffic is never cached**.
- This is intentionally a simple queue — the full IndexedDB/Dexie background-sync engine is a documented Phase-2 upgrade.

## Printing

Receipts render inside a `.print-area` div; `@media print` CSS shows only that area at **80mm thermal width** (shop header, items, totals, payment modes, khata balance, Urdu+English footer). Khata statements print in a wider A4-ish layout. **Wholesale bills print as a TAX INVOICE** (A4-ish): invoice header, bill-to block, item table with rate/qty/discount/amount, totals, amount-in-words (Pakistani numbering — crore/lakh), signature lines. Use the browser print dialog → thermal printer (retail) or regular printer (wholesale invoice).

## Roles

`owner`/`manager` see everything. `cashier` sees Billing, Bills and Shifts only; `/users`, `/wholesale` and those nav items are hidden (direct visits get a friendly "Access restricted" card).

## Wholesale pricing (display rules)

- Wholesale mode: line rate = `wholesale_price` (falls back to `retail_price` when 0/unset).
- Volume slab = best tier with `min_qty <= qty`; **slab % and manual line % are never stacked** — the larger one wins.
- A wholesale customer's `wholesale_discount_percent` is pre-filled as the bill-level discount (display only — backend stays authoritative).
- Backend is the source of truth at bill creation: the UI reads `applied_rate` / `slab_discount_percent` from the response defensively.

## Known endpoint assumptions (for the backend team)

- Shop profile has **no backend endpoint** in the contract → stored in `localStorage` (Settings → Shop profile), used on receipts.
- Supplier payments are sent as `POST /api/khata/payments/ {supplier, amount, mode, reference}` — backend should accept `supplier` alongside `customer`.
- Open shift is detected as a shift with no `closed_at`; close-shift response may include `expected_cash`/`difference` (UI falls back gracefully).
- CSV product import posts products one-by-one from the browser (no bulk endpoint in the contract).
