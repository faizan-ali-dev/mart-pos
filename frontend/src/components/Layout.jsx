import { useEffect, useState, useCallback } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { api, asList } from '../api.js';
import { getShopProfile, getQueue, isOnline, setCachedProducts, setCachedCustomers } from '../offline.js';

const NAV = [
  { to: '/', label: 'Dashboard', icon: '📊', end: true },
  { to: '/billing', label: 'Billing', urdu: 'بلنگ', icon: '🧾' },
  { to: '/bills', label: 'Bills', icon: '🧺' },
  { to: '/inventory', label: 'Inventory', urdu: 'اسٹاک', icon: '📦' },
  { to: '/khata', label: 'Khata', urdu: 'کھاتہ', icon: '📒' },
  { to: '/wholesale', label: 'Wholesale', urdu: 'ہول سیل', icon: '🏭', manage: true },
  { to: '/shifts', label: 'Shifts', icon: '⏰' },
  { to: '/users', label: 'Users', icon: '👥', manage: true },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
];

export default function Layout() {
  const { user, role, canManage, logout } = useAuth();
  const navigate = useNavigate();
  const [queueN, setQueueN] = useState(getQueue().length);
  const [online, setOnline] = useState(isOnline());
  const [shiftOpen, setShiftOpen] = useState(null);
  const [caching, setCaching] = useState(false);
  const shop = getShopProfile();

  const loadShift = useCallback(() => {
    api.get('/billing/shifts/').then((r) => {
      const list = asList(r.data);
      const open = list.find((s) => !s.closed_at && (s.is_open ?? s.status === 'open' ?? true) && s.status !== 'closed');
      setShiftOpen(open || null);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    loadShift();
    const t = setInterval(loadShift, 60000);
    const qh = () => setQueueN(getQueue().length);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('pos:queue-changed', qh);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      clearInterval(t);
      window.removeEventListener('pos:queue-changed', qh);
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, [loadShift]);

  const refreshCache = async () => {
    setCaching(true);
    try {
      const [p, c] = await Promise.all([
        api.get('/catalog/products/', { params: { page_size: 5000 } }),
        api.get('/khata/customers/', { params: { page_size: 5000 } }),
      ]);
      setCachedProducts(asList(p.data));
      setCachedCustomers(asList(c.data));
    } catch { /* best effort */ }
    setCaching(false);
  };

  const items = NAV.filter((n) => {
    if (n.manage && !canManage) return false;
    if (role === 'cashier' && !['/billing', '/bills', '/shifts'].includes(n.to)) return false;
    return true;
  });

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">🛒</span>
          <div>
            <div className="brand-name">{shop.name}</div>
            <div className="brand-sub">Mart POS</div>
          </div>
        </div>
        <nav className="nav">
          {items.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
              <span className="nav-icon">{n.icon}</span>
              <span>{n.label}</span>
              {n.urdu && <span className="nav-urdu">{n.urdu}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <button className="btn ghost small" onClick={() => { logout(); navigate('/login'); }}>⎋ Logout</button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="tb-left">
            <span className={`net ${online ? 'on' : 'off'}`} title={online ? 'Online' : 'Offline'}>
              {online ? '● Online' : '● Offline'}
            </span>
            {queueN > 0 && (
              <button className="btn small warn" onClick={() => navigate('/settings')} title="Bills waiting to sync">
                ⏳ {queueN} bill{queueN > 1 ? 's' : ''} pending sync
              </button>
            )}
            <button className="btn small ghost" onClick={refreshCache} disabled={caching} title="Cache products & customers for offline use">
              {caching ? '…' : '⟳ Refresh data'}
            </button>
          </div>
          <div className="tb-right">
            <button
              className={`shift-pill ${shiftOpen ? 'open' : 'closed'}`}
              onClick={() => navigate('/shifts')}
              title="Shift status"
            >
              {shiftOpen ? `🟢 Shift open` : `⚪ No open shift`}
            </button>
            <span className="user-chip">
              {user?.first_name || user?.username || 'User'}
              <em>{role}</em>
            </span>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
