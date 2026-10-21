"""The spec board says implemented only what it measured (requester, 10-18).

"なんで実装全部終わってる画面も未実装みたいになってるの？" Two causes:
  * relatedFiles were looked up under the app's folder only, while a spec in a repository of several apps spells
    them from the repository root (client/acme-mobile-ios/…): 22 of 22 "missing", a finished screen at 4%.
    They now resolve as the docs validator resolves them (jsonui_project.boundary_roots).
  * every section's ✓ came from spreading the spec's one done/total over the sections top-down. Only the
    structure is measured now (the Layout's tree: there exactly when the Layout is); states, data, actions and
    transitions get no per-item mark; 分岐 comes from tests.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from jui_cli.viz.sources.jsonui_project import JsonUIProject, boundary_roots

WEB = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web" / "js"


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _repo(tmp_path: Path, *, app_is_submodule: bool = False) -> Path:
    """A repository of one app: room/{.git, jui.config.json, app/{jui.config.json, docs/screens/json/x.spec.json}}."""
    room = tmp_path / "room"
    (room / ".git").mkdir(parents=True)
    _write(room / "jui.config.json", {})
    app = room / "app"
    _write(app / "jui.config.json", {"spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts"})
    if app_is_submodule:
        _write(app / ".git", "gitdir: ../.git/modules/app\n")
    return room


def _spec(room: Path, related: list[str], layout: str | None = "x") -> Path:
    spec = {"metadata": {"name": "X"}, "relatedFiles": [{"type": "f", "path": p} for p in related]}
    if layout:
        spec["metadata"]["layoutFile"] = layout
    return _write(room / "app/docs/screens/json/x.spec.json", spec)


def _impl(room: Path) -> dict:
    project = JsonUIProject(room, "r")
    project.load_all(0)
    (item,) = project.summaries(0)
    return item["impl"]


# ---------------------------------------------------------------- where relatedFiles are


def _three_spellings(room: Path) -> list[str]:
    _write(room / "app/ios/A.swift", "")                      # spelled from the repository root
    _write(room / "app/src/B.swift", "")                      # from the app
    _write(room / "app/docs/screens/json/C.swift", "")        # next to the spec
    return ["app/ios/A.swift", "src/B.swift", "C.swift", "nowhere/D.swift"]


def test_a_related_file_is_found_from_the_repository_root_the_app_and_the_spec(tmp_path):
    room = _repo(tmp_path)
    _spec(room, _three_spellings(room), layout=None)
    assert _impl(room)["related"] == {"total": 4, "done": 3}


def test_an_app_that_is_a_submodule_still_reaches_the_repository_root(tmp_path):
    """The room spans its submodules (bar/, orders/ … each with a .git); their specs spell paths from the parent."""
    room = _repo(tmp_path, app_is_submodule=True)
    _spec(room, _three_spellings(room), layout=None)
    assert _impl(room)["related"] == {"total": 4, "done": 3}


def test_nothing_above_the_room_counts(tmp_path):
    """Even when the folder above is a checkout of its own (an outer .git): the room is the ceiling."""
    room = _repo(tmp_path)
    (tmp_path / ".git").mkdir()
    _write(tmp_path / "outside.swift", "")
    _spec(room, ["outside.swift"], layout=None)          # exists only in the folder above the room
    assert _impl(room)["related"] == {"total": 1, "done": 0}
    roots = boundary_roots(room / "app/docs/screens/json/x.spec.json", room)
    assert roots == [room / "app/docs/screens/json", room / "app", room]
    assert tmp_path in boundary_roots(room / "app/docs/screens/json/x.spec.json", tmp_path)  # the control: it is a boundary


def test_a_file_being_created_at_a_repository_root_spelling_names_its_spec(tmp_path):
    room = _repo(tmp_path)
    _spec(room, ["app/ios/New.swift"], layout=None)
    project = JsonUIProject(room, "r")
    project.load_all(0)
    assert project.specs_touching(str(room / "app/ios/New.swift")) == ["r:app/x.spec.json"]


# ---------------------------------------------------------------- the structure is the Layout


def test_the_layout_decides_the_structure(tmp_path):
    room = _repo(tmp_path)
    _spec(room, [])
    assert _impl(room)["layout"] is False
    _write(room / "app/docs/screens/layouts/x.json", {"type": "View", "id": "root"})
    assert _impl(room)["layout"] is True
    _spec(room, [], layout=None)
    assert _impl(room)["layout"] is None


# ---------------------------------------------------------------- the page: marks only where measured


def _js(expr: str) -> object:
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it)"
    core = (WEB / "20-core.js").read_text()
    live = (WEB / "30-source-live.js").read_text()
    panel = (WEB / "50-panel.js").read_text()

    def cut(src: str, name: str) -> str:
        m = re.search(rf"(?:^|\n)((?:const {name} = |function {name}\())", src)
        start = m.start(1)
        if m.group(1).startswith("function"):
            depth, i = 0, src.index("{", start)
            while True:
                depth += {"{": 1, "}": -1}.get(src[i], 0)
                if depth == 0:
                    return src[start:i + 1]
                i += 1
        return src[start:src.index(";\n", start) + 1]

    parts = [cut(core, "pct"), cut(core, "sumImpl"), cut(core, "secState"), cut(live, "SPEC_KEYS"), cut(live, "labelOf"),
             cut(live, "liveSpecRow"), cut(panel, "markOf"),
             "const LIVE = { labelOfReal: {}, specRows: {} };",
             "const tl = (k) => k;"]   # the words: the table's keys (05-i18n.js is not loaded here)
    out = subprocess.run([node, "-e", "\n".join(parts) + f"\nprocess.stdout.write(JSON.stringify({expr}));"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _row(layout, related=(22, 22)) -> str:
    sections = [{"key": k, "state": "written", "items": n} for k, n in
                [("metadata", 5), ("structure", 7), ("stateManagement", 3), ("dataFlow", 4), ("userActions", 2),
                 ("transitions", 1), ("branchContracts", 0)]]
    impl = {"total": related[1] + 1, "done": related[0] + bool(layout), "related": {"total": related[1], "done": related[0]},
            "layout": layout, "components": None}
    x = {"id": "p:x", "name": "X", "projectId": "p", "file": "x.spec.json", "sections": sections, "impl": impl,
         "tests": {"total": 0, "passed": 0, "failed": 0, "running": False}, "bucket": "partial", "updatedAt": 1}
    return f"liveSpecRow({json.dumps(x)})"


def test_with_the_layout_the_structure_is_all_marked_and_nothing_else_is():
    got = _js(f"(() => {{ const s = {_row(True)}; return {{ n: s.implN, sec: [1,2,3,4,5].map((k) => secState(s, k).kind),"
              " marks: [1,2,3,4,5].map((k) => [0,1,2].map((i) => markOf(s, {}, k, i)[0])) }; })()")
    assert got["n"][1] == 7 and got["n"][2:6] == [0, 0, 0, 0]
    assert got["sec"] == ["done", "written", "written", "written", "written"]
    assert got["marks"][0] == ["✓", "✓", "✓"]
    assert got["marks"][1:] == [["", "", ""]] * 4, "states, data, actions and transitions are not measured one by one"


def test_without_the_layout_the_structure_is_not_implemented():
    got = _js(f"(() => {{ const s = {_row(False)}; return {{ n: s.implN[1], sec: secState(s, 1), mark: markOf(s, {{}}, 1, 0)[0] }}; }})()")
    assert got["n"] == 0 and got["sec"]["kind"] == "impl" and got["mark"] == "○"
