import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from './api'
import LoginView from './views/LoginView.vue'
import DashboardView from './views/DashboardView.vue'
import TasksView from './views/TasksView.vue'
import RunsView from './views/RunsView.vue'
import AccountView from './views/AccountView.vue'
import SettingsView from './views/SettingsView.vue'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/', name: 'dashboard', component: DashboardView, meta: { title: '仪表盘', icon: 'home' } },
  { path: '/tasks', name: 'tasks', component: TasksView, meta: { title: '签到任务', icon: 'list' } },
  { path: '/runs', name: 'runs', component: RunsView, meta: { title: '运行日志', icon: 'history' } },
  { path: '/account', name: 'account', component: AccountView, meta: { title: 'Telegram 账号', icon: 'user' } },
  { path: '/settings', name: 'settings', component: SettingsView, meta: { title: '系统设置', icon: 'cog' } },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  if (!to.meta.public && !getToken()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
