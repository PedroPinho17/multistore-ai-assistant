import { shallowReactive } from 'vue'
import { prefs } from '@/lib/storage'
import type { Lang, MessageTree } from '@/i18n/types'

export * from '@/i18n/types'

/**
 * Each language is its own chunk: only the active one is downloaded at start-up (main.ts
 * waits for it before mounting) and the others on the first switch to them.
 */
const LOADERS: Record<Lang, () => Promise<MessageTree>> = {
  pt: () => import('@/i18n/generated/pt').then(m => m.pt),
  en: () => import('@/i18n/generated/en').then(m => m.en),
  es: () => import('@/i18n/generated/es').then(m => m.es),
  fr: () => import('@/i18n/generated/fr').then(m => m.fr),
}

export const LANG_CODES = Object.keys(LOADERS) as Lang[]

// Reactive (shallow: the texts themselves need no proxies): t() reads it, so a computed
// built on t() updates when a language finishes loading, even if the chosen language did
// not change (e.g. it failed at start-up, English was shown, and it loads later).
const loaded = shallowReactive<Partial<Record<Lang, MessageTree>>>({})
const pending: Partial<Record<Lang, Promise<MessageTree>>> = {}

export function isLang(v: unknown): v is Lang {
  return typeof v === 'string' && Object.prototype.hasOwnProperty.call(LOADERS, v)
}

export function isLoaded(l: Lang): boolean {
  return !!loaded[l]
}

/** Downloads a language once (concurrent calls share the request; a failure can be retried). */
export function loadLang(l: Lang): Promise<MessageTree> {
  const done = loaded[l]
  if (done) return Promise.resolve(done)
  let p = pending[l]
  if (!p) {
    p = LOADERS[l]()
      .then(m => {
        loaded[l] = m
        return m
      })
      .finally(() => {
        delete pending[l]
      })
    pending[l] = p
  }
  return p
}

export function detectLang(): Lang {
  const saved = prefs.get('lang')
  if (isLang(saved)) return saved
  const nav = typeof navigator !== 'undefined' ? navigator.language : 'en'
  return LANG_CODES.find(l => nav.startsWith(l)) ?? 'en'
}

/**
 * The language actually on screen when `lang` is chosen: `lang` itself if loaded, otherwise
 * (still downloading, or it failed) English if loaded, otherwise any loaded language. With
 * nothing loaded yet, `lang`. Reactive, like t().
 */
export function shownLang(lang: Lang): Lang {
  if (loaded[lang]) return lang
  if (loaded.en) return 'en'
  return LANG_CODES.find(l => loaded[l]) ?? lang
}

/** Texts of `lang`, or of the fallback language shownLang() picks while it is missing. */
export function t(lang: Lang): MessageTree {
  const m = loaded[shownLang(lang)]
  if (!m) throw new Error('i18n: no language loaded yet (await loadLang() before mounting)')
  return m
}
