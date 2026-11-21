import { defineStore } from 'pinia'
import { computed, nextTick, ref } from 'vue'
import { api } from '@/api/client'
import type { AdminMetrics } from '@/api/types'
import { ApiError } from '@/api/types'
import { destroyAdminCharts, drawAdminCharts } from '@/lib/admin-charts'
import { DASH_DAYS, formatValue, ms, pct } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { LOCALES } from '@/i18n/types'

export const useAdminStore = defineStore('admin', () => {
  const data = ref<AdminMetrics | null>(null)
  const days = ref<(typeof DASH_DAYS)[number]>(7)
  const loading = ref(false)
  const error = ref('')
  const roleFeatures = ref<Record<string, string[]> | null>(null)
  const featureNames = ref<string[]>([])
  const savingRole = ref('')
  const updatedAt = ref<number | null>(null)
  // Formatted in the chosen language (and re-formatted when it changes)
  const updated = computed(() => {
    if (updatedAt.value == null) return null
    return new Date(updatedAt.value).toLocaleTimeString(LOCALES[useUiStore().lang], {
      hour: '2-digit',
      minute: '2-digit',
    })
  })

  const dashDays = DASH_DAYS

  const admKpis = computed(() => {
    const ui = useUiStore()
    const d = data.value
    const a = ui.t.adm
    if (!d) return []
    const s = d.summary
    const fmt = (n: number) => formatValue(n, ui.lang, 0)
    const total = s.prompt_tokens + s.completion_tokens
    return [
      { key: 'req', icon: 'chat', label: a.requests, value: fmt(s.requests), hint: a.users(s.users), tone: '' },
      {
        key: 'err',
        icon: 'alert',
        label: a.errorRate,
        value: pct(s.error_rate, ui.lang),
        hint: a.errorsN(s.errors),
        tone: s.error_rate > 0.1 ? 'bad' : s.error_rate > 0.03 ? 'warn' : 'good',
      },
      {
        key: 'lat',
        icon: 'clock',
        label: a.latency,
        value: s.p50_ms == null ? '—' : `${ms(s.p50_ms, ui.lang)} / ${ms(s.p95_ms, ui.lang)}`,
        hint: '',
        tone: '',
      },
      {
        key: 'tok',
        icon: 'hash',
        label: a.tokens,
        value: fmt(s.avg_tokens),
        hint: a.tokensTotal(fmt(total)),
        tone: '',
      },
      {
        key: 'sat',
        icon: 'up',
        label: a.satisfaction,
        value: s.satisfaction == null ? '—' : pct(s.satisfaction, ui.lang),
        hint:
          s.thumbs_up + s.thumbs_down
            ? a.ratings(s.thumbs_up, s.thumbs_down)
            : a.noRatings,
        tone: s.satisfaction == null ? '' : s.satisfaction < 0.7 ? 'warn' : 'good',
      },
      {
        key: 'sql',
        icon: 'database',
        label: a.sqlFail,
        value: pct(s.sql_fail_rate, ui.lang),
        hint: a.recovered(s.sql_recovered),
        tone: '',
      },
    ]
  })

  const intentRows = computed(() => {
    const ui = useUiStore()
    const d = data.value
    if (!d) return []
    const max = Math.max(1, ...d.by_intent.map(r => r.n))
    return d.by_intent.map(r => ({
      ...r,
      label: (ui.t.adm.intentNames as Record<string, string>)[r.intent] || r.intent,
      pct: Math.round((100 * r.n) / max),
    }))
  })

  // Only the latest request counts: switching 1 → 90 days quickly must not end up showing
  // the 1-day data if that answer arrives last. reset() (page closed) also invalidates.
  let requestSeq = 0

  async function load(nextDays?: number) {
    const ui = useUiStore()
    if (nextDays) days.value = nextDays as (typeof DASH_DAYS)[number]
    const req = ++requestSeq
    loading.value = true
    error.value = ''
    try {
      const d = await api<AdminMetrics>(`/admin/metrics?days=${days.value}`)
      if (req !== requestSeq) return
      data.value = d
      updatedAt.value = Date.now()
      await nextTick()
      if (req !== requestSeq) return
      await drawAdminCharts(
        d,
        { ok: ui.t.adm.ok, failed: ui.t.adm.failed, accuracy: ui.t.adm.accuracy },
        ui.lang,
      )
    } catch (e) {
      if (req !== requestSeq) return
      const err = e as ApiError
      error.value =
        (err.code && (ui.t.errors as Record<string, string>)[err.code]) || err.message
    } finally {
      if (req === requestSeq) loading.value = false
    }
  }

  async function loadFeatures() {
    const ui = useUiStore()
    try {
      const data = await api<{ features: string[]; roles: Record<string, string[]> }>(
        '/admin/features',
      )
      featureNames.value = data.features
      roleFeatures.value = data.roles
    } catch (e) {
      const err = e as ApiError
      error.value =
        (err.code && (ui.t.errors as Record<string, string>)[err.code]) || err.message
    }
  }

  function toggleFeature(role: string, feature: string) {
    const current = roleFeatures.value?.[role]
    if (!current) return
    roleFeatures.value = {
      ...roleFeatures.value,
      [role]: current.includes(feature)
        ? current.filter(f => f !== feature)
        : [...current, feature],
    }
  }

  async function saveRole(role: string) {
    const ui = useUiStore()
    const features = roleFeatures.value?.[role]
    if (!features) return
    savingRole.value = role
    try {
      const saved = await api<{ role: string; features: string[] }>(
        '/admin/features',
        { role, features },
        'PUT',
      )
      roleFeatures.value = { ...roleFeatures.value, [role]: saved.features }
      ui.toast(ui.t.adm.permSaved, 'ok')
      // The admin may have changed their own role: menus follow the new list
      await useAuthStore().refreshMe()
    } catch (e) {
      const err = e as ApiError
      ui.toast((err.code && (ui.t.errors as Record<string, string>)[err.code]) || err.message, 'error')
    } finally {
      savingRole.value = ''
    }
  }

  function reset() {
    requestSeq++
    loading.value = false
    data.value = null
    error.value = ''
    updatedAt.value = null
    destroyAdminCharts()
  }

  function dailyLabel() {
    const ui = useUiStore()
    const d = data.value
    if (!d) return ''
    return `${ui.t.adm.daily}: ` + d.daily.map(r => `${r.day} ${r.requests}`).join(', ')
  }

  function evalLabel() {
    const ui = useUiStore()
    const d = data.value
    if (!d) return ''
    return (
      `${ui.t.adm.eval}: ` +
      d.eval_history.map(r => `${r.model} ${pct(r.accuracy, ui.lang)}`).join(', ')
    )
  }

  return {
    data,
    days,
    loading,
    error,
    updated,
    roleFeatures,
    featureNames,
    savingRole,
    dashDays,
    admKpis,
    intentRows,
    load,
    loadFeatures,
    toggleFeature,
    saveRole,
    reset,
    dailyLabel,
    evalLabel,
  }
})
