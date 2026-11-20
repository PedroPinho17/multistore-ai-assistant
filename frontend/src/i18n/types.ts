import type { en } from '@/i18n/generated/en'

export type Lang = 'pt' | 'en' | 'es' | 'fr'
export type Scope = 'group' | 'brand' | 'store'

export const LOCALES: Record<Lang, string> = {
  pt: 'pt-PT',
  en: 'en-GB',
  es: 'es-ES',
  fr: 'fr-FR',
}

export const LANG_NAMES: Record<Lang, string> = {
  pt: 'Português',
  en: 'English',
  es: 'Español',
  fr: 'Français',
}

export const LANGS = [
  { code: 'pt' as const, name: 'Português', flag: 'pt' },
  { code: 'en' as const, name: 'English', flag: 'gb' },
  { code: 'fr' as const, name: 'Français', flag: 'fr' },
  { code: 'es' as const, name: 'Español', flag: 'es' },
]

/** Full message tree (chat + home + dash + profile + settings + admin + review). */
export type MessageTree = typeof en
