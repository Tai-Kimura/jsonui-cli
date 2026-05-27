"""Tests for openapi_naming helpers."""
from __future__ import annotations

import unittest

from jui_cli.core.openapi_naming import (
    escape_keyword,
    factory_name,
    snake_to_camel,
    snake_to_pascal,
)


class CaseConversionTests(unittest.TestCase):
    def test_snake_to_pascal(self):
        self.assertEqual(snake_to_pascal("display_name"), "DisplayName")
        self.assertEqual(snake_to_pascal("user-id"), "UserId")
        self.assertEqual(snake_to_pascal("displayName"), "DisplayName")
        self.assertEqual(snake_to_pascal("HTTPResponse"), "HTTPResponse")
        self.assertEqual(snake_to_pascal(""), "")

    def test_snake_to_camel(self):
        self.assertEqual(snake_to_camel("display_name"), "displayName")
        self.assertEqual(snake_to_camel("user-id"), "userId")
        self.assertEqual(snake_to_camel("displayName"), "displayName")

    def test_snake_to_camel_leading_caps_acronym(self):
        """Plan §2.2: ``HTTPResponse`` → ``httpResponse`` (only first letter down)."""
        self.assertEqual(snake_to_camel("HTTPResponse"), "hTTPResponse")
        # The factory_name path applies the rule more carefully.


class FactoryNameTests(unittest.TestCase):
    def test_simple_pascal(self):
        self.assertEqual(factory_name("User"), "userFromDto")

    def test_multi_word_pascal(self):
        self.assertEqual(factory_name("OrderItem"), "orderItemFromDto")
        self.assertEqual(factory_name("UserProfile"), "userProfileFromDto")

    def test_leading_acronym_only_first_lower(self):
        """``HTTPResponse`` → ``hTTPResponseFromDto``.

        Per plan §2.2, only the first letter is down-cased. (We previously
        considered down-casing the entire acronym, but the rule there is
        "最初の 1 字のみ lower 化" — let's verify the implementation matches.)
        """
        self.assertEqual(factory_name("HTTPResponse"), "hTTPResponseFromDto")


class EscapeKeywordTests(unittest.TestCase):
    def test_swift_keyword_backticked(self):
        self.assertEqual(escape_keyword("class", language="swift"), "`class`")
        self.assertEqual(escape_keyword("private", language="swift"), "`private`")
        self.assertEqual(escape_keyword("var", language="swift"), "`var`")

    def test_swift_non_keyword_passthrough(self):
        self.assertEqual(escape_keyword("displayName", language="swift"), "displayName")
        self.assertEqual(escape_keyword("user", language="swift"), "user")

    def test_kotlin_keyword_backticked(self):
        self.assertEqual(escape_keyword("class", language="kotlin"), "`class`")
        self.assertEqual(escape_keyword("when", language="kotlin"), "`when`")

    def test_already_escaped_idempotent(self):
        self.assertEqual(escape_keyword("`class`", language="swift"), "`class`")

    def test_unknown_language_passthrough(self):
        self.assertEqual(escape_keyword("class", language="rust"), "class")


if __name__ == "__main__":
    unittest.main()
