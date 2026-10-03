<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, setToken } from '../api'
import { setUser, toast, errorText } from '../store'

const route = useRoute()
const router = useRouter()

const username = ref('admin')
const password = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  try {
    const data = await api.login(username.value.trim(), password.value)
    setToken(data.access_token)
    setUser(data.username, data.must_change_password)
    toast('登录成功', 'success')
    router.push(route.query.redirect || '/')
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="card login-card">
      <div class="card-body">
        <div class="login-brand">
          <div class="brand-mark">TG</div>
          <h2 style="font-size: 19px">TG Checkin</h2>
          <p class="muted text-sm">Telegram 自动签到管理面板</p>
        </div>

        <form @submit.prevent="submit">
          <div class="field">
            <label class="label">用户名</label>
            <input v-model="username" class="input" autocomplete="username" required />
          </div>
          <div class="field">
            <label class="label">密码</label>
            <input v-model="password" class="input" type="password" autocomplete="current-password" required autofocus />
          </div>

          <button class="btn btn-primary btn-block" type="submit" :disabled="loading" style="margin-top: 8px">
            <span v-if="loading" class="spinner"></span>
            {{ loading ? '登录中…' : '登录' }}
          </button>
        </form>

        <p class="hint mt-16" style="text-align: center">
          默认账号 <code class="mono">admin</code> / <code class="mono">admin123</code><br />
          首次登录后请立即在系统设置中修改密码。
        </p>
      </div>
    </div>
  </div>
</template>
