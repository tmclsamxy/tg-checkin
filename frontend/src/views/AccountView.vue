<script setup>
import { onMounted, ref, reactive } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { api } from '../api'
import { toast, errorText } from '../store'

const loading = ref(true)
const busy = ref(false)
const status = ref(null)
const settings = ref(null)

const creds = reactive({ api_id: '', api_hash: '', phone: '' })
const code = ref('')
const password = ref('')

async function refresh() {
  loading.value = true
  try {
    const [s, st] = await Promise.all([api.telegramStatus(), api.getSettings()])
    status.value = s
    settings.value = st
    if (st.api_id) creds.api_id = st.api_id
    if (st.phone) creds.phone = st.phone
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    loading.value = false
  }
}

async function requestCode() {
  busy.value = true
  try {
    status.value = await api.requestCode(creds.api_id, creds.api_hash, creds.phone)
    toast('验证码已发送到 Telegram，请查收', 'success')
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    busy.value = false
  }
}

async function resend() {
  busy.value = true
  try {
    status.value = await api.resendCode()
    toast('验证码已重新发送', 'success')
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    busy.value = false
  }
}

async function verifyCode() {
  busy.value = true
  try {
    status.value = await api.verifyCode(code.value)
    if (status.value.needs_password) toast('该账号开启了两步验证，请输入密码', 'info')
    else if (status.value.connected) {
      toast('登录成功', 'success')
      code.value = ''
    }
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    busy.value = false
  }
}

async function verifyPassword() {
  busy.value = true
  try {
    status.value = await api.verifyPassword(password.value)
    password.value = ''
    toast('登录成功', 'success')
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    busy.value = false
  }
}

async function cancel() {
  await api.cancelLogin()
  code.value = ''
  password.value = ''
  await refresh()
}

async function reconnect() {
  busy.value = true
  try {
    status.value = await api.connectTelegram()
    toast('已连接', 'success')
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    busy.value = false
  }
}

async function logout() {
  busy.value = true
  try {
    await api.logoutTelegram()
    toast('已退出 Telegram 登录', 'success')
    await refresh()
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    busy.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="stack">
    <div class="card">
      <div class="card-header">
        <h2>连接状态</h2>
        <button class="btn btn-sm" :disabled="loading" @click="refresh">刷新</button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="muted">加载中…</div>
        <template v-else>
          <div class="row" style="gap: 14px; flex-wrap: wrap">
            <span class="badge" :class="status.connected ? 'badge-success' : 'badge-muted'">
              <span class="dot"></span>{{ status.connected ? '已连接' : '未连接' }}
            </span>
            <span v-if="status.user" class="text-sm">账号：{{ status.user }}</span>
            <span v-if="status.phone" class="text-sm muted mono">{{ status.phone }}</span>
          </div>
          <div class="row" style="margin-top: 14px; flex-wrap: wrap">
            <button v-if="!status.connected && settings && settings.has_session" class="btn btn-sm" :disabled="busy" @click="reconnect">
              <AppIcon name="refresh" size="14" /> 恢复会话
            </button>
            <button v-if="status.connected || (settings && settings.has_session)" class="btn btn-sm btn-danger" :disabled="busy" @click="logout">
              <AppIcon name="logout" size="14" /> 退出并清除会话
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- Step 1: credentials -->
    <div v-if="status && !status.connected && !status.needs_code && !status.needs_password" class="card">
      <div class="card-header"><h2>第一步 · 填写 API 凭据</h2></div>
      <div class="card-body">
        <div class="banner banner-info">
          <AppIcon name="key" />
          <div>
            前往 <a href="https://my.telegram.org/apps" target="_blank" rel="noopener">my.telegram.org</a>
            创建应用即可获得 API ID 与 API Hash。凭据会加密保存在服务端。
          </div>
        </div>
        <div class="field">
          <label class="label">API ID</label>
          <input v-model="creds.api_id" class="input mono" placeholder="12345678" />
        </div>
        <div class="field">
          <label class="label">API Hash</label>
          <input v-model="creds.api_hash" class="input mono" placeholder="32 位字符串" />
          <div class="hint">{{ settings && settings.has_api_hash ? `已保存：${settings.api_hash_masked}（留空则不修改）` : '仅保存在你的服务器上，不会外传' }}</div>
        </div>
        <div class="field">
          <label class="label">手机号</label>
          <input v-model="creds.phone" class="input" placeholder="+8613800138000" />
          <div class="hint">需包含国际区号。</div>
        </div>
        <button class="btn btn-primary" :disabled="busy || !creds.api_id || !creds.api_hash || !creds.phone" @click="requestCode">
          <span v-if="busy" class="spinner"></span>
          <AppIcon v-else name="send" size="15" /> 发送验证码
        </button>
      </div>
    </div>

    <!-- Step 2: code -->
    <div v-if="status && status.needs_code" class="card">
      <div class="card-header"><h2>第二步 · 输入验证码</h2></div>
      <div class="card-body">
        <p class="text-sm muted">验证码已发送至 Telegram（在「已保存的消息」或官方通知里）。</p>
        <div class="field" style="margin-top: 14px">
          <input v-model="code" class="input code-input" placeholder="12345" maxlength="8" @keyup.enter="verifyCode" />
        </div>
        <div class="row">
          <button class="btn btn-primary" :disabled="busy || !code" @click="verifyCode">
            <span v-if="busy" class="spinner"></span> 验证并登录
          </button>
          <button class="btn btn-sm" :disabled="busy" @click="resend">重新发送</button>
          <button class="btn btn-sm btn-ghost" @click="cancel">取消</button>
        </div>
      </div>
    </div>

    <!-- Step 3: 2FA -->
    <div v-if="status && status.needs_password" class="card">
      <div class="card-header"><h2>第三步 · 两步验证</h2></div>
      <div class="card-body">
        <p class="text-sm muted">该账号开启了云端密码，请输入以完成登录。</p>
        <div class="field" style="margin-top: 14px">
          <input v-model="password" class="input" type="password" placeholder="云端密码" @keyup.enter="verifyPassword" />
        </div>
        <div class="row">
          <button class="btn btn-primary" :disabled="busy || !password" @click="verifyPassword">
            <span v-if="busy" class="spinner"></span> 完成登录
          </button>
          <button class="btn btn-sm btn-ghost" @click="cancel">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>
