<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import AppShell from '@/components/AppShell.vue'
import { moneyEur } from '@/lib/format'
import { useDashboardStore } from '@/stores/dashboard'
import { useUiStore } from '@/stores/ui'

const dash = useDashboardStore()
const ui = useUiStore()
const { data, loading, error, margins } = storeToRefs(dash)
const { t, lang } = storeToRefs(ui)

function changeLabel(pct: number | null | undefined) {
  if (pct == null) return '—'
  if (pct > 0) return t.value.dash.changeUp(pct)
  if (pct < 0) return t.value.dash.changeDown(pct)
  return t.value.dash.changeFlat
}

watch(
  () => ui.t.pageTitles.dashboard,
  title => {
    document.title = title
  },
  { immediate: true },
)

watch(
  () => [t.value.dash.title, t.value.dash.sub] as const,
  ([title, sub]) => ui.setPageMeta(title, sub, 'dashboard'),
  { immediate: true },
)

onMounted(() => {
  void dash.load()
})
onUnmounted(() => dash.reset())

const money = (v: unknown) => moneyEur(v, lang.value)
</script>

<template>
  <AppShell>
    <div class="page-scroll">
      <main class="page wide">
        <p v-if="error" class="error" role="alert">{{ error }}</p>

        <section
          v-if="!data || data.revenue"
          class="kpis"
          :aria-label="t.dash.title"
        >
          <template v-if="data?.revenue">
            <div class="card kpi">
              <div class="label">
                <svg class="i" aria-hidden="true"><use href="#i-trend" /></svg>
                {{ t.dash.thisMonth }}
              </div>
              <div class="value">{{ money(data.revenue.this_month_to_date) }}</div>
              <div class="hint2">
                {{ changeLabel(data.revenue.change_pct) }} ·
                {{ t.dash.vsLast(data.revenue.days) }}
              </div>
            </div>
            <div class="card kpi">
              <div class="label">
                <svg class="i" aria-hidden="true"><use href="#i-history" /></svg>
                {{ t.dash.lastMonth }}
              </div>
              <div class="value">{{ money(data.revenue.last_month_same_days) }}</div>
              <div class="hint2">{{ t.dash.vsLast(data.revenue.days) }}</div>
            </div>
          </template>
          <template v-else-if="loading">
            <div v-for="i in 2" :key="i" class="card kpi">
              <div class="skeleton" style="height: 58px"></div>
            </div>
          </template>
        </section>

        <div v-if="data?.top_stores" class="dash-cols">
          <section class="card">
            <h2 class="sec">{{ t.dash.topStores }}</h2>
            <div v-if="data.top_stores.length" class="chart-wrap">
              <canvas id="dash-stores" role="img" :aria-label="t.dash.topStores"></canvas>
            </div>
            <p v-else class="muted">{{ t.dash.noStores }}</p>
          </section>
          <section class="card">
            <h2 class="sec">{{ t.dash.marginBrand }}</h2>
            <div v-if="margins.length" class="chart-wrap">
              <canvas id="dash-margin" role="img" :aria-label="t.dash.marginBrand"></canvas>
            </div>
            <p v-else class="muted">{{ t.dash.noMargin }}</p>
            <p v-if="data.margin_excluded_items" class="help">
              {{ t.dash.excluded(data.margin_excluded_items) }}
            </p>
          </section>
        </div>

        <section v-if="data?.forecast_7d" class="card">
          <h2 class="sec">{{ t.dash.forecast }}</h2>
          <div v-if="data.forecast_7d.rows.length" class="chart-wrap">
            <canvas id="dash-forecast" role="img" :aria-label="t.dash.forecast"></canvas>
          </div>
          <p v-else class="muted">{{ t.dash.noForecast }}</p>
        </section>
      </main>
    </div>
  </AppShell>
</template>
