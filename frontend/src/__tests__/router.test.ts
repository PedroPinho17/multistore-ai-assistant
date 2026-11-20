import { beforeEach, describe, expect, it } from 'vitest'
import { authGuard } from '@/router'
import { sessionStore } from '@/lib/storage'
import type { RouteLocationNormalized } from 'vue-router'

function route(
  name: string,
  opts: { public?: boolean } = {},
): RouteLocationNormalized {
  return {
    name,
    meta: { public: opts.public === true },
  } as unknown as RouteLocationNormalized
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

  it('allows public reset without a token', () => {
    expect(authGuard(route('reset', { public: true }))).toBe(true)
  })

  it('allows chat when authenticated', () => {
    sessionStore.set('token', 'abc')
    expect(authGuard(route('chat'))).toBe(true)
  })
})
