import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const html = fs.readFileSync(path.join(root, 'dist', 'index.html'), 'utf8')

if (/<script(?![^>]*\bsrc\s*=)[^>]*>/i.test(html)) {
  console.error('inline <script> without src in dist/index.html')
  process.exit(1)
}

const srcs = [...html.matchAll(/<script[^>]*\bsrc=["']([^"']+)["']/gi)].map(m => m[1])
if (!srcs.length) {
  console.error('no <script src> in dist/index.html')
  process.exit(1)
}
for (const s of srcs) {
  if (/^(https?:)?\/\//i.test(s)) {
    console.error('external (non same-origin) script:', s)
    process.exit(1)
  }
}
console.log('ok', srcs.length, 'same-origin script(s)')
