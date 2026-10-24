// Chapter T-a's footage: the real web test runner (jsonui-test-runner-web) runs demo-shop's screen tests against the
// stage's web app and its mock server, in a browser that records a video; each step's start and end are written
// beside it, so the frames can show the test file with the step being run lit (t_chapter.py).
//
//   node t_runner.mjs <stage web dir> <out dir> <app url> <mock url> <mock token> <lang> <route>=<test file>...
//
// The runner and Playwright are the stage web's own (its node_modules); nothing here asserts on its own: a step that
// fails fails the run, and the result is written as the runner returns it.
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const [stageWeb, out, appUrl, mockUrl, token, lang, ...files] = process.argv.slice(2);
const require = createRequire(path.join(stageWeb, 'package.json'));
const {chromium} = require('playwright');
const {JsonUITestRunner, TestLoader} = require('jsonui-test-runner-web');   // npm's, as the shipped web apps take it

// a phone's width: t_chapter.py sets the video in the middle of the split's right half
const VIEW = {width: 430, height: 932};
// a step held this long after it ends, so each step is seen (the runner itself waits only as long as it must)
const HOLD_MS = Number(process.env.T_HOLD_MS ?? 700);

fs.mkdirSync(out, {recursive: true});
const browser = await chromium.launch();
const runs = [];
for (const arg of files) {
  const [route, file] = arg.split('=');
  const name = path.basename(file, '.test.json');
  const context = await browser.newContext({viewport: VIEW, recordVideo: {dir: path.join(out, name), size: VIEW}});
  const page = await context.newPage();
  const t0 = Date.now();
  await page.goto(`${appUrl}${route}?lang=${lang}`);
  const steps = [];
  const runner = new JsonUITestRunner(page, {defaultTimeout: 10000, mockServerUrl: mockUrl, mockToken: token,
    screenshotOnFailure: false, verifyScreenTransitions: false});
  const execute = runner.executeStep.bind(runner);
  runner.executeStep = async (step, warnings) => {
    const entry = {step, start: Date.now() - t0};
    steps.push(entry);
    try {
      await execute(step, warnings);
      entry.ok = true;
    } catch (error) {
      entry.ok = false;
      entry.error = String(error && error.message ? error.message : error).slice(0, 300);
      throw error;
    } finally {
      entry.end = Date.now() - t0;
      await page.waitForTimeout(HOLD_MS);
    }
  };
  const result = await runner.run(TestLoader.loadFromFile(file));
  await page.waitForTimeout(HOLD_MS);
  const video = page.video();
  await context.close();
  const runOut = {file, name, steps, ms: Date.now() - t0, video: video ? await video.path() : null,
    results: result.results.map((r) => ({case: r.caseName, passed: r.passed, error: r.error ?? null}))};
  runs.push(runOut);
  console.log(`${name}: ${runOut.results.map((r) => `${r.case} ${r.passed ? 'passed' : 'FAILED ' + r.error}`).join('; ')}`);
}
await browser.close();
fs.writeFileSync(path.join(out, 'runs.json'), JSON.stringify(runs, null, 1));
process.exit(runs.every((r) => r.results.every((x) => x.passed)) ? 0 : 1);
