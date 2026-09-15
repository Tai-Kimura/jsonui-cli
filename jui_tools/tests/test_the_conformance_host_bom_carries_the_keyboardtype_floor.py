"""The conformance host's Compose BOM must still contain what the emitter names.

`jui conformance`'s codegen host compiles generated Kotlin against whatever
Compose the KotlinJsonUI `conformance-host` module resolves. The emitter names
`KeyboardType.Date / Time / DateTime / DecimalSigned`, which exist only from
ui-text 1.12.0. kjui can degrade all four to `KeyboardType.Text`, but that floor
is DECLARED, not detected: it acts only when a project sets `compose_version`,
and the staging config the codegen host generates sets none — correctly, because
the host's BOM does carry the members. Lower the BOM and the codegen host stops
compiling, with nothing in the per-push lane to say so.

**The only guard was weekly.** `android-codegen` in conformance-mobile.yml builds
the APK and would go red, but it runs on a Sunday cron. `ruby-generation-parity`
runs the same generator and compiles no Kotlin — it compares bytes. So a BOM drop
could sit on main for six days looking green.

THE BOUNDARY IS MEASURED, AND IT IS A THRESHOLD NOW, NOT AN INTERVAL. The ticket
that opened this could only say "above 2026.05.01, at or below 2026.08.00",
because 2026.06 and 2026.07 were not in the local cache and it refused to state a
fact about versions nobody had looked at. Measured 2026-09-15 from each BOM's own
pom on dl.google.com, and from `javap` over the ui-text artifact itself:

    compose-bom 2026.05.01 -> ui-text 1.11.2   10 members, none of the four
    compose-bom 2026.06.00 -> ui-text 1.11.3   (same 1.11 line)
    compose-bom 2026.06.01 -> ui-text 1.11.4   10 members, none of the four
    compose-bom 2026.07.*  -> DOES NOT EXIST   (404 on the maven mirror)
    compose-bom 2026.08.00 -> ui-text 1.12.0   26 members, ALL FOUR
    compose-bom 2026.09.00 -> ui-text 1.12.1   (current host)

⚠️ The javap arm needed its own control: the getters are name-mangled
(`getDate-PjHm6EE`), so a plain `getDate()` search returns 0 for BOTH versions
and would have read as "1.12.0 does not have them either".

⚠️ Scope: this reads the DECLARED BOM coordinate, not the resolved graph. A
project that overrides ui-text directly, or a BOM that changes what it pins
without changing its version, is outside what a text check can see. What it does
catch is the move that actually happens — somebody lowers the BOM line.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: First compose-bom whose ui-text carries Date / Time / DateTime /
#: DecimalSigned. BOM versions sort correctly as plain strings (YYYY.MM.PP).
BOM_FLOOR = "2026.08.00"

#: Where the host declares it, relative to a KotlinJsonUI checkout.
BOM_FILE = Path("conformance-host") / "build.gradle.kts"

BOM_RE = re.compile(r'androidx\.compose:compose-bom:([0-9]{4}\.[0-9]{2}\.[0-9]{2})')


def _kotlin_repo() -> tuple[Path | None, str]:
    """``(path, why_not)`` — the checkout, or why this arm cannot run.

    🔻 AN ENV VAR THAT IS SET IS A PROMISE THE FILE IS THERE. When
    `JSONUI_KOTLINJSONUI_PATH` names a checkout, a missing BOM file is NOT a
    reason to skip — it means the sparse-checkout does not include the path
    this arm reads, which is one of the three independent ways a cross-repo
    arm silently leaves CI (the others being the env spelling and the job not
    checking the sibling out at all). Skipping there would restore exactly the
    silence this test exists to end.
    """
    override = os.environ.get("JSONUI_KOTLINJSONUI_PATH")
    if override:
        return Path(override), ""
    fallback = REPO_ROOT.parent / "KotlinJsonUI"
    if fallback.exists():
        return fallback, ""
    return None, (
        "no KotlinJsonUI checkout: JSONUI_KOTLINJSONUI_PATH is unset and "
        f"{fallback} does not exist"
    )


class ConformanceHostBomFloorTests(unittest.TestCase):
    def setUp(self):
        self.repo, why_not = _kotlin_repo()
        if self.repo is None:
            self.skipTest(why_not)

    def test_the_bom_line_is_readable(self):
        # Positive control AND the sparse-checkout guard. Reaching here means a
        # checkout was named; if the file is not in it, the arm is not
        # satisfied, it is absent — and it says which.
        path = self.repo / BOM_FILE
        self.assertTrue(
            path.is_file(),
            f"{path} is not present in the KotlinJsonUI checkout. The arm cannot "
            "run. If this is CI, widen the job's sparse-checkout to include "
            f"{BOM_FILE.parent}/ — a cross-repo arm that skips here looks "
            "exactly like one that passed.",
        )
        self.assertRegex(
            path.read_text(encoding="utf-8"), BOM_RE,
            f"{path} declares no androidx.compose:compose-bom coordinate. Either "
            "the host stopped using a BOM (then this arm needs rewriting against "
            "whatever replaced it) or the spelling moved.",
        )

    def test_the_declared_bom_still_carries_the_four_keyboard_types(self):
        path = self.repo / BOM_FILE
        if not path.is_file():
            self.skipTest("covered by test_the_bom_line_is_readable")
        found = BOM_RE.findall(path.read_text(encoding="utf-8"))
        self.assertEqual(
            1, len(found),
            f"expected exactly one compose-bom coordinate in {path}, found {found}",
        )
        declared = found[0]
        self.assertGreaterEqual(
            declared, BOM_FLOOR,
            f"conformance-host declares compose-bom {declared}, below the "
            f"{BOM_FLOOR} floor. ui-text under that floor has 10 KeyboardType "
            "members and none of Date / Time / DateTime / DecimalSigned, which "
            "the kjui emitter NAMES — so the codegen host stops compiling. "
            "Either raise the BOM back, or declare compose_version in the "
            "staging config the codegen host generates so kjui degrades the "
            "four to KeyboardType.Text on purpose. Do not silence this by "
            "lowering the floor: the floor is the first BOM that has the "
            "members, measured from the artifact.",
        )

    def test_the_floor_is_a_version_the_comparison_can_order(self):
        # Boundary. String comparison is only right while every BOM version is
        # the same fixed width; `1.9.0 > 1.12.0` as text is the exact trap this
        # codebase has been bitten by before, and it is avoided here only
        # because BOM versions are zero-padded YYYY.MM.PP.
        self.assertRegex(BOM_FLOOR, r"^\d{4}\.\d{2}\.\d{2}$")
        self.assertLess("2026.06.01", BOM_FLOOR)
        self.assertGreater("2026.09.00", BOM_FLOOR)
        self.assertGreater("2027.01.00", BOM_FLOOR)


if __name__ == "__main__":
    unittest.main()
