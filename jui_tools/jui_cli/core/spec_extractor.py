"""Extract structured data from screen spec JSON."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import shared_core


class CanonicalMarkError(ValueError):
    """A `@canonical` mark that could not be expanded.

    Raised rather than absorbed. The alternative is a repository stub whose
    method takes no arguments, generated silently, which compiles on all three
    platforms and is wrong on all three.
    """


@dataclass
class MethodParam:
    name: str
    type: str
    description: str = ""
    # Swift external label. ``None`` → use ``name`` as both labels
    # (the default in Swift). ``"_"`` → suppress the external label entirely
    # (matches ``func foo(_ name: T)``). Any other string → ``label name: T``.
    # Ignored on Kotlin / TS where there are no external labels.
    label: str | None = None


@dataclass
class MethodDef:
    name: str
    params: list[MethodParam] = field(default_factory=list)
    return_type: str = ""
    is_async: bool = True
    description: str = ""
    # Empty list means "all platforms" (default). When populated, the method
    # is only emitted for the listed targets (e.g. ["ios", "android"]).
    platforms: list[str] = field(default_factory=list)


@dataclass
class RepositoryDef:
    name: str
    methods: list[MethodDef] = field(default_factory=list)
    description: str = ""


@dataclass
class UseCaseDef:
    name: str
    methods: list[MethodDef] = field(default_factory=list)
    repositories: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class EventHandlerDef:
    """View-local event handler — intentionally minimal.

    Under the new architecture ViewModel public API lives in
    ``dataFlow.viewModel`` (``ViewModelDef``). ``stateManagement.eventHandlers``
    is reserved for handlers that stay inside the View layer and never reach
    the ViewModel Protocol (rare — pure visual state toggles etc.).
    """
    name: str
    description: str = ""


@dataclass
class VarDef:
    """A public ``var`` declaration on the ViewModel.

    Emission per platform:

    - iOS Protocol: ``var <name>: <type> { get set }`` (``{ get }`` when read_only)
    - iOS Impl:     ``@Published var <name>: <type> = <default>`` (or plain ``var`` when !observable)
    - Kotlin Proto: ``var <name>: <type>`` (``val`` when read_only)
    - Kotlin Impl:  ``override var <name>: <type> = <default>``
    """
    name: str
    type: str
    description: str = ""
    optional: bool = False
    observable: bool = True
    read_only: bool = False
    platforms: list[str] | None = None


@dataclass
class ViewModelDef:
    methods: list[MethodDef] = field(default_factory=list)
    vars: list[VarDef] = field(default_factory=list)
    description: str = ""


@dataclass
class UIVariableDef:
    name: str
    type: str
    default: Any = None
    description: str = ""


@dataclass
class DisplayLogicRule:
    condition: str
    effects: list[dict] = field(default_factory=list)


@dataclass
class ComponentDef:
    """Structured representation of a single structure.components[] entry.

    Extends the raw dict with optional typed ``style`` / ``children`` /
    ``binding`` fields so the generator can render nested Layout JSON
    trees directly from the spec. Fields are optional for backward
    compatibility with specs that only use flat component lists.
    """

    id: str
    type: str
    description: str = ""
    style: dict[str, Any] = field(default_factory=dict)
    binding: dict[str, str] = field(default_factory=dict)
    children: list["ComponentDef"] = field(default_factory=list)
    initial_state: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class DecorativeElementDef:
    """A decorative grouping (hero sections, security-badge rows, etc.)
    that should be inserted into the layout tree at generation time.
    """

    id: str
    purpose: str = ""
    parent_id: str = ""
    components: list[ComponentDef] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class WrapperViewDef:
    """A wrapper View used purely to realise a visual style
    (background, cornerRadius, centering, overlay, etc.).
    """

    id: str
    wraps: str
    purpose: str = ""
    style: dict[str, Any] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass
class CollectionSlotDef:
    """A Collection's `cell`, `header` or `footer` entry, in either schema form.

    - root: a ComponentDef (the cellNode form's full tree) or a component id
      (both forms; the layoutNode form's tree is then `children` under it).
    - children / overlay: the layoutNode form — component ids from
      structure.components (or placeholders) arranged under a string root.
    - layout_file: `layoutFile`, else the deprecated `layout`.
    - generate: `generateCellLayout` — `jui g project` writes the slot's
      Layout JSON only when it is true.
    """
    kind: str
    root: ComponentDef | str | None = None
    children: list = field(default_factory=list)
    overlay: bool = False
    layout_file: str = ""
    generate: bool = False
    ui_variables: list[UIVariableDef] = field(default_factory=list)
    event_handlers: list[EventHandlerDef] = field(default_factory=list)

    @property
    def root_id(self) -> str:
        if isinstance(self.root, ComponentDef):
            return self.root.id
        return self.root or ""


@dataclass
class EmbedDef:
    """A structure.embeds[] entry: another screen hosted as a region."""
    region_id: str
    screen: str
    params: dict | None = None
    events: dict | None = None
    navigation_mode: str | None = None


@dataclass
class CollectionDef:
    id: str
    cell_id_property: str = ""
    auto_change_tracking_id: bool = False
    sections: list[dict] = field(default_factory=list)
    columns: int = 1
    layout: str = "vertical"
    line_spacing: int | None = None
    column_spacing: int | None = None
    paging: bool = False
    cell_root: ComponentDef | None = None
    generate_cell_layout: bool = False
    # structure.collection.lazy: None = not declared (the Layout default,
    # "lazy"); False = a plain stack with no scroll container ("none").
    lazy: bool | None = None
    cell_ui_variables: list[UIVariableDef] = field(default_factory=list)
    cell_event_handlers: list[EventHandlerDef] = field(default_factory=list)
    # cell / header / footer as declared ("cell" first); the four `cell_*`
    # fields above are the cell slot's, kept for their existing readers.
    slots: dict[str, CollectionSlotDef] = field(default_factory=dict)
    # structure.collection.cellClasses: the Layout refs of the cells the
    # Collection may use (the multi-cell form), written onto the Collection.
    cell_classes: list[str] = field(default_factory=list)
    # structure.collection.insets: the Layout Collection's insets, as given.
    insets: Any = None


@dataclass
class TabViewDef:
    id: str
    tabs: list[dict] = field(default_factory=list)


@dataclass
class ScreenSpec:
    name: str
    display_name: str
    description: str
    layout_file: str = ""
    repositories: list[RepositoryDef] = field(default_factory=list)
    use_cases: list[UseCaseDef] = field(default_factory=list)
    view_model: ViewModelDef = field(default_factory=ViewModelDef)
    ui_variables: list[UIVariableDef] = field(default_factory=list)
    event_handlers: list[EventHandlerDef] = field(default_factory=list)
    api_endpoints: list[dict] = field(default_factory=list)
    transitions: list[dict] = field(default_factory=list)
    layout_components: list[dict] = field(default_factory=list)
    components: list[ComponentDef] = field(default_factory=list)
    layout_tree: dict = field(default_factory=dict)
    collection: CollectionDef | None = None
    # All declared collections (structure.collection + structure.collections[]).
    # `collection` stays as the first entry for single-Collection consumers.
    collections: list[CollectionDef] = field(default_factory=list)
    tab_view: TabViewDef | None = None
    display_logic: list[DisplayLogicRule] = field(default_factory=list)
    custom_components: list[dict] = field(default_factory=list)
    decorative_elements: list[DecorativeElementDef] = field(default_factory=list)
    wrapper_views: list[WrapperViewDef] = field(default_factory=list)
    embeds: list[EmbedDef] = field(default_factory=list)



def _ui_variable_default(var: dict, where: str) -> Any:
    """A uiVariable's initial value: `default`, else `defaultValue`, else None.

    Both spellings are read: `defaultValue` is the one the agents pack's
    examples use and the key the Layout JSON `data` section writes; `default`
    is the older one. When both are given, `default` wins — the precedence the
    pack states for this field (and the one the cell path already had for a
    truthy `default`) — and, when their values differ, the other is named: a
    spec says one thing. Neither is in the spec schema (it declares name /
    type / description / notes). Read by key, so false / 0 / "" are values.

    Until 1.9.0 the screen path (stateManagement.uiVariables) read `default`
    only: `"defaultValue": "gone"` reached the Layout JSON as the type's
    default "" and nothing said so (`jui verify` compares data names only).
    The cell path read `default or defaultValue`, which let a falsy `default`
    fall through to `defaultValue`. Ticket
    generate-commands-overwrite-edited-files-and-ignore-their-flags (round 4).
    """
    if "default" in var:
        value = var["default"]
        if "defaultValue" in var and var["defaultValue"] != value:
            print(f"WARNING: {where} '{var.get('name', '?')}': both default "
                  f"({json.dumps(value)}) and defaultValue ({json.dumps(var['defaultValue'])}) "
                  f"are given; default is used")
        return value
    return var.get("defaultValue")


SLOT_KINDS = ("cell", "header", "footer")


def _parse_slot(entry: dict, kind: str) -> CollectionSlotDef:
    """One cell / header / footer entry (see CollectionSlotDef)."""
    where = f"structure.collection.{kind}.uiVariables"
    root_val = entry.get("root")
    if isinstance(root_val, dict):
        root: ComponentDef | str | None = _parse_component(root_val)
    else:
        root = root_val if isinstance(root_val, str) else None
    children = entry.get("children")
    layout_ref = entry.get("layoutFile") or entry.get("layout")
    return CollectionSlotDef(
        kind=kind,
        root=root,
        children=children if isinstance(children, list) else [],
        overlay=bool(entry.get("overlay")),
        layout_file=layout_ref.removesuffix(".json") if isinstance(layout_ref, str) else "",
        generate=bool(entry.get("generateCellLayout")),
        ui_variables=[
            UIVariableDef(
                name=var["name"],
                type=var["type"],
                default=_ui_variable_default(var, where),
                description=var.get("description", ""),
            )
            for var in entry.get("uiVariables", []) or []
        ],
        event_handlers=[
            EventHandlerDef(name=h["name"], description=h.get("description", ""))
            for h in entry.get("eventHandlers", []) or []
        ],
    )


def slot_layout_ref(collection_id: str, slot: CollectionSlotDef) -> str:
    """The layout a Collection section names for this slot — the same file
    `jui g project` writes for it: `layoutFile` (or the deprecated `layout`);
    else, when the slot opts into generation, `<collection id>_<kind>`; else
    the root id, as before.

    Until jsonui-cli 1.9.0 a section named the root id whatever the slot declared, so
    the pack's own example (root "item_cell_root", layoutFile
    "item_list/item_cell") produced a section naming "item_cell_root": sjui
    resolves that to ItemCellRootView and Dynamic mode loads
    item_cell_root.json — neither is the cell. `jui build` reads the same
    names to tell cell layouts from screens (_spec_cell_layout_stems).
    """
    if slot.layout_file:
        return slot.layout_file
    if slot.generate:
        return f"{collection_id}_{slot.kind}"
    return slot.root_id


def _parse_collection(coll_data: dict) -> CollectionDef:
    """Parse one structure.collection / structure.collections[] entry."""
    coll_id = coll_data.get("id", "collection")
    slots = {
        kind: _parse_slot(coll_data[kind], kind)
        for kind in SLOT_KINDS
        if isinstance(coll_data.get(kind), dict) and coll_data.get(kind)
    }
    sections: list[dict] = []
    declared_sections = coll_data.get("sections")
    if isinstance(declared_sections, list) and declared_sections:
        # The section-based form, as the spec writes it: each section's cell
        # / header / footer layout (and columns). Until jsonui-cli 1.9.0 it
        # was read by the validator and jsonui-doc only, and the Collection
        # g project wrote named the cell entry's root instead.
        for entry in declared_sections:
            if not isinstance(entry, dict):
                continue
            section = {k: entry[k] for k in ("cell", "header", "footer")
                       if isinstance(entry.get(k), str) and entry[k]}
            if isinstance(entry.get("columns"), (int, float)) and not isinstance(entry.get("columns"), bool):
                section["columns"] = entry["columns"]
            sections.append(section)
    elif slots:
        section: dict[str, str] = {"cell": slot_layout_ref(coll_id, slots["cell"]) if "cell" in slots else ""}
        for kind in ("header", "footer"):
            if kind in slots:
                section[kind] = slot_layout_ref(coll_id, slots[kind])
        sections.append(section)
    cell_classes = coll_data.get("cellClasses")

    cell = slots.get("cell")
    cell_root_def = cell.root if cell and isinstance(cell.root, ComponentDef) else None
    return CollectionDef(
        id=coll_id,
        cell_id_property=coll_data.get("cellIdProperty", ""),
        auto_change_tracking_id=bool(coll_data.get("autoChangeTrackingId", False)),
        sections=sections,
        cell_root=cell_root_def,
        generate_cell_layout=bool(cell and cell.generate),
        cell_ui_variables=cell.ui_variables if cell else [],
        cell_event_handlers=cell.event_handlers if cell else [],
        # Declared by the spec schema, dropped until 1.9.0 (the generated
        # Collection was lazy whatever the spec said).
        lazy=coll_data.get("lazy") if isinstance(coll_data.get("lazy"), bool) else None,
        slots=slots,
        cell_classes=[c for c in cell_classes if isinstance(c, str) and c]
        if isinstance(cell_classes, list) else [],
        insets=coll_data.get("insets") if isinstance(coll_data.get("insets"), (list, str)) else None,
    )


def _parse_embeds(raw: Any) -> list[EmbedDef]:
    """structure.embeds[]: entries without a regionId and a screen are left to
    the validator, which names them."""
    out = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        rid, screen = e.get("regionId"), e.get("screen")
        if not (isinstance(rid, str) and rid and isinstance(screen, str) and screen):
            continue
        out.append(EmbedDef(
            region_id=rid,
            screen=screen,
            params=e.get("params") if isinstance(e.get("params"), dict) else None,
            events=e.get("events") if isinstance(e.get("events"), dict) else None,
            navigation_mode=e.get("navigationMode") if isinstance(e.get("navigationMode"), str) else None,
        ))
    return out


def extract_screen_spec(spec_data: dict, spec_path=None) -> ScreenSpec:
    """Convert spec JSON to ScreenSpec dataclass.

    `spec_path` locates the project's API canon so `params: "@canonical"` can
    be expanded before anything reads it. Resolution happens here, at the one
    door every caller comes through, rather than in each command — the same
    reason `jsonui-doc` resolves at its own single entry point, and both of
    them call the same `shared/core` implementation.

    Omitting `spec_path` leaves a mark unexpanded, and `_parse_params` then
    refuses it loudly. Generating a method with no arguments because context
    was not threaded is exactly the silent shrinking this codebase keeps
    removing.
    """
    if spec_path is not None:
        resolve_canonical_marks(spec_data, spec_path)
        # `{"md": ...}` prose (shared/core/spec_texts.py): a description that
        # reaches a generated doc comment is the text, not a dict repr. An
        # unresolvable reference is left as written; `jsonui-doc validate`
        # is what names it.
        texts = shared_core.load("spec_texts")
        if texts is not None:
            spec_data = texts.resolve_spec_texts(spec_data, Path(spec_path)).data
    metadata = spec_data.get("metadata", {})
    structure = spec_data.get("structure", {})
    data_flow = spec_data.get("dataFlow", {})
    state_mgmt = spec_data.get("stateManagement", {})

    # Repositories
    repositories = []
    for repo in data_flow.get("repositories", []):
        repositories.append(RepositoryDef(
            name=repo["name"],
            methods=_parse_methods(repo.get("methods", [])),
            description=repo.get("description", ""),
        ))

    # UseCases
    use_cases = []
    for uc in data_flow.get("useCases", []):
        use_cases.append(UseCaseDef(
            name=uc["name"],
            methods=_parse_methods(uc.get("methods", [])),
            repositories=uc.get("repositories", []),
            description=uc.get("description", ""),
        ))

    # UI Variables
    ui_variables = []
    for var in state_mgmt.get("uiVariables", []):
        ui_variables.append(UIVariableDef(
            name=var["name"],
            type=var["type"],
            default=_ui_variable_default(var, "stateManagement.uiVariables"),
            description=var.get("description", ""),
        ))

    # Event Handlers (View-local only; ViewModel public API lives in
    # dataFlow.viewModel).
    event_handlers = []
    for handler in state_mgmt.get("eventHandlers", []):
        event_handlers.append(EventHandlerDef(
            name=handler["name"],
            description=handler.get("description", ""),
        ))

    # ViewModel definition (methods + vars)
    vm_data = data_flow.get("viewModel") or {}
    # ViewModel methods default to synchronous (UI event handlers). This
    # differs from Repository/UseCase methods (network calls, isAsync=True).
    vm_methods = _parse_methods(vm_data.get("methods", []), default_async=False)
    vm_vars = []
    for raw in vm_data.get("vars", []) or []:
        if not isinstance(raw, dict):
            continue
        if "platforms" in raw:
            raw_pf = raw.get("platforms")
            pf_list: list[str] | None = (
                [str(p) for p in raw_pf] if isinstance(raw_pf, list) else None
            )
        else:
            pf_list = None
        vm_vars.append(VarDef(
            name=raw["name"],
            type=raw["type"],
            description=raw.get("description", ""),
            optional=bool(raw.get("optional", False)),
            observable=bool(raw.get("observable", True)),
            read_only=bool(raw.get("readOnly", False)),
            platforms=pf_list,
        ))
    view_model = ViewModelDef(
        methods=vm_methods,
        vars=vm_vars,
        description=vm_data.get("description", ""),
    )

    # Display Logic
    display_logic = []
    for rule in state_mgmt.get("displayLogic", []):
        display_logic.append(DisplayLogicRule(
            condition=rule.get("condition", ""),
            effects=rule.get("effects", []),
        ))

    # Collection(s). `structure.collections` (array) is the multi-Collection
    # form — every entry gets the same parsing as the single slot.
    collections: list[CollectionDef] = []
    for coll_data in [structure.get("collection"), *(structure.get("collections") or [])]:
        if isinstance(coll_data, dict) and coll_data:
            collections.append(_parse_collection(coll_data))
    collection = collections[0] if collections else None

    # TabView
    tab_view = None
    tv_data = structure.get("tabView")
    if tv_data:
        tab_view = TabViewDef(
            id=tv_data.get("id", "tab_view"),
            tabs=tv_data.get("tabs", []),
        )

    raw_components = structure.get("components", [])
    components = [_parse_component(c) for c in raw_components if isinstance(c, dict)]

    decorative_elements = [
        _parse_decorative_element(d)
        for d in structure.get("decorativeElements", []) or []
        if isinstance(d, dict)
    ]
    wrapper_views = [
        _parse_wrapper_view(w)
        for w in structure.get("wrapperViews", []) or []
        if isinstance(w, dict)
    ]

    return ScreenSpec(
        name=metadata.get("name", ""),
        display_name=metadata.get("displayName", ""),
        description=metadata.get("description", ""),
        layout_file=metadata.get("layoutFile", ""),
        repositories=repositories,
        use_cases=use_cases,
        view_model=view_model,
        ui_variables=ui_variables,
        event_handlers=event_handlers,
        api_endpoints=data_flow.get("apiEndpoints", []),
        transitions=spec_data.get("transitions", []),
        layout_components=raw_components,
        components=components,
        layout_tree=structure.get("layout", {}),
        collection=collection,
        collections=collections,
        tab_view=tab_view,
        display_logic=display_logic,
        custom_components=structure.get("customComponents", []),
        decorative_elements=decorative_elements,
        wrapper_views=wrapper_views,
        embeds=_parse_embeds(structure.get("embeds")),
    )


def _parse_component(raw: dict) -> ComponentDef:
    """Parse a raw component dict into a ComponentDef (recursive)."""
    children_raw = raw.get("children") or []
    children = [
        _parse_component(c) for c in children_raw if isinstance(c, dict)
    ]
    return ComponentDef(
        id=raw.get("id", ""),
        type=raw.get("type", "View"),
        description=raw.get("description", ""),
        style=dict(raw.get("style") or {}),
        binding=dict(raw.get("binding") or {}),
        children=children,
        initial_state=raw.get("initialState", ""),
        raw=raw,
    )


def _parse_decorative_element(raw: dict) -> DecorativeElementDef:
    comps = [
        _parse_component(c)
        for c in raw.get("components", []) or []
        if isinstance(c, dict)
    ]
    return DecorativeElementDef(
        id=raw.get("id", ""),
        purpose=raw.get("purpose", ""),
        parent_id=raw.get("parentId", ""),
        components=comps,
        raw=raw,
    )


def _parse_wrapper_view(raw: dict) -> WrapperViewDef:
    return WrapperViewDef(
        id=raw.get("id", ""),
        wraps=raw.get("wraps", ""),
        purpose=raw.get("purpose", ""),
        style=dict(raw.get("style") or {}),
        raw=raw,
    )


def _parse_methods(methods_data: list, *, default_async: bool = True) -> list[MethodDef]:
    """Parse methods list (supports both string and object formats)."""
    result = []
    for m in methods_data:
        if isinstance(m, str):
            result.append(MethodDef(name=m, is_async=default_async))
        elif isinstance(m, dict):
            params = _parse_params(m.get("params"))
            raw_platforms = m.get("platforms") or []
            if not isinstance(raw_platforms, list):
                raw_platforms = []
            result.append(MethodDef(
                name=m["name"],
                params=params,
                return_type=m.get("returnType", ""),
                is_async=m.get("isAsync", default_async),
                description=m.get("description", ""),
                platforms=[str(p) for p in raw_platforms],
            ))
    return result


def resolve_canonical_marks(spec_data: dict, spec_path) -> None:
    """Expand `@canonical` marks against the project's API canon.

    Finds the canon by walking up from the spec for an `api_directory` holding
    OpenAPI documents — the same shape `jsonui-doc` uses, and the same shared
    implementation reads them, so a mark cannot expand to one list here and a
    different list there.
    """
    canon = shared_core.openapi_canonical()
    if canon is None:
        return
    # Misplaced marks count too: a spec whose only mark sits under
    # `viewModel` would otherwise return here and never be told.
    if not (list(canon.iter_marked_methods(spec_data))
            or list(canon.iter_misplaced_marks(spec_data))
            or list(canon.iter_divergence_declarations(spec_data))):
        return

    # One context, so the documents and the naming convention come from the
    # same config. The working directory is offered first because it is what
    # `jui` itself resolves its config from — in a split tree (specs in one
    # tree, app and config in another) walking up from the spec never reaches
    # the config that declares the convention.
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        cwd = None
    context = canon.build_spec_canon_context(spec_path, extra_roots=(cwd,))
    for message in context.unknown_config_keys:
        print(f"WARNING: {message}")
    if context.unresolved_extends:
        raise CanonicalMarkError("; ".join(context.unresolved_extends))
    index, convention = context.index, context.convention

    # Before resolution — see the note in jsonui-doc's validator.
    errors = canon.check_divergences(spec_data, index, convention)

    # Also before resolution, and for the same reason: `resolve_spec_marks`
    # rewrites `params` in place, so a method that carried a mark stops
    # looking like one and this walk finds nothing. It shipped below the
    # resolve call in 1.8.17 and printed nothing on every real project while
    # the function it calls returned 13 on the same specs.
    widened = canon.iter_widened_enums(spec_data, index, convention)

    mark_errors, warnings = canon.resolve_spec_marks(spec_data, index, convention)
    errors.extend(mark_errors)
    for path, message in warnings:
        # Printed, not raised: the expansion is correct, the declaration is
        # merely surprising. `jsonui-doc` carries the same text as a warning.
        print(f"WARNING: {path}: {message}")
    if errors:
        raise CanonicalMarkError("; ".join(f"{p}: {m}" for p, m in errors))

    # Inventory, not a warning — see `iter_widened_enums`. Printed without the
    # WARNING prefix on purpose: a project that gates its build at zero
    # warnings cannot act on this one (typing the argument means giving up
    # `@canonical`), so putting it on that channel would only raise the
    # accepted baseline and hide the next real warning behind it.
    #
    # Two counts because they differ: one route declared by ten methods is
    # ten expansions and one gap. Both are printed so a project comparing
    # numbers with another knows which it is holding.
    if widened:
        routes = {(w[1], w[3]) for w in widened}
        shown = ", ".join(sorted(f"{n} → {e}" for n, e in routes))
        print(f"NOTE: {spec_path}: {len(routes)} argument(s) in "
              f"{len(widened)} '@canonical' expansion(s) are enums in the "
              f"canon and expand as String; the generated DTO types them "
              f"({shown}). Signatures are unchanged.")


def _parse_params(params_data) -> list[MethodParam]:
    """Parse params (supports both string and structured array)."""
    if params_data is None:
        return []
    if params_data == "@canonical" or (
            isinstance(params_data, list) and "@canonical" in params_data):
        # Reached only when the caller did not give `extract_screen_spec` a
        # path to find the canon with. Silence here would generate a method
        # with no arguments.
        raise CanonicalMarkError(
            "'@canonical' was not expanded: extract_screen_spec() needs the "
            "spec's path to locate the project's OpenAPI documents")
    if isinstance(params_data, str):
        # Legacy free-text: "email: String, password: String"
        result = []
        for part in params_data.split(","):
            part = part.strip()
            if ":" in part:
                name, type_ = part.split(":", 1)
                result.append(MethodParam(name=name.strip(), type=type_.strip()))
            elif part:
                result.append(MethodParam(name=part, type="Any"))
        return result
    if isinstance(params_data, list):
        return [
            MethodParam(
                name=p["name"],
                type=p["type"],
                description=p.get("description", ""),
                label=p.get("label"),
            )
            for p in params_data
            if isinstance(p, dict) and "name" in p and "type" in p
        ]
    return []
