"""The page's choice of a spirit and its words (45-spirits.js, run in node; ticket 2026-10-21-jui-viz-skill-spirit).

spiritPick: at each skill's start, the models naming the skill first, else the ones naming none; weighted, weight 0
never. spiritWords: a model's words in the page's language, else ja, else the first written; a string or lines as
they are. The rest of the page (loading, wearing, the bubble, the cap of four) is the e2e's: --only spirits.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from tests.test_viz_bundle import _match, web_text


def _run(expr: str, language: str = "en"):
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    src = web_text("js", "45-spirits.js")
    parts = []
    for name in ("spiritPick", "spiritWords"):
        start = re.search(rf"\nfunction {name}\(", src).start() + 1
        parts.append(src[start:_match(src, src.index("{", start)) + 1])
    script = f"const I18N = {{ language: {json.dumps(language)} }};\n" + "\n".join(parts) + f"\nprocess.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


LIST = """[{ id: 'a', skills: ['code-review'], weight: 1 }, { id: 'b', skills: [], weight: 3 }, { id: 'c', weight: 1 },
           { id: 'z', skills: [], weight: 0 }, { id: 'd', skills: ['claude-api', 'code-review'], weight: 1 }]"""


def test_the_models_naming_the_skill_come_first():
    got = _run(f"[0, 0.49, 0.5, 0.99].map((x) => spiritPick({LIST}, 'code-review', () => x).id)")
    assert got == ["a", "a", "d", "d"]


def test_a_skill_no_model_names_takes_the_ones_naming_none_by_weight_and_never_weight_0():
    # b weighs 3 and c 1 of 4: b below 0.75, c from it; z (weight 0) is never chosen
    got = _run(f"[0, 0.74, 0.75, 0.999].map((x) => spiritPick({LIST}, 'other', () => x).id)")
    assert got == ["b", "b", "c", "c"]
    assert _run("spiritPick([{ id: 'z', weight: 0 }], 'x', () => 0.5)") is None


def test_the_words_follow_the_page_s_language_then_ja_then_the_first():
    words = "{ ja: '筆を執る', en: 'Taking up the brush', fr: 'x' }"
    assert _run(f"spiritWords({words})", "en") == "Taking up the brush"
    assert _run(f"spiritWords({words})", "de") == "筆を執る"
    assert _run("spiritWords({ fr: 'premier', de: 'zweite' })", "en") == "premier"
    assert _run("[spiritWords('as written'), spiritWords(['one', 'two']), spiritWords(null)]") == ["as written", ["one", "two"], ""]
