const API_BASE = import.meta.env.VITE_API_BASE || '';

export async function api(path, options = {}) {
  const token = localStorage.getItem('greenzaction_token');
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (!(options.body instanceof FormData) && options.body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  let data = {};
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) throw new Error(data.error || 'Something went wrong');
  return data;
}

export function saveSession(payload) {
  localStorage.setItem('greenzaction_token', payload.token);
  localStorage.setItem('greenzaction_user', JSON.stringify(payload.user));
}

export function clearSession() {
  localStorage.removeItem('greenzaction_token');
  localStorage.removeItem('greenzaction_user');
}

export function getStoredUser() {
  try { return JSON.parse(localStorage.getItem('greenzaction_user') || 'null'); } catch { return null; }
}
