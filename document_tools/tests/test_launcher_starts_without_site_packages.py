"""The distributed `jsonui-doc` must start when the sibling is not installed.

`jsonui_doc_cli.validator` imports `jsonui_test_cli`, and the launcher put
only its OWN directory on `sys.path`. So the distributed copy started only
where the ambient interpreter happened to have the sibling installed — and
failed with ModuleNotFoundError before reaching any subcommand, `--version`
included, in every shell with a project venv active. That is the normal
state for a consumer.

Three lanes hit it within minutes. Two filed it; the third read the same
traceback and concluded their local install was corrupt.

Nothing caught it:

- CI pip-installs both packages from git and never runs the distributed
  launcher, so a green CI says nothing about whether the shipped copy
  starts.
- Every existing test imports `jsonui_doc_cli` directly, which never goes
  through the launcher at all.
- A shell without a venv runs it fine, which is the shell a release is
  cut from.

`-S` is the discriminator. `-I` is not: it drops PYTHONPATH and user site,
but the repo's editable install lives in system site-packages, so the
sibling stays importable and a broken launcher still passes. Measured
both.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "jsonui-doc"


def _bare_env() -> dict:
    """The environment minus every way the sibling could arrive for free.

    `-S` drops site-packages but PYTHONPATH still applies, and this suite is
    itself run with PYTHONPATH pointing at the sibling. Leaving it in made
    BOTH arms pass — the control caught it, which is what the control is
    for: without it, "the launcher adds the path" and "the environment had
    the sibling anyway" are the same green, and that is precisely how the
    defect shipped.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def test_the_launcher_runs_without_site_packages():
    proc = subprocess.run(
        [sys.executable, "-S", str(LAUNCHER), "--version"],
        capture_output=True, text=True, env=_bare_env())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "jsonui-doc" in proc.stdout


def test_it_is_the_sibling_path_that_makes_that_work():
    """The control: without the sibling on the path, `-S` must fail.

    Otherwise "the launcher starts" and "this environment would have
    imported the sibling anyway" are the same green — which is exactly how
    the defect shipped.
    """
    source = LAUNCHER.read_text(encoding="utf-8")
    broken = source.replace(
        'for _path in (_root, _root.parent / "test_tools"):',
        "for _path in (_root,):")
    assert broken != source, "the launcher no longer adds the sibling by this spelling"

    tmp = LAUNCHER.parent / ".jsonui-doc-probe"
    try:
        tmp.write_text(broken, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-S", str(tmp), "--version"],
            capture_output=True, text=True, env=_bare_env())
        assert proc.returncode != 0
        assert "jsonui_test_cli" in proc.stderr
    finally:
        tmp.unlink(missing_ok=True)
