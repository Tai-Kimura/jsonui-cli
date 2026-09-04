"""Tests for the artifacts module (pull ios/android, status, CLI wiring)."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import artifacts
from jsonui_test_cli.artifacts import (
    ArtifactsConfigError,
    PullResult,
    collect_files,
    find_xcresult,
    pull_android,
    pull_exit_code,
    pull_ios,
    resolve_out_root,
    status,
    update_latest_symlink,
)
from jsonui_test_cli.cli import main


FIXED_STAMP = "20260101-000000"


def _cp(cmd, rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(cmd, rc, stdout, stderr)


# -- iOS helpers --------------------------------------------------------------

MANIFEST = [
    {
        "testIdentifier": "LoginTests/testLogin()",
        "attachments": [
            {"exportedFileName": "1_shot.png", "suggestedHumanReadableName": "launch_screen"},
            {"exportedFileName": "2_video.mp4", "suggestedHumanReadableName": "run_recording"},
            {"exportedFileName": "3_blob.dat", "suggestedHumanReadableName": "raw_dump"},
        ],
    },
]


def make_xcresult(tmp_path, name="Run.xcresult", mtime=None):
    """Create a fake .xcresult bundle dir with a deterministic mtime."""
    xc = tmp_path / name
    xc.mkdir(parents=True, exist_ok=True)
    if mtime is not None:
        os.utime(xc, (mtime, mtime))
    return xc


def make_xcrun_fake(exported_files, manifest=MANIFEST, rc=0, stderr=""):
    """Fake _run for `xcrun xcresulttool export attachments`.

    Writes the given exported files (and manifest.json unless None) into the
    --output-path directory.
    """
    def fake(cmd, **kw):
        assert cmd[:4] == ["xcrun", "xcresulttool", "export", "attachments"], cmd
        if rc != 0:
            return _cp(cmd, rc, "", stderr)
        out = Path(cmd[cmd.index("--output-path") + 1])
        out.mkdir(parents=True, exist_ok=True)
        for name in exported_files:
            (out / name).write_bytes(b"data:" + name.encode())
        if manifest is not None:
            (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return _cp(cmd)
    return fake


def stamp_of(xcresult):
    return datetime.fromtimestamp(Path(xcresult).stat().st_mtime).strftime("%Y%m%d-%H%M%S")


# -- Android helpers -----------------------------------------------------------

def make_adb_fake(existing_roots, calls, pulled_files=("shot.png", "clip.mp4"),
                  listings=None):
    """Fake _run for adb: ls succeeds only for existing_roots, pull writes files.

    ``listings`` maps a root to the ``ls`` stdout it should answer with (default
    ``shot.png``). A pull of ``<root>/.`` writes ``pulled_files`` into the
    destination; a pull of ``<root>/<entry>`` — the entry-wise legacy path —
    writes them under ``<dest>/<entry>/`` the way adb materialises a directory.
    """
    listings = listings or {}

    def fake(cmd, **kw):
        calls.append(list(cmd))
        assert cmd[0] == "adb", cmd
        if "shell" in cmd and "ls" in cmd:
            root = cmd[-1]
            if root in existing_roots:
                return _cp(cmd, 0, listings.get(root, "shot.png\n"))
            return _cp(cmd, 1, "", f"ls: {root}: No such file or directory")
        if "pull" in cmd:
            src, dest = cmd[-2], Path(cmd[-1])
            if not src.endswith("/."):
                dest = dest / src.rsplit("/", 1)[-1]
            dest.mkdir(parents=True, exist_ok=True)
            for name in pulled_files:
                (dest / name).write_bytes(b"x")
            return _cp(cmd)
        if "rm" in cmd:
            return _cp(cmd)
        raise AssertionError(f"unexpected adb command: {cmd}")
    return fake


ANDROID_CFG = {"artifacts": {"android": {"appId": "com.example.app"}}}
SDCARD_ROOT = "/sdcard/Android/data/com.example.app/files/jsonui-artifacts"
TMP_ROOT = "/data/local/tmp/jsonui-artifacts"
SCOPED_ROOT = f"{TMP_ROOT}/com.example.app"


def _pulls(calls):
    return [c for c in calls if "pull" in c]


def _rms(calls):
    return [c for c in calls if "rm" in c]


# -- tests: iOS ------------------------------------------------------------------

class TestPullIos:
    def test_manifest_layout_classification_and_naming(self, tmp_path, monkeypatch):
        xc = make_xcresult(tmp_path, mtime=time.time() - 100)
        monkeypatch.setattr(artifacts, "_run",
                            make_xcrun_fake(["1_shot.png", "2_video.mp4", "3_blob.dat"]))
        cfg = {"artifacts": {"ios": {"xcresult": str(xc)}}}
        out = tmp_path / "out"

        result = pull_ios(cfg, tmp_path, out)

        stamp = stamp_of(xc)
        base = out / "ios" / stamp / "LoginTests" / "testLogin()"
        assert (base / "screenshots" / "launch_screen.png").is_file()
        assert (base / "recordings" / "run_recording.mp4").is_file()
        assert (base / "other" / "raw_dump.dat").is_file()
        assert result.stamp_dir == str(out / "ios" / stamp)
        assert len(result.files) == 3
        assert result.skipped == []

    def test_duplicate_human_names_get_numeric_suffix(self, tmp_path, monkeypatch):
        manifest = [{
            "testIdentifier": "SuiteA/testDup()",
            "attachments": [
                {"exportedFileName": "1.png", "suggestedHumanReadableName": "shot"},
                {"exportedFileName": "2.png", "suggestedHumanReadableName": "shot"},
            ],
        }]
        xc = make_xcresult(tmp_path)
        monkeypatch.setattr(artifacts, "_run", make_xcrun_fake(["1.png", "2.png"], manifest))
        cfg = {"artifacts": {"ios": {"xcresult": str(xc)}}}

        result = pull_ios(cfg, tmp_path, tmp_path / "out")

        shots = tmp_path / "out" / "ios" / stamp_of(xc) / "SuiteA" / "testDup()" / "screenshots"
        assert (shots / "shot.png").is_file()
        assert (shots / "shot_1.png").is_file()
        assert len(result.files) == 2

    def test_missing_manifest_falls_back_to_unsorted(self, tmp_path, monkeypatch):
        xc = make_xcresult(tmp_path)
        monkeypatch.setattr(artifacts, "_run",
                            make_xcrun_fake(["a.png", "b.mp4"], manifest=None))
        cfg = {"artifacts": {"ios": {"xcresult": str(xc)}}}

        result = pull_ios(cfg, tmp_path, tmp_path / "out")

        unsorted = tmp_path / "out" / "ios" / stamp_of(xc) / "unsorted"
        assert (unsorted / "a.png").is_file()
        assert (unsorted / "b.mp4").is_file()
        assert len(result.files) == 2

    def test_no_xcresult_found_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(artifacts, "_run", make_xcrun_fake([]))
        cfg = {"artifacts": {"ios": {"xcresult": str(tmp_path / "nope" / "*.xcresult")}}}

        result = pull_ios(cfg, tmp_path, tmp_path / "out")

        assert result.files == []
        assert result.stamp_dir is None
        assert any("no .xcresult" in s for s in result.skipped)

    def test_export_failure_surfaces_stderr(self, tmp_path, monkeypatch):
        xc = make_xcresult(tmp_path)
        monkeypatch.setattr(artifacts, "_run",
                            make_xcrun_fake([], rc=1, stderr="requires --test-id"))
        cfg = {"artifacts": {"ios": {"xcresult": str(xc)}}}

        result = pull_ios(cfg, tmp_path, tmp_path / "out")

        assert result.files == []
        assert any("requires --test-id" in s for s in result.skipped)

    def test_override_beats_config(self, tmp_path, monkeypatch):
        cfg_xc = make_xcresult(tmp_path, "cfg.xcresult")
        override_xc = make_xcresult(tmp_path, "override.xcresult")
        seen = {}

        def fake(cmd, **kw):
            seen["path"] = cmd[cmd.index("--path") + 1]
            return make_xcrun_fake(["a.png"], manifest=None)(cmd, **kw)

        monkeypatch.setattr(artifacts, "_run", fake)
        cfg = {"artifacts": {"ios": {"xcresult": str(cfg_xc)}}}
        pull_ios(cfg, tmp_path, tmp_path / "out", xcresult_override=str(override_xc))
        assert seen["path"] == str(override_xc)


class TestXcresultDiscovery:
    def test_newest_mtime_wins_for_glob(self, tmp_path):
        now = time.time()
        make_xcresult(tmp_path, "old.xcresult", mtime=now - 1000)
        newer = make_xcresult(tmp_path, "new.xcresult", mtime=now - 10)

        found = find_xcresult({"xcresult": str(tmp_path / "*.xcresult")})
        assert found == newer

    def test_explicit_path(self, tmp_path):
        xc = make_xcresult(tmp_path, "Run.xcresult")
        assert find_xcresult({"xcresult": str(xc)}) == xc

    def test_no_match_returns_none(self, tmp_path):
        assert find_xcresult({"xcresult": str(tmp_path / "*.xcresult")}) is None


# -- tests: Android ---------------------------------------------------------------

class TestPullAndroid:
    @pytest.fixture(autouse=True)
    def _pin_adb(self, monkeypatch):
        # Resolution is find_adb's business (tested separately); pin it so the
        # fake's `cmd[0] == "adb"` assertions stay deterministic on any host.
        monkeypatch.setattr(artifacts, "find_adb", lambda cfg=None: "adb")

    def test_adb_unresolvable_is_skipped_with_guidance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(artifacts, "find_adb", lambda cfg=None: None)

        result = pull_android(ANDROID_CFG, tmp_path, tmp_path / "out")

        assert result.files == []
        assert any("adb not found" in s and "test.artifacts.android.adb" in s
                   for s in result.skipped)

    def test_merges_existing_roots_into_single_stamp_dir(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake({SDCARD_ROOT}, calls))
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)
        out = tmp_path / "out"

        result = pull_android(ANDROID_CFG, tmp_path, out)

        stamp_dir = out / "android" / FIXED_STAMP
        assert result.stamp_dir == str(stamp_dir)
        assert (stamp_dir / "shot.png").is_file()
        assert len(result.files) == 2
        # non-existing root skipped silently, no pull attempted for it
        pulls = [c for c in calls if "pull" in c]
        assert len(pulls) == 1
        assert pulls[0][-2] == f"{SDCARD_ROOT}/."
        assert result.skipped == []

    def test_clean_triggers_rm_rf(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake({SDCARD_ROOT}, calls))
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)

        pull_android(ANDROID_CFG, tmp_path, tmp_path / "out", clean=True)

        assert ["adb", "shell", "rm", "-rf", SDCARD_ROOT] in calls

    def test_no_clean_by_default(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake({SDCARD_ROOT}, calls))
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)

        pull_android(ANDROID_CFG, tmp_path, tmp_path / "out")

        assert not any("rm" in c for c in calls)

    def test_serial_override_is_used(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake({SDCARD_ROOT}, calls))
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)

        pull_android(ANDROID_CFG, tmp_path, tmp_path / "out", serial_override="emulator-5560")

        assert all(c[:3] == ["adb", "-s", "emulator-5560"] for c in calls)

    def test_missing_app_id_raises_clear_error(self, tmp_path):
        with pytest.raises(ArtifactsConfigError, match="test.artifacts.android.appId"):
            pull_android({"artifacts": {}}, tmp_path, tmp_path / "out")

    def test_adb_missing_is_skipped_not_raised(self, tmp_path, monkeypatch):
        def no_adb(cmd, **kw):
            raise FileNotFoundError("adb")
        monkeypatch.setattr(artifacts, "_run", no_adb)

        result = pull_android(ANDROID_CFG, tmp_path, tmp_path / "out")

        assert result.files == []
        assert any("adb not found" in s for s in result.skipped)

    def test_no_device_is_skipped(self, tmp_path, monkeypatch):
        def fake(cmd, **kw):
            return _cp(cmd, 1, "", "adb: no devices/emulators found")
        monkeypatch.setattr(artifacts, "_run", fake)

        result = pull_android(ANDROID_CFG, tmp_path, tmp_path / "out")

        assert result.files == []
        assert any("no devices" in s for s in result.skipped)

    def test_neither_root_exists(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake(set(), calls))
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)

        result = pull_android(ANDROID_CFG, tmp_path, tmp_path / "out")

        assert result.files == []
        assert result.stamp_dir is None
        assert any("no jsonui-artifacts" in s for s in result.skipped)


class TestPullAndroidMirrorScope:
    """The uninstall-surviving mirror lives outside the app dir, so the path is
    the only thing that can say whose runs they are. Consumer measurement on a
    shared emulator (2026-09-04): one app's ``pull --clean`` took 74 dirs /
    71 MB of the OTHER app's runs off the device, because the flat legacy root
    ``/data/local/tmp/jsonui-artifacts`` had no app dimension. Driver >= 1.8.9
    writes ``<root>/<package>``; the CLI pulls and cleans only that, and reads
    the flat root suite-by-suite without ever cleaning it.
    """

    @pytest.fixture(autouse=True)
    def _pin(self, monkeypatch):
        monkeypatch.setattr(artifacts, "find_adb", lambda cfg=None: "adb")
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)

    def test_roots_are_own_app_only_except_the_flat_legacy_root(self):
        roots = artifacts._android_roots("com.example.app")
        assert roots == [
            (SDCARD_ROOT, True),
            (SCOPED_ROOT, True),
            (TMP_ROOT, False),
        ]
        # the ONLY root that is not cleanable is the one without an app dimension
        assert [r for r, cleanable in roots if not cleanable] == [TMP_ROOT]

    def test_scoped_mirror_is_pulled_and_cleaned(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake({SCOPED_ROOT}, calls))

        result = pull_android(ANDROID_CFG, tmp_path, tmp_path / "out", clean=True)

        assert [p[-2] for p in _pulls(calls)] == [f"{SCOPED_ROOT}/."]
        assert (tmp_path / "out" / "android" / FIXED_STAMP / "shot.png").is_file()
        assert _rms(calls) == [["adb", "shell", "rm", "-rf", SCOPED_ROOT]]
        assert result.skipped == []

    def test_legacy_root_is_not_even_read_when_the_scoped_mirror_exists(self, tmp_path, monkeypatch):
        # A 1.8.9 driver wrote the scoped dir, so whatever is flat in the legacy
        # root is other apps' (or pre-upgrade leftovers): not this app's business.
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake(
            {SCOPED_ROOT, TMP_ROOT}, calls,
            listings={TMP_ROOT: "com.example.app\ncom.other.app\nOldSuite\n"}))

        pull_android(ANDROID_CFG, tmp_path, tmp_path / "out", clean=True)

        assert [p[-2] for p in _pulls(calls)] == [f"{SCOPED_ROOT}/."]
        assert not any(c[-1] == TMP_ROOT for c in calls if "ls" in c)
        assert _rms(calls) == [["adb", "shell", "rm", "-rf", SCOPED_ROOT]]

    def test_legacy_root_is_pulled_suite_by_suite_leaving_other_apps_scoped_dirs(self, tmp_path, monkeypatch):
        # Pre-1.8.9 driver on the device: its suites sit flat next to a newer
        # app's scoped dir. The scoped dir is the OTHER app's — it must not move.
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake(
            {TMP_ROOT}, calls,
            listings={TMP_ROOT: "LoginSmokeTest\ncom.other.app\nProfiling_Resume\n"}))
        out = tmp_path / "out"

        result = pull_android(ANDROID_CFG, tmp_path, out)

        assert sorted(p[-2] for p in _pulls(calls)) == [
            f"{TMP_ROOT}/LoginSmokeTest", f"{TMP_ROOT}/Profiling_Resume"]
        stamp_dir = out / "android" / FIXED_STAMP
        assert (stamp_dir / "LoginSmokeTest" / "shot.png").is_file()
        assert (stamp_dir / "Profiling_Resume" / "shot.png").is_file()
        assert not (stamp_dir / "com.other.app").exists()
        assert len(result.files) == 4
        assert any("com.other.app" in s and "alone" in s for s in result.skipped)
        assert any("no app dimension" in s and "< 1.8.9" in s for s in result.skipped)

    def test_clean_never_removes_the_legacy_root(self, tmp_path, monkeypatch):
        # This is the exact action that deleted the other app's 74 directories.
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake(
            {SDCARD_ROOT, TMP_ROOT}, calls, listings={TMP_ROOT: "LoginSmokeTest\n"}))

        result = pull_android(ANDROID_CFG, tmp_path, tmp_path / "out", clean=True)

        assert _rms(calls) == [["adb", "shell", "rm", "-rf", SDCARD_ROOT]]
        assert not any(c[-1] == TMP_ROOT for c in _rms(calls))
        assert any("not cleaned" in s and "upgrade the driver" in s for s in result.skipped)

    def test_legacy_root_holding_only_other_apps_yields_nothing(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(artifacts, "_run", make_adb_fake(
            {TMP_ROOT}, calls, listings={TMP_ROOT: "com.other.app\ncom.third.app\n"}))

        result = pull_android(ANDROID_CFG, tmp_path, tmp_path / "out", clean=True)

        assert _pulls(calls) == []
        assert _rms(calls) == []
        assert result.files == []
        assert result.stamp_dir is None
        assert not (tmp_path / "out").exists()  # no empty stamp dir left behind
        assert any("left 2 other app(s)" in s for s in result.skipped)
        assert any("no jsonui-artifacts" in s and "com.example.app" in s for s in result.skipped)

    def test_legacy_entry_classification(self):
        suites, packages = artifacts._legacy_entries(
            "LoginSmokeTest\ncom.other.app\n\nProfiling_Resume\ncom.example.app.dev\nv1.2\n")
        assert suites == ["LoginSmokeTest", "Profiling_Resume", "v1.2"]
        assert packages == ["com.other.app", "com.example.app.dev"]
        # a bare suite name with no dot is never mistaken for a package
        assert artifacts._legacy_entries("Suite\n") == (["Suite"], [])


# -- tests: status / symlink / exit codes ------------------------------------------

class TestStatus:
    @pytest.fixture(autouse=True)
    def _pin_adb(self, monkeypatch):
        monkeypatch.setattr(artifacts, "find_adb", lambda cfg=None: "/fake/adb")

    def test_resolved_shape_and_existing_files(self, tmp_path):
        cfg = {"artifacts": {
            "dir": "my-artifacts",
            "ios": {"xcresult": str(tmp_path / "*.xcresult")},
            "android": {"appId": "com.example.app", "serial": "sn1"},
        }}
        xc = make_xcresult(tmp_path)
        existing = tmp_path / "my-artifacts" / "android" / FIXED_STAMP / "shot.png"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"x")

        info = status(cfg, tmp_path)

        assert info["artifactsDir"] == str((tmp_path / "my-artifacts").resolve())
        assert info["ios"]["xcresult"] == str(xc)
        assert info["android"] == {"appId": "com.example.app", "serial": "sn1",
                                   "adb": "/fake/adb"}
        assert info["existing"] == [str(existing.resolve())]

    def test_defaults_when_unconfigured(self, tmp_path):
        info = status({}, tmp_path)
        assert info["artifactsDir"] == str((tmp_path / "tests/artifacts").resolve())
        assert info["android"] == {"appId": None, "serial": None, "adb": "/fake/adb"}
        assert info["existing"] == []


class TestFindAdb:
    """Resolution order: config explicit > PATH > env SDK > OS-default SDK."""

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        # No PATH hit, no env SDKs, HOME without default SDK — unless a test adds them.
        monkeypatch.setattr(artifacts.shutil, "which", lambda name: None)
        monkeypatch.delenv("ANDROID_HOME", raising=False)
        monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
        monkeypatch.setattr(artifacts.Path, "home", staticmethod(lambda: tmp_path / "home"))

    @staticmethod
    def _make_adb(base: Path) -> Path:
        adb = base / "platform-tools" / "adb"
        adb.parent.mkdir(parents=True, exist_ok=True)
        adb.write_text("#!/bin/sh\n")
        adb.chmod(0o755)
        return adb

    def test_explicit_config_wins(self, tmp_path):
        adb = self._make_adb(tmp_path / "sdk")
        assert artifacts.find_adb({"adb": str(adb)}) == str(adb)

    def test_explicit_config_missing_file_is_none_not_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(artifacts.shutil, "which", lambda name: "/on/path/adb")
        assert artifacts.find_adb({"adb": str(tmp_path / "nope/adb")}) is None

    def test_path_hit(self, monkeypatch):
        monkeypatch.setattr(artifacts.shutil, "which", lambda name: "/on/path/adb")
        assert artifacts.find_adb({}) == "/on/path/adb"

    def test_android_home_fallback(self, tmp_path, monkeypatch):
        adb = self._make_adb(tmp_path / "sdk")
        monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "sdk"))
        assert artifacts.find_adb({}) == str(adb)

    def test_macos_default_location_fallback(self, tmp_path):
        adb = self._make_adb(tmp_path / "home" / "Library/Android/sdk")
        assert artifacts.find_adb({}) == str(adb)

    def test_nothing_found_returns_none(self):
        assert artifacts.find_adb({}) is None


class TestLatestSymlink:
    def test_created_and_replaced(self, tmp_path):
        out = tmp_path / "out"
        a = out / "ios" / "20260101-000000"
        b = out / "ios" / "20260102-000000"
        a.mkdir(parents=True)
        b.mkdir(parents=True)

        update_latest_symlink(out, "ios", a)
        link = out / "ios" / "latest"
        assert link.is_symlink()
        assert os.readlink(link) == a.name

        update_latest_symlink(out, "ios", b)
        assert os.readlink(link) == b.name

    def test_pull_ios_updates_latest(self, tmp_path, monkeypatch):
        xc = make_xcresult(tmp_path)
        monkeypatch.setattr(artifacts, "_run", make_xcrun_fake(["a.png"], manifest=None))
        cfg = {"artifacts": {"ios": {"xcresult": str(xc)}}}
        out = tmp_path / "out"

        pull_ios(cfg, tmp_path, out)

        assert os.readlink(out / "ios" / "latest") == stamp_of(xc)


class TestPullExitCode:
    def test_all_is_best_effort_zero(self):
        results = [PullResult("ios", skipped=["no .xcresult bundle found"]),
                   PullResult("android", skipped=["adb not found on PATH"])]
        assert pull_exit_code("all", results) == 0

    def test_single_platform_with_files_is_zero(self):
        assert pull_exit_code("ios", [PullResult("ios", files=["/a.png"])]) == 0

    def test_single_platform_skipped_entirely_is_one(self):
        assert pull_exit_code("ios", [PullResult("ios", skipped=["reason"])]) == 1
        assert pull_exit_code("android", [PullResult("android")]) == 1


class TestCollectFiles:
    def test_recursive_absolute_sorted(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "2.png").write_bytes(b"x")
        (tmp_path / "1.mp4").write_bytes(b"x")
        assert collect_files(tmp_path) == [
            str((tmp_path / "1.mp4").resolve()),
            str((tmp_path / "a" / "2.png").resolve()),
        ]

    def test_missing_dir(self, tmp_path):
        assert collect_files(tmp_path / "nope") == []


class TestResolveOutRoot:
    def test_default_relative_to_project_root(self, tmp_path):
        assert resolve_out_root({}, tmp_path) == (tmp_path / "tests/artifacts").resolve()

    def test_override_wins(self, tmp_path):
        out = resolve_out_root({"artifacts": {"dir": "cfg-dir"}}, tmp_path, override="cli-dir")
        assert out == (tmp_path / "cli-dir").resolve()


# -- tests: argv-level CLI ---------------------------------------------------------

def _write_config(tmp_path, artifacts_block):
    cfg_file = tmp_path / "jui.config.json"
    cfg_file.write_text(json.dumps({"test": {"artifacts": artifacts_block}}), encoding="utf-8")
    return cfg_file


class TestCliArgv:
    def test_pull_json_ios(self, tmp_path, monkeypatch, capsys):
        xc = make_xcresult(tmp_path)
        cfg_file = _write_config(tmp_path, {"dir": "arts"})
        monkeypatch.setattr(artifacts, "_run",
                            make_xcrun_fake(["1_shot.png", "2_video.mp4", "3_blob.dat"]))

        with patch.object(sys, "argv", [
                "jsonui-test", "artifacts", "pull", "--json", "--platform", "ios",
                "--xcresult", str(xc), "--config", str(cfg_file)]):
            rc = main()

        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert set(data.keys()) == {"outputDir", "files", "skipped"}
        assert data["outputDir"] == str((tmp_path / "arts").resolve())
        assert len(data["files"]) == 3
        assert all(os.path.isabs(f) for f in data["files"])
        assert data["skipped"] == []

    def test_pull_json_single_platform_skip_exits_one(self, tmp_path, monkeypatch, capsys):
        cfg_file = _write_config(tmp_path, {"dir": "arts"})
        monkeypatch.setattr(artifacts, "_run", make_xcrun_fake([]))

        with patch.object(sys, "argv", [
                "jsonui-test", "artifacts", "pull", "--json", "--platform", "ios",
                "--xcresult", str(tmp_path / "none" / "*.xcresult"),
                "--config", str(cfg_file)]):
            rc = main()

        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["files"] == []
        assert any(s.startswith("ios:") for s in data["skipped"])

    def test_pull_android_missing_app_id_is_config_error(self, tmp_path, capsys):
        cfg_file = _write_config(tmp_path, {"dir": "arts"})

        with patch.object(sys, "argv", [
                "jsonui-test", "artifacts", "pull", "--platform", "android",
                "--config", str(cfg_file)]):
            rc = main()

        assert rc == 1
        assert "test.artifacts.android.appId" in capsys.readouterr().err

    def test_alias_a_and_out_override(self, tmp_path, monkeypatch, capsys):
        xc = make_xcresult(tmp_path)
        cfg_file = _write_config(tmp_path, {"dir": "arts"})
        monkeypatch.setattr(artifacts, "_run", make_xcrun_fake(["a.png"], manifest=None))
        out_dir = tmp_path / "elsewhere"

        with patch.object(sys, "argv", [
                "jsonui-test", "a", "pull", "--json", "--platform", "ios",
                "--xcresult", str(xc), "--out", str(out_dir),
                "--config", str(cfg_file)]):
            rc = main()

        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["outputDir"] == str(out_dir.resolve())
        assert data["files"] and all(f.startswith(str(out_dir.resolve())) for f in data["files"])

    def test_status_json(self, tmp_path, capsys):
        cfg_file = _write_config(
            tmp_path, {"dir": "arts", "android": {"appId": "com.example.app"}})

        with patch.object(sys, "argv", [
                "jsonui-test", "artifacts", "status", "--json", "--config", str(cfg_file)]):
            rc = main()

        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert set(data.keys()) == {"artifactsDir", "ios", "android", "web", "existing"}
        assert data["artifactsDir"] == str((tmp_path / "arts").resolve())
        assert data["android"]["appId"] == "com.example.app"
        assert data["existing"] == []

    def test_bare_artifacts_prints_help(self, tmp_path, capsys):
        with patch.object(sys, "argv", ["jsonui-test", "artifacts"]):
            rc = main()
        assert rc == 0
        assert "pull" in capsys.readouterr().out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestExportSuffixStrip:
    """xcresulttool appends `_<n>_<UUID>` on export; filenames should not keep it."""

    def test_strips_index_uuid_suffix(self):
        from jsonui_test_cli.artifacts import _strip_export_suffix
        assert _strip_export_suffix(
            "Failure_artifact_probe_fail_case_0_FCBD85F8-B89A-44E9-A4F6-2B129EC95F36.png"
        ) == "Failure_artifact_probe_fail_case.png"

    def test_leaves_plain_names_alone(self):
        from jsonui_test_cli.artifacts import _strip_export_suffix
        assert _strip_export_suffix("launch_screen.png") == "launch_screen.png"
        assert _strip_export_suffix("Screen Recording 2026-07-16.mp4") == "Screen Recording 2026-07-16.mp4"

    def test_never_returns_empty_stem(self):
        from jsonui_test_cli.artifacts import _strip_export_suffix
        # a name that IS only the suffix keeps its original stem
        assert _strip_export_suffix("_0_FCBD85F8-B89A-44E9-A4F6-2B129EC95F36.png") == "_0_FCBD85F8-B89A-44E9-A4F6-2B129EC95F36.png"


# -- tests: Web ---------------------------------------------------------------

class TestPullWeb:
    @staticmethod
    def _make_sources(tmp_path):
        tr = tmp_path / "test-results"
        bucket = tr / "probe-artifact-probe-fail-case-chromium"
        bucket.mkdir(parents=True)
        (bucket / "video.webm").write_bytes(b"WEBM")
        (bucket / "error-context.md").write_text("ctx")
        shots = tmp_path / "screenshots"
        shots.mkdir()
        (shots / "failure_login_case1.png").write_bytes(b"PNG")
        return tr, shots

    def test_organizes_playwright_buckets_and_driver_screenshots(self, tmp_path, monkeypatch):
        from jsonui_test_cli.artifacts import pull_web
        self._make_sources(tmp_path)
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)
        out = tmp_path / "out"

        result = pull_web({}, tmp_path, out)

        stamp = out / "web" / FIXED_STAMP
        assert (stamp / "probe-artifact-probe-fail-case-chromium" / "recordings" / "video.webm").is_file()
        assert (stamp / "probe-artifact-probe-fail-case-chromium" / "other" / "error-context.md").is_file()
        assert (stamp / "screenshots" / "failure_login_case1.png").is_file()
        assert len(result.files) == 3
        assert result.stamp_dir == str(stamp)
        assert (out / "web" / "latest").is_symlink()

    def test_missing_sources_are_skipped_not_raised(self, tmp_path, monkeypatch):
        from jsonui_test_cli.artifacts import pull_web
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)

        result = pull_web({}, tmp_path, tmp_path / "out")

        assert result.files == []
        assert result.stamp_dir is None
        assert len(result.skipped) == 2

    def test_clean_removes_source_dirs(self, tmp_path, monkeypatch):
        from jsonui_test_cli.artifacts import pull_web
        tr, shots = self._make_sources(tmp_path)
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)

        pull_web({}, tmp_path, tmp_path / "out", clean=True)

        assert not tr.exists()
        assert not shots.exists()

    def test_custom_dirs_from_config(self, tmp_path, monkeypatch):
        from jsonui_test_cli.artifacts import pull_web
        tr = tmp_path / "webapp" / "pw-out"
        (tr / "b1").mkdir(parents=True)
        (tr / "b1" / "video.webm").write_bytes(b"W")
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)
        cfg = {"artifacts": {"web": {"testResults": "webapp/pw-out",
                                     "screenshotDir": "webapp/shots"}}}

        result = pull_web(cfg, tmp_path, tmp_path / "out")

        assert any(f.endswith("b1/recordings/video.webm") for f in result.files)
        assert any("webapp/shots" in s for s in result.skipped)

    def test_root_level_files_ignored(self, tmp_path, monkeypatch):
        from jsonui_test_cli.artifacts import pull_web
        tr, _ = self._make_sources(tmp_path)
        (tr / ".last-run.json").write_text("{}")
        monkeypatch.setattr(artifacts, "_now_stamp", lambda: FIXED_STAMP)

        result = pull_web({}, tmp_path, tmp_path / "out")

        assert not any(".last-run" in f for f in result.files)
