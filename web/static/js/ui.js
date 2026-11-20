/* Componentes partilhados: seletor de idioma com bandeiras, avatar (foto ou iniciais)
 * e os textos da página inicial / login.
 *
 * Carregado antes do script principal do index.html (como o admin.js).
 * As bandeiras e os logótipos são símbolos SVG do sprite no topo do <body>.
 */
"use strict";

const LANGS = [
  { code: "pt", name: "Português", flag: "pt" },
  { code: "en", name: "English", flag: "gb" },
  { code: "fr", name: "Français", flag: "fr" },
  { code: "es", name: "Español", flag: "es" },
];

let langPickerSeq = 0;

/** Seletor de idioma com bandeiras (listbox acessível: setas, Enter, Esc, Home/End). */
const LangPicker = {
  props: { modelValue: { type: String, required: true }, label: { type: String, default: "Language" },
           compact: Boolean, up: Boolean },
  emits: ["update:modelValue"],
  data() { return { open: false, active: 0, uid: ++langPickerSeq }; },
  computed: {
    langs() { return LANGS; },
    current() { return LANGS.find(l => l.code === this.modelValue) || LANGS[0]; },
  },
  template: `
    <div class="lang-picker" :class="{ open: open, up: up }">
      <button type="button" class="lp-btn" ref="btn" @click.stop="toggle" @keydown.down.prevent="openMenu"
              aria-haspopup="listbox" :aria-expanded="open ? 'true' : 'false'"
              :aria-label="label + ': ' + current.name" :title="label">
        <span class="flag" aria-hidden="true"><svg viewBox="0 0 30 20"><use :href="'#flag-' + current.flag"/></svg></span>
        <span class="lp-name">{{ compact ? current.code.toUpperCase() : current.name }}</span>
        <svg class="i lp-chev" aria-hidden="true"><use href="#i-chevron"/></svg>
      </button>
      <ul v-if="open" class="lp-menu" role="listbox" ref="menu" tabindex="-1" :aria-label="label"
          :aria-activedescendant="'lp-' + uid + '-' + active" @keydown="onKey" @click.stop>
        <li v-for="(l, i) in langs" :key="l.code" :id="'lp-' + uid + '-' + i" role="option"
            :aria-selected="l.code === modelValue ? 'true' : 'false'" :class="{ active: i === active }"
            @mousemove="active = i" @click="pick(l.code)">
          <span class="flag" aria-hidden="true"><svg viewBox="0 0 30 20"><use :href="'#flag-' + l.flag"/></svg></span>
          <span>{{ compact ? l.code.toUpperCase() : l.name }}</span>
          <svg v-if="l.code === modelValue" class="i lp-check" aria-hidden="true"><use href="#i-check"/></svg>
        </li>
      </ul>
    </div>`,
  mounted() { document.addEventListener("click", this.close); },
  unmounted() { document.removeEventListener("click", this.close); },
  methods: {
    toggle() { this.open ? this.close() : this.openMenu(); },
    openMenu() {
      this.active = Math.max(0, LANGS.findIndex(l => l.code === this.modelValue));
      this.open = true;
      this.$nextTick(() => this.$refs.menu?.focus());
    },
    close() { this.open = false; },
    pick(code) {
      this.$emit("update:modelValue", code);
      this.open = false;
      this.$nextTick(() => this.$refs.btn?.focus());
    },
    onKey(e) {
      const n = LANGS.length;
      if (e.key === "ArrowDown") { e.preventDefault(); this.active = (this.active + 1) % n; }
      else if (e.key === "ArrowUp") { e.preventDefault(); this.active = (this.active - 1 + n) % n; }
      else if (e.key === "Home") { e.preventDefault(); this.active = 0; }
      else if (e.key === "End") { e.preventDefault(); this.active = n - 1; }
      else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.pick(LANGS[this.active].code); }
      else if (e.key === "Escape" || e.key === "Tab") { this.open = false; if (e.key === "Escape") this.$refs.btn?.focus(); }
    },
  },
};

// ---------- Avatar ----------
// Fundo das iniciais: todas estas cores têm contraste ≥ 4.5:1 com texto branco
const AVATAR_COLORS = ["#B42318", "#B54708", "#027A48", "#0E7090", "#175CD3",
                       "#5925DC", "#C11574", "#4E5BA6", "#475467", "#93370D"];
const AVATAR_TYPES = ["image/png", "image/jpeg", "image/webp"];
const AVATAR_MAX_BYTES = 2 * 1024 * 1024;    // o mesmo limite do servidor

/** Cor fixa de cada conta: hash FNV-1a do username → uma das AVATAR_COLORS. */
function avatarColor(name) {
  let h = 0x811c9dc5;
  for (const ch of name || "") { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193); }
  return AVATAR_COLORS[(h >>> 0) % AVATAR_COLORS.length];
}

/** "gerente.maia" → "GM"; "pedro" → "P". */
function avatarInitials(name) {
  return (name || "").split(/[.\s_-]+/).filter(Boolean).map(p => p[0]).join("").slice(0, 2).toUpperCase() || "?";
}

// Fotos já descarregadas (URL com ?v= → Promise<data URL>): cada uma é pedida uma vez.
// As fotos só são servidas com o token, e um <img src> não o envia: pede-se com fetch e
// mostra-se como data URL (a CSP só permite img-src 'self' data:, não blob:).
const avatarCache = new Map();
function loadAvatar(url, token) {
  if (!avatarCache.has(url)) {
    const p = fetch(url, { headers: { Authorization: "Bearer " + token } })
      .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.blob(); })
      .then(blob => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      }));
    p.catch(() => avatarCache.delete(url));      // falhou: tenta outra vez da próxima
    avatarCache.set(url, p);
  }
  return avatarCache.get(url);
}

/** Foto de perfil; sem foto (ou enquanto carrega), as iniciais num círculo da cor da conta. */
const UserAvatar = {
  props: { user: Object, size: { type: Number, default: 32 } },
  data() { return { src: null }; },
  computed: {
    initials() { return avatarInitials(this.user?.username); },
    style() {
      return { width: this.size + "px", height: this.size + "px", fontSize: Math.round(this.size * 0.4) + "px",
               background: this.src ? null : avatarColor(this.user?.username) };
    },
  },
  watch: { "user.avatar_url": { immediate: true, handler: "load" } },
  methods: {
    async load(url) {
      const token = this.$root.token;
      if (!url || !token) { this.src = null; return; }
      try {
        const data = await loadAvatar(url, token);
        if (this.user?.avatar_url === url) this.src = data;      // ainda é a mesma foto?
      } catch { if (this.user?.avatar_url === url) this.src = null; }
    },
  },
  template: `
    <span class="uavatar" :class="{ initials: !src }" :style="style" aria-hidden="true">
      <img v-if="src" :src="src" alt=""><template v-else>{{ initials }}</template>
    </span>`,
};

const UI_TEXTS = {
  pt: {
    h: {
      eyebrow: "Projeto de portefólio · dados fictícios",
      proof: ["97,5 % de acerto nas 40 perguntas de teste", "886 testes automáticos", "Dados fictícios, código no GitHub"],
      tourTitle: "Vê-o a funcionar",
      tourSub: "Capturas da aplicação, com os dados fictícios do grupo.",
      tour: [{"kicker": "Perguntas aos dados", "title": "O número, o gráfico e o SQL que o produziu", "text": "A resposta vem em linguagem simples, com gráfico e tabela automáticos. A tabela exporta para CSV e o SQL fica à vista em «Fonte», para conferires.", "points": ["Gráfico e tabela automáticos", "Exportação CSV", "Perguntas de seguimento: «e em setembro?»"], "img": "tour-chat", "w": 1000, "h": 814, "alt": "Resposta com a faturação de cada marca em outubro de 2026, com gráfico de barras e tabela"}, {"kicker": "Permissões", "title": "Cada perfil vê só as suas lojas", "text": "O gerente da BurgerLab Maia faz a mesma pergunta que o Imperador e recebe uma linha: a da sua loja. Repara que o SQL não filtra a loja: quem filtra é a base de dados.", "points": ["Row Level Security do PostgreSQL com contexto assinado (HMAC)", "Mudar o perfil dentro do SQL devolve 0 linhas", "NIF, NISS e moradas nunca chegam ao modelo"], "img": "tour-rls", "w": 1000, "h": 346, "alt": "Resposta do gerente de loja: só a BurgerLab Maia, com o SQL usado visível"}, {"kicker": "Previsão", "title": "Quanto vais vender na próxima semana", "text": "Um modelo de gradient boosting prevê a faturação dia a dia e sugere que ingredientes encomendar, só para as lojas que o perfil vê. Corre localmente, sem LLM.", "points": ["Erro médio de 102,28 € por dia (145,94 € com a semana anterior)", "Encomendas calculadas a partir das receitas", "Respeita as mesmas permissões"], "img": "tour-forecast", "w": 1000, "h": 544, "alt": "Previsão de faturação para os próximos 7 dias em gráfico de linha"}],
      alsoTitle: "E ainda",
      also: [{"icon": "history", "title": "Memória de conversa", "text": "As últimas trocas vão para o modelo, por isso «só MB Way» ou «e no Porto?» funcionam."}, {"icon": "globe", "title": "Quatro idiomas", "text": "Português, inglês, espanhol e francês, seja qual for o idioma da pergunta."}, {"icon": "users", "title": "Contas e módulos", "text": "Cada perfil cria contas do seu nível ou abaixo e escolhe que módulos dá."}, {"icon": "chart", "title": "Observabilidade", "text": "Latência, erros, tokens, 👍/👎 e o histórico da avaliação num painel só para o admin."}],
      ex: {"title": "Exemplo real", "question": "pergunta", "intent": "intenção", "sql": "SQL", "checks": "validação", "rls": "RLS", "answer": "resposta", "q": "Qual a faturação de cada marca em outubro de 2026?", "intentText": "dados · confiança 1,00 · XLM-RoBERTa (local, ~60 ms)", "checksText": "um só SELECT · sem escrita, funções perigosas ou tabelas privadas", "rlsText": "perfil imperador · contexto assinado com HMAC", "answerText": "A BurgerLab faturou 272 498,70 €, a Café Aroma 56 466,80 € e a Gelato Mar 40 720,40 €."},
      closingSub: "Sem instalar nada: escolhe uma conta e faz a primeira pergunta.",
      title: "Os números do grupo, a uma pergunta de distância.",
      lead: "Os gestores da BurgerLab, do Café Aroma e da Gelato Mar perguntam em linguagem normal e recebem o número, um gráfico e o SQL que o produziu. Cada perfil só vê as lojas a que tem acesso.",
      builtWith: "Feito com", github: "Código no GitHub",
      featTitle: "O que faz", featSub: "Vendas, lojas, produtos, menus, stock, compras e equipas de 3 marcas e 15 lojas.",
      howTitle: "Como uma pergunta é respondida", howSub: "Cada passo tem a sua verificação. Se um falhar, os outros continuam a proteger os dados.",
      rolesTitle: "Contas de demonstração", rolesSub: "As permissões estão na base de dados (Row Level Security), não no prompt. Faz a mesma pergunta com as três contas.",
      cols: { role: "Perfil", account: "Conta", password: "Palavra-passe", sees: "Vê" }, use: "Usar",
      closing: "Experimenta com uma conta de demonstração.",
    },
    l: { title: "Entrar", demoHint: "Clica numa conta para preencher." },
    avatar: { change: "Alterar foto", remove: "Remover foto", saved: "Foto atualizada.", removed: "Foto removida.",
              saving: "A enviar…", hint: "PNG, JPG ou WebP até 2 MB. É recortada num quadrado.",
              bad: "Escolhe uma imagem PNG, JPG ou WebP com menos de 2 MB.",
              fallback: "Sem foto, aparecem as tuas iniciais. PNG, JPG ou WebP até 2 MB." },
  },
  en: {
    h: {
      eyebrow: "Portfolio project · fictional data",
      proof: ["97.5 % right on the 40 test questions", "886 automated tests", "Fictional data, code on GitHub"],
      tourTitle: "See it working",
      tourSub: "Screenshots of the app, with the group's fictional data.",
      tour: [{"kicker": "Data questions", "title": "The number, the chart and the SQL behind it", "text": "The answer comes in plain language, with an automatic chart and table. The table exports to CSV and the SQL is shown under “Source”, so you can check it.", "points": ["Automatic chart and table", "CSV export", "Follow-ups: “and in September?”"], "img": "tour-chat", "w": 1000, "h": 814, "alt": "Answer with each brand's revenue in October 2026, with a bar chart and a table"}, {"kicker": "Permissions", "title": "Each role only sees its own stores", "text": "The BurgerLab Maia manager asks the same question as the Emperor and gets one row: their store. Note the SQL doesn't filter the store: the database does.", "points": ["PostgreSQL Row Level Security with a signed (HMAC) context", "Changing the role inside the SQL returns 0 rows", "Tax numbers and addresses never reach the model"], "img": "tour-rls", "w": 1000, "h": 346, "alt": "Store manager's answer: only BurgerLab Maia, with the SQL shown"}, {"kicker": "Forecast", "title": "How much you'll sell next week", "text": "A gradient boosting model forecasts daily revenue and suggests which ingredients to order, only for the stores the role can see. It runs locally, no LLM.", "points": ["Average error of €102.28 a day (€145.94 using last week)", "Orders computed from the recipes", "Same permissions apply"], "img": "tour-forecast", "w": 1000, "h": 544, "alt": "Revenue forecast for the next 7 days as a line chart"}],
      alsoTitle: "And also",
      also: [{"icon": "history", "title": "Conversation memory", "text": "Recent turns go to the model, so “only MB Way” or “and in Porto?” work."}, {"icon": "globe", "title": "Four languages", "text": "Portuguese, English, Spanish and French, whatever language the question is in."}, {"icon": "users", "title": "Accounts and modules", "text": "Each role creates accounts at its level or below and picks which modules to grant."}, {"icon": "chart", "title": "Observability", "text": "Latency, errors, tokens, 👍/👎 and the evaluation history on an admin-only dashboard."}],
      ex: {"title": "Real example", "question": "question", "intent": "intent", "sql": "SQL", "checks": "validation", "rls": "RLS", "answer": "answer", "q": "What was each brand's revenue in October 2026?", "intentText": "data · confidence 1.00 · XLM-RoBERTa (local, ~60 ms)", "checksText": "a single SELECT · no writes, dangerous functions or private tables", "rlsText": "emperor role · HMAC-signed context", "answerText": "BurgerLab made €272,498.70, Café Aroma €56,466.80 and Gelato Mar €40,720.40."},
      closingSub: "Nothing to install: pick an account and ask your first question.",
      title: "Your group's numbers, one question away.",
      lead: "Managers at BurgerLab, Café Aroma and Gelato Mar ask in plain language and get the number, a chart and the SQL that produced it. Each role only sees the stores it has access to.",
      builtWith: "Built with", github: "Code on GitHub",
      featTitle: "What it does", featSub: "Sales, stores, products, menus, stock, purchases and staff for 3 brands and 15 stores.",
      howTitle: "How a question gets answered", howSub: "Every step has its own check. If one fails, the others still protect the data.",
      rolesTitle: "Demo accounts", rolesSub: "Permissions live in the database (Row Level Security), not in the prompt. Ask the same question with all three.",
      cols: { role: "Role", account: "Account", password: "Password", sees: "Sees" }, use: "Use",
      closing: "Try it with a demo account.",
    },
    l: { title: "Sign in", demoHint: "Click an account to fill it in." },
    avatar: { change: "Change photo", remove: "Remove photo", saved: "Photo updated.", removed: "Photo removed.",
              saving: "Uploading…", hint: "PNG, JPG or WebP up to 2 MB. It's cropped to a square.",
              bad: "Choose a PNG, JPG or WebP image under 2 MB.",
              fallback: "Without a photo, your initials are shown. PNG, JPG or WebP up to 2 MB." },
  },
  es: {
    h: {
      eyebrow: "Proyecto de portfolio · datos ficticios",
      proof: ["97,5 % de acierto en las 40 preguntas de prueba", "886 tests automáticos", "Datos ficticios, código en GitHub"],
      tourTitle: "Míralo funcionar",
      tourSub: "Capturas de la aplicación, con los datos ficticios del grupo.",
      tour: [{"kicker": "Preguntas sobre los datos", "title": "La cifra, el gráfico y el SQL que la generó", "text": "La respuesta llega en lenguaje sencillo, con gráfico y tabla automáticos. La tabla se exporta a CSV y el SQL queda a la vista en «Fuente», para comprobarlo.", "points": ["Gráfico y tabla automáticos", "Exportación CSV", "Preguntas de seguimiento: «¿y en septiembre?»"], "img": "tour-chat", "w": 1000, "h": 814, "alt": "Respuesta con la facturación de cada marca en octubre de 2026, con gráfico de barras y tabla"}, {"kicker": "Permisos", "title": "Cada perfil solo ve sus tiendas", "text": "El gerente de BurgerLab Maia hace la misma pregunta que el Emperador y recibe una fila: la de su tienda. El SQL no filtra la tienda: lo hace la base de datos.", "points": ["Row Level Security de PostgreSQL con contexto firmado (HMAC)", "Cambiar el perfil dentro del SQL devuelve 0 filas", "NIF, NISS y direcciones nunca llegan al modelo"], "img": "tour-rls", "w": 1000, "h": 346, "alt": "Respuesta del gerente de tienda: solo BurgerLab Maia, con el SQL visible"}, {"kicker": "Previsión", "title": "Cuánto venderás la próxima semana", "text": "Un modelo de gradient boosting prevé la facturación día a día y sugiere qué ingredientes pedir, solo para las tiendas que ve el perfil. Se ejecuta en local, sin LLM.", "points": ["Error medio de 102,28 € al día (145,94 € con la semana anterior)", "Pedidos calculados a partir de las recetas", "Respeta los mismos permisos"], "img": "tour-forecast", "w": 1000, "h": 544, "alt": "Previsión de facturación de los próximos 7 días en un gráfico de líneas"}],
      alsoTitle: "Y además",
      also: [{"icon": "history", "title": "Memoria de conversación", "text": "Los últimos turnos van al modelo, así que «solo MB Way» o «¿y en Oporto?» funcionan."}, {"icon": "globe", "title": "Cuatro idiomas", "text": "Portugués, inglés, español y francés, sea cual sea el idioma de la pregunta."}, {"icon": "users", "title": "Cuentas y módulos", "text": "Cada perfil crea cuentas de su nivel o inferior y elige qué módulos da."}, {"icon": "chart", "title": "Observabilidad", "text": "Latencia, errores, tokens, 👍/👎 y el historial de evaluación en un panel solo para el admin."}],
      ex: {"title": "Ejemplo real", "question": "pregunta", "intent": "intención", "sql": "SQL", "checks": "validación", "rls": "RLS", "answer": "respuesta", "q": "¿Cuál fue la facturación de cada marca en octubre de 2026?", "intentText": "datos · confianza 1,00 · XLM-RoBERTa (local, ~60 ms)", "checksText": "un solo SELECT · sin escritura, funciones peligrosas ni tablas privadas", "rlsText": "perfil emperador · contexto firmado con HMAC", "answerText": "BurgerLab facturó 272 498,70 €, Café Aroma 56 466,80 € y Gelato Mar 40 720,40 €."},
      closingSub: "Sin instalar nada: elige una cuenta y haz la primera pregunta.",
      title: "Las cifras del grupo, a una pregunta de distancia.",
      lead: "Los gestores de BurgerLab, Café Aroma y Gelato Mar preguntan con sus palabras y reciben la cifra, un gráfico y el SQL que la generó. Cada perfil solo ve las tiendas a las que tiene acceso.",
      builtWith: "Hecho con", github: "Código en GitHub",
      featTitle: "Qué hace", featSub: "Ventas, tiendas, productos, menús, stock, compras y equipos de 3 marcas y 15 tiendas.",
      howTitle: "Cómo se responde una pregunta", howSub: "Cada paso tiene su control. Si uno falla, los demás siguen protegiendo los datos.",
      rolesTitle: "Cuentas de demostración", rolesSub: "Los permisos están en la base de datos (Row Level Security), no en el prompt. Haz la misma pregunta con las tres.",
      cols: { role: "Perfil", account: "Cuenta", password: "Contraseña", sees: "Ve" }, use: "Usar",
      closing: "Pruébalo con una cuenta de demostración.",
    },
    l: { title: "Entrar", demoHint: "Haz clic en una cuenta para rellenarla." },
    avatar: { change: "Cambiar foto", remove: "Quitar foto", saved: "Foto actualizada.", removed: "Foto eliminada.",
              saving: "Subiendo…", hint: "PNG, JPG o WebP de hasta 2 MB. Se recorta en un cuadrado.",
              bad: "Elige una imagen PNG, JPG o WebP de menos de 2 MB.",
              fallback: "Sin foto, se muestran tus iniciales. PNG, JPG o WebP de hasta 2 MB." },
  },
  fr: {
    h: {
      eyebrow: "Projet de portfolio · données fictives",
      proof: ["97,5 % de bonnes réponses sur 40 questions de test", "886 tests automatisés", "Données fictives, code sur GitHub"],
      tourTitle: "Voir l'outil en action",
      tourSub: "Captures de l'application, avec les données fictives du groupe.",
      tour: [{"kicker": "Questions sur les données", "title": "Le chiffre, le graphique et le SQL qui l'a produit", "text": "La réponse arrive en langage simple, avec graphique et tableau automatiques. Le tableau s'exporte en CSV et le SQL est visible dans « Source », pour vérifier.", "points": ["Graphique et tableau automatiques", "Export CSV", "Questions de suivi : « et en septembre ? »"], "img": "tour-chat", "w": 1000, "h": 814, "alt": "Réponse avec le chiffre d'affaires de chaque marque en octobre 2026, graphique en barres et tableau"}, {"kicker": "Permissions", "title": "Chaque profil ne voit que ses magasins", "text": "Le gérant de BurgerLab Maia pose la même question que l'Empereur et obtient une ligne : son magasin. Le SQL ne filtre pas le magasin : c'est la base de données qui le fait.", "points": ["Row Level Security PostgreSQL avec contexte signé (HMAC)", "Changer de profil dans le SQL renvoie 0 ligne", "NIF, NISS et adresses n'arrivent jamais au modèle"], "img": "tour-rls", "w": 1000, "h": 346, "alt": "Réponse du gérant de magasin : seulement BurgerLab Maia, avec le SQL visible"}, {"kicker": "Prévision", "title": "Combien tu vendras la semaine prochaine", "text": "Un modèle de gradient boosting prévoit le chiffre d'affaires jour par jour et suggère les ingrédients à commander, seulement pour les magasins du profil. Il tourne en local, sans LLM.", "points": ["Erreur moyenne de 102,28 € par jour (145,94 € avec la semaine précédente)", "Commandes calculées à partir des recettes", "Mêmes permissions"], "img": "tour-forecast", "w": 1000, "h": 544, "alt": "Prévision du chiffre d'affaires des 7 prochains jours en courbe"}],
      alsoTitle: "Et aussi",
      also: [{"icon": "history", "title": "Mémoire de conversation", "text": "Les derniers échanges vont au modèle : « seulement MB Way » ou « et à Porto ? » fonctionnent."}, {"icon": "globe", "title": "Quatre langues", "text": "Portugais, anglais, espagnol et français, quelle que soit la langue de la question."}, {"icon": "users", "title": "Comptes et modules", "text": "Chaque profil crée des comptes de son niveau ou inférieur et choisit les modules."}, {"icon": "chart", "title": "Observabilité", "text": "Latence, erreurs, tokens, 👍/👎 et l'historique d'évaluation dans un tableau réservé à l'admin."}],
      ex: {"title": "Exemple réel", "question": "question", "intent": "intention", "sql": "SQL", "checks": "validation", "rls": "RLS", "answer": "réponse", "q": "Quel a été le chiffre d'affaires de chaque marque en octobre 2026 ?", "intentText": "données · confiance 1,00 · XLM-RoBERTa (local, ~60 ms)", "checksText": "un seul SELECT · ni écriture, ni fonctions dangereuses, ni tables privées", "rlsText": "profil empereur · contexte signé HMAC", "answerText": "BurgerLab a fait 272 498,70 €, Café Aroma 56 466,80 € et Gelato Mar 40 720,40 €."},
      closingSub: "Rien à installer : choisis un compte et pose ta première question.",
      title: "Les chiffres du groupe, à une question près.",
      lead: "Les responsables de BurgerLab, Café Aroma et Gelato Mar posent leurs questions simplement et reçoivent le chiffre, un graphique et le SQL qui l'a produit. Chaque profil ne voit que ses magasins.",
      builtWith: "Réalisé avec", github: "Code sur GitHub",
      featTitle: "Ce qu'il fait", featSub: "Ventes, magasins, produits, menus, stock, achats et équipes de 3 marques et 15 magasins.",
      howTitle: "Comment une question obtient sa réponse", howSub: "Chaque étape a son contrôle. Si l'une échoue, les autres protègent toujours les données.",
      rolesTitle: "Comptes de démonstration", rolesSub: "Les permissions sont dans la base de données (Row Level Security), pas dans le prompt. Pose la même question avec les trois.",
      cols: { role: "Profil", account: "Compte", password: "Mot de passe", sees: "Voit" }, use: "Utiliser",
      closing: "Essaie avec un compte de démonstration.",
    },
    l: { title: "Connexion", demoHint: "Clique sur un compte pour le remplir." },
    avatar: { change: "Changer la photo", remove: "Supprimer la photo", saved: "Photo mise à jour.", removed: "Photo supprimée.",
              saving: "Envoi…", hint: "PNG, JPG ou WebP jusqu'à 2 Mo. Elle est recadrée en carré.",
              bad: "Choisis une image PNG, JPG ou WebP de moins de 2 Mo.",
              fallback: "Sans photo, tes initiales s'affichent. PNG, JPG ou WebP jusqu'à 2 Mo." },
  },
};

function installUiTexts(TEXTS) {
  const merge = (target, src) => {
    for (const [k, v] of Object.entries(src)) {
      if (v && typeof v === "object" && !Array.isArray(v) && typeof target[k] === "object") merge(target[k], v);
      else target[k] = v;
    }
  };
  for (const code of Object.keys(UI_TEXTS)) if (TEXTS[code]) merge(TEXTS[code], UI_TEXTS[code]);
}
