"""Fail if this suite is measuring a sibling package from somewhere else.

document_tools does not run alone. It validates screen tests through
`jsonui_test_cli` and resolves project config through `jui_cli`, so a green
run here is a statement about three trees, not one. `import` resolves through
`sys.path`, and on a developer machine with the CLI installed that is
`~/.jsonui-cli` — the last RELEASE, not this checkout.

That is not hypothetical. In 1.7.35 the sibling made `source` a required key;
21 tests here should have gone red and did not, because the validator they
imported predated the requirement. The same release lost a version number to
the same shape one suite over, where the path in was `subprocess` + `PATH`
instead of `import` + `sys.path`. Two entrances, one trap, and the local
reading of both was "green".

🚨 THE POPULATION IS DERIVED, NOT LISTED. The previous version of this file
named `jsonui_test_cli` and only that. It was written after being burned by
exactly this defect, and it still left the other two packages unguarded —
because a hand-written population carries the author's blind spot into the
detector that is supposed to find it. When the population was first derived
from the tree, `jui_cli` came back resolving to `~/.jsonui-cli/jui_tools`
(an editable install pointing at the DISTRIBUTED copy, version 1.6.12), and
`jsonui_doc_cli` — the package this suite exists to test — was pinned by
nothing but the current directory. Two of the three openings were open.

⚠️ `cwd` IS THE SECOND VARIABLE. `python -m` puts the current directory at
`sys.path[0]`, so `jsonui_doc_cli` resolves correctly from
`<repo>/document_tools` and from nowhere else. `PYTHONPATH` alone does not
reproduce a run; the reproduction line below names both.

Run against this checkout with the command this file prints. CI already
satisfies it: ci.yml installs jui_tools, test_tools and document_tools
editable from the repo before this suite runs, so all three resolve inside it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# A package directory under `*_tools/` that holds arms rather than a tool.
# 🔻 Named here so the scope line can report what it SKIPPED. A guard that
# silently narrows its own population looks identical to one that found
# nothing wrong.
SUITE_DIR_NAMES = frozenset({"tests"})


def tool_packages(repo: Path) -> tuple[list[str], list[str]]:
    """Every importable package this checkout ships, read off the tree.

    Returns (checked, skipped). Derived from `*_tools/*/__init__.py`, so a
    tool added tomorrow is covered without editing this file — which is the
    property the hand-written version did not have.

    🚫 NOT from `pyproject.toml`. Only two of the three tool directories have
    one, and the one without it (`jui_tools`) is the package that was
    resolving to the distributed copy. A derivation is only as wide as its
    source: this source is the directory layout, which every tool has.
    """
    checked: set[str] = set()
    skipped: set[str] = set()
    for init in repo.glob("*_tools/*/__init__.py"):
        name = init.parent.name
        (skipped if name in SUITE_DIR_NAMES else checked).add(name)
    return sorted(checked), sorted(skipped)


def path_entry_for(repo: Path, name: str) -> Path | None:
    """The `PYTHONPATH` entry that makes `name` resolve inside this checkout."""
    for init in repo.glob(f"*_tools/{name}/__init__.py"):
        return init.parent.parent
    return None


def provenance(repo: Path, names: list[str]) -> list[tuple[str, str, str]]:
    """Where each name resolves right now: (name, verdict, detail).

    verdict is 'in' (inside this checkout), 'out' (another tree), or 'absent'.

    🔻 THREE STATES, NOT TWO. 'absent' is not a pass and not a failure: there
    is nothing to mis-measure, and the tests that need the package will fail
    on their own terms with a clearer message than one from here. Collapsing
    'absent' into either of the other two is how a guard starts lying — it
    would either block a legitimate partial install or wave through a missing
    dependency as if it had been checked.

    Uses `find_spec`, which resolves without executing the module, so asking
    the question does not have the side effects of answering it.
    """
    rows: list[tuple[str, str, str]] = []
    for name in names:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError) as exc:
            rows.append((name, "absent", f"{type(exc).__name__}: {exc}"))
            continue
        if spec is None or not spec.origin:
            rows.append((name, "absent", "no importable location"))
            continue
        resolved = Path(spec.origin).resolve()
        verdict = "in" if repo in resolved.parents else "out"
        rows.append((name, verdict, str(resolved)))
    return rows


def scope_lines(repo: Path) -> list[str]:
    """What was checked, what it resolved to, and what was deliberately not.

    ⚠️ The resolved path is printed, not just the verdict. 'absent', 'stale'
    and 'a different tree entirely' are three different problems that produce
    the same one-word answer; only the path separates them.
    """
    checked, skipped = tool_packages(repo)
    rows = provenance(repo, checked)
    lines = [f"package provenance ({len(rows)} checked, {len(skipped)} skipped)"]
    for name, verdict, detail in rows:
        mark = {"in": "ok ", "out": "!! ", "absent": "-- "}[verdict]
        lines.append(f"  {mark}{name}: {detail}")
    for name in skipped:
        lines.append(f"  .. {name}: suite directory, not a tool")
    return lines


def reproduction_line(repo: Path, names: list[str]) -> str:
    """The command that makes every named package resolve inside the checkout.

    Includes `cd`, because `python -m` puts the current directory at
    `sys.path[0]` and that is what pins this package. A `PYTHONPATH=` line on
    its own is not a reproduction.
    """
    entries = []
    for name in names:
        entry = path_entry_for(repo, name)
        if entry is not None and entry not in entries:
            entries.append(entry)
    for extra in (repo / "test_tools", repo / "jui_tools"):
        if extra.is_dir() and extra not in entries:
            entries.append(extra)
    joined = ":".join(str(e) for e in entries)
    return f"cd {repo / 'document_tools'} && PYTHONPATH={joined} python3 -m pytest"


def pytest_report_header(config):
    return scope_lines(REPO)


def pytest_configure(config):
    checked, _ = tool_packages(REPO)
    rows = provenance(REPO, checked)
    strays = [(n, d) for n, v, d in rows if v == "out"]
    if not strays:
        return
    # The scope goes in the failure too. `pytest_report_header` never runs
    # when configure raises, and the one place this list is most needed is
    # the run that stops.
    detail = "\n".join(scope_lines(REPO))
    named = ", ".join(n for n, _ in strays)
    raise pytest.UsageError(
        f"{named} resolves outside this checkout ({REPO}).\n"
        "This suite reports through those packages, so it would be measuring "
        "a different version than the one you are changing — green here would "
        "mean nothing about this tree.\n"
        f"{detail}\n"
        f"Run with:  {reproduction_line(REPO, [n for n, _ in strays])}"
    )


# --------------------------------------------------------------------------
# Module state, reset where every arm can see it.
#
# `generator` keeps nine per-run ledgers (written pages, outside writes, page
# sources, document referrers, the misfiled-directory set, two counters, the
# slot facts, the diagram errors). One place resets them —
# `reset_page_failures()` — and the product calls it once, at the top of a
# run. An arm that reaches an inner function directly does not go through
# that call, so it inherits whatever the previous arm left.
#
# 🚨 That is not hypothetical either. On 2026-09-10 an arm named
# "one directory reached twice is reported once" was passing on the ledger a
# PREVIOUS arm had populated, not on the behaviour it names: a mutation that
# suppressed every directory after the first killed it, and killed the arm
# that was supposed to catch that mutation as well. Running the arms in
# reverse order did NOT show it — each uses its own tmp_path, so the keys
# never collided. Order was not the discriminator; the mutation was.
#
# ⚠️ THE FIX BELONGS HERE, NOT IN THAT FILE. Five test files reach
# `_pre_generate_spec_docs` directly; the first repair was a fixture in one
# of them, which is the shape `_write_stamped`'s own docstring argues against
# two directories over: "One place, not four call sites. The four sites here
# are the ones that exist today; a fix applied per-site reaches only the ones
# someone remembered." Reset every ledger, for every arm, once.
@pytest.fixture(autouse=True)
def _fresh_generator_ledgers():
    from jsonui_doc_cli.test_doc import generator as _gen
    _gen.reset_page_failures()
    yield
    _gen.reset_page_failures()
