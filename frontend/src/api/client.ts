import { ApiError } from '@/api/types'
import type { Lang } from '@/i18n/types'

export type LogoutCallback = () => void
export type LangGetter = () => Lang
export type TokenGetter = () => string | null
export type TranslateErrors = {
  network: string
  loginError: string
  tooMany: string
  errors: Record<string, string>
}

let getToken: TokenGetter = () => null
let getLang: LangGetter = () => 'en'
let onUnauthorized: LogoutCallback = () => undefined
let getTexts: () => TranslateErrors = () => ({
  network: 'Network error',
  loginError: 'Unauthorized',
  tooMany: 'Too many requests',
  errors: {},
})

export function configureApi(opts: {
  getToken: TokenGetter
  getLang: LangGetter
  onUnauthorized: LogoutCallback
  getTexts: () => TranslateErrors
}): void {
  getToken = opts.getToken
  getLang = opts.getLang
  onUnauthorized = opts.onUnauthorized
  getTexts = opts.getTexts
}

export function httpError(res: Response, data: unknown, t: TranslateErrors): ApiError {
  const detail = (data as { detail?: unknown } | null)?.detail
  const code =
    detail && typeof detail === 'object' && detail !== null && 'code' in detail
      ? String((detail as { code: unknown }).code)
      : undefined
  const serverMsg =
    detail && typeof detail === 'object' && detail !== null && 'message' in detail
      ? String((detail as { message: unknown }).message)
      : typeof detail === 'string'
        ? detail
        : undefined
  const known: Record<number, string> = {
    403: t.errors.forbidden ?? '',
    404: t.errors.notFound ?? '',
    429: t.tooMany,
  }
  const message =
    (code && t.errors[code]) ||
    (code && serverMsg) ||
    known[res.status] ||
    serverMsg ||
    res.statusText
  return new ApiError(message, res.status, code)
}

export async function api<T = unknown>(
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const t = getTexts()
  const token = getToken()
  const raw = body instanceof Blob
  let res: Response
  try {
    res = await fetch(path, {
      method: method || (body !== undefined && body !== null ? 'POST' : 'GET'),
      headers: {
        'Content-Type': raw ? (body as Blob).type : 'application/json',
        'Accept-Language': getLang(),
        ...(token ? { Authorization: 'Bearer ' + token } : {}),
      },
      body: raw ? (body as Blob) : body !== undefined && body !== null ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(t.network, 0)
  }
  if (res.status === 401 && token) {
    onUnauthorized()
    throw new ApiError(t.loginError, 401)
  }
  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    /* empty body */
  }
  if (!res.ok) throw httpError(res, data, t)
  return data as T
}

export async function apiBlob(
  path: string,
  init?: RequestInit,
): Promise<{ blob: Blob; res: Response }> {
  const t = getTexts()
  const token = getToken()
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        'Accept-Language': getLang(),
        ...(token ? { Authorization: 'Bearer ' + token } : {}),
        ...(init?.headers || {}),
      },
    })
  } catch {
    throw new ApiError(t.network, 0)
  }
  if (res.status === 401 && token) {
    onUnauthorized()
    throw new ApiError(t.loginError, 401)
  }
  if (!res.ok) {
    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      /* ignore */
    }
    throw httpError(res, data, t)
  }
  return { blob: await res.blob(), res }
}
