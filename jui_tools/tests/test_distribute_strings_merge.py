"""The face-side strings.json has two writers; distribution must not erase
the other one's work.

The ruling: the face copy is a distribution target PLUS an extractor append
area. SSoT sections are the SSoT's — overwritten. Face-only sections are the
extractors' — kept, and named on every build so their drift stays visible.
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jui_cli.commands.build_cmd import _merge_strings_into


class DistributeStringsByMerge(unittest.TestCase):
    def _write(self, path: Path, data) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_a_face_local_section_survives_distribution_and_is_named(self):
        """The defect this exists for: copy2 reverted every section an
        extractor had added, and whichever tool ran last owned the file."""
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json",
                              {"home": {"title": "Home"}})
            dest = self._write(Path(tmp) / "face" / "strings.json",
                               {"home": {"title": "OLD"},
                                "_poc_chip": {"add": "+ Add chip"}})
            distributed, kept = _merge_strings_into(src, dest)
            merged = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(merged["home"], {"title": "Home"},
                             "an SSoT section is the SSoT's — overwritten")
            self.assertEqual(merged["_poc_chip"], {"add": "+ Add chip"},
                             "a face-local section is the extractor's — kept")
            self.assertEqual(kept, ["_poc_chip"],
                             "kept sections are NAMED, not silently carried")
            self.assertEqual(distributed, 1)

    def test_an_ssot_section_is_overwritten_not_merged_key_by_key(self):
        """Canonical means canonical: a key the SSoT dropped from a section
        it still declares must not survive inside that section."""
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json",
                              {"home": {"title": "Home"}})
            dest = self._write(Path(tmp) / "face" / "strings.json",
                               {"home": {"title": "Old", "stale_key": "x"}})
            _merge_strings_into(src, dest)
            merged = json.loads(dest.read_text(encoding="utf-8"))
            self.assertNotIn("stale_key", merged["home"])

    def test_a_missing_destination_is_a_plain_copy(self):
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json",
                              {"home": {"title": "Home"}})
            dest = Path(tmp) / "face" / "strings.json"
            distributed, kept = _merge_strings_into(src, dest)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8")),
                             {"home": {"title": "Home"}})
            self.assertEqual((distributed, kept), (1, []))

    def test_an_unreadable_destination_is_replaced_not_preserved(self):
        """Merge needs a readable base; preserving bytes we cannot parse
        would preserve a corruption."""
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json",
                              {"home": {"title": "Home"}})
            dest = Path(tmp) / "face" / "strings.json"
            dest.parent.mkdir(parents=True)
            dest.write_text("{ not json", encoding="utf-8")
            _, kept = _merge_strings_into(src, dest)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8")),
                             {"home": {"title": "Home"}})
            self.assertEqual(kept, [])

    def test_an_identical_destination_is_not_rewritten(self):
        """mtime is a signal other lanes read (a face attributed an
        experiment's arms by it); an idempotent distribute must not touch it."""
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json",
                              {"home": {"title": "Home"}})
            dest = Path(tmp) / "face" / "strings.json"
            _merge_strings_into(src, dest)
            before = dest.stat().st_mtime_ns
            _merge_strings_into(src, dest)
            self.assertEqual(dest.stat().st_mtime_ns, before)


    def test_no_face_local_sections_means_verbatim_source_bytes(self):
        """Byte-hashing gates on faces with nothing appended must not move
        for a formatting change that distributes nothing."""
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "docs" / "strings.json"
            src.parent.mkdir(parents=True)
            raw = '{"home":   {"title": "Home"}}'  # deliberately odd spacing
            src.write_text(raw, encoding="utf-8")
            dest = Path(tmp) / "face" / "strings.json"
            _merge_strings_into(src, dest)
            self.assertEqual(dest.read_text(encoding="utf-8"), raw,
                             "verbatim bytes when nothing was kept")


if __name__ == "__main__":
    unittest.main()
