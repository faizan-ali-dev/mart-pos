import axios from 'axios';

const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export const API_BASE = BASE;

export const api = axios.create({
  baseURL: `${BASE}/api`,
  timeout: 20000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('pos_token');
  if (token) config.headers.Authorization = `Token ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem('pos_token');
      localStorage.removeItem('pos_user');
      window.dispatchEvent(new Event('pos:unauthorized'));
    }
    return Promise.reject(err);
  }
);

/** Unwrap DRF paginated responses ({results: [...]}) or plain arrays. */
export function asList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

/** True when the request never got a response (offline / server down). */
export function isNetworkError(err) {
  return !err || !err.response;
}

/** Human-friendly message from an axios error. */
export function errMsg(err, fallback = 'Something went wrong') {
  if (!err) return fallback;
  if (!err.response) return 'Server se rabta nahi ho saka — internet ya server check karein.';
  const d = err.response.data;
  if (typeof d === 'string' && d) return d;
  if (d && typeof d === 'object') {
    if (typeof d.detail === 'string') return d.detail;
    // DRF field errors: {field: ["msg"]}
    const parts = [];
    for (const [k, v] of Object.entries(d)) {
      const msg = Array.isArray(v) ? v.join(', ') : String(v);
      parts.push(`${k}: ${msg}`);
    }
    if (parts.length) return parts.join(' | ');
  }
  return fallback;
}

export const fmtRs = (n) => {
  const v = Number(n);
  if (Number.isNaN(v)) return 'Rs 0';
  return 'Rs ' + v.toLocaleString('en-PK', { maximumFractionDigits: 2 });
};

export const todayISO = () => new Date().toISOString().slice(0, 10);

export const PAYMENT_MODES = [
  { value: 'cash', label: 'Cash (نقد)' },
  { value: 'card', label: 'Card (کارڈ)' },
  { value: 'bank_transfer', label: 'Bank Transfer (بینک)' },
  { value: 'khata', label: 'Khata / Udhaar (کھاتہ)' },
];

export const modeLabel = (m) =>
  (PAYMENT_MODES.find((x) => x.value === m) || { label: m }).label;
