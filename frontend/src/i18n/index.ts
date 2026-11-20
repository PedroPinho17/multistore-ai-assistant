import { prefs } from '@/lib/storage'
import type { Lang, MessageTree } from '@/i18n/types'
import { pt } from '@/i18n/locales/pt'
import { en } from '@/i18n/locales/en'
import { es } from '@/i18n/locales/es'
import { fr } from '@/i18n/locales/fr'

export * from '@/i18n/types'

export const MESSAGES: Record<Lang, MessageTree> = { pt, en, es, fr }

export function detectLang(): Lang {
  const saved = prefs.get('lang')
  if (saved && saved in MESSAGES) return saved as Lang
  const nav = typeof navigator !== 'undefined' ? navigator.language : 'en'
  const found = (Object.keys(MESSAGES) as Lang[]).find(l => nav.startsWith(l))
  return found ?? 'en'
}

export function t(lang: Lang): MessageTree {
  return MESSAGES[lang] ?? MESSAGES.en
}
