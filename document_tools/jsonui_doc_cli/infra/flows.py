"""The flows of the infra model (the server room ticket's item 7): what a request, a device, a schedule or an event sets
going through the system, step by step — checked against the merged model and normalized for the page.

A flow starts at any node (``start``) and its steps name nodes and edges as the load definitions do (``node``; ``edge``,
or ``from`` and ``to``), so a load can be drawn from a flow later. One step is one of:

- a move along an edge (``edge``, or ``from`` and ``to``): it leaves the node the flow is at, the way the edge's
  direction allows (out: from → to, in: to → from, both: either). A ``response`` goes back along the edge it came by,
  whatever the direction;
- a step at a node (``node``): the node the flow is at;
- a branch (``branch``): the flow stops and a person chooses; a choice's steps go on from there, then the flow goes on
  after the branch (every such choice must end at one node), or it goes to another flow (``goto``) or to a later step
  of this flow (``join``). ``default`` is taken when the flow plays by itself;
- lanes side by side (``parallel``): each from where the flow is; the flow stays at that node and goes on when all
  are done.

Every path is walked (each (step, position) once), so a step reached by two paths must be reached at one node. A flow
with an error is left out, the file and the other flows stay; a problem names the place and the kind, never a value.
A goto whose flow starts elsewhere is a warning (the page jumps there). A loop the flows close by their defaults alone
would play forever by itself: an error on the flows in it.
"""
from __future__ import annotations

MAX_DEPTH = 4          # branches and lanes inside each other


def _problem(file: str, path: str, code: str, message: str, severity: str = "error") -> dict:
    return {"file": file, "path": path or "/", "code": code, "message": message, "severity": severity}


def _move_ends(step: dict) -> bool:
    return "edge" in step or "from" in step or "to" in step


def _kinds(step: dict) -> list[str]:
    out = [k for k in ("node", "branch", "parallel") if k in step]
    if _move_ends(step):
        out.append("move")
    return out


class _Flow:
    """One flow being checked: its problems, each step's position, the gotos its defaults take."""

    def __init__(self, f: dict, name: str, path: str, nodes: dict, edges: list[dict], envs: list[str]):
        self.f, self.name, self.path, self.nodes, self.envs = f, name, path, nodes, envs
        self.by_id = {e["id"]: e for e in edges if e.get("id")}
        self.edges = edges
        self.problems: list[dict] = []
        self.seen: set[tuple[int, str]] = set()
        self.at: dict[int, tuple[str, str | None]] = {}     # id(step) -> (from, to) the walk found it at
        self.top_ids = {s["id"]: i for i, s in enumerate(f["steps"]) if s.get("id")}
        self.gotos: list[tuple[str, bool, str, str]] = []   # (flow id, taken by default, the choice's path, where it leaves)
        self.wrong = False

    def err(self, path: str, code: str, message: str, severity: str = "error") -> None:
        p = _problem(self.name, path, code, message, severity)
        if p not in self.problems:
            self.problems.append(p)
        if severity == "error":
            self.wrong = True

    def node_ok(self, nid: str, path: str) -> bool:
        if nid in self.nodes and set(self.envs) & set(self.nodes[nid]["environments"]):
            return True
        self.err(path, "flow.node.missing", f"names a node that is not drawn with this flow: {nid!r}")
        return False

    def edge_between(self, a: str, b: str, back: bool) -> dict | None:
        for e in self.edges:
            if not set(self.envs) & set(e["environments"]):
                continue
            d = e.get("direction", "out")
            if e["from"] == a and e["to"] == b and (d in ("out", "both") or back):
                return e
            if e["from"] == b and e["to"] == a and (d in ("in", "both") or back):
                return e
        return None

    def move(self, step: dict, pos: str, path: str) -> str | None:
        back = step.get("action") == "response"
        if "edge" in step:
            if "from" in step or "to" in step:
                self.err(path, "flow.step.kind", "names an edge and its ends both: one of edge, or from and to")
                return None
            e = self.by_id.get(step["edge"])
            if e is None or not set(self.envs) & set(e["environments"]):
                self.err(f"{path}/edge", "flow.edge.missing", f"names an edge that is not drawn with this flow: {step['edge']!r}")
                return None
            d = e.get("direction", "out")
            if pos == e["from"] and (d in ("out", "both") or back):
                return e["to"]
            if pos == e["to"] and (d in ("in", "both") or back):
                return e["from"]
            self.err(path, "flow.discontinuous", f"the edge does not leave the node the flow is at ({pos!r})")
            return None
        if "from" not in step or "to" not in step:
            self.err(path, "flow.step.kind", "a move names both from and to")
            return None
        if not (self.node_ok(step["from"], f"{path}/from") and self.node_ok(step["to"], f"{path}/to")):
            return None
        if step["from"] != pos:
            self.err(f"{path}/from", "flow.discontinuous", f"leaves {step['from']!r}, but the flow is at {pos!r}")
            return None
        if self.edge_between(step["from"], step["to"], back) is None:
            self.err(path, "flow.edge.missing", f"no edge takes the flow from {step['from']!r} to {step['to']!r}")
            return None
        return step["to"]

    def walk(self, steps: list, i: int, pos: str, path: str, cont: list, depth: int, by_default: bool, top: int | None) -> None:
        """Walk steps[i:] from pos, then each continuation (list, index, path, top, depth) in turn. top: the index in the flow's
        own steps of the step being walked, or of the one a nested step is inside (a join must go past it)."""
        while True:
            if i >= len(steps):
                if not cont:
                    return
                steps, i, path, top, depth = cont[0]
                cont = cont[1:]
                continue
            if depth == 0:
                top = i
            step, here = steps[i], f"{path}/{i}"
            key = (id(step), pos)
            if key in self.seen:
                return
            self.seen.add(key)
            prior = self.at.get(id(step))
            if prior is not None and prior[0] != pos:
                self.err(here, "flow.paths_disagree", "reached by two paths at two different nodes")
                return
            kinds = _kinds(step)
            if len(kinds) != 1:
                self.err(here, "flow.step.kind", "one of: edge or from and to, node, branch, parallel"
                         + (" (none given)" if not kinds else f" (given {', '.join(kinds)})"))
                return
            kind = kinds[0]
            if kind == "move":
                nxt = self.move(step, pos, here)
                if nxt is None:
                    return
                self.at[id(step)] = (pos, nxt)
                pos, i = nxt, i + 1
                continue
            if kind == "node":
                if not self.node_ok(step["node"], f"{here}/node"):
                    return
                if step["node"] != pos:
                    self.err(f"{here}/node", "flow.discontinuous", f"at {step['node']!r}, but the flow is at {pos!r}")
                    return
                self.at[id(step)] = (pos, None)
                i += 1
                continue
            if depth >= MAX_DEPTH:
                self.err(here, "flow.too_deep", f"branches and lanes nest deeper than {MAX_DEPTH}")
                return
            self.at[id(step)] = (pos, None)
            if kind == "parallel":
                for k, lane in enumerate(step["parallel"]):
                    self.walk(lane, 0, pos, f"{here}/parallel/{k}", [], depth + 1, by_default, top)
                i += 1
                continue
            # a branch
            b = step["branch"]
            ids = [c["id"] for c in b["choices"]]
            if len(set(ids)) != len(ids):
                self.err(f"{here}/branch/choices", "flow.choice.duplicate", "two choices have one id")
            if b.get("default") is not None and b["default"] not in ids:
                self.err(f"{here}/branch/default", "flow.default.missing", "the default names no choice")
            rest = [(steps, i + 1, path, top, depth)] + cont
            for k, c in enumerate(b["choices"]):
                cp = f"{here}/branch/choices/{k}"
                if "goto" in c and "join" in c:
                    self.err(cp, "flow.choice.kind", "a choice goes on by one of: its steps, goto, join")
                    continue
                taken = by_default and b.get("default") == c["id"]
                sub = c.get("steps") or []
                if "goto" in c:
                    end = self._end(sub, pos, f"{cp}/steps", depth + 1, taken, top)
                    if end is not None:
                        self.gotos.append((c["goto"], taken, cp, end))
                    continue
                if "join" in c:
                    j = self.top_ids.get(c["join"])
                    if j is None:
                        self.err(f"{cp}/join", "flow.join.missing", "joins no step of this flow's own steps")
                        continue
                    if top is not None and j <= top:
                        self.err(f"{cp}/join", "flow.join.backward", "joins a step that is not after the branch")
                        continue
                    after = [(self.f["steps"], j, f"{self.path}/steps", j, 0)]
                else:
                    after = rest
                self.walk(sub, 0, pos, f"{cp}/steps", after, depth + 1, taken, top)
            return


    def _end(self, steps: list, pos: str, path: str, depth: int, by_default: bool, top: int | None) -> str | None:
        """Where a goto's choice leaves from: the node its own steps end at (walked as any other), or pos."""
        self.walk(steps, 0, pos, path, [], depth, by_default, top)
        for s in reversed(steps):
            where = self.at.get(id(s))
            if where is None:
                return None                 # a step its walk could not place: already said
            return where[1] if where[1] is not None else where[0]
        return pos


def resolve(flows: list[tuple[str, int, dict]], nodes: dict[str, dict], edges: list[dict], env_ids: list[str],
            problems: list[dict]) -> list[dict]:
    """The flows the page may play: each checked against the merged model (nodes, edges) and normalized; the problems
    of each appended to problems. flows: (file, index in its file, the flow as written)."""
    out, owner = [], {}
    checked: list[tuple[_Flow, dict]] = []
    for name, i, f in flows:
        path = f"/flows/{i}"
        if f["id"] in owner:
            problems.append(_problem(name, f"{path}/id", "flow.id.duplicate", f"flow {f['id']!r} is already in {owner[f['id']]}"))
            continue
        owner[f["id"]] = f"{name} {path}"
        want = f.get("environments") or list(env_ids)
        unknown = [e for e in want if e not in env_ids]
        if unknown:
            problems.append(_problem(name, f"{path}/environments", "environment.missing",
                                     f"names environment(s) not declared: {', '.join(unknown)}"))
            continue
        if f.get("schedule") is not None and f.get("trigger") != "schedule":
            problems.append(_problem(name, f"{path}/schedule", "flow.schedule.trigger", "a schedule is written only with trigger schedule"))
            continue
        start = nodes.get(f["start"])
        envs = [e for e in want if start is not None and e in start["environments"]]
        F = _Flow(f, name, path, nodes, edges, envs)
        if start is None or not envs:
            F.err(f"{path}/start", "flow.node.missing", f"starts at a node that is not drawn with this flow: {f['start']!r}")
        else:
            F.walk(f["steps"], 0, f["start"], f"{path}/steps", [], 0, True, None)
        checked.append((F, f))
    starts = {f["id"]: f["start"] for F, f in checked if not F.wrong}
    for F, f in checked:
        for target, _taken, cp, end in F.gotos:
            if target not in starts:
                F.err(f"{cp}/goto", "flow.goto.missing", f"goes to a flow that is not drawn: {target!r}")
            elif starts[target] != end:
                F.err(f"{cp}/goto", "flow.goto.jump", f"the flow is at {end!r} and {target!r} starts elsewhere: the page jumps there",
                      "warning")
    # a loop closed by defaults alone would play forever by itself
    by_default = {f["id"]: [t for t, taken, _cp, _end in F.gotos if taken] for F, f in checked}
    looping: set[str] = set()
    for fid in by_default:
        trail, cur = [], fid
        while cur in by_default and cur not in trail:
            trail.append(cur)
            nxt = by_default[cur]
            cur = nxt[0] if nxt else None
        if cur is not None and cur in trail:
            looping.update(trail[trail.index(cur):])
    for F, f in checked:
        if f["id"] in looping:
            F.err(f"{F.path}", "flow.default_cycle", "its defaults go round a loop of flows: played by itself it never ends")
    for F, f in checked:
        problems.extend(F.problems)
        if F.wrong:
            continue
        out.append({**f, "label": f.get("label", f["id"]), "trigger": f.get("trigger", "user"), "environments": F.envs,
                    "steps": _normalized(f["steps"], F.at)})
    return out


def _normalized(steps: list, at: dict) -> list:
    """The steps as written, each move with the ends the walk took it by (from, to) and each step with where it is."""
    out = []
    for s in steps:
        n = dict(s)
        where = at.get(id(s))
        if where is not None:
            if _move_ends(s):
                n["from"], n["to"] = where
            else:
                n["at"] = where[0]
        if "branch" in s:
            n["branch"] = {**s["branch"], "choices": [{**c, **({"steps": _normalized(c["steps"], at)} if c.get("steps") else {})}
                                                      for c in s["branch"]["choices"]]}
        if "parallel" in s:
            n["parallel"] = [_normalized(lane, at) for lane in s["parallel"]]
        out.append(n)
    return out
