"""Element ids a test's steps name, against the layouts of the project.

Design U8 (5): the ids a test names are resolved by the same expander. The
screen a test names is checked (`screen_ids`); the element ids its steps name
were not, so an id no layout has — a typo, a renamed node, web's old
spelling of an id inside an include — ran against nothing until a device
timed out on it. Each id a step names (`id`, `ids`, `container`, `cropId`,
and `visible` / `notVisible` under `when` and `while`, in nested `steps` too)
is classified by `jui_cli.core.layout_facts.classify_element` — the answer
the spec validator and the coverage data axis give — against the ids of
EVERY layout of the project, each resolved on every platform with its
includes expanded:

- on a layout: nothing
- declared in `test.appOwnedIds` (the app draws it outside every layout — a
  native navigation bar's menu item, an app toast; an entry ending in `*` is
  a prefix): nothing. A declaration no step names is one INFO per run, so
  dead ones do not pile up. A declaration is not looked up in the layouts:
  the app draws it
- none of these: INFO below LAYOUT_ID_GATE_FROM, WARNING from it, never an
  error. That is the spec validator's literal, read where it is (no copy).
  The message names the layout ids a person may have meant — never counted
  as a match: the runtime id is the layout's. Web's old spelling of an id
  inside an include is one of these from INCLUDE_ID_PREFIX_GATE_FROM on
- CANNOT CHECK, counted apart, one INFO per file and kind:
    web's spelling of an id inside an include before
    INCLUDE_ID_PREFIX_GATE_FROM (naming what web spells it as from that
    release), and UIKit's;
    an id the generated code derives from a layout id — a Collection's
    cells `<id>_item_<n>`, a Segment's or TabView's tabs `<id>_tab_<n>`
    (rjui collection_converter / segment_converter) — whose layout id is
    on a layout;
    a part of a component the project defines itself (`<id>_…` under a node
    whose type is none of the built-in ones): its own converter names them;
    web's CSS descendant form `A #B` (the web driver hands the id to
    `locator('#' + id)`), each part checked as above;
    an id no layout id could be (a character outside `[A-Za-z0-9_]`: the
    OS's own UI, or an id a component builds from data);
    an id built from a case argument (`@{…}`), known only when the case runs

Why every layout and not the one the step runs on: a screen test does not
say which screen each step is on, and it moves between screens — measured on
one face, 56 of the ids "not on the step's layout" were on the next screen's.
The runner looks an id up wherever it is. A partial included only under an
include id is left out of the union: its own ids exist at runtime only
prefixed, inside the layouts that include it, and web's old spelling of them
is exactly what the release changes.

The project is the config THE RUN READ, pushed in by `cmd_validate` as
`set_path_roots` is — not the nearest config above the test file: in a split
tree (tests beside the apps, each app's config in its own directory) the walk
up reaches a config that declares no layouts, and every id went unchecked on
the first face measured. With no config with a layout tree, or no jui_cli,
nothing is checked and the run says so once.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .models import ValidationMessage, ValidationResult

#: Keys of a step whose value is one element id.
ID_KEYS = ("id", "container", "cropId")
#: Keys of a step whose value is a condition, and the condition's id keys.
CONDITION_KEYS = ("when", "while")
CONDITION_ID_KEYS = ("visible", "notVisible")

#: What a layout id can be spelled with.
LAYOUT_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Ids the generated code derives from a layout id: (pattern, the node types
#: whose id it is derived from). rjui collection_converter.rb
#: `cell_item_id_attr` and segment_converter.rb `segment_item_id_attr`.
DERIVED = (
    (re.compile(r"^(?P<base>.+)_item_\d+$"), ("Collection",)),
    (re.compile(r"^(?P<base>.+)_tab_\d+$"), ("Segment", "TabView")),
)
CSS_DESCENDANT = re.compile(r"\s+#")

NOTICE = ("from jsonui-cli {version}, test element ids on no layout of the project become "
          "WARNING (declare the ones the app draws itself in test.appOwnedIds)")


def layout_id_gate_from():
    """(LAYOUT_ID_GATE_FROM, None), or (None, why it cannot be read).

    The spec validator's literal (document_tools), imported from the
    document_tools beside this test_tools: the tree jsonui-test runs from
    (~/.jsonui-cli, or a checkout) holds both."""
    sibling = Path(__file__).resolve().parents[3] / "document_tools"
    if (sibling / "jsonui_doc_cli" / "spec_doc" / "validator.py").is_file():
        # As `_prefer_sibling_jui_cli`: a jsonui_doc_cli installed elsewhere
        # would answer with another release's literal.
        if str(sibling) not in sys.path:
            sys.path.insert(0, str(sibling))
        cached = sys.modules.get("jsonui_doc_cli")
        if cached is not None and not str(getattr(cached, "__file__", "") or "").startswith(
                str(sibling)):
            for name in [n for n in sys.modules
                         if n == "jsonui_doc_cli" or n.startswith("jsonui_doc_cli.")]:
                del sys.modules[name]
    try:
        from jsonui_doc_cli.spec_doc import validator
    except ImportError as exc:
        return None, f"the spec validator (document_tools) is not importable: {exc}"
    return validator.LAYOUT_ID_GATE_FROM, None


def _gates():
    from ..shared_core import load
    return load("gate_versions")


def gating(version: str) -> bool:
    """Is an id on no layout a WARNING in *version*?"""
    gates = _gates()
    literal, _ = layout_id_gate_from()
    return bool(gates) and literal is not None and gates.gate_is_on(version, literal)


def gate_notice(version: str) -> str | None:
    """The line announcing the release that makes them WARNING, while one is
    announced; None when it gates already, or nothing is announced."""
    gates = _gates()
    literal, _ = layout_id_gate_from()
    if gates and literal is not None and gates.gate_state(literal) == "release" \
            and not gates.gate_is_on(version, literal):
        return NOTICE.format(version=literal)
    return None


def level_unknown(version: str) -> str | None:
    """Why the level cannot be decided (then everything stays INFO), or None."""
    if _gates() is None:
        return "shared/core/gate_versions.py is not in this tool tree"
    literal, why = layout_id_gate_from()
    return why if literal is None and why else None


# ---------------------------------------------------------------- the ids named


def _step_ids(step, path: str, out: list) -> None:
    if not isinstance(step, dict):
        return
    for key in ID_KEYS:
        if isinstance(step.get(key), str) and step[key]:
            out.append((f"{path}.{key}", step[key]))
    if isinstance(step.get("ids"), list):
        for i, value in enumerate(step["ids"]):
            if isinstance(value, str) and value:
                out.append((f"{path}.ids[{i}]", value))
    for key in CONDITION_KEYS:
        condition = step.get(key)
        if isinstance(condition, dict):
            for ckey in CONDITION_ID_KEYS:
                if isinstance(condition.get(ckey), str) and condition[ckey]:
                    out.append((f"{path}.{key}.{ckey}", condition[ckey]))
    if isinstance(step.get("steps"), list):
        for i, inner in enumerate(step["steps"]):
            _step_ids(inner, f"{path}.steps[{i}]", out)


def test_element_ids(data: dict, path: str) -> list:
    """(path, id) of every element id a screen or flow test's steps name, in
    the order they run."""
    out: list = []
    for section in ("setup", "steps", "cases", "teardown"):
        for i, item in enumerate(data.get(section) or []):
            if section != "cases":
                _step_ids(item, f"{path}.{section}[{i}]", out)
            elif isinstance(item, dict):
                for j, step in enumerate(item.get("steps") or []):
                    _step_ids(step, f"{path}.cases[{i}].steps[{j}]", out)
    return out


# ---------------------------------------------------------------- the project


class ProjectIds:
    """The ids of every layout of a project, each on every platform with its
    includes expanded — less the partials included only under an include id
    — and the ids the app declares it draws itself."""

    def __init__(self, layouts_dir: Path, styles_dir: Path, app_owned=()):
        from jui_cli.core import layout_facts as lf
        from jui_cli.core.screen_identity import NON_LAYOUT_SUBTREES

        self.layouts_dir = layouts_dir
        self.styles_dir = styles_dir
        names = []
        for path in sorted(layouts_dir.rglob("*.json")):
            rel = path.relative_to(layouts_dir)
            if NON_LAYOUT_SUBTREES.intersection(rel.parts[:-1]):
                continue
            names.append(str(rel.with_suffix("")))
        prefixed, plain = set(), set()
        for name in names:
            found: list = []
            lf._includes_and_ids(lf._load(layouts_dir / f"{name}.json"), found)
            for ref, include_id in found:
                (prefixed if include_id else plain).add(ref)
        self.only_prefixed = prefixed - plain
        self.ids, self.cell_ids, self.include_ids = set(), set(), set()
        self.include_web: dict = {}
        self.types: dict = {}
        self.unresolved: dict = {}
        for name in names:
            if name in self.only_prefixed:
                continue
            here = lf.layout_ids_every_platform(name, layouts_dir=layouts_dir,
                                                styles_dir=styles_dir)
            self.ids |= here.ids
            self.cell_ids |= here.cell_ids
            self.include_ids |= here.include_ids
            for old, now in here.include_web.items():
                self.include_web.setdefault(old, set()).update(now)
            self.types.update(here.types)
            if here.unresolved:
                self.unresolved[name] = here.unresolved
        known = self.ids | self.cell_ids
        self.include_ids -= known
        self.include_web = {k: v for k, v in self.include_web.items() if k not in known}
        self.builtin = _builtin_types()
        self.app_owned = list(app_owned)
        #: Declarations a step named, filled as the run classifies.
        self.app_owned_named: set = set()

    def app_owned_entry(self, element: str) -> str | None:
        """The `test.appOwnedIds` entry that covers *element*, or None."""
        for entry in self.app_owned:
            if entry == element or (entry.endswith("*") and element.startswith(entry[:-1])):
                return entry
        return None


def _builtin_types() -> set | None:
    """The component types the toolchain defines (attribute_definitions.json),
    or None when it is not in this tool tree (then no part is told apart)."""
    from ..shared_core import shared_core_dir
    core = shared_core_dir()
    try:
        data = json.loads((core / "attribute_definitions.json").read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    return {k for k, v in data.items() if isinstance(v, dict) and k != "common"}


#: The project of this run (`set_run_project`).
_RUN: dict = {}


def _styles_dir(config: dict, root: Path, layouts_dir: Path) -> Path:
    value = config.get("styles_directory")
    path = root / (value if isinstance(value, str) and value else "docs/screens/styles")
    return path if path.is_dir() else layouts_dir


def set_run_project(config: dict | None = None, config_path: Path | None = None) -> None:
    """Take the project from the config the run read (None clears). Its
    layouts are resolved on first use, once per run."""
    _RUN.clear()
    if not config or config_path is None:
        return
    config_path = Path(config_path).resolve()
    from .screen_ids import _layouts_dir_from_config
    layouts_dir = _layouts_dir_from_config(config, config_path)
    if layouts_dir is None:
        _RUN["why"] = f"{config_path.name} declares no layouts directory that exists"
        return
    _RUN["args"] = (layouts_dir, _styles_dir(config, config_path.parent, layouts_dir),
                    config)


def run_project():
    """(ProjectIds, None), or (None, why there is none)."""
    if "project" in _RUN:
        return _RUN["project"], None
    if "args" not in _RUN:
        return None, _RUN.get("why", "validate was not given a project config")
    from .screen_ids import _prefer_sibling_jui_cli
    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core.project_config import declared_app_owned_ids
        layouts_dir, styles_dir, config = _RUN["args"]
        _RUN["project"] = ProjectIds(layouts_dir, styles_dir, declared_app_owned_ids(config))
    except ImportError as exc:
        _RUN.pop("args")
        _RUN["why"] = f"jui_cli is not importable ({exc})"
        return None, _RUN["why"]
    return _RUN["project"], None


def unnamed_app_owned() -> list:
    """The `test.appOwnedIds` entries no step of this run named."""
    project = _RUN.get("project")
    if project is None:
        return []
    return [e for e in project.app_owned if e not in project.app_owned_named]


# ---------------------------------------------------------------- classifying


def _classify(element: str, project: ProjectIds, include_exact: bool):
    """(kind, candidates, note): `on_layout`, `app_owned`, `missing`, or a
    CANNOT CHECK kind — `include_spelling`, `derived`, `part`, `css`,
    `not_an_id`."""
    from jui_cli.core.layout_facts import classify_element

    if CSS_DESCENDANT.search(element):
        parts = [p.strip() for p in CSS_DESCENDANT.split(element) if p.strip()]
        for part in parts:
            kind, candidates, _ = _classify(part, project, include_exact)
            if kind == "missing":
                return "missing", candidates, f"its part '{part}'"
        return "css", [], None
    entry = project.app_owned_entry(element)
    if entry is not None:
        project.app_owned_named.add(entry)
        return "app_owned", [], None
    kind, candidates = classify_element(
        element, ids=project.ids, cell_ids=project.cell_ids,
        include_ids=project.include_ids, types=project.types,
        include_web=project.include_web, include_exact=include_exact)
    if kind == "in_cell":
        return "on_layout", [], None
    if kind != "missing" or element in project.include_web:
        return kind, candidates, None
    if not LAYOUT_ID.match(element):
        return "not_an_id", [], None
    known = project.ids | project.cell_ids
    for pattern, types in DERIVED:
        m = pattern.match(element)
        if m and m.group("base") in known and project.types.get(m.group("base")) in types:
            return "derived", [], None
    if project.builtin is not None:
        for base in sorted(known, key=len, reverse=True):
            type_of = project.types.get(base)
            if element.startswith(base + "_") and type_of and type_of not in project.builtin:
                return "part", [], None
    return "missing", candidates, None


#: Why each CANNOT CHECK kind cannot be checked (include spellings are worded
#: by `include_spelling_note`, which the spec validator prints too).
CANNOT = {
    "include_spelling": None,
    "derived": "derived by the generated code from a layout id it names (a Collection's "
               "cells `<id>_item_<n>`, a Segment's or TabView's tabs `<id>_tab_<n>`)",
    "part": "parts of a component this project defines — its own converter names them",
    "css": "web's CSS descendant form `A #B` (the web driver passes the id to a CSS "
           "locator); each part is on a layout",
    "not_an_id": "no layout id is spelled so (a character outside [A-Za-z0-9_]: the OS's "
                 "own UI, or an id built from data)",
    "argument": "built from case arguments — known only when the case runs",
}


def check_element_ids(data: dict, path: str, result: ValidationResult,
                      version: str) -> None:
    """Classify every element id *data*'s steps name (the module docstring);
    messages go on *result*, counts on `result.element_ids`."""
    refs = test_element_ids(data, path)
    counts = result.element_ids
    if not refs:
        return
    counts["named"] += len(refs)
    project, why = run_project()
    if project is None:
        counts["not_checked"] += len(refs)
        result.element_ids_unchecked_why = why
        return
    from jui_cli.core.layout_facts import include_id_prefix_state, include_spelling_note

    warn = gating(version)
    include_state = include_id_prefix_state(version)
    cannot: dict = {}
    for ref_path, element in refs:
        if "@{" in element:
            cannot.setdefault("argument", []).append((element, []))
            continue
        kind, candidates, note = _classify(element, project, include_state == "on")
        if kind in ("on_layout", "app_owned"):
            counts[kind] += 1
            continue
        if kind != "missing":
            cannot.setdefault(kind, []).append((element, candidates))
            continue
        counts["missing"] += 1
        text = (f"Element '{element}'" + (f": {note}" if note else "")
                + " is on no layout of this project (includes expanded, every platform)")
        if candidates:
            text += (f"; the layouts have {', '.join(repr(c) for c in candidates)} — the "
                     "runtime id is the layout's spelling")
        else:
            # Only here (ee, pack review): beside a near spelling, the hint
            # would offer a way to declare a typo instead of fixing it.
            text += "; an id the app draws itself is declared in test.appOwnedIds"
        message = ValidationMessage(path=ref_path, message=text,
                                    level="warning" if warn else "info")
        (result.warnings if warn else result.infos).append(message)
    for kind in [k for k in CANNOT if k in cannot]:
        found = cannot[kind]
        counts["cannot_check"] += len(found)
        listed = ", ".join(sorted({e for e, _ in found}))
        why = (include_spelling_note(found, project.include_web, include_state)
               if kind == "include_spelling" else CANNOT[kind])
        where = "inside includes " if kind == "include_spelling" else ""
        result.infos.append(ValidationMessage(
            path=path, level="info",
            message=f"cannot check: {len(found)} element id(s) {where}({listed}) — {why}"))
