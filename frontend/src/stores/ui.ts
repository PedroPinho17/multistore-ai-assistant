import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { prefs, sessionStore } from '@/lib/storage'
import { detectLang, isLang, isLoaded, loadLang, shownLang, t as messages } from '@/i18n'
import type { Lang, MessageTree } from '@/i18n/types'
import type { AppConfig, Theme, ThemePref, ToastType } from '@/api/types'
import { api } from '@/api/client'
import { applyAccent, type AccentValue } from '@/lib/accent'

export interface ToastItem {
  id: number
  text: string
  type: ToastType
}

export interface ConfirmOpts {
  title: string
  text: string
  subject?: string
  confirm: string
  danger?: boolean
}

let toastSeq = 1
let dialogFocus: HTMLElement | null = null

const darkQuery =
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null

function resolveTheme(pref: ThemePref): Theme {
  if (pref === 'light' || pref === 'dark') return pref
  return darkQuery?.matches ? 'dark' : 'light'
}

export const useUiStore = defineStore('ui', () => {
  const lang = ref<Lang>(detectLang())
  const themePref = ref<ThemePref>(
    (['light', 'dark', 'system'] as const).includes(prefs.get('theme') as ThemePref)
      ? (prefs.get('theme') as ThemePref)
      : 'system',
  )
  const theme = ref<Theme>(resolveTheme(themePref.value))
  const accent = ref<string | null>(prefs.get('accent'))
  const sidebarOpen = ref(false)
  const userMenu = ref(false)
  const toasts = ref<ToastItem[]>([])
  const dialog = ref<(ConfirmOpts & { resolve: (ok: boolean) => void }) | null>(null)
  const appConfig = ref<AppConfig>({
    default_accent: 'green',
    default_lang: 'pt',
    show_demo_accounts: true,
  })
  const pageTitle = ref('')
  const pageSub = ref('')
  const topbarActions = ref<'chat' | 'dashboard' | 'users' | 'review' | 'admin' | 'none'>('none')

  const t = computed<MessageTree>(() => messages(lang.value))
  const showDemo = computed(() => appConfig.value.show_demo_accounts !== false)
  const effectiveAccent = computed<AccentValue>(
    () => accent.value || appConfig.value.default_accent || 'green',
  )

  function applyTheme() {
    theme.value = resolveTheme(themePref.value)
  }

  function hasToken() {
    return !!sessionStore.get('token')
  }

  function setTheme(v: ThemePref, persist = true) {
    themePref.value = v
    prefs.set('theme', v)
    applyTheme()
    if (persist) void saveSetting({ theme: v }, hasToken())
  }

  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  let langRequest = 0

  /**
   * Shows `l`. The texts of a language not yet loaded are downloaded first; meanwhile the
   * current language stays on screen. Only the last request wins (fast double switch).
   */
  async function showLang(l: Lang): Promise<void> {
    if (!isLang(l)) return
    const req = ++langRequest
    if (isLoaded(l)) {
      lang.value = l
      return
    }
    try {
      await loadLang(l)
      if (req === langRequest) lang.value = l
    } catch {
      if (req === langRequest) toast(t.value.network)
    }
  }

  function setLang(l: Lang, persist = true): Promise<void> {
    if (!isLang(l)) return Promise.resolve()
    prefs.set('lang', l)
    if (persist) void saveSetting({ lang: l }, hasToken())
    return showLang(l)
  }

  function setAccent(a: string | null, persist = true) {
    accent.value = a
    if (a) prefs.set('accent', a)
    else prefs.del('accent')
    if (persist) void saveSetting({ accent: a }, hasToken())
  }

  function toast(text: string, type: ToastType = 'error') {
    const kind: ToastType = type === 'ok' ? 'ok' : 'error'
    const id = toastSeq++
    toasts.value.push({ id, text, type: kind })
    if (toasts.value.length > 4) toasts.value.shift()
    setTimeout(() => dismissToast(id), kind === 'error' ? 6000 : 3500)
  }

  function dismissToast(id: number) {
    toasts.value = toasts.value.filter(x => x.id !== id)
  }

  function confirmDialog(opts: ConfirmOpts): Promise<boolean> {
    if (dialog.value) closeDialog(false)
    const active = document.activeElement
    dialogFocus = active instanceof HTMLElement ? active : null
    return new Promise(resolve => {
      dialog.value = { ...opts, resolve }
    })
  }

  function closeDialog(ok: boolean) {
    const d = dialog.value
    if (!d) return
    dialog.value = null
    d.resolve(ok)
    const prev = dialogFocus
    dialogFocus = null
    void Promise.resolve().then(() => prev?.focus?.())
  }

  async function loadConfig() {
    try {
      const cfg = await (
        await fetch('/config', { headers: { 'Accept-Language': lang.value } })
      ).json()
      appConfig.value = { ...appConfig.value, ...cfg }
      const dl = cfg.default_lang
      if (!prefs.get('lang') && isLang(dl)) await showLang(dl)
    } catch {
      /* offline / no backend */
    }
  }

  async function saveSetting(changes: Record<string, unknown>, hasToken: boolean) {
    if (!hasToken) return
    try {
      await api('/settings/me', changes, 'PUT')
    } catch (e) {
      const err = e as { status?: number; message?: string }
      if (err.status !== 401) toast(err.message || String(e))
    }
  }

  async function resetSettings(hasToken: boolean) {
    if (hasToken) {
      try {
        await api('/settings/me', { lang: null, theme: null, accent: null }, 'PUT')
      } catch {
        /* ignore */
      }
    }
    for (const k of ['lang', 'theme', 'accent']) prefs.del(k)
    accent.value = null
    themePref.value = 'system'
    applyTheme()
    const dl = appConfig.value.default_lang
    if (isLang(dl)) await showLang(dl)
    toast(t.value.st.resetDone, 'ok')
  }

  function setPageMeta(
    title: string,
    sub = '',
    actions: typeof topbarActions.value = 'none',
  ) {
    pageTitle.value = title
    pageSub.value = sub
    topbarActions.value = actions
  }

  watch(
    theme,
    v => {
      document.documentElement.dataset.theme = v
      applyAccent(effectiveAccent.value, v)
    },
    { immediate: true },
  )

  watch(
    effectiveAccent,
    a => applyAccent(a, theme.value),
    { immediate: true },
  )

  // <html lang> = the language of the texts on screen, not just the chosen one: while the
  // chosen language is missing (e.g. it failed to download) the English fallback is shown,
  // and screen readers must read it as English.
  watch(
    () => shownLang(lang.value),
    v => {
      document.documentElement.lang = v
    },
    { immediate: true },
  )

  if (darkQuery) {
    darkQuery.addEventListener('change', () => {
      if (themePref.value === 'system') applyTheme()
    })
  }

  return {
    lang,
    themePref,
    theme,
    accent,
    effectiveAccent,
    sidebarOpen,
    userMenu,
    toasts,
    dialog,
    appConfig,
    pageTitle,
    pageSub,
    topbarActions,
    t,
    showDemo,
    applyTheme,
    setTheme,
    toggleTheme,
    setLang,
    setAccent,
    toast,
    dismissToast,
    confirmDialog,
    closeDialog,
    loadConfig,
    saveSetting,
    resetSettings,
    setPageMeta,
  }
})
