"""Each picture decoded once per process, each measurement taken once.

One `jui conformance gate` run asked the same questions of the same PNGs over
and over: the control diff of every face three times (the report, the
inert-complete judgement and the value-discrimination judgement each call
control_diff.compare with the same inputs), and dHash, vdHash and ink of one
screenshot each from a decode of its own. Measured on CI run 38393632937's
artifacts (4,577 PNGs): 27,938 opens, PNG decoding 128 s of the run's 247 s
locally (721 s on the CI runner).

The answers are pure functions of the file's BYTES and the arguments, so they
are kept here keyed by exactly that: a BLAKE2b digest of the file's content —
not its path, size or mtime — and the call's arguments. A file whose content
changes is a different key and is measured again; nothing is reused across
different content. The measurements themselves are the callers' own code,
unchanged: this module only decides whether a result for these bytes and
these arguments was already computed in this process.

Thread-safe for the gate's per-face workers: two threads computing the same
key both compute it and store the same value (the functions are pure), so no
lock is held across a computation.
"""

from __future__ import annotations

import hashlib
import io
import threading
from pathlib import Path
from typing import Callable

_results: dict[tuple, object] = {}
_lock = threading.Lock()


def content_key(path: Path) -> tuple[str, bytes]:
    """(digest, bytes) of the file. The bytes are handed back so the caller
    decodes what was hashed — never a second read that could differ."""
    data = Path(path).read_bytes()
    return hashlib.blake2b(data, digest_size=20).hexdigest(), data


def memo(kind: str, keys: tuple, compute: Callable[[], object]) -> object:
    """The stored result for (kind, keys), else compute() — stored."""
    key = (kind,) + keys
    with _lock:
        if key in _results:
            return _results[key]
    value = compute()
    with _lock:
        _results.setdefault(key, value)
        return _results[key]


def open_bytes(image_module, data: bytes):
    """A PIL image over bytes already read (and hashed)."""
    return image_module.open(io.BytesIO(data))


def clear() -> None:
    """Forget everything (tests)."""
    with _lock:
        _results.clear()


def size() -> int:
    with _lock:
        return len(_results)


def per_face(fn: Callable, items: list) -> list:
    """fn(item) for each item — the faces of one gate run — in threads, the
    results in the ITEMS' order (Executor.map), so what is built from them is
    built in the same order as the loop this replaces. An exception surfaces
    at the first item, in that order, that raised. Pillow decodes, diffs and
    histograms without the GIL, so the faces' pictures are read in parallel.
    JUI_CONFORMANCE_WORKERS=1 runs them one after another, as before.
    """
    import os
    from concurrent.futures import ThreadPoolExecutor

    items = list(items)
    workers = int(os.environ.get("JUI_CONFORMANCE_WORKERS", "0") or 0) or min(len(items), os.cpu_count() or 1)
    if workers <= 1 or len(items) <= 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))
