// userInteractionEnabled probe — NOT part of the conformance suite (no
// fixture writes the flag, and none has a Label or a View with onClick drawn
// as a button, so the suite cannot see either). Run explicitly:
//
//   npm run interaction-stop-probe
//
// The rule (jsonui-cli 1.9.0): what the flag stops starts from no pointer, no
// keyboard and no screen reader — false, a binding while it is false, on the
// element or around it — and a tap the tap rule makes a button (a Label or a
// View with onClick) is a button to the keyboard and to a screen reader.
//
// The probe writes one layout, runs `rjui build` over it (the production
// codegen), builds it with the host's Vite and React, and drives it in
// headless Chromium with the bound stop open and closed. For each element:
//   - keyboard: reached by Tab, and what Enter / Space / typing moved;
//   - screen reader: in Chromium's accessibility tree (not ignored), its role;
//   - pointer: what a click at its centre moved.
// It prints the table and exits 1 on any row that breaks the rule. The rows
// with no stop (…Plain), and the bound ones while open, are the controls: they
// say each path reaches what it should.
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
const WORK = join(HOST_ROOT, '.interaction-stop-probe')
function arg(name, env, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : process.env[env] || fallback
}
const RJUI = resolve(arg('--rjui', 'RJUI_TOOLS_PATH', join(HOST_ROOT, '../../../rjui_tools')))
const RUBY = arg('--ruby', 'RUBY_BIN', 'ruby')

// ------------------------------------------------------------ the layout
const kids = (s) => [
  { type: 'Button', id: `btnIn${s}`, text: `btnIn${s}`, onClick: `@{onBtnIn${s}}` },
  { type: 'Label', id: `lblIn${s}`, text: `lblIn${s}`, onClick: `@{onLblIn${s}}` },
  { type: 'View', id: `viewIn${s}`, width: 80, height: 30, background: '#3366CC', onClick: `@{onViewIn${s}}` },
  { type: 'Switch', id: `swIn${s}`, isOn: `@{swIn${s}}` },
  { type: 'TextField', id: `tfIn${s}`, text: `@{tfIn${s}}`, hint: `tfIn${s}`, width: 160 },
  { type: 'Label', id: `linkIn${s}`, text: `see https://example.com/${s}`, linkable: true },
]
const data = [{ name: 'gateOpen', class: 'Bool', defaultValue: 'true' }]
for (const s of ['Plain', 'False', 'Bound']) {
  for (const n of ['onBtnIn', 'onLblIn', 'onViewIn']) data.push({ name: `${n}${s}`, class: '() -> Void' })
  data.push({ name: `swIn${s}`, class: 'Bool', defaultValue: 'false' }, { name: `tfIn${s}`, class: 'String', defaultValue: '""' })
}
data.push({ name: 'onBtnSelf', class: '() -> Void' }, { name: 'swSelf', class: 'Bool', defaultValue: 'false' },
  { name: 'tfSelf', class: 'String', defaultValue: '""' })
const LAYOUT = {
  type: 'View', id: 'root', width: 'matchParent', height: 'matchParent', orientation: 'vertical', spacing: 6, data,
  child: [
    { type: 'View', id: 'parPlain', orientation: 'vertical', spacing: 4, child: kids('Plain') },
    { type: 'View', id: 'parFalse', orientation: 'vertical', spacing: 4, userInteractionEnabled: false, child: kids('False') },
    { type: 'View', id: 'parBound', orientation: 'vertical', spacing: 4, userInteractionEnabled: '@{gateOpen}', child: kids('Bound') },
    { type: 'Button', id: 'btnSelf', text: 'btnSelf', onClick: '@{onBtnSelf}', userInteractionEnabled: false },
    { type: 'Switch', id: 'swSelf', isOn: '@{swSelf}', userInteractionEnabled: false },
    { type: 'TextField', id: 'tfSelf', text: '@{tfSelf}', hint: 'tfSelf', width: 160, userInteractionEnabled: false },
    { type: 'Label', id: 'linkSelf', text: 'see https://example.com/self', linkable: true, userInteractionEnabled: false },
  ],
}

// The page: the generated component with counting handlers; an anchor's
// activation counts for the Label that holds it (navigation prevented).
const MAIN = `
import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { InteractionStopProbe } from './generated/components/InteractionStopProbe'
const w = window as unknown as { __counts: Record<string, number>; __setGate: (open: boolean) => void }
w.__counts = {}
const bump = (k: string) => { w.__counts[k] = (w.__counts[k] ?? 0) + 1 }
document.addEventListener('click', (e) => {
  const a = (e.target as HTMLElement).closest('a')
  if (!a) return
  e.preventDefault()
  bump((a.closest('[id]') as HTMLElement | null)?.id ?? 'anchor?')
}, true)
function Probe() {
  const [state, setState] = useState<Record<string, unknown>>({ gateOpen: true })
  w.__setGate = (open) => setState((s) => ({ ...s, gateOpen: open }))
  const d: Record<string, unknown> = { ...state }
  const set = (k: string) => (v: unknown) => { bump(k); setState((s) => ({ ...s, [k]: v })) }
  for (const s of ['Plain', 'False', 'Bound']) {
    for (const n of ['btnIn', 'lblIn', 'viewIn']) d['on' + n[0].toUpperCase() + n.slice(1) + s] = () => bump(n + s)
    d['onSwIn' + s + 'Change'] = set('swIn' + s)
    d['onTfIn' + s + 'Change'] = set('tfIn' + s)
  }
  d.onBtnSelf = () => bump('btnSelf')
  d.onSwSelfChange = set('swSelf')
  d.onTfSelfChange = set('tfSelf')
  return <InteractionStopProbe data={d} />
}
createRoot(document.getElementById('app-root')!).render(<Probe />)
`

function prepare() {
  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(join(WORK, 'src/Layouts/pages'), { recursive: true })
  mkdirSync(join(WORK, 'src/Layouts/Resources'), { recursive: true })
  // the host's strings: rjui build writes the StringManager the component imports from them
  cpSync(join(HOST_ROOT, 'src/Strings'), join(WORK, 'src/Strings'), { recursive: true })
  const config = JSON.parse(readFileSync(join(HOST_ROOT, 'rjui.config.json'), 'utf8'))
  writeFileSync(join(WORK, 'rjui.config.json'), JSON.stringify(config, null, 2))
  writeFileSync(join(WORK, 'src/Layouts/pages/interaction_stop_probe.json'), JSON.stringify(LAYOUT, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n@source "./generated";\n@import "./generated/theme.css";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html><head><meta charset="UTF-8" /></head><body><div id="app-root"></div>' +
    '<script type="module" src="/src/main.tsx"></script></body></html>')
  const run = spawnSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, encoding: 'utf8' })
  writeFileSync(join(WORK, 'rjui-build.log'), (run.stdout ?? '') + (run.stderr ?? ''))
  if (run.status !== 0) throw new Error(`rjui build failed (${run.status}) — see ${join(WORK, 'rjui-build.log')}`)
}

const TARGETS = []
for (const s of ['Plain', 'False', 'Bound']) for (const n of ['btnIn', 'lblIn', 'viewIn', 'swIn', 'tfIn', 'linkIn']) TARGETS.push(n + s)
TARGETS.push('btnSelf', 'swSelf', 'tfSelf', 'linkSelf')
const stopped = (t, open) => t.endsWith('False') || /Self$/.test(t) || (t.endsWith('Bound') && !open)
// What each element's operation is, by the key that makes it: a Switch takes
// Space, a text field typing, the rest Enter (and Space for the buttons).
const kind = (t) => t.replace(/In(Plain|False|Bound)$|Self$/, '')

async function measure(page, open) {
  await page.evaluate((o) => window.__setGate(o), open)
  await page.waitForTimeout(150)
  const counts = () => page.evaluate(() => ({ ...window.__counts }))
  const owner = () => page.evaluate((ts) => {
    let el = document.activeElement
    while (el && el !== document.body) { if (ts.includes(el.id)) return el.id; el = el.parentElement }
    return null
  }, TARGETS)
  await page.evaluate(() => { document.activeElement?.blur?.() })
  const keyboard = {}
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press('Tab')
    const t = await owner()
    const tag = await page.evaluate(() => document.activeElement?.tagName ?? '-')
    if (!t) { if (tag === 'BODY' && i > 0) break; continue }
    if (keyboard[t]) continue
    const r = {}
    for (const [key, act] of [['enter', () => page.keyboard.press('Enter')], ['space', () => page.keyboard.press('Space')],
      ['type', () => page.keyboard.type('x')]]) {
      const before = (await counts())[t] ?? 0
      await act()
      await page.waitForTimeout(40)
      r[key] = ((await counts())[t] ?? 0) - before
      await page.evaluate((id) => {
        const el = document.getElementById(id)
        const f = el?.matches('a,button,input,[tabindex]') ? el : el?.querySelector('a,button,input,[tabindex]')
        f?.focus()
      }, t)
    }
    keyboard[t] = r
  }
  const client = await page.context().newCDPSession(page)
  await client.send('DOM.enable')
  await client.send('Accessibility.enable')
  const { root } = await client.send('DOM.getDocument', { depth: -1 })
  const { nodes } = await client.send('Accessibility.getFullAXTree')
  const tree = {}
  const pointer = {}
  for (const t of TARGETS) {
    const sel = `#${t} a, #${t} button, #${t} input, button#${t}, input#${t}, #${t}[role=button]`
    const { nodeId } = await client.send('DOM.querySelector', { nodeId: root.nodeId, selector: sel })
    if (nodeId) {
      const { node } = await client.send('DOM.describeNode', { nodeId })
      const ax = nodes.find((n) => n.backendDOMNodeId === node.backendNodeId)
      tree[t] = ax && !ax.ignored ? ax.role?.value ?? '?' : null
    }
    const box = await page.locator(`#${t}`).boundingBox()
    const before = (await counts())[t] ?? 0
    if (box) await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
    await page.waitForTimeout(30)
    pointer[t] = ((await counts())[t] ?? 0) - before
    await page.keyboard.press('Escape')
  }
  await client.detach()
  return { keyboard, tree, pointer }
}

function judge(open, m) {
  const out = []
  for (const t of TARGETS) {
    const k = m.keyboard[t]
    const moved = k ? k.enter + k.space + k.type : 0
    const row = `${t.padEnd(12)} key=${k ? `${k.enter}${k.space}${k.type}` : '--'} tree=${m.tree[t] ?? '-'} pointer=${m.pointer[t]}`
    const problems = []
    if (stopped(t, open)) {
      if (k) problems.push('reached by Tab')
      if (m.tree[t]) problems.push('in the accessibility tree')
      if (m.pointer[t]) problems.push('a click moved it')
    } else {
      if (!k) problems.push('not reached by Tab')
      else if (!moved) problems.push('no key moved it')
      if (['lbl', 'view'].includes(kind(t)) && m.tree[t] !== 'button') problems.push(`read as ${m.tree[t]}, not a button`)
      if (!m.tree[t]) problems.push('not in the accessibility tree')
    }
    out.push({ row, problems })
  }
  return out
}

prepare()
await build({
  root: WORK, logLevel: 'warn', plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': join(WORK, 'src') } },
  build: { outDir: join(WORK, 'dist'), emptyOutDir: true },
})
const server = await preview({ root: WORK, logLevel: 'warn', preview: { port: 4196, strictPort: true }, build: { outDir: join(WORK, 'dist') } })
const url = server.resolvedUrls.local[0]
const browser = await chromium.launch()
let failures = 0
try {
  for (const open of [true, false, true]) {
    const page = await browser.newPage({ viewport: { width: 600, height: 1100 } })
    await page.goto(url)
    await page.waitForSelector('#root')
    const rows = judge(open, await measure(page, open))
    console.log(`INTERACTION_STOP bound stop ${open ? 'open' : 'closed'}`)
    for (const { row, problems } of rows) {
      console.log(`INTERACTION_STOP   ${row}${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
      failures += problems.length ? 1 : 0
    }
    await page.close()
  }
} finally {
  await browser.close()
  server.httpServer.close()
}
console.log(`INTERACTION_STOP ${failures} row(s) break the rule`)
process.exit(failures ? 1 : 0)
