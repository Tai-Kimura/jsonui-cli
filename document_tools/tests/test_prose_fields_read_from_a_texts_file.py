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


if __name__ == "__main__":
    unittest.main()
