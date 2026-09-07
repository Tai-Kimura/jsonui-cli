"""`jui build` syncs UseCase protocols, not only ViewModel protocols.

Reported 2026-09-07 by a consumer: a method added to
`dataFlow.useCases[].methods` reached no generated file. `jui build` synced
the ViewModel protocols and stopped there, and `jui g project` — the only
command that writes a UseCase protocol — REFUSES to overwrite an existing
one, so the declaration never arrived at all.

The failure is asymmetric, which is what made it survive: Android could not
compile (`overrides nothing`), while iOS accepted an implementation of a
method its protocol does not declare. One spec edit, one face broken.
"""

import json
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent))

from jui_cli.commands.build_cmd import _sync_usecase_protocols  # noqa: E402
from jui_cli.core.config_manager import ConfigManager  # noqa: E402

USE_CASE = {
    "name": "SettingsUseCase",
    "methods": [
        {"name": "loadSettings", "params": [], "returnType": "Settings"},
    ],
}


def _project(root: Path, use_case: dict) -> ConfigManager:
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts",
        "platforms": {
            "ios": {"root": "ios", "layoutsDir": "Layouts"},
            "android": {"root": "android", "layoutsDir": "app/src/main/assets/Layouts"},
            "web": {"root": "web", "layoutsDir": "src/Layouts"},
        },
    }), encoding="utf-8")
    spec_dir = root / "docs/screens/json"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "settings.spec.json").write_text(json.dumps({
        "type": "screen_spec",
        "metadata": {"name": "Settings", "displayName": "Settings"},
        "structure": {"components": []},
        "dataFlow": {"viewModel": {}, "useCases": [use_case]},
    }), encoding="utf-8")
    return ConfigManager(root / "jui.config.json")


def _run(mgr: ConfigManager) -> bool:
    config = mgr.load()
    return _sync_usecase_protocols(
        mgr, config, config.get("platforms", {}), Namespace(dry_run=False))


def _protocols(root: Path) -> dict[str, Path]:
    return {p.suffix.lstrip("."): p
            for p in root.rglob("SettingsUseCaseProtocol.*")}


def _scaffold(mgr: ConfigManager, root: Path) -> None:
    """Write the protocol files the way `jui g project` would.

    The build SYNCS; it does not create. So every case here starts from a
    scaffolded project, which is also the state the report describes: the
    protocol exists and the spec grew past it.
    """
    from jui_cli.commands.build_cmd import _platform_generator
    from jui_cli.core.type_mapper import TypeMapper
    from jui_cli.core.spec_extractor import UseCaseDef
    tm = TypeMapper(mgr.type_map_file)
    empty = UseCaseDef(name="SettingsUseCase", methods=[])
    # Built through the SAME factory the sync uses. Assembling generators
    # here by hand is what hid a real defect: the scaffold and the sync each
    # rooted at the project instead of at the platform, agreed with each
    # other, and disagreed with every real project. A fixture that computes
    # its own paths tests the fixture.
    for platform in ("ios", "android", "web"):
        pconf = mgr.load()["platforms"][platform]
        gen = _platform_generator(root, platform, pconf, tm)
        if gen is None or not getattr(gen, "has_separate_protocol", True):
            continue
        path = gen.usecase_protocol_path("SettingsUseCase")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(gen.generate_usecase_protocol("SettingsUseCase", empty),
                        encoding="utf-8")


class UseCaseProtocolSync(unittest.TestCase):
    def test_a_declared_method_reaches_every_platforms_protocol(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, USE_CASE)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            written = _protocols(root)
            self.assertTrue(written, "no UseCase protocol was written at all")
            for ext, path in written.items():
                body = path.read_text(encoding="utf-8")
                self.assertIn("loadSettings", body, ext)
                # Asserted on the banner too: the file has to be recognisable
                # as generated, or the next run will refuse to touch it.
                self.assertIn("@generated", body, ext)

    def test_a_method_added_later_arrives(self):
        """The reported shape: the protocol exists, then the spec grows."""
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, USE_CASE)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            before = {e: p.read_text(encoding="utf-8") for e, p in _protocols(root).items()}
            self.assertTrue(before)
            for body in before.values():
                self.assertNotIn("verifyEmailChange", body)

            grown = json.loads(json.dumps(USE_CASE))
            grown["methods"].append(
                {"name": "verifyEmailChange", "params": [], "returnType": "Bool"})
            self.assertTrue(_run(_project(root, grown)))

            for ext, path in _protocols(root).items():
                self.assertIn("verifyEmailChange",
                              path.read_text(encoding="utf-8"), ext)

    def test_a_method_removed_from_the_spec_disappears(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            two = json.loads(json.dumps(USE_CASE))
            two["methods"].append(
                {"name": "verifyEmailChange", "params": [], "returnType": "Bool"})
            mgr = _project(root, two)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            self.assertTrue(_run(_project(root, USE_CASE)))
            for ext, path in _protocols(root).items():
                body = path.read_text(encoding="utf-8")
                self.assertIn("loadSettings", body, ext)
                self.assertNotIn("verifyEmailChange", body, ext)

    def test_platforms_on_a_method_are_honoured(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            scoped = json.loads(json.dumps(USE_CASE))
            scoped["methods"].append({
                "name": "androidOnlyCall", "params": [], "returnType": "Bool",
                "platforms": ["android"],
            })
            mgr = _project(root, scoped)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            for ext, path in _protocols(root).items():
                body = path.read_text(encoding="utf-8")
                if ext == "kt":
                    self.assertIn("androidOnlyCall", body)
                else:
                    self.assertNotIn("androidOnlyCall", body, ext)

    def test_a_file_without_the_banner_is_left_alone(self):
        """Ownership is checked, not assumed.

        `jui g project` warns rather than overwrites when a protocol has
        drifted, so a consumer may be holding a hand-edited file here.
        Overwriting it silently is worse than the defect being fixed.
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, USE_CASE)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            target = next(iter(_protocols(root).values()))
            target.write_text("// hand written, no banner\n", encoding="utf-8")

            grown = json.loads(json.dumps(USE_CASE))
            grown["methods"].append(
                {"name": "verifyEmailChange", "params": [], "returnType": "Bool"})
            self.assertTrue(_run(_project(root, grown)))

            self.assertEqual("// hand written, no banner\n",
                             target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class WiredIntoTheBuild(unittest.TestCase):
    """The sync has to be CALLED, not merely correct.

    Every case above drives `_sync_usecase_protocols` directly, so deleting
    its call site in `cmd_build` leaves them all green — measured: 5 passed
    with the wiring removed. The function being right says nothing about the
    build running it, which is the whole defect one level up.
    """

    def test_cmd_build_calls_the_usecase_sync(self):
        import ast
        import inspect
        from jui_cli.commands import build_cmd

        tree = ast.parse(inspect.getsource(build_cmd.cmd_build))
        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("_sync_usecase_protocols", called)
        # Its sibling, so a refactor that drops one and keeps the other is
        # visible here rather than in a consumer's compile error.
        self.assertIn("_sync_viewmodel_protocols", called)


class NeverCreatesAProtocol(unittest.TestCase):
    """`jui build` syncs; `jui g project` creates.

    Creating here would be actively wrong on a project that spells its
    methods as signature strings: the parser puts the whole string in `name`,
    so the rendered file reads `func fetchPnl(month?: string):
    Promise<PnlResponse>() async throws` and does not compile. One face
    declares 129 methods that way and has no protocol files at all today, so
    the damage would arrive as new, non-compiling files in a project with no
    symptom before.
    """

    def test_a_project_with_no_protocol_files_gets_none(self):
        """No file, and no noise about the file.

        Dropping the `path.exists()` guard writes nothing either — the read
        below it fails and the error path returns — so "no file was created"
        does NOT distinguish the two. What it changes is one WARNING per
        absent protocol, which on the face declaring 129 string-spelled
        methods is a flood about a project that has nothing wrong with it.
        Measured: without this assertion the guard's removal is invisible.
        """
        import contextlib
        import io
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, USE_CASE)          # no _scaffold: nothing exists
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertTrue(_run(mgr))
            self.assertEqual({}, _protocols(root))
            self.assertEqual("", out.getvalue(), "silence, not warnings")

    def test_a_string_spelled_method_is_not_rendered_into_a_new_file(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            signature = "fetchPnl(month?: string): Promise<PnlResponse>"
            mgr = _project(root, {"name": "SettingsUseCase",
                                  "methods": [signature]})
            self.assertTrue(_run(mgr))
            self.assertEqual({}, _protocols(root))


class RootedAtThePlatform(unittest.TestCase):
    """The generator is rooted at the platform, not at the project.

    This is the defect the end-to-end verification caught: a second copy of
    the factory rooted at `project_root`, so every path it computed pointed
    at a file that does not exist. Because the sync only rewrites files that
    DO exist, it skipped everything and returned success — nothing printed,
    exit 0, and a symptom identical to the defect it had just fixed.

    Asserted on the path, not on the write, because the write is what went
    quiet.
    """

    def test_the_protocol_path_is_under_the_platform_root(self):
        from jui_cli.commands.build_cmd import _platform_generator
        from jui_cli.core.type_mapper import TypeMapper

        project = Path("/tmp/does-not-need-to-exist")
        for platform, root_dir in (("ios", "ios"), ("android", "android"),
                                   ("web", "web")):
            gen = _platform_generator(
                project, platform, {"root": root_dir}, TypeMapper(None))
            if gen is None or not getattr(gen, "has_separate_protocol", True):
                continue
            path = gen.usecase_protocol_path("SettingsUseCase")
            self.assertIn(root_dir, path.parts, f"{platform}: {path}")
            self.assertTrue(
                str(path).startswith(str(project / root_dir)),
                f"{platform} protocol path escapes the platform root: {path}")

    def test_both_syncs_get_their_generator_from_one_factory(self):
        """A second copy of a path rule is a second path rule.

        The two syncs each had their own factory and they disagreed by one
        path segment. Reading the source is the only way to see that they
        share one now — the behaviour is identical either way until a project
        has a platform root, which no unit fixture had.
        """
        import inspect
        from jui_cli.commands import build_cmd

        for fn in (build_cmd._sync_usecase_protocols,
                   build_cmd._sync_viewmodel_protocols):
            src = inspect.getsource(fn)
            self.assertIn("_platform_generator", src, fn.__name__)
