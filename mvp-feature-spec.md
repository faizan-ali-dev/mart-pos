# Mart POS — MVP Feature Specification

**Version:** 1.0 — 3 Oct 2026
**Stack:** Django + DRF (backend) · React + PWA (frontend) · PostgreSQL (server) · IndexedDB (local)
**MVP goal:** One mart, one billing counter — retail billing with thermal receipt printing, inventory/stock management, khata (credit ledger), WhatsApp notifications. **Offline-first.**

---

## Module 1 — Billing (POS Terminal)

### 1.1 Fast billing screen
- Barcode scanner input works as keyboard input — scan or type SKU, item is added instantly.
- Product search by name/SKU with live suggestions (works offline from the local product cache).
- Editable quantity per line; unit support (pcs, kg, litre) with decimal quantities.
- Cart shows: item, qty, rate, discount, line total; running bill total + item count.
- Cashier keyboard shortcuts: F2 search, F4 qty, F8 discount, F9 hold, F10 pay, Esc clear.

### 1.2 Payment modes
- Cash, Card, Bank transfer, **Khata (credit sale)**, Split (e.g. Rs 500 cash + rest on card).
- Cash: enter tendered amount → change due auto-calculated; round-off to nearest rupee (configurable).
- Khata payment requires selecting a customer → creates a receivable entry (see Module 3).

### 1.3 Discounts
- Per-line discount (% or flat Rs).
- Bill-level discount (% or flat Rs) with **mandatory reason** (audit trail).
- Per-role discount cap for cashiers (e.g. cashier max 5% without manager approval).

### 1.4 Hold / parked bills
- Park a bill mid-sale (customer forgot wallet), recall later by token/bill number.
- Parked bills listed on the terminal; reminder if parked longer than configurable hours.

### 1.5 Returns & refunds
- Return against original bill (preferred) or without bill (manager approval required).
- Returned qty goes back into stock automatically; refund via original payment mode or store credit.
- Reason mandatory; returns appear in the daily sales report as negative lines.

### 1.6 Receipt printing
- 80mm thermal printer via browser print (print CSS) for MVP; ESC/POS direct printing (QZ Tray) as the upgrade path for cash-drawer kick.
- Receipt content: shop name/logo, address, phone, bill no, date/time, cashier name, line items, discounts, totals, payment mode, khata balance (for credit customers), footer note (e.g. "7 din ke andar receipt ke baghair wapsi nahi").
- Urdu + English text support. Reprint any bill from history.

### 1.7 Shift & cash drawer
- Open shift: record opening cash. Close shift: system shows expected cash (opening + cash sales − payouts); cashier enters counted cash; difference logged with reason.
- Printable shift-wise sales summary.

### 1.8 Offline behavior (critical)
- Every bill is saved to the **local DB first**, printed immediately, then synced to the server in background.
- Sync queue visible on screen ("3 bills pending sync").
- Conflict rule: bills are **immutable** once created — by design there is nothing to merge, so no sync conflicts.

---

## Module 2 — Inventory & Stock Management

### 2.1 Product master
Fields: SKU/barcode (auto-generate internal SKU if none), name (EN + Urdu), category, brand, unit, purchase price, retail price, wholesale price (stored now, used in Phase 2), tax %, reorder level, track-expiry flag, active/inactive.
- Bulk import via CSV/Excel.
- Duplicate barcode prevention.

### 2.2 Stock-in (purchasing)
- Purchase Order → Goods Received Note (GRN): supplier, supplier invoice no, items with qty + purchase rate + expiry date (for tracked items).
- GRN updates stock levels and the **weighted-average cost** automatically.
- Supplier-wise purchase history.

### 2.3 Stock-out & adjustments
- Sales auto-deduct stock at billing time.
- Manual adjustment types: damage, expiry write-off, theft/loss, found stock — each with reason + manager approval.
- Stock transfer between shop floor and godown (two locations within one store in MVP).

### 2.4 Alerts & reports
- Low-stock alert (qty ≤ reorder level) on dashboard + WhatsApp to owner.
- Expiry alerts: items expiring within 30 / 60 / 90 days.
- Dead-stock report: no sale in last 60/90 days.
- Stock valuation report (qty × average cost); category-wise sales & margin report.

### 2.5 Barcode labels
- Print barcode stickers for products without a manufacturer barcode (shelf labels, weigh-scale items).

---

## Module 3 — Khata Management (Credit Ledger)

### 3.1 Customer khata (receivables)
- Customer profile: name, phone (unique), address, CNIC (optional), credit limit, notes.
- Credit sale from billing creates a khata entry linked to the bill.
- Payments: cash/card/bank against khata; partial payments allowed; allocation = **oldest due first (FIFO)**.
- Running balance per customer; over-limit sales blocked or warned (configurable).

### 3.2 Supplier khata (payables)
- Mirror of customer khata: credit purchases create payable entries; payments to suppliers recorded with mode + reference.

### 3.3 Statements & aging
- Per-customer ledger statement: date-wise bills, payments, balance — printable and sendable on WhatsApp as PDF.
- Aging report: 0–30 / 31–60 / 61–90 / 90+ days outstanding, per customer and consolidated.
- Reminder workflow: overdue list → one-tap WhatsApp reminder (see Module 4).

---

## Module 4 — WhatsApp Integration

### 4.1 Automated messages
| Trigger | Recipient | Content |
|---|---|---|
| Bill completed | Customer (opt-in) | Digital receipt + khata balance |
| Khata payment received | Customer | Payment receipt + remaining balance |
| Due / overdue | Customer | Polite reminder with outstanding amount |
| Low stock / expiry | Owner | Alert with product list |
| Day close | Owner | Sales summary: total, cash/card/khata split, top items |

### 4.2 Technical approach
- **Recommended: official WhatsApp Business Cloud API (Meta)** — reliable enough for a product you sell to others. Free tier: 1,000 service conversations/month; utility/marketing templates billed per message beyond that.
- Keep the provider behind an interface so a cheaper third-party gateway can be swapped in later if needed.
- Every send logged with delivery status; failures retried with backoff.

### 4.3 Consent & templates
- Customer opt-in captured at billing / customer creation ("receipt on WhatsApp?").
- Pre-approved message templates (Meta requirement); Urdu + English versions.
- Global on/off plus per-message-type toggles in settings.

---

## Cross-cutting requirements
- **Multi-tenancy:** every record scoped by `tenant_id` (one mart = one tenant) from day one.
- **Roles & permissions:** Owner (everything), Manager (reports + approvals), Cashier (billing only).
- **User management:** owner/manager creates and manages multiple users per tenant — set role, activate/deactivate, reset password. Full UI in Settings → Users, plus Django admin.
- **Audit log:** who created/edited/deleted what and when — especially discounts, returns, stock adjustments, khata edits.
- **Offline-first:** local-first writes, background sync, immutable bills to avoid conflicts.
- **Urdu support:** product names, receipts, and cashier-facing UI labels.

---

---

## Module 5 — Wholesale (built 2026-10-03)

- **Customer types:** retail / wholesale per customer; wholesale customers get higher credit limits and an automatic bill-level `wholesale_discount_percent`.
- **Wholesale pricing:** each product has a `wholesale_price`; wholesale bills use it automatically (falls back to retail price when 0).
- **Volume slabs (PriceSlab):** per product, tiers like "24+ units → 3% off, 60+ → 5% off". Best matching tier wins; slab and manual line discount are not stacked (larger wins).
- **Billing:** sale type retail/wholesale toggle; auto-detects wholesale when the customer is wholesale-type. Customer auto-discount stacks additively with manual bill discount, capped at 50%.
- **Wholesale invoice:** TAX INVOICE print format with bill-to block, item table, amount-in-words (lakh/crore), signature lines.
- **Reports:** wholesale summary (totals, by-customer, top items, margin estimate), retail-vs-wholesale split on dashboard.

---

## Module 6 — Growth features (built 2026-10-03)

- **Kharcha tracking:** expense categories + expenses (date, amount, payment mode, notes); summary by category; feeds net-profit calculation.
- **Cash payouts:** record payouts from the counter (supplier payment / expense / other) against the open shift; supplier payouts auto-create khata payments (FIFO); shift close deducts payouts from expected cash.
- **Promotion engine:** buy-1-get-1 (free lines, stock deducted), bundle discounts, bill-level % / flat promos with min-bill, scheduling (dates, weekdays, time windows). Best bill-level promo wins; 50% total discount cap preserved. Applied promos stored on the bill + shown on receipts (FREE badge).
- **Reports with filters + export:** sales report (date, search, category, sale_type, payment mode), purchase report (date, supplier, search), profit report (sales, COGS estimate, gross, expenses, payouts, net profit). CSV + Excel (xlsx) download via `?export=csv|xlsx`.
- **Weighing scale:** billing supports kg/litre items with a "read scale" button (Web Serial API, Chrome/Edge) + manual weight fallback. Needs a serial/USB scale on the billing PC.

## Out of scope — Phase 2 (remaining)
Multi-branch support · employee attendance/payroll · supplier auto-reorder · loyalty points · full Dexie offline sync · e-commerce integration.

---

## Appendix — Suggested Django apps & core models
- `tenants` — Tenant, Store, role-based users
- `catalog` — Category, Brand, Product, ProductBarcode
- `inventory` — StockLocation, StockLevel, PurchaseOrder, GRN, StockAdjustment, Batch (expiry)
- `billing` — Bill, BillLine, Payment, ParkedBill, Shift
- `khata` — Customer, Supplier, LedgerEntry, KhataPayment
- `notifications` — WhatsAppTemplate, MessageLog, NotificationRule
- `reports` — precomputed daily summaries
