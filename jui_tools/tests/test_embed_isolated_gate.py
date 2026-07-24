"""Tests for build_cmd._check_isolated_embed_constraints — the hard gate
that rejects present-type transitions in screens hosted inside an
``navigationMode:"isolated"`` Embed (04 embed-isolated track).

- delegate embeds never trip the gate, whatever the spec declares
- isolated embeds pass when the embedded spec has no present-type entries
- isolated embeds fail on sheet/modal/dialog/dismiss-style transitions,
  matched defensively across the free-form transition dict keys
- screens without a spec are skipped (layout-only screens)
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.build_cmd import _check_isolated_embed_constraints
from jui_cli.core.config_manager import ConfigManager


def _write_project(
    root: Path,
    *,
    navigation_mode: str = "isolated",
    transitions: list | None = None,
    with_spec: bool = True,
) -> None:
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts",
        "platforms": {},
    }, indent=2))

    layouts = root / "docs/screens/layouts"
    layouts.mkdir(parents=True)
    (layouts / "host.json").write_text(json.dumps({
        "type": "View",
        "id": "host_root",
        "child": [{
            "type": "Embed",
            "id": "pane",
            "screen": "order_detail",
            "navigationMode": navigation_mode,
        }],
    }))
    (layouts / "order_detail.json").write_text(json.dumps({
        "type": "View", "id": "order_detail_root",
    }))

    if with_spec:
        spec_dir = root / "docs/screens/json"
        spec_dir.mkdir(parents=True)
        (spec_dir / "order_detail.spec.json").write_text(json.dumps({
            "type": "screen_spec",
            "metadata": {"name": "OrderDetail", "displayName": "Order Detail"},
            "structure": {"components": []},
            "dataFlow": {"viewModel": {}},
            "transitions": transitions or [],
        }, indent=2))


def _run_gate(root: Path) -> bool:
    old = os.getcwd()
    os.chdir(root)
    try:
        return _check_isolated_embed_constraints(ConfigManager())
    finally:
        os.chdir(old)


class EmbedIsolatedGateTest(unittest.TestCase):
    def _with_project(self, **kwargs) -> bool:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_project(root, **kwargs)
            return _run_gate(root)

    def test_isolated_without_present_transitions_passes(self):
        self.assertTrue(self._with_project(
            transitions=[{"type": "push", "to": "OrderHistory"}],
        ))

    def test_isolated_with_sheet_transition_fails(self):
        self.assertFalse(self._with_project(
            transitions=[{"type": "present", "style": "sheet", "to": "Filter"}],
        ))

    def test_isolated_with_modal_style_fails(self):
        self.assertFalse(self._with_project(
            transitions=[{"style": "modal", "to": "Filter"}],
        ))

    def test_isolated_with_dismiss_action_fails(self):
        self.assertFalse(self._with_project(
            transitions=[{"action": "dismiss"}],
        ))

    def test_delegate_embed_never_trips_the_gate(self):
        self.assertTrue(self._with_project(
            navigation_mode="delegate",
            transitions=[{"type": "present", "style": "sheet", "to": "Filter"}],
        ))

    def test_layout_only_screen_without_spec_is_skipped(self):
        self.assertTrue(self._with_project(with_spec=False))


if __name__ == "__main__":
    unittest.main()
