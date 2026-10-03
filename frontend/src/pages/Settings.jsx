import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api, asList, errMsg } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Field, Badge } from '../components/ui.jsx';
import { useAuth } from '../auth.jsx';
import { getQueue, flushQueue, getShopProfile, saveShopProfile, getProductsCacheTime } from '../offline.js';

const TABS = [
  { id: 'shop', label: 'Shop profile' },
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'data', label: 'Data & offline' },
];

export default function Settings() {
  const [tab, setTab] = useState('shop');
  const { canManage } = useAuth();
  return (
    <div>
      <PageHead title="Settings" actions={
        canManage && <Link className="btn" to="/users">👥 User management</Link>
      } />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      {tab === 'shop' && <ShopTab />}
      {tab === 'whatsapp' && <WhatsAppTab />}
      {tab === 'data' && <DataTab />}
    </div>
  );
}

function ShopTab() {
  const [f, setF] = useState(getShopProfile());
  const [saved, setSaved] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    saveShopProfile(f);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };
  return (
    <form className="card" style={{ maxWidth: 640 }} onSubmit={submit}>
      <h3>Shop profile</h3>
      <p className="dim small">Ye details receipt pe print hongi. (Backend mein settings endpoint nahi hai, is liye ye browser mein save hota hai.)</p>
      <Field label="Shop name *"><input className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label="Address"><input className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
      <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
      <Field label="Receipt footer note"><input className="input" value={f.footer} onChange={(e) => setF({ ...f, footer: e.target.value })} /></Field>
      <button type="submit" className="btn primary">Save</button>
      {saved && <span className="t-green" style={{ marginLeft: 8 }}>✓ Saved</span>}
    </form>
  );
}

function WhatsAppTab() {
  const [rules, setRules] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [to, setTo] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [r, t] = await Promise.all([
        api.get('/notifications/rules/').catch(() => ({ data: [] })),
        api.get('/notifications/templates/').catch(() => ({ data: [] })),
      ]);
      setRules(asList(r.data)); setTemplates(asList(t.data));
    } catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggleRule = async (rule) => {
    try {
      const r = await api.patch(`/notifications/rules/${rule.id}/`, { enabled: !rule.enabled });
      setRules((rs) => rs.map((x) => (x.id === rule.id ? { ...x, ...r.data } : x)));
    } catch (e) { setError(errMsg(e)); }
  };

  const sendTest = async (e) => {
    e.preventDefault(); setSending(true); setSendMsg(null);
    try {
      await api.post('/notifications/send-test/', { to, message });
      setSendMsg({ type: 'ok', text: 'Test message bhej diya gaya ✓' });
    } catch (ex) { setSendMsg({ type: 'error', text: errMsg(ex) }); }
    finally { setSending(false); }
  };

  return (
    <div className="grid-2">
      <div className="card">
        <h3>Message rules</h3>
        <ErrorBox error={error} onRetry={load} />
        {loading ? <Spinner /> : rules.length === 0 ? <EmptyState title="No rules" hint="Backend mein koi notification rule nahi mila." /> : (
          <ul className="list">
            {rules.map((r) => (
              <li key={r.id} className="list-row">
                <span>{r.name || r.event || r.template}{r.description && <div className="dim small">{r.description}</div>}</span>
                <button className={`btn small ${r.enabled ? 'primary' : ''}`} onClick={() => toggleRule(r)}>
                  {r.enabled ? 'ON' : 'OFF'}
                </button>
              </li>
            ))}
          </ul>
        )}
        {templates.length > 0 && (
          <>
            <h3 style={{ marginTop: 16 }}>Templates</h3>
            <ul className="list">
              {templates.map((t) => (
                <li key={t.id} className="list-row"><span>{t.name}<div className="dim small">{(t.body || t.content || '').slice(0, 80)}</div></span><Badge tone={t.approved ? 'green' : 'amber'}>{t.approved ? 'approved' : 'pending'}</Badge></li>
              ))}
            </ul>
          </>
        )}
      </div>
      <form className="card" onSubmit={sendTest}>
        <h3>Send test message</h3>
        {sendMsg && <div className={sendMsg.type === 'ok' ? 'notice ok' : 'error-box'}>{sendMsg.text}</div>}
        <Field label="Phone (with country code) *">
          <input className="input" required value={to} onChange={(e) => setTo(e.target.value)} placeholder="923001234567" />
        </Field>
        <Field label="Message">
          <textarea className="input" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Assalam-o-Alaikum! Ye Mart POS ka test message hai." />
        </Field>
        <button type="submit" className="btn primary" disabled={sending}>{sending ? 'Sending…' : 'Send test'}</button>
      </form>
    </div>
  );
}

function DataTab() {
  const [queue, setQueue] = useState(getQueue());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const cacheTime = getProductsCacheTime();

  const retry = async () => {
    setBusy(true); setMsg('');
    try {
      const r = await flushQueue();
      setQueue(getQueue());
      setMsg(r.remaining === 0 ? `✓ ${r.sent} bill(s) sync ho gaye.` : `${r.sent} synced, ${r.remaining} abhi bhi pending hain.`);
    } catch { setMsg('Sync fail — internet check karein.'); }
    finally { setBusy(false); }
  };

  const clearCache = () => {
    localStorage.removeItem('pos_cache_products');
    localStorage.removeItem('pos_cache_customers');
    setMsg('Local cache clear kar diya gaya.');
  };

  return (
    <div className="card" style={{ maxWidth: 640 }}>
      <h3>Offline queue</h3>
      {queue.length === 0 ? <p className="dim">Koi pending bill nahi — sab sync hai ✓</p> : (
        <>
          <ul className="list">
            {queue.map((b) => (
              <li key={b._qid} className="list-row">
                <span>{(b.lines || []).length} items · queued {(b._queuedAt || '').slice(0, 16).replace('T', ' ')}</span>
                <Badge tone="amber">pending</Badge>
              </li>
            ))}
          </ul>
          <button className="btn primary" onClick={retry} disabled={busy}>{busy ? 'Syncing…' : '↻ Retry sync now'}</button>
        </>
      )}
      {msg && <div className="notice" style={{ marginTop: 8 }}>{msg}</div>}

      <h3 style={{ marginTop: 20 }}>Local cache</h3>
      <p className="dim small">
        Products & customers {cacheTime ? `cached at ${new Date(cacheTime).toLocaleString('en-PK')}` : 'not cached yet'}.
        Topbar mein "Refresh data" se dobara cache karein.
      </p>
      <button className="btn danger-ghost" onClick={clearCache}>Clear cache</button>

      <h3 style={{ marginTop: 20 }}>Offline kaise kaam karta hai</h3>
      <p className="dim small">
        Bill hamesha pehle local save hota hai, phir server ko bheja jata hai. Net na ho to bill
        queue mein chala jata hai aur net aate hi khud sync ho jata hai (har 30 sec retry + "Retry sync now").
        Ye basic queue hai — full IndexedDB/Dexie sync Phase-2 mein aayega.
      </p>
    </div>
  );
}
