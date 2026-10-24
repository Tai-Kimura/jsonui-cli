"""A worktree's spec beside the spec it started from (2.3.23, ticket 2026-10-24-viz-worktree-spec-diff-against-base;
requester: 「ベースとの差分を見るボタンつけて、押したら全画面で、左にもとで右に変更点でわかりやすく表示」).

The base ("元") is where the worktree's branch left its parent: ``git merge-base HEAD <the room's checkout's HEAD>``
(ruled 10-24: 分かれた所). The right side is what the board reads now, uncommitted edits included.

Both sides go through the sheet's own reader (sheet.build_doc, with the texts file and the Layout file read at the
same commit for the left), so a row is compared as the sheet shows it, and rows are paired per section by their key
(a component's id, a variable's or a method's name, an API's method and path, ...): same / added / removed / changed.

git: run only when the page asks (the two buttons: one spec, and a worktree's whole list), read-only, the way
gitbox._git runs it (GIT_OPTIONAL_LOCKS=0, 3 seconds) — the one place the viz runs git for a worktree; the worktree
list itself is still read from git's files (sources/jsonui_project.py). Unlike gitbox it does not go quiet on a
failure: the page says why the base could not be read. What is read at a base commit is cached by the commit's SHA.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from . import sheet as sheet_mod
from .sources import jsonui_project as jp

GIT_TIMEOUT_SEC = 3
#: the sections compared, in the sheet's order; each row's key (rows with no key, or a key met twice, pair by order)
SECTION_KEYS = {
    "metadata": lambda r: r[0],
    "components": lambda r: r[1] or None,
    "uiVariables": lambda r: r[0],
    "eventHandlers": lambda r: r[0],
    "vmMethods": lambda r: r,
    "vmVars": lambda r: r,
    "repositories": lambda r: r,
    "apis": lambda r: f"{r[1]} {r[2]}",
    "userActions": lambda r: r[0],
    "transitions": lambda r: r[0],
    "branches": lambda r: f"{r[0]}|{_j(r[1])}",
    "flowMermaid": lambda r: "flow",
}
METADATA_ROWS = ("name", "displayName", "description", "platforms", "layoutFile")
#: a worktree's whole list compares at most this many specs (a mark each); the rest are listed unmarked
LIST_MAX = 300


class BaseUnavailable(Exception):
    """The base could not be read; ``reason`` is the page's key, ``detail`` git's own words when there are any."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


def _j(v) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)


# ---------------------------------------------------------------- git, read-only

def _git(folder: Path, *args: str) -> str:
    """git, read-only, in folder: its stdout; BaseUnavailable on a failure, with git's first line of stderr."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C"}
    try:
        done = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True,
                              timeout=GIT_TIMEOUT_SEC, env=env, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise BaseUnavailable("git-missing") from None
    except subprocess.TimeoutExpired:
        raise BaseUnavailable("timeout", f"git {args[0]}") from None
    except (OSError, subprocess.SubprocessError) as e:
        raise BaseUnavailable("git-failed", str(e)) from None
    if done.returncode != 0:
        raise BaseUnavailable("git-failed", (done.stderr.strip().splitlines() or [""])[0])
    return done.stdout


def parent_head(room_repo: Path) -> str:
    """What the room's checkout has checked out, as a commit-ish the worktree can name: its branch's ref (the
    worktrees of one repository share its refs), or the commit of a detached HEAD."""
    gd = jp.git_dir(room_repo)
    try:
        head = (gd / "HEAD").read_text(encoding="utf-8").strip() if gd is not None else ""
    except OSError:
        head = ""
    if head.startswith("ref: "):
        return head[len("ref: "):]
    if len(head) >= 7 and all(c in "0123456789abcdef" for c in head):
        return head
    raise BaseUnavailable("no-parent-head")


def base_commit(worktree: Path, room_repo: Path) -> str:
    """The commit the worktree's branch left the room's checkout at."""
    parent = parent_head(room_repo)
    try:
        out = _git(worktree, "merge-base", "HEAD", parent).strip()
    except BaseUnavailable as e:
        if e.reason == "git-failed":
            raise BaseUnavailable("no-merge-base", e.detail) from None
        raise
    if not out:
        raise BaseUnavailable("no-merge-base")
    return out


def show(worktree: Path, sha: str, rel: str) -> str | None:
    """A file's text at a commit; None when the commit has no such file."""
    try:
        return _git(worktree, "show", f"{sha}:{rel}")
    except BaseUnavailable as e:
        if e.reason == "git-failed" and ("does not exist in" in e.detail or "exists on disk, but not in" in e.detail):
            return None
        raise


def spec_files(worktree: Path, sha: str, spec_dir_rel: str) -> list[str]:
    """The spec files (*.spec.json) under a folder at a commit, as paths in the repository."""
    out = _git(worktree, "ls-tree", "-r", "--name-only", sha, "--", spec_dir_rel)
    return [line for line in out.splitlines() if line.endswith(".spec.json")
            and not jp.SKIP_DIRS.intersection(Path(line).parts)]


# ---------------------------------------------------------------- one side's doc

def _md_targets(value) -> list[str]:
    out = []
    if isinstance(value, dict):
        if set(value) == {"md"} and isinstance(value["md"], str):
            return [value["md"]]
        for v in value.values():
            out += _md_targets(v)
    elif isinstance(value, list):
        for v in value:
            out += _md_targets(v)
    return out


def _doc(data: dict, layout_text: str | None) -> dict:
    nodes: list[dict] = []
    if layout_text is not None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "layout.json"
            p.write_text(layout_text, encoding="utf-8")
            nodes = jp.layout_nodes(p)
    return sheet_mod.build_doc(data, nodes, [], {"total": 0, "done": 0})


_BASE_CACHE: dict[tuple[str, str, str], dict | None] = {}


def base_doc(worktree: Path, sha: str, spec_rel: str, layouts_rel: str) -> dict | None:
    """The sheet's doc of a spec at the base commit, its prose and its Layout read at the same commit; None when the
    commit has no such spec. Cached by (commit, spec, layouts folder): a commit does not change."""
    key = (sha, spec_rel, layouts_rel)
    if key in _BASE_CACHE:
        return _BASE_CACHE[key]
    text = show(worktree, sha, spec_rel)
    if text is None:
        _BASE_CACHE[key] = None
        return None
    try:
        data = json.loads(text)
    except ValueError as e:
        raise BaseUnavailable("base-unreadable", str(e)) from None
    if not isinstance(data, dict):
        raise BaseUnavailable("base-unreadable")
    from ..core import shared_core
    texts = shared_core.load("spec_texts")
    if texts is not None:
        spec_dir = Path(spec_rel).parent
        wanted = {str(texts.paired_texts_path(Path(spec_rel)))}
        for target in _md_targets(data):
            if "#" in target:
                wanted.add(os.path.normpath(str(spec_dir / target.split("#", 1)[0])))
        with tempfile.TemporaryDirectory() as tmp:
            for rel in sorted(wanted):
                body = show(worktree, sha, rel)
                if body is not None:
                    dest = Path(tmp) / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(body, encoding="utf-8")
            data = jp.with_texts(data, Path(tmp) / spec_rel)
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    name = meta.get("layoutFile")
    layout = None
    if isinstance(name, str) and name:
        layout = show(worktree, sha, f"{layouts_rel}/{name if name.endswith('.json') else name + '.json'}")
    doc = _doc(data, layout)
    _BASE_CACHE[key] = doc
    return doc


# ---------------------------------------------------------------- pairing the rows

def _rows(doc: dict | None, section: str) -> list:
    if doc is None:
        return []
    if section == "metadata":
        meta = doc.get("metadata") or {}
        return [[f, meta.get(f)] for f in METADATA_ROWS if meta.get(f) not in (None, "", [])]
    if section == "flowMermaid":
        return [[doc["flowMermaid"]]] if doc.get("flowMermaid") else []
    rows = doc.get(section)
    return rows if isinstance(rows, list) else []


def _keys(rows: list, section: str) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for r in rows:
        try:
            k = SECTION_KEYS[section](r)
        except (IndexError, TypeError, KeyError):
            k = None
        k = _j(r) if k is None else str(k)
        n = seen.get(k, 0)
        seen[k] = n + 1
        out.append(f"{k}\x00{n}")
    return out


def _lcs(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    n, m = len(a), len(b)
    t = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            t[i][j] = t[i + 1][j + 1] + 1 if a[i] == b[j] else max(t[i + 1][j], t[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] == b[j]:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif t[i + 1][j] >= t[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def _changed_cols(left, right) -> list[int]:
    if isinstance(left, list) and isinstance(right, list):
        return [k for k in range(max(len(left), len(right)))
                if _j(left[k] if k < len(left) else None) != _j(right[k] if k < len(right) else None)]
    return [0]


def diff_section(left_rows: list, right_rows: list, section: str) -> dict:
    """The rows of one section, paired: [{s: same|add|del|chg, l, r, cols}] in the order of both sides, and counts."""
    pairs = _lcs(_keys(left_rows, section), _keys(right_rows, section))
    rows, i, j = [], 0, 0

    def flush(to_i, to_j):
        nonlocal i, j
        while i < to_i:
            rows.append({"s": "del", "l": left_rows[i], "r": None})
            i += 1
        while j < to_j:
            rows.append({"s": "add", "l": None, "r": right_rows[j]})
            j += 1

    for pi, pj in pairs:
        flush(pi, pj)
        left, right = left_rows[pi], right_rows[pj]
        if _j(left) == _j(right):
            rows.append({"s": "same", "l": left, "r": right})
        else:
            rows.append({"s": "chg", "l": left, "r": right, "cols": _changed_cols(left, right)})
        i, j = pi + 1, pj + 1
    flush(len(left_rows), len(right_rows))
    counts = {s: sum(1 for r in rows if r["s"] == s) for s in ("add", "del", "chg")}
    return {"key": section, "rows": rows, "counts": counts}


def diff_docs(left: dict | None, right: dict | None) -> dict:
    sections = [diff_section(_rows(left, k), _rows(right, k), k) for k in SECTION_KEYS]
    total = {s: sum(sec["counts"][s] for sec in sections) for s in ("add", "del", "chg")}
    return {"sections": sections, "counts": total}


# ---------------------------------------------------------------- what the page asks

def _where(project, source) -> tuple[Path, Path]:
    """(the worktree's folder, the room's checkout it is a worktree of) for a worktree's app."""
    if source is None or not source.checkout or not source.checkout.get("worktree"):
        raise BaseUnavailable("not-a-worktree")
    base = next((s for s in project.base_sources if s.key == source.base), None)
    room_repo = jp.repo_root(base.root, project.root) if base is not None else None
    if room_repo is None:
        raise BaseUnavailable("no-parent-head")
    return Path(source.checkout["worktree"]), room_repo


def _rel(path: Path, folder: Path) -> str:
    return Path(os.path.relpath(path, folder)).as_posix()


def _right_doc(project, entry) -> dict | None:
    if entry.data is None:
        return None
    nodes = project.layout_nodes_cached(project.layout_path(entry.data, entry.source, entry.path))
    return sheet_mod.build_doc(entry.data, nodes, [], {"total": 0, "done": 0})


def spec_diff(project, spec_id: str | None = None, *, app: str | None = None, deleted: str | None = None) -> dict:
    """One spec of a worktree beside its base: {ok, base, file, isNew, isDeleted, sections, counts}, or {ok: False,
    reason, detail}. A spec the worktree deleted is named by its app and its path in the repository."""
    try:
        if deleted is not None:
            source = next((s for s in project.sources if s.key == app), None)
            worktree, room_repo = _where(project, source)
            sha = base_commit(worktree, room_repo)
            left = base_doc(worktree, sha, deleted, _rel(source.layouts_dir, worktree))
            if left is None:
                raise BaseUnavailable("no-such-base-file")
            return {"ok": True, "base": sha, "file": deleted, "isNew": False, "isDeleted": True, **diff_docs(left, None)}
        entry = project.specs.get(spec_id)
        if entry is None:
            raise BaseUnavailable("unknown-spec")
        worktree, room_repo = _where(project, entry.source)
        sha = base_commit(worktree, room_repo)
        rel = _rel(entry.path, worktree)
        left = base_doc(worktree, sha, rel, _rel(entry.source.layouts_dir, worktree))
        right = _right_doc(project, entry)
        if right is None:
            raise BaseUnavailable("worktree-unreadable")
        return {"ok": True, "base": sha, "file": rel, "isNew": left is None, "isDeleted": False, **diff_docs(left, right)}
    except BaseUnavailable as e:
        return {"ok": False, "reason": e.reason, "detail": e.detail}


def list_diff(project, app: str) -> dict:
    """A worktree's whole list against its base: {ok, base, marks: {specId: {add, del, chg, isNew}}, deleted: [{file,
    name}]}, or {ok: False, reason, detail}."""
    try:
        source = next((s for s in project.sources if s.key == app), None)
        worktree, room_repo = _where(project, source)
        sha = base_commit(worktree, room_repo)
        layouts_rel = _rel(source.layouts_dir, worktree)
        in_base = set(spec_files(worktree, sha, _rel(source.spec_dir, worktree)))
        marks, now = {}, set()
        entries = sorted(((sid, e) for sid, e in project.specs.items() if e.source is source), key=lambda x: str(x[1].path))
        for sid, entry in entries[:LIST_MAX]:
            rel = _rel(entry.path, worktree)
            now.add(rel)
            if rel not in in_base:
                marks[sid] = {"add": 0, "del": 0, "chg": 0, "isNew": True}
                continue
            right = _right_doc(project, entry)
            if right is None:
                continue
            marks[sid] = {**diff_docs(base_doc(worktree, sha, rel, layouts_rel), right)["counts"], "isNew": False}
        now |= {_rel(e.path, worktree) for _, e in entries[LIST_MAX:]}
        deleted = []
        for rel in sorted(in_base - now):
            doc = base_doc(worktree, sha, rel, layouts_rel)
            meta = (doc or {}).get("metadata") or {}
            deleted.append({"file": rel, "name": meta.get("displayName") or meta.get("name") or Path(rel).name})
        return {"ok": True, "base": sha, "marks": marks, "deleted": deleted}
    except BaseUnavailable as e:
        return {"ok": False, "reason": e.reason, "detail": e.detail}
