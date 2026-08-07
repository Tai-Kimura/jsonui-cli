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
}
interface Manifest {
  fixtures: ManifestFixture[];
}

interface ResultEntry {
  id: string;
  status: 'pass' | 'fail' | 'error' | 'skipped';
  detail: string;
  screenshot?: string;
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
const fixtureMap: Record<string, { component: string; hasComponent: boolean }> = JSON.parse(
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

async function runFixture(page: Page, fixture: ManifestFixture): Promise<ResultEntry> {
  const testPath = path.join(conformanceDir, fixture.test);
  const test: ScreenTest = JSON.parse(fs.readFileSync(testPath, 'utf8'));

  const pageErrors: string[] = [];
  const onPageError = (err: Error): void => {
    pageErrors.push(err.message);
  };
  page.on('pageerror', onPageError);

  const actions = new ActionExecutor(page, 10000);
  const assertions = new AssertionExecutor(page, 10000);

  let screenshot: string | undefined;
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

    for (const testCase of test.cases) {
      if (testCase.skip) continue;
      if (!platformIncludes(testCase.platform, 'web')) continue;
      for (const step of testCase.steps) {
        if (step.action === 'screenshot') {
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
        } else if (step.action !== undefined) {
          await actions.execute(step);
        } else if (step.assert !== undefined) {
          await assertions.execute(step);
        } else {
          throw new Error(`unknown step: ${JSON.stringify(step)}`);
        }
      }
    }
    return { id: fixture.id, status: 'pass', detail: '', screenshot };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const status = classifyThrow(message);
    const pageErrorSuffix = pageErrors.length > 0 ? ` | pageerror: ${singleLine(pageErrors[0])}` : '';
    return { id: fixture.id, status, detail: singleLine(message) + pageErrorSuffix, screenshot };
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
    for (;;) {
      const index = cursor++;
      if (index >= queue.length) break;
      const fixture = queue[index];
      const result = await runFixture(page, fixture);
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
