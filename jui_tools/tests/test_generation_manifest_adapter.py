"""The adapter degrades by saying so, rather than by raising or lying.

`jui_cli.core.generation_manifest` stopped being the rule on 2026-09-09 and
became a thin re-export of `shared/core/generation_manifest.py`. Two things
have to hold for that to be safe, and only the first is obvious:

  1. in a tree that HAS `shared/core`, every name the callers import still
     resolves to the real rule;
  2. in a tree that does NOT, importing the adapter must not raise — a tool
     tree synced without `shared/` still runs everything that does not need
     the manifest, and a build that died because it could not write a note
     about itself would be worse than the missing note.

⚠️ The second arm exists because the first draft of this adapter (written by
another lane) claimed it raised `ImportError` on a tree without `shared/core`,
and a negative control showed it did not. The claim was never run. So the
degraded path is pinned here rather than described anywhere.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "jui_tools" / "jui_cli" / "core" / "generation_manifest.py"
LOADER = REPO / "jui_tools" / "jui_cli" / "core" / "shared_core.py"
RULE = REPO / "shared" / "core" / "generation_manifest.py"


def test_the_rule_is_not_in_the_adapter_any_more():
    """The 670-line writer lives in shared/core, not beside jui_cli."""
    assert RULE.is_file(), "the rule must be in shared/core"
    assert ADAPTER.is_file()
    body = ADAPTER.read_text(encoding="utf-8")
    assert "def save(" not in body, "the adapter must not carry a second writer"
    assert len(body.splitlines()) < 120, "the adapter is a shim, not a copy"


def test_in_this_tree_the_names_resolve_to_the_real_rule():
    """Positive control for the arm below: here, shared/core IS present."""
    from jui_cli.core import generation_manifest as gm
    assert gm.AVAILABLE is True
    assert hasattr(gm, "save") and hasattr(gm, "GenerationRun")
    # The re-export is the real object, not a same-named local.
    assert gm.save.__module__.endswith("generation_manifest")


#: A package name of its own. ⚠️ The first version of this helper copied the
#: adapter into a temporary `jui_cli/` and then purged `jui_cli*` from
#: `sys.modules` to force a fresh import — which evicted the REAL package that
#: the rest of the suite had already imported. Measured: `test_tool_resolver`
#: passes 12/12 alone and fails 5 when this file runs first. A probe that
#: reaches outside its own namespace is a defect in the probe, and it shows up
#: as a failure somewhere else entirely.
PROBE_PKG = "_gm_adapter_probe"


def _adapter_in_a_tree_without_shared_core(tmp_path: Path):
    """Import the adapter from a tree where the walk-up finds no shared/core."""
    pkg = tmp_path / PROBE_PKG / "core"
    pkg.mkdir(parents=True)
    (tmp_path / PROBE_PKG / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    shutil.copy(ADAPTER, pkg / "generation_manifest.py")
    shutil.copy(LOADER, pkg / "shared_core.py")
    assert not (tmp_path / "shared" / "core").exists(), "the control must be blind"

    sys.path.insert(0, str(tmp_path))
    try:
        # A plain import, so the adapter's own `from . import shared_core`
        # resolves inside the probe package rather than against the checkout.
        return importlib.import_module(f"{PROBE_PKG}.core.generation_manifest")
    finally:
        sys.path.remove(str(tmp_path))
        for name in [n for n in sys.modules if n.startswith(PROBE_PKG)]:
            del sys.modules[name]
        importlib.invalidate_caches()


def test_a_tree_without_shared_core_imports_and_says_so(tmp_path):
    """Importing is safe; AVAILABLE is what carries the bad news."""
    module = _adapter_in_a_tree_without_shared_core(tmp_path)
    assert module.AVAILABLE is False
    # The path constants stay, so a caller can still name the file it could
    # not write. They are data, not the rule.
    assert module.MANIFEST_FILENAME == "generation-manifest.json"


def test_the_missing_name_explains_which_absence_it_is(tmp_path):
    """`no attribute 'save'` reads as a typo; this must read as a tree."""
    module = _adapter_in_a_tree_without_shared_core(tmp_path)
    try:
        module.save
    except AttributeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected AttributeError for a missing rule")
    assert "shared/core/generation_manifest.py" in message
    assert "AVAILABLE" in message, "the message must name the flag to check"
