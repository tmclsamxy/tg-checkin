<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import { api } from '../api'
import { toast, errorText } from '../store'

const props = defineProps({
  // 'create' | 'edit' | 'relogin'
  mode: { type: String, default: 'create' },
  account: { type: Object, default: null }
})
const emit = defineEmits(['close', 'saved'])

const busy = ref(false)
const step = ref('creds') // creds | code | password
const created = ref(null) // the account being logged in

const form = ref({ name: '', api_id: '', api_hash: '', phone: '', enabled: true })
const code = ref('')
const password = ref('')

const title = computed(() => {
  if (props.mode === 'edit') return '编辑账号'
  if (props.mode === 'relogin') return `重新登录 · ${props.account?.name || ''}`
  return '添加 Telegram 账号'
})

watch(
  () => props.account,
  (account) => {
    if (!account) {
      form.value = { name: '', api_id: '', api_hash: '', phone: '', enabled: true }
      return
    }
    form.value = {
      name: account.name || '',
      api_id: account.api_id || '',
      api_hash: '',
      phone: account.phone || '',
      enabled: account.enabled !== false
    }
  },
  { immediate: true }
)

function fail(err) {
  toast(errorText(err), 'error')
}

/** create / edit: just persist the fields */
async function save() {
  if (!(form.value.phone || '').trim()) {
    toast('请填写手机号', 'error')
    return
  }
  busy.value = true
  try {
    if (props.mode === 'edit') {
      const payload = { name: form.value.name, enabled: form.value.enabled }
      if (form.value.api_id) payload.api_id = form.value.api_id
      if (form.value.api_hash) payload.api_hash = form.value.api_hash
      if (form.value.phone) payload.phone = form.value.phone
      await api.updateAccount(props.account.id, payload)
      toast('账号已保存', 'success')
      emit('saved')
      return
    }

    if (!form.value.api_id || !form.value.api_hash) {
      toast('请填写 API ID 与 API Hash', 'error')
      return
    }
    const account = await api.createAccount({
      name: form.value.name,
      api_id: form.value.api_id,
      api_hash: form.value.api_hash,
      phone: form.value.phone,
      enabled: form.value.enabled
    })
    created.value = account
    // straight into the login flow so one dialog does the whole job
    await sendCode()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

/** send the login code for the account being created / re-logged in */
async function sendCode() {
  const target = created.value || props.account
  if (!target) return
  busy.value = true
  try {
    // Blank api_hash means the server reuses the stored one (edit / re-login).
    const result = await api.requestCode(target.id, form.value.api_id, form.value.api_hash, form.value.phone)
    created.value = result
    step.value = 'code'
    code.value = ''
    toast('验证码已发送到 Telegram', 'success')
  } catch (err) {
    fail(err)
    emit('saved')
  } finally {
    busy.value = false
  }
}

async function resend() {
  const target = created.value || props.account
  busy.value = true
  try {
    await api.resendCode(target.id)
    toast('验证码已重新发送', 'success')
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function verifyCode() {
  const target = created.value || props.account
  busy.value = true
  try {
    const result = await api.verifyCode(target.id, code.value.trim())
    if (result.needs_password) {
      step.value = 'password'
      password.value = ''
      toast('该账号开启了两步验证，请输入密码', 'info')
      return
    }
    toast('登录成功', 'success')
    emit('saved')
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function verifyPassword() {
  const target = created.value || props.account
  busy.value = true
  try {
    await api.verifyPassword(target.id, password.value)
    toast('登录成功', 'success')
    emit('saved')
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function cancel() {
  const target = created.value || props.account
  if (step.value !== 'creds' && target) {
    try {
      await api.cancelLogin(target.id)
    } catch {
      /* best effort */
    }
  }
  emit(props.mode === 'create' && created.value ? 'saved' : 'close')
}
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>{{ title }}</h3>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">✕</button>
      </div>

      <div class="modal-body">
        <!-- credentials -->
        <template v-if="step === 'creds'">
          <div v-if="mode === 'create'" class="banner banner-info">
            <AppIcon name="key" />
            <div>
              在 <a href="https://my.telegram.org/apps" target="_blank" rel="noopener">my.telegram.org</a>
              创建应用即可获得 API ID 与 API Hash。多个账号可以共用同一套 API 凭据。
            </div>
          </div>

          <div class="field">
            <label class="label">账号备注</label>
            <input v-model="form.name" class="input" placeholder="例如：主号 / 小号一" />
            <div class="hint">留空则自动使用手机号或登录后的昵称。</div>
          </div>

          <div v-if="mode !== 'relogin'" class="grid grid-2">
            <div class="field">
              <label class="label">API ID</label>
              <input v-model="form.api_id" class="input mono" placeholder="12345678" />
            </div>
            <div class="field">
              <label class="label">API Hash</label>
              <input
                v-model="form.api_hash"
                class="input mono"
                :placeholder="account && account.has_api_hash ? '留空则不修改' : '32 位字符串'"
              />
            </div>
          </div>

          <div class="field">
            <label class="label">手机号</label>
            <input v-model="form.phone" class="input" placeholder="+8613800138000" />
            <div class="hint">需包含国际区号，登录时 Telegram 会给它发验证码。</div>
          </div>

          <div v-if="mode === 'edit'" class="switch-row">
            <div>
              <div style="font-weight: 600">启用该账号</div>
              <div class="hint">停用后它名下的任务会在定时签到中被跳过。</div>
            </div>
            <label class="switch">
              <input v-model="form.enabled" type="checkbox" />
              <span class="slider"></span>
            </label>
          </div>
        </template>

        <!-- code -->
        <template v-else-if="step === 'code'">
          <p class="text-sm muted">
            验证码已发送到 <span class="mono">{{ created?.phone || account?.phone }}</span> 的 Telegram，
            请在「已保存的消息」或官方通知里查看。
          </p>
          <div class="field" style="margin-top: 14px">
            <input
              v-model="code"
              class="input code-input"
              placeholder="12345"
              maxlength="8"
              @keyup.enter="verifyCode"
            />
          </div>
          <div class="row">
            <button class="btn btn-sm" :disabled="busy" @click="resend">重新发送</button>
            <button class="btn btn-sm btn-ghost" @click="cancel">取消</button>
          </div>
        </template>

        <!-- 2FA -->
        <template v-else>
          <p class="text-sm muted">该账号开启了云端密码（两步验证），请输入以完成登录。</p>
          <div class="field" style="margin-top: 14px">
            <input
              v-model="password"
              class="input"
              type="password"
              placeholder="云端密码"
              @keyup.enter="verifyPassword"
            />
          </div>
        </template>

        <div class="modal-footer" style="padding: 0; border: none; margin-top: 18px">
          <button type="button" class="btn" @click="cancel">取消</button>

          <button v-if="step === 'creds'" type="button" class="btn btn-primary" :disabled="busy" @click="save">
            <span v-if="busy" class="spinner"></span>
            {{ mode === 'edit' ? '保存' : '保存并发送验证码' }}
          </button>

          <button
            v-else-if="step === 'code'"
            type="button"
            class="btn btn-primary"
            :disabled="busy || !code"
            @click="verifyCode"
          >
            <span v-if="busy" class="spinner"></span> 验证并登录
          </button>

          <button
            v-else
            type="button"
            class="btn btn-primary"
            :disabled="busy || !password"
            @click="verifyPassword"
          >
            <span v-if="busy" class="spinner"></span> 完成登录
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
