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

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setShifts(asList((await api.get('/billing/shifts/')).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openShift = shifts.find((s) => !s.closed_at && s.status !== 'closed');

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
          </div>
          <button className="btn primary" onClick={() => setClosing(openShift)}>Close shift</button>
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
    </div>
  );
}
