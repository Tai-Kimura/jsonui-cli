"""The iOS scaffolds in Swift 6 with `-default-isolation MainActor`, the reporting
consumer's setting (SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor): the configuration in which
the UseCase made in a default value compiled while `@Published let` and an
unassigned stored property did not.

⚠️ `-default-isolation` is swiftc 6.2+ and CI's compiler job runs an older one,
so ci.yml's python-suite ignores this file and dev-guide/release/run-suites.sh's
test_tools leg runs it — the owner test_unit_stubs_ios_typecheck.py has. It
fails under CI or JSONUI_REQUIRE_DEFAULT_ISOLATION without the flag, and skips
with the reason elsewhere.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests import _new_screen_stubs as ns
from tests.test_new_screen_stubs_compile import swift_errors
from tests.test_unit_stubs_ios_typecheck import _require_default_isolation


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    return ns.write_project(tmp_path_factory.mktemp("stubs") / "app")


def test_the_ios_scaffolds_compile_with_main_actor_isolation(project, tmp_path):
    _require_default_isolation(tmp_path)
    assert swift_errors(project, tmp_path, "-swift-version", "6", "-default-isolation", "MainActor") == []
