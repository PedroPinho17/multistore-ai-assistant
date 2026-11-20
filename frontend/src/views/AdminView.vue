<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import AppShell from '@/components/AppShell.vue'
import { ago, formatValue, ms, pct, shortDate, shortModel } from '@/lib/format'
import { useAdminStore } from '@/stores/admin'
import { useUiStore } from '@/stores/ui'

const adm = useAdminStore()
const ui = useUiStore()
const { data, loading, error, updated, admKpis, intentRows } = storeToRefs(adm)
const { t, lang } = storeToRefs(ui)
const clock = Date.now()

watch(
  () => ui.t.pageTitles.admin,
  title => {
    document.title = title
  },
  { immediate: true },
)
watch(
  () => [t.value.adm.title, t.value.adm.sub] as const,
  ([title, sub]) => ui.setPageMeta(title, sub, 'admin'),
  { immediate: true },
)

onMounted(() => {
  void adm.load()
})
onUnmounted(() => adm.reset())
</script>

<template>
  <AppShell>
    <div class="page-scroll">
      <main class="page wide">
        <p v-if="error" class="error" role="alert">{{ error }}</p>

        <section class="kpis" :aria-label="t.adm.title">
          <template v-if="data">
            <div v-for="k in admKpis" :key="k.key" class="card kpi" :class="k.tone">
              <div class="label">
                <svg class="i" aria-hidden="true"><use :href="'#i-' + k.icon" /></svg>
                {{ k.label }}
              </div>
              <div class="value">{{ k.value }}</div>
              <div class="hint2">{{ k.hint }}</div>
            </div>
          </template>
          <template v-else>
            <div v-for="i in 6" :key="i" class="card kpi">
              <div class="skeleton" style="height: 58px"></div>
            </div>
          </template>
        </section>

        <p v-if="data && !data.summary.requests" class="card empty-state">
          <svg class="i" aria-hidden="true"><use href="#i-inbox" /></svg> {{ t.adm.empty }}
        </p>

        <div v-if="data" class="dash-cols">
          <section class="card">
            <h2 class="sec">{{ t.adm.daily }}</h2>
            <div class="chart-wrap">
              <canvas id="adm-daily" role="img" :aria-label="adm.dailyLabel()"></canvas>
            </div>
          </section>
          <section class="card">
            <h2 class="sec">{{ t.adm.intents }}</h2>
            <div v-for="r in intentRows" :key="r.intent" class="kind-row">
              <span>{{ r.label }}</span>
              <div class="kind-bar" role="img" :aria-label="r.label + ': ' + r.n">
                <span :style="{ width: r.pct + '%' }"></span>
              </div>
              <span class="n">{{ r.n }}</span>
            </div>
            <p v-if="!intentRows.length" class="muted">—</p>
            <p v-if="data.summary.requests" class="help">
              {{ t.adm.classifier }}: {{ pct(data.summary.classifier_share, lang) }} ·
              {{ t.adm.classifierHint }}<br />
              {{ t.adm.cache }}: {{ pct(data.summary.cache_share, lang) }} ·
              {{ t.adm.cacheHint(data.summary.cache_hits || 0) }}
            </p>
          </section>
        </div>

        <section v-if="data" class="card">
          <h2 class="sec">{{ t.adm.eval }}</h2>
          <p class="sec-sub">{{ t.adm.evalSub }}</p>
          <template v-if="data.eval_history.length">
            <div class="dash-cols even">
              <div class="chart-wrap">
                <canvas id="adm-eval" role="img" :aria-label="adm.evalLabel()"></canvas>
              </div>
              <div class="tbl-wrap">
                <table class="tbl">
                  <thead>
                    <tr>
                      <th>{{ t.adm.date }}</th>
                      <th>{{ t.adm.model }}</th>
                      <th>{{ t.adm.level }}</th>
                      <th class="num">{{ t.adm.accuracy }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in [...data.eval_history].reverse()" :key="r.file">
                      <td>{{ shortDate(r.date, lang) }}</td>
                      <td>
                        {{ shortModel(r.model) }}
                        <span
                          v-if="(r.source || '').startsWith('imported')"
                          class="tag-sm"
                          >{{ t.adm.imported }}</span
                        >
                      </td>
                      <td>
                        {{ r.level === 'all' ? t.adm.allLevels : r.level }} · {{ r.runs }}×
                      </td>
                      <td class="num">
                        <strong>{{ pct(r.accuracy, lang) }}</strong>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
          <p v-else class="muted">{{ t.adm.noEval }}</p>
          <p class="help">{{ t.adm.evalHow }}</p>
          <div class="cmd">uv run python -m multistore_ai_assistant.evaluate 1</div>
        </section>

        <div v-if="data" class="dash-cols even">
          <section class="card">
            <h2 class="sec">{{ t.adm.top }}</h2>
            <div v-if="data.top_questions.length" class="tbl-wrap">
              <table class="tbl">
                <thead>
                  <tr>
                    <th class="wrap">{{ t.adm.question }}</th>
                    <th class="num">{{ t.adm.times }}</th>
                    <th class="num">
                      <span class="sr-only">{{ t.adm.failed }}</span>
                      <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg>
                    </th>
                    <th class="num">
                      <span class="sr-only">{{ t.rate.label }}</span>
                      <svg class="i" aria-hidden="true"><use href="#i-up" /></svg> /
                      <svg class="i" aria-hidden="true"><use href="#i-down" /></svg>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="q in data.top_questions" :key="q.question">
                    <td class="wrap">{{ q.question }}</td>
                    <td class="num">{{ q.n }}</td>
                    <td class="num">{{ q.errors || '' }}</td>
                    <td class="num">{{ q.up || q.down ? q.up + '/' + q.down : '' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="muted">—</p>
          </section>
          <section class="card">
            <h2 class="sec">{{ t.adm.kinds }}</h2>
            <div v-if="data.by_kind.length" class="tbl-wrap">
              <table class="tbl">
                <thead>
                  <tr>
                    <th>{{ t.adm.kind }}</th>
                    <th class="num">{{ t.adm.n }}</th>
                    <th class="num">{{ t.adm.avg }}</th>
                    <th class="num">p95</th>
                    <th class="num">{{ t.adm.avgTokens }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="k in data.by_kind" :key="k.kind">
                    <td>{{ t.adm.kindNames[k.kind as keyof typeof t.adm.kindNames] || k.kind }}</td>
                    <td class="num">{{ k.n }}</td>
                    <td class="num">{{ ms(k.avg_ms, lang) }}</td>
                    <td class="num">{{ ms(k.p95_ms, lang) }}</td>
                    <td class="num">{{ formatValue(k.avg_tokens, lang, 0) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="muted">—</p>
          </section>
        </div>

        <div v-if="data" class="dash-cols even">
          <section class="card">
            <h2 class="sec">{{ t.adm.down }}</h2>
            <ul v-if="data.thumbs_down.length" class="ev-list">
              <li v-for="r in data.thumbs_down" :key="r.id" class="down">
                {{ r.question }}
                <div class="meta2">
                  <span>{{ r.username }}</span>
                  <span>{{ ago(r.created_at, clock, t.p.ago) }}</span>
                  <span>{{ t.adm.kindNames[r.kind as keyof typeof t.adm.kindNames] || r.kind }}</span>
                </div>
              </li>
            </ul>
            <p v-else class="muted">{{ t.adm.noDown }}</p>
          </section>
          <section class="card">
            <h2 class="sec">{{ t.adm.errors }}</h2>
            <ul v-if="data.recent_errors.length" class="ev-list">
              <li v-for="r in data.recent_errors" :key="r.id">
                {{ r.question }}
                <div class="meta2">
                  <span>{{ r.username }}</span>
                  <span>{{ ago(r.created_at, clock, t.p.ago) }}</span>
                  <span>{{ t.adm.kindNames[r.kind as keyof typeof t.adm.kindNames] || r.kind }}</span>
                  <span>{{ ms(r.duration_ms, lang) }}</span>
                </div>
                <code v-if="r.error">{{ r.error }}</code>
              </li>
            </ul>
            <p v-else class="muted">{{ t.adm.noErrors }}</p>
          </section>
        </div>

        <section v-if="data?.by_user.length" class="card">
          <h2 class="sec">{{ t.adm.byUser }}</h2>
          <div class="tbl-wrap">
            <table class="tbl">
              <thead>
                <tr>
                  <th>{{ t.adm.user }}</th>
                  <th>{{ t.um.role }}</th>
                  <th class="num">{{ t.adm.requests }}</th>
                  <th class="num">
                    <span class="sr-only">{{ t.adm.failed }}</span>
                    <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg>
                  </th>
                  <th class="num">Tokens</th>
                  <th>{{ t.adm.last }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in data.by_user" :key="u.username">
                  <td>{{ u.username }}</td>
                  <td>{{ t.roles[u.role as keyof typeof t.roles] || u.role }}</td>
                  <td class="num">{{ u.requests }}</td>
                  <td class="num">{{ u.errors || '' }}</td>
                  <td class="num">{{ formatValue(u.tokens, lang, 0) }}</td>
                  <td>{{ ago(u.last_at, clock, t.p.ago) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <p v-if="updated" class="help" style="text-align: center">
          {{ t.adm.updated }} {{ updated }}
        </p>
        <p v-if="loading" class="sr-only">{{ t.dash.loading }}</p>
      </main>
    </div>
  </AppShell>
</template>
