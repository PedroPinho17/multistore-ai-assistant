import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, configureApi, httpError } from '@/api/client'
import { ApiError } from '@/api/types'

const texts = {
  network: 'network down',
  loginError: 'bad auth',
  tooMany: 'slow down',
  errors: { forbidden: 'nope', notFound: 'gone', badSql: 'bad sql' },
}

describe('api client', () => {
  const logout = vi.fn()

  beforeEach(() => {
    logout.mockReset()
    configureApi({
      getToken: () => 'tok',
      getLang: () => 'pt',
      onUnauthorized: logout,
      getTexts: () => texts,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends Bearer and Accept-Language', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await api('/me')
    expect(fetchMock).toHaveBeenCalledWith(
      '/me',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer tok',
          'Accept-Language': 'pt',
        }),
      }),
    )
  })

  it('logs out on 401 when a token is present', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: { code: 'x', message: 'no' } }),
      }),
    )
    await expect(api('/me')).rejects.toThrow(ApiError)
    expect(logout).toHaveBeenCalled()
  })

  it('maps network failures to translated error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    )
    await expect(api('/me')).rejects.toMatchObject({ message: 'network down', status: 0 })
  })

  it('httpError prefers known codes and status maps', () => {
    const err = httpError(
      { status: 403, statusText: 'Forbidden' } as Response,
      { detail: { code: 'forbidden', message: 'server' } },
      texts,
    )
    expect(err.message).toBe('nope')
    expect(err.code).toBe('forbidden')
    expect(err.status).toBe(403)
  })
})
