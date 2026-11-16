"""Regression: doc-pregenerate-component-validation-ignores-custom-rules.

The HTML/MD doc generators validate many spec/component files in one run.
Reusing a single SpecValidator freezes its custom rules to whatever the
FIRST validated file resolved (SpecValidator only auto-discovers
`.jsonui-doc-rules.json` while its rules are still empty). A later file
whose nearest config differs from the first one's was then validated against
the wrong rule set, falsely SKIPping custom component types that the
standalone `validate` path (per-file discovery) accepts.

`_validator_for(file)` must build a fresh validator from each file's own
nearest rules so per-file discovery is restored.
"""
from __future__ import annotations

import io
import json
import contextlib
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import _validator_for, _pre_generate_spec_docs


def _component_spec():
    return {
        "type": "component_spec",
        "version": "1.0",
        "metadata": {
            "name": "ScannerCamera",
            "displayName": "Scanner",
            "description": "scans",
        },
        "structure": {
            "components": [
                {"type": "ScannerCamera", "id": "scanner_camera", "description": "cam"}
            ],
            "layout": {"root": "scanner_camera", "children": []},
        },
    }


def _rules(component_types):
    return {"rules": {"componentTypes": {"component": list(component_types)}}}


class ValidatorForCustomRulesTests(unittest.TestCase):
    def test_validator_for_loads_whitelisted_custom_component_type(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".jsonui-doc-rules.json").write_text(json.dumps(_rules(["ScannerCamera"])))
            cdir = root / "docs" / "components" / "json"
            cdir.mkdir(parents=True)
            cf = cdir / "scannercamera.component.json"
            cf.write_text(json.dumps(_component_spec()))

            result = _validator_for(cf).validate_file(cf)
            self.assertTrue(
                result.is_valid,
                msg=f"unexpected errors: {[m.message for m in result.errors]}",
            )

    def test_each_file_uses_its_own_nearest_rules_no_reuse_freeze(self):
        # A nearer config on the SCREEN path omits the custom type; the
        # component (under a different subtree whose nearest config is the
        # root, which whitelists it) must NOT inherit the screen's frozen
        # rules. With per-file loading the component validates clean.
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".jsonui-doc-rules.json").write_text(json.dumps(_rules(["ScannerCamera"])))
            sdir = root / "docs" / "screens" / "json"
            sdir.mkdir(parents=True)
            # Nearer config for screens that does NOT whitelist the type.
            (sdir / ".jsonui-doc-rules.json").write_text(json.dumps(_rules([])))
            cdir = root / "docs" / "components" / "json"
            cdir.mkdir(parents=True)
            cf = cdir / "scannercamera.component.json"
            cf.write_text(json.dumps(_component_spec()))

            # The component's nearest config is the root (whitelisted).
            comp_rules = _validator_for(cf)._custom_rules
            self.assertIn("ScannerCamera", comp_rules.extra_component_types)
            self.assertTrue(_validator_for(cf).validate_file(cf).is_valid)

    def test_pre_generate_does_not_skip_whitelisted_custom_component(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".jsonui-doc-rules.json").write_text(json.dumps(_rules(["ScannerCamera"])))
            docs = root / "docs"
            cdir = docs / "components" / "json"
            cdir.mkdir(parents=True)
            (cdir / "scannercamera.component.json").write_text(json.dumps(_component_spec()))

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                _pre_generate_spec_docs(docs)
            out = buf.getvalue()
            self.assertIn("OK: scannercamera.component.json", out)
            self.assertNotIn("SKIP: scannercamera.component.json", out)


if __name__ == "__main__":
    unittest.main()
