import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Modal, Field, Badge } from '../components/ui.jsx';

const TYPES = [
  { value: 'bogo', label: 'Buy X Get Y free', urdu: 'خریدو پاؤ' },
  { value: 'bundle', label: 'Bundle deal (% off 2 items)' },
  { value: 'percent', label: '% off on bill' },
  { value: 'flat', label: 'Flat Rs off on bill' },
];
const typeLabel = (t) => (TYPES.find((x) => x.value === t) || { label: t }).label;
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']; // 0..6

const fmtDate = (d) => (d || '').slice(0, 10);

export default function Promotions() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setRows(asList((await api.get('/promotions/promotions/')).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (data) => {
    if (data.id) await api.patch(`/promotions/promotions/${data.id}/`, data);
    else await api.post('/promotions/promotions/', data);
    setEditing(null); load();
  };
  const remove = async (id) => {
    if (!window.confirm('Delete this promotion?')) return;
    try { await api.delete(`/promotions/promotions/${id}/`); load(); }
    catch (e) { setError(errMsg(e)); }
  };
  const toggle = async (p) => {
    try { await api.patch(`/promotions/promotions/${p.id}/`, { is_active: !p.is_active }); load(); }
    catch (e) { setError(errMsg(e)); }
  };

  const describe = (p) => {
    const t = p.promo_type;
    if (t === 'bogo') return `Buy ${p.buy_qty || '?'} × ${p.buy_product_name || 'item'} → Get ${p.get_qty || '?'} × ${p.get_product_name || 'item'} FREE`;
    if (t === 'bundle') return `${p.buy_product_name || 'A'} + ${p.get_product_name || 'B'} — ${p.discount_percent || 0}% off`;
    if (t === 'percent') return `${p.discount_percent || 0}% off bill${Number(p.min_bill_amount || 0) > 0 ? ` (min ${fmtRs(p.min_bill_amount)})` : ''}`;
    if (t === 'flat') return `${fmtRs(p.discount_amount || 0)} off bill${Number(p.min_bill_amount || 0) > 0 ? ` (min ${fmtRs(p.min_bill_amount)})` : ''}`;
    return '';
  };

  return (
    <div>
      <PageHead title="Promotions" urdu="آفرز" actions={
        <button className="btn primary" onClick={() => setEditing({})}>+ New promotion</button>
      } />
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Loading promotions…" /> : rows.length === 0 ? (
        <EmptyState title="No promotions" hint="Buy-1-Get-1, bundle deals ya bill discounts banayein — billing mein khud apply hongi." />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Name</th><th>Type</th><th>Deal</th><th>Schedule</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className={p.is_active ? '' : 'dim'}>
                  <td><strong>{p.name}</strong></td>
                  <td><Badge tone="green">{typeLabel(p.promo_type)}</Badge></td>
                  <td className="small">{describe(p)}</td>
                  <td className="dim small">
                    {fmtDate(p.start_date) || '—'} → {fmtDate(p.end_date) || '—'}
                    {asList(p.days_of_week).length > 0 && (
                      <div>{asList(p.days_of_week).map((d) => DAYS[Number(d)] || d).join(', ')}</div>
                    )}
                    {(p.time_start || p.time_end) && <div>{(p.time_start || '').slice(0, 5)}–{(p.time_end || '').slice(0, 5)}</div>}
                  </td>
                  <td>
                    <button className={`btn small ${p.is_active ? '' : 'primary'}`} onClick={() => toggle(p)} title="Toggle active">
                      {p.is_active ? '🟢 Active' : '⚪ Off'}
                    </button>
                  </td>
                  <td className="row-actions">
                    <button className="btn small" onClick={() => setEditing(p)}>Edit</button>
                    <button className="btn small danger" onClick={() => remove(p.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="dim small" style={{ padding: '0 12px 12px' }}>
            Promotions billing mein <strong>khud-ba-khud</strong> apply hoti hain (schedule ke andar hon to). Backend authoritative hai — bill par applied promotions dikhengi.
          </p>
        </div>
      )}
      {editing && <PromoModal initial={editing} onClose={() => setEditing(null)} onSave={save} />}
    </div>
  );
}

/* ---------- product search picker ---------- */
function ProductPicker({ label, value, onPick }) {
  const [q, setQ] = useState('');
  const [options, setOptions] = useState([]);
  const search = useCallback(async () => {
    if (!q.trim()) { setOptions([]); return; }
    try {
      const r = await api.get('/catalog/products/', { params: { search: q.trim(), page_size: 10 } });
      setOptions(asList(r.data).filter((p) => p.is_active !== false));
    } catch { /* ignore */ }
  }, [q]);
  useEffect(() => { const t = setTimeout(search, 300); return () => clearTimeout(t); }, [search]);
  return (
    <Field label={label}>
      <div style={{ position: 'relative' }}>
        <input className="input" value={value ? `${value.name} (${value.sku || ''})` : q}
          onChange={(e) => { setQ(e.target.value); if (value) onPick(null); }}
          placeholder="Product search…" readOnly={!!value}
          onClick={() => { if (value) { onPick(null); setQ(''); } }} />
        {!value && options.length > 0 && (
          <div className="suggest">
            {options.map((p) => (
              <button type="button" key={p.id} className="suggest-item" onClick={() => { onPick(p); setQ(''); setOptions([]); }}>
                <span>{p.name}</span><span className="dim">{p.sku}</span><strong>{fmtRs(p.retail_price)}</strong>
              </button>
            ))}
          </div>
        )}
        {value && <div className="dim small">Click to change</div>}
      </div>
    </Field>
  );
}

/* ---------- add/edit modal ---------- */
function PromoModal({ initial, onClose, onSave }) {
  const [f, setF] = useState({
    name: initial.name || '',
    promo_type: initial.promo_type || 'bogo',
    buy_product: initial.buy_product || null,
    buy_qty: initial.buy_qty ?? 1,
    get_product: initial.get_product || null,
    get_qty: initial.get_qty ?? 1,
    discount_percent: initial.discount_percent ?? '',
    discount_amount: initial.discount_amount ?? '',
    min_bill_amount: initial.min_bill_amount ?? '',
    start_date: fmtDate(initial.start_date),
    end_date: fmtDate(initial.end_date),
    days_of_week: asList(initial.days_of_week).map(Number),
    time_start: (initial.time_start || '').slice(0, 5),
    time_end: (initial.time_end || '').slice(0, 5),
    is_active: initial.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const toggleDay = (d) => set('days_of_week',
    f.days_of_week.includes(d) ? f.days_of_week.filter((x) => x !== d) : [...f.days_of_week, d].sort());

  // Resolve product ids → objects for display when editing an existing promo.
  useEffect(() => {
    const need = [];
    if (typeof f.buy_product === 'number') need.push(['buy_product', f.buy_product]);
    if (typeof f.get_product === 'number') need.push(['get_product', f.get_product]);
    if (!need.length) return;
    let alive = true;
    (async () => {
      for (const [k, id] of need) {
        try {
          const r = await api.get(`/catalog/products/${id}/`);
          if (alive) set(k, r.data);
        } catch { /* leave as-is */ }
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try {
      const pid = (p) => (p && typeof p === 'object' ? p.id : (p || null));
      const payload = {
        ...(initial.id ? { id: initial.id } : {}),
        name: f.name.trim(),
        promo_type: f.promo_type,
        buy_product: pid(f.buy_product),
        buy_qty: Number(f.buy_qty || 0) || null,
        get_product: pid(f.get_product),
        get_qty: Number(f.get_qty || 0) || null,
        discount_percent: f.discount_percent === '' ? null : Number(f.discount_percent),
        discount_amount: f.discount_amount === '' ? null : Number(f.discount_amount),
        min_bill_amount: f.min_bill_amount === '' ? null : Number(f.min_bill_amount),
        start_date: f.start_date || null,
        end_date: f.end_date || null,
        days_of_week: f.days_of_week,
        time_start: f.time_start || null,
        time_end: f.time_end || null,
        is_active: !!f.is_active,
      };
      await onSave(payload);
    } catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };

  const t = f.promo_type;
  return (
    <Modal title={initial.id ? 'Edit promotion' : 'New promotion'} onClose={onClose} wide>
      <form onSubmit={submit}>
        {err && <div className="error-box">{err}</div>}
        <div className="form-grid">
          <Field label="Name *"><input className="input" required autoFocus value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Weekend BOGO — Cooking Oil" /></Field>
          <Field label="Type *">
            <select className="input" value={f.promo_type} onChange={(e) => set('promo_type', e.target.value)}>
              {TYPES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
            </select>
          </Field>
        </div>

        {t === 'bogo' && (
          <div className="form-grid">
            <ProductPicker label="Buy product *" value={typeof f.buy_product === 'object' ? f.buy_product : null} onPick={(p) => set('buy_product', p)} />
            <Field label="Buy qty *"><input className="input" type="number" min="1" step="1" required value={f.buy_qty} onChange={(e) => set('buy_qty', e.target.value)} /></Field>
            <ProductPicker label="Get product (FREE) *" value={typeof f.get_product === 'object' ? f.get_product : null} onPick={(p) => set('get_product', p)} />
            <Field label="Get qty *"><input className="input" type="number" min="1" step="1" required value={f.get_qty} onChange={(e) => set('get_qty', e.target.value)} /></Field>
          </div>
        )}
        {t === 'bundle' && (
          <div className="form-grid">
            <ProductPicker label="Product A *" value={typeof f.buy_product === 'object' ? f.buy_product : null} onPick={(p) => set('buy_product', p)} />
            <ProductPicker label="Product B *" value={typeof f.get_product === 'object' ? f.get_product : null} onPick={(p) => set('get_product', p)} />
            <Field label="Bundle discount % *"><input className="input" type="number" min="0" max="100" step="any" required value={f.discount_percent} onChange={(e) => set('discount_percent', e.target.value)} placeholder="e.g. 10" /></Field>
          </div>
        )}
        {t === 'percent' && (
          <div className="form-grid">
            <Field label="Discount % *"><input className="input" type="number" min="0" max="100" step="any" required value={f.discount_percent} onChange={(e) => set('discount_percent', e.target.value)} placeholder="e.g. 5" /></Field>
            <Field label="Min bill amount (Rs)"><input className="input" type="number" min="0" value={f.min_bill_amount} onChange={(e) => set('min_bill_amount', e.target.value)} placeholder="Optional" /></Field>
          </div>
        )}
        {t === 'flat' && (
          <div className="form-grid">
            <Field label="Discount amount (Rs) *"><input className="input" type="number" min="0.01" step="any" required value={f.discount_amount} onChange={(e) => set('discount_amount', e.target.value)} placeholder="e.g. 200" /></Field>
            <Field label="Min bill amount (Rs)"><input className="input" type="number" min="0" value={f.min_bill_amount} onChange={(e) => set('min_bill_amount', e.target.value)} placeholder="Optional" /></Field>
          </div>
        )}

        <h4 className="sub-h">Schedule <span className="dim small">(khali = hamesha active)</span></h4>
        <div className="form-grid">
          <Field label="Start date"><input className="input" type="date" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></Field>
          <Field label="End date"><input className="input" type="date" min={f.start_date || undefined} value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></Field>
          <Field label="Time from"><input className="input" type="time" value={f.time_start} onChange={(e) => set('time_start', e.target.value)} /></Field>
          <Field label="Time to"><input className="input" type="time" value={f.time_end} onChange={(e) => set('time_end', e.target.value)} /></Field>
        </div>
        <div className="day-checks">
          {DAYS.map((d, i) => (
            <label key={i} className={`check pill${f.days_of_week.includes(i) ? ' on' : ''}`}>
              <input type="checkbox" checked={f.days_of_week.includes(i)} onChange={() => toggleDay(i)} /> {d}
            </label>
          ))}
          <span className="dim small">koi din select na karein = roz active</span>
        </div>

        <label className="check" style={{ marginTop: 10 }}>
          <input type="checkbox" checked={!!f.is_active} onChange={(e) => set('is_active', e.target.checked)} />
          Active (billing mein apply ho)
        </label>

        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save promotion'}</button>
        </div>
      </form>
    </Modal>
  );
}
