const TOKEN_KEY = 'aicte_flow_token'
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
}

async function fetchApi(path, options = {}) {
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, signal: AbortSignal.timeout(120_000) })
  } catch (error) {
    throw new Error(error.name === 'TimeoutError'
      ? 'The demo server is taking longer to start. Please try again.'
      : 'Could not reach the demo server. Please wait a moment and try again.')
  }
  if (res.status === 401 && path !== '/auth/login' && getToken()) {
    setToken(null)
    window.dispatchEvent(new Event('auth:expired'))
    throw new Error('Session expired. Please sign in again.')
  }
  return res
}

async function request(method, path, body, isForm = false, idemKey = null) {
  const headers = {}
  if (idemKey) headers['Idempotency-Key'] = idemKey
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body && !isForm) headers['Content-Type'] = 'application/json'
  const res = await fetchApi(path, {
    method, headers, body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  })
  const ct = res.headers.get('content-type') || ''
  const data = ct.includes('json') ? await res.json() : await res.text()
  if (!res.ok) throw new Error((data && data.detail) ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `Request failed (${res.status})`)
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b, idemKey) => request('POST', p, b || {}, false, idemKey),
  put: (p, b) => request('PUT', p, b),
  upload: (file) => { const f = new FormData(); f.append('file', file); return request('POST', '/files', f, true) },
  download: async (path, name) => {
    const res = await fetchApi(path, { headers: { Authorization: `Bearer ${getToken()}` } })
    if (!res.ok) throw new Error('Download failed')
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob); a.download = name; a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  },
}

export function newKey() {
  try { return crypto.randomUUID() } catch { return `${Date.now()}-${Math.random().toString(16).slice(2)}` }
}
