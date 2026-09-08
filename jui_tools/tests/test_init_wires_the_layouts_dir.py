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
import os
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


class TestMigrateIsActuallyDriven(unittest.TestCase):
    """🚨 THE ARM ABOVE READS SOURCE. THIS ONE RUNS THE COMMAND.

    Reported 2026-09-09 by a support lane that instrumented the jui_tools
    suite with `sys.settrace` and counted, per command module, how many arms
    actually EXECUTE it:

        build_cmd.py     121 arms
        verify_cmd.py     52 arms
        migrate_cmd.py     1 arm   <- and that one is the source-reading
                                     arm in this very class

    ⚠️ A static search for the subcommand name does not answer this: arms
    import the module and call the function, so the literal never appears.
    The same lane measured `build` as 1 statically against 121 at runtime.

    ⚠️ The runtime number is a LOWER BOUND (settrace does not follow child
    processes). For the child-process route the bound is tight, though: a
    CLI driven by subprocess must spell the subcommand, and of the 8 arms in
    `jui_tools/tests` that actually spawn one, `migrate` appears in 0.

    📌 This is the reachability rung again. A source arm pins spelling,
    shape and order; it cannot see whether control reaches the code. Only
    driving the command can. `build` and `verify` do not need this treatment
    — their substitutes are thick. The tier an arm must survive depends on
    what the arm claims, not on a blanket rule.
    """

    def _project(self, root, dest="layouts"):
        """The shape the guess actually looks for.

        ⚠️ Read out of `DEFAULT_LAYOUTS_DIR` rather than assumed: the map
        says android -> `app/src/main/assets/Layouts`, and the command joins
        it onto the platform's `root`. A first draft set `root` to `"app"`
        and looked for `app/app/src/main/...`, which failed with "Cannot
        find Layouts directory" — a fixture that did not match the shape the
        implementation resolves.
        """
        from jui_cli.core.config_manager import DEFAULT_LAYOUTS_DIR

        (root / dest).mkdir(parents=True, exist_ok=True)
        src = root / DEFAULT_LAYOUTS_DIR["android"]
        (src / "nested").mkdir(parents=True, exist_ok=True)
        (src / "home.json").write_text('{"type":"View"}', encoding="utf-8")
        (src / "nested" / "detail.json").write_text('{"type":"View"}',
                                                    encoding="utf-8")
        (root / "jui.config.json").write_text(json.dumps({
            "project_name": "P",
            "layouts_directory": dest,
            "platforms": {"android": {"root": "."}},
        }), encoding="utf-8")
        return root

    def _run(self, root, dry_run):
        import argparse
        import io
        import contextlib

        from jui_cli.commands import migrate_cmd

        cwd = os.getcwd()
        os.chdir(root)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = migrate_cmd.cmd_migrate_layouts(argparse.Namespace(
                    source_platform="android", dry_run=dry_run))
            return rc, out.getvalue()
        finally:
            os.chdir(cwd)

    def test_it_copies_and_says_how_many(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._project(Path(d))

            rc, out = self._run(root, dry_run=False)

            self.assertEqual(rc, 0, out)
            self.assertIn("Copied 2 file(s)", out)
            self.assertTrue((root / "layouts" / "home.json").is_file())
            self.assertTrue((root / "layouts" / "nested" / "detail.json").is_file(),
                            "nested layouts were not carried over")

    def test_dry_run_writes_nothing(self):
        """⚠️ The control that makes the arm above mean something: without
        it, a `--dry-run` that copied anyway would pass every assertion the
        copying arm makes."""
        with tempfile.TemporaryDirectory() as d:
            root = self._project(Path(d))

            rc, out = self._run(root, dry_run=True)

            self.assertEqual(rc, 0, out)
            self.assertIn("[DRY-RUN]", out)
            self.assertIn("Would copy 2 file(s)", out)
            self.assertFalse((root / "layouts" / "home.json").exists())

    def test_the_guessed_directory_is_the_one_init_writes(self):
        """The claim the source-reading arm makes, driven instead of read.

        The fixture puts layouts at `app/src/main/assets/Layouts` and
        declares NO `layoutsDir`, so a run that finds them proves the guess
        used the shared map rather than a private list.
        """
        with tempfile.TemporaryDirectory() as d:
            root = self._project(Path(d))
            cfg = json.loads((root / "jui.config.json").read_text())
            self.assertNotIn("layoutsDir", cfg["platforms"]["android"])

            rc, out = self._run(root, dry_run=True)

            self.assertEqual(rc, 0, out)
            self.assertIn("Would copy 2 file(s)", out)

    def test_it_takes_this_platforms_convention_over_another_platforms(self):
        """🚨 THE ORDERING DEFECT, ARMED SEPARATELY BECAUSE THE GUARD HIDES IT.

        The loop walked `DEFAULT_LAYOUTS_DIR.values()` in dict order, so
        iOS's bare `Layouts` came first for EVERY platform. After the
        destination guard was added, a mutation that restored the old order
        went GREEN in every fixture here — the guard skipped `Layouts`
        (it was the destination) and the android directory was reached
        anyway. One fix had absorbed the other's symptom.

        ⚠️ So this fixture gives the project a REAL iOS `Layouts` directory
        that is NOT the destination and holds different files. With the
        wrong order, migrating android takes the iOS layouts — a silent
        success that copies the wrong screens.

        📌 Fixing the defect that hides another makes the hidden one look
        like a fresh regression. Both need their own arm, and the arm has to
        reach past the fix that masks it.
        """
        from jui_cli.core.config_manager import DEFAULT_LAYOUTS_DIR

        with tempfile.TemporaryDirectory() as d:
            # ⚠️ The destination is NOT called `layouts` here. On a
            # case-insensitive filesystem `Layouts` and `layouts` are ONE
            # directory, so with the usual fixture the iOS convention cannot
            # be made to exist separately at all — `mkdir` raises
            # FileExistsError. Measured, not assumed: the first draft of this
            # arm did exactly that. The ordering defect is only observable
            # when the two names denote two directories.
            root = self._project(Path(d), dest="dest")
            ios = root / DEFAULT_LAYOUTS_DIR["ios"]
            ios.mkdir()
            (ios / "ios_only.json").write_text('{"type":"View"}', encoding="utf-8")
            self.assertFalse(os.path.samefile(ios, root / "dest"),
                             "fixture broken: the iOS dir IS the destination")

            rc, out = self._run(root, dry_run=False)

            self.assertEqual(rc, 0, out)
            self.assertTrue((root / "dest" / "home.json").is_file(),
                            "android layouts were not the source: " + out)
            self.assertFalse((root / "dest" / "ios_only.json").exists(),
                             "migrated the iOS directory for --source-platform "
                             "android: " + out)

    def test_it_refuses_to_migrate_the_destination_onto_itself(self):
        """🚨 THE CASE-FOLDING TRAP, ARMED SEPARATELY BECAUSE THE ORDER FIX
        HIDES IT.

        A mutation that removed the destination guard left this file GREEN:
        with the platform's own convention tried first, the android fixture
        never reaches the guard at all. The guard needs a project where the
        platform's own directory is ABSENT and another candidate folds onto
        the destination.

        iOS's convention is the bare `Layouts`. A project whose
        `layouts_directory` is `layouts` makes `root / "Layouts"` exist on a
        case-insensitive filesystem, so without the guard the command takes
        its own destination as the source and reports "Copied 0 file(s)"
        with exit 0 — silent, successful and wrong.

        ⚠️ On a case-sensitive filesystem the two names are different
        directories and this arm passes for a different reason: the
        destination is simply not a candidate. That is fine — the arm asserts
        the OUTCOME (a refusal, not a zero-file success), which is correct on
        both kinds of filesystem.
        """
        import argparse
        import io
        import contextlib

        from jui_cli.commands import migrate_cmd

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "layouts").mkdir()
            (root / "jui.config.json").write_text(json.dumps({
                "project_name": "P",
                "layouts_directory": "layouts",
                "platforms": {"ios": {"root": "."}},
            }), encoding="utf-8")

            cwd = os.getcwd()
            os.chdir(root)
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = migrate_cmd.cmd_migrate_layouts(argparse.Namespace(
                        source_platform="ios", dry_run=False))
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 1, out.getvalue())
            self.assertIn("Cannot find Layouts directory", out.getvalue())
            self.assertNotIn("Copied 0 file(s)", out.getvalue())

    def test_it_refuses_a_platform_the_config_does_not_declare(self):
        import argparse
        import io
        import contextlib

        from jui_cli.commands import migrate_cmd

        with tempfile.TemporaryDirectory() as d:
            root = self._project(Path(d))
            cwd = os.getcwd()
            os.chdir(root)
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = migrate_cmd.cmd_migrate_layouts(argparse.Namespace(
                        source_platform="ios", dry_run=True))
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 1)
            self.assertIn("not found in config", out.getvalue())


if __name__ == "__main__":
    unittest.main()
