"""The pure half of `pregrant`'s Android arm.

The measured constraints these encode: a granted runtime permission cannot
be denied from inside an instrumentation run, so deny baselines are made
pre-instrumentation, and the three-way judgment (revoke / vacuously
satisfied / cannot determine) exists so an unrelated pm failure can never
read as a vacuously-satisfied deny.
"""

from jsonui_test_cli.cli import (
    _classify_deny_revokes,
    _requested_permissions_from_dumpsys,
    _test_android_deny_permissions,
)
from jsonui_test_cli.schema import ANDROID_PERMISSION_MAP


def _screen(launch=None, platform=None):
    data = {
        "type": "screen",
        "source": {"layout": "x"},
        "metadata": {"name": "x"},
        "cases": [],
    }
    if launch is not None:
        data["launch"] = launch
    if platform is not None:
        data["platform"] = platform
    return data


class TestDenyScan:
    def test_collects_only_deny_values(self):
        got = _test_android_deny_permissions(_screen(
            {"permissions": {"camera": "deny", "microphone": "allow",
                             "location": "unset", "contacts": "deny"}}))
        assert got == {"camera", "contacts"}

    def test_ios_only_test_contributes_nothing(self):
        launch = {"permissions": {"camera": "deny"}}
        assert _test_android_deny_permissions(_screen(launch, platform=["ios"])) == set()
        assert _test_android_deny_permissions(_screen(launch, platform="ios")) == set()
        # android-reachable spellings all contribute
        assert _test_android_deny_permissions(_screen(launch, platform="all")) == {"camera"}
        assert _test_android_deny_permissions(_screen(launch, platform=["ios", "android"])) == {"camera"}

    def test_absent_launch_or_permissions_is_empty(self):
        assert _test_android_deny_permissions(_screen()) == set()
        assert _test_android_deny_permissions(_screen({"clearState": True})) == set()
        assert _test_android_deny_permissions("not a dict") == set()


class TestThreeWayJudgment:
    def test_requested_goes_to_revoke_unrequested_is_vacuous(self):
        to_revoke, vacuous = _classify_deny_revokes(
            {"camera", "contacts"},
            {"android.permission.CAMERA"},
            ANDROID_PERMISSION_MAP)
        assert to_revoke == [("camera", "android.permission.CAMERA")]
        assert vacuous == [("contacts", "android.permission.READ_CONTACTS")]

    def test_unknown_name_is_skipped_like_the_driver(self):
        to_revoke, vacuous = _classify_deny_revokes(
            {"chronoscope"}, {"android.permission.CAMERA"}, ANDROID_PERMISSION_MAP)
        assert to_revoke == [] and vacuous == []


class TestDumpsysParse:
    DUMP = """Packages:
  Package [com.example.app] (abc123):
    userId=10219
    requested permissions:
      android.permission.CAMERA
      android.permission.READ_CONTACTS
    install permissions:
      android.permission.INTERNET: granted=true
"""

    def test_reads_the_requested_section(self):
        got = _requested_permissions_from_dumpsys(self.DUMP, "com.example.app")
        assert got == {"android.permission.CAMERA", "android.permission.READ_CONTACTS"}

    def test_missing_package_is_none_not_empty(self):
        # None is the loud-fail signal: nothing was read about this app, so
        # nothing may be called vacuously satisfied.
        assert _requested_permissions_from_dumpsys("garbage", "com.example.app") is None
        assert _requested_permissions_from_dumpsys(self.DUMP, "com.other.app") is None

    def test_package_without_section_is_an_empty_determination(self):
        text = "Packages:\n  Package [com.example.app] (abc):\n    userId=1\n"
        assert _requested_permissions_from_dumpsys(text, "com.example.app") == set()


def test_map_covers_every_schema_permission_name():
    # The schema's enum is the declared surface; every declarable name must
    # map (the driver's extra aliases, e.g. storage, may exceed it).
    schema_names = {"camera", "microphone", "location", "notifications",
                    "photos", "contacts", "calendar", "bluetooth"}
    assert schema_names <= set(ANDROID_PERMISSION_MAP)
