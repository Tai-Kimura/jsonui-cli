"""End-to-end test for build_cmd._sync_viewmodel_protocols and
build_cmd._distribute_layouts (normalizeLayouts opt-in).

Builds a minimal fixture project in a temp dir and asserts:
- Protocol/Base content matches expectations
- Impl inheritance is patched in
- Kotlin `override` is injected
- A second sync is a zero-diff no-op (idempotency)
- spec → Impl drift triggers an error
- layout distribution is byte-stable with normalizeLayouts off (default)
  and L1-canonicalized + idempotent with it on
"""
from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.build_cmd import (
    _distribute_layouts,
    _sync_viewmodel_protocols,
)
from jui_cli.core.config_manager import ConfigManager


def _make_args(**overrides):
    ns = argparse.Namespace(
        clean=False,
        ios_only=False,
        android_only=False,
        web_only=False,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def _build_fixture_project(root: Path, *, with_members=True) -> None:
    """Create a minimal config + one spec + stub Impl files for each platform."""
    # jui.config.json
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts",
        "platforms": {
            "ios": {
                "root": "ios",
                "layoutsDir": "Layouts",
            },
            "android": {
                "root": "android",
                "layoutsDir": "app/src/main/assets/Layouts",
            },
            "web": {
                "root": "web",
                "layoutsDir": "src/Layouts",
            },
        },
    }, indent=2))

    # Spec
    spec_dir = root / "docs/screens/json"
    spec_dir.mkdir(parents=True)
    view_model = {}
    if with_members:
        view_model = {
            "methods": [
                {"name": "onLogin"},
                {"name": "onCancel"},
            ],
            "vars": [
                {"name": "isLoading", "type": "Bool"},
            ],
        }
    (spec_dir / "login.spec.json").write_text(json.dumps({
        "type": "screen_spec",
        "metadata": {"name": "Login", "displayName": "Login"},
        "structure": {"components": []},
        "dataFlow": {"viewModel": view_model},
    }, indent=2))

    # iOS Impl
    ios_impl_dir = root / "ios/ViewModel"
    ios_impl_dir.mkdir(parents=True)
    (ios_impl_dir / "LoginViewModel.swift").write_text(
        "import Foundation\n"
        "\n"
        "class LoginViewModel: ObservableObject {\n"
        "    @Published var data = LoginData()\n"
        "    @Published var isLoading: Bool = false\n"
        "    func onLogin() {}\n"
        "    func onCancel() {}\n"
        "}\n"
    )
    # iOS sjui.config.json (required by IosGenerator)
    (root / "ios/sjui.config.json").write_text(json.dumps({
        "source_directory": "",
    }))

    # Android Impl
    android_impl_dir = (
        root / "android/app/src/main/kotlin/com/example/app/viewmodel"
    )
    android_impl_dir.mkdir(parents=True)
    (android_impl_dir / "LoginViewModel.kt").write_text(
        "package com.example.app.viewmodel\n"
        "\n"
        "import androidx.lifecycle.ViewModel\n"
        "import kotlinx.coroutines.flow.MutableStateFlow\n"
        "import kotlinx.coroutines.flow.StateFlow\n"
        "import kotlinx.coroutines.flow.asStateFlow\n"
        "\n"
        "class LoginViewModel : ViewModel() {\n"
        "    private val _data = MutableStateFlow(LoginData())\n"
        "    val data: StateFlow<LoginData> = _data.asStateFlow()\n"
        "    var isLoading: Boolean = false\n"
        "    fun onLogin() {}\n"
        "    fun onCancel() {}\n"
        "}\n"
    )
    # Android manifest to trigger package detection
    manifest_dir = root / "android/app/src/main"
    (manifest_dir / "AndroidManifest.xml").write_text(
        '<manifest package="com.example.app" />\n'
    )

    # Web Impl
    web_impl_dir = root / "web/src/viewmodels"
    web_impl_dir.mkdir(parents=True)
    (web_impl_dir / "LoginViewModel.ts").write_text(
        "export class LoginViewModel {}\n"
    )
    (root / "web/rjui.config.json").write_text("{}\n")


def _load_config(root: Path):
    import os
    old = os.getcwd()
    os.chdir(root)
    try:
        mgr = ConfigManager()
        return mgr, mgr.load()
    finally:
        os.chdir(old)


def _write_layout_fixtures(root: Path) -> None:
    """Shared layouts exercising aliases, platform overrides and includes."""
    layouts = root / "docs/screens/layouts"
    layouts.mkdir(parents=True, exist_ok=True)
    (layouts / "home.json").write_text(json.dumps({
        "type": "View",
        "id": "home_root",
        "alpha": 0.5,
        "platform": {"ios": {"cornerRadius": 8}},
        "child": [
            {"type": "Slider", "id": "volume", "minValue": 0, "maximum": 10},
            {"include": "header", "id": "top"},
        ],
    }, indent=2) + "\n")
    (layouts / "header.json").write_text(json.dumps({
        "type": "View",
        "id": "header_root",
        "child": [{"type": "Label", "id": "title", "text": "@{title}"}],
    }, indent=2) + "\n")


def _set_normalize(root: Path, enabled: bool) -> None:
    config_path = root / "jui.config.json"
    config = json.loads(config_path.read_text())
    config["build"] = {"normalizeLayouts": enabled}
    config_path.write_text(json.dumps(config, indent=2))


def _read_distributed(root: Path) -> dict[str, str]:
    """Read every distributed layout file, keyed by platform-relative path."""
    out: dict[str, str] = {}
    for rel in (
        "ios/Layouts/home.json",
        "ios/Layouts/header.json",
        "android/app/src/main/assets/Layouts/home.json",
        "web/src/Layouts/home.json",
    ):
        path = root / rel
        if path.exists():
            out[rel] = path.read_text()
    return out


class DistributeLayoutsNormalizeE2ETests(unittest.TestCase):
    def test_flag_off_is_byte_stable_and_unnormalized(self):
        """Explicit opt-out (build.normalizeLayouts: false — the escape
        hatch now that the default is on): no $jui marker, aliases pass
        through untouched, and a second distribution is a byte-level
        no-op."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _build_fixture_project(root)
            _write_layout_fixtures(root)
            _set_normalize(root, False)
            config_mgr, config = _load_config(root)
            platforms = config["platforms"]

            _distribute_layouts(config_mgr, platforms, _make_args())
            first = _read_distributed(root)
            self.assertTrue(first)

            for rel, text in first.items():
                data = json.loads(text)
                self.assertNotIn("$jui", data, rel)
            home_ios = json.loads(first["ios/Layouts/home.json"])
            self.assertEqual(home_ios["alpha"], 0.5)  # alias NOT rewritten
            self.assertEqual(home_ios["child"][0]["minValue"], 0)
            # platform override resolved as before
            self.assertEqual(home_ios["cornerRadius"], 8)
            self.assertNotIn("platform", home_ios)

            _distribute_layouts(config_mgr, platforms, _make_args())
            self.assertEqual(_read_distributed(root), first)

    def test_default_is_normalized(self):
        """No build key at all → normalizeLayouts defaults ON (SSoT phase
        14): distributed layouts carry the $jui L1 marker and aliases are
        canonicalized."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _build_fixture_project(root)
            _write_layout_fixtures(root)
            config_mgr, config = _load_config(root)
            platforms = config["platforms"]

            _distribute_layouts(config_mgr, platforms, _make_args())
            distributed = _read_distributed(root)
            self.assertTrue(distributed)
            home_ios = json.loads(distributed["ios/Layouts/home.json"])
            self.assertIn("$jui", home_ios)
            self.assertNotIn("alpha", home_ios)
            self.assertEqual(home_ios["opacity"], 0.5)

    def test_flag_on_distributes_l1_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _build_fixture_project(root)
            _write_layout_fixtures(root)
            _set_normalize(root, True)
            config_mgr, config = _load_config(root)
            platforms = config["platforms"]

            shared_before = (root / "docs/screens/layouts/home.json").read_text()

            _distribute_layouts(config_mgr, platforms, _make_args())
            first = _read_distributed(root)

            home_ios = json.loads(first["ios/Layouts/home.json"])
            # Marker present, right shape, ordered after _generated.
            self.assertEqual(
                home_ios["$jui"], {"normalized": "L1", "schemaVersion": 1}
            )
            self.assertEqual(list(home_ios.keys())[:2], ["_generated", "$jui"])
            # Aliases canonicalized on the distributed copy.
            self.assertEqual(home_ios["opacity"], 0.5)
            self.assertNotIn("alpha", home_ios)
            self.assertEqual(home_ios["child"][0]["minimum"], 0)
            self.assertNotIn("minValue", home_ios["child"][0])
            # include is preserved at L1 (not expanded).
            self.assertEqual(home_ios["child"][1]["include"], "header")
            # platform override still resolved before canonicalization.
            self.assertEqual(home_ios["cornerRadius"], 8)

            # Every distributed copy is marked, across all platforms.
            for rel, text in first.items():
                self.assertIn("$jui", json.loads(text), rel)

            # The shared L0 source is NEVER rewritten.
            self.assertEqual(
                (root / "docs/screens/layouts/home.json").read_text(),
                shared_before,
            )

            # Second build → byte-identical distribution (idempotency).
            _distribute_layouts(config_mgr, platforms, _make_args())
            self.assertEqual(_read_distributed(root), first)


class SyncProtocolE2ETests(unittest.TestCase):
    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _build_fixture_project(root)
            config_mgr, config = _load_config(root)
            platforms = config["platforms"]

            ok = _sync_viewmodel_protocols(config_mgr, config, platforms, _make_args())
            self.assertIsNot(ok, False)

            # iOS protocol file should now exist with the spec-imported methods.
            ios_proto = root / "ios/ViewModel/Protocol/LoginViewModelProtocol.swift"
            self.assertTrue(ios_proto.exists())
            body = ios_proto.read_text()
            self.assertIn("var data: LoginData", body)
            self.assertIn("func onLogin()", body)
            self.assertIn("func onCancel()", body)
            self.assertIn("@generated", body)

            # Swift Impl should have inheritance patched in.
            ios_impl = (root / "ios/ViewModel/LoginViewModel.swift").read_text()
            self.assertIn("LoginViewModelProtocol", ios_impl)

            # Android interface + override injection.
            android_proto = (
                root
                / "android/app/src/main/kotlin/com/example/app/viewmodel/protocol/LoginViewModelProtocol.kt"
            )
            self.assertTrue(android_proto.exists())
            body_kt = android_proto.read_text()
            self.assertIn("fun onLogin()", body_kt)
            self.assertIn("fun onCancel()", body_kt)

            android_impl = (
                root
                / "android/app/src/main/kotlin/com/example/app/viewmodel/LoginViewModel.kt"
            ).read_text()
            self.assertIn("LoginViewModelProtocol", android_impl)
            self.assertIn("override fun onLogin()", android_impl)
            self.assertIn("override fun onCancel()", android_impl)
            # Inheritance patching must also pull in the matching `import`,
            # since Impl (`*.viewmodel`) and Protocol (`*.viewmodel.protocol`)
            # are sibling packages.
            self.assertIn(
                "import com.example.app.viewmodel.protocol.LoginViewModelProtocol",
                android_impl,
            )

            # Protocol declares `data` as StateFlow (matching Compose
            # convention) and the Impl gains the `override` modifier on
            # its existing `val data: StateFlow<...>` line.
            self.assertIn(
                "import kotlinx.coroutines.flow.StateFlow", body_kt,
            )
            self.assertIn("val data: StateFlow<LoginData>", body_kt)
            self.assertIn(
                "override val data: StateFlow<LoginData>", android_impl,
            )

    def test_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _build_fixture_project(root)
            config_mgr, config = _load_config(root)
            platforms = config["platforms"]
            _sync_viewmodel_protocols(config_mgr, config, platforms, _make_args())

            ios_proto = root / "ios/ViewModel/Protocol/LoginViewModelProtocol.swift"
            before_proto = ios_proto.read_text()
            ios_impl = root / "ios/ViewModel/LoginViewModel.swift"
            before_impl = ios_impl.read_text()

            _sync_viewmodel_protocols(config_mgr, config, platforms, _make_args())

            self.assertEqual(ios_proto.read_text(), before_proto)
            self.assertEqual(ios_impl.read_text(), before_impl)

    def test_swift_label_drift_error(self):
        """Protocol expects `imageData:` (default label) but Impl declares
        `_ imageData:` → build must surface drift.
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _build_fixture_project(root)
            # Add a method that forces a label expectation.
            spec_path = root / "docs/screens/json/login.spec.json"
            data = json.loads(spec_path.read_text())
            data["dataFlow"]["viewModel"]["methods"].append({
                "name": "onImageSelected",
                "params": [{"name": "imageData", "type": "Data"}],
            })
            spec_path.write_text(json.dumps(data, indent=2))
            # Impl uses `_ imageData:` (drift).
            impl_path = root / "ios/ViewModel/LoginViewModel.swift"
            impl_path.write_text(
                impl_path.read_text().replace(
                    "    func onCancel() {}\n",
                    "    func onCancel() {}\n"
                    "    func onImageSelected(_ imageData: Data) {}\n",
                )
            )

            config_mgr, config = _load_config(root)
            platforms = config["platforms"]
            result = _sync_viewmodel_protocols(
                config_mgr, config, platforms, _make_args()
            )
            self.assertFalse(result)

    def test_spec_drift_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _build_fixture_project(root)
            # Add a method to viewModel that has no matching decl in Impl.
            spec_path = root / "docs/screens/json/login.spec.json"
            data = json.loads(spec_path.read_text())
            data["dataFlow"]["viewModel"]["methods"].append({"name": "onGhost"})
            spec_path.write_text(json.dumps(data, indent=2))

            config_mgr, config = _load_config(root)
            platforms = config["platforms"]
            result = _sync_viewmodel_protocols(
                config_mgr, config, platforms, _make_args()
            )
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()


class DistributedResourcesSmokeTests(unittest.TestCase):
    """What a build PRODUCED, not only that it exited 0.

    Two holes, caught by different instruments. A crash gives a non-zero
    exit and an exit-code smoke finds it. A run that quietly produces
    nothing exits 0 and that same smoke passes — which is how five projects
    ran `jui verify` against zero screens until it began naming its
    denominator. So a smoke has to assert what came out.

    The colours case is the sharp one. A crash before the platform tools
    normalise leaves the SSoT's flat form sitting at the distributed path:
    not a truncated file, a different well-formed one. Exit codes, diff line
    counts and a glance all read it as fine.

    DIRECTION MATTERS, and reading it backwards condemns healthy projects.
    Flat is the AUTHORED form — the SSoT is flat on purpose and the build
    migrates it to themed on the way out. So the property is about the
    DISTRIBUTED copy, and the source is expected to stay flat.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _build_fixture_project(self.root)
        resources = self.root / "docs/screens/layouts/Resources"
        resources.mkdir(parents=True, exist_ok=True)
        # Authored (flat) — this shape is correct at the source.
        (resources / "colors.json").write_text(json.dumps({
            "primary": "#FF0000",
            "background": "#FFFFFF",
        }, indent=2), encoding="utf-8")
        (resources / "strings.json").write_text(json.dumps({
            "login": {"title": "Login"},
        }, indent=2), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _distribute(self):
        from jui_cli.commands.build_cmd import _distribute_resources
        cfg = ConfigManager(self.root / "jui.config.json")
        platforms = cfg.load()["platforms"]
        _distribute_resources(cfg, platforms, _make_args())
        return cfg

    def test_the_run_produced_files_at_every_platform_path(self):
        # The assertion an exit code cannot make: something arrived.
        self._distribute()
        for rel in ("ios/Layouts/Resources",
                    "android/app/src/main/assets/Layouts/Resources",
                    "web/src/Layouts/Resources"):
            dest = self.root / rel
            produced = sorted(p.name for p in dest.glob("*.json"))
            self.assertEqual(["colors.json", "strings.json"], produced,
                             f"{rel} did not receive the resources")

    def test_the_authored_colours_stay_flat(self):
        # The direction guard. Flat at the source is the authored form; a
        # check that calls it broken reports every healthy project.
        self._distribute()
        src = json.loads(
            (self.root / "docs/screens/layouts/Resources/colors.json")
            .read_text(encoding="utf-8"))
        self.assertNotIn("modes", src)
        self.assertIn("primary", src)

    def test_a_distributed_colours_file_is_recognisable_as_flat(self):
        # Distribution copies; the platform tools migrate to themed. This
        # pins the shape a smoke has to look at — the DISTRIBUTED copy —
        # and states which side of it is the defect, so the next reader
        # does not have to rediscover the direction from the ticket.
        self._distribute()
        dest = (self.root / "web/src/Layouts/Resources/colors.json")
        distributed = json.loads(dest.read_text(encoding="utf-8"))
        themed = "modes" in distributed and "fallback_mode" in distributed
        self.assertFalse(
            themed,
            "the Python distribution step migrated colours, which it has "
            "never done — if that changed, this smoke should assert the "
            "themed shape here instead of the flat one",
        )


class ManifestWindowTests(unittest.TestCase):
    """The snapshot has to span every step of the build that writes.

    Shipped 1.8.8 passed its unit tests and churned on a real project: 89
    layout files recorded as written on every build, with identical bytes at
    the start and the end of each. The comparison was not the problem — the
    pair being compared was. The window opened AFTER distribution, so the
    baseline was a mid-run state: distribution copies the authored layout
    over the platform's copy, the platform tool normalises it back, and the
    two moments compared were "just overwritten" and "normalised again".

    The unit tests could not see it because their fixture wrote content
    once, with nothing in between. A build has steps in between; that is
    what makes it a build. These cases put a step inside the window.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.file = self.root / "gen" / "Home.json"
        self.file.parent.mkdir(parents=True)
        # The state a previous build left behind: normalised.
        self.file.write_text('{"normalised": true}\n', encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _cycle(self, observe_before_distribution: bool):
        """One build, with the snapshot on either side of distribution.

        The file is already on record — otherwise the bootstrap rule (a
        file with no entry is recorded on sight) would report a write and
        the window position would not be what the result depends on.
        """
        from jui_cli.core import generation_manifest as gm

        known = {"gen/Home.json"}
        run = gm.GenerationRun(project_root=self.root, version="1.8.9")
        if observe_before_distribution:
            run.observe([self.file])
        # Distribution: the authored (un-normalised) form lands on top.
        self.file.write_text('{"authored": true}\n', encoding="utf-8")
        if not observe_before_distribution:
            run.observe([self.file])
        # The platform tool normalises it back to exactly what was there.
        self.file.write_text('{"normalised": true}\n', encoding="utf-8")
        return run.written([self.file], known=known)

    def test_a_build_that_ends_where_it_started_records_nothing(self):
        self.assertEqual(
            [], self._cycle(observe_before_distribution=True),
            "an unchanged build recorded a write — the window is opening "
            "after a step that writes",
        )

    def test_the_late_window_is_what_produced_the_churn(self):
        # The control: the same cycle with the snapshot where 1.8.8 put it,
        # so this file demonstrates the defect rather than only asserting
        # its absence.
        self.assertEqual(["gen/Home.json"],
                         self._cycle(observe_before_distribution=False))

    def test_a_real_change_is_still_recorded(self):
        from jui_cli.core import generation_manifest as gm

        run = gm.GenerationRun(project_root=self.root, version="1.8.9")
        run.observe([self.file])
        self.file.write_text('{"normalised": true, "new": 1}\n', encoding="utf-8")
        self.assertEqual(["gen/Home.json"],
                         run.written([self.file], known={"gen/Home.json"}))


class PlatformSelectorAliasTests(unittest.TestCase):
    """`--platform web` means what `--web-only` means.

    The MCP tool takes `platform: "ios" | "android" | "web"`; the CLI took
    only `--ios-only` / `--android-only` / `--web-only`. Anyone who met the
    MCP interface first writes the MCP spelling here and gets exit 2 — and
    a build stopped by an unknown argument leaves every output exactly as it
    was, which is indistinguishable from a successful no-op. One project
    compared manifest checksums across two such runs, found them identical,
    and nearly recorded "no churn" from a tool that never ran.

    The old spellings stay: they are in scripts and habits, and removing
    them would trade one wrong guess for another.
    """

    def _folded(self, **kwargs):
        from jui_cli.commands.build_cmd import _apply_platform_alias

        args = _make_args(platform=None, **kwargs)
        _apply_platform_alias(args)
        return args

    def test_each_platform_sets_the_matching_flag(self):
        for platform in ("ios", "android", "web"):
            args = self._folded()
            args.platform = platform
            from jui_cli.commands.build_cmd import _apply_platform_alias
            _apply_platform_alias(args)
            self.assertTrue(getattr(args, f"{platform}_only"),
                            f"--platform {platform} did not select {platform}")
            others = {"ios", "android", "web"} - {platform}
            for other in others:
                self.assertFalse(getattr(args, f"{other}_only"))

    def test_the_old_spelling_still_works_on_its_own(self):
        args = self._folded(web_only=True)
        self.assertTrue(args.web_only)

    def test_no_platform_leaves_every_flag_alone(self):
        args = self._folded()
        for platform in ("ios", "android", "web"):
            self.assertFalse(getattr(args, f"{platform}_only"))

    def test_the_parser_accepts_the_mcp_vocabulary(self):
        # The arm that actually reproduces the report: the parser used to
        # exit 2 on this spelling.
        import argparse

        from jui_cli.commands.build_cmd import register_build_command

        parser = argparse.ArgumentParser()
        register_build_command(parser.add_subparsers(dest="command"))
        parsed = parser.parse_args(["build", "--platform", "web"])
        self.assertEqual("web", parsed.platform)


class RecordOrderTests(unittest.TestCase):
    """Migration and the has-it-been-recorded lookup must key alike.

    Caught on a real project before distribution, by a run against real
    data rather than a fixture. Key migration was perfect — 198 of 198
    renamed, `dropped 0` — a --clean build recorded 508 instead of zero,
    and two consecutive builds were byte-identical. Every number in the
    summary was right. The versions were gone anyway: entries went 1.8.7 →
    1.8.9 and `generatedAt` with them, because the lookup deciding which
    files had no record read the manifest raw while migration ran later,
    inside `save`. Every entry whose spelling changed was therefore missing
    from the lookup, the bootstrap rule fired, and `save` re-stamped what
    it had just migrated. 327 of 537 entries on that project.

    Both parts had been checked, each on its own, and neither check could
    see this: the defect is in their order. So these go through
    `_record_generation`, which is that order, and the control below runs
    the old arrangement to show it still fails there.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Two files whose keys the normaliser respells, three it leaves be.
        self.recorded = ["src/generated/A.ts", "src/generated/B.ts"]
        self.fresh = ["src/generated/C.ts", "src/generated/D.ts",
                      "src/generated/E.ts"]
        for key in self.recorded + self.fresh:
            path = self.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"// {key}\n", encoding="utf-8")
        # On record under the old spelling, from an older release. The
        # location comes from the module: written to a hand-spelled path,
        # this seed is simply never read, and then every arm here passes
        # for the reason a project with no manifest passes — including the
        # control, which reported the defect it was built to reproduce
        # while measuring an empty file. (Observed, first run.)
        from jui_cli.core import generation_manifest as gm

        seed = gm.manifest_path(self.root)
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_text(json.dumps({
            "version": 1,
            "files": {k.replace("src/generated", "src/Generated"):
                      {"version": "1.8.7",
                       "generatedAt": "2026-08-01T00:00:00Z"}
                      for k in self.recorded},
        }, indent=2), encoding="utf-8")
        self.assertEqual(
            2, len(gm.load(self.root).get("files") or {}),
            "the seeded manifest is not being read — every arm below would "
            "then be measuring a project that has no record at all",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _present(self):
        return [self.root / k for k in self.recorded + self.fresh]

    def _run(self):
        from jui_cli.core import generation_manifest as gm

        run = gm.GenerationRun(project_root=self.root, version="1.8.10")
        run.observe(self._present())
        return run

    def _versions(self):
        from jui_cli.core import generation_manifest as gm

        return {k: v.get("version")
                for k, v in gm.load(self.root)["files"].items()}

    # Arm 5 ---------------------------------------------------------------
    def test_a_migrated_entry_keeps_the_version_that_generated_it(self):
        from jui_cli.commands.build_cmd import _record_generation

        _record_generation(_ConfigStub(self.root), self._run(),
                           self._present())
        versions = self._versions()
        for key in self.recorded:
            self.assertEqual(
                "1.8.7", versions.get(key),
                "an entry that only changed spelling was re-stamped with "
                "the running version — the record's whole purpose",
            )

    # Arm 6 ---------------------------------------------------------------
    def test_the_run_records_only_the_files_that_had_no_entry(self):
        from jui_cli.commands.build_cmd import _record_generation

        written, present_keys, _ = _record_generation(
            _ConfigStub(self.root), self._run(), self._present())
        self.assertEqual(
            sorted(self.fresh), sorted(written),
            "the count is 5 of 5 when the lookup misses the migrated keys, "
            "and 3 of 5 when it sees them",
        )
        self.assertEqual(5, len(present_keys))

    # The control ---------------------------------------------------------
    def test_the_raw_lookup_is_what_loses_the_versions(self):
        # The old arrangement, spelled out: `known` from the file as
        # written, migration left to `save`, which still does it. This
        # demonstrates the defect rather than only asserting its absence,
        # so the arms above cannot pass by measuring something that was
        # never at risk.
        #
        # It has to be built this precisely. Disabling migration in both
        # places instead — the shortcut — turns the arms above red too, but
        # by dropping the old entries and adding new ones, which is a
        # different failure with a different summary. A reproduction that
        # fails differently from the original does not establish that the
        # arms above are watching the original.
        from jui_cli.commands.build_cmd import _tracked_scope
        from jui_cli.core import generation_manifest as gm

        run = self._run()
        known = set(gm.load(self.root).get("files") or {})  # ← raw
        written = run.written(self._present(), known=known)
        present_keys = [run._key(p) for p in self._present()]
        manifest = gm.save(self.root, run.version, written,
                           present_keys=present_keys,
                           scope=_tracked_scope(present_keys))

        self.assertEqual(5, len(written), "the control did not reproduce the "
                                         "over-recording it exists to show")
        self.assertEqual(["1.8.10"] * 2,
                         [self._versions()[k] for k in self.recorded],
                         "the control did not reproduce the re-stamping")

        # And this is why neither part's own tests caught it, and why arm 5
        # asserts versions rather than totals: with the defect running,
        # every count in the summary is the count of a healthy build.
        self.assertEqual(0, manifest["summary"].get("dropped", 0))
        self.assertEqual(sorted(self.recorded + self.fresh),
                         sorted(self._versions()))
        self.assertEqual(5, len(present_keys))


class _ConfigStub:
    def __init__(self, project_root):
        self.project_root = project_root


class GeneratedTreeScanTests(unittest.TestCase):
    """The scan starts from the generated tree, not from what it found in it.

    The widening began at the PARENT of each already-discovered file, so it
    could only ever reach directories that already contained one. Anything
    sitting directly in the generated tree is then invisible when the
    discovery below it happens one level down.

    It was also answering differently per environment, and not in the way
    it first looked. The collection it leaned on globs for a directory
    literally named `Generated`; the fallback is an enumerated list of four
    subdirectory names. Whether the glob matches `generated` was measured
    three ways: never on a case-sensitive filesystem, not under Python 3.12
    on a case-insensitive one, and yes under 3.14 on that same tree. So the
    reported face recorded 444 files with one python3 on PATH and 454 with
    another — same machine, same disk, same code.

    Three lanes looked at this and each generalised from the interpreter it
    happened to be running: two concluded the glob is case-sensitive, one
    concluded the old code reaches the files on macOS. Every measurement
    was correct and every conclusion was too broad. The arms below do not
    depend on either variable, which is the point of walking for the name
    instead of globbing for one spelling.

    The fixtures below hold no code file at the top level of the generated
    tree, which is what makes them fail on either filesystem rather than
    only on Linux.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.web = self.root / "web"
        (self.web / "src" / "Layouts").mkdir(parents=True)
        self.gen = self.web / "src" / "generated"
        (self.gen / "components").mkdir(parents=True)
        (self.gen / "components" / "Foo.tsx").write_text(
            "x\n", encoding="utf-8")
        # Top level holds ONLY a non-source file. That is what makes these
        # arms fail on this machine too: with a `.ts` up here, the lint
        # collection finds it on a case-insensitive filesystem, its parent
        # becomes a starting point, and the old widening reaches the rest —
        # so a fixture with one would pass on macOS whether or not the
        # repair is present, and only fail on Linux. Arms that need the
        # `.ts` add it themselves and say what they can and cannot catch.
        (self.gen / "theme.css").write_text("x\n", encoding="utf-8")
        (self.root / "jui.config.json").write_text(json.dumps({
            "platforms": {"web": {"root": "web", "layoutsDir": "src/Layouts"}},
        }), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _paths(self):
        from jui_cli.commands.build_cmd import _generated_paths
        return sorted(p.name for p in _generated_paths(_config(self.root)))

    def test_a_helper_at_the_top_of_the_tree_is_found(self):
        # The shape the report was about — a `.ts` helper beside the four
        # subdirectories. NOTE: this arm cannot fail on a case-insensitive
        # filesystem, where the glob for `Generated` matches `generated`
        # and picks the file up regardless. It is the Linux-side pin; the
        # arms below are the ones that fail here.
        (self.gen / "ColorManager.ts").write_text("x\n", encoding="utf-8")
        self.assertIn("ColorManager.ts", self._paths())

    def test_a_non_source_file_at_the_top_of_the_tree_is_found(self):
        # The one the old code could not reach by any route: not a source
        # extension, so no collection returns it, and its directory was
        # never a starting point.
        self.assertIn("theme.css", self._paths())

    def test_the_old_starting_points_are_what_missed_them(self):
        # The control. Widening from the parents of discovered files only,
        # as before — this must still miss the two above, or the arms above
        # are not measuring the repair.
        from jui_cli.commands.build_cmd import _is_generated_dir
        from jui_cli.commands.lint_generated_cmd import _collect_targets

        cm = _config(self.root)
        found = {p for _kind, p in _collect_targets(cm)}
        widened = set(found)
        starts = {p.parent for p in found if _is_generated_dir(p.parent)}
        for directory in starts:
            widened.update(f for f in directory.rglob("*") if f.is_file())
        names = {p.name for p in widened}
        self.assertNotIn("theme.css", names,
                         "the control no longer reproduces the gap")

    def test_a_vendored_tool_tree_is_not_claimed_as_output(self):
        # The toolchain ships inside the project, and its own source has a
        # directory named `generated` too. Widening to every extension is
        # what exposes it: the old collection missed those files only
        # because they are Ruby and it filtered to source extensions.
        tool = self.web / "rjui_tools" / "lib" / "core" / "generated"
        tool.mkdir(parents=True)
        (tool / "emitter.rb").write_text("x\n", encoding="utf-8")
        self.assertNotIn("emitter.rb", self._paths())

    def test_an_excluded_directory_is_not_walked_into(self):
        junk = self.web / "node_modules" / "pkg" / "generated"
        junk.mkdir(parents=True)
        (junk / "junk.ts").write_text("x\n", encoding="utf-8")
        self.assertNotIn("junk.ts", self._paths())

    def test_the_tree_is_found_under_either_spelling(self):
        # A project spelling it `Generated` gets the same answer. On a
        # case-insensitive filesystem this is the same directory as the
        # fixture's; on a case-sensitive one it is a second one, and both
        # must be found.
        other = self.web / "src" / "Generated"
        other.mkdir(exist_ok=True)  # same dir on macOS, a second one on Linux
        (other / "Marker.ts").write_text("x\n", encoding="utf-8")
        self.assertIn("Marker.ts", self._paths())


def _config(root: Path):
    from jui_cli.core.config_manager import ConfigManager
    return ConfigManager(root / "jui.config.json")


class HaltedRunRecordsWhatItWroteTests(unittest.TestCase):
    """A build that writes and then fails must not leave a stale record.

    Measured downstream: a build rewrote generated files on three faces and
    then stopped on a spec error, so nothing was recorded; the next build
    succeeded and recorded nothing either, correctly, because the bytes no
    longer changed. Both halves behave properly on their own and the
    mismatch is stable — the manifest carries one build's timestamp over
    another build's contents until something edits those files again.

    The record is of writes, not of successes.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "gen").mkdir()
        self.files = []
        for name in ("A.kt", "B.kt", "C.kt"):
            path = self.root / "gen" / name
            path.write_text("// from an earlier release\n", encoding="utf-8")
            self.files.append(path)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        from jui_cli.core import generation_manifest as gm

        run = gm.GenerationRun(project_root=self.root, version="1.8.11")
        run.observe(self.files)
        return run

    def test_a_halted_run_records_the_file_it_changed(self):
        from jui_cli.commands.build_cmd import _record_generation
        from jui_cli.core import generation_manifest as gm

        run = self._run()
        self.files[1].write_text("// written by this run\n", encoding="utf-8")
        written, _keys, _m = _record_generation(
            _ConfigStub(self.root), run, self.files, bootstrap=False)
        self.assertEqual(["gen/B.kt"], written)
        self.assertEqual("1.8.11",
                         gm.load(self.root)["files"]["gen/B.kt"]["version"])

    def test_a_halted_run_that_wrote_nothing_claims_nothing(self):
        # The rule does NOT switch itself off. Bootstrap records a file
        # with no entry on the grounds that this run produced exactly those
        # bytes; it fires on the absence of a record, not on having
        # written, so a run that stopped before writing anything would
        # claim every unrecorded file in the project.
        from jui_cli.commands.build_cmd import _record_generation
        from jui_cli.core import generation_manifest as gm

        written, _keys, _m = _record_generation(
            _ConfigStub(self.root), self._run(), self.files, bootstrap=False)
        self.assertEqual([], written)
        self.assertEqual({}, gm.load(self.root).get("files") or {})

    def test_the_control_shows_bootstrap_would_have_claimed_them(self):
        # Same fixture, same untouched files, bootstrap left on: three
        # files this run never wrote come back stamped with its version.
        # Without this arm the one above passes on any fixture where the
        # files happen to be recorded already.
        from jui_cli.commands.build_cmd import _record_generation

        written, _keys, _m = _record_generation(
            _ConfigStub(self.root), self._run(), self.files, bootstrap=True)
        self.assertEqual(["gen/A.kt", "gen/B.kt", "gen/C.kt"], sorted(written))

    def test_a_completed_run_still_bootstraps(self):
        # The halted path must not change what a successful build records:
        # a stable project still gets a first entry.
        from jui_cli.commands.build_cmd import _record_generation

        written, _keys, _m = _record_generation(
            _ConfigStub(self.root), self._run(), self.files)
        self.assertEqual(3, len(written))


class StageFailureReportTests(unittest.TestCase):
    """Stages that failed are named after everything else, or not at all.

    A platform tool logs its own failures at its own terminus, which on a
    real build is dozens of lines above the end: one measured run put the
    colours failure at line 13 of 46 and finished with a success line and
    exit 0. A reader looks at the bottom, so that is where this repeats it.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "stage-failures.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self) -> str:
        import contextlib
        import io as _io

        from jui_cli.commands.build_cmd import (
            _print_stage_failures, _stage_failures,
        )

        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            _print_stage_failures(_stage_failures(self.ledger))
        return out.getvalue()

    def test_a_failed_stage_is_named_with_its_message(self):
        self.ledger.write_text(json.dumps([
            {"stage": "colors", "message": "colors.json could not be parsed"},
        ]), encoding="utf-8")
        out = self._run()
        self.assertIn("1 stage(s) did not complete", out)
        self.assertIn("colors", out)
        self.assertIn("could not be parsed", out)

    def test_a_healthy_run_prints_nothing(self):
        # The condition that keeps this off every downstream baseline: a
        # build with no failed stage must be byte-identical to before.
        self.assertEqual("", self._run())
        self.ledger.write_text("[]", encoding="utf-8")
        self.assertEqual("", self._run())

    def test_an_unreadable_ledger_is_not_an_error(self):
        # The tools may not have written one, and a build that succeeded
        # must not fail at the last line because of it.
        self.ledger.write_text("not json", encoding="utf-8")
        self.assertEqual("", self._run())


class ForeignGeneratedTreeTests(unittest.TestCase):
    """The record must not claim files another command writes.

    `jui build` finds generated files by walking for directories named
    `generated`, and that reaches trees the test tooling owns. The rule
    that records a file with no entry yet then stamps them with the running
    version — measured on a real face, 215 mock files carrying
    `generatedBy: "jui build"` at 1.8.12, from a command with no step that
    writes into a test tree.

    Two ages, measured from the entries themselves: the mocks arrived with
    the walk added in 1.8.11 and are stamped 1.8.12, while the 16 branch
    tests are stamped 1.8.10 — the lint collection's glob was already
    reaching those before the walk existed. So pruning the walk alone
    leaves the older half in place.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        web = self.root / "web"
        (web / "src" / "Layouts").mkdir(parents=True)
        for rel in ("src/generated", "src/models/generated",
                    "tests/unit/generated", "tests/mocks/generated"):
            d = web / rel
            d.mkdir(parents=True, exist_ok=True)
            (d / "a.ts").write_text("x\n", encoding="utf-8")
        (self.root / "jui.config.json").write_text(json.dumps({
            "platforms": {"web": {"root": "web", "layoutsDir": "src/Layouts"}},
            "mock": {"mockDir": "tests/mocks"},
        }), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _keys(self):
        from jui_cli.commands.build_cmd import _generated_paths
        return sorted(p.relative_to(self.root).as_posix()
                      for p in _generated_paths(_config(self.root)))

    def test_this_commands_own_output_is_still_recorded(self):
        keys = self._keys()
        self.assertIn("web/src/generated/a.ts", keys)
        self.assertIn("web/src/models/generated/a.ts", keys)

    def test_the_declared_mock_tree_is_not_claimed(self):
        self.assertNotIn("web/tests/mocks/generated/a.ts", self._keys())

    def test_the_branch_test_tree_is_not_claimed(self):
        # The older half. It arrives through the lint collection rather
        # than the walk, so a prune applied only to the walk's starting
        # points leaves it — which is what the first attempt did.
        self.assertNotIn("web/tests/unit/generated/a.ts", self._keys())

    def test_the_mock_tree_is_read_from_the_config_not_a_literal(self):
        # A project that puts its mocks somewhere else is covered too.
        config_path = self.root / "jui.config.json"
        config = json.loads(config_path.read_text())
        config["mock"]["mockDir"] = "spec/fixtures"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        moved = self.root / "web" / "spec" / "fixtures" / "generated"
        moved.mkdir(parents=True)
        (moved / "a.ts").write_text("x\n", encoding="utf-8")

        keys = self._keys()
        self.assertNotIn("web/spec/fixtures/generated/a.ts", keys)
        # And the one it no longer declares comes back into scope.
        self.assertIn("web/tests/mocks/generated/a.ts", keys)


class ClosingLineMatchesWhatHappenedTests(unittest.TestCase):
    """`Build completed successfully` is not printed above a list of things
    that did not complete.

    A platform tool can finish having skipped work — one bad layout does
    not stop the other seventeen — and the closing line said the build
    succeeded directly above the report of what had not. That is the same
    shape as a launcher discarding an exit code, one level up: the failure
    was already on screen and the last line contradicted it. Measured on a
    real build, where a layout that raised produced the error, the stage
    report, and `Build completed successfully` together.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "stage-failures.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _entries(self):
        from jui_cli.commands.build_cmd import _stage_failures
        return _stage_failures(self.ledger)

    def test_a_run_with_a_failed_stage_reports_entries(self):
        self.ledger.write_text(json.dumps([
            {"stage": "layout", "message": "Bad.json was not generated"},
        ]), encoding="utf-8")
        self.assertEqual(1, len(self._entries()))

    def test_a_healthy_run_reports_none(self):
        # The condition that keeps the closing line unchanged for everyone
        # whose build is fine, so no downstream baseline moves.
        self.assertEqual([], self._entries())
        self.ledger.write_text("[]", encoding="utf-8")
        self.assertEqual([], self._entries())

    def test_an_unreadable_ledger_reports_none(self):
        self.ledger.write_text("not json", encoding="utf-8")
        self.assertEqual([], self._entries())

    def test_the_decision_is_taken_before_the_line_is_printed(self):
        # Structural: reading the ledger after printing is what made the
        # contradiction possible, and it reads as correct either way.
        import ast
        import inspect

        from jui_cli.commands import build_cmd

        source = inspect.getsource(build_cmd.cmd_build)
        tree = ast.parse(source.lstrip())
        read_line = printed_line = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "_stage_failures" and read_line is None:
                    read_line = node.lineno
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "Build completed successfully" in node.value:
                    printed_line = node.lineno
        self.assertIsNotNone(read_line)
        self.assertIsNotNone(printed_line)
        self.assertLess(read_line, printed_line,
                        "the ledger is read after the closing line is "
                        "chosen, so the line cannot depend on it")
