"""A manifest that drifted is not a manifest whose fixtures moved.

THE COST THIS CLOSES

A results file records the sha256 of the whole `manifest.json`, and the
manifest carries `generatedFrom` — the hash of the SSoT. So editing one
`description` string, changing nothing a fixture can be a function of, made
every platform's results stale and cost web ~3 min + android ~8 min + ios ~45
min to get back to a green gate.

MEASURED ON THE REAL CORPUS, 2026-09-15, with the TabView SCOPE sentence that
was in the working tree at the time:

    conformance/fixtures/       0 files changed
    conformance/manifest.json   1 line changed (generatedFrom)
    manifest sha256             0d22d6f56977… -> 4713207a1fff…
    with the lineage:     3 faces judged, 949/898/900 pass, "NOT re-rendered"
    lineage moved aside:  3 faces "stale results — re-run the <p> suite"

⚠️ THE OBVIOUS FIX WAS MEASURED AND REJECTED. Hashing the manifest with
`generatedFrom` removed does not work: the manifest holds no content hash of
any fixture — `layout` and `test` are PATHS — so a change to the generator
that alters what 1099 layouts emit leaves paths, counts and the whole manifest
identical, and that gate would accept yesterday's pictures as fresh. The arm
`test_a_fixture_whose_content_changed_is_not_equivalent` is that rejection,
kept executable.

⚠️ AND BOTH DIGESTS ARE NEEDED. A fixture id renamed in the manifest leaves
every layout file byte-identical, so the fixture tree alone would call the two
manifests equivalent while every result keys on an id that no longer exists.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import manifest_lineage as lineage
from jui_cli.conformance.report import load_platform_results, manifest_identity


def _tree(fixtures: dict[str, str], ids: list[str], provenance: str) -> Path:
    conf = Path(tempfile.mkdtemp()) / "conformance"
    (conf / "fixtures").mkdir(parents=True)
    for name, body in fixtures.items():
        (conf / "fixtures" / name).write_text(body, encoding="utf-8")
    (conf / "manifest.json").write_text(
        json.dumps(
            {
                "generatedFrom": provenance,
                "fixtures": [
                    {"id": i, "layout": f"fixtures/{sorted(fixtures)[0]}"} for i in ids
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return conf


class WhatCountsAsTheSameRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conf = _tree({"a.json": '{"type":"View"}'}, ["A", "B"], "ssot-v1")
        self.manifest = self.conf / "manifest.json"
        self.before = lineage.manifest_digest(self.manifest)
        lineage.record(self.conf, self.manifest)

    def _rewrite_provenance(self, value: str) -> None:
        data = json.loads(self.manifest.read_text())
        data["generatedFrom"] = value
        self.manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        lineage.record(self.conf, self.manifest)

    def test_a_prose_only_edit_leaves_the_render_equivalent(self) -> None:
        """THE TICKET."""
        self._rewrite_provenance("ssot-v2")
        self.assertNotEqual(lineage.manifest_digest(self.manifest), self.before)
        _, equivalent = manifest_identity(self.manifest, self.conf)
        self.assertIn(self.before, equivalent)

    def test_a_fixture_whose_content_changed_is_not_equivalent(self) -> None:
        """The hole the rejected manifest-minus-provenance hash would have had:
        the generator emits something different, and every path stays put."""
        (self.conf / "fixtures" / "a.json").write_text('{"type":"Label"}', encoding="utf-8")
        self._rewrite_provenance("ssot-v2")
        _, equivalent = manifest_identity(self.manifest, self.conf)
        self.assertNotIn(self.before, equivalent)

    def test_a_fixture_file_renamed_is_not_equivalent(self) -> None:
        (self.conf / "fixtures" / "a.json").rename(self.conf / "fixtures" / "b.json")
        self._rewrite_provenance("ssot-v2")
        _, equivalent = manifest_identity(self.manifest, self.conf)
        self.assertNotIn(self.before, equivalent)

    def test_a_fixture_id_renamed_is_not_equivalent(self) -> None:
        """The layouts are byte-identical, so `fixtures` alone would pass this
        — which is why the id set is digested separately."""
        data = json.loads(self.manifest.read_text())
        data["fixtures"][0]["id"] = "A_renamed"
        data["generatedFrom"] = "ssot-v2"
        self.manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.assertEqual(
            lineage.fixtures_digest(self.conf),
            lineage.fixtures_digest(self.conf),
            "sanity: the fixture tree did not move",
        )
        lineage.record(self.conf, self.manifest)
        _, equivalent = manifest_identity(self.manifest, self.conf)
        self.assertNotIn(self.before, equivalent)


class TheFallbackIsTodaysBehaviourNotANewSilenceTests(unittest.TestCase):
    """Every way this can fail must land on "stale", never on "equivalent"."""

    def setUp(self) -> None:
        self.conf = _tree({"a.json": "{}"}, ["A"], "ssot-v1")
        self.manifest = self.conf / "manifest.json"
        self.before = lineage.manifest_digest(self.manifest)
        lineage.record(self.conf, self.manifest)
        data = json.loads(self.manifest.read_text())
        data["generatedFrom"] = "ssot-v2"
        self.manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def test_no_lineage_file_at_all(self) -> None:
        lineage.lineage_path(self.conf).unlink()
        self.assertEqual(manifest_identity(self.manifest, self.conf)[1], frozenset())

    def test_an_unreadable_lineage(self) -> None:
        lineage.lineage_path(self.conf).write_text("{not json", encoding="utf-8")
        self.assertEqual(manifest_identity(self.manifest, self.conf)[1], frozenset())

    def test_an_entry_recorded_under_another_version_is_ignored(self) -> None:
        """A digest is a claim about how it was computed. Reading an old one
        under new rules would assert something nobody measured."""
        path = lineage.lineage_path(self.conf)
        payload = json.loads(path.read_text())
        for entry in payload["manifests"].values():
            entry["version"] = lineage.LINEAGE_VERSION + 1
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertNotIn(self.before, manifest_identity(self.manifest, self.conf)[1])

    def test_the_set_is_filtered_against_the_tree_not_just_read_from_the_file(self) -> None:
        """The arm with the discriminating power: a recorded entry whose
        fixtures have since moved must be DROPPED, not returned because it is
        in the file. Without this, `equivalent_manifest_hashes` could be
        `set(load(...))` and every arm above would still pass."""
        lineage.record(self.conf, self.manifest)
        self.assertIn(self.before, manifest_identity(self.manifest, self.conf)[1])
        # Same lineage file, different fixture tree.
        (self.conf / "fixtures" / "a.json").write_text("{\"moved\": true}", encoding="utf-8")
        recorded = set(lineage.load(self.conf))
        self.assertIn(self.before, recorded, "the entry is still on file …")
        self.assertNotIn(
            self.before,
            manifest_identity(self.manifest, self.conf)[1],
            "… and must not be returned: the tree it described is gone",
        )


class RecordingIsAppendOnlyAndIdempotentTests(unittest.TestCase):
    def test_recording_twice_writes_once_and_keeps_the_old_entry(self) -> None:
        conf = _tree({"a.json": "{}"}, ["A"], "ssot-v1")
        manifest = conf / "manifest.json"
        first = lineage.manifest_digest(manifest)
        _, changed = lineage.record(conf, manifest)
        self.assertTrue(changed)
        _, changed_again = lineage.record(conf, manifest)
        self.assertFalse(changed_again, "an unchanged manifest must not rewrite the file")

        data = json.loads(manifest.read_text())
        data["generatedFrom"] = "ssot-v2"
        manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        lineage.record(conf, manifest)
        entries = lineage.load(conf)
        self.assertIn(first, entries, "recording a new manifest must not drop the old one")
        self.assertEqual(len(entries), 2)


class TheGateSeesTwoStatesNotOneTests(unittest.TestCase):
    def _results(self, results_dir: Path, manifest_hash: str) -> None:
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "ios.results.json").write_text(
            json.dumps(
                {
                    "platform": "ios",
                    "manifestHash": manifest_hash,
                    "results": [{"id": "A", "status": "pass"}],
                }
            ),
            encoding="utf-8",
        )

    def test_drifted_is_not_stale_and_stale_is_not_drifted(self) -> None:
        conf = _tree({"a.json": "{}"}, ["A"], "ssot-v1")
        manifest = conf / "manifest.json"
        old = lineage.manifest_digest(manifest)
        lineage.record(conf, manifest)
        data = json.loads(manifest.read_text())
        data["generatedFrom"] = "ssot-v2"
        manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        lineage.record(conf, manifest)
        current, equivalent = manifest_identity(manifest, conf)
        results = conf / "results"
        self._results(results, old)

        drifted = load_platform_results(results, current, equivalent)[0]
        self.assertFalse(drifted.stale)
        self.assertTrue(drifted.manifest_drifted)

        # Same results, no recorded equivalence: the old verdict, unchanged.
        plain = load_platform_results(results, current)[0]
        self.assertTrue(plain.stale)
        self.assertFalse(plain.manifest_drifted)

        # And a hash nobody ever recorded is stale either way.
        self._results(results, "deadbeef" * 8)
        unknown = load_platform_results(results, current, equivalent)[0]
        self.assertTrue(unknown.stale)
        self.assertFalse(unknown.manifest_drifted)

    def test_matching_results_are_neither(self) -> None:
        conf = _tree({"a.json": "{}"}, ["A"], "ssot-v1")
        manifest = conf / "manifest.json"
        lineage.record(conf, manifest)
        current, equivalent = manifest_identity(manifest, conf)
        results = conf / "results"
        self._results(results, current)
        fresh = load_platform_results(results, current, equivalent)[0]
        self.assertFalse(fresh.stale)
        self.assertFalse(fresh.manifest_drifted)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
