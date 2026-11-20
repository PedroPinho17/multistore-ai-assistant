import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type { ExampleItem, ReviewItem } from '@/api/types'
import { ApiError } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

function apiError(e: unknown): string {
  const ui = useUiStore()
  const err = e as ApiError
  return (err.code && (ui.t.errors as Record<string, string>)[err.code]) || err.message || String(e)
}

/** How long the pending-review count in the menu is reused before asking the server again. */
export const COUNT_TTL_MS = 60_000

function blankForm(question: string, sql: string) {
  return {
    question,
    sql,
    preview: null as ReviewItem['preview'],
    testedSql: null as string | null,
    busy: '',
    err: '',
  }
}

export const useReviewStore = defineStore('review', () => {
  const items = ref<ReviewItem[]>([])
  const pending = ref(0)
  const loading = ref(false)
  const error = ref('')
  const tab = ref<'pending' | 'examples'>('pending')

  const exItems = ref<ExampleItem[]>([])
  const exLoading = ref(false)
  const exError = ref('')
  const exQ = ref('')
  const exSource = ref('')
  const exEditId = ref<number | 'new' | null>(null)
  const exForm = ref<ReturnType<typeof blankForm> | null>(null)

  const exSources = ['seed', 'feedback', 'review', 'manual'] as const

  const exFiltered = computed(() => {
    const q = exQ.value.trim().toLowerCase()
    return exItems.value.filter(
      e =>
        (!exSource.value || e.source === exSource.value) &&
        (!q ||
          e.question.toLowerCase().includes(q) ||
          e.sql.toLowerCase().includes(q)),
    )
  })

  // The shell (mounted again on every page) asks for the count on each navigation: it is
  // fetched at most once per COUNT_TTL_MS for the same account (concurrent calls share one
  // request). Another account (logout → login) starts from zero and fetches again.
  let countFor: string | null = null
  let countAt = 0
  let countReq: Promise<void> | null = null

  function loadCount(force = false): Promise<void> {
    const auth = useAuthStore()
    const who = auth.user?.username ?? null
    if (!who || !auth.hasModule('teach')) {
      pending.value = 0
      countFor = null
      return Promise.resolve()
    }
    if (countFor !== who) {
      pending.value = 0
      countReq = null
    } else if (countReq) {
      return countReq
    } else if (!force && Date.now() - countAt < COUNT_TTL_MS) {
      return Promise.resolve()
    }
    countFor = who
    countAt = Date.now()
    const req: Promise<void> = api<{ pending: number }>('/review')
      .then(d => {
        if (countFor === who) pending.value = d.pending
      })
      .catch(() => {
        if (countFor === who) countAt = 0 // failed: the next navigation tries again
      })
      .finally(() => {
        if (countReq === req) countReq = null
      })
    countReq = req
    return req
  }

  /** The /review list also brings the count: it refreshes the cache. */
  function countLoaded(n: number) {
    pending.value = n
    countFor = useAuthStore().user?.username ?? null
    countAt = Date.now()
  }

  async function loadReview() {
    loading.value = true
    error.value = ''
    try {
      const d = await api<{ pending: number; items: Omit<ReviewItem, 'draftQuestion' | 'draftSql' | 'preview' | 'testedSql' | 'busy' | 'err'>[] }>(
        '/review',
      )
      countLoaded(d.pending)
      items.value = d.items.map(i => ({
        ...i,
        draftQuestion: i.question,
        draftSql: i.sql || '',
        preview: null,
        testedSql: null,
        busy: '',
        err: '',
      }))
    } catch (e) {
      error.value = apiError(e)
    } finally {
      loading.value = false
    }
  }

  function reviewTested(i: ReviewItem) {
    return !!(i.preview && i.testedSql === i.draftSql.trim())
  }

  async function reviewTest(i: ReviewItem) {
    i.busy = 'test'
    i.err = ''
    try {
      i.preview = await api(`/review/${i.id}/preview`, { sql: i.draftSql })
      i.testedSql = i.draftSql.trim()
    } catch (e) {
      i.preview = null
      i.err = apiError(e)
    } finally {
      i.busy = ''
    }
  }

  function reviewDone(i: ReviewItem) {
    items.value = items.value.filter(x => x.id !== i.id)
    pending.value = Math.max(0, pending.value - 1)
  }

  async function reviewTeach(i: ReviewItem) {
    const ui = useUiStore()
    i.busy = 'teach'
    i.err = ''
    try {
      await api(`/review/${i.id}/teach`, { question: i.draftQuestion, sql: i.draftSql })
      reviewDone(i)
      ui.toast(ui.t.rv.taught, 'ok')
    } catch (e) {
      i.err = apiError(e)
      if ((e as ApiError).status === 404) reviewDone(i)
    } finally {
      i.busy = ''
    }
  }

  async function reviewDismiss(i: ReviewItem) {
    const ui = useUiStore()
    const ok = await ui.confirmDialog({
      title: ui.t.rv.dismissTitle,
      subject: i.question,
      text: ui.t.rv.dismissText,
      confirm: ui.t.rv.dismiss,
    })
    if (!ok) return
    i.busy = 'dismiss'
    try {
      await api(`/review/${i.id}/dismiss`, {})
      reviewDone(i)
      ui.toast(ui.t.rv.dismissed, 'ok')
    } catch (e) {
      i.err = apiError(e)
      if ((e as ApiError).status === 404) reviewDone(i)
    } finally {
      i.busy = ''
    }
  }

  function setTab(next: 'pending' | 'examples') {
    tab.value = next
    if (next === 'examples') void loadExamples()
    else void loadReview()
  }

  function reload() {
    if (tab.value === 'examples') void loadExamples()
    else void loadReview()
  }

  async function loadExamples() {
    exLoading.value = true
    exError.value = ''
    try {
      const d = await api<{ examples: Omit<ExampleItem, 'open'>[] }>('/examples')
      exItems.value = d.examples.map(e => ({ ...e, open: false }))
    } catch (e) {
      exError.value = apiError(e)
    } finally {
      exLoading.value = false
    }
  }

  function exStartNew() {
    exEditId.value = 'new'
    exForm.value = blankForm('', '')
  }

  function exStartEdit(e: ExampleItem) {
    exEditId.value = e.id
    exForm.value = blankForm(e.question, e.sql)
  }

  function exCancel() {
    exEditId.value = null
    exForm.value = null
  }

  function exTested() {
    const f = exForm.value
    return !!(f && f.preview && f.testedSql === f.sql.trim())
  }

  async function exTest() {
    const f = exForm.value
    if (!f) return
    f.busy = 'test'
    f.err = ''
    try {
      f.preview = await api('/examples/preview', { sql: f.sql })
      f.testedSql = f.sql.trim()
    } catch (e) {
      f.preview = null
      f.err = apiError(e)
    } finally {
      f.busy = ''
    }
  }

  async function exSave() {
    const ui = useUiStore()
    const f = exForm.value
    if (!f) return
    const isNew = exEditId.value === 'new'
    f.busy = 'save'
    f.err = ''
    try {
      const body = { question: f.question, sql: f.sql }
      if (isNew) await api('/examples', body)
      else await api(`/examples/${exEditId.value}`, body, 'PUT')
      exCancel()
      ui.toast(isNew ? ui.t.ex.created : ui.t.ex.saved, 'ok')
      await loadExamples()
    } catch (e) {
      f.err = apiError(e)
    } finally {
      if (exForm.value) exForm.value.busy = ''
    }
  }

  async function exDelete(e: ExampleItem) {
    const ui = useUiStore()
    const ok = await ui.confirmDialog({
      title: ui.t.ex.delTitle,
      subject: e.question,
      text: ui.t.ex.delText,
      confirm: ui.t.ex.del,
      danger: true,
    })
    if (!ok) return
    try {
      await api(`/examples/${e.id}`, null, 'DELETE')
      exItems.value = exItems.value.filter(x => x.id !== e.id)
      ui.toast(ui.t.ex.deleted, 'ok')
    } catch (err) {
      ui.toast(apiError(err))
    }
  }

  return {
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
    loadCount,
    loadReview,
    reviewTested,
    reviewTest,
    reviewTeach,
    reviewDismiss,
    setTab,
    reload,
    loadExamples,
    exStartNew,
    exStartEdit,
    exCancel,
    exTested,
    exTest,
    exSave,
    exDelete,
  }
})
