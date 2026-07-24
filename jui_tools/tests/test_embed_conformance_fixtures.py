"""Contract tests for the bespoke Embed conformance fixtures
(conformance.embed_fixtures — 04 embed-isolated track)."""
from __future__ import annotations

import unittest

from jui_cli.conformance.embed_fixtures import build_embed_fixtures


class EmbedFixturesTest(unittest.TestCase):
    def setUp(self):
        self.files, self.entries = build_embed_fixtures("test-source")
        self.by_path = dict(self.files)
        self.by_id = {e["id"]: e for e in self.entries}

    def test_emits_four_fixtures_and_two_companions(self):
        self.assertEqual(len(self.entries), 4)
        # 2 companions + 4 × (layout + test)
        self.assertEqual(len(self.files), 10)
        self.assertIn("fixtures/Embed/__screens/embed_root.layout.json", self.by_path)
        self.assertIn("fixtures/Embed/__screens/embed_params.layout.json", self.by_path)

    def test_every_entry_declares_its_companions(self):
        for entry in self.entries:
            self.assertTrue(entry["companions"], entry["id"])
            for companion in entry["companions"]:
                self.assertIn(companion, self.by_path)

    def test_isolated_root_fixture_uses_isolated_mode(self):
        entry = self.by_id["Embed/navigationMode__isolated_root"]
        layout = self.by_path[entry["layout"]]
        embed = layout["child"][1]
        self.assertEqual(embed["type"], "Embed")
        self.assertEqual(embed["navigationMode"], "isolated")
        self.assertEqual(embed["screen"], "embed_root")

    def test_nested_leaf_binding_resolves_against_host_data(self):
        entry = self.by_id["Embed/params__nested_leaf_binding"]
        layout = self.by_path[entry["layout"]]
        self.assertEqual(layout["data"][0]["name"], "hostValue")
        embed = layout["child"][1]
        # Mixed literal + binding tree; meta present because the embedded
        # layout dereferences profile.meta.age unconditionally.
        self.assertEqual(
            embed["params"],
            {"profile": {"name": "@{hostValue}", "meta": {"age": "36"}}},
        )
        test = self.by_path[entry["test"]]
        steps = test["cases"][0]["steps"]
        self.assertIn(
            {"assert": "text", "id": "embed-params-name", "equals": "from-host"},
            steps,
        )

    def test_all_fixtures_assert_host_marker_containment(self):
        # Every fixture proves the host screen stays intact around the embed.
        for entry in self.entries:
            steps = self.by_path[entry["test"]]["cases"][0]["steps"]
            self.assertIn(
                {"assert": "text", "id": "host-marker", "equals": "host"},
                steps,
                entry["id"],
            )

    def test_deterministic_output(self):
        again_files, again_entries = build_embed_fixtures("test-source")
        self.assertEqual(self.files, again_files)
        self.assertEqual(self.entries, again_entries)


if __name__ == "__main__":
    unittest.main()
