"""Waits for the browser tests that hold on a busy machine (2.3.5; the load flakes of play, name-tags, props, breaks,
bg-look, workwear and name-tag-role, one family).

Measured 10-19 under load 85–146: the page draws 1–15 frames a second instead of 60. Whatever moves per frame then
takes more wall time: a pose blending into the next (r.blend, 0.4 s of frame time capped at 0.05 s a frame: 8
frames), a tag easing up (0.35 of the way a frame), a camera following. Walking does not: liveWalk takes the real time
between frames (up to 1 s), so a walk takes about its real time at 1 fps and more (measured: the walk out of a room
took 9.6–12.8 s at 4–14 fps). So:

  until(page, js, name, ...)   wait for a predicate on page state, checked on every animation frame (polling 'raf':
                               state only changes in a frame), its name in the timeout, and with `why` a JSON of the
                               page's state at that moment in the message, so a timeout says what was missing.
  settled(page, name, ids)     wait until those robots have arrived (window.__dbg.settle: pose blended, no path, not
                               leaving, tag at its spot); returns __dbg.settleInfo. Read anything that animates only
                               after this, never by sampling on the wall clock.

The cap of a wait is never the fix: keep it as it was. Example:

    from waits import settled, until
    await until(page, "(id) => window.__dbg.props().room === id", "ten again: props back", arg=room_id,
                why="(id) => window.__dbg.settleInfo()")
    info = await settled(page, "the three typing at their desks", ids=[a, b, c])
"""
from __future__ import annotations

import json


class WaitTimeout(RuntimeError):
    pass


async def until(page, js: str, name: str, arg=None, timeout: int = 30000, why: str | None = None):
    """Wait for `js` (a function of `arg`) to be truthy, checked every animation frame; returns its value."""
    try:
        handle = await page.wait_for_function(js, arg=arg, timeout=timeout, polling="raf")
        return await handle.json_value()
    except Exception as e:   # noqa: BLE001 - say which wait, and what the page looked like
        state = ""
        if why:
            try:
                state = " state: " + json.dumps(await page.evaluate(why, arg), ensure_ascii=False)[:1500]
            except Exception as e2:  # noqa: BLE001
                state = f" state unreadable: {type(e2).__name__}"
        raise WaitTimeout(f"waiting for {name}: {str(e).splitlines()[0]}{state}") from None


async def settled(page, name: str, ids=None, timeout: int = 30000):
    """Wait until the robots `ids` (labels; all when None) have settled, then return their settleInfo."""
    await until(page, "(ids) => window.__dbg.settle(ids)", f"{name} (settled)", arg=ids, timeout=timeout,
                why="(ids) => window.__dbg.settleInfo(ids)")
    return await page.evaluate("(ids) => window.__dbg.settleInfo(ids)", ids)
