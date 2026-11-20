import { colName } from '@/lib/format'
import type { Lang } from '@/i18n/types'
import type { ChatMessage } from '@/api/types'

/** Chart when 2+ rows, first cols = labels, last col = number. */
export function canChart(r: {
  columns?: string[] | null
  rows?: unknown[][] | null
}): boolean {
  try {
    if (!r || !Array.isArray(r.columns) || !Array.isArray(r.rows)) return false
    if (r.rows.length < 2 || r.rows.length > 60 || r.columns.length < 2) return false
    return r.rows.every(
      row =>
        Array.isArray(row) &&
        row[row.length - 1] !== null &&
        row[row.length - 1] !== '' &&
        !Number.isNaN(parseFloat(String(row[row.length - 1]))),
    )
  } catch {
    return false
  }
}

export function labelCol(m: Pick<ChatMessage, 'columns' | 'rows'>): number {
  const last = (m.columns?.length ?? 1) - 1
  for (let j = 0; j < last; j++) {
    if (new Set(m.rows.map(r => String(r[j]))).size > 1) return j
  }
  return 0
}

export function chartLabel(
  m: ChatMessage,
  lang: Lang,
  chartWord: string,
  format: (v: unknown) => string,
): string {
  if (!m.columns?.length) return chartWord
  const col = colName(m.columns[m.columns.length - 1]!, lang)
  const li = labelCol(m)
  const pts = m.rows
    .slice(0, 12)
    .map(r => `${r[li]}: ${format(r[r.length - 1])}`)
    .join('; ')
  return `${chartWord} — ${col}. ${pts}${m.rows.length > 12 ? '…' : ''}`
}
