<script setup>
import { onMounted, reactive, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { api } from '../api'
import { toast, errorText, store } from '../store'

const loading = ref(true)
const saving = ref(false)
const settings = ref(null)
const info = ref(null)
const accounts = ref([])

const form = reactive({
  schedule_enabled: true,
  schedule_time: '08:00',
  timezone: 'Asia/Shanghai',
  notify_enabled: false,
  notify_bot_token: '',
  notify_receiver_id: '',
  notify_only_on_failure: false,
  notify_account_id: '',
  reply_wait_seconds: 8,
  start_command_delay: 5,
  task_interval_seconds: 5,
  max_retries: 1,
  captcha_enabled: true,
  captcha_max_rounds: 2,
  captcha_wait_seconds: 5
})

const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const pwdSaving = ref(false)

async function refresh() {
  loading.value = true
  try {
    const [s, i, a] = await Promise.all([api.getSettings(), api.systemInfo(), api.listAccounts()])
    settings.value = s
    info.value = i
    accounts.value = a
    Object.assign(form, {
      schedule_enabled: s.schedule_enabled,
      schedule_time: s.schedule_time,
      timezone: s.timezone,
      notify_enabled: s.notify_enabled,
      notify_receiver_id: s.notify_receiver_id || '',
      notify_only_on_failure: s.notify_only_on_failure,
      notify_account_id: s.notify_account_id || '',
      reply_wait_seconds: s.reply_wait_seconds,
      start_command_delay: s.start_command_delay,
      task_interval_seconds: s.task_interval_seconds,
      max_retries: s.max_retries,
      captcha_enabled: s.captcha_enabled,
      captcha_max_rounds: s.captcha_max_rounds,
      captcha_wait_seconds: s.captcha_wait_seconds
    })
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
    if (!payload.notify_bot_token) delete payload.notify_bot_token
    // empty string means "let any connected account send notifications"
    payload.notify_account_id = payload.notify_account_id ? Number(payload.notify_account_id) : null
    settings.value = await api.updateSettings(payload)
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
        <div class="card-header"><h2>人机验证</h2></div>
        <div class="card-body">
          <div class="switch-row">
            <div>
              <div style="font-weight: 600">自动解答人机验证</div>
              <div class="hint">
                部分机器人签到前会弹出算术验证码（例如「请计算 11 + 15 = ?」）。开启后会识别题目、
                算出答案并点击正确选项；识别不出来时保持原样，不会乱点。单个任务还可在任务设置里单独关闭。
              </div>
            </div>
            <label class="switch">
              <input v-model="form.captcha_enabled" type="checkbox" />
              <span class="slider"></span>
            </label>
          </div>

          <div class="grid grid-2" style="margin-top: 16px">
            <div class="field">
              <label class="label">最多连续作答轮数</label>
              <input v-model.number="form.captcha_max_rounds" class="input" type="number" min="0" max="5" />
              <div class="hint">有些机器人会连续出题，设为 0 表示关闭。</div>
            </div>
            <div class="field">
              <label class="label">作答后等待秒数</label>
              <input v-model.number="form.captcha_wait_seconds" class="input" type="number" min="1" max="60" />
              <div class="hint">点击选项后等待机器人继续回复的时间。</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h2>账号概览</h2>
          <RouterLink class="btn btn-sm" to="/account">管理账号</RouterLink>
        </div>
        <div class="card-body">
          <div class="row" style="gap: 14px; flex-wrap: wrap">
            <span class="badge badge-muted">账号 {{ settings.account_count }}</span>
            <span class="badge" :class="settings.connected_account_count ? 'badge-success' : 'badge-muted'">
              <span class="dot"></span>已连接 {{ settings.connected_account_count }}
            </span>
            <span class="badge badge-muted">任务 {{ settings.task_count }}</span>
          </div>
          <div class="hint" style="margin-top: 10px">
            API ID / API Hash 与登录会话现在按账号保存，请在「Telegram 账号」页面新增或修改。
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

          <div class="grid grid-3" style="margin-top: 16px">
            <div class="field">
              <label class="label">接收者 ID</label>
              <input v-model="form.notify_receiver_id" class="input mono" placeholder="123456789 或 me" />
              <div class="hint">填 <code class="mono">me</code> 发到「已保存的消息」。</div>
            </div>
            <div class="field">
              <label class="label">发送账号</label>
              <select v-model="form.notify_account_id" class="select">
                <option value="">自动（任一已连接账号）</option>
                <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
              </select>
              <div class="hint">多账号时指定由谁发送通知。</div>
            </div>
            <div class="field">
              <label class="label">通知机器人 Token（可选）</label>
              <input v-model="form.notify_bot_token" class="input mono" :placeholder="settings.notify_bot_token_masked || '留空则用账号本人发送'" />
              <div class="hint">留空表示用上面的账号直接发送。</div>
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
