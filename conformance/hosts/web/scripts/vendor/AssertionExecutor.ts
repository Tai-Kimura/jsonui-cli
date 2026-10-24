/**
 * JsonUI Test Runner - Web Driver
 * Assertion executor using Playwright
 *
 * Uses id attribute for element matching (ReactJsonUI exposes id as HTML id attribute)
 *
 * All element assertions auto-wait: they poll the condition every 100ms until it
 * holds or the timeout (step.timeout ?? defaultTimeout) elapses.
 */

import * as fs from 'fs';
import * as path from 'path';
import { isHidden, viewportState, probe, DETACHED } from './visibility.ts';
import { byId, label, notFound, containerPresent } from './resolve.ts';
import { ReasonHistory } from './reasonHistory.ts';
import type { Page, Locator } from 'playwright';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';
import { type TestStep, deepEquals } from './types.ts';
import { type StateProvider, lookupState, TRUNCATED_MESSAGE } from './StateProvider.ts';

/** Polling interval for auto-wait assertions */
const POLL_INTERVAL_MS = 100;
/** RGBA channel difference (0-255) below which two pixels are considered a match */
const CHANNEL_TOLERANCE = 16;

export class AssertionExecutor {
  private page: Page;
  private defaultTimeout: number;
  /**
   * Cross-screen waits are legitimately slower than in-screen ones: real
   * suites already hand-write 15-20s after a cold start. Kept distinct from
   * defaultTimeout so raising one does not silently raise the other.
   */
  private screenTransitionTimeout: number;
  private stateProvider?: StateProvider;
  private baselineDir: string;
  private updateBaselines: boolean;
  /** Warnings produced by the current step (e.g. baseline created); drained by the runner */
  public warnings: string[] = [];

  constructor(
    page: Page,
    defaultTimeout: number = 5000,
    options: {
      stateProvider?: StateProvider;
      baselineDir?: string;
      updateBaselines?: boolean;
      screenTransitionTimeout?: number;
    } = {}
  ) {
    this.page = page;
    this.defaultTimeout = defaultTimeout;
    this.screenTransitionTimeout = options.screenTransitionTimeout ?? 10000;
    this.stateProvider = options.stateProvider;
    this.baselineDir = options.baselineDir ?? './baselines';
    this.updateBaselines = options.updateBaselines ?? false;
  }

  /**
   * Execute an assertion step
   */
  async execute(step: TestStep): Promise<void> {
    const assertion = step.assert;
    if (!assertion) {
      throw new Error('Step has no assert');
    }

    const timeout = step.timeout ?? this.defaultTimeout;

    switch (assertion) {
      case 'visible':
        await this.assertVisible(step, timeout);
        break;
      case 'notVisible':
        await this.assertNotVisible(step, timeout);
        break;
      case 'hidden':
        await this.assertHidden(step, timeout);
        break;
      case 'enabled':
        await this.assertEnabled(step, timeout);
        break;
      case 'disabled':
        await this.assertDisabled(step, timeout);
        break;
      case 'text':
        await this.assertText(step, timeout);
        break;
      case 'count':
        await this.assertCount(step, timeout);
        break;
      case 'state':
        await this.assertState(step, timeout);
        break;
      case 'screenshot':
        await this.assertScreenshot(step);
        break;
      case 'openedUrl':
        await this.assertOpenedUrl(step, timeout);
        break;
      case 'screen':
        await this.assertScreen(step, step.timeout ?? this.screenTransitionTimeout);
        break;
      default:
        throw new Error(`Unknown assertion: ${assertion}`);
    }
  }

  /**
   * Poll `check` every POLL_INTERVAL_MS until it returns null (pass) or the timeout
   * elapses. `check` returns an error message string while the condition is unmet.
   * The last error message is thrown on timeout, followed by every reason seen
   * while waiting when it changed (ReasonHistory) — one reason, no block.
   */
  private async pollUntil(
    timeout: number,
    check: () => Promise<string | null>
  ): Promise<void> {
    const startTime = Date.now();
    const history = new ReasonHistory();
    let lastError = 'assertion timed out';
    let elapsed = 0;

    // Always evaluate at least once even if timeout is 0
    for (;;) {
      const lookedAt = Date.now() - startTime;
      const error = await check();
      if (error === null) {
        return;
      }
      lastError = error;
      history.observe(error, lookedAt);
      elapsed = Date.now() - startTime;
      if (elapsed >= timeout) {
        break;
      }
      await this.page.waitForTimeout(POLL_INTERVAL_MS);
    }

    throw new Error(history.message(lastError, elapsed));
  }

  /**
   * `assert: "screen"` — the named screen IS DISPLAYED.
   *
   * Not "displayed exclusively": embedded screens, split panes and tab hosts
   * legitimately show several markers at once, so this only ever looks at the
   * target's own marker.
   *
   * Measured with React 19 SSR + a suspending transition: a client-side swap
   * never exposes two screens' markers at once, and a pending transition
   * never mounts the destination's marker early — while it is pending, NO
   * marker is present. So the predicate needs no exclusivity test and no
   * transition handling, and a zero-marker reading is only meaningful once
   * the timeout has expired.
   *
   * Known limitation (measured, deliberately not part of the predicate):
   * server-rendered markup carries the marker before hydration, so on the
   * FIRST document load this can pass while clicks are still being dropped.
   * React exposes no standard "hydrated" signal, so gating on one is not
   * implementable; it does not recur on client-side navigation.
   */
  private async assertScreen(step: TestStep, timeout: number): Promise<void> {
    const screenId = step.name;
    if (!screenId) {
      throw new Error("screen requires 'name'");
    }
    await this.waitForScreenMarker(screenId, timeout);
  }

  /**
   * Wait until the named screen's marker is displayed. Public because the
   * runner's readiness gate needs the same predicate and, more importantly,
   * the same diagnosis: a second implementation would answer "not ready"
   * where this one answers "built for production" or "navigation went
   * elsewhere", and those are the sentences that end the investigation.
   *
   * Throws the last diagnosis on timeout.
   */
  async waitForScreenMarker(screenId: string, timeout: number): Promise<void> {
    const locator = this.page.locator(`[data-screen="${screenId}"]`);

    await this.pollUntil(timeout, async () => {
      if ((await locator.count()) === 0) return await this.screenDiagnosis(screenId);
      if (await locator.first().isVisible()) return null;
      return `marker-not-displayed: screen '${screenId}' is present but not visible`;
    });
  }

  /**
   * Canonical failure classes. The class names the likely CAUSE, not a
   * severity — every one of them fails the assertion just the same. A missing
   * marker anywhere points at the build (production build or stale generated
   * code), while the previous screen still being the only one present points
   * at the app or the test: the navigation did not happen.
   */
  private async screenDiagnosis(screenId: string): Promise<string> {
    const present = await this.page
      .locator('[data-screen]')
      .evaluateAll((nodes) =>
        nodes.map((n) => n.getAttribute('data-screen')).filter((v): v is string => !!v)
      )
      .catch(() => [] as string[]);

    if (present.length === 0) {
      // Name what the browser is actually showing: a redirect (auth wall,
      // error page) also has no markers, and there the build is not the
      // suspect — same misdiagnosis class as Android's foreground-app case.
      const where = this.page.url();
      return (
        `marker-absent: no screen marker anywhere (current page: ${where}). ` +
        'If this is not the screen under test, navigation went elsewhere — the build is ' +
        'not the suspect. Otherwise the app is either built for production ' +
        '(markers are development-only) or its generated code is stale — rebuild with `jui build`.'
      );
    }
    return `previous-screen-only: '${screenId}' is not displayed; displayed screens are ${JSON.stringify(present)}`;
  }

  /** In the viewport (src/visibility.ts): shown, and some of it inside the
   * window's viewport and every clipping ancestor — not merely laid out. */
  private async assertVisible(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'visible');
    const within = step.within;
    await this.pollUntil(timeout, async () => {
      // viewportState counts first, and reads an element that leaves the DOM
      // while it is being measured as absent (src/visibility.ts probe).
      // A `within` container that is not there: nothing in it is visible.
      switch (await viewportState(this.getLocator(id, within))) {
        case 'absent':
          return within
            ? `${await notFound(this.page, id, within)}: it should be visible`
            : `Element '${id}' should be visible but it does not exist`;
        case 'out': return `Element ${label(id, within)} should be visible but it is not in the viewport`;
        case 'in': return null;
      }
    });
  }

  private async assertNotVisible(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'notVisible');
    const within = step.within;
    await this.pollUntil(timeout, async () => {
      // Exactly not `visible`: absent, hidden, or nothing of it in the viewport.
      // With `within`, a container that is not there holds (nothing is drawn).
      return (await viewportState(this.getLocator(id, within))) === 'in'
        ? `Element ${label(id, within)} should not be visible but it is`
        : null;
    });
  }

  private async assertHidden(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'hidden');
    const within = step.within;
    // Not drawn, wherever it is (src/visibility.ts isHidden): no element with
    // the id (inside `within`, when given) is drawn — every match is looked
    // at, so one drawn copy among invisible ones fails. Unlike notVisible it
    // does not pass for an element below the fold or under a dialog: those
    // are drawn. A `within` container that is not there holds.
    await this.pollUntil(timeout, async () =>
      (await isHidden(this.getLocator(id, within))) ? null : `Element ${label(id, within)} should be hidden but it is shown`
    );
  }

  private async assertEnabled(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'enabled');
    const within = step.within;
    await this.pollUntil(timeout, async () => {
      const element = this.getLocator(id, within).first();
      if (await element.count() === 0) {
        return notFound(this.page, id, within);
      }
      const disabled = await this.isElementDisabled(element);
      if (disabled === DETACHED) return notFound(this.page, id, within);
      return disabled ? `Element ${label(id, within)} should be enabled but it is disabled` : null;
    });
  }

  private async assertDisabled(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'disabled');
    const within = step.within;
    await this.pollUntil(timeout, async () => {
      const element = this.getLocator(id, within).first();
      if (await element.count() === 0) {
        return notFound(this.page, id, within);
      }
      const disabled = await this.isElementDisabled(element);
      if (disabled === DETACHED) return notFound(this.page, id, within);
      return disabled ? null : `Element ${label(id, within)} should be disabled but it is enabled`;
    });
  }

  private async assertText(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'text');
    if (step.equals === undefined && step.contains === undefined) {
      throw new Error("text requires 'equals' or 'contains'");
    }
    const within = step.within;
    await this.pollUntil(timeout, async () => {
      const element = this.getLocator(id, within).first();
      if (await element.count() === 0) {
        return notFound(this.page, id, within);
      }
      const actualText = await this.readElementText(element);
      if (actualText === DETACHED) return notFound(this.page, id, within);
      if (step.equals !== undefined) {
        const expected = String(step.equals);
        return actualText === expected
          ? null
          : `Expected text '${expected}' but got '${actualText}' for element ${label(id, within)}`;
      }
      return actualText.includes(step.contains as string)
        ? null
        : `Expected text containing '${step.contains}' but got '${actualText}' for element ${label(id, within)}`;
    });
  }

  private async assertCount(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'count');
    if (step.equals === undefined || typeof step.equals !== 'number') {
      throw new Error("count requires 'equals' with integer value");
    }
    const expected = step.equals as number;
    const within = step.within;
    await this.pollUntil(timeout, async () => {
      // With `within`: the matches inside the container. A container that is
      // not there is a failure, not 0 — "this cell has no badge" must not
      // pass for a cell that is not drawn.
      if (!(await containerPresent(this.page, within))) {
        return notFound(this.page, id, within);
      }
      const actualCount = await this.getLocator(id, within).count();
      return actualCount === expected
        ? null
        : `Expected ${expected} elements with id '${id}'${within ? ` inside '${within}'` : ''}, but found ${actualCount}`;
    });
  }

  private async assertState(step: TestStep, timeout: number): Promise<void> {
    const statePath = step.path;
    if (!statePath) {
      throw new Error("state requires 'path'");
    }
    if (step.equals === undefined) {
      throw new Error("state requires 'equals'");
    }
    if (!this.stateProvider) {
      throw new Error(`Cannot assert state '${statePath}': no state provider configured`);
    }
    const provider = this.stateProvider;
    await this.pollUntil(timeout, async () => {
      const found = await lookupState(provider, statePath);
      switch (found.outcome) {
        case 'truncated':
          // Fails at once: no amount of waiting makes a truncated bridge readable.
          throw new Error(TRUNCATED_MESSAGE(statePath, found.bytes));
        case 'pending':
          return `State '${statePath}' should be ${JSON.stringify(step.equals)}, but ${found.reason}`;
        case 'unresolved':
          return `State '${statePath}' should be ${JSON.stringify(step.equals)} but the path does not resolve`;
        case 'value':
          return deepEquals(found.value, step.equals)
            ? null
            : `State '${statePath}' should be ${JSON.stringify(step.equals)} but got ${JSON.stringify(found.value)}`;
      }
    });
  }

  /**
   * Assert against the most recent window.open call recorded by the runner's
   * spy (installed on every document). Auto-waits like element assertions so
   * an open triggered by an async handler still lands within the timeout.
   * Web-only — gate with when.platform in cross-platform tests.
   */
  private async assertOpenedUrl(step: TestStep, timeout: number): Promise<void> {
    if (step.equals === undefined && step.contains === undefined) {
      throw new Error("openedUrl assertion requires 'equals' or 'contains'");
    }

    await this.pollUntil(timeout, async () => {
      const urls = await this.page.evaluate(
        () => (window as unknown as { __jsonuiOpenedUrls?: string[] }).__jsonuiOpenedUrls ?? []
      );
      const last = urls[urls.length - 1];
      if (last === undefined) {
        return 'no window.open call recorded';
      }
      if (step.equals !== undefined && last !== String(step.equals)) {
        return `last opened url '${last}' does not equal '${step.equals}'`;
      }
      if (step.contains !== undefined && !last.includes(step.contains)) {
        return `last opened url '${last}' does not contain '${step.contains}'`;
      }
      return null;
    });
  }

  private async assertScreenshot(step: TestStep): Promise<void> {
    const name = step.name;
    if (!name) {
      throw new Error("screenshot requires 'name'");
    }
    const threshold = step.threshold ?? 98.0;

    // Capture (optionally cropped to an element's bounding box)
    let capture: Buffer;
    if (step.cropId) {
      const element = this.getLocator(step.cropId, step.within).first();
      if (await element.count() === 0) {
        throw new Error(
          step.within
            ? `screenshot cropId: ${await notFound(this.page, step.cropId, step.within)}`
            : `screenshot cropId '${step.cropId}' not found`
        );
      }
      capture = await element.screenshot();
    } else {
      capture = await this.page.screenshot();
    }

    const baselinePath = path.join(this.baselineDir, 'web', `${name}.png`);

    if (this.updateBaselines || !fs.existsSync(baselinePath)) {
      fs.mkdirSync(path.dirname(baselinePath), { recursive: true });
      fs.writeFileSync(baselinePath, capture);
      this.warnings.push(
        this.updateBaselines
          ? `baseline updated: ${baselinePath}`
          : `baseline created: ${baselinePath}`
      );
      return;
    }

    const baseline = PNG.sync.read(fs.readFileSync(baselinePath));
    const current = PNG.sync.read(capture);

    if (baseline.width !== current.width || baseline.height !== current.height) {
      throw new Error(
        `Screenshot '${name}' size mismatch: baseline ${baseline.width}x${baseline.height}, ` +
        `current ${current.width}x${current.height}`
      );
    }

    const total = baseline.width * baseline.height;
    const diffPixels = pixelmatch(
      baseline.data,
      current.data,
      null,
      baseline.width,
      baseline.height,
      { threshold: CHANNEL_TOLERANCE / 255 }
    );
    const similarity = total === 0 ? 100 : (100 * (total - diffPixels)) / total;

    if (similarity < threshold) {
      throw new Error(
        `Screenshot '${name}' similarity ${similarity.toFixed(2)}% is below threshold ${threshold}%`
      );
    }
  }

  // Helper functions

  private requireId(step: TestStep, assertion: string): string {
    const id = step.id;
    if (!id) {
      throw new Error(`${assertion} requires 'id'`);
    }
    return id;
  }

  /**
   * Every element with the id attribute — among `within`'s descendants when
   * given (src/resolve.ts byId)
   */
  private getLocator(id: string, within?: string): Locator {
    return byId(this.page, id, within);
  }

  /** Bounded (src/visibility.ts probe): DETACHED when the element left the DOM. */
  private async isElementDisabled(element: Locator): Promise<boolean | typeof DETACHED> {
    return probe((timeout) => element.evaluate((el) => {
      if (el instanceof HTMLButtonElement || el instanceof HTMLInputElement) {
        return el.disabled;
      }
      return el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('disabled');
    }, undefined, { timeout }));
  }

  /** Bounded (src/visibility.ts probe): DETACHED when the element left the DOM. */
  private async readElementText(element: Locator): Promise<string | typeof DETACHED> {
    return probe((timeout) => element.evaluate((el) => {
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        return el.value;
      }
      // Check for nested input/textarea. Checkbox/radio inputs are excluded:
      // their `value` is a form-submission token (default "on"), not
      // user-visible text — for composite controls (label + input) the
      // visible text is the label's textContent.
      const input = el.querySelector(
        'input:not([type="checkbox"]):not([type="radio"]), textarea'
      );
      if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement) {
        return input.value;
      }
      return el.textContent ?? '';
    }, undefined, { timeout }));
  }
}
