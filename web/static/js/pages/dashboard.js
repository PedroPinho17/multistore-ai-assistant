/* Dashboard (/dashboard): KPIs e gráficos Chart.js.
 * Só aparecem as secções que a conta pode ver: vendas (módulo sql) e previsão (módulo forecast). */
"use strict";

const DashboardPage = {
  name: "dashboard-page",
  template: String.raw`
    <main class="page wide">
      <p class="error" v-if="dash.error" role="alert">{{ dash.error }}</p>

      <section class="kpis" :aria-label="t.dash.title" v-if="!dash.data || dash.data.revenue">
        <template v-if="dash.data">
          <div class="card kpi">
            <div class="label"><svg class="i" aria-hidden="true"><use href="#i-trend"/></svg> {{ t.dash.thisMonth }}</div>
            <div class="value">{{ money(dash.data.revenue.this_month_to_date) }}</div>
            <div class="hint2">{{ changeLabel(dash.data.revenue.change_pct) }} · {{ t.dash.vsLast(dash.data.revenue.days) }}</div>
          </div>
          <div class="card kpi">
            <div class="label"><svg class="i" aria-hidden="true"><use href="#i-history"/></svg> {{ t.dash.lastMonth }}</div>
            <div class="value">{{ money(dash.data.revenue.last_month_same_days) }}</div>
            <div class="hint2">{{ t.dash.vsLast(dash.data.revenue.days) }}</div>
          </div>
        </template>
        <template v-else>
          <div v-for="i in 2" :key="i" class="card kpi"><div class="skeleton" style="height:58px"></div></div>
        </template>
      </section>

      <div class="dash-cols" v-if="dash.data && dash.data.top_stores">
        <section class="card">
          <h2 class="sec">{{ t.dash.topStores }}</h2>
          <div class="chart-wrap" v-if="dash.data.top_stores.length"><canvas id="dash-stores" role="img" :aria-label="t.dash.topStores"></canvas></div>
          <p v-else class="muted">{{ t.dash.noStores }}</p>
        </section>
        <section class="card">
          <h2 class="sec">{{ t.dash.marginBrand }}</h2>
          <div class="chart-wrap" v-if="dashMargins().length"><canvas id="dash-margin" role="img" :aria-label="t.dash.marginBrand"></canvas></div>
          <p v-else class="muted">{{ t.dash.noMargin }}</p>
          <p v-if="dash.data.margin_excluded_items" class="help">{{ t.dash.excluded(dash.data.margin_excluded_items) }}</p>
        </section>
      </div>

      <section class="card" v-if="dash.data && dash.data.forecast_7d">
        <h2 class="sec">{{ t.dash.forecast }}</h2>
        <div class="chart-wrap" v-if="dash.data.forecast_7d.rows.length"><canvas id="dash-forecast" role="img" :aria-label="t.dash.forecast"></canvas></div>
        <p v-else class="muted">{{ t.dash.noForecast }}</p>
      </section>
    </main>
  `,
};
