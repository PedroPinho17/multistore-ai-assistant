/**
 * Start-up helpers for main.ts. The texts are a chunk of their own (i18n/index.ts), so if
 * neither the chosen language nor the English fallback can be downloaded there is nothing
 * to render the app with: a plain message (texts built in below) replaces the blank page.
 */
import type { Lang } from '@/i18n/types'

/** Loads the start-up language, or English if that fails. False if neither loaded. */
export async function loadStartupLang(
  lang: Lang,
  load: (l: Lang) => Promise<unknown>,
): Promise<boolean> {
  try {
    await load(lang)
    return true
  } catch {
    /* try English */
  }
  if (lang === 'en') return false
  try {
    await load('en')
    return true
  } catch {
    return false
  }
}

/**
 * What main.ts does at start-up: load the texts, then start the app (mount) — or, with no
 * texts at all, show the error screen in `root` instead and never mount.
 */
export async function startApp(opts: {
  lang: Lang
  load: (l: Lang) => Promise<unknown>
  start: () => void
  root: () => HTMLElement | null
  reload?: () => void
}): Promise<boolean> {
  const ok = await loadStartupLang(opts.lang, opts.load)
  if (ok) {
    opts.start()
    return true
  }
  const root = opts.root()
  if (root) showBootError(root, opts.lang, opts.reload)
  return false
}

const BOOT_TEXTS: Record<Lang, { title: string; text: string; reload: string }> = {
  pt: {
    title: 'Não foi possível abrir a aplicação',
    text: 'Verifica a ligação à internet e volta a carregar a página.',
    reload: 'Recarregar',
  },
  en: {
    title: 'The app could not be opened',
    text: 'Check your internet connection and reload the page.',
    reload: 'Reload',
  },
  es: {
    title: 'No se pudo abrir la aplicación',
    text: 'Comprueba la conexión a internet y vuelve a cargar la página.',
    reload: 'Recargar',
  },
  fr: {
    title: "Impossible d'ouvrir l'application",
    text: 'Vérifie ta connexion internet et recharge la page.',
    reload: 'Recharger',
  },
}

/** Replaces the (empty) app root with the error message. DOM API only: no inline HTML/JS (CSP). */
export function showBootError(
  root: HTMLElement,
  lang: Lang,
  reload: () => void = () => location.reload(),
): void {
  const tx = BOOT_TEXTS[lang] ?? BOOT_TEXTS.en
  const box = document.createElement('div')
  box.className = 'boot-error'
  box.setAttribute('role', 'alert')
  const title = document.createElement('h1')
  title.textContent = tx.title
  const text = document.createElement('p')
  text.textContent = tx.text
  const button = document.createElement('button')
  button.type = 'button'
  button.textContent = tx.reload
  button.addEventListener('click', () => reload())
  box.append(title, text, button)
  root.replaceChildren(box)
  document.documentElement.lang = lang
}
