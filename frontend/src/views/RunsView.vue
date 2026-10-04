<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { toast, errorText, formatDateTime } from '../store'

const runs = ref([])
const tasks = ref([])
const accounts = ref([])
const stats = ref(null)
const loading = ref(true)
const filters = ref({ task_id: '', account_id: '', status: '', limit: 100 })

async function refresh() {
  loading.value = true
  try {
    const [r, t, a, s] = await Promise.all([
      api.listRuns(filters.value),
      api.listTasks(),
      api.listAccounts(),
      api.runStats()
    ])
    runs.value = r
    tasks.value = t
    accounts.value = a
    stats.value = s
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    loading.value = false
  }
}

async function clearOld() {
  try {
    await api.clearRuns(30)
    toast('已清理 30 天前的日志', 'success')
    await refresh()
  } catch (err) {
    toast(errorText(err), 'error')
  }
}

onMounted(refresh)
</script>

<template>
  <div class="stack">
    <div class="grid grid-4">
      <div class="card stat">
        <div class="stat-label">累计执行</div>
        <div class="stat-value">{{ stats ? stats.total : '—' }}</div>
      </div>
      <div class="card stat">
        <div class="stat-label">成功</div>
        <div class="stat-value" style="color: var(--success)">{{ stats ? stats.success : '—' }}</div>
      </div>
      <div class="card stat">
        <div class="stat-label">失败</div>
        <div class="stat-value" style="color: var(--danger)">{{ stats ? stats.failed : '—' }}</div>
      </div>
      <div class="card stat">
        <div class="stat-label">今日</div>
        <div class="stat-value">{{ stats ? stats.today_total : '—' }}</div>
        <div class="stat-hint">成功 {{ stats ? stats.today_success : 0 }} · 失败 {{ stats ? stats.today_failed : 0 }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>运行日志</h2>
        <div class="row">
          <select v-model="filters.task_id" class="select" style="width: auto" @change="refresh">
            <option value="">全部任务</option>
            <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
          <select v-model="filters.account_id" class="select" style="width: auto" @change="refresh">
            <option value="">全部账号</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
          <select v-model="filters.status" class="select" style="width: auto" @change="refresh">
            <option value="">全部状态</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
          </select>
          <button class="btn btn-sm" @click="refresh">刷新</button>
        </div>
      </div>

      <div v-if="loading" class="empty">加载中…</div>
      <div v-else-if="!runs.length" class="empty">
        <div class="empty-title">没有符合条件的记录</div>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>任务</th>
              <th>账号</th>
              <th>状态</th>
              <th>结果 / 机器人回复</th>
              <th>触发</th>
              <th style="text-align: right">耗时</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in runs" :key="r.id">
              <td class="text-sm muted" style="white-space: nowrap">{{ formatDateTime(r.created_at) }}</td>
              <td>
                <div class="cell-strong">{{ r.task_name }}</div>
                <div class="cell-sub mono">{{ r.target }}</div>
              </td>
              <td class="text-sm">{{ r.account_name || '—' }}</td>
              <td>
                <span class="badge" :class="r.status === 'success' ? 'badge-success' : 'badge-failed'">
                  <span class="dot"></span>{{ r.status === 'success' ? '成功' : '失败' }}
                </span>
              </td>
              <td><div class="reply-text">{{ r.reply || r.error || '—' }}</div></td>
              <td><span class="badge badge-muted">{{ r.trigger === 'scheduled' ? '定时' : '手动' }}</span></td>
              <td style="text-align: right" class="text-sm muted">{{ (r.duration_ms / 1000).toFixed(1) }}s</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="row-between">
      <p class="text-sm muted">仅保留最近 {{ filters.limit }} 条。日志会持续增长，可定期清理。</p>
      <button class="btn btn-danger btn-sm" @click="clearOld">清理 30 天前</button>
    </div>
  </div>
</template>
