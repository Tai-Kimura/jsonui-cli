"""Tests for the flatten-install phase of `jsonui-test validate`."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.install import (
    resolve_targets,
    flatten_install,
    InstallReport,
    _platform_matches,
)
from jsonui_test_cli.cli import main


SCREEN_TEST = {
    "type": "screen",
    "metadata": {"name": "sample"},
    "cases": [{"name": "case1", "steps": [{"action": "back"}]}],
}


def _write_test(path: Path, data=SCREEN_TEST):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _screen(name, platform=None, cases=None):
    data = {"type": "screen", "metadata": {"name": name}}
    if platform is not None:
        data["platform"] = platform
    data["cases"] = cases if cases is not None else [
        {"name": "case1", "steps": [{"action": "back"}]}]
    return data


def _case(name, platform=None):
    case = {"name": name}
    if platform is not None:
        case["platform"] = platform
    case["steps"] = [{"action": "back"}]
    return case


def _flow(name, steps, platform=None, setup=None, teardown=None, checkpoints=None):
    data = {"type": "flow", "metadata": {"name": name}}
    if platform is not None:
        data["platform"] = platform
    if setup is not None:
        data["setup"] = setup
    data["steps"] = steps
    if teardown is not None:
        data["teardown"] = teardown
    if checkpoints is not None:
        data["checkpoints"] = checkpoints
    return data


class TestPlatformMatches:
    """Normative membership spec for test/case-level `platform`.

    This matrix documents the shared semantics of the four implementations of
    this decision: `_platform_matches` here plus the runtime filters in all
    three drivers — iOS `TestModels.swift:377`, Android `TestModels.kt:249`,
    web `types.ts:275` (`platformIncludes`). All four do: missing -> all,
    scalar "all" -> everything, scalar token -> itself, array -> plain literal
    contains (no special-casing of "all"; the schema forbids "all" in arrays).
    Changing one implementation means changing all four.
    """

    MATRIX = [
        # (value, target, expected)
        (None, "ios", True),            # missing -> runs everywhere
        (None, "android", True),
        (None, "web", True),
        ("all", "ios", True),           # scalar "all" matches everything
        ("all", "android", True),
        ("all", "web", True),
        ("ios", "ios", True),           # scalar token matches itself only
        ("ios", "android", False),
        ("android", "android", True),
        ("android", "web", False),
        ("web", "web", True),
        ("web", "ios", False),
        (["ios"], "ios", True),         # array = literal contains
        (["ios"], "android", False),
        (["ios", "web"], "ios", True),
        (["ios", "web"], "web", True),
        (["ios", "web"], "android", False),
        (["android", "web"], "ios", False),
        (["all"], "ios", False),        # NO special-casing: ["all"] matches nothing
        (["all"], "android", False),
        (["all"], "web", False),
        ([], "ios", False),             # empty array matches nothing (schema: minItems 1)
    ]

    @pytest.mark.parametrize("value,target,expected", MATRIX)
    def test_membership_matrix(self, value, target, expected):
        assert _platform_matches(value, target) is expected


class TestResolveTargets:
    def test_reads_documented_config_shape(self, tmp_path):
        cfg = {
            "install": {
                "ios": {"target_dir": "ios-app/UITests/GeneratedTests"},
                "android": {"assets_dir": "android-app/app/src/androidTest/assets/tests"},
            }
        }
        targets = dict(resolve_targets(cfg, tmp_path))
        assert targets["ios"] == tmp_path / "ios-app/UITests/GeneratedTests"
        assert targets["android"] == tmp_path / "android-app/app/src/androidTest/assets/tests"

    def test_accepts_plain_string_and_aliases(self, tmp_path):
        cfg = {"install": {"ios": "a/b", "web": {"dir": "c/d"}}}
        targets = dict(resolve_targets(cfg, tmp_path))
        assert targets["ios"] == tmp_path / "a/b"
        assert targets["web"] == tmp_path / "c/d"

    def test_absolute_dest_kept(self, tmp_path):
        cfg = {"install": {"ios": {"target_dir": str(tmp_path / "abs")}}}
        targets = dict(resolve_targets(cfg, Path("/somewhere/else")))
        assert targets["ios"] == tmp_path / "abs"

    def test_empty_config_no_targets(self, tmp_path):
        assert resolve_targets({}, tmp_path) == []
        assert resolve_targets(None, tmp_path) == []
        assert resolve_targets({"install": {"ios": {}}}, tmp_path) == []

    def test_platform_token_defaults_to_install_key(self, tmp_path):
        cfg = {"install": {"android": {"assets_dir": "a"}}}
        assert resolve_targets(cfg, tmp_path) == [("android", tmp_path / "a")]

    def test_explicit_platform_key_overrides_install_key(self, tmp_path):
        cfg = {"install": {
            "ios-uitests": {"target_dir": "x", "platform": "ios"},
            "web": {"dir": "y"},
        }}
        targets = resolve_targets(cfg, tmp_path)
        assert targets == [("ios", tmp_path / "x"), ("web", tmp_path / "y")]


class TestFlattenInstall:
    def test_copies_flat(self, tmp_path):
        src = _write_test(tmp_path / "tests/screens/login/login.test.json")
        dest = tmp_path / "out"
        report = flatten_install([src], [("ios", dest)])
        assert (dest / "login.test.json").exists()
        assert not report.has_collision
        assert len(report.copied) == 1

    def test_full_sync_removes_stale(self, tmp_path):
        dest = tmp_path / "out"
        dest.mkdir()
        (dest / "stale.test.json").write_text("{}", encoding="utf-8")
        (dest / "keepme.txt").write_text("x", encoding="utf-8")
        src = _write_test(tmp_path / "tests/screens/home/home.test.json")

        report = flatten_install([src], [("android", dest)])
        assert not (dest / "stale.test.json").exists()  # stale removed
        assert (dest / "keepme.txt").exists()             # non-test left alone
        assert (dest / "home.test.json").exists()
        assert report.removed == 1

    def test_collision_aborts(self, tmp_path):
        a = _write_test(tmp_path / "tests/screens/x/dup.test.json")
        b = _write_test(tmp_path / "tests/flows/y/dup.test.json")
        dest = tmp_path / "out"
        report = flatten_install([a, b], [("ios", dest)])
        assert report.has_collision
        assert not dest.exists()  # nothing written when collision detected


class TestPlatformShaping:
    """Pass 1: per-file, purely subtractive shaping per target platform."""

    def test_android_only_dropped_from_ios_target(self, tmp_path):
        src = _write_test(tmp_path / "tests/screens/gallery/gallery.test.json",
                          _screen("gallery", platform="android"))
        ios, android = tmp_path / "ios", tmp_path / "android"
        report = flatten_install([src], [("ios", ios), ("android", android)])
        assert not (ios / "gallery.test.json").exists()
        assert (android / "gallery.test.json").exists()
        assert report.skipped_files["ios"] == [str(src)]
        assert "android" not in report.skipped_files
        assert report.installed["android"] == [str(android / "gallery.test.json")]
        assert "ios" not in report.installed

    def test_web_only_sweep_dropped_from_native_targets(self, tmp_path):
        # Responsive-plan interplay: setViewport sweep tests tagged web-only
        # must be shaped out of iOS/Android bundles.
        src = _write_test(tmp_path / "tests/screens/sweep/sweep.test.json",
                          _screen("sweep", platform="web"))
        ios, android, web = tmp_path / "ios", tmp_path / "android", tmp_path / "web"
        report = flatten_install(
            [src], [("ios", ios), ("android", android), ("web", web)])
        assert not (ios / "sweep.test.json").exists()
        assert not (android / "sweep.test.json").exists()
        assert (web / "sweep.test.json").exists()
        assert report.skipped_files["ios"] == [str(src)]
        assert report.skipped_files["android"] == [str(src)]

    def test_test_level_platform_array(self, tmp_path):
        screen = _write_test(tmp_path / "tests/screens/s/s.test.json",
                             _screen("s", platform=["android", "web"]))
        flow = _write_test(tmp_path / "tests/flows/f/f.test.json",
                           _flow("f", [{"action": "back"}], platform=["android", "web"]))
        ios, android = tmp_path / "ios", tmp_path / "android"
        flatten_install([screen, flow], [("ios", ios), ("android", android)])
        assert not (ios / "s.test.json").exists()
        assert not (ios / "f.test.json").exists()
        assert (android / "s.test.json").exists()
        assert (android / "f.test.json").exists()

    def test_all_and_absent_install_everywhere_byte_for_byte(self, tmp_path):
        absent = _write_test(tmp_path / "tests/screens/a/a.test.json", _screen("a"))
        tagged = _write_test(tmp_path / "tests/screens/b/b.test.json",
                             _screen("b", platform="all"))
        targets = [(p, tmp_path / p) for p in ("ios", "android", "web")]
        report = flatten_install([absent, tagged], targets)
        for platform, dest in targets:
            assert (dest / "a.test.json").read_bytes() == absent.read_bytes()
            assert (dest / "b.test.json").read_bytes() == tagged.read_bytes()
        assert not report.skipped_files
        assert not report.pruned_cases

    def test_mixed_case_pruning(self, tmp_path):
        data = _screen("login", cases=[
            _case("common"),
            _case("biometric", platform="android"),
            _case("hover", platform=["web"]),
        ])
        src = _write_test(tmp_path / "tests/screens/login/login.test.json", data)
        ios, android = tmp_path / "ios", tmp_path / "android"
        report = flatten_install([src], [("ios", ios), ("android", android)])

        ios_cases = [c["name"] for c in
                     json.loads((ios / "login.test.json").read_text("utf-8"))["cases"]]
        android_cases = [c["name"] for c in
                         json.loads((android / "login.test.json").read_text("utf-8"))["cases"]]
        assert ios_cases == ["common"]
        assert android_cases == ["common", "biometric"]
        assert report.pruned_cases["ios"] == [(str(src), "biometric"), (str(src), "hover")]
        assert report.pruned_cases["android"] == [(str(src), "hover")]

    def test_case_level_platform_kept_not_stripped(self, tmp_path):
        # Shaping is subtractive: surviving cases keep their platform field.
        data = _screen("login", cases=[_case("common"), _case("touch", platform=["ios", "android"])])
        src = _write_test(tmp_path / "tests/screens/login/login.test.json", data)
        ios = tmp_path / "ios"
        flatten_install([src], [("ios", ios), ("web", tmp_path / "web")])
        out = json.loads((ios / "login.test.json").read_text("utf-8"))
        assert out["cases"][1]["platform"] == ["ios", "android"]
        assert out.get("platform") is None  # test-level platform not rewritten in

    def test_empty_after_prune_skips_file(self, tmp_path):
        data = _screen("droid", cases=[_case("a", platform="android"),
                                       _case("b", platform=["android"])])
        src = _write_test(tmp_path / "tests/screens/droid/droid.test.json", data)
        ios = tmp_path / "ios"
        report = flatten_install([src], [("ios", ios)])
        assert not (ios / "droid.test.json").exists()
        assert report.skipped_files["ios"] == [str(src)]

    def test_unmodified_file_byte_copied_not_reserialized(self, tmp_path):
        # Odd formatting (4-space indent, trailing newline, key order) must
        # survive untouched when nothing is pruned.
        raw = ('{\n    "cases": [\n        {"name": "c1", "steps": [{"action": "back"}]}\n    ],\n'
               '    "type": "screen",\n    "metadata": {"name": "odd"}\n}\n')
        src = tmp_path / "tests/screens/odd/odd.test.json"
        src.parent.mkdir(parents=True)
        src.write_text(raw, encoding="utf-8")
        ios = tmp_path / "ios"
        flatten_install([src], [("ios", ios)])
        assert (ios / "odd.test.json").read_bytes() == raw.encode("utf-8")

    def test_pruned_file_preserves_key_order(self, tmp_path):
        data = {
            "type": "screen",
            "platform": ["ios", "android"],
            "metadata": {"name": "ordered"},
            "launch": {"clearState": True},
            "cases": [_case("common"), _case("droid", platform="android")],
            "teardown": [{"action": "back"}],
        }
        src = _write_test(tmp_path / "tests/screens/o/o.test.json", data)
        ios = tmp_path / "ios"
        flatten_install([src], [("ios", ios)])
        out = json.loads((ios / "o.test.json").read_text("utf-8"))
        assert list(out.keys()) == list(data.keys())
        assert out["platform"] == ["ios", "android"]  # test-level value untouched
        assert [c["name"] for c in out["cases"]] == ["common"]

    def test_idempotent_install_twice_stable(self, tmp_path):
        srcs = [
            _write_test(tmp_path / "tests/screens/a/a.test.json",
                        _screen("a", cases=[_case("c"), _case("d", platform="android")])),
            _write_test(tmp_path / "tests/flows/f/f.test.json",
                        _flow("f", [{"file": "a"}])),
        ]
        targets = [("ios", tmp_path / "ios"), ("android", tmp_path / "android")]

        def snapshot():
            return {
                str(p.relative_to(tmp_path)): p.read_bytes()
                for t in ("ios", "android")
                for p in sorted((tmp_path / t).glob("*.test.json"))
            }

        flatten_install(srcs, targets)
        first = snapshot()
        flatten_install(srcs, targets)
        assert snapshot() == first
        assert first  # sanity: something was installed


class TestFlowReferenceClosure:
    """Pass 2: whole-flow drop when a fileStep reference was shaped out."""

    def _sources(self, tmp_path, flow_data, screen_data=None):
        screen = _write_test(
            tmp_path / "tests/screens/login/login.test.json",
            screen_data if screen_data is not None else _screen("login", platform="android"))
        flow = _write_test(tmp_path / "tests/flows/checkout/checkout.test.json", flow_data)
        return [screen, flow]

    def test_dangling_file_ref_drops_whole_flow(self, tmp_path):
        srcs = self._sources(tmp_path, _flow("checkout", [{"file": "login"},
                                                          {"action": "back"}]))
        ios, android = tmp_path / "ios", tmp_path / "android"
        report = flatten_install(srcs, [("ios", ios), ("android", android)])
        assert not (ios / "checkout.test.json").exists()
        assert (android / "checkout.test.json").exists()
        assert report.skipped_flows["ios"] == ["checkout → login"]
        assert "android" not in report.skipped_flows

    def test_dangling_named_case_drops_flow(self, tmp_path):
        screen = _screen("login", cases=[_case("common"),
                                         _case("biometric", platform="android")])
        srcs = self._sources(
            tmp_path, _flow("checkout", [{"file": "login", "case": "biometric"}]),
            screen_data=screen)
        ios, android = tmp_path / "ios", tmp_path / "android"
        report = flatten_install(srcs, [("ios", ios), ("android", android)])
        # File-level survival is not enough: the named case was pruned on iOS.
        assert (ios / "login.test.json").exists()
        assert not (ios / "checkout.test.json").exists()
        assert (android / "checkout.test.json").exists()
        assert report.skipped_flows["ios"] == ["checkout → login[biometric]"]

    def test_dangling_case_in_cases_selector_drops_flow(self, tmp_path):
        screen = _screen("login", cases=[_case("common"),
                                         _case("biometric", platform="android")])
        srcs = self._sources(
            tmp_path,
            _flow("checkout", [{"file": "login", "cases": ["common", "biometric"]}]),
            screen_data=screen)
        ios = tmp_path / "ios"
        report = flatten_install(srcs, [("ios", ios)])
        assert not (ios / "checkout.test.json").exists()
        assert report.skipped_flows["ios"] == ["checkout → login[biometric]"]

    def test_surviving_case_selector_keeps_flow(self, tmp_path):
        screen = _screen("login", cases=[_case("common"),
                                         _case("biometric", platform="android")])
        srcs = self._sources(
            tmp_path, _flow("checkout", [{"file": "login", "case": "common"}]),
            screen_data=screen)
        ios = tmp_path / "ios"
        report = flatten_install(srcs, [("ios", ios)])
        assert (ios / "checkout.test.json").exists()
        assert "ios" not in report.skipped_flows

    def test_dangling_ref_in_setup_drops_flow(self, tmp_path):
        srcs = self._sources(
            tmp_path, _flow("checkout", [{"action": "back"}],
                            setup=[{"file": "login"}]))
        ios = tmp_path / "ios"
        report = flatten_install(srcs, [("ios", ios)])
        assert not (ios / "checkout.test.json").exists()
        assert report.skipped_flows["ios"] == ["checkout → login"]

    def test_dangling_ref_in_teardown_drops_flow(self, tmp_path):
        srcs = self._sources(
            tmp_path, _flow("checkout", [{"action": "back"}],
                            teardown=[{"file": "login"}]))
        ios = tmp_path / "ios"
        report = flatten_install(srcs, [("ios", ios)])
        assert not (ios / "checkout.test.json").exists()
        assert report.skipped_flows["ios"] == ["checkout → login"]

    def test_self_gated_file_step_does_not_drop_flow(self, tmp_path):
        # when.platform excludes the target -> the runtime skips the step, so
        # the dangling reference is harmless and the flow survives.
        srcs = self._sources(
            tmp_path,
            _flow("checkout", [{"file": "login", "when": {"platform": "android"}},
                               {"action": "back"}]))
        ios = tmp_path / "ios"
        report = flatten_install(srcs, [("ios", ios)])
        assert (ios / "checkout.test.json").exists()
        assert "ios" not in report.skipped_flows

    def test_self_gated_array_platform_does_not_drop_flow(self, tmp_path):
        srcs = self._sources(
            tmp_path,
            _flow("checkout", [{"file": "login",
                                "when": {"platform": ["android", "web"]}},
                               {"action": "back"}]))
        ios = tmp_path / "ios"
        report = flatten_install(srcs, [("ios", ios)])
        assert (ios / "checkout.test.json").exists()
        assert "ios" not in report.skipped_flows

    def test_ref_never_in_source_set_is_left_to_validator(self, tmp_path):
        # A reference that never existed in the SSoT is a validation warning,
        # not a shaping casualty — the flow is not dropped.
        flow = _write_test(tmp_path / "tests/flows/checkout/checkout.test.json",
                           _flow("checkout", [{"file": "no_such_screen"}]))
        ios = tmp_path / "ios"
        report = flatten_install([flow], [("ios", ios)])
        assert (ios / "checkout.test.json").exists()
        assert "ios" not in report.skipped_flows

    def test_screens_prefix_spelling_resolves_like_bare_name(self, tmp_path):
        # Loaders resolve by basename with screens/ auto-lookup; the closure
        # must treat 'screens/login' and 'login' as the same reference.
        srcs = self._sources(tmp_path,
                             _flow("checkout", [{"file": "screens/login"}]))
        ios = tmp_path / "ios"
        report = flatten_install(srcs, [("ios", ios)])
        assert not (ios / "checkout.test.json").exists()
        assert report.skipped_flows["ios"] == ["checkout → login"]

    def test_flow_steps_never_pruned_file_byte_identical(self, tmp_path):
        # Gated steps and checkpoints[].afterStep indexes must stay intact —
        # when nothing is dropped, the flow file is byte-copied.
        flow_data = _flow(
            "journey",
            [{"action": "back"},
             {"action": "back", "when": {"platform": "android"}},
             {"file": "login", "when": {"platform": ["android"]}},
             {"assert": "visible", "id": "done"}],
            checkpoints=[{"afterStep": 2, "assert": [{"assert": "visible", "id": "x"}]}],
        )
        srcs = self._sources(tmp_path, flow_data)
        ios = tmp_path / "ios"
        flatten_install(srcs, [("ios", ios)])
        flow_src = srcs[1]
        assert (ios / "checkout.test.json").read_bytes() == flow_src.read_bytes()
        out = json.loads((ios / "checkout.test.json").read_text("utf-8"))
        assert len(out["steps"]) == 4
        assert out["checkpoints"][0]["afterStep"] == 2

    def test_flow_referencing_dropped_flow_cascades(self, tmp_path):
        # Dropping a flow can dangle references in flows that reference it;
        # the closure runs to a fixed point.
        screen = _write_test(tmp_path / "tests/screens/login/login.test.json",
                             _screen("login", platform="android"))
        inner = _write_test(tmp_path / "tests/flows/inner/inner.test.json",
                            _flow("inner", [{"file": "login"}]))
        outer = _write_test(tmp_path / "tests/flows/outer/outer.test.json",
                            _flow("outer", [{"file": "inner"}]))
        ios = tmp_path / "ios"
        report = flatten_install([screen, inner, outer], [("ios", ios)])
        assert not (ios / "inner.test.json").exists()
        assert not (ios / "outer.test.json").exists()
        assert set(report.skipped_flows["ios"]) == {"inner → login", "outer → inner"}


class TestPerDestCollision:
    def test_same_basename_disjoint_platforms_no_abort(self, tmp_path):
        # An ios-only foo and an android-only foo never share a destination.
        a = _write_test(tmp_path / "tests/screens/x/foo.test.json",
                        _screen("foo", platform="ios"))
        b = _write_test(tmp_path / "tests/screens/y/foo.test.json",
                        _screen("foo", platform="android"))
        ios, android = tmp_path / "ios", tmp_path / "android"
        report = flatten_install([a, b], [("ios", ios), ("android", android)])
        assert not report.has_collision
        assert json.loads((ios / "foo.test.json").read_text("utf-8"))["platform"] == "ios"
        assert json.loads((android / "foo.test.json").read_text("utf-8"))["platform"] == "android"

    def test_same_basename_same_dest_still_aborts(self, tmp_path):
        a = _write_test(tmp_path / "tests/screens/x/foo.test.json",
                        _screen("foo", platform="ios"))
        b = _write_test(tmp_path / "tests/screens/y/foo.test.json",
                        _screen("foo", platform=["ios", "web"]))
        ios = tmp_path / "ios"
        report = flatten_install([a, b], [("ios", ios)])
        assert report.has_collision
        assert report.collisions == [("ios", "foo.test.json", [str(a), str(b)])]
        assert not ios.exists()  # nothing written when collision detected

    def test_shaped_to_empty_file_does_not_collide(self, tmp_path):
        # A file that shapes out entirely never reaches the destination, so it
        # cannot trigger a (stale) collision there.
        a = _write_test(tmp_path / "tests/screens/x/foo.test.json",
                        _screen("foo", platform="android"))
        b = _write_test(tmp_path / "tests/screens/y/foo.test.json",
                        _screen("foo", platform="ios"))
        ios = tmp_path / "ios"
        report = flatten_install([a, b], [("ios", ios)])
        assert not report.has_collision
        assert json.loads((ios / "foo.test.json").read_text("utf-8"))["platform"] == "ios"


class TestValidateInstallIntegration:
    def _run(self, cwd, argv):
        old = os.getcwd()
        os.chdir(cwd)
        try:
            with patch("sys.argv", argv):
                return main()
        finally:
            os.chdir(old)

    def test_validate_installs_on_success(self, tmp_path):
        _write_test(tmp_path / "tests/screens/login/login.test.json")
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "test": {"install": {
                "ios": {"target_dir": "ios/GeneratedTests"},
                "android": {"assets_dir": "android/assets/tests"},
            }}
        }), encoding="utf-8")

        rc = self._run(tmp_path, ["jsonui-test", "validate", "tests"])
        assert rc == 0
        assert (tmp_path / "ios/GeneratedTests/login.test.json").exists()
        assert (tmp_path / "android/assets/tests/login.test.json").exists()

    def test_no_install_flag_skips(self, tmp_path):
        _write_test(tmp_path / "tests/screens/login/login.test.json")
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "test": {"install": {"ios": {"target_dir": "ios/GeneratedTests"}}}
        }), encoding="utf-8")

        rc = self._run(tmp_path, ["jsonui-test", "validate", "tests", "--no-install"])
        assert rc == 0
        assert not (tmp_path / "ios/GeneratedTests").exists()

    def test_no_config_is_validate_only(self, tmp_path):
        _write_test(tmp_path / "tests/screens/login/login.test.json")
        rc = self._run(tmp_path, ["jsonui-test", "validate", "tests"])
        assert rc == 0  # validate passes, install is a no-op

    def test_invalid_test_blocks_install(self, tmp_path):
        _write_test(tmp_path / "tests/screens/bad/bad.test.json",
                    {"type": "screen", "cases": [{"name": "c", "steps": [{"action": "nope"}]}]})
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "test": {"install": {"ios": {"target_dir": "ios/GeneratedTests"}}}
        }), encoding="utf-8")

        rc = self._run(tmp_path, ["jsonui-test", "validate", "tests"])
        assert rc == 1
        assert not (tmp_path / "ios/GeneratedTests").exists()

    def test_validate_installs_shaped_per_platform(self, tmp_path):
        _write_test(tmp_path / "tests/screens/common/common.test.json",
                    _screen("common"))
        _write_test(tmp_path / "tests/screens/droid/droid.test.json",
                    _screen("droid", platform="android"))
        _write_test(tmp_path / "tests/flows/checkout/checkout.test.json",
                    _flow("checkout", [{"file": "droid"}]))
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "test": {"install": {
                "ios": {"target_dir": "ios/GeneratedTests"},
                "android": {"assets_dir": "android/assets/tests"},
            }}
        }), encoding="utf-8")

        rc = self._run(tmp_path, ["jsonui-test", "validate", "tests"])
        assert rc == 0
        ios = tmp_path / "ios/GeneratedTests"
        android = tmp_path / "android/assets/tests"
        assert (ios / "common.test.json").exists()
        assert not (ios / "droid.test.json").exists()      # android-only shaped out
        assert not (ios / "checkout.test.json").exists()   # flow ref dangling on ios
        assert (android / "droid.test.json").exists()
        assert (android / "checkout.test.json").exists()

    def test_invalid_platform_value_fails_validate_before_install(self, tmp_path):
        _write_test(tmp_path / "tests/screens/bad/bad.test.json",
                    _screen("bad", platform="ios-swiftui"))
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "test": {"install": {"ios": {"target_dir": "ios/GeneratedTests"}}}
        }), encoding="utf-8")

        rc = self._run(tmp_path, ["jsonui-test", "validate", "tests"])
        assert rc == 1
        assert not (tmp_path / "ios/GeneratedTests").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
