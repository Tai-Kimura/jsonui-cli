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

A room can hold more than one JsonUI app. Its root is the nearest
jui.config.json above the session's cwd (rooms.py), and that config may
declare no specs at all — a repo whose top config only carries the docs
contract checks, with each app below it (client/, admin/, …) declaring its
own ``spec_directory``. So the specs are read from every config in the room:
the root's and those up to SOURCE_DEPTH folders below it (SKIP_DIRS pruned),
each one a Source with its own spec, layout and test folders. A config
reached twice — a signpost that ``extends`` the real one, both landing on the
same spec folder — is one Source (spec folders are compared by realpath).
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
CONFIG_NAME = "jui.config.json"
DEFAULT_SPEC_DIR = "docs/screens/json"
#: How many folders below the room's root a config is looked for.
SOURCE_DEPTH = 3
#: Four hops past the first config, five files at most.
#: ⚠️ The same number and rules as `_MAX_EXTENDS_HOPS` / `_follow_extends` /
#: `_extends_target` in document_tools/jsonui_doc_cli/project_config.py
#: (resolve against the config's own folder, complete a folder with
#: jui.config.json, stop on a cycle). Not imported: jui_cli reaches
#: document_tools only through the sys.path bridge
#: (config_manager.ensure_document_tools_importable), which a live server
#: should not depend on. Change the rules in one and change them in the other.
MAX_EXTENDS_HOPS = 4


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


def _read_config(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _extends_target(config: Path) -> Path | None:
    """The config this one extends, resolved against its own folder (a folder gets jui.config.json)."""
    extends = _read_config(config).get("extends")
    if not isinstance(extends, str) or not extends.strip():
        return None
    resolved = (config.parent / extends).resolve()
    if resolved.is_dir():
        resolved = resolved / CONFIG_NAME
    return resolved


def follow_extends(config: Path) -> Path | None:
    """The first config along ``extends`` (this one included) that declares ``spec_directory``.

    A config without one is a signpost when it extends another — the real
    tree keeps ``docs/<app>/jui.config.json`` with only ``extends:
    ../../<app>/jui.config.json``. None when nothing on the chain declares
    specs, the chain breaks, loops, or runs past MAX_EXTENDS_HOPS.
    """
    seen: set[Path] = set()
    current = config
    for _ in range(MAX_EXTENDS_HOPS + 1):
        if current in seen:
            return None
        seen.add(current)
        if _read_config(current).get("spec_directory"):
            return current
        nxt = _extends_target(current)
        if nxt is None or not nxt.is_file():
            return None
        current = nxt
    return None


def find_configs(root: Path, depth: int = SOURCE_DEPTH) -> list[Path]:
    """jui.config.json at the room's root and up to ``depth`` folders below it, root first, then by path."""
    found = [root / CONFIG_NAME] if (root / CONFIG_NAME).is_file() else []
    below: list[Path] = []

    def walk(folder: Path, level: int) -> None:
        if level > depth:
            return
        try:
            children = sorted(p for p in folder.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return
        for child in children:
            if child.name in SKIP_DIRS:
                continue
            if (child / CONFIG_NAME).is_file():
                below.append(child / CONFIG_NAME)
            walk(child, level + 1)

    walk(root, 1)
    return found + below


@dataclass
class Source:
    """One JsonUI app in a room: where its specs, layouts and tests are."""
    key: str            # "" for the room's own config, else the app folder relative to the room ("client")
    root: Path          # the folder of the config that declares the specs
    spec_dir: Path
    layouts_dir: Path
    tests_dir: Path
    test_cases: dict = field(default_factory=dict)       # spec file stem / layout name -> case count
    test_file_keys: dict = field(default_factory=dict)   # "screens/login.test.json" -> spec keys

    @classmethod
    def from_config(cls, key: str, config_path: Path) -> "Source":
        root = config_path.parent
        config = _read_config(config_path)

        def folder(value, default: str) -> Path:
            path = Path(value or default)
            return path if path.is_absolute() else root / path

        test_cfg = config.get("test") if isinstance(config.get("test"), dict) else {}
        return cls(key=key, root=root,
                   spec_dir=folder(config.get("spec_directory"), DEFAULT_SPEC_DIR),
                   layouts_dir=folder(config.get("layouts_directory"), "docs/screens/layouts"),
                   tests_dir=folder(test_cfg.get("testDir"), "tests"))


def discover_sources(root: Path) -> list[Source]:
    """Every Source of a room, one per distinct spec folder.

    The room's own config is read as it always was: its ``spec_directory``,
    else the default folder. A config below it counts when it, or a config it
    extends, declares ``spec_directory``. The app is named after the folder of
    the config that declares (so a signpost and its target are one app).
    A config that declares outside the room (``extends`` into another repo)
    is that repo's app, read in that repo's room, not here.
    """
    root = Path(root)
    room = root.resolve()
    sources: list[Source] = []
    seen: set[str] = set()
    for config in find_configs(root):
        is_root = config.parent == root
        declared = follow_extends(config)
        if declared is not None and not declared.resolve().parent.is_relative_to(room):
            declared = None
        if declared is None and not is_root:
            continue
        owner = declared or config
        key = "" if owner.parent.resolve() == root.resolve() else os.path.relpath(owner.parent, root).replace(os.sep, "/")
        source = Source.from_config(key, owner)
        real = os.path.realpath(source.spec_dir)
        if real in seen:
            continue
        seen.add(real)
        sources.append(source)
    return sources


@dataclass
class SpecEntry:
    path: Path
    data: dict | None = None
    hashes: dict = field(default_factory=dict)
    writing_until: dict = field(default_factory=dict)  # section -> ms
    broken: bool = False
    by: str | None = None
    by_until: int = 0
    source: Source | None = None


class JsonUIProject:
    def __init__(self, root: Path, project_id: str) -> None:
        self.root = Path(root)
        self.project_id = project_id
        # Raises like it always did when the room's own config is unreadable.
        raw = json.loads((self.root / CONFIG_NAME).read_text(encoding="utf-8"))
        self.config = raw if isinstance(raw, dict) else {}
        self.sources = discover_sources(self.root)
        self.specs: dict[str, SpecEntry] = {}
        self._layout_cache: dict[Path, tuple[int, list[dict]]] = {}
        self.test_results: dict[str, dict] = {}  # spec id -> {passed, failed, running}

    @property
    def test_cases(self) -> dict[str, int]:
        merged: dict[str, int] = {}
        for source in self.sources:
            for k, n in source.test_cases.items():
                merged[k] = merged.get(k, 0) + n
        return merged

    def artifact_dirs(self) -> list[Path]:
        """Every spec, layout and test folder of the room's apps."""
        out: list[Path] = []
        for source in self.sources:
            for d in (source.spec_dir, source.layouts_dir, source.tests_dir):
                if d not in out:
                    out.append(d)
        return out

    # ---------------------------------------------------------------- loading

    def source_of(self, path: Path) -> Source | None:
        """The app whose spec folder holds this file (the deepest one when folders nest)."""
        best = None
        for source in self.sources:
            if path.is_relative_to(source.spec_dir) and (best is None or len(source.spec_dir.parts) > len(best.spec_dir.parts)):
                best = source
        return best

    def spec_id(self, path: Path, source: Source | None = None) -> str:
        source = source or self.source_of(path)
        try:
            rel = path.relative_to(source.spec_dir).as_posix() if source else path.name
        except ValueError:
            rel = path.name
        # The room's own app keeps the id it always had.
        return f"{self.project_id}:{source.key}/{rel}" if source and source.key else f"{self.project_id}:{rel}"

    def load_all(self, at: int) -> None:
        for source in self.sources:
            if source.spec_dir.is_dir():
                for path in sorted(source.spec_dir.rglob("*.spec.json")):
                    if not SKIP_DIRS.intersection(path.relative_to(source.spec_dir).parts):
                        self.reload_spec(path, at, by=None, initial=True, source=source)
        self.load_tests()

    def reload_spec(self, path: Path, at: int, by: str | None, initial: bool = False,
                    source: Source | None = None) -> list[str]:
        """Read one spec again. Returns the sections that changed (written now)."""
        source = source or self.source_of(path)
        sid = self.spec_id(path, source)
        entry = self.specs.get(sid) or SpecEntry(path=path, source=source)
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
        for source in self.sources:
            source.test_cases, source.test_file_keys = {}, {}
            for sub in ("screens", "flows"):
                folder = source.tests_dir / sub
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
                    keys = self._test_keys(data)
                    source.test_file_keys[f"{sub}/{path.name}"] = keys
                    for key in keys:
                        source.test_cases[key] = source.test_cases.get(key, 0) + n

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

    def _source(self, source: Source | None) -> Source | None:
        return source or (self.sources[0] if self.sources else None)

    def layout_path(self, spec: dict, source: Source | None = None) -> Path | None:
        meta = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
        name = meta.get("layoutFile")
        source = self._source(source)
        if not isinstance(name, str) or not name or source is None:
            return None
        path = source.layouts_dir / (name if name.endswith(".json") else f"{name}.json")
        return path

    def related_paths(self, spec: dict, source: Source | None = None) -> list[Path]:
        source = self._source(source)
        base = source.root if source else self.root
        out = []
        for item in spec.get("relatedFiles") or []:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                p = Path(item["path"])
                out.append(p if p.is_absolute() else base / p)
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
            lp = self.layout_path(data, entry.source)
            if (lp and target == lp) or target in self.related_paths(data, entry.source):
                hits.append(sid)
        return hits

    def impl(self, spec: dict, source: Source | None = None) -> dict:
        total = done = 0
        for path in self.related_paths(spec, source):
            total += 1
            done += path.exists()
        lp = self.layout_path(spec, source)
        if lp is not None:
            total += 1
            done += lp.exists()
        ids = component_ids(spec)
        if ids:
            present = self.layout_ids_cached(lp) if lp else set()
            total += len(ids)
            done += sum(1 for i in ids if i in present)
        return {"total": total, "done": done}

    def specs_for_test_file(self, rel: str) -> list[str]:
        """Spec ids a test file (as the runner names it, e.g. screens/login.test.json) belongs to."""
        # The apps that have this test file; when none does, every app (by name).
        owners = [s for s in self.sources if rel in s.test_file_keys]
        keys = {k for s in owners for k in s.test_file_keys[rel]}
        if not keys:
            keys = {Path(rel).name.replace(".test.json", "")}
        hits = []
        for sid, entry in self.specs.items():
            if owners and entry.source not in owners:
                continue
            meta = (entry.data or {}).get("metadata") or {}
            names = {entry.path.name.replace(".spec.json", "")}
            if isinstance(meta.get("layoutFile"), str):
                names.add(Path(meta["layoutFile"]).name)
            if names & keys:
                hits.append(sid)
        return hits

    # ---------------------------------------------------------------- slice

    def summaries(self, at: int) -> list[dict]:
        out = []
        for sid, entry in sorted(self.specs.items()):
            data = entry.data or {}
            meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            stem = entry.path.name.replace(".spec.json", "")
            sections = []
            nodes = len(self.layout_nodes_cached(self.layout_path(data, entry.source)))
            for key in SECTIONS:
                items = section_items(data, key, nodes)
                writing = entry.writing_until.get(key, 0) > at or (entry.broken and entry.by_until > at)
                state = "writing" if writing else ("written" if items else "empty")
                sections.append({"key": key, "state": state, "items": items})
            impl = self.impl(data, entry.source)
            layout_name = meta.get("layoutFile") if isinstance(meta.get("layoutFile"), str) else None
            test_cases = entry.source.test_cases if entry.source else {}
            cases = test_cases.get(stem, 0) + (test_cases.get(layout_name, 0) if layout_name and layout_name != stem else 0)
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
                # The app inside the room ("" = the room's own config) and its spec folder.
                "app": entry.source.key if entry.source else "",
                "specDir": os.path.relpath(entry.source.spec_dir, self.root) if entry.source else "",
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
    folders = [f for f in project.artifact_dirs() if f.is_dir()]
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

