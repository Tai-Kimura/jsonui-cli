"""`jsonui-test contracts coverage` — the API outcomes no branch contract answers.

For every screen and platform, every response status the OpenAPI document
declares for an operation the screen's dataFlow names is placed in exactly
one bucket:

    declared = required + outside-required
    required = row + unit + unreachable + unexpressible + not-evaluated + uncovered
    uncovered = partial + default-only + unattributed
    outside-required = unreached-op + n/a(default response) + n/a(no scenario)
                       + n/a(platform-excluded)

- **row** — a contract row serves this status in its `when` (or is an
  `alsoStatuses` copy of one that does) and its `then` says something beyond
  "the op was reached".
- **unit / unreachable / unexpressible** — `excludedOutcomes`: not a row, and
  why. Unverifiable claims, so the last resort; counted apart.
- **not-evaluated** — the method has a row for the op that could not be bound
  (or an `alsoStatuses` copy whose `@response.*` the status's body cannot
  answer), so the status is neither answered nor unanswered.
- **uncovered** — none of the above: `partial` (the method answers other
  statuses of the op), `default-only` (it answers none), `unattributed` (no
  method's rows reach the op at all, and `unreachedOps` does not say why).

The unit of coverage is (screen, view-model method, operation, platform), and
the population of a method's operations is what its rows REACH — the ops the
generated tests assert were called. The generated tests bound the other side
(no call outside the reach), so deleting the row that reaches an endpoint no
longer makes its statuses disappear from this count.

Exit per platform block, composed 2 > 1 > 3 > 0 for the process:
0 pass (or `empty`: no screen exists on the platform), 1 uncovered or a
declaration error, 2 cannot start, 3 unmeasured (something could not be
evaluated, and nothing was found uncovered). This command is not a gate yet:
nothing runs it for you.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .branch_tests import (
    ALL_PLATFORMS,
    PARENT_SPEC_TYPE,
    Bindings,
    MockFile,
    _branch_active,
    _is_sub_spec_of_a_parent,
    _load_spec_result,
    _reached_ops,
    _scenario_status,
    _screen_of,
    _spec_files,
    collect_bindings,
    collect_endpoint_ops,
    describe_overlap,
    effective_platforms,
    find_app_contract_spec,
    find_mock,
    index_mock_files,
    load_project_config,
    side_call_ops,
)
from .contract_declarations import parse_declarations

HTTP_VERBS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

EXIT_PASS, EXIT_UNCOVERED, EXIT_CANNOT_START, EXIT_UNMEASURED = 0, 1, 2, 3
_PRECEDENCE = (EXIT_CANNOT_START, EXIT_UNCOVERED, EXIT_UNMEASURED, EXIT_PASS)


def compose_exit(codes) -> int:
    """2 > 1 > 3 > 0: a block that could not start outranks every finding."""
    codes = set(codes)
    for code in _PRECEDENCE:
        if code in codes:
            return code
    return EXIT_PASS


class CannotStart(Exception):
    """The command cannot run at all (exit 2)."""


# ---------------------------------------------------------------- statuses ---

def status_keys(operation) -> list[str]:
    """The response keys an operation declares: numbers, ranges (`4XX`), default."""
    keys = []
    for raw in (operation.responses or {}):
        key = str(raw).strip()
        if key == "default":
            keys.append(key)
        elif re.fullmatch(r"[1-5]\d\d", key):
            keys.append(key)
        elif re.fullmatch(r"[1-5][Xx][Xx]", key):
            keys.append(key[0] + "XX")
    return list(dict.fromkeys(keys))


def _is_range(key: str) -> bool:
    return key.endswith("XX")


def _in_range(status: str, key: str) -> bool:
    return _is_range(key) and status.isdigit() and len(status) == 3 and status[0] == key[0]


def matching_key(status: str, keys: list[str]) -> str | None:
    """The response key a served status falls under.

    Its own number when the operation declares it; otherwise the range key it
    falls in — a range answers only the statuses the operation does not
    declare by number.
    """
    if status in keys:
        return status
    for key in keys:
        if _in_range(status, key):
            return key
    return None


def _no_scenario(key: str, keys: list[str], mock: MockFile) -> bool:
    """No scenario of the mock returns this key's status (range: one in range
    that the operation does not declare by number)."""
    statuses = {str(sc.get("status", 200)) for sc in mock.scenarios.values()
                if isinstance(sc, dict)}
    if _is_range(key):
        return not any(_in_range(s, key) and s not in keys for s in statuses)
    return key not in statuses


# --------------------------------------------------------------- the index ---

@dataclass
class ApiIndex:
    """`mock.swagger`'s operations, one index across every document."""
    by_route: dict = field(default_factory=dict)   # route_key -> (doc path, Operation)
    by_id: dict = field(default_factory=dict)      # operationId -> (doc path, Operation)
    #: route_key -> doc path, for api_directory documents mock.swagger does
    #: not list (where an endpoint not in the index can be found).
    elsewhere: dict = field(default_factory=dict)


def load_api_index(swaggers: list[Path], api_directory: Path | None) -> ApiIndex:
    from .mock.generate import route_key
    from .mock.openapi import OpenApiDoc

    index = ApiIndex()
    for path in swaggers:
        try:
            doc = OpenApiDoc.load(path)
        except (OSError, ValueError) as e:
            raise CannotStart(f"mock.swagger {path} could not be read: {e}") from e
        for op in doc.operations():
            key = route_key(op.method, op.path)
            if key in index.by_route and index.by_route[key][0] != path:
                raise CannotStart(
                    f"{op.method} {op.path} is declared by both "
                    f"{index.by_route[key][0]} and {path} — one route, one document")
            index.by_route[key] = (path, op)
            if op.operation_id in index.by_id and index.by_id[op.operation_id][1] is not op:
                raise CannotStart(
                    f"operationId '{op.operation_id}' is declared twice across "
                    "mock.swagger — a side call names one operation")
            index.by_id[op.operation_id] = (path, op)
    if api_directory is not None and api_directory.is_dir():
        listed = {p.resolve() for p in swaggers}
        for path in sorted(api_directory.rglob("*.json")):
            if path.resolve() in listed:
                continue
            try:
                doc = OpenApiDoc.load(path)
            except (OSError, ValueError):
                continue
            if not doc.is_api_spec():
                continue
            for op in doc.operations():
                index.elsewhere.setdefault(route_key(op.method, op.path), path)
    return index


# ----------------------------------------------------------------- project ---

@dataclass
class Project:
    root: Path
    config_platforms: list | None
    spec_dir: Path
    mocks_dir: Path
    mocks: list
    api: ApiIndex
    app: object                  # branch_tests.AppRules
    describes_a_screen: object   # shared spec_types.describes_a_screen


def _screen_classifier():
    """`shared/core/spec_types.describes_a_screen`, through jui_cli's loader."""
    from .branch_tests import _prefer_sibling_jui_cli

    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core import shared_core
    except ImportError:
        return None
    core = shared_core.load("spec_types")
    return core.describes_a_screen if core is not None else None


def load_project(root: Path) -> Project:
    config = load_project_config(root)
    if not config:
        raise CannotStart(f"no jui.config.json in {root}")
    spec_dir_name = config.get("spec_directory")
    if not isinstance(spec_dir_name, str) or not spec_dir_name:
        raise CannotStart("spec_directory is not declared in jui.config.json")
    spec_dir = (root / spec_dir_name).resolve()
    if not spec_dir.is_dir():
        raise CannotStart(f"spec_directory {spec_dir} does not exist")

    mock = config.get("mock") if isinstance(config.get("mock"), dict) else config
    swaggers = mock.get("swagger")
    if isinstance(swaggers, str):
        swaggers = [swaggers]
    if not swaggers:
        raise CannotStart("mock.swagger is not declared — the OpenAPI documents are "
                          "what this count is taken against")
    resolved = []
    for entry in swaggers:
        path = Path(entry)
        path = (path if path.is_absolute() else root / path).resolve()
        if not path.is_file():
            raise CannotStart(f"mock.swagger {entry} does not resolve ({path})")
        resolved.append(path)
    api_dir = (root / config.get("api_directory", "docs/api")).resolve()
    if api_dir.is_dir():
        outside = [p for p in resolved if api_dir not in p.parents]
        if outside:
            raise CannotStart(
                f"mock.swagger points outside api_directory ({api_dir}): "
                + ", ".join(str(p) for p in outside))
    mocks_dir = (root / (mock.get("mockDir") or "tests/mocks")).resolve()
    if not mocks_dir.is_dir():
        raise CannotStart(f"mockDir {mocks_dir} does not exist")

    platforms = config.get("platforms")
    if isinstance(platforms, dict):
        platforms = list(platforms)
    if not isinstance(platforms, list) or not platforms:
        platforms = None

    app = find_app_contract_spec(root)
    if len(app.declaring) > 1:
        raise CannotStart(
            "apiOutcomeRules are declared by more than one app contracts spec: "
            + ", ".join(str(p) for p in app.declaring))

    classify = _screen_classifier()
    if classify is None:
        raise CannotStart("the screen-type table (shared/core/spec_types.py) could "
                          "not be read, so the screens cannot be told from the rest")
    return Project(
        root=root, config_platforms=platforms, spec_dir=spec_dir,
        mocks_dir=mocks_dir, mocks=index_mock_files(mocks_dir),
        api=load_api_index(resolved, api_dir if api_dir.is_dir() else None),
        app=app, describes_a_screen=classify)


@dataclass
class ScreenSource:
    name: str
    spec: dict | None
    problem: str | None = None


def iter_screens(project: Project, only: str | None = None) -> tuple[list, int]:
    """Every screen under spec_directory (parents merged), and the count of
    specs whose type is in neither the screen nor the non-screen table."""
    screens: list[ScreenSource] = []
    unknown = 0
    for path in _spec_files(project.spec_dir):
        name = _screen_of(path)
        if only and name != only:
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            screens.append(ScreenSource(name, None, f"not readable ({e})"))
            continue
        kind = project.describes_a_screen(raw.get("type") if isinstance(raw, dict) else None)
        if kind is False:
            continue
        if kind is None:
            unknown += 1
            continue
        if raw.get("type") != PARENT_SPEC_TYPE and _is_sub_spec_of_a_parent(path, project.spec_dir):
            continue
        spec, refusal = _load_spec_result(path)
        screens.append(ScreenSource(name, None if refusal else spec, refusal))
    return screens, unknown


# ------------------------------------------------------------------- judge ---

def _error(method=None, branch_index=None, op=None, status=None, message="") -> dict:
    return {"method": method, "branch_index": branch_index, "op": op,
            "status": status, "message": message}


@dataclass
class ScreenResult:
    spec: str
    platform_excluded: bool = False
    not_evaluated_reason: str | None = None
    units: int = 0
    contracted_methods: int = 0
    vm_methods: int = 0
    declared: int = 0
    breakdown: dict = field(default_factory=lambda: dict(
        row=0, unit=0, unreachable=0, unexpressible=0, not_evaluated=0, uncovered=0))
    row_also_statuses: int = 0
    uncovered_breakdown: dict = field(default_factory=lambda: dict(
        partial=0, default_only=0, unattributed=0))
    uncovered: list = field(default_factory=list)
    declaration_errors: list = field(default_factory=list)
    not_evaluated: list = field(default_factory=list)
    info: dict = field(default_factory=lambda: dict(
        guard_only=0, note_branches=0, also_statuses_rows=0,
        also_statuses_arrange_differs=0, side_calls_admitted=0,
        reference_holds_on_success_row=0, route_overlaps=0))
    methods_without_endpoint: int = 0
    outside_required: dict = field(default_factory=lambda: dict(
        unreached_op=0, na_default_response=0, na_no_scenario=0, na_platform_excluded=0))
    na_endpoints: dict = field(default_factory=lambda: dict(
        no_mock=0, not_in_openapi=0, non_http=0))
    notes: list = field(default_factory=list)
    http_endpoints: int = 0
    branches_active: int = 0
    branches_total: int = 0

    @property
    def statuses_required(self) -> int:
        return sum(self.breakdown.values())

    def check_arithmetic(self) -> None:
        """The partition is closed: every declared status is in one bucket."""
        outside = sum(self.outside_required.values())
        assert self.declared == self.statuses_required + outside, (self.spec, self.declared)
        assert self.breakdown["uncovered"] == sum(self.uncovered_breakdown.values()), self.spec
        assert self.row_also_statuses <= self.breakdown["row"], self.spec


def _endpoints(spec: dict):
    """(route_key -> {method, path}, methods without an endpoint, non-HTTP count)."""
    from .mock.generate import route_key

    endpoints: dict = {}
    without = 0
    non_http = 0
    flow = spec.get("dataFlow") or {}
    for section in ("repositories", "useCases"):
        for owner in flow.get(section) or []:
            if not isinstance(owner, dict):
                continue
            for method in owner.get("methods") or []:
                if not isinstance(method, dict):
                    continue
                endpoint = method.get("endpoint")
                if not isinstance(endpoint, str) or not endpoint.strip():
                    without += 1
                    continue
                m = re.match(r"^([A-Z]+)\s+(\S+)$", endpoint.strip())
                if not m or m.group(1) not in HTTP_VERBS:
                    non_http += 1
                    continue
                endpoints.setdefault(route_key(m.group(1), m.group(2)),
                                     {"method": m.group(1), "path": m.group(2)})
    return endpoints, without, non_http


def _callers(spec: dict, names: set) -> list:
    """UseCase methods whose `calls` name one of these op names."""
    out = []
    for use_case in (spec.get("dataFlow") or {}).get("useCases") or []:
        if not isinstance(use_case, dict):
            continue
        for method in use_case.get("methods") or []:
            if not isinstance(method, dict):
                continue
            for call in method.get("calls") or []:
                if isinstance(call, str) and (call in names or call.split(".")[-1] in names):
                    out.append(f"{use_case.get('name')}.{method.get('name')}")
                    break
    return sorted(set(out))


def evaluate_screen(name: str, spec: dict, platform: str, project: Project) -> ScreenResult:
    from .mock.generate import route_key

    res = ScreenResult(spec=name)
    declarations = parse_declarations(spec)
    for e in declarations.errors:
        res.declaration_errors.append(_error(message=f"{e.path}: {e.message}"))

    ops = collect_endpoint_ops(spec)
    endpoints, res.methods_without_endpoint, non_http = _endpoints(spec)
    res.na_endpoints["non_http"] = non_http
    res.http_endpoints = len(endpoints)

    def op_key(op: str):
        canonical = ops.resolve(op)
        if canonical is None:
            return None
        endpoint = ops.canonical[canonical]
        return route_key(endpoint["method"], endpoint["path"])

    names_of: dict = {}
    for canonical, endpoint in ops.canonical.items():
        names_of.setdefault(route_key(endpoint["method"], endpoint["path"]), []).append(canonical)
    for alias, canonical in ops.aliases.items():
        endpoint = ops.canonical[canonical]
        names_of.setdefault(route_key(endpoint["method"], endpoint["path"]), []).append(alias)

    if platform not in effective_platforms(project.config_platforms, declarations.platforms):
        res.platform_excluded = True
        for key in endpoints:
            entry = project.api.by_route.get(key)
            if entry is not None:
                n = len(status_keys(entry[1]))
                res.outside_required["na_platform_excluded"] += n
                res.declared += n
        res.check_arithmetic()
        return res

    evaluable: dict = {}
    for key, endpoint in endpoints.items():
        mock = find_mock(project.mocks, endpoint["method"], endpoint["path"])
        if mock is None:
            res.na_endpoints["no_mock"] += 1
            continue
        entry = project.api.by_route.get(key)
        if entry is None:
            res.na_endpoints["not_in_openapi"] += 1
            where = project.api.elsewhere.get(key)
            label = f"{endpoint['method']} {endpoint['path']}"
            res.notes.append(
                f"{label} is in {where.name}, which mock.swagger does not list — "
                "add it to mock.swagger" if where else f"{label} is in no OpenAPI document")
            continue
        evaluable[key] = (status_keys(entry[1]), mock)

    bc = spec.get("branchContracts") if isinstance(spec.get("branchContracts"), dict) else {}
    methods = {m: c for m, c in (bc.get("methods") or {}).items() if isinstance(c, dict)}
    view_model = (spec.get("dataFlow") or {}).get("viewModel") or {}
    res.vm_methods = len(view_model.get("methods") or [])

    if methods:
        bindings = collect_bindings(
            spec, methods, project.mocks, project.mocks_dir, platform,
            rules=project.app.rules, declarations=declarations)
    else:
        bindings = Bindings(routes=[], rows=[], errors=[])
    by_op = {route.op: route for route in bindings.routes}
    res.info["route_overlaps"] = len(bindings.overlaps)
    for winner, other in bindings.overlaps:
        res.notes.append(describe_overlap(winner, other))

    # ---- reach, from the rows as declared (a row that failed to bind still
    # says what it reaches)
    reach: dict = {}
    active_by_method: dict = {}
    for method, contract in methods.items():
        for i, branch in enumerate(contract.get("branches") or []):
            if not isinstance(branch, dict):
                continue
            if "note" in branch:
                res.info["note_branches"] += 1
                continue
            res.branches_total += 1
            if not _branch_active(branch, platform):
                continue
            res.branches_active += 1
            active_by_method[method] = active_by_method.get(method, 0) + 1
            then = branch.get("then") or {}
            if "api" in then:
                res.info["guard_only"] += 1
            res.info["guard_only"] += sum(
                1 for k, v in then.items()
                if k.startswith("api.") and not k.endswith(".request") and v != "called")
            for op in _reached_ops(branch):
                key = op_key(op)
                if key is not None:
                    reach.setdefault(method, set()).add(key)
    res.contracted_methods = len(active_by_method)

    # ---- binding errors
    not_evaluated_units: set = set()
    not_evaluated_statuses: set = set()
    for e in bindings.errors:
        entry = _error(e.method, e.branch_index, e.op, e.status, e.message)
        if e.method is None or e.kind == "self":
            res.declaration_errors.append(entry)
        elif e.kind == "response":
            key = op_key(e.op) if e.op else None
            if key in evaluable:
                status = matching_key(e.status, evaluable[key][0])
                not_evaluated_statuses.add((e.method, key, status))
            res.not_evaluated.append(entry)
        elif e.kind == "binding":
            branch = (methods.get(e.method, {}).get("branches") or [])[e.branch_index] \
                if e.branch_index is not None else {}
            refs = set(_reached_ops(branch)) | {
                k[len("api."):] for k in (branch.get("when") or {}) if k.startswith("api.")}
            for op in refs:
                key = op_key(op)
                if key is not None:
                    not_evaluated_units.add((e.method, key))
            res.not_evaluated.append(entry)

    # ---- unreachedOps
    unreached: dict = {}
    for u in declarations.unreached_ops:
        if u.platforms is not None and platform not in u.platforms:
            continue
        key = op_key(u.op)
        if key is None:
            res.declaration_errors.append(_error(
                op=u.op, message=f"unreachedOps api.{u.op}: no endpoint declaration names it"))
            continue
        unreached[key] = u
        if res.branches_active == 0:
            res.declaration_errors.append(_error(
                op=u.op, message=(
                    f"unreachedOps api.{u.op}: no row of this screen is active on "
                    f"{platform}, so no generated test can check the claim")))
    for method, keys in reach.items():
        for key in keys & set(unreached):
            res.declaration_errors.append(_error(
                method=method, op=unreached[key].op, message=(
                    f"{method} reaches api.{unreached[key].op}, which unreachedOps "
                    "says no contracted method calls")))
    if unreached and 0 < len(active_by_method) < len(methods):
        res.notes.append(
            f"unreachedOps verified by the bound in {len(active_by_method)} of "
            f"{len(methods)} methods on {platform}")

    # ---- exclusions
    exclusions: dict = {}
    for x in declarations.exclusions:
        if x.platforms is not None and platform not in x.platforms:
            continue
        key = op_key(x.op)
        where = f"methods.{x.method}.excludedOutcomes.api.{x.op}.{x.status}"
        if key is None:
            res.declaration_errors.append(_error(x.method, None, x.op, x.status,
                                                 f"{where}: no endpoint declaration names it"))
            continue
        if key not in reach.get(x.method, set()):
            res.declaration_errors.append(_error(
                x.method, None, x.op, x.status,
                f"{where}: {x.method} does not reach api.{x.op} on {platform} — a stale exclusion"))
            continue
        if key in evaluable and x.status not in evaluable[key][0]:
            res.declaration_errors.append(_error(
                x.method, None, x.op, x.status,
                f"{where}: the operation declares no {x.status}"))
            continue
        exclusions[(x.method, key, x.status)] = x

    # ---- rows: what each bound row answers
    covered: dict = {}         # (method, key) -> {status key: [row kinds]}
    answers: dict = {}         # (method, key, status, arrange) -> [row kinds]
    for row in bindings.rows:
        original = methods[row.method]["branches"][row.number - 1]
        when = row.branch.get("when") or {}
        then = row.branch.get("then") or {}
        if row.also is not None:
            res.info["also_statuses_rows"] += 1
        for op in _reached_ops(row.branch):
            key = op_key(op)
            if key not in evaluable:
                continue
            scenario = when.get(f"api.{op}")
            route = by_op.get(op)
            if not isinstance(scenario, str) or route is None or scenario not in route.scenarios:
                continue
            status = matching_key(_scenario_status(route, scenario), evaluable[key][0])
            if status is None:
                continue
            if not [k for k in then if k not in (f"api.{op}", f"api.{op}.request")]:
                continue
            kind = "also" if row.also else "row"
            covered.setdefault((row.method, key), {}).setdefault(status, []).append(kind)
            arrange = json.dumps({
                "when": {k: v for k, v in (original.get("when") or {}).items() if k != f"api.{op}"},
                "baseline": original.get("baseline") or {}}, sort_keys=True, ensure_ascii=False)
            answers.setdefault((row.method, key, status, arrange), []).append(kind)

    arranges: dict = {}
    for (method, key, status, arrange), kinds in answers.items():
        arranges.setdefault((method, key, status), []).append((arrange, kinds))
        if len(kinds) > 1 and "also" in kinds:
            res.declaration_errors.append(_error(
                method, None, None, status,
                f"{method}: status {status} of {names_of.get(key, ['?'])[0]} is answered by "
                f"{len(kinds)} rows with the same arrangement, one of them an "
                "alsoStatuses copy — two answers to one question"))
    for (method, key, status), groups in arranges.items():
        if len(groups) > 1 and any("also" in kinds for _, kinds in groups):
            res.info["also_statuses_arrange_differs"] += 1
    for (method, key, status) in exclusions:
        if status in covered.get((method, key), {}):
            res.declaration_errors.append(_error(
                method, None, None, status,
                f"{method}: status {status} of {names_of.get(key, ['?'])[0]} has both a "
                "row and an excludedOutcomes entry"))

    # alsoStatuses must name statuses the operation declares
    for also in declarations.also_statuses:
        branches = methods.get(also.method, {}).get("branches") or []
        if also.branch >= len(branches) or not _branch_active(branches[also.branch], platform):
            continue
        key = op_key(also.op)
        if key not in evaluable:
            continue
        for status in also.statuses:
            if matching_key(status, evaluable[key][0]) is None:
                res.declaration_errors.append(_error(
                    also.method, also.branch, also.op, status,
                    f"methods.{also.method}.branches[{also.branch}].alsoStatuses."
                    f"api.{also.op}: the operation declares no {status}"))

    # ---- info the reader weighs, never a finding
    for row in bindings.rows:
        served = set()
        for k, v in (row.branch.get("when") or {}).items():
            if k.startswith("api.") and isinstance(v, str) and k[len("api."):] in by_op:
                served.add(_scenario_status(by_op[k[len("api."):]], v))
        then = row.branch.get("then") or {}
        for rule in project.app.rules:
            if served & set(rule.statuses):
                for op in side_call_ops(rule, project.mocks, bindings.routes):
                    if then.get(f"api.{op}", "called") == "called" and then.get("api") is None:
                        res.info["side_calls_admitted"] += 1
    for also in declarations.also_statuses:
        branches = methods.get(also.method, {}).get("branches") or []
        if also.branch >= len(branches):
            continue
        claimed = {k: v for k, v in (branches[also.branch].get("then") or {}).items()
                   if not k.startswith("api")}
        route = by_op.get(also.op)
        if route is None:
            continue
        for number, other in enumerate(branches):
            if number == also.branch or not isinstance(other, dict) or "note" in other:
                continue
            scenario = (other.get("when") or {}).get(f"api.{also.op}")
            if not isinstance(scenario, str) or scenario not in route.scenarios:
                continue
            if not _scenario_status(route, scenario).startswith("2"):
                continue
            then = other.get("then") or {}
            if claimed and all(then.get(k) == v for k, v in claimed.items()):
                res.info["reference_holds_on_success_row"] += 1

    # ---- the partition
    reached_any = set().union(*reach.values()) if reach else set()
    for method, keys in sorted(reach.items()):
        for key in sorted(keys):
            if key not in evaluable or key in unreached:
                continue
            res.units += 1
            statuses, mock = evaluable[key]
            answered = covered.get((method, key), {})
            rows_answering = sum(1 for s in statuses if s in answered)
            left = []
            for status in statuses:
                res.declared += 1
                if status == "default":
                    res.outside_required["na_default_response"] += 1
                elif _no_scenario(status, statuses, mock):
                    res.outside_required["na_no_scenario"] += 1
                elif status in answered:
                    res.breakdown["row"] += 1
                    if all(kind == "also" for kind in answered[status]):
                        res.row_also_statuses += 1
                elif (method, key, status) in exclusions:
                    res.breakdown[exclusions[(method, key, status)].by] += 1
                elif (method, key) in not_evaluated_units or \
                        (method, key, status) in not_evaluated_statuses:
                    res.breakdown["not_evaluated"] += 1
                else:
                    res.breakdown["uncovered"] += 1
                    left.append(status)
            if left:
                kind = "partial" if rows_answering else "default-only"
                res.uncovered_breakdown["partial" if rows_answering else "default_only"] += len(left)
                endpoint = endpoints[key]
                res.uncovered.append({
                    "method": method, "op": names_of.get(key, ["?"])[0],
                    "route": f"{endpoint['method']} {endpoint['path']}",
                    "statuses": left, "kind": kind, "callers": []})
    for key, (statuses, mock) in sorted(evaluable.items()):
        if key in unreached:
            res.outside_required["unreached_op"] += len(statuses)
            res.declared += len(statuses)
            continue
        if key in reached_any:
            continue
        left = []
        for status in statuses:
            res.declared += 1
            if status == "default":
                res.outside_required["na_default_response"] += 1
            elif _no_scenario(status, statuses, mock):
                res.outside_required["na_no_scenario"] += 1
            else:
                res.breakdown["uncovered"] += 1
                left.append(status)
        if left:
            res.uncovered_breakdown["unattributed"] += len(left)
            endpoint = endpoints[key]
            res.uncovered.append({
                "method": None, "op": names_of.get(key, ["?"])[0],
                "route": f"{endpoint['method']} {endpoint['path']}",
                "statuses": left, "kind": "unattributed",
                "callers": _callers(spec, set(names_of.get(key, [])))})
    res.check_arithmetic()
    return res


# --------------------------------------------------------------- app level ---

def check_app(project: Project) -> list:
    """Declaration errors in the app contracts spec's apiOutcomeRules."""
    errors = []
    for path, message in project.app.problems:
        errors.append({"file": str(path), "path": None, "message": message})
    for rule in project.app.rules:
        for operation_id in rule.side_calls:
            where = f"apiOutcomeRules[{rule.id}].sideCalls {operation_id}"
            entry = project.api.by_id.get(operation_id)
            if entry is None:
                errors.append({"file": str(project.app.spec_file), "path": where,
                               "message": "no operation in mock.swagger has this operationId"})
                continue
            if entry[1].id_was_synthesized:
                errors.append({"file": str(project.app.spec_file), "path": where, "message": (
                    f"this id was synthesized — {entry[1].method} {entry[1].path} declares "
                    "no operationId; write one in the document")})
                continue
            generated = [m for m in project.mocks if m.operation_id == operation_id]
            if len(generated) != 1:
                errors.append({"file": str(project.app.spec_file), "path": where, "message": (
                    f"{len(generated)} generated mock(s) carry this operationId, so the "
                    "generated tests cannot resolve it — run `jsonui-test mock generate`")})
    return errors


# ------------------------------------------------------------------ blocks ---

@dataclass
class PlatformBlock:
    platform: str
    screens: list
    app_errors: list
    exit: int = 0
    verdict: str = "pass"

    def decide(self) -> None:
        active = [s for s in self.screens if not s.platform_excluded]
        if not active:
            self.exit, self.verdict = EXIT_PASS, "empty"
            return
        uncovered = sum(s.breakdown["uncovered"] for s in active)
        declaration = sum(len(s.declaration_errors) for s in active) + len(self.app_errors)
        unmeasured = sum(
            s.breakdown["not_evaluated"] + s.outside_required["na_no_scenario"]
            + s.na_endpoints["no_mock"] + s.na_endpoints["not_in_openapi"]
            + (1 if s.not_evaluated_reason else 0) for s in active)
        http = sum(s.http_endpoints for s in active)
        evaluated = sum(s.statuses_required for s in active)
        if uncovered:
            self.exit, self.verdict = EXIT_UNCOVERED, "uncovered"
        elif declaration:
            self.exit, self.verdict = EXIT_UNCOVERED, "declaration_error"
        elif unmeasured or (http and not evaluated):
            self.exit, self.verdict = EXIT_UNMEASURED, "unmeasured"
        else:
            self.exit, self.verdict = EXIT_PASS, "pass"


@dataclass
class CoverageReport:
    platforms: list
    project_platforms: list | None
    app_file: str | None
    rules: int
    app_errors: list
    unknown_types: int = 0
    exit: int = 0


def run_coverage(root: Path, platforms=None, screen: str | None = None) -> CoverageReport:
    """Everything the command prints, computed. Raises CannotStart."""
    project = load_project(root)
    if platforms:
        unknown = [p for p in platforms if p not in ALL_PLATFORMS]
        if unknown:
            raise CannotStart(f"unknown platform(s) {unknown} — supported: {list(ALL_PLATFORMS)}")
        chosen = [p for p in ALL_PLATFORMS if p in platforms]
    elif project.config_platforms:
        chosen = [p for p in ALL_PLATFORMS if p in project.config_platforms]
    else:
        raise CannotStart("jui.config.json declares no platforms — name one with --platform")
    app_errors = check_app(project)
    sources, unknown_types = iter_screens(project, screen)
    if screen and not sources:
        raise CannotStart(f"no screen '{screen}' under {project.spec_dir}")
    blocks = []
    for platform in chosen:
        results = []
        for source in sources:
            if source.spec is None:
                results.append(ScreenResult(spec=source.name, not_evaluated_reason=source.problem))
                continue
            results.append(evaluate_screen(source.name, source.spec, platform, project))
        block = PlatformBlock(platform, results, app_errors)
        block.decide()
        blocks.append(block)
    report = CoverageReport(
        platforms=blocks, project_platforms=project.config_platforms,
        app_file=str(project.app.spec_file) if project.app.spec_file else None,
        rules=len(project.app.rules), app_errors=app_errors, unknown_types=unknown_types)
    report.exit = compose_exit(b.exit for b in blocks)
    return report


# ------------------------------------------------------------------ output ---

_CAUSE = {
    EXIT_UNCOVERED: "write a row (alsoStatuses if the VM treats it like another status), "
                    "or an exclusion with a reason",
    EXIT_UNMEASURED: "some statuses could not be evaluated — see not-evaluated and n/a above",
}


def format_text(report: CoverageReport) -> list:
    lines = [f"contracts coverage  (project platforms: "
             f"{', '.join(report.project_platforms) if report.project_platforms else '(none)'})"]
    lines.append(f"app contracts: {report.app_file or '(none)'} · apiOutcomeRules {report.rules}")
    for error in report.app_errors:
        lines.append(f"  declaration error  {error['file']}: "
                     f"{error['path'] + ': ' if error['path'] else ''}{error['message']}")
    for block in report.platforms:
        p = block.platform
        active = [s for s in block.screens if not s.platform_excluded]
        excluded = len(block.screens) - len(active)
        if not active:
            lines.append(f"[platform={p}] info screens on {p} 0 of {len(block.screens)} "
                         "(metadata.platforms); config declares "
                         f"{p if report.project_platforms and p in report.project_platforms else '(not declared)'}")
            lines.append(f"[platform={p}] exit {block.exit} ({block.verdict})")
            continue
        branches_active = sum(s.branches_active for s in active)
        branches_total = sum(s.branches_total for s in active)
        if branches_total and not branches_active:
            lines.append(f"[platform={p}] branches active on {p} 0 of {branches_total}")
        for s in block.screens:
            if s.platform_excluded:
                continue
            if s.not_evaluated_reason:
                lines.append(f"[platform={p}] spec={s.spec}  NOT EVALUATED: {s.not_evaluated_reason}")
                continue
            lines.append(f"[platform={p}] spec={s.spec}  units {s.units}  contracted methods "
                         f"{s.contracted_methods} of {s.vm_methods}")
            b = s.breakdown
            lines.append(
                f"  statuses required {s.statuses_required} = row {b['row']} (alsoStatuses "
                f"{s.row_also_statuses}) + unit {b['unit']} + unreachable {b['unreachable']} + "
                f"unexpressible {b['unexpressible']} + not-evaluated {b['not_evaluated']} + "
                f"uncovered {b['uncovered']}")
            u = s.uncovered_breakdown
            lines.append(f"    uncovered {b['uncovered']} = partial {u['partial']} + "
                         f"default-only {u['default_only']} + unattributed {u['unattributed']}")
            if s.branches_total and not s.branches_active:
                lines.append(f"  metadata.platforms includes {p}; 0 branches active on {p} — "
                             f"write the {p} rows, or take {p} out of metadata.platforms")
            for item in s.uncovered:
                who = item["method"] or "(no method)"
                callers = f"  callers: {', '.join(item['callers'])}" if item["callers"] else ""
                lines.append(f"  uncovered  {item['kind']:<13} {who} × api.{item['op']}  "
                             f"{item['route']}  {' '.join(item['statuses'])}{callers}")
            for error in s.declaration_errors:
                lines.append(f"  declaration error  {error['message']}")
            for error in s.not_evaluated:
                lines.append(f"  not evaluated  {error['message']}")
            i = s.info
            lines.append(
                f"  info  guard-only {i['guard_only']} · note branches {i['note_branches']} · "
                f"also_statuses_rows {i['also_statuses_rows']} · also_statuses_arrange_differs "
                f"{i['also_statuses_arrange_differs']} · side_calls_admitted "
                f"{i['side_calls_admitted']} · reference_holds_on_success_row "
                f"{i['reference_holds_on_success_row']} · route_overlaps {i['route_overlaps']} · "
                f"dataFlow methods without endpoint {s.methods_without_endpoint}")
            o = s.outside_required
            lines.append(
                f"  outside required {sum(o.values())} = unreached-op {o['unreached_op']} + "
                f"n/a(default response) {o['na_default_response']} + n/a(no scenario) "
                f"{o['na_no_scenario']} + n/a(platform-excluded) {o['na_platform_excluded']}")
            n = s.na_endpoints
            lines.append(f"  n/a (E) no mock {n['no_mock']} · not in OpenAPI "
                         f"{n['not_in_openapi']} · non-HTTP {n['non_http']}")
            for note in s.notes:
                lines.append(f"  note  {note}")
        if excluded:
            lines.append(f"[platform={p}] info screens outside {p} (metadata.platforms): {excluded}")
        lines.append(f"[platform={p}] exit {block.exit} ({block.verdict})")
    if report.unknown_types:
        lines.append(f"info  {report.unknown_types} spec(s) of a type that is neither a "
                     "screen nor a known non-screen were not counted")
    total_uncovered = sum(s.breakdown["uncovered"] for b in report.platforms for s in b.screens)
    cause = _CAUSE.get(report.exit, "")
    lines.append(f"exit {report.exit} (composed 2 > 1 > 3 > 0)"
                 + (f": {total_uncovered} uncovered — {cause}" if report.exit == EXIT_UNCOVERED
                    and total_uncovered else (f": {cause}" if cause else "")))
    return lines


def to_json(report: CoverageReport) -> dict:
    platforms = []
    for block in report.platforms:
        active = [s for s in block.screens if not s.platform_excluded]
        screens = []
        for s in block.screens:
            if s.platform_excluded:
                continue
            screens.append({
                "spec": s.spec, "not_evaluated_reason": s.not_evaluated_reason,
                "units": s.units, "contracted_methods": s.contracted_methods,
                "statuses_required": s.statuses_required, "breakdown": dict(s.breakdown),
                "row_also_statuses": s.row_also_statuses,
                "uncovered_breakdown": dict(s.uncovered_breakdown),
                "uncovered": list(s.uncovered),
                "declaration_errors": list(s.declaration_errors),
                "not_evaluated": list(s.not_evaluated), "info": dict(s.info),
                "methods_without_endpoint": s.methods_without_endpoint,
                "outside_required": dict(s.outside_required),
                "na_endpoints": dict(s.na_endpoints), "notes": list(s.notes)})
        totals = {k: sum(s.breakdown[k] for s in active) for k in
                  ("row", "unit", "unreachable", "unexpressible", "not_evaluated", "uncovered")}
        platforms.append({
            "platform": block.platform, "project_platforms": report.project_platforms,
            "exit": block.exit, "verdict": block.verdict,
            "causes": {"screens_platform_excluded": len(block.screens) - len(active),
                       "screens_total": len(block.screens),
                       "branches_active": sum(s.branches_active for s in active),
                       "branches_total": sum(s.branches_total for s in active)},
            "screens": screens, "totals": totals})
    return {"app": {"spec_file": report.app_file, "rules": report.rules,
                    "declaration_errors": list(report.app_errors)},
            "platforms": platforms, "exit": report.exit}
