import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg, todayISO } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Modal, Field, Badge } from '../components/ui.jsx';

const TABS = [
  { id: 'products', label: 'Products' },
  { id: 'stock', label: 'Stock levels' },
  { id: 'grn', label: 'Receive stock (GRN)' },
  { id: 'adjust', label: 'Adjustments' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'cats', label: 'Categories' },
];

const UNITS = ['pcs', 'kg', 'g', 'litre', 'ml', 'pack', 'box', 'dozen'];
const ADJ_TYPES = [
  { value: 'damage', label: 'Damage (نقصان)' },
  { value: 'expiry', label: 'Expiry write-off' },
  { value: 'theft', label: 'Theft / loss (چوری)' },
  { value: 'found', label: 'Found stock' },
  { value: 'correction', label: 'Correction' },
];

const emptyProduct = { sku: '', name: '', name_urdu: '', category: '', brand: '', unit: 'pcs', purchase_price: '', retail_price: '', wholesale_price: '', tax_percent: '0', reorder_level: '5', track_expiry: false, is_active: true };

export default function Inventory() {
  const [tab, setTab] = useState('products');
  return (
    <div>
      <PageHead title="Inventory" urdu="اسٹاک" />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      {tab === 'products' && <ProductsTab />}
      {tab === 'stock' && <StockTab />}
      {tab === 'grn' && <GrnTab />}
      {tab === 'adjust' && <AdjustTab />}
      {tab === 'alerts' && <AlertsTab />}
      {tab === 'cats' && <CatsTab />}
    </div>
  );
}

/* ---------------- Products ---------------- */
function ProductsTab() {
  const [products, setProducts] = useState([]);
  const [cats, setCats] = useState([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null); // null | product object | 'new'
  const [importing, setImporting] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [p, c] = await Promise.all([
        api.get('/catalog/products/', { params: { search: q || undefined, page_size: 5000 } }),
        api.get('/catalog/categories/'),
      ]);
      setProducts(asList(p.data)); setCats(asList(c.data));
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [q]);

  useEffect(() => { const t = setTimeout(load, q ? 400 : 0); return () => clearTimeout(t); }, [load, q]);

  const saveProduct = async (data) => {
    const payload = {
      ...data,
      category: data.category || null,
      purchase_price: Number(data.purchase_price || 0),
      retail_price: Number(data.retail_price || 0),
      wholesale_price: Number(data.wholesale_price || 0),
      tax_percent: Number(data.tax_percent || 0),
      reorder_level: Number(data.reorder_level || 0),
    };
    if (editing === 'new') await api.post('/catalog/products/', payload);
    else await api.patch(`/catalog/products/${editing.id}/`, payload);
    setEditing(null); load();
  };

  const handleCsv = async (file) => {
    const text = await file.text();
    const rows = text.split(/\r?\n/).map((r) => r.trim()).filter(Boolean);
    if (rows.length < 2) { setError('CSV khaali hai.'); return; }
    const header = rows[0].split(',').map((h) => h.trim().toLowerCase());
    const idx = (n) => header.indexOf(n);
    setImporting({ total: rows.length - 1, done: 0, ok: 0, fail: 0 });
    let ok = 0, fail = 0;
    for (let i = 1; i < rows.length; i++) {
      const cols = rows[i].split(',').map((c) => c.trim());
      try {
        await api.post('/catalog/products/', {
          sku: idx('sku') >= 0 ? cols[idx('sku')] : '',
          name: idx('name') >= 0 ? cols[idx('name')] : `Item ${i}`,
          brand: idx('brand') >= 0 ? cols[idx('brand')] : '',
          unit: idx('unit') >= 0 ? cols[idx('unit')] : 'pcs',
          purchase_price: Number(idx('purchase_price') >= 0 ? cols[idx('purchase_price')] : 0) || 0,
          retail_price: Number(idx('retail_price') >= 0 ? cols[idx('retail_price')] : 0) || 0,
          reorder_level: Number(idx('reorder_level') >= 0 ? cols[idx('reorder_level')] : 5) || 5,
        });
        ok++;
      } catch { fail++; }
      setImporting({ total: rows.length - 1, done: i, ok, fail });
    }
    setImporting(null); load();
  };

  return (
    <div>
      <div className="toolbar">
        <input className="input" placeholder="Search products…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 300 }} />
        <div className="spacer" />
        <label className="btn">📥 CSV import<input type="file" accept=".csv" hidden onChange={(e) => e.target.files[0] && handleCsv(e.target.files[0])} /></label>
        <button className="btn primary" onClick={() => setEditing('new')}>+ Add product</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {importing && <div className="notice">Importing… {importing.done}/{importing.total} (ok {importing.ok}, fail {importing.fail})</div>}
      {loading ? <Spinner /> : products.length === 0 ? <EmptyState title="No products" hint="Add product dabayein ya CSV import karein." /> : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>SKU</th><th>Name</th><th>Category</th><th>Purchase</th><th>Retail</th><th>Reorder</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.id}>
                  <td className="mono">{p.sku || p.barcode || '—'}</td>
                  <td>{p.name}{p.name_urdu && <div className="dim small">{p.name_urdu}</div>}</td>
                  <td>{p.category_name || p.category?.name || '—'}</td>
                  <td>{fmtRs(p.purchase_price ?? 0)}</td>
                  <td><strong>{fmtRs(p.retail_price ?? p.price ?? 0)}</strong></td>
                  <td>{p.reorder_level ?? '—'}</td>
                  <td>{p.is_active === false ? <Badge tone="gray">Inactive</Badge> : <Badge tone="green">Active</Badge>}</td>
                  <td><button className="btn small" onClick={() => setEditing(p)}>Edit</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <ProductModal cats={cats} initial={editing === 'new' ? emptyProduct : editing} onClose={() => setEditing(null)} onSave={saveProduct} />}
    </div>
  );
}

function ProductModal({ cats, initial, onClose, onSave }) {
  const [f, setF] = useState({ ...emptyProduct, ...initial, category: initial.category?.id || initial.category || '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try { await onSave(f); } catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };
  return (
    <Modal title={initial.id ? 'Edit product' : 'Add product'} onClose={onClose} wide>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <div className="form-grid">
          <Field label="SKU / Barcode"><input className="input" value={f.sku || ''} onChange={(e) => set('sku', e.target.value)} placeholder="Auto if empty" /></Field>
          <Field label="Name *"><input className="input" required value={f.name || ''} onChange={(e) => set('name', e.target.value)} /></Field>
          <Field label="Name (Urdu)"><input className="input" value={f.name_urdu || ''} onChange={(e) => set('name_urdu', e.target.value)} /></Field>
          <Field label="Category">
            <select className="input" value={f.category || ''} onChange={(e) => set('category', e.target.value)}>
              <option value="">—</option>
              {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Brand"><input className="input" value={f.brand || ''} onChange={(e) => set('brand', e.target.value)} /></Field>
          <Field label="Unit">
            <select className="input" value={f.unit || 'pcs'} onChange={(e) => set('unit', e.target.value)}>
              {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </Field>
          <Field label="Purchase price"><input className="input" type="number" min="0" step="any" value={f.purchase_price ?? ''} onChange={(e) => set('purchase_price', e.target.value)} /></Field>
          <Field label="Retail price *"><input className="input" type="number" min="0" step="any" required value={f.retail_price ?? ''} onChange={(e) => set('retail_price', e.target.value)} /></Field>
          <Field label="Wholesale price"><input className="input" type="number" min="0" step="any" value={f.wholesale_price ?? ''} onChange={(e) => set('wholesale_price', e.target.value)} /></Field>
          <Field label="Tax %"><input className="input" type="number" min="0" step="any" value={f.tax_percent ?? ''} onChange={(e) => set('tax_percent', e.target.value)} /></Field>
          <Field label="Reorder level"><input className="input" type="number" min="0" value={f.reorder_level ?? ''} onChange={(e) => set('reorder_level', e.target.value)} /></Field>
          <label className="check"><input type="checkbox" checked={!!f.track_expiry} onChange={(e) => set('track_expiry', e.target.checked)} /> Track expiry</label>
          <label className="check"><input type="checkbox" checked={f.is_active !== false} onChange={(e) => set('is_active', e.target.checked)} /> Active</label>
        </div>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}

/* ---------------- Stock levels ---------------- */
function StockTab() {
  const [rows, setRows] = useState([]);
  const [lowOnly, setLowOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await api.get('/inventory/stock-levels/', { params: lowOnly ? { low_stock: true } : {} });
      setRows(asList(r.data));
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [lowOnly]);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <div className="toolbar">
        <label className="check"><input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} /> Low stock only</label>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner /> : rows.length === 0 ? <EmptyState title="No stock rows" /> : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Product</th><th>Location</th><th>Qty</th><th>Reorder level</th><th>Avg cost</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map((r, i) => {
                const qty = Number(r.qty ?? r.quantity ?? 0);
                const rl = Number(r.reorder_level ?? r.product?.reorder_level ?? 0);
                const low = qty <= rl;
                return (
                  <tr key={r.id || i}>
                    <td>{r.product_name || r.product?.name}</td>
                    <td>{r.location_name || r.location || '—'}</td>
                    <td><strong className={low ? 't-red' : ''}>{qty}</strong></td>
                    <td>{rl}</td>
                    <td>{fmtRs(r.avg_cost ?? r.average_cost ?? 0)}</td>
                    <td>{low ? <Badge tone="red">Low</Badge> : <Badge tone="green">OK</Badge>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------------- GRN ---------------- */
function GrnTab() {
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [supplier, setSupplier] = useState('');
  const [invNo, setInvNo] = useState('');
  const [lines, setLines] = useState([{ product: '', qty: '', purchase_rate: '', expiry_date: '' }]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    api.get('/khata/suppliers/').then((r) => setSuppliers(asList(r.data))).catch(() => {});
    api.get('/catalog/products/', { params: { page_size: 5000 } }).then((r) => setProducts(asList(r.data))).catch(() => {});
    api.get('/inventory/grns/').then((r) => setRecent(asList(r.data).slice(0, 10))).catch(() => {});
  }, []);

  const setLine = (i, k, v) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l)));

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setMsg(null);
    try {
      await api.post('/inventory/grns/', {
        supplier: supplier || null,
        supplier_invoice_no: invNo,
        lines: lines.filter((l) => l.product && Number(l.qty) > 0).map((l) => ({
          product: Number(l.product), qty: Number(l.qty), purchase_rate: Number(l.purchase_rate || 0),
          expiry_date: l.expiry_date || null,
        })),
      });
      setMsg({ type: 'ok', text: 'GRN save ho gaya — stock update ho gaya.' });
      setLines([{ product: '', qty: '', purchase_rate: '', expiry_date: '' }]); setInvNo('');
      const r = await api.get('/inventory/grns/'); setRecent(asList(r.data).slice(0, 10));
    } catch (ex) { setMsg({ type: 'error', text: errMsg(ex) }); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid-2">
      <form className="card" onSubmit={submit}>
        <h3>Receive stock</h3>
        {msg && <div className={msg.type === 'ok' ? 'notice ok' : 'error-box'}>{msg.text}</div>}
        <div className="form-grid">
          <Field label="Supplier">
            <select className="input" value={supplier} onChange={(e) => setSupplier(e.target.value)}>
              <option value="">—</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Supplier invoice #"><input className="input" value={invNo} onChange={(e) => setInvNo(e.target.value)} /></Field>
        </div>
        {lines.map((l, i) => (
          <div className="grn-line" key={i}>
            <select className="input" value={l.product} onChange={(e) => setLine(i, 'product', e.target.value)}>
              <option value="">— Product —</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <input className="input" type="number" min="0" step="any" placeholder="Qty" value={l.qty} onChange={(e) => setLine(i, 'qty', e.target.value)} />
            <input className="input" type="number" min="0" step="any" placeholder="Rate" value={l.purchase_rate} onChange={(e) => setLine(i, 'purchase_rate', e.target.value)} />
            <input className="input" type="date" value={l.expiry_date} onChange={(e) => setLine(i, 'expiry_date', e.target.value)} title="Expiry" />
            <button type="button" className="btn icon small danger" onClick={() => setLines(lines.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button type="button" className="btn small" onClick={() => setLines([...lines, { product: '', qty: '', purchase_rate: '', expiry_date: '' }])}>+ Add line</button>
        <div className="modal-foot">
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save GRN'}</button>
        </div>
      </form>
      <div className="card">
        <h3>Recent GRNs</h3>
        {recent.length === 0 ? <EmptyState title="No GRNs yet" /> : (
          <ul className="list">
            {recent.map((g) => (
              <li key={g.id} className="list-row">
                <span>#{g.id} · {g.supplier_name || g.supplier?.name || '—'} · {(g.lines || []).length} items</span>
                <span className="dim small">{(g.created_at || '').slice(0, 10)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ---------------- Adjustments ---------------- */
function AdjustTab() {
  const [products, setProducts] = useState([]);
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ product: '', qty_change: '', type: 'damage', reason: '', location: 'shop' });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const load = useCallback(async () => {
    try { setRows(asList((await api.get('/inventory/adjustments/')).data).slice(0, 20)); } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    api.get('/catalog/products/', { params: { page_size: 5000 } }).then((r) => setProducts(asList(r.data))).catch(() => {});
    load();
  }, [load]);

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setMsg(null);
    try {
      await api.post('/inventory/adjustments/', {
        product: Number(f.product), qty_change: Number(f.qty_change),
        type: f.type, reason: f.reason, location: f.location,
      });
      setMsg({ type: 'ok', text: 'Adjustment save ho gaya.' });
      setF({ product: '', qty_change: '', type: 'damage', reason: '', location: 'shop' });
      load();
    } catch (ex) { setMsg({ type: 'error', text: errMsg(ex) }); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid-2">
      <form className="card" onSubmit={submit}>
        <h3>Stock adjustment</h3>
        {msg && <div className={msg.type === 'ok' ? 'notice ok' : 'error-box'}>{msg.text}</div>}
        <Field label="Product *">
          <select className="input" required value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })}>
            <option value="">—</option>
            {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <div className="form-grid">
          <Field label="Qty change * (+/-)"><input className="input" required type="number" step="any" value={f.qty_change} onChange={(e) => setF({ ...f, qty_change: e.target.value })} placeholder="-5" /></Field>
          <Field label="Type">
            <select className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>
              {ADJ_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Reason *"><input className="input" required value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="e.g. expired cartons" /></Field>
        <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save adjustment'}</button>
      </form>
      <div className="card">
        <h3>Recent adjustments</h3>
        {rows.length === 0 ? <EmptyState title="No adjustments" /> : (
          <ul className="list">
            {rows.map((a, i) => (
              <li key={a.id || i} className="list-row">
                <span>{a.product_name || a.product?.name} · <strong className={Number(a.qty_change) < 0 ? 't-red' : 't-green'}>{a.qty_change}</strong> · {a.type}</span>
                <span className="dim small">{a.reason || ''}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ---------------- Alerts ---------------- */
function AlertsTab() {
  const [alerts, setAlerts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setAlerts((await api.get('/inventory/alerts/')).data); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const low = asList(alerts?.low_stock || alerts?.lowStock);
  const exp = asList(alerts?.expiring || alerts?.expiry || alerts?.expiring_soon);

  return (
    <div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner /> : (
        <div className="grid-2">
          <div className="card">
            <h3>Low stock <Badge tone="red">{low.length}</Badge></h3>
            {low.length === 0 ? <p className="dim">All stocked up ✓</p> : (
              <table className="table"><thead><tr><th>Product</th><th>Qty</th><th>Reorder</th></tr></thead>
                <tbody>{low.map((p, i) => <tr key={i}><td>{p.product_name || p.name}</td><td className="t-red"><strong>{p.qty ?? p.stock ?? 0}</strong></td><td>{p.reorder_level ?? '—'}</td></tr>)}</tbody>
              </table>
            )}
          </div>
          <div className="card">
            <h3>Expiring soon <Badge tone="amber">{exp.length}</Badge></h3>
            {exp.length === 0 ? <p className="dim">No expiring items ✓</p> : (
              <table className="table"><thead><tr><th>Product</th><th>Batch</th><th>Expiry</th></tr></thead>
                <tbody>{exp.map((p, i) => <tr key={i}><td>{p.product_name || p.name}</td><td>{p.batch || p.batch_no || '—'}</td><td>{(p.expiry_date || '').slice(0, 10)}</td></tr>)}</tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Categories ---------------- */
function CatsTab() {
  const [cats, setCats] = useState([]);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try { setCats(asList((await api.get('/catalog/categories/')).data)); } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    await api.post('/catalog/categories/', { name: name.trim() });
    setName(''); load();
  };
  const del = async (c) => {
    if (!window.confirm(`Delete "${c.name}"?`)) return;
    await api.delete(`/catalog/categories/${c.id}/`);
    load();
  };

  return (
    <div className="card" style={{ maxWidth: 560 }}>
      <h3>Categories</h3>
      <form className="row-form" onSubmit={add}>
        <input className="input" placeholder="New category name" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn primary" type="submit">Add</button>
      </form>
      {loading ? <Spinner /> : (
        <ul className="list">
          {cats.map((c) => (
            <li key={c.id} className="list-row"><span>{c.name}</span><button className="btn small danger-ghost" onClick={() => del(c)}>Delete</button></li>
          ))}
          {cats.length === 0 && <EmptyState title="No categories" />}
        </ul>
      )}
    </div>
  );
}
