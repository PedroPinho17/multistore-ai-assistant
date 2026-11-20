import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, configureApi } from '@/api/client'
import type { LoginResponse, User, UserSettings } from '@/api/types'
import { ApiError } from '@/api/types'
import { sessionStore } from '@/lib/storage'
import { useUiStore } from '@/stores/ui'
import type { Lang, Scope } from '@/i18n/types'
import type { Router } from 'vue-router'

function parseUser(raw: string | null): User | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(sessionStore.get('token'))
  const user = ref<User | null>(parseUser(sessionStore.get('user')))
  const username = ref('')
  const password = ref('')
  const loginError = ref('')
  const loggingIn = ref(false)
  const shake = ref(false)
  const showPassword = ref(false)
  const capsLock = ref(false)
  const fp = ref({
    open: false,
    login: '',
    sending: false,
    sent: false,
    error: '',
  })
  const rp = ref({
    token: '',
    pass: '',
    confirm: '',
    show: false,
    saving: false,
    done: false,
    error: '',
  })

  const isAuthenticated = computed(() => !!token.value)
  const scope = computed<Scope>(() => {
    const role = user.value?.role
    if (role === 'marca') return 'brand'
    if (role === 'loja') return 'store'
    return 'group'
  })
  const initials = computed(() =>
    (user.value?.username || '?')
      .split(/[.\s_-]/)
      .map(p => p[0])
      .join('')
      .slice(0, 2)
      .toUpperCase(),
  )

  function hasModule(m: string): boolean {
    return (user.value?.modules || []).includes(m)
  }

  function wireApi(router?: Router) {
    const ui = useUiStore()
    configureApi({
      getToken: () => token.value,
      getLang: () => ui.lang,
      onUnauthorized: () => logout(router, 'login'),
      getTexts: () => ({
        network: ui.t.network,
        loginError: ui.t.loginError,
        tooMany: ui.t.tooMany,
        errors: ui.t.errors,
      }),
    })
  }

  function applyUserSettings(st?: UserSettings | null) {
    if (!st) return
    const ui = useUiStore()
    if (st.lang) ui.setLang(st.lang)
    if (st.theme) ui.setTheme(st.theme)
  }

  async function refreshMe() {
    try {
      const me = await api<User>('/me')
      user.value = me
      sessionStore.set('user', JSON.stringify(me))
      applyUserSettings(me.settings)
    } catch {
      /* keep cached user */
    }
  }

  async function login(router: Router) {
    const ui = useUiStore()
    if (!username.value || !password.value) return
    loggingIn.value = true
    loginError.value = ''
    try {
      const data = await api<LoginResponse>('/login', {
        username: username.value,
        password: password.value,
      })
      token.value = data.token
      user.value = data.user
      password.value = ''
      sessionStore.set('token', data.token)
      sessionStore.set('user', JSON.stringify(data.user))
      showPassword.value = false
      capsLock.value = false
      await router.push({ name: 'chat' })
    } catch (e) {
      const err = e as ApiError
      loginError.value =
        err.status === 429
          ? ui.t.tooMany
          : err.status === 401
            ? ui.t.loginError
            : err.message
      shake.value = true
      setTimeout(() => {
        shake.value = false
      }, 450)
    } finally {
      loggingIn.value = false
    }
  }

  function logout(router?: Router, to: 'login' | 'home' = 'login') {
    // Sem import estático do chat store (mantém o bundle do login pequeno).
    // O chat store, se já estiver carregado, faz reset via watch no token.
    token.value = null
    user.value = null
    sessionStore.del('token')
    sessionStore.del('user')
    void import('@/stores/chat')
      .then(({ useChatStore }) => {
        try {
          useChatStore().reset()
        } catch {
          /* pinia may not be ready */
        }
      })
      .catch(() => undefined)
    if (router) {
      void router.push({ name: to === 'home' ? 'login' : to })
    }
  }

  function fillDemo(d: { user: string; pass: string }) {
    username.value = d.user
    password.value = d.pass
    loginError.value = ''
  }

  function checkCaps(e: KeyboardEvent) {
    if (e.getModifierState) capsLock.value = e.getModifierState('CapsLock')
  }

  function openForgot() {
    const ui = useUiStore()
    void ui
    fp.value = {
      open: true,
      login: username.value.includes('@') ? username.value : '',
      sending: false,
      sent: false,
      error: '',
    }
  }

  function closeForgot() {
    fp.value.open = false
  }

  async function sendForgot() {
    const ui = useUiStore()
    const state = fp.value
    state.error = ''
    if (state.login.trim().length < 3) return
    state.sending = true
    try {
      await api('/password/forgot', { login: state.login.trim(), lang: ui.lang })
      state.sent = true
    } catch (e) {
      const err = e as ApiError
      state.error = err.status === 429 ? ui.t.tooMany : err.message
    } finally {
      state.sending = false
    }
  }

  function initResetToken(raw: string) {
    rp.value = {
      token: raw,
      pass: '',
      confirm: '',
      show: false,
      saving: false,
      done: false,
      error: '',
    }
  }

  async function submitReset() {
    const ui = useUiStore()
    const state = rp.value
    const p = ui.t.p
    state.error = ''
    if (state.pass.length < 8) state.error = p.errShort
    else if (/^[0-9]+$/.test(state.pass) || /^[\p{L}]+$/u.test(state.pass)) state.error = p.errMix
    else if (state.pass !== state.confirm) state.error = p.errMatch
    if (state.error) return
    state.saving = true
    try {
      await api('/password/reset', { token: state.token, new_password: state.pass })
      rp.value = {
        token: '',
        pass: '',
        confirm: '',
        show: false,
        saving: false,
        done: true,
        error: '',
      }
    } catch (e) {
      const err = e as ApiError
      state.error = err.status === 429 ? ui.t.tooMany : err.message
    } finally {
      state.saving = false
    }
  }

  function persistLangSetting(l: Lang) {
    const ui = useUiStore()
    ui.setLang(l)
    if (token.value) void ui.saveSetting({ lang: l }, true)
  }

  return {
    token,
    user,
    username,
    password,
    loginError,
    loggingIn,
    shake,
    showPassword,
    capsLock,
    fp,
    rp,
    isAuthenticated,
    scope,
    initials,
    hasModule,
    wireApi,
    refreshMe,
    login,
    logout,
    fillDemo,
    checkCaps,
    openForgot,
    closeForgot,
    sendForgot,
    initResetToken,
    submitReset,
    applyUserSettings,
    persistLangSetting,
  }
})
