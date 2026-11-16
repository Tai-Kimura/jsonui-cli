"""INFRA.md, the writer's guide to docs/infra (ticket 2026-10-21-agents-skills-mcp-for-server-room §3a-3): its small
room is real — the files written under <!-- file: … --> pass validate infra / infra-load / infra-prices and cost infra
as they are — and every problem code it names is one the tools say."""
from __future__ import annotations

import json
import re
from pathlib import Path

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import prices as P
from jsonui_doc_cli.infra import room as R
from jsonui_doc_cli.infra.cost import run as RUN

GUIDE = Path(__file__).resolve().parents[1] / "INFRA.md"
SOURCE = Path(__file__).resolve().parents[1] / "jsonui_doc_cli"


def _files() -> dict[str, str]:
    text = GUIDE.read_text(encoding="utf-8")
    return dict(re.findall(r"<!-- file: (\S+) -->\n```json\n(.*?)\n```", text, re.S))


def _room(tmp_path: Path) -> Path:
    for rel, body in _files().items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    return tmp_path


def test_the_guide_writes_a_model_a_load_and_a_price():
    assert sorted(_files()) == ["docs/infra/load/ordinary.json", "docs/infra/main.json", "docs/infra/prices/sendgrid.json"]
    for body in _files().values():
        json.loads(body)


def test_its_room_passes_every_check_and_is_priced(tmp_path):
    root = _room(tmp_path)
    model = R.read(root)
    assert model["ok"] and [p for p in model["problems"] if p["severity"] in ("error", "warning")] == []
    assert len(model["flows"]) == 1
    loads = L.read(root)
    assert loads["ok"] and loads["problems"] == [] and [s["id"] for s in loads["scenarios"]] == ["ordinary"]
    prices = P.read(root)
    assert prices["ok"] and prices["problems"] == []
    code, out = RUN.reply(root, env={"JUI_VIZ_HOME": "/nonexistent"})
    month = out["month"]
    assert code == 0 and month["noPrice"] == [] and month["noRule"] == ["browser"] and out["prices"]["warnings"] == []
    assert {k["key"] for k in month["keys"]} == {"aws", "sendgrid"}


def test_every_code_it_names_is_said_by_the_tools():
    named = set(re.findall(r"`((?:flow|load|spec|prices|cost)\.[a-z_.]+)`", GUIDE.read_text(encoding="utf-8")))
    said = "\n".join(p.read_text(encoding="utf-8") for p in SOURCE.rglob("*.py"))
    assert named and {c for c in named if f'"{c}"' not in said and f"[{c}]" not in said} == set()
