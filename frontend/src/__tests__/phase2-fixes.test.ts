/**
 * Review fixes of phase 2 part 2: languages loaded on demand, charts that wait for Chart.js
 * safely, late admin answers, the cached pending-review count, the avatar cache on logout
 * and "delete all conversations" next to a streaming answer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { nextTick } from 'vue'
import { en } from '@/i18n/generated/en'
import { fr } from '@/i18n/generated/fr'
import { pt } from '@/i18n/generated/pt'
import AppShell from '@/components/AppShell.vue'
import type { ProfileData } from '@/api/types'
import { loadAvatar } from '@/lib/avatar'
import { prefs, sessionStore } from '@/lib/storage'
import { useAdminStore } from '@/stores/admin'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useProfileStore } from '@/stores/profile'
import { COUNT_TTL_MS, useReviewStore } from '@/stores/review'
import { useUiStore } from '@/stores/ui'

// Chart.js stand-in: `gate` holds the "download"; `created` lists the canvases drawn on.
const h = vi.hoisted(() => ({ gate: Promise.resolve(), created: [] as string[] }))
vi.mock('@/lib/chartjs', async () => {
  await h.gate
  class Chart {
    constructor(el: HTMLCanvasElement) {
      h.created.push(el.id)
    }
    destroy() {}
  }
  return { Chart }
})

function deferred<T = void>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>(r => {
    resolve = r
  })
  return { promise, resolve }
}

const ok = (body: unknown) => ({
  ok: true,
  status: 200,
  json: async () => body,
  blob: async () => new Blob(['x'], { type: 'image/webp' }),
})

function loginAs(username: string, modules: string[]) {
  const auth = useAuthStore()
  auth.token = 'tok'
  auth.user = { username, role: 'loja', modules }
  sessionStore.set('token', 'tok')
  auth.wireApi()
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.unstubAllGlobals()
  // jsdom has no matchMedia; the shell asks it whether this is the mobile layout
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
  prefs.set('lang', 'en')
  void useUiStore().setLang('en', false)
  h.created.length = 0
  h.gate = Promise.resolve()
  document.body.innerHTML = ''
})

afterEach(() => {
  vi.useRealTimers()
})

// ---------- languages ----------

describe('languages are loaded on demand', () => {
  it('starts with none, shares one request per language and falls back to what is loaded', async () => {
    vi.resetModules()
    const i18n = await import('@/i18n') // a fresh copy: nothing loaded yet
    expect(i18n.LANG_CODES.some(l => i18n.isLoaded(l))).toBe(false)
    expect(() => i18n.t('fr')).toThrow()

    const a = i18n.loadLang('pt')
    expect(i18n.loadLang('pt')).toBe(a) // one download for concurrent calls
    await a
    expect(i18n.t('pt').send).toBe(pt.send)
    expect(i18n.t('fr').send).toBe(pt.send) // fr not loaded: falls back to what is
    await i18n.loadLang('en')
    expect(i18n.t('fr').send).toBe(en.send) // English is the preferred fallback
    await i18n.loadLang('fr')
    expect(i18n.t('fr').send).toBe(fr.send)
  })

  it('the texts follow a language that loads later, even if the chosen language did not change', async () => {
    // Start-up: the Portuguese chunk failed, main.ts fell back to English; lang is still 'pt'
    vi.resetModules()
    const i18n = await import('@/i18n')
    await i18n.loadLang('en')
    prefs.set('lang', 'pt')
    const { useUiStore: freshUi } = await import('@/stores/ui')
    setActivePinia(createPinia())
    const ui = freshUi()
    expect(ui.lang).toBe('pt')
    expect(ui.t.send).toBe(en.send) // English while Portuguese is missing
    await nextTick()
    expect(document.documentElement.lang).toBe('en') // screen readers: the text is English

    await ui.setLang('pt', false) // the user picks Portuguese again: now it downloads
    expect(ui.lang).toBe('pt') // unchanged…
    expect(ui.t.send).toBe(pt.send) // …but the texts are Portuguese now
    await nextTick()
    expect(document.documentElement.lang).toBe('pt')
  })

  it('switching language keeps the current one until the new one is loaded; last switch wins', async () => {
    vi.resetModules()
    const i18n = await import('@/i18n')
    await i18n.loadLang('en')
    const { useUiStore: freshUi } = await import('@/stores/ui')
    setActivePinia(createPinia())
    prefs.del('lang')
    const ui = freshUi()
    expect(ui.lang).toBe('en')

    const p = ui.setLang('fr', false)
    expect(i18n.isLoaded('fr')).toBe(false)
    expect(ui.lang).toBe('en') // still English while French downloads
    expect(ui.t.send).toBe(en.send)
    await p
    expect(ui.lang).toBe('fr')
    expect(ui.t.send).toBe(fr.send)
    expect(document.documentElement.lang).toBe('fr')

    const slow = ui.setLang('es', false)
    const fast = ui.setLang('fr', false) // already loaded: immediate
    await Promise.all([slow, fast])
    expect(ui.lang).toBe('fr') // the late Spanish download does not override it
  })
})

// ---------- charts ----------

describe('charts that wait for Chart.js', () => {
  const DASH = { top_stores: [{ store: 'Maia', revenue: 10 }] }
  const LABELS = { revenue: 'r', margin: 'm', forecast: 'f' }
  const ADMIN = { daily: [{ day: '2026-11-19', requests: 3, errors: 1 }], eval_history: [] }
  const ADMIN_LABELS = { ok: 'ok', failed: 'failed', accuracy: 'acc' }

  async function fresh<T>(path: string, gate: Promise<void>): Promise<T> {
    vi.resetModules() // Chart.js "not downloaded yet" again
    h.gate = gate
    return (await import(/* @vite-ignore */ path)) as T
  }
  type Dash = typeof import('@/lib/dash-charts')
  type Adm = typeof import('@/lib/admin-charts')

  it('dashboard: draws nothing if the page closed during the download', async () => {
    const dl = deferred()
    const dash = await fresh<Dash>('@/lib/dash-charts', dl.promise)
    document.body.innerHTML = '<canvas id="dash-stores"></canvas>'
    const p = dash.drawDashCharts(DASH, LABELS, 'en')
    dash.destroyDashCharts() // DashboardView unmounted → store reset
    dl.resolve()
    await p
    expect(h.created).toEqual([])
    expect(dash.dashChartCount()).toBe(0)
  })

  it('dashboard: draws nothing on a canvas that left the page', async () => {
    const dl = deferred()
    const dash = await fresh<Dash>('@/lib/dash-charts', dl.promise)
    document.body.innerHTML = '<canvas id="dash-stores"></canvas>'
    const p = dash.drawDashCharts(DASH, LABELS, 'en')
    document.body.innerHTML = ''
    dl.resolve()
    await p
    expect(h.created).toEqual([])
  })

  it('dashboard: draws once Chart.js arrives if the page is still there', async () => {
    const dl = deferred()
    const dash = await fresh<Dash>('@/lib/dash-charts', dl.promise)
    document.body.innerHTML = '<canvas id="dash-stores"></canvas>'
    const p = dash.drawDashCharts(DASH, LABELS, 'en')
    dl.resolve()
    await p
    expect(h.created).toEqual(['dash-stores'])
    expect(dash.dashChartCount()).toBe(1)
  })

  it('admin: same checks', async () => {
    const dl = deferred()
    const adm = await fresh<Adm>('@/lib/admin-charts', dl.promise)
    document.body.innerHTML = '<canvas id="adm-daily"></canvas>'
    const closed = adm.drawAdminCharts(ADMIN, ADMIN_LABELS, 'en')
    adm.destroyAdminCharts()
    dl.resolve()
    await closed
    expect(h.created).toEqual([])

    await adm.drawAdminCharts(ADMIN, ADMIN_LABELS, 'en') // page still open
    expect(h.created).toEqual(['adm-daily'])
    expect(adm.adminChartCount()).toBe(1)
  })
})

// ---------- admin period ----------

function metrics(requests: number) {
  return {
    summary: { requests },
    daily: [],
    eval_history: [],
  }
}

describe('admin metrics', () => {
  function serveByDays() {
    const replies: Record<string, ReturnType<typeof deferred<unknown>>> = {}
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        const days = new URL(url, 'http://x').searchParams.get('days')!
        replies[days] ??= deferred<unknown>()
        return replies[days].promise.then(ok)
      }),
    )
    return (days: string) => (replies[days] ??= deferred<unknown>())
  }

  it('a late answer for an old period never replaces the latest one', async () => {
    loginAs('pedro', ['observability'])
    const reply = serveByDays()
    const adm = useAdminStore()
    const first = adm.load(1)
    const second = adm.load(90)
    reply('90').resolve(metrics(90))
    await second
    reply('1').resolve(metrics(1)) // arrives last
    await first
    expect(adm.days).toBe(90)
    expect(adm.data?.summary.requests).toBe(90)
    expect(adm.loading).toBe(false)
  })

  it('an answer arriving after the page closed is dropped', async () => {
    loginAs('pedro', ['observability'])
    const reply = serveByDays()
    const adm = useAdminStore()
    const p = adm.load(7)
    adm.reset()
    reply('7').resolve(metrics(7))
    await p
    expect(adm.data).toBeNull()
    expect(adm.loading).toBe(false)
  })

  it('"updated at" is formatted with the chosen language\'s locale, not the browser\'s', async () => {
    // The four app locales all write 15:05, so the formatted text proves nothing: check the
    // locale handed to the formatter (the old code passed undefined = browser locale).
    loginAs('pedro', ['observability'])
    const reply = serveByDays()
    reply('7').resolve(metrics(7))
    const adm = useAdminStore()
    await adm.load(7)
    const spy = vi.spyOn(Date.prototype, 'toLocaleTimeString')
    try {
      for (const [lang, locale] of [['fr', 'fr-FR'], ['pt', 'pt-PT'], ['en', 'en-GB']] as const) {
        await useUiStore().setLang(lang, false)
        spy.mockClear()
        expect(adm.updated).not.toBeNull() // re-formatted for the new language
        expect(spy).toHaveBeenCalledTimes(1)
        expect(spy.mock.calls[0]![0]).toBe(locale)
      }
    } finally {
      spy.mockRestore()
    }
  })

  it('the period buttons are disabled while loading', async () => {
    loginAs('pedro', ['observability'])
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(ok({ pending: 0 }))))
    const router = createRouter({
      history: createMemoryHistory('/'),
      routes: [{ path: '/admin', name: 'admin', component: { template: '<div />' } }],
    })
    await router.push('/admin')
    await router.isReady()
    const adm = useAdminStore()
    adm.loading = true
    const w = mount(AppShell, {
      global: { plugins: [router], stubs: { LangPicker: true, UserAvatar: true } },
    })
    await nextTick()
    const buttons = w.findAll('.topbar-actions .segmented button')
    expect(buttons.length).toBe(4)
    expect(buttons.every(b => b.attributes('disabled') !== undefined)).toBe(true)
    adm.loading = false
    await nextTick()
    expect(buttons.every(b => b.attributes('disabled') === undefined)).toBe(true)
    w.unmount()
  })
})

// ---------- pending-review count ----------

describe('pending-review count', () => {
  function serveCount() {
    const calls: string[] = []
    let n = 4
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url === '/review') calls.push(url)
        return Promise.resolve(ok({ pending: n++ }))
      }),
    )
    return calls
  }

  it('is fetched once per minute for the same account, even with concurrent calls', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 20, 10, 0))
    loginAs('ana', ['sql', 'teach'])
    const calls = serveCount()
    const review = useReviewStore()

    await Promise.all([review.loadCount(), review.loadCount()])
    await review.loadCount()
    expect(calls).toHaveLength(1)
    expect(review.pending).toBe(4)

    vi.setSystemTime(Date.now() + COUNT_TTL_MS + 1)
    await review.loadCount()
    expect(calls).toHaveLength(2)
    expect(review.pending).toBe(5)
  })

  it('another account starts from zero and asks again; without "teach" nothing is asked', async () => {
    loginAs('ana', ['teach'])
    const calls = serveCount()
    const review = useReviewStore()
    await review.loadCount()
    expect(review.pending).toBe(4)

    loginAs('rui', ['teach'])
    const p = review.loadCount()
    expect(review.pending).toBe(0) // not ana's count while rui's arrives
    await p
    expect(calls).toHaveLength(2)

    loginAs('sem.teach', ['sql'])
    await review.loadCount()
    expect(review.pending).toBe(0)
    expect(calls).toHaveLength(2)
  })

  it('navigating between pages (the shell mounted again) does not ask again', async () => {
    loginAs('ana', ['teach'])
    const calls = serveCount()
    const router = createRouter({
      history: createMemoryHistory('/'),
      routes: [{ path: '/:p(.*)', name: 'page', component: { template: '<div />' } }],
    })
    await router.push('/profile')
    await router.isReady()
    for (let i = 0; i < 3; i++) {
      const w = mount(AppShell, {
        global: { plugins: [router], stubs: { LangPicker: true, UserAvatar: true } },
      })
      await flushPromises()
      w.unmount()
    }
    expect(calls).toHaveLength(1)
  })
})

// ---------- logout and the avatar cache ----------

describe('logout', () => {
  it('drops the cached avatars', async () => {
    loginAs('ana', ['sql'])
    const fetchMock = vi.fn(() => Promise.resolve(ok({})))
    vi.stubGlobal('fetch', fetchMock)
    const url = '/avatars/ana.webp?v=1'
    await loadAvatar(url, 'tok')
    await loadAvatar(url, 'tok')
    expect(fetchMock).toHaveBeenCalledTimes(1) // cached

    useAuthStore().logout()
    await loadAvatar(url, 'tok')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

// ---------- delete all conversations ----------

describe('delete all conversations', () => {
  const PROFILE = { stats: { conversations: 2, questions: 3 } } as ProfileData

  it('is refused while an answer is streaming (and the stream is left alone)', async () => {
    loginAs('ana', ['sql'])
    const fetchMock = vi.fn(() => Promise.resolve(ok({})))
    vi.stubGlobal('fetch', fetchMock)
    const chat = useChatStore()
    chat.streaming = true
    chat.conversations = [{ id: 1, title: 'a' }]
    const profile = useProfileStore()
    profile.profile = PROFILE

    await profile.deleteAllConversations()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(useUiStore().toasts.map(x => x.text)).toContain(en.p.clearBusy)
    expect(chat.streaming).toBe(true)
    expect(chat.conversations).toHaveLength(1)
    expect(chat.forgetConversations()).toBe(false)
  })

  it('otherwise empties the chat list without the logout reset', async () => {
    loginAs('ana', ['sql'])
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init: RequestInit = {}) => {
        calls.push(`${init.method || 'GET'} ${url}`)
        return Promise.resolve(ok(url === '/profile' ? PROFILE : {}))
      }),
    )
    const chat = useChatStore()
    chat.conversations = [{ id: 1, title: 'a' }]
    chat.currentConv = 1
    chat.question = 'rascunho' // a reset() would clear what is being typed
    const profile = useProfileStore()
    profile.profile = PROFILE

    const p = profile.deleteAllConversations()
    await nextTick()
    useUiStore().closeDialog(true)
    await p
    expect(calls).toContain('DELETE /conversations')
    expect(chat.conversations).toEqual([])
    expect(chat.currentConv).toBeNull()
    expect(chat.question).toBe('rascunho')
  })
})
