"""Generate web (vitest) unit tests from spec branchContracts.

P2 of the branch-declarations track (docs/plans/2026-08-24-branch-
declarations-p2-design.md). The generator is deliberately mechanical:

  arrange = baseline -> named-condition witnesses -> when.data (later wins)
            + fetch stub serving named mock scenarios per declared endpoint
  act     = await vm.<method>(args from when.arg via spec param order)
            + settle() to drain fire-and-forget fetches
  assert  = the branch's `then` entries, nothing more

Everything between the spec and the emitted test is declared vocabulary:
`api.<op>` resolves through dataFlow method `endpoint` declarations to a
mock file (tests/mocks/**/*.mock.json, matched on source.method + path)
and a named scenario. Unresolvable references are HARD generation errors —
a test that cannot bind its vocabulary must not silently weaken
(feasibility kill criteria: no ritual tests).

The consumer owns one hand-written harness module per screen (VM
construction, data store, router recorder, screenRoutes, resolveString).
A skeleton is emitted only when the file does not exist.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


class BranchTestGenerationError(Exception):
    """Raised for vocabulary that cannot be bound to real assets."""


# ---------------------------------------------------------------------------
# Spec / mock loading
# ---------------------------------------------------------------------------

def load_project_config(project_root: Path) -> dict:
    for name in ("jui.config.json", "jsonui-test.config.json"):
        p = project_root / name
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
    return {}


def resolve_spec_path(screen: str, project_root: Path, explicit: str | None) -> Path:
    if explicit:
        return (project_root / explicit).resolve() if not Path(explicit).is_absolute() else Path(explicit)
    config = load_project_config(project_root)
    spec_dir = config.get("spec_directory")
    if not spec_dir:
        raise BranchTestGenerationError(
            "spec_directory is not declared in jui.config.json and --spec was not given"
        )
    return (project_root / spec_dir / f"{screen}.spec.json").resolve()


def collect_endpoint_ops(spec: dict) -> dict[str, dict]:
    """op name -> {"method": "POST", "path": "/api/..."} from dataFlow
    repositories/useCases methods that declare `endpoint`."""
    ops: dict[str, dict] = {}
    data_flow = spec.get("dataFlow") or {}
    for section in ("repositories", "useCases"):
        for entry in data_flow.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            for method in entry.get("methods", []) or []:
                if not isinstance(method, dict):
                    continue
                name = method.get("name")
                endpoint = method.get("endpoint")
                if not (isinstance(name, str) and isinstance(endpoint, str)):
                    continue
                m = re.match(r"^([A-Z]+)\s+(\S+)$", endpoint.strip())
                if not m:
                    continue
                ops[name] = {"method": m.group(1), "path": m.group(2)}
    return ops


def path_to_pattern(path: str) -> str:
    """Swagger-style path -> anchored regex source ({param} -> one segment)."""
    parts = re.split(r"(\{[^}]+\})", path)
    out = ""
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            out += "[^/]+"
        else:
            out += re.escape(part)
    return f"^{out}$"


@dataclass
class MockFile:
    file: Path
    method: str
    path: str
    active_scenario: str
    scenarios: dict


def index_mock_files(mocks_dir: Path) -> list[MockFile]:
    mocks: list[MockFile] = []
    if not mocks_dir.is_dir():
        return mocks
    for f in sorted(mocks_dir.rglob("*.mock.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        source = data.get("source") or {}
        method = source.get("method")
        path = source.get("path")
        scenarios = data.get("scenarios")
        if not (isinstance(method, str) and isinstance(path, str)
                and isinstance(scenarios, dict) and scenarios):
            continue
        active = data.get("activeScenario")
        if not (isinstance(active, str) and active in scenarios):
            active = next(iter(scenarios))
        mocks.append(MockFile(file=f, method=method.upper(), path=path,
                              active_scenario=active, scenarios=scenarios))
    return mocks


def find_mock(mocks: list[MockFile], method: str, path: str) -> MockFile | None:
    for m in mocks:
        if m.method == method.upper() and m.path == path:
            return m
    return None


# ---------------------------------------------------------------------------
# Contract model
# ---------------------------------------------------------------------------

@dataclass
class Route:
    op: str
    method: str
    path: str
    pattern: str
    scenarios: dict
    default_scenario: str


@dataclass
class GenerationReport:
    screen: str
    test_file: Path | None = None
    runtime_file: Path | None = None
    harness_file: Path | None = None
    harness_created: bool = False
    declared_branches: int = 0
    note_branches: int = 0
    methods: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)


def _iter_declared_api_refs(contract: dict):
    """Yield (op, scenario_or_None, where) for every api.* reference."""
    for i, branch in enumerate(contract.get("branches") or []):
        if not isinstance(branch, dict) or "note" in branch:
            continue
        for key, value in (branch.get("when") or {}).items():
            if key.startswith("api."):
                yield key[len("api."):], value, f"branches[{i}].when.{key}"
        for key, _value in (branch.get("then") or {}).items():
            if key == "api" or not key.startswith("api."):
                continue
            rest = key[len("api."):]
            op = rest[: -len(".request")] if rest.endswith(".request") else rest
            yield op, None, f"branches[{i}].then.{key}"


def resolve_routes(
    spec: dict, methods_contracts: dict, mocks: list[MockFile]
) -> list[Route]:
    """Bind every referenced api.<op> (plus every declared endpoint with a
    mock, so incidental calls get their default scenario) to a Route.

    Unbindable references raise — a branch whose scenario cannot be found
    must fail generation, not soften into a weaker test.
    """
    ops = collect_endpoint_ops(spec)
    routes: dict[str, Route] = {}

    def bind(op: str, where: str) -> Route:
        if op in routes:
            return routes[op]
        if op not in ops:
            raise BranchTestGenerationError(
                f"{where}: api operation '{op}' has no `endpoint` declaration in "
                "dataFlow.repositories/useCases — declare the method with its "
                "endpoint (e.g. \"endpoint\": \"POST /api/...\")"
            )
        endpoint = ops[op]
        mock = find_mock(mocks, endpoint["method"], endpoint["path"])
        if mock is None:
            raise BranchTestGenerationError(
                f"{where}: no mock file found for {endpoint['method']} "
                f"{endpoint['path']} (op '{op}') under the mocks directory"
            )
        route = Route(
            op=op, method=endpoint["method"], path=endpoint["path"],
            pattern=path_to_pattern(endpoint["path"]),
            scenarios=mock.scenarios, default_scenario=mock.active_scenario,
        )
        routes[op] = route
        return route

    for contract in methods_contracts.values():
        if not isinstance(contract, dict):
            continue
        for op, scenario, where in _iter_declared_api_refs(contract):
            route = bind(op, where)
            if scenario is not None and scenario not in route.scenarios:
                raise BranchTestGenerationError(
                    f"{where}: scenario '{scenario}' not found in "
                    f"{sorted(route.scenarios)} (mock for {route.method} {route.path})"
                )

    # Every other declared endpoint that has a mock file joins with its
    # default scenario, so incidental calls during act don't 599.
    for op, endpoint in ops.items():
        if op in routes:
            continue
        mock = find_mock(mocks, endpoint["method"], endpoint["path"])
        if mock is not None:
            routes[op] = Route(
                op=op, method=endpoint["method"], path=endpoint["path"],
                pattern=path_to_pattern(endpoint["path"]),
                scenarios=mock.scenarios, default_scenario=mock.active_scenario,
            )
    return list(routes.values())


def method_params(spec: dict, method_name: str) -> list[str]:
    view_model = (spec.get("dataFlow") or {}).get("viewModel") or {}
    for method in view_model.get("methods", []) or []:
        if isinstance(method, dict) and method.get("name") == method_name:
            params = method.get("params")
            if isinstance(params, list):
                return [p.get("name") for p in params
                        if isinstance(p, dict) and isinstance(p.get("name"), str)]
            return []
    return []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _ts(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _arrange_state(contract: dict, branch: dict, conditions: dict) -> dict:
    """baseline -> cond witnesses -> when.data (later wins)."""
    state: dict = {}
    baseline = contract.get("baseline")
    if isinstance(baseline, dict):
        state.update(baseline)
    when = branch.get("when") or {}
    cond_ref = when.get("cond")
    if isinstance(cond_ref, str) and cond_ref:
        negated = cond_ref.startswith("!")
        name = cond_ref[1:] if negated else cond_ref
        cond = conditions.get(name) or {}
        witness = cond.get("witness_false" if negated else "witness_true")
        if not isinstance(witness, dict):
            raise BranchTestGenerationError(
                f"condition '{name}' has no "
                f"{'witness_false' if negated else 'witness_true'} — test "
                "generation needs a witness to arrange the state"
            )
        state.update(witness)
    for key, value in when.items():
        if key.startswith("data."):
            state[key[len("data."):]] = value
    return state


def _branch_title(index: int, branch: dict) -> str:
    when = branch.get("when") or {}
    parts = []
    for key, value in when.items():
        parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    return f"branch {index}: " + (" & ".join(parts) if parts else "(empty when)")


def render_test_file(
    screen: str, spec: dict, routes: list[Route], harness_import: str,
) -> tuple[str, GenerationReport]:
    bc = spec.get("branchContracts") or {}
    conditions = bc.get("conditions") or {}
    methods_contracts = bc.get("methods") or {}
    report = GenerationReport(screen=screen)
    report.routes = [r.op for r in routes]

    route_specs = ",\n".join(
        "  { op: %s, method: %s, pattern: %s, scenario: %s,\n    scenarios: %s }"
        % (_ts(r.op), _ts(r.method), _ts(r.pattern), _ts(r.default_scenario),
           _ts(r.scenarios))
        for r in routes
    )

    lines: list[str] = []
    lines.append("// @generated by `jsonui-test generate branch-tests %s` — DO NOT EDIT." % screen)
    lines.append("// Source of truth: the screen spec's branchContracts section.")
    lines.append("// Regenerate after editing the spec; edit the harness (consumer-owned)")
    lines.append("// for VM construction, screenRoutes, and string resolution.")
    lines.append("import { describe, expect, it } from \"vitest\";")
    lines.append("import {")
    lines.append("  installFetchMock, partialMismatches, settle, type RouteSpec,")
    lines.append("} from \"./jsonui-branch-runtime\";")
    lines.append(f"import {{ createHarness }} from \"{harness_import}\";")
    lines.append("")
    lines.append("const ROUTES: RouteSpec[] = [")
    lines.append(route_specs)
    lines.append("];")
    lines.append("")

    for method_name, contract in methods_contracts.items():
        if not isinstance(contract, dict):
            continue
        report.methods.append(method_name)
        params = method_params(spec, method_name)
        branches = contract.get("branches") or []
        notes = [(i + 1, b["note"]) for i, b in enumerate(branches)
                 if isinstance(b, dict) and "note" in b]
        report.note_branches += len(notes)

        lines.append(f"describe({_ts(screen + '.' + method_name)}, () => {{")
        if notes:
            lines.append("  // %d note-only branch(es) — declared outside the machine-checkable" % len(notes))
            lines.append("  // contract in the spec; listed here so coverage boundaries stay visible:")
            for num, note in notes:
                lines.append(f"  //   #{num}: {note}")
        for i, branch in enumerate(branches):
            if not isinstance(branch, dict) or "note" in branch:
                continue
            report.declared_branches += 1
            lines.extend(_render_branch(
                method_name, params, contract, branch, i + 1, conditions))
        lines.append("});")
        lines.append("")

    return "\n".join(lines), report


def _render_branch(
    method_name: str, params: list[str], contract: dict, branch: dict,
    number: int, conditions: dict,
) -> list[str]:
    when = branch.get("when") or {}
    then = branch.get("then") or {}
    state = _arrange_state(contract, branch, conditions)
    overrides = {k[len("api."):]: v for k, v in when.items() if k.startswith("api.")}
    args = []
    arg_values = {k[len("arg."):]: v for k, v in when.items() if k.startswith("arg.")}
    for p in params:
        args.append(_ts(arg_values.get(p)) if p in arg_values else "undefined")
    while args and args[-1] == "undefined":
        args.pop()

    # '@data.<field>' references are captured AFTER arrange, BEFORE act.
    data_refs: list[str] = []

    def register_ref(value):
        if isinstance(value, str) and value.startswith("@data."):
            fname = value[len("@data."):]
            if fname not in data_refs:
                data_refs.append(fname)

    def collect_refs(node):
        if isinstance(node, dict):
            for v in node.values():
                collect_refs(v)
        else:
            register_ref(node)

    for key, value in then.items():
        if key.startswith("data."):
            register_ref(value)
        elif key.startswith("api.") and key.endswith(".request"):
            collect_refs(value)

    out: list[str] = []
    title = _branch_title(number, branch)
    out.append(f"  it({_ts(title)}, async () => {{")
    out.append("    const h = createHarness();")
    if state:
        out.append(f"    h.setState({_ts(state)});")
    if overrides:
        out.append(f"    const rec = installFetchMock(ROUTES, {_ts(overrides)});")
    else:
        out.append("    const rec = installFetchMock(ROUTES);")
    for fname in data_refs:
        out.append(f"    const ref_{fname} = h.readField({_ts(fname)});")
    out.append("    try {")
    call_args = ", ".join(args)
    out.append(f"      await (h.vm as any).{method_name}({call_args});")
    out.append("      await settle();")

    for key, value in then.items():
        if key == "api":
            out.append("      expect(rec.calls).toEqual([]);")
        elif key == "transition":
            out.append(
                f"      h.expectTransition({_ts(value)});"
            )
        elif key.startswith("api.") and key.endswith(".request"):
            op = key[len("api."):-len(".request")]
            out.append(
                f"      expect(rec.countFor({_ts(op)})).toBeGreaterThan(0);"
            )
            out.append(
                f"      expect(partialMismatches(rec.lastBodyFor({_ts(op)}), "
                f"{_render_expected(value)})).toEqual([]);"
            )
        elif key.startswith("api."):
            op = key[len("api."):]
            if value == "called":
                out.append(f"      expect(rec.countFor({_ts(op)})).toBeGreaterThan(0);")
            else:
                out.append(f"      expect(rec.countFor({_ts(op)})).toBe(0);")
        elif key.startswith("data."):
            fname = key[len("data."):]
            out.append(
                f"      expect(h.readField({_ts(fname)})).toEqual("
                f"{_render_expected(value)});"
            )
    out.append("    } finally {")
    out.append("      rec.restore();")
    out.append("    }")
    out.append("  });")
    return out


def _render_expected(value) -> str:
    """Expected-value expression: literals stay literal, '@data.<f>' becomes
    the pre-act capture, '@key' resolves through the harness."""
    if isinstance(value, str) and value.startswith("@data."):
        return f"ref_{value[len('@data.'):]}"
    if isinstance(value, str) and value.startswith("@"):
        return f"h.resolveString({_ts(value[1:])})"
    if isinstance(value, dict):
        entries = ", ".join(
            f"{_ts(k)}: {_render_expected(v)}" for k, v in value.items()
        )
        return "{ " + entries + " }"
    return _ts(value)


RUNTIME_TS = '''// @generated by `jsonui-test generate branch-tests` — DO NOT EDIT.
// Shared runtime for branch-contract tests: fetch stubbing with named mock
// scenarios, request recording, partial matching, and macrotask settling.

export interface RouteSpec {
  op: string;
  method: string;
  pattern: string;
  scenario: string;
  scenarios: Record<string, { status: number; body: unknown }>;
}

export interface RecordedCall {
  op: string;
  method: string;
  path: string;
  body: unknown;
}

export interface FetchRecorder {
  calls: RecordedCall[];
  countFor(op: string): number;
  lastBodyFor(op: string): unknown;
  restore(): void;
}

/** Stub globalThis.fetch: serve each route's (possibly overridden) named
 * scenario and record request bodies. Unmatched paths get an unmistakable
 * 599 so incidental un-declared calls surface instead of hanging. */
export function installFetchMock(
  routes: RouteSpec[],
  scenarioOverrides: Record<string, string> = {}
): FetchRecorder {
  const original = globalThis.fetch;
  const calls: RecordedCall[] = [];
  const compiled = routes.map((r) => ({ ...r, re: new RegExp(r.pattern) }));

  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url;
    const path = url.replace(/^https?:\\/\\/[^/]+/, "").split("?")[0];
    const method = (
      init?.method ??
      (typeof input === "object" && input !== null && "method" in (input as object)
        ? (input as Request).method
        : "GET")
    ).toUpperCase();

    for (const r of compiled) {
      if (r.method === method && r.re.test(path)) {
        let body: unknown;
        if (init?.body !== undefined) {
          try {
            body = JSON.parse(init.body as string);
          } catch {
            body = init.body;
          }
        }
        calls.push({ op: r.op, method, path, body });
        const name = scenarioOverrides[r.op] ?? r.scenario;
        const sc = r.scenarios[name];
        if (!sc) {
          throw new Error(
            `branch-runtime: scenario '${name}' missing for op '${r.op}'`
          );
        }
        return new Response(JSON.stringify(sc.body), {
          status: sc.status,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    calls.push({ op: "(unmatched)", method, path, body: undefined });
    return new Response(
      JSON.stringify({
        error: { code: "unmocked_endpoint", message: `${method} ${path}` },
      }),
      { status: 599, headers: { "Content-Type": "application/json" } }
    );
  }) as typeof fetch;

  return {
    calls,
    countFor(op: string) {
      return calls.filter((c) => c.op === op).length;
    },
    lastBodyFor(op: string) {
      const m = calls.filter((c) => c.op === op);
      return m.length ? m[m.length - 1].body : undefined;
    },
    restore() {
      globalThis.fetch = original;
    },
  };
}

/** Recursive partial match. Returns human-readable mismatch strings
 * (empty array = match). `null` expectations also accept absent keys —
 * JSON.stringify drops `undefined`, so a request that omits a field IS
 * the declared "null" outcome. */
export function partialMismatches(
  actual: unknown,
  expected: unknown,
  prefix = ""
): string[] {
  const label = prefix || "$";
  if (expected !== null && typeof expected === "object" && !Array.isArray(expected)) {
    if (actual === null || typeof actual !== "object" || Array.isArray(actual)) {
      return [`${label}: expected object, got ${JSON.stringify(actual)}`];
    }
    const out: string[] = [];
    for (const [k, v] of Object.entries(expected as Record<string, unknown>)) {
      out.push(
        ...partialMismatches(
          (actual as Record<string, unknown>)[k],
          v,
          prefix ? `${prefix}.${k}` : k
        )
      );
    }
    return out;
  }
  if (expected === null) {
    return actual === null || actual === undefined
      ? []
      : [`${label}: expected null/absent, got ${JSON.stringify(actual)}`];
  }
  return Object.is(actual, expected)
    ? []
    : [`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
}

/** Drain queued macrotasks so fire-and-forget promise chains that only
 * await already-resolved mock responses reach their terminal state. */
export async function settle(turns = 10): Promise<void> {
  for (let i = 0; i < turns; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}
'''


HARNESS_SKELETON = '''// Branch-contract test harness for `%(screen)s` — CONSUMER-OWNED.
// Generated once as a skeleton by `jsonui-test generate branch-tests`;
// edit freely, it will not be overwritten.

export interface BranchHarness {
  vm: unknown;
  /** VM field first, then the data store — the `data.*` read surface. */
  readField(name: string): unknown;
  /** Apply a witness/baseline object onto the VM + data store. */
  setState(state: Record<string, unknown>): void;
  /** Assert a `then.transition` destination against recorded navigation. */
  expectTransition(destination: string): void;
  /** Resolve an '@strings_key' expectation. */
  resolveString(key: string): string;
}

export function createHarness(): BranchHarness {
  // TODO: construct the ViewModel with a router recorder and a data store,
  // declare screenRoutes for every transition destination the contract
  // uses, and wire resolveString to the project's StringManager.
  throw new Error("branch-harness for %(screen)s is not implemented yet");
}
'''


def generate_branch_tests(
    screen: str,
    project_root: Path,
    spec_path: str | None = None,
    out_dir: str = "tests/unit/generated",
    harness_dir: str = "tests/unit/branch-harness",
    mocks_dir: str = "tests/mocks",
) -> GenerationReport:
    spec_file = resolve_spec_path(screen, project_root, spec_path)
    if not spec_file.exists():
        raise BranchTestGenerationError(f"spec not found: {spec_file}")
    with open(spec_file, "r", encoding="utf-8") as f:
        spec = json.load(f)

    bc = spec.get("branchContracts")
    if not isinstance(bc, dict) or not bc.get("methods"):
        raise BranchTestGenerationError(
            f"{spec_file.name} declares no branchContracts.methods — nothing to generate"
        )

    mocks = index_mock_files(project_root / mocks_dir)
    routes = resolve_routes(spec, bc["methods"], mocks)

    out_path = project_root / out_dir
    out_path.mkdir(parents=True, exist_ok=True)
    harness_path = project_root / harness_dir
    harness_path.mkdir(parents=True, exist_ok=True)

    rel = _relative_import(out_path, harness_path / screen)
    content, report = render_test_file(screen, spec, routes, rel)

    runtime_file = out_path / "jsonui-branch-runtime.ts"
    runtime_file.write_text(RUNTIME_TS, encoding="utf-8")
    test_file = out_path / f"{screen}.branches.test.ts"
    test_file.write_text(content + "\n", encoding="utf-8")

    harness_file = harness_path / f"{screen}.ts"
    created = False
    if not harness_file.exists():
        harness_file.write_text(HARNESS_SKELETON % {"screen": screen}, encoding="utf-8")
        created = True

    report.test_file = test_file
    report.runtime_file = runtime_file
    report.harness_file = harness_file
    report.harness_created = created
    return report


def _relative_import(from_dir: Path, to_module: Path) -> str:
    import os
    rel = os.path.relpath(to_module, from_dir)
    rel = rel.replace("\\", "/")
    if not rel.startswith("."):
        rel = "./" + rel
    return rel
