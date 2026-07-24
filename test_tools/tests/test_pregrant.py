"""Tests for `jsonui-test pregrant` (iOS addMedia photos-add pre-grant)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import main, _test_uses_add_media_on_ios


class _FakeProc:
    returncode = 0
    stdout = ""
    stderr = ""


class TestPregrant:
    """pregrant: photos-add grant for iOS addMedia (scan → bundle id → simctl)."""

    def _write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _screen_with_add_media(self, case_platform=None, when=None):
        step = {"action": "addMedia", "paths": ["icon.png"]}
        if when is not None:
            step["when"] = when
        case = {"name": "c", "steps": [step]}
        if case_platform is not None:
            case["platform"] = case_platform
        return {"type": "screen", "metadata": {"name": "s"}, "cases": [case]}

    def test_no_add_media_is_a_noop(self, tmp_path, monkeypatch, capsys):
        self._write(tmp_path / "tests/screens/a/a.test.json",
                    {"type": "screen", "metadata": {"name": "a"},
                     "cases": [{"name": "c", "steps": [{"action": "back"}]}]})
        monkeypatch.chdir(tmp_path)
        with patch('sys.argv', ['jsonui-test', 'pregrant', 'tests']):
            assert main() == 0
        assert "nothing to grant" in capsys.readouterr().out

    def test_gated_off_ios_usage_is_a_noop(self, tmp_path, monkeypatch, capsys):
        self._write(tmp_path / "tests/screens/a/a.test.json",
                    self._screen_with_add_media(when={"platform": "android"}))
        self._write(tmp_path / "tests/screens/b/b.test.json",
                    self._screen_with_add_media(case_platform="web"))
        monkeypatch.chdir(tmp_path)
        with patch('sys.argv', ['jsonui-test', 'pregrant', 'tests']):
            assert main() == 0
        assert "nothing to grant" in capsys.readouterr().out

    def test_grants_photos_add_to_runner_id(self, tmp_path, monkeypatch):
        self._write(tmp_path / "tests/screens/a/a.test.json",
                    self._screen_with_add_media())
        monkeypatch.chdir(tmp_path)

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeProc()

        with patch('subprocess.run', side_effect=fake_run):
            with patch('sys.argv', ['jsonui-test', 'pregrant', 'tests',
                                    '--bundle-id', 'com.example.AppUITests',
                                    '--udid', 'FAKE-UDID']):
                assert main() == 0

        assert calls == [["xcrun", "simctl", "privacy", "FAKE-UDID",
                          "grant", "photos-add", "com.example.AppUITests.xctrunner"]]

    def test_bundle_id_from_config_and_xctrunner_passthrough(self, tmp_path, monkeypatch):
        self._write(tmp_path / "tests/screens/a/a.test.json",
                    self._screen_with_add_media())
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "test": {"install": {"ios": {
                "target_dir": "ios/GeneratedTests",
                "uitestBundleId": "com.example.AppUITests.xctrunner"}}}
        }), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeProc()

        with patch('subprocess.run', side_effect=fake_run):
            with patch('sys.argv', ['jsonui-test', 'pregrant', 'tests', '--udid', 'U1']):
                assert main() == 0

        # already-suffixed id is passed through, not doubled
        assert calls[-1][-1] == "com.example.AppUITests.xctrunner"

    def test_missing_bundle_id_errors(self, tmp_path, monkeypatch, capsys):
        self._write(tmp_path / "tests/screens/a/a.test.json",
                    self._screen_with_add_media())
        monkeypatch.chdir(tmp_path)
        with patch('sys.argv', ['jsonui-test', 'pregrant', 'tests', '--udid', 'U1']):
            assert main() == 1
        assert "bundle id" in capsys.readouterr().err

    def test_flow_setup_usage_detected(self, tmp_path, monkeypatch):
        self._write(tmp_path / "tests/flows/f/f.test.json",
                    {"type": "flow", "metadata": {"name": "f"},
                     "setup": [{"action": "addMedia", "paths": ["icon.png"]}],
                     "steps": [{"action": "back"}]})
        monkeypatch.chdir(tmp_path)

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeProc()

        with patch('subprocess.run', side_effect=fake_run):
            with patch('sys.argv', ['jsonui-test', 'pregrant', 'tests',
                                    '--bundle-id', 'x.y', '--udid', 'U1']):
                assert main() == 0
        assert len(calls) == 1


class TestAddMediaScan:
    """Unit spec for the iOS-reachability scan used by pregrant."""

    def test_nested_repeat_steps_detected(self):
        data = {"type": "screen", "metadata": {"name": "s"}, "cases": [
            {"name": "c", "steps": [
                {"action": "repeat", "times": 2, "steps": [
                    {"action": "addMedia", "paths": ["x.png"]}]}]}]}
        assert _test_uses_add_media_on_ios(data)

    def test_file_level_platform_android_excluded(self):
        data = {"type": "screen", "platform": "android",
                "metadata": {"name": "s"}, "cases": [
                    {"name": "c", "steps": [{"action": "addMedia", "paths": ["x.png"]}]}]}
        assert not _test_uses_add_media_on_ios(data)

    def test_platform_array_including_ios_detected(self):
        data = {"type": "screen", "platform": ["ios", "web"],
                "metadata": {"name": "s"}, "cases": [
                    {"name": "c", "steps": [{"action": "addMedia", "paths": ["x.png"]}]}]}
        assert _test_uses_add_media_on_ios(data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
