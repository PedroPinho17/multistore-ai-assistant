import {
  Chart,
  BarController,
  LineController,
  BarElement,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Filler,
  Tooltip,
} from 'chart.js'
import { colName } from '@/lib/format'
import { labelCol } from '@/lib/chart-data'
import type { Lang } from '@/i18n/types'
import type { ChatMessage } from '@/api/types'

Chart.register(
  BarController,
  LineController,
  BarElement,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Filler,
  Tooltip,
)

const charts = new Map<number, Chart>()

const reduceMotion =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function destroyChart(id: number): void {
  charts.get(id)?.destroy()
  charts.delete(id)
}

export function clearCharts(): void {
  for (const id of charts.keys()) destroyChart(id)
}

export function drawChart(m: ChatMessage, lang: Lang): void {
  const el = document.getElementById(`chart-${m.id}`) as HTMLCanvasElement | null
  if (!el || !m.columns?.length) return
  destroyChart(m.id)
  const css = getComputedStyle(document.documentElement)
  const brand = css.getPropertyValue('--brand').trim()
  const muted = css.getPropertyValue('--muted').trim()
  const grid = css.getPropertyValue('--border').trim()
  const li = labelCol(m)
  const isTime = /^\d{4}(-\d{2})?(-\d{2})?$|^\d{1,2}$/.test(String(m.rows[0]?.[li]))
  charts.set(
    m.id,
    new Chart(el, {
      type: isTime ? 'line' : 'bar',
      data: {
        labels: m.rows.map(r => String(r[li])),
        datasets: [
          {
            label: colName(m.columns[m.columns.length - 1]!, lang),
            data: m.rows.map(r => parseFloat(String(r[r.length - 1]))),
            backgroundColor: brand + 'cc',
            borderColor: brand,
            borderWidth: 2,
            borderRadius: 6,
            tension: 0.35,
            fill: isTime ? { target: 'origin', above: brand + '22' } : false,
            pointRadius: 2,
          },
        ],
      },
      options: {
        animation: { duration: reduceMotion ? 0 : 900, easing: 'easeOutQuart' },
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: muted }, grid: { display: false } },
          y: { ticks: { color: muted }, grid: { color: grid } },
        },
      },
    }),
  )
}

/** Draw only if no chart instance exists yet for this message. */
export function ensureChart(m: ChatMessage, lang: Lang): void {
  if (charts.has(m.id)) return
  drawChart(m, lang)
}

/** Force-redraw all completed chart messages (e.g. after theme change). */
export function redrawCharts(messages: ChatMessage[], lang: Lang): void {
  for (const m of messages) {
    if (m.done && m.chart) drawChart(m, lang)
  }
}
