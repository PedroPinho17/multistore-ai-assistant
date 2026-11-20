/**
 * Phase 2 pages, mounted for real (only the shell, avatar and language picker are stubbed).
 * Everything is checked in English with the exact texts of the EN locale; the API is a
 * fake `fetch` that records every request.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { nextTick } from 'vue'
import { en } from '@/i18n/generated/en'
import HomeView from '@/views/HomeView.vue'
import DashboardView from '@/views/DashboardView.vue'
import ProfileView from '@/views/ProfileView.vue'
import SettingsView from '@/views/SettingsView.vue'
import UsersView from '@/views/UsersView.vue'
import AdminView from '@/views/AdminView.vue'
import ReviewView from '@/views/ReviewView.vue'
import realRouter from '@/router'
import type { User } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useReviewStore } from '@/stores/review'
import { useUiStore } from '@/stores/ui'
import { useUsersStore } from '@/stores/users'
import { prefs, sessionStore } from '@/lib/storage'

vi.mock('@/lib/dash-charts', () => ({
  drawDashCharts: vi.fn().mockResolvedValue(undefined),
  destroyDashCharts: vi.fn(),
}))
vi.mock('@/lib/admin-charts', () => ({
  drawAdminCharts: vi.fn().mockResolvedValue(undefined),
  destroyAdminCharts: vi.fn(),
}))

// ---------- fake API ----------

interface Call {
  method: string
  path: string
  body: unknown
  contentType?: string
}
interface Failure {
  fail: number
  body: unknown
}
type Handler = (call: Call) => unknown

const fail = (status: number, detail: unknown = 'boom'): Failure => ({
  fail: status,
  body: { detail },
})

/** Routes are "METHOD /path" (query string ignored). Unknown routes answer {}. */
function serve(routes: Record<string, Handler | unknown>): Call[] {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = (init.method || 'GET').toUpperCase()
      const path = String(url).split('?')[0]!
      const headers = (init.headers || {}) as Record<string, string>
      let body: unknown = init.body
      if (typeof body === 'string') {
        try {
          body = JSON.parse(body)
        } catch {
          /* keep raw */
        }
      }
      const call: Call = { method, path, body, contentType: headers['Content-Type'] }
      calls.push(call)
      const route = routes[`${method} ${path}`]
      const out = typeof route === 'function' ? await (route as Handler)(call) : (route ?? {})
      if (out && typeof out === 'object' && 'fail' in out) {
        const f = out as Failure
        return { ok: false, status: f.fail, statusText: 'Error', json: async () => f.body }
      }
      return { ok: true, status: 200, json: async () => out, blob: async () => new Blob() }
    }),
  )
  return calls
}

const sent = (calls: Call[], method: string, path: string) =>
  calls.filter(c => c.method === method && c.path === path)

function deferred<T = unknown>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>(r => {
    resolve = r
  })
  return { promise, resolve }
}

// ---------- mounting ----------

const ADMIN: User = {
  username: 'pedro',
  role: 'admin',
  modules: ['sql', 'forecast', 'users', 'observability', 'teach'],
}

function login(user: User) {
  sessionStore.set('token', 'tok')
  sessionStore.set('user', JSON.stringify(user))
  const auth = useAuthStore()
  auth.token = 'tok'
  auth.user = user
}

let wrapper: VueWrapper | null = null

async function mountView(View: object, path: string) {
  const router = createRouter({
    history: createMemoryHistory('/app/'),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/chat', name: 'chat', component: { template: '<div />' } },
      { path: '/login', name: 'login', component: { template: '<div />' } },
      { path: '/:p(.*)', name: 'page', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  wrapper = mount(View as never, {
    attachTo: document.body,
    global: {
      plugins: [router],
      stubs: {
        AppShell: { template: '<div class="shell-stub"><slot /></div>' },
        LangPicker: true,
        UserAvatar: true,
      },
    },
  })
  await flushPromises()
  await nextTick()
  return wrapper
}

const toastTexts = () => useUiStore().toasts.map(x => x.text)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.unstubAllGlobals()
  prefs.set('lang', 'en')
  login(ADMIN)
  useAuthStore().wireApi()
  void useUiStore().setLang('en', false) // loaded by test-setup.ts: switches at once
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.useRealTimers()
})

// ---------- home ----------

describe('HomeView', () => {
  it('renders the hero title', async () => {
    serve({})
    useAuthStore().token = null
    const w = await mountView(HomeView, '/')
    expect(w.find('h1').text()).toBe(en.h.title)
  })

  it('types the demo answer progressively, character by character', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    serve({})
    const w = await mountView(HomeView, '/')
    const script = en.h.demo[0]!
    const bubbles = () => w.findAll('.demo-body .msg.bot .bubble')

    expect(w.find('.demo-body .msg.user .bubble').text()).toBe(script.q)
    await vi.advanceTimersByTimeAsync(700 + 1300) // question shown, then "typing…"
    expect(bubbles()).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(150)
    const partial = bubbles()[0]!.text()
    expect(partial.length).toBeGreaterThan(0)
    expect(partial.length).toBeLessThan(script.a.length)
    expect(script.a.startsWith(partial)).toBe(true)

    await vi.advanceTimersByTimeAsync(150)
    const more = bubbles()[0]!.text()
    expect(more.length).toBeGreaterThan(partial.length) // it keeps growing on screen

    await vi.advanceTimersByTimeAsync(script.a.length * 20)
    expect(bubbles()[0]!.text().startsWith(script.a)).toBe(true)
    expect(w.find('.demo-body .msg.bot .caret').exists()).toBe(false)
  })
})

// ---------- dashboard ----------

const DASH = {
  revenue: { this_month_to_date: 1000, last_month_same_days: 900, change_pct: 11.1, days: 20 },
  top_stores: [],
  margin_by_brand: [],
}

describe('DashboardView', () => {
  it('shows skeletons while loading, then the KPIs', async () => {
    const reply = deferred()
    serve({ 'GET /dashboard': () => reply.promise })
    const w = await mountView(DashboardView, '/dashboard')
    expect(w.findAll('.kpi .skeleton')).toHaveLength(2)

    reply.resolve(DASH)
    await flushPromises()
    expect(w.findAll('.kpi .skeleton')).toHaveLength(0)
    const labels = w.findAll('.kpi .label').map(x => x.text())
    expect(labels).toEqual([en.dash.thisMonth, en.dash.lastMonth])
    expect(w.findAll('.kpi .value').map(x => x.text())).toEqual(['€1,000', '€900'])
    expect(w.text()).toContain(en.dash.changeUp(11.1))
    expect(w.text()).toContain(en.dash.noStores)
  })

  it('shows the error', async () => {
    serve({ 'GET /dashboard': fail(500, 'Base de dados em baixo') })
    const w = await mountView(DashboardView, '/dashboard')
    expect(w.find('.error').text()).toBe('Base de dados em baixo')
    expect(w.findAll('.kpi .skeleton')).toHaveLength(0)
  })
})

// ---------- profile ----------

const PROFILE = {
  email: 'a@b.pt',
  stats: { conversations: 2, questions: 5, by_kind: { sql: 3 } },
  visible_stores: 15,
}

describe('ProfileView', () => {
  it('renders the profile sections', async () => {
    serve({ 'GET /profile': PROFILE })
    const w = await mountView(ProfileView, '/profile')
    expect(w.text()).toContain('pedro')
    const titles = w.findAll('h2').map(x => x.text())
    expect(titles).toContain(en.p.pwTitle)
    expect(titles).toContain(en.p.emailTitle)
  })

  it('says when the profile cannot be loaded', async () => {
    serve({ 'GET /profile': fail(500) })
    await mountView(ProfileView, '/profile')
    expect(toastTexts()).toContain('boom')
  })

  async function pickFile(w: VueWrapper, file: File) {
    const input = w.find('#avatar-file')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
  }

  it('rejects an avatar of the wrong type or too big, without uploading', async () => {
    const calls = serve({ 'GET /profile': PROFILE })
    const w = await mountView(ProfileView, '/profile')

    await pickFile(w, new File(['gif'], 'a.gif', { type: 'image/gif' }))
    const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'a.png', { type: 'image/png' })
    await pickFile(w, big)

    expect(toastTexts().filter(x => x === en.avatar.bad)).toHaveLength(2)
    expect(sent(calls, 'POST', '/me/avatar')).toHaveLength(0)
  })

  it('uploads a valid avatar with its own content type', async () => {
    const calls = serve({
      'GET /profile': PROFILE,
      'POST /me/avatar': { avatar_url: '/avatars/pedro.webp?v=2' },
      'GET /me': { ...ADMIN, avatar_url: '/avatars/pedro.webp?v=2' }, // refreshed after upload
    })
    const w = await mountView(ProfileView, '/profile')
    await pickFile(w, new File(['png'], 'me.png', { type: 'image/png' }))

    const up = sent(calls, 'POST', '/me/avatar')
    expect(up).toHaveLength(1)
    expect(up[0]!.contentType).toBe('image/png')
    expect(useAuthStore().user?.avatar_url).toBe('/avatars/pedro.webp?v=2')
    expect(toastTexts()).toContain(en.avatar.saved)
  })

  it('checks the password rules before sending', async () => {
    const calls = serve({ 'GET /profile': PROFILE, 'POST /profile/password': { token: 'new' } })
    const w = await mountView(ProfileView, '/profile')
    const submit = async (current: string, next: string, confirm = next) => {
      await w.find('#pw-current').setValue(current)
      await w.find('#pw-new').setValue(next)
      await w.find('#pw-confirm').setValue(confirm)
      await w.find('#pw-new').element.closest('form')!.dispatchEvent(new Event('submit'))
      await flushPromises()
      return w.find('.error[role="alert"]').exists() ? w.find('.error[role="alert"]').text() : ''
    }

    expect(await submit('old-pass1', 'abc12')).toBe(en.p.errShort)
    expect(await submit('old-pass1', '12345678')).toBe(en.p.errMix)
    expect(await submit('old-pass1', 'pedro2026!')).toBe(en.p.errUser)
    expect(await submit('old-pass1', 'old-pass1')).toBe(en.p.errSame)
    expect(await submit('old-pass1', 'Nova#Senha9', 'other')).toBe(en.p.errMatch)
    expect(sent(calls, 'POST', '/profile/password')).toHaveLength(0)

    expect(await submit('old-pass1', 'Nova#Senha9')).toBe('')
    const req = sent(calls, 'POST', '/profile/password')
    expect(req.map(c => c.body)).toEqual([
      { current_password: 'old-pass1', new_password: 'Nova#Senha9' },
    ])
    expect(useAuthStore().token).toBe('new') // the server's new session (token_version)
  })

  it('does not delete all conversations while an answer is streaming', async () => {
    const calls = serve({ 'GET /profile': PROFILE })
    const chat = useChatStore()
    chat.streaming = true
    const w = await mountView(ProfileView, '/profile')

    const button = w.find('.danger-zone .btn-danger')
    expect(button.attributes('disabled')).toBeDefined()
    expect(w.find('.danger-zone').text()).toContain(en.p.clearBusy)
    await button.trigger('click')
    await flushPromises()
    expect(sent(calls, 'DELETE', '/conversations')).toHaveLength(0)
    expect(chat.streaming).toBe(true) // the stream was not cancelled
  })
})

// ---------- settings ----------

const APP_SETTINGS = {
  values: { default_accent: 'green', default_lang: 'en', show_demo_accounts: true, session_hours: 8 },
  options: { session_hours: [4, 8, 24] },
}

describe('SettingsView', () => {
  it('shows the app section to an admin', async () => {
    const calls = serve({ 'GET /settings/app': APP_SETTINGS })
    const w = await mountView(SettingsView, '/settings')
    expect(w.find('#st-look').text()).toBe(en.st.appearance)
    expect(w.find('#st-app').text()).toBe(en.st.appTitle)
    expect(sent(calls, 'GET', '/settings/app')).toHaveLength(1)
  })

  it('hides the app section from anyone else (and does not ask for it)', async () => {
    login({ username: 'pedro', role: 'imperador', modules: ['sql', 'users'] })
    const calls = serve({ 'GET /settings/app': APP_SETTINGS })
    const w = await mountView(SettingsView, '/settings')
    expect(w.find('#st-look').exists()).toBe(true)
    expect(w.find('#st-app').exists()).toBe(false)
    expect(sent(calls, 'GET', '/settings/app')).toHaveLength(0)
  })

  it('says when the app settings cannot be loaded', async () => {
    serve({ 'GET /settings/app': fail(500) })
    const w = await mountView(SettingsView, '/settings')
    expect(toastTexts()).toContain('boom')
    expect(w.find('#st-app').exists()).toBe(false)
  })
})

// ---------- users ----------

const OPTIONS = {
  roles: ['marca', 'loja'],
  brands: [{ id: 1, name: 'BurgerLab' }],
  stores: [{ id: 3, name: 'BurgerLab Maia', brand_id: 1 }],
  modules: { marca: ['sql', 'forecast', 'orders'], loja: ['sql', 'forecast', 'orders'] },
  defaults: { marca: ['sql'], loja: ['sql'] },
}

describe('UsersView', () => {
  it('renders the accounts list', async () => {
    serve({ 'GET /users': [], 'GET /users/options': OPTIONS })
    const w = await mountView(UsersView, '/users')
    expect(w.text()).toContain(en.um.count(0))
  })

  it('says when the accounts cannot be loaded', async () => {
    serve({ 'GET /users': fail(500), 'GET /users/options': OPTIONS })
    await mountView(UsersView, '/users')
    expect(toastTexts()).toContain('boom')
  })

  async function openForm() {
    const calls = serve({
      'GET /users': [],
      'GET /users/options': OPTIONS,
      'POST /users': (c: Call) => ({ username: (c.body as { username: string }).username }),
    })
    const w = await mountView(UsersView, '/users')
    useUsersStore().openNewUser() // the "New account" button lives in the (stubbed) shell
    await nextTick()
    await w.find('#nu-username').setValue('Ana.Silva')
    await w.find('#nu-password').setValue('Segura#2026x')
    return { w, calls }
  }

  it('creates an account with the chosen store and modules', async () => {
    const { w, calls } = await openForm()
    // last role preselected (loja) and the only store picked automatically
    expect((w.find('#nu-role').element as HTMLSelectElement).value).toBe('loja')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(sent(calls, 'POST', '/users').map(c => c.body)).toEqual([
      {
        username: 'ana.silva',
        password: 'Segura#2026x',
        role: 'loja',
        brand_id: null,
        store_id: 3,
        modules: ['sql'],
        email: null,
      },
    ])
    expect(toastTexts()).toContain(en.um.created('ana.silva'))
    expect(useUsersStore().form).toBeNull()
    expect(sent(calls, 'GET', '/users')).toHaveLength(2) // list reloaded
  })

  it('refuses an account without any data module', async () => {
    const { w, calls } = await openForm()
    await w.find('input[name="nu-mod-sql"]').trigger('change') // untick the only one
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('form .error').text()).toBe(en.errors.no_modules)
    expect(sent(calls, 'POST', '/users')).toHaveLength(0)
  })
})

// ---------- admin ----------

const METRICS = {
  summary: {
    requests: 12,
    users: 3,
    errors: 1,
    error_rate: 0.05,
    p50_ms: 800,
    p95_ms: 2100,
    avg_tokens: 900,
    prompt_tokens: 8000,
    completion_tokens: 2000,
    satisfaction: null,
    thumbs_up: 0,
    thumbs_down: 0,
    sql_fail_rate: 0,
    sql_recovered: 0,
    classifier_share: 0,
    cache_share: 0,
    cache_hits: 0,
  },
  daily: [],
  by_intent: [],
  by_kind: [],
  top_questions: [],
  thumbs_down: [],
  recent_errors: [],
  by_user: [],
  eval_history: [],
}

describe('AdminView', () => {
  it('renders the KPIs', async () => {
    serve({ 'GET /admin/metrics': METRICS })
    const w = await mountView(AdminView, '/admin')
    const labels = w.findAll('.kpi .label').map(x => x.text())
    expect(labels.slice(0, 2)).toEqual([en.adm.requests, en.adm.errorRate])
    expect(w.find('.kpi .value').text()).toBe('12')
    expect(w.text()).toContain(en.adm.users(3))
  })

  it('shows the error', async () => {
    serve({ 'GET /admin/metrics': fail(500) })
    const w = await mountView(AdminView, '/admin')
    expect(w.find('.error').text()).toBe('boom')
  })
})

// ---------- review ----------

const ITEM = {
  id: 7,
  question: 'Vendas de ontem?',
  answer: 'Foram 10 €.',
  sql: 'SELECT 1',
  username: 'ana',
  role: 'loja',
  created_at: '2026-11-19T10:00:00Z',
  can_teach: true,
}

describe('ReviewView', () => {
  it('renders the tabs and the empty list', async () => {
    serve({ 'GET /review': { pending: 0, items: [] } })
    const w = await mountView(ReviewView, '/review')
    expect(w.find('[role="tablist"]').exists()).toBe(true)
    expect(w.find('.empty-state').exists()).toBe(true)
  })

  it('shows the error', async () => {
    serve({ 'GET /review': fail(500) })
    const w = await mountView(ReviewView, '/review')
    expect(w.find('.error[role="alert"]').text()).toBe('boom')
  })

  it('teaches only SQL that was tested, and the exact SQL that was tested', async () => {
    const calls = serve({
      'GET /review': { pending: 2, items: [ITEM] },
      'POST /review/7/preview': { columns: ['n'], rows: [[1]], row_count: 1 },
      'POST /review/7/teach': { ok: true },
    })
    const w = await mountView(ReviewView, '/review')
    const button = (label: string) => w.findAll('.review-actions button').find(b => b.text() === label)!
    const teach = () => button(en.rv.teach)

    expect(teach().attributes('disabled')).toBeDefined() // not tested yet
    await button(en.rv.test).trigger('click')
    await flushPromises()
    expect(teach().attributes('disabled')).toBeUndefined()
    expect(w.find('.review-preview').text()).toContain(en.rv.rows(1, 1))

    await w.find('#rv-sql-7').setValue('SELECT 2') // changed after the test
    expect(teach().attributes('disabled')).toBeDefined()
    await button(en.rv.test).trigger('click')
    await flushPromises()
    await teach().trigger('click')
    await flushPromises()

    expect(sent(calls, 'POST', '/review/7/preview').map(c => c.body)).toEqual([
      { sql: 'SELECT 1' },
      { sql: 'SELECT 2' },
    ])
    expect(sent(calls, 'POST', '/review/7/teach').map(c => c.body)).toEqual([
      { question: 'Vendas de ontem?', sql: 'SELECT 2' },
    ])
    expect(w.findAll('article')).toHaveLength(0)
    expect(useReviewStore().pending).toBe(1)
    expect(toastTexts()).toContain(en.rv.taught)
  })
})

// ---------- role guards (the real router) ----------

describe('role guards', () => {
  it.each([
    ['/users', 'users'],
    ['/admin', 'observability'],
    ['/review', 'teach'],
  ])('%s without the %s module goes to the chat', async (path, module) => {
    serve({})
    login({ username: 'gerente.maia', role: 'loja', modules: ['sql'] })
    await realRouter.push(path)
    expect(realRouter.currentRoute.value.name).toBe('chat')

    login({ username: 'gestor', role: 'marca', modules: ['sql', module] })
    await realRouter.push(path)
    expect(realRouter.currentRoute.value.path).toBe(path)
  })
})
