"""No iOS conformance screenshot shows the simulator's home indicator.

The iOS baselines hash the whole picture below the status-bar crop
(baseline.PLATFORM_ENV_CHROME_CROP, bottom 0). That holds only because the
indicator is not drawn in these captures: 0 of the 901 iOS screenshots of
CI run 37213865798 carry it. Nothing kept it so. A host change that read the
hierarchy with one XCUIApplication.snapshot() after each screenshot made the
simulator draw it into the next ones: 110 of 178 common/ pictures gained the
pill, and the drawn pill alone moves a dHash by about 7 against a threshold
of 8 (measured on SwiftJsonUI's ConformanceHost, iOS 26.5, Xcode 26.6,
2026-10-05). An indicator in a screenshot is therefore a run that changed
what the baselines are about. The gate names it rather than letting it ride
the threshold.

The discriminator is the pill itself: ``data/ios_home_indicator.png``
holds its 6452 pixels, the difference between the same fixture drawn with and
without it, at their place in a 1206 x 2622 capture (box origin
:data:`PILL_ORIGIN`). A screenshot carries the indicator when more than
:data:`THRESHOLD` of those pixels have exactly the pill's colour there. A
tab bar or a box that reaches the bottom edge (12 and 7 of the 901) shares
the band but not the pill's pixels, and scores 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: The pill template's top-left corner in an iPhone 16 Pro capture.
PILL_ORIGIN = (387, 2583)
#: The capture size the template is placed in; another size is not judged.
CAPTURE_SIZE = (1206, 2622)
#: More than this share of the pill's pixels present means the indicator is.
THRESHOLD = 0.5
#: Where the dynamic and codegen hosts put their screenshots.
ARTIFACT_DIRS = ("ios", "ios-codegen")


#: The pill's pixels, beside this module so every conformance dir is judged
#: by the same template.
TEMPLATE = Path(__file__).resolve().parent / "data" / "ios_home_indicator.png"


def _image():
    from .baseline import _load_pillow  # noqa: PLC0415

    return _load_pillow()


def load_pill(path: Path) -> list[tuple[int, int, tuple[int, int, int]]]:
    """The pill's pixels: (x, y, rgb) in capture coordinates."""
    Image = _image()
    with Image.open(path) as img:
        rgba = img.convert("RGBA")
        width, height = rgba.size
        data = rgba.tobytes()
    ox, oy = PILL_ORIGIN
    pill = []
    for y in range(height):
        for x in range(width):
            i = (y * width + x) * 4
            if data[i + 3] == 255:
                pill.append((ox + x, oy + y, (data[i], data[i + 1], data[i + 2])))
    return pill


def pill_share(path: Path, pill: list[tuple[int, int, tuple[int, int, int]]]) -> float | None:
    """Share of the pill's pixels present in this screenshot, or None when the
    capture is not the size the template was taken at."""
    Image = _image()
    with Image.open(path) as img:
        if img.size != CAPTURE_SIZE:
            return None
        rgb = img.convert("RGB")
        hits = sum(1 for x, y, colour in pill if rgb.getpixel((x, y)) == colour)
    return hits / len(pill) if pill else 0.0


@dataclass
class IndicatorResult:
    checked: int = 0
    with_indicator: list[tuple[str, float]] = field(default_factory=list)
    other_size: list[str] = field(default_factory=list)


def measure(conformance_dir: Path) -> IndicatorResult:
    """Every iOS screenshot of this run, dynamic and codegen."""
    conformance_dir = Path(conformance_dir)
    pill = load_pill(TEMPLATE)
    result = IndicatorResult()
    for sub in ARTIFACT_DIRS:
        directory = conformance_dir / "artifacts" / sub
        if not directory.is_dir():
            continue
        for png in sorted(directory.glob("*.png")):
            share = pill_share(png, pill)
            if share is None:
                result.other_size.append(f"{sub}/{png.name}")
                continue
            result.checked += 1
            if share > THRESHOLD:
                result.with_indicator.append((f"{sub}/{png.name}", share))
    return result


def judge(conformance_dir: Path) -> tuple[list[str], list[str]]:
    """(problems, notices) for the gate."""
    if not TEMPLATE.is_file():
        return [f"ios home indicator: the pill template is missing ({TEMPLATE})"], []
    result = measure(conformance_dir)
    problems: list[str] = []
    notices: list[str] = []
    if result.with_indicator:
        shown = ", ".join(f"{name} ({share:.0%})" for name, share in result.with_indicator)
        problems.append(
            f"ios: {len(result.with_indicator)} of {result.checked} screenshot(s) show the home indicator, "
            f"which the baselines assume is never drawn (an XCUIApplication.snapshot() in the run draws it): {shown}"
        )
    notices.append(
        f"ios home indicator: {result.checked} screenshot(s) checked, {len(result.with_indicator)} with the pill"
        + (f"; {len(result.other_size)} of another capture size not judged" if result.other_size else "")
    )
    return problems, notices
