/* Rever 👎 (#/review, módulo "teach": admin e Imperador).
 *
 * Define REVIEW_TEXTS + installReviewTexts(TEXTS) e ReviewMixin (estado e ações,
 * juntos à aplicação principal como os outros mixins). O template está em pages/review.js.
 */
"use strict";

const REVIEW_TEXTS = {
  pt: {
    nav: { review: "Ensinar" },
    pageTitles: { review: "Ensinar o assistente · Multistore AI" },
    rv: {
      resetQuestion: "Repor a pergunta original", title: "Ensinar o assistente", sub: "Revê as respostas com 👎 e gere os exemplos que o assistente usa para escrever SQL.",
      tabs: { pending: "Para rever", examples: "Exemplos" },
      empty: "Nada para rever. Quando alguém der 👎 a uma resposta, ela aparece aqui.",
      pending: n => `${n} por rever`, more: (shown, n) => `A mostrar ${shown} de ${n}.`,
      asked: (u, when) => `${u} · ${when}`, answer: "Resposta dada", question: "Pergunta (como fica no exemplo)",
      sql: "SQL corrigido", noSql: "Esta resposta não tinha SQL (falhou). Escreve o SQL certo.",
      followUp: "Pergunta de seguimento: reescreve-a para fazer sentido sozinha (p.ex. \"E no Porto?\" → \"Faturação do Porto em outubro\").",
      error: "Erro", ml: "Resposta do modelo de previsão: não há SQL para corrigir.",
      test: "Testar", testing: "A testar…", teach: "Corrigir e ensinar", teaching: "A guardar…", dismiss: "Ignorar",
      rows: (n, shown) => n > shown ? `${n} linhas (primeiras ${shown})` : `${n} linha${n === 1 ? "" : "s"}`,
      testFirst: "Testa o SQL e confirma o resultado antes de ensinar.",
      taught: "Guardado nos exemplos. O assistente passa a usá-lo em perguntas parecidas.",
      dismissed: "Removido da lista.", dismissTitle: "Ignorar este 👎?",
      dismissText: "Sai da lista sem ensinar nada ao assistente.", refresh: "Atualizar",
    },
  },
  en: {
    nav: { review: "Teach" },
    pageTitles: { review: "Teach the assistant · Multistore AI" },
    rv: {
      resetQuestion: "Restore the original question", title: "Teach the assistant", sub: "Review answers rated 👎 and manage the examples the assistant uses to write SQL.",
      tabs: { pending: "To review", examples: "Examples" },
      empty: "Nothing to review. When someone rates an answer 👎, it shows up here.",
      pending: n => `${n} to review`, more: (shown, n) => `Showing ${shown} of ${n}.`,
      asked: (u, when) => `${u} · ${when}`, answer: "Answer given", question: "Question (as stored in the example)",
      sql: "Fixed SQL", noSql: "This answer had no SQL (it failed). Write the right SQL.",
      followUp: "Follow-up question: rewrite it so it makes sense on its own (e.g. \"And in Porto?\" → \"Revenue in Porto in October\").",
      error: "Error", ml: "Forecast model answer: there's no SQL to fix.",
      test: "Test", testing: "Testing…", teach: "Fix and teach", teaching: "Saving…", dismiss: "Dismiss",
      rows: (n, shown) => n > shown ? `${n} rows (first ${shown})` : `${n} row${n === 1 ? "" : "s"}`,
      testFirst: "Test the SQL and check the result before teaching.",
      taught: "Saved to the examples. The assistant will use it for similar questions.",
      dismissed: "Removed from the list.", dismissTitle: "Dismiss this 👎?",
      dismissText: "It leaves the list without teaching the assistant anything.", refresh: "Refresh",
    },
  },
  es: {
    nav: { review: "Enseñar" },
    pageTitles: { review: "Enseñar al asistente · Multistore AI" },
    rv: {
      resetQuestion: "Restaurar la pregunta original", title: "Enseñar al asistente", sub: "Revisa las respuestas con 👎 y gestiona los ejemplos que el asistente usa para escribir SQL.",
      tabs: { pending: "Por revisar", examples: "Ejemplos" },
      empty: "Nada que revisar. Cuando alguien dé 👎 a una respuesta, aparecerá aquí.",
      pending: n => `${n} por revisar`, more: (shown, n) => `Mostrando ${shown} de ${n}.`,
      asked: (u, when) => `${u} · ${when}`, answer: "Respuesta dada", question: "Pregunta (tal como queda en el ejemplo)",
      sql: "SQL corregido", noSql: "Esta respuesta no tenía SQL (falló). Escribe el SQL correcto.",
      followUp: "Pregunta de seguimiento: reescríbela para que tenga sentido por sí sola (p. ej. \"¿Y en Oporto?\" → \"Facturación de Oporto en octubre\").",
      error: "Error", ml: "Respuesta del modelo de previsión: no hay SQL que corregir.",
      test: "Probar", testing: "Probando…", teach: "Corregir y enseñar", teaching: "Guardando…", dismiss: "Ignorar",
      rows: (n, shown) => n > shown ? `${n} filas (primeras ${shown})` : `${n} fila${n === 1 ? "" : "s"}`,
      testFirst: "Prueba el SQL y comprueba el resultado antes de enseñar.",
      taught: "Guardado en los ejemplos. El asistente lo usará en preguntas parecidas.",
      dismissed: "Eliminado de la lista.", dismissTitle: "¿Ignorar este 👎?",
      dismissText: "Sale de la lista sin enseñar nada al asistente.", refresh: "Actualizar",
    },
  },
  fr: {
    nav: { review: "Entraîner" },
    pageTitles: { review: "Entraîner l'assistant · Multistore AI" },
    rv: {
      resetQuestion: "Rétablir la question d'origine", title: "Entraîner l'assistant", sub: "Revois les réponses notées 👎 et gère les exemples que l'assistant utilise pour écrire le SQL.",
      tabs: { pending: "À revoir", examples: "Exemples" },
      empty: "Rien à revoir. Quand quelqu'un note une réponse 👎, elle apparaît ici.",
      pending: n => `${n} à revoir`, more: (shown, n) => `${shown} affichées sur ${n}.`,
      asked: (u, when) => `${u} · ${when}`, answer: "Réponse donnée", question: "Question (telle qu'elle sera enregistrée)",
      sql: "SQL corrigé", noSql: "Cette réponse n'avait pas de SQL (elle a échoué). Écris le bon SQL.",
      followUp: "Question de suivi : reformule-la pour qu'elle se comprenne seule (p. ex. « Et à Porto ? » → « Chiffre d'affaires de Porto en octobre »).",
      error: "Erreur", ml: "Réponse du modèle de prévision : pas de SQL à corriger.",
      test: "Tester", testing: "Test…", teach: "Corriger et entraîner", teaching: "Enregistrement…", dismiss: "Ignorer",
      rows: (n, shown) => n > shown ? `${n} lignes (${shown} premières)` : `${n} ligne${n === 1 ? "" : "s"}`,
      testFirst: "Teste le SQL et vérifie le résultat avant d'entraîner.",
      taught: "Enregistré dans les exemples. L'assistant l'utilisera pour des questions similaires.",
      dismissed: "Retiré de la liste.", dismissTitle: "Ignorer ce 👎 ?",
      dismissText: "Il quitte la liste sans rien apprendre à l'assistant.", refresh: "Actualiser",
    },
  },
};

const EXAMPLES_TEXTS = {
  pt: { ex: {
    intro: "Quando alguém faz uma pergunta parecida, até 3 destes exemplos entram no prompt e ajudam o LLM a escrever o SQL certo. Servem todas as contas: um exemplo errado piora as respostas de toda a gente.",
    search: "Procurar na pergunta ou no SQL", all: "Todos", newBtn: "Novo exemplo", empty: "Nenhum exemplo com estes filtros.",
    sources: { seed: "Instalação", feedback: "Chat", review: "Revisão de 👎", manual: "Manual" },
    by: u => `por ${u}`, uses: n => n ? `usado ${n} ${n === 1 ? "vez" : "vezes"}` : "nunca usado", lastUse: d => `última: ${d}`,
    edited: (u, d) => `editado por ${u} · ${d}`, count: n => `${n} exemplo${n === 1 ? "" : "s"}`,
    showSql: "Ver SQL", hideSql: "Esconder SQL", edit: "Editar", del: "Apagar", save: "Guardar", cancel: "Cancelar",
    saving: "A guardar…", created: "Exemplo criado.", saved: "Exemplo guardado.", deleted: "Exemplo apagado.",
    delTitle: "Apagar este exemplo?", delText: "O assistente deixa de o usar. Não dá para desfazer.",
    neverHint: "Exemplos nunca usados podem ter uma pergunta pouco parecida com o que as pessoas perguntam.",
  } },
  en: { ex: {
    intro: "When someone asks a similar question, up to 3 of these examples go into the prompt and help the LLM write the right SQL. They serve every account: a wrong example makes everyone's answers worse.",
    search: "Search the question or the SQL", all: "All", newBtn: "New example", empty: "No examples match these filters.",
    sources: { seed: "Install", feedback: "Chat", review: "👎 review", manual: "Manual" },
    by: u => `by ${u}`, uses: n => n ? `used ${n} time${n === 1 ? "" : "s"}` : "never used", lastUse: d => `last: ${d}`,
    edited: (u, d) => `edited by ${u} · ${d}`, count: n => `${n} example${n === 1 ? "" : "s"}`,
    showSql: "Show SQL", hideSql: "Hide SQL", edit: "Edit", del: "Delete", save: "Save", cancel: "Cancel",
    saving: "Saving…", created: "Example created.", saved: "Example saved.", deleted: "Example deleted.",
    delTitle: "Delete this example?", delText: "The assistant stops using it. This can't be undone.",
    neverHint: "Examples that are never used may have a question unlike what people actually ask.",
  } },
  es: { ex: {
    intro: "Cuando alguien hace una pregunta parecida, hasta 3 de estos ejemplos entran en el prompt y ayudan al LLM a escribir el SQL correcto. Sirven a todas las cuentas: un ejemplo erróneo empeora las respuestas de todos.",
    search: "Buscar en la pregunta o en el SQL", all: "Todos", newBtn: "Nuevo ejemplo", empty: "Ningún ejemplo con estos filtros.",
    sources: { seed: "Instalación", feedback: "Chat", review: "Revisión de 👎", manual: "Manual" },
    by: u => `por ${u}`, uses: n => n ? `usado ${n} ${n === 1 ? "vez" : "veces"}` : "nunca usado", lastUse: d => `último: ${d}`,
    edited: (u, d) => `editado por ${u} · ${d}`, count: n => `${n} ejemplo${n === 1 ? "" : "s"}`,
    showSql: "Ver SQL", hideSql: "Ocultar SQL", edit: "Editar", del: "Eliminar", save: "Guardar", cancel: "Cancelar",
    saving: "Guardando…", created: "Ejemplo creado.", saved: "Ejemplo guardado.", deleted: "Ejemplo eliminado.",
    delTitle: "¿Eliminar este ejemplo?", delText: "El asistente deja de usarlo. No se puede deshacer.",
    neverHint: "Los ejemplos nunca usados pueden tener una pregunta poco parecida a lo que la gente pregunta.",
  } },
  fr: { ex: {
    intro: "Quand quelqu'un pose une question proche, jusqu'à 3 de ces exemples entrent dans le prompt et aident le LLM à écrire le bon SQL. Ils servent tous les comptes : un exemple faux dégrade les réponses de tout le monde.",
    search: "Chercher dans la question ou le SQL", all: "Tous", newBtn: "Nouvel exemple", empty: "Aucun exemple avec ces filtres.",
    sources: { seed: "Installation", feedback: "Chat", review: "Revue des 👎", manual: "Manuel" },
    by: u => `par ${u}`, uses: n => n ? `utilisé ${n} fois` : "jamais utilisé", lastUse: d => `dernier : ${d}`,
    edited: (u, d) => `modifié par ${u} · ${d}`, count: n => `${n} exemple${n === 1 ? "" : "s"}`,
    showSql: "Voir le SQL", hideSql: "Masquer le SQL", edit: "Modifier", del: "Supprimer", save: "Enregistrer", cancel: "Annuler",
    saving: "Enregistrement…", created: "Exemple créé.", saved: "Exemple enregistré.", deleted: "Exemple supprimé.",
    delTitle: "Supprimer cet exemple ?", delText: "L'assistant ne l'utilisera plus. Action irréversible.",
    neverHint: "Un exemple jamais utilisé a peut-être une question éloignée de ce que les gens demandent.",
  } },
};

function installReviewTexts(TEXTS) {
  const merge = (target, src) => {
    for (const [k, v] of Object.entries(src)) {
      if (v && typeof v === "object" && !Array.isArray(v) && typeof target[k] === "object") merge(target[k], v);
      else target[k] = v;
    }
  };
  for (const code of Object.keys(REVIEW_TEXTS)) if (TEXTS[code]) merge(TEXTS[code], REVIEW_TEXTS[code]);
  for (const code of Object.keys(EXAMPLES_TEXTS)) if (TEXTS[code]) merge(TEXTS[code], EXAMPLES_TEXTS[code]);
}

const ReviewMixin = {
  data() {
    return {
      rv: { items: [], pending: 0, loading: false, error: "", tab: "pending" },
      ex: { items: [], loading: false, error: "", q: "", source: "", editId: null, form: null },
    };
  },
  computed: {
    exSources() { return ["seed", "feedback", "review", "manual"]; },
    exFiltered() {
      const q = this.ex.q.trim().toLowerCase();
      return this.ex.items.filter(e => (!this.ex.source || e.source === this.ex.source)
        && (!q || e.question.toLowerCase().includes(q) || e.sql.toLowerCase().includes(q)));
    },
  },
  methods: {
    // Só o número (barra lateral): não falha nem mostra erros
    async loadReviewCount() {
      if (!this.hasModule("teach")) { this.rv.pending = 0; return; }
      try { this.rv.pending = (await this.api("/review")).pending; } catch {}
    },
    async loadReview() {
      this.rv.loading = true; this.rv.error = "";
      try {
        const d = await this.api("/review");
        this.rv.pending = d.pending;
        this.rv.items = d.items.map(i => ({
          ...i, draftQuestion: i.question, draftSql: i.sql || "", preview: null, testedSql: null,
          busy: "", err: "",
        }));
      } catch (e) { this.rv.error = this.apiError(e); }
      finally { this.rv.loading = false; }
    },
    reviewWhen(iso) {
      return new Date(iso).toLocaleString(this.lang === "en" ? "en-GB" : this.lang, { dateStyle: "short", timeStyle: "short" });
    },
    // Ensinar só depois de testar exatamente este SQL
    reviewTested(i) { return i.preview && i.testedSql === i.draftSql.trim(); },
    async reviewTest(i) {
      i.busy = "test"; i.err = "";
      try {
        i.preview = await this.api(`/review/${i.id}/preview`, { sql: i.draftSql });
        i.testedSql = i.draftSql.trim();
      } catch (e) { i.preview = null; i.err = this.apiError(e); }
      finally { i.busy = ""; }
    },
    async reviewTeach(i) {
      i.busy = "teach"; i.err = "";
      try {
        await this.api(`/review/${i.id}/teach`, { question: i.draftQuestion, sql: i.draftSql });
        this.reviewDone(i);
        this.toast(this.t.rv.taught, "ok");
      } catch (e) { i.err = this.apiError(e); if (e.status === 404) this.reviewDone(i); }
      finally { i.busy = ""; }
    },
    async reviewDismiss(i) {
      const ok = await this.confirmDialog({ title: this.t.rv.dismissTitle, subject: i.question,
                                            text: this.t.rv.dismissText, confirm: this.t.rv.dismiss });
      if (!ok) return;
      i.busy = "dismiss";
      try { await this.api(`/review/${i.id}/dismiss`, {}); this.reviewDone(i); this.toast(this.t.rv.dismissed, "ok"); }
      catch (e) { i.err = this.apiError(e); if (e.status === 404) this.reviewDone(i); }
      finally { i.busy = ""; }
    },
    setReviewTab(tab) {
      this.rv.tab = tab;
      if (tab === "examples") this.loadExamples(); else this.loadReview();
    },
    reloadTeach() { if (this.rv.tab === "examples") this.loadExamples(); else this.loadReview(); },

    // ----- Exemplos do RAG -----
    async loadExamples() {
      this.ex.loading = true; this.ex.error = "";
      try { this.ex.items = (await this.api("/examples")).examples.map(e => ({ ...e, open: false })); }
      catch (e) { this.ex.error = this.apiError(e); }
      finally { this.ex.loading = false; }
    },
    exStartNew() { this.ex.editId = "new"; this.ex.form = this.exBlankForm("", ""); },
    exStartEdit(e) { this.ex.editId = e.id; this.ex.form = this.exBlankForm(e.question, e.sql); },
    exCancel() { this.ex.editId = null; this.ex.form = null; },
    exBlankForm(question, sql) { return { question, sql, preview: null, testedSql: null, busy: "", err: "" }; },
    exTested() { const f = this.ex.form; return f && f.preview && f.testedSql === f.sql.trim(); },
    async exTest() {
      const f = this.ex.form; f.busy = "test"; f.err = "";
      try { f.preview = await this.api("/examples/preview", { sql: f.sql }); f.testedSql = f.sql.trim(); }
      catch (e) { f.preview = null; f.err = this.apiError(e); }
      finally { f.busy = ""; }
    },
    async exSave() {
      const f = this.ex.form, isNew = this.ex.editId === "new"; f.busy = "save"; f.err = "";
      try {
        const body = { question: f.question, sql: f.sql };
        if (isNew) await this.api("/examples", body); else await this.api(`/examples/${this.ex.editId}`, body, "PUT");
        this.exCancel(); this.toast(isNew ? this.t.ex.created : this.t.ex.saved, "ok"); this.loadExamples();
      } catch (e) { f.err = this.apiError(e); }
      finally { if (this.ex.form) this.ex.form.busy = ""; }
    },
    async exDelete(e) {
      const ok = await this.confirmDialog({ title: this.t.ex.delTitle, subject: e.question, text: this.t.ex.delText,
                                            confirm: this.t.ex.del, danger: true });
      if (!ok) return;
      try {
        await this.api(`/examples/${e.id}`, null, "DELETE");
        this.ex.items = this.ex.items.filter(x => x.id !== e.id); this.toast(this.t.ex.deleted, "ok");
      } catch (err) { this.toast(this.apiError(err)); }
    },
    exDate(iso) { return iso ? this.reviewWhen(iso) : ""; },

    reviewDone(i) {
      this.rv.items = this.rv.items.filter(x => x.id !== i.id);
      this.rv.pending = Math.max(0, this.rv.pending - 1);
    },
  },
};
