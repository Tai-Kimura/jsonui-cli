"""Make the suite test THIS checkout, whatever directory it is invoked from.

`pip install -e` registers an editable finder for `jsonui_doc_cli` pointing at
the *distributed* copy under `~/.jsonui-cli/document_tools`. That is right for
the `jsonui-doc` entry point and wrong for these tests: run from the repository
root instead of `document_tools/`, every `from jsonui_doc_cli...` resolved to
the installed copy, so the suite reported on the last release rather than on
the working tree — green, and measuring the wrong thing.

Nothing in the source tree caused it and nothing in the source tree announced
it; the failure only appears as a source change that the tests do not see.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1]

if sys.path[:1] != [str(_SOURCE_ROOT)]:
    sys.path.insert(0, str(_SOURCE_ROOT))

import jsonui_doc_cli  # noqa: E402

_loaded = Path(jsonui_doc_cli.__file__).resolve().parent.parent
if _loaded != _SOURCE_ROOT:
    raise RuntimeError(
        f"jsonui_doc_cli was imported from {_loaded}, not from the checkout "
        f"under test ({_SOURCE_ROOT}). The suite would report on that copy."
    )
