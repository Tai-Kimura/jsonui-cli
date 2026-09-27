// Collection insets probe — NOT part of the conformance suite (a fixture is
// one Collection and one spelling; this rule is about how the spellings add
// up). Run explicitly:
//
//   npm run collection-insets-probe
//
// The rule (the SSoT's Collection.insets, jsonui-cli 1.9.0): the insets are
// padding around the cells, inside the Collection's scroll — 1, 2 or 4
// values, an array or a `|` string, read as `paddings` reads them (one, every
// side; two, [vertical, horizontal]; four, [top, right, bottom, left]); any
// other value pads nothing. insetHorizontal and insetVertical are ADDED to
// them per edge — no precedence — as iOS and both Compose paths draw them.
// The values are exact. Until jsonui-cli 1.9.0 rjui rounded them to
// Tailwind's spacing scale (30 became 28), four values replaced
// insetHorizontal / insetVertical, two lost to insetHorizontal, and the
// string form was not read.
//
// The probe writes a page per 300 x 60 Collection (60 x 28 cells), runs
// `rjui build` over it (the production codegen), builds it with the host's
// Vite and React, and in headless Chromium reads where each Collection's
// first cell sits in the Collection's box, and whether that box is still the
// Collection's width and is the scroll container. It prints one line per
// Collection and exits 1 on any that breaks the rule.
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
const WORK = join(HOST_ROOT, '.collection-insets-probe')
function arg(name, env, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : process.env[env] || fallback
}
const RJUI = resolve(arg('--rjui', 'RJUI_TOOLS_PATH', join(HOST_ROOT, '../../../rjui_tools')))
const RUBY = arg('--ruby', 'RUBY_BIN', 'ruby')

const CELL = {
  type: 'View', width: 60, height: 28, background: '#FFFFFF',
  data: [{ name: 'name', class: 'String', defaultValue: '' }],
  child: [{ type: 'Label', text: '@{name}', fontSize: 12 }],
}
// [id, extra attributes, the first cell's x and y in the Collection's box]
const CASES = [
  ['v_start30', { insets: [0, 0, 0, 30] }, 30, 0],
  ['v_end30', { insets: [0, 30, 0, 0] }, 0, 0],
  ['v_string', { insets: '0|0|0|30' }, 30, 0],
  ['v_string_two', { insets: '6|30' }, 30, 6],
  ['v_two_h10', { insets: [4, 20], insetHorizontal: 10 }, 30, 4],
  ['v_one_v8', { insets: [10], insetVertical: 8 }, 10, 18],
  ['v_four_hv', { insets: [2, 0, 0, 30], insetHorizontal: 4, insetVertical: 8 }, 34, 10],
  ['v_h_only', { insetHorizontal: 13 }, 13, 0],
  ['v_unreadable', { insets: 'a|b' }, 0, 0],
  ['v_three', { insets: [1, 2, 3] }, 0, 0],
  ['v_bound', { insets: ['@{top}', 0, 0, 30] }, 30, 12],
  ['h_start30', { layout: 'horizontal', insets: [0, 0, 0, 30] }, 30, 0],
  ['h_two_h10', { layout: 'horizontal', insets: [4, 20], insetHorizontal: 10 }, 30, 4],
  ['grid_start30', { columns: 2, insets: [0, 0, 0, 30] }, 30, 0],
  ['pager_start30', { layout: 'horizontal', paging: true, insets: [0, 0, 0, 30] }, 30, 0],
]
// One page per Collection, so a spelling rjui cannot build fails its own
// Collection only (it is then "not drawn") — a bound value in the array
// stopped the whole layout until jsonui-cli 1.9.0.
const layout = ([id, extra]) => ({
  type: 'View', id: `page_${id}`, width: 'matchParent', orientation: 'vertical',
  data: [{ name: 'rows', class: 'CollectionDataSource' }, { name: 'top', class: 'Int', defaultValue: 12 }],
  child: [{
    type: 'Collection', id, width: 300, height: 60, background: '#EEEEEE', items: '@{rows}',
    sections: [{ cell: 'probe_insets_cell' }], ...extra,
  }],
})
const MAIN = `
import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
const pages = import.meta.glob('./generated/components/Ci*.tsx', { eager: true }) as Record<string, Record<string, unknown>>
const rows = { sections: [{ cells: { data: Array.from({ length: 12 }, (_, i) => ({ name: 'c' + i })) } }] }
const views = Object.entries(pages).map(([path, mod]) => {
  const View = Object.values(mod).find((v) => typeof v === 'function') as React.ComponentType<{ data: unknown }>
  return <div key={path} style={{ marginBottom: 8 }}><View data={{ rows, top: 12 }} /></div>
})
createRoot(document.getElementById('app-root')!).render(<div id="root">{views}</div>)
`

function prepare() {
  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(join(WORK, 'src/Layouts/pages'), { recursive: true })
  mkdirSync(join(WORK, 'src/Layouts/Resources'), { recursive: true })
  cpSync(join(HOST_ROOT, 'src/Strings'), join(WORK, 'src/Strings'), { recursive: true })
  writeFileSync(join(WORK, 'rjui.config.json'), readFileSync(join(HOST_ROOT, 'rjui.config.json')))
  for (const c of CASES) writeFileSync(join(WORK, `src/Layouts/pages/ci_${c[0]}.json`), JSON.stringify(layout(c), null, 1))
  writeFileSync(join(WORK, 'src/Layouts/probe_insets_cell.json'), JSON.stringify(CELL, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n@source "./generated";\n@import "./generated/theme.css";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html><head><meta charset="UTF-8" /></head><body><div id="app-root"></div>' +
    '<script type="module" src="/src/main.tsx"></script></body></html>')
  const run = spawnSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, encoding: 'utf8' })
  writeFileSync(join(WORK, 'rjui-build.log'), (run.stdout ?? '') + (run.stderr ?? ''))
  if (run.status !== 0) throw new Error(`rjui build failed (${run.status}) — see ${join(WORK, 'rjui-build.log')}`)
}

// The Collection's box, whether it scrolls, and its first cell's place in it.
function read(page, id) {
  return page.evaluate((cid) => {
    const box = document.getElementById(cid)
    const cell = document.getElementById(`${cid}_item_0`)
    if (!box || !cell) return null
    const b = box.getBoundingClientRect()
    const c = cell.getBoundingClientRect()
    const style = getComputedStyle(box)
    return { w: b.width, h: b.height, x: c.left - b.left + box.scrollLeft, y: c.top - b.top + box.scrollTop,
      scrollLeft: box.scrollLeft, overflow: `${style.overflowX}/${style.overflowY}`, padding: style.padding }
  }, id)
}

prepare()
await build({
  root: WORK, logLevel: 'warn', plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': join(WORK, 'src') } },
  build: { outDir: join(WORK, 'dist'), emptyOutDir: true },
})
const server = await preview({ root: WORK, logLevel: 'warn', preview: { port: 4196, strictPort: true }, build: { outDir: join(WORK, 'dist') } })
const browser = await chromium.launch()
let failures = 0
try {
  const page = await browser.newPage({ viewport: { width: 400, height: 1400 } })
  await page.goto(server.resolvedUrls.local[0])
  await page.waitForSelector('#root')
  await page.waitForTimeout(300)
  for (const [id, extra, wantX, wantY] of CASES) {
    const m = await read(page, id)
    const problems = []
    if (!m) problems.push('not drawn (see the rjui build log)')
    else {
      if (Math.abs(m.w - 300) > 0.5) problems.push(`the Collection is ${m.w}px wide, not 300`)
      if (!/auto|scroll/.test(m.overflow)) problems.push(`the Collection's box does not scroll (${m.overflow})`)
      if (Math.abs(m.x - wantX) > 0.5) problems.push(`first cell at x ${m.x}, not ${wantX}`)
      if (Math.abs(m.y - wantY) > 0.5) problems.push(`first cell at y ${m.y}, not ${wantY}`)
      if (extra.paging && m.scrollLeft !== 0) problems.push(`the pager rests scrolled ${m.scrollLeft}px`)
    }
    failures += problems.length ? 1 : 0
    console.log(`COLLECTION_INSETS ${id.padEnd(14)} ${m ? `box ${m.w}x${m.h} ${m.overflow} padding ${m.padding} first cell x ${m.x} y ${m.y}` : ''}` +
      `${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
  }
} finally {
  await browser.close()
  server.httpServer.close()
}
rmSync(WORK, { recursive: true, force: true })
console.log(`COLLECTION_INSETS ${failures} Collection(s) break the rule`)
process.exit(failures ? 1 : 0)
