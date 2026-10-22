"""A room's server migration plans (ticket 2026-10-22-viz-infra-migration-plan; plan
docs/plans/2026-10-22-viz-infra-migration-plan.md): the old model (docs/infra) + a plan's changes - its removals = the
new model, and the steps that take one to the other, one node at a time.

A plan is a folder under the migrations folder (jui.config.json's infra.migrations_dir; default
<infra.dir>/migrations — not read as the model, which is the folder's *.json only): changes.json, an infra-model v0
file (groups, nodes, edges, flows, environments) with an optional "order" of node ids, and removals.json
(infra-migration.v0.schema.json: the ids of nodes, groups, flows, and edges by id or by their two ends). Either may be
left out. The rules:

1. replace: a node (group, edge, flow) of changes whose id the old model has takes its place;
2. add: one whose id it has not is added;
3. remove: one removals names goes;
4. taken along: an edge one of whose ends goes, goes with it;
5. kept: an edge of a node replaced stays as it was unless changes (an edge with its key) or removals names it.

An edge's key is its id, or "from->to" when it has none. The steps: the nodes in "order", then the rest of changes'
nodes as written, then removals' — one each — and one last step of kind "edges" when an edge, a group or a flow
changes with no node of its own changing. An edge added comes in at the later step of its two ends (a node no step
changes is there from the start), an edge that goes leaves at the earlier step of its ends that change; a group
changed comes in at the first step of a node it holds (else the last step), a group removed and the flows go at the
last step. ``model_at(k)`` is the model after k steps, merged as the room's (model.merge), so step 0 is the old model
and the last one the new: the room animates between them and the cost simulator prices each.

A plan's problems (code migration.*) name the file and the place, never a value. The new model is checked as the
room's is; its problems that the old model does not have are the plan's too.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import model as M
from . import room as R

SCHEMA_PATH = Path(__file__).with_name("infra-migration.v0.schema.json")
FILES = ("changes.json", "removals.json")
PLAN_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_PLANS = 20
CODES = ("migration.remove_missing", "migration.duplicate", "migration.both", "migration.order_unknown",
         "migration.edge_end", "migration.no_plan")
_SCHEMA: list[dict] = []


def schema() -> dict:
    if not _SCHEMA:
        _SCHEMA.append(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    return _SCHEMA[0]


def edge_key(e: dict) -> str:
    return e["id"] if e.get("id") else f"{e['from']}->{e['to']}"


def folder(root: Path) -> str:
    """The migrations folder inside the room (Refused("bad_config") as infra.dir)."""
    return R.side_dir(Path(root), "migrations_dir")


def plan_names(root: Path, mig: str) -> list[str]:
    """The plans: the folders directly in the migrations folder whose name is an id (no symlink, none followed), by
    name, at most MAX_PLANS."""
    import os
    import stat
    fd = R.open_inside(Path(root), mig)
    if fd is None:
        return []
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            return []
        out = []
        for name in sorted(os.listdir(fd)):
            if not PLAN_NAME.match(name):
                continue
            try:
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                out.append(name)
        return out[:MAX_PLANS]
    except OSError:
        return []
    finally:
        os.close(fd)


def planned_nodes(root: Path) -> set[str]:
    """The ids of the nodes the room's plans add or put in place (their changes.json, as written; a plan that cannot be
    read gives none): a load row for one is not a mistake of the room's own load definitions."""
    try:
        mig = folder(Path(root))
    except R.Refused:
        return set()
    out: set[str] = set()
    for name in plan_names(Path(root), mig):
        raw = R.read_capped(Path(root), f"{mig}/{name}/changes.json", R.LIMITS["file_bytes"])
        try:
            data = json.loads(raw.decode("utf-8-sig")) if isinstance(raw, bytes) else {}
        except (ValueError, UnicodeDecodeError, RecursionError):
            continue
        nodes = data.get("nodes") if isinstance(data, dict) else None
        out |= {n["id"] for n in nodes or [] if isinstance(n, dict) and isinstance(n.get("id"), str)}
    return out


def _p(file: str, path: str, code: str, message: str, severity: str = "error") -> dict:
    return M._problem(file, path, code, message, severity)


def _read_one(root: Path, rel: str, where: str, problems: list[dict]) -> bytes | None:
    raw = R.read_capped(Path(root), rel, R.LIMITS["file_bytes"])
    if raw is R.TOO_BIG:
        problems.append(_p(where, "/", "read.too_large", f"over {R.LIMITS['file_bytes']} bytes: not read"))
        return None
    return raw          # None: not there (a plan may leave either file out) or not a regular file


def _check_changes(where: str, raw: bytes, problems: list[dict]) -> dict | None:
    """changes.json: an infra-model v0 file and its "order" (checked by the migration schema's $defs/order)."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        data = None
    order = None
    if isinstance(data, dict) and "order" in data:
        order = data.pop("order")
        for path, why in M.check_schema(order, schema()["$defs"]["order"], "/order", schema()):
            problems.append(_p(where, path, "schema", why))
        raw = json.dumps(data).encode()
    got, found = M.check_file(where, raw)
    problems.extend(found)
    if got is None or any(p["file"] == where and p["severity"] == "error" for p in problems):
        return None
    got["order"] = order or []
    return got


def _check_removals(where: str, raw: bytes, problems: list[dict]) -> dict | None:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        problems.append(dict(_p(where, "/", "json", f"not JSON (line {exc.lineno}, column {exc.colno})"), line=exc.lineno))
        return None
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        problems.append(_p(where, "/", "json", f"not JSON ({type(exc).__name__})"))
        return None
    found = [_p(where, path, "schema", why) for path, why in M.check_schema(data, None, "", schema())]
    if isinstance(data, dict) and isinstance(data.get("edges"), list):
        for i, e in enumerate(data["edges"]):
            node = schema()["$defs"]["id" if isinstance(e, str) else "ends"]
            found.extend(_p(where, path, "schema", why) for path, why in M.check_schema(e, node, f"/edges/{i}", schema()))
    for path, text in M._walk_strings(data, ""):
        for kind in M.secret_findings(text):
            found.append(_p(where, path, f"secret.{kind}", f"holds the shape of a secret ({kind.replace('_', ' ')})"))
    problems.extend(found)
    return None if found else data


class Plan:
    """One plan against the old model's files: its steps, its problems, and the model after any number of steps."""

    def __init__(self, name: str, mig: str, old_files: list[tuple[str, bytes]], changes: dict, removals: dict,
                 problems: list[dict]) -> None:
        self.name, self.dir = name, f"{mig}/{name}"
        self.changes_file, self.removals_file = f"{name}/changes.json", f"{name}/removals.json"
        self.problems = problems
        self.old = []                       # (file name, its object) of the old model's files with no error
        for fname, raw in old_files:
            data, _found = M.check_file(fname, raw)
            if data is not None:
                self.old.append((fname, data))
        old_nodes = {n["id"] for _f, d in self.old for n in d.get("nodes", [])}
        old_groups = {g["id"] for _f, d in self.old for g in d.get("groups", [])}
        old_flows = {f["id"] for _f, d in self.old for f in d.get("flows", [])}
        old_edges = {edge_key(e) for _f, d in self.old for e in d.get("edges", [])}
        cf, rf = self.changes_file, self.removals_file

        # changes: the first of an id is taken, a second is a problem (and left out)
        seen: dict[str, str] = {}
        self.c = {"groups": [], "nodes": [], "edges": [], "flows": []}
        for kind in ("groups", "nodes"):
            for i, item in enumerate(changes.get(kind, [])):
                if item["id"] in seen:
                    problems.append(_p(cf, f"/{kind}/{i}/id", "migration.duplicate",
                                       f"id {item['id']!r} is already in changes ({seen[item['id']]})"))
                    continue
                seen[item["id"]] = f"/{kind}/{i}"
                self.c[kind].append(item)
        keys: dict[str, int] = {}
        for i, e in enumerate(changes.get("edges", [])):
            k = edge_key(e)
            if k in keys:
                problems.append(_p(cf, f"/edges/{i}", "migration.duplicate", f"edge {k!r} is already in changes (/edges/{keys[k]})"))
                continue
            keys[k] = i
            self.c["edges"].append((i, e))
        fl: set[str] = set()
        for i, f in enumerate(changes.get("flows", [])):
            if f["id"] in fl:
                problems.append(_p(cf, f"/flows/{i}/id", "migration.duplicate", f"flow {f['id']!r} is already in changes"))
                continue
            fl.add(f["id"])
            self.c["flows"].append(f)
        self.envs = list(changes.get("environments", []))

        # removals: each named once, of the old model, and not also in changes
        self.r = {"nodes": [], "groups": [], "edges": set(), "flows": set()}
        have = {"nodes": old_nodes, "groups": old_groups, "edges": old_edges, "flows": old_flows}
        in_changes = {"nodes": {n["id"] for n in self.c["nodes"]}, "groups": {g["id"] for g in self.c["groups"]},
                      "edges": set(keys), "flows": fl}
        for kind in ("nodes", "groups", "edges", "flows"):
            named: set[str] = set()
            for i, x in enumerate(removals.get(kind, [])):
                k = x if isinstance(x, str) else f"{x['from']}->{x['to']}"
                what = kind[:-1]
                if k in named:
                    problems.append(_p(rf, f"/{kind}/{i}", "migration.duplicate", f"{what} {k!r} is named twice"))
                    continue
                named.add(k)
                if k in in_changes[kind] or (kind in ("nodes", "groups") and k in seen):
                    problems.append(_p(rf, f"/{kind}/{i}", "migration.both",
                                       f"{what} {k!r} is in changes too: it is replaced, not removed"))
                    continue
                if k not in have[kind]:
                    problems.append(_p(rf, f"/{kind}/{i}", "migration.remove_missing",
                                       f"{what} {k!r} is not in the old model: nothing to remove"))
                    continue
                if kind in ("nodes", "groups"):
                    self.r[kind].append(k)
                else:
                    self.r[kind].add(k)

        # the steps: one node each
        changing = [n["id"] for n in self.c["nodes"]] + self.r["nodes"]
        order: list[str] = []
        for i, nid in enumerate(changes.get("order", [])):
            if nid not in changing:
                problems.append(_p(cf, f"/order/{i}", "migration.order_unknown",
                                   f"{nid!r} is not a node this plan changes or removes"))
            elif nid in order:
                problems.append(_p(cf, f"/order/{i}", "migration.duplicate", f"{nid!r} is in the order twice"))
            else:
                order.append(nid)
        order += [nid for nid in changing if nid not in order]
        removed = set(self.r["nodes"])
        self.steps = [{"index": i + 1, "node": nid,
                       "kind": "remove" if nid in removed else "replace" if nid in old_nodes else "add",
                       "edgesRemoved": [], "edgesAdded": []} for i, nid in enumerate(order)]
        at = {s["node"]: s["index"] for s in self.steps}
        new_nodes = (old_nodes - removed) | {n["id"] for n in self.c["nodes"]}
        n_steps = len(self.steps)
        EDGES = n_steps + 1                 # the "edges" step, when it is needed

        # edges: when each comes and goes (rule 4 and 5 by construction: an old edge goes only when named or an end goes)
        self.edge_in: dict[int, int] = {}        # changes edge (its index in changes) -> the step it comes in at
        added_at: dict[str, int] = {}
        for i, e in self.c["edges"]:
            ends = [x for x in ("from", "to") if e[x] not in new_nodes]
            if ends:
                problems.append(_p(cf, f"/edges/{i}", "migration.edge_end",
                                   "edge end(s) not a node of the new model: " + ", ".join(f"{x}={e[x]!r}" for x in ends)))
                continue
            s = max(at.get(e["from"], 0), at.get(e["to"], 0)) or EDGES
            self.edge_in[i] = s
            added_at[edge_key(e)] = s
        self.edge_out: dict[str, int] = {}      # old edge key -> the step it goes at
        for _f, d in self.old:
            for e in d.get("edges", []):
                k = edge_key(e)
                gone = [at[x] for x in (e["from"], e["to"]) if x in removed]
                if gone:
                    s = min(gone)
                elif k in self.r["edges"]:
                    s = min([at[x] for x in (e["from"], e["to"]) if x in at] or [EDGES])
                elif k in added_at:
                    s = added_at[k]
                else:
                    continue
                self.edge_out[k] = min(s, self.edge_out.get(k, s))
        # groups and flows
        holds: dict[str, list[int]] = {}
        parent = {g["id"]: g.get("parent") for _f, d in self.old for g in d.get("groups", [])}
        parent.update({g["id"]: g.get("parent") for g in self.c["groups"]})
        for n in self.c["nodes"]:
            g, hops = n.get("group"), 0
            while g and hops < 64:
                holds.setdefault(g, []).append(at[n["id"]])
                g, hops = parent.get(g), hops + 1
        self.group_in = {g["id"]: min(holds.get(g["id"]) or [EDGES]) for g in self.c["groups"]}
        need_edges_step = (any(s == EDGES for s in self.edge_in.values()) or any(s == EDGES for s in self.edge_out.values())
                           or any(s == EDGES for s in self.group_in.values())
                           or (not n_steps and (self.r["groups"] or self.c["flows"] or self.r["flows"] or self.envs)))
        if need_edges_step:
            self.steps.append({"index": EDGES, "node": None, "kind": "edges", "edgesRemoved": [], "edgesAdded": []})
        self.last = len(self.steps)
        self.group_in = {g: min(s, self.last) for g, s in self.group_in.items()}
        for i, s in self.edge_in.items():
            self.steps[s - 1]["edgesAdded"].append(edge_key(changes["edges"][i]))
        for k, s in self.edge_out.items():
            self.steps[s - 1]["edgesRemoved"].append(k)
        self.at = at

    def counts(self) -> dict:
        kinds = [s["kind"] for s in self.steps]
        return {"added": kinds.count("add"), "replaced": kinds.count("replace"), "removed": kinds.count("remove"),
                "edgesAdded": sum(len(s["edgesAdded"]) for s in self.steps),
                "edgesRemoved": sum(len(s["edgesRemoved"]) for s in self.steps)}

    def files_at(self, k: int) -> list[tuple[str, bytes]]:
        """The model's files after k steps: the old files less what has gone or been replaced, and the plan's
        changes that have come (in changes' order, so at the last step the plan's file is changes.json as written)."""
        k = max(0, min(k, self.last))
        done = {s["node"] for s in self.steps[:k] if s["node"]}
        replaced = {n["id"] for n in self.c["nodes"] if n["id"] in done}
        groups_in = {g for g, s in self.group_in.items() if s <= k}
        end = k >= self.last and self.last > 0
        gone_groups = set(self.r["groups"]) if end else set()
        gone_flows = (self.r["flows"] | {f["id"] for f in self.c["flows"]}) if end else set()
        out = []
        for fname, d in self.old:
            nd = dict(d)
            nd["nodes"] = [n for n in d.get("nodes", []) if n["id"] not in done]
            nd["groups"] = [g for g in d.get("groups", []) if g["id"] not in groups_in and g["id"] not in gone_groups]
            nd["edges"] = [e for e in d.get("edges", []) if self.edge_out.get(edge_key(e), self.last + 1) > k]
            if "flows" in d:
                nd["flows"] = [f for f in d["flows"] if f["id"] not in gone_flows]
            out.append((fname, json.dumps(nd).encode()))
        if k:
            plan = {"version": 0,
                    "groups": [g for g in self.c["groups"] if g["id"] in groups_in],
                    "nodes": [n for n in self.c["nodes"] if n["id"] in replaced],
                    "edges": [e for i, e in self.c["edges"] if self.edge_in.get(i, self.last + 1) <= k]}
            if self.envs:
                plan["environments"] = self.envs
            if end and self.c["flows"]:
                plan["flows"] = self.c["flows"]
            out.append((self.changes_file, json.dumps(plan).encode()))
        return out

    def model_at(self, k: int) -> tuple[dict, list[dict]]:
        return M.merge(self.files_at(k))


def read_plan(root: Path, mig: str, name: str, old_files: list[tuple[str, bytes]]) -> tuple[Plan | None, list[dict]]:
    """(the plan, its problems) — None when changes.json or removals.json has an error (the plan is left out whole,
    as a model file is) or when it has neither."""
    problems: list[dict] = []
    raws = {}
    for f in FILES:
        raws[f] = _read_one(root, f"{mig}/{name}/{f}", f"{name}/{f}", problems)
    if raws["changes.json"] is None and raws["removals.json"] is None:
        if not problems:
            problems.append(_p(f"{name}/changes.json", "/", "read.unreadable",
                               "a plan needs changes.json or removals.json (regular files)"))
        return None, problems
    changes = _check_changes(f"{name}/changes.json", raws["changes.json"], problems) if raws["changes.json"] is not None \
        else {"order": []}
    removals = _check_removals(f"{name}/removals.json", raws["removals.json"], problems) if raws["removals.json"] is not None \
        else {}
    if changes is None or removals is None:
        return None, problems
    return Plan(name, mig, old_files, changes, removals, problems), problems


def report(root: Path, old_files: list[tuple[str, bytes]], old_problems: list[dict], only: str | None = None,
           infra_dir: str = R.DEFAULT_DIR, words: R.Words = R.DEFAULT_WORDS) -> list[dict] | None:
    """The room's plans as validate infra and the room give them: [{name, dir, ok, problems, steps, counts, model}],
    or None when the room has no plan (the reply then has no "migrations" at all). ``only``: that plan alone (an
    unknown name is a plan with one problem)."""
    mig = folder(root)
    names = plan_names(root, mig)
    if only is not None:
        names = [only] if only in names else []
        if not names:
            p = _p(only, "/", "migration.no_plan", f"no plan {only!r} in {mig}")
            p["short"] = R.short(p, mig, words)
            return [{"name": only, "dir": f"{mig}/{only}", "ok": False, "steps": [], "counts": {}, "problems": [p]}]
    if not names:
        return None
    seen_old = {(p.get("file"), p["code"], p["message"]) for p in old_problems}
    out = []
    for name in names:
        plan, problems = read_plan(root, mig, name, old_files)
        entry = {"name": name, "dir": f"{mig}/{name}", "steps": [], "counts": {}}
        if plan is not None:
            new, found = plan.model_at(plan.last)
            problems.extend(p for p in found if (p.get("file"), p["code"], p["message"]) not in seen_old)   # the new model's own
            entry.update(steps=plan.steps, counts=plan.counts(), model=new)
        for p in problems:          # a plan's file is named from the migrations folder, a model file's from infra.dir
            p["short"] = R.short(p, mig if str(p.get("file", "")).startswith(f"{name}/") else infra_dir, words)
        entry["problems"] = problems
        entry["ok"] = plan is not None and not M.errors(problems)
        out.append(entry)
    return out


def load(root: Path, name: str) -> tuple[Plan | None, list[dict], dict]:
    """(the plan named, its problems, the room's model as room.read gives it) for a reader that needs the model at
    each step (the cost simulator). The plan is None when the room has no such plan or it is left out; the room's
    model {ok: False, …} when the room cannot be read."""
    old = R.read(Path(root), plans=name)
    if not old.get("ok"):
        return None, [], old
    entry = (old.get("migrations") or [{}])[0]
    if not entry.get("ok") and not entry.get("steps"):
        return None, entry.get("problems", []), old
    files, _found = R.read_json_folder(Path(root), old["dir"])
    plan, _problems = read_plan(Path(root), folder(Path(root)), name, files)
    return plan, entry.get("problems", []), old
