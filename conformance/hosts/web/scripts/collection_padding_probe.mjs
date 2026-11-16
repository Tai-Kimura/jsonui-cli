// Collection padding + insets probe — NOT part of the conformance suite (a
// fixture is one Collection and one spelling; this rule is about how two
// attribute families on one Collection add up). Run explicitly:
//
//   npm run collection-padding-probe
//
// The rule (user ruling 2026-09-28, ticket
// rjui-collection-padding-and-insets-on-one-box-override-each-other): a
// Collection's own padding (padding / paddings / the per-edge paddings) is
// OUTSIDE its scroll and its insets are INSIDE — the two add up per edge, as
// iOS and both Compose paths draw them. On the web the padding is a box around
// the scroll container (rjui CollectionConverter#padding_box?), which keeps
// the Collection's id and scrolls. Until jsonui-cli 1.9.0 both sat on one box
// and an inset's side class replaced the padding on that edge (padding 16 with
// insets [0, 0, 0, 30] put the first cell at x 30, not 46), and a bound inset
// wrote all four edges inline, which cancelled the padding everywhere.
//
// The probe writes a page per 300 x 100 Collection (60 x 28 cells), runs
// `rjui build` over it (the production codegen), builds it with the host's
// Vite, React and Tailwind, and in headless Chromium reads, in the Collection's
// drawn box (the page's one child): where the first cell sits, where the
// scroll container's box starts (the padding, outside the scroll), and where
// the first cell sits after the scroll container scrolls 20 along its axis.
// It prints one line per Collection and exits 1 on any that breaks the rule.
//
//   --rjui / RJUI_TOOLS_PATH   default: <repo>/rjui_tools
//   --ruby / RUBY_BIN          default: ruby
//   CHROMIUM_PATH              a Chromium to launch instead of Playwright's own

import { spawnSync } from 'node:child_process'
import { cpSync, mkdirSync, rmSync, writeFileSync, readFileSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { build, preview } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { chromium } from 'playwright'

const HOST_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const WORK = join(HOST_ROOT, '.collection-padding-probe')
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
// [id, extra attributes, the first cell's [x, y] in the Collection's box,
//  the scroll container's [x, y] in it (the padding: outside the scroll)]
const CASES = [
  ['pad_only', { padding: 16 }, [16, 16], [16, 16]],
  ['insets_only', { insets: [0, 0, 0, 30] }, [30, 0], [0, 0]],
  ['pad_insets', { padding: 16, insets: [0, 0, 0, 30] }, [46, 16], [16, 16]],
  ['pad_bound', { padding: 16, insets: ['@{top}', 0, 0, 30] }, [46, 28], [16, 16]],
  ['edge_insets', { paddingLeft: 12, insets: [0, 0, 0, 30] }, [42, 0], [12, 0]],
  ['pads_h10', { paddings: [8, 16], insetHorizontal: 10 }, [26, 8], [16, 8]],
  ['grid_pad', { columns: 2, padding: 16, insets: [4, 0, 0, 30] }, [46, 20], [16, 16]],
  ['row_pad', { layout: 'horizontal', padding: 16, insets: [0, 0, 0, 30] }, [46, 16], [16, 16]],
]
const layout = ([id, extra]) => ({
  type: 'View', id: `page_${id}`, width: 'matchParent', orientation: 'vertical',
  data: [{ name: 'rows', class: 'CollectionDataSource' }, { name: 'top', class: 'Int', defaultValue: 12 }],
  child: [{
    type: 'Collection', id, width: 300, height: 100, background: '#EEEEEE', items: '@{rows}',
    sections: [{ cell: 'probe_padding_cell' }], ...extra,
  }],
})
const MAIN = `
import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
const pages = import.meta.glob('./generated/components/Cp*.tsx', { eager: true }) as Record<string, Record<string, unknown>>
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
  for (const c of CASES) writeFileSync(join(WORK, `src/Layouts/pages/cp_${c[0]}.json`), JSON.stringify(layout(c), null, 1))
  writeFileSync(join(WORK, 'src/Layouts/probe_padding_cell.json'), JSON.stringify(CELL, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n@source "./generated";\n@import "./generated/theme.css";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html><head><meta charset="UTF-8" /></head><body><div id="app-root"></div>' +
    '<script type="module" src="/src/main.tsx"></script></body></html>')
  const run = spawnSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, encoding: 'utf8' })
  writeFileSync(join(WORK, 'rjui-build.log'), (run.stdout ?? '') + (run.stderr ?? ''))
  if (run.status !== 0) throw new Error(`rjui build failed (${run.status}) — see ${join(WORK, 'rjui-build.log')}`)
}

// The Collection's drawn box is the page's one child; the scroll container is
// the element with the Collection's id.
function read(page, id, across) {
  return page.evaluate(async ([cid, across]) => {
    const outer = document.getElementById(`page_${cid}`)?.firstElementChild
    const scroller = document.getElementById(cid)
    const cell = document.getElementById(`${cid}_item_0`)
    if (!outer || !scroller || !cell) return null
    const o = outer.getBoundingClientRect()
    const at = (el) => { const r = el.getBoundingClientRect(); return [r.left - o.left, r.top - o.top] }
    const first = at(cell)
    const port = at(scroller)
    if (across) scroller.scrollLeft = 20
    else scroller.scrollTop = 20
    await new Promise((done) => requestAnimationFrame(() => done()))
    const scrolled = at(cell)
    const style = getComputedStyle(scroller)
    return { w: o.width, h: o.height, first, port, scrolled, scrolledBy: across ? scroller.scrollLeft : scroller.scrollTop,
      overflow: `${style.overflowX}/${style.overflowY}` }
  }, [id, across])
}

prepare()
await build({
  root: WORK, logLevel: 'warn', plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': join(WORK, 'src') } },
  build: { outDir: join(WORK, 'dist'), emptyOutDir: true },
})
const server = await preview({ root: WORK, logLevel: 'warn', preview: { port: 4197, strictPort: true }, build: { outDir: join(WORK, 'dist') } })
const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})
let failures = 0
const off = (a, b) => Math.abs(a[0] - b[0]) > 0.5 || Math.abs(a[1] - b[1]) > 0.5
try {
  const page = await browser.newPage({ viewport: { width: 400, height: 1400 } })
  await page.goto(server.resolvedUrls.local[0])
  await page.waitForSelector('#root')
  await page.waitForTimeout(300)
  for (const [id, extra, wantFirst, wantPort] of CASES) {
    const across = extra.layout === 'horizontal'
    const m = await read(page, id, across)
    const problems = []
    if (!m) problems.push('not drawn (see the rjui build log)')
    else {
      if (Math.abs(m.w - 300) > 0.5 || Math.abs(m.h - 100) > 0.5) problems.push(`the Collection is ${m.w}x${m.h}, not 300x100`)
      if (!/auto|scroll/.test(m.overflow)) problems.push(`the element with the Collection's id does not scroll (${m.overflow})`)
      if (off(m.first, wantFirst)) problems.push(`first cell at ${m.first}, not ${wantFirst}`)
      if (off(m.port, wantPort)) problems.push(`the scroll container at ${m.port}, not ${wantPort} (the padding scrolls)`)
      const want = across ? [wantFirst[0] - 20, wantFirst[1]] : [wantFirst[0], wantFirst[1] - 20]
      if (m.scrolledBy !== 20 || off(m.scrolled, want)) {
        problems.push(`scrolled 20: first cell at ${m.scrolled}, not ${want} (scrolled by ${m.scrolledBy})`)
      }
    }
    failures += problems.length ? 1 : 0
    console.log(`COLLECTION_PADDING ${id.padEnd(12)} ${m ? `box ${m.w}x${m.h} scroll ${m.overflow} at ${m.port} first cell ${m.first}` : ''}` +
      `${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
  }
} finally {
  await browser.close()
  server.httpServer.close()
}
rmSync(WORK, { recursive: true, force: true })
console.log(`COLLECTION_PADDING ${failures} Collection(s) break the rule`)
process.exit(failures ? 1 : 0)
