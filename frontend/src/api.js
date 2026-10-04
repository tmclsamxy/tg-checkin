const TOKEN_KEY = 'tgcheckin.token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

function extractMessage(data, status) {
  if (!data) return `请求失败 (${status})`
  if (typeof data === 'string') return data
  if (Array.isArray(data.detail)) {
    // FastAPI validation errors
    return data.detail.map((d) => d.msg || JSON.stringify(d)).join('；')
  }
  return data.detail || data.message || `请求失败 (${status})`
}

async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth && getToken()) headers.Authorization = `Bearer ${getToken()}`

  let res
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, '无法连接到服务器')
  }

  if (res.status === 401 && auth) {
    setToken('')
    window.dispatchEvent(new CustomEvent('tg:unauthorized'))
  }

  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) throw new ApiError(res.status, extractMessage(data, res.status))
  return data
}

export const api = {
  // ---- auth ----
  login: (username, password) => request('/api/auth/login', { method: 'POST', body: { username, password }, auth: false }),
  me: () => request('/api/auth/me'),
  changePassword: (oldPassword, newPassword) =>
    request('/api/auth/password', { method: 'POST', body: { old_password: oldPassword, new_password: newPassword } }),

  // ---- accounts ----
  listAccounts: () => request('/api/accounts'),
  createAccount: (payload) => request('/api/accounts', { method: 'POST', body: payload }),
  updateAccount: (id, payload) => request(`/api/accounts/${id}`, { method: 'PUT', body: payload }),
  deleteAccount: (id) => request(`/api/accounts/${id}`, { method: 'DELETE' }),
  reorderAccounts: (ids) => request('/api/accounts/reorder', { method: 'POST', body: { ids } }),
  requestCode: (id, apiId, apiHash, phone) =>
    request(`/api/accounts/${id}/request-code`, {
      method: 'POST',
      // blank values mean "reuse what the account already has stored"
      body: { api_id: apiId || '', api_hash: apiHash || '', phone: phone || '' }
    }),
  resendCode: (id) => request(`/api/accounts/${id}/resend-code`, { method: 'POST', body: {} }),
  verifyCode: (id, code) => request(`/api/accounts/${id}/verify-code`, { method: 'POST', body: { code } }),
  verifyPassword: (id, password) =>
    request(`/api/accounts/${id}/verify-password`, { method: 'POST', body: { password } }),
  cancelLogin: (id) => request(`/api/accounts/${id}/cancel-login`, { method: 'POST', body: {} }),
  connectAccount: (id) => request(`/api/accounts/${id}/connect`, { method: 'POST', body: {} }),
  disconnectAccount: (id) => request(`/api/accounts/${id}/disconnect`, { method: 'POST', body: {} }),
  logoutAccount: (id) => request(`/api/accounts/${id}/logout`, { method: 'POST', body: {} }),
  connectAllAccounts: () => request('/api/accounts/connect-all', { method: 'POST', body: {} }),

  // ---- tasks ----
  listTasks: (params = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== '') qs.set(k, v)
    })
    const suffix = qs.toString()
    return request(`/api/tasks${suffix ? `?${suffix}` : ''}`)
  },
  createTask: (payload) => request('/api/tasks', { method: 'POST', body: payload }),
  updateTask: (id, payload) => request(`/api/tasks/${id}`, { method: 'PUT', body: payload }),
  deleteTask: (id) => request(`/api/tasks/${id}`, { method: 'DELETE' }),
  toggleTask: (id) => request(`/api/tasks/${id}/toggle`, { method: 'POST', body: {} }),
  runTask: (id) => request(`/api/tasks/${id}/run`, { method: 'POST', body: {} }),
  runAll: (accountId) =>
    request(`/api/tasks/run-all${accountId ? `?account_id=${accountId}` : ''}`, { method: 'POST', body: {} }),
  reorderTasks: (ids) => request('/api/tasks/reorder', { method: 'POST', body: { ids } }),

  // ---- runs ----
  listRuns: (params = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== '') qs.set(k, v)
    })
    return request(`/api/runs?${qs.toString()}`)
  },
  runStats: () => request('/api/runs/stats'),
  clearRuns: (days) => request(`/api/runs${days ? `?days=${days}` : ''}`, { method: 'DELETE' }),

  // ---- settings / system ----
  getSettings: () => request('/api/settings'),
  updateSettings: (payload) => request('/api/settings', { method: 'PUT', body: payload }),
  testNotification: () => request('/api/settings/test-notification', { method: 'POST', body: {} }),
  systemInfo: () => request('/api/system/info'),
  health: () => request('/api/health', { auth: false })
}
