"""jui viz reads the specs of every JsonUI app in a room, not only the root config's.

A room's root is the nearest jui.config.json above the session's cwd. In a
repo whose top config carries only the docs contract checks, each app below
it (client/, admin/, …) declares its own spec_directory, and the spec board
showed 0 screens. Every expected count here is derived from the files the
test itself writes, never from a real repo's numbers.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path

from jui_cli.viz.sources import jsonui_project as jp
from jui_cli.viz.sources.jsonui_project import JsonUIProject, discover_sources, follow_extends

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_CONFIG = REPO_ROOT / "document_tools" / "jsonui_doc_cli" / "project_config.py"


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _specs(folder: Path, names: list[str]) -> list[str]:
    for name in names:
        _write(folder / f"{name}.spec.json", {"metadata": {"name": name, "layoutFile": name}})
    return names


def _loaded(root: Path) -> JsonUIProject:
    project = JsonUIProject(root, "room")
    project.load_all(0)
    return project


def _bounded(fn, seconds: float = 10):
    """fn() in a thread; fails rather than hangs when the search never ends."""
    out: list = []
    worker = threading.Thread(target=lambda: out.append(fn()), daemon=True)
    worker.start()
    worker.join(seconds)
    assert not worker.is_alive(), "the search did not end"
    return out[0]


def _by_app(project: JsonUIProject) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in project.summaries(0):
        out[item["app"]] = out.get(item["app"], 0) + 1
    return out


def test_a_root_without_spec_directory_reads_its_apps(tmp_path):
    _write(tmp_path / "jui.config.json", {"checks": []})
    client = _specs(tmp_path / "client/docs/screens/json", ["home", "cart", "order"])
    admin = _specs(tmp_path / "admin/specs", ["users", "audit"])
    _write(tmp_path / "client/jui.config.json", {"spec_directory": "docs/screens/json"})
    _write(tmp_path / "admin/jui.config.json", {"spec_directory": "specs"})

    project = _loaded(tmp_path)

    assert _by_app(project) == {"client": len(client), "admin": len(admin)}
    assert len(project.specs) == len(client) + len(admin)
    ids = {item["id"] for item in project.summaries(0)}
    assert "room:client/home.spec.json" in ids and "room:admin/users.spec.json" in ids


def test_each_app_reads_its_own_layouts_and_tests(tmp_path):
    _write(tmp_path / "jui.config.json", {})
    _specs(tmp_path / "app/docs/screens/json", ["login"])
    _write(tmp_path / "app/jui.config.json", {"spec_directory": "docs/screens/json",
                                              "layouts_directory": "ui", "test": {"testDir": "qa"}})
    _write(tmp_path / "app/ui/login.json", {"type": "View", "id": "root", "child": [{"type": "Label", "id": "t"}]})
    _write(tmp_path / "app/qa/screens/login.test.json", {"source": {"layout": "ui/login.json"},
                                                          "cases": [{"name": "a"}, {"name": "b"}]})

    item = _loaded(tmp_path).summaries(0)[0]

    assert item["impl"] == {"total": 1, "done": 1}  # the Layout under app/ui exists
    assert item["tests"]["total"] == 2
    assert next(s for s in item["sections"] if s["key"] == "structure")["items"] == 2


def test_a_signpost_and_its_target_on_one_folder_count_once(tmp_path):
    _write(tmp_path / "jui.config.json", {})
    names = _specs(tmp_path / "docs/admin/screens/json", ["a", "b"])
    _write(tmp_path / "admin/jui.config.json", {"spec_directory": "../docs/admin/screens/json"})
    # The signpost names the target as a folder, the form that needs jui.config.json completed.
    _write(tmp_path / "docs/admin/jui.config.json", {"extends": "../../admin"})

    project = _loaded(tmp_path)

    assert _by_app(project) == {"admin": len(names)}
    assert [s.key for s in project.sources if s.key] == ["admin"]


def test_a_signpost_reaches_an_app_beyond_the_search_depth(tmp_path):
    _write(tmp_path / "jui.config.json", {})
    deep = tmp_path / "x" / "y" / "z" / "w" / "app"
    names = _specs(deep / "s", ["one"])
    _write(deep / "jui.config.json", {"spec_directory": "s"})
    _write(tmp_path / "docs/app/jui.config.json", {"extends": "../../x/y/z/w/app/jui.config.json"})
    assert len(deep.relative_to(tmp_path).parts) > jp.SOURCE_DEPTH  # only the signpost leads there

    assert len(_loaded(tmp_path).specs) == len(names)


def test_configs_under_node_modules_are_not_apps(tmp_path):
    _write(tmp_path / "jui.config.json", {})
    real = _specs(tmp_path / "web/docs/screens/json", ["page"])
    _write(tmp_path / "web/jui.config.json", {"spec_directory": "docs/screens/json"})
    _specs(tmp_path / "web/node_modules/pkg/docs/screens/json", ["vendored"])
    _write(tmp_path / "web/node_modules/pkg/jui.config.json", {"spec_directory": "docs/screens/json"})

    assert _by_app(_loaded(tmp_path)) == {"web": len(real)}


def test_an_extends_cycle_ends_the_search(tmp_path):
    _write(tmp_path / "jui.config.json", {})
    _write(tmp_path / "a/jui.config.json", {"extends": "../b"})
    _write(tmp_path / "b/jui.config.json", {"extends": "../a"})
    found = _bounded(lambda: discover_sources(tmp_path))

    assert [s.key for s in found] == [""]  # only the room's own config


def test_the_root_config_that_declares_specs_is_read_as_before(tmp_path):
    root_specs = _specs(tmp_path / "docs/screens/json", ["top"])
    _write(tmp_path / "jui.config.json", {"spec_directory": "docs/screens/json"})
    sub = _specs(tmp_path / "sub/docs/screens/json", ["inner"])
    _write(tmp_path / "sub/jui.config.json", {"spec_directory": "docs/screens/json"})

    project = _loaded(tmp_path)

    assert _by_app(project) == {"": len(root_specs), "sub": len(sub)}
    assert "room:top.spec.json" in project.specs  # the id it always had


def _doc_tools():
    spec = importlib.util.spec_from_file_location("_viz_test_project_config", PROJECT_CONFIG)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up while it loads
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_extends_follows_the_same_rules_as_document_tools(tmp_path):
    """Both copies run on the same trees: a file, a folder, a broken target, a cycle, and the hop limit."""
    doc = _doc_tools()
    assert doc._MAX_EXTENDS_HOPS == jp.MAX_EXTENDS_HOPS
    _write(tmp_path / "real/jui.config.json", {"spec_directory": "s"})
    cases = {
        "file": {"extends": "../real/jui.config.json"},
        "folder": {"extends": "../real"},
        "broken": {"extends": "../missing"},
        "none": {"layouts_directory": "l"},
        "declares": {"spec_directory": "here"},
    }
    starts = [_write(tmp_path / name / "jui.config.json", body) for name, body in cases.items()]
    _write(tmp_path / "c1/jui.config.json", {"extends": "../c2"})
    _write(tmp_path / "c2/jui.config.json", {"extends": "../c1"})
    starts.append(tmp_path / "c1/jui.config.json")
    # A chain of h hops ends on the declaring config: the limit is crossed between 4 and 5.
    for hops in (jp.MAX_EXTENDS_HOPS, jp.MAX_EXTENDS_HOPS + 1):
        _write(tmp_path / f"h{hops}_{hops}/jui.config.json", {"spec_directory": "s"})
        for k in range(hops):
            _write(tmp_path / f"h{hops}_{k}/jui.config.json", {"extends": f"../h{hops}_{k + 1}"})
        starts.append(tmp_path / f"h{hops}_0/jui.config.json")

    ours = _bounded(lambda: [follow_extends(s.resolve()) for s in starts])
    theirs = [doc._follow_extends(s.resolve())[0] for s in starts]

    assert ours == theirs
    assert [p is not None for p in ours] == [True, True, False, False, True, False, True, False]
