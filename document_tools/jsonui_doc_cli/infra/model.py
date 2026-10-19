"""The infra model v0: validate a room's declared infrastructure and merge its files into one model.

The contract is infra-model.v0.schema.json next to this file (JSON Schema 2020-12) and the boundary document
docs/plans/2026-10-20-jui-viz-server-room-boundary.md. Nothing here keeps its own copy of the vocabularies or the
limits: ``check_schema`` walks the schema file itself (the subset of JSON Schema it uses: type, const, enum, pattern,
maxLength, minimum, maximum, minItems, maxItems, uniqueItems, required, additionalProperties false, local $ref), so a
word added to the schema is accepted here the moment it is written there.

Three passes, one problem list:

1. per file: JSON, the schema, and the shapes of secrets (``secret_findings``: ARN, an account id, an IP address, a
   connection string, credentials in a URL, a private key, an access key or token). A file with any error is left
   out whole — a file holding a secret's shape is never handed on, not even the rest of it;
2. across the files that passed: environments merged by id (the same id twice must say the same), ids unique among
   groups and nodes, every reference resolved (parent, group, edge ends, environments), no parent cycle. An element
   that names what is not there is left out (an edge with a missing end, a node in a missing group goes to no group);
3. normalized for the display: label defaults to the id, count to 1, environments to every environment, fold by
   category, managed_by "iac", direction "out"; one implicit environment "default" when none is declared. Every
   group and node gets providerResolved (its own provider, else the nearest enclosing group's; a "logical" group
   gives none), and every edge crossProvider (its two ends' providers known and different). The room's model
   together keeps the per-file limits (nodes 5,000, edges 10,000; the target size is 2,000 and 5,000).

A problem never carries the value it found (a message names the place and the kind only).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("infra-model.v0.schema.json")
FOLDED_BY_DEFAULT = ("security.iam", "security.policy", "monitoring.alarm")
IMPLICIT_ENV = {"id": "default", "label": "default", "kind": "other"}

_SCHEMA: list[dict] = []


def schema() -> dict:
    if not _SCHEMA:
        _SCHEMA.append(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    return _SCHEMA[0]


def vocabulary(name: str) -> list[str]:
    """An enum of the schema by its $defs name (category) or a property path (group.kind, environment.kind)."""
    defs = schema()["$defs"]
    if "." in name:
        d, prop = name.split(".", 1)
        return list(defs[d]["properties"][prop]["enum"])
    return list(defs[name]["enum"])


# ---------------------------------------------------------------- 1. the shapes of secrets

SECRET_SHAPES: tuple[tuple[str, re.Pattern], ...] = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("arn", re.compile(r"(?i)\barn:[a-z0-9-]+:[a-z0-9-]*:")),
    ("url_credentials", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s@]+@")),
    ("connection_string", re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|rediss?|amqps?|mssql|sqlserver|oracle|cockroachdb"
        r"|clickhouse|jdbc:[a-z0-9]+)://|\b(?:Server|Data Source|AccountKey|SharedAccessKey|Password|Pwd)\s*=")),
    ("access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token", re.compile(
        r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{10,}|\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}"
        r"|\bxox[abprs]-[A-Za-z0-9-]{10,}|\bAIza[0-9A-Za-z_-]{30,}|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.")),
    ("ip_address", re.compile(r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")),
    ("account_id", re.compile(r"(?<!\d)\d{12}(?!\d)")),
)


def secret_findings(text: str) -> list[str]:
    """The kinds of secret shapes in one string (empty: none). Used by validate and by jui viz before display."""
    return [kind for kind, rx in SECRET_SHAPES if rx.search(text)]


def _walk_strings(value, path: str):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield f"{path}/{k}", k
            yield from _walk_strings(v, f"{path}/{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk_strings(v, f"{path}/{i}")


# ---------------------------------------------------------------- 1. the schema, walked from its own file

def _type_ok(t: str, v) -> bool:
    return {"object": isinstance(v, dict), "array": isinstance(v, list), "string": isinstance(v, str),
            "integer": isinstance(v, int) and not isinstance(v, bool), "boolean": isinstance(v, bool)}.get(t, False)


def check_schema(value, node: dict | None = None, path: str = "") -> list[tuple[str, str]]:
    """(path, why) for each place ``value`` breaks the schema (the root one when ``node`` is None)."""
    node = schema() if node is None else node
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[1]
        return check_schema(value, schema()["$defs"][name], path)
    out: list[tuple[str, str]] = []
    if "const" in node and value != node["const"]:
        return [(path or "/", f"must be {json.dumps(node['const'])}")]
    if "enum" in node and value not in node["enum"]:
        return [(path or "/", "must be one of " + ", ".join(map(str, node["enum"])))]
    t = node.get("type")
    if t and not _type_ok(t, value):
        return [(path or "/", f"must be {'an' if t[0] in 'aeiou' else 'a'} {t}")]
    if isinstance(value, str):
        if "maxLength" in node and len(value) > node["maxLength"]:
            out.append((path, f"longer than {node['maxLength']} characters"))
        if "pattern" in node and not re.search(node["pattern"], value):
            out.append((path, "does not have the allowed form"))
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in node and value < node["minimum"]:
            out.append((path, f"below {node['minimum']}"))
        if "maximum" in node and value > node["maximum"]:
            out.append((path, f"above {node['maximum']}"))
    if isinstance(value, list):
        if "minItems" in node and len(value) < node["minItems"]:
            out.append((path, f"needs at least {node['minItems']} item(s)"))
        if "maxItems" in node and len(value) > node["maxItems"]:
            out.append((path, f"more than {node['maxItems']} items"))
        if node.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            out.append((path, "has the same item twice"))
        for i, v in enumerate(value[:10_000]):
            out.extend(check_schema(v, node.get("items", {}), f"{path}/{i}"))
    if isinstance(value, dict):
        props = node.get("properties", {})
        for k in node.get("required", []):
            if k not in value:
                out.append((f"{path}/{k}", "is required"))
        for k, v in value.items():
            if k in props:
                out.extend(check_schema(v, props[k], f"{path}/{k}"))
            elif node.get("additionalProperties") is False:
                out.append((f"{path}/{k}", "is not a field of the infra model v0"))
    return out


# ---------------------------------------------------------------- the passes

def _problem(file: str, path: str, code: str, message: str, severity: str = "error") -> dict:
    return {"file": file, "path": path or "/", "code": code, "message": message, "severity": severity}


def check_file(name: str, raw: bytes) -> tuple[dict | None, list[dict]]:
    """(the file's object, problems) — the object is None when the file has any error (it is left out whole)."""
    problems: list[dict] = []
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return None, [_problem(name, "/", "json", f"not JSON ({type(exc).__name__})")]
    for path, text in _walk_strings(data, ""):
        for kind in secret_findings(text):
            problems.append(_problem(name, path, f"secret.{kind}",
                                     f"holds the shape of a secret ({kind.replace('_', ' ')}): the model keeps no values; "
                                     "write a name a person reads in its place"))
    for path, why in check_schema(data):
        problems.append(_problem(name, path, "schema", why))
    return (None if problems else data), problems


def _parents_cycle(groups: dict[str, dict]) -> list[str]:
    bad = []
    for gid in groups:
        seen, cur = set(), gid
        while cur in groups and groups[cur].get("parent"):
            if cur in seen:
                bad.append(gid)
                break
            seen.add(cur)
            cur = groups[cur]["parent"]
    return bad


def merge(files: list[tuple[str, bytes]]) -> tuple[dict, list[dict]]:
    """The room's model from its files (name, bytes) in the given order, and every problem. The model is what the
    display may show: only files without errors, only elements whose references resolve, normalized."""
    problems: list[dict] = []
    envs: dict[str, dict] = {}
    env_file: dict[str, str] = {}
    groups: dict[str, dict] = {}
    nodes: dict[str, dict] = {}
    edges: list[tuple[str, int, dict]] = []
    owner: dict[str, str] = {}
    used: list[str] = []
    for name, raw in files:
        data, found = check_file(name, raw)
        problems.extend(found)
        if data is None:
            continue
        used.append(name)
        for i, e in enumerate(data.get("environments", [])):
            prev = envs.get(e["id"])
            if prev is not None and prev != e:
                problems.append(_problem(name, f"/environments/{i}", "environment.conflict",
                                         f"environment {e['id']!r} is declared differently in {env_file[e['id']]}"))
                continue
            envs[e["id"]], env_file[e["id"]] = e, name
        for kind, bucket in (("groups", groups), ("nodes", nodes)):
            for i, item in enumerate(data.get(kind, [])):
                if item["id"] in owner:
                    problems.append(_problem(name, f"/{kind}/{i}/id", "id.duplicate",
                                             f"id {item['id']!r} is already used in {owner[item['id']]}"))
                    continue
                owner[item["id"]] = f"{name} /{kind}/{i}"
                bucket[item["id"]] = dict(item, _at=(name, f"/{kind}/{i}"))
        for i, e in enumerate(data.get("edges", [])):
            edges.append((name, i, dict(e)))
    env_list = list(envs.values()) or [dict(IMPLICIT_ENV)]
    env_ids = [e["id"] for e in env_list]

    def env_refs(item: dict, name: str, path: str) -> list[str] | None:
        refs = item.get("environments")
        if refs is None:
            return list(env_ids)
        missing = [r for r in refs if r not in env_ids]
        if missing or not envs:
            problems.append(_problem(name, f"{path}/environments", "environment.missing",
                                     f"names environment(s) not declared: {', '.join(missing or refs)}"))
            return None
        return [r for r in env_ids if r in refs]

    for gid in _parents_cycle(groups):
        name, path = groups[gid]["_at"]
        problems.append(_problem(name, f"{path}/parent", "group.cycle", f"group {gid!r} is its own ancestor"))
        groups[gid].pop("parent", None)
    out_groups = []
    for gid, g in groups.items():
        name, path = g.pop("_at")
        if g.get("parent") and g["parent"] not in groups:
            problems.append(_problem(name, f"{path}/parent", "group.missing", f"parent {g['parent']!r} is not a group"))
            g.pop("parent")
        refs = env_refs(g, name, path)
        if refs is None:
            continue
        out_groups.append({**g, "label": g.get("label", gid), "environments": refs})
    by_id = {g["id"]: g for g in out_groups}

    def group_provider(gid: str | None, depth: int = 0) -> str:
        g = by_id.get(gid) if gid else None
        if g is None or depth > len(by_id):
            return ""
        if g.get("provider"):
            return g["provider"]
        if g["kind"] == "logical":                 # a group of the system's own: it gives what it holds no provider
            return ""
        return group_provider(g.get("parent"), depth + 1)
    for g in out_groups:
        g["providerResolved"] = group_provider(g["id"])
    kept_groups = set(by_id)
    out_nodes = []
    for nid, n in nodes.items():
        name, path = n.pop("_at")
        if n.get("group") and n["group"] not in kept_groups:
            problems.append(_problem(name, f"{path}/group", "group.missing", f"group {n['group']!r} is not a group"))
            n.pop("group")
        refs = env_refs(n, name, path)
        if refs is None:
            continue
        out_nodes.append({**n, "label": n.get("label", nid), "count": n.get("count", 1),
                          "providerResolved": n.get("provider") or group_provider(n.get("group")),
                          "managed_by": n.get("managed_by", "iac"),
                          "fold": n.get("fold", n["category"] in FOLDED_BY_DEFAULT), "environments": refs})
    out_nodes = _capped(out_nodes, "nodes", problems)
    kept_nodes = {n["id"]: n for n in out_nodes}
    out_edges = []
    for name, i, e in edges:
        path = f"/edges/{i}"
        missing = [end for end in ("from", "to") if e[end] not in kept_nodes]
        if missing:
            problems.append(_problem(name, path, "edge.missing",
                                     "edge end(s) not a node: " + ", ".join(f"{m}={e[m]!r}" for m in missing)))
            continue
        refs = env_refs(e, name, path)
        if refs is None:
            continue
        pf, pt = kept_nodes[e["from"]]["providerResolved"], kept_nodes[e["to"]]["providerResolved"]
        out_edges.append({**e, "direction": e.get("direction", "out"), "environments": refs,
                          "crossProvider": bool(pf and pt and pf != pt)})
    out_edges = _capped(out_edges, "edges", problems)
    model = {"version": 0, "files": used,
             "environments": [{"id": e["id"], "label": e.get("label", e["id"]), "kind": e.get("kind", "other")} for e in env_list],
             "groups": out_groups, "nodes": out_nodes, "edges": out_edges}
    return model, problems


def _capped(items: list[dict], kind: str, problems: list[dict]) -> list[dict]:
    """The room's model together keeps the schema's per-file limit (nodes 5,000, edges 10,000): what is past it is left
    out, with one problem."""
    cap = schema()["properties"][kind]["maxItems"]
    if len(items) <= cap:
        return items
    problems.append(_problem("", f"/{kind}", "model.too_big",
                             f"the room's files hold {len(items)} {kind} together; only the first {cap} are shown"))
    return items[:cap]


def errors(problems: list[dict]) -> list[dict]:
    return [p for p in problems if p["severity"] == "error"]
