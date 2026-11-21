import { beforeEach, describe, expect, it } from 'vitest'
import { authGuard, redirectIfFeatureRemoved } from '@/router'
import { sessionStore } from '@/lib/storage'
import type { RouteLocationNormalized } from 'vue-router'

function route(
  name: string,
  opts: {
    public?: boolean
    module?: string
    modulesAny?: string[]
    feature?: string
    featuresAny?: string[]
  } = {},
): RouteLocationNormalized {
  return {
    name,
    meta: {
      public: opts.public === true,
      ...(opts.module ? { module: opts.module } : {}),
      ...(opts.modulesAny ? { modulesAny: opts.modulesAny } : {}),
      ...(opts.feature ? { feature: opts.feature } : {}),
      ...(opts.featuresAny ? { featuresAny: opts.featuresAny } : {}),
    },
  } as unknown as RouteLocationNormalized
}

const ALL = ['chat', 'forecast', 'orders', 'dashboard', 'review', 'users', 'admin']

/** `features: null` = a session saved before features existed (no list at all). */
function setUser(modules: string[], features: string[] | null = ALL) {
  sessionStore.set('token', 'abc')
  sessionStore.set(
    'user',
    JSON.stringify({
      username: 'pedro',
      role: 'imperador',
      modules,
      ...(features ? { features } : {}),
    }),
  )
}

describe('router authGuard (from router/index.ts)', () => {
  beforeEach(() => {
    sessionStore.del('token')
    sessionStore.del('user')
  })

  it('redirects unauthenticated users from chat to login', () => {
    const result = authGuard(route('chat'))
    expect(result).toEqual({ name: 'login', replace: true })
  })

  it('redirects authenticated users from login to chat', () => {
    sessionStore.set('token', 'abc')
    const result = authGuard(route('login', { public: true }))
    expect(result).toEqual({ name: 'chat', replace: true })
  })

  it('allows public home without a token', () => {
    expect(authGuard(route('home', { public: true }))).toBe(true)
  })

  it('allows home even when authenticated', () => {
    setUser(['sql'])
    expect(authGuard(route('home', { public: true }))).toBe(true)
  })

  it('allows public reset without a token', () => {
    expect(authGuard(route('reset', { public: true }))).toBe(true)
  })

  it('allows chat when authenticated', () => {
    sessionStore.set('token', 'abc')
    expect(authGuard(route('chat'))).toBe(true)
  })

  it('rejects users without users module', () => {
    setUser(['sql'])
    expect(authGuard(route('users', { module: 'users' }))).toEqual({
      name: 'chat',
      replace: true,
    })
  })

  it('allows users with users module', () => {
    setUser(['users'])
    expect(authGuard(route('users', { module: 'users' }))).toBe(true)
  })

  it('rejects users without observability for admin', () => {
    setUser(['sql'])
    expect(authGuard(route('admin', { module: 'observability' }))).toEqual({
      name: 'chat',
      replace: true,
    })
  })

  it('rejects users without teach for review', () => {
    setUser(['sql'])
    expect(authGuard(route('review', { module: 'teach' }))).toEqual({
      name: 'chat',
      replace: true,
    })
  })

  it('rejects dashboard without sql or forecast', () => {
    setUser(['orders'])
    expect(
      authGuard(route('dashboard', { modulesAny: ['sql', 'forecast'] })),
    ).toEqual({ name: 'chat', replace: true })
  })

  it('hides a feature the role does not have and toasts', () => {
    setUser(['sql', 'forecast'], ['chat'])
    const seen: string[] = []
    expect(
      authGuard(route('dashboard', { feature: 'dashboard', modulesAny: ['sql', 'forecast'] }), code =>
        seen.push(code),
      ),
    ).toEqual({ name: 'chat', replace: true })
    expect(seen).toEqual(['no_feature'])
  })

  it('sends a user without chat to home', () => {
    setUser(['sql'], ['dashboard'])
    expect(authGuard(route('chat', { feature: 'chat' }))).toEqual({
      name: 'home',
      replace: true,
    })
  })

  it('opens the chat with only forecast or only orders', () => {
    const chat = route('chat', { featuresAny: ['chat', 'forecast', 'orders'] })
    setUser(['forecast'], ['forecast'])
    expect(authGuard(chat)).toBe(true)
    setUser(['orders'], ['orders'])
    expect(authGuard(chat)).toBe(true)
  })

  it('sends a user with no chat feature home, with a toast', () => {
    setUser(['sql'], ['dashboard'])
    const seen: string[] = []
    expect(
      authGuard(route('chat', { featuresAny: ['chat', 'forecast', 'orders'] }), c => seen.push(c)),
    ).toEqual({ name: 'home', replace: true })
    expect(seen).toEqual(['no_feature'])
  })

  it('sends a denied page home when the chat is closed too', () => {
    setUser(['sql', 'teach'], ['dashboard'])
    expect(authGuard(route('review', { feature: 'review', module: 'teach' }))).toEqual({
      name: 'home',
      replace: true,
    })
  })

  it('needs the users feature for /users', () => {
    setUser(['users'], ['chat'])
    expect(authGuard(route('users', { feature: 'users', module: 'users' }))).toEqual({
      name: 'chat',
      replace: true,
    })
    setUser(['users'], ['chat', 'users'])
    expect(authGuard(route('users', { feature: 'users', module: 'users' }))).toBe(true)
  })

  it('shows nothing extra when the session has no feature list', () => {
    setUser(['sql', 'teach'], null)
    expect(authGuard(route('review', { feature: 'review', module: 'teach' }))).toEqual({
      name: 'home',
      replace: true,
    })
  })

  it('reloads /me once when the session has no feature list, then decides', async () => {
    setUser(['teach'], null)
    let calls = 0
    const refresh = () => {
      calls++
      setUser(['teach'], ['review'])
      return Promise.resolve()
    }
    const result = authGuard(route('review', { feature: 'review', module: 'teach' }), undefined, refresh)
    expect(result).toBeInstanceOf(Promise)
    expect(await result).toBe(true)
    expect(calls).toBe(1)
  })

  it('does not loop when /me still has no feature list', async () => {
    setUser(['teach'], null)
    let calls = 0
    const refresh = () => {
      calls++
      return Promise.resolve()
    }
    expect(
      await authGuard(route('review', { feature: 'review', module: 'teach' }), undefined, refresh),
    ).toEqual({ name: 'home', replace: true })
    expect(calls).toBe(1)
  })

  it('allows a feature the role has', () => {
    setUser(['teach'], ['review'])
    expect(authGuard(route('review', { feature: 'review', module: 'teach' }))).toBe(true)
  })

  it('leaves the current page when a refresh drops its feature', async () => {
    setUser(['sql', 'forecast'], ['chat'])
    const gone: unknown[] = []
    const seen: string[] = []
    const dash = route('dashboard', { feature: 'dashboard', modulesAny: ['sql', 'forecast'] })
    await redirectIfFeatureRemoved(
      dash,
      to => {
        gone.push(to)
      },
      code => seen.push(code),
    )
    expect(gone).toEqual([{ name: 'chat', replace: true }])
    expect(seen).toEqual(['no_feature'])

    gone.length = 0
    seen.length = 0
    setUser(['sql', 'forecast'], ['chat', 'dashboard'])
    await redirectIfFeatureRemoved(
      dash,
      to => {
        gone.push(to)
      },
      code => seen.push(code),
    )
    expect(gone).toEqual([])
    expect(seen).toEqual([])
  })

  it('allows dashboard with sql', () => {
    setUser(['sql'])
    expect(
      authGuard(route('dashboard', { modulesAny: ['sql', 'forecast'] })),
    ).toBe(true)
  })
})
