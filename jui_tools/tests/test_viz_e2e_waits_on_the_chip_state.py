"""The connection chip says its state in data-net (connected / connecting / reconnecting) as well as in words, and no
browser suite waits on the chip's words (ticket 2026-10-21-viz-english-screen-checks §2c): 41 waits in 29 suites
read `textContent === '接続中'`, and every one of them would wait forever on an English page."""
from __future__ import annotations

import re
from pathlib import Path

from tests.test_viz_bundle import web_text

E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"


def test_the_chip_carries_its_state_beside_its_words():
    src = web_text("js", "70-main.js")
    assert "chip.dataset.net = net;" in src
    assert re.search(r"const net = ok \? 'connected' : NET\.state === 'connecting' && !LIVE\.connectedOnce \? 'connecting' : 'reconnecting';", src)
    for state in ("connected", "connecting", "reconnecting"):
        assert f"{state}: 'net.{state}'" in src


def test_no_suite_waits_on_the_chips_words():
    said = [f"{p.name}:{n}" for p in sorted(E2E.glob("*.py")) for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if re.search(r"chip\.demo['\"]?\)?\.(textContent|innerText)", line)]
    assert said == []
    waits = sum(p.read_text(encoding="utf-8").count(".chip.demo').dataset.net === ") for p in E2E.glob("*.py"))
    assert waits >= 41
