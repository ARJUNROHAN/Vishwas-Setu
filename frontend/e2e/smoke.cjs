// End-to-end smoke test: signs in as each role, opens every page it can see,
// and fails on console errors, failed API calls or uncaught exceptions.
// Usage: npm run test:smoke -- [baseUrl] [shotsDir]
// Set SMOKE_HASH=true to check the GitHub Pages build.
const { chromium } = require('playwright')
const fs = require('fs')

const BASE = (process.argv[2] || 'http://localhost:8000').replace(/\/$/, '')
const HASH = process.env.SMOKE_HASH === 'true'
const url = (path) => `${BASE}${HASH ? '/#' : ''}${path}`
const routePath = (u) => HASH ? u.hash.slice(1).split('?')[0] : u.pathname
const SHOTS = process.argv[3] || ''
const PLAN = {
  bureau: ['/', '/applications', '/deadlines', '/deadlines?tab=escalations', '/compliance', '/compliance?tab=documents', '/evc', '/alerts', '/reports', '/audit', '/config'],
  'nro.scrutiny1': ['/', '/applications', '/deadlines', '/compliance?tab=documents'],
  'nro.evc': ['/evc'],
  expert1: ['/evc'],
  authority: ['/applications?status=READY_FOR_DECISION'],
  ruleadmin: ['/config'],
  inst40: ['/', '/applications', '/compliance?tab=documents', '/alerts'],
}

;(async () => {
  const browser = await chromium.launch()
  const problems = []
  for (const [user, paths] of Object.entries(PLAN)) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    page.on('console', (m) => { if (m.type() === 'error') problems.push(`${user} console: ${m.text()}`) })
    page.on('pageerror', (e) => problems.push(`${user} pageerror: ${e.message}`))
    page.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 500) problems.push(`${user} ${r.status()} ${r.url()}`) })
    await page.goto(url('/login'))
    await page.fill('#u', user); await page.fill('#p', 'demo123')
    await page.click('button.btn.primary.wide')
    await page.waitForURL((u) => !routePath(u).startsWith('/login'), { timeout: 15000 })
    await page.locator('.page-head h1').waitFor()
    for (const p of paths) {
      await page.goto(url(p)); await page.waitForLoadState('networkidle')
      await page.locator('.page-head h1').waitFor()
      if (await page.locator('.error').count()) problems.push(`${user} ${p}: ${await page.locator('.error').allTextContents()}`)
      if (p === '/config') for (const t of ['Table 2.3 matrix', 'Checklists', 'Academic calendar', 'Alerts & escalation', 'Settings', 'Versions']) {
        await page.getByRole('button', { name: t, exact: true }).click(); await page.waitForTimeout(150)
      }
      if (p === '/alerts') { await page.getByRole('button', { name: 'Email outbox' }).click(); await page.waitForLoadState('networkidle') }
      if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: `${SHOTS}/${user}${p.replace(/[/?=&]/g, '_')}.png`, fullPage: false }) }
    }
    await page.reload(); await page.locator('.page-head h1').waitFor()
    await page.locator('a.logo').click()
    await page.waitForURL((u) => routePath(u) === '/')
    if (HASH && !page.url().startsWith(`${BASE}/#`)) problems.push(`${user}: logo left the repository path`)
    await page.getByRole('button', { name: 'Account menu', exact: true }).click()
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await page.locator('#u').waitFor()
    console.log(`${user}: pages, refresh, logo and logout OK`)
    await ctx.close()
  }
  // Flow: rule admin changes a stage time limit -> a new ruleset version is published
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    page.on('pageerror', (e) => problems.push(`flow pageerror: ${e.message}`))
    await page.goto(url('/login')); await page.fill('#u', 'ruleadmin'); await page.fill('#p', 'demo123')
    await page.click('button.btn.primary.wide'); await page.waitForURL((u) => !routePath(u).startsWith('/login'))
    await page.locator('.page-head h1').waitFor()
    await page.goto(url('/config')); await page.waitForLoadState('networkidle')
    const before = await page.locator('.page-head .crumbs li').last().textContent()
    await page.getByRole('button', { name: 'Edit' }).first().click()
    await page.locator('.modal input[type=number]').fill('12')
    await page.locator('.modal textarea').fill('E2E: circular no. TEST/2026/01')
    await page.locator('.modal button.btn.primary').click()
    await page.waitForTimeout(800); await page.reload(); await page.waitForLoadState('networkidle')
    const after = await page.locator('.page-head .crumbs li').last().textContent()
    if (before === after) problems.push(`flow: ruleset version did not change (${before})`)
    else console.log(`flow: ruleset ${before} -> ${after}`)
    // first application detail opens cleanly
    await page.goto(url('/applications')); await page.waitForLoadState('networkidle')
    await page.locator('table a.mono').first().click(); await page.waitForLoadState('networkidle')
    try { await page.locator('.trace').waitFor({ timeout: 8000 }) } catch { problems.push('detail: rule trace strip missing') }
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/detail.png` })
    await ctx.close()
  }
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    page.on('pageerror', (e) => problems.push(`login: ${e.message}`))
    await page.goto(url('/login'))
    await page.fill('#u', 'bureau'); await page.fill('#p', 'wrong-password')
    await page.click('button.btn.primary.wide')
    await page.getByText('Invalid username or password', { exact: true }).waitFor()
    if (!routePath(new URL(page.url())).startsWith('/login')) problems.push('Invalid login unexpectedly navigated')
    await page.fill('#p', 'demo123'); await page.click('button.btn.primary.wide')
    await page.locator('.page-head h1').waitFor()
    const download = page.waitForEvent('download')
    await page.goto(url('/reports')); await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: /CSV/ }).first().click()
    if (!(await download).suggestedFilename().endsWith('.csv')) problems.push('CSV download failed')
    await page.evaluate(() => localStorage.setItem('aicte_flow_token', 'expired-token'))
    await page.reload(); await page.locator('#u').waitFor()
    if (await page.evaluate(() => localStorage.getItem('aicte_flow_token'))) problems.push('Expired token was not cleared')
    console.log('invalid login, mobile rendering, CSV download and expired session OK')
    await ctx.close()
  }
  await browser.close()
  if (problems.length) { console.log(problems.join('\n')); process.exit(1) }
  console.log('smoke: OK, no console errors or 5xx')
})().catch((error) => { console.error(error); process.exit(1) })
