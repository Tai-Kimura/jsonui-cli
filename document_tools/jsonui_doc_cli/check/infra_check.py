"""check kind=infra: the room's declared infrastructure (docs/infra, boundary §6) against what the project's own files say.

builtin:infra-iac — the IaC and deploy settings in the project (Docker Compose, Terraform / OpenTofu HCL, CloudFormation
/ SAM and a synthesized CDK app's cdk.out, Bicep, Kubernetes manifests, Cloudflare wrangler), read statically: no
credentials, no plan, no state (state holds secrets in the clear). Each resource gets its provider, category and
address from infra/iac_tables.py — the one table seed drafts with — parts of another resource (attachments, rules,
routes, records, ...) are dropped, and IAM, policies and alarms are compared when declared and not asked for when not
(they are folded by default); each provider's resources are compared with that provider's declared nodes
(providerResolved) through their ``iac`` addresses, and a node's declared spec with the values its resources write
(iac_tables.TF_SPEC / CFN_SPEC; a variable or a reference is not evaluated: such a value is counted as not compared).

builtin:infra-code — the code: every node's ``evidence`` (the file is there, the pattern still in it), and the services
the code talks to by its SDK imports and the *names* of its environment variables (never their values), against the
declared nodes.

builtin:infra-load — the cost simulator's load definitions (<infra.dir>/load) against the model: see run_infra_load.

Both say what they could not check, per provider (report.target_extra["unverified"] and a warnings line each): no IaC
found for a provider that has declared nodes, a module from a source outside the project, count / for_each not
evaluated, a file that could not be parsed, a resource type with no mapping, a scan cap reached. "0 mismatches" covers
only what was read.

Findings are warnings unless the check declares "gate": true (jui.config.json checks[]): drift in a hand-kept model is
reported, it gates CI only when the project asks.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath

from ..infra import code_hints as H
from ..infra import iac_tables as T
from ..infra import model as M
from ..infra import room as R
from .report import CheckReport, ResultItem, compute_input_hashes

SKIP_DIRS = T.SKIP_DIRS   # which file is what lives in iac_tables (one copy with seed); the name stays for seed until (C) imports T
MAX_CODE_FILES = 20_000   # code files scanned (seed reads as many: infra/seed.py CODE_FILES_CAP)
MAX_BYTES = 1_000_000


class InfraCheckError(Exception):
    pass


# ---------------------------------------------------------------- walking the project

def nested_note(rel: str, why: str) -> str:
    """The line said once for a folder walked that looks like a project of its own."""
    return (f"{rel}/ has {why}: walked as part of this project. If it is another project (a product of its own), "
            f'list it in jui.config.json\'s infra.exclude ("exclude": ["{rel}"]) and it is not walked')


def _walk(root: Path, accept, code: bool = False) -> tuple[list[Path], str | None, list[str]]:
    """Files under root that accept(name) takes, walked as seed walks (iac_tables.walk_project: no symlink followed,
    SKIP_DIRS and hidden folders but .github left out; code=True also leaves out the folders seed reads only IaC in);
    and, when the walk stopped at iac_tables.WALK_CAP files, why the rest was not looked at, else None. The cap counts
    every file looked at, not the candidates: a data folder of JSON files no longer uses it up before the Terraform
    (ticket doc-infra-iac-scan-cap-reached-before-terraform)."""
    nested: list = []
    rels, stopped = T.walk_project(root, [root / p for p in R.infra_exclude(root)], nested)
    notes = [nested_note(rel, why) for rel, why in nested]
    out: list[Path] = []
    for rel, iac_only in rels:
        if code and iac_only:
            continue
        p = root / rel
        if accept(p.name) and p.is_file() and not p.is_symlink():
            out.append(p)
    if stopped is None:
        return out, None, notes
    return out, f"more than {T.WALK_CAP} files in the project: the walk stopped in {stopped}/ and the rest was not looked at", notes


def _text(p: Path) -> str | None:
    try:
        if p.stat().st_size > MAX_BYTES:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _text_or_why(p: Path) -> tuple[str | None, str]:
    try:
        size = p.stat().st_size
        if size > MAX_BYTES:
            return None, f"over {MAX_BYTES // 1_000_000} MB"
        return p.read_text(encoding="utf-8-sig", errors="replace"), ""   # a BOM first is not text (Q2)
    except OSError as exc:
        return None, f"unreadable ({exc.strerror or type(exc).__name__})"


HEAD_BYTES = 65_536
_is_cfn = T.is_cfn   # the name stays for seed until (C) imports T


def _iac_by_head(p: Path) -> str | None:
    """Whose IaC a file too big to read is, by its first bytes (a name like stack.yaml or app.yaml says nothing):
    a CloudFormation template (aws), a Kubernetes manifest, a Terraform JSON configuration; None when it is none."""
    if T.iac_kind(p.name) != "by_text":   # a YAML or JSON the name says nothing about
        return None
    try:
        with open(p, "rb") as f:
            head = f.read(HEAD_BYTES).decode("utf-8-sig", errors="replace")
    except OSError:
        return None
    if T.is_cfn(head):
        return "aws"
    if T.is_k8s(p.name, head) or ('"apiVersion"' in head and '"kind"' in head):   # a big .yaml holding JSON too
        return "kubernetes"
    if p.name.endswith(".json") and '"resource"' in head and '"terraform"' in head:
        return "*"
    return None


def _tf_json_modules(data) -> list[tuple[str, str]]:
    blocks = data.get("module") if isinstance(data, dict) else None
    out = []
    for block in (blocks if isinstance(blocks, list) else [blocks]):
        if isinstance(block, dict):
            out.extend((n, str(b.get("source", ""))) for n, b in block.items() if isinstance(b, dict))
    return out


def _tf_json_counted(data) -> bool:
    blocks = data.get("resource") if isinstance(data, dict) else None
    for block in (blocks if isinstance(blocks, list) else [blocks]):
        if isinstance(block, dict):
            for by_name in block.values():
                if isinstance(by_name, dict) and any(isinstance(b, dict) and ("count" in b or "for_each" in b)
                                                     for b in by_name.values()):
                    return True
    return False


def _tf_json_resources(data) -> list[tuple[str, str, object]]:
    """(type, name, body) of the resources of a Terraform JSON configuration (resource: {type: {name: ...}}, or a list
    of such objects, as CDKTF writes it)."""
    out = []
    blocks = data.get("resource") if isinstance(data, dict) else None
    for block in (blocks if isinstance(blocks, list) else [blocks]):
        if isinstance(block, dict):
            for t, by_name in block.items():
                if isinstance(by_name, dict):
                    out.extend((t, n, b) for n, b in by_name.items())
    return out


def _rel(p: Path, root: Path) -> str:
    return PurePosixPath(p.relative_to(root)).as_posix()


# ---------------------------------------------------------------- reading the IaC (tables: infra/iac_tables.py)

# The tables live in infra/iac_tables.py, shared with seed (ticket 2026-10-20-jui-infra-seed-and-check-tables-disagree);
# check spells no IaC type of its own.
# platform settings (firebase.json, serverless.yml, ...): seed reads them, check does not compare them (yet)
NOT_COMPARED = {name: (provider or "*") for name, (provider, _platform) in T.PAAS_FILES.items()}


def _yaml():
    try:
        import yaml
    except ImportError:
        return None

    class Loader(yaml.SafeLoader):
        pass

    def _any(loader, suffix, node):          # CloudFormation's short forms (!Ref, !GetAtt, ...): not evaluated
        return None
    Loader.add_multi_constructor("!", _any)
    return yaml, Loader


def _app_engine(text: str | None) -> bool:
    """app.yaml is App Engine's only with a runtime and no apiVersion: a Kubernetes manifest is often named so too."""
    return bool(text) and bool(re.search(r"^runtime:", text, re.M)) and not T.is_k8s("app.yaml", text)


def _node(found, address, provider, mapping, source, type_, spec=None):
    cat, svc = mapping
    if not cat.startswith("group:"):          # a network, a cluster: a group of the model, not compared as a node
        found.append({"address": address, "provider": provider, "category": cat, "service": svc, "source": source,
                      "type": type_, "spec": spec or []})


def scan_iac(root: Path) -> tuple[list[dict], dict[str, list[str]]]:
    """Resources the project's IaC declares: {address, provider, category, service, source}, and what could not be
    read, per provider ("*" when the provider cannot be told)."""
    found: list[dict] = []
    unverified: dict[str, list[str]] = {}

    def note(provider: str, why: str) -> None:
        unverified.setdefault(provider, [])
        if why not in unverified[provider]:
            unverified[provider].append(why)

    names = lambda n: T.iac_kind(n) is not None or n in NOT_COMPARED  # noqa: E731 — IaC by the table, and the platform settings
    files, stopped, nested = _walk(root, names)
    for line in nested:
        note("*", line)
    y = _yaml()
    unmapped: dict[str, set[str]] = {}
    parts: dict[str, int] = {}
    unread: set[str] = set()
    if stopped:
        # files not looked at may be anyone's IaC, of any kind ("**": every node, not only a Terraform address): no node
        # is said missing and no provider "none found"
        note("*", stopped)
        unread.update({"*", "**"})

    def part(provider: str) -> None:
        parts[provider] = parts.get(provider, 0) + 1

    def not_read(provider: str, why: str) -> None:
        """A file of this provider's IaC that was not read (too big, unreadable, not parsed): said, and its nodes are
        not asked for (run_infra_iac skips them rather than say "missing")."""
        note(provider, why)
        unread.add(provider)
    for p in files:
        rel, name = _rel(p, root), p.name
        if rel.startswith(R.DEFAULT_DIR + "/") or ".check-report" in name:
            continue
        text, why = _text_or_why(p)
        if name in NOT_COMPARED and not (name == "app.yaml" and not _app_engine(text)):
            note(NOT_COMPARED[name], f"{rel}: settings check does not compare yet (seed reads them): its nodes are not compared")
            continue
        if text is None:
            # an IaC file not read is a range not checked: said, never silent — by its name, else by its head
            kind = T.iac_kind(rel)
            who = T.iac_provider(rel) if kind not in (None, "by_text") else _iac_by_head(p)
            if who:
                not_read(who, f"{rel}: {why}: not read")
            continue
        kind = T.iac_kind(rel)
        if kind in ("terraform", "terraform_json"):
            if kind == "terraform_json":
                try:
                    tfj = json.loads(text)
                    pairs = _tf_json_resources(tfj)
                except (ValueError, RecursionError):
                    not_read("*", f"{rel}: not JSON: not read")
                    continue
            else:   # each resource with its body, for its spec (iac_tables.tf_spec)
                pairs = [(m.group(1), m.group(2), text[m.end():T.block_end(text, m.end() - 1)]) for m in T.TF_RESOURCE.finditer(text)]
            file_providers = set()
            for t, n, body in pairs:
                provider = T.tf_provider(t)
                m = T.tf_mapping(t)
                if provider is None:
                    continue
                file_providers.add(provider)
                if m == "part":
                    part(provider)
                    continue
                if m is None:
                    unmapped.setdefault(provider, set()).add(t)
                    continue
                _node(found, T.tf_address(t, n), provider, m, rel, t, T.tf_spec(body))
            if kind == "terraform_json":
                for mname, src in _tf_json_modules(tfj):
                    if not src.startswith(("./", "../")):
                        note("*", f"{rel}: module \"{mname}\" comes from outside the project: its resources were not read")
                if _tf_json_counted(tfj):
                    who = next(iter(file_providers)) if len(file_providers) == 1 else "*"
                    note(who, f"{rel}: count / for_each are not evaluated (a static read; no plan): how many is not checked")
                continue
            for mname, body in re.findall(r'^\s*module\s+"([A-Za-z0-9_-]+)"\s*\{(.*?)^\}', text, re.M | re.S):
                src = re.search(r'^\s*source\s*=\s*"([^"]+)"', body, re.M)
                if src and not src.group(1).startswith(("./", "../")):
                    note("*", f"{rel}: module \"{mname}\" comes from outside the project: its resources were not read")
            if re.search(r"^\s*(?:count|for_each)\s*=", text, re.M):
                who = next(iter(file_providers)) if len(file_providers) == 1 else "*"
                note(who, f"{rel}: count / for_each are not evaluated (a static read; no plan): how many is not checked")
        elif kind == "bicep":
            for sym, t in re.findall(r"^\s*resource\s+([A-Za-z_][A-Za-z0-9_]*)\s+'([^'@]+)@", text, re.M):
                m = T.bicep_mapping(t)
                if m == "part":
                    part("azure")
                    continue
                if m is None:
                    unmapped.setdefault("azure", set()).add(t)
                    continue
                _node(found, T.bicep_address(sym), "azure", m, rel, t)
        elif kind == "wrangler":
            _wrangler(p, rel, text, found, not_read)
        elif kind == "compose":
            if y is None:
                note("docker", f"{rel}: PyYAML is not installed: not read")
                continue
            try:
                data = y[0].load(text, Loader=y[1])
            except Exception:   # noqa: BLE001 — a file that does not parse is said, not fatal
                not_read("docker", f"{rel}: not YAML: not read")
                continue
            for svc, spec in ((data or {}).get("services") or {}).items():
                image = str((spec or {}).get("image") or "") if isinstance(spec, dict) else ""
                _node(found, T.compose_address(rel, svc), "docker", (T.compose_category(image), "compose.service"), rel,
                      "compose.service")
        elif kind in ("cfn", "by_text"):
            kind = T.iac_kind_by_text(rel, text) if kind == "by_text" else kind
            if kind == "cfn":
                _cfn(p, rel, text, y, found, not_read, unmapped, part)
            elif kind == "k8s":
                _k8s(rel, text, y, found, not_read, unmapped, part)
    for provider, n in sorted(parts.items()):
        note(provider, f"{n} resource(s) that are parts of another (attachments, rules, routes, records, ...): not nodes, "
                       "not compared")
    for provider, types in unmapped.items():
        note(provider, f"{len(types)} resource type(s) with no mapping to a category, not compared: "
                       + ", ".join(sorted(types)[:8]) + (" …" if len(types) > 8 else ""))
    if unread:
        unverified["_unread"] = sorted(unread)       # taken out by run_infra_iac: which providers' files were not read
    return found, unverified


def _cfn(p, rel, text, y, found, note, unmapped, part):
    if y is None and not p.name.endswith(".json"):
        note("aws", f"{rel}: PyYAML is not installed: not read")
        return
    try:
        data = json.loads(text) if p.name.endswith(".json") else y[0].load(text, Loader=y[1])
    except Exception:   # noqa: BLE001
        note("aws", f"{rel}: not parsed: not read")
        return
    for logical, res in ((data or {}).get("Resources") or {}).items() if isinstance(data, dict) else []:
        t = (res or {}).get("Type") if isinstance(res, dict) else None
        if not isinstance(t, str):
            continue
        m = T.cfn_mapping(t)
        if m == "part":
            part("aws")
            continue
        if m is None:
            unmapped.setdefault("aws", set()).add(t)
            continue
        _node(found, T.cfn_address(logical), "aws", m, rel, t, T.cfn_spec(res.get("Properties")))


def _k8s(rel, text, y, found, note, unmapped, part):
    try:
        if rel.endswith(".json"):
            data = json.loads(text)
            docs = data.get("items", [data]) if isinstance(data, dict) and data.get("kind") == "List" else [data]
        elif y is None:
            note("kubernetes", f"{rel}: PyYAML is not installed: not read")
            return
        else:
            docs = list(y[0].load_all(text, Loader=y[1]))
    except Exception:   # noqa: BLE001
        note("kubernetes", f"{rel}: not parsed: not read")
        return
    for d in docs:
        if not isinstance(d, dict):
            continue
        kind, name = d.get("kind"), (d.get("metadata") or {}).get("name")
        if not isinstance(kind, str) or not isinstance(name, str):
            continue
        m = T.k8s_mapping(kind, d.get("spec") if isinstance(d.get("spec"), dict) else None)
        if m == "part":
            part("kubernetes")
            continue
        if m is None:
            unmapped.setdefault("kubernetes", set()).add(kind)
            continue
        _node(found, T.k8s_address(kind, name), "kubernetes", m, rel, kind)
    if "{{" in text:
        note("kubernetes", f"{rel}: a Helm template is not rendered: not read as it deploys")


def _wrangler(p, rel, text, found, note):
    try:
        if p.name.endswith(".toml"):
            import tomllib
            data = tomllib.loads(text)
        else:
            data = T.parse_jsonc(text)   # comments and a last ",": the shared reader (seed reads the same way)
    except Exception:   # noqa: BLE001
        note("cloudflare", f"{rel}: not parsed: not read")
        return
    _node(found, T.wrangler_address(rel), "cloudflare", ("compute.function", "workers"), rel, "wrangler.worker")
    for kind, handle, _label, cat, svc in T.wrangler_bindings(data):
        _node(found, T.wrangler_address(rel, kind, handle), "cloudflare", (cat, svc), rel, f"wrangler.{kind}")


# ---------------------------------------------------------------- code: SDKs and environment names

OTHER_CODE = {".go": "Go", ".rb": "Ruby", ".java": "Java", ".kt": "Kotlin", ".swift": "Swift", ".dart": "Dart",
              ".php": "PHP", ".cs": "C#", ".rs": "Rust", ".scala": "Scala", ".ex": "Elixir"}


def scan_code(root: Path) -> tuple[list[dict], list[str]]:
    """What the code names, by infra/code_hints.py (the table seed drafts with): {provider ('' when the import does not
    say whose), category, file, line, why} from Python and JavaScript / TypeScript imports, AWS SDK clients and the
    *names* of environment variables (code and .env.example-like files); and what was not scanned."""
    hints: list[dict] = []
    notes: list[str] = []
    others: dict[str, int] = {}

    def take(name: str) -> bool:
        ext = os.path.splitext(name)[1]
        if ext in OTHER_CODE:
            others[OTHER_CODE[ext]] = others.get(OTHER_CODE[ext], 0) + 1
        return ext in H.CODE_EXT or bool(H.ENV_NAME_FILES.match(name))
    files, stopped, nested = _walk(root, take, code=True)
    notes.extend(nested)
    if stopped:
        notes.append(stopped)
    if len(files) > MAX_CODE_FILES:
        notes.append(f"more than {MAX_CODE_FILES} source files: the rest (from {_rel(files[MAX_CODE_FILES], root)}) "
                     "were not scanned")
        files = files[:MAX_CODE_FILES]
    for lang, n in sorted(others.items()):
        notes.append(f"{n} {lang} file(s): code in {lang} is not read for SDKs or environment names")
    for p in files:
        text, why = _text_or_why(p)
        rel = _rel(p, root)
        if text is None:
            notes.append(f"{rel}: {why}: not scanned")
            continue
        got = H.scan_env_names(rel, text) if H.ENV_NAME_FILES.match(p.name) else H.scan_text(rel, text)
        for (provider, cat, _svc), file, literal, line in got["hits"]:
            hints.append({"provider": provider, "category": cat, "file": file, "line": line,
                          "why": f"environment name {literal}" if literal.isupper() else "import"})
    return hints, notes


# ---------------------------------------------------------------- the checkers

def _model(project_root: Path) -> tuple[dict, str, list[Path]]:
    got = R.read(project_root)
    if not got.get("ok"):
        raise InfraCheckError(f"the infra model cannot be read ({got['reason']}): {got['message']}")
    errs = M.errors(got["problems"])
    if errs:
        raise InfraCheckError(f"the infra model has {len(errs)} error(s): run `jsonui-doc validate infra` first")
    files = [project_root / got["dir"] / f for f in got["files"]]
    return got, got["dir"], files


def _masked(r: ResultItem) -> ResultItem:
    """A report goes to a file and a terminal: names read from IaC or code (a bucket's name, a database's) that have a
    secret's shape are masked, as the model never holds one."""
    for f in ("target", "expected", "actual", "message"):
        v = getattr(r, f)
        if isinstance(v, str) and M.secret_findings(v):
            setattr(r, f, "<masked: holds the shape of a secret>")
    return r


def _status(decl, status: str) -> str:
    return status if getattr(decl, "gate", False) or status in ("ok", "skipped") else "warning"


def _compare_spec(decl, n: dict, hit: list[dict], target: str, results: list[ResultItem]) -> int:
    """A node's declared spec against the values its IaC resources write (the server room ticket's §4): a value that
    differs is a finding (target <node>#spec.<key>); returns how many declared values could not be compared."""
    written: dict[str, tuple[str, str]] = {}
    for f in hit:
        for item in f.get("spec", []):
            written.setdefault(item["key"], (item["value"], f["source"]))
    uncompared = 0
    for item in n.get("spec", []):
        if item["key"] not in written:
            uncompared += 1
            continue
        value, source = written[item["key"]]
        if value != item["value"]:
            results.append(ResultItem(f"{target}#spec.{item['key']}", _status(decl, "mismatch"), "metadata",
                                      expected=item["value"], actual=value, message=f"spec {item['key']} differs from {source}"))
    return uncompared


def run_infra_iac(decl, project_root: Path) -> CheckReport:
    model, folder, model_files = _model(project_root)
    found, unverified = scan_iac(project_root)
    unread = set(unverified.pop("_unread", []))
    ignore = set(getattr(decl, "ignore_types", []) or [])
    found = [f for f in found if f["type"] not in ignore]
    nodes = [n for n in model["nodes"] if n["managed_by"] == "iac"]
    results: list[ResultItem] = []
    claimed: set[str] = set()
    spec_uncompared = 0
    by_provider: dict[str, list[dict]] = {}
    for f in found:
        by_provider.setdefault(f["provider"], []).append(f)
    declared_providers = {n["providerResolved"] or "?" for n in nodes}
    # unread: its files are there. A file not read whose provider is not known ("*" in unread: over the size, not
    # parsed) may be this provider's: then "none found" is not said (the independent fourth verification Q4), only that some were
    # not read. ("*" notes that are no unread file — a PaaS setting, a module from outside — change nothing here.)
    for provider in sorted(declared_providers - set(by_provider) - {"?"} - unread):
        unverified.setdefault(provider, []).append(
            "no IaC read for this provider: some IaC files were not read (see *): its nodes are not compared" if "*" in unread
            else "no IaC found for this provider in the project: its nodes are not compared")
    for n in nodes:
        provider = n["providerResolved"] or "?"
        target = f"{provider}/{n['id']}"
        if not n.get("iac"):
            results.append(ResultItem(target, "skipped", "metadata", message="no iac address on the node: not compared"))
            continue
        platforms = {T.paas_platform(a) for a in n["iac"]}
        if None not in platforms:          # serverless:hello, firebase:hosting, ...: settings check does not compare
            results.append(ResultItem(target, "skipped", "metadata",
                                      message=f"{', '.join(sorted(platforms))} settings are not compared by check"))
            unverified.setdefault(provider, [])
            why = f"nodes from {', '.join(sorted(platforms))} settings are not compared"
            if why not in unverified[provider]:
                unverified[provider].append(why)
            continue
        if provider not in by_provider:
            results.append(ResultItem(target, "skipped", "metadata", message=f"no IaC read for {provider}"))
            continue
        hit = [f for f in by_provider[provider] for a in n["iac"] if T.matches(a, f["address"])]
        if hit:
            claimed.update(f["address"] for f in hit)
            cats = {f["category"] for f in hit}
            if n["category"] in cats:
                results.append(ResultItem(target, "ok", "metadata"))
            else:
                results.append(ResultItem(target, _status(decl, "mismatch"), "metadata", expected=n["category"],
                                          actual=", ".join(sorted(cats)), message=f"category differs from {hit[0]['source']}"))
            spec_uncompared += _compare_spec(decl, n, hit, target, results)
        elif provider in unread or "**" in unread or ("*" in unread and any(T.is_terraform_address(a) for a in n["iac"])):
            # one of this provider's IaC files was not read, or a Terraform file (anyone's) and the node's address is
            # a Terraform one: not there is not known. A compose or wrangler address cannot be in a Terraform file.
            results.append(ResultItem(target, "skipped", "metadata", expected=", ".join(n["iac"]),
                                      message="not found in what was read, and an IaC file was not read (see unverified)"))
        else:
            results.append(ResultItem(target, _status(decl, "missing_in_impl"), "metadata", expected=", ".join(n["iac"]),
                                      message="declared, but no such resource in this provider's IaC"))
    if spec_uncompared:
        unverified.setdefault("*", []).append(
            f"{spec_uncompared} declared spec value(s) not compared: the IaC writes no value for them (a variable, a "
            "reference, or a key iac_tables.TF_SPEC / CFN_SPEC does not know)")
    folded_quiet = 0
    for f in found:
        if f["address"] in claimed:
            continue
        if T.optional(f["category"]):          # IAM, policy, alarm: compared when declared, not asked for
            folded_quiet += 1
            continue
        if f["address"] not in claimed:
            results.append(ResultItem(f"{f['provider']}/{f['address']}", _status(decl, "missing_in_doc"), "metadata",
                                      actual=f["category"], message=f"in {f['source']}, but no node names it in iac"))
    results = [_masked(r) for r in results]
    rep = CheckReport(checker="builtin:infra-iac", target_kind="infra", target_name="infra-iac",
                      target_extra={"dir": folder, "unverified": unverified, "gate": bool(getattr(decl, "gate", False))},
                      input_hashes=compute_input_hashes(model_files, project_root), results=results, unit="resource")
    rep.warnings = [f"[unverified] {p}: {why}" for p, whys in sorted(unverified.items()) for why in whys]
    if folded_quiet:
        rep.warnings.append(f"{folded_quiet} IAM / policy / alarm resource(s) in the IaC are not declared: folded by "
                            "default, so not asked for (declare them to have them compared)")
    return rep


def run_infra_code(decl, project_root: Path) -> CheckReport:
    model, folder, model_files = _model(project_root)
    results: list[ResultItem] = []
    for n in model["nodes"]:
        for i, ev in enumerate(n.get("evidence") or []):
            target = f"{n['providerResolved'] or '?'}/{n['id']}#evidence/{i}"
            raw = R.read_capped(project_root, ev["file"], MAX_BYTES)
            if not isinstance(raw, bytes):
                results.append(ResultItem(target, _status(decl, "missing_in_impl"), "proof", expected=ev["file"],
                                          message="the evidence file is not there"))
            elif ev.get("pattern") and ev["pattern"] not in raw.decode("utf-8", errors="replace"):
                results.append(ResultItem(target, _status(decl, "missing_in_impl"), "proof", expected=ev["file"],
                                          message="the evidence pattern is no longer in the file"))
            else:
                results.append(ResultItem(target, "ok", "proof"))
    hints, notes = scan_code(project_root)
    providers = {n["providerResolved"] for n in model["nodes"]} | {n.get("provider") for n in model["nodes"]}
    categories = {n["category"] for n in model["nodes"]}
    seen: set[tuple] = set()
    for h in hints:
        key = (h["provider"], h["category"])
        if key in seen:
            continue
        seen.add(key)
        # a hint that names its provider answers to a node of that provider; one that does not (a database driver, a
        # cache's URL variable) to a node of its category
        known = (h["provider"] in providers) if h["provider"] else (h["category"] in categories)
        target = f"code/{h['provider'] or h['category']}"
        if known:
            results.append(ResultItem(target, "ok", "sampled"))
        else:
            results.append(ResultItem(target, _status(decl, "missing_in_doc"), "sampled",
                                      actual=h["provider"] or h["category"],
                                      message=f"{h['file']}:{h['line']} ({h['why']}) — no node for it"))
    results = [_masked(r) for r in results]
    rep = CheckReport(checker="builtin:infra-code", target_kind="infra", target_name="infra-code",
                      target_extra={"dir": folder, "unverified": {"*": notes} if notes else {},
                                    "gate": bool(getattr(decl, "gate", False))},
                      input_hashes=compute_input_hashes(model_files, project_root), results=results, unit="reference")
    rep.warnings = [f"[unverified] *: {n}" for n in notes] + [
        "[unverified] *: only Python and JavaScript / TypeScript imports, AWS SDK clients and environment variable names "
        "are read (not values, not calls): a service reached another way is not seen"]
    return rep


def run_infra_load(decl, project_root: Path) -> CheckReport:
    """builtin:infra-load — each load definition (the cost simulator, infra/load.py) against the model: a node billed by
    use (its pricing rule reads quantities and is not billed by the hour) with no load is missing_in_doc (its load is
    undefined, not 0); a row naming a node the model does not have is missing_in_impl; a node with its load is ok. A
    node billed by the hour with no row runs the model's count all the time: ok. Which nodes have no price is the
    cost's (L-B) to say."""
    from ..infra import load as LD   # noqa: PLC0415
    from ..infra import rules as RULES   # noqa: PLC0415
    got = LD.read(project_root)
    if not got.get("ok"):
        raise InfraCheckError(f"the load definitions cannot be read ({got['reason']}): {got['message']}")
    errs = M.errors(got["problems"])
    if errs:
        raise InfraCheckError(f"the load definitions have {len(errs)} error(s): run `jsonui-doc validate infra-load` first")
    model = R.read(project_root)
    results: list[ResultItem] = []
    for sc in got["scenarios"]:
        loaded = {row["node"] for row in sc["loads"]}
        for p in got["problems"]:
            if p["file"] == sc["file"] and p["code"] == "load.node_missing":
                results.append(ResultItem(f"load/{sc['id']}/{p['node']}", _status(decl, "missing_in_impl"), "metadata",
                                          message="the load definition names a node the model does not have"))
        for n in model["nodes"]:
            if sc["environment"] not in n["environments"]:
                continue
            target = f"load/{sc['id']}/{n['id']}"
            rule = RULES.lookup(n)
            if n["id"] in loaded:
                results.append(ResultItem(target, "ok", "metadata"))
            elif rule is None or not rule.reads:
                results.append(ResultItem(target, "skipped", "metadata", message="its kind reads no load"))
            elif rule.hourly:
                results.append(ResultItem(target, "ok", "metadata",
                                          message="no load: billed by the hour, it runs the model's count all the time"))
            else:
                results.append(ResultItem(target, _status(decl, "missing_in_doc"), "metadata",
                                          expected=", ".join(rule.reads),
                                          message="billed by use, but this load definition gives it no load (undefined, not 0)"))
    files = [project_root / got["dir"] / f for f in got["files"]] + [project_root / model["dir"] / f for f in model["files"]]
    rep = CheckReport(checker="builtin:infra-load", target_kind="infra", target_name="infra-load",
                      target_extra={"dir": got["dir"], "scenarios": [s["id"] for s in got["scenarios"]],
                                    "gate": bool(getattr(decl, "gate", False))},
                      input_hashes=compute_input_hashes(files, project_root), results=[_masked(r) for r in results],
                      unit="node")
    rep.warnings = [f"{p['file']} {p['path']}: {p['message']} [{p['code']}]" for p in got["problems"]
                    if p["severity"] == "warning" and p["code"] != "load.node_missing"]
    if not got["scenarios"]:
        rep.warnings.append(f"no load definition in {got['dir']}: nothing compared")
    return rep
