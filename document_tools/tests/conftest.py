"""Fail if this suite is measuring a `jsonui_test_cli` from somewhere else.

document_tools validates screen tests before it renders them, so most of
this suite runs the sibling package. `import jsonui_test_cli` resolves
through `sys.path`, and on a developer machine with the CLI installed that
is `~/.jsonui-cli` — the last RELEASE, not this checkout.

That is not hypothetical. In 1.7.35 the sibling made `source` a required
key; 21 tests here should have gone red and did not, because the validator
they imported predated the requirement. The same release lost a version
number to the same shape one suite over, where the path in was
`subprocess` + `PATH` instead of `import` + `sys.path`. Two entrances, one
trap, and the local reading of both was "green".

A green run has to say which tree it measured. This asserts it instead of
printing it, because a printed provenance line is one more line nobody
reads when the count says 547 passed.

Run against this checkout with:

    PYTHONPATH=<repo>/test_tools python -m pytest

CI already satisfies this: it installs test_tools editable from the repo,
so the resolved path is inside it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def pytest_configure(config):
    try:
        import jsonui_test_cli
    except ImportError:
        # Nothing to mis-measure. The tests that need it will fail on their
        # own terms, which is a clearer message than one from here.
        return
    resolved = Path(jsonui_test_cli.__file__).resolve()
    if REPO in resolved.parents:
        return
    raise pytest.UsageError(
        f"jsonui_test_cli resolves to {resolved}, which is outside this "
        f"checkout ({REPO}).\n"
        "This suite validates screen tests through that package, so it would "
        "be reporting on a different version than the one you are changing — "
        "green here would mean nothing about this tree.\n"
        f"Run with:  PYTHONPATH={REPO / 'test_tools'} python -m pytest"
    )
