"""spec → the whiteboard sheet. Design: 09 §6.

The page's sheet renderer (prototype ``renderSheet``) reads one ``doc``
object; this builds it from a real spec so the renderer ports unchanged:

  metadata        {name, displayName, description, platforms, layoutFile}
  components      [[type, id, description]]   (the Layout file's tree when the
                                               spec lists no components — the usual case)
  layoutChildren  [id]                        (the wireframe's order)
  uiVariables     [[name, type, initial]]
  eventHandlers   [[name, description]]
  vmMethods       [name]      vmVars [name]   repositories [name]
  apis            [[operation, method, path]]
  userActions     [[action, processing]]
  transitions     [[trigger or condition, destination]]
  branches        [[method, when, then]]      ("note" entries: [method, "note", text])
  related         [[type, path, exists]]
  impl            {total, done}

Strings are passed through as data; the page escapes them when it renders.
"""
from __future__ import annotations

import json
from pathlib import Path

MAX_ITEMS = 300
MAX_TEXT = 300


def _t(value) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def _list(value) -> list:
    return value[:MAX_ITEMS] if isinstance(value, list) else []


def _d(value) -> dict:
    return value if isinstance(value, dict) else {}


def _name(item) -> str:
    if isinstance(item, str):
        return _t(item)
    if isinstance(item, dict):
        return _t(item.get("name") or item.get("signature") or item.get("description") or "")
    return _t(item)


def build_doc(spec: dict, layout_nodes: list[dict], related_exists: list[bool], impl: dict) -> dict:
    meta = _d(spec.get("metadata"))
    st = _d(spec.get("structure"))
    sm = _d(spec.get("stateManagement"))
    df = _d(spec.get("dataFlow"))
    vm = _d(df.get("viewModel"))

    listed = [c for c in _list(st.get("components")) if isinstance(c, dict)]
    if listed:
        components = [[_t(c.get("type")), _t(c.get("id")), _t(c.get("description"))] for c in listed]
    else:
        components = [[_t(n["type"]), _t(n.get("id", "")), "  " * n.get("depth", 0) + _t(n["type"])]
                      for n in layout_nodes[:MAX_ITEMS]]
    layout_children = [c[1] for c in components if c[1]]

    apis = []
    for api in _list(df.get("apiEndpoints")):
        if isinstance(api, dict):
            apis.append([_t(api.get("operationId") or api.get("notes") or ""), _t(api.get("method")), _t(api.get("path"))])

    branches = []
    methods = _d(_d(spec.get("branchContracts")).get("methods"))
    for method, contract in list(methods.items())[:MAX_ITEMS]:
        for entry in _list(_d(contract).get("branches")):
            if not isinstance(entry, dict):
                continue
            if "note" in entry:
                branches.append([_t(method), "note", _t(entry.get("note"))])
            else:
                branches.append([_t(method), _t(entry.get("when")), _t(entry.get("then"))])

    related = []
    for item, exists in zip(_list(spec.get("relatedFiles")), related_exists):
        if isinstance(item, dict):
            related.append([_t(item.get("type")), _t(item.get("path")), bool(exists)])

    return {
        "metadata": {
            "name": _t(meta.get("name")), "displayName": _t(meta.get("displayName")),
            "description": _t(meta.get("description")),
            "platforms": [_t(p) for p in _list(meta.get("platforms"))],
            "layoutFile": _t(meta.get("layoutFile")),
        },
        "components": components,
        "layoutChildren": layout_children,
        "uiVariables": [[_t(v.get("name")), _t(v.get("type")), _t(v.get("initial", v.get("initialValue")))]
                        for v in _list(sm.get("uiVariables")) if isinstance(v, dict)],
        "eventHandlers": [[_t(e.get("name")), _t(e.get("description"))]
                          for e in _list(sm.get("eventHandlers")) if isinstance(e, dict)],
        "vmMethods": [_name(m) for m in _list(vm.get("methods"))],
        "vmVars": [_name(v) for v in _list(vm.get("vars"))],
        "repositories": [_name(r) for r in _list(df.get("repositories"))],
        "apis": apis,
        "userActions": [[_t(a.get("action")), _t(a.get("processing"))]
                        for a in _list(spec.get("userActions")) if isinstance(a, dict)],
        "transitions": [[_t(t.get("trigger") or t.get("condition")), _t(t.get("destination"))]
                        for t in _list(spec.get("transitions")) if isinstance(t, dict)],
        "branches": branches,
        "related": related,
        "impl": dict(impl),
    }


def sheet_for(project, spec_id: str) -> dict | None:
    """The doc for one spec of a JsonUIProject, or None if it is unknown or unreadable."""
    entry = project.specs.get(spec_id)
    if entry is None or entry.data is None:
        return None
    data = entry.data
    nodes = project.layout_nodes_cached(project.layout_path(data, entry.source, entry.path))
    exists = [Path(p).exists() for p in project.related_paths(data, entry.source, entry.path)]
    return build_doc(data, nodes, exists, project.impl(data, entry.source, entry.path))
