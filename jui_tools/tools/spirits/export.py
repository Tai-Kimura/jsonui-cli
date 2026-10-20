"""Write a skill-spirit model's .glb files from its three.js source (ticket 2026-10-21-jui-viz-skill-spirit).

    python tools/spirits/export.py MODEL_DIR --out OUT_DIR [--preview DIR] [--fps 30]

MODEL_DIR holds build.js (and spirit.json, copied as it is). build.js is an ES module that imports 'three' and
exports ``build()``, which returns:

    {spirit: Object3D,                              // optional: written as spirit.glb
     parts: [{name, object}], props: [{name, object}],  // optional: robot-<name>.glb, prop-<name>.glb
     clips: {appear: 0.6, loop: 3, leave: 0.6},      // seconds; or export `clips` beside build
     animate(t, clip)}                               // poses every root for time t of that clip

A part is built in the coordinates of where it goes (spirit.json parts[].at): a "head" part in the robot head's
own coordinates, a hand prop at the hand. animate is sampled at fps (30, or the module's FPS) into one clip per
entry of clips, with a track for each node that moves. Each root is written with three's GLTFExporter (the
vendored 0.160.0 copy in vendor/), read back with the viz page's GLTFLoader, and drawn beside what was built at
each clip's middle; the side-by-side pictures go to --preview. What glTF cannot carry stops the export with its
reason: a Sprite, a ShaderMaterial, a node that shows and hides. The spirit's see-through look is the viz page's
(spirit.json spirit.material), not the model's.

The page runs in headless Chromium (Playwright) with no server: every request is answered from this folder, the
package's vendored three and MODEL_DIR's parent (so a model can import a sibling helper as ../_x.js); anything
else is refused. The written folder is then checked as viz reads it (viz/spirits.py). Exit 1 on any problem.
"""
from __future__ import annotations

import argparse
import base64
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUI_TOOLS = HERE.parent.parent
sys.path.insert(0, str(JUI_TOOLS))

from jui_cli.viz import spirits  # noqa: E402

THREE = JUI_TOOLS / "jui_cli" / "viz" / "web" / "vendor" / "three-0.160.0"
ORIGIN = "http://spirits.invalid"
LAUNCH_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
#: a written root whose picture differs from the built one in more than this share of its pixels is a problem
MAX_DIFF = 0.005

PAGE = """<!doctype html><meta charset="utf-8">
<script type="importmap">{"imports": {"three": "/three/three.module.min.js", "three/addons/": "/three/addons/"}}</script>
<script type="module" src="/tool/export.js"></script>
"""

TYPES = {".js": "text/javascript", ".json": "application/json", ".png": "image/png", ".html": "text/html"}


def _inside(base: Path, rel: str) -> Path | None:
    path = (base / rel).resolve()
    return path if path.is_file() and (path == base or base in path.parents) else None


def resolve(url_path: str, model_dir: Path) -> Path | str | None:
    """The file (or the page's text) a request is answered with; None refuses it."""
    if url_path == "/index.html":
        return PAGE
    for prefix, base in (("/tool/", HERE), ("/model/", model_dir), ("/models/", model_dir.parent)):
        if url_path.startswith(prefix):
            return _inside(base.resolve(), url_path[len(prefix):])
    if url_path.startswith("/three/addons/exporters/") or url_path == "/three/addons/utils/TextureUtils.js":
        return _inside((HERE / "vendor").resolve(), url_path[len("/three/addons/"):])
    if url_path.startswith("/three/"):
        return _inside(THREE.resolve(), url_path[len("/three/"):])
    return None


def run_page(model_dir: Path, fps: int | None) -> dict:
    from urllib.parse import urlsplit

    from playwright.sync_api import sync_playwright

    def answer(route):
        target = resolve(urlsplit(route.request.url).path, model_dir) if route.request.url.startswith(ORIGIN + "/") else None
        if target is None:
            route.abort()
        elif isinstance(target, str):
            route.fulfill(status=200, content_type="text/html", body=target)
        else:
            route.fulfill(status=200, content_type=TYPES.get(target.suffix, "application/octet-stream"), body=target.read_bytes())

    errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=LAUNCH_ARGS)
        try:
            page = browser.new_page()
            page.on("pageerror", lambda exc: errors.append(f"page error: {exc}"))
            page.route("**/*", answer)
            page.goto(f"{ORIGIN}/index.html")
            page.wait_for_function("window.exportReady === true", timeout=30_000)
            result = page.evaluate("(o) => window.exportModel(o)", {"fps": fps})
        finally:
            browser.close()
    result["problems"] = errors + result["problems"]
    return result


def export(model_dir: Path, out: Path, preview: Path | None = None, fps: int | None = None) -> dict:
    """Writes out/ and returns {problems, report, model}: the page's problems, then the folder check's."""
    if not (model_dir / "build.js").is_file():
        return {"problems": [f"{model_dir}: no build.js"], "report": {}, "model": None}
    result = run_page(model_dir, fps)
    problems = list(result["problems"])
    for name, d in ((n, r["diffs"]) for n, r in result["report"].items()):
        for phase, diff in d.items():
            if diff > MAX_DIFF:
                problems.append(f"{name}: clip {phase} looks different once written (diff {diff:.4f}, {MAX_DIFF} at most)")
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        if old.is_file() and (old.name in (spirits.SPIRIT_GLB, spirits.SPIRIT_JSON) or spirits.PART_FILE_RE.fullmatch(old.name)):
            old.unlink()
    for name, data in result["files"].items():
        (out / name).write_bytes(base64.b64decode(data))
    if (model_dir / spirits.SPIRIT_JSON).is_file():
        shutil.copyfile(model_dir / spirits.SPIRIT_JSON, out / spirits.SPIRIT_JSON)
    if preview is not None:
        preview.mkdir(parents=True, exist_ok=True)
        for name, data in result["previews"].items():
            (preview / name).write_bytes(base64.b64decode(data))
    model = spirits.check_model(out)
    problems += model["problems"]
    return {"problems": problems, "report": result["report"], "model": model}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("model_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--preview", type=Path)
    ap.add_argument("--fps", type=int)
    args = ap.parse_args(argv)
    done = export(args.model_dir.resolve(), args.out.resolve(), args.preview, args.fps)
    for name, r in done["report"].items():
        diffs = ", ".join(f"{k} {v:.4f}" for k, v in r["diffs"].items())
        print(f"  {name}: {r['bytes']:,} bytes, clips {', '.join(r['clips']) or 'none'}; diff {diffs}")
    for p in done["problems"]:
        print(f"  problem: {p}")
    print(("OK" if not done["problems"] else "NG") + f"  {args.out}")
    return 0 if not done["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
