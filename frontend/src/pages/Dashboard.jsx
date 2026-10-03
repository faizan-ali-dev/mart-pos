import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, todayISO, errMsg } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Badge } from '../components/ui.jsx';

export default function Dashboard() {
  const [date, setDate] = useState(todayISO());
  const [summary, setSummary] = useState(null);
  const [wsSummary, setWsSummary] = useState(null);
  const [profit, setProfit] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [s, a, w, p] = await Promise.all([
        api.get('/reports/daily-summary/', { params: { date } }),
        api.get('/inventory/alerts/'),
        api.get('/reports/wholesale-summary/', { params: { date } }).catch(() => ({ data: null })),
        api.get('/reports/profit/', { params: { from: date, to: date } }).catch(() => ({ data: null })),
      ]);
      setSummary(s.data);
      setAlerts(a.data);
      setWsSummary(w.data);
      setProfit(p.data);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const s = summary || {};
  const byMode = s.by_mode || s.payment_split || {};
  const topItems = asList(s.top_items || s.top_selling || s.topItems);
  const lowStock = asList(alerts?.low_stock || alerts?.lowStock);
  const expiring = asList(alerts?.expiring || alerts?.expiry || alerts?.expiring_soon);

  const wsTotal = Number(wsSummary?.total_sales ?? wsSummary?.total ?? 0);
  const dayTotal = Number(s.total_sales ?? s.total ?? 0);
  const retailTotal = Math.max(0, dayTotal - wsTotal);

  // Net profit: prefer backend-computed net_profit (daily-summary or profit endpoint), else sales − expenses − payouts.
  const expTotal = Number(s.expenses_total ?? profit?.expenses_total ?? 0);
  const payTotal = Number(s.payouts_total ?? profit?.payouts_total ?? 0);
  const netProfit = s.net_profit ?? profit?.net_profit ?? (dayTotal - expTotal - payTotal);

  const kpis = [
    { label: "Today's Sales", urdu: 'آج کی سیل', value: fmtRs(dayTotal), tone: 'green' },
    { label: 'Wholesale today', urdu: 'ہول سیل', value: fmtRs(wsTotal), tone: 'purple' },
    { label: 'Bills', urdu: 'بل', value: s.bills_count ?? s.bill_count ?? 0, tone: 'blue' },
    { label: 'Cash', urdu: 'نقد', value: fmtRs(byMode.cash ?? 0), tone: 'gray' },
    { label: 'Card + Bank', value: fmtRs((byMode.card ?? 0) + (byMode.bank_transfer ?? 0)), tone: 'gray' },
    { label: 'Khata (credit)', urdu: 'ادھار', value: fmtRs(byMode.khata ?? 0), tone: 'amber' },
    { label: 'Low-stock items', urdu: 'کم اسٹاک', value: lowStock.length, tone: lowStock.length ? 'red' : 'gray' },
  ];

  return (
    <div>
      <PageHead
        title="Dashboard"
        actions={<input type="date" className="input" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} />}
      />
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Loading dashboard…" /> : (
        <>
          <div className="card hero-profit">
            <div className="hero-label">Net profit today <span className="urdu-sub">خالص منافع</span> <span className="dim">{date}</span></div>
            <div className={`hero-value ${Number(netProfit) < 0 ? 't-red' : 't-green'}`}>{fmtRs(netProfit)}</div>
            <div className="hero-break">{fmtRs(dayTotal)} sales − {fmtRs(expTotal)} expenses − {fmtRs(payTotal)} payouts</div>
          </div>
          <div className="kpi-grid">
            {kpis.map((k) => (
              <div className="card kpi" key={k.label}>
                <div className="kpi-label">{k.label} {k.urdu && <span className="urdu-sub">{k.urdu}</span>}</div>
                <div className={`kpi-value t-${k.tone}`}>{k.value}</div>
              </div>
            ))}
          </div>

          <div className="grid-2">
            <div className="card">
              <h3>Retail vs Wholesale</h3>
              <div className="split-bars">
                <div className="split-row">
                  <span>Retail</span>
                  <div className="split-track"><div className="split-fill r" style={{ width: `${dayTotal > 0 ? (retailTotal / dayTotal) * 100 : 0}%` }} /></div>
                  <strong>{fmtRs(retailTotal)}</strong>
                </div>
                <div className="split-row">
                  <span>Wholesale</span>
                  <div className="split-track"><div className="split-fill w" style={{ width: `${dayTotal > 0 ? (wsTotal / dayTotal) * 100 : 0}%` }} /></div>
                  <strong>{fmtRs(wsTotal)}</strong>
                </div>
              </div>
              <p className="dim small">Sale-type split for {date}. Wholesale from wholesale-summary report.</p>
            </div>

            <div className="card">
              <h3>Top selling items</h3>
              {topItems.length === 0 ? <EmptyState title="No sales data" hint="Abhi tak is date ki koi sale nahi." /> : (
                <table className="table">
                  <thead><tr><th>Item</th><th>Qty</th><th>Total</th></tr></thead>
                  <tbody>
                    {topItems.slice(0, 10).map((t, i) => (
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

            <div className="card">
              <h3>Alerts</h3>
              <h4 className="sub-h">Low stock {lowStock.length > 0 && <Badge tone="red">{lowStock.length}</Badge>}</h4>
              {lowStock.length === 0 ? <p className="dim">All stocked up ✓</p> : (
                <ul className="alert-list">
                  {lowStock.slice(0, 8).map((p, i) => (
                    <li key={i}><span>{p.product_name || p.name}</span><Badge tone="red">{p.qty ?? p.stock ?? 0} left</Badge></li>
                  ))}
                </ul>
              )}
              <h4 className="sub-h">Expiring soon {expiring.length > 0 && <Badge tone="amber">{expiring.length}</Badge>}</h4>
              {expiring.length === 0 ? <p className="dim">No expiring items ✓</p> : (
                <ul className="alert-list">
                  {expiring.slice(0, 8).map((p, i) => (
                    <li key={i}><span>{p.product_name || p.name}</span><Badge tone="amber">{(p.expiry_date || '').slice(0, 10)}</Badge></li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
