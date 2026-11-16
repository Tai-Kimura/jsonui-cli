/**
 * conformanceState provider — the ONE generic mechanism the web host
 * implements for every `class: interactive` fixture (plan 12 §2.2).
 *
 * Contract (see conformance/INTERACTIVE_HOST_CONTRACT.md):
 * - initial values come from the fixture layout's `data` section; on this
 *   host that is `create<Fx>Data()` emitted by rjui codegen (the production
 *   path), seeded into React state.
 * - `state.handlers` declares host-injected closures: invoking one sets a
 *   single state variable to a literal value; any callback payload is
 *   ignored. No fixture-specific code exists anywhere in the host.
 * - two-way write-back: rjui emits `on<Var>Change` dispatchers for bound
 *   inputs and its hook layer normally provides default setters. Fixtures
 *   have no ViewModel, so the same defaults are provided here — for every
 *   `on<Var>Change` key left undefined in the generated Data shape whose
 *   `<var>` exists, a setter for `<var>` is injected (mirrors
 *   rjui_tools/lib/react/hook_generator.rb semantics).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { getEmbedNavigator } from './components/extensions/EmbedContainer';
import { useJsonUITestBridge, type JsonUITestApplyResult } from './generated/jsonuiTestBridge';

export interface ConformanceStateVar {
  name: string;
  class: string;
  defaultValue: string;
}

export interface ConformanceStateHandler {
  name: string;
  /** Kind 1: set one state var to a literal value. */
  set?: { var: string; value: string };
  /** Kind 3: count calls — each call adds 1 to the var ("0" → "1" → "2"). */
  count?: { var: string };
  /**
   * Kind 2: drive an isolated embed's private stack through the
   * EmbedNavigatorRegistry (template v2 `getEmbedNavigator`). Exclusive
   * with `set`. `action` is "push" | "pop" (typed as string because the
   * generated registry inlines manifest JSON verbatim); unknown actions
   * are no-ops.
   */
  embed?: { id: string; action: string; screen?: string; params?: Record<string, unknown> };
}

/**
 * A change the host makes ONCE, itself, after the fixture's first draw
 * (INTERACTIVE_HOST_CONTRACT.md "afterFirstDraw"): for a visual fixture whose
 * subject is a reaction to a change — a scrollTo request is a change of the
 * value, never the value a list is drawn with.
 */
export interface ConformanceAfterFirstDraw {
  name: string;
  set: { var: string; value: string };
}

export interface ConformanceState {
  vars: ConformanceStateVar[];
  handlers: ConformanceStateHandler[];
  afterFirstDraw?: ConformanceAfterFirstDraw;
}

/**
 * What the host stamped for the runner (scripts/run.ts reads it and writes it
 * into the result entry): when the change was made and when the first frame
 * drawn with it was painted, in ms after the fixture's first paint.
 */
export interface AfterFirstDrawStamp {
  name: string;
  firedAtMs: number | null;
  appliedAtMs: number | null;
}

declare global {
  interface Window {
    __conformanceAfterFirstDraw?: AfterFirstDrawStamp;
  }
}

/** Resolves after the next painted frame (two animation frames). */
function afterPaint(callback: () => void): () => void {
  let second = 0;
  const first = requestAnimationFrame(() => {
    second = requestAnimationFrame(callback);
  });
  return () => {
    cancelAnimationFrame(first);
    cancelAnimationFrame(second);
  };
}

type DataDict = Record<string, unknown>;

/** The generated Data module's test functions, over the host's untyped store. */
export type BridgeSnapshot = (data: DataDict) => Record<string, unknown>;
export type BridgeApply = (values: Record<string, unknown>) => JsonUITestApplyResult<DataDict>;

/**
 * testBridge (INTERACTIVE_HOST_CONTRACT.md §6): the fixture's screen id and
 * the testSnapshot / applyTestInitialState functions rjui wrote into its Data
 * model. The bridge itself is rjui's generated useJsonUITestBridge — the
 * receiving side and the bridge a consumer's generated hook carries.
 */
export interface TestBridgeBinding {
  screenId: string;
  snapshot: BridgeSnapshot;
  apply: BridgeApply;
}

function TestBridgeTap({
  bridge,
  data,
  setData,
}: {
  bridge: TestBridgeBinding;
  data: DataDict;
  setData: React.Dispatch<React.SetStateAction<DataDict>>;
}): null {
  useJsonUITestBridge(
    bridge.screenId,
    data,
    (vars: Partial<DataDict>) => setData((prev) => ({ ...prev, ...vars })),
    bridge.snapshot,
    bridge.apply
  );
  return null;
}

const TWOWAY_KEY = /^on([A-Z].*)Change$/;

export function StateHost({
  createData,
  state,
  Component,
  bridge,
}: {
  createData: () => DataDict;
  state: ConformanceState;
  Component: React.ComponentType<{ data: DataDict }>;
  bridge?: TestBridgeBinding;
}): React.JSX.Element {
  const [data, setData] = useState<DataDict>(() => createData());

  // afterFirstDraw: once the first draw has been painted, set the var to the
  // literal; once a frame drawn WITH that value has been painted, stamp it.
  const afterFirstDraw = state.afterFirstDraw;
  const firstPaint = useRef<number | null>(null);
  useEffect(() => {
    if (!afterFirstDraw) return;
    window.__conformanceAfterFirstDraw = { name: afterFirstDraw.name, firedAtMs: null, appliedAtMs: null };
    return afterPaint(() => {
      firstPaint.current = performance.now();
      const { var: varName, value } = afterFirstDraw.set;
      setData((prev) => ({ ...prev, [varName]: value }));
      window.__conformanceAfterFirstDraw = { name: afterFirstDraw.name, firedAtMs: 0, appliedAtMs: null };
    });
  }, [afterFirstDraw]);
  useEffect(() => {
    const stamp = window.__conformanceAfterFirstDraw;
    if (!afterFirstDraw || !stamp || stamp.firedAtMs === null || stamp.appliedAtMs !== null) return;
    if (data[afterFirstDraw.set.var] !== afterFirstDraw.set.value) return;
    return afterPaint(() => {
      const start = firstPaint.current ?? performance.now();
      window.__conformanceAfterFirstDraw = { ...stamp, appliedAtMs: Math.round(performance.now() - start) };
    });
  }, [afterFirstDraw, data]);

  const merged = useMemo(() => {
    const out: DataDict = { ...data };

    // Declared handlers: set one var to a literal (payload ignored), or
    // drive an isolated embed's stack via the navigator registry.
    for (const handler of state.handlers) {
      if (handler.embed) {
        const embedOp = handler.embed;
        out[handler.name] = () => {
          const navigator = getEmbedNavigator(embedOp.id);
          if (!navigator) return;
          if (embedOp.action === 'push' && embedOp.screen) {
            navigator.push(embedOp.screen, embedOp.params ?? {});
          } else if (embedOp.action === 'pop') {
            navigator.pop();
          }
        };
        continue;
      }
      if (handler.count) {
        const countVar = handler.count.var;
        out[handler.name] = () =>
          setData((prev) => ({ ...prev, [countVar]: String((parseInt(String(prev[countVar] ?? '0'), 10) || 0) + 1) }));
        continue;
      }
      if (!handler.set) continue;
      const { var: varName, value } = handler.set;
      out[handler.name] = () => setData((prev) => ({ ...prev, [varName]: value }));
    }

    // Default two-way write-back for bound inputs (hook_generator semantics).
    for (const key of Object.keys(out)) {
      if (out[key] !== undefined) continue;
      const match = TWOWAY_KEY.exec(key);
      if (!match) continue;
      const prop = match[1].charAt(0).toLowerCase() + match[1].slice(1);
      if (!(prop in out)) continue;
      out[key] = (value: unknown) => setData((prev) => ({ ...prev, [prop]: value }));
    }

    return out;
  }, [data, state]);

  return (
    <>
      {bridge ? <TestBridgeTap bridge={bridge} data={data} setData={setData} /> : null}
      <Component data={merged} />
    </>
  );
}
