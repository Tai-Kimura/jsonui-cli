"""`SOURCE_DATE_EPOCH` — a build clock the receiver can pin.

Every generated page embeds the moment it was written, so running the same
command twice rewrites files whose content did not change: measured on a
consumer's site, 217 of 369 files moved between two identical runs. That makes
"the generator is deterministic" unfalsifiable for anyone downstream — they
cannot tell a real regeneration from a clock tick without a normaliser, and the
normaliser lives in this repo's release scripts, not in their hands.

`SOURCE_DATE_EPOCH` is the reproducible-builds standard for exactly this: an
integer of seconds since the Unix epoch which, when set, replaces the build
clock. A receiver runs the generator twice with it set and compares with plain
`cmp`; anything that still moves is a real difference.

Four accessors, not one, because each call site has an unset behaviour that must
not change: a naive local `now()`, an aware UTC `now()`, a local-zone `now()`,
and `today()`. Collapsing them would make an unset run behave differently from
before, which is the one thing this must not do.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

#: The variable name, spelled once.
ENV = "SOURCE_DATE_EPOCH"

#: Values already complained about, so a run with many exits warns once per
#: bad value rather than once per generated page.
_warned: set[str] = set()


def _epoch() -> int | None:
    """The pinned instant, or None to use the wall clock.

    A value that is not an integer is announced and ignored rather than
    raising: a malformed environment variable should not stop a documentation
    build, but it must not silently produce wall-clock output either, because
    the caller set it precisely to avoid that.
    """
    raw = os.environ.get(ENV)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        if raw not in _warned:
            _warned.add(raw)
            print(
                f"WARNING [doc]: {ENV} is not an integer ({raw!r}) — ignoring "
                f"it; generated timestamps will use the current time"
            )
        return None


def _pinned() -> datetime | None:
    epoch = _epoch()
    return None if epoch is None else datetime.fromtimestamp(epoch, tz=timezone.utc)


def build_datetime() -> datetime:
    """Replaces `datetime.now()`."""
    return _pinned() or datetime.now()


def build_datetime_utc() -> datetime:
    """Replaces `datetime.now(timezone.utc)`."""
    return _pinned() or datetime.now(timezone.utc)


def build_local_datetime() -> datetime:
    """Replaces `datetime.now().astimezone()`.

    Stays UTC when pinned: converting the pinned instant to the local zone
    would make the output depend on the machine's `TZ`, so two receivers in
    different zones would disagree about a build that is supposed to be
    reproducible.
    """
    return _pinned() or datetime.now().astimezone()


def build_date() -> date:
    """Replaces `date.today()`."""
    pinned = _pinned()
    return pinned.date() if pinned else date.today()
