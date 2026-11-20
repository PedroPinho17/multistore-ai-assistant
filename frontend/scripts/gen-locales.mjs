/**
 * Normalise frontend/src/i18n/generated/{en,pt,es,fr}.ts — those files are the source of truth.
 * Run: node scripts/gen-locales.mjs
 *
 * en.ts is the reference: its function parameters get real types (PARAM_TYPES below) and
 * `MessageTree = typeof en`. pt/es/fr are emitted as `export const pt: MessageTree = …` with
 * untyped parameters, so TypeScript types them from en and any missing or extra key is a
 * build error.
 *
 * Edit the generated locale files, then re-run this script to refresh types/formatting.
 * CI fails if the files drift from what this script would write.
 */
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const outDir = path.join(root, 'src/i18n/generated')

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
        .map(a => {
          const name = a.replace(/:[\s\S]*$/, '').trim()
          return typed ? `${name}: ${paramType(keyPath, name)}` : name
        })
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

/** Load a generated locale .ts file as a plain object (strip types, then eval). */
function loadLocale(code) {
  const file = path.join(outDir, `${code}.ts`)
  let src = fs.readFileSync(file, 'utf8')
  const m = src.match(/export const \w+(?::\s*MessageTree)?\s*=\s*/)
  if (!m) throw new Error(`${code}.ts: missing export const`)
  src = src.slice(m.index + m[0].length).trim()
  if (src.endsWith(';')) src = src.slice(0, -1)
  // Strip TypeScript parameter types only in arrow params: (n: number) => → (n) =>
  src = src.replace(/\(([^)=]*?)\)\s*=>/g, (_, params) => {
    const cleaned = String(params)
      .split(',')
      .map(p => p.trim().replace(/:[\s\S]*$/, '').trim())
      .filter(Boolean)
      .join(', ')
    return `(${cleaned}) =>`
  })
  return vm.runInNewContext('(' + src + ')', Object.create(null), { timeout: 5000 })
}

const TEXTS = {}
for (const code of ['pt', 'en', 'es', 'fr']) {
  TEXTS[code] = loadLocale(code)
}

fs.mkdirSync(outDir, { recursive: true })
const HEADER =
  '// Source of truth for UI strings. Edit this file, then run: node scripts/gen-locales.mjs\n'
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
