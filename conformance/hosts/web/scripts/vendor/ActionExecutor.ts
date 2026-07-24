/**
 * JsonUI Test Runner - Web Driver
 * Action executor using Playwright
 *
 * Uses id attribute for element matching (ReactJsonUI exposes id as HTML id attribute)
 */

import * as fs from 'fs';
import * as path from 'path';
import type { Page, Locator } from 'playwright';
import { type TestStep, deriveOrientation } from './types.ts';

export class ActionExecutor {
  private page: Page;
  private defaultTimeout: number;
  /** Runtime variable store shared with the runner (written by readText) */
  private variables: Record<string, string>;

  constructor(page: Page, defaultTimeout: number = 5000, variables: Record<string, string> = {}) {
    this.page = page;
    this.defaultTimeout = defaultTimeout;
    this.variables = variables;
  }

  /**
   * Execute an action step
   */
  async execute(step: TestStep): Promise<void> {
    const action = step.action;
    if (!action) {
      throw new Error('Step has no action');
    }

    const timeout = step.timeout ?? this.defaultTimeout;

    switch (action) {
      case 'tap':
        await this.executeTap(step, timeout);
        break;
      case 'doubleTap':
        await this.executeDoubleTap(step, timeout);
        break;
      case 'longPress':
        await this.executeLongPress(step, timeout);
        break;
      case 'input':
        await this.executeInput(step, timeout);
        break;
      case 'typeText':
        await this.executeTypeText(step);
        break;
      case 'clear':
        await this.executeClear(step, timeout);
        break;
      case 'scroll':
        await this.executeScroll(step, timeout);
        break;
      case 'scrollUntilVisible':
        await this.executeScrollUntilVisible(step);
        break;
      case 'swipe':
        await this.executeSwipe(step, timeout);
        break;
      case 'waitFor':
        await this.executeWaitFor(step, timeout);
        break;
      case 'waitForAny':
        await this.executeWaitForAny(step, timeout);
        break;
      case 'wait':
        await this.executeWait(step);
        break;
      case 'back':
        await this.executeBack();
        break;
      case 'hideKeyboard':
        await this.executeHideKeyboard();
        break;
      case 'screenshot':
        await this.executeScreenshot(step);
        break;
      case 'alertTap':
        await this.executeAlertTap(step, timeout);
        break;
      case 'selectOption':
        await this.executeSelectOption(step, timeout);
        break;
      case 'tapItem':
        await this.executeTapItem(step, timeout);
        break;
      case 'selectTab':
        await this.executeSelectTab(step, timeout);
        break;
      case 'readText':
        await this.executeReadText(step, timeout);
        break;
      case 'setLocation':
        await this.executeSetLocation(step);
        break;
      case 'addMedia':
        await this.executeAddMedia(step);
        break;
      case 'emitHook':
        await this.executeEmitHook(step);
        break;
      case 'setViewport':
        await this.executeSetViewport(step);
        break;
      case 'setOrientation':
        await this.executeSetOrientation(step);
        break;
      case 'repeat':
      case 'retry':
        // Control steps are executed by the runner (they need condition evaluation
        // and nested step handling); reaching here means the runner was bypassed
        throw new Error(`'${action}' is a control step and is handled by the test runner`);
      default:
        throw new Error(`Unknown action: ${action}`);
    }
  }

  private async executeTap(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("tap requires 'id'");
    }
    const element = await this.waitForElement(id, timeout);

    // If text is specified, tap on the specific text portion within the element
    if (step.text) {
      await this.tapTextPortion(element, step.text);
    } else {
      await element.click();
    }
  }

  private async executeDoubleTap(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("doubleTap requires 'id'");
    }
    const element = await this.waitForElement(id, timeout);
    await element.dblclick();
  }

  private async executeLongPress(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("longPress requires 'id'");
    }
    const duration = step.duration ?? 500;
    const element = await this.waitForElement(id, timeout);

    // Playwright doesn't have built-in long press, simulate with mouse down/up
    await element.hover();
    await this.page.mouse.down();
    await this.page.waitForTimeout(duration);
    await this.page.mouse.up();
  }

  private async executeInput(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("input requires 'id'");
    }
    const value = step.value;
    if (value === undefined) {
      throw new Error("input requires 'value'");
    }

    const element = await this.waitForElement(id, timeout);

    // Try to find an input element within the container
    const input = element.locator('input, textarea').first();
    const hasInput = await input.count() > 0;

    if (hasInput) {
      await input.fill(value);
    } else {
      // Try filling directly if the element itself is an input
      await element.fill(value);
    }
  }

  /**
   * Type into whatever currently holds keyboard focus — no element id.
   * For fields that are focused but not directly targetable (e.g. an invisible
   * code-entry input behind visible slots). Focus is established app-side
   * (auto-focus or a prior tap); keyboard events route to document.activeElement.
   */
  private async executeTypeText(step: TestStep): Promise<void> {
    const value = step.value;
    if (value === undefined) {
      throw new Error("typeText requires 'value'");
    }
    await this.page.keyboard.type(value);
  }

  private async executeClear(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("clear requires 'id'");
    }

    const element = await this.waitForElement(id, timeout);

    // Try to find an input element within the container
    const input = element.locator('input, textarea').first();
    const hasInput = await input.count() > 0;

    if (hasInput) {
      await input.clear();
    } else {
      // Try clearing directly if the element itself is an input
      await element.clear();
    }
  }

  private async executeScroll(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("scroll requires 'id'");
    }
    const direction = step.direction;
    if (!direction) {
      throw new Error("scroll requires 'direction'");
    }

    const element = await this.waitForElement(id, timeout);
    const box = await element.boundingBox();

    if (!box) {
      throw new Error(`Element '${id}' has no bounding box`);
    }

    const scrollAmount = step.amount ?? 300;

    // Scroll within the element
    await element.evaluate((el, { direction, amount }) => {
      switch (direction) {
        case 'up':
          el.scrollTop -= amount;
          break;
        case 'down':
          el.scrollTop += amount;
          break;
        case 'left':
          el.scrollLeft -= amount;
          break;
        case 'right':
          el.scrollLeft += amount;
          break;
      }
    }, { direction, amount: scrollAmount });
  }

  private async executeSwipe(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("swipe requires 'id'");
    }
    const direction = step.direction;
    if (!direction) {
      throw new Error("swipe requires 'direction'");
    }

    const element = await this.waitForElement(id, timeout);
    const box = await element.boundingBox();

    if (!box) {
      throw new Error(`Element '${id}' has no bounding box`);
    }

    const centerX = box.x + box.width / 2;
    const centerY = box.y + box.height / 2;
    const swipeDistance = Math.min(box.width, box.height) / 2;

    let startX = centerX;
    let startY = centerY;
    let endX = centerX;
    let endY = centerY;

    switch (direction) {
      case 'up':
        startY = centerY + swipeDistance;
        endY = centerY - swipeDistance;
        break;
      case 'down':
        startY = centerY - swipeDistance;
        endY = centerY + swipeDistance;
        break;
      case 'left':
        startX = centerX + swipeDistance;
        endX = centerX - swipeDistance;
        break;
      case 'right':
        startX = centerX - swipeDistance;
        endX = centerX + swipeDistance;
        break;
    }

    // Perform swipe gesture
    await this.page.mouse.move(startX, startY);
    await this.page.mouse.down();
    await this.page.mouse.move(endX, endY, { steps: 10 });
    await this.page.mouse.up();
  }

  private async executeWaitFor(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("waitFor requires 'id'");
    }
    await this.waitForElement(id, timeout);
  }

  private async executeWaitForAny(step: TestStep, timeout: number): Promise<void> {
    const ids = step.ids;
    if (!ids || ids.length === 0) {
      throw new Error("waitForAny requires non-empty 'ids'");
    }

    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      for (const id of ids) {
        const element = this.getLocator(id);
        const count = await element.count();
        if (count > 0 && await element.first().isVisible()) {
          return;
        }
      }
      await this.page.waitForTimeout(100);
    }

    throw new Error(`None of elements [${ids.join(', ')}] appeared within ${timeout}ms`);
  }

  private async executeWait(step: TestStep): Promise<void> {
    const ms = step.ms;
    if (ms === undefined) {
      throw new Error("wait requires 'ms'");
    }
    await this.page.waitForTimeout(ms);
  }

  private async executeBack(): Promise<void> {
    await this.page.goBack();
  }

  /**
   * Dismiss the soft keyboard by blurring the focused element. Under mobile
   * emulation this closes the on-screen keyboard; on desktop it is a
   * harmless blur (cross-platform parity with the ios/android drivers).
   */
  private async executeHideKeyboard(): Promise<void> {
    await this.page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (el && typeof el.blur === 'function') {
        el.blur();
      }
    });
  }

  /**
   * Sink for `screenshot` action captures. The runner wires this so the
   * capture lands in config.screenshotDir with test/case identity in the
   * name (collected by `jsonui-test artifacts pull`); the bare CWD write
   * below is only the fallback for executors used without a runner.
   */
  screenshotHandler?: (name: string) => Promise<void>;

  private async executeScreenshot(step: TestStep): Promise<void> {
    const name = step.name ?? `screenshot_${Date.now()}`;
    if (this.screenshotHandler) {
      await this.screenshotHandler(name);
      return;
    }
    await this.page.screenshot({ path: `${name}.png` });
  }

  private async executeAlertTap(step: TestStep, timeout: number): Promise<void> {
    const buttonText = step.button;
    if (!buttonText) {
      throw new Error("alertTap requires 'button'");
    }

    // Set up dialog handler before triggering
    // For web, native alerts (alert, confirm, prompt) are handled via page.on('dialog')
    // This implementation assumes the alert is already showing or will appear

    return new Promise<void>((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        this.page.removeListener('dialog', dialogHandler);
        reject(new Error(`Alert did not appear within ${timeout}ms`));
      }, timeout);

      const dialogHandler = async (dialog: import('playwright').Dialog) => {
        clearTimeout(timeoutId);

        const dialogType = dialog.type();

        // For confirm dialogs, match button text to accept/dismiss
        if (dialogType === 'confirm') {
          // Common button text mappings
          const acceptTexts = ['OK', 'Yes', 'Confirm', 'Accept', 'はい', '確認', 'OK'];
          const dismissTexts = ['Cancel', 'No', 'Dismiss', 'いいえ', 'キャンセル'];

          if (acceptTexts.some(t => t.toLowerCase() === buttonText.toLowerCase())) {
            await dialog.accept();
            resolve();
            return;
          }
          if (dismissTexts.some(t => t.toLowerCase() === buttonText.toLowerCase())) {
            await dialog.dismiss();
            resolve();
            return;
          }
          // If button text doesn't match known patterns, try accept
          await dialog.accept();
          resolve();
          return;
        }

        // For alert dialogs, just dismiss (they only have OK)
        if (dialogType === 'alert') {
          await dialog.accept();
          resolve();
          return;
        }

        // For prompt dialogs
        if (dialogType === 'prompt') {
          const acceptTexts = ['OK', 'Submit', 'Yes', 'はい', '確認'];
          if (acceptTexts.some(t => t.toLowerCase() === buttonText.toLowerCase())) {
            await dialog.accept();
          } else {
            await dialog.dismiss();
          }
          resolve();
          return;
        }

        // Default: accept
        await dialog.accept();
        resolve();
      };

      this.page.once('dialog', dialogHandler);
    });
  }

  private async executeSelectOption(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("selectOption requires 'id'");
    }

    const element = await this.waitForElement(id, timeout);

    // Try to find a select element within the container
    const select = element.locator('select').first();
    const hasSelect = await select.count() > 0;

    const targetSelect = hasSelect ? select : element;

    // Select by value, label, or index
    if (step.value !== undefined) {
      await targetSelect.selectOption({ value: step.value });
    } else if (step.label !== undefined) {
      await targetSelect.selectOption({ label: step.label });
    } else if (step.index !== undefined) {
      await targetSelect.selectOption({ index: step.index });
    } else {
      throw new Error("selectOption requires 'value', 'label', or 'index'");
    }
  }

  private async executeTapItem(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("tapItem requires 'id'");
    }
    const index = step.index;
    if (index === undefined) {
      throw new Error("tapItem requires 'index'");
    }

    // Find the item using the generated id pattern: {collectionId}_item_{index}
    const itemId = `${id}_item_${index}`;
    const element = await this.waitForElement(itemId, timeout);
    await element.click();
  }

  private async executeSelectTab(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("selectTab requires 'id'");
    }
    const index = step.index;
    if (index === undefined) {
      throw new Error("selectTab requires 'index'");
    }

    // Find the tab using the generated id pattern: {tabViewId}_tab_{index}
    const tabId = `${id}_tab_${index}`;
    const element = await this.waitForElement(tabId, timeout);
    await element.click();
  }

  private async executeScrollUntilVisible(step: TestStep): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("scrollUntilVisible requires 'id'");
    }
    const direction = step.direction ?? 'down';
    const timeout = step.timeout ?? 20000;
    const target = this.getLocator(id).first();

    const isTargetVisible = async (): Promise<boolean> => {
      return (await target.count()) > 0 && await target.isVisible();
    };

    if (await isTargetVisible()) {
      return;
    }

    // `direction` is the FIRST direction to search, not a constraint: when the
    // primary sweep reaches the end of content without a hit, the search
    // continues in the OPPOSITE direction to the other end. The target can
    // legitimately sit on the far side of the starting offset (measured on a
    // tablet 2-column page: a tall section left partially visible at the
    // viewport top made an "scroll up until visible" reset step a correct
    // no-op, and a down-only search then ran to the bottom while the target
    // sat just above the viewport).
    const searchLeg = async (
      legDirection: 'up' | 'down' | 'left' | 'right',
      deadline: number
    ): Promise<boolean> => {
      let previousMarker: string | null = null;
      let unchangedCount = 0;

      while (Date.now() < deadline) {
        const marker = await this.scrollOneStep(step.container, legDirection);

        if (await isTargetVisible()) {
          return true;
        }

        // End-reached detection: two consecutive scrolls with no position/content change
        if (marker !== null && marker === previousMarker) {
          unchangedCount += 1;
          if (unchangedCount >= 1) {
            return false;
          }
        } else {
          unchangedCount = 0;
        }
        previousMarker = marker;

        await this.page.waitForTimeout(150);
      }
      return isTargetVisible();
    };

    if (await searchLeg(direction, Date.now() + timeout)) {
      return;
    }
    // Reverse leg: grant it a real budget even when the primary leg burned the
    // step timeout (bounded: at most one extra half-timeout).
    const reverseMap = { down: 'up', up: 'down', left: 'right', right: 'left' } as const;
    const reverse = reverseMap[direction] ?? 'up';
    if (await searchLeg(reverse, Date.now() + Math.max(timeout / 2, 6000))) {
      return;
    }
    throw new Error(
      `Element '${id}' not found after scrolling to both ends of ${step.container ? `'${step.container}'` : 'the page'}`
    );
  }

  /**
   * Scroll one step in the given direction. Returns a marker string describing the
   * scroll position after scrolling (used for end-reached detection), or null if unknown.
   */
  private async scrollOneStep(
    containerId: string | undefined,
    direction: 'up' | 'down' | 'left' | 'right'
  ): Promise<string | null> {
    if (containerId) {
      const container = this.getLocator(containerId).first();
      if (await container.count() === 0) {
        throw new Error(`scrollUntilVisible container '${containerId}' not found`);
      }
      return container.evaluate((el, dir) => {
        const step = Math.round((dir === 'up' || dir === 'down' ? el.clientHeight : el.clientWidth) * 0.7);
        switch (dir) {
          case 'up': el.scrollTop -= step; break;
          case 'down': el.scrollTop += step; break;
          case 'left': el.scrollLeft -= step; break;
          case 'right': el.scrollLeft += step; break;
        }
        return `${el.scrollTop},${el.scrollLeft}`;
      }, direction);
    }

    // Scroll the window
    return this.page.evaluate((dir) => {
      const step = Math.round((dir === 'up' || dir === 'down' ? window.innerHeight : window.innerWidth) * 0.7);
      switch (dir) {
        case 'up': window.scrollBy(0, -step); break;
        case 'down': window.scrollBy(0, step); break;
        case 'left': window.scrollBy(-step, 0); break;
        case 'right': window.scrollBy(step, 0); break;
      }
      return `${window.scrollY},${window.scrollX}`;
    }, direction);
  }

  private async executeReadText(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("readText requires 'id'");
    }
    const variable = step.variable;
    if (!variable) {
      throw new Error("readText requires 'variable'");
    }
    const element = await this.waitForElement(id, timeout);

    // For input/textarea, read value; otherwise text content
    const text = await element.evaluate((el) => {
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        return el.value;
      }
      const input = el.querySelector(
        'input:not([type="checkbox"]):not([type="radio"]), textarea'
      );
      if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement) {
        return input.value;
      }
      return el.textContent ?? '';
    });

    this.variables[variable] = text;
  }

  private async executeSetLocation(step: TestStep): Promise<void> {
    const { latitude, longitude } = step;
    if (latitude === undefined || longitude === undefined) {
      throw new Error("setLocation requires 'latitude' and 'longitude'");
    }
    const context = this.page.context();
    await context.grantPermissions(['geolocation']);
    await context.setGeolocation({ latitude, longitude });
  }

  /**
   * Set files on a file input. Paths resolve relative to the test file's
   * directory (TestLoader base path); absolute paths pass through. With an
   * `id`, targets that element (the input itself, or a file input inside
   * it); without one, the page's first input[type=file]. setInputFiles
   * works on hidden inputs (display:none / opacity:0), so the native picker
   * never needs to open.
   */
  private async executeAddMedia(step: TestStep): Promise<void> {
    const paths = step.paths;
    if (!paths || paths.length === 0) {
      throw new Error("addMedia requires non-empty 'paths'");
    }

    const base = process.cwd(); // vendored: TestLoader base-path resolution not used by conformance
    const resolved = paths.map((p) => (path.isAbsolute(p) ? p : path.resolve(base, p)));
    for (const p of resolved) {
      if (!fs.existsSync(p)) {
        throw new Error(`addMedia: file not found: ${p}`);
      }
    }

    let input: Locator;
    if (step.id) {
      const target = this.getLocator(step.id).first();
      await target.waitFor({ state: 'attached', timeout: step.timeout ?? this.defaultTimeout });
      const isFileInput = await target.evaluate(
        (node) => node instanceof HTMLInputElement && node.type === 'file'
      );
      input = isFileInput ? target : target.locator('input[type="file"]').first();
    } else {
      input = this.page.locator('input[type="file"]').first();
    }

    await input.setInputFiles(resolved);
  }

  /**
   * Call a browser-side hook the app registered on window.__jsonuiTestHooks
   * (e.g. an RTDB mock emitter). A limited, declarative alternative to a raw
   * script step: the runner can only invoke hooks the app chose to expose.
   * Web-only — mobile drivers treat emitHook as a no-op with a warning.
   */
  private async executeEmitHook(step: TestStep): Promise<void> {
    const name = step.name;
    if (!name) {
      throw new Error("emitHook requires 'name'");
    }
    const hookArgs = step.hookArgs ?? [];

    await this.page.evaluate(
      ({ name, hookArgs }) => {
        const hooks = (window as unknown as {
          __jsonuiTestHooks?: Record<string, (...args: unknown[]) => unknown>;
        }).__jsonuiTestHooks;
        const fn = hooks?.[name];
        if (typeof fn !== 'function') {
          const registered = hooks ? Object.keys(hooks).join(', ') || '(none)' : '(none)';
          throw new Error(
            `emitHook: hook '${name}' is not registered on window.__jsonuiTestHooks (registered: ${registered})`
          );
        }
        return fn(...hookArgs);
      },
      { name, hookArgs }
    );
  }

  /** Resize the viewport to sweep responsive breakpoints (web-native drive) */
  private async executeSetViewport(step: TestStep): Promise<void> {
    const { width, height } = step;
    if (width === undefined || height === undefined) {
      throw new Error("setViewport requires 'width' and 'height'");
    }
    await this.page.setViewportSize({ width, height });
  }

  /**
   * Rotate to the given orientation by swapping the viewport width/height.
   * Already-matching orientation is a no-op; a `viewport: null` context
   * (headful / --start-maximized) cannot be resized, so it is a no-op with a
   * warning — dependent asserts should self-gate with `when.responsive`.
   */
  private async executeSetOrientation(step: TestStep): Promise<void> {
    const orientation = step.orientation;
    if (!orientation) {
      throw new Error("setOrientation requires 'orientation'");
    }
    const viewport = this.page.viewportSize();
    if (!viewport) {
      console.warn(
        '[ActionExecutor] setOrientation: no viewport is set (viewport: null context) - skipping (no-op)'
      );
      return;
    }
    if (deriveOrientation(viewport) === orientation) {
      return;
    }
    await this.page.setViewportSize({ width: viewport.height, height: viewport.width });
  }

  // Helper functions

  /**
   * Get locator for element by id attribute
   */
  private getLocator(id: string): Locator {
    return this.page.locator(`#${id}`);
  }

  /**
   * Wait for element to appear by id attribute
   */
  private async waitForElement(id: string, timeout: number): Promise<Locator> {
    const element = this.getLocator(id);

    try {
      await element.first().waitFor({ state: 'visible', timeout });
      return element.first();
    } catch (error) {
      throw new Error(`Element '${id}' not found by id within ${timeout}ms`);
    }
  }

  /**
   * Tap on a specific text portion within an element
   * Calculates the approximate position of the target text and clicks there
   */
  private async tapTextPortion(element: Locator, targetText: string): Promise<void> {
    // Preferred: a real DOM descendant carrying exactly the range text —
    // ReactJsonUI renders each clickable partialAttributes range as its own
    // <span onClick>. Clicking its true rect is exact for centered/matchParent
    // and wrapped labels where the proportional estimate below misses
    // (test-partialattributes-subrange-tap-misses-on-centered-matchparent-label).
    const rangeTarget = element.getByText(targetText, { exact: true }).first();
    if ((await rangeTarget.count()) > 0) {
      await rangeTarget.click();
      return;
    }

    const fullText = await element.textContent();
    if (!fullText) {
      throw new Error('Element has no text content');
    }

    const startIndex = fullText.indexOf(targetText);
    if (startIndex === -1) {
      throw new Error(`Text '${targetText}' not found in element text '${fullText}'`);
    }

    const endIndex = startIndex + targetText.length;
    const totalLength = fullText.length;

    if (totalLength === 0) {
      await element.click();
      return;
    }

    // Calculate the center position of the target text (as a ratio of the element width)
    const startRatio = startIndex / totalLength;
    const endRatio = endIndex / totalLength;
    const centerRatio = (startRatio + endRatio) / 2;

    // Get the bounding box of the element
    const box = await element.boundingBox();
    if (!box) {
      throw new Error('Element has no bounding box');
    }

    // Calculate the tap coordinate
    const tapX = box.x + (box.width * centerRatio);
    const tapY = box.y + (box.height / 2);

    // Click at the calculated position
    await this.page.mouse.click(tapX, tapY);
  }
}
