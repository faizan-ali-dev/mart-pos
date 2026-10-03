/**
 * Basic offline support (MVP):
 * - Products + customers are cached in localStorage ("Refresh data" in the topbar re-caches).
 * - If a bill can't reach the API (network error), its payload is queued in
 *   localStorage and retried automatically when the connection returns.
 * - Bills are immutable once created, so queued bills never conflict.
 *
 * This is intentionally simple. The full offline engine (IndexedDB/Dexie +
 * background sync + conflict resolution) is a documented Phase-2 upgrade.
 */
import { api, isNetworkError } from './api.js';

const K = {
  products: 'pos_cache_products',
  customers: 'pos_cache_customers',
  queue: 'pos_queue_bills',
  shop: 'pos_shop_profile',
};

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch { return fallback; }
}
function write(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* storage full */ }
}

// ---------- cached catalog ----------
export const setCachedProducts = (list) => write(K.products, { ts: Date.now(), data: list });
export const getCachedProducts = () => read(K.products, { data: [] }).data || [];
export const getProductsCacheTime = () => read(K.products, {}).ts || null;

export const setCachedCustomers = (list) => write(K.customers, { ts: Date.now(), data: list });
export const getCachedCustomers = () => read(K.customers, { data: [] }).data || [];

// ---------- pending bill queue ----------
export const getQueue = () => read(K.queue, []);
export const queueCount = () => getQueue().length;

export function queueBill(payload) {
  const q = getQueue();
  q.push({ ...payload, _qid: 'q_' + Date.now() + '_' + Math.floor(Math.random() * 1e6), _queuedAt: new Date().toISOString() });
  write(K.queue, q);
  window.dispatchEvent(new Event('pos:queue-changed'));
  return q.length;
}

function dropQueued(qid) {
  write(K.queue, getQueue().filter((b) => b._qid !== qid));
  window.dispatchEvent(new Event('pos:queue-changed'));
}

/**
 * Try to flush queued bills. Returns {sent, failed, remaining}.
 * Bills the server rejects (4xx) are kept in the queue and flushing stops,
 * so a human can inspect them in Settings instead of losing data silently.
 */
export async function flushQueue() {
  const q = getQueue();
  let sent = 0, failed = 0;
  for (const item of q) {
    const { _qid, _queuedAt, ...payload } = item;
    try {
      await api.post('/billing/bills/', payload);
      dropQueued(_qid);
      sent += 1;
    } catch (e) {
      failed += 1;
      break; // stop on first failure; retry later
    }
  }
  return { sent, failed, remaining: getQueue().length };
}

export const isOnline = () => (typeof navigator !== 'undefined' ? navigator.onLine : true);

// ---------- shop profile (local until backend exposes a settings endpoint) ----------
export const DEFAULT_SHOP = {
  name: 'My Mart',
  address: '',
  phone: '',
  footer: '7 din ke andar receipt ke baghair wapsi nahi hogi.',
};
export const getShopProfile = () => ({ ...DEFAULT_SHOP, ...read(K.shop, {}) });
export const saveShopProfile = (p) => write(K.shop, p);

export { isNetworkError };
