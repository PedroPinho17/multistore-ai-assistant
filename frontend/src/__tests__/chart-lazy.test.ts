import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'

// O módulo de gráficos (Chart.js) é simulado: `loaded` conta quantas vezes foi importado.
const spy = vi.hoisted(() => ({
  loaded: 0,
  clearCharts: (() => undefined) as () => void,
  drawChart: (() => undefined) as () => void,
}))
vi.mock('@/lib/chart', () => {
  spy.loaded++
  return {
    clearCharts: (...a: unknown[]) => (spy.clearCharts as (...x: unknown[]) => void)(...a),
    drawChart: (...a: unknown[]) => (spy.drawChart as (...x: unknown[]) => void)(...a),
    ensureChart: () => undefined,
    redrawCharts: () => undefined,
    destroyChart: () => undefined,
  }
})

/** Dá tempo a um import dinâmico que tivesse começado de chegar à factory do mock. */
async function settle() {
  await nextTick()
  await new Promise(r => setTimeout(r, 50))
}

// O estado "módulo carregado" é do módulo do chat store (partilhado no ficheiro):
// os testes que não carregam o Chart.js têm de vir antes do que o carrega.
describe('Chart.js is never downloaded just to clear or redraw', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.token = 'tok'
    auth.user = { username: 'pedro', role: 'imperador', modules: ['sql'] }
    auth.wireApi()
    vi.unstubAllGlobals()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: async () => (String(url).startsWith('/conversations/') ? [] : { alerts: [] }),
        }),
      ),
    )
  })

  it('reset, newConversation, openConversation and a theme switch do not load it', async () => {
    const chat = useChatStore()
    const ui = useUiStore()
    chat.newConversation()
    await chat.openConversation(5)
    ui.setTheme(ui.theme === 'dark' ? 'light' : 'dark')
    chat.redrawCharts()
    chat.reset()
    useAuthStore().logout()
    await settle()
    expect(spy.loaded).toBe(0)
  })

  it('once a chart was drawn, reset clears the charts right away', async () => {
    const chat = useChatStore()
    const clear = vi.fn()
    const draw = vi.fn()
    spy.clearCharts = clear
    spy.drawChart = draw
    chat.drawChart({ id: 1 } as never)
    await vi.waitFor(() => expect(draw).toHaveBeenCalledTimes(1)) // o import dinâmico acabou
    expect(spy.loaded).toBe(1)

    chat.reset()
    expect(clear).toHaveBeenCalledTimes(1) // síncrono: o módulo já está carregado
    chat.newConversation()
    expect(clear).toHaveBeenCalledTimes(2)
    expect(spy.loaded).toBe(1)
  })
})
