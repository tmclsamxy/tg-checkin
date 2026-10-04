<script setup>
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import { api } from '../api'
import { toast, errorText, formatRelative, formatDateTime } from '../store'

const router = useRouter()
const loading = ref(true)
const running = ref(false)
const info = ref(null)
const stats = ref(null)
const settings = ref(null)
const runs = ref([])
const tasks = ref([])

async function refresh() {
  loading.value = true
  try {
    const [i, s, st, r, t] = await Promise.all([
      api.systemInfo(),
      api.runStats(),
      api.getSettings(),
      api.listRuns({ limit: 8 }),
      api.listTasks()
    ])
    info.value = i
    stats.value = s
    settings.value = st
    runs.value = r
    tasks.value = t
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    loading.value = false
  }
}

async function runAll() {
  running.value = true
  try {
    const logs = await api.runAll()
    const ok = logs.filter((l) => l.status === 'success').length
    toast(`签到完成：成功 ${ok} / 共 ${logs.length}`, logs.length && ok === logs.length ? 'success' : 'error')
    await refresh()
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    running.value = false
  }
}

const successRate = computed(() => {
  if (!stats.value || !stats.value.total) return '—'
  return `${Math.round((stats.value.success / stats.value.total) * 100)}%`
})

const failedTasks = computed(() => tasks.value.filter((t) => t.last_status === 'failed'))

onMounted(refresh)
</script>

<template>
  <div class="stack">
    <div v-if="settings && !settings.connected_account_count" class="banner banner-warn">
      <AppIcon name="bolt" />
      <div>
        <template v-if="!settings.account_count">
          还没有添加 Telegram 账号。请前往
          <router-link :to="{ name: 'account' }" style="font-weight: 600">Telegram 账号</router-link>
          页面添加并登录，否则无法执行签到。
        </template>
        <template v-else>
          当前没有已连接的账号（共 {{ settings.account_count }} 个）。请前往
          <router-link :to="{ name: 'account' }" style="font-weight: 600">Telegram 账号</router-link>
          页面恢复会话或重新登录。
        </template>
      </div>
    </div>

    <div v-if="settings && !settings.schedule_enabled" class="banner banner-info">
      <AppIcon name="history" />
      <div>定时签到当前已关闭，任务只会在手动触发时执行。</div>
    </div>

    <div class="grid grid-4">
      <div class="card stat">
        <div class="stat-label">签到任务</div>
        <div class="stat-value">{{ info ? info.enabled_task_count : '—' }}<span class="muted" style="font-size: 15px"> / {{ info ? info.task_count : '—' }}</span></div>
        <div class="stat-hint">已启用 / 全部</div>
      </div>
      <div class="card stat">
        <div class="stat-label">今日执行</div>
        <div class="stat-value">{{ stats ? stats.today_total : '—' }}</div>
        <div class="stat-hint">
          成功 {{ stats ? stats.today_success : 0 }} · 失败 {{ stats ? stats.today_failed : 0 }} · 累计成功率 {{ successRate }}
        </div>
      </div>
      <div class="card stat">
        <div class="stat-label">账号</div>
        <div class="stat-value">
          {{ info ? info.connected_account_count : '—' }}<span class="muted" style="font-size: 15px"> / {{ info ? info.account_count : '—' }}</span>
        </div>
        <div class="stat-hint">已连接 / 全部</div>
      </div>
      <div class="card stat">
        <div class="stat-label">下次定时</div>
        <div class="stat-value" style="font-size: 17px">{{ info && info.next_run_at ? formatDateTime(info.next_run_at).slice(5, 16) : '未设置' }}</div>
        <div class="stat-hint">{{ settings ? settings.schedule_time : '' }} · {{ settings ? settings.timezone : '' }}</div>
      </div>
    </div>

    <div class="row-between">
      <div class="row">
        <button class="btn btn-primary" :disabled="running || !tasks.length" @click="runAll">
          <span v-if="running" class="spinner"></span>
          <AppIcon v-else name="play" size="15" />
          {{ running ? '执行中…' : '立即执行全部' }}
        </button>
        <button class="btn" @click="refresh">刷新</button>
      </div>
      <button class="btn btn-ghost btn-sm" @click="router.push({ name: 'runs' })">查看全部日志 →</button>
    </div>

    <div v-if="failedTasks.length" class="banner banner-danger">
      <AppIcon name="close" />
      <div>
        有 {{ failedTasks.length }} 个任务最近一次执行失败：
        {{ failedTasks.map((t) => t.name).join('、') }}
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>最近运行记录</h2>
        <span class="text-sm muted">{{ info ? `服务运行 ${Math.floor(info.uptime_seconds / 3600)} 小时` : '' }}</span>
      </div>
      <div v-if="!runs.length" class="empty">
        <div class="empty-title">暂无运行记录</div>
        <div class="text-sm">点击「立即执行全部」或等待定时任务触发。</div>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>任务</th>
              <th>状态</th>
              <th>机器人回复</th>
              <th>触发</th>
              <th style="text-align: right">时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in runs" :key="r.id">
              <td>
                <div class="cell-strong">{{ r.task_name }}</div>
                <div class="cell-sub mono">{{ r.target }}</div>
              </td>
              <td>
                <span class="badge" :class="r.status === 'success' ? 'badge-success' : 'badge-failed'">
                  <span class="dot"></span>{{ r.status === 'success' ? '成功' : '失败' }}
                </span>
              </td>
              <td><div class="reply-text">{{ r.reply || r.error || '—' }}</div></td>
              <td><span class="badge badge-muted">{{ r.trigger === 'scheduled' ? '定时' : '手动' }}</span></td>
              <td style="text-align: right; white-space: nowrap">{{ formatRelative(r.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
