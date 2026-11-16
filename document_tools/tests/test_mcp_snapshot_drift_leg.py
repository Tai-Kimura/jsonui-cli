"""The drift leg must count, must not judge, and must fire when told to.

Regression: shared-core-can-change-with-no-leg-that-sees-the-mcp-snapshot-drift.
`shared/core/*.json` could change with nothing reporting that the MCP server's
bundled snapshot no longer matched. Measured before this leg existed: the
release runner mentioned `shared-core|shared/core` 8 times and
`screen_identity|mcp-server` 0 times — the gate watched the other items in the
same directory and not this one.

🔻 IT REPORTS, IT DOES NOT FAIL. The snapshot can only be re-pinned after a
release exists to pin to, so between a shared/core change and the next bump the
two differ every time. A gate red by construction gets switched off, and a
switched-off gate does not report that it is off (ruling 2026-09-09, reached
independently by two lanes).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev-guide" / "release" / "check-mcp-snapshot-drift.py"


def run(repo: Path, dirs: str | None) -> str:
    env = dict(os.environ)
    if dirs is None:
        env.pop("JSONUI_MCP_SNAPSHOT_DIRS", None)
    else:
        env["JSONUI_MCP_SNAPSHOT_DIRS"] = dirs
    r = subprocess.run([sys.executable, str(SCRIPT), str(repo)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"the leg must never exit non-zero: {r.stderr}"
    return r.stdout


@pytest.fixture()
def tree(tmp_path):
    """A canon of three files and a snapshot mirroring two of them."""
    canon = tmp_path / "repo" / "shared" / "core"
    canon.mkdir(parents=True)
    for n in ("alpha.json", "beta.json", "gamma.json"):
        (canon / n).write_text(json.dumps({"n": n}), encoding="utf-8")
    data = tmp_path / "snap" / "data"
    data.mkdir(parents=True)
    for n in ("alpha.json", "beta.json"):
        (data / n).write_text(json.dumps({"n": n}), encoding="utf-8")
    src = tmp_path / "snap" / "src"
    src.mkdir(parents=True)
    (src / "loader.ts").write_text("read('alpha.json')", encoding="utf-8")
    return tmp_path / "repo", data, src


def test_it_counts_and_does_not_judge(tree):
    repo, data, src = tree
    out = run(repo, f"probe={data}:{src}")
    assert "3 file(s): 2 mirrored (2 identical, 0 differ)" in out
    for verdict in ("stale", "out of date", "FAIL", "!!"):
        assert verdict not in out, f"the leg must not print the verdict {verdict!r}"


def test_a_one_byte_change_is_detected_and_reverts(tree):
    """🔻 The positive control, on a COPY. An arm that edits the real snapshot
    to prove it works would be a worse defect than the one it tests."""
    repo, data, src = tree
    before = run(repo, f"probe={data}:{src}")
    assert "0 differ" in before

    target = data / "beta.json"
    original = target.read_text(encoding="utf-8")
    target.write_text(original + " ", encoding="utf-8")   # one byte
    during = run(repo, f"probe={data}:{src}")
    assert "1 differ" in during
    assert "DIFFERS beta.json" in during

    target.write_text(original, encoding="utf-8")
    assert "0 differ" in run(repo, f"probe={data}:{src}")


def test_the_hash_names_its_algorithm(tree):
    """Two lanes compared an md5 to a sha1 today and read it as a mismatch."""
    repo, data, src = tree
    assert "[sha256]" in run(repo, f"probe={data}:{src}")


def test_a_missing_checkout_is_not_a_count_of_zero(tree):
    repo, _data, _src = tree
    out = run(repo, "probe=/nowhere/at/all")
    assert "SKIPPED" in out
    assert "not a count of zero" in out
    assert "0 differ" not in out, "a skip must not report a comparison it never made"


def test_canon_only_says_whether_the_server_reads_it(tree):
    """🚨 'not mirrored' is two different facts and they need different fixes.

    A canon file the server never reads is correctly absent; one it DOES read
    is a mirror that was missed. Counting references on every run means the
    judgement is re-measured rather than remembered from the day it was true.
    """
    repo, data, src = tree
    out = run(repo, f"probe={data}:{src}")
    assert "CANON-ONLY gamma.json: 0 source files name it" in out

    (src / "loader.ts").write_text("read('gamma.json')", encoding="utf-8")
    out2 = run(repo, f"probe={data}:{src}")
    assert "1 source file(s) name it" in out2
    assert "MISSING" in out2


def test_unknown_reference_count_is_not_zero(tree):
    """`None` and `0` mean opposite things: nobody looked vs nobody reads it."""
    repo, data, _src = tree
    out = run(repo, f"probe={data}")
    assert "could not check" in out
    assert "0 source files name it" not in out


def test_a_snapshot_only_file_is_not_reported_as_drift(tree):
    """`coverage.json` really is in the live snapshot and comes from
    `conformance/`, not shared/core. Counting it would put a constant in every
    run and bury the file that moved."""
    repo, data, src = tree
    (data / "extra.json").write_text("{}", encoding="utf-8")
    out = run(repo, f"probe={data}:{src}")
    assert "1 snapshot-only" in out
    assert "not from shared/core" in out
    assert "1 differ" not in out
