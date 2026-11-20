import { defineStore } from 'pinia'
import { computed, nextTick, ref } from 'vue'
import { api } from '@/api/client'
import type { DashboardData } from '@/api/types'
import { ApiError } from '@/api/types'
import { destroyDashCharts, drawDashCharts } from '@/lib/dash-charts'
import { useUiStore } from '@/stores/ui'

export const useDashboardStore = defineStore('dashboard', () => {
  const data = ref<DashboardData | null>(null)
  const loading = ref(false)
  const error = ref('')

  const margins = computed(() =>
    (data.value?.margin_by_brand || []).filter(r => r.margin != null),
  )

  // Only the latest request counts; reset() (page closed) invalidates the one in flight,
  // so an answer that arrives after leaving the page neither fills the store nor draws.
  let requestSeq = 0

  async function load() {
    const ui = useUiStore()
    const req = ++requestSeq
    loading.value = true
    error.value = ''
    try {
      const d = await api<DashboardData>('/dashboard')
      if (req !== requestSeq) return
      data.value = d
      await nextTick()
      if (req !== requestSeq) return
      await drawDashCharts(d, {
        revenue: ui.t.dash.revenue,
        margin: ui.t.dash.margin,
        forecast: ui.t.dash.forecast,
      }, ui.lang)
    } catch (e) {
      if (req !== requestSeq) return
      error.value = e instanceof ApiError ? e.message : String(e)
      data.value = null
      destroyDashCharts()
    } finally {
      if (req === requestSeq) loading.value = false
    }
  }

  function reset() {
    requestSeq++
    loading.value = false
    data.value = null
    error.value = ''
    destroyDashCharts()
  }

  return { data, loading, error, margins, load, reset }
})
