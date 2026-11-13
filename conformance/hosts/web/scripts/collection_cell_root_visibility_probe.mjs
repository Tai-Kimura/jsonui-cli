// A Collection cell whose root binds its visibility, in a real browser — NOT part of the conformance suite. Run:
//
//   node scripts/collection_cell_root_visibility_probe.mjs --driver <jsonui-test-runner drivers/web/dist> [--rjui <rjui_tools>]
//
// Ticket sjui-cell-root-visibility-binding-dropped, the web's half: a layout root with a `visibility` binding is
// written as an expression container (`{cond !== "gone" && (<div ...>)}`), and until 2.5.34 rjui put neither the
// `id` prop nor the screen marker on the element inside it. A cell's root then lost the `<collectionId>_item_<n>`
// id its Collection passes, which is how the test driver finds a cell (tapItem, `within`, moveItem). The probe
// builds a screen with such a cell with the given rjui and the host's React and Vite, and runs the web driver's
// own ActionExecutor on it. It prints one line per check and exits 1 when one fails.

import { mkdirSync, rmSync, writeFileSync, readFileSync, cpSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { build, preview } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { chromium } from 'playwright'

const HOST_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const WORK = join(HOST_ROOT, '.cell-root-visibility-probe')
function arg(name, env, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : process.env[env] || fallback
}
const RJUI = resolve(arg('--rjui', 'RJUI_TOOLS_PATH', join(HOST_ROOT, '../../../rjui_tools')))
const RUBY = arg('--ruby', 'RUBY_BIN', 'ruby')
const DRIVER = arg('--driver', 'JSONUI_WEB_DRIVER_DIST', '')
if (!DRIVER) throw new Error('--driver <jsonui-test-runner drivers/web/dist> is required')
const { ActionExecutor } = createRequire(import.meta.url)(join(resolve(DRIVER), 'actions/ActionExecutor'))

const CELL = {
  type: 'View', width: 'matchParent', height: 48, background: '#FFFFFF', visibility: '@{keyVisibility}', onClick: '@{onTap}',
  data: [{ name: 'name', class: 'String', defaultValue: '' }, { name: 'keyVisibility', class: 'String', defaultValue: 'visible' },
         { name: 'onTap', class: '(() -> Void)?' }],
  child: [{ type: 'Label', id: 'key_label', text: '@{name}', fontSize: 16, onClick: '@{onTap}' }],
}
const LAYOUT = {
  type: 'View', id: 'root', width: 'matchParent', orientation: 'vertical', visibility: '@{screenVisibility}',
  data: [{ name: 'keys', class: 'CollectionDataSource' }, { name: 'screenVisibility', class: 'String', defaultValue: 'visible' }],
  child: [{ type: 'Collection', id: 'keys', width: 'matchParent', lazy: 'none', items: '@{keys}', sections: [{ cell: 'probe_key_cell' }] }],
}
const MAIN = `
import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { CellRootVisibilityProbe } from './generated/components/CellRootVisibilityProbe'
const w = window as unknown as { __calls: string[] }
w.__calls = []
const cells = ['A', 'B', 'C'].map((name, i) => ({ name, keyVisibility: i === 1 ? 'invisible' : 'visible',
                                                  onTap: () => w.__calls.push(name) }))
createRoot(document.getElementById('app-root')!).render(
  <CellRootVisibilityProbe data={{ keys: { sections: [{ cells: { data: cells } }] } } as never} />)
`

function prepare() {
  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(join(WORK, 'src/Layouts/pages'), { recursive: true })
  mkdirSync(join(WORK, 'src/Layouts/Resources'), { recursive: true })
  cpSync(join(HOST_ROOT, 'src/Strings'), join(WORK, 'src/Strings'), { recursive: true })
  const config = JSON.parse(readFileSync(join(HOST_ROOT, 'rjui.config.json'), 'utf8'))
  writeFileSync(join(WORK, 'rjui.config.json'), JSON.stringify(config, null, 2))
  writeFileSync(join(WORK, 'src/Layouts/pages/cell_root_visibility_probe.json'), JSON.stringify(LAYOUT, null, 1))
  writeFileSync(join(WORK, 'src/Layouts/probe_key_cell.json'), JSON.stringify(CELL, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html><body><div id="app-root"></div><script type="module" src="/src/main.tsx"></script></body></html>\n')
  writeFileSync(join(WORK, 'tsconfig.json'), readFileSync(join(HOST_ROOT, 'tsconfig.json')))
  execFileSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, stdio: ['ignore', 'pipe', 'pipe'] })
}

let failed = 0
function report(name, ok, detail) {
  if (!ok) failed++
  console.log(`CELL_ROOT_VISIBILITY ${ok ? 'ok  ' : 'FAIL'} ${name.padEnd(58)} ${detail}`)
}

prepare()
await build({
  // development: the screen marker is test scaffolding, gated on NODE_ENV (a production bundle renders none)
  root: WORK, logLevel: 'warn', mode: 'development', plugins: [react(), tailwindcss()],
  define: { 'process.env.NODE_ENV': JSON.stringify('development') },
  resolve: { alias: { '@': join(WORK, 'src') } },
  build: { outDir: join(WORK, 'dist'), emptyOutDir: true },
})
const server = await preview({ root: WORK, logLevel: 'warn', preview: { port: 4199, strictPort: true }, build: { outDir: join(WORK, 'dist') } })
const browser = await chromium.launch()
try {
  const page = await browser.newPage({ viewport: { width: 400, height: 900 } })
  await page.goto(server.resolvedUrls.local[0])
  await page.waitForSelector('#key_label')
  await page.waitForTimeout(200)
  const ex = new ActionExecutor(page, 3000)
  const calls = () => page.evaluate(() => window.__calls.join(''))
  const reset = () => page.evaluate(() => { window.__calls = [] })

  const ids = await page.evaluate(() => [0, 1, 2].map((n) => !!document.getElementById(`keys_item_${n}`)))
  report('the cells carry the ids their Collection passes', ids.every(Boolean), `keys_item_0..2 found=${JSON.stringify(ids)}`)
  const marker = await page.evaluate(() => document.querySelectorAll('[data-screen]').length)
  report('the screen root (visibility bound) carries the screen marker', marker === 1, `data-screen elements=${marker}`)
  const hidden = await page.evaluate(() => document.getElementById('keys_item_1')?.classList.contains('invisible') ?? null)
  report('an invisible cell keeps its place, not drawn', hidden === true, `keys_item_1 invisible=${hidden}`)

  for (const [name, step, want] of [
    ['tapItem index 2 taps C', { action: 'tapItem', id: 'keys', index: 2 }, 'C'],
    ['tap within keys_item_0 taps A', { action: 'tap', id: 'key_label', within: 'keys_item_0' }, 'A'],
  ]) {
    await reset()
    let err = ''
    try { await ex.execute(step) } catch (e) { err = e.message.split('\n')[0] }
    const got = await calls()
    report(name, !err && got === want, err ? `error=${err}` : `calls=${got}`)
  }
} finally {
  await browser.close()
  await new Promise((r) => server.httpServer.close(r))
}
console.log(`CELL_ROOT_VISIBILITY ${failed} failed`)
process.exit(failed ? 1 : 0)
