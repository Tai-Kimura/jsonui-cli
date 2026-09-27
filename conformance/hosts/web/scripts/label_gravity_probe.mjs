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
// The probe writes one layout of 200 x 44 labels (and one wrapContent-wide),
// runs `rjui build` over it (the production codegen), builds it with the
// host's Vite and React, and in headless Chromium reads where each label's
// text box sits in the label's box (a DOM Range over the text node). It
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
]
const LAYOUT = {
  type: 'View', id: 'root', width: 'matchParent', orientation: 'vertical', spacing: 6,
  child: CASES.map(([id, extra]) => ({
    type: 'Label', id: `lg_${id}`, text: 'Go', fontColor: '#000000', width: 200, height: 44, ...extra,
  })),
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
  const page = await browser.newPage({ viewport: { width: 400, height: 900 } })
  await page.goto(server.resolvedUrls.local[0])
  await page.waitForSelector('#root')
  await page.waitForTimeout(300)
  for (const [id, extra, wantV, wantH] of CASES) {
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
    console.log(`LABEL_GRAVITY ${id.padEnd(16)} ${m ? `box ${m.w}x${m.h} text top ${m.top.toFixed(1)} bottom ${m.bottom.toFixed(1)} left ${m.left.toFixed(1)} right ${m.right.toFixed(1)}` : ''}` +
      `${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
  }
  await page.close()
} finally {
  await browser.close()
  server.httpServer.close()
}
rmSync(WORK, { recursive: true, force: true })
console.log(`LABEL_GRAVITY ${failures} label(s) break the rule`)
process.exit(failures ? 1 : 0)
