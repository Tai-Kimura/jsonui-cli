// Collection reorder probe — NOT part of the conformance suite (a fixture is drawn once; a drag is a gesture over
// time and its answer is the handler's call). Run explicitly:
//
//   npm run collection-reorder-probe            (add --video DIR to record a slow pass for people to watch)
//
// The rule is shared/core/reorder_vectors.json (ticket jui-collection-drag-to-reorder, ruling B 2026-11-13): a long
// press picks a row up, it passes a row when its centre goes beyond that row's centre, a locked row is neither
// picked up nor passed, the list scrolls near its edges, and the release decides the move inside the Collection (its
// header: the first place, its footer: the last) and cancels it outside. A screen reader gets "move up" / "move
// down" on every row. The probe writes one layout, runs `rjui build` over it (the production codegen and its reorder
// helper), builds it with the host's Vite and React, and drives it in headless Chromium with the mouse and with
// touch (CDP Input.dispatchTouchEvent): after each step it reads the rows' order and the onReorder calls the page's
// view model received. It prints one line per step and exits 1 on any step that breaks the rule.
//
//   --rjui / RJUI_TOOLS_PATH   default: <repo>/rjui_tools
//   --ruby / RUBY_BIN          default: ruby
//   --video DIR                record the mouse steps, slowed, as a .webm in DIR

import { spawnSync } from 'node:child_process'
import { cpSync, mkdirSync, rmSync, writeFileSync, readFileSync, readdirSync, renameSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { build, preview } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { chromium } from 'playwright'

const HOST_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const WORK = join(HOST_ROOT, '.collection-reorder-probe')
function arg(name, env, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : process.env[env] || fallback
}
const RJUI = resolve(arg('--rjui', 'RJUI_TOOLS_PATH', join(HOST_ROOT, '../../../rjui_tools')))
const RUBY = arg('--ruby', 'RUBY_BIN', 'ruby')
const VIDEO = arg('--video', 'REORDER_PROBE_VIDEO', '')

// ------------------------------------------------------------ the layouts
const CELL = {
  type: 'View', width: 'matchParent', height: 48, background: '#FFFFFF', orientation: 'horizontal', onClick: '@{onTap}',
  data: [{ name: 'name', class: 'String', defaultValue: '' }, { name: 'onTap', class: '(() -> Void)?' }],
  child: [
    { type: 'Label', text: '@{name}', fontSize: 16, weight: 1, paddingLeft: 12, gravity: 'centerVertical', height: 'matchParent' },
    { type: 'View', id: 'grip', width: 44, height: 'matchParent', background: '#DDDDDD',
      child: [{ type: 'Label', text: '≡', fontSize: 18, centerInParent: true }] },
  ],
}
const EDGE = {
  type: 'View', width: 'matchParent', height: 40, background: '#C8D6F0',
  data: [{ name: 'title', class: 'String', defaultValue: '' }],
  child: [{ type: 'Label', text: '@{title}', fontSize: 13, paddingLeft: 12, gravity: 'centerVertical', height: 'matchParent' }],
}
const LAYOUT = {
  type: 'View', id: 'root', width: 'matchParent', orientation: 'vertical', spacing: 24, paddingTop: 16, paddingBottom: 600,
  data: [
    { name: 'free', class: 'CollectionDataSource' }, { name: 'held', class: 'CollectionDataSource' },
    { name: 'onMoveFree', class: '((Int, Int, Int) -> Void)?' }, { name: 'onMoveHeld', class: '((Int, Int, Int) -> Void)?' },
  ],
  child: [
    { type: 'Collection', id: 'free', width: 'matchParent', lazy: 'none', items: '@{free}', cellIdProperty: 'cellId',
      sections: [{ header: 'probe_reorder_edge', cell: 'probe_reorder_cell', footer: 'probe_reorder_edge' }],
      reorderable: true, onReorder: '@{onMoveFree}' },
    { type: 'Collection', id: 'held', width: 'matchParent', lazy: 'none', items: '@{held}', cellIdProperty: 'cellId',
      sections: [{ cell: 'probe_reorder_cell' }],
      reorderable: true, onReorder: '@{onMoveHeld}', reorderHandle: 'grip', reorderLockedProperty: 'locked' },
  ],
}

// The page: the generated component with a view model that moves its rows as onReorder says.
const MAIN = `
import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { CollectionReorderProbe } from './generated/components/CollectionReorderProbe'
type Row = { cellId: string; name: string; locked?: boolean }
const w = window as unknown as { __calls: unknown[]; __reset: () => void }
w.__calls = []
const rows = (names: string[], locked: number[] = []) =>
  names.map((name, i) => ({ cellId: 'id-' + name, name, onTap: () => w.__calls.push(['tap', name]),
                            ...(locked.includes(i) ? { locked: true } : {}) }))
const FREE = rows(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'])
const HELD = rows(['P', 'Q', '— locked —', 'R', 'S'], [2])
const move = (list: Row[], from: number, to: number) => { const next = list.slice(); next.splice(to, 0, next.splice(from, 1)[0]); return next }
function Probe() {
  const [free, setFree] = useState<Row[]>(FREE)
  const [held, setHeld] = useState<Row[]>(HELD)
  w.__reset = () => { setFree(FREE); setHeld(HELD); w.__calls = [] }
  const data = {
    free: { sections: [{ header: { title: 'Header (release here: first place)' }, cells: { data: free },
                         footer: { title: 'Footer (release here: last place)' } }] },
    held: { sections: [{ cells: { data: held } }] },
    onMoveFree: (section: number, from: number, to: number) => { w.__calls.push(['free', section, from, to]); setFree((l) => move(l, from, to)) },
    onMoveHeld: (section: number, from: number, to: number) => { w.__calls.push(['held', section, from, to]); setHeld((l) => move(l, from, to)) },
  }
  return <CollectionReorderProbe data={data as never} />
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
  writeFileSync(join(WORK, 'src/Layouts/pages/collection_reorder_probe.json'), JSON.stringify(LAYOUT, null, 1))
  writeFileSync(join(WORK, 'src/Layouts/probe_reorder_cell.json'), JSON.stringify(CELL, null, 1))
  writeFileSync(join(WORK, 'src/Layouts/probe_reorder_edge.json'), JSON.stringify(EDGE, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n@source "./generated";\n@import "./generated/theme.css";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width" /></head>' +
    '<body><div id="app-root"></div><script type="module" src="/src/main.tsx"></script></body></html>')
  const run = spawnSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, encoding: 'utf8' })
  writeFileSync(join(WORK, 'rjui-build.log'), (run.stdout ?? '') + (run.stderr ?? ''))
  if (run.status !== 0) throw new Error(`rjui build failed (${run.status}) — see ${join(WORK, 'rjui-build.log')}`)
}

// ------------------------------------------------------------ reading and gestures
const order = (page, id) => page.evaluate((cid) =>
  Array.from(document.querySelectorAll(`[id^="${cid}_item_"]`)).map((el) => el.textContent.replace('≡', '').trim()), id)
const calls = (page) => page.evaluate(() => window.__calls)
const box = (page, sel) => page.locator(sel).first().boundingBox()
const row = (page, id) => page.locator('[data-jsonui-reorder-index]', { has: page.locator(`#${id}`) })
const reset = async (page) => { await page.evaluate(() => window.__reset()); await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(150) }

// mouse: press at (x, y), hold, move to (x2, y2) in steps, release
async function mouseDrag(page, x, y, x2, y2, { hold = 650, steps = 20, pause = 0 } = {}) {
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.waitForTimeout(hold)
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(x + ((x2 - x) * i) / steps, y + ((y2 - y) * i) / steps)
    if (pause) await page.waitForTimeout(pause)
  }
  await page.waitForTimeout(120)
  await page.mouse.up()
  await page.waitForTimeout(200)
}

// touch, through CDP: hold (ms) before moving; 0 is a swipe
async function touchDrag(cdp, x, y, x2, y2, hold) {
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
  if (hold) await new Promise((r) => setTimeout(r, hold))
  for (let i = 1; i <= 12; i++) {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + ((x2 - x) * i) / 12, y: y + ((y2 - y) * i) / 12 }] })
    await new Promise((r) => setTimeout(r, 16))
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await new Promise((r) => setTimeout(r, 250))
}

const at = (b, fx = 0.5, fy = 0.5) => [b.x + b.width * fx, b.y + b.height * fy]

let failures = 0
function report(name, ok, detail) {
  failures += ok ? 0 : 1
  console.log(`COLLECTION_REORDER ${ok ? 'ok  ' : 'FAIL'} ${name.padEnd(58)} ${detail}`)
}

// ------------------------------------------------------------ the steps
async function mouseSteps(page, slow) {
  const pause = slow ? 25 : 0
  // 1. A to below C's centre (C's lower part): to 2
  await reset(page)
  let a = await box(page, '#free_item_0'), c = await box(page, '#free_item_2')
  await mouseDrag(page, ...at(a, 0.3), ...at(c, 0.3, 0.75), { pause })
  report('mouse: A released over C\'s lower part -> to 2', JSON.stringify(await calls(page)) === '[["free",0,0,2]]',
    `order=${(await order(page, 'free')).slice(0, 4).join('')} calls=${JSON.stringify(await calls(page))}`)
  // 2. B released over the footer: the last place
  await reset(page)
  const b = await box(page, '#free_item_1')
  const foot = await page.locator('#free > :last-child').boundingBox()
  await mouseDrag(page, ...at(b, 0.3), ...at(foot, 0.3, 0.5), { pause, steps: 30 })
  report('mouse: B released over the footer -> the last place', JSON.stringify(await calls(page)) === '[["free",0,1,11]]',
    `calls=${JSON.stringify(await calls(page))}`)
  // 3. K released over the header: the first place
  await reset(page)
  const k = await box(page, '#free_item_10')
  const head = await page.locator('#free > :first-child').boundingBox()
  await mouseDrag(page, ...at(k, 0.3), ...at(head, 0.3, 0.5), { pause, steps: 30 })
  report('mouse: K released over the header -> the first place', JSON.stringify(await calls(page)) === '[["free",0,10,0]]',
    `calls=${JSON.stringify(await calls(page))}`)
  // 4. released outside the Collection (to its right, past the page's width): cancelled
  await reset(page)
  a = await box(page, '#free_item_0')
  await mouseDrag(page, ...at(a, 0.3), a.x + 10, a.y - 80, { pause })
  report('mouse: released outside the Collection -> cancelled', JSON.stringify(await calls(page)) === '[]',
    `order=${(await order(page, 'free')).slice(0, 3).join('')} calls=${JSON.stringify(await calls(page))}`)
  // 5. a quick press and move is not a drag
  await reset(page)
  a = await box(page, '#free_item_0'); c = await box(page, '#free_item_2')
  await mouseDrag(page, ...at(a, 0.3), ...at(c, 0.3, 0.75), { hold: 100 })
  report('mouse: a press of 100 ms and a move is not a drag', JSON.stringify(await calls(page)) === '[]',
    `calls=${JSON.stringify(await calls(page))}`)
  // 6. a handle: the row's body does not pick it up, the grip does
  await reset(page)
  let p = await box(page, '#held_item_0'), q = await box(page, '#held_item_1')
  await mouseDrag(page, ...at(p, 0.2), ...at(q, 0.2, 0.75), { pause })
  const body = JSON.stringify(await calls(page))
  const grip = await page.locator('#held_item_0 #grip').boundingBox()
  await mouseDrag(page, ...at(grip), grip.x + grip.width / 2, q.y + q.height * 0.75, { pause })
  report('mouse: with a reorderHandle, the body does not drag, the grip does', body === '[]' &&
    JSON.stringify(await calls(page)) === '[["held",0,0,1]]', `body=${body} grip=${JSON.stringify(await calls(page))}`)
  // 7. a locked row is not passed: P dragged far below stops before it
  await reset(page)
  await page.locator('#held').scrollIntoViewIfNeeded()
  await page.evaluate(() => window.scrollBy(0, 200))
  await page.waitForTimeout(150)
  p = await box(page, '#held_item_0')
  const s = await box(page, '#held_item_4')
  const pgrip = await page.locator('#held_item_0 #grip').boundingBox()
  await mouseDrag(page, ...at(pgrip), pgrip.x + pgrip.width / 2, s.y + s.height * 0.75, { pause, steps: 30 })
  report('mouse: a locked row is not passed -> stops before it (to 1)', JSON.stringify(await calls(page)) === '[["held",0,0,1]]',
    `calls=${JSON.stringify(await calls(page))}`)
  // 8. auto-scroll: A held at the bottom edge of the window scrolls the page, and lands further down
  await reset(page)
  await page.setViewportSize({ width: 400, height: 420 })
  a = await box(page, '#free_item_0')
  const vh = 420
  await page.mouse.move(...at(a, 0.3)); await page.mouse.down(); await page.waitForTimeout(650)
  await page.mouse.move(a.x + a.width * 0.3, vh - 6, { steps: 15 })
  await page.waitForTimeout(350)
  await page.mouse.move(a.x + a.width * 0.3, vh / 2, { steps: 10 })   // out of the band: it stops scrolling
  await page.waitForTimeout(200)
  const scrolled = await page.evaluate(() => window.scrollY)
  const under = await page.evaluate(([x, y]) => document.elementsFromPoint(x, y).map((el) => el.id).find((id) => /^free_item_\d+$/.test(id)),
    [a.x + a.width * 0.3, vh / 2])
  await page.mouse.up(); await page.waitForTimeout(250)
  const got = await calls(page)
  report('mouse: held in the bottom band, the page scrolls and the row lands lower', scrolled > 100 && got.length === 1 && got[0][3] >= 4,
    `scrollY=${scrolled} under=${under} calls=${JSON.stringify(got)}`)
  await page.setViewportSize({ width: 400, height: 900 })
}

async function tapSteps(page) {
  await reset(page)
  await page.locator('#free_item_1').click()
  const tapped = JSON.stringify(await calls(page))
  await reset(page)
  const a = await box(page, '#free_item_0'), c = await box(page, '#free_item_2')
  await mouseDrag(page, ...at(a, 0.3), ...at(c, 0.3, 0.75))
  report('a row\'s own tap still taps; a drag\'s release is not a tap', tapped === '[["tap","B"]]' &&
    JSON.stringify(await calls(page)) === '[["free",0,0,2]]', `tap=${tapped} drag=${JSON.stringify(await calls(page))}`)
}

async function a11ySteps(page) {
  await reset(page)
  // as a keyboard user: focus the row's move button (it shows itself), then Enter
  const button = row(page, 'free_item_0').getByRole('button', { name: 'Move down' })
  await button.focus()
  const shown = await button.evaluate((el) => el.getBoundingClientRect().width > 20)
  await page.keyboard.press('Enter')
  await page.waitForTimeout(200)
  const said = await page.locator('#free [role="status"]').first().textContent()
  report('screen reader: A\'s "Move down" -> to 1, and it is said', JSON.stringify(await calls(page)) === '[["free",0,0,1]]' &&
    said === 'Moved to position 2' && shown, `calls=${JSON.stringify(await calls(page))} said="${said}" shownOnFocus=${shown}`)
  const firstUp = await row(page, 'free_item_0').getByRole('button', { name: 'Move up' }).count()
  const lockedButtons = await row(page, 'held_item_2').getByRole('button', { name: /^Move (up|down)$/ }).count()
  const nextToLocked = await row(page, 'held_item_1').getByRole('button', { name: 'Move down' }).count()
  report('screen reader: no "Move up" on the first row, none on / beside a locked row', firstUp === 0 && lockedButtons === 0 &&
    nextToLocked === 0, `firstUp=${firstUp} locked=${lockedButtons} beside=${nextToLocked}`)
}

async function touchSteps(page, cdp) {
  // a long press then a move drags, and the page does not scroll
  await reset(page)
  const a = await box(page, '#free_item_0'), c = await box(page, '#free_item_2')
  await touchDrag(cdp, ...at(a, 0.3), ...at(c, 0.3, 0.75), 650)
  const y1 = await page.evaluate(() => window.scrollY)
  report('touch: a long press and a move drags A to 2, the page does not scroll',
    JSON.stringify(await calls(page)) === '[["free",0,0,2]]' && y1 === 0, `scrollY=${y1} calls=${JSON.stringify(await calls(page))}`)
  // a swipe (no hold) scrolls the page and moves nothing
  await reset(page)
  const e = await box(page, '#free_item_6')
  await touchDrag(cdp, ...at(e, 0.3), e.x + e.width * 0.3, e.y - 250, 0)
  const y2 = await page.evaluate(() => window.scrollY)
  report('touch: a swipe scrolls the page and moves no row', JSON.stringify(await calls(page)) === '[]' && y2 > 50,
    `scrollY=${y2} calls=${JSON.stringify(await calls(page))}`)
}

prepare()
await build({
  root: WORK, logLevel: 'warn', plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': join(WORK, 'src') } },
  build: { outDir: join(WORK, 'dist'), emptyOutDir: true },
})
const server = await preview({ root: WORK, logLevel: 'warn', preview: { port: 4198, strictPort: true }, build: { outDir: join(WORK, 'dist') } })
const url = server.resolvedUrls.local[0]
const browser = await chromium.launch()
try {
  const page = await browser.newPage({ viewport: { width: 400, height: 900 } })
  await page.goto(url)
  await page.waitForSelector('#free_item_0')
  await page.waitForTimeout(300)
  await mouseSteps(page, false)
  await tapSteps(page)
  await a11ySteps(page)
  await page.close()

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  const tpage = await mobile.newPage()
  await tpage.goto(url)
  await tpage.waitForSelector('#free_item_0')
  const cdp = await mobile.newCDPSession(tpage)
  await touchSteps(tpage, cdp)
  await mobile.close()

  if (VIDEO) {
    mkdirSync(VIDEO, { recursive: true })
    const rec = await browser.newContext({ viewport: { width: 400, height: 900 }, recordVideo: { dir: VIDEO, size: { width: 400, height: 900 } } })
    const vpage = await rec.newPage()
    await vpage.goto(url)
    await vpage.waitForSelector('#free_item_0')
    await vpage.waitForTimeout(800)
    await mouseSteps(vpage, true)
    await rec.close()
    const made = readdirSync(VIDEO).filter((f) => f.endsWith('.webm')).sort()
    if (made.length) renameSync(join(VIDEO, made[made.length - 1]), join(VIDEO, 'collection-reorder-web.webm'))
    console.log(`COLLECTION_REORDER video: ${join(VIDEO, 'collection-reorder-web.webm')}`)
  }
} finally {
  await browser.close()
  server.httpServer.close()
}
console.log(`COLLECTION_REORDER ${failures} step(s) break the rule`)
process.exit(failures ? 1 : 0)
