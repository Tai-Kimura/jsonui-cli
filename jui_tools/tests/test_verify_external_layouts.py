"""`jui verify` holds an externally authored layout to its spec (ticket 2026-10-21-jui-verify-skips-every-consumer-
screen; the requester's plan A).

The rules pack writes every screen with `metadata.layoutFile` and an empty `structure.components`, so verify's
comparison skips every screen: five consumer lanes compared 0 of 151 screens. What a hand-written layout can still be
held to is checked instead: each binding root (includes expanded, an include with an id prefixing what is inside it)
and each entry of the file's own data section is declared by the spec — the data section regenerating it would write,
the view model's vars and methods, the ui variables, the event handlers. A WARNING first; `verify.external: "gate"`
in jui.config.json counts them under --fail-on-diff. Decided with the plan: an include's bindings are the including
screen's to declare; `stateManagement.cellData` (read by no part of jui) declares nothing, and a name found only there
is named as such.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

JUI = Path(__file__).resolve().parents[1] / "bin" / "jui"


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _spec(name, layout, vars_=(), methods=(), ui=(), handlers=(), **extra):
    spec = {"type": "screen_spec", "version": "1.0",
            "metadata": {"name": name, "displayName": name, "description": "a screen", "layoutFile": layout},
            "structure": {"components": [], "layout": {}},
            "dataFlow": {"viewModel": {"vars": [{"name": v, "type": "String"} for v in vars_],
                                       "methods": [{"name": m, "params": []} for m in methods]}},
            "stateManagement": {"uiVariables": [{"name": u, "type": "String"} for u in ui],
                                "eventHandlers": [{"name": h, "description": "tap"} for h in handlers]}}
    for key, value in extra.items():
        spec.setdefault("stateManagement", {})[key] = value
    return spec


@pytest.fixture()
def project(tmp_path):
    _write(tmp_path / "jui.config.json", {"project_name": "external", "spec_directory": "docs/screens/json",
                                          "layouts_directory": "docs/screens/layouts",
                                          "styles_directory": "docs/screens/styles",
                                          "platforms": {"web": {"root": "web", "layoutsDir": "src/Layouts"}}})
    (tmp_path / "docs" / "screens" / "styles").mkdir(parents=True)
    return tmp_path


def _layout(project, name, tree):
    return _write(project / "docs" / "screens" / "layouts" / f"{name}.json", tree)


def _verify(project, *args, config: dict | None = None):
    if config is not None:
        cfg = json.loads((project / "jui.config.json").read_text())
        cfg.update(config)
        _write(project / "jui.config.json", cfg)
    out = project / "verify.json"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    p = subprocess.run([sys.executable, str(JUI), "verify", "--json", str(out), *args], cwd=project, env=env,
                       capture_output=True, text=True, timeout=120)
    summary = json.loads(out.read_text()) if out.exists() else None
    return p.returncode, p.stdout + p.stderr, summary


def _screen(project, layout_tree, **spec):
    _layout(project, "home", layout_tree)
    _write(project / "docs" / "screens" / "json" / "home.spec.json", _spec("Home", "home", **spec))


TREE = {"type": "View", "id": "root", "child": [
    {"data": [{"name": "titleText", "class": "String"}, {"name": "onSaveTap", "class": "(() -> Void)"}]},
    {"type": "Label", "id": "title", "text": "@{titleText}"},
    {"type": "Button", "id": "save", "text": "save", "onClick": "@{onSaveTap}"}]}


def test_a_layout_its_spec_declares_has_no_finding(project):
    _screen(project, TREE, vars_=["titleText"], handlers=["onSaveTap"])
    rc, out, s = _verify(project, "--fail-on-diff")
    assert rc == 0, out
    assert "verified 0 of 1 screen(s)" in out and "checked against the spec's declarations: 1 of 1" in out
    assert s["externalChecked"] == 1 and s["externalTotal"] == 1 and s["externalFindings"] == {}


def test_a_binding_and_a_data_entry_the_spec_does_not_declare(project):
    _screen(project, TREE, vars_=[], handlers=["onSaveTap"])
    rc, out, s = _verify(project)
    assert rc == 0, out                                          # a WARNING by default
    assert "1 finding(s)" in out and "binding `titleText`" in out and "not declared by the spec" in out
    assert "declare each name in the screen's spec, in stateManagement.uiVariables" in out   # where the remedy points
    assert "eventHandlers are view-local and never go there" in out
    assert s["externalFindings"] == {"home.spec": [{"kind": "binding", "name": "titleText",
                                                    "why": "bound in the layout and in its data section (String), not declared by the spec"}]}


def test_a_data_entry_alone(project):
    tree = {"type": "View", "id": "root", "child": [{"data": [{"name": "unusedFlag", "class": "Bool"}]}]}
    _screen(project, tree)
    rc, out, s = _verify(project)
    assert s["externalFindings"]["home.spec"] == [
        {"kind": "data", "name": "unusedFlag", "why": "in its data section (Bool), not declared by the spec"}]


def test_each_way_of_declaring_counts(project):
    tree = {"type": "View", "id": "root", "child": [
        {"type": "Label", "id": "a", "text": "@{fromVar}"}, {"type": "Label", "id": "b", "text": "@{fromUi}"},
        {"type": "Button", "id": "c", "onClick": "@{fromMethod}"}, {"type": "Button", "id": "d", "onClick": "@{fromHandler}"}]}
    _screen(project, tree, vars_=["fromVar"], ui=["fromUi"], methods=["fromMethod"], handlers=["fromHandler"])
    rc, out, s = _verify(project, "--fail-on-diff", config={"verify": {"external": "gate"}})
    assert rc == 0 and s["externalFindings"] == {}, out


def test_an_include_with_an_id_is_the_including_screens_to_declare(project):
    _layout(project, "common/pager", {"type": "View", "id": "pager_root", "partial": True, "child": [
        {"type": "Label", "id": "summary", "text": "@{summaryText}"}]})
    tree = {"type": "View", "id": "root", "child": [{"id": "pager", "include": "common/pager"}]}
    _screen(project, tree, vars_=["summaryText"])               # the partial's own spelling: not the including one
    rc, out, s = _verify(project)
    assert [f["name"] for f in s["externalFindings"]["home.spec"]] == ["pagerSummaryText"], out
    _screen(project, tree, vars_=["pagerSummaryText"])
    rc, out, s = _verify(project)
    assert s["externalFindings"] == {}, out


def test_a_name_only_under_cell_data_is_named_as_such(project):
    _layout(project, "detail/banner", {"type": "View", "id": "banner_root", "partial": True, "child": [
        {"type": "Label", "id": "price", "text": "@{priceValue}"}]})
    tree = {"type": "View", "id": "root", "child": [{"id": "banner", "include": "detail/banner"}]}
    _screen(project, tree, cellData={"bannerSection": {"variables": [{"name": "priceValue", "type": "String"}]}})
    rc, out, s = _verify(project)
    f = s["externalFindings"]["home.spec"]
    assert [x["name"] for x in f] == ["bannerPriceValue"]
    assert "declared only under stateManagement.cellData, which jui does not read" in f[0]["why"]
    # bound as written, declared under cellData only: still not declared (cellData is no declaration, prefix or not)
    tree = {"type": "View", "id": "root", "child": [{"type": "Label", "id": "price", "text": "@{priceValue}"}]}
    _screen(project, tree, cellData={"bannerSection": {"variables": [{"name": "priceValue", "type": "String"}]}})
    rc, out, s = _verify(project)
    f = s["externalFindings"]["home.spec"]
    assert [x["name"] for x in f] == ["priceValue"] and "cellData" in f[0]["why"]


def test_an_unresolved_include_is_said_not_checked(project):
    tree = {"type": "View", "id": "root", "child": [{"id": "x", "include": "no/such_partial"}]}
    _screen(project, tree)
    rc, out, s = _verify(project)
    assert s["externalChecked"] == 0 and s["externalTotal"] == 1
    assert "unresolved include" in s["externalNotChecked"]["home.spec"] and "not checked:" in out


def test_the_gate_is_the_configs(project):
    _screen(project, TREE, vars_=[], handlers=["onSaveTap"])
    rc, out, _ = _verify(project, "--fail-on-diff")
    assert rc == 0 and "reported only" in out                    # warn by default, even with --fail-on-diff
    rc, out, _ = _verify(project, "--fail-on-diff", config={"verify": {"external": "gate"}})
    assert rc == 1 and "counted by `--fail-on-diff`" in out
    rc, out, _ = _verify(project, config={"verify": {"external": "gate"}})
    assert rc == 0                                               # the gate is --fail-on-diff's
    rc, out, _ = _verify(project, config={"verify": {"external": "strict"}})
    assert rc == 1 and "verify.external is 'strict'" in out


def test_an_include_cycle_is_said_not_checked_and_verify_goes_on(project):
    _layout(project, "parts/loop_a", {"type": "View", "id": "a", "partial": True, "child": [{"include": "parts/loop_b"}]})
    _layout(project, "parts/loop_b", {"type": "View", "id": "b", "partial": True, "child": [{"include": "parts/loop_a"}]})
    _screen(project, {"type": "View", "id": "root", "child": [{"include": "parts/loop_a"}]})
    _layout(project, "other", TREE)
    _write(project / "docs" / "screens" / "json" / "other.spec.json", _spec("Other", "other", vars_=["titleText"], handlers=["onSaveTap"]))
    rc, out, s = _verify(project)
    assert rc == 0 and s is not None, out
    assert "include cycle" in s["externalNotChecked"]["home.spec"] and s["externalChecked"] == 1 and s["externalTotal"] == 2


def test_the_report_the_json_and_the_lanes_list_count_the_same(project):
    """The list a consumer lane gets (tools/verify_external_list.py, from --json) has one row per WARNING line."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import verify_external_list as L
    _layout(project, "common/pager", {"type": "View", "id": "pager_root", "partial": True, "child": [
        {"type": "Label", "id": "summary", "text": "@{summaryText}"}, {"type": "Button", "id": "next", "onClick": "@{onNextTap}"}]})
    tree = {"type": "View", "id": "root", "child": [
        {"data": [{"name": "titleText", "class": "String"}, {"name": "unusedFlag", "class": "Bool"}]},
        {"type": "Label", "id": "title", "text": "@{titleText}"}, {"id": "pager", "include": "common/pager"}]}
    _screen(project, tree, cellData={"pagerSection": {"variables": [{"name": "summaryText", "type": "String"}]}})
    rc, out, s = _verify(project)
    warning_lines = [l for l in out.splitlines() if l.startswith("    - binding `") or l.startswith("    - data `")]
    items = L.rows(s, project)
    md = L.render("lane", s, items, L.scope(project))
    table = [l for l in md.splitlines() if l.startswith("| ") and not l.startswith("| spec")]
    assert len(warning_lines) == sum(len(v) for v in s["externalFindings"].values()) == len(items) == len(table) == 4, (out, md)
    by = {r["name"]: r for r in items}
    assert by["pagerSummaryText"]["kind"] == "cellData" and by["pagerSummaryText"]["where"] == "stateManagement.uiVariables（cellData から移す）"
    # an include's handler, the includer's name: a callback in uiVariables (not eventHandlers: view-local, never in the
    # layout's data, and doc validate wants ^on[A-Z] there)
    assert by["pagerOnNextTap"]["where"] == 'stateManagement.uiVariables（型 "(() -> Void)?"）'
    assert by["unusedFlag"]["kind"] == "data" and by["titleText"]["where"] == "stateManagement.uiVariables"
    assert by["titleText"]["spec"] == "docs/screens/json/home.spec.json" and by["titleText"]["layout"] == "home.json"


def test_a_spec_written_as_the_list_says_passes_doc_validate_and_verify(project):
    """The recommendation, applied, satisfies both rules on handler names (ticket 2026-10-21-verify-external-prefixed-
    handler-vs-doc-validate-name-rule): verify finds nothing, and doc validate (document_tools' SpecValidator) has no
    error — an include's prefixed handler declared where the list says, a callback in uiVariables. The control: the
    same handler in eventHandlers, which the list used to recommend, is an ERROR there."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import verify_external_list as L
    from jui_cli.core.document_tools_import import load_document_tools_module
    validator, _ = load_document_tools_module("spec_doc.validator")
    assert validator is not None
    _layout(project, "common/pager", {"type": "View", "id": "pager_root", "partial": True, "child": [
        {"type": "Button", "id": "next", "text": "next", "onClick": "@{onNextTap}"}]})
    tree = {"type": "View", "id": "root", "child": [{"type": "Label", "id": "title", "text": "@{titleText}"},
                                                    {"id": "pager", "include": "common/pager"}]}
    _screen(project, tree)
    rc, out, s = _verify(project)
    items = L.rows(s, project)
    ui = []
    for r in items:   # as the list says
        assert r["where"].startswith("stateManagement.uiVariables"), r
        ui.append({"name": r["name"], "type": "(() -> Void)?" if "() -> Void" in r["where"] else "String",
                   "description": "declared as the list says"})
    spec_path = project / "docs" / "screens" / "json" / "home.spec.json"
    spec = _spec("Home", "home")
    spec["stateManagement"]["uiVariables"] = ui
    _write(spec_path, spec)
    rc, out, s = _verify(project, "--fail-on-diff", config={"verify": {"external": "gate"}})
    assert rc == 0 and s["externalFindings"] == {}, out
    errors = [e.message for e in validator.SpecValidator().validate_file(spec_path).errors]
    assert not [e for e in errors if "Handler name" in e or "camelCase" in e], errors
    # the control: the old recommendation (the prefixed handler in eventHandlers) is an ERROR in doc validate
    spec["stateManagement"]["eventHandlers"] = [{"name": "pagerOnNextTap", "description": "the old advice"}]
    _write(spec_path, spec)
    errors = [e.message for e in validator.SpecValidator().validate_file(spec_path).errors]
    assert any("Handler name must start with 'on'" in e for e in errors), errors
