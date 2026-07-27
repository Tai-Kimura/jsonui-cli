"""Guard for the screen-identity SSoT asset and its single resolver.

``shared/core/screen_identity.json`` is the canonical source for what a
screen is, how it is identified and how its presence is asserted; the
resolver in ``jui_cli.core.screen_identity`` is the ONE implementation of
those rules. This guard keeps the asset parseable and internally
consistent, and pins the resolver's classification behaviour so a
divergent second implementation fails in CI.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.screen_identity import (
    MARKER_PREFIX,
    VALID_ROLES,
    build_screen_index,
    load_canon,
    marker_name,
    screen_id_for_path,
)

SHARED_CORE = Path(__file__).resolve().parents[2] / "shared" / "core"
ASSET_PATH = SHARED_CORE / "screen_identity.json"


def _write(root: Path, rel: str, payload: dict) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


class ScreenIdentityAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ASSET_PATH, "r", encoding="utf-8") as f:
            cls.canon = json.load(f)

    def test_version_and_sections(self):
        self.assertIsInstance(self.canon["version"], int)
        for section in (
            "screenId",
            "screenClassification",
            "appOwnedScreens",
            "marker",
            "assertion",
            "predicates",
            "implicitVerification",
            "diagram",
            "validatorRules",
        ):
            self.assertIn(section, self.canon)

    def test_screen_id_collection_is_recursive(self):
        # A flat glob under-collects nested sheets/cells — the canon must
        # not quietly regress to it.
        self.assertEqual(self.canon["screenId"]["collection"], "recursive")
        self.assertEqual(self.canon["screenId"]["uniqueness"], "projectWide")

    def test_classification_roles_match_resolver(self):
        self.assertEqual(tuple(self.canon["screenClassification"]["roles"]), VALID_ROLES)

    def test_classification_resolution_order_is_explicit_first(self):
        steps = self.canon["screenClassification"]["resolutionOrder"]
        self.assertEqual([s["step"] for s in steps], [1, 2, 3, 4])
        self.assertEqual(steps[0]["rule"], "explicitRole")
        self.assertEqual(steps[-1]["rule"], "defaultScreen")

    def test_marker_prefix_matches_resolver(self):
        self.assertEqual(self.canon["marker"]["prefix"], MARKER_PREFIX)
        self.assertEqual(
            self.canon["marker"]["namePattern"].replace("<screenId>", "login"),
            marker_name("login"),
        )

    def test_marker_declares_every_platform(self):
        platforms = self.canon["marker"]["platforms"]
        for key in ("ios-swiftui", "ios-uikit", "android-compose", "web-react"):
            self.assertIn(key, platforms)
            self.assertTrue(platforms[key]["mechanism"])

    def test_assertion_target_key_is_not_the_step_screen_key(self):
        # Overloading 'screen' as both "step runs on" and "assertion target"
        # is the rejected design — keep them distinct.
        self.assertEqual(self.canon["assertion"]["vocabulary"]["assert"], "screen")
        self.assertNotEqual(self.canon["assertion"]["vocabulary"]["targetKey"], "screen")

    def test_every_platform_has_a_predicate(self):
        predicates = self.canon["predicates"]
        for platform in ("ios", "android", "web"):
            self.assertIn(platform, predicates)
            self.assertTrue(predicates[platform]["predicate"])
            self.assertIn(predicates[platform]["status"], ("provisional", "measured"))

    def test_implicit_verification_timeout_is_distinct_from_default(self):
        timeout = self.canon["implicitVerification"]["timeout"]
        self.assertEqual(timeout["key"], "screenTransitionTimeout")
        self.assertGreater(timeout["defaultMs"], 5000)

    def test_failure_classes_cover_infrastructure_and_real_failure(self):
        ids = {f["id"] for f in self.canon["implicitVerification"]["failureClasses"]}
        self.assertIn("marker-absent", ids)
        self.assertIn("previous-screen-only", ids)

    def test_validator_rule_ids_are_unique_and_typed(self):
        rules = self.canon["validatorRules"]
        ids = [r["id"] for r in rules]
        self.assertEqual(len(ids), len(set(ids)))
        for rule in rules:
            self.assertIn(rule["severity"], ("error", "warning"))
            self.assertTrue(rule["message"])

    def test_app_owned_screens_declare_where_and_how(self):
        section = self.canon["appOwnedScreens"]
        self.assertEqual(section["declaration"]["location"], "jui.config.json")
        self.assertEqual(section["declaration"]["key"], "test.appOwnedScreens")
        # No library API until a real mobile case exists.
        self.assertIn("None", section["libraryApi"])

    def test_diagram_pipeline_order_is_declared(self):
        self.assertEqual(
            self.canon["diagram"]["pipeline"],
            ["resolve", "canonicalize", "collapseConsecutiveDuplicates", "buildEdges"],
        )


class ScreenIdResolutionTests(unittest.TestCase):
    def test_basename_without_extension(self):
        self.assertEqual(screen_id_for_path("Layouts/mypage/change_email_sheet.json"), "change_email_sheet")

    def test_variant_normalizes_to_base(self):
        self.assertEqual(screen_id_for_path("Layouts/home@regular.json"), "home")

    def test_reference_without_extension(self):
        self.assertEqual(screen_id_for_path("chat/message_cell"), "message_cell")


class ScreenIndexTests(unittest.TestCase):
    def _index(self, layouts: dict[str, dict]):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        for rel, payload in layouts.items():
            _write(root, rel, payload)
        self.addCleanup(self.tmp.cleanup)
        return build_screen_index(root)

    def test_nested_layouts_are_collected(self):
        index = self._index(
            {
                "login.json": {"type": "View"},
                "mypage/change_email_sheet.json": {"type": "View"},
            }
        )
        self.assertEqual(index.screen_ids, ["change_email_sheet", "login"])

    def test_cell_reference_demotes_the_referenced_layout(self):
        index = self._index(
            {
                "chat.json": {"type": "Collection", "cellClasses": ["chat/message_cell"]},
                "chat/message_cell.json": {"type": "View"},
            }
        )
        self.assertTrue(index.is_screen("chat"))
        self.assertFalse(index.is_screen("message_cell"))
        self.assertEqual(index.get("message_cell").role, "cell")
        self.assertEqual(index.get("message_cell").reason, "referenced")

    def test_include_reference_demotes_the_referenced_layout(self):
        index = self._index(
            {
                "item_detail.json": {"type": "View", "child": [{"include": "item_detail/hero_section"}]},
                "item_detail/hero_section.json": {"type": "View"},
            }
        )
        self.assertFalse(index.is_screen("hero_section"))

    def test_explicit_role_beats_derivation(self):
        # A layout nobody references would default to 'screen'; the explicit
        # role is canonical and must win.
        index = self._index(
            {
                "conversation_history/conversation_cell.json": {"type": "View", "role": "cell"},
                "orphan_widget.json": {"type": "View"},
            }
        )
        self.assertFalse(index.is_screen("conversation_cell"))
        self.assertEqual(index.get("conversation_cell").reason, "explicit")
        # ...and the un-referenced, un-declared layout still derives to screen
        self.assertTrue(index.is_screen("orphan_widget"))

    def test_explicit_screen_role_survives_a_stray_reference(self):
        index = self._index(
            {
                "host.json": {"type": "View", "child": [{"include": "real_screen"}]},
                "real_screen.json": {"type": "View", "role": "screen"},
            }
        )
        self.assertTrue(index.is_screen("real_screen"))

    def test_partial_flag_demotes(self):
        index = self._index({"detail_notes.json": {"type": "View", "partial": True}})
        self.assertFalse(index.is_screen("detail_notes"))
        self.assertEqual(index.get("detail_notes").reason, "partial-flag")

    def test_variant_file_does_not_create_a_second_entry(self):
        index = self._index(
            {
                "home.json": {"type": "View"},
                "home@regular.json": {"type": "View"},
            }
        )
        self.assertEqual(index.screen_ids, ["home"])

    def test_basename_collision_is_reported(self):
        index = self._index(
            {
                "a/settings.json": {"type": "View"},
                "b/settings.json": {"type": "View"},
            }
        )
        self.assertIn("settings", index.collisions)
        self.assertEqual(len(index.collisions["settings"]), 2)

    def test_classification_report_lists_reason_per_layout(self):
        index = self._index(
            {
                "chat.json": {"type": "Collection", "cell": "chat/message_cell"},
                "chat/message_cell.json": {"type": "View"},
            }
        )
        report = {row["screen"]: row for row in index.classification_report()}
        self.assertEqual(report["chat"]["role"], "screen")
        self.assertEqual(report["message_cell"]["role"], "cell")

    def test_unparseable_layout_does_not_abort_the_index(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        _write(root, "good.json", {"type": "View"})
        (root / "broken.json").write_text("{not json", encoding="utf-8")
        index = build_screen_index(root)
        self.assertTrue(index.is_screen("good"))
        self.assertTrue(index.is_known("broken"))

    def test_missing_directory_yields_empty_index(self):
        self.assertEqual(build_screen_index(Path("/nonexistent/layouts")).screen_ids, [])


class AppOwnedScreenTests(unittest.TestCase):
    """Screens the app implements without a JsonUI layout (hand-written
    pages). They are real navigation destinations, so an undeclared id must
    stay unknown while a declared one must be a screen."""

    def _index(self, layouts: dict[str, dict], declared):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel, payload in layouts.items():
            _write(root, rel, payload)
        return build_screen_index(root, declared)

    def test_declared_id_becomes_a_screen(self):
        index = self._index({"product_page.json": {"type": "View"}}, ["tokushoho"])
        self.assertTrue(index.is_screen("tokushoho"))
        self.assertEqual(index.get("tokushoho").reason, "app-owned")

    def test_undeclared_id_stays_unknown(self):
        index = self._index({"product_page.json": {"type": "View"}}, [])
        self.assertFalse(index.is_known("tokushoho"))

    def test_declaration_does_not_override_a_real_layout(self):
        index = self._index(
            {"chat.json": {"type": "Collection", "cell": "chat/row"}, "chat/row.json": {"type": "View"}},
            ["row"],
        )
        self.assertEqual(index.get("row").reason, "referenced")
        self.assertFalse(index.is_screen("row"))

    def test_declarations_apply_without_a_layout_directory(self):
        index = build_screen_index(Path("/nonexistent/layouts"), ["company"])
        self.assertTrue(index.is_screen("company"))

    def test_blank_declarations_are_ignored(self):
        index = self._index({"a.json": {"type": "View"}}, ["", None, 3])
        self.assertEqual(index.screen_ids, ["a"])


class CanonLoaderTests(unittest.TestCase):
    def test_load_canon_finds_the_bundled_asset(self):
        self.assertEqual(load_canon()["version"], 1)


if __name__ == "__main__":
    unittest.main()
