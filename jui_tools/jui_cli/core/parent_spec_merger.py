"""Merge a screen_parent_spec with its sub-specs into a single ScreenSpec.

Usage::

    from jui_cli.core.parent_spec_merger import ParentSpecMerger

    merger = ParentSpecMerger(spec_dir=Path("docs/screens/json"))
    merged_dict = merger.merge_from_file(Path("docs/screens/json/chat.spec.json"))
    # merged_dict is a screen_spec-shaped dict ready for extract_screen_spec()

The merger is intentionally defensive: it never rewrites sub-spec files
and gives the parent final say on metadata / rootComponents / notes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MergeConflict:
    path: str
    message: str


@dataclass
class MergeResult:
    spec: dict[str, Any]
    sub_spec_paths: list[Path] = field(default_factory=list)
    conflicts: list[MergeConflict] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


class ParentSpecMerger:
    """Merge screen_parent_spec + sub-specs into a single spec dict."""

    def __init__(self, spec_dir: Path | None = None):
        self._spec_dir = Path(spec_dir) if spec_dir else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def merge_from_file(self, parent_path: Path) -> MergeResult:
        """Load a parent_spec file, resolve sub_spec paths, and merge."""
        parent_path = Path(parent_path)
        parent_data = json.loads(parent_path.read_text())

        if parent_data.get("type") != "screen_parent_spec":
            raise ValueError(
                f"{parent_path} is not a screen_parent_spec "
                f"(type={parent_data.get('type')!r})"
            )

        base_dir = self._spec_dir or parent_path.parent
        sub_spec_paths: list[Path] = []
        sub_specs: list[dict] = []
        for entry in parent_data.get("subSpecs", []) or []:
            file_ref = entry.get("file")
            if not file_ref:
                continue
            path = (base_dir / file_ref).resolve()
            if not path.exists():
                # Try sibling-relative as a fallback
                alt = (parent_path.parent / file_ref).resolve()
                path = alt if alt.exists() else path
            sub_spec_paths.append(path)
            sub_specs.append(json.loads(path.read_text()))

        merged, conflicts = self.merge(parent_data, sub_specs)
        return MergeResult(spec=merged, sub_spec_paths=sub_spec_paths, conflicts=conflicts)

    def merge(
        self, parent_spec: dict, sub_specs: list[dict]
    ) -> tuple[dict[str, Any], list[MergeConflict]]:
        """Merge parent_spec with all sub_specs. Returns (merged_dict, conflicts)."""
        conflicts: list[MergeConflict] = []
        merged: dict[str, Any] = {
            "type": "screen_spec",
            "version": parent_spec.get("version", "1.0"),
            "metadata": dict(parent_spec.get("metadata", {})),
        }

        # ---- structure ----
        structure: dict[str, Any] = {
            "components": [],
            "layout": {},
            "decorativeElements": [],
            "wrapperViews": [],
            "customComponents": [],
            "collection": None,
            "tabView": None,
        }

        # Carry through parent-provided rootComponents as notes (the parent
        # tends to describe concept-level roots, not actual components)
        parent_structure = parent_spec.get("structure") or {}
        if parent_structure.get("notes"):
            structure["notes"] = parent_structure["notes"]

        # ---- stateManagement ----
        state: dict[str, Any] = {
            "states": [],
            "uiVariables": [],
            "eventHandlers": [],
            "displayLogic": [],
        }

        # ---- dataFlow ----
        data_flow: dict[str, Any] = {
            "repositories": [],
            "useCases": [],
            "apiEndpoints": [],
        }

        # ---- other top-level sections collected by list concat ----
        user_actions: list = []
        transitions: list = []
        related_files: list = []
        notes_parts: list[str] = []

        # Track seen keys to spot conflicts cleanly
        seen_components: dict[str, tuple[str, dict]] = {}   # id → (source, comp)
        seen_ui_vars: dict[str, tuple[str, dict]] = {}
        seen_handlers: dict[str, tuple[str, dict]] = {}
        seen_repos: dict[str, tuple[str, dict]] = {}
        seen_use_cases: dict[str, tuple[str, dict]] = {}
        seen_endpoints: dict[tuple[str, str], tuple[str, dict]] = {}

        def record_conflict(path: str, message: str) -> None:
            conflicts.append(MergeConflict(path=path, message=message))

        # Each sub-spec contributes data
        for sub in sub_specs:
            source_name = (
                (sub.get("metadata") or {}).get("name")
                or sub.get("type", "sub_spec")
            )
            sub_structure = sub.get("structure") or {}
            sub_state = sub.get("stateManagement") or {}
            sub_flow = sub.get("dataFlow") or {}

            # Components
            for comp in sub_structure.get("components", []) or []:
                if not isinstance(comp, dict):
                    continue
                cid = comp.get("id")
                if not cid:
                    structure["components"].append(comp)
                    continue
                if cid in seen_components:
                    prev_src, prev = seen_components[cid]
                    if _stripped_equal(prev, comp):
                        continue  # identical duplicate, skip silently
                    record_conflict(
                        path=f"structure.components[id={cid}]",
                        message=(
                            f"Defined by both '{prev_src}' and '{source_name}'"
                        ),
                    )
                    continue
                seen_components[cid] = (source_name, comp)
                structure["components"].append(comp)

            # decorativeElements / wrapperViews / customComponents
            for key in ("decorativeElements", "wrapperViews", "customComponents"):
                for entry in sub_structure.get(key, []) or []:
                    structure[key].append(entry)

            # layout: the first sub-spec that provides one wins
            sub_layout = sub_structure.get("layout")
            if sub_layout and not structure["layout"]:
                structure["layout"] = sub_layout

            # collection / tabView: the first one wins
            if sub_structure.get("collection") and structure["collection"] is None:
                structure["collection"] = sub_structure["collection"]
            if sub_structure.get("tabView") and structure["tabView"] is None:
                structure["tabView"] = sub_structure["tabView"]

            # uiVariables
            for var in sub_state.get("uiVariables", []) or []:
                if not isinstance(var, dict):
                    continue
                name = var.get("name")
                if not name:
                    state["uiVariables"].append(var)
                    continue
                if name in seen_ui_vars:
                    prev_src, prev = seen_ui_vars[name]
                    if _stripped_equal(prev, var):
                        continue
                    record_conflict(
                        path=f"stateManagement.uiVariables[name={name}]",
                        message=(
                            f"Defined differently in '{prev_src}' and "
                            f"'{source_name}' (types "
                            f"{prev.get('type')!r} vs {var.get('type')!r})"
                        ),
                    )
                    continue
                seen_ui_vars[name] = (source_name, var)
                state["uiVariables"].append(var)

            # eventHandlers
            for h in sub_state.get("eventHandlers", []) or []:
                if not isinstance(h, dict):
                    continue
                name = h.get("name")
                if not name:
                    state["eventHandlers"].append(h)
                    continue
                if name in seen_handlers:
                    prev_src, prev = seen_handlers[name]
                    if _stripped_equal(prev, h):
                        continue
                    record_conflict(
                        path=f"stateManagement.eventHandlers[name={name}]",
                        message=(
                            f"Defined by both '{prev_src}' and '{source_name}'"
                        ),
                    )
                    continue
                seen_handlers[name] = (source_name, h)
                state["eventHandlers"].append(h)

            # displayLogic: always concatenate (conditions may stack)
            for rule in sub_state.get("displayLogic", []) or []:
                state["displayLogic"].append(rule)

            # repositories
            for repo in sub_flow.get("repositories", []) or []:
                if not isinstance(repo, dict):
                    continue
                name = repo.get("name")
                if not name:
                    data_flow["repositories"].append(repo)
                    continue
                if name in seen_repos:
                    prev_src, prev = seen_repos[name]
                    merged_repo = _merge_repo(prev, repo, prev_src, source_name, conflicts)
                    seen_repos[name] = (f"{prev_src}+{source_name}", merged_repo)
                    # Replace in list
                    data_flow["repositories"] = [
                        merged_repo if r is prev else r
                        for r in data_flow["repositories"]
                    ]
                else:
                    seen_repos[name] = (source_name, repo)
                    data_flow["repositories"].append(repo)

            # useCases
            for uc in sub_flow.get("useCases", []) or []:
                if not isinstance(uc, dict):
                    continue
                name = uc.get("name")
                if not name:
                    data_flow["useCases"].append(uc)
                    continue
                if name in seen_use_cases:
                    prev_src, prev = seen_use_cases[name]
                    if _stripped_equal(prev, uc):
                        continue
                    record_conflict(
                        path=f"dataFlow.useCases[name={name}]",
                        message=(
                            f"Defined differently in '{prev_src}' and '{source_name}'"
                        ),
                    )
                    continue
                seen_use_cases[name] = (source_name, uc)
                data_flow["useCases"].append(uc)

            # apiEndpoints
            for ep in sub_flow.get("apiEndpoints", []) or []:
                if not isinstance(ep, dict):
                    continue
                key = (ep.get("method", ""), ep.get("path", ""))
                if key == ("", ""):
                    data_flow["apiEndpoints"].append(ep)
                    continue
                if key in seen_endpoints:
                    prev_src, prev = seen_endpoints[key]
                    if _stripped_equal(prev, ep):
                        continue
                    record_conflict(
                        path=f"dataFlow.apiEndpoints[{key[0]} {key[1]}]",
                        message=(
                            f"Defined differently in '{prev_src}' and '{source_name}'"
                        ),
                    )
                    continue
                seen_endpoints[key] = (source_name, ep)
                data_flow["apiEndpoints"].append(ep)

            # List-style sections: concat
            for src_list, dest in (
                (sub.get("userActions") or [], user_actions),
                (sub.get("transitions") or [], transitions),
                (sub.get("relatedFiles") or [], related_files),
            ):
                for item in src_list:
                    dest.append(item)

            # Notes
            if sub.get("notes"):
                v = sub["notes"]
                if isinstance(v, list):
                    notes_parts.extend(v)
                else:
                    notes_parts.append(str(v))

        # Parent additions (parent wins on non-list sections)
        for section_name, container in (
            ("structure", structure),
            ("stateManagement", state),
            ("dataFlow", data_flow),
        ):
            parent_section = parent_spec.get(section_name) or {}
            if not isinstance(parent_section, dict):
                continue
            for k, v in parent_section.items():
                if isinstance(v, list):
                    continue  # lists already handled above via sub-specs
                # Only set if missing or empty
                if not container.get(k):
                    container[k] = v

        parent_related = parent_spec.get("relatedFiles") or []
        related_files = parent_related + related_files  # parent listed first
        parent_notes = parent_spec.get("notes")
        if parent_notes:
            if isinstance(parent_notes, list):
                notes_parts = list(parent_notes) + notes_parts
            else:
                notes_parts = [str(parent_notes)] + notes_parts

        # Remove any structure keys that never received data (keep schema clean)
        if not structure["decorativeElements"]:
            structure.pop("decorativeElements", None)
        if not structure["wrapperViews"]:
            structure.pop("wrapperViews", None)
        if not structure["customComponents"]:
            structure.pop("customComponents", None)
        if structure["collection"] is None:
            structure.pop("collection", None)
        if structure["tabView"] is None:
            structure.pop("tabView", None)

        # Provide a placeholder layout if nothing was specified
        if not structure["layout"]:
            if structure["components"]:
                structure["layout"] = {
                    "root": structure["components"][0].get("id", ""),
                    "children": [],
                }
            else:
                structure["layout"] = {"root": "", "children": []}

        merged["structure"] = structure
        merged["stateManagement"] = state
        merged["dataFlow"] = data_flow
        if user_actions:
            merged["userActions"] = user_actions
        if transitions:
            merged["transitions"] = transitions
        if related_files:
            merged["relatedFiles"] = related_files
        if notes_parts:
            merged["notes"] = notes_parts

        return merged, conflicts


def _stripped_equal(a: dict, b: dict) -> bool:
    """Compare two dicts ignoring description/notes drift."""
    ignore = {"description", "notes", "createdAt", "updatedAt"}
    ak = {k: v for k, v in a.items() if k not in ignore}
    bk = {k: v for k, v in b.items() if k not in ignore}
    return ak == bk


def _merge_repo(
    prev: dict,
    curr: dict,
    prev_src: str,
    curr_src: str,
    conflicts: list[MergeConflict],
) -> dict:
    """Merge two repository definitions with the same name.

    Combines method lists by method name (same name + same signature = dedup,
    same name + different signature = conflict).
    """
    merged = dict(prev)
    prev_methods = {_method_signature(m): ("_prev", m) for m in prev.get("methods", []) or []}
    for m in curr.get("methods", []) or []:
        sig = _method_signature(m)
        if sig in prev_methods:
            continue
        # Look for same name with different signature
        name = sig.split("(")[0]
        same_name_sig = next(
            (s for s in prev_methods if s.startswith(name + "(")), None
        )
        if same_name_sig:
            conflicts.append(MergeConflict(
                path=f"dataFlow.repositories[{prev.get('name')}].methods[{name}]",
                message=(
                    f"Signature differs between '{prev_src}' and '{curr_src}': "
                    f"{same_name_sig} vs {sig}"
                ),
            ))
            continue
        prev_methods[sig] = ("_curr", m)
    merged["methods"] = [v for _, v in prev_methods.values()]
    return merged


def _method_signature(m: Any) -> str:
    """Produce a stable signature string for a method entry."""
    if isinstance(m, str):
        return m
    if not isinstance(m, dict):
        return str(m)
    name = m.get("name", "")
    params = m.get("params")
    if isinstance(params, str):
        return f"{name}({params})"
    if isinstance(params, list):
        parts = []
        for p in params:
            if isinstance(p, dict):
                parts.append(f"{p.get('name', '')}: {p.get('type', '')}")
            else:
                parts.append(str(p))
        return f"{name}({', '.join(parts)})"
    return f"{name}()"
