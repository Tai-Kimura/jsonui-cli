"""`jui build` distributes each face's Layouts and Styles where that face's own tool reads them
(ticket 2026-10-23-jui-init-ios-layouts-dir-not-where-sjui-reads): `jui init` wrote iOS's
layoutsDir "Layouts" (jui distributed to ios/Layouts) while `sjui init` wrote
source_directory "<project>" (sjui read ios/<project>/Layouts), and the face was never built.
Measured with the real tools on a fresh `jui init` of all three faces; these are the rules."""
from __future__ import annotations

import json
from pathlib import Path

from jui_cli.core.platform_dirs import derive_layouts_dirs, disagreements, tool_read_dirs

# what each tool's own init writes (measured 2026-10-23 on `jui init --ios ios --android android --web web`)
SJUI = {"source_directory": "ios", "layouts_directory": "Layouts", "styles_directory": "Styles"}
KJUI = {"source_directory": "app/src/main", "layouts_directory": "assets/Layouts", "styles_directory": "assets/Styles"}
RJUI = {"layouts_directory": "src/Layouts", "styles_directory": "src/Styles"}


def _project(root: Path, sjui=SJUI, kjui=KJUI, rjui=RJUI) -> Path:
    for face, name, data in (("ios", "sjui.config.json", sjui), ("android", "kjui.config.json", kjui),
                             ("web", "rjui.config.json", rjui)):
        (root / face).mkdir(parents=True, exist_ok=True)
        if data is not None:
            (root / face / name).write_text(json.dumps(data), encoding="utf-8")
    return root


def _platforms(ios="Layouts", android="app/src/main/assets/Layouts", web="src/Layouts") -> dict:
    return {"ios": {"root": "ios", "layoutsDir": ios}, "android": {"root": "android", "layoutsDir": android},
            "web": {"root": "web", "layoutsDir": web}}


def test_what_each_tool_reads():
    assert tool_read_dirs("ios", Path("/nowhere")) is None


def test_init_takes_each_faces_layouts_dir_from_its_tool(tmp_path):
    root = _project(tmp_path)
    platforms = _platforms()
    assert derive_layouts_dirs(root, platforms) is True
    assert {p: c["layoutsDir"] for p, c in platforms.items()} == {
        "ios": "ios/Layouts", "android": "app/src/main/assets/Layouts", "web": "src/Layouts"}
    assert derive_layouts_dirs(root, platforms) is False   # once agreed, nothing to change


def test_a_face_whose_tool_did_not_run_keeps_the_default(tmp_path):
    root = _project(tmp_path, sjui=None)
    platforms = _platforms()
    assert derive_layouts_dirs(root, platforms) is False and platforms["ios"]["layoutsDir"] == "Layouts"


def test_the_build_names_a_face_whose_tool_reads_elsewhere_and_what_to_set(tmp_path):
    root = _project(tmp_path)
    problems = disagreements(root, _platforms())
    assert problems == [
        '[ios] jui build writes the layouts to ios/Layouts (jui.config.json platforms.ios.layoutsDir "Layouts"), '
        'but sjui.config.json reads ios/ios/Layouts (source_directory + layouts_directory): '
        'set platforms.ios.layoutsDir to "ios/Layouts"']   # one line: the Styles follow layoutsDir
    assert disagreements(root, _platforms(ios="ios/Layouts")) == []


def test_a_styles_folder_that_is_not_beside_the_layouts_is_named(tmp_path):
    root = _project(tmp_path, kjui={**KJUI, "styles_directory": "assets/Theme"})
    (problem,) = disagreements(root, _platforms(ios="ios/Layouts"))
    assert problem.startswith("[android] jui build writes the styles to android/app/src/main/assets/Styles")
    assert "reads android/app/src/main/assets/Theme" in problem


def test_every_face_is_checked_and_the_existing_shapes_agree(tmp_path):
    root = _project(tmp_path, kjui={**KJUI, "layouts_directory": "assets/Elsewhere"},
                    rjui={**RJUI, "layouts_directory": "app/Layouts"})
    faces = sorted(line[1:line.index("]")] for line in disagreements(root, _platforms(ios="ios/Layouts")))
    assert faces == ["android", "web"]
    # the shapes the projects on the release machine use (measured 2026-10-23: every one agreed)
    bar = _project(tmp_path / "b", sjui={**SJUI, "source_directory": "app-for-bar"})
    assert disagreements(bar, _platforms(ios="app-for-bar/Layouts")) == []


def test_jui_build_stops_before_distributing_and_says_it(tmp_path):
    """Driven, not read: `jui build` on a project whose iOS layoutsDir is the old default exits 1 at
    the check (before any layout is distributed or any platform tool runs) with the face's line."""
    import subprocess
    import sys
    root = _project(tmp_path)
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "docs/screens/layouts").mkdir(parents=True)
    (root / "docs/screens/layouts/one.json").write_text(json.dumps({"type": "View", "id": "root"}), encoding="utf-8")
    (root / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json",
                                                      "platforms": _platforms()}), encoding="utf-8")
    jui = Path(__file__).resolve().parents[1] / "bin" / "jui"
    run = subprocess.run([sys.executable, str(jui), "build"], cwd=root, capture_output=True, text=True, timeout=300)
    assert run.returncode == 1, run.stdout[-2000:] + run.stderr[-2000:]
    assert 'ERROR [platform dirs]:\n  - [ios] jui build writes the layouts to ios/Layouts' in run.stdout
    assert not (root / "ios/Layouts/one.json").exists() and not (root / "ios/ios/Layouts/one.json").exists()
