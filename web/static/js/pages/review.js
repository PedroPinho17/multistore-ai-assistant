/* Ensinar (#/review): rever 👎 (corrigir o SQL, testar, ensinar ou ignorar) e gerir os exemplos do RAG */
"use strict";

const ReviewPage = {
  name: "review-page",
  template: String.raw`
    <main class="page">
      <div class="tabs" role="tablist" :aria-label="t.rv.title">
        <button type="button" role="tab" :aria-selected="rv.tab === 'pending' ? 'true' : 'false'" @click="setReviewTab('pending')">
          {{ t.rv.tabs.pending }} <span v-if="rv.pending" class="nav-count">{{ rv.pending }}</span></button>
        <button type="button" role="tab" :aria-selected="rv.tab === 'examples' ? 'true' : 'false'" @click="setReviewTab('examples')">
          {{ t.rv.tabs.examples }} <span v-if="ex.items.length" class="tab-count">{{ ex.items.length }}</span></button>
      </div>

      <template v-if="rv.tab === 'pending'">
      <p class="error" v-if="rv.error" role="alert">{{ rv.error }}</p>

      <template v-if="rv.loading && !rv.items.length">
        <div v-for="n in 2" :key="n" class="card"><div class="skeleton" style="height:150px"></div></div>
      </template>

      <p v-else-if="!rv.items.length && !rv.error" class="card empty-state">
        <svg class="i" aria-hidden="true"><use href="#i-inbox"/></svg> {{ t.rv.empty }}</p>

      <p v-if="rv.pending > rv.items.length" class="help">{{ t.rv.more(rv.items.length, rv.pending) }}</p>

      <article v-for="i in rv.items" :key="i.id" class="card review-item" :aria-label="i.question">
        <header class="review-head">
          <h2 class="review-q">“{{ i.question }}”</h2>
          <span class="review-meta">{{ t.rv.asked(i.username, reviewWhen(i.created_at)) }} · {{ t.roles[i.role] || i.role }}</span>
        </header>

        <div class="review-answer">
          <span class="label">{{ t.rv.answer }}</span>
          <p v-if="i.answer">{{ i.answer }}</p>
          <p v-else-if="i.error" class="error">{{ t.rv.error }}: {{ i.error }}</p>
        </div>

        <p v-if="!i.can_teach" class="help"><svg class="i" aria-hidden="true"><use href="#i-trend"/></svg> {{ t.rv.ml }}</p>

        <template v-else>
          <p v-if="i.follow_up" class="review-warn" role="note"><svg class="i" aria-hidden="true"><use href="#i-alert"/></svg> {{ t.rv.followUp }}</p>

          <div>
            <label class="lbl" :for="'rv-q-' + i.id">{{ t.rv.question }}</label>
            <input :id="'rv-q-' + i.id" :name="'q-' + i.id" class="input" v-model="i.draftQuestion" maxlength="500" />
            <button v-if="i.draftQuestion !== i.question" type="button" class="link-btn" @click="i.draftQuestion = i.question">
              {{ t.rv.resetQuestion }}: “{{ i.question }}”</button>
          </div>
          <div>
            <label class="lbl" :for="'rv-sql-' + i.id">{{ t.rv.sql }}</label>
            <textarea :id="'rv-sql-' + i.id" :name="'sql-' + i.id" v-model="i.draftSql" class="input sql-edit" rows="6"
                      spellcheck="false" :placeholder="i.sql ? '' : t.rv.noSql"></textarea>
          </div>

          <div v-if="i.preview" class="review-preview table-wrap">
            <div class="source-head"><span>{{ t.rv.rows(i.preview.row_count, i.preview.rows.length) }}</span></div>
            <table>
              <thead><tr><th v-for="c in i.preview.columns" :key="c">{{ colName(c) }}</th></tr></thead>
              <tbody><tr v-for="(r, n) in i.preview.rows" :key="n"><td v-for="(v, j) in r" :key="j" :class="{ num: isNum(v) }">{{ format(v) }}</td></tr></tbody>
            </table>
          </div>
        </template>

        <p v-if="i.err" class="error" role="alert">{{ i.err }}</p>

        <div class="review-actions">
          <template v-if="i.can_teach">
            <button type="button" class="btn-soft sm" @click="reviewTest(i)" :disabled="!!i.busy || !i.draftSql.trim()">
              <svg class="i" aria-hidden="true"><use href="#i-play"/></svg> {{ i.busy === 'test' ? t.rv.testing : t.rv.test }}</button>
            <button type="button" class="btn btn-primary sm" @click="reviewTeach(i)"
                    :disabled="!!i.busy || !reviewTested(i) || !i.draftQuestion.trim()" :title="reviewTested(i) ? '' : t.rv.testFirst">
              <svg class="i" aria-hidden="true"><use href="#i-teach"/></svg> {{ i.busy === 'teach' ? t.rv.teaching : t.rv.teach }}</button>
            <span v-if="!reviewTested(i)" class="help">{{ t.rv.testFirst }}</span>
          </template>
          <button type="button" class="btn-soft sm review-dismiss" @click="reviewDismiss(i)" :disabled="!!i.busy">
            <svg class="i" aria-hidden="true"><use href="#i-x"/></svg> {{ t.rv.dismiss }}</button>
        </div>
      </article>
      </template>

      <template v-else>
        <p class="help ex-intro">{{ t.ex.intro }}</p>
        <div class="ex-toolbar">
          <input class="input" type="search" name="ex-search" v-model="ex.q" :placeholder="t.ex.search" :aria-label="t.ex.search" />
          <div class="segmented sm" role="group" :aria-label="t.ex.sources.seed">
            <button type="button" :aria-pressed="!ex.source ? 'true' : 'false'" @click="ex.source = ''">{{ t.ex.all }}</button>
            <button v-for="s in exSources" :key="s" type="button" :aria-pressed="ex.source === s ? 'true' : 'false'"
                    @click="ex.source = s">{{ t.ex.sources[s] }}</button>
          </div>
          <button type="button" class="btn btn-primary sm" @click="exStartNew" :disabled="ex.editId !== null">
            <svg class="i" aria-hidden="true"><use href="#i-plus"/></svg> {{ t.ex.newBtn }}</button>
        </div>
        <p class="error" v-if="ex.error" role="alert">{{ ex.error }}</p>

        <article v-if="ex.editId === 'new'" class="card review-item">
          <div class="ex-editor">
            <div><label class="lbl" for="ex-q-new">{{ t.rv.question }}</label>
              <input id="ex-q-new" name="ex-question" class="input" v-model="ex.form.question" maxlength="500" /></div>
            <div><label class="lbl" for="ex-sql-new">{{ t.rv.sql }}</label>
              <textarea id="ex-sql-new" name="ex-sql" class="input sql-edit" rows="7" spellcheck="false" v-model="ex.form.sql"></textarea></div>
          </div>
          <div v-if="ex.form.preview" class="review-preview table-wrap">
            <div class="source-head"><span>{{ t.rv.rows(ex.form.preview.row_count, ex.form.preview.rows.length) }}</span></div>
            <table>
              <thead><tr><th v-for="c in ex.form.preview.columns" :key="c">{{ colName(c) }}</th></tr></thead>
              <tbody><tr v-for="(r, n) in ex.form.preview.rows" :key="n"><td v-for="(v, j) in r" :key="j" :class="{ num: isNum(v) }">{{ format(v) }}</td></tr></tbody>
            </table>
          </div>
          <p v-if="ex.form.err" class="error" role="alert">{{ ex.form.err }}</p>
          <div class="review-actions">
            <button type="button" class="btn-soft sm" @click="exTest" :disabled="!!ex.form.busy || !ex.form.sql.trim()">
              <svg class="i" aria-hidden="true"><use href="#i-play"/></svg> {{ ex.form.busy === 'test' ? t.rv.testing : t.rv.test }}</button>
            <button type="button" class="btn btn-primary sm" @click="exSave" :disabled="!!ex.form.busy || !exTested() || ex.form.question.trim().length < 3">
              <svg class="i" aria-hidden="true"><use href="#i-check"/></svg> {{ ex.form.busy === 'save' ? t.ex.saving : t.ex.save }}</button>
            <span v-if="!exTested()" class="help">{{ t.rv.testFirst }}</span>
            <button type="button" class="btn-soft sm review-dismiss" @click="exCancel">{{ t.ex.cancel }}</button>
          </div>
        </article>

        <template v-if="ex.loading && !ex.items.length">
          <div v-for="n in 3" :key="n" class="card"><div class="skeleton" style="height:60px"></div></div>
        </template>
        <p v-else-if="!exFiltered.length" class="card empty-state"><svg class="i" aria-hidden="true"><use href="#i-inbox"/></svg> {{ t.ex.empty }}</p>
        <p v-else class="help">{{ t.ex.count(exFiltered.length) }}</p>

        <article v-for="e in exFiltered" :key="e.id" class="card ex-item">
          <template v-if="ex.editId === e.id">
            <div class="ex-editor">
              <div><label class="lbl" :for="'ex-q-' + e.id">{{ t.rv.question }}</label>
                <input :id="'ex-q-' + e.id" :name="'ex-q-' + e.id" class="input" v-model="ex.form.question" maxlength="500" /></div>
              <div><label class="lbl" :for="'ex-sql-' + e.id">{{ t.rv.sql }}</label>
                <textarea :id="'ex-sql-' + e.id" :name="'ex-sql-' + e.id" class="input sql-edit" rows="7" spellcheck="false" v-model="ex.form.sql"></textarea></div>
            </div>
            <div v-if="ex.form.preview" class="review-preview table-wrap">
              <div class="source-head"><span>{{ t.rv.rows(ex.form.preview.row_count, ex.form.preview.rows.length) }}</span></div>
              <table>
                <thead><tr><th v-for="c in ex.form.preview.columns" :key="c">{{ colName(c) }}</th></tr></thead>
                <tbody><tr v-for="(r, n) in ex.form.preview.rows" :key="n"><td v-for="(v, j) in r" :key="j" :class="{ num: isNum(v) }">{{ format(v) }}</td></tr></tbody>
              </table>
            </div>
            <p v-if="ex.form.err" class="error" role="alert">{{ ex.form.err }}</p>
            <div class="review-actions">
              <button type="button" class="btn-soft sm" @click="exTest" :disabled="!!ex.form.busy || !ex.form.sql.trim()">
                <svg class="i" aria-hidden="true"><use href="#i-play"/></svg> {{ ex.form.busy === 'test' ? t.rv.testing : t.rv.test }}</button>
              <button type="button" class="btn btn-primary sm" @click="exSave" :disabled="!!ex.form.busy || !exTested() || ex.form.question.trim().length < 3">
                <svg class="i" aria-hidden="true"><use href="#i-check"/></svg> {{ ex.form.busy === 'save' ? t.ex.saving : t.ex.save }}</button>
              <span v-if="!exTested()" class="help">{{ t.rv.testFirst }}</span>
              <button type="button" class="btn-soft sm review-dismiss" @click="exCancel">{{ t.ex.cancel }}</button>
            </div>
          </template>

          <template v-else>
            <div class="ex-row">
              <div class="ex-main">
                <h2 class="ex-q">{{ e.question }}</h2>
                <div class="ex-meta">
                  <span class="ex-badge" :class="'src-' + e.source">{{ t.ex.sources[e.source] || e.source }}</span>
                  <span v-if="e.created_by">{{ t.ex.by(e.created_by) }}</span>
                  <span :class="{ 'ex-never': !e.uses }" :title="e.uses ? '' : t.ex.neverHint">{{ t.ex.uses(e.uses) }}</span>
                  <span v-if="e.last_used_at">{{ t.ex.lastUse(exDate(e.last_used_at)) }}</span>
                  <span v-if="e.updated_by">{{ t.ex.edited(e.updated_by, exDate(e.updated_at)) }}</span>
                </div>
              </div>
              <div class="ex-actions">
                <button type="button" class="btn-soft sm" @click="e.open = !e.open" :aria-expanded="e.open ? 'true' : 'false'">
                  <svg class="i" aria-hidden="true"><use href="#i-code"/></svg> {{ e.open ? t.ex.hideSql : t.ex.showSql }}</button>
                <button type="button" class="btn-soft sm icon-only" @click="exStartEdit(e)" :disabled="ex.editId !== null"
                        :aria-label="t.ex.edit + ': ' + e.question" :title="t.ex.edit"><svg class="i" aria-hidden="true"><use href="#i-edit"/></svg></button>
                <button type="button" class="btn-soft sm icon-only danger-hover" @click="exDelete(e)" :disabled="ex.editId !== null"
                        :aria-label="t.ex.del + ': ' + e.question" :title="t.ex.del"><svg class="i" aria-hidden="true"><use href="#i-trash"/></svg></button>
              </div>
            </div>
            <pre v-if="e.open" class="ex-sql">{{ e.sql }}</pre>
          </template>
        </article>
      </template>
    </main>
  `,
};
