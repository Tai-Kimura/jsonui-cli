"""Pytest configuration for the jsonui-test CLI test suite.

`test_cli.py` and `test_generator.py` were written against a previous CLI shape
(a monolithic `cmd_generate` and a `jsonui_test_cli.generator` module) that no
longer exists — generation was split into `generate test screen|flow` /
`generate description` and doc-generation moved out to `jsonui-doc`. They fail at
import/collection and block the whole suite. Ignore them at collection so the
still-valid suites (validation, report, mock) run. Remove or rewrite these two
files to the current API when generation gets test coverage again.
"""

collect_ignore = [
    "test_cli.py",
    "test_generator.py",
]
