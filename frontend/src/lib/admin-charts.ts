/** Lazy Chart.js helpers for the admin observability page. */
import type { Chart } from 'chart.js'
import { LOCALES, type Lang } from '@/i18n/types'
import { shortDate, shortModel } from '@/lib/format'

type ChartCtor = typeof Chart

let chartLoad: Promise<ChartCtor> | null = null
const charts: Record<string, Chart> = {}
// Changes on every destroy (page closed, new period): a draw that was waiting for Chart.js
// to download sees it changed and draws nothing.
let generation = 0

const reduceMotion =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

function loadChart(): Promise<ChartCtor> {
  chartLoad ??= import('@/lib/chartjs').then(m => m.Chart)
  return chartLoad
}

/** The canvas, only if it is still on the page. */
function canvas(id: string): HTMLCanvasElement | null {
  const el = document.getElementById(id)
  return el instanceof HTMLCanvasElement && el.isConnected ? el : null
}

export function destroyAdminCharts(): void {
  generation++
  for (const k of Object.keys(charts)) {
    charts[k]?.destroy()
    delete charts[k]
  }
}

export interface AdminChartData {
  daily: { day: string; requests: number; errors: number }[]
  eval_history: { date: string; model: string; accuracy: number | null }[]
}

export async function drawAdminCharts(
  data: AdminChartData | null,
  labels: { ok: string; failed: string; accuracy: string },
  lang: Lang,
): Promise<void> {
  if (!data) return
  destroyAdminCharts()
  const gen = generation
  const Chart = await loadChart()
  if (gen !== generation) return // page closed or redrawn while Chart.js was downloading
  const css = getComputedStyle(document.documentElement)
  const c = (name: string) => css.getPropertyValue(name).trim()
  const brand = c('--brand')
  const danger = c('--danger')
  const muted = c('--muted')
  const grid = c('--border')
  const base = {
    animation: { duration: reduceMotion ? 0 : 700 },
    plugins: { legend: { labels: { color: muted, boxWidth: 12 } } },
    scales: {
      x: { ticks: { color: muted }, grid: { display: false }, stacked: true },
      y: {
        ticks: { color: muted, precision: 0 },
        grid: { color: grid },
        stacked: true,
        beginAtZero: true,
      },
    },
  }
  const daily = canvas('adm-daily')
  if (daily) {
    const label = (day: string) =>
      new Date(day + 'T12:00:00').toLocaleDateString(LOCALES[lang], {
        day: 'numeric',
        month: 'short',
      })
    charts.daily = new Chart(daily, {
      type: 'bar',
      data: {
        labels: data.daily.map(r => label(r.day)),
        datasets: [
          {
            label: labels.ok,
            data: data.daily.map(r => r.requests - r.errors),
            backgroundColor: brand + 'cc',
            borderRadius: 6,
          },
          {
            label: labels.failed,
            data: data.daily.map(r => r.errors),
            backgroundColor: danger + 'cc',
            borderRadius: 6,
          },
        ],
      },
      options: base,
    })
  }
  const evalEl = canvas('adm-eval')
  if (evalEl && data.eval_history.length) {
    const palette = [brand, '#0ea5e9', '#f59e0b', '#8b5cf6', '#ec4899']
    const models = [...new Set(data.eval_history.map(r => r.model))]
    charts.eval = new Chart(evalEl, {
      type: 'bar',
      data: {
        labels: data.eval_history.map(r => [shortDate(r.date, lang), shortModel(r.model)]),
        datasets: [
          {
            label: labels.accuracy,
            data: data.eval_history.map(r => Math.round(1000 * (r.accuracy ?? 0)) / 10),
            backgroundColor: data.eval_history.map(
              r => palette[models.indexOf(r.model) % palette.length]! + 'cc',
            ),
            borderRadius: 6,
          },
        ],
      },
      options: {
        ...base,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => `${ctx.parsed.y} %` } },
        },
        scales: {
          x: { ticks: { color: muted, font: { size: 11 } }, grid: { display: false } },
          y: {
            min: 0,
            max: 100,
            ticks: { color: muted, callback: v => v + ' %' },
            grid: { color: grid },
          },
        },
      },
    })
  }
}

/** For tests: how many charts are alive. */
export function adminChartCount(): number {
  return Object.keys(charts).length
}
