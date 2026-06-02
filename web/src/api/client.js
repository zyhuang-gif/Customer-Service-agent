const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export function apiUrl(path) {
  return `${BASE}${path}`
}

export async function api(path, { method = 'GET', body, token } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(apiUrl(path), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail || `请求失败 ${resp.status}`)
  }
  return resp.json()
}
