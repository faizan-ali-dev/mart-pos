import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg, isNetworkError, modeLabel } from '../api.js';
import { Modal, Field, Spinner, ErrorBox, EmptyState, Badge, PageHead } from '../components/ui.jsx';
import { Receipt, Invoice } from '../components/Receipt.jsx';
import { useAuth } from '../auth.jsx';
import { getShopProfile, getCachedProducts, getCachedCustomers, setCachedProducts, setCachedCustomers, queueBill, queueCount } from '../offline.js';

const pName = (p) => p?.name || p?.product_name || 'Item';
const pSku = (p) => p?.sku || p?.barcode || '';
/** Retail price (original behaviour). */
const pPrice = (p) => Number(p?.retail_price ?? p?.price ?? p?.sale_price ?? 0);
/** Effective selling rate: wholesale price in wholesale mode (falls back to retail). */
const rateOf = (p, saleType) => {
  if (saleType === 'wholesale') {
    const w = Number(p?.wholesale_price ?? 0);
    return w > 0 ? w : pPrice(p);
  }
  return pPrice(p);
};
/** Best volume-slab discount % for a product/qty (wholesale mode only). */
const slabPctFor = (productId, qty, slabs, saleType) => {
  if (saleType !== 'wholesale' || !slabs) return 0;
  const tiers = slabs[String(productId)] || [];
  let best = 0;
  for (const t of tiers) {
    if (Number(qty) >= Number(t.min_qty) && Number(t.discount_percent) > best) best = Number(t.discount_percent);
  }
  return best;
};
/** Line discount % = max(manual %, slab %) — never stacked. */
const linePct = (l, saleType, slabs) =>
  Math.max(Number(l.discount_percent || 0), slabPctFor(l.product?.id, l.qty, slabs, saleType));
const lineGross = (l, saleType) => Number(l.qty || 0) * rateOf(l.product, saleType);
const lineDisc = (l, saleType, slabs) =>
  Number(l.discount_amount || 0) + lineGross(l, saleType) * (linePct(l, saleType, slabs) / 100);
const lineNet = (l, saleType, slabs) => lineGross(l, saleType) - lineDisc(l, saleType, slabs);

export default function Billing() {
  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [cart, setCart] = useState([]);
  const [showPay, setShowPay] = useState(false);
  const [payments, setPayments] = useState([{ mode: 'cash', amount: '' }]);
  const [tendered, setTendered] = useState('');
  const [billDisc, setBillDisc] = useState({ percent: '', amount: '', reason: '' });
  const [customerId, setCustomerId] = useState('');
  const [notes, setNotes] = useState('');
  const [parked, setParked] = useState([]);
  const [showParked, setShowParked] = useState(false);
  const [printBill, setPrintBill] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  // Print format: cashier's last choice wins, else tenant default from settings.
  const { tenantSettings } = useAuth();
  const [printFormat, setPrintFormat] = useState(() => localStorage.getItem('pos_print_format') || 'thermal_80');
  const [printFormatTouched, setPrintFormatTouched] = useState(() => !!localStorage.getItem('pos_print_format'));
  useEffect(() => {
    if (!printFormatTouched && tenantSettings?.default_print_format) setPrintFormat(tenantSettings.default_print_format);
  }, [tenantSettings, printFormatTouched]);
  const changePrintFormat = (f) => {
    setPrintFormatTouched(true);
    try { localStorage.setItem('pos_print_format', f); } catch { /* ignore */ }
    setPrintFormat(f);
  };
  const isWholesaleBill = (b) => String(b?.sale_type || '').toLowerCase() === 'wholesale';
  const [saleType, setSaleType] = useState('retail');   // 'retail' | 'wholesale'
  const [slabs, setSlabs] = useState(null);             // {productId: [{min_qty, discount_percent}]}
  const [scaleReading, setScaleReading] = useState(null); // cart line key currently reading from scale
  const [appliedPromos, setAppliedPromos] = useState([]); // promotions applied on last bill
  const searchRef = useRef(null);
  const shop = getShopProfile();

  const loadProducts = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await api.get('/catalog/products/', { params: { page_size: 5000 } });
      const list = asList(r.data).filter((p) => p.is_active !== false);
      setProducts(list); setCachedProducts(list);
    } catch (e) {
      const cached = getCachedProducts();
      if (cached.length) { setProducts(cached); setError(''); setNotice({ type: 'warn', msg: 'Offline — cached products dikhaye ja rahe hain.' }); }
      else setError(errMsg(e));
    } finally { setLoading(false); }
  }, []);

  const loadCustomers = useCallback(async () => {
    try {
      const r = await api.get('/khata/customers/', { params: { page_size: 5000 } });
      const list = asList(r.data);
      setCustomers(list); setCachedCustomers(list);
    } catch { setCustomers(getCachedCustomers()); }
  }, []);

  const loadParked = useCallback(async () => {
    try { setParked(asList((await api.get('/billing/parked-bills/')).data)); } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadProducts(); loadCustomers(); loadParked(); }, [loadProducts, loadCustomers, loadParked]);

  // Load volume price slabs when wholesale mode activates (display only — backend is authoritative).
  useEffect(() => {
    if (saleType !== 'wholesale' || slabs !== null) return;
    api.get('/catalog/price-slabs/')
      .then((r) => {
        const idx = {};
        for (const s of asList(r.data)) {
          const pid = String(s.product ?? s.product_id ?? '');
          if (!pid) continue;
          (idx[pid] = idx[pid] || []).push(s);
        }
        setSlabs(idx);
      })
      .catch(() => setSlabs({})); // endpoint not ready → no slabs, wholesale rates still apply
  }, [saleType, slabs]);

  // Selecting a wholesale customer flips the bill into wholesale mode (rates recalc).
  useEffect(() => {
    if (!customerId) return;
    const c = customers.find((x) => String(x.id) === String(customerId));
    if (!c) return;
    const t = String(c.customer_type || '').toLowerCase();
    if (t === 'wholesale') {
      setSaleType('wholesale');
      const wd = Number(c.wholesale_discount_percent || 0);
      // Automatic bill-level customer discount (display) — backend stays authoritative.
      setBillDisc((bd) => (
        wd > 0 && !Number(bd.percent) && !Number(bd.amount)
          ? { ...bd, percent: String(wd), reason: bd.reason || 'Wholesale customer discount' }
          : bd
      ));
    } else if (t && saleType !== 'retail') {
      setSaleType('retail');
    }
  }, [customerId, customers, saleType]);

  // ---------- cart ----------
  const addProduct = useCallback((p) => {
    if (!p) return;
    setCart((c) => {
      const i = c.findIndex((l) => l.product.id === p.id);
      if (i >= 0) { const n = [...c]; n[i] = { ...n[i], qty: n[i].qty + 1 }; return n; }
      return [...c, { key: p.id + '_' + Date.now(), product: p, qty: 1, discount_percent: '', discount_amount: '' }];
    });
    setQuery('');
    searchRef.current?.focus();
  }, []);

  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return products.filter((p) =>
      pName(p).toLowerCase().includes(q) || pSku(p).toLowerCase().includes(q)
    ).slice(0, 8);
  }, [query, products]);

  const submitSearch = () => {
    const q = query.trim().toLowerCase();
    if (!q) return;
    const exact = products.find((p) => pSku(p).toLowerCase() === q);
    if (exact) return addProduct(exact);
    if (suggestions.length === 1) return addProduct(suggestions[0]);
    // otherwise leave dropdown open for the cashier to pick
  };

  const setQty = (key, qty) => {
    const v = Number(qty);
    if (!(v > 0)) return;
    setCart((c) => c.map((l) => (l.key === key ? { ...l, qty: v } : l)));
  };
  const setLineDisc = (key, field, val) =>
    setCart((c) => c.map((l) => (l.key === key ? { ...l, [field]: val } : l)));
  const removeLine = (key) => setCart((c) => c.filter((l) => l.key !== key));

  // ---------- weighing scale (Web Serial) ----------
  const isWeighable = (p) => ['kg', 'kgs', 'kilo', 'litre', 'liter', 'ltr', 'l'].includes(String(p?.unit || '').toLowerCase());

  const readScale = async (key) => {
    if (!('serial' in navigator)) {
      setNotice({ type: 'error', msg: 'Is browser mein scale support nahi hai — Chrome/Edge use karein. Weight manually likhein.' });
      return;
    }
    setScaleReading(key);
    let port;
    try {
      port = await navigator.serial.requestPort(); // user picks the scale's COM/USB port
      await port.open({ baudRate: 9600 });
      const reader = port.readable.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let weight = null;
      const deadline = Date.now() + 20000;
      while (Date.now() < deadline && weight === null) {
        const chunk = await Promise.race([
          reader.read().then((r) => ({ ...r, timeout: false })),
          new Promise((res) => setTimeout(() => res({ value: null, done: false, timeout: true }), 1000)),
        ]);
        if (chunk.timeout) continue;
        if (chunk.value) {
          buf += decoder.decode(chunk.value, { stream: true });
          const m = buf.replace(/,/g, '').match(/-?\d+(\.\d+)?/);
          if (m) { weight = parseFloat(m[0]); break; }
        }
        if (chunk.done) break;
      }
      reader.releaseLock();
      try { await port.close(); } catch { /* ignore */ }
      if (weight !== null && weight > 0) {
        setQty(key, weight);
        setNotice({ type: 'ok', msg: `⚖ Scale se weight: ${weight}` });
      } else {
        setNotice({ type: 'error', msg: 'Scale se weight nahi mila — qty manually likhein.' });
      }
    } catch (e) {
      if (e && e.name === 'NotFoundError') {
        // User cancelled the port picker — silent, manual entry stays available.
      } else {
        setNotice({ type: 'error', msg: `Scale error (${e?.message || e}) — qty manually likhein.` });
      }
      try { await port?.close(); } catch { /* ignore */ }
    } finally {
      setScaleReading(null);
    }
  };

  const subtotal = cart.reduce((s, l) => s + lineGross(l, saleType), 0);
  const linesDiscTotal = cart.reduce((s, l) => s + lineDisc(l, saleType, slabs), 0);
  const billDiscAmt = Number(billDisc.amount || 0) + (subtotal - linesDiscTotal) * (Number(billDisc.percent || 0) / 100);
  const total = Math.max(0, subtotal - linesDiscTotal - billDiscAmt);
  const itemCount = cart.reduce((s, l) => s + Number(l.qty || 0), 0);

  // ---------- payments ----------
  const paidSum = payments.reduce((s, p) => s + (Number(p.amount) || 0), 0);
  const remaining = total - paidSum;
  const changeDue = Math.max(0, paidSum - total);
  const khataCustomer = customers.find((c) => String(c.id) === String(customerId));

  const openPay = () => {
    if (!cart.length) return;
    setPayments([{ mode: 'cash', amount: total.toFixed(0) }]);
    setTendered('');
    setShowPay(true);
  };

  const buildPayload = () => ({
    sale_type: saleType,
    lines: cart.map((l) => ({
      product: l.product.id,
      qty: Number(l.qty),
      discount_percent: Number(l.discount_percent || 0),
      discount_amount: Number(l.discount_amount || 0),
    })),
    payments: payments.filter((p) => Number(p.amount) > 0).map((p) => ({ mode: p.mode, amount: Number(p.amount) })),
    bill_discount_percent: Number(billDisc.percent || 0),
    bill_discount_amount: Number(billDisc.amount || 0),
    bill_discount_reason: billDisc.reason || '',
    customer: customerId || null,
    tendered: Number(tendered || 0) || null,
    notes: notes || '',
  });

  const resetSale = () => {
    setCart([]); setPayments([{ mode: 'cash', amount: '' }]); setTendered('');
    setBillDisc({ percent: '', amount: '', reason: '' }); setCustomerId(''); setNotes(''); setShowPay(false);
    setSaleType('retail');
  };

  const toPrintableBill = (src, queuedTag) => ({
    bill_no: src.bill_no || src.number || (queuedTag ? `QUEUED-${Date.now().toString().slice(-6)}` : src.id),
    created_at: src.created_at || new Date().toISOString(),
    sale_type: src.sale_type || src.saleType || (queuedTag ? saleType : 'retail'),
    lines: (src.lines || []).map((l) => ({
      product_name: l.product_name || l.product?.name || pName(l.product) || 'Item',
      qty: l.qty, rate: l.applied_rate ?? l.rate ?? l.price ?? 0,
      applied_rate: l.applied_rate ?? l.rate ?? l.price ?? 0,
      discount_percent: l.discount_percent ?? 0,
      slab_discount_percent: l.slab_discount_percent ?? 0,
      discount_amount: l.discount_amount || 0,
      total: l.total ?? l.line_total ?? 0,
      is_free: l.is_free ?? l.isFree ?? false,
    })),
    subtotal: src.subtotal, bill_discount_amount: src.bill_discount_amount || src.discount_total,
    bill_discount_reason: src.bill_discount_reason, grand_total: src.grand_total ?? src.total,
    payments: src.payments || [], change_due: src.change_due || 0,
    customer: src.customer && typeof src.customer === 'object' ? src.customer : (khataCustomer || null),
    cashier_name: src.cashier_name,
  });

  const completeSale = async () => {
    if (!cart.length) return;
    if (remaining > 0.5) { setNotice({ type: 'error', msg: `Payment poori nahi — ${fmtRs(remaining)} baqi hai.` }); return; }
    if (Number(billDisc.percent || billDisc.amount) > 0 && !billDisc.reason.trim()) {
      setNotice({ type: 'error', msg: 'Bill discount ke liye reason likhna zaroori hai.' }); return;
    }
    if (payments.some((p) => p.mode === 'khata') && !customerId) {
      setNotice({ type: 'error', msg: 'Khata payment ke liye customer select karein.' }); return;
    }
    const payload = buildPayload();
    setBusy(true); setNotice(null);
    try {
      const r = await api.post('/billing/bills/', payload);
      setPrintBill(toPrintableBill(r.data));
      setAppliedPromos(asList(r.data?.applied_promotions || r.data?.promotions));
      resetSale(); loadProducts();
    } catch (e) {
      if (isNetworkError(e)) {
        const n = queueBill(payload);
        setPrintBill(toPrintableBill({
          sale_type: saleType,
          lines: cart.map((l) => ({
            product: l.product, qty: l.qty,
            applied_rate: rateOf(l.product, saleType), rate: rateOf(l.product, saleType),
            discount_percent: linePct(l, saleType, slabs),
            discount_amount: lineDisc(l, saleType, slabs),
            total: lineNet(l, saleType, slabs),
          })),
          subtotal, bill_discount_amount: billDiscAmt, bill_discount_reason: billDisc.reason,
          grand_total: total, payments: payload.payments, change_due: changeDue,
        }, true));
        resetSale();
        setNotice({ type: 'warn', msg: `Offline — bill queue mein save ho gaya (${n} pending). Net aate hi sync ho jayega.` });
      } else {
        setNotice({ type: 'error', msg: errMsg(e, 'Bill save nahi ho saka.') });
      }
    } finally { setBusy(false); }
  };

  // ---------- hold / recall ----------
  const holdBill = async () => {
    if (!cart.length) return;
    try {
      await api.post('/billing/parked-bills/', { ...buildPayload(), payments: [] });
      resetSale(); loadParked();
      setNotice({ type: 'ok', msg: 'Bill hold kar diya gaya (parked).' });
    } catch (e) { setNotice({ type: 'error', msg: errMsg(e, 'Hold nahi ho saka.') }); }
  };

  const recallParked = async (pb) => {
    const lines = (pb.lines || []).map((l, i) => {
      const prod = products.find((p) => String(p.id) === String(l.product?.id || l.product));
      return {
        key: 'park_' + i + '_' + Date.now(),
        product: prod || { id: l.product?.id || l.product, name: l.product_name || 'Item', retail_price: l.rate || 0 },
        qty: Number(l.qty || 1), discount_percent: l.discount_percent || '', discount_amount: l.discount_amount || '',
      };
    });
    setCart(lines);
    setShowParked(false);
    try { await api.delete(`/billing/parked-bills/${pb.id}/`); } catch { /* best effort */ }
    loadParked();
  };

  // ---------- keyboard shortcuts ----------
  useEffect(() => {
    const h = (e) => {
      if (e.key === 'F2') { e.preventDefault(); searchRef.current?.focus(); }
      else if (e.key === 'F10') { e.preventDefault(); if (!showPay) openPay(); }
      else if (e.key === 'F9') { e.preventDefault(); holdBill(); }
      else if (e.key === 'Escape' && !showPay && !showParked) setCart([]);
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  });

  // ---------- printing ----------
  useEffect(() => {
    if (!printBill) return;
    const t = setTimeout(() => window.print(), 250);
    const done = () => setPrintBill(null);
    window.addEventListener('afterprint', done);
    return () => { clearTimeout(t); window.removeEventListener('afterprint', done); };
  }, [printBill]);

  return (
    <div className="pos">
      <PageHead
        title="Billing" urdu="بلنگ"
        actions={<>
          <span className="kbd-hint">F2 search · F9 hold · F10 pay · Esc clear</span>
          <div className="seg-toggle" title="Print format" style={{ marginBottom: 0 }}>
            <button className={printFormat === 'thermal_80' ? 'active' : ''} onClick={() => changePrintFormat('thermal_80')}>🧾 80mm</button>
            <button className={printFormat === 'a4' ? 'active' : ''} onClick={() => changePrintFormat('a4')}>📄 A4</button>
          </div>
          <button className="btn" onClick={() => { setShowParked(true); loadParked(); }}>
            Parked ({parked.length})
          </button>
        </>}
      />
      {notice && <div className={`notice ${notice.type}`}>{notice.msg}<button className="btn icon small" onClick={() => setNotice(null)}>✕</button></div>}
      {saleType === 'wholesale' && (
        <div className="ws-banner">
          🏭 <strong>WHOLESALE MODE</strong> — wholesale rates + volume slabs apply
          <span className="urdu-sub"> · ہول سیل</span>
        </div>
      )}
      {appliedPromos.length > 0 && (
        <div className="promo-chips">
          <span className="dim small">Applied promotions:</span>
          {appliedPromos.map((p, i) => (
            <Badge key={i} tone="green">🎁 {typeof p === 'string' ? p : (p.name || p.title || `Promo #${p.id || i + 1}`)}</Badge>
          ))}
          <button className="btn icon small" onClick={() => setAppliedPromos([])} aria-label="Dismiss">✕</button>
        </div>
      )}
      <ErrorBox error={error} onRetry={loadProducts} />

      <div className="pos-grid">
        <div className="pos-left">
          <div className="search-wrap">
            <input
              ref={searchRef}
              className="input big"
              placeholder="Scan barcode ya naam likhein… (Enter)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submitSearch(); }}
            />
            {query.trim() && suggestions.length > 0 && (
              <div className="suggest">
                {suggestions.map((p) => (
                  <button key={p.id} className="suggest-item" onClick={() => addProduct(p)}>
                    <span>{pName(p)}{p.name_urdu ? ` · ${p.name_urdu}` : ''}</span>
                    <span className="dim">{pSku(p)}</span>
                    <strong>{fmtRs(pPrice(p))}</strong>
                  </button>
                ))}
              </div>
            )}
          </div>

          {loading ? <Spinner label="Products load ho rahe hain…" /> : cart.length === 0 ? (
            <EmptyState title="Cart khaali hai" hint="Barcode scan karein ya upar search karein." />
          ) : (
            <table className="table cart">
              <thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Disc.</th><th>Total</th><th></th></tr></thead>
              <tbody>
                {cart.map((l) => (
                  <tr key={l.key}>
                    <td><div>{pName(l.product)}</div><div className="dim small">{pSku(l.product)}</div></td>
                    <td>
                      <div className="qty-ctl">
                        <button className="btn icon small" onClick={() => setQty(l.key, Number(l.qty) - 1)} disabled={Number(l.qty) <= 1}>−</button>
                        <input className="input qty" type="number" min="0.01" step="any" value={l.qty} onChange={(e) => setQty(l.key, e.target.value)} />
                        <button className="btn icon small" onClick={() => setQty(l.key, Number(l.qty) + 1)}>+</button>
                        {isWeighable(l.product) && (
                          <button
                            className="btn icon small"
                            title="Weighing scale se weight lein (⚖)"
                            disabled={scaleReading === l.key}
                            onClick={() => readScale(l.key)}
                          >
                            {scaleReading === l.key ? '…' : '⚖'}
                          </button>
                        )}
                      </div>
                      {isWeighable(l.product) && <div className="dim small">{l.product.unit} item — scale ya manual</div>}
                    </td>
                    <td>
                      <div>{fmtRs(rateOf(l.product, saleType))}</div>
                      {saleType === 'wholesale' && slabPctFor(l.product?.id, l.qty, slabs, saleType) > 0 && (
                        <div><Badge tone="purple">−{slabPctFor(l.product?.id, l.qty, slabs, saleType)}% slab</Badge></div>
                      )}
                      {saleType === 'wholesale' && Number(l.product?.wholesale_price || 0) <= 0 && (
                        <div className="dim small">retail rate</div>
                      )}
                    </td>
                    <td>
                      <input className="input tiny" placeholder="%" title="Discount %" value={l.discount_percent} onChange={(e) => setLineDisc(l.key, 'discount_percent', e.target.value)} />
                      <input className="input tiny" placeholder="Rs" title="Discount Rs" value={l.discount_amount} onChange={(e) => setLineDisc(l.key, 'discount_amount', e.target.value)} />
                    </td>
                    <td><strong>{fmtRs(lineNet(l, saleType, slabs))}</strong></td>
                    <td><button className="btn icon small danger" onClick={() => removeLine(l.key)}>✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="pos-right card">
          <div className="seg-toggle" role="group" aria-label="Sale type">
            <button className={saleType === 'retail' ? 'active' : ''} onClick={() => setSaleType('retail')}>Retail</button>
            <button className={saleType === 'wholesale' ? 'active ws' : ''} onClick={() => setSaleType('wholesale')}>🏭 Wholesale</button>
          </div>
          {saleType === 'wholesale' && khataCustomer && String(khataCustomer.customer_type || '').toLowerCase() === 'wholesale' && (
            <div className="dim small" style={{ marginBottom: 6 }}>
              🏭 {khataCustomer.name}{Number(khataCustomer.wholesale_discount_percent) > 0 ? ` · ${khataCustomer.wholesale_discount_percent}% auto discount` : ''}
            </div>
          )}
          <div className="tot-row"><span>Items</span><span>{itemCount}</span></div>
          <div className="tot-row"><span>Subtotal</span><span>{fmtRs(subtotal)}</span></div>
          <div className="tot-row"><span>Line discounts</span><span>−{fmtRs(linesDiscTotal)}</span></div>
          <div className="tot-row grand"><span>Total</span><span>{fmtRs(total)}</span></div>
          <div className="pos-actions">
            <button className="btn" onClick={holdBill} disabled={!cart.length}>Hold (F9)</button>
            <button className="btn danger-ghost" onClick={() => setCart([])} disabled={!cart.length}>Clear</button>
            <button className="btn primary big" onClick={openPay} disabled={!cart.length}>Pay (F10)</button>
          </div>
          <div className="dim small" style={{ marginTop: 8 }}>
            Customer (khata ke liye pay screen mein select karein)
          </div>
        </div>
      </div>

      {showPay && (
        <Modal title={`Payment — ${fmtRs(total)}`} onClose={() => setShowPay(false)} wide>
          <div className="pay-grid">
            <div>
              {payments.map((p, i) => (
                <div className="pay-row" key={i}>
                  <select className="input" value={p.mode} onChange={(e) => {
                    const n = [...payments]; n[i] = { ...n[i], mode: e.target.value }; setPayments(n);
                  }}>
                    <option value="cash">Cash (نقد)</option>
                    <option value="card">Card (کارڈ)</option>
                    <option value="bank_transfer">Bank Transfer (بینک)</option>
                    <option value="khata">Khata (کھاتہ)</option>
                  </select>
                  <input className="input" type="number" min="0" placeholder="Amount" value={p.amount}
                    onChange={(e) => { const n = [...payments]; n[i] = { ...n[i], amount: e.target.value }; setPayments(n); }} />
                  <button className="btn small" title="Set remaining" onClick={() => {
                    const n = [...payments]; const others = payments.reduce((s, x, j) => s + (j === i ? 0 : Number(x.amount) || 0), 0);
                    n[i] = { ...n[i], amount: Math.max(0, total - others).toFixed(0) }; setPayments(n);
                  }}>Exact</button>
                  {payments.length > 1 && (
                    <button className="btn icon small danger" onClick={() => setPayments(payments.filter((_, j) => j !== i))}>✕</button>
                  )}
                </div>
              ))}
              <button className="btn small" onClick={() => setPayments([...payments, { mode: 'card', amount: '' }])}>
                + Split payment add karein
              </button>

              {payments.some((p) => p.mode === 'cash') && (
                <Field label="Cash tendered (وصول شدہ رقم)">
                  <input className="input" type="number" min="0" value={tendered} onChange={(e) => setTendered(e.target.value)} placeholder={total.toFixed(0)} />
                </Field>
              )}
              {payments.some((p) => p.mode === 'khata') && (
                <Field label="Khata customer (کھاتہ گاہک)">
                  <select className="input" value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                    <option value="">— Select customer —</option>
                    {customers.map((c) => {
                      const wt = String(c.customer_type || '').toLowerCase() === 'wholesale';
                      return (
                        <option key={c.id} value={c.id}>
                          {wt ? '🏭 ' : ''}{c.name} · {c.phone}{wt ? ' (Wholesale)' : ''}{c.balance ? ` (bal ${fmtRs(c.balance)})` : ''}
                        </option>
                      );
                    })}
                  </select>
                </Field>
              )}
              <div className="grid-2" style={{ marginTop: 8 }}>
                <Field label="Bill discount %">
                  <input className="input" type="number" min="0" value={billDisc.percent} onChange={(e) => setBillDisc({ ...billDisc, percent: e.target.value })} />
                </Field>
                <Field label="Bill discount Rs">
                  <input className="input" type="number" min="0" value={billDisc.amount} onChange={(e) => setBillDisc({ ...billDisc, amount: e.target.value })} />
                </Field>
              </div>
              {(Number(billDisc.percent || 0) > 0 || Number(billDisc.amount || 0) > 0) && (
                <Field label="Discount reason (zaroori)">
                  <input className="input" value={billDisc.reason} onChange={(e) => setBillDisc({ ...billDisc, reason: e.target.value })} placeholder="e.g. regular customer" />
                </Field>
              )}
              <Field label="Notes">
                <input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional" />
              </Field>
            </div>
            <div className="pay-summary card">
              <div className="tot-row"><span>Bill total</span><span>{fmtRs(total)}</span></div>
              <div className="tot-row"><span>Paid</span><span>{fmtRs(paidSum)}</span></div>
              <div className={`tot-row ${remaining > 0.5 ? 't-red' : ''}`}><span>Remaining</span><span>{fmtRs(Math.max(0, remaining))}</span></div>
              {changeDue > 0 && <div className="tot-row t-green"><span>Change (واپسی)</span><span>{fmtRs(changeDue)}</span></div>}
              <div className="pay-modes">
                {payments.filter((p) => Number(p.amount) > 0).map((p, i) => (
                  <Badge key={i} tone="blue">{modeLabel(p.mode)}: {fmtRs(p.amount)}</Badge>
                ))}
              </div>
              <button className="btn primary big" onClick={completeSale} disabled={busy || remaining > 0.5}>
                {busy ? 'Saving…' : `✓ Complete sale ${changeDue > 0 ? `(change ${fmtRs(changeDue)})` : ''}`}
              </button>
              {queueCount() > 0 && <div className="dim small">{queueCount()} bill(s) offline queue mein hain.</div>}
            </div>
          </div>
        </Modal>
      )}

      {showParked && (
        <Modal title="Parked bills" onClose={() => setShowParked(false)}>
          {parked.length === 0 ? <EmptyState title="No parked bills" /> : (
            <ul className="list">
              {parked.map((pb) => (
                <li key={pb.id} className="list-row">
                  <span>#{pb.bill_no || pb.id} · {(pb.lines || []).length} items · {fmtRs(pb.grand_total ?? pb.total ?? 0)}</span>
                  <button className="btn small primary" onClick={() => recallParked(pb)}>Recall</button>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}

      {printBill && (
        <div className="print-area">
          {printFormat === 'a4' ? (
            <Invoice
              bill={printBill} shop={shop}
              invoiceTitle={isWholesaleBill(printBill) ? 'TAX INVOICE' : 'RETAIL INVOICE'}
            />
          ) : (
            <Receipt bill={printBill} shop={shop} />
          )}
        </div>
      )}
    </div>
  );
}
