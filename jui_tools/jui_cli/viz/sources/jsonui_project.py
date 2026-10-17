"""A JsonUI project's specs, layouts and test definitions, summarised for the boards.

Design: 09 §1–§4. The spec's shape is the one in
document_tools/jsonui_doc_cli/spec_doc/screen_spec_schema.py; nothing here
guesses beyond it. A spec that does not parse (mid-write) keeps its previous
summary and is marked writing.

The usual spec names its Layout with ``metadata.layoutFile`` and leaves
``structure.components`` empty (measured 2026-10-18: 0 of 279 specs across
two projects list components, 267 name a layoutFile, resolved as
``<layouts_directory>/<layoutFile>.json`` — 108 of 108 in JsonUIDocument).
So the structure section and the sheet's layout are read from that Layout
file; components are used only when a spec does list them.

The implementation count is a guide, not a verdict: `jui verify` is the
judge, and it is never run automatically (it is heavy).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

SECTIONS = ("metadata", "structure", "stateManagement", "dataFlow", "userActions", "transitions", "branchContracts")
METADATA_FIELDS = ("name", "displayName", "description", "platforms", "layoutFile")
SKIP_DIRS = {"node_modules", "build", ".git", "DerivedData", "Pods", ".gradle", "dist", ".next"}
WRITING_MS = 10_000


def _count(value) -> int:
    if isinstance(value, (list, dict)):
        return len(value)
    return 1 if value not in (None, "", False) else 0


def section_items(spec: dict, key: str, layout_nodes: int = 0) -> int:
    if key == "metadata":
        meta = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
        return sum(1 for f in METADATA_FIELDS if meta.get(f))
    if key == "structure":
        st = spec.get("structure") if isinstance(spec.get("structure"), dict) else {}
        components = st.get("components")
        if components:
            return len(components)
        return _layout_size(st.get("layout")) or layout_nodes
    if key == "stateManagement":
        sm = spec.get("stateManagement") if isinstance(spec.get("stateManagement"), dict) else {}
        return sum(_count(sm.get(k)) for k in ("states", "uiVariables", "eventHandlers", "displayLogic") if sm.get(k))
    if key == "dataFlow":
        df = spec.get("dataFlow") if isinstance(spec.get("dataFlow"), dict) else {}
        vm = df.get("viewModel") if isinstance(df.get("viewModel"), dict) else {}
        return (sum(_count(df.get(k)) for k in ("repositories", "useCases", "apiEndpoints", "customTypes") if df.get(k))
                + _count(vm.get("methods")) * bool(vm.get("methods")) + _count(vm.get("vars")) * bool(vm.get("vars")))
    if key == "userActions":
        n = _count(spec.get("userActions")) if spec.get("userActions") else 0
        val = spec.get("validation") if isinstance(spec.get("validation"), dict) else {}
        return n + sum(_count(val.get(k)) for k in ("clientSide", "serverSide") if val.get(k))
    if key == "transitions":
        return _count(spec.get("transitions")) if spec.get("transitions") else 0
    if key == "branchContracts":
        bc = spec.get("branchContracts") if isinstance(spec.get("branchContracts"), dict) else {}
        methods = bc.get("methods") if isinstance(bc.get("methods"), dict) else {}
        return sum(len(m.get("branches") or []) for m in methods.values() if isinstance(m, dict))
    return 0


def _layout_size(node) -> int:
    if isinstance(node, str):
        return 1
    if not isinstance(node, dict):
        return 0
    total = 1 if node.get("root") or node.get("id") else 0
    for child in node.get("children") or []:
        total += _layout_size(child)
    return total


def section_hash(spec: dict, key: str) -> str:
    value = spec.get(key)
    if key == "userActions":
        value = [value, spec.get("validation")]
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def component_ids(spec: dict) -> list[str]:
    st = spec.get("structure") if isinstance(spec.get("structure"), dict) else {}
    return [c["id"] for c in st.get("components") or [] if isinstance(c, dict) and isinstance(c.get("id"), str)]


def layout_nodes(path: Path) -> list[dict]:
    """The components of a Layout JSON tree, depth-first: {type, id?, depth}.

    A component is an object with a string "type". Children are read from
    "child" (one object or a list) and "children", the two spellings Layout
    JSON uses.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[dict] = []

    def walk(node, depth: int) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, depth)
            return
        if not isinstance(node, dict):
            return
        if isinstance(node.get("type"), str):
            item = {"type": node["type"], "depth": depth}
            if isinstance(node.get("id"), str):
                item["id"] = node["id"]
            out.append(item)
            depth += 1
        for key in ("child", "children"):
            if key in node:
                walk(node[key], depth)

    walk(data, 0)
    return out


def layout_ids(path: Path) -> set[str]:
    return {n["id"] for n in layout_nodes(path) if "id" in n}


@dataclass
class SpecEntry:
    path: Path
    data: dict | None = None
    hashes: dict = field(default_factory=dict)
    writing_until: dict = field(default_factory=dict)  # section -> ms
    broken: bool = False
    by: str | None = None
    by_until: int = 0


class JsonUIProject:
    def __init__(self, root: Path, project_id: str) -> None:
        self.root = Path(root)
        self.project_id = project_id
        raw = json.loads((self.root / "jui.config.json").read_text(encoding="utf-8"))
        self.config = raw if isinstance(raw, dict) else {}

        def folder(key: str, default: str) -> Path:
            value = self.config.get(key) or default
            path = Path(value)
            return path if path.is_absolute() else self.root / path

        self.spec_dir = folder("spec_directory", "docs/screens/json")
        self.layouts_dir = folder("layouts_directory", "docs/screens/layouts")
        test_cfg = self.config.get("test") if isinstance(self.config.get("test"), dict) else {}
        test_dir = Path(test_cfg.get("testDir") or "tests")
        self.tests_dir = test_dir if test_dir.is_absolute() else self.root / test_dir
        self.specs: dict[str, SpecEntry] = {}
        self._layout_cache: dict[Path, tuple[int, list[dict]]] = {}
        self.test_cases: dict[str, int] = {}  # spec file stem / layout name -> case count
        self.test_results: dict[str, dict] = {}  # spec id -> {passed, failed, running}

    # ---------------------------------------------------------------- loading

    def spec_id(self, path: Path) -> str:
        try:
            rel = path.relative_to(self.spec_dir).as_posix()
        except ValueError:
            rel = path.name
        return f"{self.project_id}:{rel}"

    def load_all(self, at: int) -> None:
        if self.spec_dir.is_dir():
            for path in sorted(self.spec_dir.rglob("*.spec.json")):
                if not SKIP_DIRS.intersection(path.relative_to(self.spec_dir).parts):
                    self.reload_spec(path, at, by=None, initial=True)
        self.load_tests()

    def reload_spec(self, path: Path, at: int, by: str | None, initial: bool = False) -> list[str]:
        """Read one spec again. Returns the sections that changed (written now)."""
        sid = self.spec_id(path)
        entry = self.specs.get(sid) or SpecEntry(path=path)
        self.specs[sid] = entry
        if not path.exists():
            del self.specs[sid]
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            entry.broken = True  # mid-write: keep the previous summary
            if by:
                entry.by, entry.by_until = by, at + WRITING_MS
            return []
        entry.broken = False
        changed = []
        for key in SECTIONS:
            h = section_hash(data, key)
            if not initial and entry.hashes.get(key) not in (None, h):
                changed.append(key)
                entry.writing_until[key] = at + WRITING_MS
            entry.hashes[key] = h
        entry.data = data
        if by:
            entry.by, entry.by_until = by, at + WRITING_MS
        return changed

    def load_tests(self) -> None:
        self.test_cases = {}
        for sub in ("screens", "flows"):
            folder = self.tests_dir / sub
            if not folder.is_dir():
                continue
            for path in folder.glob("*.test.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(data, dict):
                    continue
                cases = data.get("cases") if isinstance(data.get("cases"), list) else []
                n = sum(1 for c in cases if isinstance(c, dict) and c.get("name"))
                for key in self._test_keys(data):
                    self.test_cases[key] = self.test_cases.get(key, 0) + n

    @staticmethod
    def _test_keys(data: dict) -> list[str]:
        keys = []
        sources = [data.get("source")] if isinstance(data.get("source"), dict) else []
        sources += [s for s in data.get("sources") or [] if isinstance(s, dict)]
        for src in sources:
            for k in ("layout", "document"):
                v = src.get(k)
                if isinstance(v, str) and v:
                    keys.append(Path(v).name.replace(".spec.json", "").replace(".json", ""))
        return keys

    # ---------------------------------------------------------------- lookups

    def layout_nodes_cached(self, path: Path | None) -> list[dict]:
        if path is None:
            return []
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            return []
        hit = self._layout_cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
        nodes = layout_nodes(path)
        self._layout_cache[path] = (mtime, nodes)
        return nodes

    def layout_ids_cached(self, path: Path | None) -> set[str]:
        return {n["id"] for n in self.layout_nodes_cached(path) if "id" in n}

    def layout_path(self, spec: dict) -> Path | None:
        meta = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
        name = meta.get("layoutFile")
        if not isinstance(name, str) or not name:
            return None
        path = self.layouts_dir / (name if name.endswith(".json") else f"{name}.json")
        return path

    def related_paths(self, spec: dict) -> list[Path]:
        out = []
        for item in spec.get("relatedFiles") or []:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                p = Path(item["path"])
                out.append(p if p.is_absolute() else self.root / p)
        return out

    def specs_touching(self, file_path: str) -> list[str]:
        """Spec ids a file edit belongs to: the spec itself, its Layout, its relatedFiles."""
        target = Path(file_path)
        hits = []
        for sid, entry in self.specs.items():
            if target == entry.path:
                hits.append(sid)
                continue
            data = entry.data or {}
            lp = self.layout_path(data)
            if (lp and target == lp) or target in self.related_paths(data):
                hits.append(sid)
        return hits

    def impl(self, spec: dict) -> dict:
        total = done = 0
        for path in self.related_paths(spec):
            total += 1
            done += path.exists()
        lp = self.layout_path(spec)
        if lp is not None:
            total += 1
            done += lp.exists()
        ids = component_ids(spec)
        if ids:
            present = self.layout_ids_cached(lp) if lp else set()
            total += len(ids)
            done += sum(1 for i in ids if i in present)
        return {"total": total, "done": done}

    # ---------------------------------------------------------------- slice

    def summaries(self, at: int) -> list[dict]:
        out = []
        for sid, entry in sorted(self.specs.items()):
            data = entry.data or {}
            meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            stem = entry.path.name.replace(".spec.json", "")
            sections = []
            nodes = len(self.layout_nodes_cached(self.layout_path(data)))
            for key in SECTIONS:
                items = section_items(data, key, nodes)
                writing = entry.writing_until.get(key, 0) > at or (entry.broken and entry.by_until > at)
                state = "writing" if writing else ("written" if items else "empty")
                sections.append({"key": key, "state": state, "items": items})
            impl = self.impl(data)
            layout_name = meta.get("layoutFile") if isinstance(meta.get("layoutFile"), str) else None
            cases = self.test_cases.get(stem, 0) + (self.test_cases.get(layout_name, 0) if layout_name and layout_name != stem else 0)
            result = self.test_results.get(sid, {})
            tests = {"total": cases, "passed": result.get("passed", 0), "failed": result.get("failed", 0),
                     "running": bool(result.get("running"))}
            by = entry.by if entry.by_until > at else None
            written_any = any(s["items"] for s in sections)
            impl_done = impl["total"] > 0 and impl["done"] == impl["total"]
            tests_done = cases > 0 and tests["passed"] >= cases and not tests["failed"]
            bucket = "live" if by else "todo" if not written_any else "done" if impl_done and tests_done else "partial"
            item = {
                "id": sid, "projectId": self.project_id,
                "name": meta.get("displayName") or meta.get("name") or stem,
                "file": os.path.relpath(entry.path, self.root),
                "sections": sections, "impl": impl, "tests": tests, "bucket": bucket,
                "updatedAt": at,
            }
            if by:
                item["by"] = by
            out.append(item)
        return out


def watch(project: JsonUIProject, on_change):
    """watchdog on the project's spec, layout and test folders; on_change(path) per file event.

    Returns the observer (call .stop() / .join()), or None when none of the
    folders exist. Folders in SKIP_DIRS are ignored.
    """
    folders = [f for f in {project.spec_dir, project.layouts_dir, project.tests_dir} if f.is_dir()]
    if not folders:
        return None
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory or event.event_type not in ("created", "modified", "moved", "deleted"):
                return
            raw = getattr(event, "dest_path", "") or event.src_path
            path = raw if isinstance(raw, str) else raw.decode()
            if not path.endswith(".json") or SKIP_DIRS.intersection(Path(path).parts):
                return
            on_change(path)

    observer = Observer()
    for folder in folders:
        observer.schedule(Handler(), str(folder), recursive=True)
    observer.daemon = True
    observer.start()
    return observer

