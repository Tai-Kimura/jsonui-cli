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
    platform_skipped: int = 0
    methods: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)


def _branch_active(branch: dict, platform: str) -> bool:
    """Platform-scoped branches (branch['platforms']) render only on their
    listed platforms; unscoped branches render everywhere."""
    platforms = branch.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        return True
    return platform in platforms


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


def _mocks_dir_label(mocks_dir: Path | None) -> str:
    """Absolute path when known — "the mocks directory" told an author the
    file was missing when it existed somewhere the search never looked."""
    if mocks_dir is None:
        return "the mocks directory"
    return str(mocks_dir)


def resolve_routes(
    spec: dict, methods_contracts: dict, mocks: list[MockFile],
    mocks_dir: Path | None = None,
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
                f"{endpoint['path']} (op '{op}') — searched "
                f"{_mocks_dir_label(mocks_dir)} and found "
                f"{len(mocks)} mock file(s)"
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


RESPONSE_REF_PREFIX = "@response."


def resolve_response_refs(methods_contracts: dict, routes: list[Route]) -> None:
    """Replace `@response.<path>` in `then` with the value the branch's own
    scenario actually returns, in place.

    Some screens display a string the server chose — an API error message
    passed through to an alert. The contract cannot spell it as a literal
    (it is not ours) nor as a strings key (it is not in the table), so those
    branches were being written as prose notes and going untested. What the
    contract *can* say is "this field shows what the server sent", and since
    the branch already names the scenario, the expected text is knowable
    here: read it out of the mock and hand the renderers a literal.

    Resolution failures raise. A reference that cannot be bound is a broken
    declaration, and quietly asserting something weaker would leave the
    branch looking covered.
    """
    by_op = {route.op: route for route in routes}

    for method_name, contract in methods_contracts.items():
        if not isinstance(contract, dict):
            continue
        for i, branch in enumerate(contract.get("branches") or []):
            if not isinstance(branch, dict) or "note" in branch:
                continue
            then = branch.get("then")
            if not isinstance(then, dict):
                continue
            refs = [
                (k, v) for k, v in then.items()
                if isinstance(v, str) and v.startswith(RESPONSE_REF_PREFIX)
            ]
            if not refs:
                continue
            where = f"methods.{method_name}.branches[{i}]"
            scenarios = {
                k[len("api."):]: v
                for k, v in (branch.get("when") or {}).items()
                if k.startswith("api.") and isinstance(v, str)
            }
            if len(scenarios) != 1:
                raise BranchTestGenerationError(
                    f"{where}: '@response.<path>' needs exactly one "
                    f"`api.<op>` in `when` to read the response from, found "
                    f"{len(scenarios)}"
                )
            op, scenario_name = next(iter(scenarios.items()))
            route = by_op.get(op)
            if route is None:
                raise BranchTestGenerationError(
                    f"{where}: no route bound for api operation '{op}'"
                )
            scenario = route.scenarios.get(scenario_name)
            if not isinstance(scenario, dict):
                raise BranchTestGenerationError(
                    f"{where}: scenario '{scenario_name}' of '{op}' is not an "
                    "object, so it has no response body to read"
                )
            body = scenario.get("body")
            for key, ref in refs:
                path = ref[len(RESPONSE_REF_PREFIX):]
                then[key] = _read_response_path(body, path, where, key, scenario_name)


def _read_response_path(body, path: str, where: str, key: str, scenario: str):
    if not path:
        raise BranchTestGenerationError(
            f"{where}.then.{key}: '@response.' needs a field path "
            "(e.g. '@response.error.message')"
        )
    node = body
    walked: list[str] = []
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            available = (
                ", ".join(sorted(node)) if isinstance(node, dict) else "(not an object)"
            )
            at = ".".join(walked) or "(root)"
            raise BranchTestGenerationError(
                f"{where}.then.{key}: scenario '{scenario}' has no "
                f"'{path}' in its response body — at {at} the available "
                f"keys are: {available}"
            )
        node = node[part]
        walked.append(part)
    if isinstance(node, (dict, list)):
        raise BranchTestGenerationError(
            f"{where}.then.{key}: '{path}' in scenario '{scenario}' is a "
            f"{type(node).__name__}, and a displayed value must be a scalar"
        )
    return node


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


def _method_is_declared(spec: dict, method_name: str) -> bool:
    view_model = (spec.get("dataFlow") or {}).get("viewModel") or {}
    for method in view_model.get("methods", []) or []:
        if isinstance(method, dict) and method.get("name") == method_name:
            return True
        if isinstance(method, str) and method.split("(")[0].strip() == method_name:
            return True
    return False


def check_arg_bindings(spec: dict, methods_contracts: dict) -> None:
    """Every `arg.<name>` has to name a declared parameter.

    The act call is built from `dataFlow.viewModel.methods[].params`, so an
    `arg` that matches nothing there used to be dropped on the floor: the
    method was invoked with no arguments and the branch passed or failed for
    reasons unrelated to what it declared. A harness with a closed switch
    notices (it receives nil); a lenient one substitutes a default and stays
    green while testing a different case than the contract describes.

    eventHandlers are not an alternative declaration site. They are
    View-layer handlers by design and carry no signature, which is why
    adding params there changes nothing — a method whose arguments a
    contract wants to pin belongs in the ViewModel's public API.
    """
    for method_name, contract in methods_contracts.items():
        if not isinstance(contract, dict):
            continue
        params = set(method_params(spec, method_name))
        declared = _method_is_declared(spec, method_name)
        for i, branch in enumerate(contract.get("branches") or []):
            if not isinstance(branch, dict) or "note" in branch:
                continue
            for key in (branch.get("when") or {}):
                if not key.startswith("arg."):
                    continue
                name = key[len("arg."):]
                if name in params:
                    continue
                where = f"methods.{method_name}.branches[{i}].when.{key}"
                if not declared:
                    raise BranchTestGenerationError(
                        f"{where}: '{method_name}' is not declared in "
                        "dataFlow.viewModel.methods, so it has no parameter "
                        "list to bind this argument to — declare it there "
                        "with `params` (stateManagement.eventHandlers is "
                        "View-layer only and carries no signature)"
                    )
                raise BranchTestGenerationError(
                    f"{where}: '{method_name}' declares no parameter "
                    f"'{name}' — its params are "
                    f"{sorted(params) if params else '(none)'}"
                )


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
            if not _branch_active(branch, "web"):
                report.platform_skipped += 1
                lines.append(
                    f"  // branch {i + 1} is platform-scoped "
                    f"({branch.get('platforms')}) — not generated for web")
                continue
            report.declared_branches += 1
            lines.extend(_render_branch(
                method_name, params, contract, branch, i + 1, conditions))
        lines.append("});")
        lines.append("")

    return "\n".join(lines), report


def _collect_data_refs(then: dict) -> list[str]:
    """'@data.<field>' references in `then` — captured AFTER arrange,
    BEFORE act (shared by all platform renderers)."""
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
    return data_refs


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

    data_refs = _collect_data_refs(then)

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
            out.append("      expect(rec.matchedCalls()).toEqual([]);")
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
  /** Calls bound to a declared route — the `api: "none"` surface.
   * Unmatched traffic (third-party SDKs, undeclared endpoints) is still
   * recorded and served a 599 for diagnostics, but does not count. */
  matchedCalls(): RecordedCall[];
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
    matchedCalls() {
      return calls.filter((c) => c.op !== "(unmatched)");
    },
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

/** Write the state keys the ViewModel actually declares, and hand back the
 * rest for the data store.
 *
 * A plain assignment loop cannot be used here. JavaScript creates a
 * property on assignment, so arranging a data-only field (one the screen
 * updates through its data store and the ViewModel never declares) invents
 * that property on the ViewModel — and since readField consults the
 * ViewModel first, every later read returns the arranged value no matter
 * what the implementation did. The branch then fails against correct code,
 * which is the worst kind of failure to debug: the harness lies about the
 * subject.
 *
 * The failure only shows up once a baseline arranges the pre-state, so it
 * waits for exactly the contracts most worth writing ("… is cleared", "…
 * is closed"). */
export function applyDeclaredKeys(
  vm: object,
  state: Record<string, unknown>
): void {
  const target = vm as Record<string, unknown>;
  for (const [key, value] of Object.entries(state)) {
    if (key in target) {
      target[key] = value;
    }
  }
}
'''


HARNESS_SKELETON = '''// Branch-contract test harness for `%(screen)s` — CONSUMER-OWNED.
// Generated once as a skeleton by `jsonui-test generate branch-tests`;
// edit freely, it will not be overwritten.

/** Spec '@key' expectations — bare own-section key to FULL strings key.
 * Keep this a closed *_STRING_KEYS map (values are full keys) rather than
 * building keys with template interpolation: `jui lint-strings --usage`
 * counts map values into the used set, while a dynamic
 * getString(`%(screen)s_${key}`) call is flagged as dynamic and blocks
 * consumers running the usage gate (lint.stringsUsage: true). */
const %(screen_const)s_BRANCH_STRING_KEYS: Record<string, string> = {
  // "some_error": "%(screen)s_some_error",
};

/** `then.transition` destinations — screen name to URL pattern. Owned
 * here because route shapes are this app's concern, not the spec's. */
const SCREEN_ROUTES: Record<string, RegExp> = {
  // some_screen: /^\\/some\\/route$/,
};

export interface BranchHarness {
  vm: unknown;
  /** VM field first, then the data store — the `data.*` read surface. */
  readField(name: string): unknown;
  /** Apply a witness/baseline object onto the VM + data store.
   *
   * Write the ViewModel through `applyDeclaredKeys(vm, state)` from the
   * runtime rather than assigning in a loop, then hand the same object to
   * the data store. Assigning every key directly invents ViewModel
   * properties for data-only fields, and because readField consults the
   * ViewModel first, those invented properties then shadow the store for
   * the rest of the test — the branch fails against a correct
   * implementation. It surfaces the moment a baseline arranges a pre-state
   * ("visible" before asserting it closes), so it waits for exactly the
   * contracts most worth writing. */
  setState(state: Record<string, unknown>): void;
  /** Assert a `then.transition` destination against recorded navigation. */
  expectTransition(destination: string): void;
  /** Resolve an '@strings_key' expectation via the closed map above. */
  resolveString(key: string): string;
}

export function createHarness(): BranchHarness {
  // TODO: construct the ViewModel with a router recorder and a data store;
  // resolveString should look the key up in %(screen_const)s_BRANCH_STRING_KEYS
  // (throw on a missing entry — same contract as SCREEN_ROUTES) and pass the
  // full key to the project's StringManager.
  throw new Error("branch-harness for %(screen)s is not implemented yet");
}
'''


# ---------------------------------------------------------------------------
# Android (Kotlin / JVM) renderer — same contract model, different emission.
#
# Mocking stays at the HTTP boundary (MockWebServer): Retrofit ApiService,
# Repository implementations, and kotlinx-serialization DTO decoding all run
# REAL — the "2xx but the payload is wrong" class (silent response-field
# drops, swagger/implementation drift) is inside the net, not mocked away.
# ---------------------------------------------------------------------------

def _pascal(screen: str) -> str:
    return "".join(p.capitalize() for p in screen.split("_"))


def _kt_str(s: str) -> str:
    """Kotlin string literal ($ must not interpolate)."""
    out = json.dumps(s, ensure_ascii=False)
    return out.replace("$", "${'$'}")


def _kt(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return _kt_str(value)
    if isinstance(value, dict):
        entries = ", ".join(f"{_kt_str(str(k))} to {_kt(v)}" for k, v in value.items())
        return f"mapOf<String, Any?>({entries})"
    if isinstance(value, list):
        entries = ", ".join(_kt(v) for v in value)
        return f"listOf<Any?>({entries})"
    raise BranchTestGenerationError(f"cannot render value {value!r} as Kotlin")


def _kt_expected(value) -> str:
    """Expected-value expression for Kotlin asserts: '@data.<f>' becomes the
    pre-act capture wrapped in Ref(...), '@key' resolves via the harness."""
    if isinstance(value, str) and value.startswith("@data."):
        return f"Ref(ref_{value[len('@data.'):]})"
    if isinstance(value, str) and value.startswith("@"):
        return f"h.resolveString({_kt_str(value[1:])})"
    if isinstance(value, dict):
        entries = ", ".join(
            f"{_kt_str(str(k))} to {_kt_expected(v)}" for k, v in value.items()
        )
        return f"mapOf<String, Any?>({entries})"
    return _kt(value)


def render_kotlin_test_file(
    screen: str, spec: dict, routes: list[Route], package: str,
) -> tuple[str, GenerationReport]:
    bc = spec.get("branchContracts") or {}
    conditions = bc.get("conditions") or {}
    methods_contracts = bc.get("methods") or {}
    report = GenerationReport(screen=screen)
    report.routes = [r.op for r in routes]
    pascal = _pascal(screen)

    route_lines = []
    for r in routes:
        scen = ", ".join(
            f"{_kt_str(name)} to ({sc.get('status', 200)} to "
            f"{_kt_str(json.dumps(sc.get('body'), ensure_ascii=False))})"
            for name, sc in r.scenarios.items()
        )
        route_lines.append(
            f"  RouteSpec({_kt_str(r.op)}, {_kt_str(r.method)}, "
            f"Regex({_kt_str(r.pattern)}), {_kt_str(r.default_scenario)},\n"
            f"    mapOf({scen}))"
        )

    lines: list[str] = []
    lines.append(f"// @generated by `jsonui-test generate branch-tests {screen} --platform android` — DO NOT EDIT.")
    lines.append("// Source of truth: the screen spec's branchContracts section.")
    lines.append(f"package {package}")
    lines.append("")
    lines.append("import org.junit.Assert.assertEquals")
    lines.append("import org.junit.Assert.assertTrue")
    lines.append("import org.junit.Test")
    lines.append("import org.junit.runner.RunWith")
    lines.append("import org.robolectric.RobolectricTestRunner")
    lines.append("")
    lines.append(f"@RunWith(RobolectricTestRunner::class)")
    lines.append(f"class {pascal}BranchesTest {{")
    lines.append("")
    lines.append("  private val routes = listOf(")
    lines.append(",\n".join(route_lines))
    lines.append("  )")

    for method_name, contract in methods_contracts.items():
        if not isinstance(contract, dict):
            continue
        report.methods.append(method_name)
        params = method_params(spec, method_name)
        branches = contract.get("branches") or []
        notes = [(i + 1, b["note"]) for i, b in enumerate(branches)
                 if isinstance(b, dict) and "note" in b]
        report.note_branches += len(notes)
        lines.append("")
        lines.append(f"  // ===== {method_name} =====")
        if notes:
            lines.append("  // %d note-only branch(es) — outside the machine-checkable contract:" % len(notes))
            for num, note in notes:
                lines.append(f"  //   #{num}: {note}")
        for i, branch in enumerate(branches):
            if not isinstance(branch, dict) or "note" in branch:
                continue
            if not _branch_active(branch, "android"):
                report.platform_skipped += 1
                lines.append(
                    f"  // branch {i + 1} is platform-scoped "
                    f"({branch.get('platforms')}) — not generated for android")
                continue
            report.declared_branches += 1
            lines.extend(_render_kotlin_branch(
                pascal, method_name, params, contract, branch, i + 1, conditions))
    lines.append("}")
    return "\n".join(lines) + "\n", report


def _render_kotlin_branch(
    pascal: str, method_name: str, params: list[str], contract: dict,
    branch: dict, number: int, conditions: dict,
) -> list[str]:
    when = branch.get("when") or {}
    then = branch.get("then") or {}
    state = _arrange_state(contract, branch, conditions)
    overrides = {k[len("api."):]: v for k, v in when.items() if k.startswith("api.")}
    arg_values = {k[len("arg."):]: v for k, v in when.items() if k.startswith("arg.")}
    args = [
        _kt(arg_values.get(p)) if p in arg_values else "null"
        for p in params
    ]
    while args and args[-1] == "null":
        args.pop()
    data_refs = _collect_data_refs(then)

    out: list[str] = []
    out.append("")
    out.append(f"  // {_branch_title(number, branch)}")
    out.append(f"  @Test fun `{method_name} branch {number}`() {{")
    out.append(
        f"    runBranchTest(routes, {_kt({k: v for k, v in overrides.items()})}, "
        f"::create{pascal}BranchHarness) {{ h, rec ->"
    )
    if state:
        out.append(f"      h.setState({_kt(state)})")
    for fname in data_refs:
        out.append(f"      val ref_{fname} = h.readField({_kt_str(fname)})")
    call_args = ", ".join(args)
    out.append(f"      h.invoke({_kt_str(method_name)}{', ' + call_args if call_args else ''})")
    out.append("      h.settle()")
    for key, value in then.items():
        if key == "api":
            out.append("      assertTrue(\"expected no declared-API calls, got ${rec.matchedCalls()}\", rec.matchedCalls().isEmpty())")
        elif key == "transition":
            out.append(f"      h.expectTransition({_kt_str(value)})")
        elif key.startswith("api.") and key.endswith(".request"):
            op = key[len("api."):-len(".request")]
            out.append(f"      assertTrue(rec.countFor({_kt_str(op)}) > 0)")
            out.append(
                f"      assertEquals(emptyList<String>(), "
                f"partialMismatches(rec.lastBodyFor({_kt_str(op)}), {_kt_expected(value)}))"
            )
        elif key.startswith("api."):
            op = key[len("api."):]
            if value == "called":
                out.append(f"      assertTrue(rec.countFor({_kt_str(op)}) > 0)")
            else:
                out.append(f"      assertEquals(0, rec.countFor({_kt_str(op)}))")
        elif key.startswith("data."):
            fname = key[len("data."):]
            out.append(
                f"      assertFieldEquals({_kt_expected(value)}, "
                f"h.readField({_kt_str(fname)}))"
            )
    out.append("    }")
    out.append("  }")
    return out


def _relative_kotlin_paths(package: str) -> str:
    return package.replace(".", "/")


KOTLIN_RUNTIME = '''// @generated by `jsonui-test generate branch-tests --platform android` — DO NOT EDIT.
// Shared runtime for branch-contract tests: MockWebServer scenario serving,
// request recording, reflection-based state access, partial matching, and
// coroutine settling. HTTP is the ONLY mocked boundary — Retrofit services,
// Repository implementations, and DTO deserialization run real.
package %(package)s

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import java.lang.reflect.Field
import java.lang.reflect.Modifier
import kotlin.reflect.full.instanceParameter
import kotlin.reflect.full.memberFunctions
import kotlin.reflect.jvm.isAccessible

data class RouteSpec(
  val op: String,
  val method: String,
  val pattern: Regex,
  val defaultScenario: String,
  val scenarios: Map<String, Pair<Int, String>>,
)

data class RecordedCall(val op: String, val method: String, val path: String, val body: String?)

class Recorder {
  val calls = mutableListOf<RecordedCall>()
  /** Calls bound to a declared route — the `api: "none"` surface. */
  fun matchedCalls(): List<RecordedCall> = calls.filter { it.op != "(unmatched)" }
  fun countFor(op: String): Int = calls.count { it.op == op }
  fun lastBodyFor(op: String): JsonElement? =
    calls.lastOrNull { it.op == op }?.body?.let { Json.parseToJsonElement(it) }
}

/** '@data.<field>' pre-act capture marker for partial matching / asserts. */
data class Ref(val value: Any?)

interface BranchHarness {
  val vm: Any
  fun readField(name: String): Any?
  fun setState(state: Map<String, Any?>)
  fun invoke(name: String, vararg args: Any?)
  fun expectTransition(destination: String)
  fun resolveString(key: String): String
  fun settle()
}

@OptIn(ExperimentalCoroutinesApi::class)
fun runBranchTest(
  routes: List<RouteSpec>,
  scenarioOverrides: Map<String, Any?>,
  harnessFactory: (baseUrl: String, dispatcher: TestDispatcher) -> BranchHarness,
  block: (BranchHarness, Recorder) -> Unit,
) {
  val dispatcher = StandardTestDispatcher()
  Dispatchers.setMain(dispatcher)
  val recorder = Recorder()
  val server = MockWebServer()
  server.dispatcher = object : Dispatcher() {
    override fun dispatch(request: RecordedRequest): MockResponse {
      val path = (request.path ?: "/").substringBefore("?")
      val method = request.method ?: "GET"
      for (r in routes) {
        if (r.method == method && r.pattern.matches(path)) {
          recorder.calls.add(RecordedCall(r.op, method, path, request.body.readUtf8()))
          val name = (scenarioOverrides[r.op] as? String) ?: r.defaultScenario
          val sc = r.scenarios[name]
            ?: error("branch-runtime: scenario '" + name + "' missing for op '" + r.op + "'")
          return MockResponse()
            .setResponseCode(sc.first)
            .setHeader("Content-Type", "application/json")
            .setBody(sc.second)
        }
      }
      recorder.calls.add(RecordedCall("(unmatched)", method, path, null))
      return MockResponse().setResponseCode(599)
        .setHeader("Content-Type", "application/json")
        .setBody("{\\"error\\":{\\"code\\":\\"unmocked_endpoint\\"}}")
    }
  }
  server.start()
  try {
    block(harnessFactory(server.url("/").toString(), dispatcher), recorder)
  } finally {
    server.shutdown()
    Dispatchers.resetMain()
  }
}

/** Reflection base: readField / setState / invoke work on any VM whose state
 * lives in fields, StateFlows, or a `_data` MutableStateFlow<data class>. */
@OptIn(ExperimentalCoroutinesApi::class)
abstract class BaseBranchHarness(
  final override val vm: Any,
  private val dispatcher: TestDispatcher,
) : BranchHarness {

  override fun settle() {
    // Real HTTP I/O (MockWebServer + OkHttp threads) completes off the test
    // dispatcher; the coroutine then resumes ON it. Interleave virtual-time
    // draining with short real-time waits until the pipeline is quiet.
    repeat(60) {
      dispatcher.scheduler.advanceUntilIdle()
      Thread.sleep(5)
    }
    dispatcher.scheduler.advanceUntilIdle()
  }

  private fun findField(target: Any, name: String): Field? {
    var cls: Class<*>? = target.javaClass
    while (cls != null) {
      for (candidate in arrayOf(name, "_" + name)) {
        try {
          val f = cls.getDeclaredField(candidate)
          f.isAccessible = true
          return f
        } catch (_: NoSuchFieldException) {}
      }
      cls = cls.superclass
    }
    return null
  }

  private fun unwrap(value: Any?): Any? =
    if (value is StateFlow<*>) value.value else value

  override fun readField(name: String): Any? {
    val field = findField(vm, name)
    if (field != null) {
      val raw = unwrap(field.get(vm))
      if (raw != null || dataValue() == null) return raw
    }
    val data = dataValue() ?: return null
    val dataField = findField(data, name) ?: return null
    return unwrap(dataField.get(data))
  }

  private fun dataFlow(): MutableStateFlow<Any?>? {
    // `_data` is the kjui-generated backing MutableStateFlow; the public
    // `data` field is a read-only wrapper, so check the backing field first.
    for (candidate in arrayOf("_data", "data")) {
      val f = findField(vm, candidate) ?: continue
      val raw = f.get(vm)
      if (raw is MutableStateFlow<*>) {
        @Suppress("UNCHECKED_CAST")
        return raw as MutableStateFlow<Any?>
      }
    }
    return null
  }

  private fun dataValue(): Any? = dataFlow()?.value

  override fun setState(state: Map<String, Any?>) {
    val dataKeys = mutableMapOf<String, Any?>()
    for ((k, v) in state) {
      val field = findField(vm, k)
      if (field != null && !Modifier.isStatic(field.modifiers)) {
        val current = field.get(vm)
        if (current is MutableStateFlow<*>) {
          @Suppress("UNCHECKED_CAST")
          (current as MutableStateFlow<Any?>).value = coerce(v, current.value?.javaClass)
        } else {
          field.set(vm, coerce(v, field.type))
        }
      }
      dataKeys[k] = v
    }
    applyToData(dataKeys)
  }

  /** Copy the `_data` data class with every state key it declares. */
  private fun applyToData(state: Map<String, Any?>) {
    val flow = dataFlow() ?: return
    val current = flow.value ?: return
    val copyFn = current::class.memberFunctions.firstOrNull { it.name == "copy" } ?: return
    copyFn.isAccessible = true
    val callArgs = mutableMapOf(copyFn.instanceParameter!! to current as Any?)
    var any = false
    for (param in copyFn.parameters) {
      val name = param.name ?: continue
      if (name in state) {
        callArgs[param] = state[name]
        any = true
      }
    }
    if (any) flow.value = copyFn.callBy(callArgs)
  }

  private fun coerce(value: Any?, type: Class<*>?): Any? {
    if (value == null || type == null) return value
    return when (type) {
      java.lang.Long.TYPE, java.lang.Long::class.java ->
        (value as? Number)?.toLong() ?: value
      java.lang.Integer.TYPE, java.lang.Integer::class.java ->
        (value as? Number)?.toInt() ?: value
      java.lang.Double.TYPE, java.lang.Double::class.java ->
        (value as? Number)?.toDouble() ?: value
      java.lang.Float.TYPE, java.lang.Float::class.java ->
        (value as? Number)?.toFloat() ?: value
      else -> value
    }
  }

  /** VM method first (by name + arity), else a data-field lambda (the
   * kjui action-handler pattern stores `onXxxTap` closures in the data). */
  override fun invoke(name: String, vararg args: Any?) {
    val method = vm.javaClass.methods.firstOrNull {
      it.name == name && it.parameterCount == args.size
    }
    if (method != null) {
      method.isAccessible = true
      method.invoke(vm, *args)
      return
    }
    val handler = readField(name)
      ?: error("branch-harness: no method or data handler named '" + name + "'")
    when (handler) {
      is Function0<*> -> handler.invoke()
      is Function1<*, *> -> @Suppress("UNCHECKED_CAST") (handler as Function1<Any?, Any?>).invoke(args.getOrNull(0))
      is Function2<*, *, *> -> @Suppress("UNCHECKED_CAST") (handler as Function2<Any?, Any?, Any?>).invoke(args.getOrNull(0), args.getOrNull(1))
      else -> error("branch-harness: '" + name + "' is not invokable (" + handler.javaClass + ")")
    }
  }
}

/** Numeric-tolerant equality for data-field asserts (JSON 5 vs Long field). */
fun assertFieldEquals(expected: Any?, actual: Any?) {
  val e = if (expected is Ref) expected.value else expected
  if (e is Number && actual is Number) {
    org.junit.Assert.assertEquals(e.toDouble(), actual.toDouble(), 0.0)
    return
  }
  org.junit.Assert.assertEquals(e, actual)
}

/** Recursive partial match against a recorded JSON request body.
 * `null` expectations also accept absent keys (serializers drop nulls). */
fun partialMismatches(actual: JsonElement?, expected: Any?, prefix: String = ""): List<String> {
  val label = prefix.ifEmpty { "${'$'}" }
  val exp = if (expected is Ref) expected.value else expected
  if (exp is Map<*, *>) {
    if (actual !is JsonObject) {
      return listOf(label + ": expected object, got " + actual)
    }
    val out = mutableListOf<String>()
    for ((k, v) in exp) {
      val key = k.toString()
      out += partialMismatches(actual[key], v, if (prefix.isEmpty()) key else "$prefix.$key")
    }
    return out
  }
  if (exp == null) {
    return if (actual == null || actual is JsonNull) emptyList()
    else listOf(label + ": expected null/absent, got " + actual)
  }
  if (actual == null || actual is JsonNull) {
    return listOf(label + ": expected " + exp + ", got " + actual)
  }
  if (actual !is JsonPrimitive) {
    return listOf(label + ": expected scalar " + exp + ", got " + actual)
  }
  val matches = when (exp) {
    is Boolean -> actual.booleanOrNull == exp
    is Number -> actual.doubleOrNull == exp.toDouble()
    is String -> actual.isString && actual.content == exp
    else -> false
  }
  return if (matches) emptyList()
  else listOf(label + ": expected " + exp + ", got " + actual)
}
'''


KOTLIN_HARNESS_SKELETON = '''// Branch-contract test harness for `%(screen)s` — CONSUMER-OWNED.
// Generated once as a skeleton by `jsonui-test generate branch-tests`;
// edit freely, it will not be overwritten.
package %(package)s

import kotlinx.coroutines.test.TestDispatcher

/** Spec '@key' expectations — bare own-section key to the resolved string.
 * Keep this a closed map (same reasoning as the web harness: dynamic
 * resource-name construction defeats string-usage lint gates). */
// private val %(screen_const)s_BRANCH_STRINGS: Map<String, Int> = mapOf(
//   "some_error" to R.string.%(screen)s_some_error,
// )

/** `then.transition` destinations — screen name to an observable predicate
 * on the VM's navigation state (kjui exposes transitions as StateFlows). */
// private val SCREEN_FLOWS: Map<String, (vm) -> Boolean> = mapOf(...)

fun create%(pascal)sBranchHarness(baseUrl: String, dispatcher: TestDispatcher): BranchHarness {
  // TODO: build the real stack against MockWebServer —
  //   Retrofit(baseUrl) -> ApiService -> RepositoryImpl(s) -> ViewModel
  // with ApplicationProvider.getApplicationContext() (Robolectric), then
  // return an object extending BaseBranchHarness(vm, dispatcher) that
  // implements expectTransition (SCREEN_FLOWS) and resolveString.
  throw NotImplementedError("branch-harness for %(screen)s is not implemented yet")
}
'''


# ---------------------------------------------------------------------------
# iOS (Swift / XCTest) renderer.
#
# Same HTTP-boundary principle via URLProtocol interception (the consumer
# network stack builds sessions from URLSessionConfiguration.default, which
# honors URLProtocol.registerClass) — repositories, Codable decoding, and
# the ViewModel run real. Swift has no runtime reflection WRITES, so the
# split is: READS are generic (Mirror over the VM and its `data` struct,
# @Published unwrapped best-effort), WRITES go through the consumer harness
# (the kjui/sjui-generated `Data.update(dictionary:)` map setter plus typed
# event-handler routing for VM-internal state).
# ---------------------------------------------------------------------------

def _swift_str(s: str) -> str:
    """Swift string literal (JSON escapes are Swift-compatible except the
    \\uXXXX form, which Swift writes as \\u{XXXX})."""
    out = json.dumps(s, ensure_ascii=False)
    return re.sub(r"\\u([0-9a-fA-F]{4})", r"\\u{\1}", out)


def _swift(value) -> str:
    if value is None:
        return "NSNull()"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return _swift_str(value)
    if isinstance(value, dict):
        if not value:
            return "[:]"
        entries = ", ".join(f"{_swift_str(str(k))}: {_swift(v)}" for k, v in value.items())
        return f"[{entries}]"
    if isinstance(value, list):
        entries = ", ".join(_swift(v) for v in value)
        return f"[{entries}]"
    raise BranchTestGenerationError(f"cannot render value {value!r} as Swift")


def _swift_expected(value) -> str:
    if isinstance(value, str) and value.startswith("@data."):
        return f"Ref(value: ref_{value[len('@data.'):]})"
    if isinstance(value, str) and value.startswith("@"):
        return f"h.resolveString({_swift_str(value[1:])})"
    if isinstance(value, dict):
        entries = ", ".join(
            f"{_swift_str(str(k))}: {_swift_expected(v)}" for k, v in value.items()
        )
        return f"[{entries}]"
    return _swift(value)


def render_swift_test_file(
    screen: str, spec: dict, routes: list[Route], module: str,
) -> tuple[str, GenerationReport]:
    bc = spec.get("branchContracts") or {}
    conditions = bc.get("conditions") or {}
    methods_contracts = bc.get("methods") or {}
    report = GenerationReport(screen=screen)
    report.routes = [r.op for r in routes]
    pascal = _pascal(screen)

    route_lines = []
    for r in routes:
        scen = ", ".join(
            f"{_swift_str(name)}: ({sc.get('status', 200)}, "
            f"{_swift_str(json.dumps(sc.get('body'), ensure_ascii=False))})"
            for name, sc in r.scenarios.items()
        )
        route_lines.append(
            f"    RouteSpec(op: {_swift_str(r.op)}, method: {_swift_str(r.method)},\n"
            f"      pattern: {_swift_str(r.pattern)}, defaultScenario: {_swift_str(r.default_scenario)},\n"
            f"      scenarios: [{scen}])"
        )

    lines: list[str] = []
    lines.append(f"// @generated by `jsonui-test generate branch-tests {screen} --platform ios` — DO NOT EDIT.")
    lines.append("// Source of truth: the screen spec's branchContracts section.")
    lines.append("import XCTest")
    lines.append(f"@testable import {module}")
    lines.append("")
    lines.append(f"final class {pascal}BranchesTest: XCTestCase {{")
    lines.append("")
    lines.append("  private let routes: [RouteSpec] = [")
    lines.append(",\n".join(route_lines))
    lines.append("  ]")

    for method_name, contract in methods_contracts.items():
        if not isinstance(contract, dict):
            continue
        report.methods.append(method_name)
        params = method_params(spec, method_name)
        branches = contract.get("branches") or []
        notes = [(i + 1, b["note"]) for i, b in enumerate(branches)
                 if isinstance(b, dict) and "note" in b]
        report.note_branches += len(notes)
        lines.append("")
        lines.append(f"  // ===== {method_name} =====")
        if notes:
            lines.append("  // %d note-only branch(es) — outside the machine-checkable contract:" % len(notes))
            for num, note in notes:
                lines.append(f"  //   #{num}: {note}")
        for i, branch in enumerate(branches):
            if not isinstance(branch, dict) or "note" in branch:
                continue
            if not _branch_active(branch, "ios"):
                report.platform_skipped += 1
                lines.append(
                    f"  // branch {i + 1} is platform-scoped "
                    f"({branch.get('platforms')}) — not generated for ios")
                continue
            report.declared_branches += 1
            lines.extend(_render_swift_branch(
                pascal, method_name, params, contract, branch, i + 1, conditions))
    lines.append("}")
    return "\n".join(lines) + "\n", report


def _render_swift_branch(
    pascal: str, method_name: str, params: list[str], contract: dict,
    branch: dict, number: int, conditions: dict,
) -> list[str]:
    when = branch.get("when") or {}
    then = branch.get("then") or {}
    state = _arrange_state(contract, branch, conditions)
    overrides = {k[len("api."):]: v for k, v in when.items() if k.startswith("api.")}
    arg_values = {k[len("arg."):]: v for k, v in when.items() if k.startswith("arg.")}
    args = [
        _swift(arg_values.get(p)) if p in arg_values else "NSNull()"
        for p in params
    ]
    while args and args[-1] == "NSNull()":
        args.pop()
    data_refs = _collect_data_refs(then)

    out: list[str] = []
    out.append("")
    out.append(f"  // {_branch_title(number, branch)}")
    out.append(f"  func test_{method_name}_branch_{number}() {{")
    out.append(
        f"    runBranchTest(routes: routes, overrides: {_swift(overrides) if overrides else '[:]'},"
    )
    out.append(f"                      harnessFactory: create{pascal}BranchHarness) {{ h, rec in")
    if state:
        out.append(f"      h.setState({_swift(state)})")
    for fname in data_refs:
        out.append(f"      let ref_{fname} = h.readField({_swift_str(fname)})")
    call_args = ", ".join(args)
    out.append(f"      h.invoke({_swift_str(method_name)}, args: [{call_args}])")
    out.append("      h.settle()")
    for key, value in then.items():
        if key == "api":
            out.append("      XCTAssertTrue(rec.matchedCalls().isEmpty, \"expected no declared-API calls, got \\(rec.matchedCalls())\")")
        elif key == "transition":
            out.append(f"      h.expectTransition({_swift_str(value)})")
        elif key.startswith("api.") and key.endswith(".request"):
            op = key[len("api."):-len(".request")]
            out.append(f"      XCTAssertGreaterThan(rec.countFor({_swift_str(op)}), 0)")
            out.append(
                f"      XCTAssertEqual(partialMismatches(rec.lastBodyFor({_swift_str(op)}), "
                f"{_swift_expected(value)}), [])"
            )
        elif key.startswith("api."):
            op = key[len("api."):]
            if value == "called":
                out.append(f"      XCTAssertGreaterThan(rec.countFor({_swift_str(op)}), 0)")
            else:
                out.append(f"      XCTAssertEqual(rec.countFor({_swift_str(op)}), 0)")
        elif key.startswith("data."):
            fname = key[len("data."):]
            out.append(
                f"      assertFieldEquals({_swift_expected(value)}, "
                f"h.readField({_swift_str(fname)}))"
            )
    out.append("    }")
    out.append("  }")
    return out


SWIFT_RUNTIME = '''// @generated by `jsonui-test generate branch-tests --platform ios` — DO NOT EDIT.
// Shared runtime for branch-contract tests: URLProtocol scenario serving,
// request recording, Mirror-based reads, partial matching, and run-loop
// settling. HTTP is the ONLY mocked boundary — the consumer network stack
// builds URLSessions from URLSessionConfiguration.default, which honors
// URLProtocol.registerClass, so repositories and Codable decoding run real.
import Foundation
import XCTest

struct RouteSpec {
  let op: String
  let method: String
  let pattern: String
  let defaultScenario: String
  let scenarios: [String: (Int, String)]
}

struct RecordedCall {
  let op: String
  let method: String
  let path: String
  let body: Any?
}

final class Recorder {
  var calls: [RecordedCall] = []
  /// Calls bound to a declared route — the `api: "none"` surface. On iOS
  /// the URLProtocol intercepts the whole process, so third-party SDK
  /// traffic (analytics etc.) shows up as "(unmatched)"; it is served a
  /// 599 and recorded for diagnostics but is not the contract surface.
  func matchedCalls() -> [RecordedCall] { calls.filter { $0.op != "(unmatched)" } }
  func countFor(_ op: String) -> Int { calls.filter { $0.op == op }.count }
  func lastBodyFor(_ op: String) -> Any? { calls.last { $0.op == op }?.body }
}

/// '@data.<field>' pre-act capture marker.
struct Ref { let value: Any? }

protocol BranchHarness {
  var vm: AnyObject { get }
  /// Return the field's current value. An unset field may come back as
  /// Swift nil or NSNull() — both compare equal to a `null` in the
  /// contract, so an Optional property can be passed straight through.
  func readField(_ name: String) -> Any?
  func setState(_ state: [String: Any])
  func invoke(_ name: String, args: [Any])
  func expectTransition(_ destination: String)
  func resolveString(_ key: String) -> String
  func settle()
}

final class BranchURLProtocol: URLProtocol {
  static var routes: [RouteSpec] = []
  static var overrides: [String: String] = [:]
  static var recorder: Recorder?

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func stopLoading() {}

  private static func bodyData(of request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    // URLSession hands custom protocols the body as a stream.
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let bufferSize = 4096
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let read = stream.read(buffer, maxLength: bufferSize)
      if read <= 0 { break }
      data.append(buffer, count: read)
    }
    return data
  }

  override func startLoading() {
    let path = request.url?.path ?? "/"
    let method = (request.httpMethod ?? "GET").uppercased()
    let raw = Self.bodyData(of: request)
    let body = raw.flatMap { try? JSONSerialization.jsonObject(with: $0) }

    for route in Self.routes {
      guard route.method == method,
            let regex = try? NSRegularExpression(pattern: route.pattern),
            regex.firstMatch(in: path, range: NSRange(path.startIndex..., in: path)) != nil
      else { continue }
      Self.recorder?.calls.append(RecordedCall(op: route.op, method: method, path: path, body: body))
      let name = Self.overrides[route.op] ?? route.defaultScenario
      guard let scenario = route.scenarios[name] else {
        client?.urlProtocol(self, didFailWithError: NSError(
          domain: "branch-runtime", code: 1,
          userInfo: [NSLocalizedDescriptionKey: "scenario '\\(name)' missing for op '\\(route.op)'"]))
        return
      }
      respond(status: scenario.0, body: scenario.1)
      return
    }
    Self.recorder?.calls.append(RecordedCall(op: "(unmatched)", method: method, path: path, body: nil))
    respond(status: 599, body: "{\\"error\\":{\\"code\\":\\"unmocked_endpoint\\"}}")
  }

  private func respond(status: Int, body: String) {
    guard let url = request.url,
          let response = HTTPURLResponse(
            url: url, statusCode: status, httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"])
    else { return }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }
}

/// URLProtocol.registerClass only reaches URLSession.shared — consumer
/// network stacks that build sessions from URLSessionConfiguration.default
/// never consult it. Swizzle the `default`/`ephemeral` getters (the
/// OHHTTPStubs-proven approach) so every new configuration carries the
/// branch protocol at the front of protocolClasses.
private let installConfigurationSwizzle: Void = {
  for selector in [#selector(getter: URLSessionConfiguration.default),
                   #selector(getter: URLSessionConfiguration.ephemeral)] {
    let swizzled = selector == #selector(getter: URLSessionConfiguration.default)
      ? #selector(URLSessionConfiguration.branchTestDefault)
      : #selector(URLSessionConfiguration.branchTestEphemeral)
    guard let original = class_getClassMethod(URLSessionConfiguration.self, selector),
          let replacement = class_getClassMethod(URLSessionConfiguration.self, swizzled)
    else { continue }
    method_exchangeImplementations(original, replacement)
  }
}()

extension URLSessionConfiguration {
  @objc class func branchTestDefault() -> URLSessionConfiguration {
    let config = branchTestDefault()  // swapped: calls the original getter
    config.protocolClasses = [BranchURLProtocol.self] + (config.protocolClasses ?? [])
    return config
  }
  @objc class func branchTestEphemeral() -> URLSessionConfiguration {
    let config = branchTestEphemeral()  // swapped: calls the original getter
    config.protocolClasses = [BranchURLProtocol.self] + (config.protocolClasses ?? [])
    return config
  }
}

func runBranchTest(
  routes: [RouteSpec],
  overrides: [String: String],
  harnessFactory: () -> BranchHarness,
  block: (BranchHarness, Recorder) throws -> Void
) rethrows {
  _ = installConfigurationSwizzle
  let recorder = Recorder()
  BranchURLProtocol.routes = routes
  BranchURLProtocol.overrides = overrides
  BranchURLProtocol.recorder = recorder
  URLProtocol.registerClass(BranchURLProtocol.self)
  defer {
    URLProtocol.unregisterClass(BranchURLProtocol.self)
    BranchURLProtocol.routes = []
    BranchURLProtocol.overrides = [:]
    BranchURLProtocol.recorder = nil
  }
  let harness = harnessFactory()
  defer {
    // Deliberate retain-for-process-lifetime: deallocating @MainActor
    // types goes through the isolated-deinit back-deploy shim on pre-26
    // simulators, which crashes with an invalid free
    // (swift_task_deinitOnExecutorMainActorBackDeploy ->
    // BUG_IN_CLIENT_OF_LIBMALLOC, observed on the iOS 18.6 runtime).
    // A handful of retained test VMs per process is harmless; a runtime
    // crash on teardown fails every branch test at 0.000s.
    BranchHarnessRetainer.retain(harness)
  }
  try block(harness, recorder)
}

enum BranchHarnessRetainer {
  private static var retained: [BranchHarness] = []
  static func retain(_ harness: BranchHarness) { retained.append(harness) }
}

/// Generic READ access: Mirror over the subject (labels match `name` or
/// `_name`), unwrapping @Published best-effort. Swift cannot WRITE fields
/// reflectively — writes go through the consumer harness.
func mirrorField(_ subject: Any, _ name: String) -> Any? {
  var mirror: Mirror? = Mirror(reflecting: subject)
  while let m = mirror {
    for child in m.children where child.label == name || child.label == "_" + name {
      return unwrapPublished(child.value)
    }
    mirror = m.superclassMirror
  }
  return nil
}

private func unwrapPublished(_ value: Any) -> Any? {
  let typeName = String(describing: type(of: value))
  guard typeName.hasPrefix("Published<") else { return flattenOptional(value) }
  // Published<T> internals are not API. Its storage enum is either
  // .value(T) or .publisher(Publisher) — Mirror descendant paths cover both
  // (an enum case's associated value appears under the case's label).
  let mirror = Mirror(reflecting: value)
  for path: [MirrorPath] in [
    ["storage", "value"],
    ["storage", "publisher", "subject", "currentValue", "value"],
    ["storage", "publisher", "subject", "currentValue"],
    ["currentValue"],
  ] {
    if let found = descend(mirror, path) { return flattenOptional(found) }
  }
  return nil
}

private func descend(_ mirror: Mirror, _ path: [MirrorPath]) -> Any? {
  var current: Any? = nil
  var m = mirror
  for step in path {
    guard let label = step as? String,
          let child = m.children.first(where: { $0.label == label })
    else { return nil }
    current = child.value
    m = Mirror(reflecting: child.value)
  }
  return current
}

/// Mirror hands back Optionals as containers; flatten to the wrapped value.
private func flattenOptional(_ value: Any) -> Any? {
  let mirror = Mirror(reflecting: value)
  guard mirror.displayStyle == .optional else { return value }
  return mirror.children.first.map { flattenOptional($0.value) } ?? nil
}

/// Base harness: generic reads (VM field first, then the VM's `data`
/// struct), run-loop settling. Writes/invoke/transition/strings are the
/// consumer's typed closed maps.
class BaseBranchHarness: BranchHarness {
  let vm: AnyObject
  init(vm: AnyObject) { self.vm = vm }

  func readField(_ name: String) -> Any? {
    if let own = mirrorField(vm, name), !(own is NSNull) {
      // Direct VM member (plain var or @Published).
      if !isNestedContainer(own) { return own }
    }
    if let data = mirrorField(vm, "data") {
      if let inner = mirrorField(data, name) { return inner }
    }
    return mirrorField(vm, name)
  }

  private func isNestedContainer(_ value: Any) -> Bool { false }

  func setState(_ state: [String: Any]) {
    fatalError("branch-harness must override setState (Swift has no reflective writes)")
  }

  func invoke(_ name: String, args: [Any]) {
    fatalError("branch-harness must override invoke")
  }

  func expectTransition(_ destination: String) {
    fatalError("branch-harness must override expectTransition")
  }

  func resolveString(_ key: String) -> String {
    fatalError("branch-harness must override resolveString")
  }

  func settle() {
    // Task { @MainActor } continuations land on the main queue; URLProtocol
    // work completes on URLSession's queues. Drain the main run loop with
    // short real-time slices until the pipeline is quiet.
    for _ in 0..<80 {
      RunLoop.main.run(until: Date().addingTimeInterval(0.005))
    }
  }
}

/// "Absent" has two spellings here: a `null` in the contract arrives as
/// NSNull(), while a harness returning an Optional property straight
/// through hands back Swift nil. They mean the same thing, and comparing
/// their descriptions ("<null>" vs "nil") never matches — so neither
/// spelling is a convention a harness author has to remember.
private func normalizeNull(_ value: Any?) -> Any? {
  if value is NSNull { return nil }
  return value
}

/// Numeric-tolerant equality (JSON 5 vs Double field) with Ref unwrap.
func assertFieldEquals(_ expected: Any?, _ actual: Any?,
                       file: StaticString = #filePath, line: UInt = #line) {
  let exp = normalizeNull((expected as? Ref).map { $0.value } ?? expected)
  let act = normalizeNull(actual)
  if let en = asDouble(exp), let an = asDouble(act) {
    XCTAssertEqual(en, an, accuracy: 0.0, file: file, line: line)
    return
  }
  let e = exp.map { "\\($0)" } ?? "nil"
  let a = act.map { "\\($0)" } ?? "nil"
  XCTAssertEqual(e, a, file: file, line: line)
}

private func asDouble(_ value: Any?) -> Double? {
  if let b = value as? Bool { _ = b; return nil }
  if let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() { return n.doubleValue }
  if let d = value as? Double { return d }
  if let i = value as? Int { return Double(i) }
  return nil
}

/// Recursive partial match against a recorded JSON body. NSNull/nil
/// expectations also accept absent keys (encoders drop nils).
func partialMismatches(_ actual: Any?, _ expected: Any?, _ prefix: String = "") -> [String] {
  let label = prefix.isEmpty ? "$" : prefix
  let exp = (expected as? Ref).map { $0.value } ?? expected
  if let dict = exp as? [String: Any] {
    guard let actualDict = actual as? [String: Any] else {
      return ["\\(label): expected object, got \\(String(describing: actual))"]
    }
    var out: [String] = []
    for (k, v) in dict {
      out += partialMismatches(actualDict[k], v, prefix.isEmpty ? k : "\\(prefix).\\(k)")
    }
    return out
  }
  if exp == nil || exp is NSNull {
    if actual == nil || actual is NSNull { return [] }
    return ["\\(label): expected null/absent, got \\(String(describing: actual))"]
  }
  guard let actualValue = actual, !(actualValue is NSNull) else {
    return ["\\(label): expected \\(String(describing: exp)), got nil"]
  }
  if let en = asDouble(exp), let an = asDouble(actualValue) {
    return en == an ? [] : ["\\(label): expected \\(en), got \\(an)"]
  }
  if let eb = exp as? Bool, let ab = actualValue as? Bool {
    return eb == ab ? [] : ["\\(label): expected \\(eb), got \\(ab)"]
  }
  if let es = exp as? String, let asv = actualValue as? String {
    return es == asv ? [] : ["\\(label): expected \\(es), got \\(asv)"]
  }
  return ["\\(label): expected \\(String(describing: exp)), got \\(String(describing: actualValue))"]
}
'''


SWIFT_HARNESS_SKELETON = '''// Branch-contract test harness for `%(screen)s` — CONSUMER-OWNED.
// Generated once as a skeleton by `jsonui-test generate branch-tests`;
// edit freely, it will not be overwritten.
//
// Swift has no reflective writes, so this harness is the typed side of the
// contract: setState routes through the generated Data.update(dictionary:)
// (plus event-handler calls for VM-internal state), while invoke /
// expectTransition / resolveString are closed switches — an unknown name
// must fail loudly, never soften.
import Foundation
import XCTest
@testable import %(module)s

func create%(pascal)sBranchHarness() -> BranchHarness {
  // TODO: construct the real ViewModel (repositories build their own
  // network stack — URLProtocol interception is already active when this
  // factory runs) and return a subclass of BaseBranchHarness overriding:
  //   setState: vm.data.update(dictionary: state) + handler routing for
  //             VM-internal fields (e.g. name inputs)
  //   invoke:   switch over declared method / handler names
  //   expectTransition: switch over the VM's navigation @Published flags
  //   resolveString: closed key -> StringManager accessor map
  fatalError("branch-harness for %(screen)s is not implemented yet")
}
'''


def generate_branch_tests(
    screen: str,
    project_root: Path,
    spec_path: str | None = None,
    out_dir: str = "tests/unit/generated",
    harness_dir: str = "tests/unit/branch-harness",
    mocks_dir: str = "tests/mocks",
    platform: str = "web",
    package: str | None = None,
    module: str | None = None,
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

    mocks_path = (project_root / mocks_dir).resolve()
    mocks = index_mock_files(mocks_path)
    routes = resolve_routes(spec, bc["methods"], mocks, mocks_path)
    check_arg_bindings(spec, bc["methods"])
    resolve_response_refs(bc["methods"], routes)

    if platform == "android":
        if not package:
            raise BranchTestGenerationError(
                "--package is required for --platform android (Kotlin package "
                "of the generated test sources)"
            )
        return _emit_android(
            screen, spec, routes, project_root, out_dir, harness_dir, package)
    if platform == "ios":
        if not module:
            raise BranchTestGenerationError(
                "--module is required for --platform ios (the app module name "
                "for @testable import)"
            )
        return _emit_ios(
            screen, spec, routes, project_root, out_dir, harness_dir, module)
    if platform != "web":
        raise BranchTestGenerationError(
            f"unknown platform '{platform}' — supported: web, android, ios"
        )

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
        harness_file.write_text(
            HARNESS_SKELETON % {"screen": screen,
                                "screen_const": screen.upper()},
            encoding="utf-8",
        )
        created = True

    report.test_file = test_file
    report.runtime_file = runtime_file
    report.harness_file = harness_file
    report.harness_created = created
    return report


def _emit_ios(
    screen: str, spec: dict, routes: list[Route], project_root: Path,
    out_dir: str, harness_dir: str, module: str,
) -> GenerationReport:
    """iOS emission: Swift XCTest sources. With Xcode's file-system-
    synchronized test groups, dropping the files into the test target's
    folder is registration enough."""
    pascal = _pascal(screen)
    out_path = project_root / out_dir
    out_path.mkdir(parents=True, exist_ok=True)
    harness_path = project_root / harness_dir
    harness_path.mkdir(parents=True, exist_ok=True)

    content, report = render_swift_test_file(screen, spec, routes, module)

    runtime_file = out_path / "JsonuiBranchRuntime.swift"
    runtime_file.write_text(SWIFT_RUNTIME, encoding="utf-8")
    test_file = out_path / f"{pascal}BranchesTest.swift"
    test_file.write_text(content, encoding="utf-8")

    harness_file = harness_path / f"{pascal}BranchHarness.swift"
    created = False
    if not harness_file.exists():
        harness_file.write_text(
            SWIFT_HARNESS_SKELETON % {
                "screen": screen, "pascal": pascal, "module": module,
            },
            encoding="utf-8",
        )
        created = True

    report.test_file = test_file
    report.runtime_file = runtime_file
    report.harness_file = harness_file
    report.harness_created = created
    return report


def _emit_android(
    screen: str, spec: dict, routes: list[Route], project_root: Path,
    out_dir: str, harness_dir: str, package: str,
) -> GenerationReport:
    """Android emission: Kotlin JUnit4 (Robolectric) sources.

    out_dir/harness_dir point at the Kotlin source roots (e.g.
    app/src/test/java); the package path is appended automatically."""
    pascal = _pascal(screen)
    pkg_path = _relative_kotlin_paths(package)
    out_path = project_root / out_dir / pkg_path
    out_path.mkdir(parents=True, exist_ok=True)
    harness_path = project_root / harness_dir / pkg_path
    harness_path.mkdir(parents=True, exist_ok=True)

    content, report = render_kotlin_test_file(screen, spec, routes, package)

    runtime_file = out_path / "JsonuiBranchRuntime.kt"
    runtime_file.write_text(KOTLIN_RUNTIME % {"package": package},
                            encoding="utf-8")
    test_file = out_path / f"{pascal}BranchesTest.kt"
    test_file.write_text(content, encoding="utf-8")

    harness_file = harness_path / f"{pascal}BranchHarness.kt"
    created = False
    if not harness_file.exists():
        harness_file.write_text(
            KOTLIN_HARNESS_SKELETON % {
                "screen": screen,
                "screen_const": screen.upper(),
                "pascal": pascal,
                "package": package,
            },
            encoding="utf-8",
        )
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
