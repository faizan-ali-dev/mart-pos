import { useEffect } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from './auth.jsx';
import { flushQueue, queueCount } from './offline.js';
import Layout from './components/Layout.jsx';
import Login from './pages/Login.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Billing from './pages/Billing.jsx';
import Bills from './pages/Bills.jsx';
import Inventory from './pages/Inventory.jsx';
import Khata from './pages/Khata.jsx';
import Wholesale from './pages/Wholesale.jsx';
import Shifts from './pages/Shifts.jsx';
import Users from './pages/Users.jsx';
import Settings from './pages/Settings.jsx';
import { Spinner } from './components/ui.jsx';

function Protected({ children }) {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <div className="boot"><Spinner label="Loading…" /></div>;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return children;
}

/** Owner/manager-only gate: cashiers get a friendly 403 card. */
export function ManageOnly({ children }) {
  const { canManage } = useAuth();
  if (!canManage) {
    return (
      <div className="forbidden">
        <div className="forbidden-card">
          <div className="forbidden-icon">🔒</div>
          <h2>Access restricted</h2>
          <p>Ye page sirf <strong>owner / manager</strong> ke liye hai.<br />This page is only available to owners and managers.</p>
        </div>
      </div>
    );
  }
  return children;
}

export default function App() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // Auto-flush the offline bill queue: on boot, when coming back online, and every 30s.
  useEffect(() => {
    if (!user) return;
    let alive = true;
    const tryFlush = async () => {
      if (!alive || queueCount() === 0 || !navigator.onLine) return;
      try { await flushQueue(); } catch { /* retry later */ }
    };
    tryFlush();
    const t = setInterval(tryFlush, 30000);
    window.addEventListener('online', tryFlush);
    const unauth = () => navigate('/login');
    window.addEventListener('pos:unauthorized', unauth);
    return () => { alive = false; clearInterval(t); window.removeEventListener('online', tryFlush); window.removeEventListener('pos:unauthorized', unauth); };
  }, [user, navigate]);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Layout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="billing" element={<Billing />} />
        <Route path="bills" element={<Bills />} />
        <Route path="inventory" element={<Inventory />} />
        <Route path="khata" element={<Khata />} />
        <Route path="wholesale" element={<ManageOnly><Wholesale /></ManageOnly>} />
        <Route path="shifts" element={<Shifts />} />
        <Route path="users" element={<ManageOnly><Users /></ManageOnly>} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
