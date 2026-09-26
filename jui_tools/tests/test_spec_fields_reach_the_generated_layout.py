"""What `jui g project` does with the fields a screen spec gives it.

1. A uiVariable's initial value, on the screen path (stateManagement) and the
   cell path (structure.collection.cell): `defaultValue` — the spelling the
   agents pack teaches — and `default`, the older one, both reach the Layout
   JSON `data` section; `defaultValue` wins when both are given (and the other
   is named); false / 0 / "" are values. Until 1.8.121 the screen path read
   `default` only, so `"defaultValue": "gone"` became the type's "" without a
   word (`jui verify` compares data names only), and the cell path's
   `default or defaultValue` let a falsy `default` fall through.
2. `structure.collection.lazy: false` — declared by the spec schema ("a plain
   VStack/Column/div ... NO scroll container") — reaches the Collection node as
   the Layout's `"lazy": "none"`; until 1.8.121 it was dropped.
3. Every field the spec schema declares for the sections extract_screen_spec
   reads is either read by `jui g project` or named below with the reason it
   is not — measured by running a spec synthesized from the schema, with every
   dict recording the keys asked of it, through the extractor and the Layout
   JSON generators. A field added to the schema and read by nothing, or a
   reader removed, turns this red.

Ticket generate-commands-overwrite-edited-files-and-ignore-their-flags,
round 4 (from the pack lane's audit).
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from jui_cli.core.spec_extractor import extract_screen_spec
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.cell_layout_generator import CellLayoutGenerator
from jui_cli.generators.layout_generator import LayoutGenerator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = REPO_ROOT / "document_tools" / "jsonui_doc_cli" / "spec_doc" / "screen_spec_schema.py"


def _spec(ui_variables: list[dict], collection: dict | None = None) -> dict:
    coll = collection or {"id": "list", "cell": {
        "root": {"id": "cell_root", "type": "View"}, "generateCellLayout": True,
        "uiVariables": json.loads(json.dumps(ui_variables))}}
    return {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Probe", "displayName": "P", "description": "p"},
        "structure": {"components": [], "collection": coll},
        "stateManagement": {"uiVariables": json.loads(json.dumps(ui_variables))},
    }


def _data(spec: dict) -> tuple[dict, dict]:
    s = extract_screen_spec(spec)
    lg = LayoutGenerator(TypeMapper())
    screen = {e["name"]: e.get("defaultValue", "<absent>") for e in lg._build_data_section(s)}
    cell = {e["name"]: e.get("defaultValue", "<absent>")
            for e in CellLayoutGenerator(lg)._build_cell_data_section(s.collection)}
    return screen, cell


# [name, type, the spelling(s) given, what the data section must get]
CASES = [
    ("viaDefaultValue", "String", {"defaultValue": "gone"}, "gone"),
    ("viaDefault", "String", {"default": "gone"}, "gone"),
    ("boolTrueDefaultValue", "Bool", {"defaultValue": True}, True),
    ("boolFalseDefault", "Bool", {"default": False}, False),
    ("zeroDefaultSevenDefaultValue", "Int", {"default": 0, "defaultValue": 7}, 7),
    ("emptyDefaultValue", "String", {"defaultValue": ""}, ""),
    ("both", "String", {"default": "a", "defaultValue": "b"}, "b"),
    ("neither", "String", {}, ""),  # the type's own default
]


@pytest.mark.parametrize("name,type_,given,want", CASES, ids=[c[0] for c in CASES])
def test_a_variables_initial_value_reaches_the_data_section_on_both_paths(name, type_, given, want, capsys):
    var = {"name": name, "type": type_, "description": "d", **given}
    screen, cell = _data(_spec([var]))
    assert screen[name] == want, f"screen path: {given} -> {screen[name]!r}"
    assert cell[name] == want, f"cell path: {given} -> {cell[name]!r}"


def test_both_spellings_with_different_values_are_named(capsys):
    _data(_spec([{"name": "both", "type": "String", "description": "d", "default": "a", "defaultValue": "b"}]))
    said = capsys.readouterr().out
    for where in ("stateManagement.uiVariables", "structure.collection.cell.uiVariables"):
        assert (f"WARNING: {where} 'both': both defaultValue (\"b\") and default (\"a\") are given; "
                f"defaultValue is used") in said, said


def test_the_same_value_in_both_spellings_says_nothing(capsys):
    _data(_spec([{"name": "same", "type": "String", "description": "d", "default": "x", "defaultValue": "x"}]))
    assert "WARNING" not in capsys.readouterr().out


def _collection_node(lazy) -> dict:
    coll = {"id": "list", "cell": {"root": "cell_root"}}
    if lazy is not None:
        coll["lazy"] = lazy
    spec = _spec([], coll)
    # The Collection node is appended to the layout tree's children: a spec
    # without structure.layout gets none (reported with this round).
    spec["structure"]["layout"] = {"root": "probe_root", "children": []}
    layout = LayoutGenerator(TypeMapper()).generate(extract_screen_spec(spec))
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "Collection":
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(layout)
    assert len(found) == 1, layout
    return found[0]


def test_a_collection_declared_not_lazy_is_the_layouts_lazy_none():
    assert _collection_node(False).get("lazy") == "none"


@pytest.mark.parametrize("lazy", [True, None], ids=["lazy true", "lazy absent"])
def test_a_lazy_collection_writes_no_lazy_key(lazy):
    assert "lazy" not in _collection_node(lazy)


# --------------------------------------------------------------------------
# 3. The family: every declared field is read, or named here with its reason.
# --------------------------------------------------------------------------

# A pattern over the field's path (arrays and nested `children` collapsed),
# and why `jui g project` does not read it. Each pattern must still match a
# field it does not read — a stale line is red too.
NOT_READ = [
    (r"(^|\.)notes$|^dataFlow\.diagram$|^metadata\.(author|createdAt|updatedAt)$",
     "documentation: jsonui-doc renders it"),
    (r"^stateManagement\.states(\.|$)", "documentation: jsonui-doc renders the state table"),
    (r"^dataFlow\.apiEndpoints\.", "documentation / jui verify; generation reads the methods"),
    (r"^transitions\.", "documentation; navigation code is the navigation agents' job"),
    (r"^structure\.customComponents\.", "documentation / validation (the converters are scaffolded by g converter)"),
    (r"\.methods\.(endpoint|canonicalDivergence)(\.|$)",
     "read by the canon (resolve_canonical_marks, with the spec's path) and by jsonui-doc / jsonui-test"),
    (r"^metadata\.platforms$", "REPORTED: read by jsonui-test only; g project writes every platform's files"),
    (r"^structure\.embeds(\.|$)", "REPORTED: read by jui build's isolated-embed gate; g project writes no Embed node"),
    (r"^structure\.layout\.root$", "REPORTED: the root component ID is not written to the generated root View"),
    (r"^structure\.collection\.cell\.(children|overlay)(\.|$)",
     "REPORTED: the layoutNode form of a cell — only its root is read"),
    (r"^structure\.collection\.cell\.(dataKeys|viewName)$",
     "REPORTED: dataKeys is legacy (the schema prefers uiVariables); viewName is not used"),
    (r"^structure\.collection\.cell\.layout$", "read as layoutFile's deprecated fallback (after an `or`)"),
    (r"^structure\.collection\.(header|footer)\.",
     "REPORTED: a header / footer given as a cellNode or a component tree — only its root's id is used"),
]
# The spelling the pack teaches for a uiVariable's initial value: not in the
# schema, read all the same.
MUST_READ_UNDECLARED = [
    "stateManagement.uiVariables.defaultValue",
    "structure.collection.cell.uiVariables.defaultValue",
]


def _load_schema():
    spec = importlib.util.spec_from_file_location("screen_spec_schema_for_audit", SCHEMA_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SCREEN_SPEC_SCHEMA


class _Tracked(dict):
    def __init__(self, data, path, seen):
        super().__init__(data)
        self._path, self._seen = path, seen

    def _mark(self, key):
        self._seen.add(f"{self._path}.{key}" if self._path else str(key))

    def get(self, key, default=None):
        self._mark(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self._mark(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self._mark(key)
        return super().__contains__(key)


def _track(value, path, seen):
    if isinstance(value, dict):
        return _Tracked({k: _track(v, f"{path}.{k}" if path else k, seen) for k, v in value.items()}, path, seen)
    if isinstance(value, list):
        return [_track(v, path, seen) for v in value]
    return value


def _audit() -> tuple[set[str], set[str]]:
    schema = _load_schema()
    defs = schema["$defs"]

    def resolve(node):
        while "$ref" in node:
            node = defs[node["$ref"].split("/")[-1]]
        return node

    def objects(node):
        node = resolve(node)
        alts = node.get("oneOf") or node.get("anyOf")
        cands = [resolve(a) for a in alts] if alts else [node]
        return [c for c in cands if c.get("type") == "object" or "properties" in c]

    def sample(node, path, declared, variant, depth=0):
        node = resolve(node)
        objs = objects(node)
        if objs:
            obj = objs[0] if variant == 0 else objs[-1]
            out = {}
            for key, sub in (obj.get("properties") or {}).items():
                p = f"{path}.{key}" if path else key
                declared.add(p)
                if depth > 4 and key == "children":
                    continue
                out[key] = sample(sub, p, declared, variant, depth + 1)
            return out
        t = node.get("type")
        if isinstance(t, list):
            t = next((x for x in t if x != "null"), "string")
        if t == "array" or "items" in node:
            return [sample(node.get("items", {"type": "string"}), path, declared, variant, depth + 1)]
        if "enum" in node:
            return node["enum"][0]
        if "const" in node:
            return node["const"]
        if t == "boolean":
            return True
        if t in ("integer", "number"):
            return 1
        return {"name": "probeName", "type": "String", "id": "probe_id", "root": "probe_root",
                "layoutFile": "probe/probe_file"}.get(path.split(".")[-1], "x")

    sections = ["metadata", "structure", "dataFlow", "stateManagement", "transitions"]
    declared: set[str] = set()
    seen: set[str] = set()
    # A oneOf's first and last object alternative; with and without a TabView
    # (the Layout generator takes another path for one).
    for variant in (0, 1):
        for with_tab in (True, False):
            spec = {"type": "screen_spec", "version": "1.0"}
            for section in sections:
                spec[section] = sample(schema["properties"][section], section, declared, variant)
            if not with_tab:
                spec["structure"].pop("tabView", None)
            for holder in (spec["stateManagement"], spec["structure"]["collection"].get("cell", {})):
                for var in holder.get("uiVariables", []):
                    var["defaultValue"] = "gone"
            tracked = _track(spec, "", seen)
            s = extract_screen_spec(tracked)
            lg = LayoutGenerator(TypeMapper())
            lg.generate(s)
            cg = CellLayoutGenerator(lg)
            raw = tracked["structure"].get("collection")
            for coll in s.collections[:1]:
                if cg.should_generate(coll):
                    cg.generate(coll, s)
                    cell = raw.get("cell") if isinstance(raw, dict) else None
                    cg.resolve_output_path(coll, Path("/tmp/Layouts"), cell if isinstance(cell, dict) else None)

    def norm(p):
        return re.sub(r"(\.children)+", ".children", p)

    declared = {norm(p) for p in declared if p not in sections}
    seen = {norm(p) for p in seen}
    return declared - seen, seen


@pytest.mark.skipif(not SCHEMA_FILE.is_file(), reason="document_tools (the spec schema) is not beside jui_tools")
def test_every_declared_spec_field_is_read_by_g_project_or_named_with_its_reason():
    unread, seen = _audit()
    unnamed = sorted(p for p in unread if not any(re.search(pat, p) for pat, _ in NOT_READ))
    stale = [why for pat, why in NOT_READ if not any(re.search(pat, p) for p in unread)]
    missing = [p for p in MUST_READ_UNDECLARED if p not in seen]
    assert not unnamed, f"declared, read by nothing, and not named here: {unnamed}"
    assert not stale, f"named here but now read (drop the line): {stale}"
    assert not missing, f"the taught spelling is not read: {missing}"
    # The measurement is alive: it saw the reads it is about.
    assert {"stateManagement.uiVariables.name", "structure.collection.lazy",
            "structure.collection.cell.uiVariables.defaultValue"} <= seen
