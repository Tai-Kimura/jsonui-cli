/**
 * JsonUI Test Runner - Web Driver
 * Assertion executor using Playwright
 *
 * Uses id attribute for element matching (ReactJsonUI exposes id as HTML id attribute)
 */

import type { Page, Locator } from 'playwright';
import type { TestStep } from './types.ts';

export class AssertionExecutor {
  private page: Page;
  private defaultTimeout: number;

  constructor(page: Page, defaultTimeout: number = 5000) {
    this.page = page;
    this.defaultTimeout = defaultTimeout;
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
      default:
        throw new Error(`Unknown assertion: ${assertion}`);
    }
  }

  private async assertVisible(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("visible requires 'id'");
    }
    const element = await this.waitForElement(id, timeout);
    const isVisible = await element.isVisible();
    if (!isVisible) {
      throw new Error(`Element '${id}' should be visible but it is not`);
    }
  }

  private async assertNotVisible(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("notVisible requires 'id'");
    }

    // Wait briefly and check element is not visible
    await this.page.waitForTimeout(Math.min(timeout, 1000));

    const element = this.getLocator(id);
    const count = await element.count();

    if (count > 0) {
      const isVisible = await element.first().isVisible();
      if (isVisible) {
        throw new Error(`Element '${id}' should not be visible but it is`);
      }
    }
    // Success - element was not found or not visible
  }

  private async assertEnabled(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("enabled requires 'id'");
    }
    const element = await this.waitForElement(id, timeout);

    // Check for disabled attribute or aria-disabled
    const isDisabled = await element.evaluate((el) => {
      if (el instanceof HTMLButtonElement || el instanceof HTMLInputElement) {
        return el.disabled;
      }
      return el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('disabled');
    });

    if (isDisabled) {
      throw new Error(`Element '${id}' should be enabled but it is disabled`);
    }
  }

  private async assertDisabled(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("disabled requires 'id'");
    }
    const element = await this.waitForElement(id, timeout);

    // Check for disabled attribute or aria-disabled
    const isDisabled = await element.evaluate((el) => {
      if (el instanceof HTMLButtonElement || el instanceof HTMLInputElement) {
        return el.disabled;
      }
      return el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('disabled');
    });

    if (!isDisabled) {
      throw new Error(`Element '${id}' should be disabled but it is enabled`);
    }
  }

  private async assertText(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("text requires 'id'");
    }
    const element = await this.waitForElement(id, timeout);

    // For input/textarea, get value; otherwise get text content
    const actualText = await element.evaluate((el) => {
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        return el.value;
      }
      // Check for nested input/textarea. Checkbox/radio inputs are excluded:
      // their `value` is a form-submission token (default "on"), not
      // user-visible text — for composite controls (label + input) the
      // visible text is the label's textContent. [local patch, see VENDOR.md]
      const input = el.querySelector(
        'input:not([type="checkbox"]):not([type="radio"]), textarea'
      );
      if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement) {
        return input.value;
      }
      return el.textContent ?? '';
    });

    if (step.equals !== undefined) {
      const expectedText = String(step.equals);
      if (actualText !== expectedText) {
        throw new Error(`Expected text '${expectedText}' but got '${actualText}' for element '${id}'`);
      }
    } else if (step.contains !== undefined) {
      if (!actualText.includes(step.contains)) {
        throw new Error(`Expected text containing '${step.contains}' but got '${actualText}' for element '${id}'`);
      }
    } else {
      throw new Error("text requires 'equals' or 'contains'");
    }
  }

  private async assertCount(step: TestStep, timeout: number): Promise<void> {
    const id = step.id;
    if (!id) {
      throw new Error("count requires 'id'");
    }
    if (step.equals === undefined || typeof step.equals !== 'number') {
      throw new Error("count requires 'equals' with integer value");
    }

    const expected = step.equals as number;

    // Wait for at least one element (or timeout)
    try {
      await this.waitForElement(id, timeout);
    } catch {
      // If no elements found and expected is 0, that's valid
      if (expected === 0) {
        return;
      }
      throw new Error(`Expected ${expected} elements with id '${id}', but found 0`);
    }

    // Count all elements with the given data-testid
    const elements = this.getLocator(id);
    const actualCount = await elements.count();

    if (actualCount !== expected) {
      throw new Error(`Expected ${expected} elements with id '${id}', but found ${actualCount}`);
    }
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
}
