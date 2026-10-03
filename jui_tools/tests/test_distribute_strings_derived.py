"""The face-side strings.json is the shared copy's bytes; this build's
extraction adds what the layouts derive.

Until 1.9.10 distribution merged and kept every section only the face copy
had, so a section removed from the shared strings.json survived in the
gitignored face copy and in the tracked outputs built from it (ticket
face-strings-json-keeps-a-section-the-shared-copy-removed). Measured on a
consumer client: strings.xml, Localizable.strings and the web StringManager
all kept a removed section on the machine that had built it before.
"""
import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jui_cli.commands.build_cmd import _distribute_strings_into


class DistributeStringsDerived(unittest.TestCase):
    def _write(self, path: Path, data) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def test_a_section_removed_from_the_shared_copy_leaves_the_face(self):
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json", {"home": {"title": "Home"}})
            dest = self._write(Path(tmp) / "face" / "strings.json",
                               {"home": {"title": "Home"}, "zz_probe": {"probe_key": "Removed"}})
            _distribute_strings_into(src, dest)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8")), {"home": {"title": "Home"}})

    def test_a_face_only_section_is_not_carried(self):
        """The extractor puts back what the layouts derive on the same build;
        nothing the face copy held is kept for it."""
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json", {"home": {"title": "Home"}})
            dest = self._write(Path(tmp) / "face" / "strings.json",
                               {"home": {"title": "OLD"}, "_poc_chip": {"add": "+ Add chip"}})
            self.assertEqual(_distribute_strings_into(src, dest), 1)
            self.assertNotIn("_poc_chip", json.loads(dest.read_text(encoding="utf-8")))

    def test_the_face_copy_is_the_shared_bytes(self):
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "docs" / "strings.json"
            src.parent.mkdir(parents=True)
            src.write_text('{\n    "home": {"title": "Home"}\n}\n', encoding="utf-8")
            dest = self._write(Path(tmp) / "face" / "strings.json", {"other": {}})
            _distribute_strings_into(src, dest)
            self.assertEqual(dest.read_bytes(), src.read_bytes())

    def test_a_missing_or_unreadable_destination_is_written(self):
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json", {"home": {"title": "Home"}})
            missing = Path(tmp) / "face1" / "strings.json"
            _distribute_strings_into(src, missing)
            self.assertEqual(missing.read_bytes(), src.read_bytes())
            broken = Path(tmp) / "face2" / "strings.json"
            broken.parent.mkdir(parents=True)
            broken.write_text("{not json", encoding="utf-8")
            _distribute_strings_into(src, broken)
            self.assertEqual(broken.read_bytes(), src.read_bytes())

    def test_an_identical_destination_is_not_rewritten(self):
        with TemporaryDirectory() as tmp:
            src = self._write(Path(tmp) / "docs" / "strings.json", {"home": {"title": "Home"}})
            dest = Path(tmp) / "face" / "strings.json"
            _distribute_strings_into(src, dest)
            past = time.time() - 3600
            os.utime(dest, (past, past))
            _distribute_strings_into(src, dest)
            self.assertEqual(int(dest.stat().st_mtime), int(past))


if __name__ == "__main__":
    unittest.main()
