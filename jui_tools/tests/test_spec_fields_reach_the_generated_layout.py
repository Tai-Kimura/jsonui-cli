"""What `jui g project` does with the fields a screen spec gives it.

1. A uiVariable's initial value, on the screen path (stateManagement) and the
   cell path (structure.collection.cell): `defaultValue` — the spelling the
   agents pack's examples use — and `default`, the older one, both reach the
   Layout JSON `data` section; `default` wins when both are given, the
   precedence the pack states (and the other is named when it differs);
   false / 0 / "" are values. Until 1.8.121 the screen path read
   `default` only, so `"defaultValue": "gone"` became the type's "" without a
   word (`jui verify` compares data names only), and the cell path's
   `default or defaultValue` let a falsy `default` fall through.
2. `structure.collection.lazy: false` — declared by the spec schema ("a plain
   VStack/Column/div ... NO scroll container") — reaches the Collection node as
   the Layout's `"lazy": "none"`; until 1.8.121 it was dropped.
3. Every field the spec schema declares for the sections extract_screen_spec
   reads is either read by `jui g project` or named below with the reason it
   is not, and who reads it instead — measured by running a spec synthesized
   from the schema, with every dict recording the keys asked of it, through
   the extractor and the Layout JSON generators (every Collection entry opted
   into generation). A field added to the schema and read by nothing, or a
   reader removed, turns this red; so does a field this table calls
   documentation that the schema does not (4).
4. Round 5: the layout facts the audit found dropped are written — Embed
   nodes, the layout root, the cell / header / footer trees — and the fields
   the tools read without the schema declaring them are declared (both are
   armed in test_g_project_writes_the_layout_facts_a_spec_declares.py and
   document_tools' test_schema_declares_what_the_tools_read.py).

Ticket generate-commands-overwrite-edited-files-and-ignore-their-flags,
rounds 4 and 5 (from the pack lane's audit).
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
    # default wins, a falsy one too (the cell path's `or` gave 7 here)
    ("zeroDefaultSevenDefaultValue", "Int", {"default": 0, "defaultValue": 7}, 0),
    ("emptyDefaultValue", "String", {"defaultValue": ""}, ""),
    ("both", "String", {"default": "a", "defaultValue": "b"}, "a"),
    ("falseDefaultTrueDefaultValue", "Bool", {"default": False, "defaultValue": True}, False),
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
        assert (f"WARNING: {where} 'both': both default (\"a\") and defaultValue (\"b\") are given; "
                f"default is used") in said, said


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
# and why `jui g project` does not read it — who does, measured 2026-09-26 by
# running the Python tools' spec commands on a spec synthesized the same way,
# with every key asked recorded per command. Each pattern must still match a
# field it does not read — a stale line is red too. A reason that starts with
# "documentation" must be what the schema says of the field: its description
# carries "Documentation only".
DOC_ONLY = "Documentation only"
NOT_READ = [
    (r"(^|\.)notes$", "documentation: jsonui-doc renders most (not a displayLogic rule's, a cell's "
                        "uiVariables' / eventHandlers', or a decorative component's)"),
    (r"^dataFlow\.diagram$|^metadata\.author$|^dataFlow\.apiEndpoints\.(request|response)$"
     r"|^stateManagement\.states\.values\.description$|^structure\.customComponents\.description$"
     r"|^transitions\.condition$", "documentation: jsonui-doc renders it"),
    (r"^metadata\.(createdAt|updatedAt)$", "documentation: jsonui-doc renders it; the validator checks the date"),
    (r"^structure\.collections?\.(description|sections\.(description|index))$",
     "documentation: the faces write them to describe a Collection and its sections (declared so in jsonui-cli "
     "1.9.0; before, undeclared)"),
    (r"^metadata\.group$", "read by jsonui-doc generate mermaid (the flow diagram's groups)"),
    (r"^metadata\.platforms$", "read by jsonui-test (branch-tests, contracts coverage); g project writes "
                               "every platform's files"),
    (r"^stateManagement\.states(\.name|\.values(\.value|\.visibleElements)?)?$",
     "read by jsonui-doc (the state table) and jsonui-test contracts coverage (visibleElements)"),
    (r"^dataFlow\.apiEndpoints\.(method|path)$", "read by jsonui-test (contracts coverage, branch-tests) "
                                                 "and jsonui-doc"),
    (r"^dataFlow\.(repositories|useCases)\.methods\.(endpoint|canonicalDivergence)(\.|$)",
     "read by the canon (resolve_canonical_marks — `jui g project` passes the spec's path, this audit "
     "does not) and by jsonui-doc / jsonui-test"),
    (r"^dataFlow\.viewModel\.methods\.(endpoint|canonicalDivergence)(\.|$)",
     "read on repositories / useCases methods only; on a ViewModel method no tool reads it (the schema "
     "says so)"),
    (r"^structure\.customComponents\.(name|specFile)$",
     "read by jsonui-doc, the validator and jsonui-test unit-stubs; the converters are scaffolded by "
     "g converter"),
    (r"^transitions\.destination$", "read by jsonui-doc (and its flow diagram)"),
    (r"^structure\.collections?\.(cell|header|footer)\.dataKeys$",
     "legacy binding list (the schema prefers uiVariables): read by jsonui-doc only"),
    (r"^structure\.collections?\.(cell|header|footer)\.viewName$",
     "the view class: read by jsonui-doc; a section names the layout, and each platform derives the "
     "class from it"),
]
# A uiVariable's initial value, in both spellings, on both paths.
MUST_READ = [
    "stateManagement.uiVariables.defaultValue",
    "stateManagement.uiVariables.default",
    "structure.collection.cell.uiVariables.defaultValue",
    "structure.collection.cell.uiVariables.default",
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


def _audit() -> tuple[set[str], set[str], dict[str, dict]]:
    """(declared fields not read, keys read, each declared field's schema)."""
    schema = _load_schema()
    defs = schema["$defs"]
    nodes: dict[str, dict] = {}

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
                nodes.setdefault(p, sub)
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
        leaf = path.split(".")[-1]
        if leaf == "id":
            # One id per place: the generator looks components up by id, and
            # one shared id let the last registered (a decorative element's)
            # stand for every component — structure.components never reached
            # the node builder.
            return "probe_" + re.sub(r"[^a-z0-9]+", "_", path.lower())
        return {"name": "probeName", "type": "String", "root": "probe_root",
                "layoutFile": "probe/probe_file"}.get(leaf, "x")

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
            # The trees name a structure.components entry, so the node builder
            # renders a declared component, not only placeholders.
            component_id = spec["structure"]["components"][0]["id"]
            spec["structure"]["layout"]["children"].append(component_id)
            colls = [spec["structure"]["collection"], *spec["structure"].get("collections", [])]
            for coll in colls:
                for kind in ("cell", "header", "footer"):
                    entry = coll.get(kind)
                    if not isinstance(entry, dict):
                        continue
                    if isinstance(entry.get("children"), list):
                        entry["children"].append(component_id)
                    # Every cell / header / footer opts in, as an entry must
                    # for `jui g project` to write its Layout JSON (one that
                    # does not is a layout authored elsewhere, and its tree is
                    # read by jsonui-doc only).
                    entry["generateCellLayout"] = True
            for holder in (spec["stateManagement"], colls[0].get("cell", {})):
                for var in holder.get("uiVariables", []):
                    var["defaultValue"] = "gone"
            tracked = _track(spec, "", seen)
            s = extract_screen_spec(tracked)
            lg = LayoutGenerator(TypeMapper())
            lg.generate(s)
            cg = CellLayoutGenerator(lg)
            for c in s.collections:
                for slot in cg.slots_to_generate(c):
                    cg.generate_slot(slot, s)
                    cg.slot_output_path(c, slot, Path("/tmp/Layouts"))

    def norm(p):
        return re.sub(r"(\.children)+", ".children", p)

    declared = {norm(p) for p in declared if p not in sections}
    seen = {norm(p) for p in seen}
    return declared - seen, seen, {norm(p): n for p, n in nodes.items()}


@pytest.mark.skipif(not SCHEMA_FILE.is_file(), reason="document_tools (the spec schema) is not beside jui_tools")
def test_every_declared_spec_field_is_read_by_g_project_or_named_with_its_reason():
    unread, seen, nodes = _audit()
    unnamed = sorted(p for p in unread if not any(re.search(pat, p) for pat, _ in NOT_READ))
    stale = [why for pat, why in NOT_READ if not any(re.search(pat, p) for p in unread)]
    missing = [p for p in MUST_READ if p not in seen or p not in nodes]
    assert not unnamed, f"declared, read by nothing, and not named here: {unnamed}"
    assert not stale, f"named here but now read (drop the line): {stale}"
    assert not missing, f"an initial value's spelling is not declared and read: {missing}"
    # The measurement is alive: it saw the reads it is about.
    assert {"stateManagement.uiVariables.name", "structure.collection.lazy",
            "structure.collection.cell.uiVariables.defaultValue", "structure.embeds.regionId",
            "structure.layout.root", "structure.collection.header.children.zIndex",
            "structure.components.platform"} <= seen


@pytest.mark.skipif(not SCHEMA_FILE.is_file(), reason="document_tools (the spec schema) is not beside jui_tools")
def test_a_field_named_documentation_here_is_documentation_only_in_the_schema():
    """The reason given here and the schema's word for the field are one
    statement: a field this table calls documentation says so where authors
    read it, and a field the schema calls documentation is not read here."""
    unread, seen, nodes = _audit()
    doc_patterns = [pat for pat, why in NOT_READ if why.startswith("documentation")]
    here = {p for p in unread if any(re.search(pat, p) for pat in doc_patterns)}

    def says_doc(p):
        node = nodes[p]
        while "$ref" in node:
            node = _load_schema()["$defs"][node["$ref"].split("/")[-1]]
        return DOC_ONLY in (node.get("description") or "")
    assert here, "the documentation reasons match nothing"
    unsaid = sorted(p for p in here if not says_doc(p))
    assert not unsaid, f"called documentation here, not in the schema: {unsaid}"
    read_anyway = sorted(p for p in seen if p in nodes and says_doc(p))
    assert not read_anyway, f"the schema says documentation only, g project reads it: {read_anyway}"
