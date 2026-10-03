import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api, asList, errMsg } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Field, Badge } from '../components/ui.jsx';
import { useAuth, saveTenantSettingsLocal } from '../auth.jsx';
import { getQueue, flushQueue, getShopProfile, saveShopProfile, getProductsCacheTime } from '../offline.js';

const TABS = [
  { id: 'shop', label: 'Shop profile' },
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'printing', label: 'Printing' },
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
      {tab === 'printing' && <PrintingTab />}
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

/**
 * WhatsApp connection settings (owner-only editing).
 * Values are stored server-side via /api/tenants/settings/ so every mart just
 * fills values here after deploy — no code changes needed. Falls back to
 * browser-local storage when the backend endpoint isn't available yet.
 */
function WhatsAppConnectionCard() {
  const { role, canManage, tenantSettings, refreshTenantSettings } = useAuth();
  const isOwner = role === 'owner';
  const [form, setForm] = useState(() => ({
    whatsapp_mode: tenantSettings?.whatsapp_mode || 'dummy',
    whatsapp_phone_number_id: tenantSettings?.whatsapp_phone_number_id || '',
    whatsapp_test_mode: tenantSettings?.whatsapp_test_mode !== false,
    whatsapp_test_number: tenantSettings?.whatsapp_test_number || '',
  }));
  const [masked, setMasked] = useState(() => tenantSettings?.whatsapp_access_token_masked || '');
  const [newToken, setNewToken] = useState('');
  const [changingToken, setChangingToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [localOnly, setLocalOnly] = useState(false);

  useEffect(() => {
    let alive = true;
    refreshTenantSettings().then((r) => {
      if (!alive) return;
      if (r.ok && r.backend) {
        const d = r.settings || {};
        setForm({
          whatsapp_mode: d.whatsapp_mode || 'dummy',
          whatsapp_phone_number_id: d.whatsapp_phone_number_id || '',
          whatsapp_test_mode: d.whatsapp_test_mode !== false,
          whatsapp_test_number: d.whatsapp_test_number || '',
        });
        setMasked(d.whatsapp_access_token_masked || '');
        setLocalOnly(false);
      } else {
        setLocalOnly(true);
      }
    });
    return () => { alive = false; };
  }, [refreshTenantSettings]);

  if (!canManage) return null;

  const save = async (e) => {
    e.preventDefault();
    setSaving(true); setMsg(null);
    const tok = newToken.trim();
    const payload = {
      whatsapp_mode: form.whatsapp_mode,
      whatsapp_phone_number_id: form.whatsapp_phone_number_id.trim(),
      whatsapp_test_mode: !!form.whatsapp_test_mode,
      whatsapp_test_number: form.whatsapp_test_number.trim(),
      default_print_format: tenantSettings?.default_print_format || 'thermal_80',
      ...(tok ? { whatsapp_access_token: tok } : {}),
    };
    try {
      await api.put('/tenants/settings/', payload);
      const r = await refreshTenantSettings();
      if (tok) { setMasked('••••' + tok.slice(-4)); setNewToken(''); setChangingToken(false); }
      setLocalOnly(!(r.ok && r.backend));
      setMsg({ type: 'ok', text: '✓ WhatsApp settings save ho gayin.' });
    } catch (ex) {
      saveTenantSettingsLocal({ ...payload, ...(tok ? { whatsapp_access_token_masked: '••••' + tok.slice(-4) } : {}) });
      if (tok) { setMasked('••••' + tok.slice(-4)); setNewToken(''); setChangingToken(false); }
      setLocalOnly(true);
      setMsg({ type: 'warn', text: 'Backend settings endpoint available nahi — settings sirf is browser mein save hui hain.' });
    } finally { setSaving(false); }
  };

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  if (!isOwner) {
    return (
      <div className="card" style={{ marginBottom: 16 }}>
        <h3>WhatsApp connection</h3>
        <p className="dim small">🔒 Connection settings sirf <strong>owner</strong> change kar sakta hai — tumhare paas read-only access hai.</p>
        <ul className="list">
          <li className="list-row"><span>Mode</span><Badge tone={form.whatsapp_mode === 'meta' ? 'green' : 'gray'}>{form.whatsapp_mode === 'meta' ? 'Live — Meta Cloud API' : 'Testing (simulated)'}</Badge></li>
          <li className="list-row"><span>Phone Number ID</span><span className="dim">{form.whatsapp_phone_number_id || '—'}</span></li>
          <li className="list-row"><span>Access token</span><span className="dim">{masked ? `saved ${masked}` : '—'}</span></li>
          <li className="list-row"><span>Test mode</span><Badge tone={form.whatsapp_test_mode ? 'amber' : 'gray'}>{form.whatsapp_test_mode ? 'ON' : 'OFF'}</Badge></li>
        </ul>
      </div>
    );
  }

  return (
    <form className="card" style={{ marginBottom: 16 }} onSubmit={save}>
      <h3>WhatsApp connection</h3>
      {localOnly && <div className="notice warn" style={{ marginBottom: 8 }}>Backend settings endpoint abhi available nahi — values sirf is browser mein save hongi.</div>}
      {msg && <div className={msg.type === 'ok' ? 'notice ok' : msg.type === 'warn' ? 'notice warn' : 'error-box'} style={{ marginBottom: 8 }}>{msg.text}</div>}
      <Field label="Mode">
        <select className="input" value={form.whatsapp_mode} onChange={set('whatsapp_mode')}>
          <option value="dummy">Testing (simulated) — koi real message nahi jayega</option>
          <option value="meta">Live — Meta Cloud API — asal WhatsApp messages</option>
        </select>
      </Field>
      {form.whatsapp_mode === 'meta' && (
        <>
          <Field label="Phone Number ID *">
            <input className="input" required value={form.whatsapp_phone_number_id} onChange={set('whatsapp_phone_number_id')} placeholder="e.g. 123456789012345" />
          </Field>
          <Field label="Access Token">
            {masked && !changingToken ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span className="dim">✓ Saved <code>{masked}</code></span>
                <button type="button" className="btn small" onClick={() => setChangingToken(true)}>Change</button>
              </div>
            ) : (
              <input
                type="password" className="input" value={newToken} autoComplete="new-password"
                onChange={(e) => setNewToken(e.target.value)}
                placeholder={masked ? 'Naya token likhein (khaali = purana rahega)' : 'Meta access token paste karein'}
              />
            )}
          </Field>
        </>
      )}
      <label className="check" style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '8px 0' }}>
        <input type="checkbox" checked={!!form.whatsapp_test_mode} onChange={set('whatsapp_test_mode')} />
        <span>Test mode <span className="dim">— ON ho to saare messages test number pe jayenge (safe testing)</span></span>
      </label>
      <Field label="Test phone number (country code ke saath)">
        <input className="input" value={form.whatsapp_test_number} onChange={set('whatsapp_test_number')} placeholder="923001234567" />
      </Field>
      <button type="submit" className="btn primary" disabled={saving}>{saving ? 'Saving…' : 'Save WhatsApp settings'}</button>
      <p className="dim small" style={{ marginTop: 10 }}>
        Values kahan se milengi: <strong>developers.facebook.com</strong> → apni app → <strong>WhatsApp → API Setup</strong> →
        wahan <em>Phone number ID</em> aur <em>Access token</em> milta hai. Note: gahak ko pehli dafa bheje jane wale
        messages (jaise udhaar reminder) ke liye Meta se <strong>approved template</strong> chahiye hota hai —
        plain text sirf 24-hour reply window mein jata hai.
      </p>
    </form>
  );
}

function WhatsAppTab() {
  const { tenantSettings } = useAuth();
  const [rules, setRules] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [to, setTo] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState(null);

  // Prefill the test number from tenant settings (once).
  useEffect(() => {
    if (!to && tenantSettings?.whatsapp_test_number) setTo(tenantSettings.whatsapp_test_number);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantSettings]);

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
      const r = await api.post('/notifications/send-test/', { to, message: message || 'Test from Mart POS' });
      const d = r.data || {};
      const okFlag = d.ok !== false;
      setSendMsg({
        type: okFlag ? 'ok' : 'error',
        text: `${okFlag ? '✓' : '✗'} provider: ${d.provider || 'unknown'} → ${d.to || to}${d.detail ? ` · ${d.detail}` : ''}`,
      });
    } catch (ex) { setSendMsg({ type: 'error', text: errMsg(ex) }); }
    finally { setSending(false); }
  };

  return (
    <div>
      <WhatsAppConnectionCard />
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
        <p className="dim small">Test mode ON ho to backend number ko ignore karke test number pe bhejega.</p>
        {sendMsg && <div className={sendMsg.type === 'ok' ? 'notice ok' : 'error-box'}>{sendMsg.text}</div>}
        <Field label="Phone (with country code) *">
          <input className="input" required value={to} onChange={(e) => setTo(e.target.value)} placeholder="923001234567" />
        </Field>
        <Field label="Message">
          <textarea className="input" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Test from Mart POS" />
        </Field>
        <button type="submit" className="btn primary" disabled={sending}>{sending ? 'Sending…' : 'Send test'}</button>
      </form>
      </div>
    </div>
  );
}

function PrintingTab() {
  const { canManage, tenantSettings, refreshTenantSettings } = useAuth();
  const [format, setFormat] = useState(() => tenantSettings?.default_print_format || 'thermal_80');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (tenantSettings?.default_print_format) setFormat(tenantSettings.default_print_format);
  }, [tenantSettings]);

  if (!canManage) {
    return (
      <div className="card">
        <h3>Printing</h3>
        <p className="dim">🔒 Printing settings sirf owner / manager ke liye hain.</p>
      </div>
    );
  }

  const save = async (e) => {
    e.preventDefault();
    setSaving(true); setMsg(null);
    try {
      await api.put('/tenants/settings/', { default_print_format: format });
      await refreshTenantSettings();
      setMsg({ type: 'ok', text: '✓ Default print format save ho gaya.' });
    } catch (ex) {
      saveTenantSettingsLocal({ default_print_format: format });
      setMsg({ type: 'warn', text: 'Backend settings endpoint available nahi — setting sirf is browser mein save hui.' });
    } finally { setSaving(false); }
  };

  return (
    <form className="card" style={{ maxWidth: 640 }} onSubmit={save}>
      <h3>Printing</h3>
      {msg && <div className={msg.type === 'ok' ? 'notice ok' : 'notice warn'} style={{ marginBottom: 8 }}>{msg.text}</div>}
      <p className="dim small">Har bill ke liye default print format. Billing aur Bills history mein har bill pe override kar sakte hain (🧾 80mm / 📄 A4 toggle).</p>
      <Field label="Default print format">
        <select className="input" value={format} onChange={(e) => setFormat(e.target.value)}>
          <option value="thermal_80">🧾 80mm thermal receipt — counter printer ke liye</option>
          <option value="a4">📄 A4 invoice — retail invoice / tax invoice</option>
        </select>
      </Field>
      <button type="submit" className="btn primary" disabled={saving}>{saving ? 'Saving…' : 'Save printing settings'}</button>
    </form>
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
