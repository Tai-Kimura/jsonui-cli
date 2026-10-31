"""The Figma calls' spinner thread is joined before the call returns or raises, whatever the failure (ticket
2026-10-31-ci-python-suite-figma-spinner-thread-aborts-at-shutdown).

A spinner thread left alive writes to stderr every 0.1 s; at interpreter shutdown it can hold stderr's lock while
Python finalizes it, and Python aborts ("_enter_buffered_busy: could not acquire lock for <stderr>", exit 134) after
every test has passed. Measured before the fix: the four calls left one thread each on a FigmaAPIError raised by the
opener (a refused redirect, a URL that is not the Figma API), a read timeout, an OSError and a KeyboardInterrupt — 16
of the 32 cells below. Nothing here reaches the network: ``_open`` is stood in for.
"""
from __future__ import annotations

import email.message
import io
import threading
import urllib.error

import pytest

from jsonui_doc_cli.figma import api_client as C

CALLS = {
    "fetch_file": lambda: C.fetch_file("KEY", "t"),
    "fetch_nodes": lambda: C.fetch_nodes("KEY", "t", ["1:2"]),
    "fetch_file_images": lambda: C.fetch_file_images("KEY", "t"),
    "fetch_image_renders": lambda: C.fetch_image_renders("KEY", "t", ["1:2"]),
}


class _Answer:
    def __init__(self, body: bytes = b"{}", exc: BaseException | None = None):
        self.body, self.exc = body, exc

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        if self.exc is not None:
            raise self.exc
        return self.body


def _raise(exc: BaseException):
    raise exc


# each way the opener or the read can end: (what _open does, the exception the call lets out or None)
PATHS = {
    "answered": (lambda: _Answer(), None),
    "HTTPError 404": (lambda: _raise(urllib.error.HTTPError("u", 404, "x", email.message.Message(), io.BytesIO())),
                      C.FigmaAPIError),
    "URLError": (lambda: _raise(urllib.error.URLError("x")), C.FigmaAPIError),
    "not JSON": (lambda: _Answer(b"not json"), C.FigmaAPIError),
    "the opener refuses (redirect / not the Figma API)": (lambda: _raise(C.FigmaAPIError("refused", 302)),
                                                         C.FigmaAPIError),
    "read timeout": (lambda: _Answer(exc=TimeoutError("timed out")), TimeoutError),
    "OSError from the opener": (lambda: _raise(ConnectionResetError("reset")), ConnectionResetError),
    "KeyboardInterrupt in the read": (lambda: _Answer(exc=KeyboardInterrupt()), KeyboardInterrupt),
}


def _spinners() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == C.SPINNER_THREAD_NAME and t.is_alive()]


@pytest.fixture(autouse=True)
def started(monkeypatch):
    """The spinners each arm starts; whatever the arm finds, they are stopped at its end, so one cell that leaks
    does not fail the cells after it (nor leave a thread for the interpreter's shutdown)."""
    made: list = []
    start = C._Spinner.start

    def recording(self):
        made.append(self)
        return start(self)
    monkeypatch.setattr(C._Spinner, "start", recording)
    yield made
    for s in made:
        s._stop.set()
        if s._thread is not None:
            s._thread.join()


@pytest.mark.parametrize("path", list(PATHS))
@pytest.mark.parametrize("name", list(CALLS))
def test_no_spinner_thread_outlives_the_call(monkeypatch, capsys, started, name, path):
    opens, lets_out = PATHS[path]
    monkeypatch.setattr(C, "_open", lambda req, timeout: opens())
    assert _spinners() == []
    if lets_out is None:
        CALLS[name]()
    else:
        with pytest.raises(lets_out):
            CALLS[name]()
    assert _spinners() == [], f"{name} / {path}: the spinner thread is still running"
    # the spinner wrote its last line once: the finally's stop after an earlier stop adds nothing
    err = capsys.readouterr().err
    assert err.count("\n") == 1, err


def test_the_spinner_counted_here_is_the_one_the_calls_start(monkeypatch, started):
    """Positive control: while ``_open`` is running, the thread counted above is alive, and it is the one the call
    started."""
    seen = []
    monkeypatch.setattr(C, "_open", lambda req, timeout: (seen.append(len(_spinners())), _Answer())[1])
    C.fetch_file("KEY", "t")
    assert seen == [1] and len(started) == 1 and _spinners() == []
