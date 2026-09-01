"""The editor reads the COPY, so the copy going stale has to be sayable.

`place_editor_schema` is called only from `mock generate`. A project that
validates but never generates keeps whatever copy it was first given, and
until this landed nothing anywhere read those copies: `Warnings:`, `No drift`
and `0 stale` were all silent about it. Measured across every consumer on one
machine the day this was written: 162 copies, 0 fresh.

The two directions are counted apart because they are not equally bad, and
the test fixes that asymmetry rather than just the count — a copy that allows
a dropped key costs one warning, and a copy MISSING a key this CLI accepts
makes the editor mark a correct declaration invalid.
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_test_cli.mock.generate import (
    EDITOR_SCHEMA_FILENAME, editor_schema_drift, editor_schema_text)


def _scenario_props(text):
    return json.loads(text)["properties"]["scenarios"]["additionalProperties"]


class EditorSchemaDrift(unittest.TestCase):
    def _mock_dir(self, tmp, copy_text):
        d = Path(tmp) / "mocks" / "a"
        d.mkdir(parents=True)
        (d / "x.mock.json").write_text('{"scenarios":{}}', encoding="utf-8")
        (d / EDITOR_SCHEMA_FILENAME).write_text(copy_text, encoding="utf-8")
        return Path(tmp) / "mocks"

    def test_a_copy_equal_to_the_shipped_one_is_not_reported(self):
        with TemporaryDirectory() as tmp:
            mock_dir = self._mock_dir(tmp, editor_schema_text())
            self.assertEqual(editor_schema_drift(mock_dir), (1, 0, 0))

    def test_a_copy_that_only_allows_more_is_stale_but_not_the_bad_way(self):
        """`+headers`: the CLI answers with one warning and exit 0."""
        with TemporaryDirectory() as tmp:
            doc = json.loads(editor_schema_text())
            _scenario_props(editor_schema_text())  # shape assertion
            doc["properties"]["scenarios"]["additionalProperties"][
                "properties"]["headers"] = {"type": "object"}
            mock_dir = self._mock_dir(tmp, json.dumps(doc, indent=2))
            total, stale, missing = editor_schema_drift(mock_dir)
            self.assertEqual((total, stale), (1, 1))
            self.assertEqual(missing, 0, "an extra key does not redden anything")

    def test_a_copy_missing_a_shipped_key_is_counted_on_the_bad_side(self):
        """The copies say additionalProperties:false, so a missing key makes
        the editor reject a declaration this CLI accepts."""
        with TemporaryDirectory() as tmp:
            doc = json.loads(editor_schema_text())
            props = doc["properties"]["scenarios"]["additionalProperties"][
                "properties"]
            dropped = sorted(props)[0]
            props.pop(dropped)
            mock_dir = self._mock_dir(tmp, json.dumps(doc, indent=2))
            self.assertEqual(editor_schema_drift(mock_dir), (1, 1, 1))

    def test_an_unreadable_copy_counts_as_misleading_rather_than_fresh(self):
        """Never pass on absence: a copy that cannot be parsed is not
        honouring the shipped vocabulary, so it goes on the side that
        misleads rather than being skipped."""
        with TemporaryDirectory() as tmp:
            mock_dir = self._mock_dir(tmp, "{ not json")
            self.assertEqual(editor_schema_drift(mock_dir), (1, 1, 1))

    def test_an_orphan_copy_has_no_reader_and_is_not_counted(self):
        """Three faces hit this on day one: a cleanup that deleted the mocks
        left the hidden schema copy behind, in a directory `mock generate`
        never visits — so the note could never be cleared by the remedy it
        named. A copy no mock points at cannot mislead an editor, and
        counting it answers a different question than this function asks."""
        with TemporaryDirectory() as tmp:
            doc = json.loads(editor_schema_text())
            doc["properties"]["scenarios"]["additionalProperties"][
                "properties"].pop(sorted(
                    doc["properties"]["scenarios"]["additionalProperties"][
                        "properties"])[0])
            orphan_dir = Path(tmp) / "mocks" / "gone"
            orphan_dir.mkdir(parents=True)
            (orphan_dir / EDITOR_SCHEMA_FILENAME).write_text(
                json.dumps(doc, indent=2), encoding="utf-8")
            self.assertEqual(editor_schema_drift(Path(tmp) / "mocks"),
                             (0, 0, 0))

    def test_a_stale_copy_beside_a_mock_is_still_counted(self):
        """The negative test the adjudication demanded: narrowing the
        denominator to readers must not lose the copies this note exists
        for. A directory with one mock and one stale copy stays in."""
        with TemporaryDirectory() as tmp:
            doc = json.loads(editor_schema_text())
            props = doc["properties"]["scenarios"]["additionalProperties"][
                "properties"]
            props.pop(sorted(props)[0])
            mock_dir = self._mock_dir(tmp, json.dumps(doc, indent=2))
            self.assertEqual(editor_schema_drift(mock_dir), (1, 1, 1))

    def test_no_mock_dir_is_silent_rather_than_an_error(self):
        """This runs inside a summary line. A project with no mocks must not
        fail the gate that was reporting on something else."""
        self.assertEqual(editor_schema_drift(None), (0, 0, 0))
        with TemporaryDirectory() as tmp:
            self.assertEqual(editor_schema_drift(Path(tmp) / "nope"),
                             (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
