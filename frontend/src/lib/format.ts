import type { Lang } from '@/i18n/types'
import { LOCALES } from '@/i18n/types'
import { COLUMN_LABELS } from '@/api/types'

export function isNum(v: unknown): boolean {
  return typeof v === 'number' || (typeof v === 'string' && v !== '' && !Number.isNaN(Number(v)))
}

export function formatValue(v: unknown, lang: Lang, dec?: number): string {
  if (v === null || v === undefined) return '—'
  if (isNum(v)) {
    const n = Number(v)
    const digits = dec ?? (Number.isInteger(n) ? 0 : 2)
    return n.toLocaleString(LOCALES[lang], {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  }
  return String(v)
}

export function colName(c: string, lang: Lang): string {
  return COLUMN_LABELS[lang][c] ?? c.replace(/_/g, ' ')
}

export function nowTime(lang: Lang): string {
  return new Date().toLocaleTimeString(LOCALES[lang], { hour: '2-digit', minute: '2-digit' })
}

export function timeFromIso(iso: string, lang: Lang): string {
  return new Date(iso).toLocaleTimeString(LOCALES[lang], { hour: '2-digit', minute: '2-digit' })
}

export function dateFmt(iso: string, lang: Lang): string {
  return new Date(iso).toLocaleDateString(LOCALES[lang], {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function moneyEur(v: unknown, lang: Lang): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(LOCALES[lang] || 'en-GB', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  })
}

export function pct(x: number | null | undefined, lang: Lang): string {
  if (x == null) return '—'
  return (100 * x).toLocaleString(LOCALES[lang], { maximumFractionDigits: 1 }) + ' %'
}

export function ms(x: number | null | undefined, lang: Lang): string {
  if (x == null) return '—'
  return x >= 1000
    ? (x / 1000).toLocaleString(LOCALES[lang], { maximumFractionDigits: 1 }) + ' s'
    : x + ' ms'
}

export function ago(
  iso: string,
  nowMs: number,
  texts: {
    now: string
    min: (n: number) => string
    h: (n: number) => string
    d: (n: number) => string
  },
): string {
  const min = Math.round((nowMs - new Date(iso).getTime()) / 60000)
  if (min < 1) return texts.now
  if (min < 60) return texts.min(min)
  if (min < 1440) return texts.h(Math.round(min / 60))
  return texts.d(Math.round(min / 1440))
}

export function decodeJwtExp(token: string | null): number | null {
  if (!token) return null
  try {
    const payload = JSON.parse(atob(token.split('.')[1]!)) as { exp?: number }
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

export function shortDate(iso: string, lang: Lang): string {
  return new Date(iso).toLocaleString(LOCALES[lang], {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function shortModel(m: string): string {
  return (m || '').replace(/^openai\//, '').replace('Qwen2.5-Coder-', 'Qwen ')
}

export function pwStrength(v: string): number {
  if (!v) return 0
  let score = 0
  if (v.length >= 8) score++
  if (v.length >= 12) score++
  if (/[a-z]/.test(v) && /[A-Z]/.test(v)) score++
  if (/[0-9]/.test(v) && /[^A-Za-z0-9]/.test(v)) score++
  return v.length < 8 ? Math.min(score, 1) : score
}

export const KIND_ORDER = ['sql', 'forecast', 'orders', 'no_sql', 'denied', 'error'] as const
export const MODULE_ORDER = [
  'sql',
  'forecast',
  'orders',
  'teach',
  'users',
  'observability',
] as const
export const DATA_MODULES = ['sql', 'forecast', 'orders'] as const
export const DASH_DAYS = [1, 7, 30, 90] as const

