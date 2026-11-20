import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { prefs } from '@/lib/storage'
import { detectLang, MESSAGES, t as messages } from '@/i18n'
import type { Lang, MessageTree } from '@/i18n/types'
import type { AppConfig, Theme, ThemePref, ToastType } from '@/api/types'
import { api } from '@/api/client'

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
  const sidebarOpen = ref(false)
  const userMenu = ref(false)
  const toasts = ref<ToastItem[]>([])
  const dialog = ref<(ConfirmOpts & { resolve: (ok: boolean) => void }) | null>(null)
  const appConfig = ref<AppConfig>({
    default_accent: 'green',
    default_lang: 'pt',
    show_demo_accounts: true,
  })

  const t = computed<MessageTree>(() => messages(lang.value))
  const showDemo = computed(() => appConfig.value.show_demo_accounts !== false)

  function applyTheme() {
    theme.value = resolveTheme(themePref.value)
  }

  function setTheme(v: ThemePref) {
    themePref.value = v
    prefs.set('theme', v)
    applyTheme()
  }

  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  function setLang(l: Lang) {
    lang.value = l
    prefs.set('lang', l)
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
      if (!prefs.get('lang') && typeof dl === 'string' && dl in MESSAGES) {
        lang.value = dl as Lang
      }
    } catch {
      /* offline / no backend */
    }
  }

  async function saveSetting(changes: Record<string, unknown>, hasToken: boolean) {
    if (!hasToken) return
    try {
      await api('/settings/me', changes, 'PUT')
    } catch {
      /* ignore in part 1 */
    }
  }

  watch(
    theme,
    v => {
      document.documentElement.dataset.theme = v
    },
    { immediate: true },
  )

  watch(
    lang,
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
    sidebarOpen,
    userMenu,
    toasts,
    dialog,
    appConfig,
    t,
    showDemo,
    applyTheme,
    setTheme,
    toggleTheme,
    setLang,
    toast,
    dismissToast,
    confirmDialog,
    closeDialog,
    loadConfig,
    saveSetting,
  }
})
