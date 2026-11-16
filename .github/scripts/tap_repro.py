#!/usr/bin/env python3
"""The iOS tap-miss reproduction: make the loop fixtures, then judge the run.

ios-tap-repro.yml runs this. Ticket
ios-dynamic-interactive-fixture-tap-not-delivered-intermittently: twice in
CI an interactive Dynamic fixture's tap fired no callback, and a local loop
of 600 taps (unloaded and at load average 150-200) never missed. The
remaining axes live on the CI runner (Xcode 26.3, the image, its own load),
so the loop runs there.

  make  <conformance dir> <repeats>
      Appends `repeats` copies of each of the two fixtures to the manifest,
      ALTERNATING (Loop/sw_001, Loop/clip_001, Loop/sw_002, ...). Every copy
      has its own id: the host waits for a per-fixture marker, and two
      consecutive fixtures with one id would let the marker of the previous
      one answer for the next.

  judge <results.json>
      Counts the Loop/ results and prints every miss with its post-tap line
      (SwiftJsonUI 8815b51+: "a second tap made it pass (touch not
      delivered)" or "a second tap did not either"). Exits 1 when the
      results do not hold all the loop fixtures (the run stopped early) —
      a short run is not "no miss".
"""
from __future__ import annotations

import collections
import copy
import json
import sys
from pathlib import Path

SOURCES = (
    ("Switch/onValueChange__callback_fire", "sw"),
    ("common/clipToBounds__hit_overflow_true", "clip"),
)
# The fixture that ran just before each miss in CI (manifest order): a visual
# fixture of the same component, which captures app.screenshot() before the
# batch advances. --after-visual puts it in front of each interactive copy.
VISUAL_BEFORE = {
    "Switch/onValueChange__callback_fire": ("Switch/thumbTintColor__binding", "swvis"),
    "common/clipToBounds__hit_overflow_true": ("common/clipToBounds__binding", "clipvis"),
}
PREFIX = "Loop/"


def make(conformance: Path, repeats: int, after_visual: bool = False) -> int:
    manifest_path = conformance / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    by_id = {f["id"]: f for f in manifest["fixtures"]}
    wanted = [fid for fid, _ in SOURCES]
    if after_visual:
        wanted += [VISUAL_BEFORE[fid][0] for fid, _ in SOURCES]
    missing = [fid for fid in wanted if fid not in by_id]
    if missing:
        print(f"error: the manifest has no {missing}", file=sys.stderr)
        return 1
    order = []
    for fid, tag in SOURCES:
        if after_visual:
            order.append(VISUAL_BEFORE[fid])
        order.append((fid, tag))
    added = []
    for i in range(1, repeats + 1):
        for fid, tag in order:
            fixture = copy.deepcopy(by_id[fid])
            stem = f"fixtures/Loop/{tag}_{i:03d}"
            fixture["id"] = f"{PREFIX}{tag}_{i:03d}"
            layout = json.loads((conformance / fixture["layout"]).read_text())
            test = json.loads((conformance / fixture["test"]).read_text())
            test["source"]["layout"] = f"{stem}.layout.json"
            (conformance / stem).parent.mkdir(parents=True, exist_ok=True)
            (conformance / f"{stem}.layout.json").write_text(json.dumps(layout, indent=1))
            (conformance / f"{stem}.test.json").write_text(json.dumps(test, indent=1))
            fixture["layout"] = f"{stem}.layout.json"
            fixture["test"] = f"{stem}.test.json"
            added.append(fixture)
    manifest["fixtures"] += added
    manifest_path.write_text(json.dumps(manifest, indent=1))
    shape = "visual -> interactive pairs" if after_visual else "alternating"
    print(f"[tap repro] added {len(added)} loop fixture(s): {repeats} x {len(order)}, {shape}")
    for fixture in added[:4]:
        print(f"  {fixture['id']} ({fixture['class']})")
    return 0


def judge(results_path: Path, expected: int, out=sys.stdout) -> int:
    results = json.loads(results_path.read_text())["results"]
    loop = [r for r in results if r["id"].startswith(PREFIX)]
    counts = collections.Counter(r["status"] for r in loop)
    misses = [r for r in loop if r["status"] != "pass"]
    kinds = collections.Counter()
    for r in misses:
        detail = r.get("detail", "")
        if "a second tap made it pass" in detail:
            kinds["touch not delivered"] += 1
        elif "a second tap did not either" in detail:
            kinds["no handler answered"] += 1
        else:
            kinds["no post-tap line"] += 1
    print(f"[tap repro] {len(misses)} miss(es) in {len(loop)} loop fixture(s) "
          f"(expected {expected}): {dict(counts)}", file=out)
    if misses:
        print(f"[tap repro] by kind: {dict(kinds)}", file=out)
    for r in misses:
        print(f"::warning title=tap miss::{r['id']}: {r.get('detail', '')}", file=out)
    if len(loop) != expected:
        print(f"error: {len(loop)} loop result(s), {expected} expected — the run stopped "
              "before the loop finished, so its miss count is not the loop's", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) in (3, 4) and argv[0] == "make" and (len(argv) == 3 or argv[3] == "--after-visual"):
        return make(Path(argv[1]), int(argv[2]), after_visual=len(argv) == 4)
    if len(argv) == 3 and argv[0] == "judge":
        return judge(Path(argv[1]), int(argv[2]))
    print("usage: tap_repro.py make <conformance dir> <repeats> [--after-visual] | judge <results.json> <expected>",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
