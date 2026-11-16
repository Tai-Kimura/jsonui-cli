"""Every top-level key of jui.config.json a tool reads is one shared/core/config_keys.py knows (ticket
jui-config-keys-infra-exclude-unknown-top-level: infra.exclude, new in 2.3.17, made `jui build` say "no tool reads
'infra'" 28 times on a consumer's face, and infra had been read since 2.3.9; db and build were missing the same way).

The keys are collected from the readers' code, not listed by hand: in jui_tools, document_tools, test_tools and
shared/core, a name holding the loaded config —
  * json.load / json.loads in a function that names jui.config.json (or CONFIG_NAME),
  * a call of one of the config loaders (CONFIG_LOADERS),
  * .load() of a ConfigManager (self in config_manager.py, or a name ending config_mgr / config_manager),
  * a parameter named like one (PARAMS) in a file that names jui.config.json —
and the string keys read off it: name.get("k"), name["k"], "k" in name. What it cannot see: a key read through a
name it does not follow (an attribute, a dict passed on under another name). The other direction holds the list
honest too: every known key is read somewhere the scan sees, but the ones NOT_SEEN names with why.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli import shared_core

ROOT = Path(__file__).resolve().parents[2]
TREES = ("jui_tools/jui_cli", "document_tools/jsonui_doc_cli", "test_tools/jsonui_test_cli", "shared/core")
CONFIG_LOADERS = {"read_config", "load_config_dict", "load_project_config", "find_project_config",
                  "_find_project_config", "_load_test_config", "_read_config_doc"}
PARAMS = {"config", "cfg", "jui_config", "project_config", "raw_config"}
#: Known keys the scan does not see read, and why. Closed: one that becomes seen is red too.
NOT_SEEN = {"project_name": "init writes it into every new config (init_cmd); nothing reads it back"}


def _names_the_file(node) -> bool:
    return any((isinstance(n, ast.Constant) and n.value == "jui.config.json")
               or (isinstance(n, ast.Name) and n.id == "CONFIG_NAME") for n in ast.walk(node))


def _loads_the_config(call: ast.Call, fn_names_it: bool, path: Path) -> bool:
    f = call.func
    name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
    if name in CONFIG_LOADERS:
        return True
    if name in ("load", "loads") and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        owner = f.value.id
        if owner == "json":
            return fn_names_it
        return owner.endswith(("config_mgr", "config_manager")) or (owner == "self" and path.name == "config_manager.py")
    return False


def _key(n, names):
    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("get", "pop", "setdefault")
            and isinstance(n.func.value, ast.Name) and n.func.value.id in names and n.args
            and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
        return n.args[0].value
    if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id in names
            and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)):
        return n.slice.value
    if (isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], (ast.In, ast.NotIn))
            and isinstance(n.left, ast.Constant) and isinstance(n.left.value, str)
            and isinstance(n.comparators[0], ast.Name) and n.comparators[0].id in names):
        return n.left.value
    return None


def readers(source: str, path: Path) -> dict[str, list[str]]:
    """key -> where it is read, in one file."""
    tree = ast.parse(source)
    file_names_it = _names_the_file(tree)
    out: dict[str, list[str]] = {}
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        fn_names_it = _names_the_file(fn)
        names = {a.arg for a in fn.args.args + fn.args.kwonlyargs if a.arg in PARAMS} if file_names_it else set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and _loads_the_config(n.value, fn_names_it, path):
                for t in n.targets:
                    first = t.elts[0] if isinstance(t, ast.Tuple) and t.elts else t
                    if isinstance(first, ast.Name):
                        names.add(first.id)
        for n in ast.walk(fn):
            if (k := _key(n, names)) is not None:
                out.setdefault(k, []).append(f"{path}:{n.lineno}")
    return out


def read_keys() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for tree in TREES:
        for p in sorted((ROOT / tree).rglob("*.py")):
            if "tests" in p.relative_to(ROOT).parts:
                continue
            for k, where in readers(p.read_text(encoding="utf-8"), p.relative_to(ROOT)).items():
                found.setdefault(k, []).extend(where)
    return found


def keys():
    return shared_core.load("config_keys")


def test_every_key_a_reader_reads_is_known():
    found = read_keys()
    assert {k: v[:3] for k, v in found.items() if k not in keys().KNOWN_TOP_LEVEL} == {}


def test_every_known_key_is_read_or_named_why_not():
    found = read_keys()
    assert sorted(k for k in keys().KNOWN_TOP_LEVEL if k not in found) == sorted(NOT_SEEN)


def test_the_scan_reaches_the_readers_the_ticket_names():
    """infra in the server room's reader, db in the legacy declaration, build in normalizeLayouts."""
    found = read_keys()
    assert any(w.startswith("document_tools/jsonui_doc_cli/infra/room.py") for w in found.get("infra", []))
    assert any(w.startswith("document_tools/jsonui_doc_cli/project_config.py") for w in found.get("db", []))
    assert any(w.startswith("jui_tools/jui_cli/commands/build_cmd.py") for w in found.get("build", []))


def test_the_scan_sees_each_way_of_holding_the_config():
    src = '''
import json
def a(root):
    config = json.loads((root / "jui.config.json").read_text())
    return config.get("alpha"), config["beta"], "gamma" in config
def b(config_mgr):
    config = config_mgr.load()
    return config.get("delta")
def c(path):
    cfg, where = find_project_config(path)
    return cfg.get("epsilon")
def d(other):
    return other.get("not_a_config_key")
'''
    assert sorted(readers(src, Path("x.py"))) == ["alpha", "beta", "delta", "epsilon", "gamma"]


def test_the_warning_path_is_quiet_for_the_keys_the_tools_read():
    """The path that warned on the consumers' faces (openapi_canonical: a config holding API documents, the parameter case
    resolved): a config with infra.exclude, db and build.normalizeLayouts names no unknown key."""
    canon = shared_core.load("openapi_canonical")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs" / "api").mkdir(parents=True)
        (root / "docs" / "api" / "s.json").write_text(json.dumps(
            {"swagger": "2.0", "info": {"title": "t", "version": "1"},
             "paths": {"/a": {"get": {"parameters": [{"name": "page_size", "in": "query", "type": "integer"}],
                                      "responses": {"200": {"description": "ok"}}}}}}), encoding="utf-8")
        (root / "jui.config.json").write_text(json.dumps(
            {"api_directory": "docs/api", "infra": {"exclude": ["other-app"]},
             "db": {"dialect": "postgresql"}, "build": {"normalizeLayouts": False}}), encoding="utf-8")
        spec = root / "docs" / "screens" / "s.spec.json"
        spec.parent.mkdir(parents=True)
        spec.write_text("{}", encoding="utf-8")
        ctx = canon.build_spec_canon_context(spec)
    assert ctx.index, "the config answered (the warning path ran)"
    assert ctx.unknown_config_keys == ()
