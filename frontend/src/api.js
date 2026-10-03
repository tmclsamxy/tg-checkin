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

  // ---- telegram ----
  telegramStatus: () => request('/api/telegram/status'),
  requestCode: (apiId, apiHash, phone) =>
    request('/api/telegram/request-code', { method: 'POST', body: { api_id: apiId, api_hash: apiHash, phone } }),
  resendCode: () => request('/api/telegram/resend-code', { method: 'POST', body: {} }),
  verifyCode: (code) => request('/api/telegram/verify-code', { method: 'POST', body: { code } }),
  verifyPassword: (password) => request('/api/telegram/verify-password', { method: 'POST', body: { password } }),
  cancelLogin: () => request('/api/telegram/cancel-login', { method: 'POST', body: {} }),
  connectTelegram: () => request('/api/telegram/connect', { method: 'POST', body: {} }),
  disconnectTelegram: () => request('/api/telegram/disconnect', { method: 'POST', body: {} }),
  logoutTelegram: () => request('/api/telegram/logout', { method: 'POST', body: {} }),
  testNotification: () => request('/api/telegram/test-notification', { method: 'POST', body: {} }),

  // ---- tasks ----
  listTasks: () => request('/api/tasks'),
  createTask: (payload) => request('/api/tasks', { method: 'POST', body: payload }),
  updateTask: (id, payload) => request(`/api/tasks/${id}`, { method: 'PUT', body: payload }),
  deleteTask: (id) => request(`/api/tasks/${id}`, { method: 'DELETE' }),
  toggleTask: (id) => request(`/api/tasks/${id}/toggle`, { method: 'POST', body: {} }),
  runTask: (id) => request(`/api/tasks/${id}/run`, { method: 'POST', body: {} }),
  runAll: () => request('/api/tasks/run-all', { method: 'POST', body: {} }),
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
  systemInfo: () => request('/api/system/info'),
  health: () => request('/api/health', { auth: false })
}
