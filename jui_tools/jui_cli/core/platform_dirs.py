"""Where each platform's own tool reads the Layouts and Styles `jui build` distributes.

`jui build` writes a face's Layout JSON to ``<root>/<layoutsDir>`` and its
styles beside it, ``<root>/<layoutsDir>/../Styles`` (jui.config.json). The
tool that builds the face reads them from its own config: sjui and kjui from
``<root>/<source_directory>/<layouts_directory>`` (and ``styles_directory``),
rjui from ``<root>/<layouts_directory>``. Nothing tied the two, and `jui init`
wrote iOS's ``layoutsDir`` as ``Layouts`` while `sjui init` wrote
``source_directory: <project>``: jui distributed to ``ios/Layouts``, sjui read
``ios/<project>/Layouts``, and the face was never built (ticket
2026-10-23-jui-init-ios-layouts-dir-not-where-sjui-reads).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: The config each face's tool writes in its platform root.
TOOL_CONFIG = {"ios": "sjui.config.json", "android": "kjui.config.json", "web": "rjui.config.json"}


def _tool_config(platform: str, platform_root: Path) -> tuple[str, dict] | None:
    name = TOOL_CONFIG.get(platform)
    path = platform_root / name if name else None
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return (name, data) if isinstance(data, dict) else None


def _join(source: object, rel: object) -> str | None:
    if not isinstance(rel, str) or not rel:
        return None
    parts = [p for p in (source if isinstance(source, str) else "", rel) if p]
    return os.path.normpath("/".join(parts))


def tool_read_dirs(platform: str, platform_root: Path) -> dict[str, str] | None:
    """``{"file", "layouts", "styles"}`` relative to the platform root, as the
    face's tool reads them (a key it does not spell is left out: its own
    default is not this module's to guess). None when it has no config."""
    found = _tool_config(platform, platform_root)
    if found is None:
        return None
    name, data = found
    source = data.get("source_directory")
    out = {"file": name}
    for key, field in (("layouts", "layouts_directory"), ("styles", "styles_directory")):
        joined = _join(source, data.get(field))
        if joined:
            out[key] = joined
    return out


def disagreements(project_root: Path, platforms: dict) -> list[str]:
    """One sentence per face whose ``layoutsDir`` (or the Styles beside it) is
    not where its tool reads: the tool would build from a folder `jui build`
    never writes (iOS: "Layouts directory not found"; a face whose folder
    exists from before: its stale copy, silently)."""
    problems = []
    for platform, pconfig in platforms.items():
        if not isinstance(pconfig, dict) or not pconfig.get("root") or not pconfig.get("layoutsDir"):
            continue
        reads = tool_read_dirs(platform, project_root / pconfig["root"])
        if reads is None:
            continue
        writes = {"layouts": os.path.normpath(pconfig["layoutsDir"])}
        writes["styles"] = os.path.normpath(os.path.join(os.path.dirname(writes["layouts"]), "Styles"))
        for kind in ("layouts", "styles"):
            if kind == "styles" and reads.get("layouts", writes["layouts"]) != writes["layouts"]:
                break   # the Styles follow layoutsDir: the layouts' line already says what to set
            if kind in reads and reads[kind] != writes[kind]:
                field = "layouts_directory" if kind == "layouts" else "styles_directory"
                fix = (f"set platforms.{platform}.layoutsDir to \"{reads['layouts']}\"" if kind == "layouts"
                       else f"put {reads['file']}'s {field} beside its layouts_directory (\"Styles\")")
                problems.append(
                    f"[{platform}] jui build writes the {kind} to {pconfig['root']}/{writes[kind]} "
                    f"(jui.config.json platforms.{platform}.layoutsDir \"{pconfig['layoutsDir']}\"), but "
                    f"{reads['file']} reads {pconfig['root']}/{reads[kind]} (source_directory + {field}): {fix}")
    return problems


def derive_layouts_dirs(project_root: Path, platforms: dict) -> bool:
    """Set each face's ``layoutsDir`` to where its tool reads the layouts (`jui
    init`, once each tool has written its config). Whether any changed."""
    changed = False
    for platform, pconfig in platforms.items():
        if not isinstance(pconfig, dict) or not pconfig.get("root"):
            continue
        reads = tool_read_dirs(platform, project_root / pconfig["root"])
        if reads and reads.get("layouts") and reads["layouts"] != pconfig.get("layoutsDir"):
            pconfig["layoutsDir"] = reads["layouts"]
            changed = True
    return changed
