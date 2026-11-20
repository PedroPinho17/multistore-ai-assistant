import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadStartupLang, showBootError, startApp } from '@/boot'
import type { Lang } from '@/i18n/types'

describe('start-up language', () => {
  it('loads the chosen language', async () => {
    const load = vi.fn(async () => undefined)
    expect(await loadStartupLang('pt', load)).toBe(true)
    expect(load.mock.calls).toEqual([['pt']])
  })

  it('falls back to English when the chosen one fails', async () => {
    const load = vi.fn(async (l: Lang) => {
      if (l === 'pt') throw new Error('chunk failed')
    })
    expect(await loadStartupLang('pt', load)).toBe(true)
    expect(load.mock.calls).toEqual([['pt'], ['en']])
  })

  it('reports failure when neither loads (English is not tried twice)', async () => {
    const fail = vi.fn(async () => {
      throw new Error('offline')
    })
    expect(await loadStartupLang('fr', fail)).toBe(false)
    expect(fail.mock.calls).toEqual([['fr'], ['en']])
    fail.mockClear()
    expect(await loadStartupLang('en', fail)).toBe(false)
    expect(fail.mock.calls).toEqual([['en']])
  })
})

describe('start-up error screen', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="app"></div>'
  })

  it('replaces the blank page with a message in the chosen language and a reload button', () => {
    const root = document.getElementById('app')!
    const reload = vi.fn()
    showBootError(root, 'pt', reload)

    const box = root.querySelector('[role="alert"]')!
    expect(box.querySelector('h1')!.textContent).toBe('Não foi possível abrir a aplicação')
    expect(box.querySelector('p')!.textContent).toContain('ligação à internet')
    const button = box.querySelector('button')!
    expect(button.textContent).toBe('Recarregar')
    button.click()
    expect(reload).toHaveBeenCalledTimes(1)
    expect(document.documentElement.lang).toBe('pt')
  })

  it('has texts in every language', () => {
    const root = document.getElementById('app')!
    const titles = (['pt', 'en', 'es', 'fr'] as const).map(l => {
      showBootError(root, l, () => undefined)
      return root.querySelector('h1')!.textContent
    })
    expect(new Set(titles).size).toBe(4)
    expect(titles.every(Boolean)).toBe(true)
  })
})

describe('startApp (what main.ts runs)', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="app"></div>'
  })
  const root = () => document.getElementById('app')

  it('starts the app once the texts are loaded, without the error screen', async () => {
    const start = vi.fn()
    expect(await startApp({ lang: 'pt', load: async () => undefined, start, root })).toBe(true)
    expect(start).toHaveBeenCalledTimes(1)
    expect(root()!.querySelector('[role="alert"]')).toBeNull()
  })

  it('also starts with the English fallback', async () => {
    const start = vi.fn()
    const load = vi.fn(async (l: Lang) => {
      if (l !== 'en') throw new Error('chunk failed')
    })
    expect(await startApp({ lang: 'fr', load, start, root })).toBe(true)
    expect(start).toHaveBeenCalledTimes(1)
  })

  it('with no texts at all: shows the error screen and never starts the app', async () => {
    const start = vi.fn()
    const reload = vi.fn()
    const load = vi.fn(async () => {
      throw new Error('offline')
    })
    expect(await startApp({ lang: 'es', load, start, root, reload })).toBe(false)
    expect(start).not.toHaveBeenCalled()
    const alert = root()!.querySelector('[role="alert"]')!
    expect(alert.querySelector('h1')!.textContent).toBe('No se pudo abrir la aplicación')
    alert.querySelector('button')!.click()
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
