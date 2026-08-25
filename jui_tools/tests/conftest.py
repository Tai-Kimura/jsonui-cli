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

# NOTE: this file is pytest-only. CI runs `python -m unittest discover`, which
# never loads it, so nothing here can be the sole fix for anything CI must
# also do — see the repo-root insert at the top of
# test_spec_validation_wiring.py, which is in the test module for that reason.
# On CI the equivalent of the check above is that jui_cli is installed
# editable from the checkout.
