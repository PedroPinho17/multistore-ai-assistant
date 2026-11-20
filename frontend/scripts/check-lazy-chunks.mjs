/**
 * CI check after `npm run build`: Chart.js must stay out of the start-up code.
 *
 * Follows the static imports (`import … from "./x.js"`, `import "./x.js"`, `export … from`)
 * from the entry script and the modulepreload links of dist/index.html: everything the
 * browser downloads before the app can start. Dynamic `import("./x.js")` is not followed
 * (that is the lazy loading this check protects). Fails if that start-up graph contains the
 * chartjs chunk or any Chart.js code (found by a text that Chart.js always contains, so a
 * stray `import … from 'chart.js'` that lands in another chunk is caught too).
 *
 * Run: node scripts/check-lazy-chunks.mjs [distDir]
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const dist = path.resolve(
  process.argv[2] || path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist'),
)
const CHARTJS_MARKER = 'Canvas is already in use'
const BASE = '/'

const fail = msg => {
  console.error('check-lazy-chunks:', msg)
  process.exit(1)
}

const html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8')
const fromHtml = [
  ...html.matchAll(/<script[^>]*\btype=["']module["'][^>]*\bsrc=["']([^"']+)["']/gi),
  ...html.matchAll(/<link[^>]*\brel=["']modulepreload["'][^>]*\bhref=["']([^"']+)["']/gi),
].map(m => m[1])
const entries = fromHtml
  .filter(src => src.startsWith(BASE))
  .map(src => path.join(dist, src.slice(BASE.length)))
if (!entries.length) fail('no module entry script in dist/index.html')

// Static import/export-from of a relative .js file; `import(` never matches (no "(" allowed)
const STATIC_IMPORT = /(?:^|[;\s}])(?:import|export)\s*(?:[^'"();]*?\bfrom\s*)?["'](\.\.?\/[^"']+\.js)["']/g

const seen = new Set()
const queue = [...entries]
while (queue.length) {
  const file = queue.shift()
  if (seen.has(file)) continue
  seen.add(file)
  if (!fs.existsSync(file)) fail(`missing chunk ${path.relative(dist, file).replace(/\\/g, '/')}`)
  const code = fs.readFileSync(file, 'utf8')
  for (const m of code.matchAll(STATIC_IMPORT)) queue.push(path.resolve(path.dirname(file), m[1]))
}

const startup = [...seen].map(f => path.relative(dist, f).replace(/\\/g, '/'))
for (const file of seen) {
  const name = path.basename(file)
  if (name.startsWith('chartjs-')) fail(`the start-up code imports the Chart.js chunk (${name})`)
  if (fs.readFileSync(file, 'utf8').includes(CHARTJS_MARKER))
    fail(`Chart.js code is in a start-up chunk (${path.basename(file)})`)
}

// The check is only meaningful if Chart.js is in the build at all (marker still valid)
const assets = fs.readdirSync(path.join(dist, 'assets')).filter(f => f.endsWith('.js'))
const chartChunks = assets.filter(f =>
  fs.readFileSync(path.join(dist, 'assets', f), 'utf8').includes(CHARTJS_MARKER),
)
if (!chartChunks.length) fail(`no chunk contains "${CHARTJS_MARKER}": update CHARTJS_MARKER`)

console.log(`ok: start-up = ${startup.join(', ')}; Chart.js only in lazy ${chartChunks.join(', ')}`)
