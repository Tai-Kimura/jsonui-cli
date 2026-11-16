/**
 * JsonUI Test Runner - Web Driver
 * State provider for `state` assertions and `state` conditions
 */

import type { Page } from 'playwright';
import { lookupInBridge, readBridge, type StateLookup } from './StateBridge.ts';

/**
 * Provides ViewModel state values by dot-notation path.
 *
 * The default is BridgeStateProvider, which needs nothing from the harness. A
 * provider passed in the runner config (`stateProvider`) wins over it.
 */
export interface StateProvider {
  /**
   * Get the value at the given dot-notation path (e.g. 'user.isLoggedIn').
   * Returns undefined when the path does not resolve.
   */
  getValue(path: string): Promise<unknown>;
  /**
   * Optional richer answer: pending / truncated / value / unresolved. When
   * present the runner uses it instead of getValue (a truncated bridge fails
   * at once, a pending one says why on timeout).
   */
  lookup?(path: string): Promise<StateLookup>;
}

/**
 * The default provider: resolves `path` in the `data` of
 * `window.__JSONUI_STATE__[screenId]`, for the screen the runner says `state`
 * reads (spec §6: the screen under test; in a flow the step's `screen`, else
 * the last one named; a referenced case reads its own file's screen).
 */
export class BridgeStateProvider implements StateProvider {
  // Plain fields, not parameter properties: the conformance web host vendors
  // this file and runs it under Node's type stripping, which rejects them.
  private page: Page;
  private screen: () => string | undefined;

  constructor(page: Page, screen: () => string | undefined) {
    this.page = page;
    this.screen = screen;
  }

  async lookup(path: string): Promise<StateLookup> {
    const screenId = this.screen();
    if (!screenId) {
      return {
        outcome: 'pending',
        reason: 'no screen to read state from (a flow step names none yet, and the test has no source.layout)'
      };
    }
    return lookupInBridge(await readBridge(this.page, screenId), path, screenId);
  }

  async getValue(path: string): Promise<unknown> {
    const found = await this.lookup(path);
    return found.outcome === 'value' ? found.value : undefined;
  }
}

/** A provider's answer as a lookup (harness providers have only getValue). */
export async function lookupState(provider: StateProvider, path: string): Promise<StateLookup> {
  if (provider.lookup) return provider.lookup(path);
  const value = await provider.getValue(path);
  return value === undefined ? { outcome: 'unresolved' } : { outcome: 'value', value };
}

export const TRUNCATED_MESSAGE = (path: string, bytes: number): string =>
  `state '${path}': the state bridge is truncated (${bytes} bytes; the iOS bridge holds up to 32 KB)`;
