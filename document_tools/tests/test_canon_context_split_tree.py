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

    def test_a_declared_but_empty_api_directory_answers_as_broken(self):
        """This test used to assert the opposite — "nearest is not the rule,
        holding the canon is" — and that ruling is what three faces measured
        as misattribution: a declared path that resolved to nothing was
        outvoted by a shallower config's documents, so the canon arrived from
        one file and the convention from another's absence, and every correct
        divergence declaration re-emerged as an error in the document's raw
        spelling. The ruling now: DECLARING api_directory is the rule, and
        holding the canon only breaks ties among configs that declare
        nothing (the undeclared case keeps falling through — asserted in
        DeclaredButEmptyApiDirectoryAnswersTests)."""
        self.write("outer/jui.config.json",
                   {"api_directory": "api",
                    "spec": {"canonical_param_case": "snake_case"}})
        self.write("outer/api/s.json", SWAGGER)
        self.write("outer/inner/jui.config.json", {"api_directory": "nothing"})
        spec = self.write("outer/inner/specs/f.spec.json", _spec({"name": "a"}))

        ctx = canon.build_spec_canon_context(spec)
        self.assertEqual(ctx.index, {})
        self.assertIn("inner", str(ctx.config_path))

    def test_no_config_at_all_is_silent(self):
        spec = self.write("bare/specs/f.spec.json", _spec({"name": "a"}))
        ctx = canon.build_spec_canon_context(spec)
        self.assertEqual(ctx.index, {})
        self.assertIsNone(ctx.convention)


if __name__ == "__main__":
    unittest.main()


class UnresolvableExtendsTests(unittest.TestCase):
    """A pointer that names nothing must not read like no pointer.

    Measured before the fix: a one-character typo in `extends` produced output
    byte-identical to deleting the key. The settings simply did not arrive, and
    the only visible effect was that parameter names came out spelled the API
    document's way — noticeable only by A/B. `validate spec` said
    `Errors: 0, Warnings: 0` and `generate` exited 0.

    Reported by the lane that adopted `extends` the same day it shipped, which
    is the third time this shape has been found in a mechanism added to close
    the previous one: `mockDir` fixed the declaration losing to a search, and
    left the unresolvable declaration silent (v1.6.50); this added a pointer
    to close the config-level version, and left the unresolvable pointer
    silent in turn.

    Writing `extends` is a statement of intent. Not writing it is not — so an
    absent key stays silent, and only a broken one is reported.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "api" / "s.json").write_text(
            json.dumps(SWAGGER), encoding="utf-8")
        (self.root / "jui.config.json").write_text(
            json.dumps({"api_directory": "docs/api"}), encoding="utf-8")
        (self.root / "app").mkdir()
        (self.root / "app" / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../docs/api",
             "spec": {"canonical_param_case": "camelCase"}}), encoding="utf-8")
        self.stub_dir = self.root / "docs" / "face"
        self.stub_dir.mkdir(parents=True)
        self.spec = self.stub_dir / "s.spec.json"
        self.spec.write_text(json.dumps(_spec({"name": "a"})), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def stub(self, body):
        if body is None:
            (self.stub_dir / "jui.config.json").unlink(missing_ok=True)
        else:
            (self.stub_dir / "jui.config.json").write_text(
                json.dumps(body), encoding="utf-8")
        return canon.build_spec_canon_context(self.spec)

    def test_a_pointer_that_names_nothing_is_reported(self):
        ctx = self.stub({"extends": "../../app/zzz-typo.json"})
        self.assertEqual(len(ctx.unresolved_extends), 1)
        self.assertIn("names no file", ctx.unresolved_extends[0])
        self.assertIn("canonical_param_case", ctx.unresolved_extends[0])

    def test_a_correct_pointer_says_nothing(self):
        ctx = self.stub({"extends": "../../app/jui.config.json"})
        self.assertEqual(ctx.unresolved_extends, ())
        self.assertEqual(ctx.convention, "camelCase")

    def test_no_pointer_at_all_says_nothing(self):
        """Not writing one is not a statement of intent."""
        ctx = self.stub(None)
        self.assertEqual(ctx.unresolved_extends, ())

    def test_an_empty_or_wrongly_typed_pointer_is_reported(self):
        for bad in ("", "   ", 5, []):
            ctx = self.stub({"extends": bad})
            self.assertEqual(len(ctx.unresolved_extends), 1, f"extends={bad!r}")

    def test_a_pointer_to_unreadable_json_is_reported(self):
        (self.root / "app" / "broken.json").write_text("{ not json",
                                                       encoding="utf-8")
        ctx = self.stub({"extends": "../../app/broken.json"})
        self.assertEqual(len(ctx.unresolved_extends), 1)
        self.assertIn("not readable JSON", ctx.unresolved_extends[0])

    def test_the_typo_and_the_absent_key_no_longer_look_the_same(self):
        """The property, stated directly. This is what was false."""
        typo = self.stub({"extends": "../../app/zzz-typo.json"})
        absent = self.stub(None)
        self.assertEqual(typo.convention, absent.convention)   # still the same
        self.assertNotEqual(typo.unresolved_extends,
                            absent.unresolved_extends)          # but not silent


class UnknownConfigKeyTests(unittest.TestCase):
    """A misspelled key is not a broken declaration — it is no declaration.

    `extends` failed twice in one day. v1.7.9 reported a value that named no
    file; this is the key itself written `extend`, which the value check
    cannot see because `config.get("extends")` simply returns None. The output
    was byte-identical to deleting the key, and only A/B found it.

    The general defect is that `jui.config.json` has never had an opinion about
    keys it does not recognise, so `mockdir`, `canonicalParamCase` and every
    other near-miss are equally silent. The known set is a declaration
    collected from what each tool reads; the corpus check below is what keeps
    it honest — a key added to a tool and not here shows up as a false
    positive on a real config.
    """

    def keys(self):
        return shared_core.load("config_keys")

    def test_a_near_miss_is_reported_with_the_key_it_resembles(self):
        k = self.keys()
        unknown = k.unknown_keys({"extend": "../x.json"})
        self.assertEqual(unknown, ["extend"])
        self.assertIn("Did you mean 'extends'?", k.message("cfg", unknown))

    def test_a_key_no_tool_reads_is_reported_without_a_guess(self):
        k = self.keys()
        unknown = k.unknown_keys({"zzz_project_thing": 1})
        self.assertEqual(unknown, ["zzz_project_thing"])
        self.assertNotIn("Did you mean", k.message("cfg", unknown))

    def test_underscore_prefixed_keys_are_notes(self):
        """Two consumer configs already carry `_note` / `_comment`."""
        self.assertEqual(
            self.keys().unknown_keys({"_note": "why", "_comment": "x"}), [])

    def test_every_key_the_tools_read_is_accepted(self):
        """The false-positive boundary, stated as the whole known set."""
        k = self.keys()
        self.assertEqual(k.unknown_keys({key: None for key in k.KNOWN_TOP_LEVEL}),
                         [])

    def test_a_correct_config_says_nothing(self):
        self.assertEqual(self.keys().unknown_keys(
            {"project_name": "x", "platforms": ["web"], "spec": {},
             "extends": "../a.json", "_note": "n"}), [])

    def test_the_suggestion_stays_quiet_when_it_would_be_a_guess(self):
        """A hint that is usually wrong trains readers to skip the message."""
        k = self.keys()
        self.assertIsNone(k._nearest(["completely_unrelated"]))


class DiagnosticsCoverEveryConfigExaminedTests(unittest.TestCase):
    """Which config answers, and which configs were looked at, are two questions.

    The walk used to return at the first config that resolved an index, so a
    stub further along the ancestry was never opened — its `extends` was never
    followed and its unknown keys never seen. Short-circuiting the first
    question silently narrowed the second.

    Not reachable from either CLI when it was found: neither adapter passes an
    explicit `config_path`, so the ancestry was always walked from the spec
    outwards and the stub came first. A lane measured the two orderings and
    reported the latent one. That is the shape this codebase keeps finding —
    a second path that is correct today because nothing takes it.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "api" / "s.json").write_text(
            json.dumps(SWAGGER), encoding="utf-8")
        # The root config resolves the canon on its own.
        (self.root / "jui.config.json").write_text(
            json.dumps({"api_directory": "docs/api"}), encoding="utf-8")
        self.stub_dir = self.root / "docs" / "face"
        self.stub_dir.mkdir(parents=True)
        self.spec = self.stub_dir / "s.spec.json"
        self.spec.write_text(json.dumps(_spec({"name": "a"})), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_broken_pointer_is_seen_even_when_another_config_answered(self):
        (self.stub_dir / "jui.config.json").write_text(
            json.dumps({"extends": "../../nowhere.json"}), encoding="utf-8")
        ctx = canon.build_spec_canon_context(
            self.spec, config_path=self.root / "jui.config.json")
        self.assertTrue(ctx.index, "the explicit config still answers")
        self.assertEqual(len(ctx.unresolved_extends), 1)

    def test_an_unknown_key_is_seen_the_same_way(self):
        (self.stub_dir / "jui.config.json").write_text(
            json.dumps({"extend": "../../nowhere.json"}), encoding="utf-8")
        ctx = canon.build_spec_canon_context(
            self.spec, config_path=self.root / "jui.config.json")
        self.assertTrue(ctx.index)
        self.assertEqual(len(ctx.unknown_config_keys), 1)

    def test_the_first_config_to_resolve_still_supplies_the_answer(self):
        """Widening the diagnostics must not change who answers."""
        (self.stub_dir / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../api", "spec": {"canonical_param_case": "camelCase"}}),
            encoding="utf-8")
        ctx = canon.build_spec_canon_context(self.spec)
        self.assertEqual(ctx.convention, "camelCase")
        self.assertIn("face", str(ctx.config_path))

    def test_a_clean_ancestry_says_nothing(self):
        (self.stub_dir / "jui.config.json").write_text(
            json.dumps({"_note": "stub"}), encoding="utf-8")
        ctx = canon.build_spec_canon_context(self.spec)
        self.assertEqual(ctx.unresolved_extends, ())
        self.assertEqual(ctx.unknown_config_keys, ())


class ComparedNothingIsNotAMatchTests(unittest.TestCase):
    """An endpoint check that found no canon must not read like one that passed.

    Deleting the OpenAPI documents took a spec from one endpoint warning to
    none, and said nothing about why. Zero warnings is what a project whose
    routes all match produces, so the two were the same output.

    This is the oldest check in the validator and the only one that had the
    hole: the marks added later already fail loudly when the canon cannot be
    found. The lesson reached the new checks and was never applied back — the
    same shape a consumer lane found in its own three gates on the same day,
    the guard present in the two built after learning it and absent from the
    one that already existed. They audited theirs after reading that two of
    this tool's measurements had been empty; this is the return pass.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "screens").mkdir(parents=True)
        (self.root / "jui.config.json").write_text(
            json.dumps({"api_directory": "docs/api"}), encoding="utf-8")
        self.spec = self.root / "docs" / "screens" / "s.spec.json"
        self.spec.write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "S.json"},
            "metadata": {"name": "S", "description": "S.", "screen": "s"},
            "dataFlow": {"repositories": [{"name": "R", "methods": [
                {"name": "m", "endpoint": "GET /api/nowhere", "params": []}]}]},
        }), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def canon(self, present: bool):
        doc = self.root / "docs" / "api" / "s.json"
        if present:
            doc.write_text(json.dumps(
                {"openapi": "3.0.3", "paths": {"/api/real": {"get": {
                    "responses": {"200": {"description": "ok"}}}}}}),
                encoding="utf-8")
        elif doc.exists():
            doc.unlink()

    def warnings(self):
        v = SpecValidator()
        v._spec_file_path = self.spec
        result = SpecValidationResult()
        data = json.loads(self.spec.read_text())
        v._validate_api_endpoint_canonical(data, result)
        return [m.message for m in result.warnings]

    def test_no_canon_says_so(self):
        self.canon(False)
        w = self.warnings()
        self.assertEqual(len(w), 1)
        self.assertIn("were not checked", w[0])
        self.assertIn("nothing was compared", w[0])

    def test_it_carries_how_many_were_skipped(self):
        """A quantity beside the verdict, in BOTH units. Had the corpus
        measurement behind v1.7.12 printed the directories it scanned next to
        its count, the two faces that yielded no files would have been visible
        in it. And the unit must be named: a lane summed the site counts
        against its route count and reported the checker counting something
        else — 134 routes, 263 sites, both right, in different units."""
        self.canon(False)
        self.assertIn("1 endpoint(s), declared in 1 place(s)",
                      self.warnings()[0])

    def test_a_canon_that_is_present_checks_instead(self):
        """The boundary: with a canon, the drifted route is the finding, and
        the did-not-check notice is absent."""
        self.canon(True)
        w = self.warnings()
        self.assertEqual(len(w), 1)
        self.assertIn("/api/nowhere", w[0])
        self.assertNotIn("were not checked", w[0])

    def test_a_spec_declaring_no_endpoints_stays_quiet(self):
        """The false-positive boundary — nothing to check is not a shortfall."""
        self.canon(False)
        self.spec.write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "S.json"},
            "metadata": {"name": "S", "description": "S.", "screen": "s"},
            "dataFlow": {"viewModel": {"methods": [{"name": "onLoad"}]}},
        }), encoding="utf-8")
        self.assertEqual(self.warnings(), [])


class DeclaredButEmptyApiDirectoryAnswersTests(unittest.TestCase):
    """A config that NAMES an api_directory answers, even when it holds nothing.

    Before this, a declared directory that resolved to no documents was
    treated as "keep looking", and the walk fell through to a shallower
    config — in the measured case a repository-root `{}` whose DEFAULT
    directory held the real documents. The canon then arrived from one config
    while the convention silently reverted to another's absence, and every
    correct camelCase divergence declaration re-emerged as an error keyed on
    the document's raw spelling. Two consumer lanes hit it independently within the
    hour: one pointed its api_directory at a missing path and got 44
    convention-shifted errors instead of the compared-nothing notice; the
    other typoed its path and got 72.

    The ruling is v1.7.9's, applied to one more key: writing `api_directory`
    is a statement of intent, and a declaration that resolves to nothing must
    surface as a broken declaration — not as permission to keep searching.

        root/jui.config.json          {}            (default dir holds docs)
        root/docs/api/swagger.json                  (the REAL documents)
        root/docs/user/jui.config.json              extends -> ../../user
        root/docs/user/screens/json/f.spec.json
        root/user/jui.config.json     api_directory -> ../docs/api-missing
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(SWAGGER), encoding="utf-8")
        (self.root / "docs" / "user" / "screens" / "json").mkdir(parents=True)
        (self.root / "jui.config.json").write_text("{}", encoding="utf-8")
        (self.root / "docs" / "user" / "jui.config.json").write_text(
            json.dumps({"extends": "../../user/jui.config.json"}),
            encoding="utf-8")
        self.app = self.root / "user"
        self.app.mkdir()
        (self.app / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../docs/api-missing",
             "spec": {"canonical_param_case": "camelCase"}}), encoding="utf-8")
        self.spec = (self.root / "docs" / "user" / "screens" / "json"
                     / "f.spec.json")
        self.spec.write_text(json.dumps(_spec(
            {"name": "m", "endpoint": "POST /api/quotes",
             "params": [{"name": "venueSlug", "type": "String"}],
             "canonicalDivergence": {
                 "omitted": [{"name": "tierId", "reason": "server derives"}]},
             })), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def context(self):
        return canon.build_spec_canon_context(self.spec)

    def validate(self):
        v = SpecValidator()
        v._spec_file_path = self.spec
        result = SpecValidationResult()
        data = json.loads(self.spec.read_text())
        v._resolve_canonical_marks(data, result)
        v._validate_api_endpoint_canonical(data, result)
        return ([m.message for m in result.errors],
                [m.message for m in result.warnings])

    def test_the_declaring_config_answers_with_its_empty_index(self):
        ctx = self.context()
        self.assertEqual(ctx.index, {})
        self.assertEqual(Path(ctx.config_path).resolve(),
                         (self.app / "jui.config.json").resolve())

    def test_the_shallower_configs_documents_are_not_borrowed(self):
        """The root's default directory holds the real swagger; it must not
        leak into a run whose own config names a different place."""
        ctx = self.context()
        self.assertEqual(ctx.index, {})

    def test_the_searched_directory_is_recorded(self):
        ctx = self.context()
        self.assertEqual(Path(ctx.api_dir).resolve(),
                         (self.root / "docs" / "api-missing").resolve())

    def test_the_notice_fires_and_names_the_place(self):
        errors, warnings = self.validate()
        notice = [w for w in warnings if "were not checked" in w]
        self.assertEqual(len(notice), 1)
        self.assertIn("api-missing", notice[0])
        self.assertIn("jui.config.json", notice[0])

    def test_the_divergence_error_says_unreachable_not_undeclared(self):
        """The failure must be attributed to the broken path, not to the
        declarations. 'does not declare' on 44 correct rows is what the
        fallthrough produced; 'is not declared in any OpenAPI document' is
        the honest sentence."""
        errors, _ = self.validate()
        self.assertTrue(errors)
        for message in errors:
            self.assertNotIn("does not declare", message)

    def test_a_config_that_says_nothing_still_lets_the_walk_continue(self):
        """The boundary a consumer monorepo measured on purpose and asked to keep: a
        face config with NO api_directory key falls through, and a root whose
        default directory holds the documents answers. Monorepos rely on it."""
        (self.app / "jui.config.json").write_text(json.dumps(
            {"spec": {"canonical_param_case": "camelCase"}}), encoding="utf-8")
        ctx = self.context()
        self.assertTrue(ctx.index)
        self.assertEqual(Path(ctx.config_path).resolve(),
                         (self.root / "jui.config.json").resolve())


class UncheckedCountIsPerFileTests(unittest.TestCase):
    """The notice is a per-file fact now, and the counts must sum to the run.

    The first version fired once per validator while counting per file, and
    a consumer lane measured the disagreement directly: it held the run's
    unchecked total at four and moved declarations between the two files, and
    the reported number tracked the file order (1 <-> 3) instead of the total.
    Per-file emission makes each count that file's own fact; the batch total
    is their sum, not whichever file came first.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "screens").mkdir(parents=True)
        (self.root / "jui.config.json").write_text(
            json.dumps({"api_directory": "docs/api"}), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _file(self, name, n):
        methods = [{"name": f"m{i}", "endpoint": f"GET /api/{name}/{i}",
                    "params": []} for i in range(n)]
        p = self.root / "docs" / "screens" / f"{name}.spec.json"
        p.write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "R.json"},
            "metadata": {"name": name, "description": "d.", "screen": name},
            "dataFlow": {"repositories": [{"name": "R", "methods": methods}]},
        }), encoding="utf-8")
        return p

    def test_each_file_reports_its_own_count_and_the_sum_is_the_run(self):
        files = [self._file("items", 1), self._file("profile", 3)]
        v = SpecValidator()  # ONE validator, as `validate spec <dir>` uses
        counts = []
        for p in files:
            v._spec_file_path = p
            result = SpecValidationResult()
            v._validate_api_endpoint_canonical(
                json.loads(p.read_text()), result)
            notices = [w.message for w in result.warnings
                       if "were not checked" in w.message]
            self.assertEqual(len(notices), 1, p.name)
            counts.append(int(notices[0].split(" ")[0]))
        self.assertEqual(sorted(counts), [1, 3])
        self.assertEqual(sum(counts), 4)


class EveryWalkKeyHasABrokenDeclarationProbeTests(unittest.TestCase):
    """Walk `WALK_READS`; a key without a probe here fails this suite.

    Four key families produced eight versions of one defect — a declaration
    falling quietly to the default or the search when it fails to resolve,
    with the landing spot able to answer, so every downstream check stays
    correctly silent. A consumer lane tabulated them and named the rule:
    a declared key ships WITH the shot at its empty-resolution case.

    Each probe builds the adversarial tree — the declaration broken AND a
    shallower config able to answer — and asserts two things: the breakage
    surfaces in the context's diagnostics, and the shallower config has not
    silently supplied the answer the broken declaration was meant to give.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(SWAGGER), encoding="utf-8")
        (self.root / "docs" / "screens").mkdir(parents=True)
        self.spec = self.root / "docs" / "screens" / "f.spec.json"
        self.spec.write_text(json.dumps(_spec({"name": "a"})), encoding="utf-8")
        # The shallower config that could answer everything by default.
        (self.root / "jui.config.json").write_text("{}", encoding="utf-8")
        self.app = self.root / "app"
        self.app.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _stub(self, target="../app/jui.config.json"):
        (self.root / "docs" / "jui.config.json").write_text(
            json.dumps({"extends": target}), encoding="utf-8")

    def _probe_extends(self):
        self._stub(target="../nowhere/jui.config.json")
        ctx = canon.build_spec_canon_context(self.spec)
        self.assertTrue(ctx.unresolved_extends)

    def _probe_api_directory(self):
        self._stub()
        (self.app / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../docs/api-missing"}), encoding="utf-8")
        ctx = canon.build_spec_canon_context(self.spec)
        self.assertEqual(ctx.index, {},
                         "the root's default directory answered for a "
                         "declared-but-empty api_directory")

    def _probe_spec_canonical_param_case(self):
        self._stub()
        (self.app / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../docs/api",
             "spec": {"canonical_param_case": "camelcase"}}), encoding="utf-8")
        ctx = canon.build_spec_canon_context(self.spec)
        self.assertTrue(ctx.invalid_config_values)
        self.assertIsNone(ctx.convention,
                          "a typo'd convention must resolve as no convention "
                          "AND say so — not silently become the typo")

    def test_every_registered_key_is_probed(self):
        probes = {
            "extends": self._probe_extends,
            "api_directory": self._probe_api_directory,
            "spec.canonical_param_case": self._probe_spec_canonical_param_case,
        }
        unprobed = [k for k in canon.WALK_READS if k not in probes]
        self.assertEqual(unprobed, [],
                         "a key was added to the walk without a "
                         "broken-declaration probe — that is how the last "
                         "four families shipped")
        for key in canon.WALK_READS:
            with self.subTest(key=key):
                probes[key]()

    def test_the_typo_convention_is_named_with_its_valid_values(self):
        self._stub()
        (self.app / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../docs/api",
             "spec": {"canonical_param_case": "CamelCase"}}), encoding="utf-8")
        ctx = canon.build_spec_canon_context(self.spec)
        self.assertEqual(len(ctx.invalid_config_values), 1)
        message = ctx.invalid_config_values[0]
        self.assertIn("'CamelCase'", message)
        self.assertIn("asIs, camelCase, snake_case", message)

    def test_a_valid_convention_says_nothing(self):
        self._stub()
        (self.app / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../docs/api",
             "spec": {"canonical_param_case": "camelCase"}}), encoding="utf-8")
        ctx = canon.build_spec_canon_context(self.spec)
        self.assertEqual(ctx.invalid_config_values, ())
        self.assertEqual(ctx.convention, "camelCase")


class WalkReadsMatchesTheCodeTests(unittest.TestCase):
    """WALK_READS must equal what the walk's source actually reads.

    The probe suite above guards one direction: a key registered without a
    probe fails. A lane shot the other direction and it passed silently —
    it taught the walk a new `config.get(...)` WITHOUT registering it, and
    every suite stayed green, because WALK_READS was a hand-maintained list
    referenced by nothing but its own tests. That is the exact entry point
    of all five defect families: nobody 'registers a key without a probe';
    what actually happens is 'the walk learns to read a new key', and the
    reader must remember the registry. config_keys.py already solved this
    shape with a corpus check that goes stale loudly; this is the same
    move — the source is scanned, so teaching the walk a new key without
    registering it turns THIS test red, and registering without a probe
    turns the probe suite red. Both directions are now structure.
    """

    #: Functions that constitute the walk. A read added anywhere else that
    #: feeds the context should be moved into (or called from) these.
    WALK_FUNCTIONS = ("build_spec_canon_context", "_follow_extends")

    def _keys_read_by_the_source(self):
        import ast

        source = Path(canon.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        reads: set = set()

        def receiver_name(value):
            """`config.get(...)` and `(spec_cfg or {}).get(...)` both count."""
            if isinstance(value, ast.Name):
                return value.id
            if isinstance(value, ast.BoolOp):
                for v in value.values:
                    if isinstance(v, ast.Name):
                        return v.id
            return None

        class Visitor(ast.NodeVisitor):
            def visit_Call(self, node):
                f = node.func
                if (isinstance(f, ast.Attribute) and f.attr == "get"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    name = receiver_name(f.value)
                    if name == "config":
                        reads.add(node.args[0].value)
                    elif name == "spec_cfg":
                        reads.add("spec." + node.args[0].value)
                self.generic_visit(node)

            def visit_Compare(self, node):
                # `"api_directory" in config`
                if (isinstance(node.left, ast.Constant)
                        and isinstance(node.left.value, str)
                        and len(node.ops) == 1
                        and isinstance(node.ops[0], ast.In)
                        and isinstance(node.comparators[0], ast.Name)
                        and node.comparators[0].id == "config"):
                    reads.add(node.left.value)
                self.generic_visit(node)

        for fn in ast.walk(tree):
            if (isinstance(fn, ast.FunctionDef)
                    and fn.name in self.WALK_FUNCTIONS):
                Visitor().visit(fn)
        # `config.get("spec")` is the container reach for
        # `spec.canonical_param_case`; the dotted form is the declaration.
        if "spec" in reads and any(k.startswith("spec.") for k in reads):
            reads.discard("spec")
        return reads

    def test_the_registry_and_the_source_agree(self):
        reads = self._keys_read_by_the_source()
        registered = set(canon.WALK_READS)
        self.assertEqual(
            reads - registered, set(),
            "the walk reads keys WALK_READS does not declare — register "
            "them AND give each a broken-declaration probe")
        self.assertEqual(
            registered - reads, set(),
            "WALK_READS declares keys the walk no longer reads — prune "
            "them or the probes assert dead behavior")

    def test_the_scan_itself_sees_the_known_reads(self):
        """The scanner's own negative control: a scan that returned an empty
        set would make the agreement test pass vacuously against an empty
        registry diff — 'compared nothing' wearing a green checkmark."""
        reads = self._keys_read_by_the_source()
        self.assertIn("extends", reads)
        self.assertIn("api_directory", reads)
        self.assertIn("spec.canonical_param_case", reads)
