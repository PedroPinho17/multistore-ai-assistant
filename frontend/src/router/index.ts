import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteLocationRaw,
} from 'vue-router'
import { sessionStore } from '@/lib/storage'

/** Auth redirect guard — exported so tests exercise the real logic, not a copy. */
export function authGuard(
  to: RouteLocationNormalized,
): true | RouteLocationRaw {
  const token = sessionStore.get('token')
  if (!to.meta.public && !token) return { name: 'login', replace: true }
  if (to.name === 'login' && token) return { name: 'chat', replace: true }
  return true
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: { name: 'chat' } },
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
    { path: '/:pathMatch(.*)*', redirect: { name: 'chat' } },
  ],
})

router.beforeEach(authGuard)

export default router
