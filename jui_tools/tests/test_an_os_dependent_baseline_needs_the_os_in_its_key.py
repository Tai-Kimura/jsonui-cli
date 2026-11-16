"""When a picture depends on the OS that drew it, the baseline key must say which.

`glass` resolves through `#available(iOS 26.0, *)`, and that asks the RUNNING
OS -- so the same fixture draws a different picture on iOS 25 and on iOS 26.
The baseline is keyed by `<env>/<platform>`, which does not separate those, so
two runs on different simulator runtimes compare against each other and every
glass fixture reports `moved`.

✅ ANSWERED 2026-09-15. The condition arrived exactly as written — `glass` was
baked into `ci/ios` and this file went red on the bake — and the answer is
`hashes_by_os` in the same manifest rather than `<platform>-<os>.hashes.json`.
Per-ENTRY and not per-FILE, because the measurement said the file-level claim
is false: of the 61 entries that moved on the toolchain change, every one is a
system-DRAWN control (26 Switch / 12 TabView / 10 Segment / 6 control_* /
5 Slider / 2 Collection, zero others) — that is the SDK the host links against,
a different axis from `#available`. Keying the file by OS would have asserted
that the whole corpus depends on the running OS.

This arm stays: it is what stops an OS-dependent picture landing in the
agnostic table again. `test_the_os_key_gates_the_comparison` is its other
half — that the key PREVENTS the comparison rather than annotating it.

The original deferral is kept below because the reasoning is still how the
decision should be read.

THIS WAS AN ARM AND NOT A FIX, for a measured reason. On this tree:

    glass fixtures                    2  (common/glass__true, __false)
    entries for them in ci/ios        0  of 856
    entries for them in local/ios     0  of 856

The pictures have never been baked. The collision needs a baked entry AND a
re-bake on a different runtime, and the first half has not happened -- so
splitting the baseline today would mean deciding, with no information, what
to do with 856 existing entries whose OS version nobody recorded (the
`rendered_by` field only started carrying `simulator_os` in this same train).
Changing a structure while the answer is unknown is worse than deciding when
the condition arrives.

What is NOT acceptable is leaving it to be rediscovered. A property that
holds by accident has no guard: nobody looks for a problem they do not have.
So this file fails the moment the condition becomes real, and says what to do.

`rendered_by` ALREADY records the OS (conformance-mobile.yml passes
`simulator_os=iOS <runtime>` inside `ios.toolchain`), and the gate emits a
NOTICE when a regression is measured against a baseline drawn by different
tools. A notice is not a key: it explains the `moved` entries after the fact
rather than preventing the comparison. Different quantities; this arm is
about the second.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

CONFORMANCE = REPO / "conformance"


def _os_dependent_attributes() -> set:
    """Declared attributes whose rendering depends on the running OS.

    Derived from the declaration, not from a list of names: an attribute
    earns membership by saying so in its own description. Hardcoding
    "glass" here would make this file a second spelling of the vocabulary,
    which is the defect this train spent the day on.
    """
    definitions = json.loads(
        (REPO / "shared" / "core" / "attribute_definitions.json").read_text(
            encoding="utf-8"
        )
    )
    found = set()
    for component, attrs in definitions.items():
        if component.startswith("_") or not isinstance(attrs, dict):
            continue
        for attribute, defn in attrs.items():
            if not isinstance(defn, dict):
                continue
            blob = json.dumps(defn, ensure_ascii=False)
            if "#available" in blob or "UIGlassEffect" in blob or "glassEffect" in blob:
                found.add(component + "." + attribute)
    return found


def _fixture_ids_for(attributes: set) -> set:
    manifest = json.loads((CONFORMANCE / "manifest.json").read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"] if isinstance(manifest, dict) else manifest
    wanted = {a.split(".", 1)[1].lower() for a in attributes}
    out = set()
    for f in fixtures:
        stem = f["id"].rsplit("/", 1)[-1].split("__")[0].lower()
        if stem in wanted:
            out.add(f["id"])
    return out


def _baseline_entries(env: str, platform: str) -> set:
    path = CONFORMANCE / "baselines" / env / (platform + ".hashes.json")
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("hashes", {}))


def _artifact_name(fixture_id: str) -> str:
    return fixture_id.replace("/", "_") + ".png"


def test_the_derivation_finds_something():
    """Positive control. Every arm below narrows this set; if the predicate
    stops matching, they all pass by checking nothing."""
    attrs = _os_dependent_attributes()
    assert attrs, "no OS-dependent attribute found -- the predicate has gone blind"
    assert any(a.endswith(".glass") for a in attrs), sorted(attrs)


def test_the_fixtures_are_locatable():
    """Second control: the derivation reaches actual fixtures, not just a
    name. A set of attributes nothing renders would make the tripwire
    unfireable."""
    ids = _fixture_ids_for(_os_dependent_attributes())
    assert ids, "OS-dependent attributes exist but no fixture exercises them"


def test_no_os_dependent_picture_is_baked_under_an_os_agnostic_key():
    """THE TRIPWIRE.

    Green today because nothing is baked. It fires the first time somebody
    bakes one of these, and the message is the instruction.
    """
    ids = _fixture_ids_for(_os_dependent_attributes())
    names = {_artifact_name(i) for i in ids}
    baked = []
    for env in ("ci", "local"):
        for platform in ("ios", "android", "web"):
            hit = names & _baseline_entries(env, platform)
            baked += [env + "/" + platform + ": " + n for n in sorted(hit)]
    assert not baked, (
        "An OS-dependent picture has been baked into a baseline whose key is "
        "only <env>/<platform>:\n  " + "\n  ".join(baked) + "\n\n"
        "These fixtures resolve through an availability check, so the same "
        "fixture draws differently on different simulator runtimes, and the "
        "next bake on another runtime will report every one of them as "
        "`moved` with nothing wrong.\n\n"
        "The baseline key has to carry the OS version before these are baked "
        "-- `baselines/<env>/<platform>-<os>.hashes.json` or equivalent. "
        "`rendered_by` already records the runtime, but that produces a "
        "NOTICE after a regression is measured; it does not stop the "
        "comparison from happening.\n\n"
        "Deciding this was deferred on 2026-09-14 for a measured reason: at "
        "that point 0 of 856 entries were OS-dependent, and 856 existing "
        "entries had no recorded OS version to migrate by. That reason "
        "expires exactly here."
    )
