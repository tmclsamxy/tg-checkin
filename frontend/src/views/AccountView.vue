<script setup>
import { computed, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import AccountFormModal from '../components/AccountFormModal.vue'
import { api } from '../api'
import { toast, errorText, formatRelative } from '../store'

const loading = ref(true)
const busyId = ref(null)
const accounts = ref([])
const modal = ref(null) // { mode, account }

const connectedCount = computed(() => accounts.value.filter((a) => a.connected).length)
const totalTasks = computed(() => accounts.value.reduce((sum, a) => sum + (a.task_count || 0), 0))
const canConnectAll = computed(() => accounts.value.some((a) => !a.connected && a.has_session))

async function refresh() {
  loading.value = true
  try {
    accounts.value = await api.listAccounts()
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    loading.value = false
  }
}

async function withBusy(account, action) {
  busyId.value = account.id
  try {
    await action()
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    busyId.value = null
  }
}

function connect(account) {
  return withBusy(account, async () => {
    await api.connectAccount(account.id)
    toast(`「${account.name}」已连接`, 'success')
    await refresh()
  })
}

function disconnect(account) {
  return withBusy(account, async () => {
    await api.disconnectAccount(account.id)
    toast(`「${account.name}」已断开`, 'success')
    await refresh()
  })
}

async function logout(account) {
  if (!confirm(`确定退出「${account.name}」并清除已保存的会话？\n该账号下的任务需要重新登录后才能运行。`)) return
  return withBusy(account, async () => {
    await api.logoutAccount(account.id)
    toast('已退出登录并清除会话', 'success')
    await refresh()
  })
}

async function remove(account) {
  const extra = account.task_count ? `\n它的 ${account.task_count} 个任务会改为使用默认账号。` : ''
  if (!confirm(`确定删除账号「${account.name}」？${extra}`)) return
  return withBusy(account, async () => {
    const res = await api.deleteAccount(account.id)
    toast(res.message, 'success')
    await refresh()
  })
}

function toggle(account) {
  return withBusy(account, async () => {
    const updated = await api.updateAccount(account.id, { enabled: !account.enabled })
    Object.assign(account, updated)
    toast(updated.enabled ? '账号已启用' : '账号已停用', 'success')
  })
}

async function connectAll() {
  try {
    const res = await api.connectAllAccounts()
    toast(res.message, 'success')
    await refresh()
  } catch (err) {
    toast(errorText(err), 'error')
  }
}

function onSaved() {
  modal.value = null
  refresh()
}

function statusOf(account) {
  if (!account.enabled) return { cls: 'badge-muted', text: '已停用' }
  if (account.needs_code || account.needs_password) return { cls: 'badge-warn', text: '等待验证' }
  if (account.connected) return { cls: 'badge-success', text: '已连接' }
  if (account.has_session) return { cls: 'badge-muted', text: '未连接' }
  return { cls: 'badge-failed', text: '未登录' }
}

onMounted(refresh)
</script>

<template>
  <div class="stack">
    <div class="grid grid-3">
      <div class="card stat">
        <div class="stat-label">账号总数</div>
        <div class="stat-value">{{ accounts.length }}</div>
      </div>
      <div class="card stat">
        <div class="stat-label">已连接</div>
        <div class="stat-value" style="color: var(--success)">{{ connectedCount }}</div>
      </div>
      <div class="card stat">
        <div class="stat-label">名下任务</div>
        <div class="stat-value">{{ totalTasks }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>Telegram 账号</h2>
        <div class="row">
          <button v-if="canConnectAll" class="btn btn-sm" @click="connectAll">
            <AppIcon name="refresh" size="14" /> 全部恢复会话
          </button>
          <button class="btn btn-sm btn-primary" @click="modal = { mode: 'create', account: null }">
            <AppIcon name="plus" size="14" /> 添加账号
          </button>
        </div>
      </div>

      <div v-if="loading" class="empty">加载中…</div>

      <div v-else-if="!accounts.length" class="empty">
        <div class="empty-title">还没有添加任何 Telegram 账号</div>
        <div class="empty-hint">
          每个账号独立登录、独立保存会话，任务可以指定用哪个账号执行。<br />
          多个账号可以共用同一套 API ID / API Hash。
        </div>
        <button class="btn btn-primary" @click="modal = { mode: 'create', account: null }">添加第一个账号</button>
      </div>

      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>账号</th>
              <th>手机号</th>
              <th>状态</th>
              <th>任务</th>
              <th>最近连接</th>
              <th style="text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="account in accounts" :key="account.id">
              <td>
                <div class="cell-strong">{{ account.name }}</div>
                <div class="cell-sub">{{ account.tg_user || '尚未登录' }}</div>
              </td>
              <td class="mono text-sm">{{ account.phone || '—' }}</td>
              <td>
                <span class="badge" :class="statusOf(account).cls">
                  <span class="dot"></span>{{ statusOf(account).text }}
                </span>
                <div v-if="account.last_error" class="cell-sub" style="max-width: 240px">
                  {{ account.last_error }}
                </div>
              </td>
              <td class="text-sm">{{ account.task_count }}</td>
              <td class="text-sm muted" style="white-space: nowrap">
                {{ account.last_connected_at ? formatRelative(account.last_connected_at) : '—' }}
              </td>
              <td style="text-align: right">
                <div class="row-actions">
                  <button
                    v-if="!account.connected && account.has_session"
                    class="btn btn-sm"
                    :disabled="busyId === account.id"
                    @click="connect(account)"
                  >
                    恢复会话
                  </button>
                  <button
                    v-else-if="account.connected"
                    class="btn btn-sm"
                    :disabled="busyId === account.id"
                    @click="disconnect(account)"
                  >
                    断开
                  </button>
                  <button
                    v-else
                    class="btn btn-sm btn-primary"
                    :disabled="busyId === account.id"
                    @click="modal = { mode: 'relogin', account }"
                  >
                    登录
                  </button>

                  <label class="switch" :title="account.enabled ? '已启用，点击停用' : '已停用，点击启用'">
                    <input type="checkbox" :checked="account.enabled" @change="toggle(account)" />
                    <span class="slider"></span>
                  </label>

                  <button class="btn btn-sm btn-ghost" title="编辑账号" @click="modal = { mode: 'edit', account }">
                    <AppIcon name="cog" size="14" />
                  </button>
                  <button
                    class="btn btn-sm btn-ghost"
                    title="重新登录（换手机号或会话失效时用）"
                    @click="modal = { mode: 'relogin', account }"
                  >
                    <AppIcon name="refresh" size="14" />
                  </button>
                  <button
                    class="btn btn-sm btn-ghost"
                    title="退出登录并清除会话"
                    :disabled="busyId === account.id"
                    @click="logout(account)"
                  >
                    <AppIcon name="logout" size="14" />
                  </button>
                  <button
                    class="btn btn-sm btn-danger"
                    title="删除账号（名下任务改为使用默认账号）"
                    :disabled="busyId === account.id"
                    @click="remove(account)"
                  >
                    <AppIcon name="trash" size="14" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="banner banner-info">
      <AppIcon name="key" />
      <div>
        凭据与会话都以 Fernet 加密保存在你的服务器上。同一个账号在多处登录可能触发 Telegram 的风控，
        建议只在这个服务里保持一个长期会话。
      </div>
    </div>

    <AccountFormModal
      v-if="modal"
      :mode="modal.mode"
      :account="modal.account"
      @close="modal = null"
      @saved="onSaved"
    />
  </div>
</template>
