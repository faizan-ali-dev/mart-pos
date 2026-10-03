import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Modal, Field, Badge } from '../components/ui.jsx';

export default function Shifts() {
  const [shifts, setShifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [opening, setOpening] = useState('');
  const [showOpen, setShowOpen] = useState(false);
  const [closing, setClosing] = useState(null); // shift object
  const [counted, setCounted] = useState('');
  const [busy, setBusy] = useState(false);
  const [payouts, setPayouts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [showPayout, setShowPayout] = useState(false);
  const [payoutForm, setPayoutForm] = useState({ amount: '', purpose: 'supplier_payment', supplier: '', notes: '' });

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [s, p] = await Promise.all([
        api.get('/billing/shifts/'),
        api.get('/billing/payouts/').catch(() => ({ data: [] })),
      ]);
      setShifts(asList(s.data));
      setPayouts(asList(p.data));
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get('/khata/suppliers/', { params: { page_size: 5000 } })
      .then((r) => setSuppliers(asList(r.data))).catch(() => {});
  }, []);

  const openShift = shifts.find((s) => !s.closed_at && s.status !== 'closed');

  // Payouts belonging to a shift — match by shift id when the field exists,
  // otherwise fall back to showing all (backend may not expose the link yet).
  const payoutsFor = (shift) => {
    if (!shift) return [];
    const withLink = payouts.filter((p) => p.shift != null || p.shift_id != null);
    const list = withLink.length
      ? withLink.filter((p) => String(p.shift ?? p.shift_id) === String(shift.id))
      : payouts;
    return list;
  };
  const openPayouts = payoutsFor(openShift);
  const openPayoutsTotal = openPayouts.reduce((s, p) => s + Number(p.amount || 0), 0);

  const doPayout = async (e) => {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const payload = {
        amount: Number(payoutForm.amount),
        purpose: payoutForm.purpose,
        notes: payoutForm.notes || '',
        ...(payoutForm.purpose === 'supplier_payment' && payoutForm.supplier
          ? { supplier: Number(payoutForm.supplier) } : {}),
      };
      await api.post('/billing/payouts/', payload); // backend auto-attaches the open shift
      setShowPayout(false);
      setPayoutForm({ amount: '', purpose: 'supplier_payment', supplier: '', notes: '' });
      load();
    } catch (e2) { setError(errMsg(e2)); }
    finally { setBusy(false); }
  };

  const purposeLabel = (p) =>
    ({ supplier_payment: 'Supplier payment (سپلائر)', expense: 'Expense (خرچہ)', other: 'Other (دیگر)' })[p] || p;

  const doOpen = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      await api.post('/billing/shifts/', { opening_cash: Number(opening || 0) });
      setShowOpen(false); setOpening(''); load();
    } catch (e2) { setError(errMsg(e2)); }
    finally { setBusy(false); }
  };

  const expectedCash = (s) => Number(s.expected_cash ?? s.expected ?? 0);
  const diff = closing ? Number(counted || 0) - expectedCash(closing) : 0;

  const doClose = async () => {
    setBusy(true);
    try {
      await api.post(`/billing/shifts/${closing.id}/close/`, { counted_cash: Number(counted || 0) });
      setClosing(null); setCounted(''); load();
    } catch (e) { setError(errMsg(e)); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <PageHead title="Shifts" urdu="شِفٹ" actions={
        !openShift && <button className="btn primary" onClick={() => setShowOpen(true)}>+ Open shift</button>
      } />
      <ErrorBox error={error} onRetry={load} />

      {openShift && (
        <div className="card highlight">
          <h3>🟢 Shift open <span className="dim small">since {(openShift.opened_at || '').slice(0, 16).replace('T', ' ')}</span></h3>
          <div className="kpi-grid small">
            <div className="kpi"><div className="kpi-label">Opening cash</div><div className="kpi-value">{fmtRs(openShift.opening_cash ?? 0)}</div></div>
            <div className="kpi"><div className="kpi-label">Expected cash</div><div className="kpi-value">{fmtRs(expectedCash(openShift))}</div></div>
            <div className="kpi"><div className="kpi-label">Bills</div><div className="kpi-value">{openShift.bills_count ?? '—'}</div></div>
            <div className="kpi"><div className="kpi-label">Payouts</div><div className="kpi-value t-red">{fmtRs(openPayoutsTotal)}</div></div>
          </div>
          <div className="row-actions" style={{ marginBottom: 8 }}>
            <button className="btn" onClick={() => setShowPayout(true)}>💸 Record payout</button>
            <button className="btn primary" onClick={() => setClosing(openShift)}>Close shift</button>
          </div>
          <p className="dim small">Expected = opening + cash sales − refunds − payouts (API se, defensively).</p>
          {openPayouts.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table className="table">
                <thead><tr><th>Time</th><th>Purpose</th><th>Supplier</th><th>Notes</th><th>Amount</th></tr></thead>
                <tbody>
                  {openPayouts.map((p) => (
                    <tr key={p.id}>
                      <td className="dim small">{(p.created_at || '').slice(11, 16)}</td>
                      <td>{purposeLabel(p.purpose)}</td>
                      <td>{p.supplier_name || p.supplier?.name || '—'}</td>
                      <td className="dim">{p.notes || '—'}</td>
                      <td className="t-red"><strong>−{fmtRs(p.amount)}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {loading ? <Spinner /> : (
        <div className="card table-wrap" style={{ marginTop: 16 }}>
          <h3>Shift history</h3>
          {shifts.length === 0 ? <EmptyState title="No shifts yet" /> : (
            <table className="table">
              <thead><tr><th>Opened</th><th>Closed</th><th>Opening</th><th>Expected</th><th>Counted</th><th>Diff</th><th>Status</th></tr></thead>
              <tbody>
                {shifts.map((s) => {
                  const d = Number(s.difference ?? (s.counted_cash != null ? Number(s.counted_cash) - expectedCash(s) : 0));
                  return (
                    <tr key={s.id}>
                      <td>{(s.opened_at || '').slice(0, 16).replace('T', ' ')}</td>
                      <td>{s.closed_at ? s.closed_at.slice(0, 16).replace('T', ' ') : '—'}</td>
                      <td>{fmtRs(s.opening_cash ?? 0)}</td>
                      <td>{fmtRs(expectedCash(s))}</td>
                      <td>{s.counted_cash != null ? fmtRs(s.counted_cash) : '—'}</td>
                      <td className={d < 0 ? 't-red' : d > 0 ? 't-green' : ''}>{s.closed_at ? fmtRs(d) : '—'}</td>
                      <td>{s.closed_at ? <Badge tone="gray">Closed</Badge> : <Badge tone="green">Open</Badge>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {showOpen && (
        <Modal title="Open shift" onClose={() => setShowOpen(false)}>
          <form onSubmit={doOpen}>
            <Field label="Opening cash (Rs)">
              <input className="input" type="number" min="0" autoFocus value={opening} onChange={(e) => setOpening(e.target.value)} placeholder="0" />
            </Field>
            <div className="modal-foot">
              <button type="button" className="btn" onClick={() => setShowOpen(false)}>Cancel</button>
              <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Opening…' : 'Open shift'}</button>
            </div>
          </form>
        </Modal>
      )}

      {closing && (
        <Modal title="Close shift" onClose={() => setClosing(null)}>
          <div className="kpi-grid small">
            <div className="kpi"><div className="kpi-label">Expected cash</div><div className="kpi-value">{fmtRs(expectedCash(closing))}</div></div>
            <div className="kpi"><div className="kpi-label">Payouts deducted</div><div className="kpi-value t-red">{fmtRs(payoutsFor(closing).reduce((s, p) => s + Number(p.amount || 0), 0))}</div></div>
            <div className="kpi"><div className="kpi-label">Difference</div><div className={`kpi-value ${diff < 0 ? 't-red' : 't-green'}`}>{fmtRs(diff)}</div></div>
          </div>
          <Field label="Counted cash (Rs)">
            <input className="input" type="number" min="0" autoFocus value={counted} onChange={(e) => setCounted(e.target.value)} placeholder={String(expectedCash(closing))} />
          </Field>
          <div className="modal-foot">
            <button className="btn" onClick={() => setClosing(null)}>Cancel</button>
            <button className="btn primary" onClick={doClose} disabled={busy || counted === ''}>{busy ? 'Closing…' : 'Confirm close'}</button>
          </div>
        </Modal>
      )}
      {showPayout && (
        <Modal title="Record payout (ادائیگی)" onClose={() => setShowPayout(false)}>
          <form onSubmit={doPayout}>
            <div className="form-grid">
              <Field label="Amount (Rs) *">
                <input className="input" type="number" min="0.01" step="any" required autoFocus
                  value={payoutForm.amount} onChange={(e) => setPayoutForm({ ...payoutForm, amount: e.target.value })} placeholder="e.g. 5000" />
              </Field>
              <Field label="Purpose *">
                <select className="input" value={payoutForm.purpose} onChange={(e) => setPayoutForm({ ...payoutForm, purpose: e.target.value })}>
                  <option value="supplier_payment">Supplier payment (سپلائر)</option>
                  <option value="expense">Expense (خرچہ)</option>
                  <option value="other">Other (دیگر)</option>
                </select>
              </Field>
              {payoutForm.purpose === 'supplier_payment' && (
                <Field label="Supplier" span>
                  <select className="input" value={payoutForm.supplier} onChange={(e) => setPayoutForm({ ...payoutForm, supplier: e.target.value })}>
                    <option value="">— Select supplier —</option>
                    {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </Field>
              )}
              <Field label="Notes" span>
                <input className="input" value={payoutForm.notes} onChange={(e) => setPayoutForm({ ...payoutForm, notes: e.target.value })} placeholder="e.g. Milk supplier weekly payment" />
              </Field>
            </div>
            <p className="dim small">Payout khuli shift se auto-attach hogi aur expected cash se minus hogi.</p>
            <div className="modal-foot">
              <button type="button" className="btn" onClick={() => setShowPayout(false)}>Cancel</button>
              <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Record payout'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
