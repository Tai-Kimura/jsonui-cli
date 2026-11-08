"""The spec HTML's colour swatches read colors.json as the tools read it.

`_load_colors_map` took the top level's strings as the token map. A themed
file (`{"light": {...}, "dark": {...}}`) gave no colour at all, so every token
was drawn as bare code, and its `fallback_mode` was a token; a `_` note
(`_comment`) was a token in either form. Now: notes and meta keys are no
colours, and a themed file is the palette type_converter_core picks.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.spec_doc import html_generator as hg


def _tokens(body) -> dict:
    with tempfile.TemporaryDirectory() as d:
        res = Path(d) / "Resources"
        res.mkdir()
        (res / "colors.json").write_text(json.dumps(body))
        return hg._load_colors_map(Path(d))


class SpecSwatchesReadColorsJsonAsTheToolsDo(unittest.TestCase):
    def test_a_themed_file_gives_its_fallback_palette(self):
        body = {"_comment": "n", "modes": ["light", "dark"], "fallback_mode": "dark",
                "light": {"ink": "#111111"}, "dark": {"ink": "#EEEEEE", "_note": "d"}}
        self.assertEqual(_tokens(body), {"ink": "#EEEEEE"})

    def test_a_themed_file_without_fallback_takes_light(self):
        body = {"dark": {"ink": "#EEEEEE"}, "light": {"ink": "#111111"}}
        self.assertEqual(_tokens(body), {"ink": "#111111"})

    def test_a_flat_file_leaves_its_note_out(self):
        self.assertEqual(_tokens({"_comment": "n", "ink": "#111111"}), {"ink": "#111111"})

    def test_a_themed_token_is_drawn_as_a_swatch(self):
        colors = _tokens({"light": {"ink": "#111111"}, "dark": {"ink": "#EEEEEE"}})
        html = hg._render_swatch("ink", colors)
        self.assertIn('class="swatch"', html)
        self.assertIn("#111111", html)

    def test_unreadable_or_absent_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(hg._load_colors_map(Path(d)), {})
            (Path(d) / "Resources").mkdir()
            (Path(d) / "Resources" / "colors.json").write_text("{not json")
            self.assertEqual(hg._load_colors_map(Path(d)), {})


if __name__ == "__main__":
    unittest.main()
