import { fmtRs, modeLabel } from '../api.js';
import { numToWordsPKR } from '../utils/words.js';

/**
 * 80mm thermal receipt. Rendered inside a `.print-area` div;
 * print CSS (@media print) shows only that area at 80mm width.
 */
export function Receipt({ bill, shop }) {
  const b = bill || {};
  const lines = b.lines || b.items || [];
  const payments = b.payments || [];
  const no = b.bill_no || b.number || b.code || b.id || '—';
  const dt = b.created_at || b.date || new Date().toISOString();
  const customer = b.customer || {};
  const custName = typeof customer === 'string' ? customer : customer.name;

  const lineName = (l) => l.product_name || l.name || l.product?.name || 'Item';
  const lineQty = (l) => Number(l.qty ?? l.quantity ?? 0);
  const lineRate = (l) => Number(l.rate ?? l.price ?? l.unit_price ?? 0);
  const lineTotal = (l) => Number(l.total ?? l.line_total ?? lineQty(l) * lineRate(l));
  const lineDisc = (l) => Number(l.discount_amount ?? l.discount ?? 0);

  return (
    <div className="receipt">
      <div className="r-center r-shop">{shop?.name || 'My Mart'}</div>
      {shop?.address && <div className="r-center">{shop.address}</div>}
      {shop?.phone && <div className="r-center">📞 {shop.phone}</div>}
      <div className="r-sep" />
      <div className="r-row"><span>Bill: {no}</span><span>{new Date(dt).toLocaleString('en-PK')}</span></div>
      {b.cashier_name && <div className="r-row"><span>Cashier: {b.cashier_name}</span></div>}
      {custName && <div className="r-row"><span>Customer: {custName}</span></div>}
      <div className="r-sep" />
      {lines.map((l, i) => (
        <div key={i} className="r-item">
          <div className="r-row"><span>{lineName(l)} {l.is_free ? <span className="r-free">FREE 🎁</span> : null}</span><span>{fmtRs(lineTotal(l))}</span></div>
          <div className="r-row r-dim"><span>{lineQty(l)} × {fmtRs(lineRate(l))}{lineDisc(l) > 0 ? `  (−${fmtRs(lineDisc(l))})` : ''}</span></div>
        </div>
      ))}
      <div className="r-sep" />
      <div className="r-row"><span>Subtotal</span><span>{fmtRs(b.subtotal ?? lines.reduce((s, l) => s + lineTotal(l), 0))}</span></div>
      {Number(b.bill_discount_amount || b.discount_total || 0) > 0 && (
        <div className="r-row"><span>Discount{b.bill_discount_reason ? ` (${b.bill_discount_reason})` : ''}</span><span>−{fmtRs(b.bill_discount_amount || b.discount_total)}</span></div>
      )}
      <div className="r-row r-total"><span>TOTAL</span><span>{fmtRs(b.grand_total ?? b.total)}</span></div>
      <div className="r-sep" />
      {payments.map((p, i) => (
        <div className="r-row" key={i}><span>{modeLabel(p.mode)} {p.tendered ? `(tendered ${fmtRs(p.tendered)})` : ''}</span><span>{fmtRs(p.amount)}</span></div>
      ))}
      {Number(b.change_due || 0) > 0 && (
        <div className="r-row"><span>Change (واپسی)</span><span>{fmtRs(b.change_due)}</span></div>
      )}
      {customer && Number(customer.balance ?? customer.outstanding ?? 0) > 0 && (
        <div className="r-row"><span>Khata balance (بقایا)</span><span>{fmtRs(customer.balance ?? customer.outstanding)}</span></div>
      )}
      <div className="r-sep" />
      <div className="r-center">{shop?.footer || '7 din ke andar receipt ke baghair wapsi nahi hogi.'}</div>
      <div className="r-center r-dim">شکریہ — Thank you for shopping!</div>
    </div>
  );
}

/** Printable khata ledger statement (A4-ish). */
export function Statement({ customer, entries, shop }) {
  const list = entries || [];
  const bal = (e) => Number(e.balance ?? e.running_balance ?? 0);
  return (
    <div className="statement">
      <div className="s-head">
        <div>
          <h2>{shop?.name || 'My Mart'}</h2>
          <div className="dim">{shop?.address} {shop?.phone && `· ${shop.phone}`}</div>
        </div>
        <div className="s-title">Khata Statement (کھاتہ)</div>
      </div>
      <div className="s-cust">
        <div><strong>{customer?.name}</strong> · {customer?.phone}</div>
        <div>Credit limit: {fmtRs(customer?.credit_limit || 0)} · <strong>Balance: {fmtRs(customer?.balance ?? 0)}</strong></div>
      </div>
      <table className="s-table">
        <thead><tr><th>Date</th><th>Description</th><th>Bill</th><th>Payment</th><th>Balance</th></tr></thead>
        <tbody>
          {list.map((e, i) => (
            <tr key={e.id || i}>
              <td>{(e.date || e.created_at || '').slice(0, 10)}</td>
              <td>{e.description || e.narration || e.type}</td>
              <td>{Number(e.debit ?? e.bill_amount ?? (e.type === 'bill' ? e.amount : 0)) > 0 ? fmtRs(e.debit ?? e.bill_amount ?? e.amount) : '—'}</td>
              <td>{Number(e.credit ?? e.payment_amount ?? (e.type === 'payment' ? e.amount : 0)) > 0 ? fmtRs(e.credit ?? e.payment_amount ?? e.amount) : '—'}</td>
              <td>{fmtRs(bal(e))}</td>
            </tr>
          ))}
          {list.length === 0 && <tr><td colSpan={5} className="dim">No entries yet.</td></tr>}
        </tbody>
      </table>
      <div className="s-foot dim">Generated {new Date().toLocaleString('en-PK')} · {shop?.name}</div>
    </div>
  );
}

/**
 * A4 invoice (generalized). Rendered inside `.print-area`;
 * print CSS shows only that area at full width (see .invoice styles).
 * Props: { bill, shop, invoiceTitle } — title is "TAX INVOICE" for wholesale,
 * "RETAIL INVOICE" for retail. Reads applied_rate / slab_discount_percent
 * defensively — backend may or may not include them; falls back to rate +
 * discount_amount.
 */
export function Invoice({ bill, shop, invoiceTitle }) {
  const b = bill || {};
  const lines = b.lines || b.items || [];
  const payments = b.payments || [];
  const no = b.bill_no || b.number || b.code || b.id || '—';
  const dt = b.created_at || b.date || new Date().toISOString();
  const customer = b.customer || {};
  const custName = typeof customer === 'string' ? customer : customer.name;

  const lineName = (l) => l.product_name || l.name || l.product?.name || 'Item';
  const lineQty = (l) => Number(l.qty ?? l.quantity ?? 0);
  const lineRate = (l) => Number(l.applied_rate ?? l.rate ?? l.price ?? l.unit_price ?? 0);
  const lineTotal = (l) => Number(l.total ?? l.line_total ?? lineQty(l) * lineRate(l));
  const lineDiscPct = (l) => Number(l.slab_discount_percent ?? l.discount_percent ?? 0);
  const lineDiscAmt = (l) => Number(l.discount_amount ?? l.discount ?? 0);

  const subtotal = Number(b.subtotal ?? lines.reduce((s, l) => s + lineTotal(l), 0));
  const grandTotal = Number(b.grand_total ?? b.total ?? subtotal);

  return (
    <div className="invoice">
      <div className="inv-head">
        <div>
          <div className="inv-shop">{shop?.name || 'My Mart'}</div>
          {shop?.address && <div>{shop.address}</div>}
          {shop?.phone && <div>📞 {shop.phone}</div>}
        </div>
        <div className="inv-title">{invoiceTitle || 'TAX INVOICE'}</div>
      </div>

      <div className="inv-meta">
        <div className="inv-billto">
          <div className="inv-sec-label">Bill To</div>
          <div className="inv-cust-name">{custName || 'Walk-in wholesale'}</div>
          {customer.phone && <div>📞 {customer.phone}</div>}
          {customer.address && <div>{customer.address}</div>}
          {customer.cnic && <div>CNIC: {customer.cnic}</div>}
        </div>
        <div className="inv-billinfo">
          <div className="inv-sec-label">Invoice Details</div>
          <div><strong>Invoice No:</strong> {no}</div>
          <div><strong>Date:</strong> {new Date(dt).toLocaleString('en-PK')}</div>
          {b.cashier_name && <div><strong>Salesman:</strong> {b.cashier_name}</div>}
        </div>
      </div>

      <table className="inv-table">
        <thead>
          <tr><th>#</th><th>Item</th><th>Qty</th><th>Rate</th><th>Disc.</th><th>Amount</th></tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td>{lineName(l)} {l.is_free ? <span className="r-free">FREE 🎁</span> : null}</td>
              <td>{lineQty(l)}</td>
              <td>{fmtRs(lineRate(l))}</td>
              <td>
                {lineDiscPct(l) > 0 ? `${lineDiscPct(l)}%` : ''}
                {lineDiscAmt(l) > 0 ? ` ${fmtRs(lineDiscAmt(l))}` : ''}
                {lineDiscPct(l) <= 0 && lineDiscAmt(l) <= 0 ? '—' : ''}
              </td>
              <td>{fmtRs(lineTotal(l))}</td>
            </tr>
          ))}
          {lines.length === 0 && <tr><td colSpan={6}>No items.</td></tr>}
        </tbody>
      </table>

      <div className="inv-totals">
        <div className="inv-row"><span>Subtotal</span><span>{fmtRs(subtotal)}</span></div>
        {Number(b.bill_discount_amount || b.discount_total || 0) > 0 && (
          <div className="inv-row">
            <span>Bill discount{b.bill_discount_reason ? ` (${b.bill_discount_reason})` : ''}</span>
            <span>−{fmtRs(b.bill_discount_amount || b.discount_total)}</span>
          </div>
        )}
        <div className="inv-row grand"><span>Grand Total</span><span>{fmtRs(grandTotal)}</span></div>
        <div className="inv-words"><strong>Amount in words:</strong> {numToWordsPKR(grandTotal)}</div>
      </div>

      <div className="inv-payments">
        {payments.map((p, i) => (
          <div className="inv-row" key={i}><span>{modeLabel(p.mode)}</span><span>{fmtRs(p.amount)}</span></div>
        ))}
        {Number(b.change_due || 0) > 0 && (
          <div className="inv-row"><span>Change (واپسی)</span><span>{fmtRs(b.change_due)}</span></div>
        )}
      </div>

      <div className="inv-foot">
        <div>{shop?.footer || 'Goods once sold will not be taken back without invoice.'}</div>
        <div className="inv-sign">Received by: ____________________ &nbsp;&nbsp; For {shop?.name || 'My Mart'}: ____________________</div>
      </div>
    </div>
  );
}

/** Backwards-compatible wholesale wrapper: always renders a TAX INVOICE. */
export function WholesaleInvoice({ bill, shop }) {
  return <Invoice bill={bill} shop={shop} invoiceTitle="TAX INVOICE" />;
}
