"""The canon and the naming convention must come from one config.

They were two resolutions, and a split tree pulled them apart. Specs in one
tree, app and config in another: the API documents resolved through the
repository-root config, while the convention was searched for by walking up
from the spec — a walk that never enters the app's subtree. So a run expanded
`@canonical` marks in `camelCase` and compared `canonicalDivergence` against
the document's raw spelling **in the same run**, and a project that set the
convention could not write a divergence in either spelling: the camelCase name
"is not declared by the operation", the raw name leaves "the rest" as an
unaccounted difference.

Reported by the lane that requested the feature, an hour after adopting it.

The existing tests could not have caught it. They pass `convention` straight
into the checker, so they exercise what the convention does and never how it
is found — and the defect was entirely in the finding. These build the tree
shape and go through the real resolution instead.

Same shape as the mockDir defect three days earlier — a declared config losing
to a path walk. That one was closed by making the declaration outrank the
search; this reintroduced the search as the only path for a new setting, which
is why the fix is one context answering both questions rather than a second
search origin. Adding origins is what left the door open the last two times.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli import shared_core
from jsonui_doc_cli.spec_doc.validator import SpecValidator, SpecValidationResult

canon = shared_core.openapi_canonical()

SWAGGER = {
    "openapi": "3.0.3",
    "paths": {"/api/quotes": {"post": {
        "requestBody": {"required": True, "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/Req"}}}},
        "responses": {"200": {"description": "ok"}}}}},
    "components": {"schemas": {"Req": {
        "type": "object",
        "required": ["venue_slug", "tier_id"],
        "properties": {"venue_slug": {"type": "string"},
                       "tier_id": {"type": "string"}}}}},
}


def _spec(method: dict) -> dict:
    return {"type": "screen",
            "metadata": {"name": "F", "description": "F.", "screen": "f"},
            "dataFlow": {"repositories": [{"name": "R", "methods": [method]}]}}


class SplitTreeTests(unittest.TestCase):
    """`docs/<face>/screens/json/` in one tree, `<face>/jui.config.json` in another.

        root/jui.config.json              api_directory, no convention
        root/docs/api/swagger.json
        root/docs/user/screens/json/*     <- the specs
        root/user/jui.config.json         <- the convention, and where jui runs
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(SWAGGER), encoding="utf-8")
        (self.root / "docs" / "user" / "screens" / "json").mkdir(parents=True)
        self.spec_path = (self.root / "docs" / "user" / "screens" / "json"
                          / "f.spec.json")
        (self.root / "jui.config.json").write_text(
            json.dumps({"api_directory": "docs/api"}), encoding="utf-8")
        # The stub on the specs' own ancestry names the config that owns this
        # face. Without it the nearest reachable config is the repository
        # root's, which holds the canon and declares no convention — and then
        # the answer depends on where the command was typed, which is the
        # defect this file is about.
        (self.root / "docs" / "user" / "jui.config.json").write_text(
            json.dumps({"extends": "../../user/jui.config.json"}),
            encoding="utf-8")
        self.app = self.root / "user"
        self.app.mkdir()
        (self.app / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../docs/api",
             "spec": {"canonical_param_case": "camelCase"}}), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def resolve(self, method: dict, cwd: Path):
        """Validate as the app does — from its own directory."""
        data = _spec(method)
        self.spec_path.write_text(json.dumps(data), encoding="utf-8")
        import os
        previous = os.getcwd()
        os.chdir(cwd)
        try:
            v = SpecValidator()
            v._spec_file_path = self.spec_path
            result = SpecValidationResult()
            v._resolve_canonical_marks(data, result)
        finally:
            os.chdir(previous)
        return (data["dataFlow"]["repositories"][0]["methods"][0],
                [m.message for m in result.errors])

    def test_the_convention_reaches_the_run_from_the_app_directory(self):
        m, errs = self.resolve({"name": "fetchQuotes",
                                "endpoint": "POST /api/quotes",
                                "params": "@canonical"}, cwd=self.app)
        self.assertEqual(errs, [])
        self.assertEqual([p["name"] for p in m["params"]],
                         ["venueSlug", "tierId"])

    def test_a_divergence_written_in_that_convention_is_accepted(self):
        """The reported case. Before the fix this failed in both spellings."""
        _m, errs = self.resolve({
            "name": "fetchQuotes", "endpoint": "POST /api/quotes",
            "params": [{"name": "slug", "type": "String"},
                       {"name": "tierId", "type": "String"}],
            "canonicalDivergence": {"renamed": {"venueSlug": "slug"},
                                    "reason": "front shortens it"},
        }, cwd=self.app)
        self.assertEqual(errs, [])

    def test_expansion_and_checking_agree(self):
        """The defect was not that either half was wrong — it was that the two
        halves of one run disagreed. Pinned as a property, not as two values."""
        expanded, _e = self.resolve({"name": "a", "endpoint": "POST /api/quotes",
                                     "params": "@canonical"}, cwd=self.app)
        names = [p["name"] for p in expanded["params"]]
        _m, errs = self.resolve({
            "name": "a", "endpoint": "POST /api/quotes",
            "params": [{"name": n, "type": "String"} for n in names],
            "canonicalDivergence": {"renamed": {}, "reason": "identical"},
        }, cwd=self.app)
        self.assertEqual(errs, [])

    def test_the_raw_spelling_is_now_the_one_that_is_wrong(self):
        """The convention having arrived, the document's own spelling is the
        divergence — which is the right way round."""
        _m, errs = self.resolve({
            "name": "fetchQuotes", "endpoint": "POST /api/quotes",
            "params": [{"name": "venue_slug", "type": "String"},
                       {"name": "tier_id", "type": "String"}],
            "canonicalDivergence": {"renamed": {}, "reason": "raw"},
        }, cwd=self.app)
        self.assertTrue(errs)

    def test_the_answer_does_not_depend_on_where_the_command_was_typed(self):
        """The property, not a value. The defect was that the same spec got
        `camelCase` from the app directory and nothing from the repository
        root — one tree, two answers, and the two tools run from different
        places."""
        for cwd in (self.app, self.root, self.root / "docs"):
            m, errs = self.resolve({"name": "fetchQuotes",
                                    "endpoint": "POST /api/quotes",
                                    "params": "@canonical"}, cwd=cwd)
            self.assertEqual(errs, [])
            self.assertEqual([p["name"] for p in m["params"]],
                             ["venueSlug", "tierId"], f"cwd={cwd.name}")

    def test_without_the_stub_the_nearest_reachable_config_answers(self):
        """The boundary. No pointer on the ancestry, so the repository root's
        config answers — it holds the canon and declares no convention. That
        is a project that has not adopted the pointer, not a bug."""
        (self.root / "docs" / "user" / "jui.config.json").unlink()
        m, errs = self.resolve({"name": "fetchQuotes",
                                "endpoint": "POST /api/quotes",
                                "params": "@canonical"}, cwd=self.app)
        self.assertEqual(errs, [])
        self.assertEqual([p["name"] for p in m["params"]],
                         ["venue_slug", "tier_id"])


class OneConfigAnswersBothTests(unittest.TestCase):
    """The documents and the convention cannot come from different files.

    The bug was not a missing search path; it was that two answers were sourced
    independently. A second search origin would have fixed this layout and left
    the next one open — which is what happened the last two times.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, data):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_the_config_that_supplies_the_documents_supplies_the_convention(self):
        self.write("outer/jui.config.json",
                   {"api_directory": "api",
                    "spec": {"canonical_param_case": "snake_case"}})
        self.write("outer/api/s.json", SWAGGER)
        self.write("outer/inner/jui.config.json",
                   {"api_directory": "api",
                    "spec": {"canonical_param_case": "camelCase"}})
        self.write("outer/inner/api/s.json", SWAGGER)
        spec = self.write("outer/inner/specs/f.spec.json", _spec({"name": "a"}))

        ctx = canon.build_spec_canon_context(spec)
        self.assertEqual(ctx.convention, "camelCase")
        self.assertIn("inner", str(ctx.config_path))

    def test_a_config_with_no_documents_does_not_win(self):
        """Nearest is not the rule — holding the canon is."""
        self.write("outer/jui.config.json",
                   {"api_directory": "api",
                    "spec": {"canonical_param_case": "snake_case"}})
        self.write("outer/api/s.json", SWAGGER)
        self.write("outer/inner/jui.config.json", {"api_directory": "nothing"})
        spec = self.write("outer/inner/specs/f.spec.json", _spec({"name": "a"}))

        ctx = canon.build_spec_canon_context(spec)
        self.assertEqual(ctx.convention, "snake_case")
        self.assertTrue(ctx.index)

    def test_no_config_at_all_is_silent(self):
        spec = self.write("bare/specs/f.spec.json", _spec({"name": "a"}))
        ctx = canon.build_spec_canon_context(spec)
        self.assertEqual(ctx.index, {})
        self.assertIsNone(ctx.convention)


if __name__ == "__main__":
    unittest.main()
