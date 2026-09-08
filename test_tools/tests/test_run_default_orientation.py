"""A run can declare the orientation it runs in, and the declaration travels.

The feature has four seams and each of them fails silently on its own, in the
same direction — green, in the wrong orientation:

* the top-level `orientation` key in a test file (rejected as unknown before
  this landed, so a file declaring it did not run at all);
* the value, which nothing checks at run time — an orientation the driver does
  not recognise leaves the device as it booted and every assertion still
  passes;
* `test.orientation` in config, which is a table keyed by tier rather than a
  resolved value, because one installed bundle is executed by four lanes;
* the sidecar that carries that table onto the device, which is written on
  every install INCLUDING when it declares nothing, so that "no default
  declared" and "installed by an older CLI" stay two observations.

The arms below are grouped by seam and each names which of those four it is
about, because a green run of this file is the only thing standing between a
typo in config and a tablet lane that reports success in portrait.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import main
from jsonui_test_cli.report import (
    VALID_RESULT_KEYS,
    VALID_RESULT_ORIENTATIONS,
    validate_results_data,
)
from jsonui_test_cli.install import flatten_install
from jsonui_test_cli.run_defaults import (
    SIDECAR_ALWAYS,
    SIDECAR_FILENAME,
    SIDECAR_SCHEMA_VERSION,
    build_sidecar,
    validate_orientation_defaults,
)
from jsonui_test_cli.schema import (
    KEY_DRIVER_REQUIREMENTS,
    ORIENTATION_DEFAULT_TIERS,
    RESPONSIVE_BUCKETS,
    RESPONSIVE_ORIENTATIONS,
)
from jsonui_test_cli.validation.models import ValidationResult
from jsonui_test_cli.validation.orientation import validate_orientation_field


def _screen(**extra):
    data = {
        "type": "screen",
        "source": {"layout": "login.json"},
        "metadata": {"screen": "login", "description": "d"},
        "cases": [{"name": "c", "description": "d",
                   "steps": [{"assert": "visible", "id": "t"}]}],
    }
    data.update(extra)
    return data


def _flow(**extra):
    data = {
        "type": "flow",
        "metadata": {"description": "d"},
        "steps": [{"action": "wait", "ms": 10, "screen": "login"}],
    }
    data.update(extra)
    return data


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _validate(tmp_path, data, name="a.test.json", config=None):
    """Run the real `validate` over one file. Returns (exit code, output)."""
    _write(tmp_path / name, data)
    argv = ["jsonui-test", "validate", str(tmp_path / name)]
    if config is not None:
        cfg = tmp_path / "jui.config.json"
        cfg.write_text(json.dumps(config), encoding="utf-8")
        argv += ["--config", str(cfg)]
    else:
        argv += ["--no-install"]
    return argv


# --- seam 1: the key is accepted at the top level of both test types --------

class TestTheKeyIsAccepted:
    """Before this landed, `orientation` was an unknown top-level key.

    That is the arm that would go green again for the wrong reason if the
    constant were removed but the schema kept, so it asserts on the actual
    validator rather than on the constant list.
    """

    @pytest.mark.parametrize("data,name", [
        (_screen(orientation="landscape"), "s.test.json"),
        (_flow(orientation="portrait"), "f.test.json"),
    ])
    def test_declaring_an_orientation_validates(self, tmp_path, capsys, data, name):
        argv = _validate(tmp_path, data, name)
        sys.argv = argv
        assert main() == 0
        out = capsys.readouterr().out
        assert "Unknown top-level key: orientation" not in out

    def test_it_is_not_confused_for_the_other_types_key(self, tmp_path, capsys):
        """The two key lists are separate, and a key in BOTH must not trip the
        'wrong test type' message that a key in only one produces."""
        sys.argv = _validate(tmp_path, _flow(orientation="landscape"), "f.test.json")
        assert main() == 0
        out = capsys.readouterr().out
        assert "should this file be type" not in out


# --- seam 2: the value is checked, on both faces ----------------------------

class TestTheValueIsChecked:

    def test_a_misspelled_orientation_is_an_error(self, tmp_path, capsys):
        sys.argv = _validate(tmp_path, _screen(orientation="Landscape"))
        assert main() == 1
        assert "Unknown orientation: 'Landscape'" in capsys.readouterr().out

    def test_a_non_string_is_an_error(self, tmp_path, capsys):
        sys.argv = _validate(tmp_path, _flow(orientation=["landscape"]), "f.test.json")
        assert main() == 1
        assert "'orientation' must be a string" in capsys.readouterr().out

    def test_both_faces_use_one_value_list(self):
        """Three sites name this word — the action, the responsive constraint,
        and now the top-level key. They share `RESPONSIVE_ORIENTATIONS`; a
        fourth spelling would be drift below where the schema gate can see."""
        for value in RESPONSIVE_ORIENTATIONS:
            result = ValidationResult(file_path="p")
            validate_orientation_field(value, "p", result)
            assert result.errors == []


# --- seam 2b: the declaration is version-gated ------------------------------

class TestTheDeclarationIsVersionGated:
    """An older driver ignores a key it does not know, silently.

    `runtime_support` exists for exactly that, and it only covers keys that
    appear in KEY_DRIVER_REQUIREMENTS — so a key added without an entry is
    added without the guard, and nothing says so.
    """

    def test_orientation_states_a_driver_requirement(self):
        assert "orientation" in KEY_DRIVER_REQUIREMENTS

    def test_all_three_drivers_are_named(self):
        """web included. The ticket is about iOS and Android tablets, but no
        driver applies a run-scoped default today, so naming only two would
        leave 'web ignores the default' true and unstated."""
        assert set(KEY_DRIVER_REQUIREMENTS["orientation"]) == {"ios", "android", "web"}

    def test_validate_says_so_when_the_version_cannot_be_read(self, tmp_path, capsys):
        """iOS and Android versions are not readable from a project tree, so
        this is a note rather than a gate — and the note is the point: it is
        the only place the run says the declaration may be ignored."""
        sys.argv = _validate(tmp_path, _screen(orientation="landscape"))
        assert main() == 0
        out = capsys.readouterr().out
        assert "requires the ios driver" in out
        assert "ignores the declaration silently" in out


# --- seam 3: the config table -----------------------------------------------

class TestTheConfigTable:

    def test_tiers_exclude_every_orientation_bearing_bucket(self):
        """`regular-landscape: portrait` is a contradiction: the bucket
        already names an orientation. Derived from RESPONSIVE_BUCKETS so a
        new tier is declarable without a second edit; pinned here so a bucket
        added with a different spelling is noticed instead of absorbed."""
        assert ORIENTATION_DEFAULT_TIERS == ["compact", "medium", "regular"]
        assert all("landscape" not in t for t in ORIENTATION_DEFAULT_TIERS)
        assert set(ORIENTATION_DEFAULT_TIERS) < set(RESPONSIVE_BUCKETS)

    def test_a_valid_table_reports_nothing(self):
        assert validate_orientation_defaults(
            {"orientation": {"regular": "landscape", "compact": "portrait"}}) == []

    def test_absent_is_not_an_error(self):
        assert validate_orientation_defaults({}) == []

    def test_an_unknown_tier_is_reported(self):
        errors = validate_orientation_defaults(
            {"orientation": {"regular-landscape": "portrait"}})
        assert len(errors) == 1
        assert "unknown tier 'regular-landscape'" in errors[0]

    def test_an_unknown_orientation_is_reported(self):
        errors = validate_orientation_defaults({"orientation": {"medium": "sideways"}})
        assert len(errors) == 1
        assert "unknown orientation 'sideways'" in errors[0]

    def test_a_scalar_is_reported(self):
        """A single value would be a device-independent-looking answer that is
        wrong for one of the two lanes sharing the bundle."""
        errors = validate_orientation_defaults({"orientation": "landscape"})
        assert len(errors) == 1
        assert "must be an object keyed by tier" in errors[0]

    def test_a_bad_table_fails_validate_and_blocks_the_install(self, tmp_path, capsys):
        """The install is gated on the error count, so this arm is what keeps
        an unrecognised tier off a device."""
        ios = tmp_path / "ios"
        config = {"test": {"orientation": {"regular": "sideways"},
                           "install": {"ios": {"target_dir": "ios"}}}}
        sys.argv = _validate(tmp_path, _screen(), config=config)
        assert main() == 1
        assert "test.orientation.regular" in capsys.readouterr().out
        assert not (ios / SIDECAR_FILENAME).exists()


# --- seam 4: the sidecar ----------------------------------------------------

class TestTheSidecar:

    def test_it_is_written_even_when_nothing_is_declared(self, tmp_path):
        """THE arm. A sidecar written only when a default exists puts 'nothing
        declared' and 'installed by a CLI too old to have the feature' back
        into one observation on the device — the distinction it exists for."""
        assert SIDECAR_ALWAYS
        src = _write(tmp_path / "a.test.json", _screen())
        ios = tmp_path / "ios"
        flatten_install([src], [("ios", ios)], sidecar=build_sidecar({}))
        written = json.loads((ios / SIDECAR_FILENAME).read_text(encoding="utf-8"))
        assert written == {"schemaVersion": SIDECAR_SCHEMA_VERSION, "orientation": {}}

    def test_every_target_gets_one(self, tmp_path):
        src = _write(tmp_path / "a.test.json", _screen())
        targets = [("ios", tmp_path / "ios"), ("android", tmp_path / "android")]
        report = flatten_install([src], targets,
                                 sidecar=build_sidecar({"orientation": {"regular": "landscape"}}))
        assert len(report.sidecars) == 2
        for _platform, dest in targets:
            assert json.loads((dest / SIDECAR_FILENAME).read_text())["orientation"] == {
                "regular": "landscape"}

    def test_the_stale_clean_does_not_count_it(self, tmp_path):
        """The clean globs `*.test.json` and this name does not match — but
        the two live in one directory, so the day that glob widens, this is
        what says so.

        Asserted on the REMOVED COUNT, not on the file existing: the sidecar
        is rewritten after the clean in the same call, so a clean that ate it
        would leave it on disk anyway and an existence check could never go
        red. Measured — the existence form of this arm survived widening the
        glob to `*.json`; this form does not."""
        src = _write(tmp_path / "a.test.json", _screen())
        ios = tmp_path / "ios"
        flatten_install([src], [("ios", ios)], clean=True, sidecar=build_sidecar({}))
        report = flatten_install([src], [("ios", ios)], clean=True,
                                 sidecar=build_sidecar({}))
        assert (ios / SIDECAR_FILENAME).exists()
        assert report.removed == 1, "the clean reached something besides the test file"

    def test_it_carries_the_table_not_a_resolved_value(self):
        """One bundle is executed by phone and tablet lanes both. A resolved
        orientation could be right for at most one of them."""
        built = build_sidecar({"orientation": {"compact": "portrait",
                                              "regular": "landscape"}})
        assert built["orientation"] == {"compact": "portrait", "regular": "landscape"}

    def test_an_invalid_value_never_reaches_the_device(self):
        """Belt to `validate`'s braces: the build drops what it cannot name,
        so a config that somehow skipped validation cannot put a value the
        driver has no branch for onto a device."""
        built = build_sidecar({"orientation": {"regular": "sideways",
                                              "bogus": "portrait"}})
        assert built["orientation"] == {}

    def test_validate_installs_it_from_config(self, tmp_path, capsys):
        config = {"test": {"testDir": ".",
                           "orientation": {"regular": "landscape"},
                           "install": {"ios": {"target_dir": "ios"}}}}
        sys.argv = _validate(tmp_path, _screen(), config=config)
        assert main() == 0
        written = json.loads((tmp_path / "ios" / SIDECAR_FILENAME).read_text())
        assert written == {"schemaVersion": 1, "orientation": {"regular": "landscape"}}
        assert SIDECAR_FILENAME in capsys.readouterr().out


# --- seam 5: the run reports which orientation it ACTUALLY ran in -----------

def _results(**case_extra):
    case = {"testName": "t", "caseName": "c", "status": "passed", "durationMs": 1}
    case.update(case_extra)
    return {"format": "jsonui-test-results", "version": 1, "platform": "ios",
            "suites": [{"suiteName": "s", "results": [case]}]}


class TestTheRunReportsTheOrientation:
    """Declared and observed are two fields because they can disagree.

    'portrait' resolves to `setOrientationNatural()` on Android, and a tablet
    whose natural orientation is landscape does not turn portrait. A run that
    asked for one orientation and executed in the other is therefore a real
    outcome — and with a single field it is an invisible one, because the
    single field would be the request and the report would assume it was
    honoured.
    """

    def test_both_fields_are_accepted(self):
        assert validate_results_data(
            _results(declaredOrientation="landscape",
                     observedOrientation="portrait"), "r") == []

    def test_neither_is_required(self):
        """Optional so that a driver older than the one that measures
        orientation keeps producing valid results."""
        assert validate_results_data(_results(), "r") == []

    def test_they_are_two_keys_not_one(self):
        for field in ("declaredOrientation", "observedOrientation"):
            assert field in VALID_RESULT_KEYS

    @pytest.mark.parametrize("field", ["declaredOrientation", "observedOrientation"])
    def test_an_unknown_value_is_rejected(self, field):
        errors = validate_results_data(_results(**{field: "sideways"}), "r")
        assert len(errors) == 1
        assert field in errors[0]

    def test_the_value_list_is_the_authoring_sides(self):
        """One word, one list. The results side naming its own would let a
        driver report an orientation no test file could ask for."""
        assert VALID_RESULT_ORIENTATIONS == RESPONSIVE_ORIENTATIONS
