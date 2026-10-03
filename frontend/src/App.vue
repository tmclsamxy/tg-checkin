<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import ToastHost from './components/ToastHost.vue'
import { api, getToken, setToken } from './api'
import { store, setUser, clearUser } from './store'

const route = useRoute()
const router = useRouter()

const navItems = [
  { name: 'dashboard', label: '仪表盘', icon: 'home' },
  { name: 'tasks', label: '签到任务', icon: 'list' },
  { name: 'runs', label: '运行日志', icon: 'history' },
  { name: 'account', label: 'Telegram 账号', icon: 'user' },
  { name: 'settings', label: '系统设置', icon: 'cog' }
]

const title = computed(() => route.meta.title || '仪表盘')
const initial = computed(() => (store.user ? store.user.slice(0, 2).toUpperCase() : '?'))

function onUnauthorized() {
  clearUser()
  router.push({ name: 'login' })
}

async function loadUser() {
  if (!getToken()) return
  try {
    const me = await api.me()
    setUser(me.username, me.must_change_password)
  } catch {
    setToken('')
    clearUser()
  }
}

async function logout() {
  setToken('')
  clearUser()
  router.push({ name: 'login' })
}

onMounted(() => {
  loadUser()
  window.addEventListener('tg:unauthorized', onUnauthorized)
})
onUnmounted(() => window.removeEventListener('tg:unauthorized', onUnauthorized))
</script>

<template>
  <div v-if="route.name === 'login'">
    <router-view />
    <ToastHost />
  </div>

  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">TG</div>
        <div>
          <div class="brand-title">TG Checkin</div>
          <div class="brand-sub">Telegram 自动签到</div>
        </div>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
          :class="{ active: route.name === item.name }"
        >
          <AppIcon :name="item.icon" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="user-chip">
          <div class="avatar">{{ initial }}</div>
          <div class="flex-1">
            <div style="font-weight: 600; font-size: 13px">{{ store.user || '未登录' }}</div>
            <div class="text-sm muted">管理员</div>
          </div>
        </div>
        <button class="btn btn-block btn-sm" @click="logout">
          <AppIcon name="logout" size="15" /> 退出登录
        </button>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <h1>{{ title }}</h1>
        <div class="topbar-actions">
          <router-link :to="{ name: 'tasks' }" class="btn btn-primary btn-sm">
            <AppIcon name="play" size="15" /> 立即签到
          </router-link>
        </div>
      </header>

      <main class="content">
        <router-view />
      </main>
    </div>

    <ToastHost />
  </div>
</template>
