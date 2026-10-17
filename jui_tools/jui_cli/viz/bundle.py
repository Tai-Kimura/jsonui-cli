"""The view's script, /app.js: web/js/ concatenated in a fixed order for the mode.

The prototype was one module whose parts share top-level names (plan 07 §1), so the parts are joined into one
module rather than imported from each other. Two modes pick which data source goes in the middle:

- ``live``: the WebSocket client (25-net.js) and the source built from the server's slices (30-source-live.js).
- ``demo``: the prototype's script and simulation (30-source-demo.js) — ``/?demo=1``.

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
    "live": ("10-robot-core.js", "20-core.js", "25-net.js", "30-source-live.js",
             "40-scene.js", "50-panel.js", "60-log.js", "70-main.js"),
    "demo": ("10-robot-core.js", "20-core.js", "30-source-demo.js",
             "40-scene.js", "50-panel.js", "60-log.js", "70-main.js"),
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
