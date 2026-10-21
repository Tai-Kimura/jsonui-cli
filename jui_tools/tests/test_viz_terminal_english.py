"""The terminal's words are English (the requester's ruling: 端末は英語に統一 — whatever the page's language, no
dictionary). Every string literal with Japanese in the modules that print to the terminal or to serve.log is either a
docstring or text the page shows (the page's language switch translates it; listed below with where it goes). A new
Japanese line for the terminal fails here.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JA = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")

#: module -> each literal with Japanese that the page shows (whole, an f-string with {} for its values) -> where it goes
PAGE_TEXT = {   # the page's words are in the table now (web/i18n: the language switch's move); none is left here
    "jui_cli/commands/viz_cmd.py": {},
    "jui_cli/viz/config.py": {},
    "jui_cli/viz/server.py": {},
    "jui_cli/viz/hooks_installer.py": {},
}


def _docstring_lines(src: str) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def japanese_literals(path: Path) -> list[tuple[int, str]]:
    """(line, text) of each string literal with Japanese that is not a docstring; an f-string as its literal parts
    joined, with {} for each value."""
    src = path.read_text(encoding="utf-8")
    docs = _docstring_lines(src)
    tree = ast.parse(src)
    inside = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in ast.walk(n) if v is not n}
    out = []
    for n in ast.walk(tree):
        if id(n) in inside or getattr(n, "lineno", None) in docs:
            continue
        if isinstance(n, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            text = n.value
        else:
            continue
        if JA.search(text):
            out.append((n.lineno, text))
    return sorted(out)


def test_the_terminal_modules_have_no_japanese_but_the_pages_text():
    left = [f"{rel}:{line}: {text[:100]}" for rel, page in PAGE_TEXT.items()
            for line, text in japanese_literals(ROOT / rel) if text not in page]
    assert left == [], "Japanese for the terminal or serve.log (write it in English):\n" + "\n".join(left)


def test_every_page_text_listed_is_still_there():
    """A listed text that is gone (translated or moved) is taken off the list, so the list never hides a new line."""
    gone = [f"{rel}: {text}" for rel, page in PAGE_TEXT.items()
            for text in set(page) - {t for _, t in japanese_literals(ROOT / rel)}]
    assert gone == []


def test_the_gate_sees_a_japanese_log_line_an_fstring_part_and_skips_a_docstring(tmp_path):
    f = tmp_path / "m.py"
    f.write_text('"""モジュールの説明"""\n\ndef g(x):\n    """関数の説明"""\n    log("拒否")\n    print(f"ポート {x} は使用中")\n',
                 encoding="utf-8")
    assert japanese_literals(f) == [(5, "拒否"), (6, "ポート {} は使用中")]
