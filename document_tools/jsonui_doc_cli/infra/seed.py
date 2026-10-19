"""Seed: draft a room's infra model (docs/infra) from what the project already says — IaC, config files, then code.

Boundary: docs/plans/2026-10-20-jui-viz-server-room-boundary.md; the research's §3e (the hybrid) and §4.2 (the order of
the inputs, by how common they are). The draft is a starting point for a person or an agent to edit; it is never the
display's source by itself: it is written to ``<infra.dir>/seed/`` (a folder below the model's, which neither jui viz
nor ``validate infra`` reads) and a person moves what they keep into the model's folder.

What it reads, in the research's order:

1. Docker Compose (the environment ``local``);
2. Terraform / OpenTofu (``*.tf`` and ``*.tf.json``: several providers in one configuration; the state is never read);
3. Kubernetes manifests (a Helm template is reported, not rendered);
4. CloudFormation / SAM templates and a synthesized CDK (``cdk.out/*.template.json``);
5. Cloudflare wrangler (``wrangler.toml`` / ``.json`` / ``.jsonc``: its bindings are the edges);
6. firebase.json, vercel.json, netlify.toml, serverless.yml, fly.toml, render.yaml, app.yaml (App Engine);
7. Bicep (Pulumi needs a stack export and is reported, not read);
8. deploy workflows (hints) and code: SDK imports and the names of environment variables (Python, JavaScript /
   TypeScript; ``.env.example`` and the like by name only — a ``.env`` holds values and is never read).

What it never does:

- read Terraform state (``*.tfstate``), variable values (``*.tfvars``) or ``.env`` files — they hold values in plain
  text; they are counted in the report as skipped;
- write a value: an ARN, an account id, an IP address or CIDR block, a connection string, a key or token. Labels are
  ids, resource names and the names of environment variables. Every string goes through ``model.secret_findings``
  and the finished draft through ``model.check_file`` and ``model.merge``: a draft with any error is not written;
- disagree with ``check kind=infra``: what each IaC resource is, and the ``iac`` address a node holds, come from
  iac_tables.py — the one table check reads too — so a draft taken as it is compares clean with check
  (docs/bugs/2026-10-20-jui-infra-seed-and-check-tables-disagree.md);
- drop an input quietly: what could not be matched is reported per provider (``unmatched``), what is deliberately not
  drawn (a resource that is part of another, like a policy attachment or a DNS record) is counted per provider and
  type (``notDrawn``), and what was not read is listed (``skipped``).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath

from . import code_hints as C
from . import iac_tables as T
from . import model as M

FILE_CAP = 2_000_000          # one input file, bytes
WALK_CAP = 200_000            # files looked at by name
CODE_FILES_CAP = 20_000       # code files read
LIST_CAP = 200                # items listed per provider in the report (the count is always whole)
DRAFT_NAME = "draft.json"
REPORT_NAME = "seed-report.json"

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".terraform", ".terragrunt-cache", "vendor", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", ".nuxt", ".svelte-kit", "target", "Pods", "DerivedData", ".gradle", "coverage", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages", ".idea", ".vscode", ".serverless", ".aws-sam",
    ".wrangler", ".vercel", ".netlify", ".firebase", "bower_components", ".cache", "tmp",
}
KEEP_HIDDEN_DIRS = {".github"}

ENV_LOCAL = {"id": "local", "label": "local (Docker Compose)", "kind": "local"}
ENV_DEPLOYED = {"id": "deployed", "label": "deployed (seed: split into the real environments)", "kind": "other"}

ID_RX = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
REL_RX = re.compile(M.schema()["$defs"]["relPath"]["pattern"])
SERVICE_RX = re.compile(M.schema()["$defs"]["node"]["properties"]["service"]["pattern"])
PROVIDER_RX = re.compile(M.schema()["$defs"]["provider"]["pattern"])
REGION_RX = re.compile(M.schema()["$defs"]["group"]["properties"]["region"]["pattern"])
FOLDED = set(M.FOLDED_BY_DEFAULT)


def read_text(path: Path) -> str | None:
    """The one place an input file is read (tests watch it). None: a symlink, not a regular file, over FILE_CAP, or
    unreadable."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > FILE_CAP:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# ================================================================ the vocabulary of the inputs

# What an IaC resource is (its provider, category and service, or a part of another) and the iac address a node holds
# come from iac_tables.py only — the one table seed and check share (boundary §3, §6). Seed spells no IaC type here.

# What code says (SDK imports, AWS clients, the names of environment variables) comes from code_hints.py only — the one
# copy check reads too. Seed keeps no SDK or environment table.


# ================================================================ the draft being built

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-._")
    return s[:56].rstrip("-._") or "x"


class Draft:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.ids: set[str] = set()
        self.groups: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self.origin: dict[str, str] = {}          # id -> local / deployed / any
        self.edges: dict[tuple[str, str], dict] = {}
        self.unmatched: dict[str, list[dict]] = {}
        self.not_drawn: dict[str, dict[str, int]] = {}
        self.skipped: list[dict] = []
        self.notes: list[str] = []
        self.inputs: dict[str, list[str]] = {}
        self.withheld = 0
        self.by_key: dict[tuple, str] = {}

    # ---- values never leave: every string passes here
    def safe(self, text, fallback: str | None = None):
        if text is None:
            return fallback
        text = str(text)
        if M.secret_findings(text):
            self.withheld += 1
            return fallback
        return text

    def new_id(self, base: str) -> str:
        b = _slug(base)
        nid, k = b, 2
        while nid in self.ids:
            nid, k = f"{b}-{k}", k + 1
        self.ids.add(nid)
        return nid

    def input(self, kind: str, rel: str) -> None:
        self.inputs.setdefault(kind, []).append(rel)

    def miss(self, provider: str, file: str, what: str, why: str) -> None:
        self.unmatched.setdefault(provider or "(unknown)", []).append(
            {"file": file, "what": self.safe(what, "(withheld: value-shaped)"), "why": why})

    def part(self, provider: str, what: str) -> None:
        d = self.not_drawn.setdefault(provider, {})
        d[what] = d.get(what, 0) + 1

    def top_group(self, provider: str, origin: str = "deployed") -> str:
        key = ("top", provider)
        if key not in self.by_key:
            gid = self.new_id(f"{provider}-{T.TOP_GROUP_KIND.get(provider, 'account')}")
            self.groups[gid] = {"id": gid, "kind": T.TOP_GROUP_KIND.get(provider, "account"), "provider": provider,
                                "label": f"{provider} ({T.TOP_GROUP_KIND.get(provider, 'account')})"}
            self.origin[gid] = origin
            self.by_key[key] = gid
        return self.by_key[key]

    def external_group(self) -> str:
        key = ("external",)
        if key not in self.by_key:
            gid = self.new_id("external")
            self.groups[gid] = {"id": gid, "kind": "logical", "label": "External services"}
            self.origin[gid] = "any"
            self.by_key[key] = gid
        return self.by_key[key]

    def add_group(self, key: tuple, base: str, kind: str, provider: str | None, label: str, parent: str | None,
                  origin: str = "deployed", **extra) -> str:
        if key in self.by_key:
            return self.by_key[key]
        gid = self.new_id(base)
        g = {"id": gid, "kind": kind, "label": self.safe(label, gid)}
        if provider:
            g["provider"] = provider
        if parent:
            g["parent"] = parent
        g.update({k: v for k, v in extra.items() if v is not None})
        self.groups[gid] = g
        self.origin[gid] = origin
        self.by_key[key] = gid
        return gid

    def add_node(self, key: tuple, base: str, category: str, provider: str | None, service: str | None, label: str,
                 group: str | None, file: str, pattern: str | None = None, line: int | None = None,
                 iac: str | None = None, origin: str = "deployed", **extra) -> str:
        if key in self.by_key:
            nid = self.by_key[key]
            self.evidence(nid, file, pattern, line)
            if iac:
                self.add_iac(nid, iac)
            return nid
        nid = self.new_id(base)
        n = {"id": nid, "category": category, "label": self.safe(label, nid)}
        if provider and PROVIDER_RX.match(provider):
            n["provider"] = provider
        if service and SERVICE_RX.match(service):
            n["service"] = service
        if group:
            n["group"] = group
        for k, v in extra.items():
            v = self.safe(v) if isinstance(v, str) else v
            if v is not None:
                n[k] = v
        self.nodes[nid] = n
        self.origin[nid] = origin
        self.by_key[key] = nid
        if iac:
            self.add_iac(nid, iac)
        self.evidence(nid, file, pattern, line)
        return nid

    def add_iac(self, nid: str, iac: str) -> None:
        iac = self.safe(iac)
        lst = self.nodes[nid].setdefault("iac", [])
        if iac and iac not in lst and len(lst) < 50 and len(iac) <= 300:
            lst.append(iac)

    def evidence(self, nid: str, file: str, pattern: str | None, line: int | None) -> None:
        if not REL_RX.match(file or ""):
            return
        ev = {"file": file}
        p = self.safe(pattern)
        if p:
            ev["pattern"] = p[:200]
        if line:
            ev["line"] = line
        lst = self.nodes[nid].setdefault("evidence", [])
        if any(e["file"] == file and e.get("pattern") == ev.get("pattern") for e in lst):
            return
        if len(lst) < 50:
            lst.append(ev)

    def edge(self, a: str, b: str, label: str | None = None, protocol: str | None = None) -> None:
        if a == b or a not in self.nodes or b not in self.nodes:
            return
        if self.nodes[a]["category"] in FOLDED or self.nodes[b]["category"] in FOLDED:
            return
        e = {"from": a, "to": b}
        if protocol:
            e["protocol"] = protocol
        lab = self.safe(label)
        if lab:
            e["label"] = lab[:200]
        self.edges.setdefault((a, b), e)

    # ---- the finished draft
    def document(self) -> dict:
        origins = set(self.origin.values())
        has_local = "local" in origins
        has_deployed = "deployed" in origins
        envs = []
        if has_local:
            envs.append(dict(ENV_LOCAL))
            if has_deployed:
                envs.append(dict(ENV_DEPLOYED))

        def env_of(i: str):
            o = self.origin.get(i, "any")
            if not has_local or o == "any":
                return None
            return ["local"] if o == "local" else ["deployed"]
        groups, nodes, edges = [], [], []
        for g in self.groups.values():
            e = env_of(g["id"])
            groups.append({**g, **({"environments": e} if e else {})})
        for n in self.nodes.values():
            e = env_of(n["id"])
            nodes.append({**n, **({"environments": e} if e else {})})
        dropped = 0
        for (a, b), ed in self.edges.items():
            ea, eb = env_of(a), env_of(b)
            if ea and eb and not set(ea) & set(eb):
                dropped += 1
                continue
            e = ea or eb
            edges.append({**ed, **({"environments": e} if e else {})})
        if dropped:
            self.notes.append(f"{dropped} edge(s) between the local (Compose) and the deployed nodes are not drawn")
        caps = M.schema()["properties"]
        for name, items in (("groups", groups), ("nodes", nodes), ("edges", edges)):
            cap = caps[name]["maxItems"]
            if len(items) > cap:
                self.notes.append(f"{len(items)} {name} found; the draft keeps the first {cap} (the model's limit)")
                del items[cap:]
        kept = {n["id"] for n in nodes} | {g["id"] for g in groups}
        edges = [e for e in edges if e["from"] in kept and e["to"] in kept]
        for n in nodes:
            if n.get("group") and n["group"] not in kept:
                n.pop("group")
        doc = {"$schema": "https://jsonui.dev/schemas/infra-model/v0.json", "version": 0,
               "description": "Draft by jsonui-doc seed infra: not the display source. Review it, then move what "
                              "you keep into the model's folder."}
        if envs:
            doc["environments"] = envs
        doc.update(groups=groups, nodes=nodes, edges=edges)
        return doc

    def report(self) -> dict:
        def capped(items):
            return {"count": len(items), "items": items[:LIST_CAP]}
        rep = {"version": 0, "inputs": {k: sorted(v)[:LIST_CAP] for k, v in sorted(self.inputs.items())},
               "unmatched": {p: capped(v) for p, v in sorted(self.unmatched.items())},
               "notDrawn": {p: dict(sorted(v.items())) for p, v in sorted(self.not_drawn.items())},
               "skipped": self.skipped[:LIST_CAP], "skippedCount": len(self.skipped),
               "notes": self.notes, "withheld": self.withheld}
        return _scrub(rep)


def _scrub(value):
    """The report holds no value either (a file name could): any string with a secret's shape is replaced."""
    if isinstance(value, str):
        return "(withheld: value-shaped)" if M.secret_findings(value) else value
    if isinstance(value, dict):
        return {_scrub(k): _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


# ================================================================ walking the project

def _walk(root: Path, exclude: list[Path], d: Draft) -> list[str]:
    out: list[str] = []
    seen = 0
    ex = {str(p.resolve()) for p in exclude}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if str(Path(dirpath).resolve()) in ex:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(n for n in dirnames if n not in SKIP_DIRS and (not n.startswith(".") or n in KEEP_HIDDEN_DIRS)
                             and str((Path(dirpath) / n).resolve()) not in ex)
        for fn in sorted(filenames):
            seen += 1
            if seen > WALK_CAP:
                d.notes.append(f"more than {WALK_CAP} files: the rest of the project was not looked at")
                return out
            out.append(Path(dirpath, fn).relative_to(root).as_posix())
    return out


TFSTATE = re.compile(r"\.tfstate(\.backup|\.\d+\.backup)?$|\.tfplan$")
ENV_VALUES = re.compile(r"^\.env(\.[\w-]+)?$")
COMPOSE = re.compile(r"^(docker-)?compose(\.[\w-]+)?\.ya?ml$")


def classify(rel: str) -> str | None:
    """What one file is to seed (None: not an input). Files that hold values are 'never' (counted, not read)."""
    name = rel.rsplit("/", 1)[-1]
    low = name.lower()
    if TFSTATE.search(low):
        return "never:terraform state (values in plain text)"
    if low.endswith(".tfvars") or low.endswith(".tfvars.json"):
        return "never:terraform variable values"
    if C.ENV_NAME_FILES.match(low):
        return "env_names"
    if ENV_VALUES.match(low):
        return "never:environment values (.env)"
    if COMPOSE.match(low):
        return "compose"
    if low.endswith(".tf.json"):
        return "terraform_json"
    if low.endswith(".tf"):
        return "terraform"
    if low.endswith(".bicep"):
        return "bicep"
    if low in ("wrangler.toml", "wrangler.json", "wrangler.jsonc"):
        return "wrangler"
    if name in T.PAAS_FILES and T.PAAS_FILES[name][1] != "appengine":
        return T.PAAS_FILES[name][1]                 # firebase, render, serverless, vercel, netlify, fly, procfile
    if low == "pulumi.yaml" or low == "pulumi.yml":
        return "pulumi"
    if "/cdk.out/" in f"/{rel}" and low.endswith(".template.json"):
        return "cfn"
    if low.endswith((".template.json", ".template.yaml", ".template.yml", ".cfn.json", ".cfn.yaml", ".cfn.yml")) or \
            low in ("template.yaml", "template.yml", "template.json"):
        return "cfn"
    if rel.startswith(".github/workflows/") and low.endswith((".yml", ".yaml")):
        return "workflow"
    if low.endswith((".yml", ".yaml")):
        return "yaml"
    ext = os.path.splitext(low)[1]
    if ext in C.CODE_EXT and not low.endswith((".d.ts", ".min.js")):
        return "code"
    return None


# ================================================================ YAML / TOML / JSONC

def _yaml():
    try:
        import yaml  # noqa: PLC0415
        return yaml
    except ImportError:
        return None


def _cfn_loader(yaml):
    class Loader(yaml.SafeLoader):
        pass

    def tag(loader, suffix, node):
        if isinstance(node, yaml.ScalarNode):
            v = loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            v = loader.construct_sequence(node, deep=True)
        else:
            v = loader.construct_mapping(node, deep=True)
        return {"Ref" if suffix == "Ref" else f"Fn::{suffix}": v}
    Loader.add_multi_constructor("!", tag)
    return Loader


def _yaml_docs(text: str, cfn: bool = False) -> list | None:
    yaml = _yaml()
    if yaml is None:
        return None
    try:
        loader = _cfn_loader(yaml) if cfn else yaml.SafeLoader
        return [doc for doc in yaml.load_all(text, Loader=loader)]
    except Exception:  # noqa: BLE001 — any YAML the reader refuses is reported, not raised
        return None


def _toml(text: str):
    try:
        import tomllib  # noqa: PLC0415
    except ImportError:
        return None
    try:
        return tomllib.loads(text)
    except Exception:  # noqa: BLE001
        return None


def _jsonc(text: str):
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    s = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    try:
        return json.loads(s)
    except ValueError:
        return None


def _line_of(text: str, needle: str) -> int | None:
    k = text.find(needle)
    return text.count("\n", 0, k) + 1 if k >= 0 else None


# ================================================================ Terraform / OpenTofu

TF_BLOCK = re.compile(r'^[ \t]*(resource|module|provider|data)\s+"([A-Za-z0-9_-]+)"(?:\s+"([A-Za-z0-9_-]+)")?\s*\{', re.M)
TF_REF = re.compile(r'(?<![\w.])(data\.)?([a-z][a-z0-9]*_[a-z0-9_]+)\.([A-Za-z_][A-Za-z0-9_-]*)')
HEREDOC = re.compile(r"<<-?\s*([A-Za-z_][A-Za-z0-9_]*)[^\n]*\n")


def _block_end(text: str, i: int) -> int:
    depth, n, j = 0, len(text), i
    while j < n:
        c = text[j]
        if c == '"':
            j += 1
            while j < n and text[j] != '"' and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
        elif c == "#" or text.startswith("//", j):
            k = text.find("\n", j)
            j = n if k < 0 else k
            continue
        elif text.startswith("/*", j):
            k = text.find("*/", j + 2)
            j = n if k < 0 else k + 2
            continue
        elif text.startswith("<<", j):
            m = HEREDOC.match(text, j)
            if m:
                end = re.compile(r"^\s*" + re.escape(m.group(1)) + r"\s*$", re.M).search(text, m.end())
                j = n if end is None else end.end()
                continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return n


def _literal(body: str, attr: str) -> str | None:
    m = re.search(r'^\s*' + attr + r'\s*=\s*"([^"$]*)"', body, re.M)
    return m.group(1) if m else None


class _TfRes:
    __slots__ = ("dir", "type", "name", "file", "line", "body", "refs", "header")

    def __init__(self, dir_, type_, name, file, line, body, refs, header):
        self.dir, self.type, self.name, self.file, self.line, self.body, self.refs = dir_, type_, name, file, line, body, refs
        self.header = header


def _tf_parse(d: Draft, rel: str, text: str, resources: list, providers: dict, modules: list) -> None:
    dir_ = rel.rsplit("/", 1)[0] if "/" in rel else "."
    for m in TF_BLOCK.finditer(text):
        kind, a, b = m.group(1), m.group(2), m.group(3)
        end = _block_end(text, m.end() - 1)
        body = text[m.end():end]
        line = text.count("\n", 0, m.start()) + 1
        if kind == "resource" and b:
            refs = [(r.group(2), r.group(3)) for r in TF_REF.finditer(body) if not r.group(1)]
            resources.append(_TfRes(dir_, a, b, rel, line, body, refs, m.group(0).rstrip("{").strip()))
        elif kind == "provider":
            prov = T.TF_PROVIDER_BLOCK.get(a, T.TF_PROVIDER.get(a, a))
            providers[(prov, _literal(body, "alias"))] = _literal(body, "region")
        elif kind == "module":
            src = _literal(body, "source") or ""
            modules.append((rel, line, a, src))


def _tf_json_parse(d: Draft, rel: str, text: str, resources: list, providers: dict, modules: list) -> None:
    try:
        data = json.loads(text)
    except ValueError:
        d.miss("terraform", rel, rel, "not JSON")
        return
    dir_ = rel.rsplit("/", 1)[0] if "/" in rel else "."
    for type_, byname in (data.get("resource") or {}).items():
        for name, body in (byname or {}).items():
            raw = json.dumps(body)
            refs = [(r.group(2), r.group(3)) for r in TF_REF.finditer(raw) if not r.group(1)]
            resources.append(_TfRes(dir_, type_, name, rel, _line_of(text, f'"{name}"'), raw, refs, f'"{name}"'))
    for name, body in (data.get("module") or {}).items():
        modules.append((rel, _line_of(text, f'"{name}"'), name, (body or {}).get("source", "")))


def seed_terraform(d: Draft, files: list[tuple[str, str, str]]) -> None:
    resources: list[_TfRes] = []
    providers: dict[tuple[str, str | None], str | None] = {}
    modules: list = []
    for kind, rel, text in files:
        (_tf_json_parse if kind == "terraform_json" else _tf_parse)(d, rel, text, resources, providers, modules)
    for rel, line, name, src in modules:
        if not (src.startswith("./") or src.startswith("../")):
            d.miss("terraform", rel, f"module.{name}", "the module's source is outside the project: not read")
        elif src.startswith("../"):
            d.notes.append(f"module.{name} ({rel}): a local module outside its folder is read only if it is inside the project")
    by_key = {(r.dir, r.type, r.name): r for r in resources}
    region_group: dict[tuple[str, str | None], str] = {}

    def place(prov: str, body: str) -> str:
        m = re.search(r"^\s*provider\s*=\s*([a-z0-9_-]+)\.([A-Za-z0-9_-]+)", body, re.M)
        alias = m.group(2) if m else None
        top = d.top_group(prov)
        key = (prov, alias) if (prov, alias) in providers else (prov, None)
        region = providers.get(key)
        if region and REGION_RX.match(region) and not M.secret_findings(region):
            if key not in region_group:
                region_group[key] = d.add_group(("region", prov, region), f"{prov}-{region}", "region", prov,
                                                f"{prov} {region}", top, region=region)
            return region_group[key]
        return top
    ids: dict[tuple, str] = {}
    kinds: dict[tuple, str] = {}
    # groups first (their parents are groups), then nodes
    ordered = sorted(resources, key=lambda r: _group_order(T.tf_mapping(r.type)))
    for r in ordered:
        prov = T.tf_provider(r.type)
        if prov is None:
            d.part("terraform", r.type)
            continue
        if not PROVIDER_RX.match(prov):
            prov = "(unknown)"
        addr = T.tf_address(r.type, r.name)
        mapped = T.tf_mapping(r.type)
        if mapped == "part":
            d.part(prov, r.type)
            continue
        if mapped is None:
            d.miss(prov, r.file, addr, "no category for this resource type")
            continue
        cat, svc = mapped
        key = (r.dir, r.type, r.name)
        parent, parent_rank = None, 99
        for rt, rn in _expanded_refs(r, by_key):
            k = kinds.get((r.dir, rt, rn), "")
            if k.startswith("group:") and _rank(k) < parent_rank:
                parent, parent_rank = ids[(r.dir, rt, rn)], _rank(k)
        if cat.startswith("group:"):
            gkind = cat[6:]
            vis = "public" if re.search(r"map_public_ip_on_launch\s*=\s*true", r.body) else None
            gid = d.add_group(("tf",) + key, f"{svc}-{r.name}", gkind, prov, f"{r.name} ({svc} {gkind})",
                              parent or place(prov, r.body), visibility=vis)
        else:
            engine = _literal(r.body, "engine") or _literal(r.body, "database_version")
            ver = _literal(r.body, "engine_version")
            gid = d.add_node(("tf",) + key, f"{svc.split('.')[0]}-{r.name}", cat, prov, svc, f"{r.name} ({svc})",
                             parent or place(prov, r.body), r.file, r.header, r.line, iac=addr,
                             engine=(f"{engine} {ver}" if engine and ver else engine))
            if re.search(r"^\s*(count|for_each)\s*=", r.body, re.M):
                d.notes.append(f"{addr} ({r.file}): count/for_each is not evaluated; the draft shows one")
        ids[key], kinds[key] = gid, cat
    for r in resources:
        a = ids.get((r.dir, r.type, r.name))
        if not a or a not in d.nodes:
            continue
        for rt, rn in r.refs:
            b = ids.get((r.dir, rt, rn))
            if b and b in d.nodes:
                d.edge(a, b, "terraform reference")
    d.inputs.setdefault("terraform_providers", []).extend(sorted({p for p, _a in providers}))


def _group_order(mapped) -> int:
    """Groups before nodes (a node's group must be known), networks before what they hold."""
    cat = mapped[0] if isinstance(mapped, tuple) else ""
    return 0 if cat == "group:network" else 1 if cat.startswith("group:") else 2


def _rank(kind: str) -> int:
    return {"group:subnet": 0, "group:cluster": 1, "group:namespace": 1, "group:network": 2, "group:project": 3}.get(kind, 9)


def _expanded_refs(r: _TfRes, by_key: dict) -> list[tuple[str, str]]:
    """Its own references, and one step through the parts it names (a DB's subnet group names the subnets)."""
    out = list(r.refs)
    for rt, rn in r.refs:
        p = by_key.get((r.dir, rt, rn))
        if p is not None and T.tf_mapping(rt) == "part":
            out.extend(p.refs)
    return out


# ================================================================ Compose

def _image_engine(image: str | None) -> str | None:
    if not image:
        return None
    last = image.split("@", 1)[0].rsplit("/", 1)[-1]
    name, _, tag = last.partition(":")
    return f"{name} {tag}".strip() if re.match(r"^[\w.-]{0,30}$", tag or "") else name


def seed_compose(d: Draft, rel: str, text: str) -> None:
    docs = _yaml_docs(text)
    if not docs or not isinstance(docs[0], dict):
        d.miss("docker", rel, rel, "not readable as YAML" if _yaml() else "PyYAML is not installed")
        return
    services = docs[0].get("services") or {}
    if not isinstance(services, dict):
        d.miss("docker", rel, rel, "services is not a mapping")
        return
    grp = d.add_group(("compose",), "compose", "host", "docker", "Docker Compose", None, origin="local")
    ids = {}
    for name, svc in services.items():
        svc = svc if isinstance(svc, dict) else {}
        image = svc.get("image") if isinstance(svc.get("image"), str) else None
        cat = T.compose_category(image)
        known = cat != "compute.container"
        service = next((k for k, _c in T.COMPOSE_IMAGE if k in (image or "").lower()), "container")
        engine = _image_engine(image) if cat.startswith(("database", "cache")) else None
        ids[name] = d.add_node(("compose", name), f"compose-{name}", cat, "docker", f"compose.{service}",
                               f"{name}", grp, rel, str(name), _line_of(text, f"\n  {name}:"),
                               iac=T.compose_address(rel, str(name)), origin="local", engine=engine)
        if not known and not svc.get("build") and image:
            d.notes.append(f"compose service {name} ({rel}): the image is not one seed knows; drawn as a container")
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        deps = svc.get("depends_on") or []
        deps = list(deps.keys()) if isinstance(deps, dict) else list(deps)
        links = [str(x).split(":", 1)[0] for x in (svc.get("links") or [])]
        for dep in deps + links:
            if dep in ids:
                d.edge(ids[name], ids[dep], "depends_on")
    for key in ("volumes", "networks", "secrets", "configs"):
        if isinstance(docs[0].get(key), dict):
            for _ in docs[0][key]:
                d.part("docker", f"compose {key}")


# ================================================================ Kubernetes

def seed_k8s(d: Draft, items: list[tuple[str, dict, str]]) -> None:
    cluster = d.add_group(("k8s",), "kubernetes", "cluster", "kubernetes", "Kubernetes", None)
    workloads: list[tuple[str, dict, str]] = []
    services: dict[tuple[str, str], dict] = {}
    deferred = []
    for rel, doc, text in items:
        kind = str(doc.get("kind"))
        meta = doc.get("metadata") or {}
        name = str(meta.get("name") or "unnamed")
        ns = str(meta.get("namespace") or "default")
        spec = doc.get("spec") or {}
        if kind == "Namespace":
            d.add_group(("k8s-ns", name), f"ns-{name}", "namespace", None, name, cluster)
            continue
        nsg = d.add_group(("k8s-ns", ns), f"ns-{ns}", "namespace", None, ns, cluster)
        line = _line_of(text, f"name: {name}")
        mapped = T.k8s_mapping(kind, spec)
        if kind == "Service":
            services[(ns, name)] = spec
        if mapped == "part":
            d.part("kubernetes", kind if kind != "Service" else "Service (ClusterIP)")
            continue
        if mapped is None:
            d.miss("kubernetes", rel, T.k8s_address(kind, name), "no category for this kind")
            continue
        cat, svc = mapped
        nid = d.add_node(("k8s", kind, ns, name), f"k8s-{kind.lower()}-{name}", cat, "kubernetes", svc, name, nsg,
                         rel, name, line, iac=T.k8s_address(kind, name),
                         count=_int(spec.get("replicas")) if kind in T.K8S_WORKLOAD else None)
        if kind in T.K8S_WORKLOAD or kind == "CronJob":
            tmpl = spec.get("template") or {}
            if kind == "CronJob":
                tmpl = ((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {}
            labels = ((tmpl.get("metadata") or {}).get("labels")) or {}
            workloads.append((ns, labels if isinstance(labels, dict) else {}, nid))
        elif kind == "Service":
            deferred.append(("svc", ns, name, nid))
        elif kind in ("Ingress", "Gateway", "HTTPRoute"):
            for b in re.findall(r"'name':\s*'([^']+)'", repr(spec.get("rules") or spec.get("defaultBackend") or "")):
                deferred.append(("ing", ns, b, nid))

    def selected(ns: str, svc_name: str) -> list[str]:
        sel = (services.get((ns, svc_name)) or {}).get("selector") or {}
        if not isinstance(sel, dict) or not sel:
            return []
        return [nid for wns, labels, nid in workloads if wns == ns and all(labels.get(k) == v for k, v in sel.items())]
    for how, ns, name, nid in deferred:
        for w in selected(ns, name):
            d.edge(nid, w, "routes to" if how == "ing" else "selects")


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 1000 else None


# ================================================================ CloudFormation / SAM / CDK

def _cfn_refs(value, out: set) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "Ref" and isinstance(v, str):
                out.add(v)
            elif k == "Fn::GetAtt":
                tgt = v[0] if isinstance(v, list) and v else (v.split(".", 1)[0] if isinstance(v, str) else None)
                if isinstance(tgt, str):
                    out.add(tgt)
            elif k == "Fn::Sub":
                s = v[0] if isinstance(v, list) and v else v
                if isinstance(s, str):
                    out.update(x.split(".", 1)[0] for x in re.findall(r"\$\{([A-Za-z0-9.]+)\}", s))
            _cfn_refs(v, out)
    elif isinstance(value, list):
        for v in value:
            _cfn_refs(v, out)


def seed_cfn(d: Draft, rel: str, resources: dict, text: str, source: str = "cloudformation") -> None:
    top = d.top_group("aws")
    ids, kinds = {}, {}
    order = sorted(resources.items(),
                   key=lambda kv: _group_order(T.cfn_mapping(str((kv[1] if isinstance(kv[1], dict) else {}).get("Type") or ""))))
    refs_of = {}
    for lid, res in order:
        res = res if isinstance(res, dict) else {}
        typ = str(res.get("Type") or "")
        refs: set = set()
        _cfn_refs(res.get("Properties"), refs)
        dep = res.get("DependsOn")
        refs.update([dep] if isinstance(dep, str) else [x for x in (dep or []) if isinstance(x, str)])
        refs_of[lid] = refs
        mapped = T.cfn_mapping(typ)
        if mapped == "part":
            d.part("aws", typ)
            continue
        if mapped is None:
            if typ.startswith("AWS::"):
                d.miss("aws", rel, f"{lid} ({typ})", "no category for this resource type")
            else:
                d.miss("(unknown)", rel, f"{lid} ({typ})", "not an AWS resource type")
            continue
        cat, svc = mapped
        path = ((res.get("Metadata") or {}).get("aws:cdk:path")) if isinstance(res.get("Metadata"), dict) else None
        label = lid
        if isinstance(path, str) and "/" in path:
            label = "/".join(p for p in path.split("/")[1:] if p not in ("Resource", "Default")) or lid
        parent = None
        for r in refs:
            if r in ids and kinds[r].startswith("group:") and (parent is None or _rank(kinds[r]) < _rank(kinds[parent])):
                parent = r
        pg = ids[parent] if parent else top
        line = _line_of(text, f"{lid}:") or _line_of(text, f'"{lid}"')
        if cat.startswith("group:"):
            gid = d.add_group(("cfn", rel, lid), f"{svc}-{lid}", cat[6:], "aws", f"{label} ({svc})", pg)
        else:
            gid = d.add_node(("cfn", rel, lid), f"{svc.split('.')[0]}-{lid}", cat, "aws", svc, f"{label} ({svc})", pg,
                             rel, lid, line, iac=T.cfn_address(lid))
        ids[lid], kinds[lid] = gid, cat
    for lid, refs in refs_of.items():
        a = ids.get(lid)
        for r in refs:
            if a and r in ids:
                d.edge(a, ids[r], f"{source} reference")


# ================================================================ wrangler, PaaS files, Bicep

def seed_wrangler(d: Draft, rel: str, text: str) -> None:
    cfg = _toml(text) if rel.endswith(".toml") else _jsonc(text)
    if not isinstance(cfg, dict):
        d.miss("cloudflare", rel, rel, "not readable (TOML needs Python 3.11+)" if rel.endswith(".toml") else "not readable")
        return
    top = d.top_group("cloudflare")
    name = str(cfg.get("name") or Path(rel).parent.name or "worker")
    w = d.add_node(("worker", name), f"worker-{name}", "compute.function", "cloudflare", "workers", name, top, rel,
                   "name", _line_of(text, "name"), iac=T.wrangler_address(rel))

    for kind, handle, label, cat, svc in T.wrangler_bindings(cfg):
        nid = d.add_node(("cf", svc, label), f"{svc}-{label}", cat, "cloudflare", svc, label, top, rel, handle,
                         _line_of(text, handle), iac=T.wrangler_address(rel, kind, handle))
        if kind == "queues.consumers":
            d.edge(nid, w, f"{kind} binding")
        else:
            d.edge(w, nid, f"{kind} binding")
    for s in cfg.get("services") or []:
        if isinstance(s, dict) and s.get("service"):
            other = d.add_node(("worker", str(s["service"])), f"worker-{s['service']}", "compute.function", "cloudflare",
                               "workers", str(s["service"]), top, rel, str(s["service"]), _line_of(text, str(s["service"])))
            d.edge(w, other, "service binding")
    crons = ((cfg.get("triggers") or {}).get("crons")) or []
    if crons:
        c = d.add_node(("cf-cron", name), f"cron-{name}", "scheduler", "cloudflare", "workers.cron", f"{name} cron", top,
                       rel, "crons", _line_of(text, "crons"))
        d.edge(c, w, "cron trigger")
    for key in ("routes", "route"):
        if cfg.get(key):
            d.part("cloudflare", f"wrangler {key}")
    if isinstance(cfg.get("env"), dict) and cfg["env"]:
        d.notes.append(f"{rel}: [env.*] sections ({', '.join(map(str, cfg['env']))}) are not drawn separately")
    for key in ("ai", "vectorize", "hyperdrive", "analytics_engine_datasets", "browser", "mtls_certificates"):
        if cfg.get(key):
            d.miss("cloudflare", rel, f"wrangler {key}", "binding kind seed does not draw yet")


def seed_firebase(d: Draft, rel: str, text: str) -> None:
    try:
        cfg = json.loads(text)
    except ValueError:
        d.miss("firebase", rel, rel, "not JSON")
        return
    top = d.top_group(_paas_provider("firebase"))
    made = {}
    for key, cat, svc in (("hosting", "edge.cdn", "hosting"), ("functions", "compute.function", "functions"),
                          ("firestore", "database.document", "firestore"), ("database", "database.kv", "rtdb"),
                          ("storage", "storage.object", "storage")):
        if key in cfg:
            made[key] = d.add_node(("firebase", svc), f"firebase-{svc}", cat, "firebase", svc, f"Firebase {svc}", top,
                                   rel, f'"{key}"', _line_of(text, f'"{key}"'), iac=T.paas_address("firebase", key))
    if "hosting" in made and "functions" in made and '"function"' in text:
        d.edge(made["hosting"], made["functions"], "rewrite")
    for key in cfg:
        if key not in ("hosting", "functions", "firestore", "database", "storage", "emulators", "remoteconfig",
                       "extensions", "$schema"):
            d.miss("firebase", rel, key, "firebase.json key seed does not draw")


def _paas_provider(platform: str) -> str | None:
    """The provider iac_tables.PAAS_FILES gives a platform's settings file (None: not clear, as for a Procfile)."""
    return next((prov for prov, plat in T.PAAS_FILES.values() if plat == platform), None)


def _paas_node(d: Draft, provider: str, rel: str, name: str, text: str, cat="compute.paas", svc="app", pattern=None,
               platform: str | None = None):
    top = d.top_group(provider)
    return d.add_node((provider, svc, name), f"{provider}-{name}", cat, provider, svc, name, top, rel, pattern or name,
                      _line_of(text, pattern or name), iac=T.paas_address(platform or provider, name))


def seed_vercel(d: Draft, rel: str, text: str) -> None:
    cfg = _jsonc(text)
    if not isinstance(cfg, dict):
        d.miss("vercel", rel, rel, "not JSON")
        return
    name = str(cfg.get("name") or Path(rel).parent.name or "project")
    if rel == "vercel.json":
        name = cfg.get("name") or d.root.name
    p = _paas_node(d, "vercel", rel, str(name), text, svc="project", pattern="{")
    for c in cfg.get("crons") or []:
        if isinstance(c, dict) and c.get("path"):
            s = d.add_node(("vercel-cron", name), f"vercel-cron-{name}", "scheduler", "vercel", "cron", f"{name} cron",
                           d.top_group(_paas_provider("vercel")), rel, '"crons"', _line_of(text, '"crons"'))
            d.edge(s, p, "cron")
            break


def seed_netlify(d: Draft, rel: str, text: str) -> None:
    cfg = _toml(text)
    if not isinstance(cfg, dict):
        d.miss("netlify", rel, rel, "not readable TOML")
        return
    name = Path(rel).parent.name if "/" in rel else d.root.name
    site = _paas_node(d, "netlify", rel, name, text, svc="site", pattern="[build]" if "[build]" in text else None)
    fn = (cfg.get("functions") or {}) if isinstance(cfg.get("functions"), dict) else {}
    if fn or (cfg.get("build") or {}).get("functions"):
        f = d.add_node(("netlify-fn", name), f"netlify-functions-{name}", "compute.function", "netlify", "functions",
                       f"{name} functions", d.top_group(_paas_provider("netlify")), rel, "functions", _line_of(text, "functions"))
        d.edge(site, f, "functions")


def seed_fly(d: Draft, rel: str, text: str) -> None:
    cfg = _toml(text)
    if not isinstance(cfg, dict) or not cfg.get("app"):
        d.miss("fly", rel, rel, "no app name, or not readable TOML")
        return
    _paas_node(d, "fly", rel, str(cfg["app"]), text, pattern="app")


def seed_render(d: Draft, rel: str, text: str) -> None:
    docs = _yaml_docs(text)
    cfg = docs[0] if docs else None
    if not isinstance(cfg, dict):
        d.miss("render", rel, rel, "not readable YAML")
        return
    top = d.top_group(_paas_provider("render"))
    for s in cfg.get("services") or []:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        t = str(s.get("type") or "web")
        cat, svc = {"cron": ("scheduler", "cron"), "redis": ("cache", "keyvalue"), "keyvalue": ("cache", "keyvalue"),
                    "worker": ("compute.paas", "worker"), "pserv": ("compute.paas", "private")}.get(t, ("compute.paas", t))
        d.add_node(("render", str(s["name"])), f"render-{s['name']}", cat, "render", svc, str(s["name"]), top, rel,
                   str(s["name"]), _line_of(text, f"name: {s['name']}"), iac=T.paas_address("render", str(s["name"])))
    for db in cfg.get("databases") or []:
        if isinstance(db, dict) and db.get("name"):
            d.add_node(("render", str(db["name"])), f"render-{db['name']}", "database.relational", "render", "postgres",
                       str(db["name"]), top, rel, str(db["name"]), _line_of(text, f"name: {db['name']}"),
                       iac=T.paas_address("render", str(db["name"])))


def seed_appengine(d: Draft, rel: str, text: str) -> None:
    docs = _yaml_docs(text)
    cfg = docs[0] if docs else None
    if not isinstance(cfg, dict) or "runtime" not in cfg:
        d.miss("gcp", rel, rel, "App Engine app.yaml not readable")
        return
    name = str(cfg.get("service") or "default")
    _paas_node(d, _paas_provider("appengine"), rel, name, text, svc="appengine", pattern="runtime", platform="appengine")


def seed_serverless(d: Draft, rel: str, text: str) -> None:
    docs = _yaml_docs(text, cfn=True)
    cfg = docs[0] if docs else None
    if not isinstance(cfg, dict):
        d.miss("serverless", rel, rel, "not readable YAML")
        return
    prov = cfg.get("provider")
    pname = str(prov.get("name") if isinstance(prov, dict) else prov or _paas_provider("serverless"))
    pname = {"google": "gcp"}.get(pname, pname)
    if pname not in ("aws", "gcp", "azure"):
        d.miss(pname, rel, rel, "serverless provider seed does not draw")
        return
    top = d.top_group(pname)
    svc = {"aws": "lambda", "gcp": "functions", "azure": "functions"}[pname]
    api = None
    for fname, f in (cfg.get("functions") or {}).items():
        fid = d.add_node(("sls", rel, fname), f"fn-{fname}", "compute.function", pname, svc, str(fname), top, rel,
                         f"{fname}:", _line_of(text, f"{fname}:"), iac=T.paas_address("serverless", str(fname)))
        for ev in (f or {}).get("events") or [] if isinstance(f, dict) else []:
            if isinstance(ev, dict) and ({"http", "httpApi"} & set(ev)):
                api = api or d.add_node(("sls-api", rel), "http-api", "gateway.api", pname, "apigateway", "HTTP API",
                                        top, rel, "http", _line_of(text, "http"))
                d.edge(api, fid, "invokes")
    res = ((cfg.get("resources") or {}).get("Resources")) if isinstance(cfg.get("resources"), dict) else None
    if isinstance(res, dict):
        seed_cfn(d, rel, res, text, source="serverless resources")


BICEP_RES = re.compile(r"^\s*resource\s+([A-Za-z_][A-Za-z0-9_]*)\s+'([A-Za-z0-9.]+/[A-Za-z0-9./]+)@[^']*'", re.M)


def seed_bicep(d: Draft, rel: str, text: str) -> None:
    top = d.top_group("azure")
    found = []
    for m in BICEP_RES.finditer(text):
        sym, typ = m.group(1), m.group(2).lower()
        line = text.count("\n", 0, m.start()) + 1
        mapped = T.bicep_mapping(typ)
        if mapped == "part":
            d.part("azure", typ)
            continue
        if mapped is None:
            d.miss("azure", rel, f"{sym} ({typ})", "no category for this resource type")
            continue
        end = _block_end(text, text.find("{", m.end()))
        body = text[m.end():end]
        cat, svc = mapped
        if cat.startswith("group:"):
            d.add_group(("bicep", rel, sym), f"{svc}-{sym}", cat[6:], "azure", f"{sym} ({svc})", top)
            continue
        nid = d.add_node(("bicep", rel, sym), f"{svc}-{sym}", cat, "azure", svc, f"{sym} ({svc})", top, rel,
                         f"resource {sym}", line, iac=T.bicep_address(sym))
        found.append((sym, nid, body))
    syms = {s: n for s, n, _b in found}
    for s, n, body in found:
        for o in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\.(?:id|name|properties)", body):
            if o in syms:
                d.edge(n, syms[o], "bicep reference")


# ================================================================ code

def _code_root(root: Path, rel: str, cache: dict) -> str:
    parts = rel.split("/")[:-1]
    for k in range(len(parts), -1, -1):
        cand = "/".join(parts[:k]) or "."
        if cand not in cache:
            base = root / cand
            cache[cand] = any((base / f).is_file() for f in ("package.json", "pyproject.toml", "requirements.txt",
                                                              "setup.py", "setup.cfg", "Pipfile", "go.mod", "Gemfile"))
        if cache[cand]:
            return cand
    return "."


class _Code:
    def __init__(self, d: Draft) -> None:
        self.d = d
        self.uses: dict[str, list[tuple[tuple[str, str, str], str, str, int | None]]] = {}   # app -> hits
        self.unclear: dict[tuple[str, str], tuple[str, int | None]] = {}

    def hit(self, app: str, what: tuple[str, str, str], file: str, pattern: str, line: int | None) -> None:
        self.uses.setdefault(app, []).append((what, file, pattern, line))

    def take(self, app: str, found: dict) -> None:
        """One file's hints from code_hints (scan_text / scan_env_names) into the draft."""
        for what, rel, pattern, line in found["hits"]:
            self.hit(app, what, rel, pattern, line)
        for prov, rel, mod, line in found["unclear"]:
            self.unclear.setdefault((prov, f"{rel}:{mod}"), (rel, line))
        for prov, rel, what, why in found["misses"]:
            self.d.miss(prov, rel, what, why)

    def finish(self) -> None:
        d = self.d
        resolved = {(p, rel.split(":", 1)[0]) for app, hits in self.uses.items() for (p, _c, _s), rel, _pat, _l in hits}
        for (prov, key), (rel, line) in sorted(self.unclear.items()):
            if (prov, rel) not in resolved:
                d.miss(prov, rel, key.split(":", 1)[1], "SDK import: which service is not clear from the import alone")
        for app, hits in sorted(self.uses.items()):
            app_label = "app" if app == "." else app
            a = d.add_node(("app", app), f"app-{app_label.replace('/', '-')}", "compute.container", None, None,
                           f"{app_label} (app: where it runs is not known)", None, f"{app}/" if app != "." else hits[0][1],
                           None, None, origin="any")
            d.nodes[a]["evidence"] = [e for e in d.nodes[a].get("evidence", []) if REL_RX.match(e["file"]) and
                                      not e["file"].endswith("/")]
            engines: dict[tuple, set] = {}
            for (prov, cat, svc), rel, pattern, line in hits:
                if prov:
                    key = ("code", prov, cat, svc)
                    group = d.external_group() if prov in C.SAAS or cat == "external.saas" else None
                    nid = d.add_node(key, f"{prov}-{svc or cat}", cat, prov, svc or None,
                                     f"{prov} {svc}".strip(), group, rel, pattern, line, origin="any",
                                     managed_by="external" if group else None)
                else:
                    key = ("code", "", cat)
                    nid = d.add_node(key, cat.replace("database.", "") if cat != "cache" else "cache", cat, None, None,
                                     f"{cat} (provider not known)", None, rel, pattern, line, origin="any")
                    if svc:
                        engines.setdefault(key, set()).add(svc)
                d.evidence(a, rel, None, None)
                d.edge(a, nid, "uses (code)")
            for key, engs in engines.items():
                nid = d.by_key[key]
                if len(engs) == 1 and "engine" not in d.nodes[nid]:
                    d.nodes[nid]["engine"] = next(iter(engs))
        if self.uses:
            d.notes.append("nodes from code: an app node per code root (where it runs is not known), and what it talks "
                           "to; a node with no provider needs one, and a node may be the same as one from IaC — merge them")


# ================================================================ the whole run

def draft(root: Path, exclude: list[Path] | None = None) -> tuple[dict, dict]:
    """(the draft model, the report) for the project at ``root``. Reads no file that holds values."""
    root = Path(root).resolve()
    d = Draft(root)
    files = _walk(root, exclude or [], d)
    tf: list[tuple[str, str, str]] = []
    k8s: list[tuple[str, dict, str]] = []
    code_cache: dict = {}
    code = _Code(d)
    code_n = 0
    workflow_hits: dict[str, list[tuple[str, int]]] = {}
    for rel in files:
        kind = classify(rel)
        if kind is None:
            continue
        if kind.startswith("never:"):
            d.skipped.append({"file": rel, "why": f"{kind[6:]}: never read"})
            continue
        if kind == "code":
            code_n += 1
            if code_n > CODE_FILES_CAP:
                if code_n == CODE_FILES_CAP + 1:
                    d.notes.append(f"more than {CODE_FILES_CAP} code files: the rest were not read")
                continue
        path = root / rel
        text = read_text(path)
        if text is None:
            d.skipped.append({"file": rel, "why": "a symlink, not a regular file, unreadable, or over "
                                                  f"{FILE_CAP} bytes"})
            continue
        if kind == "yaml":
            if "AWSTemplateFormatVersion" in text or re.search(r"^Resources:\s*$", text, re.M) and "AWS::" in text:
                kind = "cfn"
            elif re.search(r"^apiVersion:", text, re.M) and re.search(r"^kind:", text, re.M):
                kind = "k8s"
            elif T.PAAS_FILES.get(rel.rsplit("/", 1)[-1], (None, ""))[1] == "appengine" and \
                    re.search(r"^runtime:", text, re.M) and not re.search(r"^apiVersion:", text, re.M):
                kind = "appengine"
            elif rel.endswith(("Chart.yaml", "Chart.yml")):
                d.miss("kubernetes", rel, rel, "Helm chart: not rendered (seed `helm template` output instead)")
                continue
            else:
                continue
        if kind != "code":
            d.input(kind, rel)
        if kind in ("terraform", "terraform_json"):
            tf.append((kind, rel, text))
        elif kind == "compose":
            seed_compose(d, rel, text)
        elif kind == "k8s":
            if "{{" in text:
                d.miss("kubernetes", rel, rel, "Helm/Go template: not rendered (seed `helm template` output instead)")
                continue
            docs = _yaml_docs(text)
            if docs is None:
                d.miss("kubernetes", rel, rel, "not readable YAML" if _yaml() else "PyYAML is not installed")
                continue
            k8s.extend((rel, doc, text) for doc in docs if isinstance(doc, dict) and doc.get("kind"))
        elif kind == "cfn":
            doc = None
            if rel.endswith(".json"):
                try:
                    doc = json.loads(text)
                except ValueError:
                    doc = None
            else:
                docs = _yaml_docs(text, cfn=True)
                doc = docs[0] if docs else None
            if not isinstance(doc, dict) or not isinstance(doc.get("Resources"), dict):
                d.miss("aws", rel, rel, "not a readable CloudFormation template")
                continue
            seed_cfn(d, rel, doc["Resources"], text, "cdk" if "cdk.out/" in rel else "cloudformation")
        elif kind == "wrangler":
            seed_wrangler(d, rel, text)
        elif kind == "firebase":
            seed_firebase(d, rel, text)
        elif kind == "vercel":
            seed_vercel(d, rel, text)
        elif kind == "netlify":
            seed_netlify(d, rel, text)
        elif kind == "fly":
            seed_fly(d, rel, text)
        elif kind == "render":
            seed_render(d, rel, text)
        elif kind == "serverless":
            seed_serverless(d, rel, text)
        elif kind == "appengine":
            seed_appengine(d, rel, text)
        elif kind == "bicep":
            seed_bicep(d, rel, text)
        elif kind == "pulumi":
            d.miss("pulumi", rel, rel, "Pulumi needs `pulumi stack export`; seed does not run it")
        elif kind == "procfile":
            d.miss(_paas_provider("procfile") or "(unknown)", rel, rel,
                   "Procfile: the platform that runs it is not clear from the file")
        elif kind == "workflow":
            for rx, prov in C.WORKFLOW_HINTS:
                m = rx.search(text)
                if m:
                    workflow_hits.setdefault(prov, []).append((rel, text.count("\n", 0, m.start()) + 1))
        elif kind == "env_names":
            code.take(_code_root(root, rel, code_cache), C.scan_env_names(rel, text))
        elif kind == "code":
            code.take(_code_root(root, rel, code_cache), C.scan_text(rel, text))
    if code_n:
        d.input("code", f"{min(code_n, CODE_FILES_CAP)} file(s)")
    if tf:
        seed_terraform(d, tf)
    if k8s:
        seed_k8s(d, k8s)
    code.finish()
    if workflow_hits:
        ci = None
        for prov, hits in sorted(workflow_hits.items()):
            for rel, line in hits:
                ci = d.add_node(("ci", "deploy"), "deploy-workflows", "ci", "github", "actions", "deploy workflows",
                                None, rel, None, line, origin="any")
            d.notes.append(f"deploy workflows mention {prov}: {', '.join(sorted({r for r, _l in hits}))}")
        _ = ci
    if not d.nodes and not d.groups:
        d.notes.append("nothing found to draft from")
    return d.document(), d.report()


def declared_diff(root: Path, doc: dict) -> dict | None:
    """When the room already declares a model: the drafted nodes none of whose iac or evidence the model names."""
    from . import room as R  # noqa: PLC0415
    res = R.read(root)
    if not res.get("ok"):
        return None
    names = set()
    for n in res["nodes"]:
        names.update(n.get("iac") or [])
        names.update(e.get("pattern") or e["file"] for e in n.get("evidence") or [])
    new = [n["id"] for n in doc["nodes"]
           if not (set(n.get("iac") or []) | {e.get("pattern") or e["file"] for e in n.get("evidence") or []}) & names]
    return {"dir": res["dir"], "files": res["files"], "draftNodesNotDeclared": new[:LIST_CAP],
            "draftNodesNotDeclaredCount": len(new)}


def check_draft(doc: dict) -> list[dict]:
    """The error problems of the draft as the room would see it (check_file and merge): must be empty to be written."""
    raw = (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    _data, found = M.check_file(DRAFT_NAME, raw)
    _model, merged = M.merge([(DRAFT_NAME, raw)])
    seen, out = set(), []
    for p in M.errors(found) + M.errors(merged):
        k = (p["path"], p["code"])
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def run(root: Path, out_dir: Path | None = None, to_stdout: bool = False, force: bool = False,
        echo=print, err=None) -> int:
    """The command: 0 written (or printed), 2 not (the room's config is bad, the draft failed its own check, or the
    files are there and --force was not given)."""
    import sys  # noqa: PLC0415
    from . import room as R  # noqa: PLC0415
    err = err or (lambda s: print(s, file=sys.stderr))
    root = Path(root).resolve()
    try:
        folder, _icons, _p = R.infra_config(root)
    except R.Refused as r:
        err(f"seed infra: {r.reason}: {r.message}")
        return 2
    out_dir = Path(out_dir) if out_dir else root / folder / "seed"
    doc, rep = draft(root, exclude=[root / folder, out_dir])
    problems = check_draft(doc)
    if problems:
        for p in problems:
            err(f"seed infra: the draft fails its own check: {p['path']}: {p['code']}")
        err("seed infra: nothing written")
        return 2
    diff = declared_diff(root, doc)
    if diff:
        rep["declared"] = _scrub(diff)
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    if to_stdout:
        echo(text.rstrip("\n"))
    else:
        targets = [out_dir / DRAFT_NAME, out_dir / REPORT_NAME]
        if not force and any(t.exists() for t in targets):
            err(f"seed infra: {out_dir} already holds a draft; pass --force to replace it")
            return 2
        out_dir.mkdir(parents=True, exist_ok=True)
        targets[0].write_text(text, encoding="utf-8")
        targets[1].write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    um = sum(v["count"] for v in rep["unmatched"].values())
    by_p: dict[str, int] = {}
    for n in doc["nodes"]:
        by_p[n.get("provider", "(none)")] = by_p.get(n.get("provider", "(none)"), 0) + 1
    summary = (f"seed infra: {len(doc['nodes'])} nodes, {len(doc['groups'])} groups, {len(doc['edges'])} edges "
               f"({', '.join(f'{p} {c}' for p, c in sorted(by_p.items())) or 'none'}); "
               f"unmatched {um} ({', '.join(f'{p} {v['count']}' for p, v in rep['unmatched'].items()) or 'none'}); "
               f"skipped {rep['skippedCount']}")
    (err if to_stdout else echo)(summary)
    if not to_stdout:
        echo(f"seed infra: wrote {out_dir / DRAFT_NAME} and {REPORT_NAME} (a draft: move what you keep into {folder}/)")
    return 0
