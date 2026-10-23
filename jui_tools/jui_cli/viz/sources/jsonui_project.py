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
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ...core.document_tools_import import distribution_root
from .. import quiet_fs

SECTIONS = ("metadata", "structure", "stateManagement", "dataFlow", "userActions", "transitions", "branchContracts")
#: a spec's prose in YAML (shared/core/spec_texts.py TEXTS_SUFFIX): watched, so an edit to it reads the spec again
TEXTS_SUFFIX = ".texts.yaml"
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
    if quiet_fs.is_dir(resolved):
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
        if nxt is None or not quiet_fs.is_file(nxt):
            return None
        current = nxt
    return None


def find_configs(root: Path, depth: int = SOURCE_DEPTH) -> list[Path]:
    """jui.config.json at the room's root and up to ``depth`` folders below it, root first, then by path."""
    found = [root / CONFIG_NAME] if quiet_fs.is_file(root / CONFIG_NAME) else []
    below: list[Path] = []

    def walk(folder: Path, level: int) -> None:
        if level > depth:
            return
        try:
            children = sorted(p for p in folder.iterdir() if quiet_fs.is_dir(p) and not quiet_fs.is_symlink(p))
        except OSError:
            return
        for child in children:
            if child.name in SKIP_DIRS:
                continue
            if quiet_fs.is_file(child / CONFIG_NAME):
                below.append(child / CONFIG_NAME)
            walk(child, level + 1)

    walk(root, 1)
    return found + below


def boundary_roots(spec_path: Path, ceiling: Path | None = None) -> list[Path]:
    """The folders a path a spec declares may be written from: the spec's own folder, then every declared boundary
    above it — a folder holding jui.config.json or .git — up to the nearest .git, or up to ``ceiling`` (the room's
    root) when the spec is inside it.

    ⚠️ The rule of document_tools/jsonui_doc_cli/spec_doc/validator.py ``_declared_path_roots`` (steps 2 and 3) and
    ``_boundary_roots``, which jui_cli cannot import (document_tools is reached only through the sys.path bridge).
    Each names the other; change one and change the other. In a repository of several apps a spec names files
    from the repository root (client/acme-mobile-ios/…) as well as from its app, so the app folder alone
    found none of them and a finished screen read as 4% implemented.

    One difference, deliberate: the validator stops at the nearest .git, so an app that is a submodule of the
    room's repository stops at its own; a room is the parent repository with its submodules in it (bar/,
    orders/ … each with a .git of its own), and their specs spell paths from the parent. The room's root is
    a bound the room already has, not a guess about the machine.
    """
    within = ceiling is not None and spec_path.is_relative_to(ceiling)
    roots = [spec_path.parent]
    for parent in spec_path.parents:
        if quiet_fs.is_file(parent / "jui.config.json") or quiet_fs.exists(parent / ".git"):
            if parent not in roots:
                roots.append(parent)
        if (parent == ceiling) if within else quiet_fs.exists(parent / ".git"):
            break
    return roots


def resolve_declared(value: str, roots: list[Path]) -> tuple[Path, bool]:
    """(where the declared path is, whether it exists): the first root it exists under, else the first root."""
    path = Path(value)
    if path.is_absolute():
        return path, quiet_fs.exists(path)
    for root in roots:
        if quiet_fs.exists(root / path):
            return root / path, True
    return (roots[0] / path if roots else path), False


_TEST_DIRS: list = []


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def test_dirs():
    """jsonui-test's own rules for where test files live and which one a driver's `file` names
    (test_tools/jsonui_test_cli/test_dirs.py of the distribution this jui runs from), loaded by
    path so there is one copy of them. None when the tree has no test_tools/: tests are then
    not counted, rather than counted by a second, guessed rule."""
    if not _TEST_DIRS:
        path = distribution_root() / "test_tools" / "jsonui_test_cli" / "test_dirs.py"
        module = None
        if quiet_fs.is_file(path):
            name = "_jui_viz_jsonui_test_dirs"
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
        _TEST_DIRS.append(module)
    return _TEST_DIRS[0]


@dataclass
class Source:
    """One JsonUI app in a room: where its specs, layouts and tests are."""
    key: str            # "" for the room's own config, else the app folder relative to the room ("client")
    root: Path          # the folder of the config that declares the specs
    spec_dir: Path
    layouts_dir: Path
    tests_dir: Path | None  # None: jsonui-test's rules were not found (see test_dirs())
    test_cases: dict = field(default_factory=dict)       # spec file stem / layout name -> case count
    test_file_keys: dict = field(default_factory=dict)   # "screens/login.test.json" -> spec keys
    test_file_paths: dict = field(default_factory=dict)  # the same key -> the file under the room ("tests/user/screens/login.test.json")
    android_app_id: str | None = None                    # test.artifacts.android.appId: ties a saved Android result
    # A checkout other than the room's (a git worktree a session works in, outside the room): {"branch", "worktree"};
    # the room's own app, while one of its worktrees is shown beside it: {"branch"}. None otherwise.
    checkout: dict | None = None
    base: str | None = None   # a worktree's app: the key of the room's app it is a checkout of
    # In a linked worktree (a room's app@branch, or a room that is itself a worktree): a saved result no command of
    # this server's ran is never tied to it (it is the main checkout's: ingest._saved_specs)
    linked: bool = False

    @classmethod
    def from_config(cls, key: str, config_path: Path) -> "Source":
        root = config_path.parent
        config = _read_config(config_path)

        def folder(value, default: str) -> Path:
            path = Path(value or default)
            return path if path.is_absolute() else root / path

        test_cfg = config.get("test") if isinstance(config.get("test"), dict) else {}
        artifacts = test_cfg.get("artifacts") if isinstance(test_cfg.get("artifacts"), dict) else {}
        android = artifacts.get("android") if isinstance(artifacts.get("android"), dict) else {}
        app_id = android.get("appId")
        return cls(key=key, root=root, android_app_id=app_id if isinstance(app_id, str) and app_id else None,
                   spec_dir=folder(config.get("spec_directory"), DEFAULT_SPEC_DIR),
                   layouts_dir=folder(config.get("layouts_directory"), "docs/screens/layouts"),
                   tests_dir=test_dirs().test_root(test_cfg, root) if test_dirs() else None)


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


# ---------------------------------------------------------------- the checkouts sessions work in (git worktrees)
#
# A session often works in a git worktree of a room's repository outside the room (a scratchpad, ~/…/wt/x): its
# specs reach the room's board only after a merge and a pull (ticket 2026-10-23-jui-viz-spec-board-shows-worktree-in-
# progress). The room shows them beside its own, each worktree an app of its own ("<app>@<branch>"), but only a
# worktree a session that has not ended is working in: a machine keeps many worktrees no one works in (gates, the
# integration's, a recording's). git is read, never written, and never run: the worktree list is the repository's
# own files (<git dir>/worktrees/<name>/gitdir names each worktree's .git, its HEAD its branch), as `git worktree
# list` reads them.

def git_dir(folder: Path) -> Path | None:
    """The git directory of a checkout: its .git folder, or the one a .git file points at (a worktree, a submodule)."""
    dot = folder / ".git"
    try:
        if quiet_fs.is_dir(dot):
            return dot
        if quiet_fs.is_file(dot):
            line = dot.read_text(encoding="utf-8").strip()
            if line.startswith("gitdir:"):
                target = Path(line[len("gitdir:"):].strip())
                return target if target.is_absolute() else (folder / target).resolve()
    except OSError:
        pass
    return None


def head_branch(gitdir: Path) -> str:
    """The branch a git directory's HEAD names, else its commit (8 characters); "?" when it cannot be read."""
    try:
        head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return "?"
    if head.startswith("ref: refs/heads/"):
        return head[len("ref: refs/heads/"):]
    return head[:8] if head else "?"


def repo_root(folder: Path, ceiling: Path) -> Path | None:
    """The checkout an app's folder is in: the nearest folder from it up to ``ceiling`` holding .git."""
    for candidate in (folder, *folder.parents):
        if quiet_fs.exists(candidate / ".git"):
            return candidate
        if candidate == ceiling:
            break
    return None


def worktrees(repo: Path) -> list[tuple[Path, str]]:
    """(folder, branch) of each linked worktree of a checkout's repository whose folder is still there."""
    gd = git_dir(repo)
    if gd is None:
        return []
    out = []
    try:
        admins = sorted(p for p in (gd / "worktrees").iterdir() if quiet_fs.is_dir(p))
    except OSError:
        return []
    for admin in admins:
        try:
            dot = Path((admin / "gitdir").read_text(encoding="utf-8").strip())
        except OSError:
            continue
        folder = dot.parent
        if quiet_fs.is_dir(folder):
            out.append((folder, head_branch(admin)))
    return out


def is_linked(folder: Path) -> bool:
    """Whether a folder is in a linked worktree: its checkout's .git file points into <git dir>/worktrees/<name>."""
    for candidate in (folder, *folder.parents):
        if quiet_fs.exists(candidate / ".git"):
            gd = git_dir(candidate)
            return gd is not None and gd.parent.name == "worktrees"
    return False


def _real(path: Path) -> Path:
    try:
        return Path(os.path.realpath(path))
    except OSError:
        return path


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
        for source in self.sources:
            source.linked = is_linked(source.root)
        self.base_sources = list(self.sources)   # the room's own apps; self.sources adds the worktrees shown
        self.specs: dict[str, SpecEntry] = {}
        self._layout_cache: dict[Path, tuple[int, list[dict]]] = {}
        self.test_results: dict[str, dict] = {}  # spec id -> {passed, failed, running}
        self._tests_by_name: dict[str, list[tuple[Source, str]]] | None = None  # test file name -> (app, key)

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
                if d is not None and d not in out:
                    out.append(d)
        return out

    # ---------------------------------------------------------------- the worktrees sessions work in

    def worktree_sources(self, cwds) -> list[Source]:
        """The apps of the worktrees a cwd in ``cwds`` is inside: each of the room's apps whose checkout has a linked
        worktree outside the room holding one of them, as that worktree's own app (its config at the same place in
        the worktree as the app's in the room's checkout)."""
        room = _real(self.root)
        cwds = [_real(Path(c)) for c in cwds]
        found: list[Source] = []
        seen: set[str] = set()
        for base in self.base_sources:
            repo = repo_root(base.root, self.root)
            if repo is None:
                continue
            rel = os.path.relpath(base.root, repo)
            for folder, branch in worktrees(repo):
                real = _real(folder)
                if real.is_relative_to(room) or not any(c.is_relative_to(real) for c in cwds):
                    continue
                config = folder / rel / CONFIG_NAME if rel != "." else folder / CONFIG_NAME
                if not quiet_fs.is_file(config):
                    continue
                declared = follow_extends(config) or config
                key = f"{base.key}@{branch}"
                if key in seen:
                    continue
                seen.add(key)
                source = Source.from_config(key, declared)
                source.checkout, source.base, source.linked = {"branch": branch, "worktree": str(folder)}, base.key, True
                found.append(source)
        return found

    def set_worktrees(self, cwds, at: int) -> bool:
        """Show the worktrees sessions work in (worktree_sources): a new one's specs read, a gone one's dropped, and
        each of the room's apps marked with its own branch while one of its worktrees is shown. True when the apps
        changed (the caller watches the new folders)."""
        wanted = {s.key: s for s in self.worktree_sources(cwds)}
        shown = {s.key: s for s in self.sources if s.base is not None}
        same = {k for k in wanted if k in shown and shown[k].root == wanted[k].root}
        if same == set(wanted) == set(shown):
            return False
        for key, source in shown.items():
            if key in same:
                continue
            for sid in [sid for sid, e in self.specs.items() if e.source is source]:
                del self.specs[sid]
        kept = [shown[k] for k in sorted(same)]
        added = [wanted[k] for k in sorted(wanted) if k not in same]
        with_twins = {s.base for s in kept + added}
        for base in self.base_sources:
            repo = repo_root(base.root, self.root) if base.key in with_twins else None
            gd = git_dir(repo) if repo is not None else None
            base.checkout = {"branch": head_branch(gd)} if gd is not None else None
        self.sources = self.base_sources + kept + added
        for source in added:
            if quiet_fs.is_dir(source.spec_dir):
                for path in sorted(source.spec_dir.rglob("*.spec.json")):
                    if not SKIP_DIRS.intersection(path.relative_to(source.spec_dir).parts):
                        self.reload_spec(path, at, by=None, initial=True, source=source)
        self._tests_by_name = None
        self.load_tests()
        return True

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
            if quiet_fs.is_dir(source.spec_dir):
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
        if not quiet_fs.exists(path):
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
            h = section_hash(data, key)   # the JSON as written: a texts file edited alone changes no section
            if not initial and entry.hashes.get(key) not in (None, h):
                changed.append(key)
                entry.writing_until[key] = at + WRITING_MS
            entry.hashes[key] = h
        entry.data = with_texts(data, path)
        if by:
            entry.by, entry.by_until = by, at + WRITING_MS
        return changed

    def reload_texts(self, path: Path, at: int) -> None:
        """A texts file (``*.texts.yaml``) changed: every spec of the app whose folder holds it reads its prose again
        (a reference may name a file other than its paired one, relative to the spec's folder)."""
        for entry in list(self.specs.values()):
            if entry.source is not None and path.is_relative_to(entry.source.spec_dir):
                self.reload_spec(entry.path, at, by=None, source=entry.source)

    def load_tests(self) -> None:
        """Every test file under each app's test folder (jsonui-test's rule: test.testDir, recursive)."""
        rules = test_dirs()
        # A test folder inside another app's (the room's tests/ holding the user app's tests/user): its files
        # are the inner app's only. The outer key (user/flows/x) agrees with a driver's path for longer than the
        # inner one (flows/x), so the outer app — no specs — won every saved row (10-19 ticket
        # 2026-10-19-jui-viz-saved-results-tie-to-the-outer-tests-folder).
        folders = {id(s): _resolved(s.tests_dir) for s in self.sources if s.tests_dir is not None}
        for source in self.sources:
            source.test_cases, source.test_file_keys, source.test_file_paths = {}, {}, {}
            self._tests_by_name = None
            if rules is None or source.tests_dir is None:
                continue
            mine = folders[id(source)]
            inner = [d for k, d in folders.items() if k != id(source) and d != mine and mine in d.parents]
            for path in rules.test_files(source.tests_dir):
                if inner and any(d in _resolved(path).parents for d in inner):
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(data, dict):
                    continue
                cases = data.get("cases") if isinstance(data.get("cases"), list) else []
                n = sum(1 for c in cases if isinstance(c, dict) and c.get("name"))
                keys = self._test_keys(data)
                key = path.relative_to(source.tests_dir).as_posix()
                source.test_file_keys[key] = keys
                source.test_file_paths[key] = self.room_path(path)
                for key in keys:
                    source.test_cases[key] = source.test_cases.get(key, 0) + n

    def room_path(self, path: Path) -> str:
        """A test file as a path under the room ("tests/admin/screens/x.test.json"), else its whole path."""
        full = _resolved(path)
        try:
            return full.relative_to(_resolved(self.root)).as_posix()
        except ValueError:
            return full.as_posix()

    def test_file_matches(self, name: str, only: list[Source] | None = None) -> list[tuple[Source, str]]:
        """The (app, test file) a driver's `file` names: the longest agreeing path tail, one file only
        (test_dirs.match_test_file across every candidate app's files; a tie names none). The tail is matched
        against the file's path under the room, not under its app's test folder: two apps' tests/admin/screens/x
        and tests/user/screens/x are both screens/x under their folders, and a driver's
        ../tests/admin/screens/x names one of them (10-19, the outer tests folder ticket)."""
        rules = test_dirs()
        if rules is None:
            return []
        # The rule needs at least the file name to agree, so only the files of that name are candidates
        # (a row is matched for each room; every file of every app was 2.3.1's freeze, 10-19).
        if self._tests_by_name is None:
            self._tests_by_name = {}
            for source in self.sources:
                for key, where in source.test_file_paths.items():
                    self._tests_by_name.setdefault(rules.segments(key)[-1], []).append((source, key, where))
        wanted = rules.segments(name)
        pool = [(source, key, where) for source, key, where in self._tests_by_name.get(wanted[-1] if wanted else "", ())
                if only is None or source in only]
        hit = rules.match_test_file(name, [where for _, _, where in pool])
        if hit is None:
            return []
        found = [(source, key) for source, key, where in pool if where == hit]
        return found if len(found) == 1 else []

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

    @staticmethod
    def _changed_after(at_ms: int, *paths: Path | None) -> bool:
        for path in paths:
            try:
                if path is not None and path.stat().st_mtime * 1000 > at_ms:
                    return True
            except OSError:
                pass
        return False

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

    def _roots(self, source: Source | None, spec_path: Path | None) -> list[Path]:
        if spec_path is not None:
            return boundary_roots(spec_path, self.root)
        return [source.root] if source else [self.root]

    def layout_path(self, spec: dict, source: Source | None = None, spec_path: Path | None = None) -> Path | None:
        """The Layout file a spec names: under the declared layouts folder first, then as relatedFiles are (the
        validator's ``_declared_path_roots("layout")``)."""
        meta = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
        name = meta.get("layoutFile")
        source = self._source(source)
        if not isinstance(name, str) or not name or source is None:
            return None
        name = name if name.endswith(".json") else f"{name}.json"
        roots = [source.layouts_dir] + (boundary_roots(spec_path, self.root) if spec_path is not None else [])
        return resolve_declared(name, roots)[0]

    def related_paths(self, spec: dict, source: Source | None = None, spec_path: Path | None = None) -> list[Path]:
        roots = self._roots(self._source(source), spec_path)
        return [resolve_declared(item["path"], roots)[0] for item in spec.get("relatedFiles") or []
                if isinstance(item, dict) and isinstance(item.get("path"), str)]

    def specs_touching(self, file_path: str) -> list[str]:
        """Spec ids a file edit belongs to: the spec itself, its Layout, its relatedFiles."""
        target = Path(file_path)
        hits = []
        for sid, entry in self.specs.items():
            if target == entry.path:
                hits.append(sid)
                continue
            data = entry.data or {}
            lp = self.layout_path(data, entry.source, entry.path)
            # Every place a relatedFile may be written from: a file being created does not exist anywhere yet.
            roots = self._roots(self._source(entry.source), entry.path)
            declared = [Path(item["path"]) for item in data.get("relatedFiles") or []
                        if isinstance(item, dict) and isinstance(item.get("path"), str)]
            if (lp and target == lp) or any(target == (d if d.is_absolute() else r / d) for d in declared for r in roots):
                hits.append(sid)
        return hits

    def impl(self, spec: dict, source: Source | None = None, spec_path: Path | None = None) -> dict:
        """What can be measured about a spec's implementation, and its sum.

        related     relatedFiles that exist / all
        layout      whether the Layout file exists (None: the spec names none)
        components  listed component ids found in the Layout / all (None: the spec lists none — the usual case,
                    where the structure IS the Layout, so it is implemented exactly when the Layout exists)
        total/done  the sum of the three, for the bucket and the status line
        Nothing here measures a state, a data-flow item, a user action or a transition one by one: the inputs say
        nothing about them, and the board says so instead of guessing.
        """
        related = [quiet_fs.exists(p) for p in self.related_paths(spec, source, spec_path)]
        lp = self.layout_path(spec, source, spec_path)
        layout = None if lp is None else quiet_fs.exists(lp)
        ids = component_ids(spec)
        components = None
        if ids:
            present = self.layout_ids_cached(lp) if lp else set()
            components = {"total": len(ids), "done": sum(1 for i in ids if i in present)}
        total = len(related) + (layout is not None) + (components["total"] if components else 0)
        done = sum(related) + bool(layout) + (components["done"] if components else 0)
        return {"total": total, "done": done, "related": {"total": len(related), "done": sum(related)},
                "layout": layout, "components": components}

    def specs_for_test_file(self, rel: str, only: list[Source] | None = None) -> list[str]:
        """Spec ids a test file belongs to, *rel* as a driver names it (any of the three spellings).
        *only*: the apps a saved result was tied to (none of the others is a candidate)."""
        matched = self.test_file_matches(rel, only)
        owners = [source for source, _ in matched]
        if only is not None and not owners:
            return []
        if matched:
            source, key = matched[0]
            keys = set(source.test_file_keys[key])
        else:  # no app has this test file: every app, by the file's name
            keys = set()
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
            nodes = len(self.layout_nodes_cached(self.layout_path(data, entry.source, entry.path)))
            for key in SECTIONS:
                items = section_items(data, key, nodes)
                writing = entry.writing_until.get(key, 0) > at or (entry.broken and entry.by_until > at)
                state = "writing" if writing else ("written" if items else "empty")
                sections.append({"key": key, "state": state, "items": items})
            impl = self.impl(data, entry.source, entry.path)
            layout = self.layout_path(data, entry.source, entry.path)
            layout_name = meta.get("layoutFile") if isinstance(meta.get("layoutFile"), str) else None
            test_cases = entry.source.test_cases if entry.source else {}
            cases = test_cases.get(stem, 0) + (test_cases.get(layout_name, 0) if layout_name and layout_name != stem else 0)
            result = self.test_results.get(sid, {})
            # what a done spec has passed: its test cases, and as many as its branches (requester 10-23: 「分岐も全部で
            # 完了」); the bucket, the 分岐 tab and every list say the same count (needed)
            needed = max(cases, section_items(data, "branchContracts", nodes))
            tests = {"total": cases, "needed": needed, "passed": result.get("passed", 0), "failed": result.get("failed", 0),
                     "running": bool(result.get("running"))}
            if result.get("latest"):
                tests["at"] = result["latest"]
                # mtime moves on a git checkout too, so this can only say "may be stale" (10-18).
                if self._changed_after(result["latest"], entry.path, layout):
                    tests["maybeStale"] = True
            by = entry.by if entry.by_until > at else None
            written_any = any(s["items"] for s in sections)
            impl_done = impl["total"] > 0 and impl["done"] == impl["total"]
            tests_done = cases > 0 and tests["passed"] >= needed and not tests["failed"]   # a test file of its own, as before
            bucket = "live" if by else "todo" if not written_any else "done" if impl_done and tests_done else "partial"
            # a worktree's spec is named from the worktree's folder (its rows say the branch; ../../ from the room
            # would only say where the scratchpad is)
            base_dir = Path(entry.source.checkout["worktree"]) if entry.source and entry.source.checkout and entry.source.checkout.get("worktree") else self.root
            item = {
                "id": sid, "projectId": self.project_id,
                # The app inside the room ("" = the room's own config) and its spec folder.
                "app": entry.source.key if entry.source else "",
                # the checkout it is read from, when the room shows a worktree of its app (Source.checkout)
                **({"checkout": _checkout_view(entry.source.checkout)} if entry.source and entry.source.checkout else {}),
                "specDir": os.path.relpath(entry.source.spec_dir, base_dir) if entry.source else "",
                "name": meta.get("displayName") or meta.get("name") or stem,
                "file": os.path.relpath(entry.path, base_dir),
                "sections": sections, "impl": impl, "tests": tests, "bucket": bucket,
                "updatedAt": at,
                # when it last moved on (ticket 2026-10-23-viz-spec-list-not-recent-first): the newest of the spec's
                # write, its Layout's write and its newest test result; the lists put the newest first
                **_advanced(_mtime_ms(entry.path), _mtime_ms(layout), result.get("lastAt") or 0),
            }
            if by:
                item["by"] = by
            out.append(item)
        return out


def _checkout_view(checkout: dict) -> dict:
    """A checkout for the page: its branch, and a worktree's folder with the home folder as ~."""
    from ..rooms import tilde
    return {"branch": checkout["branch"], **({"worktree": tilde(checkout["worktree"])} if checkout.get("worktree") else {})}


def _mtime_ms(path: Path | None) -> int:
    try:
        return int(path.stat().st_mtime * 1000) if path is not None else 0
    except OSError:
        return 0


def _advanced(spec: int, layout: int, test: int) -> dict:
    """advancedAt and what moved it (advancedBy: spec / layout / test), for the lists' order and the time beside each
    spec's share (ticket 2026-10-23-viz-spec-no-last-updated-time). A tie names the first of spec, layout, test."""
    at, by = max((spec, "spec"), (layout, "layout"), (test, "test"), key=lambda x: x[0])
    return {"advancedAt": at, "advancedBy": by} if at else {"advancedAt": 0}


def with_texts(data: dict, path: Path) -> dict:
    """``data`` with its ``{"md": ...}`` prose read from the texts file (shared/core/spec_texts.py), as every other
    reader of a spec does (ticket 2026-10-23-viz-spec-sheet-shows-md-reference-raw). One it cannot read stays a
    reference, and the sheet says so; without shared/core the spec is kept as written."""
    from ...core import shared_core
    texts = shared_core.load("spec_texts")
    if texts is None:
        return data
    try:
        return texts.resolve_spec_texts(data, path).data
    except Exception:   # a texts file the resolver refuses outright (no PyYAML): the references stay, named on the sheet
        return data


def watch(project: JsonUIProject, on_change):
    """watchdog on the project's spec, layout and test folders; on_change(path) per file event.

    Returns the observer (call .stop() / .join()), or None when none of the
    folders exist. Folders in SKIP_DIRS are ignored.
    """
    from .. import data_docs
    folders = [f for f in project.artifact_dirs() if quiet_fs.is_dir(f)]
    folders += [d for _k, d, _r in data_docs.doc_dirs(project) if d not in folders]   # the data server's (2.3.5)
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
            if not path.endswith((".json", TEXTS_SUFFIX)) or SKIP_DIRS.intersection(Path(path).parts):
                return
            on_change(path)

    observer = Observer()
    for folder in folders:
        observer.schedule(Handler(), str(folder), recursive=True)
    observer.daemon = True
    observer.start()
    return observer

