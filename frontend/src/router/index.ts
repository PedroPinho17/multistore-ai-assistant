import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteLocationRaw,
} from 'vue-router'
import { sessionStore } from '@/lib/storage'
import { CHAT_FEATURES, hasAnyFeature, hasFeature } from '@/lib/features'
import type { User } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

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

type DeniedCode = 'no_module' | 'no_feature'
type GuardResult = true | RouteLocationRaw

function deny(
  to: RouteLocationNormalized,
  user: User | null,
  onDenied?: (code: DeniedCode) => void,
  code: DeniedCode = 'no_module',
): RouteLocationRaw {
  onDenied?.(code)
  // Back to the chat when it can be opened; otherwise (or if the chat itself was refused) home
  const canChat = hasAnyFeature(user?.features, CHAT_FEATURES)
  const name = to.name !== 'chat' && canChat ? 'chat' : 'home'
  return { name, replace: true }
}

function needsFeature(to: RouteLocationNormalized): boolean {
  return !!to.meta.feature || !!(to.meta.featuresAny as string[] | undefined)?.length
}

/**
 * Auth + module + feature redirect guard — exported so tests exercise the real logic.
 * A session saved before features existed has no list: `refresh` reloads `/me` once and the
 * guard decides again (without it, the missing list simply opens nothing).
 */
export function authGuard(
  to: RouteLocationNormalized,
  onDenied?: (code: DeniedCode) => void,
  refresh?: () => Promise<unknown>,
): GuardResult | Promise<GuardResult> {
  const token = sessionStore.get('token')
  const user = readUser()
  if (token && user && !user.features && refresh && needsFeature(to)) {
    return refresh().then(() => authGuard(to, onDenied))
  }
  return checkRoute(to, token, user, onDenied)
}

function checkRoute(
  to: RouteLocationNormalized,
  token: string | null,
  user: User | null,
  onDenied?: (code: DeniedCode) => void,
): GuardResult {
  const isPublic = to.meta.public === true

  if (!isPublic && !token) return { name: 'login', replace: true }
  if (to.name === 'login' && token) return { name: 'chat', replace: true }
  // Home stays public even when logged in (match old UI).
  if (to.name === 'home') return true

  if (token) {
    const modulesAny = to.meta.modulesAny as string[] | undefined
    const module = to.meta.module as string | undefined
    const feature = to.meta.feature as string | undefined
    const featuresAny = to.meta.featuresAny as string[] | undefined
    if (modulesAny?.length && !modulesAny.some(m => hasModule(user, m))) {
      return deny(to, user, onDenied, 'no_module')
    }
    if (module && !hasModule(user, module)) {
      return deny(to, user, onDenied, 'no_module')
    }
    if (feature && !hasFeature(user?.features, feature)) {
      return deny(to, user, onDenied, 'no_feature')
    }
    if (featuresAny?.length && !hasAnyFeature(user?.features, featuresAny)) {
      return deny(to, user, onDenied, 'no_feature')
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
      meta: { featuresAny: [...CHAT_FEATURES] },
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { feature: 'dashboard', modulesAny: ['sql', 'forecast'] },
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
      meta: { feature: 'users', module: 'users' },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
      meta: { feature: 'admin', module: 'observability' },
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('@/views/ReviewView.vue'),
      meta: { feature: 'review', module: 'teach' },
    },
    { path: '/:pathMatch(.*)*', redirect: { name: 'chat' } },
  ],
})

function denyToast(code: DeniedCode) {
  const ui = useUiStore()
  const text = code === 'no_feature' ? ui.t.errors.no_feature : ui.t.errors.no_module
  ui.toast(text, 'error')
}

/** After `/me` drops a feature, leave the page and show the same no-access toast as `beforeEach`. */
export async function redirectIfFeatureRemoved(
  current: RouteLocationNormalized,
  go: (to: RouteLocationRaw) => unknown,
  onDenied: (code: DeniedCode) => void = denyToast,
): Promise<void> {
  const decision = await Promise.resolve(authGuard(current, onDenied))
  if (decision !== true) await go(decision)
}

router.beforeEach(to =>
  authGuard(to, denyToast, () => useAuthStore().refreshMe()),
)

export default router
