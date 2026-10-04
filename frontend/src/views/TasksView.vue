<script setup>
import { computed, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import TaskFormModal from '../components/TaskFormModal.vue'
import { api } from '../api'
import { toast, errorText, formatRelative } from '../store'

const tasks = ref([])
const accounts = ref([])
const accountFilter = ref('')
const loading = ref(true)
const runningId = ref(null)
const runningAll = ref(false)
const showForm = ref(false)
const editing = ref(null)
const confirmDelete = ref(null)

const accountNames = () => {
  const map = {}
  accounts.value.forEach((a) => {
    map[a.id] = a.name
  })
  return map
}

function accountName(task) {
  if (!task.account_id) return '默认账号'
  return accountNames()[task.account_id] || '已删除'
}

const visibleTasks = computed(() => {
  if (!accountFilter.value) return tasks.value
  const id = Number(accountFilter.value)
  return tasks.value.filter((task) => task.account_id === id)
})

async function refresh() {
  loading.value = true
  try {
    const [t, a] = await Promise.all([api.listTasks(), api.listAccounts()])
    tasks.value = t
    accounts.value = a
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    loading.value = false
  }
}

async function runAll() {
  runningAll.value = true
  try {
    const logs = await api.runAll(accountFilter.value || null)
    if (!logs.length) {
      toast('没有可执行的任务', 'info')
    } else {
      const failed = logs.filter((log) => log.status !== 'success').length
      toast(failed ? `执行完成，${failed} 项失败` : '全部执行成功', failed ? 'error' : 'success')
    }
    await refresh()
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    runningAll.value = false
  }
}

function openCreate() {
  editing.value = null
  showForm.value = true
}

function openEdit(task) {
  editing.value = task
  showForm.value = true
}

async function toggle(task) {
  try {
    await api.toggleTask(task.id)
    await refresh()
  } catch (err) {
    toast(errorText(err), 'error')
  }
}

async function run(task) {
  runningId.value = task.id
  try {
    const log = await api.runTask(task.id)
    if (log.status === 'success') toast(`${task.name}：执行成功`, 'success')
    else toast(`${task.name}：${log.error || '执行失败'}`, 'error')
    await refresh()
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    runningId.value = null
  }
}

async function remove(task) {
  try {
    await api.deleteTask(task.id)
    toast('任务已删除', 'success')
    confirmDelete.value = null
    await refresh()
  } catch (err) {
    toast(errorText(err), 'error')
  }
}

function describe(task) {
  if (task.action_type === 'message') return `发送消息 ${task.message}`
  if (task.button_type === 'text') return `点击按钮「${task.button_text}」`
  return `点击回调 ${task.callback_data}`
}

onMounted(refresh)
</script>

<template>
  <div class="stack">
    <div class="row-between">
      <p class="muted text-sm">
        共 {{ visibleTasks.length }} 个任务
        <template v-if="accountFilter">（已按账号过滤，共 {{ tasks.length }} 个）</template>
        · 定时任务按此处顺序依次执行
      </p>
      <div class="row">
        <select v-model="accountFilter" class="select" style="width: auto">
          <option value="">全部账号</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <button class="btn" :disabled="runningAll || !tasks.length" @click="runAll">
          <span v-if="runningAll" class="spinner dark"></span>
          <AppIcon v-else name="play" size="15" />
          {{ accountFilter ? '执行该账号任务' : '全部执行' }}
        </button>
        <button class="btn btn-primary" @click="openCreate">
          <AppIcon name="plus" size="15" /> 新建任务
        </button>
      </div>
    </div>

    <div class="card">
      <div v-if="loading" class="empty">加载中…</div>
      <div v-else-if="!tasks.length" class="empty">
        <div class="empty-title">还没有签到任务</div>
        <div class="text-sm">点击右上角「新建任务」添加第一个签到目标。</div>
      </div>
      <div v-else-if="!visibleTasks.length" class="empty">该账号下还没有任务</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width: 40px">#</th>
              <th>目标</th>
              <th>账号</th>
              <th>动作</th>
              <th>状态</th>
              <th>上次执行</th>
              <th style="text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(task, i) in visibleTasks" :key="task.id">
              <td class="muted">{{ i + 1 }}</td>
              <td>
                <div class="cell-strong">{{ task.name }}</div>
                <div class="cell-sub mono">{{ task.target }}</div>
                <div v-if="task.start_command" class="cell-sub">启动命令 {{ task.start_command }}</div>
              </td>
              <td class="text-sm">{{ accountName(task) }}</td>
              <td>
                <span class="badge badge-brand">{{ task.action_type === 'message' ? '消息' : '按钮' }}</span>
                <span v-if="task.auto_captcha" class="badge badge-muted" title="自动识别人机验证并作答">自动验证</span>
                <div class="cell-sub" style="margin-top: 4px">{{ describe(task) }}</div>
              </td>
              <td>
                <span v-if="task.last_status === 'success'" class="badge badge-success"><span class="dot"></span>成功</span>
                <span v-else-if="task.last_status === 'failed'" class="badge badge-failed"><span class="dot"></span>失败</span>
                <span v-else class="badge badge-muted">未执行</span>
                <div v-if="task.last_message" class="cell-sub" style="margin-top: 4px; max-width: 220px">
                  {{ task.last_message.slice(0, 60) }}
                </div>
              </td>
              <td class="text-sm muted" style="white-space: nowrap">
                {{ task.last_run_at ? formatRelative(task.last_run_at) : '—' }}
              </td>
              <td>
                <div class="row-actions">
                  <button class="btn btn-sm" :disabled="runningId === task.id" @click="run(task)">
                    <span v-if="runningId === task.id" class="spinner dark"></span>
                    <AppIcon v-else name="play" size="14" />
                    执行
                  </button>
                  <label class="switch" :title="task.enabled ? '已启用' : '已停用'">
                    <input type="checkbox" :checked="task.enabled" @change="toggle(task)" />
                    <span class="slider"></span>
                  </label>
                  <button class="btn btn-sm btn-ghost" title="编辑" @click="openEdit(task)">
                    <AppIcon name="edit" size="14" />
                  </button>
                  <button class="btn btn-sm btn-ghost" title="删除" @click="confirmDelete = task">
                    <AppIcon name="trash" size="14" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <TaskFormModal
      v-if="showForm"
      :task="editing"
      @close="showForm = false"
      @saved="
        showForm = false;
        refresh()
      "
    />

    <div v-if="confirmDelete" class="modal-mask" @click.self="confirmDelete = null">
      <div class="modal" style="max-width: 400px">
        <div class="modal-header"><h3>删除任务</h3></div>
        <div class="modal-body">
          确定删除「{{ confirmDelete.name }}」吗？该任务的运行日志也会一并清除。
        </div>
        <div class="modal-footer">
          <button class="btn" @click="confirmDelete = null">取消</button>
          <button class="btn btn-danger" @click="remove(confirmDelete)">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>
