/* Painel de KPIs de vendas (/dashboard): textos + mixin (estado e gráficos). */
"use strict";

const dashCharts = {};

const DASH_TEXTS = {
  pt: {
    nav: { dashboard: "Dashboard" },
    pageTitles: { dashboard: "Dashboard · Multistore AI" },
    dash: {
      title: "Dashboard", sub: "Faturação, lojas, margens e previsão no teu âmbito.",
      refresh: "Atualizar", loading: "A carregar…", empty: "Ainda sem dados neste âmbito.",
      thisMonth: "Faturação este mês (até hoje)", lastMonth: "Mesmo período do mês passado",
      vsLast: n => `vs os mesmos ${n} dias do mês passado`,
      excluded: n => `${n} ${n === 1 ? "produto sem custo conhecido ficou" : "produtos sem custo conhecido ficaram"} de fora da margem.`,
      topStores: "Top 5 lojas (este mês)", marginBrand: "Margem por marca (este mês)",
      forecast: "Previsão a 7 dias", revenue: "Faturação (€)", margin: "Margem (€)",
      store: "Loja", brand: "Marca", noStores: "Sem lojas com vendas este mês.",
      noMargin: "Sem margem calculável este mês.", noForecast: "Previsão indisponível.",
      changeUp: p => `↑ ${p} %`, changeDown: p => `↓ ${Math.abs(p)} %`, changeFlat: "igual ao mês passado",
    },
  },
  en: {
    nav: { dashboard: "Dashboard" },
    pageTitles: { dashboard: "Dashboard · Multistore AI" },
    dash: {
      title: "Dashboard", sub: "Revenue, stores, margins and forecast in your scope.",
      refresh: "Refresh", loading: "Loading…", empty: "No data in this scope yet.",
      thisMonth: "Revenue this month (to date)", lastMonth: "Same period last month",
      vsLast: n => `vs the same ${n} days last month`,
      excluded: n => `${n} ${n === 1 ? "product with unknown cost was" : "products with unknown cost were"} left out of the margin.`,
      topStores: "Top 5 stores (this month)", marginBrand: "Margin by brand (this month)",
      forecast: "7-day forecast", revenue: "Revenue (€)", margin: "Margin (€)",
      store: "Store", brand: "Brand", noStores: "No stores with sales this month.",
      noMargin: "No margin this month.", noForecast: "Forecast unavailable.",
      changeUp: p => `↑ ${p} %`, changeDown: p => `↓ ${Math.abs(p)} %`, changeFlat: "same as last month",
    },
  },
  es: {
    nav: { dashboard: "Panel" },
    pageTitles: { dashboard: "Panel · Multistore AI" },
    dash: {
      title: "Panel", sub: "Facturación, tiendas, márgenes y previsión en tu ámbito.",
      refresh: "Actualizar", loading: "Cargando…", empty: "Aún no hay datos en este ámbito.",
      thisMonth: "Facturación este mes (hasta hoy)", lastMonth: "Mismo periodo del mes pasado",
      vsLast: n => `vs los mismos ${n} días del mes pasado`,
      excluded: n => `${n} ${n === 1 ? "producto sin coste conocido quedó" : "productos sin coste conocido quedaron"} fuera del margen.`,
      topStores: "Top 5 tiendas (este mes)", marginBrand: "Margen por marca (este mes)",
      forecast: "Previsión a 7 días", revenue: "Facturación (€)", margin: "Margen (€)",
      store: "Tienda", brand: "Marca", noStores: "Sin tiendas con ventas este mes.",
      noMargin: "Sin margen este mes.", noForecast: "Previsión no disponible.",
      changeUp: p => `↑ ${p} %`, changeDown: p => `↓ ${Math.abs(p)} %`, changeFlat: "igual que el mes pasado",
    },
  },
  fr: {
    nav: { dashboard: "Tableau" },
    pageTitles: { dashboard: "Tableau de bord · Multistore AI" },
    dash: {
      title: "Tableau de bord", sub: "Chiffre d'affaires, magasins, marges et prévision dans ton périmètre.",
      refresh: "Actualiser", loading: "Chargement…", empty: "Pas encore de données dans ce périmètre.",
      thisMonth: "CA ce mois-ci (à ce jour)", lastMonth: "Même période le mois dernier",
      vsLast: n => `vs les mêmes ${n} jours du mois dernier`,
      excluded: n => `${n} ${n === 1 ? "produit au coût inconnu a été exclu" : "produits au coût inconnu ont été exclus"} de la marge.`,
      topStores: "Top 5 magasins (ce mois)", marginBrand: "Marge par marque (ce mois)",
      forecast: "Prévision sur 7 jours", revenue: "CA (€)", margin: "Marge (€)",
      store: "Magasin", brand: "Marque", noStores: "Aucun magasin avec des ventes ce mois-ci.",
      noMargin: "Pas de marge ce mois-ci.", noForecast: "Prévision indisponible.",
      changeUp: p => `↑ ${p} %`, changeDown: p => `↓ ${Math.abs(p)} %`, changeFlat: "identique au mois dernier",
    },
  },
};

function installDashboardTexts(TEXTS) {
  for (const lang of Object.keys(DASH_TEXTS)) {
    const src = DASH_TEXTS[lang], dst = TEXTS[lang];
    Object.assign(dst.nav, src.nav);
    Object.assign(dst.pageTitles, src.pageTitles);
    dst.dash = src.dash;
  }
}

const DashboardMixin = {
  data() {
    return { dash: { data: null, loading: false, error: "" } };
  },
  methods: {
    async loadDashboard() {
      this.dash.loading = true; this.dash.error = "";
      try {
        this.dash.data = await this.api("/dashboard");
        this.$nextTick(() => this.drawDashCharts());
      } catch (e) {
        this.dash.error = e.message; this.dash.data = null;
        this.destroyDashCharts();
      } finally { this.dash.loading = false; }
    },
    destroyDashCharts() {
      for (const id of Object.keys(dashCharts)) { dashCharts[id].destroy(); delete dashCharts[id]; }
    },
    money(v) {
      const n = Number(v);
      if (!Number.isFinite(n)) return "—";
      return n.toLocaleString(LOCALES[this.lang] || "en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
    },
    changeLabel(pct) {
      if (pct == null) return "—";
      if (pct > 0) return this.t.dash.changeUp(pct);
      if (pct < 0) return this.t.dash.changeDown(pct);
      return this.t.dash.changeFlat;
    },
    _barChart(id, labels, values, label) {
      const el = document.getElementById(id);
      if (!el || typeof Chart === "undefined") return;
      dashCharts[id]?.destroy();
      const brand = getComputedStyle(document.documentElement).getPropertyValue("--brand").trim() || "#0f7a5a";
      dashCharts[id] = new Chart(el, {
        type: "bar",
        data: { labels, datasets: [{ label, data: values, backgroundColor: brand + "cc", borderRadius: 6 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { callback: v => this.money(v) } } },
        },
      });
    },
    _lineChart(id, labels, values, label) {
      const el = document.getElementById(id);
      if (!el || typeof Chart === "undefined") return;
      dashCharts[id]?.destroy();
      const brand = getComputedStyle(document.documentElement).getPropertyValue("--brand").trim() || "#0f7a5a";
      dashCharts[id] = new Chart(el, {
        type: "line",
        data: { labels, datasets: [{ label, data: values, borderColor: brand, backgroundColor: brand + "33",
                                     fill: true, tension: 0.3, pointRadius: 3 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { callback: v => this.money(v) } } },
        },
      });
    },
    // Secções presentes conforme os módulos da conta (sql: vendas; forecast: previsão)
    dashMargins() { return (this.dash.data?.margin_by_brand || []).filter(r => r.margin != null); },
    drawDashCharts() {
      const d = this.dash.data; if (!d) return;
      if (d.top_stores) {
        this._barChart("dash-stores", d.top_stores.map(r => r.store), d.top_stores.map(r => r.revenue), this.t.dash.revenue);
      }
      if (d.margin_by_brand) {
        const m = this.dashMargins();              // marcas só com custos desconhecidos não têm margem
        this._barChart("dash-margin", m.map(r => r.brand), m.map(r => r.margin), this.t.dash.margin);
      }
      if (d.forecast_7d) {
        const rows = d.forecast_7d.rows || [];
        this._lineChart("dash-forecast", rows.map(r => r[0]), rows.map(r => r[1]), this.t.dash.forecast);
      }
    },
  },
};
