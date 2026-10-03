import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Modal, Field, Badge } from '../components/ui.jsx';
import { Statement } from '../components/Receipt.jsx';
import { getShopProfile } from '../offline.js';

const TABS = [
  { id: 'customers', label: 'Customers', urdu: 'گاہک' },
  { id: 'aging', label: 'Aging report' },
  { id: 'suppliers', label: 'Suppliers', urdu: 'سپلائر' },
];

export default function Khata() {
  const [tab, setTab] = useState('customers');
  return (
    <div>
      <PageHead title="Khata" urdu="کھاتہ" />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label} {t.urdu && <span className="nav-urdu">{t.urdu}</span>}
          </button>
        ))}
      </div>
      {tab === 'customers' && <CustomersTab />}
      {tab === 'aging' && <AgingTab />}
      {tab === 'suppliers' && <SuppliersTab />}
    </div>
  );
}

/* ---------------- Customers ---------------- */
function CustomersTab() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setRows(asList((await api.get('/khata/customers/', { params: { search: q || undefined } })).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [q]);
  useEffect(() => { const t = setTimeout(load, q ? 400 : 0); return () => clearTimeout(t); }, [load, q]);

  const save = async (data) => {
    if (data.id) await api.patch(`/khata/customers/${data.id}/`, data);
    else await api.post('/khata/customers/', data);
    setEditing(null); load();
  };

  const totalOut = rows.reduce((s, c) => s + Number(c.balance ?? c.outstanding ?? 0), 0);

  return (
    <div>
      <div className="toolbar">
        <input className="input" placeholder="Search name / phone…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 300 }} />
        <div className="spacer" />
        <span className="dim">Total outstanding: <strong className="t-red">{fmtRs(totalOut)}</strong></span>
        <button className="btn primary" onClick={() => setEditing({})}>+ Add customer</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner /> : rows.length === 0 ? <EmptyState title="No customers" hint="Khata customers yahan add karein." /> : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Name</th><th>Type</th><th>Phone</th><th>Balance</th><th>Credit limit</th><th>WhatsApp</th><th></th></tr></thead>
            <tbody>
              {rows.map((c) => {
                const bal = Number(c.balance ?? c.outstanding ?? 0);
                const lim = Number(c.credit_limit ?? 0);
                const isWs = String(c.customer_type || '').toLowerCase() === 'wholesale';
                return (
                  <tr key={c.id} className="clickable" onClick={() => setSelected(c)}>
                    <td><strong>{c.name}</strong></td>
                    <td>{isWs ? <Badge tone="purple">🏭 Wholesale</Badge> : <Badge tone="gray">Retail</Badge>}</td>
                    <td className="mono">{c.phone || '—'}</td>
                    <td className={bal > 0 ? 't-red' : ''}><strong>{fmtRs(bal)}</strong></td>
                    <td>{lim > 0 ? fmtRs(lim) : '—'}{lim > 0 && bal >= lim && <Badge tone="red">over limit</Badge>}</td>
                    <td>{c.whatsapp_opt_in ? '✓' : '—'}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button className="btn small" onClick={() => setEditing(c)}>Edit</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {editing && <CustomerModal initial={editing} onClose={() => setEditing(null)} onSave={save} />}
      {selected && <CustomerDetail customer={selected} onClose={() => { setSelected(null); load(); }} />}
    </div>
  );
}

function CustomerModal({ initial, onClose, onSave }) {
  const [f, setF] = useState({
    name: initial.name || '', phone: initial.phone || '', address: initial.address || '',
    cnic: initial.cnic || '', credit_limit: initial.credit_limit ?? '', notes: initial.notes || '',
    whatsapp_opt_in: initial.whatsapp_opt_in ?? true,
    customer_type: initial.customer_type || 'retail',
    wholesale_discount_percent: initial.wholesale_discount_percent ?? '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try { await onSave({ ...initial, ...f, credit_limit: Number(f.credit_limit || 0), wholesale_discount_percent: Number(f.wholesale_discount_percent || 0) }); }
    catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };
  return (
    <Modal title={initial.id ? 'Edit customer' : 'Add customer'} onClose={onClose}>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <div className="form-grid">
          <Field label="Name *"><input className="input" required value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
          <Field label="Phone *"><input className="input" required value={f.phone} onChange={(e) => set('phone', e.target.value)} placeholder="03xx-xxxxxxx" /></Field>
          <Field label="Customer type">
            <select className="input" value={f.customer_type} onChange={(e) => set('customer_type', e.target.value)}>
              <option value="retail">Retail</option>
              <option value="wholesale">🏭 Wholesale</option>
            </select>
          </Field>
          <Field label="Wholesale auto discount %"><input className="input" type="number" min="0" max="100" step="any" value={f.wholesale_discount_percent} onChange={(e) => set('wholesale_discount_percent', e.target.value)} placeholder="e.g. 5" /></Field>
          <Field label="Address" span><input className="input" value={f.address} onChange={(e) => set('address', e.target.value)} /></Field>
          <Field label="CNIC (optional)"><input className="input" value={f.cnic} onChange={(e) => set('cnic', e.target.value)} /></Field>
          <Field label="Credit limit (Rs)"><input className="input" type="number" min="0" value={f.credit_limit} onChange={(e) => set('credit_limit', e.target.value)} /></Field>
          <Field label="Notes" span><input className="input" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></Field>
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

function CustomerDetail({ customer, onClose }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showPay, setShowPay] = useState(false);
  const [print, setPrint] = useState(false);
  const shop = getShopProfile();

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setEntries(asList((await api.get('/khata/ledger/', { params: { customer: customer.id } })).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [customer.id]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!print) return;
    const t = setTimeout(() => window.print(), 250);
    const done = () => setPrint(false);
    window.addEventListener('afterprint', done);
    return () => { clearTimeout(t); window.removeEventListener('afterprint', done); };
  }, [print]);

  const recordPayment = async ({ amount, mode, reference }) => {
    await api.post('/khata/payments/', { customer: customer.id, amount: Number(amount), mode, reference });
    setShowPay(false); load();
  };

  const bal = Number(customer.balance ?? customer.outstanding ?? 0);

  return (
    <Modal title={`${customer.name} — ledger`} onClose={onClose} wide>
      <div className="toolbar">
        <span>Phone: <strong className="mono">{customer.phone || '—'}</strong></span>
        {String(customer.customer_type || '').toLowerCase() === 'wholesale' && <Badge tone="purple">🏭 Wholesale</Badge>}
        <span>Balance: <strong className={bal > 0 ? 't-red' : 't-green'}>{fmtRs(bal)}</strong></span>
        <div className="spacer" />
        <button className="btn" onClick={() => setPrint(true)}>🖨 Print statement</button>
        <button className="btn primary" onClick={() => setShowPay(true)}>+ Record payment</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner /> : (
        <table className="table">
          <thead><tr><th>Date</th><th>Description</th><th>Bill</th><th>Payment</th><th>Balance</th></tr></thead>
          <tbody>
            {entries.map((e, i) => {
              const debit = Number(e.debit ?? e.bill_amount ?? (e.type === 'bill' ? e.amount : 0));
              const credit = Number(e.credit ?? e.payment_amount ?? (e.type === 'payment' ? e.amount : 0));
              return (
                <tr key={e.id || i}>
                  <td>{(e.date || e.created_at || '').slice(0, 10)}</td>
                  <td>{e.description || e.narration || e.type}</td>
                  <td>{debit > 0 ? <span className="t-red">{fmtRs(debit)}</span> : '—'}</td>
                  <td>{credit > 0 ? <span className="t-green">{fmtRs(credit)}</span> : '—'}</td>
                  <td>{fmtRs(e.balance ?? e.running_balance ?? 0)}</td>
                </tr>
              );
            })}
            {entries.length === 0 && <tr><td colSpan={5}><EmptyState title="No entries" hint="Is customer ka koi khata record nahi." /></td></tr>}
          </tbody>
        </table>
      )}
      {showPay && <PaymentModal title={`Payment — ${customer.name}`} balance={bal} onClose={() => setShowPay(false)} onSave={recordPayment} />}
      {print && (
        <div className="print-area">
          <Statement customer={customer} entries={entries} shop={shop} />
        </div>
      )}
    </Modal>
  );
}

function PaymentModal({ title, balance, onClose, onSave, supplier }) {
  const [amount, setAmount] = useState(balance > 0 ? String(balance) : '');
  const [mode, setMode] = useState('cash');
  const [reference, setReference] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try { await onSave({ amount, mode, reference, supplier }); }
    catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <Field label="Amount (Rs) *"><input className="input" type="number" min="0.01" step="any" required value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Mode">
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="cash">Cash</option>
            <option value="card">Card</option>
            <option value="bank_transfer">Bank transfer</option>
          </select>
        </Field>
        <Field label="Reference"><input className="input" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Optional" /></Field>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Record payment'}</button>
        </div>
      </form>
    </Modal>
  );
}

/* ---------------- Aging ---------------- */
function AgingTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setData((await api.get('/khata/aging/')).data); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const rows = asList(data?.customers || data?.rows || data?.aging);
  const buckets = data?.buckets || ['0–30', '31–60', '61–90', '90+'];
  const total = data?.total ?? rows.reduce((s, r) => s + Number(r.total ?? 0), 0);

  return (
    <div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner /> : (
        <div className="card table-wrap">
          <div className="toolbar"><strong>Total outstanding: <span className="t-red">{fmtRs(total)}</span></strong></div>
          {rows.length === 0 ? <EmptyState title="No overdue balances" hint="Sab khata clear hai ✓" /> : (
            <table className="table">
              <thead><tr><th>Customer</th>{buckets.map((b) => <th key={b}>{b} days</th>)}<th>Total</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td><strong>{r.customer_name || r.name || r.customer}</strong><div className="dim small">{r.phone || ''}</div></td>
                    {buckets.map((b) => <td key={b}>{fmtRs(r[b] ?? r.amounts?.[b] ?? 0)}</td>)}
                    <td><strong className="t-red">{fmtRs(r.total ?? 0)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Suppliers ---------------- */
function SuppliersTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);
  const [paying, setPaying] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setRows(asList((await api.get('/khata/suppliers/')).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (data) => {
    if (data.id) await api.patch(`/khata/suppliers/${data.id}/`, data);
    else await api.post('/khata/suppliers/', data);
    setEditing(null); load();
  };
  // NOTE: backend contract lists /api/khata/payments/ for customer payments;
  // we send {supplier} — backend team to accept supplier payments on the same endpoint.
  const paySupplier = async ({ amount, mode, reference }) => {
    await api.post('/khata/payments/', { supplier: paying.id, amount: Number(amount), mode, reference });
    setPaying(null); load();
  };

  return (
    <div>
      <div className="toolbar">
        <div className="spacer" />
        <button className="btn primary" onClick={() => setEditing({})}>+ Add supplier</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner /> : rows.length === 0 ? <EmptyState title="No suppliers" /> : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Name</th><th>Phone</th><th>Payable</th><th></th></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td><strong>{s.name}</strong></td>
                  <td className="mono">{s.phone || '—'}</td>
                  <td className={Number(s.balance ?? 0) > 0 ? 't-red' : ''}><strong>{fmtRs(s.balance ?? s.payable ?? 0)}</strong></td>
                  <td className="row-actions">
                    <button className="btn small" onClick={() => setEditing(s)}>Edit</button>
                    <button className="btn small primary" onClick={() => setPaying(s)}>Record payment</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <SupplierModal initial={editing} onClose={() => setEditing(null)} onSave={save} />}
      {paying && <PaymentModal title={`Pay supplier — ${paying.name}`} balance={Number(paying.balance ?? 0)} onClose={() => setPaying(null)} onSave={paySupplier} supplier />}
    </div>
  );
}

function SupplierModal({ initial, onClose, onSave }) {
  const [f, setF] = useState({ name: initial.name || '', phone: initial.phone || '', address: initial.address || '', notes: initial.notes || '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try { await onSave({ ...initial, ...f }); }
    catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };
  return (
    <Modal title={initial.id ? 'Edit supplier' : 'Add supplier'} onClose={onClose}>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <Field label="Name *"><input className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="Address"><input className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
        <Field label="Notes"><input className="input" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}
