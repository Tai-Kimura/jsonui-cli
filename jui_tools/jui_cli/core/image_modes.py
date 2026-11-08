"""A picture of its own for a colour mode: ``<name>.<mode>.svg`` beside ``<name>.svg``.

``<mode>`` is a mode of colors.json (every mode, not only light and dark). A
layout names ``<name>``; the app draws the picture of the mode ColorManager is
in, and ``<name>.svg`` in a mode without one. An image with no mode's picture
is drawn as it always was.

No platform's own light/dark switch is used (an asset catalog's appearances,
drawable-night, ``<picture media>``): they know two modes, and they follow the
OS while a mode chosen in the app does not. Each face asks its ColorManager.

``jui build`` sorts the SVGs (``split``), writes every picture, and writes the
table each face's generator reads (``write_table``) beside colors.json, as
``image_modes.json``:

    {"version": 1, "images": {"ic_star": {"dark": "ic_star__dark"}}}

The value is the asset's name on iOS and Android (``<name>__<mode>``); the web
copies ``ic_star.dark.svg`` as it is and spells the same table its own way.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TABLE_NAME = "image_modes.json"
RESERVED_META_KEYS = ("fallback_mode", "systemModeMapping", "modes", "colorSchemes")
DEFAULT_MODE = "light"


def read_modes(colors_file: Path) -> list[str]:
    """colors.json's modes, as the tools read them (shared/core/color_manager_core.rb).

    A top-level key whose value is an object is a mode (settings such as
    systemModeMapping and colorSchemes, and ``_`` notes, are not); a flat file
    or none is the one mode ``light``.
    """
    try:
        raw = json.loads(colors_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [DEFAULT_MODE]
    if not isinstance(raw, dict):
        return [DEFAULT_MODE]
    # A `_` key (`_comment`) is a note, neither a colour nor a mode (ColorManagerCore.note_key?).
    # At the top of a themed file it was the first content key, the file read
    # as flat, and every mode's picture was an ERROR.
    content = [k for k in raw if k not in RESERVED_META_KEYS and not (isinstance(k, str) and k.startswith("_"))]
    if not content or not isinstance(raw[content[0]], dict):
        return [DEFAULT_MODE]
    return [k for k in content if isinstance(raw[k], dict)]


def mode_suffix(mode: str) -> str:
    """The mode as a name's suffix: ``[a-z0-9_]``, as an Android resource name takes it."""
    return re.sub(r"[^a-z0-9_]", "_", mode.lower())


def asset_name(name: str, mode: str) -> str:
    return f"{name}__{mode_suffix(mode)}"


def split(svg_files: list[Path], modes: list[str]) -> tuple[dict, dict, list[str]]:
    """(images, variants, errors).

    *images* is ``{name: path}`` for every picture drawn under its own name (an
    image with no mode, and each mode's base). *variants* is
    ``{name: {mode: path}}``. A stem whose last dotted part is no mode, with no
    ``<rest>.svg`` beside it, is an image named with a dot, as before.
    """
    by_stem = {p.stem: p for p in svg_files}
    images: dict[str, Path] = {}
    variants: dict[str, dict[str, Path]] = {}
    errors: list[str] = []
    for stem, path in sorted(by_stem.items()):
        base, dot, last = stem.rpartition(".")
        if not dot:
            images[stem] = path
            continue
        if last in modes:
            if base not in by_stem:
                errors.append(
                    f"{path.name} is the {last!r} picture of {base!r}, and there is no {base}.svg: "
                    f"a layout names {base!r}, and {base}.svg is drawn in every mode without its own picture"
                )
                continue
            variants.setdefault(base, {})[last] = path
            continue
        if base in by_stem:
            errors.append(
                f"{path.name}: {last!r} is not a mode of colors.json ({', '.join(modes)}); "
                f"a picture for a mode is <name>.<mode>.svg"
            )
            continue
        images[stem] = path
    # Two pictures that one face would write under one name.
    seen: dict[str, str] = {}
    for name in sorted(images):
        seen[name.lower()] = f"{images[name].name}"
    for name, by_mode in sorted(variants.items()):
        for mode, path in sorted(by_mode.items()):
            key = asset_name(name, mode)
            if key.lower() in seen:
                errors.append(f"{path.name} and {seen[key.lower()]} are both written as {key!r}")
            else:
                seen[key.lower()] = path.name
    return images, variants, errors


def table(variants: dict) -> dict:
    return {
        "version": 1,
        "images": {
            name: {mode: asset_name(name, mode) for mode in sorted(by_mode)}
            for name, by_mode in sorted(variants.items())
        },
    }


def write_table(resources_dir: Path, variants: dict) -> bool:
    """Write the table beside colors.json; with no mode's picture, there is no file.

    Returns True when the file changed. A project without a mode's picture gets
    no file and its generated code is what it was.
    """
    path = resources_dir / TABLE_NAME
    if not variants:
        if path.exists():
            path.unlink()
            return True
        return False
    data = (json.dumps(table(variants), indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    resources_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True
