#!/usr/bin/env node
/**
 * Web conformance runner (manifest-driven).
 *
 * Builds the host (vite build), serves it (vite preview), then executes
 * every fixture's screen-test JSON against its route using the vendored
 * jsonui-test-runner Playwright executors, and writes a
 * RESULTS_SCHEMA.md-conformant results file.
 *
 * Options (flag / env / default):
 *   --conformance-dir / JSONUI_CONFORMANCE_DIR   ../../.. of this script
 *   --results / JSONUI_RESULTS_FILE              <conformance>/results/web.results.json
 *   --artifacts / JSONUI_ARTIFACTS_DIR           <conformance>/artifacts/web
 *   --port                                        4177
 *   --workers                                     6
 *   --skip-build                                  reuse existing dist/
 *   --only <prefix>                               run only fixture ids with this prefix (debugging)
 */

import { spawn, spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import type { Page } from 'playwright';
import { ActionExecutor } from './vendor/ActionExecutor.ts';
import { AssertionExecutor } from './vendor/AssertionExecutor.ts';
import type { ScreenTest, TestStep } from './vendor/types.ts';
import { platformIncludes } from './vendor/types.ts';
import { BridgeStateProvider } from './vendor/StateProvider.ts';
import { readBridge, type BridgeSnapshot } from './vendor/StateBridge.ts';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hostDir = path.resolve(scriptDir, '..');

function arg(name: string, envName?: string, fallback?: string): string | undefined {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) return process.argv[idx + 1];
  if (envName && process.env[envName]) return process.env[envName];
  return fallback;
}
const hasFlag = (name: string): boolean => process.argv.includes(name);

const conformanceDir = path.resolve(
  arg('--conformance-dir', 'JSONUI_CONFORMANCE_DIR', path.resolve(hostDir, '../..'))!
);
const resultsFile = path.resolve(
  arg('--results', 'JSONUI_RESULTS_FILE', path.join(conformanceDir, 'results/web.results.json'))!
);
const artifactsDir = path.resolve(
  arg('--artifacts', 'JSONUI_ARTIFACTS_DIR', path.join(conformanceDir, 'artifacts/web'))!
);
const port = Number(arg('--port', undefined, '4177'));
const workers = Number(arg('--workers', undefined, '6'));
const only = arg('--only');

interface ManifestFixture {
  id: string;
  class: 'assertable' | 'visual' | 'interactive';
  platforms: string[];
  mode: string | string[] | null;
  test: string;
  layout: string;
  state?: { afterFirstDraw?: { name: string; set: { var: string; value: string } } } | null;
  testBridge?: TestBridgeSpec | null;
}

/** INTERACTIVE_HOST_CONTRACT.md §6. */
interface TestBridgeSpec {
  data: { name: string; class: string; defaultValue?: unknown }[];
  initialState?: Record<string, unknown>;
  receipt?: { applied: string[]; rejected: { key: string; reason: string }[] };
  remount?: boolean;
}
interface Manifest {
  fixtures: ManifestFixture[];
}

interface ResultEntry {
  id: string;
  status: 'pass' | 'fail' | 'error' | 'skipped';
  detail: string;
  screenshot?: string;
  frames?: string;
  afterFirstDraw?: AfterFirstDrawResult;
}

/**
 * RESULTS_SCHEMA.md `afterFirstDraw`: what the host stamped for a fixture
 * that declares `state.afterFirstDraw`, and how the picture came to rest
 * before it was taken. `fired` is the host's own stamp of a frame drawn with
 * the changed value; anything else is `not-fired`, which the gate fails.
 */
interface AfterFirstDrawResult {
  name: string;
  status: 'fired' | 'not-fired';
  firedAtMs?: number;
  appliedAtMs?: number;
  landing: string;
}

interface Frame {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Where each element that carries an id was drawn, for the gate's frame
 * parity (conformance/frames.schema.json; RESULTS_SCHEMA.md `frames`).
 * getBoundingClientRect, in CSS px, 2 decimals, relative to the page's
 * origin (the viewport at scroll 0), not to #root: CSS margin collapsing lets
 * the first child's top margin escape #root, #app-root and body alike
 * (measured: alignTopView's #root and #app-root both start at y = 120 while
 * the anchor is at 120 and the target where iOS draws it), so any element's
 * origin would shift every frame. The page is the fixture's screen, as the
 * root view is on iOS and Android. Only the fixture's own tree is read. An element
 * with no box (display: none, not rendered) is left out, as the other
 * platforms' accessibility trees leave it out; an id on more than one element
 * goes in `duplicates`. Returns null when the fixture has no single #root, so
 * the gate counts "no frames file" instead of reading a guess.
 */
async function captureFrames(page: Page, fixtureId: string): Promise<object | null> {
  const read = await page.evaluate(() => {
    const host = document.getElementById('app-root');
    if (!host) return null;
    const found = new Map<string, Element[]>();
    for (const el of Array.from(host.querySelectorAll('[id]'))) {
      if (el.getClientRects().length === 0) continue;
      const list = found.get(el.id) ?? [];
      list.push(el);
      found.set(el.id, list);
    }
    const roots = found.get('root') ?? [];
    if (roots.length !== 1) return null;
    const box = (el: Element) => {
      const r = el.getBoundingClientRect();
      return { x: r.left, y: r.top, width: r.width, height: r.height };
    };
    // The page at scroll 0: the viewport's size, origin (0, 0).
    const rootBox = {
      x: -window.scrollX,
      y: -window.scrollY,
      width: document.documentElement.clientWidth,
      height: document.documentElement.clientHeight,
    };
    const frames: Record<string, { x: number; y: number; width: number; height: number }> = {};
    const duplicates: string[] = [];
    for (const [id, els] of found) {
      if (els.length > 1) {
        duplicates.push(id);
        continue;
      }
      const b = box(els[0]);
      frames[id] = { x: b.x - rootBox.x, y: b.y - rootBox.y, width: b.width, height: b.height };
    }
    return { root: rootBox, frames, duplicates, density: window.devicePixelRatio };
  });
  if (!read) return null;
  const round = (f: Frame): Frame => ({
    x: Math.round(f.x * 100) / 100,
    y: Math.round(f.y * 100) / 100,
    width: Math.round(f.width * 100) / 100,
    height: Math.round(f.height * 100) / 100,
  });
  const frames: Record<string, Frame> = {};
  for (const id of Object.keys(read.frames).sort()) frames[id] = round(read.frames[id]);
  const doc: Record<string, unknown> = {
    schemaVersion: 1,
    fixture: fixtureId,
    platform: 'web',
    source: 'get-bounding-client-rect',
    density: read.density,
    root: round(read.root),
    frames,
  };
  if (read.duplicates.length > 0) doc.duplicates = read.duplicates.sort();
  return doc;
}

const manifestPath = path.join(conformanceDir, 'manifest.json');
const manifestBytes = fs.readFileSync(manifestPath);
const manifest: Manifest = JSON.parse(manifestBytes.toString('utf8'));
const manifestHash = crypto.createHash('sha256').update(manifestBytes).digest('hex');

const fixtureMapPath = path.join(hostDir, 'src/generated/fixture-map.json');
if (!fs.existsSync(fixtureMapPath)) {
  console.error('fixture-map.json missing — run `npm run generate` first');
  process.exit(1);
}
const fixtureMap: Record<string, { component: string; screenId: string; hasComponent: boolean }> = JSON.parse(
  fs.readFileSync(fixtureMapPath, 'utf8')
);

const playwrightVersion: string = JSON.parse(
  fs.readFileSync(path.join(hostDir, 'node_modules/playwright/package.json'), 'utf8')
).version;

// ------------------------------------------------------------------ build
if (!hasFlag('--skip-build')) {
  console.log('[run] vite build...');
  const build = spawnSync('npx', ['vite', 'build'], { cwd: hostDir, stdio: 'inherit' });
  if (build.status !== 0) {
    console.error('[run] vite build failed');
    process.exit(1);
  }
}

// ------------------------------------------------------------------ serve
console.log(`[run] starting vite preview on port ${port}...`);
const server = spawn('npx', ['vite', 'preview', '--port', String(port), '--strictPort'], {
  cwd: hostDir,
  stdio: ['ignore', 'pipe', 'pipe'],
});
let serverOutput = '';
server.stdout.on('data', (d: Buffer) => (serverOutput += d.toString()));
server.stderr.on('data', (d: Buffer) => (serverOutput += d.toString()));
const stopServer = (): void => {
  if (!server.killed) server.kill('SIGTERM');
};
process.on('exit', stopServer);
process.on('SIGINT', () => {
  stopServer();
  process.exit(130);
});

const baseUrl = `http://localhost:${port}`;
async function waitForServer(timeoutMs = 30000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(baseUrl);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`vite preview did not come up on ${baseUrl}\n${serverOutput}`);
}

// ------------------------------------------------------------------ classify
// RESULTS_SCHEMA: `fail` = an assertion evaluated and rejected;
// `error` = could not execute (render crash, missing element, timeout).
function classifyThrow(message: string): 'fail' | 'error' {
  if (/not found by id within|did not appear within|has no bounding box|Timeout|timeout/i.test(message)) {
    return 'error';
  }
  if (/should be|should not be|Expected text|Expected \d+ elements/.test(message)) {
    return 'fail';
  }
  return 'error';
}

const singleLine = (s: string): string => s.replace(/\s+/g, ' ').trim().slice(0, 500);

// ------------------------------------------------------------------ fixture execution
//: The one capture size for the web lane. Baselines are hashed from frames
//: this size; a capture at any other size cannot match one.
const VIEWPORT = { width: 1024, height: 768 } as const;

/** Width/height straight out of the PNG IHDR chunk (bytes 16..24, big-endian). */
function pngSize(png: Buffer): { width: number; height: number } {
  return { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
}

/**
 * afterFirstDraw (INTERACTIVE_HOST_CONTRACT.md): wait for the host's stamp of a
 * frame drawn with the changed value, then read where every id is drawn until
 * it has stood still for STILL_MS — the shape of the iOS host's Landing.wait,
 * a bounded read rather than a fixed sleep. The series goes into the result,
 * so a red says whether the change never landed, or was still moving when the
 * budget ran out.
 */
const AFTER_FIRST_DRAW_BUDGET_MS = 10000;
const LANDING_STILL_MS = 1000;
const LANDING_STEP_MS = 250;
async function awaitAfterFirstDraw(page: Page, name: string): Promise<AfterFirstDrawResult> {
  const start = Date.now();
  let stamp: { firedAtMs: number | null; appliedAtMs: number | null } | undefined;
  while (Date.now() - start < AFTER_FIRST_DRAW_BUDGET_MS) {
    stamp = await page.evaluate(() => window.__conformanceAfterFirstDraw);
    if (stamp?.appliedAtMs != null) break;
    await page.waitForTimeout(50);
  }
  if (stamp?.appliedAtMs == null) {
    return { name, status: 'not-fired', landing: `no applied stamp within ${AFTER_FIRST_DRAW_BUDGET_MS} ms (host stamp: ${JSON.stringify(stamp ?? null)})` };
  }
  const series: string[] = [];
  let last: string | null = null;
  let since = Date.now();
  const landStart = Date.now();
  let outcome = `budget ${AFTER_FIRST_DRAW_BUDGET_MS / 1000}s`;
  for (;;) {
    const doc = (await captureFrames(page, '')) as { frames?: unknown } | null;
    const value = JSON.stringify(doc?.frames ?? null);
    const t = Date.now() - landStart;
    if (value !== last) {
      series.push(`${(t / 1000).toFixed(2)} ${value.length > 200 ? value.slice(0, 200) + '…' : value}`);
      last = value;
      since = Date.now();
    }
    if (Date.now() - since >= LANDING_STILL_MS) {
      outcome = `still ${LANDING_STILL_MS / 1000}s at ${(t / 1000).toFixed(2)}s`;
      break;
    }
    if (t >= AFTER_FIRST_DRAW_BUDGET_MS) break;
    await page.waitForTimeout(LANDING_STEP_MS);
  }
  return {
    name,
    status: 'fired',
    firedAtMs: stamp.firedAtMs ?? undefined,
    appliedAtMs: stamp.appliedAtMs,
    landing: `${series.length} reading(s) (${outcome})`,
  };
}

// ------------------------------------------------------------------ testBridge (contract §6)
/** How long a fixture's receipt may take: the host's screen-ready time. */
const RECEIPT_TIMEOUT_MS = 10000;

/**
 * Job 1 — deliver at launch. On web a launch is a tab: one
 * JSONUI_TEST_INITIAL_STATE payload in its sessionStorage, carrying every
 * testBridge fixture of the batch that has an initialState, each under the
 * screen id this host staged it as (fx_NNNN). Written once per worker tab,
 * before its first fixture; the generated useJsonUITestBridge consumes a
 * screen's entry the first time that screen mounts.
 */
async function deliverInitialState(page: Page, batch: ManifestFixture[]): Promise<string | null> {
  const screens: Record<string, Record<string, unknown>> = {};
  for (const fixture of batch) {
    const values = fixture.testBridge?.initialState;
    if (values) screens[fixtureMap[fixture.id].screenId] = values;
  }
  if (Object.keys(screens).length === 0) return null;
  const launchId = crypto.randomUUID();
  await page.goto(baseUrl, { waitUntil: 'load' });
  // writtenAt (spec §10.2): the page's clock when written. Each fixture is a
  // new document (goto), opened after it, so the generated helper takes it.
  await page.evaluate((payload) => {
    window.sessionStorage.setItem(
      'JSONUI_TEST_INITIAL_STATE',
      JSON.stringify({ ...JSON.parse(payload), writtenAt: Date.now() })
    );
  }, JSON.stringify({ version: 1, launchId, screens }));
  return launchId;
}

const asSet = (values: string[]): string => JSON.stringify([...new Set(values)].sort());

/**
 * Job 2 — check the receipt: wait for the fixture's bridge to show
 * initialState with this launch's launchId, then compare applied and rejected
 * (key + reason) with the manifest as sets. Null when it matches, else what
 * was seen.
 */
async function checkReceipt(page: Page, screenId: string, launchId: string | null, spec: TestBridgeSpec): Promise<string | null> {
  const expected = spec.receipt!;
  const start = Date.now();
  let seen: BridgeSnapshot | null = null;
  for (;;) {
    seen = await readBridge(page, screenId);
    if (seen && launchId !== null && seen.launchId === launchId && seen.initialState) break;
    if (Date.now() - start >= RECEIPT_TIMEOUT_MS) {
      return `testBridge: no receipt for launch ${launchId} on screen '${screenId}' within ${RECEIPT_TIMEOUT_MS} ms (bridge: ${JSON.stringify(seen)})`;
    }
    await page.waitForTimeout(50);
  }
  const got = seen.initialState!;
  const gotApplied = asSet(got.applied ?? []);
  const gotRejected = asSet((got.rejected ?? []).map((r) => `${r.key}: ${r.reason}`));
  const wantApplied = asSet(expected.applied);
  const wantRejected = asSet(expected.rejected.map((r) => `${r.key}: ${r.reason}`));
  if (gotApplied === wantApplied && gotRejected === wantRejected) return null;
  return `testBridge: receipt differs on screen '${screenId}' — applied ${gotApplied} (expected ${wantApplied}), rejected ${gotRejected} (expected ${wantRejected})`;
}

async function runFixture(page: Page, fixture: ManifestFixture, launchId: string | null): Promise<ResultEntry> {
  const testPath = path.join(conformanceDir, fixture.test);
  const test: ScreenTest = JSON.parse(fs.readFileSync(testPath, 'utf8'));

  const pageErrors: string[] = [];
  const onPageError = (err: Error): void => {
    pageErrors.push(err.message);
  };
  page.on('pageerror', onPageError);

  const actions = new ActionExecutor(page, 10000);
  // Job 3 — `state` reads this fixture's screen: the bridge rjui's generated
  // helper publishes under the staged screen id.
  const screenId = fixtureMap[fixture.id].screenId;
  const assertions = new AssertionExecutor(page, 10000, {
    stateProvider: new BridgeStateProvider(page, () => screenId),
  });

  let screenshot: string | undefined;
  let frames: string | undefined;
  let afterFirstDraw: AfterFirstDrawResult | undefined;
  try {
    await page.goto(`${baseUrl}/fixture/${fixture.id}`, { waitUntil: 'load' });
    // Pages are reused across fixtures per worker, and the mouse stays where
    // the previous fixture's actions left it — a native control under that
    // stale cursor renders :hover. Which fixture ran before on this page is
    // scheduling-dependent, so Button/Check/Slider screenshots differed run
    // to run while being perfectly stable within a run (measured: 5 controls
    // + 27 fixtures flapping, all interactive hosts). Park the cursor in the
    // root's empty bottom edge before anything is captured.
    const viewport = page.viewportSize();
    await page.mouse.move(0, (viewport?.height ?? 600) - 1);

    if (!platformIncludes(test.platform, 'web')) {
      return { id: fixture.id, status: 'skipped', detail: `test platform ${JSON.stringify(test.platform)} excludes web` };
    }

    const bridgeSpec = fixture.testBridge;
    if (bridgeSpec?.receipt) {
      const differs = await checkReceipt(page, screenId, launchId, bridgeSpec);
      if (differs !== null) {
        return { id: fixture.id, status: 'fail', detail: differs };
      }
    }
    if (bridgeSpec?.remount) {
      // Job 4 — a new instance of the same screen in the same launch, its
      // store rebuilt (src/main.tsx keys the fixture on a generation).
      const remounted = await page.evaluate(() => {
        if (!window.__conformanceRemount) return false;
        window.__conformanceRemount();
        return true;
      });
      if (!remounted) throw new Error('testBridge: the host page has no __conformanceRemount');
    }

    for (const testCase of test.cases) {
      if (testCase.skip) continue;
      if (!platformIncludes(testCase.platform, 'web')) continue;
      for (const step of testCase.steps) {
        if (step.action === 'screenshot') {
          const declared = fixture.state?.afterFirstDraw;
          if (declared && !afterFirstDraw) {
            afterFirstDraw = await awaitAfterFirstDraw(page, declared.name);
            console.log(`[run] afterFirstDraw ${fixture.id}: ${afterFirstDraw.status} — ${afterFirstDraw.landing}`);
          }
          const name = step.name ?? fixture.id.replace(/\//g, '_');
          const file = path.join(artifactsDir, `${name}.png`);
          // waitFor proves the element is in the DOM, not that it has been
          // painted or settled. Screenshots racing paint, font loading, CSS
          // transitions or the text caret made the effect check's inert set
          // flap run to run with no code change (docs/bugs:
          // web-conformance-effect-check-is-nondeterministic; a plain
          // double-rAF was measured insufficient). Settle, then capture
          // until two consecutive frames are byte-identical.
          await page.evaluate(() => (document as any).fonts?.ready);
          // Re-assert the viewport before every capture. Twice in four CI runs
          // (30870693593 common/maxHeight__fill_clamp, 30876855224
          // common/View__fill-h) a single fixture came back at 1280x800
          // instead of the context's 1024x768 — different fixture each time,
          // so nothing about the fixture causes it, and a frame captured at
          // another size is a guaranteed baseline miss. setViewportSize is a
          // no-op when the size already matches, so this costs nothing.
          await page.setViewportSize(VIEWPORT);
          const shotOpts = { animations: 'disabled', caret: 'hide' } as const;
          let image = await page.screenshot(shotOpts);
          for (let attempt = 0; attempt < 5; attempt++) {
            await page.waitForTimeout(60);
            const next = await page.screenshot(shotOpts);
            const stable = next.equals(image);
            image = next;
            if (stable) break;
            if (attempt === 4) {
              console.warn(`[run] screenshot never stabilized: ${fixture.id}`);
            }
          }
          // Belt to the viewport braces: read the size back out of the PNG
          // header and re-capture once if it is wrong. Whatever lets a frame
          // out at the wrong size, a wrong-sized frame must never reach the
          // baseline comparison silently.
          for (let attempt = 0; attempt < 2; attempt += 1) {
            const size = pngSize(image);
            if (size.width === VIEWPORT.width && size.height === VIEWPORT.height) break;
            console.warn(
              `[run] capture at ${size.width}x${size.height}, expected ` +
              `${VIEWPORT.width}x${VIEWPORT.height}: ${fixture.id}` +
              (attempt === 1 ? ' — kept, will fail the visual gate' : ' — recapturing')
            );
            if (attempt === 1) break;
            await page.setViewportSize(VIEWPORT);
            await page.waitForTimeout(100);
            image = await page.screenshot(shotOpts);
          }
          fs.writeFileSync(file, image);
          screenshot = `artifacts/web/${name}.png`;
          // Frames are read at the moment the screenshot was taken. A failure
          // to read them leaves the fixture's verdict alone; the gate counts
          // the missing file.
          try {
            const doc = await captureFrames(page, fixture.id);
            if (doc) {
              fs.writeFileSync(path.join(artifactsDir, `${name}.frames.json`), JSON.stringify(doc, null, 2) + '\n');
              frames = `artifacts/web/${name}.frames.json`;
            }
          } catch (err) {
            console.warn(`[run] frames not captured: ${fixture.id}: ${err instanceof Error ? err.message : err}`);
          }
        } else if (step.action !== undefined) {
          await actions.execute(step);
        } else if (step.assert !== undefined) {
          await assertions.execute(step);
        } else {
          throw new Error(`unknown step: ${JSON.stringify(step)}`);
        }
      }
    }
    // A declaring fixture with no screenshot step (an interactive one that
    // asserts the change instead of photographing it, TestBridge/
    // initialState__bridge_follows) still owes its stamp: the gate
    // (after_first_draw.py) reads the result, not the steps.
    const declaredChange = fixture.state?.afterFirstDraw;
    if (declaredChange && !afterFirstDraw) {
      afterFirstDraw = await awaitAfterFirstDraw(page, declaredChange.name);
      console.log(`[run] afterFirstDraw ${fixture.id}: ${afterFirstDraw.status} — ${afterFirstDraw.landing}`);
    }
    return { id: fixture.id, status: 'pass', detail: '', screenshot, frames, afterFirstDraw };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const status = classifyThrow(message);
    const pageErrorSuffix = pageErrors.length > 0 ? ` | pageerror: ${singleLine(pageErrors[0])}` : '';
    return { id: fixture.id, status, detail: singleLine(message) + pageErrorSuffix, screenshot, frames, afterFirstDraw };
  } finally {
    page.off('pageerror', onPageError);
  }
}

function preflightStatus(fixture: ManifestFixture): ResultEntry | null {
  if (!fixture.platforms.includes('web')) {
    return { id: fixture.id, status: 'skipped', detail: 'not applicable to web' };
  }
  const mode = fixture.mode;
  if (mode !== null && mode !== undefined) {
    const modes = Array.isArray(mode) ? mode : [mode];
    if (!modes.includes('react')) {
      return { id: fixture.id, status: 'skipped', detail: `mode: ${modes.join(',')} (host renders react mode)` };
    }
  }
  const mapped = fixtureMap[fixture.id];
  if (!mapped) {
    return { id: fixture.id, status: 'error', detail: 'fixture missing from generated registry (rerun npm run generate)' };
  }
  if (!mapped.hasComponent) {
    return { id: fixture.id, status: 'error', detail: 'rjui codegen produced no component for this layout' };
  }
  return null;
}

// ------------------------------------------------------------------ main
async function main(): Promise<void> {
  await waitForServer();
  console.log('[run] server up, launching chromium...');

  fs.mkdirSync(artifactsDir, { recursive: true });
  fs.mkdirSync(path.dirname(resultsFile), { recursive: true });

  const browser = await chromium.launch();

  const fixtures = only ? manifest.fixtures.filter((f) => f.id.startsWith(only)) : manifest.fixtures;
  const results = new Map<string, ResultEntry>();
  const queue: ManifestFixture[] = [];

  for (const fixture of fixtures) {
    const pre = preflightStatus(fixture);
    if (pre) {
      results.set(fixture.id, pre);
    } else {
      queue.push(fixture);
    }
  }

  console.log(`[run] ${queue.length} fixtures to execute (${fixtures.length - queue.length} pre-resolved)`);
  let done = 0;
  let cursor = 0;

  async function worker(): Promise<void> {
    const context = await browser.newContext({ viewport: VIEWPORT });
    // `pending.invalid` never completes and never fails
    // (INTERACTIVE_HOST_CONTRACT.md §5): a route that neither fulfills nor
    // continues stalls the request forever, so the LOADING face becomes the
    // resting state instead of racing the shutter. Matched before anything
    // else — without this the browser NXDOMAINs it like any `.invalid`
    // name and the error face is photographed instead.
    await context.route('**pending.invalid**', () => { /* hold forever */ });
    const page = await context.newPage();
    // One launch per worker tab: every testBridge fixture of the batch.
    const launchId = await deliverInitialState(page, queue);
    for (;;) {
      const index = cursor++;
      if (index >= queue.length) break;
      const fixture = queue[index];
      const result = await runFixture(page, fixture, launchId);
      results.set(fixture.id, result);
      done += 1;
      if (done % 50 === 0) console.log(`[run] ${done}/${queue.length}`);
    }
    await context.close();
  }

  await Promise.all(Array.from({ length: Math.min(workers, queue.length) }, () => worker()));
  await browser.close();
  stopServer();

  // One entry per manifest fixture, in manifest order.
  const ordered: ResultEntry[] = fixtures.map((f) => results.get(f.id)!).filter(Boolean);
  const payload = {
    platform: 'web',
    manifestHash,
    runner: { name: 'playwright', version: playwrightVersion },
    results: ordered.map((r) => {
      const entry: Record<string, unknown> = { id: r.id, status: r.status, detail: r.detail };
      if (r.screenshot) entry.screenshot = r.screenshot;
      if (r.frames) entry.frames = r.frames;
      if (r.afterFirstDraw) entry.afterFirstDraw = r.afterFirstDraw;
      return entry;
    }),
  };
  fs.writeFileSync(resultsFile, JSON.stringify(payload, null, 2) + '\n');

  const counts: Record<string, number> = {};
  for (const r of ordered) counts[r.status] = (counts[r.status] ?? 0) + 1;
  console.log(`[run] wrote ${resultsFile}`);
  console.log(`[run] summary: ${JSON.stringify(counts)}`);

  const failures = ordered.filter((r) => r.status === 'fail' || r.status === 'error');
  if (failures.length > 0) {
    console.log('[run] non-pass (fail/error):');
    for (const f of failures.slice(0, 50)) console.log(`  ${f.status.padEnd(5)} ${f.id} — ${f.detail}`);
    if (failures.length > 50) console.log(`  ... and ${failures.length - 50} more`);
  }
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error(err);
    stopServer();
    process.exit(1);
  });
