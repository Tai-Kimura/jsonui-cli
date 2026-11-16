"""component_metadata.json's words about a default vs. the declared default.

jsonui-mcp-server's ``lookup_component`` answers with a component's
attributes from ``attribute_definitions.json``, each with its declared
``default``, and beside them the prose ``rules`` of
``component_metadata.json``. Where that prose states a default it restates
the declaration, and nothing kept the two together. On 2026-09-26 three
did not agree:

- Slider's rule said "default 0-100". minimum / maximum declare 0 and 1,
  and every face draws 0 .. 1.
- Collection's rule described ``lazy`` as a boolean, "default true". It is
  a declared enum lazy / eager / none, defaulting to 'lazy'; sjui and kjui
  draw ``lazy: false`` as 'lazy'.
- NetworkImage's rule gave contentMode a Swift default, ".center for
  matchParent". contentMode declares no default, and no Swift path draws
  that: SwiftUI (codegen and Dynamic) draws fit, UIKit aspectFill.

The facts are derived from the declaration; the reading is recorded by
hand and enforced. Every metadata string that uses the word "default" is
read once, into one of two tables:

  STATES_A_DEFAULT  The string states the default of these attributes.
                    Each attribute is named in the string, by its name or
                    a declared alias spelling. Each declares a default,
                    and the string carries that value as a word: a string
                    value in quotes, a number or a boolean bare.
  NOT_A_DEFAULT     The word is used otherwise; the reason is recorded.

A string in neither table is red until it has been read. A row whose
string has gone is red too, so the tables cannot drift from the file. The
rows are keyed by the exact text: a reworded rule is read again.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
METADATA = REPO_ROOT / "shared" / "core" / "component_metadata.json"
DEFINITIONS = REPO_ROOT / "shared" / "core" / "attribute_definitions.json"

DEFAULT_WORD = re.compile(r"\bdefault\b", re.IGNORECASE)

# (component, exact string) -> attributes whose declared default it states
STATES_A_DEFAULT: dict[tuple[str, str], list[str]] = {
    ("Slider", "minimum / maximum define the range (default 0 and 1: with neither set the range is 0 .. 1); "
               "minimumValue / minValue and maximumValue / maxValue are alias spellings"): ["minimum", "maximum"],
    ("Collection", "lazy (default 'lazy') is the outer container: 'lazy' virtualizes (LazyVStack/LazyColumn/"
                   "LazyVerticalGrid with internal scroll); 'eager' draws every cell in a scroll container, with no "
                   "virtualization; 'none' draws them with NO scroll container (use when nested in an "
                   "already-scrollable parent). Sticky headers and paging require 'lazy'."): ["lazy"],
    ("Embed", "navigationMode 'delegate' (default): parent NavController/Router is shared; pop/dismiss/navigateBack "
              "are bounded at the embed and do not close it. 'isolated': the embed owns a private nav stack — push "
              "stays inside, pop stops at the embed stack root, the embed never closes itself. Requires SwiftJsonUI "
              ">= 10.5.0 / KotlinJsonUI >= 2.12.0 / EmbedContainer.tsx template v2."): ["navigationMode"],
}

# (component, exact string) -> why the word is not an attribute's default
NOT_A_DEFAULT: dict[tuple[str, str], str] = {
    ("TextView", "Multi-line input (unlike TextField which is single-line by default)"):
        "describes TextField's line count, not the value of an attribute",
}


def metadata_strings(metadata: dict) -> list[tuple[str, str, str]]:
    """(component, path, string) for every string under each component."""
    found: list[tuple[str, str, str]] = []

    def walk(component: str, node, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(component, value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(component, value, f"{path}.{index}")
        elif isinstance(node, str):
            found.append((component, path, node))

    for component, entry in metadata.items():
        if not component.startswith("_"):
            walk(component, entry, component)
    return found


def _section(definitions: dict, component: str) -> dict:
    section = definitions.get(component)
    if isinstance(section, dict) and isinstance(section.get("_alias_of"), str):
        section = definitions.get(section["_alias_of"])
    return section if isinstance(section, dict) else {}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9_]+(?:\.[0-9]+)?", text))


def _value_spellings(value) -> list[str]:
    """How the declared default appears in prose."""
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, (int, float)):
        return [str(int(value))] if float(value).is_integer() else [repr(value)]
    if isinstance(value, str):
        return [f"'{value}'", f'"{value}"', f"`{value}`"]
    return [json.dumps(value)]


def disagreements(definitions: dict, component: str, attributes: list[str], text: str) -> list[str]:
    """What the text gets wrong about these attributes' declared defaults."""
    problems: list[str] = []
    section = _section(definitions, component)
    words = _words(text)
    for name in attributes:
        attr = section.get(name)
        if not isinstance(attr, dict):
            problems.append(f"{component}.{name} is not declared")
            continue
        names = [name] + [a for a in attr.get("aliases") or [] if isinstance(a, str)]
        if not any(n in words for n in names):
            problems.append(f"{component}.{name}: the text does not name it ({' / '.join(names)})")
        if "default" not in attr:
            problems.append(f"{component}.{name} declares no default, and the text states one")
            continue
        spellings = _value_spellings(attr["default"])
        bare = [s for s in spellings if not s[0] in "'\"`"]
        found = any(s in words for s in bare) or any(s in text for s in spellings if s not in bare)
        if not found:
            problems.append(
                f"{component}.{name} declares default {attr['default']!r}; the text does not say "
                f"{' or '.join(spellings)}"
            )
    return problems


class ComponentMetadataDefaultsAgree(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        cls.definitions = json.loads(DEFINITIONS.read_text(encoding="utf-8"))
        cls.mentions = [
            (component, path, text)
            for component, path, text in metadata_strings(cls.metadata)
            if DEFAULT_WORD.search(text)
        ]

    def test_the_file_is_read(self) -> None:
        self.assertGreaterEqual(len(metadata_strings(self.metadata)), 100)
        self.assertGreaterEqual(len(self.mentions), 3, "no metadata string uses the word 'default'?")

    def test_every_string_that_says_default_has_been_read(self) -> None:
        read = set(STATES_A_DEFAULT) | set(NOT_A_DEFAULT)
        unread = [f"{path}: {text}" for component, path, text in self.mentions if (component, text) not in read]
        self.assertEqual(unread, [], "classify each in STATES_A_DEFAULT or NOT_A_DEFAULT")

    def test_no_row_names_a_string_that_is_gone(self) -> None:
        present = {(component, text) for component, _, text in self.mentions}
        self.assertEqual(set(STATES_A_DEFAULT) & set(NOT_A_DEFAULT), set())
        gone = [f"{c}: {t}" for (c, t) in list(STATES_A_DEFAULT) + list(NOT_A_DEFAULT) if (c, t) not in present]
        self.assertEqual(gone, [], "the metadata no longer holds these strings; read the file again")

    def test_a_stated_default_is_the_declared_default(self) -> None:
        problems = [
            p
            for (component, text), attributes in STATES_A_DEFAULT.items()
            for p in disagreements(self.definitions, component, attributes, text)
        ]
        self.assertEqual(problems, [])

    def test_the_check_tells_the_three_found_on_2026_09_26_from_the_declaration(self) -> None:
        """Controls: the text before this change, each red for its reason."""
        slider = disagreements(self.definitions, "Slider", ["minimum", "maximum"],
                               "minimumValue/maximumValue define range (default 0-100)")
        self.assertEqual([p.split(" declares")[0] for p in slider], ["Slider.maximum"], slider)

        lazy = disagreements(self.definitions, "Collection", ["lazy"],
                             "lazy (default true) controls virtualization: true uses LazyVStack/LazyColumn/"
                             "LazyVerticalGrid with internal scroll; false renders eagerly")
        self.assertEqual(len(lazy), 1, lazy)
        self.assertIn("declares default 'lazy'", lazy[0])

        content_mode = disagreements(self.definitions, "NetworkImage", ["contentMode"],
                                     "Default contentMode is .center for matchParent (Swift)")
        self.assertEqual(content_mode, ["NetworkImage.contentMode declares no default, and the text states one"])

        # and a text that names the value and not the attribute
        unnamed = disagreements(self.definitions, "Slider", ["maximum"], "the range defaults to 0 .. 1")
        self.assertEqual(len(unnamed), 1, unnamed)
        self.assertIn("does not name it", unnamed[0])


if __name__ == "__main__":
    unittest.main()
