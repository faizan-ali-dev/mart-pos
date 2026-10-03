import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg, todayISO, modeLabel } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Modal, Badge } from '../components/ui.jsx';
import { Receipt, WholesaleInvoice } from '../components/Receipt.jsx';
import { getShopProfile } from '../offline.js';

export default function Bills() {
  const [date, setDate] = useState(todayISO());
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState(null);
  const [printBill, setPrintBill] = useState(null);
  const shop = getShopProfile();

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await api.get('/billing/bills/', { params: { date } });
      setBills(asList(r.data));
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (b) => {
    try {
      const r = await api.get(`/billing/bills/${b.id}/`);
      setDetail(r.data);
    } catch { setDetail(b); } // fall back to list row data
  };

  const reprint = async (b) => {
    try {
      const r = await api.get(`/billing/bills/${b.id}/`);
      setPrintBill(r.data);
    } catch { setPrintBill(b); } // fall back to list row data
  };

  useEffect(() => {
    if (!printBill) return;
    const t = setTimeout(() => window.print(), 250);
    const done = () => setPrintBill(null);
    window.addEventListener('afterprint', done);
    return () => { clearTimeout(t); window.removeEventListener('afterprint', done); };
  }, [printBill]);

  const modes = (b) => (b.payments || []).map((p) => p.mode).filter(Boolean);

  return (
    <div>
      <PageHead title="Bills history" actions={
        <input type="date" className="input" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} />
      } />
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Bills load ho rahe hain…" /> : bills.length === 0 ? (
        <EmptyState title="Koi bill nahi" hint="Is date ko koi sale record nahi mili." />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Bill #</th><th>Time</th><th>Items</th><th>Total</th><th>Payment</th><th></th></tr></thead>
            <tbody>
              {bills.map((b) => (
                <tr key={b.id}>
                  <td><strong>#{b.bill_no || b.number || b.id}</strong>{String(b.sale_type || '').toLowerCase() === 'wholesale' && <div><Badge tone="purple">🏭 WS</Badge></div>}</td>
                  <td>{(b.created_at || '').slice(11, 16) || (b.created_at || '').slice(0, 10)}</td>
                  <td>{(b.lines || b.items || []).length}</td>
                  <td>{fmtRs(b.grand_total ?? b.total ?? 0)}</td>
                  <td>{modes(b).map((m) => <Badge key={m} tone="blue">{modeLabel(m)}</Badge>)}</td>
                  <td className="row-actions">
                    <button className="btn small" onClick={() => openDetail(b)}>View</button>
                    <button className="btn small" onClick={() => reprint(b)}>Reprint</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail && (
        <Modal title={<>Bill #{detail.bill_no || detail.number || detail.id}{' '}{String(detail.sale_type || '').toLowerCase() === 'wholesale' && <Badge tone="purple">🏭 Wholesale</Badge>}</>} onClose={() => setDetail(null)} wide>
          <table className="table">
            <thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Disc.</th><th>Total</th></tr></thead>
            <tbody>
              {(detail.lines || detail.items || []).map((l, i) => (
                <tr key={i}>
                  <td>{l.product_name || l.product?.name || 'Item'}</td>
                  <td>{l.qty ?? l.quantity}</td>
                  <td>{fmtRs(l.rate ?? l.price ?? 0)}</td>
                  <td>{fmtRs(l.discount_amount || 0)}</td>
                  <td>{fmtRs(l.total ?? l.line_total ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="tot-row"><span>Subtotal</span><span>{fmtRs(detail.subtotal ?? 0)}</span></div>
          <div className="tot-row"><span>Discount</span><span>{fmtRs(detail.bill_discount_amount ?? detail.discount_total ?? 0)}</span></div>
          <div className="tot-row grand"><span>Total</span><span>{fmtRs(detail.grand_total ?? detail.total ?? 0)}</span></div>
          <div className="tot-row"><span>Payments</span><span>{(detail.payments || []).map((p) => `${modeLabel(p.mode)} ${fmtRs(p.amount)}`).join(' + ')}</span></div>
          {Number(detail.change_due || 0) > 0 && <div className="tot-row"><span>Change</span><span>{fmtRs(detail.change_due)}</span></div>}
          <div style={{ marginTop: 12 }}>
            <button className="btn primary" onClick={() => { setPrintBill(detail); setDetail(null); }}>🖨 Reprint receipt</button>
          </div>
        </Modal>
      )}

      {printBill && (
        <div className="print-area">
          {String(printBill.sale_type || '').toLowerCase() === 'wholesale'
            ? <WholesaleInvoice bill={printBill} shop={shop} />
            : <Receipt bill={printBill} shop={shop} />}
        </div>
      )}
    </div>
  );
}
