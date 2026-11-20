/** Accent colour math (custom palette + favicon / CSS variables). */

export const ACCENTS = ['green', 'orange', 'blue', 'wine', 'purple', 'graphite'] as const
export type NamedAccent = (typeof ACCENTS)[number]

export const ACCENT_COLORS: Record<NamedAccent, [string, string]> = {
  green: ['#14905f', '#0b6b4e'],
  orange: ['#d9480f', '#9a3412'],
  blue: ['#2563eb', '#1e40af'],
  wine: ['#be123c', '#881337'],
  purple: ['#7c3aed', '#5b21b6'],
  graphite: ['#4b5563', '#1f2937'],
}

const HEX_RE = /^#[0-9a-f]{6}$/
const WHITE: [number, number, number] = [255, 255, 255]
const BLACK: [number, number, number] = [0, 0, 0]
const DARK_SURFACE: [number, number, number] = [0x14, 0x1a, 0x18]
const MIN_CONTRAST = 4.6
const ACCENT_VARS = [
  '--brand',
  '--brand-2',
  '--brand-soft',
  '--btn',
  '--btn-2',
  '--logo-1',
  '--logo-2',
] as const

export type AccentValue = NamedAccent | string

export function isCustomAccent(a: string | null | undefined): boolean {
  return HEX_RE.test(a || '')
}

function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function rgbToHex(c: number[]): string {
  return (
    '#' +
    c
      .map(v =>
        Math.round(Math.max(0, Math.min(255, v)))
          .toString(16)
          .padStart(2, '0'),
      )
      .join('')
  )
}

function mixRgb(a: number[], b: number[], t: number): [number, number, number] {
  return a.map((v, i) => v + (b[i]! - v) * t) as [number, number, number]
}

function luminance(c: number[]): number {
  const f = (v: number) => {
    const x = v / 255
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(c[0]!) + 0.7152 * f(c[1]!) + 0.0722 * f(c[2]!)
}

function contrastRatio(a: number[], b: number[]): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x! + 0.05) / (y! + 0.05)
}

function untilContrast(
  c: number[],
  target: number[],
  against: number[],
  min = MIN_CONTRAST,
): [number, number, number] {
  for (let t = 0; t <= 1.0001; t += 0.02) {
    const out = mixRgb(c, target, t)
    if (contrastRatio(out, against) >= min) return out
  }
  return target as [number, number, number]
}

export function customPalette(hex: string) {
  const base = hexToRgb(hex)
  const btn = untilContrast(base, BLACK, WHITE)
  const soft = mixRgb(btn, WHITE, 0.9)
  const brand = untilContrast(btn, BLACK, soft)
  const btn2 = mixRgb(btn, BLACK, 0.18)
  const dSoft = mixRgb(base, DARK_SURFACE, 0.82)
  const dBrand = untilContrast(untilContrast(base, WHITE, DARK_SURFACE), WHITE, dSoft)
  const adjusted = Math.max(...base.map((v, i) => Math.abs(v - btn[i]!))) > 24
  const H = rgbToHex
  return {
    light: {
      '--brand': H(brand),
      '--brand-2': H(btn2),
      '--brand-soft': H(soft),
      '--btn': H(btn),
      '--btn-2': H(btn2),
      '--logo-1': H(mixRgb(btn, WHITE, 0.12)),
      '--logo-2': H(btn2),
    },
    dark: {
      '--brand': H(dBrand),
      '--brand-2': H(dBrand),
      '--brand-soft': H(dSoft),
      '--btn': H(btn),
      '--btn-2': H(btn2),
      '--logo-1': H(mixRgb(btn, WHITE, 0.12)),
      '--logo-2': H(btn2),
    },
    swatch: [H(mixRgb(btn, WHITE, 0.12)), H(btn2)] as [string, string],
    adjusted,
  }
}

export function accentColors(a: AccentValue): [string, string] {
  if (isCustomAccent(a)) return customPalette(a).swatch
  return ACCENT_COLORS[(a as NamedAccent) in ACCENT_COLORS ? (a as NamedAccent) : 'green']
}

export function accentSwatchStyle(a: AccentValue): { background: string } {
  const [x, y] = accentColors(a)
  return { background: `linear-gradient(135deg, ${x}, ${y})` }
}

export function faviconSvg(accent: AccentValue): string {
  const [a, b] = accentColors(accent)
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
        `<stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>` +
        `<rect width="64" height="64" rx="14" fill="url(#g)"/>` +
        `<path d="M16 13h32a7 7 0 0 1 7 7v18a7 7 0 0 1-7 7H30l-14 10V45a7 7 0 0 1-7-7V20a7 7 0 0 1 7-7z" fill="#fff"/>` +
        `<rect x="20.5" y="25" width="7" height="11" rx="3.5" fill="${b}"/>` +
        `<rect x="36.5" y="21" width="7" height="15" rx="3.5" fill="${b}"/></svg>`,
    )
  )
}

export function applyAccent(accent: AccentValue, theme: 'light' | 'dark'): void {
  const root = document.documentElement
  if (isCustomAccent(accent)) {
    const pal = customPalette(accent)[theme === 'dark' ? 'dark' : 'light']
    root.dataset.accent = 'custom'
    for (const [k, v] of Object.entries(pal)) root.style.setProperty(k, v)
  } else {
    for (const k of ACCENT_VARS) root.style.removeProperty(k)
    root.dataset.accent = accent in ACCENT_COLORS ? accent : 'green'
  }
  const link = document.getElementById('favicon') as HTMLLinkElement | null
  if (link) link.href = faviconSvg(accent)
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', accentColors(accent)[1])
}
