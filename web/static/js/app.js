/* Aplicação Vue: estado, router (/…), API e ações. As páginas estão em pages/. */
// Contas públicas de demonstração (as mesmas do README)
const DEMO_ACCOUNTS = [
  { user: "pedro", pass: "imperador123", role: "imperador", icon: "crown" },
  { user: "gestor.burgerlab", pass: "marca123", role: "marca", icon: "tag" },
  { user: "gerente.maia", pass: "loja123", role: "loja", icon: "store" },
];
// Páginas da UI: têm de coincidir com UI_PATHS em api/routes/pages.py (o servidor devolve a UI nestes caminhos)
const ROUTES = { "/": "home", "/login": "login", "/chat": "chat", "/profile": "profile",
                 "/users": "users", "/admin": "admin", "/settings": "settings", "/review": "review" };
const PATHS = Object.fromEntries(Object.entries(ROUTES).map(([path, view]) => [view, path]));
const PRIVATE_VIEWS = ["chat", "profile", "users", "admin", "settings", "review"];
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
const KIND_ORDER = ["sql", "forecast", "orders", "no_sql", "denied", "error"];

const LOCALES = { pt: "pt-PT", en: "en-GB", es: "es-ES", fr: "fr-FR" };
const LANG_NAMES = { pt: "Português", en: "English", es: "Español", fr: "Français" };
const COLUMN_LABELS = {
  pt: { day: "Dia", forecast_revenue_eur: "Faturação prevista (€)", ingredient: "Ingrediente", unit: "Unidade",
        needed_7_days: "Necessário (7 dias)", stock: "Stock", to_order: "A encomendar" },
  en: { day: "Day", forecast_revenue_eur: "Forecast revenue (€)", ingredient: "Ingredient", unit: "Unit",
        needed_7_days: "Needed (7 days)", stock: "Stock", to_order: "To order" },
  es: { day: "Día", forecast_revenue_eur: "Facturación prevista (€)", ingredient: "Ingrediente", unit: "Unidad",
        needed_7_days: "Necesario (7 días)", stock: "Stock", to_order: "A pedir" },
  fr: { day: "Jour", forecast_revenue_eur: "Chiffre d'affaires prévu (€)", ingredient: "Ingrédient", unit: "Unité",
        needed_7_days: "Nécessaire (7 jours)", stock: "Stock", to_order: "À commander" },
};

const store = {  // sessionStorage: o token desaparece quando se fecha o separador
  get(k) { try { return sessionStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch {} },
  del(k) { try { sessionStorage.removeItem(k); } catch {} },
};
const prefs = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};
// Limpa tokens antigos guardados em localStorage pela versão anterior
try { localStorage.removeItem("token"); localStorage.removeItem("user"); } catch {}

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let nextId = 1;
const charts = {};

const RootApp = {
  mixins: [AdminMixin, SettingsMixin, ReviewMixin],
  data() {
    return {
      lang: prefs.get("lang") || (Object.keys(TEXTS).find(l => navigator.language.startsWith(l)) || "en"),
      // Tema: escolha (claro / escuro / sistema) e o que está aplicado agora
      themePref: ["light", "dark", "system"].includes(prefs.get("theme")) ? prefs.get("theme") : "system",
      theme: (prefs.get("theme") === "light" || prefs.get("theme") === "dark") ? prefs.get("theme")
             : (darkQuery.matches ? "dark" : "light"),
      accent: (ACCENTS.includes(prefs.get("accent")) || isCustomAccent(prefs.get("accent"))) ? prefs.get("accent") : null,
      appConfig: { default_accent: "green", default_lang: "pt", show_demo_accounts: true },
      token: store.get("token"),
      user: JSON.parse(store.get("user") || "null"),
      username: "", password: "", loginError: "", loggingIn: false, shake: false,
      question: "", messages: [], loading: false, stepIndex: 0, stepTimer: null, welcomeDone: false,
      alerts: [], alertsOpen: true,
      conversations: [], currentConv: null, sidebarOpen: false,
      editingId: null, editTitle: "", announce: "",
      dialog: null, toasts: [], userMenu: false,
      view: null, showPassword: false, capsLock: false,
      demo: { msgs: [], typing: false }, demoTimer: null, demoSession: 0,
      profile: null, clock: Date.now(),
      pw: { current: "", new: "", confirm: "", show: false, saving: false, error: "", ok: false },
    };
  },
  computed: {
    last() { const m = this.messages[this.messages.length - 1]; return m && m.from === "bot" && !m.welcome ? m : null; },
    t() { return TEXTS[this.lang]; },
    // Âmbito de dados da conta: o admin vê o grupo como o Imperador
    scope() { return { marca: "brand", loja: "store" }[this.user?.role] || "group"; },
    // Sugestões do início do chat: do âmbito da conta e só dos módulos que ela tem
    starterSuggestions() {
      return (this.t.starters[this.scope] || []).filter(([mod]) => this.hasModule(mod)).map(([, q]) => q);
    },
    langNames() { return LANG_NAMES; },
    demoAccounts() { return DEMO_ACCOUNTS; },
    tokenExp() {
      try { return JSON.parse(atob(this.token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp * 1000; }
      catch { return null; }
    },
    sessionLeft() {
      if (!this.tokenExp) return "—";
      const ms = this.tokenExp - this.clock;
      if (ms <= 0) return this.t.p.sessionExpired;
      return this.t.p.left(Math.floor(ms / 3600000), Math.floor((ms % 3600000) / 60000));
    },
    scopeText() {
      const p = this.t.p, pr = this.profile || {};
      if (!this.user) return "";
      if (this.user.role === "imperador" || this.user.role === "admin") return p.scopeAll;
      if (this.user.role === "marca") return p.scopeBrand(pr.brand_name || "…");
      return p.scopeStore(pr.store_name || "…", pr.brand_name || "…");
    },
    permissions() {
      const p = this.t.p, u = this.user, pr = this.profile || {};
      if (!u) return [];
      const n = pr.visible_stores ?? "…";
      const boss = u.role === "imperador" || u.role === "admin";
      const stores = boss ? p.storesAll(n)
        : u.role === "marca" ? p.storesBrand(n, pr.brand_name || "…") : p.storesOne(pr.store_name || "…");
      const mods = this.t.mods, has = m => this.hasModule(m);
      return [
        { ok: true, text: stores },
        { ok: has("sql"), text: mods.sql }, { ok: has("forecast"), text: mods.forecast },
        { ok: has("orders"), text: mods.orders }, { ok: boss, text: p.purchases },
        { ok: has("teach"), text: mods.teach }, { ok: has("users"), text: mods.users },
        ...(has("observability") ? [{ ok: true, text: mods.observability }] : []),
        { ok: false, text: p.personal }, { ok: false, text: p.write },
      ];
    },
    kindRows() {
      const counts = this.profile?.stats?.by_kind || {};
      const max = Math.max(1, ...Object.values(counts));
      return KIND_ORDER.filter(k => counts[k]).map(k => ({
        key: k, label: this.t.p.kinds[k], n: counts[k], pct: Math.round(100 * counts[k] / max) }));
    },
    pwStrength() {
      const v = this.pw.new;
      if (!v) return 0;
      let score = 0;
      if (v.length >= 8) score++;
      if (v.length >= 12) score++;
      if (/[a-z]/.test(v) && /[A-Z]/.test(v)) score++;
      if (/[0-9]/.test(v) && /[^A-Za-z0-9]/.test(v)) score++;
      return v.length < 8 ? Math.min(score, 1) : score;
    },
    // Título e subtítulo do topo das páginas privadas
    pageTitle() {
      if (this.view === "chat") return this.conversations.find(c => c.id === this.currentConv)?.title || this.t.newChat;
      return { profile: this.t.p.title, users: this.t.um.title, admin: this.t.adm.title, settings: this.t.st.title,
               review: this.t.rv.title }[this.view] || this.t.title;
    },
    pageSub() {
      return { chat: this.t.title, profile: this.scopeText, users: this.t.um.sub, admin: this.t.adm.sub,
               settings: this.t.st.sub, review: this.t.rv.sub }[this.view] || "";
    },
    effectiveAccent() { return this.accent || this.appConfig.default_accent || "green"; },
    showDemo() { return this.appConfig.show_demo_accounts !== false;
    },
    initials() { return (this.user?.username || "?").split(/[.\s_-]/).map(p => p[0]).join("").slice(0, 2).toUpperCase(); },
  },
  watch: {
    theme: { immediate: true, handler(v) {
      document.documentElement.dataset.theme = v;
      this.applyAccent();
    } },
    effectiveAccent: { immediate: true, handler() { this.applyAccent(); } },
    lang:  { immediate: true, handler(v) {
      document.documentElement.lang = v;
      if (this.view) document.title = this.t.pageTitles[this.view];
      if (this.view === "home") this.startDemo();
      if (this.token && this.view === "chat") this.loadAlerts();   // texto dos alertas vem no idioma pedido
    } },
  },
  async mounted() {
    window.addEventListener("popstate", this.onRoute);
    document.addEventListener("click", this.onLinkClick);
    document.addEventListener("click", () => (this.userMenu = false));
    document.addEventListener("keydown", e => { if (e.key === "Escape") this.userMenu = false; });
    setInterval(() => (this.clock = Date.now()), 30000);
    darkQuery.addEventListener("change", () => { if (this.themePref === "system") this.applyTheme(); });
    this.loadConfig();                           // cor/idioma por defeito e contas de demo (público)
    if (this.token) await this.refreshMe();      // módulos e definições atuais da conta
    this.onRoute();
  },
  methods: {
    // ----- Diálogo de confirmação e toasts -----
    confirmDialog(opts) {                       // devolve uma Promise<boolean>
      if (this.dialog) this.closeDialog(false);
      this._dlgFocus = document.activeElement;
      return new Promise(resolve => {
        this.dialog = { ...opts, resolve };
        this.$nextTick(() => this.$refs.dlgOk?.focus());
      });
    },
    closeDialog(ok) {
      const d = this.dialog;
      if (!d) return;
      this.dialog = null;
      d.resolve(ok);
      this._dlgFocus?.focus?.();
    },
    dialogKey(e) {
      if (e.key === "Escape") { e.preventDefault(); this.closeDialog(false); }
      else if (e.key === "Tab") {               // o foco fica preso dentro do diálogo
        e.preventDefault();
        const { dlgOk, dlgCancel } = this.$refs;
        (document.activeElement === dlgOk ? dlgCancel : dlgOk)?.focus();
      }
    },
    toast(text, type = "error") {
      const id = nextId++;
      this.toasts.push({ id, text, type });
      if (this.toasts.length > 4) this.toasts.shift();
      setTimeout(() => this.dismissToast(id), type === "error" ? 6000 : 3500);
    },
    dismissToast(id) { this.toasts = this.toasts.filter(x => x.id !== id); },

    // ----- Router (/, /login, /chat, /profile, …) com a History API -----
    go(view) {
      const path = PATHS[view];
      if (location.pathname !== path || location.hash) history.pushState(null, "", path);
      this.onRoute();
    },
    // Links internos (<a href="/chat">) mudam de página sem recarregar
    onLinkClick(e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest?.("a[href]");
      if (!a || a.target || a.hasAttribute("download")) return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin || !(url.pathname in ROUTES)) return;
      if (url.pathname === location.pathname && url.hash) return;      // âncora na mesma página (#features)
      e.preventDefault();
      this.go(ROUTES[url.pathname]);
    },
    onRoute() {
      // Links antigos (/#/chat) passam para o URL novo (/chat)
      if (location.hash.startsWith("#/")) history.replaceState(null, "", location.hash.slice(1) || "/");
      const path = location.pathname.replace(/\/+$/, "") || "/";
      let v = ROUTES[path] || "home";
      if (!this.token && PRIVATE_VIEWS.includes(v)) v = "login";
      if (this.token && v === "login") v = "chat";
      if (v === "users" && !this.hasModule("users")) v = "chat";
      if (v === "admin" && !this.hasModule("observability")) v = "chat";
      if (v === "review" && !this.hasModule("teach")) v = "chat";
      if (location.pathname !== PATHS[v]) history.replaceState(null, "", PATHS[v] + (v === "home" ? location.hash : ""));
      const prev = this.view;
      // Mesma página (âncora da homepage, link para a página atual): só fecha os menus
      if (v === prev) { this.userMenu = false; this.sidebarOpen = false; return; }
      this.view = v;
      this.enterView(v, prev);
    },
    enterView(v, prev) {
      document.title = this.t.pageTitles[v];
      if (prev === "home" && v !== "home") this.stopDemo();
      if (prev === "admin" && v !== "admin") this.destroyAdminCharts();
      if (v !== prev) { window.scrollTo(0, 0); const ps = document.getElementById("page-scroll"); if (ps) ps.scrollTop = 0; }
      this.userMenu = false; this.sidebarOpen = false;
      if (v === "home") this.startDemo();
      if (v === "login") this.$nextTick(() => document.getElementById("u")?.focus());
      if (v === "chat") {
        if (!this.messages.length) this.welcome();
        this.loadConversations();
        this.$nextTick(() => document.getElementById("question")?.focus());
      }
      if (v === "profile") {
        this.pw = { current: "", new: "", confirm: "", show: false, saving: false, error: "", ok: false };
        this.loadProfile();
      }
      if (v === "users") { this.um.form = null; this.um.editId = null; this.loadUsers(); }
      if (v === "admin") this.loadMetrics();
      if (v === "settings") this.loadAppSettings();
      if (v === "review") { this.loadReview(); if (this.rv.tab === "examples") this.loadExamples(); }
      else if (v !== "home" && v !== "login" && prev !== v) this.loadReviewCount();
    },
    scrollToId(id) { document.getElementById(id)?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" }); },

    // ----- Homepage: conversa de demonstração animada -----
    startDemo() {
      this.stopDemo();
      const session = ++this.demoSession;
      const script = this.t.h.demo;
      this.demo = { msgs: [], typing: false };
      if (reduceMotion) {
        const d = script[0];
        this.demo.msgs = [{ id: nextId++, from: "user", text: d.q },
                          { id: nextId++, from: "bot", text: d.a, shown: d.a, done: true, bars: d.bars, tag: d.tag }];
        return;
      }
      const wait = ms => new Promise(r => { this.demoTimer = setTimeout(r, ms); });
      const alive = () => session === this.demoSession;
      (async () => {
        for (let i = 0; alive(); i++) {
          const d = script[i % script.length];
          if (this.demo.msgs.length >= 4) this.demo.msgs.splice(0, 2);
          this.demo.msgs.push({ id: nextId++, from: "user", text: d.q });
          await wait(700); if (!alive()) return;
          this.demo.typing = true;
          await wait(1300); if (!alive()) return;
          this.demo.typing = false;
          this.demo.msgs.push({ id: nextId++, from: "bot", text: d.a, shown: "", done: false, bars: d.bars, tag: d.tag });
          await this.typeOut(this.demo.msgs[this.demo.msgs.length - 1]);
          await wait(3600);
        }
      })();
    },
    stopDemo() { this.demoSession++; clearTimeout(this.demoTimer); this.demo.typing = false; },

    // ----- Login -----
    checkCaps(e) { if (e.getModifierState) this.capsLock = e.getModifierState("CapsLock"); },
    useDemo(d) {                                 // tabela da página inicial → login já preenchido
      this.username = d.user; this.password = d.pass; this.loginError = "";
      this.go("login");
      this.$nextTick(() => document.querySelector(".auth-form .primary")?.focus());
    },
    async uploadAvatar(e) {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      try {
        const image = await avatarFromFile(file);
        await this.api("/profile/avatar", { image });
        this.user = { ...this.user, avatar: image }; store.set("user", JSON.stringify(this.user));
        this.toast(this.t.avatar.saved, "ok");
      } catch (err) { this.toast(err.status ? err.message : this.t.avatar.bad); }
    },
    async removeAvatar() {
      try {
        await this.api("/profile/avatar", null, "DELETE");
        this.user = { ...this.user, avatar: null }; store.set("user", JSON.stringify(this.user));
        this.toast(this.t.avatar.removed, "ok");
      } catch (err) { this.toast(err.message); }
    },
    fillDemo(d) {
      this.username = d.user; this.password = d.pass; this.loginError = "";
      this.$nextTick(() => document.querySelector(".auth-form .primary")?.focus());
    },

    // ----- Perfil -----
    setTheme(v) { this.themePref = v; prefs.set("theme", v); this.applyTheme(); this.saveSetting({ theme: v }); },
    async loadProfile() {
      try { this.profile = await this.api("/profile"); } catch {}
    },
    async changePassword() {
      const p = this.t.p, pw = this.pw;
      pw.error = ""; pw.ok = false;
      const v = pw.new;
      if (v.length < 8) pw.error = p.errShort;
      else if (/^[0-9]+$/.test(v) || /^[\p{L}]+$/u.test(v)) pw.error = p.errMix;
      else if (v.toLowerCase().includes(this.user.username.toLowerCase())) pw.error = p.errUser;
      else if (v === pw.current) pw.error = p.errSame;
      else if (v !== pw.confirm) pw.error = p.errMatch;
      if (pw.error) return;
      pw.saving = true;
      try {
        await this.api("/profile/password", { current_password: pw.current, new_password: v });
        this.pw = { current: "", new: "", confirm: "", show: false, saving: false, error: "", ok: true };
      } catch (e) {
        pw.error = e.status === 429 ? this.t.tooMany
          : e.code === "pw_wrong_current" ? p.wrongCurrent : e.message;
      } finally { pw.saving = false; }
    },
    async deleteAllConversations() {
      const n = this.profile?.stats?.conversations || 0;
      if (!n) return;
      const ok = await this.confirmDialog({ title: this.t.dlg.clearTitle, text: this.t.p.confirmClear(n),
                                            confirm: this.t.dlg.del, danger: true });
      if (!ok) return;
      try {
        await this.api("/conversations", null, "DELETE");
        this.clearCharts();
        this.conversations = []; this.currentConv = null; this.messages = [];
        await this.loadProfile();
        this.toast(this.t.dlg.cleared, "ok");
      } catch (e) { this.toast(e.message); }
    },
    ago(iso) {
      const a = this.t.p.ago, min = Math.round((this.clock - new Date(iso)) / 60000);
      if (min < 1) return a.now;
      if (min < 60) return a.min(min);
      if (min < 1440) return a.h(Math.round(min / 60));
      return a.d(Math.round(min / 1440));
    },
    dateFmt(iso) { return new Date(iso).toLocaleDateString(LOCALES[this.lang], { day: "numeric", month: "short", year: "numeric" }); },

    now() { return new Date().toLocaleTimeString(LOCALES[this.lang], { hour: "2-digit", minute: "2-digit" }); },
    setLang(l) { this.lang = l; prefs.set("lang", l); this.saveSetting({ lang: l }); },
    colName(c) { return COLUMN_LABELS[this.lang][c] || c.replace(/_/g, " "); },
    toggleTheme() { this.setTheme(this.theme === "dark" ? "light" : "dark"); },

    // ----- Definições da conta: aplicadas logo, guardadas no browser e na conta -----
    applyTheme() { this.theme = this.themePref === "system" ? (darkQuery.matches ? "dark" : "light") : this.themePref; },
    redrawCharts() {
      this.$nextTick(() => {
        this.messages.forEach(m => m.chart && m.done && this.drawChart(m));
        if (this.view === "admin") this.drawAdminCharts();
      });
    },
    // Cor de destaque: predefinida (CSS por [data-accent]) ou personalizada (tons calculados e postos em variáveis)
    applyAccent() {
      const a = this.effectiveAccent, root = document.documentElement;
      const VARS = ["--brand", "--brand-2", "--brand-soft", "--btn", "--btn-2", "--logo-1", "--logo-2"];
      if (isCustomAccent(a)) {
        const pal = customPalette(a)[this.theme === "dark" ? "dark" : "light"];
        root.dataset.accent = "custom";
        for (const [k, v] of Object.entries(pal)) root.style.setProperty(k, v);
      } else {
        VARS.forEach(k => root.style.removeProperty(k));
        root.dataset.accent = a;
      }
      const link = document.getElementById("favicon");
      if (link) link.href = faviconSvg(a);
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", accentColors(a)[1]);
      this.redrawCharts();
    },
    setAccent(a) { this.accent = a; prefs.set("accent", a); this.saveSetting({ accent: a }); },
    async saveSetting(changes) {
      if (!this.token) return;
      try { await this.api("/settings/me", changes, "PUT"); }
      catch (e) { if (e.status !== 401) this.toast(this.apiError(e)); }
    },
    applyUserSettings(st) {                      // definições guardadas na conta ganham ao browser
      if (!st) return;
      if (st.lang) { this.lang = st.lang; prefs.set("lang", st.lang); }
      if (st.theme) { this.themePref = st.theme; prefs.set("theme", st.theme); this.applyTheme(); }
      if (st.accent) { this.accent = st.accent; prefs.set("accent", st.accent); }
    },
    async resetSettings() {
      try { await this.api("/settings/me", { lang: null, theme: null, accent: null }, "PUT"); } catch {}
      for (const k of ["lang", "theme", "accent"]) { try { localStorage.removeItem(k); } catch {} }
      this.accent = null; this.themePref = "system"; this.applyTheme();
      this.lang = this.appConfig.default_lang || this.lang;
      this.toast(this.t.st.resetDone, "ok");
    },
    async loadConfig() {
      try {
        const cfg = await (await fetch("/config", { headers: { "Accept-Language": this.lang } })).json();
        this.appConfig = { ...this.appConfig, ...cfg };
        if (!prefs.get("lang") && !this.token && TEXTS[cfg.default_lang]) this.lang = cfg.default_lang;
      } catch {}
    },

    async api(path, body, method) {
      let res;
      try {
        res = await fetch(path, {
          method: method || (body ? "POST" : "GET"),
          headers: { "Content-Type": "application/json", "Accept-Language": this.lang,
                     ...(this.token ? { Authorization: "Bearer " + this.token } : {}) },
          body: body ? JSON.stringify(body) : undefined,
        });
      } catch { throw new Error(this.t.network); }
      if (res.status === 401 && this.token) { this.logout("login"); throw new Error(this.t.loginError); }
      let data = null;
      try { data = await res.json(); } catch {}
      if (!res.ok) throw this.httpError(res, data);
      return data;
    },
    // Erros conhecidos no idioma do site; o resto usa a mensagem do servidor ({code, message})
    httpError(res, data) {
      const code = data?.detail?.code;
      const known = { 403: this.t.errors.forbidden, 404: this.t.errors.notFound, 429: this.t.tooMany };
      const err = new Error((code && this.t.errors[code]) || known[res.status]
        || (typeof data?.detail === "string" ? data.detail : data?.detail?.message || res.statusText));
      err.status = res.status; err.code = code;
      return err;
    },

    async login() {
      if (!this.username || !this.password) return;
      this.loggingIn = true;
      try {
        const data = await this.api("/login", { username: this.username, password: this.password });
        this.token = data.token; this.user = data.user; this.password = ""; this.loginError = "";
        this.um.options = null;
        store.set("token", data.token); store.set("user", JSON.stringify(data.user));
        this.showPassword = false; this.capsLock = false;
        this.refreshMe();                          // foto e marca (para o avatar)
        this.go("chat");
      } catch (e) {
        this.loginError = e.status === 429 ? this.t.tooMany : (e.status === 401 ? this.t.loginError : e.message);
        this.shake = true; setTimeout(() => (this.shake = false), 450);
      } finally { this.loggingIn = false; }
    },
    logout(to) {
      this.clearCharts();
      this.token = null; this.user = null; this.messages = []; this.welcomeDone = false;
      this.conversations = []; this.currentConv = null; this.profile = null;
      this.destroyAdminCharts();
      this.um = { list: [], options: null, loading: false, form: null, editId: null, edit: null, query: "", role: "", status: "" };
      this.adm = { data: null, days: 7, loading: false, error: "", updated: null };
      store.del("token"); store.del("user");
      this.go(typeof to === "string" ? to : "home");
    },
    clearChat() { this.newConversation(); },

    async loadConversations() {
      try { this.conversations = await this.api("/conversations"); } catch {}
    },
    // Os gráficos de mensagens que já não estão no ecrã são destruídos (libertam memória)
    clearCharts() { for (const id of Object.keys(charts)) { charts[id].destroy(); delete charts[id]; } },
    newConversation() {
      this.clearCharts();
      this.currentConv = null; this.sidebarOpen = false;
      this.messages = []; this.welcome();
    },
    async openConversation(id) {
      this.sidebarOpen = false;
      if (this.loading || id === this.currentConv) return;
      try {
        const msgs = await this.api(`/conversations/${id}`);
        this.clearCharts();
        this.currentConv = id; this.messages = []; this.welcomeDone = false;
        const time = iso => new Date(iso).toLocaleTimeString(LOCALES[this.lang],
                                                             { hour: "2-digit", minute: "2-digit" });
        let lastQuestion = "";
        for (const m of msgs) {
          if (m.role === "user") {
            lastQuestion = m.content;
            this.messages.push({ id: nextId++, from: "user", text: m.content, time: time(m.created_at) });
          } else {
            this.addBot({ text: m.content, shown: m.content, done: true, time: time(m.created_at),
                          question: lastQuestion, sql: m.sql, kind: m.kind, error: m.kind === "error",
                          requestId: m.request_id, rating: m.rating });
          }
        }
        this.$nextTick(this.scrollDown);
      } catch (e) { this.toast(e.message); }
    },
    async deleteConversation(c) {
      const ok = await this.confirmDialog({ title: this.t.dlg.delTitle, subject: c.title, text: this.t.dlg.delText,
                                            confirm: this.t.dlg.del, danger: true });
      if (!ok) return;
      try {
        await this.api(`/conversations/${c.id}`, null, "DELETE");
        if (c.id === this.currentConv) this.newConversation();
        this.loadConversations();
        this.toast(this.t.dlg.deleted, "ok");
      } catch (e) { this.toast(e.message); }
    },
    startRename(c) { this.editingId = c.id; this.editTitle = c.title; },
    async saveTitle(c) {
      if (this.editingId !== c.id) return;          // evita gravar duas vezes (Enter + blur)
      this.editingId = null;
      const title = this.editTitle.trim();
      if (!title || title === c.title) return;
      try { await this.api(`/conversations/${c.id}`, { title }, "PATCH"); c.title = title; }
      catch (e) { this.toast(e.message); }
    },

    async loadAlerts() {
      try { this.alerts = (await this.api("/alerts")).alerts || []; }
      catch { this.alerts = []; }
    },

    welcome() {
      this.loadAlerts();
      this.welcomeDone = false;
      const name = this.user.username.split(/[.\s]/)[0];
      const m = this.addBot({ text: this.t.welcome(name.charAt(0).toUpperCase() + name.slice(1), this.scope,
                                                   this.hasModule("forecast"), this.hasModule("orders")), welcome: true });
      this.typeOut(m).then(() => { this.welcomeDone = true; this.scrollDown(); });
    },

    addBot(fields) {
      const m = { id: nextId++, from: "bot", text: "", shown: "", done: false, time: this.now(),
                  rows: [], showTable: false, showSql: false, liked: false, copied: false, sqlCopied: false,
                  requestId: null, rating: null, suggestions: [], explanation: "", explaining: false, ...fields };
      this.messages.push(m);
      return this.messages[this.messages.length - 1];   // versão reativa
    },

    // Efeito "máquina de escrever": revela o texto aos poucos
    typeOut(m) {
      return new Promise(resolve => {
        if (reduceMotion || !m.text) { m.shown = m.text; m.done = true; return resolve(); }
        const chunk = Math.max(1, Math.round(m.text.length / 90));
        let i = 0;
        const tick = () => {
          i = Math.min(m.text.length, i + chunk);
          m.shown = m.text.slice(0, i);
          if (i % 12 === 0) this.scrollDown();
          if (i < m.text.length) setTimeout(tick, 14 + Math.random() * 18);
          else { m.done = true; this.scrollDown(); resolve(); }
        };
        tick();
      });
    },

    startSteps() {
      this.stepIndex = 0;
      this.stepTimer = setInterval(() => {
        if (this.stepIndex < this.t.steps.length - 1) this.stepIndex++;
      }, 1400);
    },

    // Passos reais do streaming → índice em t.steps
    stepOf(step) { return { classify: 0, sql: 1, query: 2, forecast: 2, answer: 3 }[step] ?? this.stepIndex; },

    botFields(q, r) {
      return {
        question: q, text: r.error || r.answer || "", error: !!r.error, sql: r.sql, kind: r.kind,
        requestId: r.request_id, rating: null, cached: !!r.cached, suggestions: r.suggestions || [],
        columns: r.columns, rows: r.rows || [], chart: this.canChart(r),
        showTable: (r.rows || []).length > 1 && (r.rows || []).length <= 12,
      };
    },

    // Lê o /ask/stream (Server-Sent Events). Devolve a mensagem criada, ou null se o servidor não suportar.
    async streamAsk(q) {
      let res;
      try {
        res = await fetch("/ask/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept-Language": this.lang, Authorization: "Bearer " + this.token },
          body: JSON.stringify({ question: q, lang: this.lang, conversation_id: this.currentConv }),
        });
      } catch { throw new Error(this.t.network); }
      if (res.status === 404 || res.status === 405 || !res.body) return null;     // servidor antigo: usa o /ask
      if (res.status === 401) { this.logout("login"); throw new Error(this.t.loginError); }
      if (!res.ok) { let data = null; try { data = await res.json(); } catch {} throw this.httpError(res, data); }

      clearInterval(this.stepTimer);
      const reader = res.body.getReader(), decoder = new TextDecoder();
      let buffer = "", m = null, data = null, final = null;
      const handle = ev => {
        if (ev.type === "status") this.stepIndex = this.stepOf(ev.step);
        else if (ev.type === "data") data = ev;
        else if (ev.type === "token") {
          if (!m) { m = this.addBot({ question: q }); this.loading = false; }
          m.text += ev.text; m.shown = m.text; this.scrollDown();
        } else if (ev.type === "done") final = ev;
        else if (ev.type === "error") final = { error: ev.message };
      };
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let cut;
          while ((cut = buffer.indexOf("\n\n")) >= 0) {
            const line = buffer.slice(0, cut).trim(); buffer = buffer.slice(cut + 2);
            if (line.startsWith("data:")) { try { handle(JSON.parse(line.slice(5))); } catch {} }
          }
        }
      } catch {}   // ligação cortada a meio: mostra a mensagem traduzida, não o "network error" do browser
      if (!final) final = { error: this.t.network };
      if (final.conversation_id) { this.currentConv = final.conversation_id; this.loadConversations(); }
      const fields = this.botFields(q, { ...(data || {}), ...final });
      if (m) Object.assign(m, fields);
      else m = this.addBot(fields);
      m.shown = m.text;   // sem tokens (p.ex. erro antes da resposta) o texto também tem de aparecer
      return m;
    },

    async send(text) {
      const q = (text ?? this.question).trim();
      if (!q || this.loading) return;
      this.messages.push({ id: nextId++, from: "user", text: q, time: this.now() });
      this.question = ""; this.$nextTick(this.autoGrow);
      this.loading = true; this.startSteps(); this.scrollDown();
      let m, streamed = false;
      try {
        m = await this.streamAsk(q);
        streamed = !!m;
        if (!m) {
          const r = await this.api("/ask", { question: q, lang: this.lang, conversation_id: this.currentConv });
          this.currentConv = r.conversation_id;
          this.loadConversations();
          m = this.addBot(this.botFields(q, r));
        }
      } catch (e) {
        m = this.addBot({ text: e.message, error: true });
      } finally {
        clearInterval(this.stepTimer); this.loading = false;
      }
      if (streamed) m.done = true; else await this.typeOut(m);
      this.announce = m.text;
      if (m.chart) this.$nextTick(() => this.drawChart(m));
      this.$nextTick(() => { this.scrollDown(); document.getElementById("question")?.focus(); });
    },

    async explain(m) {
      if (m.explanation || m.explaining) return;
      m.explaining = true;
      try { m.explanation = (await this.api("/explain", { request_id: m.requestId, lang: this.lang })).explanation; }
      catch (e) { this.toast(e.message); }
      finally { m.explaining = false; }
    },

    async like(m) {
      try { await this.api("/feedback", { question: m.question, sql: m.sql }); m.liked = true; }
      catch (e) { this.toast(e.status === 400 ? this.t.errors.badSql : e.message); }
    },
    async copy(m) {
      try { await navigator.clipboard.writeText(m.text); m.copied = true; setTimeout(() => (m.copied = false), 1500); } catch {}
    },
    async copySql(m) {
      try { await navigator.clipboard.writeText(m.sql); m.sqlCopied = true; setTimeout(() => (m.sqlCopied = false), 1500); } catch {}
    },
    downloadCsv(m) {
      // Prefixo ' evita "CSV injection" (fórmulas ao abrir no Excel)
      const cell = v => {
        let s = v === null || v === undefined ? "" : String(v);
        if (/^[=+\-@\t\r]/.test(s) && isNaN(Number(s))) s = "'" + s;
        return /[",;\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      const csv = [m.columns.map(c => this.colName(c)), ...m.rows].map(r => r.map(cell).join(";")).join("\n");
      const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: "resultado.csv" });
      a.click(); URL.revokeObjectURL(url);
    },

    scrollDown() { this.$nextTick(() => { const c = document.getElementById("chat-scroll"); if (c) c.scrollTop = c.scrollHeight; }); },
    autoGrow() { const el = document.getElementById("question"); if (!el) return; el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; },

    // Gráfico quando há 2+ linhas, 1.ª coluna = rótulo e última coluna = número
    canChart(r) {
      if (!r.columns || !r.rows || r.rows.length < 2 || r.rows.length > 60 || r.columns.length < 2) return false;
      return r.rows.every(row => row[row.length - 1] !== null && !isNaN(parseFloat(row[row.length - 1])));
    },
    // Coluna dos rótulos: a 1.ª que varia ("loja | mês | total" de uma só loja → mês)
    labelCol(m) {
      const last = m.columns.length - 1;
      for (let j = 0; j < last; j++) if (new Set(m.rows.map(r => String(r[j]))).size > 1) return j;
      return 0;
    },
    drawChart(m) {
      const el = document.getElementById("chart-" + m.id);
      if (!el) return;
      charts[m.id]?.destroy();
      const css = getComputedStyle(document.documentElement);
      const brand = css.getPropertyValue("--brand").trim(), muted = css.getPropertyValue("--muted").trim(),
            grid = css.getPropertyValue("--border").trim();
      const li = this.labelCol(m);
      const isTime = /^\d{4}(-\d{2})?(-\d{2})?$|^\d{1,2}$/.test(String(m.rows[0][li]));
      charts[m.id] = new Chart(el, {
        type: isTime ? "line" : "bar",
        data: {
          labels: m.rows.map(r => r[li]),
          datasets: [{ label: this.colName(m.columns[m.columns.length - 1]), data: m.rows.map(r => parseFloat(r[r.length - 1])),
                       backgroundColor: brand + "cc", borderColor: brand, borderWidth: 2, borderRadius: 6,
                       tension: .35, fill: isTime ? { target: "origin", above: brand + "22" } : false, pointRadius: 2 }],
        },
        options: {
          animation: { duration: reduceMotion ? 0 : 900, easing: "easeOutQuart" },
          plugins: { legend: { display: false } },
          scales: { x: { ticks: { color: muted }, grid: { display: false } },
                    y: { ticks: { color: muted }, grid: { color: grid } } },
        },
      });
    },
    chartLabel(m) {
      const col = this.colName(m.columns[m.columns.length - 1]);
      const li = this.labelCol(m);
      const pts = m.rows.slice(0, 12).map(r => `${r[li]}: ${this.format(r[r.length - 1])}`).join("; ");
      return `${this.t.chart} — ${col}. ${pts}${m.rows.length > 12 ? "…" : ""}`;
    },
    isNum(v) { return typeof v === "number" || (typeof v === "string" && v !== "" && !isNaN(v)); },
    // Casas decimais por coluna: se algum valor tiver cêntimos, mostram-se em todos (50 793,00, não 50 793)
    colDecimals(m, j) {
      m._dec ??= {};
      return (m._dec[j] ??= m.rows.some(r => this.isNum(r[j]) && !Number.isInteger(Number(r[j]))) ? 2 : 0);
    },
    format(v, dec) {
      if (v === null || v === undefined) return "—";
      if (this.isNum(v)) {
        const n = Number(v);
        dec ??= Number.isInteger(n) ? 0 : 2;
        return n.toLocaleString(LOCALES[this.lang], { minimumFractionDigits: dec, maximumFractionDigits: dec });
      }
      return v;
    },
  },
};

// Páginas: cada uma é um componente com o seu template (web/static/js/pages/).
// O estado e as ações vivem na instância raiz (um store único, sem build nem Pinia);
// connectPages dá a cada página acesso a eles, como um mapState/mapActions automático.
const PAGES = { "home-page": HomePage, "login-page": LoginPage, "app-shell": AppShell, "chat-page": ChatPage,
                "profile-page": ProfilePage, "settings-page": SettingsPage, "users-page": UsersPage,
                "admin-page": AdminPage, "review-page": ReviewPage };

function connectPages(root, pages) {
  const sources = [root, ...(root.mixins || [])];
  const dataKeys = sources.flatMap(o => (o.data ? Object.keys(o.data.call({})) : []));
  const computedKeys = sources.flatMap(o => Object.keys(o.computed || {}));
  const methodKeys = sources.flatMap(o => Object.keys(o.methods || {}));
  const computed = {}, methods = {};
  for (const k of [...dataKeys, ...computedKeys]) {
    computed[k] = { get() { return this.$root[k]; }, set(v) { this.$root[k] = v; } };
  }
  for (const k of methodKeys) methods[k] = function (...args) { return this.$root[k](...args); };
  for (const page of Object.values(pages)) {
    page.computed = { ...computed, ...(page.computed || {}) };
    page.methods = { ...methods, ...(page.methods || {}) };
  }
}
connectPages(RootApp, PAGES);

const app = Vue.createApp(RootApp);
app.component("lang-picker", LangPicker).component("user-avatar", UserAvatar);
for (const [tag, page] of Object.entries(PAGES)) app.component(tag, page);
app.mount("#app");

