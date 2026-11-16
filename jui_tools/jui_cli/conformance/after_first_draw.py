"""Did every host fire the change a fixture declares for after its first draw?

A visual fixture whose subject is a reaction to a change declares it in its
manifest state as ``afterFirstDraw: {name, set: {var, value}}``
(INTERACTIVE_HOST_CONTRACT.md "afterFirstDraw"): the host draws the fixture,
sets the var to the literal once, and the runner photographs it only after the
picture has come to rest. A scrollTo request is such a change — the value a
list is drawn with scrolls nowhere (jsonui-cli 1.9.0) — and before this the
scrollAnchor fixtures photographed a list nothing had asked to scroll, so
top / center / bottom drew one picture on every face
(conformance-collection-scrollanchor-family-does-not-discriminate).

A host that does not fire leaves the fixture at its first draw, and that
picture is a perfectly good screenshot: it compares, it has a baseline, and
every other check reads it as the fixture. So the runner stamps the result
(RESULTS_SCHEMA.md ``afterFirstDraw``) and this check fails a declared
fixture whose result does not say ``fired``:

* an entry with no stamp at all — a host or runner that does not implement
  the contract;
* a stamp that says ``not-fired`` — the host never stamped a frame drawn with
  the changed value within the runner's budget.

A skipped entry is not judged here (skips are counted where they are judged).
The codegen faces' results (``codegen/<platform>.results.json``) are judged
when they exist: parity compares those pictures with the dynamic ones, and an
unfired codegen picture would be compared as if it were the fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

#: The faces whose results carry an afterFirstDraw stamp.
CODEGEN_FACES = ("ios", "android")


def declared(manifest: dict) -> dict[str, dict]:
    """``{fixture id: afterFirstDraw declaration}`` for every declaring fixture."""
    out = {}
    for entry in manifest.get("fixtures", []):
        decl = ((entry.get("state") or {}).get("afterFirstDraw"))
        if decl:
            out[entry["id"]] = {"decl": decl, "platforms": entry.get("platforms") or []}
    return out


def _results(path: Path) -> dict[str, dict] | None:
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {e["id"]: e for e in doc.get("results", []) if isinstance(e, dict) and "id" in e}


def problems_for(face: str, decls: dict[str, dict], results: dict[str, dict]) -> tuple[list[str], int]:
    """Problems for one results file, and how many declared entries it judged."""
    problems: list[str] = []
    judged = 0
    platform = face.split(" ", 1)[0]
    for fid in sorted(decls):
        if platform not in decls[fid]["platforms"]:
            continue
        entry = results.get(fid)
        if entry is None or entry.get("status") == "skipped":
            continue
        judged += 1
        stamp = entry.get("afterFirstDraw")
        if not isinstance(stamp, dict):
            problems.append(
                f"{face}: {fid} declares afterFirstDraw but its result carries no stamp — "
                "the host or runner does not implement the contract, so the screenshot "
                "may be the first draw"
            )
        elif stamp.get("status") != "fired":
            problems.append(
                f"{face}: {fid} afterFirstDraw {stamp.get('status')!r} — "
                f"{stamp.get('landing', 'no landing recorded')}"
            )
    return problems, judged


def judge(
    conformance_dir: Path,
    platforms: Sequence[str],
    *,
    results_dir: Path | None = None,
    codegen: bool = False,
) -> tuple[list[str], list[str]]:
    """``(problems, notices)`` for *platforms* (and their codegen faces with *codegen*)."""
    conformance_dir = Path(conformance_dir)
    manifest = json.loads((conformance_dir / "manifest.json").read_text(encoding="utf-8"))
    decls = declared(manifest)
    if not decls:
        return [], []
    results_dir = Path(results_dir) if results_dir else conformance_dir / "results"
    problems: list[str] = []
    notices: list[str] = []
    for platform in dict.fromkeys(platforms):
        faces = [(platform, results_dir / f"{platform}.results.json")]
        if codegen and platform in CODEGEN_FACES:
            faces.append((f"{platform} codegen", conformance_dir / "codegen" / f"{platform}.results.json"))
        for face, path in faces:
            results = _results(path)
            if results is None:
                continue  # a missing results file is the report's own failure
            found, judged = problems_for(face, decls, results)
            problems.extend(found)
            if not found:
                notices.append(f"{face}: afterFirstDraw fired on {judged} of {judged} declaring fixture(s)")
    return problems, notices
