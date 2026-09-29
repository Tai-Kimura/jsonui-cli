"""A case `intent` written as `{"md": ...}` reaches the gate as its text.

The intent is read in three places here — the unit pages, the stub
generator and `--check`'s report — and each once did `str(case["intent"])`.
Unresolved, a reference would have printed `{'md': '...'}` into a generated
test's failure message; resolved and then `str()`-ed, the unit page would
have lost that the text is Markdown. Both directions are pinned: the case
carries the YAML text, and it is still a `MarkdownText`.

Both spellings of a spec that carries cases are covered, because they are
read by two different loaders: an app contracts spec (read raw) and a screen
spec (read through `_load_spec_result`).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import unit_contracts as uc
from jsonui_test_cli.branch_tests import APP_CONTRACTS_SPEC_TYPE

INTENT = "**retries once**\n\n- then gives up\n"
YAML = "cases:\n  retries: |\n    **retries once**\n\n    - then gives up\n"


def _project(tmp_path, spec_type):
    specs = tmp_path / "docs" / "screens"
    specs.mkdir(parents=True)
    block = {"target": "SharedHttpClient",
             "cases": [{"name": "retries_once", "intent": {"md": "cases.retries"}},
                       {"name": "plain", "intent": "inline"}]}
    spec = {"type": spec_type, "version": "1.0",
            "metadata": {"name": "storefront", "description": "d"},
            "unitContracts": block}
    (specs / "storefront.spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (specs / "storefront.texts.yaml").write_text(YAML, encoding="utf-8")
    (tmp_path / "jui.config.json").write_text(
        json.dumps({"spec_directory": "docs/screens", "platforms": {}}),
        encoding="utf-8")
    return tmp_path


def _intents(root):
    cases = uc.discover_unit_contracts(root)[0]
    return {c.name: c.intent for c in cases}


def _is_markdown(value):
    return type(value).__name__ == "MarkdownText"


def test_an_app_spec_intent_is_the_yaml_text_and_still_markdown(tmp_path):
    intents = _intents(_project(tmp_path, APP_CONTRACTS_SPEC_TYPE))
    assert intents["retries_once"] == INTENT
    assert _is_markdown(intents["retries_once"])
    assert intents["plain"] == "inline"
    assert not _is_markdown(intents["plain"])


def test_a_screen_spec_intent_is_the_yaml_text_and_still_markdown(tmp_path):
    intents = _intents(_project(tmp_path, "screen_spec"))
    assert intents["retries_once"] == INTENT
    assert _is_markdown(intents["retries_once"])


# --------------------------------------------------------------------------
# An unresolvable reference is refused, in the resolver's words, by every
# command that reads the spec — never written out as `{'md': ...}`.
#
# The three ways it happens on a real machine: the key is misspelled, the
# texts file is missing, or PyYAML is not installed.

import argparse  # noqa: E402

import pytest  # noqa: E402

from jsonui_test_cli import cli  # noqa: E402
from jsonui_test_cli import branch_tests as bt  # noqa: E402
from jsonui_test_cli import contracts_coverage as cc  # noqa: E402


def _broken(tmp_path, how, spec_type="screen_spec"):
    root = _project(tmp_path, spec_type)
    specs = root / "docs" / "screens"
    (root / "web" / "tests").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens",
        "platforms": {"web": {"root": "web", "unitTestsDir": "tests"}}}),
        encoding="utf-8")
    if how == "misspelled":
        (specs / "storefront.texts.yaml").write_text(
            "cases:\n  retires: typo\n", encoding="utf-8")
    elif how == "no file":
        (specs / "storefront.texts.yaml").unlink()
    return root


class _NoYaml:
    def __enter__(self):
        self.saved = sys.modules.get("yaml", self)
        sys.modules["yaml"] = None

    def __exit__(self, *exc):
        if self.saved is self:
            sys.modules.pop("yaml", None)
        else:
            sys.modules["yaml"] = self.saved


def _maybe_no_yaml(how):
    import contextlib
    return _NoYaml() if how == "no pyyaml" else contextlib.nullcontext()


HOWS = ("misspelled", "no file", "no pyyaml")
FIELD = "unitContracts.cases[0].intent"


@pytest.mark.parametrize("how", HOWS)
@pytest.mark.parametrize("check", (False, True))
@pytest.mark.parametrize("spec_type", (APP_CONTRACTS_SPEC_TYPE, "screen_spec"))
def test_unit_stubs_refuses_an_unresolved_intent(tmp_path, monkeypatch, capsys,
                                                 how, check, spec_type):
    root = _broken(tmp_path, how, spec_type)
    monkeypatch.chdir(root)
    with _maybe_no_yaml(how):
        rc = cli.cmd_generate_unit_stubs(
            argparse.Namespace(check=check, dry_run=False, spec_dir=None))
    out = capsys.readouterr().out
    assert rc == 1, out
    assert FIELD in out, out
    assert "{'md'" not in out
    written = [p.read_text() for p in (root / "web" / "tests").rglob("*") if p.is_file()]
    assert written == [], written


@pytest.mark.parametrize("how", HOWS)
def test_branch_scan_reports_an_unresolved_reference_as_a_problem(tmp_path, how):
    root = _broken(tmp_path, how)
    with _maybe_no_yaml(how):
        _screens, scanned, problems = bt.discover_branch_screens(root)
    assert "storefront" in scanned
    assert any(FIELD in p and "storefront" in p for p in problems), problems
    assert not any("refused by the merger" in p for p in problems), problems


def test_branch_generate_refuses_an_unresolved_reference(tmp_path):
    root = _broken(tmp_path, "misspelled")
    with pytest.raises(bt.BranchTestGenerationError) as e:
        bt._load_spec(root / "docs" / "screens" / "storefront.spec.json")
    assert FIELD in str(e.value)


def test_coverage_does_not_evaluate_a_spec_it_cannot_resolve(tmp_path):
    root = _broken(tmp_path, "misspelled")
    (root / "docs" / "api").mkdir(parents=True)
    (root / "docs" / "api" / "openapi.json").write_text(
        json.dumps({"openapi": "3.0.0", "paths": {}}), encoding="utf-8")
    (root / "tests" / "mocks").mkdir(parents=True)
    config = json.loads((root / "jui.config.json").read_text(encoding="utf-8"))
    config["mock"] = {"swagger": "docs/api/openapi.json"}
    (root / "jui.config.json").write_text(json.dumps(config), encoding="utf-8")
    project = cc.load_project(root)
    sources, _unknown = cc.iter_screens(project)
    (source,) = [s for s in sources if s.name == "storefront"]
    assert source.spec is None
    assert FIELD in (source.problem or "")


def test_a_sub_spec_reference_the_merger_could_not_resolve_is_refused(tmp_path):
    root = _broken(tmp_path, "misspelled")
    specs = root / "docs" / "screens"
    sub = specs / "storefront.spec.json"
    sub.rename(specs / "storefront_body.spec.json")
    (specs / "storefront.texts.yaml").rename(specs / "storefront_body.texts.yaml")
    (specs / "storefront.spec.json").write_text(json.dumps({
        "type": "screen_parent_spec", "version": "1.0",
        "metadata": {"name": "storefront", "description": "d"},
        "subSpecs": [{"file": "storefront_body.spec.json", "name": "body"}]}),
        encoding="utf-8")
    with pytest.raises(bt.SpecTextsError) as e:
        bt._load_spec_result(specs / "storefront.spec.json")
    assert "storefront_body.spec.json" in str(e.value)
    assert FIELD in str(e.value)


def test_an_intent_that_is_still_a_dict_is_never_its_repr():
    assert uc._intent_of({"md": "cases.retries"}) == ""
