"""Which of a browser suite's Japanese words are the page's words, and their key (ticket
2026-10-21-viz-english-screen-checks §2c) — the list a person works from when moving a suite to T(key).

    python3 tools/viz_e2e/words_to_keys.py live.py notify.py      # or no names: every suite, counts only
    python3 tools/viz_e2e/words_to_keys.py --json live.py

Each string literal in the suite's code (not comments, not docstrings) that holds Japanese is looked up in the
Japanese table: words equal to a key's words -> T("key"); words that are a key's words with its {slots} filled ->
T("key", slot=...), marked "slots" (a pattern can match words that are not that key's: look); words found inside a longer literal (an `in` or `includes` check) -> the key, marked "part";
two keys with the same words -> every key, marked "ambiguous"; none -> "not the page's" (the content a suite
gives the page — a question, a prompt — or words to look at by hand). It writes nothing.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from jui_cli.viz import i18n  # noqa: E402

JA = re.compile(r"[぀-ヿ㐀-鿿！-｠]")
SLOT = re.compile(r"\{(\w+)\}")


def _forms(value) -> list[str]:
    return list(value.values()) if isinstance(value, dict) else [value]


def table() -> tuple[dict[str, list[str]], list[tuple[str, re.Pattern, list[str]]]]:
    """words -> keys (no slot), and (key, pattern, slot names) for words with slots."""
    exact: dict[str, list[str]] = {}
    slotted = []
    for key, value in i18n.bundled("ja").items():
        for words in _forms(value):
            names = SLOT.findall(words)
            if not names:
                exact.setdefault(words, []).append(key)
            elif JA.search(SLOT.sub("", words)):
                parts = SLOT.split(words)
                pattern = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)" for i, p in enumerate(parts))
                try:
                    slotted.append((key, re.compile(f"^{pattern}$"), names))
                except re.error:   # a slot twice in one words
                    pass
    return exact, slotted


def literals(path: Path) -> list[tuple[int, str]]:
    """(line, value) of each str literal with Japanese in the code (docstrings left out)."""
    src = path.read_text(encoding="utf-8")
    docs = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docs.add(first.lineno)
    out = []
    middle = getattr(tokenize, "FSTRING_MIDDLE", None)   # 3.12+: an f-string's words are tokens of their own
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.start[0] in docs or tok.type not in (tokenize.STRING, middle):
            continue
        if tok.type == middle:
            value = tok.string
        else:
            try:
                value = ast.literal_eval(tok.string)
            except (ValueError, SyntaxError):
                value = tok.string   # an f-string before 3.12: read as written
        if isinstance(value, str) and JA.search(value):
            out.append((tok.start[0], value))
    return out


def classify(value: str, exact, slotted) -> dict:
    if value in exact:
        keys = exact[value]
        return {"kind": "ambiguous" if len(keys) > 1 else "key", "keys": keys,
                "use": f'T("{keys[0]}")' if len(keys) == 1 else None}
    for key, pattern, names in slotted:
        m = pattern.match(value)
        if m:
            args = ", ".join(f'{n}={m.group(n)!r}' for n in dict.fromkeys(names))
            return {"kind": "slots", "keys": [key], "use": f'T("{key}", {args})'}
    inside = [k for w, ks in exact.items() if len(w) >= 3 and JA.search(w) and w in value for k in ks]
    if inside:
        return {"kind": "part", "keys": sorted(set(inside))[:5], "use": None}
    return {"kind": "not the page's", "keys": [], "use": None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A suite's Japanese words and the table's keys for them")
    ap.add_argument("suites", nargs="*", help="suite files (default: every *.py here, counts only)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    exact, slotted = table()
    files = [HERE / s for s in a.suites] if a.suites else sorted(p for p in HERE.glob("*.py") if p.name != Path(__file__).name)
    report = {}
    for f in files:
        report[f.name] = [{"line": n, "words": v, **classify(v, exact, slotted)} for n, v in literals(f)]
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    for name, rows in report.items():
        counts = {k: sum(1 for r in rows if r["kind"] == k) for k in ("key", "slots", "part", "ambiguous", "not the page's")}
        if not rows:
            continue
        print(f"{name}: " + ", ".join(f"{k} {n}" for k, n in counts.items()))
        if a.suites:
            for r in rows:
                print(f"  {r['line']:>5} {r['kind']:<15} {r['words'][:60]!r} -> {r['use'] or ', '.join(r['keys']) or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
