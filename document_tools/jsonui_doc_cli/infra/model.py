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
    ("private_key", re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("arn", re.compile(r"(?i)\barn:[a-z0-9-]+:[a-z0-9-]*:")),
    ("url_credentials", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s@]+@")),
    # a scheme with a host or path after it; the scheme alone ("postgresql://", as a doc says which driver) is no value
    ("connection_string", re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|rediss?|amqps?|mssql|sqlserver|oracle|cockroachdb"
        r"|clickhouse|jdbc:[a-z0-9]+)://[^\s'\"]"
        r"|\b(?:Server|Data Source|AccountKey|SharedAccessKey|Password|Pwd)\s*=\s*[^\s;'\"]")),   # a key with a value
    ("access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token", re.compile(
        r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{10,}|\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}"
        r"|\bgithub_pat_[A-Za-z0-9_]{20,}|\bglpat-[A-Za-z0-9_-]{20,}"
        r"|\bxox[abprs]-[A-Za-z0-9-]{10,}|\bAIza[0-9A-Za-z_-]{30,}|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\."
        r"|(?<![A-Za-z0-9/+=])(?=[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=]))(?=[A-Za-z0-9/+]{0,39}[A-Z])"
        r"(?=[A-Za-z0-9/+]{0,39}[a-z])(?=[A-Za-z0-9/+]{0,39}\d)"
        r"[A-Za-z0-9/+]{40}")),   # 40 characters in mixed case with a digit: an AWS secret key (a hex hash is lowercase)
    ("account_id", re.compile(r"(?<![\d-])(?:\d{12}|\d{4}-\d{4}-\d{4})(?![\d-])")),
)
# an IPv4 address: not after a letter, a digit or a dot (v1.25.3.1 is a version), and not before ".<digit>" (1.2.3.4.5);
# a dot after it ends a sentence. 0.0.0.0 and 127.0.0.0/8 (any interface, this machine) are no one's address.
_IPV4 = re.compile(r"(?<![\w.])((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3})(?!\.?\d)")
_IPV6 = re.compile(r"(?<![\w:.])([0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})(?![\w:])")
_INVISIBLE = re.compile(r"[\u00ad\u200b-\u200f\u2060-\u2064\ufeff]")


def _ip_found(text: str) -> bool:
    import ipaddress
    for m in _IPV4.finditer(text):
        ip = m.group(1)
        if ip != "0.0.0.0" and not ip.startswith("127."):
            return True
    for m in _IPV6.finditer(text):
        try:
            ip = ipaddress.IPv6Address(m.group(1))
        except ValueError:
            continue
        if not (ip.is_loopback or ip.is_unspecified):
            return True
    return False


def secret_findings(text: str) -> list[str]:
    """The kinds of secret shapes in one string (empty: none). Characters that do not show (zero-width, soft hyphen)
    are taken out first, so splitting a value with one does not hide it. Used by validate and before display."""
    text = _INVISIBLE.sub("", text)
    out = [kind for kind, rx in SECRET_SHAPES if rx.search(text)]
    if _ip_found(text):
        out.append("ip_address")
    return out


_FIELDS: dict[int, set[str]] = {}


def field_names() -> set[str]:
    """Every field name the schema knows (a key elsewhere is shown masked in a path: it may be anything)."""
    key = id(schema())
    if key in _FIELDS:
        return _FIELDS[key]
    names: set[str] = set()

    def walk(n):
        if isinstance(n, dict):
            names.update((n.get("properties") or {}).keys())
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(schema())
    _FIELDS.clear()
    _FIELDS[key] = names
    return names


def _seg(key: str) -> str:
    """A key as a JSON Pointer segment: a field the schema has, as it is; any other key masked (it may be a value)."""
    return key if key in field_names() and not secret_findings(key) else "<key>"


def _walk_strings(value, path: str):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield f"{path}/{_seg(k)}", k
            yield from _walk_strings(v, f"{path}/{_seg(k)}")
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
    if "const" in node and not (type(value) is type(node["const"]) and value == node["const"]):   # 0.0 and false are not 0
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
                out.append((f"{path}/{_seg(k)}", "is not a field of the infra model v0"))
    return out


# ---------------------------------------------------------------- the passes

def _problem(file: str, path: str, code: str, message: str, severity: str = "error") -> dict:
    return {"file": file, "path": path or "/", "code": code, "message": message, "severity": severity}


def check_file(name: str, raw: bytes) -> tuple[dict | None, list[dict]]:
    """(the file's object, problems) — the object is None when the file has any error (it is left out whole)."""
    problems: list[dict] = []
    try:
        data = json.loads(raw.decode("utf-8"))
    except RecursionError:
        return None, [_problem(name, "/", "json", "nested too deeply to read")]
    except json.JSONDecodeError as exc:
        return None, [dict(_problem(name, "/", "json", f"not JSON (line {exc.lineno}, column {exc.colno})"), line=exc.lineno)]
    except (ValueError, UnicodeDecodeError) as exc:
        return None, [_problem(name, "/", "json", f"not JSON ({type(exc).__name__})")]
    try:
        strings = list(_walk_strings(data, ""))
    except RecursionError:
        return None, [_problem(name, "/", "json", "nested too deeply to read")]
    for path, text in strings:
        for kind in secret_findings(text):
            problems.append(_problem(name, path, f"secret.{kind}",
                                     f"holds the shape of a secret ({kind.replace('_', ' ')}): the model keeps no values; "
                                     "write a name a person reads in its place"))
    try:
        found = check_schema(data)
    except RecursionError:
        return None, problems + [_problem(name, "/", "json", "nested too deeply to read")]
    for path, why in found:
        if path in ("/groups", "/nodes", "/edges") and why.startswith("more than"):
            continue        # the room's limit cuts what is past it (merge, model.too_big): the rest is still drawn
        problems.append(_problem(name, path, "schema", why))
    return (None if problems else data), problems


def _parents_cycle(groups: dict[str, dict]) -> list[str]:
    """The groups on a parent cycle (not those that only lead into one), in the order they were declared."""
    on_cycle: set[str] = set()
    for gid in groups:
        path, cur = [], gid
        while cur in groups and cur not in path and cur not in on_cycle:
            path.append(cur)
            cur = groups[cur].get("parent")
        if cur in path:
            on_cycle.update(path[path.index(cur):])
    return [g for g in groups if g in on_cycle]


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
        problems.append(_problem(name, f"{path}/parent", "group.cycle", f"group {gid!r} is on a parent cycle"))
        groups[gid].pop("parent", None)
    for gid, g in groups.items():
        if g.get("parent") and g["parent"] not in groups:
            name, path = g["_at"]
            problems.append(_problem(name, f"{path}/parent", "group.missing", f"parent {g['parent']!r} is not a group"))
            g.pop("parent")

    def within(item: dict, inside: list[str] | None, name: str, path: str, what: str) -> list[str] | None:
        """The environments an element is drawn in: its own (all when it names none) and only those of what holds
        it (its group, an edge's two ends) — so switching to an environment never draws a part without what holds
        it. Naming one the container is not in is an error; nothing left: the element is left out."""
        own = env_refs(item, name, path)
        if own is None:
            return None
        if inside is None:
            return own
        outside = [e for e in own if e not in inside]
        if outside and item.get("environments") is not None:
            problems.append(_problem(name, f"{path}/environments", "environment.outside",
                                     f"names environment(s) {', '.join(outside)} that {what} is not in"))
        kept = [e for e in own if e in inside]
        if not kept:
            problems.append(_problem(name, path, "environment.none",
                                     f"in no environment {what} is in: left out"))
            return None
        return kept

    # groups, parents first: a group is drawn only where its parent is (and a group whose parent was left out, for
    # its environments or its own errors, loses that parent rather than pointing at nothing)
    effective: dict[str, list[str]] = {}
    out_groups = []
    pending = list(groups)
    while pending:
        progressed = False
        for gid in list(pending):
            g = groups[gid]
            parent = g.get("parent")
            if parent and parent in pending:
                continue
            pending.remove(gid)
            progressed = True
            name, path = g.pop("_at")
            if parent and parent not in effective:
                problems.append(_problem(name, f"{path}/parent", "group.missing",
                                         f"parent {parent!r} was left out: this group has no parent"))
                g.pop("parent")
                parent = None
            refs = within(g, effective.get(parent) if parent else None, name, path, f"its parent {parent!r}")
            if refs is None:
                continue
            effective[gid] = refs
            out_groups.append({**g, "label": g.get("label", gid), "environments": refs})
        if not progressed:      # cannot happen once cycles are cut; a guard against looping
            break
    out_groups = _capped(out_groups, "groups", problems)
    by_id = {g["id"]: g for g in out_groups}
    for g in out_groups:
        if g.get("parent") and g["parent"] not in by_id:      # its parent was past the limit
            g.pop("parent")

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
    out_nodes = []
    for nid, n in nodes.items():
        name, path = n.pop("_at")
        if n.get("group") and n["group"] not in by_id:
            problems.append(_problem(name, f"{path}/group", "group.missing", f"group {n['group']!r} is not a group"))
            n.pop("group")
        gid = n.get("group")
        refs = within(n, by_id[gid]["environments"] if gid else None, name, path, f"its group {gid!r}")
        if refs is None:
            continue
        out_nodes.append({**n, "label": n.get("label", nid), "count": n.get("count", 1),
                          "providerResolved": n.get("provider") or group_provider(gid),
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
        both = [x for x in kept_nodes[e["from"]]["environments"] if x in kept_nodes[e["to"]]["environments"]]
        refs = within(e, both, name, path, "both its ends")
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
    """The room's model together keeps the schema's limit (groups 1,000, nodes 5,000, edges 10,000), one file or
    several: what is past it is left out, with one problem, and the rest is drawn."""
    cap = schema()["properties"][kind]["maxItems"]
    if len(items) <= cap:
        return items
    problems.append(_problem("", f"/{kind}", "model.too_big",
                             f"the room's files hold {len(items)} {kind} together; only the first {cap} are shown"))
    return items[:cap]


def errors(problems: list[dict]) -> list[dict]:
    return [p for p in problems if p["severity"] == "error"]
