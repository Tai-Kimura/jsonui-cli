"""Path questions that answer False instead of raising, for the readers of files other programs write (ticket
2026-10-23-viz-data-docs-is-file-raises-einval-during-a-swap).

On macOS a stat of a path being swapped between a file and a symlink fails with EINVAL. Python 3.11 to 3.13's
``Path.is_file`` / ``is_dir`` / ``exists`` / ``is_symlink`` pass that on (they swallow only ENOENT, ENOTDIR, EBADF and
ELOOP), so one swap ended a whole read (measured 10-24: about 1,270 of 700,000 calls during a file/symlink swap on
3.11, none on 3.14, none for a file replaced by a file). These answer as 3.14 does: an error is "not there now", and
the next read sees what settled.
"""

from __future__ import annotations

import os


def is_file(path: os.PathLike | str) -> bool:
    try:
        return os.path.isfile(path)
    except (OSError, ValueError):
        return False


def is_dir(path: os.PathLike | str) -> bool:
    try:
        return os.path.isdir(path)
    except (OSError, ValueError):
        return False


def exists(path: os.PathLike | str) -> bool:
    try:
        return os.path.exists(path)
    except (OSError, ValueError):
        return False


def is_symlink(path: os.PathLike | str) -> bool:
    try:
        return os.path.islink(path)
    except (OSError, ValueError):
        return False
