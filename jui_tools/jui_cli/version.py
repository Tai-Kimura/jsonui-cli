"""Toolchain version + source coordinates, resolved from the repo root.

The single source of truth for the toolchain version is the ``VERSION`` file
at the jsonui-cli root. Everything else derives from it:

- ``jui --version`` and ``setup.py`` read it at run/install time.
- The Ruby tools keep literal constants (their copies must work standalone in
  consumer projects, where the root file does not exist) — those constants are
  locked to this file by ``tests/test_version_lockstep.py``.
- ``jui sync_tool`` stamps version + source SHA into each consumer project so
  bug reports can name the exact toolchain they were produced with.

The source SHA has two providers, because the home install is not a git
checkout (``installer/bootstrap.sh`` deletes ``.git`` after cloning):

1. ``<root>/.git`` present (a dev checkout): ``git rev-parse HEAD``.
2. ``<root>/SOURCE_SHA`` file: stamped by bootstrap.sh right before it removes
   ``.git``, or by hand after an rsync from a dev checkout (dev-guide 09).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

#: jsonui-cli root for the running package (…/jui_tools/jui_cli/version.py).
_OWN_ROOT = Path(__file__).resolve().parents[2]

UNKNOWN_VERSION = "unknown"


def toolchain_root() -> Path:
    """Root directory of the jsonui-cli tree this package runs from."""
    return _OWN_ROOT


def toolchain_version(root: Path | None = None) -> str:
    """Version recorded in ``<root>/VERSION`` (``"unknown"`` if unreadable)."""
    version_file = (root or _OWN_ROOT) / "VERSION"
    try:
        text = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return UNKNOWN_VERSION
    return text or UNKNOWN_VERSION


def source_sha(root: Path | None = None) -> str | None:
    """Git SHA the tree at *root* was produced from, or None.

    A dev checkout answers from git; an installed tree (no ``.git``) answers
    from the ``SOURCE_SHA`` stamp. Git wins when both exist — the stamp can
    go stale in a checkout, git cannot.
    """
    root = root or _OWN_ROOT
    if (root / ".git").exists():
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            proc = None
        if proc and proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    stamp = root / "SOURCE_SHA"
    try:
        text = stamp.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def version_label(root: Path | None = None) -> str:
    """Human-facing ``<version> (<short sha>)`` label for --version output."""
    version = toolchain_version(root)
    sha = source_sha(root)
    if sha:
        return f"{version} ({sha[:12]})"
    return version
