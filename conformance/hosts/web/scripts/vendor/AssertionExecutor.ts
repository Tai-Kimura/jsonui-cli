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
import type { Page, Locator } from 'playwright';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';
import { type TestStep, deepEquals } from './types.ts';
import type { StateProvider } from './StateProvider.ts';

/** Polling interval for auto-wait assertions */
const POLL_INTERVAL_MS = 100;
/** RGBA channel difference (0-255) below which two pixels are considered a match */
const CHANNEL_TOLERANCE = 16;

export class AssertionExecutor {
  private page: Page;
  private defaultTimeout: number;
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
    } = {}
  ) {
    this.page = page;
    this.defaultTimeout = defaultTimeout;
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
      default:
        throw new Error(`Unknown assertion: ${assertion}`);
    }
  }

  /**
   * Poll `check` every POLL_INTERVAL_MS until it returns null (pass) or the timeout
   * elapses. `check` returns an error message string while the condition is unmet.
   * The last error message is thrown on timeout.
   */
  private async pollUntil(
    timeout: number,
    check: () => Promise<string | null>
  ): Promise<void> {
    const startTime = Date.now();
    let lastError = 'assertion timed out';

    // Always evaluate at least once even if timeout is 0
    for (;;) {
      const error = await check();
      if (error === null) {
        return;
      }
      lastError = error;
      if (Date.now() - startTime >= timeout) {
        break;
      }
      await this.page.waitForTimeout(POLL_INTERVAL_MS);
    }

    throw new Error(lastError);
  }

  private async assertVisible(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'visible');
    await this.pollUntil(timeout, async () => {
      const element = this.getLocator(id).first();
      if (await element.count() === 0) {
        return `Element '${id}' should be visible but it does not exist`;
      }
      return await element.isVisible()
        ? null
        : `Element '${id}' should be visible but it is not`;
    });
  }

  private async assertNotVisible(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'notVisible');
    await this.pollUntil(timeout, async () => {
      const element = this.getLocator(id);
      if (await element.count() === 0) {
        return null;
      }
      return await element.first().isVisible()
        ? `Element '${id}' should not be visible but it is`
        : null;
    });
  }

  private async assertEnabled(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'enabled');
    await this.pollUntil(timeout, async () => {
      const element = this.getLocator(id).first();
      if (await element.count() === 0) {
        return `Element '${id}' not found by id`;
      }
      const disabled = await this.isElementDisabled(element);
      return disabled ? `Element '${id}' should be enabled but it is disabled` : null;
    });
  }

  private async assertDisabled(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'disabled');
    await this.pollUntil(timeout, async () => {
      const element = this.getLocator(id).first();
      if (await element.count() === 0) {
        return `Element '${id}' not found by id`;
      }
      const disabled = await this.isElementDisabled(element);
      return disabled ? null : `Element '${id}' should be disabled but it is enabled`;
    });
  }

  private async assertText(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'text');
    if (step.equals === undefined && step.contains === undefined) {
      throw new Error("text requires 'equals' or 'contains'");
    }
    await this.pollUntil(timeout, async () => {
      const element = this.getLocator(id).first();
      if (await element.count() === 0) {
        return `Element '${id}' not found by id`;
      }
      const actualText = await this.readElementText(element);
      if (step.equals !== undefined) {
        const expected = String(step.equals);
        return actualText === expected
          ? null
          : `Expected text '${expected}' but got '${actualText}' for element '${id}'`;
      }
      return actualText.includes(step.contains as string)
        ? null
        : `Expected text containing '${step.contains}' but got '${actualText}' for element '${id}'`;
    });
  }

  private async assertCount(step: TestStep, timeout: number): Promise<void> {
    const id = this.requireId(step, 'count');
    if (step.equals === undefined || typeof step.equals !== 'number') {
      throw new Error("count requires 'equals' with integer value");
    }
    const expected = step.equals as number;
    await this.pollUntil(timeout, async () => {
      const actualCount = await this.getLocator(id).count();
      return actualCount === expected
        ? null
        : `Expected ${expected} elements with id '${id}', but found ${actualCount}`;
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
      const actual = await provider.getValue(statePath);
      return deepEquals(actual, step.equals)
        ? null
        : `State '${statePath}' should be ${JSON.stringify(step.equals)} but got ${JSON.stringify(actual)}`;
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
      const element = this.getLocator(step.cropId).first();
      if (await element.count() === 0) {
        throw new Error(`screenshot cropId '${step.cropId}' not found`);
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
   * Get locator for element by id attribute
   */
  private getLocator(id: string): Locator {
    return this.page.locator(`#${id}`);
  }

  private async isElementDisabled(element: Locator): Promise<boolean> {
    return element.evaluate((el) => {
      if (el instanceof HTMLButtonElement || el instanceof HTMLInputElement) {
        return el.disabled;
      }
      return el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('disabled');
    });
  }

  private async readElementText(element: Locator): Promise<string> {
    return element.evaluate((el) => {
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
    });
  }
}
