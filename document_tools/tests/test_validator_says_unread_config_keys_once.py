"""`validate` says a config's unread keys once per run, not under every spec.

The canon context carries the config's "no tool reads" line, and every spec
with a declared endpoint added it to its own result — `validate spec <dir>`
on three specs printed the same line three times, one key read as three
warnings. Same shape as the per-spec repetition in `jui verify`.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonui_doc_cli.spec_doc.validator import SpecValidator

SWAGGER = {"openapi": "3.0.3", "paths": {"/api/me/locale": {"put": {}}}}


def _project(root: Path, names, config) -> list[Path]:
    (root / "docs" / "api").mkdir(parents=True)
    (root / "docs" / "api" / "swagger.json").write_text(
        json.dumps(SWAGGER), encoding="utf-8")
    (root / "docs" / "screens").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(config), encoding="utf-8")
    paths = []
    for name in names:
        spec = {"type": "screen_spec",
                "metadata": {"name": name.title(), "screen": name},
                "dataFlow": {"apiEndpoints": [
                    {"method": "PUT", "path": "/api/me/locale"}]}}
        path = root / "docs" / "screens" / f"{name}.spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        paths.append(path)
    return paths


def _said(results) -> list[str]:
    return [w.message for r in results for w in r.warnings
            if "no tool reads" in w.message]


def test_three_specs_under_one_config_carry_the_line_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = _project(tmp_path / "app", ["alpha", "beta", "gamma"],
                     {"zzzProbe": 1, "yyyProbe": 2})
    validator = SpecValidator()
    said = _said([validator.validate_file(p) for p in paths])
    assert len(said) == 1, said
    assert "'yyyProbe', 'zzzProbe'" in said[0]


def test_a_second_config_and_a_second_run_still_say_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    one = _project(tmp_path / "one", ["alpha", "beta"], {"zzzProbe": 1})
    two = _project(tmp_path / "two", ["alpha", "beta"], {"zzzProbe": 1})
    validator = SpecValidator()
    assert len(_said([validator.validate_file(p) for p in one + two])) == 2
    # A new validator is a new run: nothing carried over.
    assert len(_said([SpecValidator().validate_file(one[0])])) == 1
