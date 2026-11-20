import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { sessionStore } from '@/lib/storage'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStore.del('token')
    sessionStore.del('user')
    vi.unstubAllGlobals()
  })

  it('login stores token in sessionStorage and clears password', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        token: 'abc',
        user: { username: 'pedro', role: 'imperador', modules: ['sql'] },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const auth = useAuthStore()
    const ui = useUiStore()
    auth.wireApi()
    void ui
    auth.username = 'pedro'
    auth.password = 'imperador123'

    const push = vi.fn()
    await auth.login({ push } as never)

    expect(auth.token).toBe('abc')
    expect(sessionStore.get('token')).toBe('abc')
    expect(auth.password).toBe('')
    expect(push).toHaveBeenCalledWith({ name: 'chat' })
  })

  it('logout clears token and user', () => {
    sessionStore.set('token', 'x')
    sessionStore.set('user', JSON.stringify({ username: 'a', role: 'loja' }))
    const auth = useAuthStore()
    auth.token = 'x'
    auth.user = { username: 'a', role: 'loja' }
    auth.logout()
    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(sessionStore.get('token')).toBeNull()
  })

  it('hasModule checks user.modules', () => {
    const auth = useAuthStore()
    auth.user = { username: 'x', role: 'marca', modules: ['sql', 'forecast'] }
    expect(auth.hasModule('sql')).toBe(true)
    expect(auth.hasModule('orders')).toBe(false)
  })
})
