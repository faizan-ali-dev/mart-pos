import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg, todayISO } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Modal, Field, Badge } from '../components/ui.jsx';

const TABS = [
  { id: 'list', label: 'Expenses', urdu: 'اخراجات' },
  { id: 'categories', label: 'Categories', urdu: 'کیٹیگریز' },
];

const MODES = [
  { value: 'cash', label: 'Cash (نقد)' },
  { value: 'card', label: 'Card (کارڈ)' },
  { value: 'bank_transfer', label: 'Bank Transfer (بینک)' },
];
const modeLabel = (m) => (MODES.find((x) => x.value === m) || { label: m }).label;

export default function Expenses() {
  const [tab, setTab] = useState('list');
  return (
    <div>
      <PageHead title="Expenses" urdu="اخراجات" />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label} {t.urdu && <span className="nav-urdu">{t.urdu}</span>}
          </button>
        ))}
      </div>
      {tab === 'list' && <ExpensesTab />}
      {tab === 'categories' && <CategoriesTab />}
    </div>
  );
}

/* ---------------- Expenses list ---------------- */
function ExpensesTab() {
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [catId, setCatId] = useState('');
  const [rows, setRows] = useState([]);
  const [cats, setCats] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);

  const loadCats = useCallback(async () => {
    try { setCats(asList((await api.get('/expenses/categories/')).data)); } catch { /* ignore */ }
  }, []);
  useEffect(() => { loadCats(); }, [loadCats]);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params = { from, to, ...(catId ? { category: catId } : {}) };
      const [r, s] = await Promise.all([
        api.get('/expenses/expenses/', { params }),
        api.get('/expenses/summary/', { params: { from, to } }).catch(() => ({ data: null })),
      ]);
      setRows(asList(r.data));
      setSummary(s.data);
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [from, to, catId]);
  useEffect(() => { load(); }, [load]);

  const save = async (data) => {
    if (data.id) await api.patch(`/expenses/expenses/${data.id}/`, data);
    else await api.post('/expenses/expenses/', data);
    setEditing(null); load();
  };
  const remove = async (id) => {
    if (!window.confirm('Delete this expense?')) return;
    try { await api.delete(`/expenses/expenses/${id}/`); load(); }
    catch (e) { setError(errMsg(e)); }
  };

  const catName = (id) => cats.find((c) => String(c.id) === String(id))?.name || '—';
  const byCat = asList(summary?.by_category || summary?.byCategory);
  const total = Number(summary?.total ?? rows.reduce((s, r) => s + Number(r.amount || 0), 0));

  return (
    <div>
      <div className="toolbar">
        <input type="date" className="input" value={from} max={todayISO()} onChange={(e) => setFrom(e.target.value)} />
        <span className="dim">to</span>
        <input type="date" className="input" value={to} max={todayISO()} onChange={(e) => setTo(e.target.value)} />
        <select className="input" value={catId} onChange={(e) => setCatId(e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">All categories</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setEditing({})}>+ Add expense</button>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 12 }}>
        <div className="card kpi">
          <div className="kpi-label">Total expenses <span className="urdu-sub">کل اخراجات</span></div>
          <div className="kpi-value t-red">{fmtRs(total)}</div>
        </div>
        {byCat.slice(0, 5).map((b, i) => (
          <div className="card kpi" key={i}>
            <div className="kpi-label">{b.category_name || b.category || b.name}</div>
            <div className="kpi-value">{fmtRs(b.total ?? b.amount ?? 0)}</div>
          </div>
        ))}
      </div>

      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Loading expenses…" /> : rows.length === 0 ? (
        <EmptyState title="No expenses" hint="Is period mein koi kharcha record nahi." />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Date</th><th>Category</th><th>Amount</th><th>Mode</th><th>Notes</th><th></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{(r.date || r.created_at || '').slice(0, 10)}</td>
                  <td><Badge tone="amber">{r.category_name || catName(r.category || r.category_id)}</Badge></td>
                  <td><strong className="t-red">{fmtRs(r.amount)}</strong></td>
                  <td>{modeLabel(r.payment_mode || r.mode)}</td>
                  <td className="dim">{r.notes || r.description || '—'}</td>
                  <td className="row-actions">
                    <button className="btn small" onClick={() => setEditing(r)}>Edit</button>
                    <button className="btn small danger" onClick={() => remove(r.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <ExpenseModal initial={editing} categories={cats} onClose={() => setEditing(null)} onSave={save} />}
    </div>
  );
}

function ExpenseModal({ initial, categories, onClose, onSave }) {
  const [f, setF] = useState({
    date: (initial.date || initial.created_at || todayISO()).slice(0, 10),
    category: initial.category || initial.category_id || '',
    amount: initial.amount ?? '',
    payment_mode: initial.payment_mode || initial.mode || 'cash',
    notes: initial.notes || initial.description || '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try {
      await onSave({
        ...(initial.id ? { id: initial.id } : {}),
        date: f.date,
        category: f.category || null,
        amount: Number(f.amount),
        payment_mode: f.payment_mode,
        notes: f.notes,
      });
    } catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };
  return (
    <Modal title={initial.id ? 'Edit expense' : 'Add expense (خرچہ)'} onClose={onClose}>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <div className="form-grid">
          <Field label="Date *"><input className="input" type="date" required max={todayISO()} value={f.date} onChange={(e) => set('date', e.target.value)} /></Field>
          <Field label="Amount (Rs) *"><input className="input" type="number" min="0.01" step="any" required autoFocus value={f.amount} onChange={(e) => set('amount', e.target.value)} placeholder="e.g. 2500" /></Field>
          <Field label="Category *">
            <select className="input" required value={f.category} onChange={(e) => set('category', e.target.value)}>
              <option value="">— Select —</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Payment mode">
            <select className="input" value={f.payment_mode} onChange={(e) => set('payment_mode', e.target.value)}>
              {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </Field>
          <Field label="Notes" span><input className="input" value={f.notes} onChange={(e) => set('notes', e.target.value)} placeholder="e.g. Bijli ka bill" /></Field>
        </div>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}

/* ---------------- Categories ---------------- */
function CategoriesTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setRows(asList((await api.get('/expenses/categories/')).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (data) => {
    if (data.id) await api.patch(`/expenses/categories/${data.id}/`, { name: data.name, description: data.description });
    else await api.post('/expenses/categories/', { name: data.name, description: data.description });
    setEditing(null); load();
  };
  const remove = async (id) => {
    if (!window.confirm('Delete this category? Expenses using it will keep their record.')) return;
    try { await api.delete(`/expenses/categories/${id}/`); load(); }
    catch (e) { setError(errMsg(e)); }
  };

  return (
    <div>
      <div className="toolbar">
        <span className="dim">{rows.length} categories</span>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setEditing({})}>+ Add category</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner /> : rows.length === 0 ? (
        <EmptyState title="No categories" hint="Pehle kharchon ki categories banayein — Rent, Bijli, Salary…" />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Name</th><th>Description</th><th></th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td><strong>{c.name}</strong></td>
                  <td className="dim">{c.description || '—'}</td>
                  <td className="row-actions">
                    <button className="btn small" onClick={() => setEditing(c)}>Edit</button>
                    <button className="btn small danger" onClick={() => remove(c.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <CategoryModal initial={editing} onClose={() => setEditing(null)} onSave={save} />}
    </div>
  );
}

function CategoryModal({ initial, onClose, onSave }) {
  const [name, setName] = useState(initial.name || '');
  const [desc, setDesc] = useState(initial.description || '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try { await onSave({ ...initial, name: name.trim(), description: desc.trim() }); }
    catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };
  return (
    <Modal title={initial.id ? 'Edit category' : 'Add category'} onClose={onClose}>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <Field label="Name *"><input className="input" required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Rent, Bijli, Salary" /></Field>
        <Field label="Description"><input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}
