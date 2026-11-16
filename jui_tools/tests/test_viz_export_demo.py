"""jui viz export-demo: the demo page as a static folder (P8)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from jui_cli.cli import main
from jui_cli.viz import export_demo

REPO = Path(__file__).resolve().parents[2]


def test_the_export_is_a_relative_static_demo_without_live_parts(tmp_path):
    out = tmp_path / "viz-demo"
    result = export_demo.export(out)
    names = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert {"index.html", "app.js", "app.css"} <= set(names)
    assert any(n.startswith("vendor/three-0.160.0/") and n.endswith("three.module.min.js") for n in names)
    assert any(n.startswith("fonts/") and n.endswith(".woff2") for n in names)
    # Mermaid (2.3.5) stays out: the demo's hand-written sheets draw no diagram (export_demo.NOT_EXPORTED)
    assert not any("mermaid" in n for n in names)
    assert result["files"] == len(names) and result["bytes"] < 3_000_000
    for name in ("index.html", "app.js", "app.css"):
        text = (out / name).read_text()
        for live in export_demo.LIVE_ONLY:
            assert live not in text, (name, live)
        assert not re.search(r'(?:src|href)="/(?!/)|url\("/|"/vendor/', text), name
        # the words' table (a JSON block, never run) holds the words' URLs: links shown, not fetched
        page = re.sub(r'<script type="application/json" id="jui-viz-strings">.*?</script>', '', text, flags=re.S)
        assert not re.search(r'https?://(?!www\.w3\.org)', page) or name == "app.js", name
    html = (out / "index.html").read_text()
    assert '<script type="module" src="app.js"></script>' in html and "boot.js" not in html


def test_the_demo_script_reaches_no_other_host(tmp_path):
    """The page must not talk to the outside: no fetch / import of an absolute URL."""
    out = tmp_path / "d"
    export_demo.export(out)
    app = (out / "app.js").read_text()
    assert not re.search(r"(?:fetch|import)\(\s*['\"`]https?://", app)
    assert "new WebSocket" not in app


def test_export_refuses_a_folder_that_is_not_empty(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # a viz command: never the real home
    (tmp_path / "keep.txt").write_text("x")
    assert main(["viz", "export-demo", "--out", str(tmp_path)]) == 1
    assert "is not empty" in capsys.readouterr().err
    assert (tmp_path / "keep.txt").read_text() == "x"


def test_every_web_file_is_in_the_wheel(tmp_path):
    """setup.py's package_data names each folder; a new folder under web/ that is
    not named would be missing from the installed package (P8 §5)."""
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "jui_tools/jui_cli/viz/web"],
                             capture_output=True, text=True, check=True).stdout.split()
    import fnmatch
    import ast

    tree = ast.parse((REPO / "jui_tools" / "setup.py").read_text())
    patterns = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "jui_cli.viz":
                    patterns = [e.value for e in v.elts]
    assert patterns, "setup.py has no package_data for jui_cli.viz"
    missing = []
    for path in tracked:
        rel = path[len("jui_tools/jui_cli/viz/"):]
        # setuptools globs do not cross "/": match each pattern within its own folder depth
        if not any(fnmatch.fnmatch(rel, p) and rel.count("/") == p.count("/") for p in patterns):
            missing.append(rel)
    assert missing == [], missing
