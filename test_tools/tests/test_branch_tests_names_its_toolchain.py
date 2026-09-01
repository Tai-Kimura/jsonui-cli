"""The generation run says which version produced the files.

Bootstrap is not an operation any lane performs — it happens to a project
rather than being done by it — so it leaves no trace in a lane's record. A
lane regenerated branch tests with a renderer that had arrived minutes
earlier, and could not say WHILE DOING IT which version had written the
files. They settled it afterwards by re-running `--check` and finding
nothing stale.

That is a reconciliation, not a record. It works only while the tree still
matches, so it cannot answer the same question about a commit from last
week, and it cannot answer it at all for a tree that has moved on.

TWO THINGS ARE PINNED HERE, and the second is the constraint:

1. the generation output names the version
2. the GENERATED FILES DO NOT

A version baked into the artefacts would drift every one of them on every
release, and `--check` would lose the difference between "the generator
changed" and "the number did" — the one distinction it exists to make. So
the negative arm is not tidiness; it is the requirement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli import __version__
from jsonui_test_cli.cli import cmd_generate_branch_tests

from test_branch_tests_generator import BASIC, _project


class _Args:
    def __init__(self, root, **kw):
        self.screen = kw.pop("screen", "checkout")
        self.spec = None
        self.check = kw.pop("check", False)
        self.platform = kw.pop("platform", "web")
        # The parser's own defaults. `None` here reached `project_root /
        # None` and reddened every test in this file with a TypeError,
        # which is a stub defect reading exactly like a product one.
        self.out_dir = "tests/unit/generated"
        self.harness_dir = "tests/unit/branch-harness"
        self.mocks_dir = "tests/mocks"
        self.package = None
        self.module = None
        for key, value in kw.items():
            setattr(self, key, value)


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = _project(tmp_path, BASIC)
    monkeypatch.chdir(root)
    return root


def _run(project, capsys, **kw):
    rc = cmd_generate_branch_tests(_Args(project, **kw))
    return rc, capsys.readouterr()


class TestTheRunNamesItsVersion:
    def test_the_generation_output_carries_the_version(self, project, capsys):
        rc, out = _run(project, capsys)

        assert rc == 0
        assert f"jsonui-test {__version__}" in out.out

    def test_the_version_is_the_toolchain_one_not_a_literal(self, project,
                                                            capsys):
        """`__version__` is read from the toolchain's VERSION file, so this
        also fails if the package ever goes back to hard-coding it — which
        is how a stale copy on PATH kept claiming a plausible number."""
        _, out = _run(project, capsys)

        version = (Path(__file__).resolve().parents[2] / "VERSION").read_text(
            encoding="utf-8").strip()
        assert f"jsonui-test {version}" in out.out


class TestTheFilesDoNotCarryIt:
    """The requirement, not a preference. See the module docstring."""

    def test_no_generated_file_embeds_the_version(self, project, capsys):
        _run(project, capsys)

        written = [p for p in project.rglob("*")
                   if p.is_file() and p.suffix in {".ts", ".kt", ".swift"}]
        assert written, "nothing was generated, so this proves nothing"
        for path in written:
            assert __version__ not in path.read_text(encoding="utf-8"), path

    def test_two_runs_produce_identical_bytes(self, project, capsys):
        """The consequence the constraint protects, stated as the property
        it actually is.

        The first draft of this monkeypatched `cli.__version__` and
        asserted the files were unchanged. That passes whether or not the
        constraint holds: if the version were embedded from
        `branch_tests.__version__`, or read at import, patching the name in
        `cli` would change nothing and the test would agree. It measured
        the patch, not the generator. Determinism is what can be measured
        from outside, and `--check` rests on it directly.
        """
        _run(project, capsys)
        before = {p: p.read_bytes() for p in project.rglob("*")
                  if p.is_file() and p.suffix in {".ts", ".kt", ".swift"}}

        _run(project, capsys)

        assert {p: p.read_bytes() for p in before} == before


class TestCheckDoesNotClaimIt:
    def test_check_output_does_not_name_the_running_version(self, project,
                                                            capsys):
        """`--check` reports on files it did not write. Naming the running
        version beside its verdict would read as a claim about what
        produced them, which is the very confusion this closes."""
        _run(project, capsys)

        _, out = _run(project, capsys, check=True)

        assert "generated by jsonui-test" not in out.out
