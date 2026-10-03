import { reactive } from 'vue'

export const store = reactive({
  user: null,
  mustChangePassword: false,
  toasts: []
})

let seed = 0

export function toast(message, type = 'info') {
  const id = ++seed
  store.toasts.push({ id, message, type })
  setTimeout(() => dismissToast(id), type === 'error' ? 6000 : 3800)
}

export function dismissToast(id) {
  const index = store.toasts.findIndex((t) => t.id === id)
  if (index !== -1) store.toasts.splice(index, 1)
}

export function setUser(username, mustChangePassword = false) {
  store.user = username
  store.mustChangePassword = mustChangePassword
}

export function clearUser() {
  store.user = null
  store.mustChangePassword = false
}

/** Convert an unknown caught error into a readable message. */
export function errorText(err) {
  if (!err) return '未知错误'
  return err.message || String(err)
}

const UNITS = [
  [60, '秒'],
  [60, '分钟'],
  [24, '小时']
]

export function formatRelative(iso) {
  if (!iso) return '—'
  const then = new Date(iso.replace(' ', 'T') + (iso.endsWith('Z') ? '' : 'Z'))
  if (Number.isNaN(then.getTime())) return iso
  const diff = (Date.now() - then.getTime()) / 1000
  if (diff < 60) return '刚刚'
  let value = diff
  let unit = '秒'
  for (const [factor, name] of UNITS) {
    if (value < factor) break
    value /= factor
    unit = name
  }
  return `${Math.floor(value)} ${unit}前`
}

export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso.replace(' ', 'T') + (iso.endsWith('Z') ? '' : 'Z'))
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
