"""`app_contracts_spec` is accepted, and an unknown type is refused as one.

Before this, `_validate_spec` was the `else` arm for every non-component
type, so an unknown type was validated as a screen spec: the author of
`{"type": "app_contract"}` was told `structure` was missing, `displayName`
was missing, and the name was not PascalCase — four errors describing a
document they never claimed to be writing, with the type error among them
reading as a detail. The measurement that mattered was the MISSPELLED known
type: it is indistinguishable, in the output, from a mis-written screen spec.
"""

import unittest

from jsonui_doc_cli.spec_doc.validator import (
    APP_CONTRACTS_SPEC,
    KNOWN_SPEC_TYPES,
    SpecValidator,
)


def _app_spec(**over):
    spec = {
        "type": APP_CONTRACTS_SPEC,
        "version": "1.0",
        "metadata": {"name": "user", "description": "units this app owns"},
        "unitContracts": [
            {"target": "SharedClient", "cases": [{"name": "retries once"}]}
        ],
    }
    spec.update(over)
    return spec


def _errors(spec):
    return SpecValidator().validate_data(spec, "spec").errors


class FaceContractsSpecIsAccepted(unittest.TestCase):
    def test_a_well_formed_app_spec_validates_clean(self):
        self.assertEqual([], [e.message for e in _errors(_app_spec())])

    def test_the_app_name_is_not_held_to_the_screen_rules(self):
        """An app name is not a class name.

        `metadata.name` here identifies the app, so the PascalCase rule and
        the `displayName` requirement — both correct for a screen — would
        report a correctly written app spec as malformed.
        """
        msgs = [e.message for e in _errors(_app_spec())]
        self.assertNotIn("Name must be PascalCase: 'user'", msgs)
        self.assertFalse([m for m in msgs if "displayName" in m], msgs)


class AnUnknownTypeIsRefusedAsATypeError(unittest.TestCase):
    def test_a_misspelled_app_type_reports_the_type_and_nothing_else(self):
        errs = _errors(_app_spec(type="app_contract"))
        self.assertEqual(1, len(errs), [e.message for e in errs])
        self.assertEqual("type", errs[0].path)
        self.assertIn("app_contract", errs[0].message)

    def test_it_is_not_reported_as_a_malformed_screen_spec(self):
        """The regression this arm exists for.

        With the refusal inside `_validate_spec`, these four came back
        together and the author read the loudest one — a missing `structure`
        — as the problem.
        """
        msgs = " | ".join(e.message for e in _errors(_app_spec(type="app_contract")))
        for screen_word in ("structure", "displayName", "PascalCase"):
            self.assertNotIn(screen_word, msgs)

    def test_the_message_names_every_type_that_would_have_worked(self):
        msg = _errors(_app_spec(type="nonsense"))[0].message
        for known in KNOWN_SPEC_TYPES:
            self.assertIn(known, msg)


class AFaceSpecCannotHoldScreenOwnedSections(unittest.TestCase):
    def test_each_forbidden_section_is_refused_by_name(self):
        for section in SpecValidator._APP_SPEC_FORBIDDEN:
            with self.subTest(section=section):
                paths = [e.path for e in _errors(_app_spec(**{section: ["x"]}))]
                self.assertIn(section, paths)

    def test_branch_contracts_is_refused(self):
        """N2. Declared separately from the loop above because the reason
        differs: nothing yet decides which app owns a screenless branch, and
        writable-but-unread is the failure this type exists to remove."""
        paths = [e.path for e in _errors(_app_spec(branchContracts={"a": {}}))]
        self.assertIn("branchContracts", paths)

    def test_an_empty_forbidden_section_is_left_alone(self):
        """An empty list declares nothing and changes no output, so refusing
        it would report a document that says nothing as saying something."""
        self.assertEqual([], [e.message for e in _errors(_app_spec(structure=[]))])


class TheScreenTypesAreUnchanged(unittest.TestCase):
    """The control for the dispatch rewrite: the three screen types still
    reach `_validate_spec`, and a screen spec missing `structure` still says
    so rather than being refused as an unknown type."""

    def test_a_screen_spec_missing_structure_still_reports_structure(self):
        msgs = " | ".join(e.message for e in _errors(
            {"type": "screen_spec", "version": "1.0",
             "metadata": {"name": "Listing", "displayName": "L",
                          "description": "d"}}))
        self.assertIn("structure", msgs)

    def test_a_spec_with_no_type_is_still_read_as_a_screen_spec(self):
        msgs = " | ".join(e.message for e in _errors(
            {"version": "1.0",
             "metadata": {"name": "Listing", "displayName": "L",
                          "description": "d"}}))
        self.assertIn("structure", msgs)
        self.assertNotIn("Expected one of", msgs)


if __name__ == "__main__":
    unittest.main()
