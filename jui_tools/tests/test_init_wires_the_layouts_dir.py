"""`jui init` writes `layoutsDir`, so the build has somewhere to distribute.

A project made by `jui init` declared only `root`. Eight places read
`layoutsDir`, and most of them `continue` without a word when it is
missing — layout distribution, styles, resources, images, hotload config,
the lint collection, and the count behind the manifest's `(N distributed)`
clause. So the four distribution steps did nothing, editing a shared
resource never reached the platform, and the only visible sign was a
clause going missing from a line, which reads the same as "distributed
nothing" and as "could not count".

Measured on such a project: writing colours into the shared
`Resources/colors.json` left the platform copy byte-identical, with
nothing printed either way.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.core.config_manager import DEFAULT_LAYOUTS_DIR


class InitLayoutsDirTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._cwd = Path.cwd()

    def tearDown(self):
        import os

        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _init(self, **platforms) -> dict:
        import argparse
        import os

        from jui_cli.commands.init_cmd import cmd_init

        os.chdir(self.root)
        fields = dict(project_name="P", ios=None, android=None, web=None,
                      ios_mode="swiftui", android_mode="compose",
                      package_name=None, no_sync_tools=True)
        fields.update(platforms)
        args = argparse.Namespace(**fields)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_init(args)
        return json.loads((self.root / "jui.config.json").read_text())

    def test_every_platform_gets_a_layouts_dir(self):
        config = self._init(ios="./ios", android="./android", web="./web")
        for name, expected in DEFAULT_LAYOUTS_DIR.items():
            with self.subTest(platform=name):
                self.assertEqual(
                    expected, config["platforms"][name].get("layoutsDir"),
                    "a platform without layoutsDir has every distribution "
                    "step skip it silently",
                )

    def test_a_single_platform_project_gets_one_too(self):
        config = self._init(web="./web")
        self.assertEqual(DEFAULT_LAYOUTS_DIR["web"],
                         config["platforms"]["web"]["layoutsDir"])

    def test_migrate_guesses_from_the_same_map(self):
        # Two lists is how they drifted: init wrote none and migrate
        # carried its own candidates, so a project could be migrated FROM a
        # directory the build would never distribute TO.
        import inspect

        from jui_cli.commands import migrate_cmd

        source = inspect.getsource(migrate_cmd.cmd_migrate_layouts)
        self.assertIn("DEFAULT_LAYOUTS_DIR", source)
        self.assertNotIn("app/src/main/assets/Layouts", source)


if __name__ == "__main__":
    unittest.main()
