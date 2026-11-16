"""A screen whose spec is gone leaves no protocol behind (`jui build`, iOS and Android).

Ticket jui-build-leaves-orphan-protocol-and-kjui-view-after-screen-removal (2.5.33): a screen's spec and layout
were deleted; `jui build` removed its Data, its GeneratedView and its web outputs, and kept its ViewModelProtocol
on both OS — and, measured on a consumer copy, the RepositoryProtocol of a repository only that spec declared.
The kept ViewModelProtocol names the deleted <Screen>Data, so the app no longer compiles.

The fixture writes the protocols the way the tools do — the ViewModel sync for ViewModels, the generators'
own `generate_*_protocol` (what `jui g project` writes) for repositories and use cases — through the factory
the build uses, so the banners and the paths are the real ones. EXPECTED counts are registered before any run.
"""

import io
import json
import sys
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent))

from jui_cli.commands.build_cmd import (  # noqa: E402
    _platform_generator,
    _prune_orphan_protocols,
    _sync_viewmodel_protocols,
)
from jui_cli.core.config_manager import ConfigManager  # noqa: E402
from jui_cli.core.spec_extractor import RepositoryDef, UseCaseDef  # noqa: E402
from jui_cli.core.type_mapper import TypeMapper  # noqa: E402

PLATFORMS = ("ios", "android")
# Per screen: one ViewModel protocol on each of iOS and Android (web has none: rjui writes its base).
EXPECTED_VM_PER_SCREEN = 2


def _spec(name: str, *, repositories=(), use_cases=(), layout_file: str | None = None) -> dict:
    spec = {
        "type": "screen_spec",
        "metadata": {"name": name, "displayName": name},
        "structure": {"components": []},
        "dataFlow": {
            "viewModel": {},
            "repositories": [{"name": r, "methods": []} for r in repositories],
            "useCases": [{"name": u, "methods": []} for u in use_cases],
        },
    }
    if layout_file:
        spec["metadata"]["layoutFile"] = layout_file
    return spec


def _project(root: Path, specs: dict[str, dict]) -> ConfigManager:
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
    for stem, body in specs.items():
        (spec_dir / f"{stem}.spec.json").write_text(json.dumps(body), encoding="utf-8")
    return ConfigManager(root / "jui.config.json")


def _gens(mgr: ConfigManager):
    tm = TypeMapper(mgr.type_map_file)
    platforms = mgr.load()["platforms"]
    return {p: _platform_generator(mgr.project_root, p, platforms[p], tm) for p in PLATFORMS}


def _write_protocols(mgr: ConfigManager, *, repositories=(), use_cases=()) -> None:
    config = mgr.load()
    with redirect_stdout(io.StringIO()):
        assert _sync_viewmodel_protocols(mgr, config, config["platforms"], Namespace(
            dry_run=False, ios_only=False, android_only=False, web_only=False))
    for gen in _gens(mgr).values():
        for name in repositories:
            path = gen.repository_protocol_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(gen.generate_repository_protocol(name, RepositoryDef(name=name, methods=[], description="")),
                            encoding="utf-8")
        for name in use_cases:
            path = gen.usecase_protocol_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(gen.generate_usecase_protocol(name, UseCaseDef(name=name, methods=[], description="")),
                            encoding="utf-8")


def _prune(mgr: ConfigManager, **flags) -> tuple[list[Path], str]:
    args = Namespace(dry_run=False, ios_only=False, android_only=False, web_only=False)
    for k, v in flags.items():
        setattr(args, k, v)
    out = io.StringIO()
    with redirect_stdout(out):
        removed = _prune_orphan_protocols(mgr, mgr.load()["platforms"], args)
    return removed, out.getvalue()


def _paths(mgr: ConfigManager, *, screens=(), repositories=(), use_cases=(), subdir="") -> list[Path]:
    out = []
    for gen in _gens(mgr).values():
        out += [gen.viewmodel_protocol_path(s, subdir) for s in screens]
        out += [gen.repository_protocol_path(r) for r in repositories]
        out += [gen.usecase_protocol_path(u) for u in use_cases]
    return out


class OrphanProtocols(unittest.TestCase):
    def setUp(self):
        self._dir = TemporaryDirectory()
        self.root = Path(self._dir.name)
        self.mgr = _project(self.root, {
            "catalog": _spec("Catalog", repositories=["InventoryRepository"], use_cases=["CatalogUseCase"]),
            "basket": _spec("Basket", repositories=["InventoryRepository", "BasketRepository"],
                            use_cases=["BasketUseCase"]),
        })
        _write_protocols(self.mgr, repositories=["InventoryRepository", "BasketRepository"],
                         use_cases=["CatalogUseCase", "BasketUseCase"])
        self.gone = _paths(self.mgr, screens=["Basket"], repositories=["BasketRepository"], use_cases=["BasketUseCase"])
        self.live = _paths(self.mgr, screens=["Catalog"], repositories=["InventoryRepository"],
                           use_cases=["CatalogUseCase"])

    def tearDown(self):
        self._dir.cleanup()

    def _delete_spec(self, stem: str) -> None:
        (self.root / "docs/screens/json" / f"{stem}.spec.json").unlink()

    def test_the_fixture_wrote_every_protocol_it_counts(self):
        self.assertEqual(len(self.gone), 3 * len(PLATFORMS))
        self.assertEqual([p for p in self.gone + self.live if not p.is_file()], [])
        self.assertEqual(len(_paths(self.mgr, screens=["Basket"])), EXPECTED_VM_PER_SCREEN)

    def test_nothing_is_pruned_while_every_spec_is_there(self):
        removed, out = _prune(self.mgr)
        self.assertEqual(removed, [])
        self.assertEqual(out, "")

    def test_a_deleted_screens_protocols_go_and_the_others_stay(self):
        self._delete_spec("basket")
        removed, out = _prune(self.mgr)
        self.assertEqual(sorted(removed), sorted(self.gone))
        self.assertEqual([p for p in self.gone if p.exists()], [])
        self.assertEqual([p for p in self.live if not p.exists()], [])
        self.assertIn(f"Pruned {len(self.gone)} generated protocol file(s) whose spec is gone:", out)
        self.assertIn("  - ios/", out)

    def test_the_last_declarer_of_every_repository_and_use_case_gone(self):
        # The syncs return early when nothing declares a repository or use case; the prune must not.
        (self.root / "docs/screens/json" / "catalog.spec.json").write_text(json.dumps(_spec("Catalog")),
                                                                           encoding="utf-8")
        self._delete_spec("basket")
        removed, _ = _prune(self.mgr)
        stale = self.gone + _paths(self.mgr, repositories=["InventoryRepository"], use_cases=["CatalogUseCase"])
        self.assertEqual(sorted(removed), sorted(stale))

    def test_a_hand_written_protocol_without_the_banner_stays(self):
        self._delete_spec("basket")
        hand = [p for p in self.gone]
        for p in hand:
            p.write_text("protocol Basket {}\n", encoding="utf-8")
        removed, out = _prune(self.mgr)
        self.assertEqual(removed, [])
        self.assertEqual([p for p in hand if not p.exists()], [])
        self.assertEqual(out, "")

    def test_a_banner_for_another_name_stays(self):
        # Copied from another file and renamed: the banner names the other declaration, so the generator did not
        # write this one.
        self._delete_spec("basket")
        for gen in _gens(self.mgr).values():
            for src, dst in ((gen.viewmodel_protocol_path("Catalog"), gen.viewmodel_protocol_path("Basket")),
                             (gen.repository_protocol_path("InventoryRepository"),
                              gen.repository_protocol_path("BasketRepository")),
                             (gen.usecase_protocol_path("CatalogUseCase"), gen.usecase_protocol_path("BasketUseCase"))):
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        removed, _ = _prune(self.mgr)
        self.assertEqual(removed, [])

    def test_an_unreadable_spec_stops_the_prune_and_says_so(self):
        self._delete_spec("basket")
        (self.root / "docs/screens/json" / "broken.spec.json").write_text("{ not json", encoding="utf-8")
        removed, out = _prune(self.mgr)
        self.assertEqual(removed, [])
        self.assertEqual([p for p in self.gone if not p.exists()], [])
        self.assertIn("orphan protocols were not pruned: 1 spec file(s) could not be loaded (broken.spec.json)", out)

    def test_a_spec_of_a_type_this_build_does_not_know_stops_the_prune(self):
        self._delete_spec("basket")
        (self.root / "docs/screens/json" / "later.spec.json").write_text(json.dumps({"type": "screen_spec_v9"}),
                                                                         encoding="utf-8")
        removed, out = _prune(self.mgr)
        self.assertEqual(removed, [])
        self.assertIn("(later.spec.json)", out)

    def test_no_spec_loaded_prunes_nothing(self):
        for stem in ("basket", "catalog"):
            self._delete_spec(stem)
        removed, _ = _prune(self.mgr)
        self.assertEqual(removed, [])
        self.assertEqual([p for p in self.gone + self.live if not p.exists()], [])

    def test_a_dry_run_lists_and_deletes_nothing(self):
        self._delete_spec("basket")
        removed, out = _prune(self.mgr, dry_run=True)
        self.assertEqual(sorted(removed), sorted(self.gone))
        self.assertEqual([p for p in self.gone if not p.exists()], [])
        self.assertIn("Would prune", out)

    def test_a_one_platform_build_prunes_that_platform_only(self):
        self._delete_spec("basket")
        removed, _ = _prune(self.mgr, ios_only=True)
        ios = _gens(self.mgr)["ios"]
        self.assertTrue(removed)
        self.assertTrue(all(ios._src_base in p.parents for p in removed))
        android = _gens(self.mgr)["android"]
        self.assertTrue(android.viewmodel_protocol_path("Basket").exists())


class OrphanProtocolsInASubdirectory(unittest.TestCase):
    """iOS puts the ViewModel protocol of a screen whose layout sits in a subdirectory under ViewModel/<Sub>/Protocol."""

    def test_a_deleted_subdirectory_screen_is_found_and_a_moved_one_leaves_its_old_copy(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, {
                "catalog": _spec("Catalog"),
                "basket": _spec("Basket", layout_file="shop/basket"),
                "card": _spec("Card", layout_file="shop/card"),
            })
            _write_protocols(mgr)
            ios = _gens(mgr)["ios"]
            basket = ios.viewmodel_protocol_path("Basket", "shop")
            old_card = ios.viewmodel_protocol_path("Card", "shop")
            self.assertTrue(basket.is_file() and old_card.is_file())
            self.assertEqual(basket.parent.parent.name, "Shop")
            (root / "docs/screens/json/basket.spec.json").unlink()
            (root / "docs/screens/json/card.spec.json").write_text(
                json.dumps(_spec("Card", layout_file="mall/card")), encoding="utf-8")
            _write_protocols(mgr)
            new_card = ios.viewmodel_protocol_path("Card", "mall")
            removed, _ = _prune(mgr)
            self.assertIn(basket, removed)
            self.assertIn(old_card, removed)
            self.assertTrue(new_card.is_file())


if __name__ == "__main__":
    unittest.main()
