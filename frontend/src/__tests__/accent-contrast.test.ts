import { describe, expect, it } from 'vitest'
import { customPalette } from '@/lib/accent'

/** Same AA pairs as the old pytest against settings.js — now against accent.ts. */
const COLORS = [
  '#ffff00',
  '#bdbdbd',
  '#ffffff',
  '#000000',
  '#00ff00',
  '#ff00ff',
  '#00e5ff',
  '#ff5a00',
  '#7a7a7a',
  '#123456',
  '#c2185b',
  '#0f7a5a',
]

function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function contrastRatio(a: number[], b: number[]): number {
  const f = (v: number) => {
    const x = v / 255
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4
  }
  const L = (c: number[]) => 0.2126 * f(c[0]!) + 0.7152 * f(c[1]!) + 0.0722 * f(c[2]!)
  const [x, y] = [L(a), L(b)].sort((p, q) => q - p)
  return (x! + 0.05) / (y! + 0.05)
}

const WHITE: [number, number, number] = [255, 255, 255]
const DARK: [number, number, number] = [0x14, 0x1a, 0x18]

describe('customPalette contrast AA', () => {
  it.each(COLORS)('%s meets AA on every text/background pair', hex => {
    const p = customPalette(hex)
    const c = (a: string | number[], b: string | number[]) =>
      contrastRatio(typeof a === 'string' ? hexToRgb(a) : a, typeof b === 'string' ? hexToRgb(b) : b)
    const pairs = {
      white_on_button: c(WHITE, p.light['--btn']),
      brand_on_white: c(p.light['--brand'], WHITE),
      brand_on_soft: c(p.light['--brand'], p.light['--brand-soft']),
      dark_brand_on_surface: c(p.dark['--brand'], DARK),
      dark_brand_on_soft: c(p.dark['--brand'], p.dark['--brand-soft']),
      white_on_dark_button: c(WHITE, p.dark['--btn']),
    }
    for (const [name, ratio] of Object.entries(pairs)) {
      expect(ratio, `${hex} ${name}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('flags light colours as adjusted', () => {
    expect(customPalette('#ffff00').adjusted).toBe(true)
    expect(customPalette('#bdbdbd').adjusted).toBe(true)
  })

  it('leaves colours that already work alone', () => {
    expect(customPalette('#0f7a5a').adjusted).toBe(false)
    expect(customPalette('#123456').adjusted).toBe(false)
  })
})
