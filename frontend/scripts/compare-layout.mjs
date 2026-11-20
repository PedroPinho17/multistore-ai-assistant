/* global document -- page.evaluate() callbacks run in the browser */
/**
 * Dev-only screenshot script: captures the main pages at 1440 / 1024 / 768 / 390 px,
 * including the open drawer, user menu, dialogs and toasts, so layouts can be checked by eye.
 * It only takes screenshots; it does not diff them.
 *
 * Not run in CI. Requires Playwright, a running app (Vite or the built SPA) and an account:
 *
 *   npx playwright install chromium
 *   # terminal 1: npm run dev   (or serve the built app behind the API)
 *   # terminal 2 (bash; in PowerShell set $env:LAYOUT_USER / $env:LAYOUT_PASSWORD first):
 *   LAYOUT_USER=<user> LAYOUT_PASSWORD=<password> node scripts/compare-layout.mjs
 *   BASE_URL=http://127.0.0.1:5173 LAYOUT_USER=<user> LAYOUT_PASSWORD=<password> node scripts/compare-layout.mjs
 *
 * Screenshots land in frontend/scripts/layout-shots/ (ignored by the rule in frontend/.gitignore).
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(fileURLToPath(import.meta.url))
const outDir = path.join(root, 'layout-shots')
const BASE = (process.env.BASE_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const WIDTHS = [1440, 1024, 768, 390]
const DEMO = {
  username: process.env.LAYOUT_USER,
  password: process.env.LAYOUT_PASSWORD,
}
if (!DEMO.username || !DEMO.password) {
  console.error(
    'compare-layout: LAYOUT_USER and LAYOUT_PASSWORD are required (an account on the running app):\n' +
      '  LAYOUT_USER=<user> LAYOUT_PASSWORD=<password> node scripts/compare-layout.mjs',
  )
  process.exit(1)
}

async function loadPlaywright() {
  try {
    return await import('playwright')
  } catch {
    console.error(
      'compare-layout: install Playwright first:\n  npm i -D playwright && npx playwright install chromium',
    )
    process.exit(1)
  }
}

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  const user = page.locator('#username, input[name="username"], input[type="text"]').first()
  const pass = page.locator('#password, input[name="password"], input[type="password"]').first()
  if (await user.count()) {
    await user.fill(DEMO.username)
    await pass.fill(DEMO.password)
    await page.locator('button.primary, button[type="submit"]').first().click()
    await page.waitForURL(/\/(chat|dashboard)/, { timeout: 15000 }).catch(() => {})
  }
}

async function shot(page, name) {
  const file = path.join(outDir, `${name}.png`)
  await page.screenshot({ path: file, fullPage: false })
  console.log('wrote', path.relative(root, file))
}

async function main() {
  const { chromium } = await loadPlaywright()
  fs.mkdirSync(outDir, { recursive: true })

  const browser = await chromium.launch({ headless: true })
  const publicPaths = ['/', '/login', '/reset-password']
  const authedPaths = ['/chat', '/dashboard', '/profile', '/settings', '/users', '/admin', '/review']

  for (const width of WIDTHS) {
    const height = width <= 390 ? 844 : 900
    const context = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: 1,
    })
    const page = await context.newPage()

    for (const p of publicPaths) {
      await page.goto(`${BASE}${p}`, { waitUntil: 'networkidle' }).catch(() =>
        page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }),
      )
      await shot(page, `${width}-public${p === '/' ? '-home' : p.replace(/\//g, '-')}`)
    }

    await login(page)

    for (const p of authedPaths) {
      await page.goto(`${BASE}${p}`, { waitUntil: 'networkidle' }).catch(() =>
        page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }),
      )
      await shot(page, `${width}${p.replace(/\//g, '-')}`)
    }

    // Open drawer (mobile / narrow)
    await page.goto(`${BASE}/chat`, { waitUntil: 'domcontentloaded' })
    const menu = page.locator('.topbar .menu-btn, button.menu-btn').first()
    if (await menu.isVisible().catch(() => false)) {
      await menu.click()
      await page.waitForTimeout(300)
      await shot(page, `${width}-chat-drawer-open`)
    }

    // User menu
    const userBtn = page.locator('.user-btn, [aria-haspopup="menu"]').first()
    if (await userBtn.count()) {
      await userBtn.click()
      await page.waitForTimeout(200)
      await shot(page, `${width}-chat-user-menu`)
      await page.keyboard.press('Escape')
    }

    // Dialog (delete chat) if a delete control exists
    const del = page.locator('.conv-del, button[title*="Delete"], button[aria-label*="Delete"]').first()
    if (await del.count()) {
      await del.click({ force: true }).catch(() => {})
      await page.waitForTimeout(200)
      if (await page.locator('.dlg, [role="dialog"]').count()) {
        await shot(page, `${width}-chat-dialog`)
        await page.keyboard.press('Escape')
      }
    }

    // Toast: trigger via UI store if exposed, else inject a toast node for visual check
    await page.evaluate(() => {
      const host = document.querySelector('.toasts') || document.body
      const el = document.createElement('div')
      el.className = 'toast'
      el.setAttribute('role', 'status')
      el.textContent = 'Layout check toast'
      host.appendChild(el)
    })
    await page.waitForTimeout(100)
    await shot(page, `${width}-chat-toast`)

    await context.close()
  }

  await browser.close()
  console.log('done →', outDir)
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
