"""A spec's prose may live in a YAML texts file and render as Markdown.

`{"md": "a.b.c"}` in `description` / `notes` / `intent` reads the spec's
paired `<name>.texts.yaml`; `{"md": "other.texts.yaml#a.b"}` names a file.
An inline string stays plain text — its line breaks kept, nothing else
reinterpreted — so no existing spec changes meaning.

What is pinned here:

* resolution happens where the spec is read, into a `str` subclass, so every
  reader that treats the field as a string keeps working;
* each YAML rule that has a silent wrong reading (a `yes:` key turned boolean,
  a dotted key, a duplicate key, a list) is an error that names the key;
* a page with no texts-file reference is byte-identical: the Markdown CSS is
  added only to a page that renders Markdown;
* Markdown cannot carry raw HTML into the page.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli import shared_core
from jsonui_doc_cli.prose import plain_html, prose_html
from jsonui_doc_cli.spec_doc.html_generator import generate_spec_html
from jsonui_doc_cli.spec_doc.markdown_generator import generate_spec_markdown
from jsonui_doc_cli.spec_doc.validator import APP_CONTRACTS_SPEC, SpecValidator

texts = shared_core.load("spec_texts")


def _app_spec(description, intent="checks"):
    return {
        "type": APP_CONTRACTS_SPEC,
        "version": "1.0",
        "metadata": {"name": "app", "description": description},
        "unitContracts": [
            {"target": "ApiClient",
             "cases": [{"name": "retriesOnce", "intent": intent}]}
        ],
    }


class _Dir(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def write(self, name, content):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_text(json.dumps(content, ensure_ascii=False),
                            encoding="utf-8")
        return path

    def resolve(self, spec, yaml_text=None, name="app.spec.json"):
        path = self.write(name, spec)
        if yaml_text is not None:
            self.write(name.replace(".spec.json", ".texts.yaml"), yaml_text)
        return texts.resolve_spec_texts(spec, path)


class References(_Dir):
    def test_a_nested_key_in_the_paired_file_resolves_to_markdown(self):
        r = self.resolve(
            _app_spec({"md": "overview"},
                      {"md": "cases.api_client.retries_once"}),
            "overview: |\n  # Title\n\n  - a\n"
            "cases:\n  api_client:\n    retries_once: |\n      **bold**\n")
        self.assertEqual([], r.errors)
        desc = r.data["metadata"]["description"]
        intent = r.data["unitContracts"][0]["cases"][0]["intent"]
        self.assertTrue(texts.is_markdown(desc))
        self.assertEqual("# Title\n\n- a\n", desc)
        self.assertIsInstance(intent, str)
        self.assertEqual("**bold**\n", intent)

    def test_a_named_file_resolves_relative_to_the_spec(self):
        self.write("shared/net.texts.yaml", "timeouts:\n  default: ten\n")
        r = self.resolve(_app_spec({"md": "shared/net.texts.yaml#timeouts.default"}))
        self.assertEqual([], r.errors)
        self.assertEqual("ten", r.data["metadata"]["description"])

    def test_notes_entries_resolve_one_by_one(self):
        spec = _app_spec("plain")
        spec["notes"] = ["inline", {"md": "n1"}]
        r = self.resolve(spec, "n1: from yaml\n")
        self.assertEqual([], r.errors)
        self.assertEqual(["inline", "from yaml"], r.data["notes"])
        self.assertFalse(texts.is_markdown(r.data["notes"][0]))
        self.assertTrue(texts.is_markdown(r.data["notes"][1]))

    def test_a_plain_string_is_left_alone_and_the_input_is_not_modified(self):
        spec = _app_spec("line 1\nline 2", {"md": "x"})
        r = self.resolve(spec, "x: y\n")
        self.assertEqual("line 1\nline 2", r.data["metadata"]["description"])
        self.assertFalse(texts.is_markdown(r.data["metadata"]["description"]))
        self.assertEqual({"md": "x"},
                         spec["unitContracts"][0]["cases"][0]["intent"])

    def test_a_spec_with_no_reference_and_no_file_is_unchanged(self):
        spec = _app_spec("d")
        r = self.resolve(spec)
        self.assertEqual(spec, r.data)
        self.assertEqual(([], []), (r.errors, r.warnings))


class ReferenceErrors(_Dir):
    def errors(self, spec, yaml_text=None):
        return self.resolve(spec, yaml_text).errors

    def test_an_undefined_key_is_named(self):
        (e,) = self.errors(_app_spec({"md": "nope"}), "other: x\n")
        self.assertIn("app.texts.yaml#nope", e)
        self.assertIn("not defined", e)

    def test_a_key_that_names_a_mapping_is_refused(self):
        (e,) = self.errors(_app_spec({"md": "a"}), "a:\n  b: x\n")
        self.assertIn("is a mapping", e)

    def test_a_missing_file_is_named(self):
        (e,) = self.errors(_app_spec({"md": "gone.texts.yaml#k"}))
        self.assertIn("gone.texts.yaml does not exist", e)

    def test_a_malformed_reference_is_refused(self):
        (e,) = self.errors(_app_spec({"md": "k", "extra": 1}), "k: x\n")
        self.assertIn("'extra'", e)

    def test_a_reference_outside_a_prose_field_is_refused(self):
        spec = _app_spec("d")
        spec["metadata"]["name"] = {"md": "k"}
        (e,) = self.errors(spec, "k: x\n")
        self.assertIn("metadata.name", e)
        self.assertIn("description / notes / intent", e)


class YamlRules(_Dir):
    def errors(self, yaml_text):
        return self.resolve(_app_spec({"md": "ok"}), "ok: fine\n" + yaml_text).errors

    def test_a_yes_key_is_a_boolean_and_is_refused(self):
        (e,) = self.errors("yes: x\n")
        self.assertIn("bool", e)
        self.assertIn("quote the key", e)

    def test_a_dotted_key_is_refused(self):
        (e,) = self.errors("a.b: x\n")
        self.assertIn("'a.b'", e)
        self.assertIn("path separator", e)

    def test_a_duplicate_key_is_refused_instead_of_keeping_the_last(self):
        (e,) = self.errors("dup: 1st\ndup: 2nd\n")
        self.assertIn("duplicate key 'dup'", e)
        # The line of the second key, not PyYAML's `in "<unicode string>"`.
        self.assertIn("line 3:", e)
        self.assertNotIn("<unicode string>", e)

    def test_a_list_value_is_refused(self):
        (e,) = self.errors("l:\n  - a\n")
        self.assertIn("'l' is a list", e)

    def test_an_empty_value_is_refused(self):
        (e,) = self.errors("empty:\n")
        self.assertIn("'empty' is empty", e)


class UnusedKeys(_Dir):
    def test_a_paired_key_nothing_references_is_a_warning(self):
        r = self.resolve(_app_spec({"md": "used"}), "used: a\nstale:\n  old: b\n")
        self.assertEqual([], r.errors)
        (w,) = r.warnings
        self.assertIn("stale.old", w)

    def test_a_named_file_is_not_audited_for_unused_keys(self):
        self.write("shared.texts.yaml", "used: a\nother: b\n")
        r = self.resolve(_app_spec({"md": "shared.texts.yaml#used"}))
        self.assertEqual(([], []), (r.errors, r.warnings))


class ValidatorReadsThrough(_Dir):
    def test_validate_file_hands_on_the_resolved_spec(self):
        path = self.write("app.spec.json", _app_spec({"md": "overview"}))
        self.write("app.texts.yaml", "overview: |\n  **x**\n")
        result = SpecValidator().validate_file(path)
        self.assertEqual([], [e.message for e in result.errors])
        self.assertTrue(texts.is_markdown(result.spec_data["metadata"]["description"]))

    def test_an_unresolvable_reference_fails_validation(self):
        path = self.write("app.spec.json", _app_spec({"md": "missing"}))
        self.write("app.texts.yaml", "other: x\n")
        result = SpecValidator().validate_file(path)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("missing" in e.message for e in result.errors))


class Rendering(_Dir):
    def test_plain_text_keeps_its_line_breaks_and_is_escaped(self):
        self.assertEqual("a &lt;b&gt;<br>c", prose_html("a <b>\nc"))
        self.assertEqual("", plain_html(None))

    def test_markdown_renders_and_raw_html_does_not(self):
        md = texts.MarkdownText("## H\n\n- `x`\n\n<script>alert(1)</script>\n"
                                "[l](javascript:alert(1))")
        out = prose_html(md)
        self.assertIn('<div class="md">', out)
        self.assertIn("<h2>H</h2>", out)
        self.assertIn("<code>x</code>", out)
        self.assertNotIn("<script>", out)
        self.assertNotIn('href="javascript:', out)

    def test_a_page_gets_the_markdown_css_only_when_it_renders_markdown(self):
        plain = generate_spec_html(_app_spec("one\ntwo"))
        self.assertIn("one<br>two", plain)
        self.assertNotIn(".md h3", plain)
        md = generate_spec_html(_app_spec(texts.MarkdownText("### Rule\n\ntext")))
        self.assertIn("<h3>Rule</h3>", md)
        self.assertIn(".md h3", md)
        # The CSS lands inside the page's stylesheet, not after it.
        self.assertLess(md.index(".md h3"), md.index("</style>"))

    def test_the_markdown_page_keeps_a_multiline_note_inside_its_list_item(self):
        spec = _app_spec("d")
        spec["notes"] = [texts.MarkdownText("para 1\n\npara 2")]
        out = generate_spec_markdown(spec)
        self.assertIn("- para 1\n  \n  para 2", out)



class _NoModule:
    """`sys.modules[name] = None` for the block: `import name` raises
    ImportError, the state of a launcher-only install."""

    def __init__(self, *names):
        self.names = names

    def __enter__(self):
        import sys
        self.saved = {n: sys.modules.get(n, _NoModule) for n in self.names}
        for n in self.names:
            sys.modules[n] = None
        return self

    def __exit__(self, *exc):
        import sys
        for n, v in self.saved.items():
            if v is _NoModule:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = v


class MissingRenderer(unittest.TestCase):
    """A: markdown-it-py missing must not crash a page — the unit pages
    render intents without going through the validator's check."""

    def setUp(self):
        import io
        from jsonui_doc_cli import prose, run_log
        self.prose = prose
        # The renderer is cached once built; a machine that never had the
        # module never built it.
        self.saved_md = prose._md
        prose._md = None
        getattr(prose, "reset_render_warnings", lambda: None)()
        run_log.reset()
        self.out = io.StringIO()

    def tearDown(self):
        self.prose._md = self.saved_md
        getattr(self.prose, "reset_render_warnings", lambda: None)()

    def _unit_page(self, intent):
        from jsonui_doc_cli.test_doc.html.unit import generate_unit_html
        target = {"target": "ApiClient", "screens": [], "spec_files": [],
                  "cases": [{"name": "retries", "intent": intent,
                             "status": {}}],
                  "faces": {"web": {"declared": ["retries"], "implemented": [],
                                    "missing": [], "never_runs": [],
                                    "unattributed": [], "files": []}}}
        return generate_unit_html(target, ["web"])

    def test_a_markdown_intent_falls_back_to_escaped_text_and_warns_once(self):
        import contextlib
        from jsonui_doc_cli import run_log
        md = texts.MarkdownText("**bold** <b>x</b>\nline 2")
        with _NoModule("markdown_it"), contextlib.redirect_stdout(self.out):
            page1 = self._unit_page(md)
            page2 = self._unit_page(md)
        for page in (page1, page2):
            self.assertIn("**bold** &lt;b&gt;x&lt;/b&gt;<br>line 2", page)
            self.assertNotIn('<div class="md">', page)
        printed = self.out.getvalue()
        self.assertEqual(1, printed.count("markdown-it-py is not installed"),
                         printed)
        self.assertEqual(1, run_log.count())
        self.assertRegex(printed, run_log.COUNTING_RE)

    def test_the_warning_is_once_per_run_not_once_per_process(self):
        import contextlib
        from jsonui_doc_cli.test_doc.generator import reset_per_run_ledgers
        md = texts.MarkdownText("x")
        with _NoModule("markdown_it"), contextlib.redirect_stdout(self.out):
            self.prose.prose_html(md)
            reset_per_run_ledgers()
            self.prose.prose_html(md)
        self.assertEqual(2, self.out.getvalue().count(
            "markdown-it-py is not installed"))


class TableCellsInMarkdown(unittest.TestCase):
    """C: every prose value inside a Markdown table row keeps the row."""

    TWO = texts.MarkdownText("line one\nline two") if texts else "line one\nline two"

    def _rows_have_no_raw_break(self, out, needle="line one"):
        (row,) = [ln for ln in out.splitlines() if needle in ln]
        self.assertIn("line one<br>line two", row)
        self.assertTrue(row.rstrip().endswith("|"), row)

    def test_component_markdown_tables(self):
        from jsonui_doc_cli.spec_doc.html_generator import generate_component_markdown
        for section in ("props", "slots", "components", "internal", "events"):
            spec = {"metadata": {"name": "C", "description": "d"}}
            item = {"name": "x", "type": "String", "description": self.TWO}
            if section == "props":
                spec["props"] = {"items": [item]}
            elif section == "slots":
                spec["slots"] = {"items": [item]}
            elif section == "components":
                spec["structure"] = {"components": [
                    {"type": "View", "id": "v", "description": self.TWO}]}
            elif section == "internal":
                spec["stateManagement"] = {"internalStates": [item]}
            else:
                spec["stateManagement"] = {"exposedEvents": [item]}
            with self.subTest(section=section):
                self._rows_have_no_raw_break(generate_component_markdown(spec))

    def test_branch_contract_row_notes_and_note_rows(self):
        spec = _app_spec("d")
        spec["type"] = "screen_spec"
        spec["branchContracts"] = {"methods": {"onTap": {"branches": [
            {"when": {"data.a": True}, "then": {"api": "none"},
             "notes": self.TWO},
        ]}}}
        self._rows_have_no_raw_break(generate_spec_markdown(spec))


class MarkdownBlocksInTheMarkdownPage(unittest.TestCase):
    """C: a Markdown value keeps its block structure in the .md page."""

    def test_notes_label_puts_a_markdown_block_on_its_own_lines(self):
        spec = _app_spec("d")
        spec["type"] = "screen_spec"
        spec["structure"] = {"components": [], "layout": {},
                             "notes": texts.MarkdownText("## Heading\n\n- item")}
        out = generate_spec_markdown(spec)
        self.assertNotIn("**Notes:** ## Heading", out)
        self.assertIn("\n## Heading\n", out)
        self.assertIn("\n- item", out)

    def test_a_plain_note_stays_inline(self):
        spec = _app_spec("d")
        spec["type"] = "screen_spec"
        spec["structure"] = {"components": [], "layout": {}, "notes": "short"}
        self.assertIn("**Notes:** short", generate_spec_markdown(spec))

    def test_a_method_description_stays_inside_its_list_item(self):
        spec = _app_spec("d")
        spec["type"] = "screen_spec"
        spec["dataFlow"] = {"repositories": [{"name": "Repo", "methods": [
            {"name": "load", "description": texts.MarkdownText(
                "first\n\n- sub a\n- sub b")}]}]}
        out = generate_spec_markdown(spec)
        self.assertIn("\n  - sub a\n  - sub b", out)
        self.assertNotIn("\n- sub a", out)


class FileReferenceRules(_Dir):
    """G / H: the file half of a `file#key` reference."""

    def errors(self, ref):
        return self.resolve(_app_spec({"md": ref})).errors

    def test_an_empty_file_part_is_named(self):
        self.write("app.texts.yaml", "key: x\n")
        (e,) = self.errors("#key")
        self.assertIn("no file before '#'", e)
        self.assertNotIn("does not exist", e)

    def test_an_absolute_path_is_refused(self):
        other = Path(tempfile.mkdtemp()) / "abs.texts.yaml"
        other.write_text("key: x\n", encoding="utf-8")
        (e,) = self.errors(f"{other}#key")
        self.assertIn("absolute", e)

    def test_a_file_that_is_not_a_texts_file_is_refused(self):
        self.write("secrets.yaml", "key: x\n")
        (e,) = self.errors("secrets.yaml#key")
        self.assertIn(".texts.yaml", e)
        self.assertIn("secrets.yaml", e)

    def test_a_relative_shared_file_above_the_spec_is_still_allowed(self):
        self.write("shared/net.texts.yaml", "k: shared\n")
        path = self.write("screens/app.spec.json",
                          _app_spec({"md": "../shared/net.texts.yaml#k"}))
        r = texts.resolve_spec_texts(
            _app_spec({"md": "../shared/net.texts.yaml#k"}), path)
        self.assertEqual([], r.errors)
        self.assertEqual("shared", r.data["metadata"]["description"])


class YamlMessages(_Dir):
    """G: the message names what the author wrote."""

    def errors(self, yaml_text):
        return self.resolve(_app_spec({"md": "ok"}), "ok: fine\n" + yaml_text).errors

    def test_a_bool_and_an_int_key_are_non_string_keys_not_duplicates(self):
        (e,) = self.errors("yes: a\n1: b\n")
        self.assertNotIn("duplicate", e)
        self.assertIn("not a string", e)
        self.assertIn("yes", e)

    def test_a_merge_key_is_named_as_unsupported(self):
        (e,) = self.errors("base: &b\n  x: one\nderived:\n  <<: *b\n  y: two\n")
        self.assertIn("merge key", e)
        self.assertNotIn("constructor", e)


class NoReferencesNoDependency(_Dir):
    """I: a spec that references nothing never needs PyYAML or markdown-it."""

    def test_no_reference_and_no_pyyaml_is_not_an_error(self):
        spec = _app_spec("plain")
        with _NoModule("yaml"):
            r = self.resolve(spec, "stale: x\n")
        self.assertEqual([], r.errors)
        (w,) = r.warnings
        self.assertIn("PyYAML", w)
        self.assertIn("skipped", w)

    def test_validation_passes_without_either_dependency(self):
        from jsonui_doc_cli import prose
        path = self.write("app.spec.json", _app_spec("plain"))
        self.write("app.texts.yaml", "stale: x\n")
        saved = prose._md
        prose._md = None
        try:
            with _NoModule("yaml", "markdown_it"):
                result = SpecValidator().validate_file(path)
        finally:
            prose._md = saved
        self.assertEqual([], [e.message for e in result.errors])

    def test_a_texts_file_that_resolves_nothing_to_markdown_needs_no_renderer(self):
        from jsonui_doc_cli import prose
        path = self.write("app.spec.json", _app_spec({"md": "gone"}))
        self.write("app.texts.yaml", "other: x\n")
        saved = prose._md
        prose._md = None
        try:
            with _NoModule("markdown_it"):
                result = SpecValidator().validate_file(path)
        finally:
            prose._md = saved
        messages = [e.message for e in result.errors]
        self.assertTrue(any("not defined" in m for m in messages), messages)
        self.assertFalse(any("markdown-it-py" in m for m in messages), messages)

    def test_a_resolved_reference_still_needs_the_renderer(self):
        from jsonui_doc_cli import prose
        path = self.write("app.spec.json", _app_spec({"md": "k"}))
        self.write("app.texts.yaml", "k: x\n")
        saved = prose._md
        prose._md = None
        try:
            with _NoModule("markdown_it"):
                result = SpecValidator().validate_file(path)
        finally:
            prose._md = saved
        self.assertTrue(any("markdown-it-py" in e.message for e in result.errors))


if __name__ == "__main__":
    unittest.main()
