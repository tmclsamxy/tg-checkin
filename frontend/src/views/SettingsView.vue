<script setup>
import { onMounted, reactive, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { api } from '../api'
import { toast, errorText, store } from '../store'

const loading = ref(true)
const saving = ref(false)
const settings = ref(null)
const info = ref(null)

const form = reactive({
  api_id: '',
  api_hash: '',
  phone: '',
  schedule_enabled: true,
  schedule_time: '08:00',
  timezone: 'Asia/Shanghai',
  notify_enabled: false,
  notify_bot_token: '',
  notify_receiver_id: '',
  notify_only_on_failure: false,
  reply_wait_seconds: 8,
  start_command_delay: 5,
  task_interval_seconds: 5,
  max_retries: 1
})

const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const pwdSaving = ref(false)

async function refresh() {
  loading.value = true
  try {
    const [s, i] = await Promise.all([api.getSettings(), api.systemInfo()])
    settings.value = s
    info.value = i
    Object.assign(form, {
      api_id: s.api_id || '',
      phone: s.phone || '',
      schedule_enabled: s.schedule_enabled,
      schedule_time: s.schedule_time,
      timezone: s.timezone,
      notify_enabled: s.notify_enabled,
      notify_receiver_id: s.notify_receiver_id || '',
      notify_only_on_failure: s.notify_only_on_failure,
      reply_wait_seconds: s.reply_wait_seconds,
      start_command_delay: s.start_command_delay,
      task_interval_seconds: s.task_interval_seconds,
      max_retries: s.max_retries
    })
    form.api_hash = ''
    form.notify_bot_token = ''
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const payload = { ...form }
    if (!payload.api_hash) delete payload.api_hash
    if (!payload.notify_bot_token) delete payload.notify_bot_token
    settings.value = await api.updateSettings(payload)
    form.api_hash = ''
    form.notify_bot_token = ''
    toast('设置已保存', 'success')
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    saving.value = false
  }
}

async function testNotify() {
  try {
    const res = await api.testNotification()
    toast(res.message, res.ok ? 'success' : 'error')
  } catch (err) {
    toast(errorText(err), 'error')
  }
}

async function changePassword() {
  if (pwd.new_password !== pwd.confirm) {
    toast('两次输入的新密码不一致', 'error')
    return
  }
  pwdSaving.value = true
  try {
    await api.changePassword(pwd.old_password, pwd.new_password)
    toast('密码已更新，下次登录请使用新密码', 'success')
    store.mustChangePassword = false
    pwd.old_password = ''
    pwd.new_password = ''
    pwd.confirm = ''
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    pwdSaving.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="stack">
    <div v-if="store.mustChangePassword" class="banner banner-warn">
      <AppIcon name="key" />
      <div>当前使用的是默认密码，请立即修改为强密码。</div>
    </div>

    <div v-if="loading" class="card"><div class="empty">加载中…</div></div>

    <template v-else>
      <div class="card">
        <div class="card-header">
          <h2>定时与执行</h2>
          <span class="text-sm muted">{{ info ? `版本 ${info.version} · Python ${info.python}` : '' }}</span>
        </div>
        <div class="card-body">
          <div class="switch-row">
            <div>
              <div style="font-weight: 600">启用定时签到</div>
              <div class="hint">关闭后仅支持手动触发。</div>
            </div>
            <label class="switch">
              <input v-model="form.schedule_enabled" type="checkbox" />
              <span class="slider"></span>
            </label>
          </div>

          <div class="grid grid-2" style="margin-top: 16px">
            <div class="field">
              <label class="label">每日执行时间</label>
              <input v-model="form.schedule_time" class="input" placeholder="08:00" />
              <div class="hint">
                下一次：{{ info && info.next_run_at ? info.next_run_at.replace('T', ' ') : '未安排' }}
              </div>
            </div>
            <div class="field">
              <label class="label">时区</label>
              <input v-model="form.timezone" class="input" placeholder="Asia/Shanghai" />
              <div class="hint">例如 Asia/Shanghai、UTC、America/New_York</div>
            </div>
          </div>

          <div class="grid grid-2">
            <div class="field">
              <label class="label">等待回复秒数</label>
              <input v-model.number="form.reply_wait_seconds" class="input" type="number" min="1" max="120" />
              <div class="hint">发送签到后等待机器人回复的时间。</div>
            </div>
            <div class="field">
              <label class="label">启动命令后等待</label>
              <input v-model.number="form.start_command_delay" class="input" type="number" min="0" max="60" />
            </div>
            <div class="field">
              <label class="label">任务间隔秒数</label>
              <input v-model.number="form.task_interval_seconds" class="input" type="number" min="0" max="300" />
              <div class="hint">避免触发 Telegram 频率限制。</div>
            </div>
            <div class="field">
              <label class="label">失败重试次数</label>
              <input v-model.number="form.max_retries" class="input" type="number" min="0" max="5" />
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h2>API 凭据</h2></div>
        <div class="card-body">
          <div class="grid grid-2">
            <div class="field">
              <label class="label">API ID</label>
              <input v-model="form.api_id" class="input mono" />
            </div>
            <div class="field">
              <label class="label">API Hash</label>
              <input v-model="form.api_hash" class="input mono" :placeholder="settings.api_hash_masked || '未设置'" />
              <div class="hint">留空表示不修改（当前：{{ settings.api_hash_masked || '未设置' }}）</div>
            </div>
          </div>
          <div class="field">
            <label class="label">手机号</label>
            <input v-model="form.phone" class="input" placeholder="+8613800138000" />
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h2>结果通知</h2>
          <button class="btn btn-sm" :disabled="!form.notify_enabled" @click="testNotify">
            <AppIcon name="bell" size="14" /> 发送测试
          </button>
        </div>
        <div class="card-body">
          <div class="switch-row">
            <div>
              <div style="font-weight: 600">启用通知</div>
              <div class="hint">签到结束后把汇总结果推送给你。</div>
            </div>
            <label class="switch">
              <input v-model="form.notify_enabled" type="checkbox" />
              <span class="slider"></span>
            </label>
          </div>
          <div class="switch-row">
            <div>
              <div style="font-weight: 600">仅在失败时通知</div>
              <div class="hint">减少打扰，只在有任务失败时推送。</div>
            </div>
            <label class="switch">
              <input v-model="form.notify_only_on_failure" type="checkbox" />
              <span class="slider"></span>
            </label>
          </div>

          <div class="grid grid-2" style="margin-top: 16px">
            <div class="field">
              <label class="label">接收者 ID</label>
              <input v-model="form.notify_receiver_id" class="input mono" placeholder="123456789 或 me" />
              <div class="hint">填 <code class="mono">me</code> 发到「已保存的消息」。</div>
            </div>
            <div class="field">
              <label class="label">通知机器人 Token（可选）</label>
              <input v-model="form.notify_bot_token" class="input mono" :placeholder="settings.notify_bot_token_masked || '留空则用当前账号发送'" />
              <div class="hint">留空表示用已登录的账号直接发送。</div>
            </div>
          </div>
        </div>
      </div>

      <div class="row-between">
        <div />
        <div class="row">
          <button class="btn" @click="refresh">重置</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            <span v-if="saving" class="spinner"></span> 保存设置
          </button>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h2>修改登录密码</h2></div>
        <div class="card-body">
          <div class="grid grid-3">
            <div class="field">
              <label class="label">当前密码</label>
              <input v-model="pwd.old_password" class="input" type="password" />
            </div>
            <div class="field">
              <label class="label">新密码</label>
              <input v-model="pwd.new_password" class="input" type="password" />
              <div class="hint">至少 8 位</div>
            </div>
            <div class="field">
              <label class="label">确认新密码</label>
              <input v-model="pwd.confirm" class="input" type="password" />
            </div>
          </div>
          <button class="btn btn-primary" :disabled="pwdSaving || !pwd.old_password || !pwd.new_password" @click="changePassword">
            <span v-if="pwdSaving" class="spinner"></span> 更新密码
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
