"""The baseline records the subject AND the tools that drew the picture.

`rendered_by` held the library SHA — the subject. The tools that decide
what the picture looks like (Xcode, the SDK, the simulator runtime, the
device; on Android the API level and AGP) were recorded nowhere. So when
an entry `moved`, the file could say "the library is the same / different"
and nothing else: a token change in a new Xcode moves pictures that use
none of the changed features, and from the baseline alone that is
indistinguishable from a library regression.

🔻 The mechanism was already there and one leg was already using it.
`rendered_by` is a free-form dict, and the web leg has passed
`chromium=<version>` since it was written. iOS and Android passed the
library SHA only. Nothing had to be built — the empty half had to be
filled, and an arm had to hold it filled.

That is why the arms below are about the WORKFLOW and not only the writer:
the writer accepted tool keys all along. What did not exist was anyone
passing them, and nothing that noticed the absence.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "conformance-mobile.yml"

# The gate invocation is one long python -c line; read the flags out of it.
_RENDERED_BY = re.compile(r"'--rendered-by','([^=']+)=")


class TheWorkflowPassesToolsNotOnlyTheSubject(unittest.TestCase):
    """Both halves, for every platform that bakes pictures."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.keys = set(_RENDERED_BY.findall(cls.text))

    def test_the_gate_is_still_the_place_that_passes_them(self):
        """Positive control: if the flag moved, every arm below goes quiet."""
        self.assertGreater(
            len(self.keys), 0, "no --rendered-by in the workflow — the arms below measure nothing"
        )

    def test_every_platform_records_its_subject(self):
        for key in ("swiftjsonui.src", "kotlinjsonui.src", "rjui.src"):
            self.assertIn(key, self.keys, f"{key} missing — the subject is unrecorded")

    def test_every_platform_records_its_tools(self):
        """The half that was empty. web already had `chromium`."""
        for key in ("ios.toolchain", "android.toolchain", "chromium"):
            self.assertIn(key, self.keys, f"{key} missing — the tools are unrecorded")

    def test_the_tool_keys_are_fed_by_a_step_that_measures(self):
        """A hardcoded string would satisfy the arm above and record a lie.

        Each toolchain value must come from a job output, and that output
        must come from a step that runs something.
        """
        for job, step_id in (("ios", "toolchain"), ("android", "android_toolchain")):
            self.assertIn(
                f"toolchain: ${{{{ steps.{step_id}.outputs.spec }}}}",
                self.text,
                f"{job}: toolchain output is not wired to a step",
            )
            self.assertIn(f"id: {step_id}", self.text, f"{job}: no step with id {step_id}")

    def test_ios_names_the_four_tools_that_move_pictures(self):
        """Xcode / SDK / simulator OS / device. Dropping one loses a cause."""
        block = self.text[self.text.index("id: toolchain") :][:2000]
        for field in ("xcode=", "sdk=", "simulator_os=", "device="):
            self.assertIn(field, block, f"ios toolchain does not record {field}")

    def test_ios_reads_the_tools_instead_of_hardcoding_them(self):
        block = self.text[self.text.index("id: toolchain") :][:2000]
        self.assertIn("xcodebuild -version", block)
        self.assertIn("--show-sdk-version", block)
        self.assertIn("simctl list runtimes", block)

    def test_android_names_its_tools(self):
        block = self.text[self.text.index("id: android_toolchain") :][:2000]
        for field in ("api_level=", "agp=", "gradle="):
            self.assertIn(field, block, f"android toolchain does not record {field}")


class WhatTheRecordCannotDo(unittest.TestCase):
    """Name the limits in an arm, so a later reader does not over-read it."""

    def test_the_record_is_metadata_and_never_part_of_a_comparison(self):
        """Folding tools into `hashes` would make an Xcode bump read as
        "the picture changed" — the confusion this exists to end."""
        from jui_cli.conformance import baseline

        src = Path(baseline.__file__).read_text(encoding="utf-8")
        head = src[: src.index('"hashes": hashes')]
        self.assertIn('"rendered_by"', head, "rendered_by must be written outside hashes")

    def test_a_local_bake_records_no_tools_by_default(self):
        """Guessing them here would write a confident wrong answer — the
        same reason the library SHA is absent unless passed."""
        import tempfile

        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed (jui-tools[conformance])")
        from jui_cli.conformance import baseline
        import json as _json

        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp)
            shots = conf / "artifacts" / "ios"
            shots.mkdir(parents=True)
            Image.new("L", (8, 8), 9).save(shots / "A.png")
            baseline.update_baseline(conf, "ios")
            m = _json.loads((conf / "baselines" / "local" / "ios.hashes.json").read_text())
            self.assertEqual(m["rendered_by"], {})


if __name__ == "__main__":
    unittest.main()
