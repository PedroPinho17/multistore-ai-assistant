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
