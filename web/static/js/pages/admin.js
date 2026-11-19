/* Observabilidade (/admin, só admin) */
"use strict";

const AdminPage = {
  name: "admin-page",
  template: String.raw`
    <main class="page wide">
          <p class="error" v-if="adm.error" role="alert">{{ adm.error }}</p>

          <section class="kpis" :aria-label="t.adm.title">
            <template v-if="adm.data">
              <div v-for="k in admKpis" :key="k.key" class="card kpi" :class="k.tone">
                <div class="label"><svg class="i" aria-hidden="true"><use :href="'#i-' + k.icon"/></svg> {{ k.label }}</div>
                <div class="value">{{ k.value }}</div>
                <div class="hint2">{{ k.hint }}</div>
              </div>
            </template>
            <template v-else><div v-for="i in 6" :key="i" class="card kpi"><div class="skeleton" style="height:58px"></div></div></template>
          </section>

          <p v-if="adm.data && !adm.data.summary.requests" class="card empty-state"><svg class="i" aria-hidden="true"><use href="#i-inbox"/></svg> {{ t.adm.empty }}</p>

          <div class="dash-cols" v-if="adm.data">
            <section class="card">
              <h2 class="sec">{{ t.adm.daily }}</h2>
              <div class="chart-wrap"><canvas id="adm-daily" role="img" :aria-label="dailyLabel()"></canvas></div>
            </section>
            <section class="card">
              <h2 class="sec">{{ t.adm.intents }}</h2>
              <div v-for="r in intentRows" :key="r.intent" class="kind-row">
                <span>{{ r.label }}</span>
                <div class="kind-bar" role="img" :aria-label="r.label + ': ' + r.n"><span :style="{ width: r.pct + '%' }"></span></div>
                <span class="n">{{ r.n }}</span>
              </div>
              <p v-if="!intentRows.length" class="muted">—</p>
              <p class="help" v-if="adm.data.summary.requests">{{ t.adm.classifier }}: {{ pct(adm.data.summary.classifier_share) }} · {{ t.adm.classifierHint }}<br>{{ t.adm.cache }}: {{ pct(adm.data.summary.cache_share) }} · {{ t.adm.cacheHint(adm.data.summary.cache_hits || 0) }}</p>
            </section>
          </div>

          <section class="card" v-if="adm.data">
            <h2 class="sec">{{ t.adm.eval }}</h2>
            <p class="sec-sub">{{ t.adm.evalSub }}</p>
            <template v-if="adm.data.eval_history.length">
              <div class="dash-cols even">
                <div class="chart-wrap"><canvas id="adm-eval" role="img" :aria-label="evalLabel()"></canvas></div>
                <div class="tbl-wrap">
                  <table class="tbl">
                    <thead><tr><th>{{ t.adm.date }}</th><th>{{ t.adm.model }}</th><th>{{ t.adm.level }}</th><th class="num">{{ t.adm.accuracy }}</th></tr></thead>
                    <tbody>
                      <tr v-for="r in [...adm.data.eval_history].reverse()" :key="r.file">
                        <td>{{ shortDate(r.date) }}</td>
                        <td>{{ shortModel(r.model) }} <span v-if="(r.source || '').startsWith('imported')" class="tag-sm">{{ t.adm.imported }}</span></td>
                        <td>{{ r.level === 'all' ? t.adm.allLevels : r.level }} · {{ r.runs }}×</td>
                        <td class="num"><strong>{{ pct(r.accuracy) }}</strong></td>
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

          <div class="dash-cols even" v-if="adm.data">
            <section class="card">
              <h2 class="sec">{{ t.adm.top }}</h2>
              <div class="tbl-wrap" v-if="adm.data.top_questions.length">
                <table class="tbl">
                  <thead><tr><th class="wrap">{{ t.adm.question }}</th><th class="num">{{ t.adm.times }}</th><th class="num"><span class="sr-only">{{ t.adm.failed }}</span><svg class="i" aria-hidden="true"><use href="#i-alert"/></svg></th><th class="num"><span class="sr-only">{{ t.rate.label }}</span><svg class="i" aria-hidden="true"><use href="#i-up"/></svg> / <svg class="i" aria-hidden="true"><use href="#i-down"/></svg></th></tr></thead>
                  <tbody>
                    <tr v-for="q in adm.data.top_questions" :key="q.question">
                      <td class="wrap">{{ q.question }}</td><td class="num">{{ q.n }}</td>
                      <td class="num">{{ q.errors || '' }}</td><td class="num">{{ q.up || q.down ? q.up + '/' + q.down : '' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="muted">—</p>
            </section>
            <section class="card">
              <h2 class="sec">{{ t.adm.kinds }}</h2>
              <div class="tbl-wrap" v-if="adm.data.by_kind.length">
                <table class="tbl">
                  <thead><tr><th>{{ t.adm.kind }}</th><th class="num">{{ t.adm.n }}</th><th class="num">{{ t.adm.avg }}</th><th class="num">p95</th><th class="num">{{ t.adm.avgTokens }}</th></tr></thead>
                  <tbody>
                    <tr v-for="k in adm.data.by_kind" :key="k.kind">
                      <td>{{ t.adm.kindNames[k.kind] || k.kind }}</td><td class="num">{{ k.n }}</td>
                      <td class="num">{{ ms(k.avg_ms) }}</td><td class="num">{{ ms(k.p95_ms) }}</td><td class="num">{{ format(k.avg_tokens, 0) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="muted">—</p>
            </section>
          </div>

          <div class="dash-cols even" v-if="adm.data">
            <section class="card">
              <h2 class="sec">{{ t.adm.down }}</h2>
              <ul class="ev-list" v-if="adm.data.thumbs_down.length">
                <li v-for="r in adm.data.thumbs_down" :key="r.id" class="down">
                  {{ r.question }}
                  <div class="meta2"><span>{{ r.username }}</span><span>{{ ago(r.created_at) }}</span><span>{{ t.adm.kindNames[r.kind] || r.kind }}</span></div>
                </li>
              </ul>
              <p v-else class="muted">{{ t.adm.noDown }}</p>
            </section>
            <section class="card">
              <h2 class="sec">{{ t.adm.errors }}</h2>
              <ul class="ev-list" v-if="adm.data.recent_errors.length">
                <li v-for="r in adm.data.recent_errors" :key="r.id">
                  {{ r.question }}
                  <div class="meta2"><span>{{ r.username }}</span><span>{{ ago(r.created_at) }}</span><span>{{ t.adm.kindNames[r.kind] || r.kind }}</span><span>{{ ms(r.duration_ms) }}</span></div>
                  <code v-if="r.error">{{ r.error }}</code>
                </li>
              </ul>
              <p v-else class="muted">{{ t.adm.noErrors }}</p>
            </section>
          </div>

          <section class="card" v-if="adm.data && adm.data.by_user.length">
            <h2 class="sec">{{ t.adm.byUser }}</h2>
            <div class="tbl-wrap">
              <table class="tbl">
                <thead><tr><th>{{ t.adm.user }}</th><th>{{ t.um.role }}</th><th class="num">{{ t.adm.requests }}</th><th class="num"><span class="sr-only">{{ t.adm.failed }}</span><svg class="i" aria-hidden="true"><use href="#i-alert"/></svg></th><th class="num">Tokens</th><th>{{ t.adm.last }}</th></tr></thead>
                <tbody>
                  <tr v-for="u in adm.data.by_user" :key="u.username">
                    <td>{{ u.username }}</td><td>{{ t.roles[u.role] || u.role }}</td><td class="num">{{ u.requests }}</td>
                    <td class="num">{{ u.errors || '' }}</td><td class="num">{{ format(u.tokens, 0) }}</td><td>{{ ago(u.last_at) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <p class="help" v-if="adm.updated" style="text-align:center">{{ t.adm.updated }} {{ adm.updated }}</p>
            </main>
  `,
};
