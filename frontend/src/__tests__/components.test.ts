import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import ToastStack from '@/components/ToastStack.vue'
import LangPicker from '@/components/LangPicker.vue'
import AppShell from '@/components/AppShell.vue'
import { useUiStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { sessionStore } from '@/lib/storage'

describe('ConfirmDialog', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
  })

  it('focuses Cancel when dialog opens and restores previous focus on close', async () => {
    const opener = document.createElement('button')
    opener.textContent = 'open'
    document.body.appendChild(opener)
    opener.focus()
    expect(document.activeElement).toBe(opener)

    const ui = useUiStore()
    const wrapper = mount(ConfirmDialog, { attachTo: document.body })
    const pending = ui.confirmDialog({
      title: 'Apagar?',
      text: 'Confirma',
      confirm: 'Apagar',
      danger: true,
    })
    await nextTick()
    await flushPromises()

    const cancel = wrapper.find('.dlg-cancel').element as HTMLButtonElement
    expect(document.activeElement).toBe(cancel)

    ui.closeDialog(false)
    await pending
    await flushPromises()
    await nextTick()
    expect(document.activeElement).toBe(opener)
    wrapper.unmount()
  })
})

describe('ToastStack', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('announces via a single aria-live region without role on cards', async () => {
    const ui = useUiStore()
    const wrapper = mount(ToastStack, { attachTo: document.body })
    ui.toast('Guardado', 'ok')
    await nextTick()
    await flushPromises()

    const live = wrapper.find('[aria-live]')
    expect(live.exists()).toBe(true)
    expect(live.attributes('aria-live')).toBe('polite')
    expect(live.text()).toContain('Guardado')

    const card = wrapper.find('.toast')
    expect(card.attributes('aria-hidden')).toBe('true')
    expect(card.attributes('role')).toBeUndefined()

    ui.toast('Falhou', 'error')
    await nextTick()
    await flushPromises()
    expect(wrapper.find('[aria-live]').attributes('aria-live')).toBe('assertive')
    wrapper.unmount()
  })
})

describe('LangPicker', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('emits update when a language is picked', async () => {
    const wrapper = mount(LangPicker, {
      props: { modelValue: 'pt', label: 'Idioma' },
      attachTo: document.body,
    })
    await wrapper.find('.lp-btn').trigger('click')
    await nextTick()
    const options = wrapper.findAll('[role="option"]')
    expect(options.length).toBeGreaterThan(1)
    await options[1]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['en'])
    wrapper.unmount()
  })
})

describe('AppShell delete while streaming', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStore.del('token')
    sessionStore.del('user')
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  it('disables delete on the conversation being answered', async () => {
    const { createMemoryHistory, createRouter } = await import('vue-router')
    const router = createRouter({
      history: createMemoryHistory('/'),
      routes: [{ path: '/chat', name: 'chat', component: { template: '<div />' } }],
    })
    await router.push('/chat')
    await router.isReady()

    const auth = useAuthStore()
    auth.token = 'tok'
    auth.user = { username: 'pedro', role: 'imperador', modules: ['sql'] }
    const chat = useChatStore()
    const ui = useUiStore()
    chat.currentConv = 7
    chat.conversations = [
      { id: 7, title: 'active' },
      { id: 8, title: 'other' },
    ]
    chat.streaming = true
    chat.loading = true

    const wrapper = mount(AppShell, {
      global: {
        plugins: [router],
        stubs: {
          LangPicker: true,
          UserAvatar: true,
        },
      },
    })
    await nextTick()

    const delLabel = ui.t.delete
    const activeDel = wrapper
      .findAll('button.conv-del')
      .find(
        b =>
          (b.attributes('aria-label') || '').startsWith(delLabel) &&
          (b.attributes('aria-label') || '').includes('active'),
      )
    const otherDel = wrapper
      .findAll('button.conv-del')
      .find(
        b =>
          (b.attributes('aria-label') || '').startsWith(delLabel) &&
          (b.attributes('aria-label') || '').includes('other'),
      )

    expect(activeDel).toBeTruthy()
    expect(activeDel!.attributes('disabled')).toBeDefined()
    expect(otherDel).toBeTruthy()
    expect(otherDel!.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
})

describe('ui loadConfig lang guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.unstubAllGlobals()
  })

  it('ignores unsupported default_lang from /config', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          default_accent: 'green',
          default_lang: 'xx',
          show_demo_accounts: true,
        }),
      }),
    )
    const ui = useUiStore()
    const before = ui.lang
    await ui.loadConfig()
    expect(ui.lang).toBe(before)
  })
})
