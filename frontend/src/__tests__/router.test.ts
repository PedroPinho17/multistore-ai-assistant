import { beforeEach, describe, expect, it } from 'vitest'
import { authGuard } from '@/router'
import { sessionStore } from '@/lib/storage'
import type { RouteLocationNormalized } from 'vue-router'

function route(
  name: string,
  opts: { public?: boolean; module?: string; modulesAny?: string[] } = {},
): RouteLocationNormalized {
  return {
    name,
    meta: {
      public: opts.public === true,
      ...(opts.module ? { module: opts.module } : {}),
      ...(opts.modulesAny ? { modulesAny: opts.modulesAny } : {}),
    },
  } as unknown as RouteLocationNormalized
}

function setUser(modules: string[]) {
  sessionStore.set('token', 'abc')
  sessionStore.set(
    'user',
    JSON.stringify({ username: 'pedro', role: 'imperador', modules }),
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

  it('allows dashboard with sql', () => {
    setUser(['sql'])
    expect(
      authGuard(route('dashboard', { modulesAny: ['sql', 'forecast'] })),
    ).toBe(true)
  })
})
