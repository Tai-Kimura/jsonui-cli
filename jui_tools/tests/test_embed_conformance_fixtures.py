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

    def test_emits_six_fixtures_and_three_companions(self):
        self.assertEqual(len(self.entries), 6)
        # 3 companions + 6 × (layout + test)
        self.assertEqual(len(self.files), 15)
        self.assertIn("fixtures/Embed/__screens/embed_root.layout.json", self.by_path)
        self.assertIn("fixtures/Embed/__screens/embed_second.layout.json", self.by_path)
        self.assertIn("fixtures/Embed/__screens/embed_params.layout.json", self.by_path)

    def test_fixture_classes(self):
        classes = {e["id"]: e["class"] for e in self.entries}
        self.assertEqual(classes["Embed/navigationMode__delegate_baseline"], "assertable")
        self.assertEqual(classes["Embed/navigationMode__isolated_root"], "assertable")
        self.assertEqual(classes["Embed/navigationMode__isolated_push"], "interactive")
        self.assertEqual(classes["Embed/navigationMode__isolated_pop_boundary"], "interactive")

    def test_push_fixture_declares_embed_handler_state(self):
        entry = self.by_id["Embed/navigationMode__isolated_push"]
        self.assertEqual(
            entry["state"],
            {
                "vars": [],
                "handlers": [
                    {
                        "name": "confPush",
                        "embed": {"id": "pane", "action": "push", "screen": "embed_second"},
                    }
                ],
            },
        )
        steps = self.by_path[entry["test"]]["cases"][0]["steps"]
        self.assertIn({"action": "tap", "id": "push-button"}, steps)
        self.assertIn(
            {"assert": "text", "id": "embed-second-label", "equals": "embed-second"},
            steps,
        )

    def test_pop_boundary_fixture_pops_twice_and_stays_on_root(self):
        entry = self.by_id["Embed/navigationMode__isolated_pop_boundary"]
        handler_names = [h["name"] for h in entry["state"]["handlers"]]
        self.assertEqual(handler_names, ["confPush", "confPop"])
        steps = self.by_path[entry["test"]]["cases"][0]["steps"]
        pop_taps = [s for s in steps if s == {"action": "tap", "id": "pop-button"}]
        self.assertEqual(len(pop_taps), 2)
        # After the bounded second pop the embed root must still be asserted.
        last_root_assert = max(
            i for i, s in enumerate(steps)
            if s == {"assert": "text", "id": "embed-root-label", "equals": "embed-root"}
        )
        last_pop = max(i for i, s in enumerate(steps) if s == {"action": "tap", "id": "pop-button"})
        self.assertGreater(last_root_assert, last_pop)

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
