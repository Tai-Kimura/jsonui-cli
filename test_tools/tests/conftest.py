"""Pytest configuration for the jsonui-test CLI test suite.

This file used to ignore `test_cli.py` and `test_generator.py` at collection,
on the stated grounds that they were written against a CLI shape that "no
longer exists". Measured, that premise was wrong in the way that matters: the
subjects had not been deleted, they had *moved* to `jsonui-doc`
(`DocumentGenerator` and `generate_schema_reference` live in
`jsonui_doc_cli/test_doc/generator.py`; `generate -f/-o/--schema` and
`generate html` are `jsonui-doc generate doc|html`). All 45 tests were
recoverable, and 44 of the 45 failures came from two mechanical causes — one
unused import, and inline flow steps needing the `screen` the schema now
requires. `test_cli.py` keeps the 14 that test what `jsonui-test` still owns;
the other 31 moved to `document_tools/tests/test_test_doc_{cli,generator}.py`.

Worth keeping in mind next time: an ignore entry written as a temporary
measure reads, a few months later, as a statement that the coverage is gone.
Nothing re-checks it, because the suite is green precisely because it is not
looking. `collect_ignore` and a green run are indistinguishable from having no
such tests at all.

This file also pins the suite to THIS checkout. `pip install -e` registers an editable
finder for `jsonui_test_cli` pointing at the distributed copy under the
user-level install directory — right for the `jsonui-test` entry point, wrong
here. Two separate accidents currently keep it right: `tests/__init__.py` makes
pytest insert `test_tools/` rather than `test_tools/tests/`, and 16 of the 24
test modules pin the path themselves. Either alone suffices, which is why
removing one and re-measuring shows no change and proves nothing. Neither is a
stated property, and eight modules — including the one that checks the bundled
schema — rely entirely on the other files.

The failure mode is why it is worth stating: the installed copy passes, because
it IS a release. Measuring the wrong tree looks exactly like measuring the right
one.

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

import jsonui_test_cli
import pytest  # noqa: E402

_loaded = Path(jsonui_test_cli.__file__).resolve().parent.parent
if _loaded != _SOURCE_ROOT:
    raise RuntimeError(
        f"jsonui_test_cli was imported from {_loaded}, not from the checkout "
        f"under test ({_SOURCE_ROOT}). The suite would report on that copy."
    )


@pytest.fixture(autouse=True)
def _fresh_mock_source():
    """One resolved mock source per test, as there is one per CLI process.

    `validate` resolves the source once at the top of a run, so a real process
    never sees a previous run's. This suite does: modules that call the
    validators directly run after modules that invoke `main` in-process, and
    they inherited a boundary pointing at a deleted temp directory — every
    mock reference then resolved to nothing, which reads exactly like a
    project with no mocks. Two tests passed or failed on nothing but what had
    run before them.

    Reset here rather than weakened in the product: the staleness is a
    property of running many runs in one process, and the fix that looked
    right in the product — ignoring a boundary that does not contain the file —
    turns "out of bounds" back into "unbounded" for split trees.
    """
    from jsonui_test_cli.validation import mock as _mock_mod
    _mock_mod.set_mock_source()
    _mock_mod._MOCK_INDEX_CACHE.clear()
    yield
    _mock_mod.set_mock_source()
    _mock_mod._MOCK_INDEX_CACHE.clear()
