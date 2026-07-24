/**
 * JsonUI Test Runner - Web Driver Models
 * Type definitions for test cases and results
 */

// MARK: - Screen Test

export interface ScreenTest {
  type: 'screen';
  source: TestSource;
  metadata: TestMetadata;
  platform?: PlatformTarget;
  initialState?: InitialState;
  /** App launch configuration (apply via applyLaunchConfig before navigation) */
  launch?: LaunchConfig;
  /** API mock scenario set applied (and the screen reloaded) before the cases run */
  mocks?: MockScenarioMap;
  setup?: TestStep[];
  teardown?: TestStep[];
  cases: TestCase[];
}

/** Map of OpenAPI operationId -> mock scenario name */
export type MockScenarioMap = Record<string, string>;

export interface TestSource {
  layout: string;
  spec?: string;
}

export interface TestMetadata {
  name: string;
  description?: string;
  generatedAt?: string;
  generatedBy?: string;
  tags?: string[];
}

export interface InitialState {
  viewModel?: Record<string, unknown>;
}

export interface TestCase {
  name: string;
  description?: string;
  skip?: boolean;
  platform?: PlatformTarget;
  /** Run this case only when the current size matches (resolved at runtime; unmet gates skip the case) */
  responsive?: ResponsiveCondition;
  initialState?: InitialState;
  steps: TestStep[];
  /** Default argument values for @{varName} substitution */
  args?: Record<string, unknown>;
}

// MARK: - Flow Test

export interface FlowTest {
  type: 'flow';
  sources?: FlowTestSource[];  // Now optional (not needed when using file references)
  metadata: TestMetadata;
  platform?: PlatformTarget;
  initialState?: FlowInitialState;
  /** App launch configuration (apply via applyLaunchConfig before navigation) */
  launch?: LaunchConfig;
  /**
   * File-level mock scenarios (operationId -> scenario) applied before the
   * first navigation, so startup fetches run under the selected scenarios.
   * Parity with ScreenTest.mocks; step-level setMocks handles mid-flow switches.
   */
  mocks?: Record<string, string>;
  setup?: FlowTestStep[];
  teardown?: FlowTestStep[];
  steps: FlowTestStep[];
  checkpoints?: Checkpoint[];
}

export interface FlowTestSource {
  layout: string;
  spec?: string;
  alias?: string;
}

export interface FlowInitialState {
  screen?: string;
  viewModels?: Record<string, Record<string, unknown>>;
}

export interface FlowTestStep {
  // For inline steps
  screen?: string;
  action?: string;
  assert?: string;
  id?: string;
  ids?: string[];
  text?: string;
  value?: string;
  direction?: 'up' | 'down' | 'left' | 'right';
  duration?: number;
  timeout?: number;
  ms?: number;
  name?: string;
  equals?: unknown;
  contains?: string;
  path?: string;
  amount?: number;
  button?: string;
  label?: string;
  index?: number;
  /** When true, a failure of this step is recorded as a warning and execution continues */
  optional?: boolean;
  /** Pre-condition; step is skipped when not satisfied (also valid on file/block steps) */
  when?: WhenCondition;
  /** Re-tap once when the UI did not change after the tap (accepted, no-op on web) */
  retryTapIfNoChange?: boolean;
  /** Scrollable container id for scrollUntilVisible */
  container?: string;
  /** Runtime variable name for readText */
  variable?: string;
  /** Iteration count for repeat */
  times?: number;
  /** Loop condition for repeat */
  while?: WhenCondition;
  /** Number of retries for retry (0-3) */
  maxRetries?: number;
  /** Latitude for setLocation */
  latitude?: number;
  /** Longitude for setLocation */
  longitude?: number;
  /** Media file paths for addMedia */
  paths?: string[];
  /** Positional arguments for emitHook (passed to the registered page hook) */
  hookArgs?: unknown[];
  /** Crop element id for screenshot assertion */
  cropId?: string;
  /** Similarity threshold (0-100) for screenshot assertion */
  threshold?: number;
  /** Scenario map for the setMocks action (operationId -> scenario) */
  mocks?: MockScenarioMap;
  /** Viewport width in logical pixels for setViewport */
  width?: number;
  /** Viewport height in logical pixels for setViewport */
  height?: number;
  /** Target orientation for setOrientation */
  orientation?: ResponsiveOrientation;
  // For file reference steps
  file?: string;
  case?: string;
  cases?: string[];
  /** Arguments to override screen test default args (for file reference steps) */
  args?: Record<string, unknown>;
  // For block steps (grouped inline actions)
  block?: string;
  description?: string;
  descriptionFile?: string;
  steps?: FlowTestStep[];
}

export interface Checkpoint {
  name: string;
  afterStep: number;
  screenshot?: boolean;
}

// MARK: - Condition (for 'when' and 'repeat.while')

export interface WhenCondition {
  /** Instant check: element is currently visible */
  visible?: string;
  /** Instant check: element is currently absent or invisible */
  notVisible?: string;
  /** Current platform matches (same matching rules as the step-level platform field) */
  platform?: PlatformTarget;
  /** Current size class / viewport size matches (resolved at runtime from the live viewport) */
  responsive?: ResponsiveCondition;
  /** ViewModel state matches (requires a state provider) */
  state?: { path: string; equals: unknown };
}

/**
 * Condition keys this driver understands. A condition containing any other key
 * (e.g. one added by a newer schema) is treated as UNMET so the step fail-safe
 * skips instead of running at a state it cannot verify (never run-anyway,
 * never throw).
 */
export const KNOWN_CONDITION_KEYS: ReadonlySet<string> = new Set([
  'visible',
  'notVisible',
  'platform',
  'responsive',
  'state'
]);

/** Keys of a condition object this driver does not understand (fail-safe skip when non-empty) */
export function unknownConditionKeys(condition: WhenCondition): string[] {
  return Object.keys(condition).filter(key => !KNOWN_CONDITION_KEYS.has(key));
}

// MARK: - Responsive (size-class gating resolved at runtime)

export type ResponsiveOrientation = 'portrait' | 'landscape';

/** Exclusive width tier resolved from the current viewport width */
export type ResponsiveSizeTier = 'compact' | 'medium' | 'regular';

/**
 * Named size-class bucket from the render-side canonical vocabulary
 * (shared/core/attribute_definitions.json). Bare tiers match at any
 * orientation; 'landscape' matches at any tier; '<tier>-landscape' matches
 * tier AND landscape.
 */
export type ResponsiveBucket =
  | 'compact'
  | 'medium'
  | 'regular'
  | 'landscape'
  | 'compact-landscape'
  | 'medium-landscape'
  | 'regular-landscape';

/** Explicit size constraint; present keys are ANDed, min/max are inclusive. Units: logical px on web. */
export interface ResponsiveConstraint {
  minWidth?: number;
  maxWidth?: number;
  minHeight?: number;
  maxHeight?: number;
  orientation?: ResponsiveOrientation;
}

/** Value of the `responsive` condition / case-level gate: a named bucket or a size constraint */
export type ResponsiveCondition = ResponsiveBucket | ResponsiveConstraint;

/**
 * Named-bucket width thresholds in logical px. Defaults mirror the web
 * renderer's Tailwind breakpoints (`md:` 768 / `lg:` 1024 — the web SSoT,
 * rjui_tools responsive_helper). Thresholds are overridable for projects that
 * also override the renderer's breakpoints; bucket NAMES are fixed — config
 * cannot add or rename buckets, otherwise validation and the runner would
 * disagree on the vocabulary.
 */
export interface ResponsiveThresholds {
  /** Minimum width (inclusive) for the `medium` tier */
  medium: number;
  /** Minimum width (inclusive) for the `regular` tier */
  regular: number;
}

export interface ViewportDimensions {
  width: number;
  height: number;
}

/**
 * Minimal page surface needed to read the current viewport size. Structurally
 * satisfied by a Playwright Page; kept narrow so resolution is unit-testable
 * without a live browser.
 */
export interface ViewportSource {
  viewportSize(): { width: number; height: number } | null;
  evaluate<R>(fn: () => R): Promise<R>;
}

/**
 * Resolve the current viewport size. `page.viewportSize()` returns null for
 * `viewport: null` contexts (headful / --start-maximized), so fall back to
 * `window.innerWidth/innerHeight` — which is also what the renderer's CSS
 * breakpoints actually see (closer to the SSoT than the viewport setting).
 */
export async function resolveViewportSize(page: ViewportSource): Promise<ViewportDimensions> {
  const viewport = page.viewportSize();
  if (viewport) {
    return { width: viewport.width, height: viewport.height };
  }
  return page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
}

/** Orientation derived from the current size (square counts as landscape) */
export function deriveOrientation(size: ViewportDimensions): ResponsiveOrientation {
  return size.height > size.width ? 'portrait' : 'landscape';
}

/** Exclusive width tier: >= regular -> 'regular', >= medium -> 'medium', else 'compact' */
export function resolveSizeTier(width: number, thresholds: ResponsiveThresholds): ResponsiveSizeTier {
  if (width >= thresholds.regular) {
    return 'regular';
  }
  if (width >= thresholds.medium) {
    return 'medium';
  }
  return 'compact';
}

/**
 * Evaluate a `responsive` condition against the current size.
 * - Named tier buckets match the resolved tier at any orientation.
 * - 'landscape' matches orientation landscape at any tier.
 * - '<tier>-landscape' matches tier AND landscape.
 * - Constraint objects AND all present keys (min/max inclusive per the schema).
 * - An unrecognized named bucket (newer schema than this driver) is UNMET, so
 *   the gated step/case fail-safe skips.
 */
export function matchesResponsive(
  condition: ResponsiveCondition,
  size: ViewportDimensions,
  thresholds: ResponsiveThresholds
): boolean {
  const orientation = deriveOrientation(size);

  if (typeof condition === 'string') {
    const tier = resolveSizeTier(size.width, thresholds);
    switch (condition) {
      case 'compact':
      case 'medium':
      case 'regular':
        return tier === condition;
      case 'landscape':
        return orientation === 'landscape';
      case 'compact-landscape':
      case 'medium-landscape':
      case 'regular-landscape':
        return orientation === 'landscape' && tier === condition.slice(0, -'-landscape'.length);
      default:
        // Fail-safe: a bucket this driver does not know is unmet -> skip
        return false;
    }
  }

  if (condition.minWidth !== undefined && size.width < condition.minWidth) return false;
  if (condition.maxWidth !== undefined && size.width > condition.maxWidth) return false;
  if (condition.minHeight !== undefined && size.height < condition.minHeight) return false;
  if (condition.maxHeight !== undefined && size.height > condition.maxHeight) return false;
  if (condition.orientation !== undefined && condition.orientation !== orientation) return false;
  return true;
}

// MARK: - Launch Configuration

export type LaunchPermissionValue = 'allow' | 'deny' | 'unset';

export interface LaunchConfig {
  /** Clear cookies + local/session storage for the origin before launch */
  clearState?: boolean;
  /** Permission grants applied before launch (camera, microphone, location, notifications, photos, contacts, calendar, bluetooth) */
  permissions?: Record<string, LaunchPermissionValue>;
  /** Launch arguments written to sessionStorage["JSONUI_TEST_ARGS"] as JSON */
  arguments?: Record<string, string | number | boolean>;
}

// MARK: - Test Step (for Screen Tests)

export interface TestStep {
  action?: ActionType;
  assert?: AssertionType;
  id?: string;
  ids?: string[];
  text?: string;
  value?: string;
  direction?: 'up' | 'down' | 'left' | 'right';
  duration?: number;
  timeout?: number;
  ms?: number;
  name?: string;
  equals?: unknown;
  contains?: string;
  path?: string;
  amount?: number;
  button?: string;
  label?: string;
  index?: number;
  /** When true, a failure of this step is recorded as a warning and execution continues */
  optional?: boolean;
  /** Pre-condition; step is skipped when not satisfied */
  when?: WhenCondition;
  /** Re-tap once when the UI did not change after the tap (accepted, no-op on web) */
  retryTapIfNoChange?: boolean;
  /** Scrollable container id for scrollUntilVisible */
  container?: string;
  /** Runtime variable name for readText */
  variable?: string;
  /** Iteration count for repeat */
  times?: number;
  /** Loop condition for repeat */
  while?: WhenCondition;
  /** Nested steps for repeat/retry control steps */
  steps?: TestStep[];
  /** Number of retries for retry (0-3) */
  maxRetries?: number;
  /** Latitude for setLocation */
  latitude?: number;
  /** Longitude for setLocation */
  longitude?: number;
  /** Media file paths for addMedia */
  paths?: string[];
  /** Positional arguments for emitHook (passed to the registered page hook) */
  hookArgs?: unknown[];
  /** Crop element id for screenshot assertion */
  cropId?: string;
  /** Similarity threshold (0-100) for screenshot assertion */
  threshold?: number;
  /** Scenario map for the setMocks action (operationId -> scenario) */
  mocks?: MockScenarioMap;
  /** Viewport width in logical pixels for setViewport */
  width?: number;
  /** Viewport height in logical pixels for setViewport */
  height?: number;
  /** Target orientation for setOrientation */
  orientation?: ResponsiveOrientation;
}

// MARK: - Action & Assertion Types

export type ActionType =
  | 'tap'
  | 'doubleTap'
  | 'longPress'
  | 'input'
  | 'typeText'
  | 'clear'
  | 'scroll'
  | 'scrollUntilVisible'
  | 'swipe'
  | 'waitFor'
  | 'waitForAny'
  | 'wait'
  | 'back'
  | 'hideKeyboard'
  | 'screenshot'
  | 'alertTap'
  | 'selectOption'
  | 'tapItem'
  | 'selectTab'
  | 'readText'
  | 'repeat'
  | 'retry'
  | 'setLocation'
  | 'addMedia'
  | 'setMocks'
  | 'setViewport'
  | 'setOrientation'
  | 'emitHook';

export type AssertionType =
  | 'visible'
  | 'notVisible'
  | 'enabled'
  | 'disabled'
  | 'text'
  | 'count'
  | 'state'
  | 'screenshot'
  | 'openedUrl';

// MARK: - Platform Target

export type PlatformTarget = string | string[];

export function platformIncludes(target: PlatformTarget | undefined, platform: string): boolean {
  if (!target) return true;
  if (typeof target === 'string') {
    return target === platform || target === 'all';
  }
  return target.includes(platform);
}

// MARK: - Test Result

/** Why a skipped result was skipped; only set for gate-caused skips (results.schema.json skipReason) */
export type SkipReason = 'platform' | 'responsive';

export interface TestResult {
  testName: string;
  caseName: string;
  passed: boolean;
  /** True when the case was skipped (skip flag, platform or responsive mismatch); passed stays true for compatibility */
  skipped?: boolean;
  /** Why the case was skipped (platform vs responsive gate); unset for plain `skip: true` skips */
  skipReason?: SkipReason;
  error?: string;
  /** Warnings collected during the case (optional-step failures, baseline created, ...) */
  warnings?: string[];
  durationMs: number;
}

export interface TestSuiteResult {
  suiteName: string;
  results: TestResult[];
  totalDurationMs: number;
}

export function getPassedCount(result: TestSuiteResult): number {
  return result.results.filter(r => r.passed).length;
}

export function getFailedCount(result: TestSuiteResult): number {
  return result.results.filter(r => !r.passed).length;
}

export function allPassed(result: TestSuiteResult): boolean {
  return result.results.every(r => r.passed);
}

// MARK: - Loaded Test

export type LoadedTest =
  | { type: 'screen'; test: ScreenTest; filePath: string }
  | { type: 'flow'; test: FlowTest; filePath: string };

// MARK: - Helper Functions

export function isAction(step: TestStep): boolean {
  return step.action !== undefined;
}

export function isAssertion(step: TestStep): boolean {
  return step.assert !== undefined;
}

export function isFileReference(step: FlowTestStep): boolean {
  return step.file !== undefined;
}

/**
 * Deep equality for state values (primitives compared strictly, objects/arrays structurally)
 */
export function deepEquals(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null || a === undefined || b === undefined) return false;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object') return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

export function isBlockStep(step: FlowTestStep): boolean {
  return step.block !== undefined;
}

export function isInlineStep(step: FlowTestStep): boolean {
  return step.screen !== undefined && (step.action !== undefined || step.assert !== undefined);
}
