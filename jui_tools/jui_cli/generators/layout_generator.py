"""Generate Layout JSON skeleton from screen spec."""
from __future__ import annotations

import copy
from typing import Any

from ..core.normalizer.include_expander import _to_camel_case as _snake_to_camel
from ..core.spec_extractor import EmbedDef, ScreenSpec, UIVariableDef
from ..core.type_mapper import TypeMapper


class LayoutGenerator:
    """Generates Layout JSON from ScreenSpec."""

    def __init__(self, type_mapper: TypeMapper):
        self._type_mapper = type_mapper

    def generate(self, spec: ScreenSpec) -> dict[str, Any]:
        """Generate the complete Layout JSON structure.

        The output is written to the shared ``layouts_directory`` (e.g.
        ``docs/screens/layouts/``) which is the single source of truth that
        developers may edit. The ``@generated`` marker is injected *only*
        at distribution time (``jui build`` → each platform's Layouts/ dir),
        since it's those per-platform copies that are truly clobbered on
        every build.
        """
        return self._generate_body(spec)

    def _generate_body(self, spec: ScreenSpec) -> dict[str, Any]:
        data_section = self._build_data_section(spec)
        children_tree = self._build_children_tree(spec)

        # TabView case: root is TabView
        if spec.tab_view:
            return self._build_tabview_layout(spec, data_section)

        # Normal case
        layout: dict[str, Any] = {"data": data_section}
        root_overlay = bool((spec.layout_tree or {}).get("overlay"))
        # structure.layout.root names the view that holds the layout's
        # children — a structure.components entry, as the spec validator asks
        # ("Root component ... not found in components list"). It is the
        # container the generator puts them in: that component's type, style
        # and bindings when it is declared, a View otherwise, with its id (the
        # root View itself carries the id when there are no children). Until
        # jsonui-cli 1.9.0 it was read by jsonui-doc and the validator only, and no
        # generated layout carried it. Left off when the tree already uses the
        # id — a layout's ids are unique.
        root_id = self._layout_root_id(spec, children_tree)

        if spec.collection:
            # Collection-based layout
            layout["type"] = "View"
            inner = self._root_container(spec, root_id, children_tree, root_overlay)
            layout["child"] = inner
        else:
            layout["type"] = "View"
            if children_tree:
                inner_view = self._root_container(spec, root_id, children_tree, root_overlay)
                if root_overlay:
                    # Overlay screens skip the ScrollView wrapper so
                    # children can stack full-screen
                    layout["child"] = inner_view
                else:
                    layout["child"] = {
                        "type": "ScrollView",
                        "child": inner_view,
                    }
            elif root_id:
                layout["id"] = root_id

        return layout

    def _root_container(self, spec: ScreenSpec, root_id: str | None,
                        children_tree: list, overlay: bool) -> dict[str, Any]:
        container: dict[str, Any] = {"type": "View"}
        if root_id:
            comp = self.component_map(spec).get(root_id)
            if comp:
                # Decoratives aimed at the root already reached the children
                # (the unreached-parent fallback in _walk_layout_tree).
                decorative, self._decorative_by_parent = self._decorative_by_parent, {}
                try:
                    container = self._component_to_node(comp, self._build_visibility_map(spec))
                finally:
                    self._decorative_by_parent = decorative
            container["id"] = root_id
        container["children"] = children_tree
        if not overlay:
            container.setdefault("orientation", "vertical")
        else:
            container.pop("orientation", None)
        return container

    def _layout_root_id(self, spec: ScreenSpec, children_tree: list) -> str | None:
        root = (spec.layout_tree or {}).get("root")
        if not isinstance(root, str) or not root:
            return None
        if root in self._collect_node_ids(children_tree):
            return None
        return root

    def _build_data_section(self, spec: ScreenSpec) -> list[dict[str, Any]]:
        """Build the data section from uiVariables, displayLogic, and collection.

        Under the new architecture ``stateManagement.eventHandlers`` is a
        View-local concept and must not populate Data. Callback properties
        that need to live on Data (so Layout JSON bindings like
        ``"onClick": "@{onLoginTap}"`` can resolve against ``data.onLoginTap``)
        must be declared explicitly in ``stateManagement.uiVariables`` with
        a callback type (``"(() -> Void)?"`` or the ``callback`` alias).
        """
        data: list[dict[str, Any]] = []

        # UI Variables
        for var in spec.ui_variables:
            resolved = self._type_mapper.resolve(var.type)
            entry: dict[str, Any] = {
                "name": var.name,
                "class": resolved["class"],
            }
            default = var.default if var.default is not None else resolved["defaultValue"]
            if default is not None:
                entry["defaultValue"] = default
            data.append(entry)

        # DisplayLogic → visibility properties (honours explicit variableName)
        existing_names = {entry["name"] for entry in data}
        visibility_names: set[str] = set()
        for rule in spec.display_logic:
            for effect in rule.effects:
                element_id = effect.get("element", "")
                vis_name = (
                    effect.get("variableName")
                    or _snake_to_camel(element_id) + "Visibility"
                )
                if vis_name in visibility_names or vis_name in existing_names:
                    continue
                visibility_names.add(vis_name)
                default_state = "visible" if effect.get("state") == "gone" else "gone"
                data.append({
                    "name": vis_name,
                    "class": "String",
                    "defaultValue": default_state,
                })

        # Collection → CollectionDataSource
        if spec.collection:
            items_name = _snake_to_camel(spec.collection.id) + "Items"
            data.append({
                "name": items_name,
                "class": "CollectionDataSource",
            })

        # TabView → selectedIndex
        if spec.tab_view:
            data.append({
                "name": "selectedTabIndex",
                "class": "Int",
                "defaultValue": 0,
            })

        return data

    def _build_children_tree(self, spec: ScreenSpec) -> list[dict[str, Any]]:
        """Build the children tree from layout and components.

        structure.embeds[] become Embed nodes: where the layout tree names a
        regionId, there; an embed the tree does not name is appended, so every
        declared region is in the layout (the pack's implement agent: "one
        per structure.embeds[].regionId"). A spec with no structure.layout
        still gets its embeds and its Collection — until jsonui-cli 1.9.0 it got
        neither, the Collection's items variable sitting in `data` with no
        Collection to read it.
        """
        children = []
        comp_map = self.component_map(spec)
        embeds = {"nodes": {e.region_id: self._embed_node(e) for e in spec.embeds}, "placed": set()}

        # Build visibility lookup (honours explicit variableName)
        vis_map = self._build_visibility_map(spec)

        layout = spec.layout_tree
        if layout:
            children.extend(self._walk_layout_tree(layout, comp_map, vis_map, embeds))

        for rid, node in embeds["nodes"].items():
            if rid not in embeds["placed"]:
                children.append(copy.deepcopy(node))

        # Add Collection if present
        if spec.collection:
            coll_node = self._build_collection_node(spec)
            children.append(coll_node)

        return children

    @staticmethod
    def _embed_node(e: EmbedDef) -> dict[str, Any]:
        node: dict[str, Any] = {"type": "Embed", "id": e.region_id, "screen": e.screen}
        if e.params is not None:
            node["params"] = copy.deepcopy(e.params)
        if e.events is not None:
            node["events"] = copy.deepcopy(e.events)
        if e.navigation_mode is not None:
            node["navigationMode"] = e.navigation_mode
        return node

    def component_map(self, spec: ScreenSpec) -> dict[str, dict]:
        """id -> component for structure.components (nested included) and
        the decorative elements' components; also stashes where each
        decorative group goes, for _component_to_node."""
        # Flatten components (including nested children) into a lookup map
        comp_map: dict[str, dict] = {}
        for c in spec.layout_components:
            self._register_component(c, comp_map)

        # Register decorative element components so layout references
        # that target them (by id) still resolve to proper nodes
        decorative_by_parent: dict[str, list[dict]] = {}
        decorative_root: list[dict] = []
        for elem in spec.decorative_elements or []:
            parent_id = (
                elem.parent_id if hasattr(elem, "parent_id") else elem.get("parentId", "")
            ) or ""
            elem_components = (
                elem.components if hasattr(elem, "components") else elem.get("components", [])
            )
            # Register each decorative component in comp_map so that
            # layout_tree string references can still resolve to them
            for sub in elem_components:
                raw = sub.raw if hasattr(sub, "raw") else sub
                self._register_component(raw, comp_map)
            # Collect the list under its parent (or root) for later injection
            decorative_group = {
                "id": elem.id if hasattr(elem, "id") else elem.get("id", ""),
                "purpose": elem.purpose if hasattr(elem, "purpose") else elem.get("purpose", ""),
                "components": [
                    (s.raw if hasattr(s, "raw") else s) for s in elem_components
                ],
            }
            if parent_id:
                decorative_by_parent.setdefault(parent_id, []).append(decorative_group)
            else:
                decorative_root.append(decorative_group)

        # Stash for use in _build_node
        self._decorative_by_parent = decorative_by_parent
        self._decorative_root = decorative_root
        return comp_map

    def _walk_layout_tree(self, layout: dict, comp_map: dict, vis_map: dict, embeds: dict) -> list:
        children = []
        decorative_by_parent = self._decorative_by_parent
        decorative_root = self._decorative_root
        for child in layout.get("children", []):
            node = self._build_node(child, comp_map, vis_map, embeds)
            if node:
                children.append(node)

        # Inject decorative elements whose parentId points at the root/layout
        # (no matching component inside the tree) so they still get emitted.
        for group in decorative_root:
            for sub in group["components"]:
                if not isinstance(sub, dict):
                    continue
                children.append(self._component_to_node(sub, vis_map))

        # Inject decorative elements that target components not reached via
        # the layout tree (fallback — append at the end rather than dropping)
        referenced_ids = self._collect_node_ids(children)
        for parent_id, groups in decorative_by_parent.items():
            if parent_id in referenced_ids:
                continue
            for group in groups:
                for sub in group["components"]:
                    if isinstance(sub, dict):
                        children.append(self._component_to_node(sub, vis_map))

        return children

    @staticmethod
    def _collect_node_ids(nodes: list) -> set[str]:
        """Flatten node IDs (including nested `child`/`children`) for lookup."""
        out: set[str] = set()

        def walk(n):
            if isinstance(n, dict):
                nid = n.get("id")
                if nid:
                    out.add(nid)
                for key in ("child", "children"):
                    if key in n:
                        v = n[key]
                        if isinstance(v, list):
                            for c in v:
                                walk(c)
                        elif isinstance(v, dict):
                            walk(v)
            elif isinstance(n, list):
                for c in n:
                    walk(c)

        walk(nodes)
        return out

    def _register_component(self, comp: Any, comp_map: dict) -> None:
        """Recursively register component ids (including nested children)."""
        if not isinstance(comp, dict):
            return
        cid = comp.get("id")
        if cid:
            comp_map[cid] = comp
        for child in comp.get("children") or []:
            self._register_component(child, comp_map)

    def _build_visibility_map(self, spec: ScreenSpec) -> dict[str, str]:
        """Map element ID → visibility variable name, prioritising variableName."""
        vis_map: dict[str, str] = {}
        for rule in spec.display_logic:
            for effect in rule.effects:
                element_id = effect.get("element", "")
                if not element_id:
                    continue
                vis_map[element_id] = (
                    effect.get("variableName")
                    or _snake_to_camel(element_id) + "Visibility"
                )
        return vis_map

    @staticmethod
    def _take_embed(node_id: str, embeds: dict | None) -> dict[str, Any] | None:
        if not embeds or node_id not in embeds["nodes"]:
            return None
        embeds["placed"].add(node_id)
        return copy.deepcopy(embeds["nodes"][node_id])

    def _build_node(
        self, child, comp_map: dict, vis_map: dict, embeds: dict | None = None
    ) -> dict[str, Any] | None:
        """Recursively build a layout node (an Embed where it names a regionId)."""
        if isinstance(child, str):
            embed = self._take_embed(child, embeds)
            if embed is not None:
                return embed
            comp = comp_map.get(child)
            if not comp:
                return {"type": "View", "id": child}
            return self._component_to_node(comp, vis_map)
        elif isinstance(child, dict):
            child_id = child.get("id", "")
            embed = self._take_embed(child_id, embeds) if child_id else None
            comp = comp_map.get(child_id) if child_id and embed is None else None
            if embed is not None:
                node = embed
            else:
                node = self._component_to_node(comp, vis_map) if comp else {"type": "View", "id": child_id}

            # Propagate overlay/zIndex hints from the layout tree
            overlay = bool(child.get("overlay"))
            if overlay:
                # Remove orientation so children stack (ZStack-style)
                node.pop("orientation", None)
            z_index = child.get("zIndex")
            if z_index is not None:
                node["zIndex"] = z_index

            nested = child.get("children", [])
            if nested:
                sub_nodes = []
                for sub in nested:
                    sub_node = self._build_node(sub, comp_map, vis_map, embeds)
                    if sub_node:
                        sub_nodes.append(sub_node)
                if sub_nodes:
                    # Overlay containers may order by zIndex
                    if overlay:
                        sub_nodes.sort(
                            key=lambda n: n.get("zIndex", 0)
                        )
                    node["children"] = sub_nodes
            return node
        return None

    def _component_to_node(self, comp: dict, vis_map: dict) -> dict[str, Any]:
        """Convert a component definition to a layout node.

        Applies optional ``style`` attributes, expands ``binding`` shortcuts
        into ``@{var}`` bindings, and recurses into ``children``.
        """
        node: dict[str, Any] = {
            "type": comp.get("type", "View"),
            "id": comp.get("id", ""),
        }

        # Apply style attributes directly onto the node
        style = comp.get("style")
        if isinstance(style, dict):
            for k, v in style.items():
                node[k] = v

        # Apply binding shortcuts → @{variable}
        binding = comp.get("binding")
        if isinstance(binding, dict):
            for attr, var in binding.items():
                if isinstance(var, str):
                    node[attr] = f"@{{{var}}}"

        # The Layout JSON `platform` directive, as the component declares it
        # (read by jsonui-doc only until jsonui-cli 1.9.0).
        platform = comp.get("platform")
        if isinstance(platform, (str, dict)) and platform:
            node["platform"] = copy.deepcopy(platform)

        # Recurse into spec-defined children
        children = comp.get("children")
        if isinstance(children, list) and children:
            child_nodes = [
                self._component_to_node(c, vis_map)
                for c in children
                if isinstance(c, dict)
            ]
            if child_nodes:
                # Layout JSON uses "child" (singular) for container children
                node["child"] = child_nodes

        # Visibility binding from displayLogic
        comp_id = comp.get("id", "")
        if comp_id in vis_map:
            node["visibility"] = f"@{{{vis_map[comp_id]}}}"

        # Inject decorative elements that target this component as parentId
        decorative_parent_map = getattr(self, "_decorative_by_parent", None) or {}
        if comp_id and comp_id in decorative_parent_map:
            decorative_nodes: list[dict] = []
            for group in decorative_parent_map[comp_id]:
                for sub in group.get("components", []):
                    if isinstance(sub, dict):
                        decorative_nodes.append(self._component_to_node(sub, vis_map))
            if decorative_nodes:
                existing = node.get("child")
                if existing is None:
                    node["child"] = decorative_nodes
                elif isinstance(existing, list):
                    node["child"] = list(existing) + decorative_nodes
                elif isinstance(existing, dict):
                    node["child"] = [existing] + decorative_nodes

        return node

    def _build_collection_node(self, spec: ScreenSpec) -> dict[str, Any]:
        """Build a Collection node from spec."""
        coll = spec.collection
        items_name = _snake_to_camel(coll.id) + "Items"

        node: dict[str, Any] = {
            "type": "Collection",
            "id": coll.id,
            "items": f"@{{{items_name}}}",
            "width": "matchParent",
            "weight": 1,
        }

        if coll.cell_id_property:
            node["cellIdProperty"] = coll.cell_id_property

        if coll.auto_change_tracking_id:
            node["autoChangeTrackingId"] = True

        if coll.cell_classes:
            node["cellClasses"] = list(coll.cell_classes)

        if coll.sections:
            node["sections"] = []
            for section in coll.sections:
                s: dict[str, Any] = {}
                if "cell" in section:
                    s["cell"] = section["cell"]
                if section.get("header"):
                    s["header"] = section["header"]
                if section.get("footer"):
                    s["footer"] = section["footer"]
                if "columns" in section:
                    s["columns"] = section["columns"]
                node["sections"].append(s)

        if coll.columns > 1:
            node["columns"] = coll.columns
        if coll.layout != "vertical":
            node["layout"] = coll.layout
        if coll.line_spacing is not None:
            node["lineSpacing"] = coll.line_spacing
        if coll.column_spacing is not None:
            node["columnSpacing"] = coll.column_spacing
        if coll.paging:
            node["paging"] = True
        # structure.collection.lazy false: "a plain VStack/Column/div with
        # ForEach and NO scroll container" (the spec schema) — the Layout's
        # lazy "none". true is the Layout default and is not written.
        if coll.lazy is False:
            node["lazy"] = "none"

        return node

    def _build_tabview_layout(self, spec: ScreenSpec, data_section: list) -> dict[str, Any]:
        """Build a TabView layout."""
        tabs = []
        for tab in spec.tab_view.tabs:
            tab_entry: dict[str, Any] = {
                "title": tab.get("title", ""),
                "view": tab.get("layoutFile", tab.get("view", "")),
            }
            if tab.get("icon"):
                tab_entry["icon"] = tab["icon"]
            if tab.get("selectedIcon"):
                tab_entry["selectedIcon"] = tab["selectedIcon"]
            if tab.get("iconType"):
                tab_entry["iconType"] = tab["iconType"]
            tabs.append(tab_entry)

        return {
            "data": data_section,
            "type": "TabView",
            "id": spec.tab_view.id,
            "selectedIndex": "@{selectedTabIndex}",
            "tabs": tabs,
        }
