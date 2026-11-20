import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { nextTick } from 'vue'
import ResetPasswordView from '@/views/ResetPasswordView.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import IconSprite from '@/components/IconSprite.vue'

describe('reset token from URL', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useUiStore()
  })

  it('initResetToken stores token from hash', () => {
    const auth = useAuthStore()
    auth.initResetToken('hash-token-xyz')
    expect(auth.rp.token).toBe('hash-token-xyz')
    expect(auth.rp.done).toBe(false)
  })

  it('ResetPasswordView reads token from hash on mount', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/reset-password',
          name: 'reset',
          component: ResetPasswordView,
        },
      ],
    })
    await router.push({ path: '/reset-password', hash: '#token=from-hash-99' })
    await router.isReady()

    const wrapper = mount(ResetPasswordView, {
      global: {
        plugins: [router],
        stubs: { IconSprite: true, LangPicker: true },
        components: { IconSprite },
      },
      attachTo: document.body,
    })
    await nextTick()
    const auth = useAuthStore()
    expect(auth.rp.token).toBe('from-hash-99')
    wrapper.unmount()
  })
})
