/**
 * One-shot helper: evaluate legacy text blobs and emit merged TS locale snippets.
 * Run: node scripts/gen-locales.mjs
 *
 * en.ts is the reference: its function parameters get real types (PARAM_TYPES below) and
 * `MessageTree = typeof en`. pt/es/fr are emitted as `export const pt: MessageTree = …` with
 * untyped parameters, so TypeScript types them from en and any missing or extra key is a
 * build error.
 */
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const outDir = path.join(root, 'frontend/src/i18n/generated')

function load(rel) {
  return fs.readFileSync(path.join(root, rel), 'utf8')
}

function extractConst(src, name) {
  const re = new RegExp(`const ${name} = `)
  const start = src.search(re)
  if (start < 0) throw new Error(`const ${name} not found`)
  const after = start + `const ${name} = `.length
  let i = after
  let depth = 0
  let inStr = null
  let esc = false
  for (; i < src.length; i++) {
    const ch = src[i]
    if (inStr) {
      if (esc) {
        esc = false
        continue
      }
      if (ch === '\\') {
        esc = true
        continue
      }
      if (ch === inStr) inStr = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      inStr = ch
      continue
    }
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) {
        i++
        break
      }
    }
  }
  return src.slice(after, i)
}

function merge(target, src) {
  for (const [k, v] of Object.entries(src)) {
    if (v && typeof v === 'object' && !Array.isArray(v) && typeof target[k] === 'object' && target[k]) {
      merge(target[k], v)
    } else {
      target[k] = v
    }
  }
}

// Types of the text functions' parameters in en.ts: by parameter name, with overrides
// per key path ("adm.ratings.u") where the same name means something else.
const TYPES_BY_NAME = {
  n: 'number',
  shown: 'number',
  h: 'number',
  m: 'number',
  p: 'number',
  f: 'boolean',
  o: 'boolean',
  scope: 'Scope',
  u: 'string',
  b: 'string',
  st: 'string',
  d: 'string',
  name: 'string',
  who: 'string',
  when: 'string',
}
const PARAM_TYPES = {
  'adm.tokensTotal.n': 'string', // already formatted
  'um.createdBy.n': 'string', // a username
  'adm.ratings.u': 'number',
  'adm.ratings.d': 'number',
  'p.storesAll.n': 'number | string', // "…" while the profile loads
  'p.storesBrand.n': 'number | string',
}

function paramType(keyPath, name) {
  const t = PARAM_TYPES[`${keyPath}.${name}`] || TYPES_BY_NAME[name]
  if (!t) throw new Error(`no type for parameter "${name}" of ${keyPath}: add it to TYPES_BY_NAME/PARAM_TYPES`)
  return t
}

let typed = true // true while serializing en.ts

function serialize(value, indent = 0, keyPath = '') {
  const pad = '  '.repeat(indent)
  const pad2 = '  '.repeat(indent + 1)
  if (typeof value === 'function') {
    let s = value.toString()
    if (s.startsWith('function ')) {
      const m = s.match(/^function\s*\(([^)]*)\)\s*\{([\s\S]*)\}$/)
      if (m) {
        const args = m[1]
        const body = m[2].trim()
        if (body.startsWith('return ') && !body.includes(';') && !body.includes('\n')) {
          s = `(${args}) => ${body.slice(7)}`
        }
      }
    }
    // en: typed parameters. pt/es/fr: untyped, typed by `: MessageTree` (contextual typing).
    s = s.replace(/^\(?([^)=]*?)\)?\s*=>/, (_, args) => {
      const params = String(args)
        .split(',')
        .map(a => a.trim())
        .filter(Boolean)
        .map(a => (typed ? `${a}: ${paramType(keyPath, a)}` : a))
        .join(', ')
      return `(${params}) =>`
    })
    return s
  }
  if (value === null) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    if (!value.length) return '[]'
    const items = value.map(v => pad2 + serialize(v, indent + 1, keyPath))
    return '[\n' + items.join(',\n') + ',\n' + pad + ']'
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value)
    if (!keys.length) return '{}'
    const lines = keys.map(k => {
      const key = /^[A-Za-z_$][\w$]*$/.test(k) ? k : JSON.stringify(k)
      return `${pad2}${key}: ${serialize(value[k], indent + 1, keyPath ? `${keyPath}.${k}` : k)}`
    })
    return '{\n' + lines.join(',\n') + ',\n' + pad + '}'
  }
  return 'undefined'
}

const textsJs = load('web/static/js/texts.js')
const TEXTS = vm.runInNewContext('(' + extractConst(textsJs, 'TEXTS') + ')', {}, { timeout: 5000 })
const PAGE_TEXTS = vm.runInNewContext('(' + extractConst(textsJs, 'PAGE_TEXTS') + ')', {}, { timeout: 5000 })
for (const code of Object.keys(PAGE_TEXTS)) merge(TEXTS[code], PAGE_TEXTS[code])

function installFrom(file, name) {
  const src = load(file)
  const obj = vm.runInNewContext('(' + extractConst(src, name) + ')', {}, { timeout: 5000 })
  for (const code of Object.keys(obj)) if (TEXTS[code]) merge(TEXTS[code], obj[code])
}

installFrom('web/static/js/admin.js', 'ADMIN_TEXTS')
installFrom('web/static/js/dashboard.js', 'DASH_TEXTS')
installFrom('web/static/js/ui.js', 'UI_TEXTS')
installFrom('web/static/js/review.js', 'REVIEW_TEXTS')
installFrom('web/static/js/review.js', 'EXAMPLES_TEXTS')
installFrom('web/static/js/settings.js', 'SETTINGS_TEXTS')

// Ensure shell/nav extras present
for (const code of Object.keys(TEXTS)) {
  const t = TEXTS[code]
  t.nav = {
    ...(t.nav || {}),
    settings: t.nav?.settings || t.st?.title || 'Settings',
    review: t.nav?.review || t.rv?.title || 'Review',
    dashboard: t.nav?.dashboard || t.dash?.title || 'Dashboard',
  }
  t.pageTitles = {
    ...(t.pageTitles || {}),
    settings: t.pageTitles?.settings || `${t.st?.title || 'Settings'} · Multistore AI`,
    review: t.pageTitles?.review || `${t.rv?.title || 'Review'} · Multistore AI`,
    dashboard: t.pageTitles?.dashboard || `${t.dash?.title || 'Dashboard'} · Multistore AI`,
    users: t.pageTitles?.users || `${t.um?.title || 'Users'} · Multistore AI`,
    admin: t.pageTitles?.admin || `${t.adm?.title || 'Admin'} · Multistore AI`,
  }
  // l.title from UI_TEXTS
  if (!t.l.title) t.l.title = t.login
}

// Texts only the new UI has (not in web/static/js)
const NEW_UI_TEXTS = {
  pt: { p: { clearBusy: 'Espera que a resposta em curso termine antes de apagar as conversas.' } },
  en: { p: { clearBusy: 'Wait for the current answer to finish before deleting your chats.' } },
  es: { p: { clearBusy: 'Espera a que termine la respuesta en curso antes de borrar las conversaciones.' } },
  fr: { p: { clearBusy: 'Attends la fin de la réponse en cours avant de supprimer les conversations.' } },
}
for (const code of Object.keys(NEW_UI_TEXTS)) merge(TEXTS[code], NEW_UI_TEXTS[code])

fs.mkdirSync(outDir, { recursive: true })
const HEADER = '// Generated by scripts/gen-locales.mjs from the old UI texts (web/static/js). Do not edit by hand.\n'
for (const code of ['pt', 'en', 'es', 'fr']) {
  typed = code === 'en'
  const body = serialize(TEXTS[code], 0)
  const file = typed
    ? `${HEADER}import type { Scope } from '@/i18n/types'\n\nexport const en = ${body}\n`
    : `${HEADER}import type { MessageTree } from '@/i18n/types'\n\nexport const ${code}: MessageTree = ${body}\n`
  fs.writeFileSync(path.join(outDir, `${code}.ts`), file)
  console.log('wrote', code, file.length)
}
console.log('done', outDir)
