"""The reorder rule's Python reference (ticket jui-collection-drag-to-reorder, ruling B 2026-11-13).

shared/core/reorder_vectors.json is the contract every face's runtime reads: SwiftJsonUI and KotlinJsonUI drag their
rows by it and rjui's generated helper drags the web's. This module is the same rule written once in Python, pinned
against the vectors by jui_tools/tests/test_reorder_vectors.py, so a vector that contradicts its own rule text is
caught where it is written. No face imports it.
"""
from __future__ import annotations

from collections.abc import Sequence


def bounds(count: int, locked: Sequence[int], start: int) -> tuple[int, int]:
    """The indices a row at *start* may land on: between the nearest locked row above it and the nearest below."""
    above = [i for i in locked if i < start]
    below = [i for i in locked if i > start]
    return (max(above) + 1 if above else 0), (min(below) - 1 if below else count - 1)


def drop(rows: Sequence, start: int, to: int, locked: Sequence[int] = ()) -> list | str:
    """The order after onReorder's (start, to), or why it is refused: "no-move", "out-of-range" or "locked"."""
    count = len(rows)
    if not (0 <= start < count and 0 <= to < count):
        return "out-of-range"
    if start in locked:
        return "locked"
    if to == start:
        return "no-move"
    low, high = bounds(count, locked, start)
    if not low <= to <= high:
        return "locked"
    order = list(rows)
    order.insert(to, order.pop(start))
    return order


def drag_to(heights: Sequence[float], start: int, dy: float, locked: Sequence[int] = ()) -> int | None:
    """Which `to` a finger *dy* below (negative: above) the row at *start* means; None when the row is locked."""
    if start in locked:
        return None
    centres, top = [], 0.0
    for height in heights:
        centres.append(top + height / 2)
        top += height
    dragged = centres[start] + dy
    to = start
    to += sum(1 for i in range(start + 1, len(heights)) if centres[i] < dragged)
    to -= sum(1 for i in range(start) if centres[i] > dragged)
    low, high = bounds(len(heights), locked, start)
    return max(low, min(high, to))


def ios_on_move(start: int, destination: int) -> int:
    """SwiftUI onMove's destination (counted before the row is taken out) as `to` (counted after)."""
    return destination - 1 if destination > start else destination


def a11y(count: int, start: int, action: str, locked: Sequence[int] = ()) -> int | None:
    """The `to` of the screen reader's move up / move down, or None when the action is not offered."""
    if start in locked:
        return None
    to = start - 1 if action == "up" else start + 1
    low, high = bounds(count, locked, start)
    return to if low <= to <= high else None


def release(heights: Sequence[float], start: int, grab_at: float, dy: float, locked: Sequence[int] = (),
            header: float = 0.0, footer: float = 0.0) -> int | None:
    """The `to` a release means, or None when it is cancelled (the finger outside the container)."""
    rows = sum(heights)
    finger = header + sum(heights[:start]) + grab_at + dy
    if not 0 <= finger < header + rows + footer:
        return None
    if start in locked:
        return None
    low, high = bounds(len(heights), locked, start)
    if finger < header:
        return low
    if finger >= header + rows:
        return high
    return drag_to(heights, start, dy, locked)


BAND = 48.0
MAX_SPEED = 800.0


def auto_scroll(viewport: float, finger_y: float, band: float = BAND, max_speed: float = MAX_SPEED) -> float:
    """The scroll speed (per second; negative: up) for a finger at *finger_y* in a visible area *viewport* high."""
    top_depth = (band - finger_y) / band
    bottom_depth = (finger_y - (viewport - band)) / band
    if top_depth <= 0 and bottom_depth <= 0:
        return 0.0
    if top_depth >= bottom_depth:
        return -max_speed * min(1.0, top_depth)
    return max_speed * min(1.0, bottom_depth)
