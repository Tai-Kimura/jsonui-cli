"""A dynamic converter that re-implements the modifier order must not lose a stage.

THE DEFECT THIS EXISTS FOR

SwiftJsonUI's dynamic renderer has one pipeline — ``applyStandardModifiers`` —
whose stage list includes ``border``. Four converters opt out of it and
re-implement the order by hand, mirroring the generator's Ruby: Label, Image,
NetworkImage and Text. All four copied the chain as far as ``cornerRadius`` and
stopped, so ``borderWidth`` + ``borderColor`` on those components drew nothing
in dynamic mode while codegen drew the outline.

Measured 2026-09-16 on a consumer screen: ``type: Label, borderWidth: 1,
borderColor: "gold", cornerRadius: 18``. The generated view emits
``.overlay(RoundedRectangle(cornerRadius: 18).stroke(gold, lineWidth: 1))``;
the dynamic chain went background → cornerRadius → textShadow → margins, with
no border step anywhere. Two screenshots of the same screen, one with the
outline and one without.

⚠️ WHY NO CONFORMANCE FIXTURE CAUGHT IT. Every fixture that declares
``borderWidth`` — nine of them — declares it on ``type: "View"``, and View is
one of the components that DOES use the standard pipeline. The corpus asks the
border question only where the answer was already yes.

So this arm asks the question at the source level instead, where it is cheap
and total: a converter that applies cornerRadius by hand has taken over the
chain, and it owns every stage of it that its component can declare.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ENV_VAR = "JSONUI_SWIFTJSONUI_PATH"
SIBLING = "SwiftJsonUI"
CONVERTERS = "Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Converters"

#: A converter that calls this has NOT taken the chain over — the pipeline
#: applies every stage, border included.
PIPELINE = "applyStandardModifiers"
#: Evidence that the converter re-implements the order itself.
HAND_ROLLED = "applyCornerRadius"
#: The stage that went missing.
REQUIRED = "applyBorder"


def _sibling() -> tuple[Path | None, bool]:
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override), True
    candidate = REPO_ROOT.parent / SIBLING
    return (candidate if candidate.exists() else None), False


class AHandRolledChainKeepsTheBorderStageTests(unittest.TestCase):
    def test_every_hand_rolled_converter_applies_the_border(self) -> None:
        root, named = _sibling()
        if root is None:
            # Same three-ways-out reasoning as the web-marker source arm: under
            # CI a missing sibling is the defect (a renamed env var silently
            # deletes this gate), locally it is an honest skip.
            if os.environ.get("CI"):
                self.fail(
                    f"running under CI but no {SIBLING} checkout was found — "
                    f"${ENV_VAR} is unset and {REPO_ROOT.parent / SIBLING} does "
                    "not exist. A skip here would delete this gate silently"
                )
            self.skipTest(f"no {SIBLING} sibling and ${ENV_VAR} unset")
        directory = root / CONVERTERS
        if not directory.is_dir():
            self.assertFalse(
                named,
                f"${ENV_VAR} names {root} but {CONVERTERS} is not there — widen "
                "the job's sparse-checkout rather than letting this skip",
            )
            self.skipTest(f"{directory} is absent")

        hand_rolled: list[str] = []
        missing: list[str] = []
        scanned = 0
        for path in sorted(directory.glob("*.swift")):
            text = path.read_text(encoding="utf-8")
            scanned += 1
            if PIPELINE in text or HAND_ROLLED not in text:
                continue
            hand_rolled.append(path.name)
            if REQUIRED not in text:
                missing.append(path.name)

        # 🔻 A SCAN THAT FOUND NO HAND-ROLLED CONVERTER WOULD PASS WITHOUT
        # ASKING ANYTHING. The population is the point of the arm, so it is
        # asserted and printed rather than assumed.
        self.assertGreater(scanned, 10, f"only {scanned} converter(s) read — wrong directory?")
        self.assertGreater(
            len(hand_rolled),
            0,
            f"no converter under {CONVERTERS} re-implements the chain "
            f"(scanned {scanned}). Either the design changed — in which case "
            "delete this arm and say so — or the predicate stopped matching",
        )
        self.assertEqual(
            missing,
            [],
            f"{missing} apply cornerRadius by hand without applyBorder. A "
            "component whose chain is hand-rolled owns every stage of it: a "
            "declared border on these draws in codegen and not in dynamic. "
            f"(hand-rolled converters: {hand_rolled}; scanned {scanned})",
        )
        print(
            f"[dynamic chain arm] scanned {scanned} converter(s), "
            f"{len(hand_rolled)} hand-rolled: {hand_rolled}"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
