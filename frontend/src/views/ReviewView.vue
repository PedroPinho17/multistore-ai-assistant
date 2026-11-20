<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import AppShell from '@/components/AppShell.vue'
import { colName, formatValue, isNum } from '@/lib/format'
import { useReviewStore } from '@/stores/review'
import { useUiStore } from '@/stores/ui'

const review = useReviewStore()
const ui = useUiStore()
const {
  items,
  pending,
  loading,
  error,
  tab,
  exItems,
  exLoading,
  exError,
  exQ,
  exSource,
  exEditId,
  exForm,
  exSources,
  exFiltered,
} = storeToRefs(review)
const { t, lang } = storeToRefs(ui)

function reviewWhen(iso: string) {
  return new Date(iso).toLocaleString(lang.value === 'en' ? 'en-GB' : lang.value, {
    dateStyle: 'short',
    timeStyle: 'short',
  })
}

watch(
  () => ui.t.pageTitles.review,
  title => {
    document.title = title
  },
  { immediate: true },
)
watch(
  () => [t.value.rv.title, t.value.rv.sub] as const,
  ([title, sub]) => ui.setPageMeta(title, sub, 'review'),
  { immediate: true },
)

onMounted(() => {
  void review.loadReview()
})
</script>

<template>
  <AppShell>
    <div class="page-scroll">
      <main class="page">
        <div class="tabs" role="tablist" :aria-label="t.rv.title">
          <button
            type="button"
            role="tab"
            :aria-selected="tab === 'pending' ? 'true' : 'false'"
            @click="review.setTab('pending')"
          >
            {{ t.rv.tabs.pending }}
            <span v-if="pending" class="nav-count">{{ pending }}</span>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="tab === 'examples' ? 'true' : 'false'"
            @click="review.setTab('examples')"
          >
            {{ t.rv.tabs.examples }}
            <span v-if="exItems.length" class="tab-count">{{ exItems.length }}</span>
          </button>
        </div>

        <template v-if="tab === 'pending'">
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <template v-if="loading && !items.length">
            <div v-for="n in 2" :key="n" class="card">
              <div class="skeleton" style="height: 150px"></div>
            </div>
          </template>
          <p v-else-if="!items.length && !error" class="card empty-state">
            <svg class="i" aria-hidden="true"><use href="#i-inbox" /></svg> {{ t.rv.empty }}
          </p>
          <p v-if="pending > items.length" class="help">
            {{ t.rv.more(items.length, pending) }}
          </p>

          <article
            v-for="i in items"
            :key="i.id"
            class="card review-item"
            :aria-label="i.question"
          >
            <header class="review-head">
              <h2 class="review-q">“{{ i.question }}”</h2>
              <span class="review-meta"
                >{{ t.rv.asked(i.username, reviewWhen(i.created_at)) }} ·
                {{ t.roles[i.role as keyof typeof t.roles] || i.role }}</span
              >
            </header>
            <div class="review-answer">
              <span class="label">{{ t.rv.answer }}</span>
              <p v-if="i.answer">{{ i.answer }}</p>
              <p v-else-if="i.error" class="error">{{ t.rv.error }}: {{ i.error }}</p>
            </div>
            <p v-if="!i.can_teach" class="help">
              <svg class="i" aria-hidden="true"><use href="#i-trend" /></svg> {{ t.rv.ml }}
            </p>
            <template v-else>
              <p v-if="i.follow_up" class="review-warn" role="note">
                <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg>
                {{ t.rv.followUp }}
              </p>
              <div>
                <label class="lbl" :for="'rv-q-' + i.id">{{ t.rv.question }}</label>
                <input
                  :id="'rv-q-' + i.id"
                  v-model="i.draftQuestion"
                  class="input"
                  maxlength="500"
                />
                <button
                  v-if="i.draftQuestion !== i.question"
                  type="button"
                  class="link-btn"
                  @click="i.draftQuestion = i.question"
                >
                  {{ t.rv.resetQuestion }}: “{{ i.question }}”
                </button>
              </div>
              <div>
                <label class="lbl" :for="'rv-sql-' + i.id">{{ t.rv.sql }}</label>
                <textarea
                  :id="'rv-sql-' + i.id"
                  v-model="i.draftSql"
                  class="input sql-edit"
                  rows="6"
                  spellcheck="false"
                  :placeholder="i.sql ? '' : t.rv.noSql"
                ></textarea>
              </div>
              <div v-if="i.preview" class="review-preview table-wrap">
                <div class="source-head">
                  <span>{{ t.rv.rows(i.preview.row_count, i.preview.rows.length) }}</span>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th v-for="c in i.preview.columns" :key="c">{{ colName(c, lang) }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(r, n) in i.preview.rows" :key="n">
                      <td
                        v-for="(v, j) in r"
                        :key="j"
                        :class="{ num: isNum(v) }"
                      >
                        {{ formatValue(v, lang) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
            <p v-if="i.err" class="error" role="alert">{{ i.err }}</p>
            <div class="review-actions">
              <template v-if="i.can_teach">
                <button
                  type="button"
                  class="btn-soft sm"
                  :disabled="!!i.busy || !i.draftSql.trim()"
                  @click="review.reviewTest(i)"
                >
                  <svg class="i" aria-hidden="true"><use href="#i-play" /></svg>
                  {{ i.busy === 'test' ? t.rv.testing : t.rv.test }}
                </button>
                <button
                  type="button"
                  class="btn btn-primary sm"
                  :disabled="!!i.busy || !review.reviewTested(i) || !i.draftQuestion.trim()"
                  :title="review.reviewTested(i) ? '' : t.rv.testFirst"
                  @click="review.reviewTeach(i)"
                >
                  <svg class="i" aria-hidden="true"><use href="#i-teach" /></svg>
                  {{ i.busy === 'teach' ? t.rv.teaching : t.rv.teach }}
                </button>
                <span v-if="!review.reviewTested(i)" class="help">{{ t.rv.testFirst }}</span>
              </template>
              <button
                type="button"
                class="btn-soft sm review-dismiss"
                :disabled="!!i.busy"
                @click="review.reviewDismiss(i)"
              >
                <svg class="i" aria-hidden="true"><use href="#i-x" /></svg> {{ t.rv.dismiss }}
              </button>
            </div>
          </article>
        </template>

        <template v-else>
          <p class="help ex-intro">{{ t.ex.intro }}</p>
          <div class="ex-toolbar">
            <input
              v-model="exQ"
              class="input"
              type="search"
              name="ex-search"
              :placeholder="t.ex.search"
              :aria-label="t.ex.search"
            />
            <div class="segmented sm" role="group" :aria-label="t.ex.sources.seed">
              <button
                type="button"
                :aria-pressed="!exSource ? 'true' : 'false'"
                @click="exSource = ''"
              >
                {{ t.ex.all }}
              </button>
              <button
                v-for="s in exSources"
                :key="s"
                type="button"
                :aria-pressed="exSource === s ? 'true' : 'false'"
                @click="exSource = s"
              >
                {{ t.ex.sources[s] }}
              </button>
            </div>
            <button
              type="button"
              class="btn btn-primary sm"
              :disabled="exEditId !== null"
              @click="review.exStartNew()"
            >
              <svg class="i" aria-hidden="true"><use href="#i-plus" /></svg> {{ t.ex.newBtn }}
            </button>
          </div>
          <p v-if="exError" class="error" role="alert">{{ exError }}</p>

          <article v-if="exEditId === 'new' && exForm" class="card review-item">
            <div class="ex-editor">
              <div>
                <label class="lbl" for="ex-q-new">{{ t.rv.question }}</label>
                <input id="ex-q-new" v-model="exForm.question" class="input" maxlength="500" />
              </div>
              <div>
                <label class="lbl" for="ex-sql-new">{{ t.rv.sql }}</label>
                <textarea
                  id="ex-sql-new"
                  v-model="exForm.sql"
                  class="input sql-edit"
                  rows="7"
                  spellcheck="false"
                ></textarea>
              </div>
            </div>
            <div v-if="exForm.preview" class="review-preview table-wrap">
              <div class="source-head">
                <span>{{
                  t.rv.rows(exForm.preview.row_count, exForm.preview.rows.length)
                }}</span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th v-for="c in exForm.preview.columns" :key="c">{{ colName(c, lang) }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(r, n) in exForm.preview.rows" :key="n">
                    <td v-for="(v, j) in r" :key="j" :class="{ num: isNum(v) }">
                      {{ formatValue(v, lang) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-if="exForm.err" class="error" role="alert">{{ exForm.err }}</p>
            <div class="review-actions">
              <button
                type="button"
                class="btn-soft sm"
                :disabled="!!exForm.busy || !exForm.sql.trim()"
                @click="review.exTest()"
              >
                <svg class="i" aria-hidden="true"><use href="#i-play" /></svg>
                {{ exForm.busy === 'test' ? t.rv.testing : t.rv.test }}
              </button>
              <button
                type="button"
                class="btn btn-primary sm"
                :disabled="
                  !!exForm.busy || !review.exTested() || exForm.question.trim().length < 3
                "
                @click="review.exSave()"
              >
                <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>
                {{ exForm.busy === 'save' ? t.ex.saving : t.ex.save }}
              </button>
              <span v-if="!review.exTested()" class="help">{{ t.rv.testFirst }}</span>
              <button type="button" class="btn-soft sm review-dismiss" @click="review.exCancel()">
                {{ t.ex.cancel }}
              </button>
            </div>
          </article>

          <template v-if="exLoading && !exItems.length">
            <div v-for="n in 3" :key="n" class="card">
              <div class="skeleton" style="height: 60px"></div>
            </div>
          </template>
          <p v-else-if="!exFiltered.length" class="card empty-state">
            <svg class="i" aria-hidden="true"><use href="#i-inbox" /></svg> {{ t.ex.empty }}
          </p>
          <p v-else class="help">{{ t.ex.count(exFiltered.length) }}</p>

          <article v-for="e in exFiltered" :key="e.id" class="card ex-item">
            <template v-if="exEditId === e.id && exForm">
              <div class="ex-editor">
                <div>
                  <label class="lbl" :for="'ex-q-' + e.id">{{ t.rv.question }}</label>
                  <input
                    :id="'ex-q-' + e.id"
                    v-model="exForm.question"
                    class="input"
                    maxlength="500"
                  />
                </div>
                <div>
                  <label class="lbl" :for="'ex-sql-' + e.id">{{ t.rv.sql }}</label>
                  <textarea
                    :id="'ex-sql-' + e.id"
                    v-model="exForm.sql"
                    class="input sql-edit"
                    rows="7"
                    spellcheck="false"
                  ></textarea>
                </div>
              </div>
              <div v-if="exForm.preview" class="review-preview table-wrap">
                <div class="source-head">
                  <span>{{
                    t.rv.rows(exForm.preview.row_count, exForm.preview.rows.length)
                  }}</span>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th v-for="c in exForm.preview.columns" :key="c">
                        {{ colName(c, lang) }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(r, n) in exForm.preview.rows" :key="n">
                      <td v-for="(v, j) in r" :key="j" :class="{ num: isNum(v) }">
                        {{ formatValue(v, lang) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-if="exForm.err" class="error" role="alert">{{ exForm.err }}</p>
              <div class="review-actions">
                <button
                  type="button"
                  class="btn-soft sm"
                  :disabled="!!exForm.busy || !exForm.sql.trim()"
                  @click="review.exTest()"
                >
                  <svg class="i" aria-hidden="true"><use href="#i-play" /></svg>
                  {{ exForm.busy === 'test' ? t.rv.testing : t.rv.test }}
                </button>
                <button
                  type="button"
                  class="btn btn-primary sm"
                  :disabled="
                    !!exForm.busy || !review.exTested() || exForm.question.trim().length < 3
                  "
                  @click="review.exSave()"
                >
                  <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>
                  {{ exForm.busy === 'save' ? t.ex.saving : t.ex.save }}
                </button>
                <span v-if="!review.exTested()" class="help">{{ t.rv.testFirst }}</span>
                <button
                  type="button"
                  class="btn-soft sm review-dismiss"
                  @click="review.exCancel()"
                >
                  {{ t.ex.cancel }}
                </button>
              </div>
            </template>
            <template v-else>
              <div class="ex-row">
                <div class="ex-main">
                  <h2 class="ex-q">{{ e.question }}</h2>
                  <div class="ex-meta">
                    <span class="ex-badge" :class="'src-' + e.source">{{
                      t.ex.sources[e.source as keyof typeof t.ex.sources] || e.source
                    }}</span>
                    <span v-if="e.created_by">{{ t.ex.by(e.created_by) }}</span>
                    <span :class="{ 'ex-never': !e.uses }" :title="e.uses ? '' : t.ex.neverHint">{{
                      t.ex.uses(e.uses)
                    }}</span>
                    <span v-if="e.last_used_at">{{
                      t.ex.lastUse(reviewWhen(e.last_used_at))
                    }}</span>
                    <span v-if="e.updated_by">{{
                      t.ex.edited(e.updated_by, reviewWhen(e.updated_at || ''))
                    }}</span>
                  </div>
                </div>
                <div class="ex-actions">
                  <button
                    type="button"
                    class="btn-soft sm"
                    :aria-expanded="e.open ? 'true' : 'false'"
                    @click="e.open = !e.open"
                  >
                    <svg class="i" aria-hidden="true"><use href="#i-code" /></svg>
                    {{ e.open ? t.ex.hideSql : t.ex.showSql }}
                  </button>
                  <button
                    type="button"
                    class="btn-soft sm icon-only"
                    :disabled="exEditId !== null"
                    :aria-label="t.ex.edit + ': ' + e.question"
                    @click="review.exStartEdit(e)"
                  >
                    <svg class="i" aria-hidden="true"><use href="#i-edit" /></svg>
                  </button>
                  <button
                    type="button"
                    class="btn-soft sm icon-only danger-hover"
                    :disabled="exEditId !== null"
                    :aria-label="t.ex.del + ': ' + e.question"
                    @click="review.exDelete(e)"
                  >
                    <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg>
                  </button>
                </div>
              </div>
              <pre v-if="e.open" class="ex-sql">{{ e.sql }}</pre>
            </template>
          </article>
        </template>
      </main>
    </div>
  </AppShell>
</template>
