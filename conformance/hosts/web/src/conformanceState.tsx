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
import React, { useMemo, useState } from 'react';

export interface ConformanceStateVar {
  name: string;
  class: string;
  defaultValue: string;
}

export interface ConformanceStateHandler {
  name: string;
  set: { var: string; value: string };
}

export interface ConformanceState {
  vars: ConformanceStateVar[];
  handlers: ConformanceStateHandler[];
}

type DataDict = Record<string, unknown>;

const TWOWAY_KEY = /^on([A-Z].*)Change$/;

export function StateHost({
  createData,
  state,
  Component,
}: {
  createData: () => DataDict;
  state: ConformanceState;
  Component: React.ComponentType<{ data: DataDict }>;
}): React.JSX.Element {
  const [data, setData] = useState<DataDict>(() => createData());

  const merged = useMemo(() => {
    const out: DataDict = { ...data };

    // Declared handlers: set one var to a literal (payload ignored).
    for (const handler of state.handlers) {
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

  return <Component data={merged} />;
}
