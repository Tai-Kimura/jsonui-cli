"""Which fixtures do not draw the same picture twice.

WHY THIS EXISTS. `baseline update --fail-on-moved` treats any difference as
"moved", which is what makes it a gate: a bake must not absorb a picture that
changed without someone attributing the change. But a handful of fixtures
render something that is *not a function of the code* — a spinning activity
indicator, an image that arrives over time — and they differ run to run on a
correct machine. An exact check that fires every time teaches the operator to
pass `--no-fail-on-moved`, and then the gate protects nothing at all.

WHAT IS MEASURED (2026-09-05, iPhone 16 Pro C13F2A69, one host, one corpus,
four runs). Hamming against the committed baseline:

    Indicator/color__alias_tint                  1, 0, 3, 3
    __control/NetworkImage__no-defaultImage…     1, 0, 0, 2

Four runs, four pictures; the raw PNG bytes differ every time. The
NetworkImage control matched the baseline EXACTLY on one run and differed on
the next, so a single observation could not tell "flaky" from "the library
moved it by one bit" — both predict that reading.

This is not the first observation of the class. `baselines/README.md`'s iOS
calibration (2026-07-03), status bar frozen, 490 screenshots: distance 0 on
486, distance 1 on 3 — "Indicator activity-spinner frames". Indicator wobbles
as a CLASS, and that was measured two months before tonight.

SCOPE, AND WHAT IS NOT MEASURED. Two shapes qualify, derived from what a
fixture's layout DECLARES rather than from its name:

  * animated — the layout contains an Indicator
  * async    — the layout contains a NetworkImage with no `defaultImage`,
               so the frame depends on when the load lands

Everything else is treated as stable. That is a narrow set built from two
measured fixtures plus three calibration screenshots, and OTHER CLASSES ARE
UNMEASURED. `SelectBox_selectedValue` sits at distance 6 in the 07-03
calibration — one observation, not reproduced tonight — and is deliberately
NOT in the set; it is named in `baselines/README.md` so the next person sees
it without it silently weakening the check.

The cost of being narrow is bounded on purpose: a fixture outside this set
that wobbles still fails the exact check, BY NAME. The next unstable class
arrives as a named refusal rather than as a repeat of tonight's
investigation.
"""
from __future__ import annotations

import json
from pathlib import Path

#: Why a fixture is exempt from the exact check. The reason travels with the
#: name so a report says which kind of instability was tolerated.
ANIMATED = "animated (Indicator draws a different frame each capture)"
ASYNC = "async (NetworkImage without defaultImage — the frame depends on load timing)"


def screenshot_name(fixture_id: str) -> str:
    """`__control/NetworkImage__x` -> `control_NetworkImage__x.png`."""
    return fixture_id.lstrip("_").replace("/", "_") + ".png"


def _declares(node, predicate) -> bool:
    if isinstance(node, dict):
        if predicate(node):
            return True
        return any(_declares(v, predicate) for v in node.values())
    if isinstance(node, list):
        return any(_declares(i, predicate) for i in node)
    return False


def _is_indicator(node: dict) -> bool:
    return str(node.get("type", "")).casefold() == "indicator"


def _is_async_network_image(node: dict) -> bool:
    if str(node.get("type", "")).casefold() != "networkimage":
        return False
    # A declared defaultImage gives the view something to draw immediately,
    # so the capture does not depend on when the network answers.
    return not node.get("defaultImage")


def unstable_screenshots(conformance_dir: Path) -> dict[str, str]:
    """`{screenshot name: reason}` for fixtures whose picture is not stable.

    Derived from each fixture's layout — the declaration is the source, not
    the fixture id, so a rename cannot quietly drop a fixture out of the set
    and a new fixture of the same shape joins it without anyone maintaining
    a list.
    """
    manifest_path = Path(conformance_dir) / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures", manifest if isinstance(manifest, list) else [])

    out: dict[str, str] = {}
    for fixture in fixtures:
        layout_rel = fixture.get("layout")
        if not layout_rel:
            continue
        layout_path = Path(conformance_dir) / layout_rel
        if not layout_path.is_file():
            continue
        try:
            layout = json.loads(layout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _declares(layout, _is_indicator):
            out[screenshot_name(fixture["id"])] = ANIMATED
        elif _declares(layout, _is_async_network_image):
            out[screenshot_name(fixture["id"])] = ASYNC
    return out
