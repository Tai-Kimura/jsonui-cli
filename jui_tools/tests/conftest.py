"""Make the suite test THIS checkout, whatever directory it is invoked from.

`pip install -e` registers an editable finder for `jui_cli` pointing at the
distributed copy under the user-level install directory. That is right for the
`jui` entry point and wrong for these tests.

Today the suite happens to be safe: `tests/__init__.py` makes pytest insert
`jui_tools/` (the package's parent) rather than `jui_tools/tests/`, and that
insert outranks the editable finder. Measured — delete that one empty file and
every `import jui_cli` here resolves to the installed copy instead, with the
suite still fully green, because the installed copy IS a release. Only two of
this directory's test modules pin the path themselves, and the first one
collected is not among them, so nothing else would catch it.

A property that load-bearing should be stated, not inferred from a file whose
purpose looks like packaging. The check below costs nothing and turns "measured
the wrong tree" from a silent pass into an error.

(Each tool directory carries its own copy of this guard: they are distributed
independently, so a shared helper would be a cross-tree import that the guard
itself has to run before.)
"""

from __future__ import annotations

import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1]

if sys.path[:1] != [str(_SOURCE_ROOT)]:
    sys.path.insert(0, str(_SOURCE_ROOT))

import jui_cli  # noqa: E402

_loaded = Path(jui_cli.__file__).resolve().parent.parent
if _loaded != _SOURCE_ROOT:
    raise RuntimeError(
        f"jui_cli was imported from {_loaded}, not from the checkout under "
        f"test ({_SOURCE_ROOT}). The suite would report on that copy."
    )

# `generate project` validates the spec through
# `document_tools.jsonui_doc_cli.spec_doc.validator` — a top-level namespace
# package that only resolves when the repository root is importable. CI runs
# pytest from there, so it resolves and the wiring test runs. Run the suite the
# documented way (`cd jui_tools && pytest tests`) and it does not, so that test
# skipped itself — and the command under test takes its "document_tools not
# available, skipping validation" branch. The gate was green in both places and
# only ever exercised in one.
_REPO_ROOT = _SOURCE_ROOT.parent
if (_REPO_ROOT / "document_tools").is_dir() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(1, str(_REPO_ROOT))
