// SelectBox caret probe — NOT part of the conformance suite (a fixture draws with no app theme, and this rule is
// about the caret under an app's own dark mode). Run explicitly:
//
//   npm run selectbox-caret-probe
//
// The rule (ticket rjui-selectbox-caret-fixed-black-ignores-theme-dark-mode, the orchestrator's ruling 2026-11-14):
// the library's default caret follows the text colour at runtime — whatever makes it, an app's theme.css switching
// on data-theme or on prefers-color-scheme, a fontColor, a bound one — as the browser's own arrow followed the page's
// color-scheme up to 2.5.34; caretAttributes.tintColor wins. 2.5.35 / 2.5.36 baked #000000 into a background SVG at
// build time, and on a dark theme (the admin face's #201C15 surface) it vanished.
//
// The probe writes one layout of SelectBoxes and a Date, runs `rjui build` (the production codegen), builds it with
// the host's Vite and React, and in headless Chromium, under three themes — light, `<html data-theme="dark">`, and
// the OS's dark (prefers-color-scheme) — the page's own theme.css switching the text and surface colours as an app
// does, reads the pixels where each control's caret is drawn and compares the most distinct one with the control's
// background. It prints one line per control and theme, and exits 1 on any caret that cannot be told from its
// background, or that is not drawn in the colour it should follow.
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
import { PNG } from 'pngjs'

const HOST_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const WORK = join(HOST_ROOT, '.selectbox-caret-probe')
function arg(name, env, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : process.env[env] || fallback
}
const RJUI = resolve(arg('--rjui', 'RJUI_TOOLS_PATH', join(HOST_ROOT, '../../../rjui_tools')))
const RUBY = arg('--ruby', 'RUBY_BIN', 'ruby')

const LIGHT = { text: [17, 17, 17], surface: [255, 255, 255] }
const DARK = { text: [240, 232, 220], surface: [32, 28, 21] }   // the admin face's dark: #201C15 surface

// [id, attributes, which colour the caret should be: 'text' (the theme's), or an [r,g,b]]
const CASES = [
  ['plain', { items: ['One', 'Two'] }, 'text'],
  ['date', { selectItemType: 'Date' }, 'text'],
  ['fontColor', { items: ['One'], fontColor: '#2266DD' }, [0x22, 0x66, 0xdd]],
  ['boundColor', { items: ['One'], fontColor: '@{ink}' }, [0x00, 0xaa, 0x55]],
  ['tint', { items: ['One'], fontColor: '#2266DD', caretAttributes: { tintColor: '#DD2222' } }, [0xdd, 0x22, 0x22]],
]
const LAYOUT = {
  type: 'View', id: 'root', width: 'matchParent', orientation: 'vertical', spacing: 8,
  child: CASES.map(([id, extra]) => ({ type: 'SelectBox', id: `sb_${id}`, width: 220, height: 44, ...extra })),
}
const MAIN = `
import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { SelectboxCaretProbe } from './generated/components/SelectboxCaretProbe'
const theme = new URLSearchParams(window.location.search).get('theme')
if (theme === 'data') document.documentElement.setAttribute('data-theme', 'dark')
createRoot(document.getElementById('app-root')!).render(<SelectboxCaretProbe data={{ ink: '#00AA55' }} />)
`
// The app's own theme.css: text and surface switch on data-theme and on the OS's dark, as the admin face's does.
const rgb = (c) => `rgb(${c.join(' ')})`
const THEME = `
:root { color: ${rgb(LIGHT.text)}; background: ${rgb(LIGHT.surface)}; }
:root[data-theme="dark"] { color: ${rgb(DARK.text)}; background: ${rgb(DARK.surface)}; color-scheme: dark; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) { color: ${rgb(DARK.text)}; background: ${rgb(DARK.surface)}; color-scheme: dark; }
}
select, input { background-color: transparent !important; }
`

function prepare() {
  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(join(WORK, 'src/Layouts/pages'), { recursive: true })
  mkdirSync(join(WORK, 'src/Layouts/Resources'), { recursive: true })
  cpSync(join(HOST_ROOT, 'src/Strings'), join(WORK, 'src/Strings'), { recursive: true })
  writeFileSync(join(WORK, 'rjui.config.json'), readFileSync(join(HOST_ROOT, 'rjui.config.json')))
  writeFileSync(join(WORK, 'src/Layouts/pages/selectbox_caret_probe.json'), JSON.stringify(LAYOUT, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/theme.css'), THEME)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n@source "./generated";\n@import "./generated/theme.css";\n@import "./theme.css";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html><head><meta charset="UTF-8" /></head><body><div id="app-root"></div>' +
    '<script type="module" src="/src/main.tsx"></script></body></html>')
  const run = spawnSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, encoding: 'utf8' })
  writeFileSync(join(WORK, 'rjui-build.log'), (run.stdout ?? '') + (run.stderr ?? ''))
  if (run.status !== 0) throw new Error(`rjui build failed (${run.status}) — see ${join(WORK, 'rjui-build.log')}`)
}

const lum = ([r, g, b]) => {
  const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}
const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

// The caret's square: 16 x 16, 12 in from the control's trailing edge, centred (the three faces' one caret).
async function caretPixels(page, id) {
  const box = await page.evaluate((cid) => {
    const el = document.getElementById(cid)
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { x: r.right - 12 - 16, y: r.top + r.height / 2 - 8, w: 16, h: 16 }
  }, id)
  if (!box) return null
  const png = PNG.sync.read(await page.screenshot({ clip: { x: box.x, y: box.y, width: box.w, height: box.h } }))
  const px = []
  for (let i = 0; i < png.data.length; i += 4) px.push([png.data[i], png.data[i + 1], png.data[i + 2]])
  return px
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
  for (const [theme, query, scheme, palette] of [['light', '', 'light', LIGHT], ['data-theme', '?theme=data', 'light', DARK], ['os-dark', '', 'dark', DARK]]) {
    const page = await browser.newPage({ viewport: { width: 400, height: 600 }, colorScheme: scheme, deviceScaleFactor: 2 })
    await page.goto(`${server.resolvedUrls.local[0]}${query}`)
    await page.waitForSelector('#root')
    await page.waitForTimeout(300)
    for (const [id, , want] of CASES) {
      const px = await caretPixels(page, `sb_${id}`)
      const problems = []
      let best = null
      if (!px) problems.push('not drawn')
      else {
        // the most distinct pixel from the page's surface (the control is transparent over it)
        best = px.reduce((a, p) => (dist(p, palette.surface) > dist(a, palette.surface) ? p : a), px[0])
        const c = contrast(best, palette.surface)
        if (c < 3) problems.push(`caret ${best} on ${palette.surface}: contrast ${c.toFixed(2)} < 3`)
        const target = want === 'text' ? palette.text : want
        if (dist(best, target) > 60) problems.push(`caret ${best}, not the colour it follows ${target}`)
      }
      failures += problems.length ? 1 : 0
      console.log(`SELECTBOX_CARET ${theme.padEnd(10)} ${id.padEnd(10)} ${best ? `caret rgb(${best.join(',')})` : ''}` +
        `${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
    }
    await page.close()
  }
} finally {
  await browser.close()
  server.httpServer.close()
}
rmSync(WORK, { recursive: true, force: true })
console.log(`SELECTBOX_CARET ${failures} caret(s) break the rule`)
process.exit(failures ? 1 : 0)
