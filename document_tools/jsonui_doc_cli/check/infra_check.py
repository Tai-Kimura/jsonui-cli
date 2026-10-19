"""check kind=infra: the room's declared infrastructure (docs/infra, boundary §6) against what the project's own files say.

builtin:infra-iac — the IaC and deploy settings in the project (Docker Compose, Terraform / OpenTofu HCL, CloudFormation
/ SAM and a synthesized CDK app's cdk.out, Bicep, Kubernetes manifests, Cloudflare wrangler), read statically: no
credentials, no plan, no state (state holds secrets in the clear). Each resource gets its provider, category and
address from infra/iac_tables.py — the one table seed drafts with — parts of another resource (attachments, rules,
routes, records, ...) are dropped, and IAM, policies and alarms are compared when declared and not asked for when not
(they are folded by default); each provider's resources are compared with that provider's declared nodes
(providerResolved) through their ``iac`` addresses.

builtin:infra-code — the code: every node's ``evidence`` (the file is there, the pattern still in it), and the services
the code talks to by its SDK imports and the *names* of its environment variables (never their values), against the
declared nodes.

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

from ..infra import iac_tables as T
from ..infra import model as M
from ..infra import room as R
from .report import CheckReport, ResultItem, compute_input_hashes

SKIP_DIRS = {".git", "node_modules", "vendor", "build", "dist", ".terraform", ".venv", "venv", "__pycache__", "Pods",
             ".next", ".wrangler", "target", ".gradle", "DerivedData"}   # cdk.out is read: a synthesized CDK app
MAX_FILES = 5000
MAX_BYTES = 1_000_000


class InfraCheckError(Exception):
    pass


# ---------------------------------------------------------------- walking the project

def _walk(root: Path, accept) -> tuple[list[Path], bool]:
    """Files under root (no symlink followed, SKIP_DIRS and hidden folders left out) that accept(name) takes, at most
    MAX_FILES; the bool says whether the cap was reached."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if accept(name) and p.is_file() and not p.is_symlink():
                out.append(p)
                if len(out) >= MAX_FILES:
                    return out, True
    return out, False


def _text(p: Path) -> str | None:
    try:
        if p.stat().st_size > MAX_BYTES:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _rel(p: Path, root: Path) -> str:
    return PurePosixPath(p.relative_to(root)).as_posix()


# ---------------------------------------------------------------- reading the IaC (tables: infra/iac_tables.py)

# The tables live in infra/iac_tables.py, shared with seed (ticket 2026-10-20-jui-infra-seed-and-check-tables-disagree).
# These names stay for code that imported them from here; new code imports iac_tables.
TF_PROVIDER = T.TF_PROVIDER
TF_CATEGORY = {t: (None if c.startswith("group:") else c) for t, (c, _s) in T.TF_TYPES.items()}
CFN_CATEGORY = {t: c for t, (c, _s) in T.CFN_TYPES.items() if not c.startswith("group:")}
K8S_CATEGORY = {k: T.k8s_mapping(k)[0] for k in (*T.K8S_WORKLOAD, "CronJob", "Ingress", "PersistentVolumeClaim")}
COMPOSE_IMAGE = T.COMPOSE_IMAGE
COMPOSE_NAMES = re.compile(r"^(?:docker-)?compose(?:\.[\w-]+)?\.ya?ml$")
WRANGLER = re.compile(r"^wrangler\.(?:toml|json|jsonc)$")
# settings files seed reads and check does not compare (yet): file name -> provider
NOT_COMPARED = {"firebase.json": "firebase", "render.yaml": "render", "serverless.yml": "aws", "serverless.yaml": "aws",
                "vercel.json": "vercel", "netlify.toml": "netlify", "fly.toml": "fly", "app.yaml": "gcp", "Procfile": "heroku"}


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
    return bool(text) and bool(re.search(r"^runtime:", text, re.M)) and not re.search(r"^apiVersion:", text, re.M)


def _node(found, address, provider, mapping, source):
    cat, svc = mapping
    if not cat.startswith("group:"):          # a network, a cluster: a group of the model, not compared as a node
        found.append({"address": address, "provider": provider, "category": cat, "service": svc, "source": source})


def scan_iac(root: Path) -> tuple[list[dict], dict[str, list[str]]]:
    """Resources the project's IaC declares: {address, provider, category, service, source}, and what could not be
    read, per provider ("*" when the provider cannot be told)."""
    found: list[dict] = []
    unverified: dict[str, list[str]] = {}

    def note(provider: str, why: str) -> None:
        unverified.setdefault(provider, [])
        if why not in unverified[provider]:
            unverified[provider].append(why)

    names = lambda n: n.endswith((".tf", ".yaml", ".yml", ".json", ".toml", ".jsonc", ".bicep")) or n == "Procfile"  # noqa: E731
    files, capped = _walk(root, names)
    if capped:
        note("*", f"more than {MAX_FILES} candidate files: the rest were not read")
    y = _yaml()
    unmapped: dict[str, set[str]] = {}
    for p in files:
        rel, name = _rel(p, root), p.name
        if rel.startswith(R.DEFAULT_DIR + "/") or ".check-report" in name:
            continue
        text = _text(p)
        if name in NOT_COMPARED and not (name == "app.yaml" and not _app_engine(text)):
            note(NOT_COMPARED[name], f"{rel}: settings check does not compare yet (seed reads them): its nodes are not compared")
            continue
        if text is None:
            continue
        if name.endswith(".tf"):
            for t, n in re.findall(r'^\s*resource\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"', text, re.M):
                provider = T.tf_provider(t)
                m = T.tf_mapping(t)
                if provider is None or m == "part":
                    continue
                if m is None:
                    unmapped.setdefault(provider, set()).add(t)
                    continue
                _node(found, T.tf_address(t, n), provider, m, rel)
            for mname, body in re.findall(r'^\s*module\s+"([A-Za-z0-9_-]+)"\s*\{(.*?)^\}', text, re.M | re.S):
                src = re.search(r'^\s*source\s*=\s*"([^"]+)"', body, re.M)
                if src and not src.group(1).startswith(("./", "../")):
                    note("*", f"{rel}: module \"{mname}\" comes from outside the project: its resources were not read")
            if re.search(r"^\s*(?:count|for_each)\s*=", text, re.M):
                note("*", f"{rel}: count / for_each are not evaluated (a static read; no plan): how many is not checked")
        elif name.endswith(".bicep"):
            for sym, t in re.findall(r"^\s*resource\s+([A-Za-z_][A-Za-z0-9_]*)\s+'([^'@]+)@", text, re.M):
                m = T.bicep_mapping(t)
                if m == "part":
                    continue
                if m is None:
                    unmapped.setdefault("azure", set()).add(t)
                    continue
                _node(found, T.bicep_address(sym), "azure", m, rel)
        elif WRANGLER.match(name):
            _wrangler(p, rel, text, found, note)
        elif COMPOSE_NAMES.match(name):
            if y is None:
                note("docker", f"{rel}: PyYAML is not installed: not read")
                continue
            try:
                data = y[0].load(text, Loader=y[1])
            except Exception:   # noqa: BLE001 — a file that does not parse is said, not fatal
                note("docker", f"{rel}: not YAML: not read")
                continue
            for svc, spec in ((data or {}).get("services") or {}).items():
                image = str((spec or {}).get("image") or "") if isinstance(spec, dict) else ""
                _node(found, T.compose_address(rel, svc), "docker", (T.compose_category(image), "compose.service"), rel)
        elif name.endswith((".yaml", ".yml", ".json")):
            if "/cdk.out/" in f"/{rel}" and name.endswith(".template.json") or "AWSTemplateFormatVersion" in text \
                    or "AWS::" in text:
                _cfn(p, rel, text, y, found, note, unmapped)
            elif re.search(r"^apiVersion:", text, re.M) and re.search(r"^kind:", text, re.M):
                _k8s(rel, text, y, found, note, unmapped)
    for provider, types in unmapped.items():
        note(provider, f"{len(types)} resource type(s) with no mapping to a category, not compared: "
                       + ", ".join(sorted(types)[:8]) + (" …" if len(types) > 8 else ""))
    return found, unverified


def _cfn(p, rel, text, y, found, note, unmapped):
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
            continue
        if m is None:
            unmapped.setdefault("aws", set()).add(t)
            continue
        _node(found, T.cfn_address(logical), "aws", m, rel)


def _k8s(rel, text, y, found, note, unmapped):
    if y is None:
        note("kubernetes", f"{rel}: PyYAML is not installed: not read")
        return
    try:
        docs = list(y[0].load_all(text, Loader=y[1]))
    except Exception:   # noqa: BLE001
        note("kubernetes", f"{rel}: not YAML: not read")
        return
    for d in docs:
        if not isinstance(d, dict):
            continue
        kind, name = d.get("kind"), (d.get("metadata") or {}).get("name")
        if not isinstance(kind, str) or not isinstance(name, str):
            continue
        m = T.k8s_mapping(kind, d.get("spec") if isinstance(d.get("spec"), dict) else None)
        if m == "part":
            continue
        if m is None:
            unmapped.setdefault("kubernetes", set()).add(kind)
            continue
        _node(found, T.k8s_address(kind, name), "kubernetes", m, rel)
    if "{{" in text:
        note("kubernetes", f"{rel}: a Helm template is not rendered: not read as it deploys")


def _wrangler(p, rel, text, found, note):
    try:
        if p.name.endswith(".toml"):
            import tomllib
            data = tomllib.loads(text)
        else:
            data = json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))
    except Exception:   # noqa: BLE001
        note("cloudflare", f"{rel}: not parsed: not read")
        return
    _node(found, T.wrangler_address(rel), "cloudflare", ("compute.function", "workers"), rel)
    for kind, handle, _label, cat, svc in T.wrangler_bindings(data):
        _node(found, T.wrangler_address(rel, kind, handle), "cloudflare", (cat, svc), rel)


# ---------------------------------------------------------------- code: SDKs and environment names

SDK_HINTS = (  # (regex on an import / require line, provider, category or None)
    (r"\bboto3\b|@aws-sdk/|aws-sdk", "aws", None), (r"google[.-]cloud|@google-cloud/", "gcp", None),
    (r"firebase-admin|firebase/", "firebase", None), (r"@azure/|azure[.-]", "azure", None),
    (r"@supabase/supabase-js|\bsupabase\b", "supabase", None), (r"\bstripe\b", "stripe", "external.saas"),
    (r"\bopenai\b", "openai", "external.saas"), (r"\banthropic\b", "anthropic", "external.saas"),
    (r"@sendgrid/|\bsendgrid\b", "sendgrid", "mail"), (r"\btwilio\b", "twilio", "external.saas"),
    (r"@auth0/|\bauth0\b", "auth0", "auth"), (r"\bsentry[_-]sdk\b|@sentry/", "sentry", "monitoring"),
)
ENV_HINTS = ((r"\bDATABASE_URL\b|\b(?:DB|POSTGRES|MYSQL)_HOST\b", "database.relational"),
             (r"\bREDIS_(?:URL|HOST)\b", "cache"), (r"\b[A-Z_]*S3_BUCKET[A-Z_]*\b|\bGCS_BUCKET\b", "storage.object"),
             (r"\bSMTP_HOST\b", "mail"), (r"\b(?:SQS|PUBSUB)_[A-Z_]*\b", "queue"))
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rb", ".kt", ".java", ".swift", ".dart")
IMPORT_LINE = re.compile(r"^\s*(?:import\b|from\s+\S+\s+import\b|const\s+.*=\s*require\(|require\b|use\b).*$", re.M)


def scan_code(root: Path) -> tuple[list[dict], list[str]]:
    """What the code names: {provider|None, category|None, file, line, why} from import lines and environment
    variable *names*; and what was not scanned."""
    hints: list[dict] = []
    notes: list[str] = []
    files, capped = _walk(root, lambda n: n.endswith(CODE_EXT) or n in (".env.example", "env.example"))
    if capped:
        notes.append(f"more than {MAX_FILES} source files: the rest were not scanned")
    for p in files:
        text = _text(p)
        if text is None:
            continue
        rel = _rel(p, root)
        for m in IMPORT_LINE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            for rx, provider, cat in SDK_HINTS:
                if re.search(rx, m.group(0)):
                    hints.append({"provider": provider, "category": cat, "file": rel, "line": line, "why": "import"})
        for rx, cat in ENV_HINTS:
            for m in re.finditer(rx, text):
                hints.append({"provider": None, "category": cat, "file": rel,
                              "line": text.count("\n", 0, m.start()) + 1, "why": f"environment name {m.group(0)}"})
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


def _status(decl, status: str) -> str:
    return status if getattr(decl, "gate", False) or status in ("ok", "skipped") else "warning"


def run_infra_iac(decl, project_root: Path) -> CheckReport:
    model, folder, model_files = _model(project_root)
    found, unverified = scan_iac(project_root)
    ignore = set(getattr(decl, "ignore_types", []) or [])
    found = [f for f in found if f["address"].split(".")[0] not in ignore]
    nodes = [n for n in model["nodes"] if n["managed_by"] == "iac"]
    results: list[ResultItem] = []
    claimed: set[str] = set()
    by_provider: dict[str, list[dict]] = {}
    for f in found:
        by_provider.setdefault(f["provider"], []).append(f)
    declared_providers = {n["providerResolved"] or "?" for n in nodes}
    for provider in sorted(declared_providers - set(by_provider) - {"?"}):
        unverified.setdefault(provider, []).append("no IaC found for this provider in the project: its nodes are not compared")
    for n in nodes:
        provider = n["providerResolved"] or "?"
        target = f"{provider}/{n['id']}"
        if not n.get("iac"):
            results.append(ResultItem(target, "skipped", "metadata", message="no iac address on the node: not compared"))
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
        else:
            results.append(ResultItem(target, _status(decl, "missing_in_impl"), "metadata", expected=", ".join(n["iac"]),
                                      message="declared, but no such resource in this provider's IaC"))
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
        known = (h["provider"] in providers) if h["provider"] else (h["category"] in categories)
        target = f"code/{h['provider'] or h['category']}"
        if known:
            results.append(ResultItem(target, "ok", "sampled"))
        else:
            results.append(ResultItem(target, _status(decl, "missing_in_doc"), "sampled",
                                      actual=h["provider"] or h["category"],
                                      message=f"{h['file']}:{h['line']} ({h['why']}) — no node for it"))
    rep = CheckReport(checker="builtin:infra-code", target_kind="infra", target_name="infra-code",
                      target_extra={"dir": folder, "unverified": {"*": notes} if notes else {},
                                    "gate": bool(getattr(decl, "gate", False))},
                      input_hashes=compute_input_hashes(model_files, project_root), results=results, unit="reference")
    rep.warnings = [f"[unverified] *: {n}" for n in notes] + [
        "[unverified] *: only import lines and environment variable names are read (not values, not calls): a service "
        "reached another way is not seen"]
    return rep
