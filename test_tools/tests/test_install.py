"""Tests for the flatten-install phase of `jsonui-test validate`."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.install import resolve_targets, flatten_install, InstallReport
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
