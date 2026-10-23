"""The spec sheet's words in one language (requester 10-23: 「画像の中に英語と日本語混在してるの気になる」).

- The Japanese table says レイアウト, as the sheet's overview row does (panel.meta.layout): no Japanese string says
  "layout" in Latin letters.
- What is shown in Latin letters on purpose is an identifier and looks like one: a Layout row's component type beside
  its Japanese name (View beside コンテナ) is code, and the log strip's hook name (SessionStart) is in the mono font.
- The e2e pictures taken alone (spec_nest, spec_worktrees, test_tally) are in Japanese, as run.py's are: a picture
  laid beside another is in one language.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web"
E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"


def test_the_japanese_table_says_layout_in_japanese():
    ja = json.loads((WEB / "i18n" / "ja.json").read_text(encoding="utf-8"))
    latin = {k: v for k, v in ja.items() if isinstance(v, str) and re.search(r"\blayout\b", v, re.I)}
    assert latin == {}


def test_a_layout_rows_component_type_is_code():
    panel = (WEB / "js" / "50-panel.js").read_text(encoding="utf-8")
    assert '<code class="desc ty-raw">${esc(desc)}</code>' in panel


def test_the_log_strips_hook_name_is_in_the_mono_font():
    css = (WEB / "app.css").read_text(encoding="utf-8")
    rule = re.search(r"#ticker \.kind \{([^}]*)\}", css).group(1)
    assert "var(--font-mono)" in rule


def test_the_pictures_taken_alone_are_in_japanese():
    for name in ("spec_nest.py", "spec_worktrees.py", "test_tally.py"):
        assert 'os.environ.setdefault("JUI_VIZ_LANGUAGE", "ja")' in (E2E / name).read_text(encoding="utf-8"), name
