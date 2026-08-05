"""The spec validation in `jui g project` must actually be reachable in CI.

`_cmd_generate_project` validates every spec, but only when
`document_tools` imports. That made the check silently optional: with the
install step ordered after the suite, CI ran the whole job with the
validation branch dead, and a test whose fixture specs were invalid passed
for a month because nothing looked at them. Moving one line in `ci.yml`
puts it back exactly as quietly.

Two tests, and the pairing is the point:

  * the wiring test reads `ci.yml` and fails if the install is reordered
    after the suite. It needs nothing installed, so it means the same
    thing on every machine.
  * the behaviour test proves validation actually rejects a bad spec. It
    can only run where `document_tools` is importable, so on its own a
    skip could hide a CI that stopped installing it — which is what the
    wiring test rules out.

Neither alone is enough. A plain "document_tools must import" assertion
was the other option and was rejected: it fails on any checkout where the
package is not installed, which is the normal local state, and a test that
is red for everyone teaches people to ignore it.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"

HAVE_DOCUMENT_TOOLS = importlib.util.find_spec("document_tools") is not None


@unittest.skipUnless(CI_WORKFLOW.is_file(), f"not a repo checkout ({CI_WORKFLOW})")
class CiWiringTest(unittest.TestCase):
    def test_document_tools_installs_before_the_jui_tools_suite(self):
        lines = CI_WORKFLOW.read_text(encoding="utf-8").splitlines()

        def index_of(step: str) -> int:
            hits = [i for i, line in enumerate(lines) if line.strip() == f"- name: {step}"]
            self.assertEqual(len(hits), 1, f"expected exactly one '{step}' step: {hits}")
            return hits[0]

        install = index_of("Install document_tools (dev)")
        suite = index_of("Run unit tests")
        self.assertLess(
            install,
            suite,
            "ci.yml runs the jui_tools suite before document_tools is installed, so "
            "`jui g project`'s spec validation cannot run there — the suite would go "
            "green on specs nothing validated",
        )

    def test_test_tools_installs_before_document_tools(self):
        """jsonui_doc_cli imports its validator from jsonui_test_cli."""
        lines = CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
        order = [
            i
            for i, line in enumerate(lines)
            if line.strip()
            in ("- name: Install test_tools (dev)", "- name: Install document_tools (dev)")
        ]
        self.assertEqual(len(order), 2)
        self.assertEqual(
            [lines[i].strip() for i in order],
            ["- name: Install test_tools (dev)", "- name: Install document_tools (dev)"],
        )


@unittest.skipUnless(HAVE_DOCUMENT_TOOLS, "document_tools not importable here")
class SpecValidationRejectsBadSpecsTest(unittest.TestCase):
    """Where the validator is present, a bad spec must stop the command.

    Guards the other half: the wiring can be right while the validation
    itself has been reduced to a warning, and the suite would not notice.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "jui.config.json").write_text(
            json.dumps(
                {
                    "spec_directory": "docs/screens/json",
                    "layouts_directory": "docs/screens/layouts",
                    "platforms": {"ios": {"root": "ios", "layoutsDir": "Layouts"}},
                }
            )
        )
        spec_dir = self.root / "docs/screens/json"
        spec_dir.mkdir(parents=True)
        (self.root / "docs/screens/layouts").mkdir(parents=True)
        # Missing version / description / layout — the shape that used to
        # sail through because nothing was checking.
        (spec_dir / "home.spec.json").write_text(
            json.dumps(
                {
                    "type": "screen_spec",
                    "metadata": {"name": "Home", "displayName": "Home"},
                    "structure": {"components": []},
                    "dataFlow": {"repositories": [], "viewModel": {"methods": [], "vars": []}},
                    "stateManagement": {"uiVariables": []},
                }
            )
        )
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_invalid_spec_is_a_non_zero_exit(self):
        from jui_cli.commands.generate_cmd import _cmd_generate_project

        args = argparse.Namespace(
            file=None,
            force=False,
            skip_layout=True,
            dry_run=False,
            ios_only=True,
            android_only=False,
            web_only=False,
            type_map=None,
        )
        self.assertEqual(
            _cmd_generate_project(args),
            1,
            "an invalid spec generated anyway — the validation branch is not "
            "stopping the command",
        )


if __name__ == "__main__":
    unittest.main()
