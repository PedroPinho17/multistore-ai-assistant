/** Lazy Chart.js helpers for the sales dashboard. */
import type { Chart } from 'chart.js'
import type { Lang } from '@/i18n/types'
import { moneyEur } from '@/lib/format'

type ChartCtor = typeof Chart

let chartLoad: Promise<ChartCtor> | null = null
const charts: Record<string, Chart> = {}
// Changes on every destroy (page closed, new data): a draw that was waiting for Chart.js
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

export function destroyDashCharts(): void {
  generation++
  for (const id of Object.keys(charts)) {
    charts[id]?.destroy()
    delete charts[id]
  }
}

/** The canvas, only if it is still on the page. */
function canvas(id: string): HTMLCanvasElement | null {
  const el = document.getElementById(id)
  return el instanceof HTMLCanvasElement && el.isConnected ? el : null
}

function brandColor(): string {
  return (
    getComputedStyle(document.documentElement).getPropertyValue('--brand').trim() || '#0f7a5a'
  )
}

function barChart(
  Ctor: ChartCtor,
  id: string,
  labels: string[],
  values: number[],
  label: string,
  lang: Lang,
): void {
  const el = canvas(id)
  if (!el) return
  const brand = brandColor()
  charts[id] = new Ctor(el, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label, data: values, backgroundColor: brand + 'cc', borderRadius: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: reduceMotion ? 0 : 700 },
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { callback: v => moneyEur(v, lang) } } },
    },
  })
}

function lineChart(
  Ctor: ChartCtor,
  id: string,
  labels: string[],
  values: number[],
  label: string,
  lang: Lang,
): void {
  const el = canvas(id)
  if (!el) return
  const brand = brandColor()
  charts[id] = new Ctor(el, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label,
          data: values,
          borderColor: brand,
          backgroundColor: brand + '33',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: reduceMotion ? 0 : 700 },
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { callback: v => moneyEur(v, lang) } } },
    },
  })
}

export interface DashChartData {
  top_stores?: { store: string; revenue: number }[] | null
  margin_by_brand?: { brand: string; margin: number | null }[] | null
  forecast_7d?: { rows: [string, number][] } | null
}

export async function drawDashCharts(
  data: DashChartData | null,
  labels: { revenue: string; margin: string; forecast: string },
  lang: Lang,
): Promise<void> {
  if (!data) return
  destroyDashCharts()
  const gen = generation
  const Ctor = await loadChart()
  if (gen !== generation) return // page closed or redrawn while Chart.js was downloading
  if (data.top_stores) {
    barChart(
      Ctor,
      'dash-stores',
      data.top_stores.map(r => r.store),
      data.top_stores.map(r => r.revenue),
      labels.revenue,
      lang,
    )
  }
  if (data.margin_by_brand) {
    const m = data.margin_by_brand.filter(r => r.margin != null)
    barChart(
      Ctor,
      'dash-margin',
      m.map(r => r.brand),
      m.map(r => Number(r.margin)),
      labels.margin,
      lang,
    )
  }
  if (data.forecast_7d) {
    const rows = data.forecast_7d.rows || []
    lineChart(
      Ctor,
      'dash-forecast',
      rows.map(r => r[0]),
      rows.map(r => r[1]),
      labels.forecast,
      lang,
    )
  }
}

/** For tests: how many charts are alive. */
export function dashChartCount(): number {
  return Object.keys(charts).length
}
