"""The second tag gate (`dev-guide/release/check-tag-from-prev.py`), on real
git repositories built here.

Its expected values come from the previous tag, git's own range and the tag
name — never from the tag body's claims or the candidate's tree. The arms:

RANGE membership, per commit — the full body is green, including a merge
subject that names another range commit (an unanchored count reads it
twice); red for a deleted line, a deleted line plus a duplicate, a deleted
line plus an out-of-range commit (both keep the line count, which is what
the first second gate compared), an out-of-range line alone, a duplicate
alone, an unresolvable line, and a wrong or absent RANGE line; a longer
abbreviation of a listed commit is the same commit.

Stamps, derived from PREV's stamp commit on its first-parent line — the set
is the files whose line moved from the version before to PREV's (a line that
only adds PREV's version is prose, not a stamp); red for a stamp left behind
and for one of two stamp lines left behind.

History marks naming PREV's version, asymmetric — green when they survive or
when lines are added; red for a blanket bump, for a swap that keeps the
total, and for a deletion; INERT when PREV has none; a version is matched as
a whole token.

The tag's shape — annotated, PREV an ancestor, a later version compared as
numbers, the optional tested SHA; the exit status (0 / 1 / 2) from the
script run as a file; and two mutations of the gate that must flip a
verdict (membership judged by count, marks judged by total).

Run it with this tree on the path, from test_tools:

    PYTHONPATH=<repo>/test_tools:<repo>/jui_tools:<repo>/document_tools \
      python3 -m pytest tests/test_tag_gate_from_prev.py

This file loads the gate from this tree by path, so it does not need the
path itself — but the rest of test_tools does: without it, jsonui_doc_cli is
imported from the distributed copy (~/.jsonui-cli/document_tools), and a run
of the whole directory measures that release, not this tree (2026-09-25: 65
failed that way, 0 with the path).
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev-guide/release/check-tag-from-prev.py"

PP, OLD, NEW = "1.9.9", "1.9.10", "1.9.11"
STAMPS = ["VERSION", "lib/version.rb", "pyproject.toml"]
MARK = f"As of {OLD} the answer is cached."


def _load(source: str | None = None):
    spec = importlib.util.spec_from_file_location("check_tag_from_prev_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    if source is None:
        spec.loader.exec_module(module)
    else:
        exec(compile(source, str(SCRIPT), "exec"), module.__dict__)
    return module


gate = _load()

ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "gate", "GIT_AUTHOR_EMAIL": "gate@example.invalid",
    "GIT_COMMITTER_NAME": "gate", "GIT_COMMITTER_EMAIL": "gate@example.invalid",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=ENV).stdout.rstrip("\n")


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str, files: dict[str, str] | None = None) -> str:
    if files:
        _write(repo, files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _stamped(version: str, pyproject_pin: str | None = None) -> dict[str, str]:
    pin = pyproject_pin or version
    return {
        "VERSION": f"{version}\n",
        "lib/version.rb": f"VERSION = '{version}'\n",
        "pyproject.toml": f'version = "{version}"\ndeps = ["sib @ git+x@v{pin}#sub"]\n',
    }


def _tag(repo: Path, name: str, body: str, target: str = "HEAD") -> None:
    msg = repo / ".tagmsg"
    msg.write_text(body, encoding="utf-8")
    _git(repo, "tag", "-f", "-a", name, "-F", str(msg), target)
    msg.unlink()


def _body(repo: Path, prev: str, lines: list[str] | None = None, declared: int | None = None,
          range_line: bool = True) -> str:
    listing = lines if lines is not None else _git(repo, "log", "--format=  %h %s", f"{prev}..HEAD").splitlines()
    count = declared if declared is not None else int(_git(repo, "rev-list", "--count", f"{prev}..HEAD"))
    head = f"RANGE: {count} commit{'s' if count != 1 else ''} since {prev}\n" if range_line else ""
    return f"v{NEW} — a release\n\n{head}" + "\n".join(listing) + "\n"


def _repo(tmp_path: Path, *, mark: bool = True, bump: dict[str, str] | None = None,
          after_bump: dict[str, str] | None = None) -> dict:
    """base (PP) -> stamp commit (OLD, plus the prose mark) -> tag PREV ->
    m1 on main, s1 on a side branch, a merge whose subject names s1 -> the
    NEW stamp commit (or `bump`) -> tag NEW with an honest body."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "base", {**_stamped(PP), "README.md": "hello\n",
                           "docs/history.md": f"Until {PP} this returned None.\n"})
    history = f"Until {PP} this returned None.\n" + (f"{MARK}\n" if mark else "")
    _commit(repo, f"{OLD}: stamp", {**_stamped(OLD), "docs/history.md": history})
    _tag(repo, f"v{OLD}", f"v{OLD}\n")
    m1 = _commit(repo, "feature: m1", {"README.md": "hello m1\n"})
    _git(repo, "checkout", "-q", "-b", "side", f"v{OLD}")
    s1 = _commit(repo, "side: s1", {"side.txt": "s1\n"})
    _git(repo, "checkout", "-q", "main")
    s1_short = _git(repo, "rev-parse", "--short", s1)
    _git(repo, "merge", "-q", "--no-ff", "-m", f"Merge commit '{s1_short}' into main", s1)
    merge = _git(repo, "rev-parse", "HEAD")
    release = _commit(repo, f"{NEW}: stamp", bump if bump is not None else _stamped(NEW))
    if after_bump:
        _commit(repo, "after", after_bump)
    _tag(repo, f"v{NEW}", _body(repo, f"v{OLD}"))
    return {"repo": repo, "prev": f"v{OLD}", "tag": f"v{NEW}", "m1": m1, "s1": s1,
            "s1_short": s1_short, "merge": merge, "release": release}


def _run(module, capsys, *argv) -> tuple[int, str]:
    rc = module.main([str(a) for a in argv])
    return rc, capsys.readouterr().out


def _retag(r: dict, body: str) -> None:
    _tag(r["repo"], r["tag"], body)


def _listing(r: dict) -> list[str]:
    return _git(r["repo"], "log", "--format=  %h %s", f"{r['prev']}..HEAD").splitlines()


def _fails(out: str) -> list[str]:
    # The numbered check lines only: the closing line "… 11 PASS / 1 FAIL of
    # 12" contains " FAIL " too.
    return [line for line in out.splitlines() if re.match(r"^\s+\d+ FAIL ", line)]


# ------------------------------------------------------------ RANGE -------

def test_the_full_body_is_green_and_every_count_is_printed(tmp_path, capsys):
    r = _repo(tmp_path)
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 0, out
    assert "range: expected 4 (from rev-list) | lines 4 | missing 0 extra 0 duplicate 0 unresolved 0" in out
    assert "ALL CHECKS PASSED" in out


def test_a_merge_subject_naming_another_range_commit_is_not_a_listing(tmp_path, capsys):
    r = _repo(tmp_path)
    body = _git(r["repo"], "cat-file", "tag", r["tag"])
    # The specimen is at the discriminating position: an unanchored count of
    # s1's short SHA over the body reads 2 (its listing line and the merge
    # subject), which is what made v1.8.119's six false reds.
    assert body.count(r["s1_short"]) == 2
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 0 and "duplicate 0" in out, out


def _drop(lines: list[str], sha: str) -> list[str]:
    kept = [line for line in lines if not line.startswith(f"  {sha[:7]}")]
    assert len(kept) == len(lines) - 1
    return kept


@pytest.mark.parametrize("mutation, want", [
    ("delete s1", "lines 3 | missing 1 extra 0 duplicate 0 unresolved 0"),
    ("delete s1, duplicate m1", "lines 4 | missing 1 extra 0 duplicate 1 unresolved 0"),
    ("delete s1, add PREV's commit", "lines 4 | missing 1 extra 1 duplicate 0 unresolved 0"),
    ("add PREV's commit", "lines 5 | missing 0 extra 1 duplicate 0 unresolved 0"),
    ("duplicate m1", "lines 5 | missing 0 extra 0 duplicate 1 unresolved 0"),
    ("add an unresolvable line", "lines 5 | missing 0 extra 0 duplicate 0 unresolved 1"),
])
def test_membership_is_judged_per_commit(tmp_path, capsys, mutation, want):
    r = _repo(tmp_path)
    lines = _listing(r)
    m1_line = next(line for line in lines if line.startswith(f"  {r['m1'][:7]}"))
    prev_line = _git(r["repo"], "log", "-1", "--format=  %h %s", r["prev"])
    mutated = {
        "delete s1": _drop(lines, r["s1"]),
        "delete s1, duplicate m1": _drop(lines, r["s1"]) + [m1_line],
        "delete s1, add PREV's commit": _drop(lines, r["s1"]) + [prev_line],
        "add PREV's commit": lines + [prev_line],
        "duplicate m1": lines + [m1_line],
        "add an unresolvable line": lines + ["  0123456789ab not a commit here"],
    }[mutation]
    # The RANGE line stays honest, so the listing arm alone must see it.
    _retag(r, _body(r["repo"], r["prev"], mutated))
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 1, out
    assert want in out, out
    assert [line for line in _fails(out)] == [
        line for line in _fails(out) if "every range commit is listed once" in line], out


def test_a_prose_line_naming_a_range_commit_is_not_a_listing(tmp_path, capsys):
    r = _repo(tmp_path)
    m1_short = _git(r["repo"], "rev-parse", "--short", r["m1"])
    body = _body(r["repo"], r["prev"]) + f"\nWhy: the fix in {m1_short} is kept, and\n  {m1_short} was measured again.\n"
    # The second prose line starts with two spaces and a hex word: only the
    # listing shape "  <hex> <subject>" with the hex resolving counts, and
    # this one resolves — so it is a listing, and m1 is listed twice.
    _retag(r, body)
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 1 and "duplicate 1" in out, out
    _retag(r, _body(r["repo"], r["prev"]) + f"\nWhy: the fix in {m1_short} is kept.\n")
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 0 and "duplicate 0" in out, out


def test_a_longer_abbreviation_is_the_same_commit(tmp_path, capsys):
    r = _repo(tmp_path)
    lines = [f"  {r['m1'][:12]} feature: m1" if line.startswith(f"  {r['m1'][:7]}") else line
             for line in _listing(r)]
    assert any(line.startswith(f"  {r['m1'][:12]} ") for line in lines)
    _retag(r, _body(r["repo"], r["prev"], lines))
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 0, out


@pytest.mark.parametrize("variant, detail", [
    ("declares one more", "declared (5, 'v1.9.10'), rev-list 4 since v1.9.10"),
    ("no RANGE line", "declared None, rev-list 4 since v1.9.10"),
    ("the right count since another tag", "declared (4, 'v1.9.9'), rev-list 4 since v1.9.10"),
])
def test_the_range_line_is_checked_against_rev_list(tmp_path, capsys, variant, detail):
    r = _repo(tmp_path)
    body = {
        "declares one more": lambda: _body(r["repo"], r["prev"], declared=5),
        "no RANGE line": lambda: _body(r["repo"], r["prev"], range_line=False),
        "the right count since another tag":
            lambda: _body(r["repo"], r["prev"]).replace(f"since {r['prev']}", "since v1.9.9"),
    }[variant]()
    _retag(r, body)
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 1
    assert len(_fails(out)) == 1 and detail in _fails(out)[0], out


# ------------------------------------------------------------ stamps ------

def test_the_stamp_set_is_derived_from_prevs_stamp_commit(tmp_path, capsys):
    r = _repo(tmp_path)
    commit = gate.stamp_commit(str(r["repo"]), r["prev"])
    # docs/history.md gained a line naming OLD in the same commit, without
    # losing one naming PP: prose, not a stamp.
    assert gate.stamps_from(str(r["repo"]), commit, PP, OLD) == sorted(STAMPS)
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert f"({PP} -> {OLD}, first-parent): 3 file(s)" in out
    assert f"stamp pyproject.toml — v{OLD} had {OLD}x2; v{NEW} has {NEW}x2 {OLD}x0" in out


def test_the_stamp_commit_is_on_prevs_first_parent_line(tmp_path):
    # PREV's stamp arrives by a merge of a side-branch bump (the shape of a
    # stamp re-applied by cherry-pick on a train branch). The first-parent
    # answer is the merge; without --first-parent git follows the side commit.
    repo = tmp_path / "fp"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "base", _stamped(PP))
    _git(repo, "checkout", "-q", "-b", "train")
    side = _commit(repo, f"{OLD}: stamp (cherry-picked)", _stamped(OLD))
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge branch 'train'", "train")
    merge = _git(repo, "rev-parse", "HEAD")
    _tag(repo, f"v{OLD}", f"v{OLD}\n")
    assert _git(repo, "log", "-1", "--format=%H", f"v{OLD}", "--", "VERSION") == side
    assert gate.stamp_commit(str(repo), f"v{OLD}") == merge
    assert gate.stamps_from(str(repo), merge, PP, OLD) == sorted(STAMPS)


@pytest.mark.parametrize("bump, stamp, detail", [
    ({**_stamped(NEW), "lib/version.rb": f"VERSION = '{OLD}'\n"}, "lib/version.rb",
     f"v{NEW} has {NEW}x0 {OLD}x1"),
    (_stamped(NEW, pyproject_pin=OLD), "pyproject.toml", f"v{NEW} has {NEW}x1 {OLD}x1"),
    # The new line was added and the old one kept: the NEW count is right, so
    # only "no OLD left" sees it.
    ({**_stamped(NEW), "VERSION": f"{NEW}\n{OLD}\n"}, "VERSION", f"v{NEW} has {NEW}x1 {OLD}x1"),
    # A stamp line deleted outright: no OLD is left, so only "as many NEW as
    # PREV had OLD" sees it.
    ({**_stamped(NEW), "pyproject.toml": f'version = "{NEW}"\n'}, "pyproject.toml",
     f"v{NEW} has {NEW}x1 {OLD}x0"),
])
def test_a_stamp_left_behind_is_red(tmp_path, capsys, bump, stamp, detail):
    r = _repo(tmp_path, bump=bump)
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 1
    assert len(_fails(out)) == 1 and f"stamp {stamp} " in _fails(out)[0] and detail in _fails(out)[0], out


# ------------------------------------------------------------ marks -------

def test_marks_that_survive_or_are_added_are_green(tmp_path, capsys):
    r = _repo(tmp_path, after_bump={"docs/new.md": f"Since {OLD} a new note.\n"})
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 0, out
    assert f"marks naming {OLD} outside the stamps: v{OLD}=1 v{NEW}=2 | gone 0 added 1" in out


@pytest.mark.parametrize("change, kind, counts", [
    ({"docs/history.md": f"Until {PP} this returned None.\nAs of {NEW} the answer is cached.\n"},
     "BUMPED", f"v{OLD}=1 v{NEW}=0 | gone 1 added 0"),
    ({"docs/history.md": f"Until {PP} this returned None.\nAs of {NEW} the answer is cached.\n",
      "docs/other.md": f"Since {OLD} another note.\n"},
     "BUMPED", f"v{OLD}=1 v{NEW}=1 | gone 1 added 1"),
    ({"docs/history.md": f"Until {PP} this returned None.\n"}, "GONE", f"v{OLD}=1 v{NEW}=0 | gone 1 added 0"),
])
def test_a_rewritten_or_removed_mark_is_red(tmp_path, capsys, change, kind, counts):
    r = _repo(tmp_path, bump={**_stamped(NEW), **change})
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 1
    assert counts in out, out
    assert f"{kind:6s} x1 docs/history.md: {MARK}" in out, out
    assert len(_fails(out)) == 1 and "survives" in _fails(out)[0], out


def test_no_mark_at_prev_is_inert_not_a_pass_by_accident(tmp_path, capsys):
    r = _repo(tmp_path, mark=False)
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 0
    assert f"v{OLD} has no mark naming {OLD}: this arm is INERT" in out


@pytest.mark.parametrize("line, hit", [
    (f"As of {OLD} x", True), (f"v{OLD}", True), (f"({OLD})", True),
    (f"{OLD}0 is another version", False), (f"1{OLD} is another version", False),
    (f"{OLD[:-1]} is a prefix", False),
])
def test_a_version_is_matched_as_a_whole_token(line, hit):
    assert bool(gate.mentions(OLD).search(line)) is hit


# ------------------------------------------------------------ shape -------

def test_a_lightweight_tag_is_red(tmp_path, capsys):
    r = _repo(tmp_path)
    _git(r["repo"], "tag", "-d", r["tag"])
    _git(r["repo"], "tag", r["tag"])
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 1 and "FAIL [from the tag] v1.9.11 is an annotated tag object" in out, out


def test_prev_must_be_an_ancestor_and_older(tmp_path, capsys):
    r = _repo(tmp_path)
    rc, out = _run(gate, capsys, r["repo"], r["tag"], r["prev"])
    assert rc == 1
    assert f"FAIL [from PREV] {r['tag']} is an ancestor of {r['prev']}" in out, out
    assert "FAIL [from the tag] v1.9.10 names a later version than v1.9.11" in out, out


def test_an_empty_range_is_red(tmp_path, capsys):
    r = _repo(tmp_path)
    rc, out = _run(gate, capsys, r["repo"], r["tag"], r["tag"])
    assert rc == 1
    assert "FAIL [from rev-list] the range v1.9.11..v1.9.11 is not empty — 0 commit(s)" in out, out


def test_no_version_file_at_prev_is_red_not_an_empty_pass(tmp_path, capsys):
    repo = tmp_path / "nv"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "base", {"lib/version.rb": f"VERSION = '{OLD}'\n"})
    _tag(repo, f"v{OLD}", f"v{OLD}\n")
    _commit(repo, "bump", {"lib/version.rb": f"VERSION = '{NEW}'\n"})
    _tag(repo, f"v{NEW}", _body(repo, f"v{OLD}"))
    rc, out = _run(gate, capsys, repo, f"v{OLD}", f"v{NEW}")
    assert rc == 1
    assert "FAIL [from PREV] v1.9.10:VERSION says 1.9.10 — read <none>" in out, out
    assert "FAIL [from PREV] the stamp set is derived and contains VERSION — 0 file(s)" in out, out


@pytest.mark.parametrize("prev, tag, later", [
    ("v1.9.0", "v1.12.0", True),     # as strings '1.12.0' < '1.9.0'
    ("v1.9.9", "v1.9.10", True),
    ("v1.9.10", "v1.9.10", False),
    ("v2.0.0", "v1.99.99", False),
])
def test_versions_compare_as_numbers(prev, tag, later):
    assert gate.later(prev, tag) is later


def test_a_tag_name_that_is_not_a_version_is_none():
    assert gate.version_of("v1.9") is None and gate.version_of("release") is None


def test_the_tested_sha_is_hand_supplied_and_compared(tmp_path, capsys):
    r = _repo(tmp_path)
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"], r["release"])
    assert rc == 0 and "PASS [HAND-SUPPLIED] v1.9.11 peels to the tested commit" in out, out
    rc, out = _run(gate, capsys, r["repo"], r["prev"], r["tag"], r["merge"])
    assert rc == 1 and "FAIL [HAND-SUPPLIED]" in out, out


# ------------------------------------------------------------ the file ----

def test_the_exit_status_is_the_verdict_when_run_as_a_file(tmp_path):
    r = _repo(tmp_path)
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *map(str, a)],
                                    capture_output=True, text=True)
    assert run(r["repo"], r["prev"], r["tag"]).returncode == 0
    _retag(r, _body(r["repo"], r["prev"], _drop(_listing(r), r["s1"])))
    assert run(r["repo"], r["prev"], r["tag"]).returncode == 1
    usage = run(r["repo"], r["prev"])
    assert usage.returncode == 2 and "Usage: check-tag-from-prev.py" in usage.stderr


# ------------------------------------------------------------ mutations ---

MEMBERSHIP = 'not (sets["missing"] or sets["extra"] or sets["duplicate"] or sets["unresolved"])'
MARKS_JUDGED = "not gone,"


@pytest.mark.parametrize("name, find, replace, arm", [
    ("membership judged by count", MEMBERSHIP, 'sets["listed_lines"] == len(sets["expected"])',
     "delete s1, duplicate m1"),
    ("marks judged by total", MARKS_JUDGED, "sum(a.values()) <= sum(b.values()),", "swap"),
])
def test_a_mutation_of_the_gate_flips_a_verdict(tmp_path, capsys, name, find, replace, arm):
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count(find) == 1, name
    mutant = _load(source.replace(find, replace))
    if arm == "swap":
        r = _repo(tmp_path, bump={**_stamped(NEW),
                                  "docs/history.md": f"Until {PP} this returned None.\nAs of {NEW} the answer is cached.\n",
                                  "docs/other.md": f"Since {OLD} another note.\n"})
    else:
        r = _repo(tmp_path)
        lines = _listing(r)
        m1_line = next(line for line in lines if line.startswith(f"  {r['m1'][:7]}"))
        _retag(r, _body(r["repo"], r["prev"], _drop(lines, r["s1"]) + [m1_line]))
    assert _run(gate, capsys, r["repo"], r["prev"], r["tag"])[0] == 1
    rc, out = _run(mutant, capsys, r["repo"], r["prev"], r["tag"])
    assert rc == 0, f"{name}: the mutant should pass what the gate refuses\n{out}"
