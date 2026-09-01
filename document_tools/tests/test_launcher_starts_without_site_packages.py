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

import json
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
    needle = "if _sibling.is_dir() and str(_sibling) not in sys.path:"
    assert needle in source, "the launcher no longer adds the sibling by this spelling"
    broken = source.replace(needle, "if False:")

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


def test_every_subcommand_reaches_its_own_module_tree():
    """`--version` answering is a weaker claim than the ticket makes.

    Under the defect as reported these are redundant: the chain died in
    `jsonui_doc_cli.cli`, so `--version` and every subcommand failed at the
    same import, and the red-check confirms that — removing the sibling
    reddens all five of these along with the arm above.

    What they guard is the next one. `check` and `generate` pull their own
    module trees behind them, and `validator.py` is not the only place in
    this package that reaches across to `jsonui_test_cli`
    (`test_doc/markdown/generator.py` does too). A cross-package import
    added below a subcommand would leave the arm above green while the
    thing two lanes actually run stays broken — which is the shape of the
    failure this file exists for, one level down.
    """
    for subcommand in ("init", "validate", "rules", "generate", "check"):
        proc = subprocess.run(
            [sys.executable, "-S", str(LAUNCHER), subcommand, "--help"],
            capture_output=True, text=True, env=_bare_env())
        assert proc.returncode == 0, (
            f"{subcommand}: " + proc.stdout + proc.stderr)


def test_the_launchers_own_tree_resolves_before_the_siblings():
    """Own tree first. The tuple reads in the opposite order on purpose.

    `sys.path.insert(0, ...)` puts the LAST iterated entry in front, so the
    fix that added the sibling also put the sibling ahead of this package's
    own directory. `tests` is the one top-level name that exists in both
    trees, and a bare `import tests` from here resolved into test_tools/.
    Nothing shipped imports it, so this asserts an order rather than a
    repaired failure — the point is that the next reader of that tuple sees
    the reversal stated instead of having to derive it.
    """
    source = LAUNCHER.read_text(encoding="utf-8")
    marker = "from jsonui_doc_cli.cli import main"
    assert marker in source, "the launcher no longer imports by this spelling"

    probe_src = source.split(marker)[0] + "import json\nprint(json.dumps(sys.path[:2]))\n"
    probe = LAUNCHER.parent / ".jsonui-doc-order-probe"
    try:
        probe.write_text(probe_src, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-S", str(probe)],
            capture_output=True, text=True, env=_bare_env())
        assert proc.returncode == 0, proc.stdout + proc.stderr
        first, second = json.loads(proc.stdout)
    finally:
        probe.unlink(missing_ok=True)

    assert Path(first).name == "document_tools", (
        f"own tree must resolve first, got {first}")
    assert Path(second).name == "test_tools", (
        f"sibling must resolve second, got {second}")
