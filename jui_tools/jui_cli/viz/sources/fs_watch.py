"""The observer the server's file watchers use (ticket 2026-11-12-viz-loop-stalls-on-watcher-stop).

On macOS, watchdog's FSEvents emitter registers a stream and then starts it; when fseventsd is in trouble the start fails
("Cannot start fsevents stream"), the emitter's thread ends, and the stream stays registered unstarted. Stopping that
observer later called FSEventStreamStop on it, and the server ended with SIGSEGV (2026-11-12 16:36, after fseventsd was
restarted). Here an emitter whose stream did not start is never stopped through FSEvents, and ``started`` tells the
caller, after the start, whether every folder is watched: one that is not is let go and the caller does without it.

Elsewhere (Linux) this is watchdog's own Observer.
"""
from __future__ import annotations

import sys
import threading

#: How long ``started`` waits for each emitter to say whether its stream started.
START_WAIT_SEC = 5.0


def observer():
    """A new observer (not started)."""
    if sys.platform != "darwin":
        from watchdog.observers import Observer
        return Observer()
    return _guarded_fsevents_observer()


def started(obs, wait_sec: float = START_WAIT_SEC) -> bool:
    """After ``obs.start()``: True when each folder's stream started; False when one did not (or did not say so within
    wait_sec). Not FSEvents: True."""
    for emitter in list(getattr(obs, "emitters", ())):
        settled = getattr(emitter, "settled", None)
        if settled is None:
            continue
        if not settled.wait(wait_sec) or emitter.failed is not None:
            return False
    return True


def failure(obs) -> str:
    """Why the streams that did not start did not, for the log."""
    for emitter in list(getattr(obs, "emitters", ())):
        if getattr(emitter, "failed", None) is not None:
            return f"{type(emitter.failed).__name__}: {emitter.failed}"
    return "no answer from FSEvents"


_CLASS = None


def _guarded_fsevents_observer():
    global _CLASS
    if _CLASS is None:
        import time

        import _watchdog_fsevents as _fsevents
        from watchdog.observers.api import BaseObserver
        from watchdog.observers.fsevents import FSEventsEmitter, FSEventsObserver

        class GuardedEmitter(FSEventsEmitter):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.settled = threading.Event()   # its stream started, or failed to
                self.failed: BaseException | None = None
                self._added = False
                self._stopping = False
                self._guard = threading.Lock()

            def run(self) -> None:
                self.pathnames = [self.watch.path]
                self._start_time = time.monotonic()
                with self._guard:
                    if self._stopping:
                        self.settled.set()
                        return
                    try:
                        _fsevents.add_watch(self, self.watch, self.events_callback, self.pathnames)
                    except Exception as exc:  # noqa: BLE001 — the stream is registered, not started: never stopped
                        self.failed = exc
                        self.settled.set()
                        return
                    self._added = True
                self.settled.set()
                try:
                    _fsevents.read_events(self)
                except Exception:  # noqa: BLE001
                    pass

            def on_thread_stop(self) -> None:
                with self._guard:
                    self._stopping = True
                    if not self._added:
                        return     # not started: FSEventStreamStop on it ends the process (SIGSEGV)
                super().on_thread_stop()

        class GuardedObserver(FSEventsObserver):
            def __init__(self, *, timeout: float = 1.0) -> None:
                BaseObserver.__init__(self, GuardedEmitter, timeout=timeout)

        _CLASS = GuardedObserver
    return _CLASS()


def kept_or_none(obs, what: str):
    """``obs`` once started, when every folder is watched; else it is stopped (safely) and None is returned: the server
    does without that watcher rather than end (a stream FSEvents would not start)."""
    if started(obs):
        return obs
    print(f"jui viz: {what} not watched: FSEvents did not start ({failure(obs)})"[:300], file=sys.stderr, flush=True)
    try:
        obs.stop()
        obs.join(timeout=1)
    except Exception:  # noqa: BLE001
        pass
    return None
