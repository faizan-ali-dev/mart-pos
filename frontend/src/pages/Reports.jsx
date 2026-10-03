import { useEffect, useState, useCallback } from 'react';
import { api, asList, fmtRs, errMsg, todayISO, modeLabel } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState } from '../components/ui.jsx';

const TABS = [
  { id: 'sales', label: 'Sales', urdu: 'سیل' },
  { id: 'purchases', label: 'Purchases', urdu: 'خریداری' },
  { id: 'profit', label: 'Profit', urdu: 'منافع' },
];

/** Download a GET response as a file (CSV/Excel export). */
async function downloadFile(path, params, fallbackName) {
  const r = await api.get(path, { params, responseType: 'blob' });
  const blob = r.data instanceof Blob ? r.data : new Blob([r.data]);
  const cd = r.headers?.['content-disposition'] || '';
  const m = cd.match(/filename\*?=(?:UTF-8''|")?([^";\n]+)/i);
  const name = (m && decodeURIComponent(m[1].replace(/"/g, ''))) || fallbackName;
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => window.URL.revokeObjectURL(url), 4000);
}

const stamp = () => todayISO();

export default function Reports() {
  const [tab, setTab] = useState('sales');
  return (
    <div>
      <PageHead title="Reports" urdu="رپورٹس" />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label} {t.urdu && <span className="nav-urdu">{t.urdu}</span>}
          </button>
        ))}
      </div>
      {tab === 'sales' && <SalesTab />}
      {tab === 'purchases' && <PurchasesTab />}
      {tab === 'profit' && <ProfitTab />}
    </div>
  );
}

/* ---------------- Sales ---------------- */
function SalesTab() {
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [saleType, setSaleType] = useState('');
  const [payMode, setPayMode] = useState('');
  const [cats, setCats] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');

  useEffect(() => {
    api.get('/catalog/categories/').then((r) => setCats(asList(r.data))).catch(() => {});
  }, []);

  const params = useCallback(() => {
    const p = { from, to };
    if (search.trim()) p.search = search.trim();
    if (category) p.category = category;
    if (saleType) p.sale_type = saleType;
    if (payMode) p.payment_mode = payMode;
    return p;
  }, [from, to, search, category, saleType, payMode]);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setRows(asList((await api.get('/reports/sales/', { params: params() })).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [params]);
  useEffect(() => { load(); }, [load]);

  const doExport = async (fmt) => {
    setExporting(fmt); setError('');
    try {
      await downloadFile('/reports/sales/', { ...params(), export: fmt },
        `sales_${stamp()}.${fmt === 'xlsx' ? 'xlsx' : 'csv'}`);
    } catch (e) { setError(errMsg(e, 'Export nahi ho saka.')); }
    finally { setExporting(''); }
  };

  const total = rows.reduce((s, r) => s + Number(r.grand_total ?? r.total ?? r.amount ?? 0), 0);

  return (
    <div>
      <div className="toolbar wrap">
        <input type="date" className="input" value={from} max={todayISO()} onChange={(e) => setFrom(e.target.value)} />
        <span className="dim">to</span>
        <input type="date" className="input" value={to} max={todayISO()} onChange={(e) => setTo(e.target.value)} />
        <input className="input" placeholder="Search bill / item…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 160 }} />
        <select className="input" value={category} onChange={(e) => setCategory(e.target.value)} style={{ maxWidth: 170 }}>
          <option value="">All categories</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input" value={saleType} onChange={(e) => setSaleType(e.target.value)} style={{ maxWidth: 140 }}>
          <option value="">Retail + Wholesale</option>
          <option value="retail">Retail</option>
          <option value="wholesale">Wholesale</option>
        </select>
        <select className="input" value={payMode} onChange={(e) => setPayMode(e.target.value)} style={{ maxWidth: 150 }}>
          <option value="">All payments</option>
          <option value="cash">Cash</option>
          <option value="card">Card</option>
          <option value="bank_transfer">Bank Transfer</option>
          <option value="khata">Khata</option>
        </select>
        <div className="spacer" />
        <button className="btn" disabled={!!exporting} onClick={() => doExport('csv')}>{exporting === 'csv' ? '…' : '⬇ CSV'}</button>
        <button className="btn" disabled={!!exporting} onClick={() => doExport('xlsx')}>{exporting === 'xlsx' ? '…' : '⬇ Excel'}</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Loading sales…" /> : rows.length === 0 ? (
        <EmptyState title="No sales" hint="Is filter mein koi sale nahi mili." />
      ) : (
        <div className="card table-wrap">
          <div className="rep-total"><span>{rows.length} bills</span><strong>Total: {fmtRs(total)}</strong></div>
          <table className="table">
            <thead><tr><th>Bill</th><th>Date</th><th>Type</th><th>Customer</th><th>Items</th><th>Payment</th><th>Total</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id || i}>
                  <td className="mono">{r.bill_no || r.number || r.id}</td>
                  <td className="dim small">{(r.created_at || r.date || '').slice(0, 16).replace('T', ' ')}</td>
                  <td>{String(r.sale_type || 'retail') === 'wholesale' ? '🏭 WS' : 'Retail'}</td>
                  <td>{r.customer_name || r.customer?.name || '—'}</td>
                  <td>{r.items_count ?? r.item_count ?? (r.lines || []).length ?? '—'}</td>
                  <td className="small">{asList(r.payments).map((p) => modeLabel(p.mode)).join(', ') || (r.payment_mode ? modeLabel(r.payment_mode) : '—')}</td>
                  <td><strong>{fmtRs(r.grand_total ?? r.total ?? r.amount ?? 0)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------------- Purchases ---------------- */
function PurchasesTab() {
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [search, setSearch] = useState('');
  const [supplierId, setSupplierId] = useState('');
  const [suppliers, setSuppliers] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');

  useEffect(() => {
    api.get('/khata/suppliers/', { params: { page_size: 5000 } })
      .then((r) => setSuppliers(asList(r.data))).catch(() => {});
  }, []);

  const params = useCallback(() => {
    const p = { from, to };
    if (search.trim()) p.search = search.trim();
    if (supplierId) p.supplier = supplierId;
    return p;
  }, [from, to, search, supplierId]);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setRows(asList((await api.get('/reports/purchases/', { params: params() })).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [params]);
  useEffect(() => { load(); }, [load]);

  const doExport = async (fmt) => {
    setExporting(fmt); setError('');
    try {
      await downloadFile('/reports/purchases/', { ...params(), export: fmt },
        `purchases_${stamp()}.${fmt === 'xlsx' ? 'xlsx' : 'csv'}`);
    } catch (e) { setError(errMsg(e, 'Export nahi ho saka.')); }
    finally { setExporting(''); }
  };

  const total = rows.reduce((s, r) => s + Number(r.total_cost ?? r.total ?? r.amount ?? 0), 0);

  return (
    <div>
      <div className="toolbar wrap">
        <input type="date" className="input" value={from} max={todayISO()} onChange={(e) => setFrom(e.target.value)} />
        <span className="dim">to</span>
        <input type="date" className="input" value={to} max={todayISO()} onChange={(e) => setTo(e.target.value)} />
        <input className="input" placeholder="Search GRN / item…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 160 }} />
        <select className="input" value={supplierId} onChange={(e) => setSupplierId(e.target.value)} style={{ maxWidth: 220 }}>
          <option value="">All suppliers</option>
          {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <div className="spacer" />
        <button className="btn" disabled={!!exporting} onClick={() => doExport('csv')}>{exporting === 'csv' ? '…' : '⬇ CSV'}</button>
        <button className="btn" disabled={!!exporting} onClick={() => doExport('xlsx')}>{exporting === 'xlsx' ? '…' : '⬇ Excel'}</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Loading purchases…" /> : rows.length === 0 ? (
        <EmptyState title="No purchases" hint="Is filter mein koi khareedari nahi mili." />
      ) : (
        <div className="card table-wrap">
          <div className="rep-total"><span>{rows.length} records</span><strong>Total: {fmtRs(total)}</strong></div>
          <table className="table">
            <thead><tr><th>Ref</th><th>Date</th><th>Supplier</th><th>Items</th><th>Invoice #</th><th>Total</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id || i}>
                  <td className="mono">{r.grn_no || r.number || r.id}</td>
                  <td className="dim small">{(r.created_at || r.date || r.received_at || '').slice(0, 16).replace('T', ' ')}</td>
                  <td>{r.supplier_name || r.supplier?.name || '—'}</td>
                  <td>{r.items_count ?? r.item_count ?? (r.lines || []).length ?? '—'}</td>
                  <td className="dim">{r.supplier_invoice_no || r.invoice_no || '—'}</td>
                  <td><strong>{fmtRs(r.total_cost ?? r.total ?? r.amount ?? 0)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------------- Profit ---------------- */
function ProfitTab() {
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setData((await api.get('/reports/profit/', { params: { from, to } })).data); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, [from, to]);
  useEffect(() => { load(); }, [load]);

  const d = data || {};
  const sales = Number(d.sales_total ?? d.sales ?? 0);
  const cogs = Number(d.cogs_estimate ?? d.cogs ?? 0);
  const gross = d.gross_profit ?? (sales - cogs);
  const exp = Number(d.expenses_total ?? d.expenses ?? 0);
  const pay = Number(d.payouts_total ?? d.payouts ?? 0);
  const net = d.net_profit ?? (Number(gross) - exp - pay);

  return (
    <div>
      <div className="toolbar">
        <input type="date" className="input" value={from} max={todayISO()} onChange={(e) => setFrom(e.target.value)} />
        <span className="dim">to</span>
        <input type="date" className="input" value={to} max={todayISO()} onChange={(e) => setTo(e.target.value)} />
        <div className="spacer" />
        <button className="btn" onClick={load}>Refresh</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Calculating profit…" /> : !data ? (
        <EmptyState title="No data" hint="Is period ka profit data nahi mila." />
      ) : (
        <>
          <div className="card hero-profit">
            <div className="hero-label">Net profit (خالص منافع) <span className="dim">{from} → {to}</span></div>
            <div className={`hero-value ${Number(net) < 0 ? 't-red' : 't-green'}`}>{fmtRs(net)}</div>
            <div className="hero-break">{fmtRs(sales)} sales − {fmtRs(cogs)} COGS − {fmtRs(exp)} expenses − {fmtRs(pay)} payouts</div>
          </div>
          <div className="kpi-grid">
            <div className="card kpi"><div className="kpi-label">Sales total</div><div className="kpi-value t-green">{fmtRs(sales)}</div></div>
            <div className="card kpi"><div className="kpi-label">COGS (estimate)</div><div className="kpi-value">{fmtRs(cogs)}</div></div>
            <div className="card kpi"><div className="kpi-label">Gross profit</div><div className={`kpi-value ${Number(gross) < 0 ? 't-red' : 't-green'}`}>{fmtRs(gross)}</div></div>
            <div className="card kpi"><div className="kpi-label">Expenses <span className="urdu-sub">اخراجات</span></div><div className="kpi-value t-red">{fmtRs(exp)}</div></div>
            <div className="card kpi"><div className="kpi-label">Payouts</div><div className="kpi-value t-red">{fmtRs(pay)}</div></div>
          </div>
          <p className="dim small" style={{ marginTop: 10 }}>
            Note: COGS har product ki <strong>maujooda average cost</strong> se estimate hota hai — purani khareed rate se thora farq ho sakta hai. Net profit = Gross profit − Expenses − Payouts.
          </p>
        </>
      )}
    </div>
  );
}
