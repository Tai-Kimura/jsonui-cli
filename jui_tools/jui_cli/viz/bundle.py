"""The view's script, /app.js: web/js/ concatenated in a fixed order for the mode.

The prototype was one module whose parts share top-level names (plan 07 §1), so the parts are joined into one
module rather than imported from each other. Two modes pick which data source goes in the middle:

- ``live``: the WebSocket client (25-net.js) and the source built from the server's slices (30-source-live.js).
- ``demo``: the prototype's script and simulation (30-source-demo.js) — ``/?demo=1`` — and the talk view's demo
  frames (31-talk-demo-data.js: data only, written by tools/viz_e2e/talk_demo_gen.py).

``JUI_VIZ_E2E=1`` appends 80-dbg.js, the hook the browser tests drive the 3D boards through (``window.__dbg``);
it is never served otherwise. The server builds both modes once at start and, with ``JUI_VIZ_DEV=1``, again on
every request (``build`` itself always reads the files).
"""

from __future__ import annotations

import os
from importlib import resources

MODES = ("live", "demo")

# The order is the module's order: a part may use a name only an earlier part declares at its top level.
ORDER = {
    "live": ("05-i18n.js", "10-robot-core.js", "20-core.js", "25-net.js", "30-source-live.js",
             "40-scene.js", "45-spirits.js", "50-panel.js", "51-denials.js", "52-data-docs.js", "53-waits.js", "53-roster.js", "53-devices.js", "54-bills.js", "55-history.js", "56-server-room.js", "56-sr-models.js", "56-server-cost.js", "57-fulltext.js", "58-talk.js", "59-sr-flows.js", "60-log.js", "70-main.js"),
    "demo": ("05-i18n.js", "10-robot-core.js", "20-core.js", "30-source-demo.js", "31-talk-demo-data.js",
             "40-scene.js", "45-spirits.js", "50-panel.js", "51-denials.js", "52-data-docs.js", "53-waits.js", "53-roster.js", "53-devices.js", "54-bills.js", "55-history.js", "56-server-room.js", "56-sr-models.js", "56-server-cost.js", "57-fulltext.js", "58-talk.js", "59-sr-flows.js", "60-log.js", "70-main.js"),
}
E2E_PART = "80-dbg.js"


def e2e_enabled(environ=None) -> bool:
    """Whether the browser-test hook is appended (``JUI_VIZ_E2E=1``)."""
    return (os.environ if environ is None else environ).get("JUI_VIZ_E2E") == "1"


def dev_enabled(environ=None) -> bool:
    """Whether the server should rebuild /app.js on every request (``JUI_VIZ_DEV=1``)."""
    return (os.environ if environ is None else environ).get("JUI_VIZ_DEV") == "1"


def parts(mode: str, e2e: bool | None = None) -> tuple[str, ...]:
    """The web/js/ files /app.js is made of, in order."""
    if mode not in ORDER:
        raise ValueError(f"unknown mode {mode!r} (expected one of {', '.join(MODES)})")
    names = ORDER[mode]
    if e2e_enabled() if e2e is None else e2e:
        names = names + (E2E_PART,)
    return names


class MissingPart(LookupError):
    """A part of the bundle is not in the package. The server answers /app.js with 404 (LookupError)."""


def _read(name: str) -> str:
    f = resources.files(__package__).joinpath("web", "js", name)
    if not f.is_file():
        raise MissingPart(f"web/js/{name} is not in the package")
    return f.read_text(encoding="utf-8")


def build(mode: str, e2e: bool | None = None) -> str:
    """/app.js for ``mode`` ('live' or 'demo'). ``e2e`` defaults to ``JUI_VIZ_E2E``.

    Raises LookupError (MissingPart) when a part is absent, and ValueError for an unknown mode."""
    out = []
    for name in parts(mode, e2e):
        out.append(f"// ---- web/js/{name} ----\n")
        text = _read(name)
        out.append(text if text.endswith("\n") else text + "\n")
    return "".join(out)
