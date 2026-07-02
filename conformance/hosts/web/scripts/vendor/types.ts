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
  setup?: TestStep[];
  teardown?: TestStep[];
  cases: TestCase[];
}

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
}

// MARK: - Action & Assertion Types

export type ActionType =
  | 'tap'
  | 'doubleTap'
  | 'longPress'
  | 'input'
  | 'clear'
  | 'scroll'
  | 'swipe'
  | 'waitFor'
  | 'waitForAny'
  | 'wait'
  | 'back'
  | 'screenshot'
  | 'alertTap'
  | 'selectOption'
  | 'tapItem'
  | 'selectTab';

export type AssertionType =
  | 'visible'
  | 'notVisible'
  | 'enabled'
  | 'disabled'
  | 'text'
  | 'count';

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

export interface TestResult {
  testName: string;
  caseName: string;
  passed: boolean;
  error?: string;
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

export function isBlockStep(step: FlowTestStep): boolean {
  return step.block !== undefined;
}

export function isInlineStep(step: FlowTestStep): boolean {
  return step.screen !== undefined && (step.action !== undefined || step.assert !== undefined);
}
