"""Where `jui generate` finds the spec validator (document_tools).

The launcher (jui_tools/bin/jui) puts only jui_tools on sys.path, and the
import was written `document_tools.jsonui_doc_cli…`. Only a face that set
`document_tools_path` could resolve it, and none had: on every face `jui
generate` printed "WARNING: document_tools not available, skipping
validation" and generated from specs nobody had validated.

The validator is found by the first of these that imports:

1. the name as it stands — `document_tools_path` from jui.config.json has
   already been put on sys.path by `ensure_document_tools_importable`;
2. the distribution this jui runs from — its root holds jui_tools/ and
   document_tools/ side by side (~/.jsonui-cli, or a jsonui-cli checkout).
   The root goes on sys.path so `document_tools.` resolves, and its
   test_tools/ goes FIRST: the validator imports `jsonui_test_cli`
   (`contract_declarations`), and `install_jsonui_test.sh` installs that
   package with a plain `pip install .` at whatever version it was given — a
   copy the validator was not released with. Found first, that copy decides
   the validator's answers, and where it lacks the module, a spec that
   declares contracts gets an ERROR ("jsonui-test (jsonui_test_cli) is not
   importable") and generate stops. Measured with this jui and a jsonui-test
   one release older, on the module the validator imported then
   (`gate_literal`, now shared/core/gate_versions.py): every spec whose layout
   lacked an id got "is not importable" in place of its verdict. Before the
   pip name, so the validator and what it imports are the release this jui is;
3. the pip name — `jsonui_doc_cli`, document_tools installed with `pip -e`.

Routes 2 and 3 reach the same file in a checkout (the validator's own imports
are relative, so either package name works).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

VALIDATOR = "jsonui_doc_cli.spec_doc.validator"


def distribution_root() -> Path:
    """The directory holding the running jui_tools/ (and its siblings)."""
    import jui_cli
    return Path(jui_cli.__file__).resolve().parents[2]


def _import(module: str):
    return importlib.import_module(module).SpecValidator


def load_spec_validator() -> tuple[object | None, str]:
    """(SpecValidator, where it came from), or (None, every route tried)."""
    tried: list[str] = []
    try:
        return _import(f"document_tools.{VALIDATOR}"), "document_tools (already on sys.path)"
    except ImportError as e:
        tried.append(f"document_tools.{VALIDATOR}: {e}")

    root = distribution_root()
    if (root / "document_tools" / "jsonui_doc_cli").is_dir():
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        test_tools = root / "test_tools"
        if (test_tools / "jsonui_test_cli").is_dir():
            if str(test_tools) in sys.path:
                sys.path.remove(str(test_tools))
            sys.path.insert(0, str(test_tools))
        try:
            return _import(f"document_tools.{VALIDATOR}"), f"document_tools beside jui_tools in {root}"
        except ImportError as e:
            tried.append(f"{root / 'document_tools'}: {e}")
    else:
        tried.append(f"{root}: no document_tools/ beside jui_tools")

    try:
        return _import(VALIDATOR), "jsonui_doc_cli (pip)"
    except ImportError as e:
        tried.append(f"{VALIDATOR}: {e}")
    return None, "; ".join(tried)
