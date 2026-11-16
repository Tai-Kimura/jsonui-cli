"""tools/spirits/export.py: a model's three.js source written as the .glb files viz reads, and the bundled models it
made. The browser runs only where Playwright and its Chromium are installed (skipped otherwise)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from jui_cli.viz import spirits

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "spirits"
BLOCKS = Path(__file__).resolve().parent / "fixtures" / "spirits" / "blocks"
BUNDLED = ROOT / "jui_cli" / "viz" / "web" / "spirits"


def load_tool():
    spec = importlib.util.spec_from_file_location("spirits_export", TOOL / "export.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("spirits_export", mod)
    spec.loader.exec_module(mod)
    return mod


def has_browser() -> bool:
    if importlib.util.find_spec("playwright") is None:
        return False
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:  # no browser installed for this Playwright
        return False


def test_the_page_is_answered_only_from_its_folders(tmp_path):
    tool = load_tool()
    model = tmp_path / "models" / "m"
    model.mkdir(parents=True)
    (model / "build.js").write_text("export function build() {}", encoding="utf-8")
    (tmp_path / "models" / "_shared.js").write_text("", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
    assert tool.resolve("/model/build.js", model) == (model / "build.js").resolve()
    assert tool.resolve("/models/_shared.js", model) == (tmp_path / "models" / "_shared.js").resolve()
    assert tool.resolve("/model/../../secret.txt", model) is None
    assert tool.resolve("/models/../secret.txt", model) is None
    assert tool.resolve("/three/three.module.min.js", model).name == "three.module.min.js"
    assert tool.resolve("/three/addons/loaders/GLTFLoader.js", model).parent.name == "loaders"
    assert tool.resolve("/three/addons/exporters/GLTFExporter.js", model) == (TOOL / "vendor" / "exporters" / "GLTFExporter.js").resolve()
    assert tool.resolve("/three/addons/utils/TextureUtils.js", model).parent.parent.name == "vendor"
    assert tool.resolve("/three/../../server.py", model) is None
    assert tool.resolve("/elsewhere.js", model) is None


def test_the_tools_exporter_is_the_three_0_160_0_copy_its_readme_records():
    import hashlib
    import re

    rows = re.findall(r"^\| `([^`]+)` \| `[^`]+` \| `([0-9a-f]{64})` \|$", (TOOL / "vendor" / "VENDOR.md").read_text(encoding="utf-8"), re.M)
    assert sorted(r for r, _ in rows) == ["exporters/GLTFExporter.js", "utils/TextureUtils.js"]
    for rel, digest in rows:
        assert hashlib.sha256((TOOL / "vendor" / rel).read_bytes()).hexdigest() == digest, rel


def test_every_bundled_model_is_ok_and_has_its_source_here():
    found = spirits.scan(BUNDLED)
    names = [m["name"] for m in found["models"]]
    assert names == ["gear-giant", "ink-scholar"] and found["skipped"] == []
    for m in found["models"]:
        assert m["ok"], (m["name"], m["problems"])
        assert m["notes"] == []
        src = TOOL / "models" / m["name"]
        assert (src / "build.js").is_file()
        # spirit.json is copied as it is by the tool
        assert (src / "spirit.json").read_bytes() == (BUNDLED / m["name"] / "spirit.json").read_bytes()
        spec = json.loads((src / "spirit.json").read_text(encoding="utf-8"))
        assert set(spec["name"]) == {"ja", "en"}
        assert m["files"]["spirit.glb"]["clips"] == ["appear", "loop", "leave"]


def test_the_bundled_models_ship_with_the_package():
    text = (ROOT / "setup.py").read_text(encoding="utf-8")
    assert '"web/spirits/*/*"' in text
    assert '"web/vendor/three-0.160.0/addons/loaders/*.js"' in text and '"web/vendor/three-0.160.0/addons/utils/*.js"' in text


@pytest.fixture(scope="module")
def browser_ok():
    if not has_browser():
        pytest.skip("Playwright with Chromium is not installed")


def test_a_model_of_boxes_and_cylinders_is_written_read_back_and_drawn_the_same(tmp_path, browser_ok):
    tool = load_tool()
    done = tool.export(BLOCKS, tmp_path / "out", tmp_path / "preview")
    assert done["problems"] == []
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["prop-stick.glb", "robot-cap.glb", "spirit.glb", "spirit.json"]
    report = done["report"]
    assert report["spirit.glb"]["clips"] == ["appear", "loop", "leave"]
    # the arm swings and the two-bone cylinder bends in the loop: both read back from the written clip
    loop = spirits.read_glb((tmp_path / "out" / "spirit.glb").read_bytes())["json"]
    channels = [a for a in loop["animations"] if a["name"] == "loop"][0]["channels"]
    nodes = {n.get("name"): i for i, n in enumerate(loop["nodes"])}
    moved = {(c["target"]["node"], c["target"]["path"]) for c in channels}
    assert (nodes["arm"], "rotation") in moved and (nodes["tailTip"], "rotation") in moved
    assert loop["skins"] and done["model"]["ok"]
    assert all(v <= tool.MAX_DIFF for r in report.values() for v in r["diffs"].values())
    assert sorted(p.name for p in (tmp_path / "preview").iterdir()) == [
        "prop-stick-loop.png", "robot-cap-loop.png", "spirit-appear.png", "spirit-leave.png", "spirit-loop.png"]


def test_what_gltf_cannot_carry_stops_the_export_with_its_reason(tmp_path, browser_ok):
    tool = load_tool()
    model = tmp_path / "models" / "bad"
    model.mkdir(parents=True)
    (model / "build.js").write_text("""
import * as THREE from 'three';
export const clips = { loop: 1 };
export function build() {
  const spirit = new THREE.Group();
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ color: 0xffffff }));
  glow.name = 'glow';
  const ghost = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.ShaderMaterial({}));
  ghost.name = 'ghost';
  const blink = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
  blink.name = 'blink';
  spirit.add(glow, ghost, blink);
  return { spirit, animate(t) { blink.visible = t < 0.5; } };
}
""", encoding="utf-8")
    problems = tool.export(model, tmp_path / "out")["problems"]
    assert any("glow is a Sprite" in p for p in problems), problems
    assert any("ghost has a ShaderMaterial" in p for p in problems), problems
    assert any("blink shows and hides in clip loop" in p for p in problems), problems
