"""Moving a part's words into the table, one part a commit (ticket 2026-10-21-jui-viz-language-switch-ja-en).

    python3 tools/viz_i18n/move.py scan js/50-panel.js            # the lines that still say Japanese
    python3 tools/viz_i18n/move.py apply SPEC.py                  # one part's edits and keys, checked, then written
    python3 tools/viz_i18n/move.py check js/58-talk.js --base REV [--head REV]

A part is named from jui_cli/viz/web/ (js/58-talk.js, index.html, app.css). A spec is a Python file with
PART, EDITS = [(old, new), …] (each old found exactly once) and KEYS = {key: (en, ja)}; a key already in the table
must keep its words.

The check is the arm that the Japanese words are kept letter for letter, both ways:
- every new key's Japanese words are in the part as it was, whole: each {slot} where a ${…} stood and nothing else
  changed around it (a `…` of tlHTML read as <code>…</code>);
- every run of Japanese the part no longer says is in the Japanese words of the table.
So a word changed, dropped or added in the move is red, and so is a Japanese word removed with no key to say it.
"""
from __future__ import annotations

import argparse
import json
import re
import runpy
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
JT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(JT))
import finder  # noqa: E402
from jui_cli.viz import i18n  # noqa: E402

WEB = JT / "jui_cli" / "viz" / "web"
REPO_PREFIX = "jui_tools/jui_cli/viz/web/"


#: Reviewed moves that are not piece for piece and say the same words: (part, key or gone run) -> why. Closed: a new
#: one is red until it is reviewed and written here.
KNOWN = {
    ("js/58-talk.js", "月"): "the day's line: `${M}月${D}日` became toLocaleDateString(LOCALE, {month: 'long', day: "
                             "'numeric'}), which ja-JP writes 10月21日, the same (node, 10-21)",
    ("js/58-talk.js", "日"): "the same line as 月",
    ("js/58-talk.js", "talk.row.aria"): "the {unread} slot was a template of its own (`未読 ${c.unread}、`), now the key "
                                        "talk.row.unread, which is checked by itself",
    ("js/54-bills.js", "pr.done.set"): "was `${model}: ${{set: '保存しました', …}[op]}（次の応答から）`: the same words, "
                                       "one key a choice",
    ("js/54-bills.js", "pr.done.remove"): "as pr.done.set ('削除しました')",
    ("js/54-bills.js", "pr.done.reset"): "as pr.done.set ('既定に戻しました')",
}


def forms(value) -> list[str]:
    return list(value.values()) if isinstance(value, dict) else [value]


def _as_code(text: str) -> str:
    """tlHTML's marks as the markup they were: `a` -> <code>a</code>."""
    out, opened = [], False
    for part in re.split(r"(`)", text):
        if part == "`":
            out.append("</code>" if opened else "<code>")
            opened = not opened
        else:
            out.append(part)
    return "".join(out)


def _js_forms(text: str) -> set:
    """The words as a JS string may write them: as they are, and with \\n, \\' and \\" escapes."""
    return {text, text.replace("\n", "\\n"),
            text.replace("\\", "\\\\").replace("\n", "\\n").replace("'", "\\'").replace('"', '\\"')}


def _found(text: str, old: str) -> bool:
    """The whole words are in the old part, each {slot} where a ${…} (or a ' + … + ' join) stood, nothing else
    between: a space, a mark or a letter changed next to a slot is not found."""
    for form in _js_forms(text):
        parts = re.split(r"\{\w+\}", form)
        if len(parts) == 1:
            if form in old:
                return True
            continue
        slot = r"(?:\$\{[^`\n]{0,300}?\}|['\"`]\s*\+[^\n]{0,200}?\+\s*['\"`])"
        if re.search(slot.join(re.escape(p) for p in parts), old):
            return True
    return False


def check(name: str, old: str, new: str, ja: dict, en: dict) -> list[str]:
    """What breaks 'the Japanese words kept letter for letter' in this move of ``name`` (old -> new)."""
    problems = []
    quoted = lambda key, text: f"'{key}'" in text or f'"{key}"' in text  # noqa: E731
    added = [k for k in ja if quoted(k, new) and not quoted(k, old)]
    for key in added:
        if (name, key) in KNOWN:
            continue
        if key not in en:
            problems.append(f"{key}: no English words")
        elif i18n.shape_problem(ja[key], en[key]):
            problems.append(f"{key}: Japanese {i18n.shape_problem(ja[key], en[key])}")
        for text in forms(ja[key]):
            if not (_found(text, old) or _found(_as_code(text), old)):
                problems.append(f"{key}: {text!r} is not in {name} as it was")
    said = "\n".join(t for v in ja.values() for t in forms(v))
    gone = Counter(finder.runs(name, old)) - Counter(finder.runs(name, new))
    for run in sorted(gone):
        if run not in said and (name, run) not in KNOWN:
            problems.append(f"{name}: {run!r} is gone and no Japanese words say it")
    return problems


def table(lang: str) -> dict:
    return json.loads((WEB / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


def _git_show(rev: str, name: str) -> str:
    return subprocess.run(["git", "show", f"{rev}:{REPO_PREFIX}{name}"], cwd=JT, check=True, capture_output=True,
                          text=True).stdout


def _git_table(rev: str, lang: str) -> dict:
    return json.loads(_git_show(rev, f"i18n/{lang}.json"))


def cmd_scan(args) -> int:
    text = (WEB / args.part).read_text(encoding="utf-8")
    found = finder.lines(args.part, text)
    for n, line in found:
        print(f"{n:5d}: {line.strip()[:200]}")
    print(f"{args.part}: {len(found)} lines, {len(finder.chars(args.part, text))} Japanese characters", file=sys.stderr)
    return 0


def cmd_check(args) -> int:
    old = _git_show(args.base, args.part)
    if args.head:
        new, ja, en = _git_show(args.head, args.part), _git_table(args.head, "ja"), _git_table(args.head, "en")
    else:
        new, ja, en = (WEB / args.part).read_text(encoding="utf-8"), table("ja"), table("en")
    problems = check(args.part, old, new, ja, en)
    for p in problems:
        print(p)
    print(f"{args.part}: {'kept letter for letter' if not problems else f'{len(problems)} problem(s)'}", file=sys.stderr)
    return 1 if problems else 0


def cmd_apply(args) -> int:
    spec = runpy.run_path(args.spec)
    name = spec["PART"]
    path = WEB / name
    old = path.read_text(encoding="utf-8")
    new = old
    for before, after in spec["EDITS"]:
        n = new.count(before)
        if n != 1:
            print(f"{name}: {n} matches for {before[:80]!r}", file=sys.stderr)
            return 1
        new = new.replace(before, after)
    en, ja = table("en"), table("ja")
    for key, (e, j) in spec["KEYS"].items():
        for lang, words, value in (("en", en, e), ("ja", ja, j)):
            if key in words and words[key] != value:
                print(f"{key}: already in {lang}.json with other words", file=sys.stderr)
                return 1
            words[key] = value
    unused = [k for k in spec["KEYS"] if f"'{k}'" not in new and f'"{k}"' not in new]
    problems = [f"{k}: not used in {name}" for k in unused] + check(name, old, new, ja, en)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    for lang, words in (("en", en), ("ja", ja)):
        (WEB / "i18n" / f"{lang}.json").write_text(json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.write_text(new, encoding="utf-8")
    left = len(finder.chars(name, new))
    print(f"{name}: {len(spec['EDITS'])} edits, {len(spec['KEYS'])} keys; kept letter for letter; {left} Japanese characters left")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Move a viz part's words into web/i18n/{en,ja}.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("part")
    c = sub.add_parser("check")
    c.add_argument("part")
    c.add_argument("--base", required=True, help="the revision before the move")
    c.add_argument("--head", help="the revision after it (default: the working tree)")
    a = sub.add_parser("apply")
    a.add_argument("spec")
    args = ap.parse_args(argv)
    return {"scan": cmd_scan, "check": cmd_check, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
