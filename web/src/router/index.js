import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', component: () => import('../views/ChatView.vue') },
  { path: '/login', component: () => import('../views/LoginView.vue') },
  { path: '/agent-desk', component: () => import('../views/AgentDeskView.vue'), meta: { requiresAuth: true } },
  { path: '/dashboard', component: () => import('../views/DashboardView.vue'), meta: { requiresAuth: true } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (to.meta.requiresAuth) {
    const auth = useAuthStore()
    if (!auth.isLoggedIn) return '/login'
  }
  return true
})

export default router
