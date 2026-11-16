// Screen-marker measurement probe (screen-identity track, Phase 0) — NOT part
// of the conformance suite. Run explicitly:
//
//   npm run screen-marker-probe
//
// Web asks two questions the canon cannot assume:
//
// 1. Does server-rendered markup expose the marker BEFORE hydration attaches
//    handlers? If it does, an assertion that only checks the marker can pass
//    on a page that is not yet interactive — the canon currently claims this
//    outright ("attached && hydration complete") without having measured it.
//
// 2. During a client-side screen swap, do the outgoing and incoming markers
//    ever coexist in the DOM? React 19 keeps the old UI on screen while a
//    transition is pending, which would make a naive presence check see two
//    screens at once.
//
// The probe builds a tiny two-screen app with the host's own React and Vite,
// serves it with a deliberately DELAYED hydration script so the pre-hydration
// window is wide enough to sample, and drives it with Playwright. It asserts
// nothing on its own: it prints measurements.

import { createServer } from 'node:http'
import { mkdirSync, rmSync, writeFileSync, readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createElement as h } from 'react'
import { renderToString } from 'react-dom/server'
import { build } from 'vite'
import { chromium } from 'playwright'

const HYDRATION_DELAY_MS = 1500

// --------------------------------------------------------------------------
// The app under measurement. Written with createElement so the probe needs no
// JSX transform — the shape is what matters: a screen root carrying the
// marker attribute, plus a handler whose effect is observable from the DOM.
// --------------------------------------------------------------------------
const APP_SOURCE = `
import { createElement as h, useState, useTransition, Suspense, lazy } from 'react'

// A destination that suspends for a beat, like a route split across a chunk
// boundary or a screen awaiting its first data. This is the case where React
// keeps the OUTGOING screen mounted while the next one prepares — the shape a
// screen assertion could read as "arrived" too early.
const SlowScreen = lazy(() => new Promise(resolve => {
  setTimeout(() => resolve({
    default: () => h('div', { 'data-screen': 'slow_screen', id: 'slow_screen_root_view' },
      h('p', { id: 'slow_screen_child_0' }, 'slow_screen-child-0')),
  }), 1200)
}))

export function App() {
  const [screen, setScreen] = useState('probe_home')
  const [clicks, setClicks] = useState(0)
  const [isPending, startTransition] = useTransition()

  let body
  if (screen === 'probe_home') {
    body = h('div', { 'data-screen': 'probe_home', id: 'probe_home_root_view' },
      h('p', { id: 'probe_home_child_0' }, 'probe_home-child-0'),
      h('p', { id: 'click_count' }, 'clicks:' + clicks),
      h('button', { id: 'bump', onClick: () => setClicks(c => c + 1) }, 'bump'),
      h('button', {
        id: 'go_detail',
        onClick: () => startTransition(() => setScreen('detail_screen')),
      }, 'go-detail'),
      h('button', {
        id: 'go_slow',
        onClick: () => startTransition(() => setScreen('slow_screen')),
      }, 'go-slow'))
  } else if (screen === 'detail_screen') {
    body = h('div', { 'data-screen': 'detail_screen', id: 'detail_screen_root_view' },
      h('p', { id: 'detail_screen_child_0' }, 'detail_screen-child-0'))
  } else {
    body = h(Suspense, { fallback: h('p', { id: 'slow_fallback' }, 'loading') }, h(SlowScreen))
  }

  return h('main', { id: 'app_root', 'data-pending': String(isPending) }, body)
}
`

const CLIENT_SOURCE = `
import { createElement as h } from 'react'
import { hydrateRoot } from 'react-dom/client'
import { App } from './app.js'

hydrateRoot(document.getElementById('root'), h(App))
document.documentElement.setAttribute('data-hydrated', 'true')
`

// The sources have to live inside the host so `react` resolves through its
// node_modules — a system temp dir cannot see them.
const HOST_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const WORK_DIR = join(HOST_ROOT, '.screen-marker-probe')

async function bundleClient() {
  const dir = WORK_DIR
  rmSync(dir, { recursive: true, force: true })
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'app.js'), APP_SOURCE)
  writeFileSync(join(dir, 'client.js'), CLIENT_SOURCE)
  await build({
    configFile: false,
    logLevel: 'error',
    root: dir,
    build: {
      outDir: join(dir, 'dist'),
      emptyOutDir: true,
      minify: false,
      rollupOptions: { input: join(dir, 'client.js'), output: { entryFileNames: 'client.js' } },
    },
  })
  return { dir, bundle: readFileSync(join(dir, 'dist', 'client.js'), 'utf8') }
}

async function ssrHtml(dir) {
  const { App } = await import(join(dir, 'app.js'))
  return renderToString(h(App))
}

function serve(markup, bundle) {
  const html = `<!doctype html><html><head><title>screen marker probe</title></head>` +
    `<body><div id="root">${markup}</div>` +
    `<script type="module" src="/client.js"></script></body></html>`
  const server = createServer((req, res) => {
    if (req.url === '/client.js') {
      // Delay the hydration bundle so the pre-hydration window is wide
      // enough to sample deterministically.
      setTimeout(() => {
        res.writeHead(200, { 'content-type': 'text/javascript' })
        res.end(bundle)
      }, HYDRATION_DELAY_MS)
      return
    }
    res.writeHead(200, { 'content-type': 'text/html' })
    res.end(html)
  })
  return new Promise(resolve => {
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })
}

/** marker presence / Playwright visibility / interactivity, as one row. */
async function snapshot(page, label, screenId) {
  const locator = page.locator(`[data-screen="${screenId}"]`)
  const count = await locator.count()
  const visible = count > 0 ? await locator.first().isVisible() : false
  const hydrated = await page.evaluate(() => document.documentElement.hasAttribute('data-hydrated'))
  return `${label}: count=${count} isVisible=${visible} hydrated=${hydrated}`
}

async function main() {
  const { dir, bundle } = await bundleClient()
  const markup = await ssrHtml(dir)

  console.log('[screen-marker] SSR MARKUP')
  console.log(`  data-screen present in server HTML: ${markup.includes('data-screen="probe_home"')}`)
  console.log(`  markup: ${markup.slice(0, 160)}`)

  const { server, port } = await serve(markup, bundle)
  const browser = await chromium.launch()
  const page = await browser.newPage()

  // Do not wait for the delayed module: sample the pre-hydration window.
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'commit' })
  await page.waitForSelector('[data-screen]', { state: 'attached' })

  console.log('[screen-marker] BEFORE HYDRATION')
  console.log('  ' + await snapshot(page, 'probe_home', 'probe_home'))

  // Interactivity check: a click before hydration must be a no-op, and that
  // is precisely the gap between "marker visible" and "screen usable".
  await page.locator('#bump').click()
  console.log(`  click before hydration -> ${await page.locator('#click_count').innerText()}`)

  await page.waitForFunction(() => document.documentElement.hasAttribute('data-hydrated'), null, { timeout: 15000 })
  console.log('[screen-marker] AFTER HYDRATION')
  console.log('  ' + await snapshot(page, 'probe_home', 'probe_home'))
  await page.locator('#bump').click()
  console.log(`  click after hydration -> ${await page.locator('#click_count').innerText()}`)

  // A transition that suspends: does the destination's marker appear while
  // the user is still looking at the source screen?
  const slow = await page.evaluate(async () => {
    const read = () => Array.from(document.querySelectorAll('[data-screen]'))
      .map(el => el.getAttribute('data-screen')).join('+') || '(none)'
    const samples = []
    document.getElementById('go_slow').click()
    for (let i = 0; i < 10; i++) {
      samples.push(`${Math.round(performance.now())}ms:${read()}/pending=` +
        document.getElementById('app_root').getAttribute('data-pending'))
      await new Promise(r => setTimeout(r, 200))
    }
    return samples
  })
  console.log('[screen-marker] SUSPENDING TRANSITION (200ms samples)')
  for (const row of slow) console.log(`  ${row}`)

  // Plain client-side swap: sample per animation frame to catch any window in
  // which both markers are attached.
  await page.reload({ waitUntil: 'load' })
  await page.waitForFunction(() => document.documentElement.hasAttribute('data-hydrated'), null, { timeout: 15000 })
  const during = await page.evaluate(async () => {
    const samples = []
    document.getElementById('go_detail').click()
    for (let i = 0; i < 12; i++) {
      samples.push(Array.from(document.querySelectorAll('[data-screen]'))
        .map(el => el.getAttribute('data-screen')).join('+') || '(none)')
      await new Promise(r => requestAnimationFrame(r))
    }
    return samples
  })
  console.log('[screen-marker] CLIENT-SIDE SWAP (per animation frame)')
  console.log(`  ${during.join(' -> ')}`)

  console.log('[screen-marker] AFTER SWAP')
  console.log('  ' + await snapshot(page, 'probe_home', 'probe_home'))
  console.log('  ' + await snapshot(page, 'detail_screen', 'detail_screen'))

  await browser.close()
  server.close()
  rmSync(WORK_DIR, { recursive: true, force: true })
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
