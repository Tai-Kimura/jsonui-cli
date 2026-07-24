/**
 * JsonUI Test Runner - Web Driver
 * State provider for `state` assertions and `state` conditions
 */

import type { Page } from 'playwright';

/**
 * Provides ViewModel state values by dot-notation path.
 * Custom providers can be injected through the runner config.
 */
export interface StateProvider {
  /**
   * Get the value at the given dot-notation path (e.g. 'user.isLoggedIn').
   * Returns undefined when the path does not resolve.
   */
  getValue(path: string): Promise<unknown>;
}

/**
 * Default state provider reading window.__JSONUI_STATE__ via page.evaluate.
 * The JsonUI app is expected to expose its ViewModel state on that global.
 */
export class WindowStateProvider implements StateProvider {
  private page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async getValue(statePath: string): Promise<unknown> {
    return this.page.evaluate((p) => {
      const root = (window as unknown as { __JSONUI_STATE__?: unknown }).__JSONUI_STATE__;
      let current: unknown = root;
      for (const segment of p.split('.')) {
        if (current === null || current === undefined || typeof current !== 'object') {
          return undefined;
        }
        current = (current as Record<string, unknown>)[segment];
      }
      return current;
    }, statePath);
  }
}
