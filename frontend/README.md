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
- Reports: `/api/reports/daily-summary/` (`?date=` — now also returns `expenses_total`, `payouts_total`, `net_profit`), `/api/reports/wholesale-summary/` (`?date=`, `?customer=`), `/api/reports/sales/` (`?from=&to=&search=&category=&sale_type=&payment_mode=&format=json|csv|xlsx`), `/api/reports/purchases/` (`?from=&to=&supplier=&search=&format=`), `/api/reports/profit/` (`?from=&to=` → `{sales_total, cogs_estimate, gross_profit, expenses_total, payouts_total, net_profit}`)
- Expenses (owner/manager): `/api/expenses/categories/` (CRUD), `/api/expenses/expenses/` (CRUD `?from=&to=&category=`), `/api/expenses/summary/` (`?from=&to=` → `{total, by_category[]}`)
- Payouts: `/api/billing/payouts/` (CRUD `{amount, purpose: supplier_payment|expense|other, supplier?, notes}` — auto-attaches to the open shift)
- Promotions (owner/manager): `/api/promotions/promotions/` (CRUD `{name, promo_type: bogo|bundle|percent|flat, buy_product, buy_qty, get_product, get_qty, discount_percent, discount_amount, min_bill_amount, start_date, end_date, days_of_week[0-6 Mon..Sun], time_start, time_end, is_active}`); bill create response includes `applied_promotions[]`, free lines carry `is_free: true` (rate 0)
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
| `/shifts` | Open/close shift with cash reconciliation, history, **cash payouts** (record supplier/expense payouts, deducted from expected cash) |
| `/expenses` | **Expenses** (owner/manager only) — expense records with date/category/mode filters, categories CRUD, summary cards |
| `/promotions` | **Promotions** (owner/manager only) — BOGO, bundle, % / flat bill discounts with scheduling (dates, weekdays, time range), active toggle |
| `/reports` | **Reports** (owner/manager only) — Sales / Purchases / Profit tabs, filters, **CSV + Excel export** |
| `/users` | User management — roles (owner/manager/cashier), activate/deactivate, reset password. Hidden from cashiers (friendly 403) |
| `/settings` | Shop profile, **WhatsApp connection (mode/token/test) + rules/templates/test**, **Printing (default print format)**, offline queue & cache |

## Offline behavior (basic, real)

- Products + customers are cached in `localStorage` (topbar **⟳ Refresh data** re-caches).
- If a bill POST fails with a **network error**, the payload is queued in `localStorage` (`pos_queue_bills`); the topbar shows the pending count.
- The queue auto-flushes on boot, on `online` events, and every 30s; **Settings → Data & offline** has a manual "Retry sync now".
- Bills are immutable once created, so queued bills never conflict.
- The service worker (`public/sw.js`) caches the app shell; **API traffic is never cached**.
- This is intentionally a simple queue — the full IndexedDB/Dexie background-sync engine is a documented Phase-2 upgrade.

## Printing

Receipts render inside a `.print-area` div; `@media print` CSS shows only that area. Two formats, switchable per bill via the 🧾 80mm / 📄 A4 toggle on the Billing and Bills pages (the toggle remembers the cashier's last choice; the tenant default comes from **Settings → Printing**):

- **80mm thermal receipt** — shop header, items, totals, payment modes, khata balance, Urdu+English footer. Use the browser print dialog → thermal printer.
- **A4 invoice** — full-width layout: invoice header, bill-to block, item table with rate/qty/discount/amount, totals, amount-in-words (Pakistani numbering — crore/lakh), signature lines. Wholesale bills print as **TAX INVOICE**, retail bills as **RETAIL INVOICE**. Use a regular printer.

Khata statements also print in a wider A4-ish layout.

## WhatsApp setup (in-app, no code changes)

**Settings → WhatsApp → WhatsApp connection** (owner only; managers see read-only):

1. **Mode** — *Testing (simulated)*: sends are logged, no real message leaves the machine. *Live — Meta Cloud API*: real WhatsApp messages.
2. **Live mode needs**: *Phone Number ID* and *Access Token* from **developers.facebook.com** → your app → **WhatsApp → API Setup**. The token field shows a masked value (`••••abcd`) once saved; leave it empty to keep the existing token, or press *Change* to enter a new one.
3. **Test mode** (recommended ON while trying): every message is forced to the *Test phone number* so no real customer gets a test message.
4. **Send test message** — shows which provider was actually used and the real recipient.

All values are stored server-side per tenant (`GET/PUT /api/tenants/settings/`), so after deploy each mart owner just fills them in here. If the backend settings endpoint isn't deployed yet, values fall back to browser-local storage with a warning.

**Meta notes:** business-initiated messages (e.g. khata reminders) require **Meta-approved message templates** — plain text only works inside the 24-hour customer-service window after the customer's last message. Keep template names in **Settings → WhatsApp → Templates** in sync with what Meta approved.

## Roles

`owner`/`manager` see everything. `cashier` sees Billing, Bills and Shifts only; `/users`, `/wholesale`, `/expenses`, `/promotions`, `/reports` and those nav items are hidden (direct visits get a friendly "Access restricted" card).

## Weighing scale (billing)

Cart lines for products with unit **kg / litre** show a **⚖ button** next to the qty. It uses the **Web Serial API** (`navigator.serial`): the cashier picks the scale's COM/USB port once, and the first numeric reading (9600 baud) is filled into qty. **Manual weight entry always works** as fallback — the qty field stays editable.

Hardware requirements (documented for the billing PC):
- A weighing scale with **serial (RS-232) or USB-serial output** (most commercial scales / "cashier scales" have this; check the scale prints or streams weight over COM port).
- **Chrome or Edge** browser (Web Serial is Chromium-only; Firefox/Safari show a clear error and fall back to manual entry).
- If the scale is unplugged or sends nothing within ~20s, the UI shows an error and the cashier types the weight manually.

## Reports & exports

Reports → Sales / Purchases / Profit tabs with date, search, category, supplier, sale-type and payment-mode filters. **Export CSV / Export Excel** buttons call the same endpoint with `?format=csv|xlsx`; the file downloads as a blob (`sales_YYYY-MM-DD.csv` etc., or the server's `Content-Disposition` filename when provided). Profit cards: sales, COGS estimate, gross profit, expenses, payouts, net profit — COGS uses each product's *current* weighted-average cost, so treat it as an estimate.

## Promotions (display rules)

Promotions are **never calculated in the frontend** — the backend applies them at bill creation (schedule-aware). After a bill is saved, the UI shows the response's `applied_promotions[]` as 🎁 chips, and lines with `is_free: true` render a green **FREE** badge on the receipt/invoice (rate 0).

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
