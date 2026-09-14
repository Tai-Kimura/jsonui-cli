"""`input` is declared twice, and the degradations are declared in prose.

Two holes found by mutating the SSoT after 1.8.80's declaration landed. Both
mutations survived every suite:

  drop the four new values from TextView's enum only   1946 passed
  delete the sentence about signedDecimal degrading    1946 passed

The first is the shape this lane walked into the same afternoon in a different
file: a word that names two things read as if it named one. `input` is not one
declaration with two homes -- TextField and TextView each carry their own copy,
and nothing made them agree. Adding a value to one is a normal-looking edit.

The second is narrower but worse to lose. What a value degrades to on each face
was decided before any emitter existed, deliberately, so the declaration is a
contract rather than a description of whatever got built. That decision lives
only in prose, and no gate reads prose. The web emitter has since landed against
it -- signedDecimal collapses onto decimal because HTML has no signed-decimal
type -- so deleting the sentence would leave a collapse that looks like a bug to
the next reader and like a feature to the next implementer.

These arms cannot check that the prose is TRUE. They check that it is THERE,
which is the part a later edit takes away silently.
"""

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO_ROOT / "shared" / "core" / "attribute_definitions.json"

#: Components that declare `input`. Derived by scanning rather than listed, so a
#: third component growing one is caught instead of silently unchecked.
def _components_declaring(attribute: str, definitions: dict) -> list:
    return sorted(
        name
        for name, attrs in definitions.items()
        if isinstance(attrs, dict) and attribute in attrs
    )


class InputIsDeclaredInMoreThanOnePlace(unittest.TestCase):
    def setUp(self):
        self.definitions = json.loads(DEFINITIONS.read_text(encoding="utf-8"))
        self.hosts = _components_declaring("input", self.definitions)

    def test_the_hosts_are_found_by_scanning_not_by_a_list(self):
        # Guards the arms below: if `input` ever stops being declared twice,
        # they would pass vacuously over a single copy.
        self.assertGreaterEqual(
            len(self.hosts), 2,
            f"`input` is declared in {self.hosts} — the arms below compare copies "
            "and have nothing to compare",
        )

    def test_every_declaration_of_input_carries_the_same_enum(self):
        enums = {host: self.definitions[host]["input"]["enum"] for host in self.hosts}
        first = self.hosts[0]
        for host in self.hosts[1:]:
            self.assertEqual(
                enums[first], enums[host],
                f"{first}.input and {host}.input declare different values. A value "
                f"added to one and not the other is declared for one component and "
                f"not the other, which reads as a missing implementation rather "
                f"than a missing declaration.\n"
                f"  only in {first}: {sorted(set(enums[first]) - set(enums[host]))}\n"
                f"  only in {host}: {sorted(set(enums[host]) - set(enums[first]))}",
            )

    def test_every_declaration_of_input_carries_the_same_description(self):
        # The degradations are per-value, not per-component, so the two copies
        # must say the same thing. Editing one is the same hole as the enum.
        texts = {host: self.definitions[host]["input"]["description"] for host in self.hosts}
        first = self.hosts[0]
        for host in self.hosts[1:]:
            self.assertEqual(
                texts[first], texts[host],
                f"{first}.input and {host}.input describe the same values differently",
            )


class TheDegradationsAreStillWrittenDown(unittest.TestCase):
    """Each token names something that vanishes without a trace if removed."""

    #: token -> why losing it costs something a reader cannot recover.
    REQUIRED_IN_INPUT = {
        "signedDecimal": "the value that collapses onto decimal on web",
        "decimal": "what it collapses ONTO — the collapse needs both names",
        "textarea": "the element with no type attribute, which is WHY TextView "
                    "cannot honour the date family",
        "datetime-local": "the web spelling, shared with SelectBox's datepicker",
        "DecimalSigned": "the Compose member that actually EXISTS. The plan for this "
                         "work named it SignedDecimal, which does not, and this "
                         "description repeated the plan until 2026-09-14 while the "
                         "emitter already emitted the real one — the declaration named "
                         "a member no compiler would accept. Both spellings are in "
                         "the text deliberately, so a grep for SignedDecimal returns "
                         "the correction, not the defect",
        "Android, dynamic": "the face that does NOT support these. The runtime "
                            "renderer falls to else -> KeyboardType.Text for all "
                            "four, so 'Android supports it' is true only of codegen. "
                            "Saying 'Android' without the face is the same scope "
                            "error this repo shipped in a dev-guide the same week",
        "1.12.0 is the first": "the version floor. ui-text 1.11 has ten "
                               "KeyboardType members and none of these four, so a "
                               "consumer on an older Compose gets a compile error "
                               "rather than a degradation",
        "Signed is a suffix": "the naming rule behind the DecimalSigned spelling. "
                              "Compose writes <base><modifier>, and 1.12.0 ships "
                              "three members that follow it — NumberSigned, "
                              "DecimalPasswordSigned, NumberPasswordSigned (javap -p "
                              "on KeyboardType$Companion in the ui-text 1.12.0 aar) — "
                              "so the rule is evidenced, not asserted, and the next "
                              "value added here should not be written Signed-first",
        "the hit count is not a measure": "the sentence that stops a grep census "
                                          "from being read as a failed correction. "
                                          "Both spellings are in this text on "
                                          "purpose; without this line the next reader "
                                          "counts SignedDecimal hits and concludes "
                                          "the fix never landed. It is also the "
                                          "sentence most likely to be tidied away, "
                                          "since an attribute description explaining "
                                          "grep looks out of place",
    }

    #: The superseded pair says in its own description that it is superseded and
    #: that the normalizer fold is not written yet. Without it, a reader finds
    #: two spellings for one effect and no way to tell which to use.
    REQUIRED_IN_SUPERSEDED = {"SUPERSEDED", "glass"}

    def setUp(self):
        self.definitions = json.loads(DEFINITIONS.read_text(encoding="utf-8"))

    def test_input_still_says_what_each_face_cannot_express(self):
        for host in _components_declaring("input", self.definitions):
            text = self.definitions[host]["input"]["description"]
            for token, why in self.REQUIRED_IN_INPUT.items():
                self.assertIn(
                    token, text,
                    f"{host}.input no longer mentions {token!r} ({why}). The "
                    f"degradation was decided 2026-09-14 before the emitters "
                    f"existed; the web emitter was written against it. This arm "
                    f"cannot tell whether the sentence is still correct, only "
                    f"that it is still there.",
                )

    def test_the_superseded_pair_still_says_it_is_superseded(self):
        for attribute in ("applyLiquidGlass", "glassEffectStyle"):
            text = self.definitions["TextField"][attribute]["description"]
            for token in self.REQUIRED_IN_SUPERSEDED:
                self.assertIn(
                    token, text,
                    f"TextField.{attribute} no longer says it is superseded by "
                    f"glass. Both spellings are live until the normalizer fold "
                    f"lands, and without the note there is nothing to tell a "
                    f"layout author which one to write.",
                )


if __name__ == "__main__":
    unittest.main()
