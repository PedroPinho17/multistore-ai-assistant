/* Página de Definições (/settings): aparência e idioma da conta + definições da aplicação (admin).
 *
 * As escolhas da conta são guardadas na BD (PUT /settings/me) e no browser, para
 * aparecerem logo ao abrir a página. As da aplicação (PUT /settings/app) são as
 * predefinições de todos: cor, idioma, contas de demonstração e duração da sessão.
 */
"use strict";

const ACCENTS = ["green", "orange", "blue", "wine", "purple", "graphite"];
// Cor do botão (texto branco) de cada tema de cor: favicon, barra do browser e amostras
const ACCENT_COLORS = {
  green: ["#14905f", "#0b6b4e"], orange: ["#d9480f", "#9a3412"], blue: ["#2563eb", "#1e40af"],
  wine: ["#be123c", "#881337"], purple: ["#7c3aed", "#5b21b6"], graphite: ["#4b5563", "#1f2937"],
};

// ---------- Cor personalizada: tons calculados com contraste AA garantido ----------
const HEX_RE = /^#[0-9a-f]{6}$/;
const isCustomAccent = a => HEX_RE.test(a || "");
const WHITE = [255, 255, 255], BLACK = [0, 0, 0];
const DARK_SURFACE = [0x14, 0x1a, 0x18];             // --surface do tema escuro
const MIN_CONTRAST = 4.6;                            // AA pede 4,5; fica uma pequena margem

function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
function rgbToHex(c) { return "#" + c.map(v => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join(""); }
function mixRgb(a, b, t) { return a.map((v, i) => v + (b[i] - v) * t); }
function luminance(c) {
  const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
}
function contrastRatio(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}
/** Aproxima ``c`` de ``target`` (preto ou branco) só o necessário para ter contraste com ``against``. */
function untilContrast(c, target, against, min = MIN_CONTRAST) {
  for (let t = 0; t <= 1.0001; t += 0.02) {
    const out = mixRgb(c, target, t);
    if (contrastRatio(out, against) >= min) return out;
  }
  return target;
}

/** Tons do tema claro e escuro a partir de uma cor ``#rrggbb``, sempre com contraste AA:
 *  texto branco nos botões, texto da cor sobre branco e sobre o fundo suave, e o mesmo no escuro. */
function customPalette(hex) {
  const base = hexToRgb(hex);
  const btn = untilContrast(base, BLACK, WHITE);                 // botão com texto branco
  const soft = mixRgb(btn, WHITE, 0.9);                         // fundo suave (chips, item ativo)
  const brand = untilContrast(btn, BLACK, soft);                // texto/ligações: legível no branco e no suave
  const btn2 = mixRgb(btn, BLACK, 0.18);                        // hover
  const dSoft = mixRgb(base, DARK_SURFACE, 0.82);
  const dBrand = untilContrast(untilContrast(base, WHITE, DARK_SURFACE), WHITE, dSoft);
  const adjusted = Math.max(...base.map((v, i) => Math.abs(v - btn[i]))) > 24;
  const H = rgbToHex;
  return {
    light: { "--brand": H(brand), "--brand-2": H(btn2), "--brand-soft": H(soft), "--btn": H(btn), "--btn-2": H(btn2),
             "--logo-1": H(mixRgb(btn, WHITE, 0.12)), "--logo-2": H(btn2) },
    dark: { "--brand": H(dBrand), "--brand-2": H(dBrand), "--brand-soft": H(dSoft), "--btn": H(btn), "--btn-2": H(btn2),
            "--logo-1": H(mixRgb(btn, WHITE, 0.12)), "--logo-2": H(btn2) },
    swatch: [H(mixRgb(btn, WHITE, 0.12)), H(btn2)],
    adjusted,
  };
}

/** As duas cores do gradiente (favicon, amostra) de uma cor predefinida ou personalizada. */
function accentColors(a) { return isCustomAccent(a) ? customPalette(a).swatch : (ACCENT_COLORS[a] || ACCENT_COLORS.green); }

/** Favicon em SVG com a cor escolhida (o ícone do separador acompanha a cor da conta).
 *  Desenho simplificado (duas barras grossas) para se ler a 16 px. */
function faviconSvg(accent) {
  const [a, b] = accentColors(accent);
  return "data:image/svg+xml," + encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>` +
    `<rect width="64" height="64" rx="14" fill="url(#g)"/>` +
    `<path d="M16 13h32a7 7 0 0 1 7 7v18a7 7 0 0 1-7 7H30l-14 10V45a7 7 0 0 1-7-7V20a7 7 0 0 1 7-7z" fill="#fff"/>` +
    `<rect x="20.5" y="25" width="7" height="11" rx="3.5" fill="${b}"/>` +
    `<rect x="36.5" y="21" width="7" height="15" rx="3.5" fill="${b}"/></svg>`);
}

const SETTINGS_TEXTS = {
  pt: {
    nav: { settings: "Definições" },
    pageTitles: { settings: "Definições · Multistore AI" },
    st: {
      title: "Definições", sub: "Aparência e idioma da tua conta. Ficam guardados e seguem-te para qualquer computador.",
      appearance: "Aparência", themeHint: "Sistema segue o modo claro ou escuro do teu computador.",
      light: "Claro", dark: "Escuro", system: "Sistema",
      accent: "Cor de destaque", accentHint: "Botões, ligações, gráficos e o ícone do separador.",
      custom: "Personalizada", pickColor: "Escolher uma cor", adjusted: "Ajustámos ligeiramente o tom para o texto e os botões continuarem legíveis (contraste AA).",
      accents: { green: "Verde", orange: "Laranja", blue: "Azul", wine: "Vinho", purple: "Roxo", graphite: "Grafite" },
      preview: "Pré-visualização", previewBtn: "Botão", previewMsg: "Qual a faturação de ontem?",
      langHint: "As respostas do assistente também seguem este idioma.",
      reset: "Repor predefinições", resetDone: "Definições repostas.", saved: "Guardado.",
      defaultTag: "predefinição",
      appTitle: "Aplicação", appSub: "Só o admin vê esta parte. Vale para todas as contas que não escolheram outra coisa.",
      defAccent: "Cor por defeito", defLang: "Idioma por defeito", defLangHint: "Para quem ainda não escolheu um idioma.",
      demo: "Contas de demonstração", demoHint: "Mostra a tabela de contas na página inicial e no login. Desliga numa instalação real.",
      session: "Duração da sessão", sessionHint: "Depois disto é preciso entrar outra vez. Vale para os próximos logins.",
      hours: n => `${n} h`, save: "Guardar alterações", appSaved: "Definições da aplicação guardadas.",
      lastChange: (who, when) => `Última alteração: ${who} · ${when}`, never: "Ainda sem alterações (valores por defeito).",
      on: "Ligado", off: "Desligado",
    },
    errors: { admin_only: "Só o admin pode mudar isto.", bad_setting: "Valor inválido." },
    h: { closingNoDemo: "Pede uma conta a quem gere a aplicação." },
  },
  en: {
    nav: { settings: "Settings" },
    pageTitles: { settings: "Settings · Multistore AI" },
    st: {
      title: "Settings", sub: "Your account's appearance and language. Saved to your account, on any computer.",
      appearance: "Appearance", themeHint: "System follows your computer's light or dark mode.",
      light: "Light", dark: "Dark", system: "System",
      accent: "Accent colour", accentHint: "Buttons, links, charts and the tab icon.",
      custom: "Custom", pickColor: "Pick a colour", adjusted: "We adjusted the shade slightly so text and buttons stay readable (AA contrast).",
      accents: { green: "Green", orange: "Orange", blue: "Blue", wine: "Wine", purple: "Purple", graphite: "Graphite" },
      preview: "Preview", previewBtn: "Button", previewMsg: "What was yesterday's revenue?",
      langHint: "The assistant's answers follow this language too.",
      reset: "Reset to defaults", resetDone: "Settings reset.", saved: "Saved.",
      defaultTag: "default",
      appTitle: "Application", appSub: "Only the admin sees this part. It applies to every account that hasn't chosen otherwise.",
      defAccent: "Default colour", defLang: "Default language", defLangHint: "For anyone who hasn't picked a language yet.",
      demo: "Demo accounts", demoHint: "Shows the accounts table on the home page and the sign-in page. Turn off for a real install.",
      session: "Session length", sessionHint: "After this, people sign in again. Applies to new sign-ins.",
      hours: n => `${n} h`, save: "Save changes", appSaved: "Application settings saved.",
      lastChange: (who, when) => `Last change: ${who} · ${when}`, never: "No changes yet (default values).",
      on: "On", off: "Off",
    },
    errors: { admin_only: "Only the admin can change this.", bad_setting: "Invalid value." },
    h: { closingNoDemo: "Ask whoever runs the app for an account." },
  },
  es: {
    nav: { settings: "Ajustes" },
    pageTitles: { settings: "Ajustes · Multistore AI" },
    st: {
      title: "Ajustes", sub: "Apariencia e idioma de tu cuenta. Se guardan en tu cuenta, en cualquier ordenador.",
      appearance: "Apariencia", themeHint: "Sistema sigue el modo claro u oscuro de tu ordenador.",
      light: "Claro", dark: "Oscuro", system: "Sistema",
      accent: "Color de acento", accentHint: "Botones, enlaces, gráficos y el icono de la pestaña.",
      custom: "Personalizado", pickColor: "Elegir un color", adjusted: "Hemos ajustado un poco el tono para que el texto y los botones sigan siendo legibles (contraste AA).",
      accents: { green: "Verde", orange: "Naranja", blue: "Azul", wine: "Vino", purple: "Morado", graphite: "Grafito" },
      preview: "Vista previa", previewBtn: "Botón", previewMsg: "¿Cuánto se facturó ayer?",
      langHint: "Las respuestas del asistente también siguen este idioma.",
      reset: "Restablecer", resetDone: "Ajustes restablecidos.", saved: "Guardado.",
      defaultTag: "predeterminado",
      appTitle: "Aplicación", appSub: "Solo el admin ve esta parte. Vale para todas las cuentas que no han elegido otra cosa.",
      defAccent: "Color predeterminado", defLang: "Idioma predeterminado", defLangHint: "Para quien aún no ha elegido idioma.",
      demo: "Cuentas de demostración", demoHint: "Muestra la tabla de cuentas en la página de inicio y en el acceso. Desactívalo en una instalación real.",
      session: "Duración de la sesión", sessionHint: "Después hay que volver a entrar. Vale para los próximos accesos.",
      hours: n => `${n} h`, save: "Guardar cambios", appSaved: "Ajustes de la aplicación guardados.",
      lastChange: (who, when) => `Último cambio: ${who} · ${when}`, never: "Aún sin cambios (valores predeterminados).",
      on: "Activado", off: "Desactivado",
    },
    errors: { admin_only: "Solo el admin puede cambiar esto.", bad_setting: "Valor no válido." },
    h: { closingNoDemo: "Pide una cuenta a quien gestiona la aplicación." },
  },
  fr: {
    nav: { settings: "Paramètres" },
    pageTitles: { settings: "Paramètres · Multistore AI" },
    st: {
      title: "Paramètres", sub: "Apparence et langue de ton compte. Enregistrées sur ton compte, sur n'importe quel ordinateur.",
      appearance: "Apparence", themeHint: "Système suit le mode clair ou sombre de ton ordinateur.",
      light: "Clair", dark: "Sombre", system: "Système",
      accent: "Couleur d'accent", accentHint: "Boutons, liens, graphiques et l'icône de l'onglet.",
      custom: "Personnalisée", pickColor: "Choisir une couleur", adjusted: "Nous avons légèrement ajusté la teinte pour que le texte et les boutons restent lisibles (contraste AA).",
      accents: { green: "Vert", orange: "Orange", blue: "Bleu", wine: "Bordeaux", purple: "Violet", graphite: "Graphite" },
      preview: "Aperçu", previewBtn: "Bouton", previewMsg: "Quel a été le chiffre d'affaires d'hier ?",
      langHint: "Les réponses de l'assistant suivent aussi cette langue.",
      reset: "Rétablir les valeurs par défaut", resetDone: "Paramètres rétablis.", saved: "Enregistré.",
      defaultTag: "par défaut",
      appTitle: "Application", appSub: "Seul l'admin voit cette partie. Elle s'applique à tous les comptes qui n'ont rien choisi.",
      defAccent: "Couleur par défaut", defLang: "Langue par défaut", defLangHint: "Pour ceux qui n'ont pas encore choisi de langue.",
      demo: "Comptes de démonstration", demoHint: "Affiche le tableau des comptes sur l'accueil et la connexion. À désactiver pour une vraie installation.",
      session: "Durée de la session", sessionHint: "Ensuite, il faut se reconnecter. S'applique aux prochaines connexions.",
      hours: n => `${n} h`, save: "Enregistrer", appSaved: "Paramètres de l'application enregistrés.",
      lastChange: (who, when) => `Dernière modification : ${who} · ${when}`, never: "Aucune modification (valeurs par défaut).",
      on: "Activé", off: "Désactivé",
    },
    errors: { admin_only: "Seul l'admin peut modifier ceci.", bad_setting: "Valeur invalide." },
    h: { closingNoDemo: "Demande un compte à la personne qui gère l'application." },
  },
};

function installSettingsTexts(TEXTS) {
  const merge = (target, src) => {
    for (const [k, v] of Object.entries(src)) {
      if (v && typeof v === "object" && !Array.isArray(v) && typeof target[k] === "object") merge(target[k], v);
      else target[k] = v;
    }
  };
  for (const code of Object.keys(SETTINGS_TEXTS)) if (TEXTS[code]) merge(TEXTS[code], SETTINGS_TEXTS[code]);
}

const SettingsMixin = {
  data() {
    return { appForm: null, appMeta: null, appSaving: false };
  },
  computed: {
    accents() { return ACCENTS; },
    appDirty() {
      const f = this.appForm, v = this.appMeta?.values;
      return !!(f && v && Object.keys(f).some(k => f[k] !== v[k]));
    },
  },
  methods: {
    accentSwatch(a) { const [x, y] = accentColors(a); return { background: `linear-gradient(135deg, ${x}, ${y})` }; },
    isCustom(value) { return isCustomAccent(value); },
    customHex(value) { return isCustomAccent(value) ? value : (prefs.get("customAccent") || "#0f7a5a"); },
    customAdjusted(value) { return isCustomAccent(value) && customPalette(value).adjusted; },
    // Seletor nativo: enquanto arrasta só pré-visualiza; ao largar ("change") guarda na conta
    previewCustom(hex) { this.accent = hex.toLowerCase(); },
    saveCustom(hex) { hex = hex.toLowerCase(); prefs.set("customAccent", hex); this.setAccent(hex); },
    async loadAppSettings() {
      if (this.user?.role !== "admin") return;
      try {
        this.appMeta = await this.api("/settings/app");
        this.appForm = { ...this.appMeta.values };
      } catch (e) { this.toast(this.apiError(e)); }
    },
    async saveAppSettings() {
      const changes = Object.fromEntries(Object.entries(this.appForm).filter(([k, v]) => v !== this.appMeta.values[k]));
      if (!Object.keys(changes).length) return;
      this.appSaving = true;
      try {
        this.appMeta = await this.api("/settings/app", changes, "PUT");
        this.appForm = { ...this.appMeta.values };
        this.appConfig = { ...this.appConfig, default_accent: this.appForm.default_accent,
                           default_lang: this.appForm.default_lang, show_demo_accounts: this.appForm.show_demo_accounts };
        this.toast(this.t.st.appSaved, "ok");
      } catch (e) { this.toast(this.apiError(e)); }
      finally { this.appSaving = false; }
    },
    lastChangeText() {
      const m = this.appMeta;
      if (!m || !m.updated_at) return this.t.st.never;
      const when = this.dateFmt(m.updated_at) + " " +
        new Date(m.updated_at).toLocaleTimeString(LOCALES[this.lang], { hour: "2-digit", minute: "2-digit" });
      return m.updated_by ? this.t.st.lastChange(m.updated_by, when) : this.t.st.lastChange(when, "").replace(/ · $/, "");
    },
  },
};
