"""`jui build` syncs Repository protocols too — the layer below use cases.

Found 2026-09-07 while fixing the aggregator, and it is the same hole one
level down. `jui build` grew a ViewModel sync, then a UseCase sync; all
three generators carry a `repository_protocol_path` and nothing called it,
so a method added to `dataFlow.repositories[].methods` reached the protocol
only by re-running `jui g project` — which refuses to overwrite an existing
protocol, so in practice never.

Closing the UseCase layer is what made this visible: that change and its
tests were both about use cases, so neither could see the layer beside it.

EXPECTED COUNTS ARE REGISTERED HERE, BEFORE THE RUN. The trap in this
function is that a wrong generator root makes every path miss, every file
"not exist", and the function return True having written nothing — silent,
exit 0, and indistinguishable from success if the arm only checks the
return value.
"""

import json
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent))

from jui_cli.commands.build_cmd import _sync_repository_protocols  # noqa: E402
from jui_cli.core.config_manager import ConfigManager  # noqa: E402

REPOSITORY = {
    "name": "InventoryRepository",
    "methods": [
        {"name": "fetchStock", "params": [], "returnType": "StockResponse"},
    ],
}

#: Registered before running, then CORRECTED by measurement: the guess was
#: three (one per face) and the population is two. Web's generator sets
#: `has_separate_protocol = False`, so it has no protocol file to sync, and
#: android names the file `InventoryRepository.kt` while iOS names it
#: `InventoryRepositoryProtocol.swift`. A glob written from the iOS spelling
#: finds ONE file, and every per-file assertion below would have passed over
#: that single file while claiming to cover the faces.
EXPECTED_PROTOCOLS = 2


def _project(root: Path, repository: dict) -> ConfigManager:
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
    (spec_dir / "catalog.spec.json").write_text(json.dumps({
        "type": "screen_spec",
        "metadata": {"name": "Catalog", "displayName": "Catalog"},
        "structure": {"components": []},
        "dataFlow": {"viewModel": {}, "repositories": [repository]},
    }), encoding="utf-8")
    return ConfigManager(root / "jui.config.json")


def _run(mgr: ConfigManager) -> bool:
    config = mgr.load()
    return _sync_repository_protocols(
        mgr, config, config.get("platforms", {}), Namespace(dry_run=False))


def _protocols(root: Path, mgr: ConfigManager) -> dict[str, Path]:
    """The files the SYNC would touch, derived from the generators rather
    than from a filename pattern — the two faces spell the file
    differently, and a pattern taken from one of them silently measures a
    population of one."""
    from jui_cli.commands.build_cmd import _platform_generator
    from jui_cli.core.type_mapper import TypeMapper
    tm = TypeMapper(mgr.type_map_file)
    out: dict[str, Path] = {}
    for platform in ("ios", "android", "web"):
        pconf = mgr.load()["platforms"][platform]
        gen = _platform_generator(root, platform, pconf, tm)
        if gen is None or not getattr(gen, "has_separate_protocol", True):
            continue
        path = gen.repository_protocol_path("InventoryRepository")
        if path.exists():
            out[platform] = path
    return out


def _scaffold(mgr: ConfigManager, root: Path) -> None:
    """Write the protocols the way `jui g project` would — through the SAME
    factory the sync uses. A fixture that computes its own paths shares the
    bug it is meant to catch: root the generator at the project instead of
    the platform and the fixture and the subject agree with each other while
    both disagree with every real project."""
    from jui_cli.commands.build_cmd import _platform_generator
    from jui_cli.core.type_mapper import TypeMapper
    from jui_cli.core.spec_extractor import RepositoryDef
    tm = TypeMapper(mgr.type_map_file)
    empty = RepositoryDef(name="InventoryRepository", methods=[], description="")
    for platform in ("ios", "android", "web"):
        pconf = mgr.load()["platforms"][platform]
        gen = _platform_generator(root, platform, pconf, tm)
        if gen is None or not getattr(gen, "has_separate_protocol", True):
            continue
        path = gen.repository_protocol_path("InventoryRepository")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            gen.generate_repository_protocol("InventoryRepository", empty),
            encoding="utf-8")


class RepositoryProtocolSync(unittest.TestCase):
    def test_the_scaffold_writes_the_number_this_test_expects(self):
        # The denominator, measured rather than assumed: if the scaffold
        # wrote fewer files than EXPECTED_PROTOCOLS, every assertion below
        # would be about a smaller set and would still pass.
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, REPOSITORY)
            _scaffold(mgr, root)
            self.assertEqual(EXPECTED_PROTOCOLS, len(_protocols(root, mgr)))

    def test_a_declared_method_reaches_every_protocol(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, REPOSITORY)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            written = _protocols(root, mgr)
            self.assertEqual(EXPECTED_PROTOCOLS, len(written))
            for ext, path in written.items():
                self.assertIn("fetchStock", path.read_text(encoding="utf-8"), ext)

    def test_it_writes_nothing_when_the_protocol_does_not_exist(self):
        # SYNC, NOT CREATE — creating is `jui g project`'s job. This is also
        # the arm that separates "wrote everything" from "wrote nothing and
        # returned True", which is what a wrong generator root produces.
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, REPOSITORY)
            self.assertTrue(_run(mgr))
            self.assertEqual({}, _protocols(root, mgr))

    def test_a_file_without_the_generated_banner_is_left_alone(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, REPOSITORY)
            _scaffold(mgr, root)
            hand_written = sorted(_protocols(root, mgr).values())[0]
            hand_written.write_text("// mine\n", encoding="utf-8")
            self.assertTrue(_run(mgr))
            self.assertEqual("// mine\n",
                             hand_written.read_text(encoding="utf-8"))

    def test_a_platform_scoped_method_reaches_only_that_face(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            scoped = {
                "name": "InventoryRepository",
                "methods": [{"name": "fetchStock", "params": [],
                             "returnType": "StockResponse",
                             "platforms": ["android"]}],
            }
            mgr = _project(root, scoped)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            written = _protocols(root, mgr)
            self.assertIn("fetchStock", written["android"].read_text(encoding="utf-8"))
            for ext in set(written) - {"android"}:
                self.assertNotIn("fetchStock",
                                 written[ext].read_text(encoding="utf-8"), ext)


    def test_the_build_command_actually_calls_it(self):
        """The function working is not the build using it.

        Measured: deleting the call from `cmd_build` left every other arm in
        this file green, because they all invoke `_sync_repository_protocols`
        directly. A defect that reaches users — the sync existing and never
        running — was invisible to a file named after the sync.

        This reads the call out of `cmd_build`'s own source. That is weaker than
        driving `jui build` end to end (it proves the call is written, not
        that control reaches it), and it is what catches the regression the
        other arms cannot see. The same gap exists for the UseCase sync
        added in the previous commit; reported rather than fixed here.
        """
        import inspect
        from jui_cli.commands import build_cmd
        source = inspect.getsource(build_cmd.cmd_build)
        self.assertIn("_sync_repository_protocols(", source)
        # Ordered after the use cases it depends on nothing from, but before
        # the gates, the same as its sibling.
        self.assertLess(source.index("_sync_usecase_protocols("),
                        source.index("_sync_repository_protocols("))


if __name__ == "__main__":
    unittest.main()
