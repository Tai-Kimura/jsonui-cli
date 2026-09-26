// Collection scrollTo probe — NOT part of the conformance suite (a fixture is
// one Collection with no way to send a value after the page settles). Run
// explicitly:
//
//   npm run collection-scroll-probe
//
// The rule (the SSoT's Collection.scrollTo, jsonui-cli 1.9.0): an Int is a
// cell counted across the drawn sections in order, headers and footers not
// counted; a String is the FIRST cell, in section order, whose key it is;
// anything else scrolls nowhere. The request is a CHANGE of the value: the
// value a Collection is drawn with scrolls nowhere.
//
// The probe writes one layout, runs `rjui build` over it (the production
// codegen), builds it with the host's Vite and React, and drives it in
// headless Chromium: it reads each Collection's scroll offset and the cells at
// its top edge when the page has settled, then after each value it sends.
// Every Collection is 120 high with scrollAnchor top and scrollAnimated false,
// so the named cell's top edge is the Collection's.
//   gridSections  2 columns, two sections with a header (a grid per section)
//   gridOne       2 columns, one section (one grid)
//   listSections  1 column, two sections with a header (the control route)
//   listKeyed     1 column, cellIdProperty `key`, a key both sections have
//   listInitial   drawn with scrollTo 7 — it must stay at its top
// It prints one line per step and exits 1 on any step that breaks the rule.
//
//   --rjui / RJUI_TOOLS_PATH   default: <repo>/rjui_tools
//   --ruby / RUBY_BIN          default: ruby

import { spawnSync } from 'node:child_process'
import { cpSync, mkdirSync, rmSync, writeFileSync, readFileSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { build, preview } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { chromium } from 'playwright'

const HOST_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const WORK = join(HOST_ROOT, '.collection-scroll-probe')
function arg(name, env, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : process.env[env] || fallback
}
const RJUI = resolve(arg('--rjui', 'RJUI_TOOLS_PATH', join(HOST_ROOT, '../../../rjui_tools')))
const RUBY = arg('--ruby', 'RUBY_BIN', 'ruby')

// ------------------------------------------------------------ the layouts
const CELL = {
  type: 'View', width: 'matchParent', height: 30, background: '#FFFFFF',
  data: [{ name: 'name', class: 'String', defaultValue: '' }],
  child: [{ type: 'Label', text: '@{name}', fontSize: 12 }],
}
const EDGE = {
  type: 'View', width: 'matchParent', height: 20, background: '#CCCCCC',
  data: [{ name: 'title', class: 'String', defaultValue: '' }],
  child: [{ type: 'Label', text: '@{title}', fontSize: 10 }],
}
const collection = (id, extra) => ({
  type: 'Collection', id, width: 240, height: 120, background: '#EEEEEE',
  scrollAnchor: 'top', scrollAnimated: false, ...extra,
})
const two = [{ cell: 'probe_scroll_cell', header: 'probe_scroll_edge' }, { cell: 'probe_scroll_cell', header: 'probe_scroll_edge' }]
const LAYOUT = {
  type: 'View', id: 'root', width: 'matchParent', orientation: 'vertical', spacing: 8,
  data: [
    { name: 'gridRows', class: 'CollectionDataSource' }, { name: 'oneRows', class: 'CollectionDataSource' },
    { name: 'listRows', class: 'CollectionDataSource' }, { name: 'keyedRows', class: 'CollectionDataSource' },
    { name: 'gridTarget', class: 'Int', defaultValue: 0 }, { name: 'oneTarget', class: 'Int', defaultValue: 0 },
    { name: 'listTarget', class: 'Int', defaultValue: 0 }, { name: 'keyTarget', class: 'String', defaultValue: '' },
    { name: 'initialTarget', class: 'Int', defaultValue: 0 },
  ],
  child: [
    collection('gridSections', { items: '@{gridRows}', sections: two, columns: 2, scrollTo: '@{gridTarget}' }),
    collection('gridOne', { items: '@{oneRows}', sections: [{ cell: 'probe_scroll_cell' }], columns: 2, scrollTo: '@{oneTarget}' }),
    collection('listSections', { items: '@{listRows}', sections: two, scrollTo: '@{listTarget}' }),
    collection('listKeyed', { items: '@{keyedRows}', sections: [{ cell: 'probe_scroll_cell' }, { cell: 'probe_scroll_cell' }],
      cellIdProperty: 'key', scrollTo: '@{keyTarget}' }),
    collection('listInitial', { items: '@{listRows}', sections: two, scrollTo: '@{initialTarget}' }),
  ],
}

// The page: the generated component with state the probe sets from outside.
const MAIN = `
import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { CollectionScrollProbe } from './generated/components/CollectionScrollProbe'
const w = window as unknown as { __set: (k: string, v: unknown) => void }
const cells = (names: string[], keys?: string[]) => ({ data: names.map((name, i) => (keys ? { name, key: keys[i] } : { name })) })
const range = (p: string, n: number) => Array.from({ length: n }, (_, i) => p + i)
const sections = (a: string[], b: string[]) => ({ sections: [
  { header: { title: 'HA' }, cells: cells(a) }, { header: { title: 'HB' }, cells: cells(b) },
] })
function Probe() {
  const [state, setState] = useState<Record<string, unknown>>({
    gridRows: sections(range('a', 4), range('b', 10)),
    oneRows: { sections: [{ cells: cells(range('g', 20)) }] },
    listRows: sections(range('a', 5), range('b', 8)),
    keyedRows: { sections: [
      { cells: cells(range('a', 6), range('k', 6)) },
      { cells: cells(range('b', 6), ['k3', 'x1', 'x2', 'x3', 'x4', 'x5']) },
    ] },
    gridTarget: 0, oneTarget: 0, listTarget: 0, keyTarget: '', initialTarget: 7,
  })
  w.__set = (k, v) => setState((s) => ({ ...s, [k]: v }))
  return <CollectionScrollProbe data={state} />
}
createRoot(document.getElementById('app-root')!).render(<Probe />)
`

function prepare() {
  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(join(WORK, 'src/Layouts/pages'), { recursive: true })
  mkdirSync(join(WORK, 'src/Layouts/Resources'), { recursive: true })
  cpSync(join(HOST_ROOT, 'src/Strings'), join(WORK, 'src/Strings'), { recursive: true })
  const config = JSON.parse(readFileSync(join(HOST_ROOT, 'rjui.config.json'), 'utf8'))
  writeFileSync(join(WORK, 'rjui.config.json'), JSON.stringify(config, null, 2))
  writeFileSync(join(WORK, 'src/Layouts/pages/collection_scroll_probe.json'), JSON.stringify(LAYOUT, null, 1))
  writeFileSync(join(WORK, 'src/Layouts/probe_scroll_cell.json'), JSON.stringify(CELL, null, 1))
  writeFileSync(join(WORK, 'src/Layouts/probe_scroll_edge.json'), JSON.stringify(EDGE, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n@source "./generated";\n@import "./generated/theme.css";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html><head><meta charset="UTF-8" /></head><body><div id="app-root"></div>' +
    '<script type="module" src="/src/main.tsx"></script></body></html>')
  const run = spawnSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, encoding: 'utf8' })
  writeFileSync(join(WORK, 'rjui-build.log'), (run.stdout ?? '') + (run.stderr ?? ''))
  if (run.status !== 0) throw new Error(`rjui build failed (${run.status}) — see ${join(WORK, 'rjui-build.log')}`)
}

// A Collection's scroll offset, whether it is a scroll container, and the
// names of the cells whose top edge is its top edge.
function read(page, id) {
  return page.evaluate((cid) => {
    const box = document.getElementById(cid)
    if (!box) return null
    const top = box.getBoundingClientRect().top
    const style = getComputedStyle(box)
    const cells = Array.from(box.querySelectorAll(`[id^="${cid}_item_"]`))
      .filter((el) => Math.abs(el.getBoundingClientRect().top - top) < 1)
      .map((el) => el.textContent.trim())
    return { scrollTop: Math.round(box.scrollTop), overflowY: style.overflowY,
      scrollable: box.scrollHeight > box.clientHeight + 1 && ['auto', 'scroll'].includes(style.overflowY), atTop: cells }
  }, id)
}

const STEPS = [
  // [collection, the value to send (undefined: as drawn), a cell the top row must hold (null: none moved)]
  ['gridSections', undefined, null],  // drawn with 0: still at its top (its header)
  ['gridSections', 5, 'b1'],          // a0…a3 are cells 0…3, b0 4, b1 5; the headers are not counted
  ['gridOne', undefined, 'g0'],
  ['gridOne', 9, 'g9'],
  ['listSections', undefined, null],
  ['listSections', 6, 'b1'],          // a0…a4 are cells 0…4, b0 5, b1 6
  ['listKeyed', undefined, 'a0'],
  ['listKeyed', 'k3', 'a3'],          // both sections have k3: the first section's
  ['listKeyed', 'x2', 'b2'],
  ['listKeyed', 'nothing', 'b2'],     // no cell's key: it stays where it was
  ['listKeyed', '0#123', 'b2'],       // the Kotlin-only legacy form: the web does not read it
  ['listInitial', undefined, null],   // drawn with 7: still at its top
]
const TARGETS = { gridSections: 'gridTarget', gridOne: 'oneTarget', listSections: 'listTarget', listKeyed: 'keyTarget', listInitial: 'initialTarget' }

prepare()
await build({
  root: WORK, logLevel: 'warn', plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': join(WORK, 'src') } },
  build: { outDir: join(WORK, 'dist'), emptyOutDir: true },
})
const server = await preview({ root: WORK, logLevel: 'warn', preview: { port: 4197, strictPort: true }, build: { outDir: join(WORK, 'dist') } })
const url = server.resolvedUrls.local[0]
const browser = await chromium.launch()
let failures = 0
try {
  const page = await browser.newPage({ viewport: { width: 400, height: 900 } })
  await page.goto(url)
  await page.waitForSelector('#root')
  await page.waitForTimeout(400)
  for (const [id, value, want] of STEPS) {
    if (value !== undefined) {
      await page.evaluate(([k, v]) => window.__set(k, v), [TARGETS[id], value])
      await page.waitForTimeout(250)
    }
    const m = await read(page, id)
    const problems = []
    if (!m) problems.push('not drawn')
    else if (want === null) { if (m.scrollTop !== 0) problems.push(`scrolled to ${m.scrollTop} with no change sent`) }
    else if (!m.atTop.includes(want)) problems.push(`${want} is not at the top`)
    if (m && value !== undefined && !m.scrollable) problems.push(`not a scroll container (overflow-y ${m.overflowY})`)
    failures += problems.length ? 1 : 0
    console.log(`COLLECTION_SCROLL ${id.padEnd(13)} ${value === undefined ? 'drawn' : `send ${JSON.stringify(value)}`.padEnd(14)} ` +
      `scrollTop=${m?.scrollTop} overflowY=${m?.overflowY} scrollable=${m?.scrollable} top=[${m?.atTop.join(' ')}]` +
      `${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
  }
  await page.close()
} finally {
  await browser.close()
  server.httpServer.close()
}
console.log(`COLLECTION_SCROLL ${failures} step(s) break the rule`)
process.exit(failures ? 1 : 0)
