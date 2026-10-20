"""spec → the whiteboard sheet. Design: 09 §6.

The page's sheet renderer (prototype ``renderSheet``) reads one ``doc``
object; this builds it from a real spec so the renderer ports unchanged:

  metadata        {name, displayName, description, platforms, layoutFile}
  components      [[type, id, description, depth]]   (the Layout file's tree when the spec lists no
                                               components — the usual case — depth-first, depth 0 at its
                                               top; listed components in structure.layout's order: _listed_tree.
                                               The page rebuilds the tree from the order and the depths: a
                                               row's parent is the nearest row above it one level up)
  layoutChildren  [id]                        (the wireframe's order when there are no depths: the demo)
  uiVariables     [[name, type, initial]]
  eventHandlers   [[name, description]]
  vmMethods       [name]      vmVars [name]   repositories [name]
  apis            [[operation, method, path]]
  userActions     [[action, processing, destination]]
  transitions     [[trigger or condition, destination, type or method]]
  branches        [[method, when, then]]      ("note" entries: [method, "note", text]; when / then: the spec's
                                               object or array as it is, for the page's formatted block, or
                                               text — _json_or_text)
  related         [[type, path, exists]]
  impl            {total, done}
  flowMermaid     the data flow diagram document_tools' spec page draws ("" when there is none; 2.3.5)

Strings are passed through as data; the page escapes them when it renders.
"""
from __future__ import annotations

import json
from pathlib import Path

MAX_ITEMS = 300
MAX_TEXT = 300
#: A branch's when / then larger than this (as JSON) goes as text, cut like any other (ticket 2026-10-20-jui-viz-spec-branch-json-formatted).
MAX_JSON = 20_000
#: Mermaid's own default maxTextSize: a longer diagram is not drawn (the page shows the boxes instead).
MERMAID_MAX = 50_000
_DOC_HTML: list = []


def _doc_html():
    """document_tools' spec page generator (spec_doc/html_generator.py), found by jui's own routes; None if none."""
    if not _DOC_HTML:
        from ..core.document_tools_import import load_document_tools_module
        _DOC_HTML.append(load_document_tools_module("spec_doc.html_generator")[0])
    return _DOC_HTML[0]


def dataflow_mermaid(spec: dict) -> str:
    """The data flow diagram of a spec, by document_tools' rule (html_generator: ``dataFlow.diagram``, else
    ``_build_dataflow_mermaid(metadata, dataFlow)``) — one copy of the builder, so the whiteboard and the generated
    spec page draw the same graph. "" when the spec has no data flow, the builder is not found or fails on the spec,
    or the text is longer than MERMAID_MAX."""
    df = spec.get("dataFlow")
    if not isinstance(df, dict) or not df:
        return ""
    gen = _doc_html()
    if gen is None:
        return ""
    try:
        text = df.get("diagram") or gen._build_dataflow_mermaid(_d(spec.get("metadata")), df)
    except Exception:  # a spec the builder cannot read: the page keeps the boxes
        return ""
    return text if isinstance(text, str) and len(text) <= MERMAID_MAX else ""


def _t(value) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def _json_or_text(value):
    """A branch's when / then: an object or an array as the spec wrote it (the page formats it, every string in it
    put in as text), anything else — or one over MAX_JSON as JSON — the one line it always was."""
    if isinstance(value, (dict, list)):
        try:
            if len(json.dumps(value, ensure_ascii=False)) <= MAX_JSON:
                return value
        except (TypeError, ValueError):
            pass
    return _t(value)


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


def _listed_tree(listed: list[dict], layout: dict) -> list[list]:
    """structure.components as [type, id, description, depth], in the order of structure.layout's tree.

    The tree is structure.layout: ``root`` (an id) and ``children`` (ids, or {id, children} for a nested one). A
    listed component's depth is how many listed components are above it on that tree, so the list stays a
    depth-first order whose depth never grows by more than one from a row to the next (the page rebuilds the tree
    from it). Listed components the tree does not name follow at depth 0, in the spec's order. The rows are the
    listed components, each once — the same count section_items gives.
    """
    by_id: dict[str, dict] = {}
    for c in listed:
        if isinstance(c.get("id"), str) and c["id"] not in by_id:
            by_id[c["id"]] = c
    order: list[tuple[dict, int]] = []
    seen: set[int] = set()

    def visit(node, above: int) -> None:
        if isinstance(node, str):
            ident, kids = node, []
        elif isinstance(node, dict):
            ident, kids = node.get("id"), node.get("children")
        else:
            return
        comp = by_id.get(ident) if isinstance(ident, str) else None
        if comp is not None and id(comp) not in seen:
            seen.add(id(comp))
            order.append((comp, above))
            above += 1
        for kid in kids if isinstance(kids, list) else []:
            visit(kid, above)

    root = layout.get("root")
    top = layout.get("children")
    if isinstance(root, str) and root:
        visit({"id": root, "children": top}, 0)
    elif isinstance(top, list):
        for kid in top:
            visit(kid, 0)
    order += [(c, 0) for c in listed if id(c) not in seen]
    return [[_t(c.get("type")), _t(c.get("id")), _t(c.get("description")), depth] for c, depth in order]


def build_doc(spec: dict, layout_nodes: list[dict], related_exists: list[bool], impl: dict) -> dict:
    meta = _d(spec.get("metadata"))
    st = _d(spec.get("structure"))
    sm = _d(spec.get("stateManagement"))
    df = _d(spec.get("dataFlow"))
    vm = _d(df.get("viewModel"))

    listed = [c for c in _list(st.get("components")) if isinstance(c, dict)]
    if listed:
        components = _listed_tree(listed, _d(st.get("layout")))
    else:
        components = [[_t(n["type"]), _t(n.get("id", "")), _t(n["type"]), int(n.get("depth", 0))]
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
                branches.append([_t(method), _json_or_text(entry.get("when")), _json_or_text(entry.get("then"))])

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
        # the third: where it goes (userAction.destination; "" when the spec says none), its own column on the sheet
        "userActions": [[_t(a.get("action")), _t(a.get("processing")), _t(a.get("destination"))]
                        for a in _list(spec.get("userActions")) if isinstance(a, dict)],
        # the third: how it moves (type / method: push, sheet, dismiss …), for the page's colours (2.3.5)
        "transitions": [[_t(t.get("trigger") or t.get("condition")), _t(t.get("destination")), _t(t.get("type") or t.get("method") or "")]
                        for t in _list(spec.get("transitions")) if isinstance(t, dict)],
        "branches": branches,
        "related": related,
        "impl": dict(impl),
        "flowMermaid": dataflow_mermaid(spec),
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
