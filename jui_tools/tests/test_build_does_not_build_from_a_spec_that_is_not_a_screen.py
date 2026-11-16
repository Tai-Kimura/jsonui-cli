"""`jui build` loads only the specs that describe a screen.

`_load_all_specs` skipped files referenced as sub-specs and nothing else, so
1.8.52's `app_contracts_spec` — a container for unit targets no single screen
owns — was loaded as a screen. `extract_screen_spec` then took its
`metadata.name`, which for that type is the APP's display name, as a screen
name, and protocol sync wrote a file per platform:

    protocol acme-store checkoutViewModelProtocol: ObservableObject

A hyphen and a space in an identifier: invalid Swift and invalid Kotlin, under
an @generated header, on both platforms. `jui build` printed "Protocol sync:
updated 2 protocol(s)" and exited 0 with no warning, and both consumer trees
compile those directories unconditionally — iOS via
fileSystemSynchronizedGroups, Android because `app/src/main/kotlin/` is a
source root — so the next build after a green `jui build` failed.

⚠️ Reported by a consumer face as the SAME root as the `jui verify` defect,
after that one had already been fixed here. One missing piece of knowledge
reached by two paths, and fixing the path that was reported would have left
the heavier one: verify green, build broken. That is why the table lives in
`shared/core/spec_types.py` and neither caller restates it.

The name below is a neutral stand-in that keeps the SHAPE that matters — a
hyphen and a space inside a value that becomes an identifier. The reported
name had exactly that shape; it is not reproduced here because consumer
vocabulary does not belong in this repository. A tidier fixture (`AppName`)
would still have proved the skip and would not have shown what the skip
prevents, so the shape is the part that had to survive.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.commands import build_cmd  # noqa: E402


class _Config:
    def __init__(self, spec_dir: Path):
        self.spec_directory = spec_dir


def _screen(name: str) -> dict:
    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": name, "displayName": name, "description": "d"},
        "structure": {"components": [], "layout": {}},
    }


class LoadAllSpecsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.spec_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name: str, data: dict):
        (self.spec_dir / name).write_text(json.dumps(data), encoding="utf-8")

    def _load(self):
        return build_cmd._load_all_specs(_Config(self.spec_dir))

    def test_a_screen_spec_is_loaded(self):
        # The arm that keeps the fix from being "skip everything".
        self._write("home.spec.json", _screen("Home"))
        self.assertEqual(1, len(self._load()))

    def test_an_app_contracts_spec_is_not_loaded_as_a_screen(self):
        # The reported defect, with the reported name.
        self._write("home.spec.json", _screen("Home"))
        self._write("app_contracts.spec.json", {
            "type": "app_contracts_spec",
            "version": "1.0",
            "metadata": {"name": "acme-store checkout",
                         "description": "app-owned unit targets"},
            "unitContracts": [],
        })
        loaded = self._load()
        self.assertEqual(1, len(loaded), [p.name for p, _ in loaded])
        self.assertEqual("home.spec.json", loaded[0][0].name)

    def test_the_app_name_never_reaches_a_generated_identifier(self):
        # Stated against the symptom rather than the mechanism: whatever the
        # loader does, this string must not come back, because everything
        # downstream builds identifiers out of what it returns.
        self._write("app_contracts.spec.json", {
            "type": "app_contracts_spec",
            "version": "1.0",
            "metadata": {"name": "acme-store checkout",
                         "description": "d"},
            "unitContracts": [],
        })
        for _, spec in self._load():
            self.assertNotIn("acme-store checkout", str(getattr(spec, "name", "")))
        self.assertEqual([], self._load())

    def test_an_unknown_type_is_skipped_and_announced(self):
        # Skipped AND said. Silence here would make a run that declined to
        # build something differ from a clean run only in what is absent.
        self._write("gizmo.spec.json", {
            "type": "some_future_spec",
            "version": "1.0",
            "metadata": {"name": "Gizmo", "description": "d"},
        })
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            loaded = self._load()
        self.assertEqual([], loaded)
        out = buf.getvalue()
        self.assertIn("gizmo.spec.json", out)
        self.assertIn("some_future_spec", out)

    def test_a_sub_spec_referenced_by_a_parent_is_still_skipped(self):
        # The behaviour that was already there stays there.
        self._write("parent.spec.json", {
            "type": "screen_parent_spec",
            "version": "1.0",
            "metadata": {"name": "Parent", "displayName": "Parent",
                         "description": "d"},
            "structure": {"components": [], "layout": {}},
            "subSpecs": [{"file": "parent-part.spec.json"}],
        })
        self._write("parent-part.spec.json", {
            "type": "screen_sub_spec",
            "version": "1.0",
            "metadata": {"name": "Part", "displayName": "Part",
                         "description": "d"},
            "structure": {"components": [], "layout": {}},
        })
        loaded = self._load()
        self.assertEqual(["parent.spec.json"], [p.name for p, _ in loaded])
