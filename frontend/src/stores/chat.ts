import { defineStore } from 'pinia'
import { computed, nextTick, ref, watch } from 'vue'
import { api, apiBlob, httpError } from '@/api/client'
import router from '@/router'
import type {
  AlertItem,
  AskResult,
  ChatMessage,
  Conversation,
  StoredMessage,
} from '@/api/types'
import { ApiError } from '@/api/types'
import { createSseParser } from '@/lib/sse'
import {
  isSseData,
  isSseDone,
  isSseError,
  isSseStatus,
  isSseToken,
} from '@/lib/sse-events'
import { canChart } from '@/lib/chart-data'
import { colName, formatValue, isNum, nowTime, timeFromIso } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

type ChartModule = typeof import('@/lib/chart')
let chartModule: ChartModule | null = null
let chartLoad: Promise<ChartModule> | null = null

/** Chart.js só se descarrega quando se desenha um gráfico. */
function chartApi(): Promise<ChartModule> {
  chartLoad ??= import('@/lib/chart').then(m => (chartModule = m))
  return chartLoad
}

/** Limpar/redesenhar nunca descarrega o Chart.js: sem módulo carregado não há gráficos. */
function withLoadedCharts(fn: (m: ChartModule) => void): void {
  if (chartModule) fn(chartModule)
  else if (chartLoad) void chartLoad.then(fn) // a carregar para um gráfico: espera por ele
}

let nextId = 1
let streamAbort: AbortController | null = null
let streamSession = 0

const reduceMotion =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

function isAbortError(e: unknown): boolean {
  return (
    (e instanceof DOMException && e.name === 'AbortError') ||
    (e instanceof Error && e.name === 'AbortError')
  )
}

export const useChatStore = defineStore('chat', () => {
  const question = ref('')
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const streaming = ref(false)
  const stepIndex = ref(0)
  const stepTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const welcomeDone = ref(false)
  const alerts = ref<AlertItem[]>([])
  const alertsOpen = ref(true)
  const conversations = ref<Conversation[]>([])
  const currentConv = ref<number | null>(null)
  const editingId = ref<number | null>(null)
  const editTitle = ref('')
  const announce = ref('')
  const exportingPdf = ref(false)

  const last = computed(() => {
    const m = messages.value[messages.value.length - 1]
    return m && m.from === 'bot' && !m.welcome ? m : null
  })

  const starterSuggestions = computed(() => {
    const auth = useAuthStore()
    const ui = useUiStore()
    return (ui.t.starters[auth.scope] || [])
      .filter(([mod]) => auth.hasModule(mod))
      .map(([, q]) => q)
  })

  const pageTitle = computed(() => {
    const ui = useUiStore()
    return (
      conversations.value.find(c => c.id === currentConv.value)?.title || ui.t.newChat
    )
  })

  function scrollDown() {
    void nextTick(() => {
      const c = document.getElementById('chat-scroll')
      if (c) c.scrollTop = c.scrollHeight
    })
  }

  function autoGrow() {
    const el = document.getElementById('question') as HTMLTextAreaElement | null
    if (!el) return
    el.style.height = 'auto'
    el.style.height = el.scrollHeight + 'px'
  }

  function startSteps() {
    stepIndex.value = 0
    if (stepTimer.value) clearInterval(stepTimer.value)
    const ui = useUiStore()
    stepTimer.value = setInterval(() => {
      if (stepIndex.value < ui.t.steps.length - 1) stepIndex.value++
    }, 1400)
  }

  function stepOf(step: string): number {
    return ({ classify: 0, sql: 1, query: 2, forecast: 2, answer: 3 } as Record<string, number>)[
      step
    ] ?? stepIndex.value
  }

  function addBot(fields: Partial<ChatMessage> & { text?: string }): ChatMessage {
    const ui = useUiStore()
    const m: ChatMessage = {
      id: nextId++,
      from: 'bot',
      text: '',
      shown: '',
      done: false,
      time: nowTime(ui.lang),
      rows: [],
      showTable: false,
      showSql: false,
      liked: false,
      copied: false,
      sqlCopied: false,
      requestId: null,
      rating: null,
      suggestions: [],
      explanation: '',
      explaining: false,
      ...fields,
    }
    messages.value.push(m)
    return messages.value[messages.value.length - 1]!
  }

  function typeOut(m: ChatMessage): Promise<void> {
    return new Promise(resolve => {
      if (reduceMotion || !m.text) {
        m.shown = m.text
        m.done = true
        return resolve()
      }
      const chunk = Math.max(1, Math.round(m.text.length / 90))
      let i = 0
      const tick = () => {
        i = Math.min(m.text.length, i + chunk)
        m.shown = m.text.slice(0, i)
        if (i % 12 === 0) scrollDown()
        if (i < m.text.length) setTimeout(tick, 14 + Math.random() * 18)
        else {
          m.done = true
          scrollDown()
          resolve()
        }
      }
      tick()
    })
  }

  function botFields(q: string, r: AskResult): Partial<ChatMessage> {
    const rows = r.rows || []
    return {
      question: q,
      text: r.error || r.answer || '',
      error: !!r.error,
      sql: r.sql,
      kind: r.kind,
      requestId: r.request_id,
      rating: null,
      cached: !!r.cached,
      suggestions: r.suggestions || [],
      columns: r.columns,
      rows,
      chart: canChart(r),
      showTable: rows.length > 1 && rows.length <= 12,
    }
  }

  async function loadAlerts() {
    try {
      const data = await api<{ alerts: AlertItem[] }>('/alerts')
      alerts.value = data.alerts || []
    } catch {
      alerts.value = []
    }
  }

  function welcome() {
    const auth = useAuthStore()
    const ui = useUiStore()
    if (!auth.user) return
    void loadAlerts()
    welcomeDone.value = false
    const raw = (auth.user.username || '').split(/[.\s]/)[0] || ''
    const name = raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : ''
    const m = addBot({
      text: ui.t.welcome(
        name,
        auth.scope,
        auth.hasModule('forecast'),
        auth.hasModule('orders'),
      ),
      welcome: true,
    })
    void typeOut(m).then(() => {
      welcomeDone.value = true
      scrollDown()
    })
  }

  async function loadConversations() {
    try {
      conversations.value = await api<Conversation[]>('/conversations')
    } catch {
      /* ignore */
    }
  }

  function newConversation() {
    if (loading.value || streaming.value) return
    withLoadedCharts(m => m.clearCharts())
    currentConv.value = null
    useUiStore().sidebarOpen = false
    messages.value = []
    welcome()
  }

  async function openConversation(id: number) {
    const ui = useUiStore()
    ui.sidebarOpen = false
    if (loading.value || streaming.value || id === currentConv.value) return
    try {
      const msgs = await api<StoredMessage[]>(`/conversations/${id}`)
      withLoadedCharts(m => m.clearCharts())
      currentConv.value = id
      messages.value = []
      welcomeDone.value = false
      let lastQuestion = ''
      for (const m of msgs) {
        if (m.role === 'user') {
          lastQuestion = m.content
          messages.value.push({
            id: nextId++,
            from: 'user',
            text: m.content,
            shown: m.content,
            done: true,
            time: timeFromIso(m.created_at, ui.lang),
            rows: [],
            showTable: false,
            showSql: false,
            liked: false,
            copied: false,
            sqlCopied: false,
            explanation: '',
            explaining: false,
          })
        } else {
          addBot({
            text: m.content,
            shown: m.content,
            done: true,
            time: timeFromIso(m.created_at, ui.lang),
            question: lastQuestion,
            sql: m.sql,
            kind: m.kind,
            error: m.kind === 'error',
            requestId: m.request_id,
            rating: m.rating,
          })
        }
      }
      void nextTick(scrollDown)
    } catch (e) {
      ui.toast((e as Error).message)
    }
  }

  async function deleteConversation(c: Conversation) {
    const ui = useUiStore()
    if ((loading.value || streaming.value) && c.id === currentConv.value) return
    const ok = await ui.confirmDialog({
      title: ui.t.dlg.delTitle,
      subject: c.title,
      text: ui.t.dlg.delText,
      confirm: ui.t.dlg.del,
      danger: true,
    })
    if (!ok) return
    try {
      await api(`/conversations/${c.id}`, null, 'DELETE')
      if (c.id === currentConv.value) newConversation()
      void loadConversations()
      ui.toast(ui.t.dlg.deleted, 'ok')
    } catch (e) {
      ui.toast((e as Error).message)
    }
  }

  function startRename(c: Conversation) {
    editingId.value = c.id
    editTitle.value = c.title
  }

  async function saveTitle(c: Conversation) {
    if (editingId.value !== c.id) return
    editingId.value = null
    const title = editTitle.value.trim()
    if (!title || title === c.title) return
    try {
      await api(`/conversations/${c.id}`, { title }, 'PATCH')
      c.title = title
    } catch (e) {
      useUiStore().toast((e as Error).message)
    }
  }

  async function recoverConversation(q: string, knownIds: Set<number>) {
    await loadConversations()
    if (currentConv.value) return
    const chars = Array.from(q)
    const title = chars.length > 60 ? chars.slice(0, 60).join('') + '…' : q
    const fresh = conversations.value.find(c => !knownIds.has(c.id) && c.title === title)
    if (fresh) currentConv.value = fresh.id
  }

  async function streamAsk(q: string): Promise<ChatMessage | null> {
    const auth = useAuthStore()
    const ui = useUiStore()
    const session = streamSession
    const ac = new AbortController()
    streamAbort = ac
    const knownConvs = new Set(conversations.value.map(c => c.id))
    const body = JSON.stringify({
      question: q,
      lang: ui.lang,
      conversation_id: currentConv.value,
    })
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept-Language': ui.lang,
      Authorization: 'Bearer ' + auth.token,
    }
    let res: Response
    try {
      res = await fetch('/ask/stream', { method: 'POST', headers, body, signal: ac.signal })
    } catch (e) {
      if (isAbortError(e) || session !== streamSession) return null
      throw new ApiError(ui.t.network, 0)
    }
    if (session !== streamSession || ac.signal.aborted) return null
    if (res.ok && !res.body) return null
    if (res.status === 401) {
      auth.logout(router, 'login')
      throw new ApiError(ui.t.loginError, 401)
    }
    if (!res.ok) {
      let data: unknown = null
      try {
        data = await res.json()
      } catch {
        /* ignore */
      }
      throw httpError(res, data, {
        network: ui.t.network,
        loginError: ui.t.loginError,
        tooMany: ui.t.tooMany,
        errors: ui.t.errors,
      })
    }

    if (stepTimer.value) clearInterval(stepTimer.value)
    let m: ChatMessage | null = null
    let data: AskResult | null = null
    let final: AskResult | null = null

    const handle = (ev: unknown) => {
      if (isSseStatus(ev) && ev.step) stepIndex.value = stepOf(ev.step)
      else if (isSseData(ev)) data = ev
      else if (isSseToken(ev)) {
        if (!m) {
          m = addBot({ question: q })
          loading.value = false
        }
        m.text += ev.text || ''
        m.shown = m.text
        scrollDown()
      } else if (isSseDone(ev)) {
        final = ev
        loading.value = false
      } else if (isSseError(ev)) {
        final = { error: ev.message }
        loading.value = false
      }
    }

    const parser = createSseParser(handle, (raw, err) =>
      console.warn('SSE: evento com JSON inválido ignorado', err, raw.slice(0, 200)),
    )
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let finished = false
    try {
      for (;;) {
        if (session !== streamSession || ac.signal.aborted) break
        let chunk: ReadableStreamReadResult<Uint8Array>
        try {
          chunk = await reader.read()
        } catch (e) {
          if (isAbortError(e)) break
          break
        }
        if (chunk.value) parser.push(decoder.decode(chunk.value, { stream: true }))
        if (chunk.done) {
          parser.push(decoder.decode())
          parser.end()
          finished = true
          break
        }
      }
    } finally {
      if (!finished) void reader.cancel().catch(() => undefined)
      if (streamAbort === ac) streamAbort = null
    }

    if (session !== streamSession || ac.signal.aborted) return null

    if (!final) {
      final = { error: ui.t.network }
      await recoverConversation(q, knownConvs)
    }
    if (session !== streamSession || ac.signal.aborted) return null
    if (final.conversation_id) {
      currentConv.value = final.conversation_id
      void loadConversations()
    }
    const fields = botFields(q, { ...(data || {}), ...final })
    if (m) Object.assign(m, fields)
    else m = addBot(fields)
    loading.value = false
    m.shown = m.text || ''
    return m
  }

  async function send(text?: string) {
    const ui = useUiStore()
    const q = (text ?? question.value).trim()
    if (!q || loading.value || streaming.value) return
    const session = streamSession
    streaming.value = true
    messages.value.push({
      id: nextId++,
      from: 'user',
      text: q,
      shown: q,
      done: true,
      time: nowTime(ui.lang),
      rows: [],
      showTable: false,
      showSql: false,
      liked: false,
      copied: false,
      sqlCopied: false,
      explanation: '',
      explaining: false,
    })
    question.value = ''
    void nextTick(autoGrow)
    loading.value = true
    startSteps()
    scrollDown()
    let m: ChatMessage | undefined
    let streamed = false
    try {
      const streamedMsg = await streamAsk(q)
      if (session !== streamSession) return
      streamed = !!streamedMsg
      if (streamedMsg) m = streamedMsg
      else {
        const r = await api<AskResult>('/ask', {
          question: q,
          lang: ui.lang,
          conversation_id: currentConv.value,
        })
        if (session !== streamSession) return
        currentConv.value = r.conversation_id ?? null
        void loadConversations()
        m = addBot(botFields(q, r))
      }
    } catch (e) {
      if (session !== streamSession || isAbortError(e)) return
      m = addBot({ text: (e as Error).message, error: true })
    } finally {
      if (session === streamSession) {
        if (stepTimer.value) clearInterval(stepTimer.value)
        stepTimer.value = null
        loading.value = false
        streaming.value = false
      }
    }
    if (session !== streamSession || !m) return
    if (streamed) m.done = true
    else await typeOut(m)
    if (session !== streamSession) return
    announce.value = m.text
    if (m.chart) {
      void nextTick(async () => {
        const { ensureChart } = await chartApi()
        ensureChart(m!, ui.lang)
      })
    }
    void nextTick(() => {
      scrollDown()
      document.getElementById('question')?.focus()
    })
  }

  async function exportPdf() {
    const ui = useUiStore()
    if (!currentConv.value || exportingPdf.value) return
    exportingPdf.value = true
    try {
      const { blob } = await apiBlob(`/conversations/${currentConv.value}/pdf`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download =
        (conversations.value.find(c => c.id === currentConv.value)?.title || 'conversation') +
        '.pdf'
      a.click()
      URL.revokeObjectURL(url)
      ui.toast(ui.t.pdfDone, 'ok')
    } catch (e) {
      ui.toast((e as Error).message, 'error')
    } finally {
      exportingPdf.value = false
    }
  }

  async function explain(m: ChatMessage) {
    if (m.explanation || m.explaining) return
    const ui = useUiStore()
    m.explaining = true
    try {
      const r = await api<{ explanation: string }>('/explain', {
        request_id: m.requestId,
        lang: ui.lang,
      })
      m.explanation = r.explanation
    } catch (e) {
      ui.toast((e as Error).message)
    } finally {
      m.explaining = false
    }
  }

  async function like(m: ChatMessage) {
    const ui = useUiStore()
    try {
      await api('/feedback', { question: m.question, sql: m.sql })
      m.liked = true
    } catch (e) {
      const err = e as ApiError
      ui.toast(err.status === 400 ? ui.t.errors.badSql : err.message)
    }
  }

  async function copy(m: ChatMessage) {
    const ui = useUiStore()
    try {
      await navigator.clipboard.writeText(m.text)
      m.copied = true
      setTimeout(() => {
        m.copied = false
      }, 1500)
    } catch {
      ui.toast(ui.t.copyFailed)
    }
  }

  async function copySql(m: ChatMessage) {
    const ui = useUiStore()
    try {
      await navigator.clipboard.writeText(m.sql || '')
      m.sqlCopied = true
      setTimeout(() => {
        m.sqlCopied = false
      }, 1500)
    } catch {
      ui.toast(ui.t.copyFailed)
    }
  }

  function downloadCsv(m: ChatMessage) {
    const ui = useUiStore()
    const cell = (v: unknown) => {
      let s = v === null || v === undefined ? '' : String(v)
      if (/^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s))) s = "'" + s
      return /[",;\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }
    const csv = [(m.columns || []).map(c => colName(c, ui.lang)), ...m.rows]
      .map(r => (r as unknown[]).map(cell).join(';'))
      .join('\n')
    const url = URL.createObjectURL(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: 'resultado.csv' })
    a.click()
    URL.revokeObjectURL(url)
  }

  async function rate(m: ChatMessage, value: number) {
    const ui = useUiStore()
    const next = m.rating === value ? 0 : value
    const before = m.rating
    m.rating = next || null
    try {
      await api('/ratings', { request_id: m.requestId, rating: next })
      if (next === -1) ui.toast(ui.t.rate.thanks, 'ok')
    } catch (e) {
      m.rating = before
      ui.toast((e as Error).message)
    }
  }

  function colDecimals(m: ChatMessage, j: number): number {
    m._dec ??= {}
    return (m._dec[j] ??= m.rows.some(r => isNum(r[j]) && !Number.isInteger(Number(r[j]))) ? 2 : 0)
  }

  function format(v: unknown, dec?: number): string {
    return formatValue(v, useUiStore().lang, dec)
  }

  function reset() {
    streamAbort?.abort()
    streamAbort = null
    streamSession++
    if (stepTimer.value) clearInterval(stepTimer.value)
    stepTimer.value = null
    withLoadedCharts(m => m.clearCharts())
    messages.value = []
    conversations.value = []
    currentConv.value = null
    welcomeDone.value = false
    loading.value = false
    streaming.value = false
    question.value = ''
    alerts.value = []
    announce.value = ''
    exportingPdf.value = false
    editingId.value = null
    editTitle.value = ''
  }

  const ui = useUiStore()
  const auth = useAuthStore()
  // Logout limpa o token sem import estático do chat: abort/reset sync aqui.
  watch(
    () => auth.token,
    (t, prev) => {
      if (prev && !t) reset()
    },
    { flush: 'sync' },
  )
  watch(
    () => ui.theme,
    () => {
      withLoadedCharts(m => m.redrawCharts(messages.value, ui.lang))
    },
  )

  return {
    question,
    messages,
    loading,
    streaming,
    stepIndex,
    welcomeDone,
    alerts,
    alertsOpen,
    conversations,
    currentConv,
    editingId,
    editTitle,
    announce,
    exportingPdf,
    last,
    starterSuggestions,
    pageTitle,
    scrollDown,
    autoGrow,
    welcome,
    loadConversations,
    newConversation,
    openConversation,
    deleteConversation,
    startRename,
    saveTitle,
    streamAsk,
    send,
    exportPdf,
    explain,
    like,
    copy,
    copySql,
    downloadCsv,
    rate,
    colDecimals,
    format,
    isNum,
    drawChart: (m: ChatMessage) => {
      void chartApi().then(api => api.drawChart(m, useUiStore().lang))
    },
    ensureChart: (m: ChatMessage) => {
      void chartApi().then(api => api.ensureChart(m, useUiStore().lang))
    },
    redrawCharts: (msgs?: ChatMessage[]) => {
      withLoadedCharts(api => api.redrawCharts(msgs ?? messages.value, useUiStore().lang))
    },
    reset,
    botFields,
    addBot,
  }
})
