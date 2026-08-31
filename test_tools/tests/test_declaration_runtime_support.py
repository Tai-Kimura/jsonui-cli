"""A declaration the installed driver does not read is caught at validate time.

The schema is the authoring side and the driver is the runtime, and they ship
as separate releases. Between jsonui-cli 1.7.32 (accepts `screenReady`) and
driver 1.8.4 (reads it) a project can write a declaration that validates green
and is then ignored.

Ignored is not neutral. `screenReady: 'none'` exists to say "do not wait for
this screen"; ignored, the default gate runs and the file waits fifteen
seconds for exactly the marker it declared it would not wait for, then fails
naming the screen. Nothing in that output points at the declaration. It is the
failure shape the value-checking in `screen.py` prevents within a release,
reappearing across releases.

The reporting lane had not hit it: they knew, from a message, that 1.8.4 was
required, and held the declaration back. That is a notification standing in
for a check, and it only works while someone remembers to send it.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.schema import KEY_DRIVER_REQUIREMENTS  # noqa: E402
from jsonui_test_cli.validation.runtime_support import (  # noqa: E402
    check_declarations,
    collect_declared_keys,
    installed_driver_version,
    parse_version,
)

REQ = {"screenReady": {"web": "1.8.4"}}


def with_driver(root: Path, version: str | None, at: Path | None = None) -> Path:
    if version is not None:
        pkg = (at or root) / "node_modules" / "jsonui-test-runner-web"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "package.json").write_text(
            json.dumps({"name": "jsonui-test-runner-web", "version": version}),
            encoding="utf-8")
    return root


def write_test(root: Path, name: str = "a.test.json", **extra) -> Path:
    path = root / name
    path.write_text(json.dumps({
        "type": "screen",
        "source": {"layout": "layouts/admin_reservations.json"},
        "metadata": {"name": "x"},
        "cases": [{"name": "c", "steps": []}],
        **extra,
    }), encoding="utf-8")
    return path


class TestVersionComparison:
    @pytest.mark.parametrize("older,newer", [
        ("1.8.3", "1.8.4"), ("1.8.9", "1.9.0"), ("1.9.0", "2.0.0"),
    ])
    def test_ordering(self, older, newer):
        assert parse_version(older) < parse_version(newer)

    def test_a_prerelease_counts_as_its_release(self):
        # Deliberate, and stated rather than left to be discovered: drivers
        # ship as plain X.Y.Z, so ordering `1.8.4-beta.1` before `1.8.4`
        # would only ever matter to someone testing an unreleased build,
        # for whom reding the run would be wrong.
        assert parse_version("1.8.4-beta.1") == parse_version("1.8.4")

    def test_equal_is_not_older(self):
        # The boundary that decides whether the exact required version reds.
        assert not parse_version("1.8.4") < parse_version("1.8.4")


class TestTheCheckFiresOnlyWhenItShould:
    def test_an_older_driver_is_an_error(self, tmp_path):
        with_driver(tmp_path, "1.8.3")
        declared = {"screenReady": [write_test(tmp_path, screenReady="none")]}
        errors, notes = check_declarations(declared, REQ, tmp_path)
        assert len(errors) == 1 and notes == []
        # Names the version found, the version needed, and the silence.
        assert "1.8.3" in errors[0] and "1.8.4" in errors[0]
        assert "without saying so" in errors[0]

    def test_the_required_version_passes(self, tmp_path):
        with_driver(tmp_path, "1.8.4")
        declared = {"screenReady": [write_test(tmp_path, screenReady="none")]}
        assert check_declarations(declared, REQ, tmp_path) == ([], [])

    def test_a_newer_driver_passes(self, tmp_path):
        with_driver(tmp_path, "1.9.0")
        declared = {"screenReady": [write_test(tmp_path, screenReady="none")]}
        assert check_declarations(declared, REQ, tmp_path) == ([], [])

    def test_no_declaration_means_no_finding_even_on_an_old_driver(self, tmp_path):
        # The check is about declarations, not about driver currency. Reding
        # every project on an old driver would be a different feature, and a
        # wrong one.
        with_driver(tmp_path, "1.8.2")
        assert check_declarations({}, REQ, tmp_path) == ([], [])


class TestWhatCannotBeMeasuredIsSaid:
    def test_an_unreadable_driver_warns_rather_than_guessing(self, tmp_path):
        # No node_modules at all: tests may be run from elsewhere. Assuming
        # "absent means old" would red those projects; assuming "absent means
        # fine" would be the silence this check exists to remove.
        declared = {"screenReady": [write_test(tmp_path, screenReady="none")]}
        errors, notes = check_declarations(declared, REQ, tmp_path)
        assert errors == [] and len(notes) == 1
        assert "could not be read" in notes[0]
        assert "not checked" in notes[0]

    def test_a_hoisted_node_modules_is_found(self, tmp_path):
        # A monorepo installs above the package that declares the dependency.
        # Missing it would turn every such project into the warning above,
        # which is how a check stops being read.
        workspace = tmp_path / "packages" / "admin"
        workspace.mkdir(parents=True)
        with_driver(workspace, "1.8.3", at=tmp_path)
        declared = {"screenReady": [write_test(workspace, screenReady="none")]}
        errors, _ = check_declarations(declared, REQ, workspace)
        assert len(errors) == 1

    def test_a_malformed_manifest_is_unreadable_not_old(self, tmp_path):
        pkg = tmp_path / "node_modules" / "jsonui-test-runner-web"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text("{ not json", encoding="utf-8")
        assert installed_driver_version("web", tmp_path) is None


class TestKeyCollection:
    def test_only_declared_keys_are_reported(self, tmp_path):
        a = write_test(tmp_path, "a.test.json", screenReady="none")
        write_test(tmp_path, "b.test.json")
        found = collect_declared_keys([a, tmp_path / "b.test.json"],
                                      {"screenReady"})
        assert found == {"screenReady": [a]}

    def test_unreadable_files_do_not_crash_the_check(self, tmp_path):
        bad = tmp_path / "bad.test.json"
        bad.write_text("{ not json", encoding="utf-8")
        # Malformed files are the file validator's finding, reported there
        # with a position. Raising here would replace it with a stack trace.
        assert collect_declared_keys([bad], {"screenReady"}) == {}


class TestTheRequirementComesFromTheSchema:
    def test_screen_ready_is_declared_with_its_requirement(self):
        # Guards the class, not the instance: the requirement is data beside
        # the key in the canonical schema, so adding a key means stating its
        # runtime requirement. test_schema_drift pins both directions.
        assert KEY_DRIVER_REQUIREMENTS["screenReady"] == {"web": "1.8.4"}
