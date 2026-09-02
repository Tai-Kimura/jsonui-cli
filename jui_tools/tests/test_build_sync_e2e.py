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
        """One build, with the snapshot on either side of distribution."""
        from jui_cli.core import generation_manifest as gm

        run = gm.GenerationRun(project_root=self.root, version="1.8.9")
        if observe_before_distribution:
            run.observe([self.file])
        # Distribution: the authored (un-normalised) form lands on top.
        self.file.write_text('{"authored": true}\n', encoding="utf-8")
        if not observe_before_distribution:
            run.observe([self.file])
        # The platform tool normalises it back to exactly what was there.
        self.file.write_text('{"normalised": true}\n', encoding="utf-8")
        return run.written([self.file])

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
        self.assertEqual(["gen/Home.json"], run.written([self.file]))
