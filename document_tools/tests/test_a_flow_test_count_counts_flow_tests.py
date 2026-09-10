"""Regression: flow-tests-are-counted-but-zero-transitions-are-checked-on-a-face-using-the-fallback.

`*.test.json` under a face's test root is screen tests AND flow tests; only
`type == "flow"` is one. The checker always applied that filter — `load_flow`
returns None otherwise — but the two places that COUNTED did not. A face with
no `flows/` directory, where the fallback climbs to `tests/<app>/`, read:

    flow tests 116 in tests/admin (fallback …) checked 0 transition(s), absent 0
    WARNING [doc-diagram]: … 116 flow test file(s) not checked against a spec

with 116 screen tests and zero flow tests. `checked 0` was right; the labels
were not.

🚨 The danger is not that it reads like "no violations" — it reads like a
BACKLOG. Every face without a `flows/` directory sees a large number described
as unchecked on every run, learns to skip the line, and is not there on the day
a real one appears.

⚠️ The first version of this ticket said the opposite — that 116 flow tests
were going unchecked — and would have been implemented as "check the 116".
The center was replaced after a reviewer read the 116 files' `type` field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc.mermaid.flow_graph import flow_tests, load_flow  # noqa: E402


def _test_file(path: Path, kind: str, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"type": kind, "metadata": {"name": name}}
    if kind == "flow":
        body["steps"] = []
    else:
        body["screen_id"] = name
    path.write_text(json.dumps(body), encoding="utf-8")


def test_a_directory_of_screen_tests_holds_zero_flow_tests(tmp_path):
    """The reported shape: the fallback climbs to a directory full of screen
    tests, and the count must not describe them as flow tests."""
    root = tmp_path / "tests" / "admin"
    for i in range(5):
        _test_file(root / f"screen_{i}.test.json", "screen", f"screen_{i}")

    assert flow_tests(root) == [], "screen tests are not flow tests"
    # …and the raw glob still sees them, which is the whole point: the number
    # was coming from the glob rather than from the predicate.
    assert len(list(root.rglob("*.test.json"))) == 5


def test_flow_tests_are_counted_and_their_data_comes_back(tmp_path):
    root = tmp_path / "tests" / "user" / "flows"
    for i in range(3):
        _test_file(root / f"flow_{i}.test.json", "flow", f"flow_{i}")
    _test_file(root / "not_a_flow.test.json", "screen", "home")

    found = flow_tests(root)
    assert len(found) == 3
    assert [p.name for p, _d in found] == ["flow_0.test.json", "flow_1.test.json", "flow_2.test.json"]
    # The data is parsed once, here — which is what makes this ONE enumeration
    # rather than two that agree today.
    assert all(d.get("type") == "flow" for _p, d in found)


def test_the_count_and_the_walk_read_the_same_list(tmp_path):
    """The property the ticket is about. Not "the numbers match today" — the
    two sides must not be able to diverge, so they read one list.

    ⚠️ Both sides used to start from the same glob and part ways at the
    filter, which is why they agreed on a face with a `flows/` directory and
    disagreed on one without.
    """
    root = tmp_path / "tests" / "mixed"
    _test_file(root / "a.test.json", "flow", "a")
    for i in range(9):
        _test_file(root / f"s{i}.test.json", "screen", f"s{i}")

    enumerated = flow_tests(root)
    walked = [p for p in sorted(root.rglob("*.test.json")) if load_flow(p) is not None]
    assert [p for p, _d in enumerated] == walked
    assert len(enumerated) == 1, "nine screen tests must not inflate the count"


def test_a_missing_or_absent_directory_is_zero_not_an_error(tmp_path):
    """Both call sites reach this with a path that may not exist."""
    assert flow_tests(None) == []
    assert flow_tests(tmp_path / "no-such-dir") == []
    (tmp_path / "a_file").write_text("x", encoding="utf-8")
    assert flow_tests(tmp_path / "a_file") == [], "a file is not a directory"


def test_unparseable_and_wrongly_typed_files_are_left_out(tmp_path):
    """The predicate is `load_flow`'s, not a second copy of it."""
    root = tmp_path / "tests"
    _test_file(root / "good.test.json", "flow", "good")
    (root / "broken.test.json").write_text("{not json", encoding="utf-8")
    (root / "a_list.test.json").write_text("[]", encoding="utf-8")
    _test_file(root / "component.test.json", "component", "c")

    found = flow_tests(root)
    assert [p.name for p, _d in found] == ["good.test.json"]


def test_every_site_that_counts_or_walks_flow_tests_calls_the_one_enumeration():
    """⚠️ "It is in one place now" is not the claim. The claim is that every
    site reads it — which is a different sentence, and the one that closes.

    Three sites exist: the walk that builds the graph, the `flow tests N`
    clause, and the `no spec directory found` warning. The first always had
    the filter; the other two did not. A reviewer measured one of them and
    reported the population as one, so this arm derives the population from
    the source rather than trusting either count.

    ⚠️ `ast`, not grep: a source-reading check that matches text also matches
    the comments explaining it, and this file's own prose says
    `rglob("*.test.json")` several times.
    """
    import ast as _ast

    pkg = REPO / "document_tools" / "jsonui_doc_cli"
    raw_globs: list[str] = []
    callers: set[str] = set()
    definitions: set[str] = set()
    for path in sorted(pkg.rglob("*.py")):
        rel = str(path.relative_to(pkg))
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, _ast.FunctionDef) and node.name == "flow_tests":
                definitions.add(rel)
            if isinstance(node, _ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, _ast.Name) else getattr(fn, "attr", None)
                if name == "flow_tests":
                    callers.add(rel)
                if name == "rglob" and node.args:
                    arg = node.args[0]
                    if isinstance(arg, _ast.Constant) and arg.value == "*.test.json":
                        raw_globs.append(f"{rel}:{node.lineno}")

    # ⚠️ Defining it is not calling it. The first version of this arm asserted
    # the definition file was among the callers and went red on a correct
    # implementation — the two are different questions and need different sets.
    assert definitions == {"test_doc/mermaid/flow_graph.py"}, \
        f"the enumeration must live where load_flow does, found {sorted(definitions)}"

    # Both counting sites and the walk. `basename` is not enough: two of these
    # files are called generator.py.
    assert callers == {"test_doc/generator.py", "test_doc/mermaid/generator.py"}, \
        f"every site that counts or walks flow tests must call it, got {sorted(callers)}"

    # …and no site that asks "how many flow tests" re-globs. Three raw globs
    # remain and each answers a different question — every test file for page
    # generation, the app-owned screen scan, and the enumeration itself —
    # pinned so a fourth has to be justified rather than appearing quietly.
    assert len(raw_globs) == 3, f"a new raw *.test.json glob appeared: {raw_globs}"


def test_the_no_spec_directory_warning_counts_flow_tests_too(tmp_path, capsys):
    """The second counting site, and the worse of the two: it calls the files
    "flow test file(s) not checked against a spec", which is a claim about a
    BACKLOG, not just a wrong number.

    ⚠️ It fires on a different condition from the `flow tests N` clause — a
    group with no spec directory — so a specimen built for the first one does
    not reach it. That is why measuring one site reported the population as
    one site.
    """
    import ast as _ast

    src = (REPO / "document_tools" / "jsonui_doc_cli" / "test_doc" / "generator.py").read_text(
        encoding="utf-8")
    tree = _ast.parse(src)

    # Find the assignment that feeds the warning and check what it calls.
    found = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, _ast.Name) and tgt.id == "n_flows":
                fn = node.value.func if isinstance(node.value, _ast.Call) else None
                inner = None
                if fn is not None and getattr(fn, "id", None) == "len" and node.value.args:
                    a = node.value.args[0]
                    if isinstance(a, _ast.Call):
                        inner = getattr(a.func, "id", None) or getattr(a.func, "attr", None)
                found.append(inner)
    assert found, "the `no spec directory` warning no longer computes n_flows"
    assert all(f == "flow_tests" for f in found), \
        f"n_flows must come from the one enumeration, got {found}"
