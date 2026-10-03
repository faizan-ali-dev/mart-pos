import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api } from './api.js';

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pos_user')) || null; } catch { return null; }
  });
  const [ready, setReady] = useState(false);

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
      })
      .catch(() => logout())
      .finally(() => setReady(true));
  }, [logout]);

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
    return me;
  };

  const role = (user && (user.role || user.user_role || user.groups?.[0])) || 'cashier';
  const canManage = role === 'owner' || role === 'manager' || role === 'admin';

  return (
    <AuthCtx.Provider value={{ user, role, canManage, login, logout, ready }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
