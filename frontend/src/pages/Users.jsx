import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api, asList, errMsg } from '../api.js';
import { PageHead, Spinner, ErrorBox, EmptyState, Field, Badge } from '../components/ui.jsx';
import { useAuth } from '../auth.jsx';
import { getQueue, flushQueue, getShopProfile, saveShopProfile } from '../offline.js';

const ROLE_TONES = { owner: 'purple', manager: 'blue', cashier: 'gray', admin: 'purple' };
export const roleBadge = (role) => <Badge tone={ROLE_TONES[role] || 'gray'}>{role || '—'}</Badge>;

export default function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState(null);
  const [resetting, setResetting] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setUsers(asList((await api.get('/tenants/users/')).data)); }
    catch (e) { setError(errMsg(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggleActive = async (u) => {
    try {
      await api.patch(`/tenants/users/${u.id}/`, { is_active: !u.is_active });
      load();
    } catch (e) { setError(errMsg(e)); }
  };

  return (
    <div>
      <PageHead title="User management" urdu="صارفین" actions={
        <button className="btn primary" onClick={() => setShowAdd(true)}>+ Add user</button>
      } />
      <ErrorBox error={error} onRetry={load} />
      {loading ? <Spinner label="Users load ho rahe hain…" /> : users.length === 0 ? (
        <EmptyState title="No users" hint="Pehla user add karein." />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Status</th><th style={{ textAlign: 'right' }}>Actions</th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td><strong className="mono">{u.username}</strong></td>
                  <td>{[u.first_name, u.last_name].filter(Boolean).join(' ') || '—'}</td>
                  <td>{roleBadge(u.role)}</td>
                  <td>{u.is_active === false ? <Badge tone="red">Inactive</Badge> : <Badge tone="green">Active</Badge>}</td>
                  <td className="row-actions" style={{ textAlign: 'right' }}>
                    <button className="btn small" onClick={() => setEditing(u)}>Edit</button>
                    <button className="btn small" onClick={() => setResetting(u)}>Reset password</button>
                    <button
                      className={`btn small ${u.is_active === false ? 'primary' : 'danger-ghost'}`}
                      onClick={() => toggleActive(u)}
                    >
                      {u.is_active === false ? 'Activate' : 'Deactivate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && <UserForm title="Add user" onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); load(); }} />}
      {editing && <UserForm title={`Edit — ${editing.username}`} initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {resetting && <ResetPassword user={resetting} onClose={() => setResetting(null)} />}
    </div>
  );
}

const ROLES = [
  { value: 'owner', label: 'Owner — full access' },
  { value: 'manager', label: 'Manager — reports, approvals, users' },
  { value: 'cashier', label: 'Cashier — billing only' },
];

function UserForm({ title, initial, onClose, onSaved }) {
  const isNew = !initial;
  const [f, setF] = useState({
    username: initial?.username || '',
    password: '',
    first_name: initial?.first_name || '',
    last_name: initial?.last_name || '',
    role: initial?.role || 'cashier',
    is_active: initial?.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try {
      if (isNew) {
        await api.post('/tenants/users/', {
          username: f.username.trim(), password: f.password,
          first_name: f.first_name.trim(), last_name: f.last_name.trim(),
          role: f.role, is_active: f.is_active,
        });
      } else {
        await api.patch(`/tenants/users/${initial.id}/`, {
          first_name: f.first_name.trim(), last_name: f.last_name.trim(),
          role: f.role, is_active: f.is_active,
        });
      }
      onSaved();
    } catch (ex) { setErr(errMsg(ex)); setBusy(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><h3>{title}</h3><button className="btn icon" onClick={onClose}>✕</button></div>
        <div className="modal-body">
          <form onSubmit={submit}>
            {err && <div className="error-box">{err}</div>}
            <div className="form-grid">
              <Field label="Username *">
                <input className="input" required value={f.username} disabled={!isNew} onChange={(e) => set('username', e.target.value)} placeholder="e.g. cashier2" />
              </Field>
              {isNew && (
                <Field label="Password *">
                  <input className="input" type="password" required minLength={4} value={f.password} onChange={(e) => set('password', e.target.value)} />
                </Field>
              )}
              <Field label="First name"><input className="input" value={f.first_name} onChange={(e) => set('first_name', e.target.value)} /></Field>
              <Field label="Last name"><input className="input" value={f.last_name} onChange={(e) => set('last_name', e.target.value)} /></Field>
              <Field label="Role *">
                <select className="input" value={f.role} onChange={(e) => set('role', e.target.value)}>
                  {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </Field>
              <label className="check"><input type="checkbox" checked={!!f.is_active} onChange={(e) => set('is_active', e.target.checked)} /> Active (login allowed)</label>
            </div>
            <div className="modal-foot">
              <button type="button" className="btn" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function ResetPassword({ user, onClose }) {
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault(); setErr('');
    if (pw !== pw2) { setErr('Passwords match nahi ho rahe.'); return; }
    setBusy(true);
    try {
      await api.post(`/tenants/users/${user.id}/reset-password/`, { password: pw });
      setDone(true);
    } catch (ex) { setErr(errMsg(ex)); }
    finally { setBusy(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><h3>Reset password — {user.username}</h3><button className="btn icon" onClick={onClose}>✕</button></div>
        <div className="modal-body">
          {done ? (
            <div className="notice ok">Password reset ho gaya ✓<div style={{ marginTop: 8 }}><button className="btn primary" onClick={onClose}>Done</button></div></div>
          ) : (
            <form onSubmit={submit}>
              {err && <div className="error-box">{err}</div>}
              <Field label="New password *"><input className="input" type="password" required minLength={4} value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
              <Field label="Confirm password *"><input className="input" type="password" required value={pw2} onChange={(e) => setPw2(e.target.value)} /></Field>
              <div className="modal-foot">
                <button type="button" className="btn" onClick={onClose}>Cancel</button>
                <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Resetting…' : 'Reset password'}</button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
