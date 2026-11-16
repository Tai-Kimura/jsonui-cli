"""`generate spec <dir> --format markdown` wrote HTML into `.html` files.

`cmd_generate_spec` hands a directory to `cmd_generate_spec_batch` before it
works out a format, and the batch never read `args.format` — it called
`generate_spec_html` and wrote `.html` unconditionally. A project asking for
Markdown over 103 specs got 103 HTML files and no complaint. Same in 1.8.15.

What is NOT changed: omitting `--format` over a directory still produces
HTML. There is nothing to infer from — the output is a directory, so there
is no extension to read a format off — and every other thing about the batch
form says HTML: the default output directory is `<parent>/html`, the
documented invocation is `generate spec docs/specs/ -o docs/html`, and the
progress line announces it. Defaulting to Markdown would change what that
documented command produces, which is a behaviour change wearing a bug
fix's clothes. The help text was the part that was wrong.

The arms assert on the files on disk, not on which branch ran: the defect
was that a format was chosen correctly somewhere and never reached the
writer.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_doc_cli.cli import (  # noqa: E402
    cmd_generate_component, cmd_generate_spec,
)

SPEC = {
    "type": "screen_spec",
    "version": "1.0",
    "metadata": {"name": "Login", "displayName": "Login",
                 "description": "A spec.", "layoutFile": "login"},
    "structure": {"components": []},
}

# The sibling: `cmd_generate_component` dispatches to its own batch on
# `is_dir()`, and that one had the identical defect. Found only because
# someone swept for siblings after the spec batch was fixed — the sweep the
# first fix should have carried. Both are driven from one file so the next
# batch command has somewhere obvious to be added.
COMPONENT = {
    "type": "component_spec",
    "version": "1.0",
    "metadata": {"name": "Chip", "displayName": "Chip", "description": "d"},
    "structure": {
        "components": [{"type": "Label", "id": "chip", "description": "c"}],
        "layout": {"root": "chip", "children": []},
    },
}


KINDS = {
    "spec": (cmd_generate_spec, "spec.json", SPEC),
    "component": (cmd_generate_component, "component.json", COMPONENT),
}


def run(fmt, *, kind="spec", count=2):
    cmd, ext, body = KINDS[kind]
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        specs = root / "specs"
        specs.mkdir()
        for i in range(count):
            (specs / f"s{i}.{ext}").write_text(json.dumps(body), encoding="utf-8")
        out = root / "out"
        code = cmd(argparse.Namespace(
            file=str(specs), output=str(out), format=fmt, layouts_dir=None))
        written = sorted(p.name for p in out.rglob("*") if p.is_file())
        bodies = [p.read_text(encoding="utf-8")
                  for p in sorted(out.rglob("*")) if p.is_file()]
        return code, written, bodies


def looks_like_html(text: str) -> bool:
    return "<html" in text.lower() or "<!doctype" in text.lower()


@pytest.mark.parametrize("kind", list(KINDS))
class TestAnExplicitFormatIsHonoured:
    def test_markdown_writes_markdown_files(self, kind):
        code, written, bodies = run("markdown", kind=kind)
        assert code == 0
        assert written == ["s0.md", "s1.md"]

    def test_markdown_writes_markdown_content(self, kind):
        # The extension alone would pass against a version that renamed the
        # file and still wrote HTML into it — which is the shape of the
        # defect, one step along.
        _, written, bodies = run("markdown", kind=kind)
        assert bodies
        # Report the shape, not the file: a failing arm here used to paste a
        # whole generated HTML page into the output.
        shapes = ["html" if looks_like_html(b) else "markdown" for b in bodies]
        assert shapes == ["markdown"] * len(bodies), (written, shapes)
        assert all(b.lstrip().startswith("#") for b in bodies)

    def test_html_still_writes_html(self, kind):
        code, written, bodies = run("html", kind=kind)
        assert code == 0
        assert written == ["s0.html", "s1.html"]
        assert all(looks_like_html(b) for b in bodies)


@pytest.mark.parametrize("kind", list(KINDS))
class TestTheDefaultIsUnchanged:
    """A directory with no `--format` produced HTML before and produces HTML
    now. This is the documented invocation."""

    def test_omitting_the_format_still_writes_html(self, kind):
        code, written, bodies = run(None, kind=kind)
        assert code == 0
        assert written == ["s0.html", "s1.html"]
        assert all(looks_like_html(b) for b in bodies)


class TestTheSingleFilePathIsUntouched:
    """It already read the format; the batch branch was the only gap."""

    @pytest.mark.parametrize("out_name,expect_html", [
        ("x.md", False),
        ("x.html", True),
    ])
    def test_a_single_file_infers_from_the_output_extension(self, out_name, expect_html):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "one.spec.json"
            spec.write_text(json.dumps(SPEC), encoding="utf-8")
            out = root / out_name
            code = cmd_generate_spec(argparse.Namespace(
                file=str(spec), output=str(out), format=None, layouts_dir=None))
            assert code == 0
            assert looks_like_html(out.read_text(encoding="utf-8")) is expect_html
