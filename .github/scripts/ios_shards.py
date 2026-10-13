#!/usr/bin/env python3
"""Split conformance-mobile's iOS jobs into shards, and put the shards back
together as the one result the report reads.

One iOS job took 108-114 minutes (run 38393632937): the fixture suite (one
XCTest, ~30 min) and 124 probe tests (~60-70 min) ran one after another on one
simulator. A shard runs a contiguous slice of the suite's runnable fixtures
(SwiftJsonUI's CONFORMANCE_SHARD=k/n) and a share of the probe classes
(CONFORMANCE_ONLY_TESTING), so n shards take about 1/n of the tests each.

    ios_shards.py tests <UITests dir>
        the XCTest classes and test methods the sources declare
    ios_shards.py plan  <UITests dir> <weights.json> <mode> <n> <k>
        shard k's test classes, space-separated (ConformanceUITests in every
        shard — each runs its own slice of the suite)
    ios_shards.py merge --mode ios|ios-codegen --shards N --uitests DIR
                        --manifest PATH --out DIR SHARD_DIR...
        the merged results file, screenshots and per-test record under DIR,
        or exit 1 naming what does not add up
    ios_shards.py meta SHARD_DIR...
        key=value per line from the shards' meta.json, which must agree

THE MERGE IS THE GATE THAT NOTHING WAS DROPPED. It proves, rather than
assumes, that the shards partition the run:
- exactly the shards 1..N, each once, each with the same manifest hash;
- fixtures: every shard counted the same runnable total; their `executed`
  lists are disjoint and together that total; each runnable fixture's result
  comes from the shard that ran it, and one that no shard ran (skipped for
  its own reason) reads the same in every shard. A results file without the
  shard record is a SwiftJsonUI that ignored CONFORMANCE_SHARD — every shard
  ran everything — and is refused;
- probes: every (class, test) the sources declare is in exactly one shard's
  record, and nothing else is; the suite's one test is in every shard;
- screenshots: no two shards wrote the same file, and every screenshot or
  frames record a result names is there.

Planning is deterministic — the same sources, weights, mode and n give every
shard the same plan, so no plan job is needed: each shard computes its own
share, and the merge recomputes the union from the sources.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

SUITE_CLASS = "ConformanceUITests"
SUITE_TEST = "testConformanceSuite"
ELSEWHERE = "in another shard"  # SwiftJsonUI ShardRecord.elsewhere

TEST_CASE_CLASS = re.compile(r"\bclass\s+(\w+)\s*:\s*XCTestCase\b")
TEST_FUNC = re.compile(r"\bfunc\s+(test\w*)\s*\(\s*\)")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")
RECORD = re.compile(r"^Test Case '-\[[\w.]+?\.(\w+) (\w+)\]' (passed|failed|skipped) \(([\d.]+) seconds\)")

# Per mode: where run_conformance.sh / collect_results.sh put the results file
# and the screenshots, relative to the conformance dir (and to a shard's dir).
LAYOUT = {
    "ios": ("results/ios.results.json", "artifacts/ios"),
    "ios-codegen": ("codegen/ios.results.json", "artifacts/ios-codegen"),
}


class Refused(Exception):
    """The shards do not add up to one run."""


def declared_tests(uitests: Path) -> dict[str, list[str]]:
    """{class: [test, ...]} from the sources, comments removed. A source with
    tests and not exactly one XCTestCase class is refused: its tests could not
    be attributed, and a plan built on a guess would drop or double them."""
    out: dict[str, list[str]] = {}
    for source in sorted(uitests.rglob("*.swift")):
        if "Vendor" in source.relative_to(uitests).parts:
            continue
        text = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", source.read_text(encoding="utf-8", errors="replace")))
        classes = TEST_CASE_CLASS.findall(text)
        tests = TEST_FUNC.findall(text)
        if not tests and not classes:
            continue
        if len(classes) != 1:
            raise Refused(f"{source.name}: {len(classes)} XCTestCase classes with {len(tests)} tests — "
                          "cannot tell which class a test belongs to")
        if classes[0] in out:
            raise Refused(f"{classes[0]} is declared in two files")
        out[classes[0]] = sorted(tests)
    if SUITE_CLASS not in out:
        raise Refused(f"no {SUITE_CLASS} in {uitests}")
    return out


def plan(classes: list[str], weights: dict[str, float], n: int) -> list[list[str]]:
    """The probe classes in n shares of about equal weight: longest first, each
    to the lightest share so far (ties to the lower share). A class with no
    weight counts as the median — a new probe lands somewhere, never nowhere."""
    if n < 1:
        raise Refused(f"n must be at least 1, got {n}")
    known = sorted(weights[c] for c in classes if c in weights)
    median = known[len(known) // 2] if known else 1.0
    load = [0.0] * n
    shares: list[list[str]] = [[] for _ in range(n)]
    for cls in sorted(classes, key=lambda c: (-weights.get(c, median), c)):
        k = min(range(n), key=lambda i: (load[i], i))
        shares[k].append(cls)
        load[k] += weights.get(cls, median)
    return [sorted(s) for s in shares]


def shard_classes(uitests: Path, weights_file: Path, mode: str, n: int, k: int) -> list[str]:
    if not 1 <= k <= n:
        raise Refused(f"shard {k} of {n}")
    weights = json.loads(weights_file.read_text(encoding="utf-8")).get(mode)
    if weights is None:
        raise Refused(f"{weights_file} has no weights for {mode}")
    probes = [c for c in declared_tests(uitests) if c != SUITE_CLASS]
    return [SUITE_CLASS] + plan(probes, weights, n)[k - 1]


def read_record(path: Path) -> list[tuple[str, str, str, float]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = RECORD.match(line)
        if m:
            out.append((m.group(1), m.group(2), m.group(3), float(m.group(4))))
    return out


def merge(mode: str, n: int, uitests: Path, manifest: Path, shard_dirs: list[Path], out: Path) -> dict:
    results_rel, artifacts_rel = LAYOUT[mode]
    problems: list[str] = []

    files = {}
    for d in shard_dirs:
        path = d / results_rel
        if not path.is_file():
            problems.append(f"{d.name}: no {results_rel}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data.get("shard")
        if not isinstance(record, dict):
            problems.append(f"{d.name}: {results_rel} has no shard record — the SwiftJsonUI that ran "
                            "ignores CONFORMANCE_SHARD, so this shard ran every fixture")
            continue
        if record.get("count") != n:
            problems.append(f"{d.name}: shard record says {record.get('index')}/{record.get('count')}, the run has {n}")
            continue
        if record.get("index") in files:
            problems.append(f"{d.name}: shard {record.get('index')} twice")
            continue
        files[record["index"]] = (d, data)
    missing = sorted(set(range(1, n + 1)) - set(files))
    if missing:
        problems.append(f"shard(s) {missing} of {n} produced no usable results")
    if problems:
        raise Refused("\n".join(problems))

    shards = [files[k] for k in range(1, n + 1)]
    first = shards[0][1]
    for d, data in shards[1:]:
        for key in ("platform", "manifestHash"):
            if data.get(key) != first.get(key):
                problems.append(f"{d.name}: {key} {data.get(key)!r} differs from shard 1's {first.get(key)!r}")

    # Fixtures.
    totals = {data["shard"]["runnable"] for _, data in shards}
    if len(totals) != 1:
        problems.append(f"the shards counted different runnable totals: {sorted(totals)}")
    owner: dict[str, int] = {}
    for k, (d, data) in enumerate(shards, start=1):
        for fid in data["shard"]["executed"]:
            if fid in owner:
                problems.append(f"{fid}: run in shard {owner[fid]} and shard {k}")
            owner[fid] = k
    total = next(iter(totals))
    if len(owner) != total:
        problems.append(f"the shards ran {len(owner)} fixtures between them; each counted {total} runnable")

    manifest_ids = [f["id"] for f in json.loads(manifest.read_text(encoding="utf-8"))["fixtures"]]
    by_shard = [{r["id"]: r for r in data["results"]} for _, data in shards]
    for k, results in enumerate(by_shard, start=1):
        if sorted(results) != sorted(manifest_ids):
            problems.append(f"shard {k}: {len(results)} results for {len(manifest_ids)} manifest fixtures")
    if problems:
        raise Refused("\n".join(problems))

    merged = []
    for fid in [r["id"] for r in first["results"]]:
        if fid in owner:
            entry = by_shard[owner[fid] - 1][fid]
            if entry.get("detail") == ELSEWHERE:
                problems.append(f"{fid}: shard {owner[fid]} lists it as executed and as run elsewhere")
            for k, results in enumerate(by_shard, start=1):
                if k != owner[fid] and results[fid].get("detail") != ELSEWHERE:
                    problems.append(f"{fid}: shard {k} has a result for it ({results[fid].get('status')}), "
                                    f"shard {owner[fid]} ran it")
        else:
            entries = [results[fid] for results in by_shard]
            if any(e != entries[0] for e in entries[1:]):
                problems.append(f"{fid}: no shard ran it, and the shards disagree on why")
            entry = entries[0]
            if entry.get("detail") == ELSEWHERE:
                problems.append(f"{fid}: every shard says another shard ran it")
        merged.append(entry)

    census: dict[str, int] = defaultdict(int)
    for _, data in shards:
        for key, value in (data.get("webMarkers") or {}).items():
            census[key] += value

    combined = {key: value for key, value in first.items() if key not in ("shard", "results", "webMarkers")}
    combined["webMarkers"] = dict(sorted(census.items()))
    combined["results"] = merged

    # Screenshots and frames records.
    art_out = out / artifacts_rel
    art_out.mkdir(parents=True, exist_ok=True)
    origin: dict[str, str] = {}
    for d, _ in shards:
        src = d / artifacts_rel
        for f in sorted(src.rglob("*")) if src.is_dir() else []:
            if not f.is_file():
                continue
            rel = f.relative_to(src).as_posix()
            if rel in origin:
                problems.append(f"{artifacts_rel}/{rel}: written by {origin[rel]} and {d.name}")
                continue
            origin[rel] = d.name
            (art_out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, art_out / rel)
    for entry in merged:
        for key in ("screenshot", "frames"):
            named = entry.get(key)
            if named and Path(named).name not in {Path(r).name for r in origin}:
                problems.append(f"{entry['id']}: its {key} {named} is in no shard's artifacts")

    # Per-test records.
    declared = declared_tests(uitests)
    expected = {(c, t) for c, tests in declared.items() for t in tests if c != SUITE_CLASS}
    seen: dict[tuple[str, str], str] = {}
    suite: list[tuple[str, float]] = []
    lines = []
    for d, _ in shards:
        record = d / "xctests.txt"
        if not record.is_file():
            problems.append(f"{d.name}: no xctests.txt")
            continue
        suite_here = 0
        for cls, test, verdict, seconds in read_record(record):
            if (cls, test) == (SUITE_CLASS, SUITE_TEST):
                suite_here += 1
                suite.append((verdict, seconds))
                continue
            if (cls, test) not in expected:
                problems.append(f"{d.name}: ran {cls}.{test}, which the sources do not declare")
            if (cls, test) in seen:
                problems.append(f"{cls}.{test}: in {seen[(cls, test)]} and {d.name}")
            seen[(cls, test)] = d.name
            lines.append(f"Test Case '-[ConformanceHostUITests.{cls} {test}]' {verdict} ({seconds:.3f} seconds).")
        if suite_here != 1:
            problems.append(f"{d.name}: {SUITE_CLASS}.{SUITE_TEST} {suite_here} times, not once")
    for cls, test in sorted(expected - set(seen)):
        problems.append(f"{cls}.{test}: in no shard's record")
    if problems:
        raise Refused("\n".join(problems))

    suite_verdict = "failed" if any(v == "failed" for v, _ in suite) else (
        "skipped" if all(v == "skipped" for v, _ in suite) else "passed")
    lines.append(f"Test Case '-[ConformanceHostUITests.{SUITE_CLASS} {SUITE_TEST}]' {suite_verdict} "
                 f"({sum(s for _, s in suite):.3f} seconds).")
    lines.sort()

    (out / results_rel).parent.mkdir(parents=True, exist_ok=True)
    (out / results_rel).write_text(json.dumps(combined, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    (out / "xctests.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    statuses = Counter(e["status"] for e in merged)
    return {"fixtures": len(merged), "statuses": dict(sorted(statuses.items())), "runnable": total,
            "screenshots": sum(1 for r in origin if r.endswith(".png")), "probe_tests": len(seen),
            "shards": n}


def meta(shard_dirs: list[Path]) -> dict[str, str]:
    """What drew the pixels (meta.json: library_sha, toolchain), the same in
    every shard or refused — shards drawn by different sources are not one
    run. No shard writing meta.json gives {}."""
    seen = {d.name: json.loads((d / "meta.json").read_text(encoding="utf-8"))
            for d in shard_dirs if (d / "meta.json").is_file()}
    if not seen:
        return {}
    if len(seen) != len(shard_dirs):
        raise Refused(f"meta.json in {sorted(seen)} only, of {sorted(d.name for d in shard_dirs)}")
    values = list(seen.values())
    if any(v != values[0] for v in values[1:]):
        raise Refused("the shards were drawn by different sources: "
                      + "; ".join(f"{k}: {v}" for k, v in sorted(seen.items())))
    return values[0]


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "tests":
        declared = declared_tests(Path(argv[1]))
        for cls, tests in declared.items():
            print(f"{cls}: {len(tests)}")
        print(f"{len(declared)} classes, {sum(len(t) for t in declared.values())} tests")
        return 0
    if len(argv) == 6 and argv[0] == "plan":
        print(" ".join(shard_classes(Path(argv[1]), Path(argv[2]), argv[3], int(argv[4]), int(argv[5]))))
        return 0
    if len(argv) >= 2 and argv[0] == "meta":
        for key, value in meta([Path(d) for d in argv[1:]]).items():
            print(f"{key}={value}")
        return 0
    if argv and argv[0] == "merge":
        p = argparse.ArgumentParser(prog="ios_shards.py merge")
        p.add_argument("--mode", required=True, choices=sorted(LAYOUT))
        p.add_argument("--shards", required=True, type=int)
        p.add_argument("--uitests", required=True, type=Path)
        p.add_argument("--manifest", required=True, type=Path)
        p.add_argument("--out", required=True, type=Path)
        p.add_argument("shard_dirs", nargs="+", type=Path)
        a = p.parse_args(argv[1:])
        summary = merge(a.mode, a.shards, a.uitests, a.manifest, a.shard_dirs, a.out)
        print(f"merged {a.mode}: " + ", ".join(f"{k}={v}" for k, v in summary.items()))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Refused as e:
        print(f"error: the iOS shards do not add up to one run:\n{e}", file=sys.stderr)
        sys.exit(1)
