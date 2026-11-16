"""A config's unread keys are said once per run, not once per spec.

`resolve_canonical_marks` builds the canon context per spec, and the context
carries the config's "no tool reads" line — so a project with 38 marked specs
printed the same line 38 times in one `jui verify` (measured on a consumer's
admin face, 2.3.17 and 2.3.18). The warning was right; 38 copies buried it,
and a gate counting warning lines counted 38 for one key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.core.spec_extractor import extract_screen_spec  # noqa: E402

SWAGGER = {
    "openapi": "3.0.3",
    "paths": {"/api/me/locale": {"put": {"requestBody": {
        "required": True, "content": {"application/json": {"schema": {
            "type": "object", "required": ["locale"],
            "properties": {"locale": {"type": "string"}}}}}}}}},
}


def _project(root: Path, names, config) -> list[Path]:
    (root / "docs" / "api").mkdir(parents=True)
    (root / "docs" / "api" / "swagger.json").write_text(
        json.dumps(SWAGGER), encoding="utf-8")
    (root / "docs" / "screens").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(config), encoding="utf-8")
    paths = []
    for name in names:
        spec = {
            "type": "screen_spec",
            "metadata": {"name": name.title(), "description": "F.", "screen": name},
            "dataFlow": {"repositories": [{"name": "UserRepository", "methods": [
                {"name": "updateLocale", "endpoint": "PUT /api/me/locale",
                 "params": "@canonical"}]}]},
        }
        path = root / "docs" / "screens" / f"{name}.spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        paths.append(path)
    return paths


def _extract(paths):
    return [extract_screen_spec(json.loads(p.read_text()), p) for p in paths]


def _lines(out: str) -> list[str]:
    return [l for l in out.splitlines() if "no tool reads" in l]


def test_two_specs_under_one_config_print_the_line_once(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    paths = _project(tmp_path / "app", ["alpha", "beta", "gamma"],
                     {"zzzProbe": 1, "yyyProbe": 2})
    specs = _extract(paths)
    lines = _lines(capsys.readouterr().out)
    assert len(lines) == 1, lines
    assert "'yyyProbe', 'zzzProbe'" in lines[0]
    # Saying it once must not cost the later specs their expansion.
    for spec in specs:
        params = spec.repositories[0].methods[0].params
        assert [(p.name, p.type) for p in params] == [("locale", "String")]


def test_two_configs_each_get_their_line(tmp_path, monkeypatch, capsys):
    # Once per config, not once per process: a second project's unread key
    # is a different fact and is still said.
    monkeypatch.chdir(tmp_path)
    one = _project(tmp_path / "one", ["alpha", "beta"], {"zzzProbe": 1})
    two = _project(tmp_path / "two", ["alpha", "beta"], {"zzzProbe": 1})
    _extract(one + two)
    lines = _lines(capsys.readouterr().out)
    assert len(lines) == 2, lines
    assert str(tmp_path / "one" / "jui.config.json") in lines[0]
    assert str(tmp_path / "two" / "jui.config.json") in lines[1]
