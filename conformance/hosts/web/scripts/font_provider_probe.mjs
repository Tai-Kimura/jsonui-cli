// Font provider probe — NOT part of the conformance suite (a fixture draws
// with no app configuration, and this rule is about what the app's
// Configuration.Font does to every text). Run explicitly:
//
//   npm run font-provider-probe
//
// The rule (P1, the requester's ruling 2026-11-13): every text is the app's
// font. A component that writes no fontFamily still goes through
// Configuration.Font.resolve — the app's fontProvider when it sets one, else
// Configuration.Font.family — as iOS (sjuiFont(FontSpec(family: nil, ...)),
// ProviderReachesEveryTextTests) and KotlinJsonUI (Configuration.Font.resolve)
// do. Until this probe's change only a written fontFamily (or a bound
// `font`) reached it: the other texts took the page's inherited font
// (ticket jui-font-provider-not-reached-without-font-attributes-android-web).
//
// The probe writes one layout of the ten components that draw text, none of
// them with a font attribute, and a Label with a fontFamily as the control;
// runs `rjui build` over it (the production codegen); builds it with the
// host's Vite and React; and in headless Chromium reads the computed
// font-family of each component's text in three runs:
//   provider  the app sets Configuration.Font.fontProvider: every text is
//             the provider's face (the control its own family through it);
//   family    the app sets only Configuration.Font.family: every text is
//             that family (the control its own written one);
//   none      the app sets neither: no text is either face (the page's).
//   weights   the provider returns a face per weight (as client / bar do:
//             Regular for a spec with none): each text is the face of the
//             weight it draws — a Segment's and a Radio title's medium, a
//             Button's regular — and every text's computed font-weight is the
//             `none` run's (the provider does not thin or thicken a text).
// It prints one line per component and run, and exits 1 on any that breaks.
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
const WORK = join(HOST_ROOT, '.font-provider-probe')
function arg(name, env, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : process.env[env] || fallback
}
const RJUI = resolve(arg('--rjui', 'RJUI_TOOLS_PATH', join(HOST_ROOT, '../../../rjui_tools')))
const RUBY = arg('--ruby', 'RUBY_BIN', 'ruby')

const PROVIDER_FACE = 'ProbeProviderFace'
const FAMILY_FACE = 'ProbeFamilyFace'
const WRITTEN_FACE = 'ProbeWrittenFace'

// [id, component]; where its text is drawn is read by `textElement` below.
const CASES = [
  ['Label', { type: 'Label', text: 'Label' }],
  ['Button', { type: 'Button', text: 'Button', onClick: '@{tap}' }],
  ['TextField', { type: 'TextField', text: 'TextField' }],
  ['TextView', { type: 'TextView', text: 'TextView' }],
  ['SelectBox', { type: 'SelectBox', items: ['SelectBox', 'Other'] }],
  ['Switch', { type: 'Switch', label: 'Switch' }],
  ['CheckBox', { type: 'CheckBox', label: 'CheckBox' }],
  ['Radio', { type: 'Radio', items: ['Radio', 'Other'] }],
  ['RadioTitle', { type: 'Radio', text: 'RadioTitle', items: ['One', 'Two'] }],
  ['IconLabel', { type: 'IconLabel', text: 'IconLabel' }],
  ['Segment', { type: 'Segment', items: ['Segment', 'Other'] }],
]
const CONTROL = ['written', { type: 'Label', text: 'written', fontFamily: WRITTEN_FACE }]

const LAYOUT = {
  type: 'View', id: 'root', width: 'matchParent', orientation: 'vertical', spacing: 6,
  child: [...CASES, CONTROL].map(([id, c]) => ({ ...c, id: `fp_${id}` })),
}
const MAIN = `
import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { Configuration } from './lib/jsonui/Configuration'
import { FontProviderProbe } from './generated/components/FontProviderProbe'
const run = new URLSearchParams(window.location.search).get('run')
if (run === 'provider') {
  Configuration.Font.fontProvider = (spec) => ({ fontFamily: spec.family ?? '${PROVIDER_FACE}, monospace' })
} else if (run === 'weights') {
  const face = { medium: 'Medium', semibold: 'SemiBold', bold: 'Bold' }
  Configuration.Font.fontProvider = (spec) => ({ fontFamily: spec.family ?? 'ProbeW' + (face[String(spec.weight ?? '').toLowerCase()] ?? 'Regular') + ', monospace' })
} else if (run === 'family') {
  Configuration.Font.family = '${FAMILY_FACE}, monospace'
}
createRoot(document.getElementById('app-root')!).render(<FontProviderProbe data={{ tap: () => {} }} />)
`

function prepare() {
  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(join(WORK, 'src/Layouts/pages'), { recursive: true })
  mkdirSync(join(WORK, 'src/Layouts/Resources'), { recursive: true })
  cpSync(join(HOST_ROOT, 'src/Strings'), join(WORK, 'src/Strings'), { recursive: true })
  writeFileSync(join(WORK, 'rjui.config.json'), readFileSync(join(HOST_ROOT, 'rjui.config.json')))
  writeFileSync(join(WORK, 'src/Layouts/pages/font_provider_probe.json'), JSON.stringify(LAYOUT, null, 1))
  writeFileSync(join(WORK, 'src/main.tsx'), MAIN)
  writeFileSync(join(WORK, 'src/index.css'), '@import "tailwindcss";\n@source "./generated";\n@import "./generated/theme.css";\n')
  writeFileSync(join(WORK, 'index.html'),
    '<!doctype html><html><head><meta charset="UTF-8" /></head><body><div id="app-root"></div>' +
    '<script type="module" src="/src/main.tsx"></script></body></html>')
  const run = spawnSync(RUBY, [join(RJUI, 'bin/rjui'), 'build'], { cwd: WORK, encoding: 'utf8' })
  writeFileSync(join(WORK, 'rjui-build.log'), (run.stdout ?? '') + (run.stderr ?? ''))
  if (run.status !== 0) throw new Error(`rjui build failed (${run.status}) — see ${join(WORK, 'rjui-build.log')}`)
}

// The computed font-family the component's own text is drawn in: the first
// text node whose characters are the case's label (the control `<input>` /
// `<textarea>` / `<select>` draw theirs themselves, so their own family).
function read(page, id, text) {
  return page.evaluate(([cid, want]) => {
    const box = document.getElementById(cid)
    if (!box) return { where: 'not drawn' }
    const field = want === 'RadioTitle' ? null : [box, ...box.querySelectorAll('input, textarea, select')].find((e) =>
      ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.tagName))
    if (field) return { where: field.tagName.toLowerCase(), family: getComputedStyle(field).fontFamily, weight: getComputedStyle(field).fontWeight }
    const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT)
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.textContent.trim() === want) {
        return { where: n.parentElement.tagName.toLowerCase(), family: getComputedStyle(n.parentElement).fontFamily, weight: getComputedStyle(n.parentElement).fontWeight }
      }
    }
    return { where: 'no text' }
  }, [id, text])
}

prepare()
await build({
  root: WORK, logLevel: 'warn', plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': join(WORK, 'src') } },
  build: { outDir: join(WORK, 'dist'), emptyOutDir: true },
})
const server = await preview({ root: WORK, logLevel: 'warn', preview: { port: 4197, strictPort: true }, build: { outDir: join(WORK, 'dist') } })
const browser = await chromium.launch()
let failures = 0
try {
  const noneWeight = {}
  for (const run of ['none', 'provider', 'family', 'weights']) {
    const page = await browser.newPage({ viewport: { width: 400, height: 900 } })
    await page.goto(`${server.resolvedUrls.local[0]}?run=${run}`)
    await page.waitForSelector('#root')
    await page.waitForTimeout(300)
    for (const [id] of [...CASES, CONTROL]) {
      const m = await read(page, `fp_${id}`, id)
      const family = m.family ?? ''
      const drawnWeight = { Segment: 'Medium', RadioTitle: 'Medium' }[id] ?? 'Regular'
      const want = id === 'written' ? WRITTEN_FACE : { provider: PROVIDER_FACE, family: FAMILY_FACE, none: null, weights: `ProbeW${drawnWeight}` }[run]
      if (run === 'none') noneWeight[id] = m.weight
      const problems = []
      if (run !== 'none' && m.weight !== noneWeight[id]) problems.push(`weight ${m.weight}, not ${noneWeight[id]} as with nothing set`)
      if (!m.family) problems.push(m.where)
      else if (want && !family.includes(want)) problems.push(`drawn in ${family}, not ${want}`)
      else if (!want && (family.includes(PROVIDER_FACE) || family.includes(FAMILY_FACE))) problems.push(`drawn in ${family} with nothing set`)
      failures += problems.length ? 1 : 0
      console.log(`FONT_PROVIDER ${run.padEnd(8)} ${id.padEnd(10)} ${m.where.padEnd(8)} w${m.weight ?? '-'} ${family}${problems.length ? `  <- ${problems.join('; ')}` : ''}`)
    }
    await page.close()
  }
} finally {
  await browser.close()
  server.httpServer.close()
}
rmSync(WORK, { recursive: true, force: true })
console.log(`FONT_PROVIDER ${failures} text(s) break the rule`)
process.exit(failures ? 1 : 0)
