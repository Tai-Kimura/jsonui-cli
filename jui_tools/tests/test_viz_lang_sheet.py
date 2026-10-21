"""tools/viz_e2e/lang_sheet.py (ticket 2026-10-21-viz-english-screen-checks §2d): the shots of a Japanese run and an
English run side by side in one HTML file, with what screen_check found on the English page — one file that opens
by itself (pictures inside it), to share with the people who look."""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"))
import lang_sheet  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
EN_REPORT = {"lang": "en", "keys": ["#rb-title: panel.rb.title"], "japanese": ["span.who: 太郎"],
             "overflow": [{"at": "button.wb-btn", "text": "Back to the room (Esc)", "over": 14}],
             "canvas": [{"text": "Server ro…", "left": 10, "right": 240, "canvas": 256, "font": "36px x", "maxWidth": None},
                        {"text": "A very long sign", "left": 0, "right": 300, "canvas": 256, "font": "36px x", "maxWidth": None}]}


def _run(root: Path, language: str, entries: dict[str, dict]) -> Path:
    folder = root / "demo" / "server-room" / "shots"
    folder.mkdir(parents=True)
    for name in entries:
        (folder / f"{name}.png").write_bytes(PNG)
    (folder / "shots.json").write_text(json.dumps({n: {"language": language, "report": r} for n, r in entries.items()}))
    return root


def test_the_sheet_pairs_each_shot_and_lists_what_the_english_page_had(tmp_path):
    ja = _run(tmp_path / "ja", "ja", {"door": {"lang": "ja"}, "board": {"lang": "ja"}})
    en = _run(tmp_path / "en", "en", {"door": EN_REPORT})
    page = lang_sheet.build(ja, en)
    assert page.startswith("<!doctype html>") and "<title>viz English check</title>" in page
    assert page.count("data:image/png;base64,") == 3 and "no picture" in page        # board has no English shot
    assert "panel.rb.title" in page and "Back to the room (Esc)" in page and "(14px over)" in page
    assert "“Server ro…” cut" in page and "“A very long sign” past the edge (0–300 of 256px" in page
    assert "span.who: 太郎" in page
    summary = re.search(r'<a href="#s-door">door</a></td>(.*?)</tr>', page).group(1)
    assert re.findall(r">(\d+)<", summary) == ["1", "1", "2", "1"]
    assert "Nothing found on the English page." in page                               # board: nothing reported
    assert "src=\"http" not in page and "<script" not in page                        # opens by itself


def test_the_words_of_a_report_are_escaped(tmp_path):
    ja = _run(tmp_path / "ja", "ja", {"x": {}})
    en = _run(tmp_path / "en", "en", {"x": {"japanese": ["<img src=x onerror=alert(1)>"]}})
    page = lang_sheet.build(ja, en)
    assert "<img src=x" not in page and "&lt;img src=x onerror=alert(1)&gt;" in page


def test_the_command_writes_the_file(tmp_path):
    ja = _run(tmp_path / "ja", "ja", {"x": {}})
    en = _run(tmp_path / "en", "en", {"x": {}})
    out = tmp_path / "sheet.html"
    assert lang_sheet.main([str(ja), str(en), "-o", str(out)]) == 0 and out.read_text().count("data:image/png") == 2
