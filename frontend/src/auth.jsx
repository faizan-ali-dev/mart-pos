import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api } from './api.js';

const AuthCtx = createContext(null);

const TENANT_SETTINGS_KEY = 'pos_tenant_settings';
export const DEFAULT_TENANT_SETTINGS = {
  whatsapp_mode: 'dummy', // 'dummy' (simulated) | 'meta' (live Meta Cloud API)
  whatsapp_phone_number_id: '',
  whatsapp_access_token_masked: '',
  whatsapp_test_mode: true,
  whatsapp_test_number: '',
  default_print_format: 'thermal_80', // 'thermal_80' | 'a4'
};
export const loadTenantSettings = () => {
  try {
    return { ...DEFAULT_TENANT_SETTINGS, ...(JSON.parse(localStorage.getItem(TENANT_SETTINGS_KEY)) || {}) };
  } catch { return { ...DEFAULT_TENANT_SETTINGS }; }
};
export const saveTenantSettingsLocal = (s) => {
  try { localStorage.setItem(TENANT_SETTINGS_KEY, JSON.stringify({ ...loadTenantSettings(), ...s })); } catch { /* ignore */ }
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pos_user')) || null; } catch { return null; }
  });
  const [ready, setReady] = useState(false);
  const [tenantSettings, setTenantSettings] = useState(loadTenantSettings);

  /** Fetch tenant-level settings (WhatsApp connection, default print format). Falls back to local copy. */
  const refreshTenantSettings = useCallback(async () => {
    try {
      const r = await api.get('/tenants/settings/');
      const merged = { ...DEFAULT_TENANT_SETTINGS, ...(r.data || {}) };
      localStorage.setItem(TENANT_SETTINGS_KEY, JSON.stringify(merged));
      setTenantSettings(merged);
      return { ok: true, settings: merged, backend: true };
    } catch (e) {
      return { ok: false, settings: loadTenantSettings(), backend: false, error: e };
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('pos_token');
    localStorage.removeItem('pos_user');
    setUser(null);
  }, []);

  // Validate any stored token on boot.
  useEffect(() => {
    const token = localStorage.getItem('pos_token');
    if (!token) { setReady(true); return; }
    api.get('/auth/me/')
      .then((res) => {
        setUser(res.data);
        localStorage.setItem('pos_user', JSON.stringify(res.data));
        refreshTenantSettings().catch(() => {});
      })
      .catch(() => logout())
      .finally(() => setReady(true));
  }, [logout, refreshTenantSettings]);

  // Auto logout when the API says the token is invalid.
  useEffect(() => {
    const h = () => logout();
    window.addEventListener('pos:unauthorized', h);
    return () => window.removeEventListener('pos:unauthorized', h);
  }, [logout]);

  const login = async (username, password) => {
    const res = await api.post('/auth/login/', { username, password });
    const { token, user: u } = res.data || {};
    if (!token) throw new Error('Login failed: no token returned by server.');
    localStorage.setItem('pos_token', token);
    const me = u || (await api.get('/auth/me/')).data;
    localStorage.setItem('pos_user', JSON.stringify(me));
    setUser(me);
    refreshTenantSettings().catch(() => {});
    return me;
  };

  const role = (user && (user.role || user.user_role || user.groups?.[0])) || 'cashier';
  const canManage = role === 'owner' || role === 'manager' || role === 'admin';

  return (
    <AuthCtx.Provider value={{ user, role, canManage, login, logout, ready, tenantSettings, refreshTenantSettings }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
