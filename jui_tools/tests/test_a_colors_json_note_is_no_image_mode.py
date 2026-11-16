"""A `_` key in colors.json is a note, not a colour mode, for jui build's
image-modes stage too.

`read_modes` took the first content key to tell a themed file from a flat
one, and did not leave the notes out: a themed file with `_comment` on top
read as flat, its only mode was `light`, and every `<name>.<mode>.svg` was an
ERROR — jui build exited 1. The colour stage (ColorManagerCore.note_key?) had
been reading the same file right since 2.5.14.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core import image_modes

THEMED = {"modes": ["light", "dark"], "fallback_mode": "light",
          "light": {"ink": "#111111"}, "dark": {"ink": "#EEEEEE"}}


def _modes(body) -> list[str]:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "colors.json"
        path.write_text(json.dumps(body))
        return image_modes.read_modes(path)


class AColorsJsonNoteIsNoImageMode(unittest.TestCase):
    def test_a_note_on_top_of_a_themed_file_leaves_its_modes(self):
        self.assertEqual(_modes({"_comment": "notes", **THEMED}), ["light", "dark"])

    def test_control_the_same_file_without_the_note(self):
        self.assertEqual(_modes(THEMED), ["light", "dark"])

    def test_a_note_in_a_palette_is_not_read(self):
        body = {"light": {"_comment": "n", "ink": "#111111"}, "dark": {"_comment": "n", "ink": "#EEEEEE"}}
        self.assertEqual(_modes(body), ["light", "dark"])

    def test_a_flat_file_with_a_note_on_top_is_the_one_mode_light(self):
        self.assertEqual(_modes({"_comment": "notes", "ink": "#111111"}), ["light"])

    def test_a_dark_picture_beside_a_note_on_top_is_no_error(self):
        modes = _modes({"_comment": "notes", **THEMED})
        with tempfile.TemporaryDirectory() as d:
            svgs = [Path(d) / "logo.svg", Path(d) / "logo.dark.svg"]
            for p in svgs:
                p.write_text("<svg/>")
            _, variants, errors = image_modes.split(svgs, modes)
        self.assertEqual(errors, [])
        self.assertIn("logo", variants)


if __name__ == "__main__":
    unittest.main()
