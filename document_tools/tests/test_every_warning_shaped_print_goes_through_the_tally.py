"""Every line the gate would count as a warning is emitted through `run_log.warn`.

Static half of the B2 contract. The dynamic arm (in-process CLI run, closing
line == the gate's expression over the output) sees only the paths its
fixture reaches; this one walks the package with the AST and asks, for every
`print()` whose first argument is (partly) a string constant, whether that
string matches the gate's expression. Same-line `grep 'print(.*WARNING \\['`
missed `reproducible.py`, where the `print(` and the f-string sat on
different lines — the walk is AST on purpose.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

import jsonui_doc_cli
from jsonui_doc_cli.run_log import COUNTING_RE

PACKAGE = Path(jsonui_doc_cli.__file__).resolve().parent


def _literal_text(node: ast.AST) -> str:
    """The literal parts of a string-ish expression, concatenated."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_literal_text(v) for v in node.values)
    if isinstance(node, ast.FormattedValue):
        return ""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal_text(node.left) + _literal_text(node.right)
    return ""


def _calls(func_name: str) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            if name != func_name:
                continue
            text = _literal_text(node.args[0])
            if text:
                out.append((str(path.relative_to(PACKAGE)), node.lineno, text))
    return out


class WarningShapedLinesGoThroughTheTally(unittest.TestCase):
    def test_no_print_emits_a_line_the_gate_would_count(self):
        offenders = [(f, n, s[:60]) for f, n, s in _calls("print") if COUNTING_RE.search(s)]
        self.assertEqual(offenders, [], "these print() calls bypass run_log.warn")

    def test_the_walk_sees_the_warn_calls(self):
        # 陽性対照 on the instrument: the same walk over `warn(` finds the
        # tally's own emitters, so an empty list above is not a blind walk.
        seen = [(f, n) for f, n, s in _calls("warn") if COUNTING_RE.search(s)]
        self.assertGreaterEqual(len(seen), 10, seen)


if __name__ == "__main__":
    unittest.main()
