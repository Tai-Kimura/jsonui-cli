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
