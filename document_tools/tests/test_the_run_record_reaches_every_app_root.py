"""Regression: doc-generate-html-records-its-manifest-in-one-root-so-a-multi-app-run-leaves-the-other-faces-without-one
(and doc-manifest-run-record-lands-in-one-face-and-carries-the-others-paths).

`_resolve_project_root` returned ONE root — the first `--app` with a config —
so a site run over four apps wrote its pages and its run facts into one face's
manifest, and the other three could never hold `summary.run`. The v1.8.66
notice had told every face to read `summary.run.outsideOutput.*` as the
outside-writes discriminator; for three of four faces that key was
structurally absent, which reads exactly like "nothing written outside".

Measured 2026-09-10 on isolated copies: 4 apps → 1 manifest, 2 apps → 1.

The record now lands in every root the run resolved: `--config` alone, else
every app with a config, else the walk-up. Each copy carries the same run
facts and the same `recordedAt` (one stamp per run), names the apps it
covered, records the pages under ITS root only, and reports its own
`manifestIsGitTracked`.

⚠️ The CLI arm SHOOTS THE COMMAND. The one-root defect lived in the wiring
between `cmd_generate_html` and the generator; a function-level arm passes a
list the command never built.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _manifest(root: Path) -> dict:
    p = root / ".jsonui-cli" / "generation-manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


# ---------------------------------------------------------------- unit ----

@pytest.fixture()
def two_roots(tmp_path, monkeypatch):
    """Two app roots and an output tree holding one page under each."""
    out = tmp_path / "site" / "html"
    roots = {}
    written = []
    for name in ("a", "b"):
        root = tmp_path / name
        page = root / "docs" / "html" / "index.html"
        page.parent.mkdir(parents=True)
        page.write_text("<html></html>", encoding="utf-8")
        roots[name] = root
        written.append(page.resolve())
    out.mkdir(parents=True)
    monkeypatch.setattr(gen, "get_written_pages", lambda: set(written))
    return out, roots


def test_every_root_gets_the_same_run_record(two_roots, capsys):
    out, roots = two_roots
    outside = {"directories": ["/elsewhere"], "gitTrackedDirectories": {}, "uncheckable": []}
    gen._record_generation_manifest(
        out, [{"app": "a", "root": roots["a"]}, {"app": "b", "root": roots["b"]}],
        [], outside, slots={"declarations": 2, "paths": 2, "sharedPaths": 0, "sharedPathKeys": []})
    runs = {n: _manifest(r)["summary"]["run"] for n, r in roots.items()}
    assert runs["a"]["recordedAt"] == runs["b"]["recordedAt"], "one stamp per run"
    assert runs["a"]["recordedBy"] == runs["b"]["recordedBy"] == "jsonui-doc generate html"
    assert runs["a"]["apps"] == runs["b"]["apps"] == ["a", "b"]
    # The outside-writes record is scoped per root (see the arm below), so
    # here — nothing under either root — both say so explicitly.
    assert runs["a"]["outsideOutput"]["directories"] == [] == runs["b"]["outsideOutput"]["directories"]
    assert runs["a"]["documentSlots"] == runs["b"]["documentSlots"]
    printed = capsys.readouterr().out
    assert printed.count("Manifest created:") == 2, printed


def test_pages_are_recorded_under_their_own_root_only(two_roots):
    out, roots = two_roots
    gen._record_generation_manifest(
        out, [{"app": "a", "root": roots["a"]}, {"app": "b", "root": roots["b"]}], [], {})
    assert set(_manifest(roots["a"])["files"]) == {"docs/html/index.html"}
    assert set(_manifest(roots["b"])["files"]) == {"docs/html/index.html"}
    # Same relative key, two different files: neither manifest lists a page
    # that lives under the other root.
    assert _manifest(roots["a"])["summary"]["tracked"] == 1


def test_a_second_run_says_updated_not_created(two_roots, capsys):
    out, roots = two_roots
    targets = [{"app": "a", "root": roots["a"]}, {"app": "b", "root": roots["b"]}]
    gen._record_generation_manifest(out, targets, [], {})
    capsys.readouterr()
    gen._record_generation_manifest(out, targets, [], {})
    printed = capsys.readouterr().out
    assert printed.count("Manifest updated:") == 2 and "Manifest created:" not in printed


def test_a_single_root_keeps_the_single_tree_spelling(two_roots, capsys):
    """One root, one manifest, no per-root line; `apps` is `[]`, said.

    ⚠️ Inverted 2026-09-10: `apps` used to be absent on a single-root run, and
    a face reading it beside a four-root run's `apps` could not tell "no
    --app" from "not recorded"."""
    out, roots = two_roots
    gen._record_generation_manifest(out, roots["a"], [], {})
    run = _manifest(roots["a"])["summary"]["run"]
    assert run["apps"] == []
    assert "Manifest created:" not in capsys.readouterr().out
    assert not (roots["b"] / ".jsonui-cli").exists()


# ----------------------------------------------------------------- CLI ----

def _spec() -> str:
    return json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": "s", "name": "S", "displayName": "S", "description": "d."},
        "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                      "layout": {"root": "root", "children": []}}})


def _test_json() -> str:
    return json.dumps({
        "type": "screen", "platform": "ios", "source": {"layout": "s"},
        "metadata": {"name": "s", "description": "d"},
        "cases": [{"name": "o", "description": "o",
                   "steps": [{"action": "tap", "id": "x"}]}]})


@pytest.fixture()
def two_apps(tmp_path):
    """Two apps, each with its own config and specs, under one site."""
    site = tmp_path / "site"
    (site / "tests" / "screens").mkdir(parents=True)
    (site / "tests" / "screens" / "s.test.json").write_text(_test_json(), encoding="utf-8")
    for name in ("a", "b"):
        app = site / name
        (app / "docs" / "screens" / "json").mkdir(parents=True)
        (app / "docs" / "screens" / "json" / "s.spec.json").write_text(_spec(), encoding="utf-8")
        (app / "jui.config.json").write_text(
            json.dumps({"spec_directory": "docs/screens/json"}), encoding="utf-8")
    return site


def _run(site: Path, *extra: str) -> str:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "test_tools"), str(REPO / "document_tools")])
    r = subprocess.run(
        [sys.executable, "-m", "jsonui_doc_cli.cli", "generate", "html",
         str(site / "tests"), "-o", str(site / "out"), *extra],
        capture_output=True, text=True, env=env, cwd=str(REPO / "document_tools"))
    return r.stdout + r.stderr


def test_the_command_records_into_every_app_root(two_apps):
    out = _run(two_apps, "--app", f"a:{two_apps / 'a' / 'docs'}", "--app", f"b:{two_apps / 'b' / 'docs'}")
    # isfile, not "the note is gone": the historical path writes one file.
    files = [two_apps / n / ".jsonui-cli" / "generation-manifest.json" for n in ("a", "b")]
    assert [f.is_file() for f in files] == [True, True], out
    runs = [_manifest(two_apps / n)["summary"]["run"] for n in ("a", "b")]
    assert runs[0]["recordedAt"] == runs[1]["recordedAt"]
    assert runs[0]["apps"] == runs[1]["apps"] == ["a", "b"]
    assert "Manifests recorded at: 2 roots" in out
    assert out.count("Manifest created:") == 2


def test_config_narrows_the_set_to_one_root(two_apps):
    out = _run(two_apps, "--config", str(two_apps / "a" / "jui.config.json"),
               "--app", f"a:{two_apps / 'a' / 'docs'}", "--app", f"b:{two_apps / 'b' / 'docs'}")
    assert (two_apps / "a" / ".jsonui-cli" / "generation-manifest.json").is_file()
    assert not (two_apps / "b" / ".jsonui-cli").exists(), out
    assert "Manifests recorded at:" not in out
    assert "(from --config)" in out


def test_outside_writes_are_scoped_to_each_root(two_roots):
    """One face's block used to carry every face's directories; now each block
    names writes under ITS root, and says so — an empty list is an answer."""
    out, roots = two_roots
    a_dir = str((roots["a"] / "docs" / "components").resolve())
    b_dir = str((roots["b"] / "docs" / "requirements").resolve())
    elsewhere = "/elsewhere/docs"
    outside = {"directories": [a_dir, b_dir, elsewhere],
               "gitTrackedDirectories": {a_dir: 5, b_dir: 14},
               "gitModifiedDirectories": {b_dir: 2},
               "uncheckable": [elsewhere]}
    gen._record_generation_manifest(
        out, [{"app": "a", "root": roots["a"]}, {"app": "b", "root": roots["b"]}], [], outside)
    a = _manifest(roots["a"])["summary"]["run"]["outsideOutput"]
    b = _manifest(roots["b"])["summary"]["run"]["outsideOutput"]
    # Recorded relative to each face's root since 1.9.4 (a tracked manifest
    # must not carry the operator's home directory); the scoping is the same.
    assert a["directories"] == ["docs/components"] and b["directories"] == ["docs/requirements"]
    assert a["gitTrackedDirectories"] == {"docs/components": 5}
    assert b["gitTrackedDirectories"] == {"docs/requirements": 14}
    assert a["gitModifiedDirectories"] == {} and b["gitModifiedDirectories"] == {"docs/requirements": 2}
    assert a["uncheckable"] == [] and b["uncheckable"] == []
    assert a["scope"] == ["."] and b["scope"] == ["."]


def test_a_single_root_block_is_scoped_and_says_so(two_roots):
    """⚠️ Inverted 2026-09-10: a single-root block used to carry the run-level
    record with no `scope`, and beside multi-root blocks that had one it read
    as "unrestricted" — the absence wearing another meaning. Every block is
    scoped to its face's root (∪ docs) and names the scope."""
    out, roots = two_roots
    own = str((roots["a"] / "docs" / "html").resolve())
    outside = {"directories": ["/elsewhere/docs", own], "gitTrackedDirectories": {}, "uncheckable": []}
    gen._record_generation_manifest(out, roots["a"], [], outside)
    block = _manifest(roots["a"])["summary"]["run"]["outsideOutput"]
    assert block["directories"] == ["docs/html"]
    assert block["scope"] == ["."] and block["scopeRelative"] == ["."]
    assert block["directoriesRelative"] == ["docs/html"]
    assert block["elsewhere"] == 1  # /elsewhere/docs: counted, not listed


def test_a_docs_directory_outside_the_root_is_still_the_faces_own(two_roots, tmp_path):
    """A split tree keeps a face's docs under the PARENT repository's docs/,
    outside the face's root — and that is what the run writes. Scoped to the
    root alone both faces read an empty list (measured on one face's tree
    before this arm); the --app directory is part of the face's scope."""
    out, roots = two_roots
    docs_a = tmp_path / "docs" / "a"
    docs_b = tmp_path / "docs" / "b"
    for d in (docs_a, docs_b):
        (d / "screens" / "html").mkdir(parents=True)
    wa, wb = str((docs_a / "screens" / "html").resolve()), str((docs_b / "screens" / "html").resolve())
    outside = {"directories": [wa, wb], "gitTrackedDirectories": {wa: 3, wb: 4}, "uncheckable": []}
    gen._record_generation_manifest(
        out, [{"app": "a", "root": roots["a"], "docs": docs_a},
              {"app": "b", "root": roots["b"], "docs": docs_b}], [], outside)
    a = _manifest(roots["a"])["summary"]["run"]["outsideOutput"]
    b = _manifest(roots["b"])["summary"]["run"]["outsideOutput"]
    ra, rb = str(roots["a"].resolve()), str(roots["b"].resolve())
    assert a["directories"] == [os.path.relpath(wa, ra)] and b["directories"] == [os.path.relpath(wb, rb)]
    assert a["directories"][0].startswith("..")
    assert a["gitTrackedDirectories"] == {os.path.relpath(wa, ra): 3}
    assert b["gitTrackedDirectories"] == {os.path.relpath(wb, rb): 4}
    assert a["scope"] == [".", os.path.relpath(str(docs_a.resolve()), ra)]


@pytest.fixture()
def split_tree(tmp_path):
    """The reported shape: a parent repository whose root config carries only
    checks, each app's config beside the app, and every app's docs under the
    PARENT's docs/ — outside the app's root."""
    site = tmp_path / "site"
    (site / "tests" / "screens").mkdir(parents=True)
    (site / "tests" / "screens" / "s.test.json").write_text(_test_json(), encoding="utf-8")
    (site / "jui.config.json").write_text(json.dumps({"checks": {}}), encoding="utf-8")
    for name in ("a", "b"):
        (site / name).mkdir()
        (site / name / "jui.config.json").write_text(
            json.dumps({"spec_directory": f"../docs/{name}/screens/json"}), encoding="utf-8")
        (site / "docs" / name / "screens" / "json").mkdir(parents=True)
        (site / "docs" / name / "screens" / "json" / "s.spec.json").write_text(_spec(), encoding="utf-8")
    return site


def test_the_command_scopes_each_faces_record_to_its_own_docs_in_a_split_tree(split_tree):
    out = _run(split_tree, "--app", f"a:{split_tree / 'docs' / 'a'}", "--app", f"b:{split_tree / 'docs' / 'b'}")
    assert "Manifests recorded at: 2 roots" in out, out
    ra, rb = split_tree / "a", split_tree / "b"
    assert (ra / ".jsonui-cli" / "generation-manifest.json").is_file()
    assert (rb / ".jsonui-cli" / "generation-manifest.json").is_file()
    a = _manifest(ra)["summary"]["run"]
    b = _manifest(rb)["summary"]["run"]
    assert a["recordedAt"] == b["recordedAt"] and a["apps"] == ["a", "b"]
    # The run writes each app's docs (outside -o and outside every root); each
    # face's block names ITS docs and not the other's.
    oa = a.get("outsideOutput") or {}
    ob = b.get("outsideOutput") or {}
    assert oa.get("scope") == [".", "../docs/a"]
    assert all(d.startswith("../docs/a/") for d in oa.get("directories", [])), oa
    assert all(d.startswith("../docs/b/") for d in ob.get("directories", [])), ob
    assert oa.get("directories") and ob.get("directories"), (oa, ob)


def test_a_split_tree_run_writes_no_absolute_path_into_either_manifest(split_tree):
    """Regression: doc-run-manifest-scan-roots-absolute-path (2026-09-29).

    The reporting faces track `.jsonui-cli/generation-manifest.json` in a
    public repository. Through 1.9.3 every doc run over `--app <face>:<docs>`
    wrote the checkout's absolute path into it — `summary.run.scan.roots`
    (the --app docs directory, outside the face root) and six entries of
    `outsideOutput` — so the file could not be committed and never stopped
    differing. Measured on the real command, over the WHOLE file, with both
    spellings of the temporary directory (macOS hands out `/var/…`, which
    resolves to `/private/var/…`), so a path in either form is caught."""
    _run(split_tree, "--app", f"a:{split_tree / 'docs' / 'a'}", "--app", f"b:{split_tree / 'docs' / 'b'}")
    prefixes = {str(split_tree), str(split_tree.resolve())}
    for face, docs in (("a", "../docs/a"), ("b", "../docs/b")):
        path = split_tree / face / ".jsonui-cli" / "generation-manifest.json"
        raw = path.read_text(encoding="utf-8")
        leaked = sorted(p for p in prefixes if p in raw)
        assert leaked == [], f"{face}: the manifest names the checkout {leaked}"
        run = json.loads(raw)["summary"]["run"]
        assert run["scan"]["roots"] == [".", docs]
        # The positive side of the same file: the paths are still there, spelled
        # relative — not dropped (an empty record would pass the check above).
        assert run["outsideOutput"]["directories"], run["outsideOutput"]
        assert run["outsideOutput"]["scope"] == [".", docs]
