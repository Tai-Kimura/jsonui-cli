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

# NOTE: this file is pytest-only, and since 1.7.0 CI runs pytest — so the
# check above now executes there too. It did not when it was written: CI ran
# `python -m unittest discover`, which never loads conftest, and the note here
# used to say so. Left as a record because the reasoning it drove is still
# load-bearing elsewhere — the repo-root insert at the top of
# test_spec_validation_wiring.py sits in the test module, not here, and that
# placement was correct then and costs nothing now.
#
# What has NOT changed: a fix placed only in this file reaches only the
# runners that read conftest. `python -m unittest discover` still runs by
# hand, and still collects nothing from the pytest-style modules.


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _viz_home_follows_home(monkeypatch):
    """jui viz's runtime folder comes from JUI_VIZ_HOME / XDG_STATE_HOME before HOME. A test that points
    HOME at a temporary folder must not reach the real one through a variable the machine happens to set."""
    monkeypatch.delenv("JUI_VIZ_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)


@pytest.fixture(autouse=True)
def _cwd_is_put_back():
    """jui viz serve leaves the folder it was launched from (2.3.1: a deleted launch folder broke its children).
    A test that runs serve in-process takes the whole test process into a temporary viz home, which pytest
    removes later; every test after it then starts its subprocesses in a deleted folder and fails with
    FileNotFoundError (7 in test_web_viewmodel_base_ownership.py on the 2.3.1 release branch). Put it back."""
    import os

    before = os.getcwd()
    try:
        yield
    finally:
        os.chdir(before)


def pytest_configure(config):
    config.addinivalue_line("markers", "viz_ja: the test reads jui viz's Japanese words (the server's or the page's): "
                                       "run it with the words in Japanese")


@pytest.fixture(autouse=True)
def _viz_words(request, monkeypatch):
    """jui viz's words are English by default (the requester's ruling). A test marked viz_ja reads the Japanese words
    letter for letter: it runs with JUI_VIZ_LANGUAGE=ja (a server it starts reads it) and the Japanese table active in
    this process (what tl() says here). Only those: every other test runs in English, so a word the English table
    lacks still shows. The table active before the test is put back after it, marked or not (a test that runs serve
    in-process activates its own)."""
    from jui_cli.viz import i18n

    before = i18n._ACTIVE
    if request.node.get_closest_marker("viz_ja"):
        monkeypatch.setenv(i18n.LANGUAGE_ENV, "ja")
        i18n.activate(i18n.load("ja"))
    else:
        monkeypatch.delenv(i18n.LANGUAGE_ENV, raising=False)
        i18n.activate(i18n.Strings())   # empty: tl() loads the default the first time it is asked
    try:
        yield
    finally:
        i18n.activate(before)
