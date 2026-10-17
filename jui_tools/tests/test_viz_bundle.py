"""jui viz: /app.js assembly (jui_cli/viz/bundle.py) and the shipped web files (jui_cli/viz/web/).

The browser behaviour itself is checked outside pytest (tools/viz_e2e/, plan 10 §6); these arms pin what can be
read without a browser: the parts and their order per mode, the e2e hook only on request, the page's CSP shape
(no inline script but the import map, no on* attributes), nothing fetched from outside, and the vendored files
still being the ones VENDOR.md records.
"""

from __future__ import annotations

import hashlib
import re
from importlib import resources

import pytest

from jui_cli.viz import bundle

WEB = resources.files("jui_cli.viz").joinpath("web")


def web_text(*parts):
    return WEB.joinpath(*parts).read_text(encoding="utf-8")


def test_each_mode_is_its_parts_in_order():
    assert bundle.parts("demo", e2e=False) == ("10-robot-core.js", "20-core.js", "30-source-demo.js",
                                               "40-scene.js", "50-panel.js", "60-log.js", "70-main.js")
    assert bundle.parts("live", e2e=False) == ("10-robot-core.js", "20-core.js", "25-net.js", "30-source-live.js",
                                               "40-scene.js", "50-panel.js", "60-log.js", "70-main.js")


def test_build_joins_the_parts_in_that_order_with_a_marker_each():
    for mode in bundle.MODES:
        js = bundle.build(mode, e2e=False)
        marks = re.findall(r"^// ---- web/js/(\S+) ----$", js, re.M)
        assert tuple(marks) == bundle.parts(mode, e2e=False)
        for name in marks:
            assert web_text("js", name) in js


def test_the_demo_has_no_socket_and_the_live_view_no_script():
    demo, live = bundle.build("demo", e2e=False), bundle.build("live", e2e=False)
    assert "new WebSocket(" not in demo and "new WebSocket(" in live
    # The demo script's own names (its loop, its still states) stay out of the live bundle.
    for name in ("const LOOP = 84", "const STILL = {", "function computeSpecs("):
        assert name in demo and name not in live


def test_the_e2e_hook_is_appended_only_when_asked():
    assert "window.__dbg" not in bundle.build("live", e2e=False)
    assert "window.__dbg" not in bundle.build("demo", e2e=False)
    for mode in bundle.MODES:
        assert bundle.build(mode, e2e=True).rstrip().endswith(web_text("js", "80-dbg.js").rstrip())


def test_the_environment_decides_by_default(monkeypatch):
    monkeypatch.delenv("JUI_VIZ_E2E", raising=False)
    assert "window.__dbg" not in bundle.build("demo")
    monkeypatch.setenv("JUI_VIZ_E2E", "1")
    assert "window.__dbg" in bundle.build("demo")
    monkeypatch.setenv("JUI_VIZ_E2E", "0")  # only "1" turns it on
    assert "window.__dbg" not in bundle.build("demo")
    assert bundle.dev_enabled({"JUI_VIZ_DEV": "1"}) and not bundle.dev_enabled({})


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="unknown mode 'debug'"):
        bundle.build("debug")


def test_every_part_is_read_from_the_package_not_the_checkout():
    for mode in bundle.MODES:
        for name in bundle.parts(mode, e2e=True):
            assert WEB.joinpath("js", name).is_file(), name


# ---- the page and its CSP (plan 05 §4, plan 07 §6) ----------------------------------------------------------

def test_the_page_has_one_inline_script_the_import_map_and_no_handlers():
    html = web_text("index.html")
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
    inline = [attrs for attrs, body in scripts if body.strip()]
    assert inline == [' type="importmap"']
    assert [attrs for attrs, body in scripts if not body.strip()] == [' type="module" src="/boot.js"']
    assert not re.search(r"\son[a-z]+\s*=", html), "an on* attribute would need 'unsafe-inline'"
    assert '<meta name="jui-viz-token" content="__JUI_VIZ_TOKEN__">' in html


def test_the_import_map_points_at_the_vendored_three():
    html = web_text("index.html")
    assert '"three": "/vendor/three-0.160.0/three.module.min.js"' in html
    assert '"three/addons/": "/vendor/three-0.160.0/addons/"' in html
    for rel in ("three.module.min.js", "addons/controls/OrbitControls.js", "addons/geometries/RoundedBoxGeometry.js"):
        assert WEB.joinpath("vendor", "three-0.160.0", *rel.split("/")).is_file()
    js = bundle.build("live", e2e=False)
    assert set(re.findall(r"from '([^']+)'", js)) == {"three", "three/addons/controls/OrbitControls.js",
                                                     "three/addons/geometries/RoundedBoxGeometry.js"}


def test_nothing_is_fetched_from_outside():
    """No absolute URL in what the page loads or runs (plan 07 §6). Vendor files are pinned by sha256 below."""
    texts = {"index.html": web_text("index.html"), "app.css": web_text("app.css"), "boot.js": web_text("boot.js")}
    for mode in bundle.MODES:
        texts[f"app.js ({mode})"] = bundle.build(mode, e2e=True)
    for name, text in texts.items():
        hits = [u for u in re.findall(r"(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}[^\s'\"`)]*", text, re.I)]
        assert hits == [], f"{name}: {hits[:5]}"
    css = texts["app.css"]
    assert "fonts.googleapis" not in css and "@import" not in css
    assert set(re.findall(r'url\("([^"]+)"\)', css)) == {"/fonts/JetBrainsMono-Medium.woff2", "/fonts/JetBrainsMono-Bold.woff2"}


def test_the_vendored_files_are_the_ones_vendor_md_records():
    md = web_text("vendor", "VENDOR.md")
    rows = re.findall(r"^\| `([^`]+)` \| `[^`]+` \| `([0-9a-f]{64})` \|$", md, re.M)
    assert len(rows) == 7
    for rel, digest in rows:
        parts = rel.split("/")
        f = WEB.joinpath(*(parts[1:] if parts[0] == ".." else ["vendor", *parts]))
        assert hashlib.sha256(f.read_bytes()).hexdigest() == digest, rel
    assert WEB.joinpath("vendor", "three-0.160.0", "LICENSE").is_file()
    assert WEB.joinpath("fonts", "OFL.txt").is_file()
