// Label gravity probe — NOT part of the conformance suite (a fixture shows one
// Label, and this rule is about where the text sits across a row of shapes).
// Run explicitly:
//
//   npm run label-gravity-probe
//
// The rule (4f 2026-09-27): a Label's text sits at the vertical its gravity
// names (top, bottom, centerVertical / center), else the middle — the canon's
// leafOwnFrameChannel default; across, at textAlign's position, else at the
// horizontal its gravity names (left, right, centerHorizontal / center), else
// the start. A single-run web label is a flex ROW; until jsonui-cli 1.9.0 the
// base converter also mapped gravity as a column's onto it, so `right` drew
// the text at the bottom, `bottom` at the bottom end, and `centerVertical` in
// the middle across as well.
//
// The lines of a multi-line Label follow the same rule across (4f round 6,
// 2026-09-27): textAlign, else the horizontal part of gravity, else the
// start. The `ml_*` labels are wrapContent-wide with two lines of different
// lengths (a `\n`); the `wrap_*` ones 150px wide with a text that wraps.
// Until jsonui-cli 1.9.0 gravity placed the text's box but not its lines: a
// wrapped text filled the row and its lines stayed at the start, and so did
// the shorter line of a two-line one.
//
// A responsive gravity (a size class's override) is mapped the same way, so
// it lands on the same axes inside its breakpoint; until jsonui-cli 1.9.0 it
// was mapped as a column's there as well.
//
// The probe writes one layout of 200 x 44 labels (and one wrapContent-wide),
// runs `rjui build` over it (the production codegen), builds it with the
// host's Vite and React, and in headless Chromium — at 400px and at 1100px,
// the regular size class — reads where each label's text box sits in the
// label's box (a DOM Range over the text node). It
// prints one line per label and exits 1 on any that breaks the rule.
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
const WORK = join(HOST_ROOT, '.label-gravity-probe')
function arg(name, env, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : process.env[env] || fallback
}
const RJUI = resolve(arg('--rjui', 'RJUI_TOOLS_PATH', join(HOST_ROOT, '../../../rjui_tools')))
const RUBY = arg('--ruby', 'RUBY_BIN', 'ruby')

// [id, extra attributes, expected vertical, expected horizontal]
const CASES = [
  ['none', {}, 'middle', 'start'],
  ['left', { gravity: 'left' }, 'middle', 'start'],
  ['right', { gravity: 'right' }, 'middle', 'end'],
  ['top', { gravity: 'top' }, 'top', 'start'],
  ['bottom', { gravity: 'bottom' }, 'bottom', 'start'],
  ['centerVertical', { gravity: 'centerVertical' }, 'middle', 'start'],
  ['center', { gravity: 'center' }, 'middle', 'middle'],
  ['centerHorizontal', { gravity: 'centerHorizontal' }, 'middle', 'middle'],
  ['bottomRight', { gravity: ['bottom', 'right'] }, 'bottom', 'end'],
  ['textAlignWins', { gravity: 'right', textAlign: 'center' }, 'middle', 'middle'],
  ['wrapBottom', { gravity: 'bottom', width: 'wrapContent' }, 'bottom', 'start'],
  ['fillRight', { gravity: 'right', width: 'matchParent' }, 'middle', 'end'],
  ['wrapHeightRight', { gravity: 'right', height: 'wrapContent' }, 'middle', 'end'],
  // A size class's gravity replaces the base one, on the same axes: at the
  // regular width (lg:, 1100px here) these take the second pair.
  ['respRight', { gravity: 'top', responsive: { regular: { gravity: 'right' } } }, 'top', 'start', 'middle', 'end'],
  ['respBottom', { gravity: 'left', textAlign: 'center', responsive: { regular: { gravity: 'bottom' } } }, 'middle', 'middle', 'bottom', 'middle'],
]
// [id, extra attributes, where every line sits across the label's box]
const TWO_LINES = 'Go\nGo Go Go Go'
const WRAPS = 'Go Go Go Go Go Go Go Go Go Go Go Go Go'
const LINE_CASES = [
  ['ml_none', { text: TWO_LINES }, 'start'],
  ['ml_center', { text: TWO_LINES, gravity: 'center' }, 'middle'],
  ['ml_right', { text: TWO_LINES, gravity: 'right' }, 'end'],
  ['ml_textAlign', { text: TWO_LINES, textAlign: 'center', gravity: 'left' }, 'middle'],
  ['wrap_none', { text: WRAPS, width: 150 }, 'start'],
  ['wrap_center', { text: WRAPS, width: 150, gravity: 'center' }, 'middle'],
  ['wrap_right', { text: WRAPS, width: 150, gravity: 'right' }, 'end'],
  ['wrap_chz', { text: WRAPS, width: 150, gravity: 'centerHorizontal' }, 'middle'],
]
const LAYOUT = {
  type: 'View', id: 'root', width: 'matchParent', orientation: 'vertical', spacing: 6,
  child: [
    ...CASES.map(([id, extra]) => ({
      type: 'Label', id: `lg_${id}`, text: 'Go', fontColor: '#000000', width: 200, height: 44, ...extra,
    })),
    ...LINE_CASES.map(([id, extra]) => ({
      type: 'Label', id: `lg_${id}`, fontColor: '#000000', fontSize: 14, lines: 0, width: 'wrapContent', height: 'wrapContent', ...extra,
    })),
  ],
}
const MAIN = `
import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { LabelGravityProbe } from './generated/components/LabelGravityProbe'
createRoot(document.getElementById('app-root')!).render(<LabelGravityProbe data={{}} />)
`

function prepare() {
  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(join(WORK, 'src/Layouts/pages'), { recursive: true })
  mkdirSync(join(WORK, 'src/Layouts/Resources'), { recursive: true })
  cpSync(join(HOST_ROOT, 'src/Strings'), join(WORK, 'src/Strings'), { recursive: true })
  writeFileSync(join(WORK, 'rjui.config.json'), readFileSync(join(HOST_ROOT, 'rjui.config.json')))
  writeFileSync(join(WORK, 'src/Layouts/pages/label_gravity_probe.json'), JSON.stringify(LAYOUT, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n@source "./generated";\n@import "./generated/theme.css";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html><head><meta charset="UTF-8" /></head><body><div id="app-root"></div>' +
    '<script type="module" src="/src/main.tsx"></script></body></html>')
  const run = spawnSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, encoding: 'utf8' })
  writeFileSync(join(WORK, 'rjui-build.log'), (run.stdout ?? '') + (run.stderr ?? ''))
  if (run.status !== 0) throw new Error(`rjui build failed (${run.status}) — see ${join(WORK, 'rjui-build.log')}`)
}

// Where a label's text box sits in the label's box, in px from each edge.
function read(page, id) {
  return page.evaluate((lid) => {
    const box = document.getElementById(lid)
    if (!box) return null
    const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT)
    const text = walker.nextNode()
    if (!text) return null
    const range = document.createRange()
    range.selectNodeContents(text)
    const t = range.getBoundingClientRect()
    const b = box.getBoundingClientRect()
    return { w: b.width, h: b.height, top: t.top - b.top, bottom: b.bottom - t.bottom, left: t.left - b.left, right: b.right - t.right }
  }, id)
}

// Each line of a label's text: its px from the label box's left and right
// edges (the text's client rects, grouped by their top).
function readLines(page, id) {
  return page.evaluate((lid) => {
    const box = document.getElementById(lid)
    if (!box) return null
    const range = document.createRange()
    range.selectNodeContents(box)
    const b = box.getBoundingClientRect()
    const lines = new Map()
    for (const r of range.getClientRects()) {
      if (r.width < 1) continue
      const key = Math.round(r.top)
      const line = lines.get(key) || { left: Infinity, right: -Infinity }
      line.left = Math.min(line.left, r.left); line.right = Math.max(line.right, r.right)
      lines.set(key, line)
    }
    return { w: b.width, lines: [...lines.entries()].sort((x, y) => x[0] - y[0]).map(([, l]) => ({ left: l.left - b.left, right: b.right - l.right })) }
  }, id)
}

function where(near, far) {
  if (Math.abs(near - far) <= 2) return 'middle'
  return near < far ? 'near' : 'far'
}

prepare()
await build({
  root: WORK, logLevel: 'warn', plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': join(WORK, 'src') } },
  build: { outDir: join(WORK, 'dist'), emptyOutDir: true },
})
const server = await preview({ root: WORK, logLevel: 'warn', preview: { port: 4198, strictPort: true }, build: { outDir: join(WORK, 'dist') } })
const browser = await chromium.launch()
let failures = 0
try {
  for (const [viewport, regular] of [[400, false], [1100, true]]) {
  const page = await browser.newPage({ viewport: { width: viewport, height: 900 } })
  await page.goto(server.resolvedUrls.local[0])
  await page.waitForSelector('#root')
  await page.waitForTimeout(300)
  for (const [id, extra, baseV, baseH, regV, regH] of CASES) {
    const wantV = regular && regV ? regV : baseV
    const wantH = regular && regH ? regH : baseH
    const m = await read(page, `lg_${id}`)
    const v = m && { near: 'top', far: 'bottom', middle: 'middle' }[where(m.top, m.bottom)]
    const h = m && (m.left + m.right < 2 ? 'start' : { near: 'start', far: 'end', middle: 'middle' }[where(m.left, m.right)])
    const problems = []
    if (!m) problems.push('not drawn')
    else {
      if (m.h < 40 && extra.height !== 'wrapContent') problems.push(`the label is ${m.h}px tall`)
      if (v !== wantV) problems.push(`vertical ${v}, not ${wantV}`)
      if (h !== wantH) problems.push(`horizontal ${h}, not ${wantH}`)
    }
    failures += problems.length ? 1 : 0
    console.log(`LABEL_GRAVITY ${String(viewport).padStart(4)}px ${id.padEnd(16)} ${m ? `box ${m.w}x${m.h} text top ${m.top.toFixed(1)} bottom ${m.bottom.toFixed(1)} left ${m.left.toFixed(1)} right ${m.right.toFixed(1)}` : ''}` +
      `${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
  }
  for (const [id, , want] of LINE_CASES) {
    const m = await readLines(page, `lg_${id}`)
    const problems = []
    if (!m) problems.push('not drawn')
    else {
      if (m.lines.length < 2) problems.push(`${m.lines.length} line(s), not 2 or more`)
      for (const [i, l] of m.lines.entries()) {
        const at = l.left < 1.5 && l.right < 1.5 ? 'fills' : (Math.abs(l.left - l.right) <= 2 ? 'middle' : (l.left < 1.5 ? 'start' : (l.right < 1.5 ? 'end' : 'off')))
        if (at !== 'fills' && at !== want) problems.push(`line ${i + 1} ${at}, not ${want}`)
      }
      if (!m.lines.some((l) => !(l.left < 1.5 && l.right < 1.5))) problems.push('no line shorter than the box: nothing to tell')
    }
    failures += problems.length ? 1 : 0
    console.log(`LABEL_GRAVITY ${String(viewport).padStart(4)}px ${id.padEnd(16)} ${m ? `box ${m.w.toFixed(1)} ${m.lines.map((l) => `line left ${l.left.toFixed(1)} right ${l.right.toFixed(1)}`).join(', ')}` : ''}` +
      `${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
  }
  await page.close()
  }
} finally {
  await browser.close()
  server.httpServer.close()
}
rmSync(WORK, { recursive: true, force: true })
console.log(`LABEL_GRAVITY ${failures} label(s) break the rule`)
process.exit(failures ? 1 : 0)
