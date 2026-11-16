"""The Data fields a layout DECLARES, per platform, as the generators collect them.

validate checks a test's `initialState` against the Data of the screen under
test: a key has to be one of its declared fields, and the value has to fit the
field's class (plan test-runner-initialstate-and-related, decisions 1 and 2).
Those fields are whatever the generator for the platform puts in the Data type
from the layout's `data` sections, so this reads the layout the way they do:

- styles merged into each node (`style` → `<styles>/<name>.json`, deep-merged
  under the node; the node's own keys win, arrays are replaced, the style's
  `type` is dropped when the node has one) — sjui / kjui / rjui StyleLoader;
- includes expanded inline (`include` → `<layouts>/<name>.json`): the include
  node's own `data` / `shared_data` are appended to the partial's, its other
  keys override the partial's, and every data name is prefixed by the
  include's id in camelCase (`header` + `title_text` → `headerTitleText`) —
  IncludeExpander;
- then the declared items: `data` arrays, each item's `platform` checked
  against the platform's tokens (DataItemPlatform), the first declaration of a
  name kept. Every generator reads a `data` array on any node (a data[] a
  style merged in included). They part ways in one place, measured by
  shared/core/layout_data_fields_vectors.json: ios and android (the shared
  DataModelUpdaterCore) honour an item's `mode` (ios: swiftui, android:
  compose); web (rjui) does not read `mode`. (Until the initialState train
  rjui also skipped a data[] on a node with other keys and one from a style —
  ticket rjui-data-declared-in-a-node-with-other-keys-or-a-style-is-not-collected.)

Not declared, so not listed on any platform: `data` written as an object (the
style shorthand), and the fields a generator adds by itself (`<id>IsFocused`,
a Radio group's selection, TabView members).

Each generator's spec runs the generator's own steps on the vector's files;
tests/test_layout_data_fields_vectors.py runs this module on the same files.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

PLATFORMS = ("ios", "android", "web")

#: DataItemPlatform.TOKENS (shared/core/data_item_platform.rb).
PLATFORM_TOKENS = {
    "ios": ("ios", "swift", "swiftui", "uikit"),
    "android": ("android", "kotlin", "java", "compose", "xml"),
    "web": ("web", "typescript", "javascript", "react"),
}

#: The mode each generator builds (sjui `data_mode_filter`, kjui's default
#: `mode`); web does not filter on mode.
PLATFORM_MODE = {"ios": "swiftui", "android": "compose", "web": None}

_INCLUDE_ROOT = "_jui_include_root"


def declared_data_fields(layout_path: Path, platform: str, *,
                         layouts_dir: Path, styles_dir: Path | None) -> list[tuple[str, object]]:
    """[(name, class as written)] the platform's generator declares for this layout."""
    if platform not in PLATFORMS:
        raise ValueError(f"unknown platform {platform!r}; one of {', '.join(PLATFORMS)}")
    tree = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    tree = _merge_styles(tree, styles_dir)
    tree = _expand_includes(tree, Path(layouts_dir), styles_dir, None)
    fields: list[tuple[str, object]] = []
    seen: set[str] = set()
    if platform == "web":
        _collect_web(tree, True, fields, seen)
    else:
        _collect_core(tree, platform, fields, seen)
    return fields


# -- item filters --------------------------------------------------------

def _applies(item: dict, platform: str) -> bool:
    value = item.get("platform")
    if not isinstance(value, str):
        return True
    named = [t.strip().lower() for t in value.split(",") if t.strip()]
    return not named or any(t in PLATFORM_TOKENS[platform] for t in named)


def _take(items, platform: str, with_mode: bool, fields, seen) -> None:
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        if not _applies(item, platform):
            continue
        if with_mode and "mode" in item and item["mode"] != PLATFORM_MODE[platform]:
            continue
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        fields.append((item["name"], item.get("class")))


# -- ios / android: DataModelUpdaterCore.extract_data_properties ---------

def _collect_core(node, platform, fields, seen) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("data"), list):
            _take(node["data"], platform, True, fields, seen)
        child = node.get("child")
        for c in (child if isinstance(child, list) else [child] if child is not None else []):
            _collect_core(c, platform, fields, seen)
    elif isinstance(node, list):
        for item in node:
            _collect_core(item, platform, fields, seen)


# -- web: rjui DataModelGenerator.extract_data_properties ----------------

def _declares_data(node: dict, is_root: bool) -> bool:
    # Any node's data[], as sjui / kjui read it (rjui IncludeExpander.declares_data?).
    return isinstance(node.get("data"), list)


def _collect_web(node, is_root, fields, seen) -> None:
    if isinstance(node, dict):
        if _declares_data(node, is_root):
            _take(node["data"], "web", False, fields, seen)
        child = node.get("child") if node.get("child") is not None else node.get("children")
        for c in (child if isinstance(child, list) else [child] if child is not None else []):
            _collect_web(c, False, fields, seen)
    elif isinstance(node, list):
        for item in node:
            _collect_web(item, False, fields, seen)


# -- styles: StyleLoader.load_and_merge ----------------------------------

def _deep_merge(base: dict, over: dict) -> dict:
    result = dict(base)
    for key, value in over.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _merge_styles(node, styles_dir: Path | None):
    if not isinstance(node, dict):
        return node
    if "style" in node:
        style = None
        if styles_dir is not None:
            path = Path(styles_dir) / f"{node['style']}.json"
            if path.is_file():
                try:
                    style = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    style = None
        own = {k: v for k, v in node.items() if k != "style"}
        if isinstance(style, dict):
            base = dict(style)
            if "type" in own:
                base.pop("type", None)
            node = _deep_merge(base, own)
        else:
            node = own
    for key in ("child", "children"):
        if key in node:
            value = node[key]
            node[key] = ([_merge_styles(c, styles_dir) for c in value] if isinstance(value, list)
                         else _merge_styles(value, styles_dir))
    return node


# -- includes: IncludeExpander.process_includes ---------------------------

def _camel(name: str) -> str:
    if "_" not in name:
        return name
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _prefixed(prefix: str | None, name: str) -> str:
    if not prefix:
        return name
    camel = _camel(name)
    return prefix + (camel[:1].upper() + camel[1:])


def _prefix_data_names(node, prefix) -> None:
    if not isinstance(node, dict):
        return
    if isinstance(node.get("data"), list):
        node["data"] = [dict(item, name=_prefixed(prefix, item["name"]))
                        if isinstance(item, dict) and item.get("name") else item
                        for item in node["data"]]
    child = node.get("child") if node.get("child") is not None else node.get("children")
    for c in (child if isinstance(child, list) else [child] if isinstance(child, dict) else []):
        _prefix_data_names(c, prefix)


def _expand_includes(node, layouts_dir: Path, styles_dir, prefix):
    if not isinstance(node, dict):
        return node
    if "include" in node:
        path = layouts_dir / f"{node['include']}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Include file not found: {path}")
        included = _merge_styles(json.loads(path.read_text(encoding="utf-8")), styles_dir)
        include_id = node.get("id")
        new_prefix = (_prefixed(prefix, include_id) if prefix and include_id
                      else _camel(include_id) if include_id else prefix)
        for key, value in node.items():
            if key in ("include", "id"):
                continue
            if key in ("data", "shared_data"):
                if isinstance(value, list):
                    included[key] = list(included.get(key) or []) + value
                else:
                    included.setdefault(key, [])
            else:
                included[key] = copy.deepcopy(value)
        if new_prefix:
            _prefix_data_names(included, new_prefix)
        included[_INCLUDE_ROOT] = True
        return _expand_includes(included, layouts_dir, styles_dir, new_prefix)
    for key in ("child", "children"):
        if key in node:
            value = node[key]
            expanded = ([_expand_includes(c, layouts_dir, styles_dir, prefix) for c in value]
                        if isinstance(value, list) else _expand_includes(value, layouts_dir, styles_dir, prefix))
            if key == "children":
                node.pop("children")
                node["child"] = expanded
            else:
                node["child"] = expanded
    return node
