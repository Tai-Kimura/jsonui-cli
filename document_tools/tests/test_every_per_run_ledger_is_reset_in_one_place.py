"""Every per-run ledger joins the one reset, and the reset actually empties it.

Regression: `html/sidebar.py:_REPORTED_SHARED_SLOTS` was a per-run ledger that
`reset_page_failures()` did not clear. It cleared itself inside ONE test file
instead, which reaches only the arms that remembered — the shape
`_write_stamped`'s docstring argues against two directories over ("One place,
not four call sites").

⚠️ THE POPULATION IS READ OFF THE SOURCE, NOT OFF THE REGISTRY. If this check
asked `run_state` which ledgers exist and then checked that those are
registered, it would agree with the registry no matter what either one said —
two instruments sharing one derivation are not each other's control. So the
population here comes from `ast` over the package's own files, and the
registry is the thing being measured against it.

🔻 THE HAND-WRITTEN PART IS THE EXEMPTION, NOT THE POPULATION. A name that is
module-level mutable state and is NOT per-run has to say so here, with its
reason. A new ledger added as a bare `set()` matches neither and fails — which
is what nothing did when the tenth one landed.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import run_state  # noqa: E402
from jsonui_doc_cli.test_doc import generator  # noqa: E402  (registers on import)
from jsonui_doc_cli.test_doc.html import sidebar  # noqa: E402

PKG = REPO / "document_tools" / "jsonui_doc_cli" / "test_doc"

#: Module-level mutables that are NOT per-run state, and why. Each one is
#: checked below for still existing, so this list cannot quietly rot into a
#: blanket exemption for names nobody has looked at in a year.
NOT_PER_RUN = {
    "__all__": "export list, a constant",
    "SUPPORTED_PLATFORMS": "constant table of platform names",
    "_STATUS_LABELS": "constant lookup, check report page",
    "_STATUS_LABEL": "constant lookup, unit page",
    "_STATUS_HELP": "constant lookup, unit page",
    "_REGISTRY": "the registry itself — clearing it would unregister everyone",
}

_MUTABLE_FACTORIES = {"list", "dict", "set", "OrderedDict", "defaultdict", "Counter"}


def _module_level_state() -> list[tuple[str, str, str, int]]:
    """(name, verdict, file, line) for every module-level mutable in the package.

    verdict is 'registered' or 'bare'. Read with `ast`, so a declaration is
    classified by what the SOURCE says, not by what importing it produces.
    """
    found: list[tuple[str, str, str, int]] = []
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names, value = [node.target.id], node.value
            else:
                continue
            if not names or value is None:
                continue
            rel = str(path.relative_to(PKG))
            if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                    and value.func.attr == "ledger"):
                found.append((names[0], "registered", rel, node.lineno))
                continue
            literal = isinstance(value, (ast.List, ast.Dict, ast.Set))
            factory = None
            if isinstance(value, ast.Call):
                factory = getattr(value.func, "id", None) or getattr(value.func, "attr", None)
            if literal or factory in _MUTABLE_FACTORIES:
                found.append((names[0], "bare", rel, node.lineno))
    return found


def test_every_module_level_mutable_is_registered_or_declared_not_per_run():
    unclassified = [
        (name, where, line)
        for name, verdict, where, line in _module_level_state()
        if verdict == "bare" and name not in NOT_PER_RUN
    ]
    assert not unclassified, (
        "module-level mutable state that is neither registered as a per-run "
        "ledger nor declared NOT_PER_RUN:\n" + "\n".join(
            f"  {n} at {w}:{l}" for n, w, l in unclassified) +
        "\nRegister it with run_state.ledger(globals(), \"<name>\", <factory>), "
        "or add it to NOT_PER_RUN with the reason it survives a run.")


def test_the_registration_name_matches_the_name_it_is_assigned_to():
    """A copy-pasted registration that names its neighbour registers nothing.

    The runtime cannot see this: `ledger(globals(), "_page_sources", dict)`
    assigned to `_document_referrers` clears the wrong one and both look
    populated. Only the source says which name the assignment used.
    """
    source_names = {n for n, verdict, _, _ in _module_level_state() if verdict == "registered"}
    # `external()` entries (run_log) reset themselves and are not assignments,
    # so they are not in the source population by construction. Comparing
    # against them would make this arm fail for a reason it is not about.
    runtime_names = {e.name for e in run_state.entries() if e.reset is None}
    assert source_names == runtime_names, (
        "registered-by-source and registered-at-runtime disagree: "
        f"source only={sorted(source_names - runtime_names)}, "
        f"runtime only={sorted(runtime_names - source_names)}")


def test_no_exemption_is_stale():
    live = {name for name, _, _, _ in _module_level_state()}
    stale = sorted(set(NOT_PER_RUN) - live)
    assert not stale, f"NOT_PER_RUN names that no longer exist: {stale}"


def test_the_reset_empties_every_registered_ledger():
    """Registration is a claim; this is the effect.

    Populates each ledger through the module attribute — the way the product
    reaches them — and asserts the one reset leaves nothing behind.
    """
    filler = {list: lambda v: v.append("x"), set: lambda v: v.add("x"),
              dict: lambda v: v.update({"x": 1})}
    touched = []
    for entry in run_state.entries():
        if entry.reset is not None:
            continue
        value = entry.namespace.get(entry.name)
        fill = filler.get(type(value))
        if fill is not None:
            fill(value)
        else:  # the integer counters
            entry.namespace[entry.name] = 7
        touched.append(entry)
    assert touched, "no ledgers registered — the check has nothing to measure"

    run_state.reset_per_run_ledgers()

    left = []
    for entry in touched:
        value = entry.namespace.get(entry.name)
        if value:  # non-empty container or non-zero counter
            left.append(f"{entry.name}={value!r}")
    assert not left, f"still populated after the reset: {left}"


def test_the_tenth_ledger_is_the_one_this_ticket_is_about():
    """Named, so a regression says which ledger rather than 'one of twelve'."""
    assert "_REPORTED_SHARED_SLOTS" in run_state.all_registered_names()
    sidebar._REPORTED_SHARED_SLOTS.add(("x", ()))
    run_state.reset_per_run_ledgers()
    assert sidebar._REPORTED_SHARED_SLOTS == set()


def test_the_generator_reset_is_the_registry_reset():
    """The product's entry point calls the one place, not a private copy."""
    generator._pages_written.add(Path("x"))
    generator.reset_per_run_ledgers()
    assert generator._pages_written == set()


def test_the_reset_reaches_the_state_that_resets_itself():
    """`run_log` is registered through `external()`, so the effect arm above
    — which populates ledgers through their namespace — cannot see it.

    🚨 Found by mutation, not by reading: dropping the last registry entry
    (`_REGISTRY[:-1]`) left all six arms green, because the entry it dropped
    was the one external and nothing measured it. A member of the population
    that no arm reaches is exactly this ticket's defect, one level up.
    """
    from jsonui_doc_cli import run_log

    run_log.warn("something this run found")
    assert run_log.count() > 0, "run_log did not record — the arm cannot measure"

    run_state.reset_per_run_ledgers()

    assert run_log.count() == 0
