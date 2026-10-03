import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg, todayISO } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Modal, Field, Badge } from '../components/ui.jsx';

const TABS = [
  { id: 'slabs', label: 'Price slabs', urdu: 'ریٹ سلیب' },
  { id: 'customers', label: 'Wholesale customers', urdu: 'ہول سیل گاہک' },
  { id: 'report', label: 'Wholesale report' },
];

export default function Wholesale() {
  const [tab, setTab] = useState('slabs');
  return (
    <div>
      <PageHead title="Wholesale" urdu="ہول سیل" />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label} {t.urdu && <span className="nav-urdu">{t.urdu}</span>}
          </button>
        ))}
      </div>
      {tab === 'slabs' && <SlabsTab />}
      {tab === 'customers' && <WholesaleCustomersTab />}
      {tab === 'report' && <WholesaleReportTab />}
    </div>
  );
}

/* ---------------- Price slabs ---------------- */
function SlabsTab() {
  const [q, setQ] = useState('');
  const [options, setOptions] = useState([]);
  const [product, setProduct] = useState(null);
  const [slabs, setSlabs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);

  const search = useCallback(async () => {
    if (!q.trim()) { setOptions([]); return; }
    try {
      const r = await api.get('/catalog/products/', { params: { search: q.trim(), page_size: 20 } });
      setOptions(asList(r.data).filter((p) => p.is_active !== false));
    } catch { /* ignore */ }
  }, [q]);
  useEffect(() => { const t = setTimeout(search, 350); return () => clearTimeout(t); }, [search]);

  const loadSlabs = useCallback(async (pid) => {
    setLoading(true); setError('');
    try {
      const r = await api.get('/catalog/price-slabs/', { params: { product: pid } });
      // Defensive: some backends return all slabs — filter client-side too.
      setSlabs(asList(r.data).filter((s) => String(s.product ?? s.product_id ?? '') === String(pid))
        .sort((a, b) => Number(a.min_qty) - Number(b.min_qty)));
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);

  const pick = (p) => { setProduct(p); setQ(''); setOptions([]); loadSlabs(p.id); };

  const save = async (data) => {
    if (data.id) await api.patch(`/catalog/price-slabs/${data.id}/`, { min_qty: data.min_qty, discount_percent: data.discount_percent });
    else await api.post('/catalog/price-slabs/', { product: product.id, min_qty: data.min_qty, discount_percent: data.discount_percent });
    setEditing(null); loadSlabs(product.id);
  };
  const remove = async (id) => {
    if (!window.confirm('Delete this price slab?')) return;
    await api.delete(`/catalog/price-slabs/${id}/`);
    loadSlabs(product.id);
  };

  return (
    <div>
      <div className="toolbar">
        <div style={{ position: 'relative', minWidth: 320 }}>
          <input className="input" placeholder="Product search karein (naam / SKU)…" value={q} onChange={(e) => setQ(e.target.value)} />
          {options.length > 0 && (
            <div className="suggest">
              {options.map((p) => (
                <button key={p.id} className="suggest-item" onClick={() => pick(p)}>
                  <span>{p.name}</span><span className="dim">{p.sku}</span><strong>{fmtRs(p.wholesale_price || p.retail_price)}</strong>
                </button>
              ))}
            </div>
          )}
        </div>
        {product && (
          <>
            <span>Selected: <strong>{product.name}</strong> <span className="dim">({product.sku})</span></span>
            <span className="dim small">Retail {fmtRs(product.retail_price)} · Wholesale {fmtRs(product.wholesale_price || product.retail_price)}</span>
            <div className="spacer" />
            <button className="btn primary" onClick={() => setEditing({})}>+ Add slab</button>
          </>
        )}
      </div>
      <ErrorBox error={error} onRetry={() => product && loadSlabs(product.id)} />
      {!product ? <EmptyState title="Product select karein" hint="Upar search kar ke product chunein, phir uske volume slabs manage karein." />
        : loading ? <Spinner /> : slabs.length === 0 ? <EmptyState title="No slabs" hint="Is product ke liye koi volume slab nahi — add karein." /> : (
          <div className="card table-wrap">
            <table className="table">
              <thead><tr><th>Min qty</th><th>Discount %</th><th>Effective rate</th><th></th></tr></thead>
              <tbody>
                {slabs.map((s) => {
                  const base = Number(product.wholesale_price || product.retail_price || 0);
                  const eff = base * (1 - Number(s.discount_percent || 0) / 100);
                  return (
                    <tr key={s.id}>
                      <td><strong>{s.min_qty}+</strong></td>
                      <td><Badge tone="purple">−{s.discount_percent}%</Badge></td>
                      <td>{fmtRs(eff)}</td>
                      <td className="row-actions">
                        <button className="btn small" onClick={() => setEditing(s)}>Edit</button>
                        <button className="btn small danger" onClick={() => remove(s.id)}>Delete</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="dim small" style={{ padding: '0 12px 12px' }}>
              Rule: qty ≥ min_qty par sab se bara tier lagta hai (manual discount ke saath stack nahi hota — jo bara ho wahi apply hota hai).
            </p>
          </div>
        )}
      {editing && product && <SlabModal initial={editing} onClose={() => setEditing(null)} onSave={save} />}
    </div>
  );
}

function SlabModal({ initial, onClose, onSave }) {
  const [minQty, setMinQty] = useState(initial.min_qty ?? '');
  const [pct, setPct] = useState(initial.discount_percent ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try { await onSave({ ...initial, min_qty: Number(minQty), discount_percent: Number(pct) }); }
    catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };
  return (
    <Modal title={initial.id ? 'Edit slab' : 'Add price slab'} onClose={onClose}>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <Field label="Min qty *"><input className="input" type="number" min="1" step="1" required value={minQty} onChange={(e) => setMinQty(e.target.value)} placeholder="e.g. 50" /></Field>
        <Field label="Discount % *"><input className="input" type="number" min="0" max="100" step="any" required value={pct} onChange={(e) => setPct(e.target.value)} placeholder="e.g. 7.5" /></Field>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}

/* ---------------- Wholesale customers ---------------- */
function WholesaleCustomersTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await api.get('/khata/customers/', { params: { page_size: 5000 } });
      // Defensive: filter client-side in case the backend ignores customer_type param.
      setRows(asList(r.data).filter((c) => String(c.customer_type || '').toLowerCase() === 'wholesale'));
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (data) => {
    if (data.id) await api.patch(`/khata/customers/${data.id}/`, data);
    else await api.post('/khata/customers/', { ...data, customer_type: 'wholesale' });
    setEditing(null); load();
  };

  return (
    <div>
      <div className="toolbar">
        <span className="dim">{rows.length} wholesale customers</span>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setEditing({ customer_type: 'wholesale' })}>+ Add wholesale customer</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner /> : rows.length === 0 ? <EmptyState title="No wholesale customers" hint="Wholesale customers yahan add karein." /> : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Name</th><th>Phone</th><th>Auto discount</th><th>Credit limit</th><th>Balance</th><th></th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td><strong>{c.name}</strong> <Badge tone="purple">🏭 Wholesale</Badge></td>
                  <td className="mono">{c.phone || '—'}</td>
                  <td>{Number(c.wholesale_discount_percent || 0) > 0 ? `${c.wholesale_discount_percent}%` : '—'}</td>
                  <td>{Number(c.credit_limit || 0) > 0 ? fmtRs(c.credit_limit) : '—'}</td>
                  <td className={Number(c.balance ?? 0) > 0 ? 't-red' : ''}>{fmtRs(c.balance ?? c.outstanding ?? 0)}</td>
                  <td><button className="btn small" onClick={() => setEditing(c)}>Edit</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <WholesaleCustomerModal initial={editing} onClose={() => setEditing(null)} onSave={save} />}
    </div>
  );
}

function WholesaleCustomerModal({ initial, onClose, onSave }) {
  const [f, setF] = useState({
    name: initial.name || '', phone: initial.phone || '', address: initial.address || '',
    credit_limit: initial.credit_limit ?? '',
    wholesale_discount_percent: initial.wholesale_discount_percent ?? '',
    whatsapp_opt_in: initial.whatsapp_opt_in ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try {
      await onSave({
        ...initial, ...f,
        customer_type: 'wholesale',
        credit_limit: Number(f.credit_limit || 0),
        wholesale_discount_percent: Number(f.wholesale_discount_percent || 0),
      });
    } catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };
  return (
    <Modal title={initial.id ? 'Edit wholesale customer' : 'Add wholesale customer'} onClose={onClose}>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <div className="form-grid">
          <Field label="Name *"><input className="input" required value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
          <Field label="Phone *"><input className="input" required value={f.phone} onChange={(e) => set('phone', e.target.value)} /></Field>
          <Field label="Address" span><input className="input" value={f.address} onChange={(e) => set('address', e.target.value)} /></Field>
          <Field label="Auto wholesale discount %"><input className="input" type="number" min="0" max="100" step="any" value={f.wholesale_discount_percent} onChange={(e) => set('wholesale_discount_percent', e.target.value)} placeholder="e.g. 5" /></Field>
          <Field label="Credit limit (Rs)"><input className="input" type="number" min="0" value={f.credit_limit} onChange={(e) => set('credit_limit', e.target.value)} /></Field>
          <label className="check"><input type="checkbox" checked={!!f.whatsapp_opt_in} onChange={(e) => set('whatsapp_opt_in', e.target.checked)} /> WhatsApp receipts & reminders</label>
        </div>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}

/* ---------------- Wholesale report ---------------- */
function WholesaleReportTab() {
  const [date, setDate] = useState(todayISO());
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/khata/customers/', { params: { page_size: 5000 } })
      .then((r) => setCustomers(asList(r.data).filter((c) => String(c.customer_type || '').toLowerCase() === 'wholesale')))
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await api.get('/reports/wholesale-summary/', {
        params: { date, ...(customerId ? { customer: customerId } : {}) },
      });
      setData(r.data);
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [date, customerId]);
  useEffect(() => { load(); }, [load]);

  const d = data || {};
  const byCustomer = asList(d.by_customer || d.byCustomer);
  const topItems = asList(d.top_items || d.topItems);

  return (
    <div>
      <div className="toolbar">
        <input type="date" className="input" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} />
        <select className="input" value={customerId} onChange={(e) => setCustomerId(e.target.value)} style={{ maxWidth: 260 }}>
          <option value="">All wholesale customers</option>
          {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <div className="spacer" />
        <button className="btn" onClick={load}>Refresh</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Loading report…" /> : !d || Object.keys(d).length === 0 ? (
        <EmptyState title="No wholesale sales" hint="Is date ko koi wholesale sale nahi hui." />
      ) : (
        <>
          <div className="kpi-grid">
            <div className="card kpi"><div className="kpi-label">Wholesale sales <span className="urdu-sub">ہول سیل</span></div><div className="kpi-value t-purple">{fmtRs(d.total_sales ?? d.total ?? 0)}</div></div>
            <div className="card kpi"><div className="kpi-label">Bills</div><div className="kpi-value t-blue">{d.bills_count ?? d.bill_count ?? 0}</div></div>
            <div className="card kpi"><div className="kpi-label">Margin estimate</div><div className="kpi-value t-green">{fmtRs(d.margin_estimate ?? d.margin ?? 0)}</div></div>
          </div>
          <div className="grid-2">
            <div className="card">
              <h3>By customer</h3>
              {byCustomer.length === 0 ? <EmptyState title="No data" /> : (
                <table className="table">
                  <thead><tr><th>Customer</th><th>Bills</th><th>Total</th></tr></thead>
                  <tbody>
                    {byCustomer.map((r, i) => (
                      <tr key={i}>
                        <td><strong>{r.customer_name || r.name || r.customer}</strong></td>
                        <td>{r.bills_count ?? r.bills ?? '—'}</td>
                        <td>{fmtRs(r.total ?? r.total_sales ?? 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="card">
              <h3>Top wholesale items</h3>
              {topItems.length === 0 ? <EmptyState title="No data" /> : (
                <table className="table">
                  <thead><tr><th>Item</th><th>Qty</th><th>Total</th></tr></thead>
                  <tbody>
                    {topItems.map((t, i) => (
                      <tr key={i}>
                        <td>{t.product_name || t.name || t.product}</td>
                        <td>{t.qty ?? t.quantity ?? '—'}</td>
                        <td>{fmtRs(t.total ?? t.revenue ?? 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
