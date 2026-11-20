import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteLocationRaw,
} from 'vue-router'
import { sessionStore } from '@/lib/storage'
import type { User } from '@/api/types'

function readUser(): User | null {
  const raw = sessionStore.get('user')
  if (!raw) return null
  try {
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

function hasModule(user: User | null, m: string): boolean {
  return !!(user?.modules || []).includes(m)
}

/** Auth + module redirect guard — exported so tests exercise the real logic. */
export function authGuard(
  to: RouteLocationNormalized,
): true | RouteLocationRaw {
  const token = sessionStore.get('token')
  const user = readUser()
  const isPublic = to.meta.public === true

  if (!isPublic && !token) return { name: 'login', replace: true }
  if (to.name === 'login' && token) return { name: 'chat', replace: true }
  // Home stays public even when logged in (match old UI).
  if (to.name === 'home') return true

  if (token) {
    const modulesAny = to.meta.modulesAny as string[] | undefined
    const module = to.meta.module as string | undefined
    if (modulesAny?.length && !modulesAny.some(m => hasModule(user, m))) {
      return { name: 'chat', replace: true }
    }
    if (module && !hasModule(user, module)) {
      return { name: 'chat', replace: true }
    }
  }
  return true
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
      meta: { public: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/reset-password',
      name: 'reset',
      component: () => import('@/views/ResetPasswordView.vue'),
      meta: { public: true },
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { modulesAny: ['sql', 'forecast'] },
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('@/views/ProfileView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('@/views/UsersView.vue'),
      meta: { module: 'users' },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
      meta: { module: 'observability' },
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('@/views/ReviewView.vue'),
      meta: { module: 'teach' },
    },
    { path: '/:pathMatch(.*)*', redirect: { name: 'chat' } },
  ],
})

router.beforeEach(authGuard)

export default router
