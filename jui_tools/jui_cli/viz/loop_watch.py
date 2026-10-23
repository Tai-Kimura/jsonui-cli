"""What a stuck server leaves in serve.log (ticket 2026-10-24-viz-serve-stops-answering-after-setsockopt-einval).

The real server stopped answering /health on 10-24 and was killed; all its log kept was a symptom, and the start that
followed wrote over that. From here on the server leaves the cause behind in two ways:

* ``SIGUSR1`` writes every thread's stack to stderr (serve.log under ``start``). ``stop`` sends it before it kills a
  server that did not end on TERM.
* A watch thread: when the loop has not run for ``after_sec``, it writes one line (how long, the connections open,
  the last request and the ones still being handled) and every thread's stack, once each time it stands still, and a
  line when the loop runs again.
"""

from __future__ import annotations

import asyncio
import faulthandler
import signal
import struct
import sys
import threading
import time
from typing import Callable

#: How long the loop may not run before the watch writes the stacks (a page's request is answered well within 1 s).
STUCK_SEC = 10.0
#: How often the loop marks that it ran, and how often the watch looks.
BEAT_SEC = 1.0


def thread_names() -> str:
    """Each thread's id as faulthandler writes it (``Thread 0x…``) and its name: 3.11's faulthandler writes no names."""
    width = 2 * struct.calcsize("L")
    return ", ".join(f"0x{t.ident:0{width}x} {t.name}" for t in threading.enumerate() if t.ident is not None)


def dump_on_usr1() -> None:
    """``kill -USR1 <pid>`` writes every thread's stack to stderr, the loop's own included even when it is stuck, then
    a line naming the threads (written by the main thread once it runs Python: not at all while it is stuck in C)."""
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, lambda signum, frame: print(f"jui viz: threads: {thread_names()}", file=sys.stderr, flush=True))
        faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True, chain=True)


class RequestNotes:
    """The last request the server took and the ones it is handling, for the watch's line. Only the method and the
    path are kept (never the query, a header or a body)."""

    def __init__(self) -> None:
        self.last: tuple[str, str, float, bool] | None = None   # method, path, when it came, whether it was answered
        self.handling: dict[int, tuple[str, str, float]] = {}

    def middleware(self):
        from aiohttp import web

        @web.middleware
        async def note(request, handler):
            key = id(request)
            entry = (request.method, request.path, time.monotonic())
            self.handling[key] = entry
            self.last = (*entry, False)
            try:
                return await handler(request)
            finally:
                self.handling.pop(key, None)
                if self.last is not None and self.last[:3] == entry:
                    self.last = (*entry, True)

        return note

    def describe(self, now: float) -> str:
        if self.last is None:
            last = "no request yet"
        else:
            method, path, at, done = self.last
            last = f"{method} {path} {now - at:.1f} s ago ({'answered' if done else 'not answered'})"
        handling = sorted(self.handling.values(), key=lambda e: e[2])
        parts = [f"{m} {p} for {now - at:.1f} s" for m, p, at in handling[:5]]
        more = f" and {len(handling) - 5} more" if len(handling) > 5 else ""
        return f"last request: {last}; being handled: {len(handling)}" + (f" ({', '.join(parts)}{more})" if parts else "")


class LoopWatch:
    """Marks every BEAT_SEC on the loop that it ran; a daemon thread writes to ``out`` when the mark is older than
    ``after_sec``. ``describe(now)`` gives the rest of the line (the connections, the requests)."""

    def __init__(self, loop: asyncio.AbstractEventLoop, describe: Callable[[float], str], after_sec: float = STUCK_SEC,
                 beat_sec: float = BEAT_SEC, out=None) -> None:
        self._loop = loop
        self._describe = describe
        self._after = after_sec
        self._beat_sec = beat_sec
        self._out = out
        self._ran = time.monotonic()
        self._stop = threading.Event()
        self._handle: asyncio.TimerHandle | None = None
        self._thread = threading.Thread(target=self._watch, name="jui-viz-loop-watch", daemon=True)

    def start(self) -> None:
        self._beat()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._handle is not None:
            self._handle.cancel()

    def _beat(self) -> None:
        self._ran = time.monotonic()
        if not self._stop.is_set():
            self._handle = self._loop.call_later(self._beat_sec, self._beat)

    def _write(self, text: str) -> None:
        out = self._out or sys.stderr
        print(f"jui viz: {text}", file=out, flush=True)

    def _watch(self) -> None:
        stuck_since = None
        while not self._stop.wait(self._beat_sec):
            now = time.monotonic()
            idle = now - self._ran
            if idle >= self._after and stuck_since is None:
                stuck_since = self._ran
                try:
                    self._write(f"the loop has not run for {idle:.1f} s: {self._describe(now)}; every thread's stack:")
                except Exception as exc:  # noqa: BLE001 - the stacks matter more than the line
                    self._write(f"the loop has not run for {idle:.1f} s (the line failed: {exc!r}); every thread's stack:")
                self._write(f"threads: {thread_names()}")
                out = self._out or sys.stderr
                faulthandler.dump_traceback(file=out, all_threads=True)
                out.flush()
            elif idle < self._after and stuck_since is not None:
                self._write(f"the loop runs again, after {self._ran - stuck_since:.1f} s")
                stuck_since = None
