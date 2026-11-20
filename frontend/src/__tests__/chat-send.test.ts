import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'
import { sessionStore } from '@/lib/storage'

function sseChunk(events: unknown[]) {
  return events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('')
}

function streamBody(payload: string, opts?: { gate?: Promise<void>; onFirstRead?: () => void }) {
  const bytes = new TextEncoder().encode(payload)
  let offset = 0
  let first = true
  return {
    getReader: () => ({
      read: vi.fn(async () => {
        if (first) {
          first = false
          opts?.onFirstRead?.()
          if (opts?.gate) await opts.gate
        }
        if (offset >= bytes.length) return { done: true, value: undefined }
        const value = bytes.slice(offset)
        offset = bytes.length
        return { done: false, value }
      }),
      cancel: vi.fn().mockResolvedValue(undefined),
    }),
  }
}

function mockFetchByUrl(handlers: Record<string, (url: string, init?: RequestInit) => Promise<unknown>>) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const path = String(url).split('?')[0]!
    for (const key of Object.keys(handlers)) {
      if (path === key || path.endsWith(key)) return handlers[key]!(path, init)
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
  })
}

describe('chat send / streamAsk', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStore.del('token')
    sessionStore.del('user')
    const auth = useAuthStore()
    auth.token = 'tok'
    auth.user = {
      username: 'pedro',
      role: 'imperador',
      modules: ['sql', 'forecast', 'orders'],
    }
    auth.wireApi()
    useUiStore()
    vi.unstubAllGlobals()
  })

  it('clears loading on done without tokens and sets shown from answer', async () => {
    const payload = sseChunk([
      { type: 'status', step: 'classify' },
      {
        type: 'data',
        kind: 'orders',
        columns: ['ingredient'],
        rows: [['Pão']],
      },
      {
        type: 'done',
        kind: 'orders',
        answer: 'Encomenda 12 pães.',
        conversation_id: 99,
      },
    ])
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: true,
          status: 200,
          body: streamBody(payload),
          json: async () => ({}),
        }),
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [{ id: 99, title: 'Encomenda' }],
        }),
      }),
    )

    const chat = useChatStore()
    await chat.send('Que ingredientes?')

    expect(chat.loading).toBe(false)
    expect(chat.streaming).toBe(false)
    const bot = chat.messages.find(m => m.from === 'bot' && !m.welcome)
    expect(bot?.text).toBe('Encomenda 12 pães.')
    expect(bot?.shown).toBe('Encomenda 12 pães.')
    expect(bot?.done).toBe(true)
    expect(chat.currentConv).toBe(99)
  })

  it('loading is true before first token, then clears', async () => {
    let release!: () => void
    const gate = new Promise<void>(r => {
      release = r
    })
    const payload = sseChunk([
      { type: 'token', text: 'Olá' },
      { type: 'done', answer: 'Olá', conversation_id: 1 },
    ])
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: true,
          status: 200,
          body: streamBody(payload, { gate }),
          json: async () => ({}),
        }),
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [],
        }),
      }),
    )

    const chat = useChatStore()
    const p = chat.send('hi')
    await Promise.resolve()
    await Promise.resolve()
    expect(chat.loading).toBe(true)
    expect(chat.streaming).toBe(true)
    release()
    await p
    expect(chat.loading).toBe(false)
    const bot = chat.messages.find(m => m.from === 'bot')
    expect(bot?.shown).toContain('Olá')
  })

  it('calls parser.end() so leftover buffer without trailing blank line is processed', async () => {
    const payload =
      'data: {"type":"token","text":"Hi"}\n\n' +
      'data: {"type":"done","answer":"Hi","conversation_id":3}'
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: true,
          status: 200,
          body: streamBody(payload),
          json: async () => ({}),
        }),
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [],
        }),
      }),
    )

    const chat = useChatStore()
    await chat.send('hi')
    const bot = chat.messages.find(m => m.from === 'bot')
    expect(bot?.text).toBe('Hi')
    expect(bot?.shown).toBe('Hi')
    expect(chat.currentConv).toBe(3)
  })

  it('stream drop before done recovers with network error and re-selects server conversation', async () => {
    const partial = sseChunk([{ type: 'token', text: 'Parcial…' }])
    const bytes = new TextEncoder().encode(partial)
    let reads = 0
    const reader = {
      read: vi.fn(async () => {
        reads++
        if (reads === 1) return { done: false, value: bytes }
        throw new TypeError('network cut')
      }),
      cancel: vi.fn().mockResolvedValue(undefined),
    }
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: true,
          status: 200,
          body: { getReader: () => reader },
          json: async () => ({}),
        }),
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [{ id: 42, title: 'cut' }],
        }),
      }),
    )

    const chat = useChatStore()
    const ui = useUiStore()
    await chat.send('cut')
    expect(chat.loading).toBe(false)
    expect(chat.streaming).toBe(false)
    const bot = chat.messages.find(m => m.from === 'bot')
    expect(bot?.error).toBe(true)
    expect(bot?.text).toBe(ui.t.network)
    expect(chat.currentConv).toBe(42)
  })

  it('SSE error event becomes an error bubble', async () => {
    const payload = sseChunk([{ type: 'error', message: 'SQL inválido' }])
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: true,
          status: 200,
          body: streamBody(payload),
          json: async () => ({}),
        }),
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [],
        }),
      }),
    )

    const chat = useChatStore()
    await chat.send('bad')
    const bot = chat.messages.find(m => m.from === 'bot')
    expect(bot?.error).toBe(true)
    expect(bot?.text).toBe('SQL inválido')
  })

  it('401 on stream logs out and clears chat', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: false,
          status: 401,
          body: null,
          json: async () => ({ detail: 'no' }),
        }),
      }),
    )
    const push = vi.fn()
    const auth = useAuthStore()
    auth.wireApi({ push } as never)
    sessionStore.set('token', 'tok')

    const chat = useChatStore()
    chat.messages = [
      {
        id: 1,
        from: 'user',
        text: 'x',
        shown: 'x',
        done: true,
        time: '',
        rows: [],
        showTable: false,
        showSql: false,
        liked: false,
        copied: false,
        sqlCopied: false,
        explanation: '',
        explaining: false,
      },
    ]
    await chat.send('secret')

    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(chat.messages).toEqual([])
    expect(chat.loading).toBe(false)
    expect(chat.streaming).toBe(false)
  })

  it('one-question guard ignores second send while streaming', async () => {
    let release!: () => void
    const gate = new Promise<void>(r => {
      release = r
    })
    const payload = sseChunk([
      { type: 'token', text: 'A' },
      { type: 'done', answer: 'A', conversation_id: 1 },
    ])
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: true,
          status: 200,
          body: streamBody(payload, { gate }),
          json: async () => ({}),
        }),
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [],
        }),
      }),
    )

    const chat = useChatStore()
    const first = chat.send('one')
    await Promise.resolve()
    await Promise.resolve()
    expect(chat.streaming).toBe(true)
    await chat.send('two')
    release()
    await first
    const users = chat.messages.filter(m => m.from === 'user')
    expect(users).toHaveLength(1)
    expect(users[0]?.text).toBe('one')
  })

  it('logout mid-stream aborts signal after first chunk and leaves clean chat', async () => {
    const first = sseChunk([{ type: 'token', text: 'Tarde' }])
    const rest = sseChunk([{ type: 'done', answer: 'Tarde demais', conversation_id: 5 }])
    let savedSignal: AbortSignal | undefined
    let reads = 0
    const reader = {
      read: vi.fn(async () => {
        reads++
        if (reads === 1) {
          return { done: false, value: new TextEncoder().encode(first) }
        }
        await new Promise<void>((_resolve, reject) => {
          if (savedSignal?.aborted) {
            reject(new DOMException('Aborted', 'AbortError'))
            return
          }
          savedSignal?.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true },
          )
        })
        return { done: false, value: new TextEncoder().encode(rest) }
      }),
      cancel: vi.fn().mockResolvedValue(undefined),
    }
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async (_url, init) => {
          savedSignal = init?.signal ?? undefined
          return {
            ok: true,
            status: 200,
            body: { getReader: () => reader },
            json: async () => ({}),
          }
        },
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [],
        }),
      }),
    )

    const chat = useChatStore()
    const auth = useAuthStore()
    const p = chat.send('bye')
    await vi.waitFor(() => {
      expect(chat.messages.some(m => m.from === 'bot' && m.shown?.includes('Tarde'))).toBe(true)
    })
    expect(savedSignal).toBeTruthy()
    expect(savedSignal!.aborted).toBe(false)

    auth.logout()
    expect(savedSignal!.aborted).toBe(true)
    expect(chat.messages).toEqual([])
    expect(chat.loading).toBe(false)
    expect(chat.streaming).toBe(false)

    await p
    expect(chat.messages).toEqual([])
    expect(chat.messages.some(m => m.text?.includes('Tarde'))).toBe(false)
  })

  it('deleteConversation of the active conversation is blocked while streaming', async () => {
    let release!: () => void
    const gate = new Promise<void>(r => {
      release = r
    })
    const payload = sseChunk([{ type: 'done', answer: 'ok', conversation_id: 7 }])
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: true,
          status: 200,
          body: streamBody(payload, { gate }),
          json: async () => ({}),
        }),
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [{ id: 7, title: 'active' }],
        }),
      }),
    )
    const chat = useChatStore()
    const ui = useUiStore()
    const confirm = vi.spyOn(ui, 'confirmDialog')
    chat.currentConv = 7
    chat.conversations = [{ id: 7, title: 'active', updated_at: '' }]
    const p = chat.send('q')
    await Promise.resolve()
    await Promise.resolve()
    expect(chat.streaming).toBe(true)
    await chat.deleteConversation(chat.conversations[0]!)
    expect(confirm).not.toHaveBeenCalled()
    expect(chat.currentConv).toBe(7)
    release()
    await p
  })

  it('newConversation is a no-op while streaming', async () => {
    let release!: () => void
    const gate = new Promise<void>(r => {
      release = r
    })
    const payload = sseChunk([{ type: 'done', answer: 'ok', conversation_id: 1 }])
    vi.stubGlobal(
      'fetch',
      mockFetchByUrl({
        '/ask/stream': async () => ({
          ok: true,
          status: 200,
          body: streamBody(payload, { gate }),
          json: async () => ({}),
        }),
        '/conversations': async () => ({
          ok: true,
          status: 200,
          json: async () => [],
        }),
        '/alerts': async () => ({
          ok: true,
          status: 200,
          json: async () => ({ alerts: [] }),
        }),
      }),
    )
    const chat = useChatStore()
    const p = chat.send('x')
    await Promise.resolve()
    await Promise.resolve()
    const before = chat.messages.length
    chat.newConversation()
    expect(chat.messages.length).toBe(before)
    release()
    await p
  })
})
