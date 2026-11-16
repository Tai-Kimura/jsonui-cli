"""Every problem a room's read gives says what is wrong on its line (ticket
2026-10-22-doc-validate-infra-config-exclude-prints-only-its-code: a bad infra.exclude entry printed
`jui.config.json: config.exclude  [config.exclude]`, the same for a missing folder and a path outside the project).

The codes are gathered from the source of the modules room.read gathers problems from (room, model, flows, and
migration for the plans; ticket 2026-10-22-viz-infra-migration-plan), so
a new code with no words of its own is red here, not mute on the terminal. A code still without words says its message.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import model as M, room as R

INFRA = Path(R.__file__).resolve().parent
SOURCES = {name: (INFRA / f"{name}.py").read_text(encoding="utf-8") for name in ("room", "model", "flows", "migration")}
LITERAL = re.compile(r'(?:\b_p(?:roblem)?\([^,()]+,[^,()]+,|\.err\([^,()]+,)\s*"([a-z_]+(?:\.[a-z_]+)*)"')
WHERE = "docs/infra/main.json"
MESSAGE = "the message document_tools wrote"


def _codes() -> set[str]:
    codes = {c for text in SOURCES.values() for c in LITERAL.findall(text)}
    return codes | {f"secret.{k}" for k in M.SECRET_KINDS}


class Told(R.Words):
    """The defaults, with a note of each code that fell to other()."""

    def __init__(self) -> None:
        self.fell: list[str] = []

    def other(self, where, code, message):
        self.fell.append(code)
        return super().other(where, code, message)


def _problems(code: str) -> list[dict]:
    p = {"file": "main.json", "path": "/nodes/0", "code": code, "message": MESSAGE, "severity": "error", "line": 3}
    if code == "config.exclude":
        return [dict(p, file=R.CONFIG_NAME, path="/infra/exclude/0", why=why) for why in R.EXCLUDE_JA]
    return [p]


def test_the_codes_are_gathered_from_every_place_that_makes_one():
    """Each call that makes a problem names its code as written, but the two that pass one along (the secret's kind,
    a flow's err) — so the list below is the whole of what the read can say."""
    calls = sum(len(re.findall(r"(?<!def )(?:\b_p(?:roblem)?|\.err)\(", t)) for t in SOURCES.values())
    passed_along = ['_problem(name, path, f"secret.{kind}",', "_problem(self.name, path, code, message, severity)",
                    "M._problem(file, path, code, message, severity)", '_p(where, path, f"secret.{kind}",']
    assert all(any(s in t for t in SOURCES.values()) for s in passed_along)
    named = sum(len(LITERAL.findall(t)) for t in SOURCES.values())
    assert calls == named + len(passed_along), "a problem made with a code that is not written out: add it to this arm"
    codes = _codes()
    assert {"config.exclude", "environment.outside", "environment.none", "spec.ha"} <= codes   # the ticket's family
    assert set(R.FLOW_JA) <= codes and len(codes) >= 45
    assert set(R.MIGRATION_JA) <= codes


@pytest.mark.parametrize("code", sorted(_codes()))
def test_every_code_the_read_gives_has_words_of_its_own(code):
    words = Told()
    for p in _problems(code):
        line = R.short(p, "docs/infra", words)
        assert line != f"{WHERE}: {code}" and line != f"{R.CONFIG_NAME}: {code}"
    assert words.fell == []


def test_every_way_an_exclude_entry_is_wrong_has_its_words():
    """The whys room.py writes and the ones EXCLUDE_JA says are the same, and no two say the same."""
    written = set(re.findall(r'_exclude_problem\([^,]+,\s*"(\w+)"', SOURCES["room"]))
    assert written == set(R.EXCLUDE_JA)
    lines = [R.short(p, "docs/infra") for p in _problems("config.exclude")]
    assert len(set(lines)) == len(lines) == 5


def test_a_code_with_no_words_yet_says_its_message():
    p = {"file": "main.json", "path": "/x", "code": "something.new", "message": MESSAGE, "severity": "error"}
    assert R.short(p, "docs/infra") == f"{WHERE}: {MESSAGE}（something.new）"


def _validate(root: Path) -> tuple[int, list[str]]:
    tools = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "validate", "infra", str(root)],
                       cwd=tools, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    return r.returncode, [line for line in r.stdout.splitlines() if line.startswith(("ERROR ", "WARNING "))]


def _room(tmp_path, model: dict, config: dict | None = None) -> Path:
    root = tmp_path / "room"
    (root / "docs/infra").mkdir(parents=True)
    (root / "docs/infra/main.json").write_text(json.dumps(model))
    if config is not None:
        (root / "jui.config.json").write_text(json.dumps(config))
    return root


OK = {"version": 0, "nodes": [{"id": "api", "category": "compute.container"}]}


def test_validate_infra_tells_the_exclude_cases_apart(tmp_path):
    """The ticket's two, and the other three: each line says its case, not the code alone."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    cases = {"not_a_list": "vendor", "not_inside": ["../outside"], "no_folder": ["nope"],
             "outside_link": ["linked"], "too_many": ["kept"] * (R.EXCLUDE_MAX + 1)}
    seen = {}
    for why, exclude in cases.items():
        root = _room(tmp_path / why, OK, {"infra": {"exclude": exclude}})
        (root / "kept").mkdir()
        (root / "linked").symlink_to(outside)
        rc, lines = _validate(root)
        mine = [line for line in lines if R.EXCLUDE_JA[why] in line]
        assert len(mine) == 1 and mine[0].endswith("  [config.exclude]"), lines
        assert rc == (0 if why == "no_folder" else 1)
        seen[why] = mine[0]
    assert seen["no_folder"].startswith("WARNING jui.config.json: /infra/exclude/0 ")
    assert seen["not_inside"].startswith("ERROR jui.config.json: /infra/exclude/0 ")
    assert len(set(seen.values())) == 5


def test_validate_infra_says_the_model_codes_that_had_no_words(tmp_path):
    model = {"version": 0, "environments": [{"id": "prod", "kind": "production"}, {"id": "dev", "kind": "development"}],
             "groups": [{"id": "g", "kind": "logical", "environments": ["prod"]}],
             "nodes": [{"id": "a", "category": "compute.vm", "group": "g", "environments": ["dev"]},
                       {"id": "db", "category": "database.relational", "spec": [{"key": "deployment", "value": "Multi-AZ"}]}]}
    _rc, lines = _validate(_room(tmp_path, model))
    assert lines == [
        f"ERROR {WHERE}: /nodes/0/environments が、入れ物（親の group・辺の両端）に無い環境を名指ししています  [environment.outside]",
        f"ERROR {WHERE}: /nodes/0 は、入れ物（親の group・辺の両端）のどの環境にも無いため外します  [environment.none]",
        f"WARNING {WHERE}: /nodes/1/spec/0 の spec は Multi-AZ と言いますが ha は言いません（費用と 3D は ha を読みます: "
        "ha: multi-az と書いてください）  [spec.ha]"]


def test_a_flows_and_a_plans_step_is_said_step_not_ho():
    """The room's Japanese words say ステップ for a step (a flow's request and response, a plan's), never 歩 (requester
    10-23); 歩 as a verb (歩かない: a link not walked into) stays."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "jsonui_doc_cli" / "infra" / "room.py").read_text(encoding="utf-8")
    assert "2 ステップ" in src
    assert not re.findall(r".{0,20}歩(?![かきくけこい]).{0,10}", src)
